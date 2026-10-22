"""ALU8 golden vectors — b3-opcode.md."""

from __future__ import annotations

import pytest

from simulators.cyclesim.blocks.alu8 import (
    ALU_ADD,
    ALU_CMP,
    ALU_NOP,
    ALU_SUB,
    AluControls,
    eval_alu8,
)


@pytest.mark.parametrize(
    "a,b,ctrl,expect_y",
    [
        (0x00, 0x00, ALU_NOP, 0x00),
        (0xA5, 0xFF, ALU_NOP, 0xA5),
        (0x12, 0x34, ALU_ADD, 0x46),
        (0x12, 0x34, ALU_SUB, 0xDE),
        (0x12, 0x34, ALU_CMP, 0xDE),
    ],
)
def test_alu8_macro_ops(a: int, b: int, ctrl: AluControls, expect_y: int) -> None:
    res = eval_alu8(a, b, ctrl)
    assert res.y == expect_y


def test_alu8_inc() -> None:
    ctrl = AluControls(cin=1, bctrl=0b0000, lgc=0, s0=0, s1=0)
    assert eval_alu8(0x12, 0x00, ctrl).y == 0x13


def test_alu8_cmp_z() -> None:
    res = eval_alu8(0x12, 0x12, ALU_CMP)
    assert res.z is True


def test_logic_result_preserves_physical_carry() -> None:
    ctrl = AluControls(cin=1, bctrl=0xF, lgc=0xA, s0=1)
    res = eval_alu8(0x80, 0, ctrl)
    assert res.y == 0x80 and res.c_hi == 1


def test_unknown_convenience_operand_is_not_zero() -> None:
    res = eval_alu8(None, 0, ALU_ADD)
    assert res.y is None and res.z is None
