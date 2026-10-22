"""Non-pipelined control vocabulary and immutable, single-bus SYS traces."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Literal

from simulators.cyclesim.data.isa import (
    OP_ADD, OP_BEQ, OP_CALL, OP_CMP, OP_HALT, OP_JMP, OP_LDA, OP_LDIO,
    OP_RET, OP_STA, OP_STA16, OP_STIO, is_reserved_opcode, insn_length,
)


class SequentialState(str, Enum):
    FETCH_OPCODE = "FETCH_OPCODE"
    FETCH_OPERAND = "FETCH_OPERAND"
    EXECUTE = "EXECUTE"
    MEM_READ = "MEM_READ"
    MEM_WRITE = "MEM_WRITE"
    STACK_RP_LO = "STACK_RP_LO"
    STACK_RP_HI = "STACK_RP_HI"
    STACK_DATA_LO = "STACK_DATA_LO"
    STACK_DATA_HI = "STACK_DATA_HI"
    STACK_WRITE_RP_LO = "STACK_WRITE_RP_LO"
    STACK_WRITE_RP_HI = "STACK_WRITE_RP_HI"
    WAIT = "WAIT"


@dataclass(frozen=True)
class SequentialControl:
    opcode: int
    name: str
    length: int
    memory: bool = False
    redirect: bool = False
    stack: bool = False
    alu: str = "NOP"
    typical_sys: int = 2


_CONTROLS = {
    OP_ADD: SequentialControl(OP_ADD, "ADD", 2, alu="ADD", typical_sys=3),
    OP_LDA: SequentialControl(OP_LDA, "LDA", 2, memory=True, typical_sys=3),
    OP_STA: SequentialControl(OP_STA, "STA", 2, memory=True, typical_sys=3),
    OP_BEQ: SequentialControl(OP_BEQ, "BEQ", 3, redirect=True, typical_sys=4),
    OP_JMP: SequentialControl(OP_JMP, "JMP", 3, redirect=True, typical_sys=4),
    OP_CALL: SequentialControl(OP_CALL, "CALL", 3, redirect=True, stack=True, typical_sys=9),
    OP_RET: SequentialControl(OP_RET, "RET", 1, redirect=True, stack=True, typical_sys=7),
    OP_LDIO: SequentialControl(OP_LDIO, "LDIO", 2, memory=True, typical_sys=3),
    OP_STIO: SequentialControl(OP_STIO, "STIO", 2, memory=True, typical_sys=3),
    OP_HALT: SequentialControl(OP_HALT, "HALT", 1),
    OP_CMP: SequentialControl(OP_CMP, "CMP", 2, alu="CMP", typical_sys=3),
    OP_STA16: SequentialControl(OP_STA16, "STA16", 3, memory=True, typical_sys=4),
}

SEQUENTIAL_CONTROLS = tuple(_CONTROLS.values())
# Successful, no-WAIT instruction costs. BEQ has the same cost for both outcomes.
SYS_COSTS = {control.name: control.typical_sys for control in SEQUENTIAL_CONTROLS}
SYS_COSTS["TRAP"] = 2


def control_for(opcode: int) -> SequentialControl:
    op = opcode & 0xFF
    if is_reserved_opcode(op):
        return SequentialControl(op, "TRAP", 1)
    # Preserve the ISA helper's lengths for other undefined opcodes.
    return _CONTROLS.get(op, SequentialControl(op, "TRAP", insn_length(op), typical_sys=insn_length(op) + 1))


@dataclass(frozen=True)
class BusAccess:
    """The one real byte access performed on the unified bus during this SYS."""

    kind: Literal["read", "write"]
    address: int
    value: int


@dataclass(frozen=True)
class StageActivity:
    fetch_active: bool = False
    fetch_address: int | None = None
    execute_active: bool = False
    execute_opcode: int | None = None


@dataclass(frozen=True)
class SysTrace:
    sys_index: int
    state: SequentialState
    stage: StageActivity
    pc_before: int
    pc_after: int
    ir: int
    mbr: int
    abs16_hi: int
    r0: int
    z: bool
    c: bool
    bus_access: BusAccess | None = None
    strobes: frozenset[str] = field(default_factory=frozenset)
    retired: bool = False
    waiting: bool = False
    fault: str | None = None

    @property
    def mem_address(self) -> int | None:
        return self.bus_access.address if self.bus_access is not None else None

    @property
    def mem_read(self) -> int | None:
        bus = self.bus_access
        return bus.value if bus is not None and bus.kind == "read" else None

    @property
    def mem_write(self) -> tuple[int, int] | None:
        bus = self.bus_access
        return (bus.address, bus.value) if bus is not None and bus.kind == "write" else None

    @property
    def reg_we(self) -> bool:
        return "REG_WE" in self.strobes

    @property
    def flg_we(self) -> bool:
        return "FLG_WE" in self.strobes

    @property
    def pc_load_en(self) -> bool:
        return "PC_LOAD_EN" in self.strobes
