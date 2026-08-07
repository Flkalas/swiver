# Subset C (S5)

The v0.1 Subset-C compiler is a **bootstrap tool** used to generate small Swiver programs.
It is intentionally tiny and grows only as needed for kernel bring-up.

## Static allocation (normative target)

v1.0 breadboard has no hardware stack or frame pointer. **S5 Subset C** therefore targets **static allocation**: locals and parameters live in **fixed RAM cells** at compile time; **unbounded recursion** is out of scope. See [plover-whitepaper.md](../../plover-whitepaper.md) §2.3.1.

## Supported (v0.1)

- `int main(void) { return <int>; }`
- `int main(void) { return add(<int>, <int>); }` (built-in `add` pattern)

## Output

- Subset C → Swiver asm text → `.sram.hex` (use frozen images in [fixtures](../fixtures/))

## Frozen smoke image

[add_imm-sram.md](../fixtures/add_imm-sram.md) — pre-built program for breadboard.

