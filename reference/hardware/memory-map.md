# Memory Map v1.0

**Related:** [cpld-system-controller.md](cpld-system-controller.md) · [mailbox-protocol.md](../copro/mailbox-protocol.md)

---

## 1. CPU address space (16-bit)

One unified **64 KiB instruction/data address space** uses one shared address/data bus. Instructions execute from RAM wherever the selected map exposes RAM. Each instruction completes before the next opcode fetch; instruction/operand fetch and data execution do not overlap ([cpld-sequential-cu.md](cpld-sequential-cu.md)).

| Range | Mode A (Boot) | Mode B (Run) | Notes |
|-------|---------------|--------------|-------|
| `$0000–$07FF` | **Boot ROM** (2 KB) | RAM | SST39 low window |
| `$0800–$FEFF` | RAM | RAM | Kernel, data, stack |
| `$FF00–$FFFB` | **Mailbox** (252 B) | Mailbox | Full A15–A0 decode |
| `$FFFC–$FFFF` | **ROM vector** | **RAM vector** | Never Mailbox |

**Decode priority:** `MAILBOX_EN` wins for `$FF00–$FFFB` only. `$FFFC–$FFFF` is excluded from mailbox.

---

## 2. Physical RAM — 2× IS62C256AL

| Chip | `/CE` condition | CPU range |
|------|---------------|-----------|
| **RAM_1** | `A15=0` | `$0000–$7FFF` |
| **RAM_2** | `A15=1` ∧ ¬`MAILBOX_EN` | `$8000–$FFFF` (except mailbox window) |

### 2.1 Breadboard — 74HC138×2 + discrete glue

| Block | Role |
|-------|------|
| **08/32/04** | `MAILBOX_EN`, MAP×A11 boot ROM, final `/CE` combine |
| **74HC138 #2** | Half-select: low 32 KiB vs high 32 KiB (A15, MAP-gated) |
| **74HC138 #1** | CBA = A15,A14,A13 → coarse Y*; E = `!MAILBOX_EN` |
| **CPLD-DP** | GPR only — **no** address decode (CU has no decode) |

Reference: [`decode_ce_breadboard()`](../hw/logic/cpld_decode.py) · [breadboard-wiring.md](../hw-bringup/breadboard-wiring.md).

---

## 3. MAP_MODE (operator manual)

| MAP_MODE | Switch | `$0000–$07FF` | `$FFFC–$FFFF` |
|----------|--------|---------------|---------------|
| 0 | **Boot** | ROM | ROM |
| 1 | **Run** | RAM | RAM |

No automatic map switch from software — operator toggles DIP, then **RESET**.

---

## 4. Flash (SST39) vs CPU map

| Access | Address source |
|--------|----------------|
| Instruction fetch (Mode A boot) | PC → decode glue |
| Utility read | PC or boot copy loops |

Flash physical layout: [rom-architecture.md](rom-architecture.md). Control strobes come from the CPLD-CU sequential FSM; Flash and RAM share the CPU access path.
