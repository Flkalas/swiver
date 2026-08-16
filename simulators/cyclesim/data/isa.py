"""ISA helpers — implements swiver-whitepaper §6 / microcode-spec.md."""


from __future__ import annotations

OP_ADD = 0x01
OP_LDA = 0x02
OP_STA = 0x03
OP_BEQ = 0x04
OP_JMP = 0x05
OP_CALL = 0x06
OP_RET = 0x07
OP_HALT = 0x0A
OP_CMP = 0x0D
OP_LDIO = 0x08
OP_STIO = 0x09
OP_STA16 = 0x0F

WIDE_ABS16_OPS = frozenset({OP_BEQ, OP_JMP, OP_CALL, OP_STA16})


def is_reserved_opcode(opcode: int) -> bool:
    """Gi1 v1.0 — 0x10–0x1F invalid (no TFR); M3b trap/NOP."""
    return (opcode & 0xFF) & 0x10 == 0x10


PHASE_COUNT: dict[int, int] = {
    OP_ADD: 3,
    OP_LDA: 2,
    OP_STA: 2,
    OP_BEQ: 2,
    OP_JMP: 1,
    OP_CALL: 1,
    OP_RET: 1,
    OP_HALT: 1,
    OP_CMP: 3,
    OP_LDIO: 2,
    OP_STIO: 2,
    OP_STA16: 2,
}


def phase_count(opcode: int) -> int:
    op = opcode & 0xFF
    if is_reserved_opcode(op):
        return 1
    return PHASE_COUNT.get(op, 1)


def insn_length(opcode: int) -> int:
    op = opcode & 0xFF
    if op in WIDE_ABS16_OPS:
        return 3
    if op in (OP_HALT, OP_RET) or is_reserved_opcode(op):
        return 1
    return 2
