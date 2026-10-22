"""HC283 full-adder truth equations and known-integer convenience wrappers."""

from __future__ import annotations
from simulators.cyclesim.values import from_bits, logic_and, logic_or, logic_xor, to_bits


def full_adder(a: int, b: int, cin: int) -> tuple[int, int]:
    return (
        logic_xor(logic_xor(a, b), cin),
        logic_or(logic_or(logic_and(a, b), logic_and(a, cin)), logic_and(b, cin)),
    )


def add_bits(a: list[int], b: list[int], cin: int) -> tuple[list[int], int]:
    if len(a) != len(b):
        raise ValueError("adder operand widths differ")
    result = []
    for ai, bi in zip(a, b):
        value, cin = full_adder(ai, bi, cin)
        result.append(value)
    return result, cin


def add4(a: int, b: int, cin: int) -> tuple[int | None, int]:
    values, cout = add_bits(to_bits(a, 4), to_bits(b, 4), cin)
    return from_bits(values), cout


def add8(a: int, b: int, cin: int) -> tuple[int | None, int]:
    values, cout = add_bits(to_bits(a), to_bits(b), cin)
    return from_bits(values), cout
