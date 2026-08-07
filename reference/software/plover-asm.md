# Swiver assembler (S1)

**Source extension:** `.pls` (Swiver Language Source). Use frozen `.sram.hex` images in [fixtures](../fixtures/) for breadboard burn.

## Syntax

- Labels: `name:` (absolute address)
- Directives: `.ORG addr`, `.EQU name value`, `.DB n`, `.DW addr16`
- Comments: `; ...`

## Opcodes (normative)

| Mnemonic | Bytes | Operand |
|----------|-------|---------|
| ADD | 2 | imm8 |
| LDA, STA, LDIO, STIO, CMP | 2 | addr8 |
| BEQ, JMP, CALL, STA16 | 3 | addr16 LE |
| LDIO, STIO | 2 | MMIO **offset** from `$FF00` |
| RET, HALT, ADD_RR | 1 | — |

Branch targets use **absolute** 16-bit addresses (label or `$hex`).

## Example

```asm
        .ORG 0
start:  ADD 5
        ADD 3
        HALT
```

## Output

- `.sram.hex` — byte image
- `.lst` — listing
- `.map` — symbol table
