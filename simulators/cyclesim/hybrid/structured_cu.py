"""ROM-free hierarchical CU: instruction class, continuation stage and shared step.

Stage is the continuation context, not an expanded per-transfer return address.
One common adjust engine handles PC/RP, direction, low/high and carry/borrow.
No calls to HybridCpu.instruction/_adjust/_address are used by this executor.
"""
from dataclasses import dataclass
from enum import IntEnum
from functools import lru_cache

from simulators.cyclesim.data.isa import insn_length
from simulators.cyclesim.hybrid.cpu import Transfer
from simulators.cyclesim.hybrid.incdec import IncDecCpu, UnitTransfer


class Stage(IntEnum):
    FETCH_ADDRESS = 0
    FETCH_READ = 1
    PC_INCREMENT = 2
    OPERAND_ADDRESS = 3
    OPERAND_INCREMENT = 4
    OPERAND_READ = 5
    MEMORY_HIGH = 6
    MEMORY_ADDRESS = 7
    MEMORY_ACCESS = 8
    ACC_ALU = 9
    JUMP = 10
    RP_LOW_ADDRESS = 11
    RP_LOW_READ = 12
    RP_HIGH_ADDRESS = 13
    RP_HIGH_READ = 14
    RET_PREDECREMENT = 15
    STACK_LOW_ADDRESS = 16
    STACK_LOW_ACCESS = 17
    RP_INCREMENT = 18
    STACK_HIGH_ADDRESS = 19
    STACK_HIGH_ACCESS = 20
    RP_FINAL_ADJUST = 21
    RP_LOW_WRITE_ADDRESS = 22
    RP_LOW_WRITE = 23
    RP_HIGH_WRITE_ADDRESS = 24
    RP_HIGH_WRITE = 25
    STOP = 26


def instruction_class(opcode):
    if opcode in (1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 13, 15):
        return opcode
    return 0 if insn_length(opcode) == 1 else 11


@dataclass(frozen=True)
class Action:
    kind: str
    target: str = ""
    amount: int = 0
    transfer: Transfer | None = None


@lru_cache(None)
def action(stage, klass, second=0):
    s = Stage(stage)
    if s == Stage.STOP:
        return Action("stop")
    if s in (Stage.FETCH_ADDRESS, Stage.OPERAND_ADDRESS):
        return Action("address", "PC")
    if s in (Stage.PC_INCREMENT, Stage.OPERAND_INCREMENT):
        return Action("adjust", "PC", 1)
    if s == Stage.MEMORY_ADDRESS:
        return Action("address", "TMP")
    if s in (Stage.RP_LOW_ADDRESS, Stage.RP_LOW_WRITE_ADDRESS):
        return Action("address", "literal", 0xF00)
    if s in (Stage.RP_HIGH_ADDRESS, Stage.RP_HIGH_WRITE_ADDRESS):
        return Action("address", "literal", 0xF01)
    if s in (Stage.STACK_LOW_ADDRESS, Stage.STACK_HIGH_ADDRESS):
        return Action("address", "RP")
    if s == Stage.RET_PREDECREMENT:
        return Action("adjust", "RP", -2)
    if s == Stage.RP_INCREMENT:
        return Action("adjust", "RP", 1)
    if s == Stage.RP_FINAL_ADJUST:
        return Action("adjust", "RP", 1 if klass == 6 else -1)
    if s == Stage.ACC_ALU:
        return Action("alu", amount=int(klass == 13))
    if s == Stage.JUMP:
        return Action("jump")
    singles = {
        Stage.FETCH_READ: Transfer("MEM", "IR"),
        Stage.OPERAND_READ: Transfer("MEM", "MBR" if klass in (1, 13) else "TMP_HI" if second else "TMP_LO"),
        Stage.MEMORY_HIGH: Transfer("CU", "TMP_HI", constant=255 if klass in (8, 9) else 0),
        Stage.MEMORY_ACCESS: Transfer("MEM", "DP") if klass in (2, 8) else Transfer("DP", "MEM"),
        Stage.RP_LOW_READ: Transfer("MEM", "DP", "RP_LO", guard="low"),
        Stage.RP_HIGH_READ: Transfer("MEM", "DP", "RP_HI", guard="call" if klass == 6 else "ret"),
        Stage.STACK_LOW_ACCESS: Transfer("DP", "MEM", "PC_LO") if klass == 6 else Transfer("MEM", "TMP_LO"),
        Stage.STACK_HIGH_ACCESS: Transfer("DP", "MEM", "PC_HI") if klass == 6 else Transfer("MEM", "TMP_HI"),
        Stage.RP_LOW_WRITE: Transfer("DP", "MEM", "RP_LO"),
        Stage.RP_HIGH_WRITE: Transfer("DP", "MEM", "RP_HI"),
    }
    return Action("single", transfer=singles[s])


def first_step(a):
    return int(a.kind == "adjust" and abs(a.amount) == 1)


