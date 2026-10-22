# Breadboard v1.0 wiring reference (sequential)

**Normative:** [system-architecture.md](../hardware/system-architecture.md) · [cpld-system-controller.md](../hardware/cpld-system-controller.md) · [cpld-sequential-cu.md](../hardware/cpld-sequential-cu.md) · [cpld-dual-routing.md](../hardware/cpld-dual-routing.md)

Single breadboard target — **v1.0 dual CPLD / sequential CU**. **CPLD-CU** = sequential FSM + strobes; **CPLD-DP** = **R0 + `q_a`**; **MBR 574 → ALU B**; CE/mailbox = **138×2 + glue**.

---

## Block placement (logical)

```text
  ROM ──► IR ──► CPLD-CU ── strobes ──► ALU / MEM / PC
                    │ reg_we
                    └──► CPLD-DP ◄── data bus
                              └── q_a ──► ALU A
  MBR 574 ──────────────────────────────► ALU B

  A[15:0] ──► 138×2 + glue ──► /CE ──► RAM×2 + ROM
```

---

## Control path

Instructions and data share one 64 KiB address space and one address/data bus; RAM is executable. Complete the current instruction before the next fetch. Opcode/operand fetch never overlaps EX.

| Source | Role |
|--------|------|
| **IR[4:0]** | Sequential decode on **CPLD-CU** |
| **MBR 574** | Operand imm8 / abs16; **ALU B** |
| **CPLD-CU** | Direct strobes to SoC |
| **G-IC** | **`reg_we` only** → CPLD-DP (R0 write) |
| **FLG 574** | Z → CU branch |

---

## 574 package count

| IC | Role |
|----|------|
| PC (+161 high) | Instruction address |
| IR | Opcode → CPLD-CU `OPC[4:0]` |
| MBR | Operand / abs16 low; **ALU B source** |
| FLG | Z, C |

This is a logical latch-role list, not a revised procurement count. Preserve [BOM.md](../project/BOM.md) quantities; actual PC, abs16, and return-stack latch allocation must be reconciled against the sequential CU implementation before hardware sign-off.

---

## CPLD ↔ ALU

| Source | ALU / bus |
|--------|-----------|
| CPLD-DP `q_a` | ALU A |
| MBR 574 `net_mbr` | ALU B |
| CPLD-CU strobes | `cin`, `bctrl*`, `lgc*`, `s0`, `s1`, `MEM_*`, `Y_OE`, `FLG_WE`, `PC_LOAD_EN` |

ALU B is driven from **MBR 574** on this path.

---

## Bring-up order

M1 ALU → M2a dual CPLD (JED + MBR→B) → M2b memory → M3a verify → M3b fetch → M4/M5.
