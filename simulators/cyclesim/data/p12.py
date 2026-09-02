"""P12 pipe control vocabulary and immutable SYS trace records."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from simulators.cyclesim.data.isa import (
    OP_ADD, OP_BEQ, OP_CALL, OP_CMP, OP_HALT, OP_JMP, OP_LDA, OP_LDIO,
    OP_RET, OP_STA, OP_STA16, OP_STIO, is_reserved_opcode, insn_length,
)


class P12State(str, Enum):
    FILL = "FILL"
    IF_EX = "IF_EX"
    OPERAND_IF = "OPERAND_IF"
    MEM_STALL = "MEM_STALL"
    BRANCH_BUBBLE = "BRANCH_BUBBLE"
    STACK_EX = "STACK_EX"
    STRETCH = "STRETCH"
    FALLBACK_FE2 = "FALLBACK_FE2"


@dataclass(frozen=True)
class P12Control:
    opcode: int
    name: str
    length: int
    memory: bool = False
    redirect: bool = False
    stack: bool = False
    alu: str = "NOP"
    typical_sys: int = 1


_CONTROLS = {
    OP_ADD: P12Control(OP_ADD, "ADD", 2, alu="ADD", typical_sys=2),
    OP_LDA: P12Control(OP_LDA, "LDA", 2, memory=True, typical_sys=3),
    OP_STA: P12Control(OP_STA, "STA", 2, memory=True, typical_sys=3),
    OP_BEQ: P12Control(OP_BEQ, "BEQ", 3, redirect=True, alu="CMP", typical_sys=3),
    OP_JMP: P12Control(OP_JMP, "JMP", 3, redirect=True, typical_sys=4),
    OP_CALL: P12Control(OP_CALL, "CALL", 3, redirect=True, stack=True, typical_sys=6),
    OP_RET: P12Control(OP_RET, "RET", 1, redirect=True, stack=True, typical_sys=4),
    OP_LDIO: P12Control(OP_LDIO, "LDIO", 2, memory=True, typical_sys=3),
    OP_STIO: P12Control(OP_STIO, "STIO", 2, memory=True, typical_sys=3),
    OP_HALT: P12Control(OP_HALT, "HALT", 1),
    OP_CMP: P12Control(OP_CMP, "CMP", 2, alu="CMP", typical_sys=2),
    OP_STA16: P12Control(OP_STA16, "STA16", 3, memory=True, typical_sys=4),
}

P12_CONTROLS = tuple(_CONTROLS.values())
SYS_COSTS = {control.name: control.typical_sys for control in P12_CONTROLS}


def control_for(opcode: int) -> P12Control:
    op = opcode & 0xFF
    if is_reserved_opcode(op) or op == 0x0C:
        return P12Control(op, "TRAP", 1)
    return _CONTROLS.get(op, P12Control(op, "TRAP", insn_length(op)))


@dataclass(frozen=True)
class StageActivity:
    if_active: bool = False
    if_address: int | None = None
    ex_active: bool = False
    ex_opcode: int | None = None


@dataclass(frozen=True)
class SysTrace:
    sys_index: int
    state: P12State
    stage: StageActivity
    pc_before: int
    pc_after: int
    ir: int
    mbr: int
    r0: int
    z: bool
    c: bool
    mem_read: int | None = None
    mem_write: tuple[int, int] | None = None
    strobes: frozenset[str] = field(default_factory=frozenset)
    retired: bool = False
    stalled: bool = False
    bubble: bool = False
    stretched: bool = False
    fallback: bool = False

    @property
    def reg_we(self) -> bool:
        return "REG_WE" in self.strobes

    @property
    def flg_we(self) -> bool:
        return "FLG_WE" in self.strobes

    @property
    def pc_load_en(self) -> bool:
        return "PC_LOAD_EN" in self.strobes
