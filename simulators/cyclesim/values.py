"""Four-state wire values; packed integers are never wire-value sentinels."""

from __future__ import annotations
from collections.abc import Iterable

L, H, X, Z = 0, 1, 2, 3
VALUE_NAMES = {L: "0", H: "1", X: "X", Z: "Z"}


def validate(value: int) -> int:
    if type(value) is not int or value not in VALUE_NAMES:
        raise ValueError(f"invalid logic value: {value!r}")
    return value


def resolve(values: Iterable[int]) -> int:
    """Resolve equal-strength drivers, ignoring Z independent of order."""
    driven = {validate(v) for v in values} - {Z}
    return Z if not driven else next(iter(driven)) if len(driven) == 1 else X


def logic_not(a: int) -> int:
    return 1 - a if a in (L, H) else X


def logic_and(a: int, b: int) -> int:
    return L if L in (a, b) else H if a == b == H else X


def logic_or(a: int, b: int) -> int:
    return H if H in (a, b) else L if a == b == L else X


def logic_xor(a: int, b: int) -> int:
    return a ^ b if a in (L, H) and b in (L, H) else X


def bit(v: int, i: int) -> int:
    """Extract from a known packed integer (2 and 3 are ordinary numbers)."""
    return (v >> i) & 1


def from_bits(bits: Iterable[int]) -> int | None:
    out = 0
    for i, b in enumerate(bits):
        validate(b)
        if b not in (L, H):
            return None
        out |= b << i
    return out


def to_bits(v: int, width: int = 8) -> list[int]:
    return [(v >> i) & 1 for i in range(width)]
