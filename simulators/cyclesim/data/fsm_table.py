"""idx5 FSM control table — LEGACY Gi1 multiphase golden (not the Active sequential CPU).

Active CU truth: reference/hardware/cpld-sequential-cu.md
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from simulators.cyclesim.blocks.alu8 import ALU_ADD, ALU_CMP, ALU_NOP, ALU_SUB, AluControls


class Template(str, Enum):
    ALU_REG = "ALU_REG"
    MEM_LD = "MEM_LD"
    MEM_ST = "MEM_ST"
    BEQ = "BEQ"
    JMP = "JMP"
    CALL = "CALL"
    RET = "RET"
    HALT = "HALT"


@dataclass(frozen=True)
class CtrlRow:
    opcode: int
    phase: int
    template: Template
    reg_we: bool = False
    mem_rd: bool = False
    mem_wr: bool = False
    y_oe: bool = False
    w_sel: int = 0
    flg_we: bool = False
    pc_load_en: bool = False
    pc_load_flg_z: bool = False
    alu: AluControls = ALU_NOP

    @property
    def idx5(self) -> int:
        return ((self.opcode & 0x1F) << 2) | (self.phase & 3)


def idx5_index(opcode: int, phase: int) -> int:
    return ((opcode & 0x1F) << 2) | (phase & 3)


# Frozen rows — M3a-control-store.md §2 (Gi1 v1.0)
FSM_ROWS: tuple[CtrlRow, ...] = (
    # ADD 0x01
    CtrlRow(0x01, 0, Template.ALU_REG, alu=ALU_ADD),
    CtrlRow(0x01, 1, Template.ALU_REG, alu=ALU_ADD),
    CtrlRow(0x01, 2, Template.ALU_REG, y_oe=True, reg_we=True, w_sel=0, flg_we=True, alu=ALU_ADD),
    # LDA 0x02
    CtrlRow(0x02, 0, Template.MEM_LD, mem_rd=True, alu=ALU_NOP),
    CtrlRow(0x02, 1, Template.MEM_LD, reg_we=True, w_sel=0, alu=ALU_NOP),
    # STA 0x03
    CtrlRow(0x03, 0, Template.MEM_ST, y_oe=True, alu=ALU_NOP),
    CtrlRow(0x03, 1, Template.MEM_ST, mem_wr=True, alu=ALU_NOP),
    # BEQ 0x04
    CtrlRow(0x04, 0, Template.BEQ, alu=ALU_SUB),
    CtrlRow(0x04, 1, Template.BEQ, pc_load_en=True, pc_load_flg_z=True, alu=ALU_NOP),
    # JMP 0x05
    CtrlRow(0x05, 0, Template.JMP, pc_load_en=True, alu=ALU_NOP),
    # CALL 0x06
    CtrlRow(0x06, 0, Template.CALL, pc_load_en=True, alu=ALU_NOP),
    # RET 0x07
    CtrlRow(0x07, 0, Template.RET, pc_load_en=True, alu=ALU_NOP),
    # LDIO 0x08
    CtrlRow(0x08, 0, Template.MEM_LD, mem_rd=True, alu=ALU_NOP),
    CtrlRow(0x08, 1, Template.MEM_LD, reg_we=True, w_sel=0, alu=ALU_NOP),
    # STIO 0x09
    CtrlRow(0x09, 0, Template.MEM_ST, y_oe=True, alu=ALU_NOP),
    CtrlRow(0x09, 1, Template.MEM_ST, mem_wr=True, alu=ALU_NOP),
    # HALT 0x0A
    CtrlRow(0x0A, 0, Template.HALT),
    # CMP 0x0D
    CtrlRow(0x0D, 0, Template.ALU_REG, alu=ALU_CMP),
    CtrlRow(0x0D, 1, Template.ALU_REG, alu=ALU_CMP),
    CtrlRow(0x0D, 2, Template.ALU_REG, flg_we=True, alu=ALU_CMP),
    # STA16 0x0F
    CtrlRow(0x0F, 0, Template.MEM_ST, y_oe=True, alu=ALU_NOP),
    CtrlRow(0x0F, 1, Template.MEM_ST, mem_wr=True, alu=ALU_NOP),
)

FSM_BY_KEY: dict[tuple[int, int], CtrlRow] = {(r.opcode, r.phase): r for r in FSM_ROWS}
FSM_BY_IDX5: dict[int, CtrlRow] = {r.idx5: r for r in FSM_ROWS}


def lookup_row(opcode: int, phase: int) -> CtrlRow | None:
    return FSM_BY_KEY.get((opcode & 0xFF, phase & 3))


def active_idx5_slots() -> list[int]:
    return sorted({r.idx5 for r in FSM_ROWS})
