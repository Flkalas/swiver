"""Behavioral R0/MBR CPU with sequential execution on one shared memory bus.

Each ``step`` performs one SYS. Fetch and execute never overlap, and every
counted SYS performs at most one real byte memory access. Arithmetic remains
a functional abstraction; this is not a structural ALU or hardware timing test.
"""

from __future__ import annotations

from simulators.cyclesim.blocks.cpld import CpldDp
from simulators.cyclesim.blocks.fetch import Abs16HiReg, FlgReg, IrReg, MbrReg, MemArray, PcReg
from simulators.cyclesim.blocks.return_stack import RP_CELL, STACK_BASE, STACK_TOP, ReturnStack
from simulators.cyclesim.data.isa import (
    OP_ADD, OP_BEQ, OP_CALL, OP_CMP, OP_HALT, OP_JMP, OP_LDA, OP_LDIO,
    OP_RET, OP_STA, OP_STA16, OP_STIO,
)
from simulators.cyclesim.data.sequential import BusAccess, SequentialState, StageActivity, SysTrace, control_for


class CpuM3b:
    """R0-only CPU. ``state`` names the next pending real operation.

    ``last_trace.state`` names the completed SYS, including inserted WAITs.
    The next opcode can be fetched only after the current instruction retires.
    """

    def __init__(self) -> None:
        self.pc = PcReg()
        self.ir = IrReg()
        self.mbr = MbrReg()
        self.abs16_hi = Abs16HiReg()
        self.flg = FlgReg()
        self.mem = MemArray()
        # Retained for callers inspecting/seeding a stack outside counted SYS.
        self.return_stack = ReturnStack(self.mem)
        self.cpld_dp = CpldDp()
        self.gpr = self.cpld_dp
        self.trace: list[SysTrace] = []
        self.reset(pc=0)

    def reset(self, pc: int | None = None, *, from_vector: bool = False) -> None:
        """Initialize the model without counted SYS or a hardware reset FSM.

        Vector reads are an explicit, uncounted setup abstraction. An explicit
        ``from_vector`` reads the current map's vector; omitted PC retains the
        existing convenience of using an installed ROM vector, otherwise zero.
        """
        if from_vector:
            pc = self.mem.sys.reset_vector()
        elif pc is None:
            has_vector = 0xFFFC in self.mem.sys.rom or 0xFFFD in self.mem.sys.rom
            pc = self.mem.sys.reset_vector() if has_vector else 0
        self.pc.pc = pc & 0xFFFF
        self.halted = False
        self.fault: str | None = None
        self.sys_index = 0
        self.state = SequentialState.FETCH_OPCODE
        self.trace.clear()
        self.last_trace: SysTrace | None = None
        self.current_op = 0
        self._operand_byte = self._operand_len = 0
        self._stack_rp = self._stack_next_rp = self._stack_addr = 0
        self._stack_return = self._stack_target = 0
        self._wait_next = False
        self._trace_fetch: dict[str, int | bool] = {}
        self.cpld_dp.regs = [0]
        self.flg.z = self.flg.c = False
        self.ir.ir = self.mbr.mbr = self.abs16_hi.hi = 0

    def _eff_addr(self) -> int:
        from simulators.cyclesim.blocks.mem_decode import MAILBOX_BASE
        if self.current_op in (OP_LDIO, OP_STIO):
            return MAILBOX_BASE | self.mbr.mbr
        if self.current_op == OP_STA16:
            return self.current_operand16
        return self.mbr.mbr

    def _read(self, addr: int) -> BusAccess:
        addr &= 0xFFFF
        return BusAccess("read", addr, self.mem.read(addr) & 0xFF)

    def _write(self, addr: int, value: int) -> BusAccess:
        addr, value = addr & 0xFFFF, value & 0xFF
        self.mem.write(addr, value)
        return BusAccess("write", addr, value)

    def _ready_to_execute(self) -> None:
        ctl = control_for(self.current_op)
        if ctl.stack:
            self._stack_rp = self._stack_next_rp = self._stack_addr = 0
            self._stack_return = self.pc.pc
            self._stack_target = self.current_operand16 if self.current_op == OP_CALL else 0
            self.state = SequentialState.STACK_RP_LO
        elif self.current_op in (OP_LDA, OP_LDIO):
            self.state = SequentialState.MEM_READ
        elif ctl.memory:
            self.state = SequentialState.MEM_WRITE
        else:
            self.state = SequentialState.EXECUTE

    def _retire(self) -> None:
        if not self.halted:
            self.state = SequentialState.FETCH_OPCODE

    def _execute(self) -> tuple[set[str], BusAccess | None]:
        op = self.current_op
        strobes = {"EXECUTE"}
        bus = None
        if op == OP_ADD:
            result = self.gpr.qa() + self.mbr.mbr
            self.gpr.regs[0] = result & 0xFF
            self.flg.z, self.flg.c = (result & 0xFF) == 0, result > 0xFF
            strobes |= {"Y_OE", "REG_WE", "FLG_WE", "ALU_ADD"}
        elif op == OP_CMP:
            result = (self.gpr.qa() - self.mbr.mbr) & 0x1FF
            self.flg.z, self.flg.c = (result & 0xFF) == 0, result < 0x100
            strobes |= {"FLG_WE", "ALU_CMP"}
        elif op in (OP_LDA, OP_LDIO):
            bus = self._read(self._eff_addr())
            self.gpr.regs[0] = bus.value
            strobes |= {"MEM_RD", "REG_WE"}
        elif op in (OP_STA, OP_STIO, OP_STA16):
            bus = self._write(self._eff_addr(), self.gpr.qa())
            strobes |= {"Y_OE", "MEM_WR"}
        elif op == OP_JMP or (op == OP_BEQ and self.flg.z):
            self.pc.pc = self.current_operand16
            strobes.add("PC_LOAD_EN")
        elif op == OP_HALT:
            self.halted = True
            strobes.add("HALT")
        elif control_for(op).name == "TRAP":
            strobes.add("TRAP")
        return strobes, bus

    def _stack_step(self) -> tuple[set[str], BusAccess, bool]:
        """Perform exactly one byte access, advancing only on a real SYS."""
        state = self.state
        call = self.current_op == OP_CALL
        strobes = {"STACK"}
        retired = False
        if state is SequentialState.STACK_RP_LO:
            bus = self._read(RP_CELL)
            self._stack_rp = bus.value
            self.state = SequentialState.STACK_RP_HI
        elif state is SequentialState.STACK_RP_HI:
            bus = self._read(RP_CELL + 1)
            self._stack_rp |= bus.value << 8
            rp = self._stack_rp
            if rp < STACK_BASE or rp > STACK_TOP + 1 or (rp - STACK_BASE) % 2:
                self.fault = "invalid return stack pointer"
            elif call and rp > STACK_TOP - 1:
                self.fault = "return stack overflow"
            elif not call and rp <= STACK_BASE:
                self.fault = "return stack underflow"
            if self.fault is not None:
                self.halted = True
                strobes.add("STACK_FAULT")
            else:
                self._stack_addr = rp if call else rp - 2
                self._stack_next_rp = rp + 2 if call else rp - 2
                self.state = SequentialState.STACK_DATA_LO
        elif state is SequentialState.STACK_DATA_LO:
            if call:
                bus = self._write(self._stack_addr, self._stack_return)
            else:
                bus = self._read(self._stack_addr)
                self._stack_target = bus.value
            self.state = SequentialState.STACK_DATA_HI
        elif state is SequentialState.STACK_DATA_HI:
            if call:
                bus = self._write(self._stack_addr + 1, self._stack_return >> 8)
            else:
                bus = self._read(self._stack_addr + 1)
                self._stack_target |= bus.value << 8
            self.state = SequentialState.STACK_WRITE_RP_LO
        elif state is SequentialState.STACK_WRITE_RP_LO:
            bus = self._write(RP_CELL, self._stack_next_rp)
            self.state = SequentialState.STACK_WRITE_RP_HI
        elif state is SequentialState.STACK_WRITE_RP_HI:
            bus = self._write(RP_CELL + 1, self._stack_next_rp >> 8)
            self.pc.pc = self._stack_target
            strobes |= {"PC_LOAD_EN", "STACK_PUSH" if call else "STACK_POP"}
            retired = True
            self._retire()
        else:
            raise RuntimeError(f"not a stack state: {state}")
        strobes.add("MEM_RD" if bus.kind == "read" else "MEM_WR")
        return strobes, bus, retired

    def _emit(self, state: SequentialState, before: int, stage: StageActivity, strobes: set[str], bus: BusAccess | None = None, *, retired: bool = False, waiting: bool = False) -> None:
        rec = SysTrace(
            sys_index=self.sys_index, state=state, stage=stage,
            pc_before=before, pc_after=self.pc.pc, ir=self.ir.ir,
            mbr=self.mbr.mbr, abs16_hi=self.abs16_hi.hi, r0=self.gpr.qa(),
            z=self.flg.z, c=self.flg.c, bus_access=bus,
            strobes=frozenset(strobes), retired=retired, waiting=waiting,
            fault=self.fault,
        )
        self.last_trace = rec
        self.trace.append(rec)
        self.sys_index += 1

    def request_wait(self) -> None:
        """Insert one visible no-progress SYS before the next pending operation."""
        self._wait_next = True

    def step(self) -> None:
        if self.halted:
            return
        before = self.pc.pc
        state = self.state
        self._trace_fetch = {}
        if self._wait_next:
            self._wait_next = False
            self._emit(SequentialState.WAIT, before, StageActivity(), {"WAIT"}, waiting=True)
            return
        if state is SequentialState.FETCH_OPCODE:
            bus = self._read(before)
            self.current_op = self.ir.ir = bus.value
            increment = self.current_op != OP_HALT
            if increment:
                self.pc.pc = (before + 1) & 0xFFFF
            self._operand_len = control_for(self.current_op).length - 1
            self._operand_byte = 0
            self._trace_fetch = {"net_fetch": 1, "pc_inc_count": int(increment), "net_ir_load": True}
            if self._operand_len:
                self.state = SequentialState.FETCH_OPERAND
            else:
                self._ready_to_execute()
            strobes = {"FETCH", "MEM_RD", "IR_LOAD"}
            if increment:
                strobes.add("PC_INC")
            self._emit(state, before, StageActivity(True, before), strobes, bus)
            return
        if state is SequentialState.FETCH_OPERAND:
            bus = self._read(before)
            self.pc.pc = (before + 1) & 0xFFFF
            if self._operand_byte == 0:
                self.mbr.mbr = bus.value
                load_strobe, load_net = "MBR_LOAD", "net_mbr_load"
            else:
                self.abs16_hi.hi = bus.value
                load_strobe, load_net = "ABS16_HI_LOAD", "net_abs16_hi_load"
            self._operand_byte += 1
            self._trace_fetch = {"net_fetch": 1, "pc_inc_count": 1, load_net: True}
            if self._operand_byte == self._operand_len:
                self._ready_to_execute()
            self._emit(state, before, StageActivity(True, before), {"FETCH", "MEM_RD", load_strobe, "PC_INC"}, bus)
            return
        if state in (SequentialState.EXECUTE, SequentialState.MEM_READ, SequentialState.MEM_WRITE):
            strobes, bus = self._execute()
            retired = True
            self._retire()
        else:
            strobes, bus, retired = self._stack_step()
        self._emit(state, before, StageActivity(execute_active=True, execute_opcode=self.current_op), strobes, bus, retired=retired)

    def run(self, max_steps: int = 500, *, wall_s: float = 10.0) -> int:
        import time
        deadline, steps = time.monotonic() + wall_s, 0
        while not self.halted and steps < max_steps and time.monotonic() <= deadline:
            self.step()
            steps += 1
        return steps

    @property
    def fetch_pending(self) -> bool:
        return not self.halted and self.state is SequentialState.FETCH_OPCODE

    @property
    def current_operand(self) -> int:
        return self.mbr.mbr & 0xFF

    @property
    def current_operand16(self) -> int:
        return self.mbr.mbr | (self.abs16_hi.hi << 8)

    @property
    def operand16(self) -> int:
        return self.current_operand16

    @property
    def sys_ticks(self) -> int:
        return self.sys_index

    @property
    def traces(self) -> tuple[SysTrace, ...]:
        return tuple(self.trace)
