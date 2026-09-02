"""M3b behavioral CPU using the active P12 IF|EX SYS schedule."""

from __future__ import annotations

from simulators.cyclesim.blocks.cpld import CpldDp
from simulators.cyclesim.blocks.fetch import Abs16HiReg, FlgReg, IrReg, MbrReg, MemArray, PcReg
from simulators.cyclesim.blocks.return_stack import ReturnStack, StackError
from simulators.cyclesim.data.isa import OP_ADD, OP_BEQ, OP_CALL, OP_CMP, OP_HALT, OP_JMP, OP_LDA, OP_LDIO, OP_RET, OP_STA, OP_STA16, OP_STIO
from simulators.cyclesim.data.p12 import P12State, StageActivity, SysTrace, control_for


class CpuM3b:
    """R0-only M3b model. ``step`` advances exactly one counted SYS tick."""

    def __init__(self) -> None:
        self.pc = PcReg()
        self.ir = IrReg()
        self.mbr = MbrReg()
        self.abs16_hi = Abs16HiReg()
        self.flg = FlgReg()
        self.mem = MemArray()
        self.return_stack = ReturnStack(self.mem)
        self.cpld_dp = CpldDp()
        self.gpr = self.cpld_dp
        self.halted = False
        self.sys_index = 0
        self.state = P12State.FILL
        self.trace: list[SysTrace] = []
        self.last_trace: SysTrace | None = None
        self.fetch_pending = True
        self.current_op = 0
        self._stage = "fetch"
        self._operand_byte = 0
        self._operand_len = 0
        self._stack_ticks = 0
        self._bubble = False
        self._stretch_next = False
        self._fallback_next = False
        self._trace_fetch: dict[str, int | bool] = {}

    def reset(self, pc: int | None = None, *, from_vector: bool = False) -> None:
        if from_vector or pc is None:
            pc = self.mem.sys.reset_vector() if (self.mem.sys.rom.get(0xFFFC) is not None or self.mem.sys.rom.get(0xFFFD) is not None) else 0
        self.pc.pc = pc & 0xFFFF
        self.halted = False
        self.sys_index = 0
        self.state = P12State.FILL
        self.trace.clear()
        self.last_trace = None
        self.fetch_pending = True
        self.current_op = 0
        self._stage = "fetch"
        self._operand_byte = self._operand_len = self._stack_ticks = 0
        self._bubble = False
        self._stretch_next = self._fallback_next = False
        self.cpld_dp.regs = [0]
        self.flg.z = self.flg.c = False
        self.ir.ir = self.mbr.mbr = self.abs16_hi.hi = 0

    def _eff_addr(self) -> int:
        from simulators.cyclesim.blocks.mem_decode import MAILBOX_BASE
        if self.current_op in (OP_LDIO, OP_STIO):
            return MAILBOX_BASE | self.mbr.mbr
        if self.current_op == OP_STA16:
            return self.mbr.mbr | (self.abs16_hi.hi << 8)
        return self.mbr.mbr

    def _fetch_record(self, before: int, addr: int, *, ir: bool = False) -> None:
        self._trace_fetch = {"net_fetch": 1, "pc_inc_count": 1, "net_ir_load" if ir else "net_mbr_load": True}

    def _execute(self) -> tuple[set[str], int | None, tuple[int, int] | None]:
        op = self.current_op
        strobes: set[str] = {"EX"}
        read: int | None = None
        write: tuple[int, int] | None = None
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
            read = self.mem.read(self._eff_addr())
            self.gpr.regs[0] = read
            strobes |= {"MEM_RD", "REG_WE"}
        elif op in (OP_STA, OP_STIO, OP_STA16):
            addr, val = self._eff_addr(), self.gpr.qa()
            self.mem.write(addr, val)
            write = (addr, val)
            strobes |= {"Y_OE", "MEM_WR"}
        elif op == OP_BEQ:
            strobes.add("PC_LOAD_EN")
            if self.flg.z:
                self.pc.pc = self.mbr.mbr | (self.abs16_hi.hi << 8)
                self._bubble = True
        elif op == OP_JMP:
            self.pc.pc = self.mbr.mbr | (self.abs16_hi.hi << 8)
            strobes.add("PC_LOAD_EN")
            self._bubble = True
        elif op == OP_CALL:
            try:
                self.return_stack.push_return(self.pc.pc)
                self.pc.pc = self.mbr.mbr | (self.abs16_hi.hi << 8)
                strobes |= {"PC_LOAD_EN", "STACK_PUSH"}
                self._bubble = True
            except StackError:
                self.halted = True
        elif op == OP_RET:
            try:
                self.pc.pc = self.return_stack.pop_return()
                strobes |= {"PC_LOAD_EN", "STACK_POP"}
                self._bubble = True
            except StackError:
                self.halted = True
        elif op == OP_HALT:
            self.halted = True
        return strobes, read, write

    def _emit(self, state: P12State, before: int, stage: StageActivity, strobes: set[str], read: int | None = None, write: tuple[int, int] | None = None, *, retired: bool = False, stalled: bool = False, bubble: bool = False, stretched: bool = False, fallback: bool = False) -> None:
        rec = SysTrace(self.sys_index, state, stage, before, self.pc.pc, self.ir.ir, self.mbr.mbr, self.gpr.qa(), self.flg.z, self.flg.c, read, write, frozenset(strobes), retired, stalled, bubble, stretched, fallback)
        self.last_trace = rec
        self.trace.append(rec)
        self.sys_index += 1

    def request_stretch(self) -> None:
        """Add one visible SYS to the next advancement (lab qualification hook)."""
        self._stretch_next = True

    def request_fallback_fe2(self) -> None:
        """Use the named serial fetch/execute fallback on the next advancement."""
        self._fallback_next = True

    def step(self) -> None:
        if self.halted:
            return
        if self._stage == "extra":
            self._extra_tick()
            return
        before = self.pc.pc
        if self._stretch_next or self._fallback_next:
            stretch, fallback = self._stretch_next, self._fallback_next
            self._stretch_next = self._fallback_next = False
            state = P12State.STRETCH if stretch else P12State.FALLBACK_FE2
            self._emit(state, before, StageActivity(), {state.value}, stretched=stretch, fallback=fallback)
            return
        if self._stage == "fetch":
            addr = self.pc.pc
            self.current_op = self.mem.read(addr)
            self.ir.ir = self.current_op
            ctl = control_for(self.current_op)
            if self.current_op != OP_HALT:
                self.pc.pc = (self.pc.pc + 1) & 0xFFFF
            self._operand_len = ctl.length - 1
            self._operand_byte = 0
            self.fetch_pending = False
            self._fetch_record(before, addr, ir=True)
            if self.current_op == OP_HALT:
                self._execute()
                self._emit(P12State.FILL if self.sys_index == 0 else P12State.IF_EX, before, StageActivity(True, addr, True, self.current_op), {"IF", "EX"}, retired=True)
                return
            self._stage = "operand" if self._operand_len else "execute"
            self.state = P12State.FILL if self.sys_index == 0 else (P12State.OPERAND_IF if self._operand_len else P12State.IF_EX)
            self._emit(self.state, before, StageActivity(True, addr, False, None), {"IF", "IR_LOAD", "PC_INC"})
            return
        if self._stage == "operand":
            addr = self.pc.pc
            val = self.mem.read(addr)
            self.pc.pc = (self.pc.pc + 1) & 0xFFFF
            if self._operand_byte == 0:
                self.mbr.mbr = val
            else:
                self.abs16_hi.hi = val
            self._operand_byte += 1
            self._trace_fetch = {"net_fetch": 1, "pc_inc_count": 1, "net_mbr_load" if self._operand_byte == 1 else "net_abs16_hi_load": True}
            self._stage = "execute" if self._operand_byte >= self._operand_len else "operand"
            load_strobe = "MBR_LOAD" if self._operand_byte == 1 else "ABS16_HI_LOAD"
            ctl = control_for(self.current_op)
            if self._stage == "execute" and ctl.memory:
                self.state = P12State.OPERAND_IF
                self._stage = "execute"
                self._emit(self.state, before, StageActivity(True, addr, False, None), {"IF", load_strobe, "PC_INC"})
            elif self._stage == "execute":
                strobes, read, write = self._execute()
                state = P12State.STACK_EX if ctl.stack else (P12State.MEM_STALL if ctl.memory else P12State.IF_EX)
                self.state = state
                self.fetch_pending = not ctl.redirect
                self._emit(state, before, StageActivity(True, addr, True, self.current_op), strobes | {"IF", load_strobe, "PC_INC"}, read, write, retired=not self.halted, stalled=ctl.memory)
                if self.halted:
                    return
                self._stack_ticks = 2 if ctl.stack else (1 if self._bubble else 0)
                self._stage = "extra" if self._stack_ticks else "fetch"
                self._bubble = False
            else:
                self.state = P12State.OPERAND_IF
                self._emit(self.state, before, StageActivity(True, addr, False, None), {"IF", load_strobe, "PC_INC"})
            return
        strobes, read, write = self._execute()
        ctl = control_for(self.current_op)
        state = P12State.STACK_EX if ctl.stack else (P12State.MEM_STALL if ctl.memory else P12State.IF_EX)
        self.state = state
        self.fetch_pending = not ctl.redirect
        self._emit(state, before, StageActivity(not ctl.memory, self.pc.pc if not ctl.memory else None, True, self.current_op), strobes, read, write, retired=not self.halted, stalled=ctl.memory)
        if self.halted:
            return
        if ctl.stack:
            self._stack_ticks = 2
        elif self._bubble:
            self._stack_ticks = 1
        self._stage = "extra" if self._stack_ticks else "fetch"
        self._bubble = False

    def _extra_tick(self) -> None:
        before = self.pc.pc
        ctl = control_for(self.current_op)
        if self._stack_ticks > 1:
            state, strobes = P12State.STACK_EX, {"STACK_EX"}
        else:
            state, strobes = (P12State.BRANCH_BUBBLE if ctl.redirect else P12State.STACK_EX), {"BUBBLE" if ctl.redirect else "STACK_EX"}
        self._stack_ticks -= 1
        self._emit(state, before, StageActivity(), strobes, bubble=ctl.redirect)
        if not self._stack_ticks:
            self._stage = "fetch"
            self.fetch_pending = True

    def run(self, max_steps: int = 500, *, wall_s: float = 10.0) -> int:
        import time
        deadline, steps = time.monotonic() + wall_s, 0
        while not self.halted and steps < max_steps and time.monotonic() <= deadline:
            if self._stage == "extra":
                self._extra_tick()
            else:
                self.step()
            steps += 1
        return steps

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