def steps(a):
    return range(first_step(a), 5 if a.kind == "adjust" else
                 2 if a.kind in ("address", "alu", "jump") else 1)


def command(a, step):
    if a.kind == "stop":
        return None
    if a.kind == "single":
        return a.transfer
    if a.kind == "address":
        suffix = "HI" if step else "LO"
        if a.target == "literal":
            return Transfer("CU", "ADDR_" + suffix, constant=(a.amount >> (step*8)) & 255)
        if a.target == "TMP":
            return Transfer("TMP_" + suffix, "ADDR_" + suffix)
        return Transfer("DP", "ADDR_" + suffix, a.target + "_" + suffix)
    if a.kind == "adjust":
        if step == 0:
            return Transfer("CU", "MBR", constant=abs(a.amount))
        reg = a.target + ("_HI" if step >= 3 else "_LO")
        if step in (2, 4):
            return Transfer("RESULT", "DP", reg)
        constructor = UnitTransfer if step == 3 or abs(a.amount) == 1 else Transfer
        return constructor("ALU", "RESULT", reg, subtract=a.amount < 0)
    if a.kind == "alu":
        return (Transfer("ALU", "RESULT", subtract=bool(a.amount)) if step == 0 else
                Transfer("RESULT", "CU" if a.amount else "DP", flags=True))
    if a.kind == "jump":
        suffix = "HI" if step else "LO"
        return Transfer("TMP_" + suffix, "DP", "PC_" + suffix)
    raise AssertionError(a)


def action_done(a, step, carry):
    if a.kind == "adjust":
        propagate = not carry if a.amount < 0 else carry
        return step == 4 or (step == 2 and not propagate)
    return step == (1 if a.kind in ("address", "alu", "jump") else 0)


def execution_stage(klass, z):
    if klass in (1, 13): return Stage.ACC_ALU
    if klass in (2, 3, 8, 9): return Stage.MEMORY_HIGH
    if klass == 15: return Stage.MEMORY_ADDRESS
    if klass == 5 or (klass == 4 and z): return Stage.JUMP
    if klass in (6, 7): return Stage.RP_LOW_ADDRESS
    return Stage.FETCH_ADDRESS


def next_stage(stage, klass, second, z):
    s = Stage(stage)
    if s == Stage.FETCH_READ:
        return Stage.STOP if klass == 10 else Stage.PC_INCREMENT
    if s == Stage.PC_INCREMENT:
        return execution_stage(klass, z) if klass in (0, 7) else Stage.OPERAND_ADDRESS
    if s == Stage.OPERAND_READ:
        return (Stage.OPERAND_ADDRESS if not second and klass in (4, 5, 6, 15)
                else execution_stage(klass, z))
    if s in (Stage.MEMORY_ACCESS, Stage.ACC_ALU, Stage.JUMP):
        return Stage.FETCH_ADDRESS
    if s == Stage.RP_HIGH_READ:
        return Stage.STACK_LOW_ADDRESS if klass == 6 else Stage.RET_PREDECREMENT
    if s == Stage.RP_HIGH_WRITE:
        return Stage.JUMP
    if s == Stage.STOP:
        return Stage.STOP
    return Stage(int(s) + 1)


@lru_cache(None)
def commands():
    out = [None]
    for stage in Stage:
        for klass in range(16):
            for second in (0, 1):
                a = action(stage, klass, second)
                for step in steps(a):
                    t = command(a, step)
                    if t not in out: out.append(t)
    assert len(out) <= 64
    return tuple(out)


class StructuredCpu(IncDecCpu):
    def reset(self, pc=0):
        super().reset(pc)
        self.stage, self.microstep, self.klass, self.second = Stage.FETCH_ADDRESS, 0, 0, 0
        self.control_trace = []

    def step_instruction(self, *, wait_every=0):
        if self.halted: return
        for _ in range(256):
            if self.stage == Stage.STOP:
                self.halted = True
                self.retired += 1
                return
            a = action(self.stage, self.klass, self.second)
            t = command(a, self.microstep)
            self.control_trace.append((int(self.stage), self.microstep, self.klass, self.second))
            self.transfer(t, waits=int(bool(wait_every and self.transfers % wait_every == 0)))
            if self.halted: return
            if t.destination == "IR": self.klass = instruction_class(self.ir)
            if action_done(a, self.microstep, self.work_carry):
                nxt = next_stage(self.stage, self.klass, self.second, self.z)
                if self.stage == Stage.OPERAND_READ: self.second = 1
                if nxt == Stage.FETCH_ADDRESS: self.second = 0
                self.stage = nxt
                self.microstep = first_step(action(nxt, self.klass, self.second))
            else:
                self.microstep += 1
            if self.stage == Stage.FETCH_ADDRESS and self.microstep == 0:
                self.retired += 1
                return
        raise AssertionError("structured CU transfer cap")
