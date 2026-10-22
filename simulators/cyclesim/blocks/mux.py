"""HC153/HC157 selection, with separate packed-address and wire APIs."""

from __future__ import annotations
from simulators.cyclesim.values import H, L, X, from_bits


def mux2(sel: int, a: int, b: int) -> int:
    if sel in (L, H):
        value = a if sel == L else b
        return value if value in (L, H) else X
    return a if a == b and a in (L, H) else X


def mux4(sel: int | None, c0: int, c1: int, c2: int, c3: int) -> int:
    """Packed address 0..3; unknown address is None, never integer X=2."""
    choices = (c0, c1, c2, c3)
    if sel is None:
        return c0 if c0 in (L, H) and all(c == c0 for c in choices) else X
    if type(sel) is not int or not 0 <= sel <= 3:
        raise ValueError("mux4 address must be 0..3 or None")
    value = choices[sel]
    return value if value in (L, H) else X


def mux4_bits(s0: int, s1: int, c0: int, c1: int, c2: int, c3: int) -> int:
    return mux2(s1, mux2(s0, c0, c1), mux2(s0, c2, c3))


def mux4_byte(sel_per_bit: list[int | None], c0: int, c1: int, c2: int, c3: int) -> int | None:
    return from_bits(
        mux4(sel_per_bit[i], *((c >> i) & 1 for c in (c0, c1, c2, c3))) for i in range(8)
    )
