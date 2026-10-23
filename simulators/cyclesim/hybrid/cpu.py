"""Executable bus-transfer candidate, with abstract CPLDs and a package ALU.

All payload moves over DBUS. No private 16-bit address/return datapath exists.
The Python sequencer is NOT a synthesized CU. Transfer phases model registered
574 capture pulses, not analog clock integrity. One transfer takes four ticks:
setup, capture, hold, release; memory effects happen once, at capture.
"""
from dataclasses import dataclass

from simulators.cyclesim.blocks.mem_decode import MemSystem
from simulators.cyclesim.data.isa import insn_length
from simulators.cyclesim.ttl.netlist import Circuit

DP_REGS = ("R0", "PC_LO", "PC_HI", "RP_LO", "RP_HI")
LATCHES = ("ADDR_LO", "ADDR_HI", "MBR", "TMP_LO", "TMP_HI", "RESULT")


@dataclass(frozen=True)
class Transfer:
    source: str
    destination: str
    select: str = "R0"
    constant: int = 0
    subtract: bool = False
    flags: bool = False
    guard: str = ""


class HybridCpu:
    def __init__(self):
        self.mem = MemSystem()
        self.alu = Circuit()
        self.a = self.alu.bus("A", 8)
        self.b = self.alu.bus("B", 8)
        self.sub = self.alu.bus("SUB", 1)
        self.y, self.carry = self.alu.import_alu(self.a, self.b, self.sub[0])
        self.alu.finalize()
        self.reset()

    def reset(self, pc=0):
        self.dp = dict.fromkeys(DP_REGS, 0)
        self.latches = dict.fromkeys(LATCHES, 0)
        self.dp["PC_LO"], self.dp["PC_HI"] = pc & 255, pc >> 8
        self.ir = 0
        self.z = self.c = self.work_carry = False
        self.guard_bits = (False, False, False, False)
        self.halted = False
        self.fault = None
        self.ticks = self.transfers = self.retired = 0
        self.events = []
        self.accesses = []
        self.latch_clocks = dict.fromkeys(LATCHES, 0)

    @property
    def pc(self): return self.dp["PC_LO"] | self.dp["PC_HI"] << 8
    @property
    def r0(self): return self.dp["R0"]
    @property
    def address(self): return self.latches["ADDR_LO"] | self.latches["ADDR_HI"] << 8

    def _memory(self):
        # Independent decode, from external address-latch outputs only.
        a = self.address
        if 0xFF00 <= a < 0xFFFC:
            return self.mem.mailbox, a & 255, True, "mailbox"
        if not self.mem.map_mode and (a < 0x0800 or a >= 0xFFFC):
            return self.mem.rom, a, False, "rom"
        return self.mem.ram, a, True, "ram"

    def _drive(self, t):
        if t.source == "CU": return t.constant & 255, None
        if t.source == "DP": return self.dp[t.select], None
        if t.source in ("TMP_LO", "TMP_HI", "RESULT"): return self.latches[t.source], None
        if t.source == "MEM":
            memory, key, _, _ = self._memory()
            return memory.get(key, 0) & 255, None
        if t.source == "ALU":
            self.alu.set(self.a, self.dp[t.select])
            self.alu.set(self.b, self.latches["MBR"])
            self.alu.set(self.sub, int(t.subtract))
            self.alu.settle()
            return self.alu.read(self.y), bool(self.alu.read([self.carry]))
        raise ValueError(t.source)

    def transfer(self, t, *, waits=0):
        if waits < 0: raise ValueError("negative WAIT")
        if t.select not in DP_REGS: raise ValueError(t.select)
        if t.source == "ALU" and t.destination != "RESULT":
            raise ValueError("ALU must capture RESULT before shared-bus writeback")
        if any(self.latch_clocks.values()): raise AssertionError("clock not released")
        value, carry = self._drive(t)
        # No driver change between setup, capture and hold. Clock release precedes
        # the following transfer's setup. WAIT is inserted before capture.
        self.ticks += 1 + waits
        before = self.address
        if t.destination in self.latches:
            self.latch_clocks[t.destination] = 1
            self.latches[t.destination] = value
        elif t.destination == "DP": self.dp[t.select] = value
        elif t.destination == "IR": self.ir = value
        elif t.destination == "MEM":
            memory, key, writable, _ = self._memory()
            if writable: memory[key] = value
        elif t.destination != "CU": raise ValueError(t.destination)
        if t.source == "MEM": self.accesses.append(("read", before, value))
        if t.destination == "MEM": self.accesses.append(("write", before, value))
        if carry is not None:
            self.work_carry = carry
        if t.flags: self.z, self.c = value == 0, self.work_carry
        if t.guard == "low":
            self.guard_bits = (bool(value & 1), value > 0xF0, value == 0xF0, value == 0)
        elif t.guard in ("call", "ret"):
            odd, above_f0, equal_f0, zero = self.guard_bits
            if odd or value < 0xF6 or value > 0xFE or (value == 0xFE and above_f0):
                self.fault = "invalid return stack pointer"
            elif t.guard == "call" and value == 0xFE and equal_f0:
                self.fault = "return stack overflow"
            elif t.guard == "ret" and value == 0xF6 and zero:
                self.fault = "return stack underflow"
            self.halted = self.fault is not None
        self.ticks += 3
        self.transfers += 1
        self.events.append((t, value, before, self.ticks))
        # Check the actual source after destinations change: a direct ALU->R0
        # path would change ALU A during hold and fail this check.
        assert self._drive(t)[0] == value, "source changed during capture/hold"
        for name in self.latch_clocks: self.latch_clocks[name] = 0

    def _literal(self, value, destination):
        yield Transfer("CU", destination, constant=value)

    def _address(self, prefix=None, literal=None):
        if literal is not None:
            yield from self._literal(literal & 255, "ADDR_LO")
            yield from self._literal(literal >> 8, "ADDR_HI")
        elif prefix == "TMP":
            yield Transfer("TMP_LO", "ADDR_LO")
            yield Transfer("TMP_HI", "ADDR_HI")
        else:
            yield Transfer("DP", "ADDR_LO", prefix + "_LO")
            yield Transfer("DP", "ADDR_HI", prefix + "_HI")

    def _adjust(self, prefix, amount):
        # Every arithmetic result passes through the actual external 12-chip ALU.
        # No Python PC/RP increment is used by the executor.
        yield from self._literal(abs(amount), "MBR")
        yield from self._alu_write(prefix + "_LO", "DP", amount < 0)
        propagate = not self.work_carry if amount < 0 else self.work_carry
        if propagate:
            yield from self._literal(1, "MBR")
            yield from self._alu_write(prefix + "_HI", "DP", amount < 0)

    def _alu_write(self, select, destination, subtract=False, flags=False):
        yield Transfer("ALU", "RESULT", select, subtract=subtract)
        yield Transfer("RESULT", destination, select, flags=flags)

    def _jump(self):
        yield Transfer("TMP_LO", "DP", "PC_LO")
        yield Transfer("TMP_HI", "DP", "PC_HI")

    def _stack(self, call):
        yield from self._address(literal=0x0F00)
        yield Transfer("MEM", "DP", "RP_LO", guard="low")
        yield from self._address(literal=0x0F01)
        yield Transfer("MEM", "DP", "RP_HI", guard="call" if call else "ret")
        if self.halted: return
        if not call: yield from self._adjust("RP", -2)
        yield from self._address("RP")
        yield Transfer("DP", "MEM", "PC_LO") if call else Transfer("MEM", "TMP_LO")
        yield from self._adjust("RP", 1)
        yield from self._address("RP")
        yield Transfer("DP", "MEM", "PC_HI") if call else Transfer("MEM", "TMP_HI")
        yield from self._adjust("RP", 1 if call else -1)
        yield from self._address(literal=0x0F00)
        yield Transfer("DP", "MEM", "RP_LO")
        yield from self._address(literal=0x0F01)
        yield Transfer("DP", "MEM", "RP_HI")
        yield from self._jump()

    def instruction(self):
        yield from self._address("PC")
        yield Transfer("MEM", "IR")
        if self.ir != 10: yield from self._adjust("PC", 1)
        for byte in range(insn_length(self.ir) - 1):
            yield from self._address("PC")
            # Address latches hold the fetch address while ALU increments PC.
            yield from self._adjust("PC", 1)
            target = "MBR" if self.ir in (1, 13) else ("TMP_LO" if byte == 0 else "TMP_HI")
            yield Transfer("MEM", target)
        op = self.ir
        if op in (1, 13):
            yield from self._alu_write("R0", "DP" if op == 1 else "CU", op == 13, True)
        elif op in (2, 3, 8, 9, 15):
            if op != 15: yield from self._literal(255 if op in (8, 9) else 0, "TMP_HI")
            yield from self._address("TMP")
            yield Transfer("MEM", "DP", "R0") if op in (2, 8) else Transfer("DP", "MEM", "R0")
        elif op == 5 or (op == 4 and self.z): yield from self._jump()
        elif op in (6, 7): yield from self._stack(op == 6)
        elif op == 10: self.halted = True
        if not self.fault: self.retired += 1

    def step_instruction(self, *, wait_every=0):
        if self.halted: return
        for index, transfer in enumerate(self.instruction()):
            if index >= 256: raise RuntimeError("instruction transfer cap")
            self.transfer(transfer, waits=int(bool(wait_every and self.transfers % wait_every == 0)))
