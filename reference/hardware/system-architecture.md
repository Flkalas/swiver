# Swiver v1.0 sequential — System Architecture

**Version:** 1.0 sequential · **Hardware:** dual-CPLD + non-pipelined in-order CU · **Date:** 2026-10-23
**Status:** Active normative specification

**v1.0 sequential:** **Non-pipelined in-order** execution, a **unified 64 KiB address space** and a **shared instruction/data bus**, including execution from RAM. An instruction completes before the next opcode fetch; operand fetch never overlaps execute. Datapath keeps **R0 (AC)** + **MBR→ALU B**, G-IC **`reg_we`**.

**CU truth:** [cpld-sequential-cu.md](cpld-sequential-cu.md) (bitstream Design fits pending).

---

## 1. Overview

| Item | Specification |
|------|---------------|
| **CPU** | 8-bit TTL datapath: alu8 (12×74HC DIP) + **R0 in CPLD-DP**; **MBR 574 → ALU B** |
| **Control** | **Sequential CU** in **CPLD-CU** — opcode fetch / operand fetch / execute or stack accesses / WAIT; **direct strobes** |
| **ISA** | Opcode **`[4:0]`**; core `0x01–0x0F`; **`0x10–0x1F` reserved**; `0x0C` reserved |
| **System CPLD** | **2× ATF1504AS-10JU44** — CPLD-CU (sequential) + CPLD-DP (R0) |
| **CE decode** | **74HC138×2** + **74HC08/32/04** glue → RAM/ROM `/CE` |
| **Flags / branch** | **574×1 FLG** (Z/C) + CPLD-CU `PC_LOAD_EN` (redirect on final execute) |
| **RAM** | **2× IS62C256AL** — 64 KB via **A15** bank (shared bus) |
| **ROM** | **1× SST39SF010A** — boot + fixed assets (shared bus; RAM is executable) |
| **I/O** | MMIO **Mailbox** @ `$FF00–$FFFB` — polling only, **no IRQ** |
| **Coprocessor** | **RP2350B** — GPU, HID, virtual FDD (separate board) |
| **Sequential wiring** | Shared bus and map-qualified enables; physical implementation and fit pending |

### Metrics (v1.0 sequential)

| Metric | **v1.0 sequential** |
|--------|--------------|
| CU schedule | **Non-pipelined in-order** |
| ADD/CMP default SYS | **3** per instruction, excluding WAIT |
| G-IC wires | **1** (`reg_we`) |
| GPR in CPLD | **R0** |
| Opcode `0x10–0x1F` | **Reserved** |
| Sequential CU bitstream | **Design fits pending** |

---

## 2. Design philosophy

- **Counted timing:** each opcode byte, operand byte and execute/stack phase consumes a SYS; extra delay is visible WAIT.
- **Complete then fetch:** no prefetch and no IF/EX or operand-fetch/execute overlap.
- **Deterministic:** no IRQ; no branch prediction or branch bubbles.
- **AC-centric:** single visible GPR; extra state in **RAM**.
- **Unified memory:** the same mapped 64 KiB and bus serve instruction fetch, data, stack and MMIO; RAM code is executable.
- **Control:** sequential CPLD CU; ROM supplies boot code/assets rather than control words.
- **Physical acceptance:** sequential timing, wiring and WinCUPL Design fits remain pending; old P12 path estimates do not validate them.

---

## 3. Block diagram

```text
  PC / operand / stack address ──► shared A[15:0]
  Flash / SRAM / MMIO ◄──────────► shared 8-bit instruction/data bus
                                         │ IR / operand latch
                                         ▼
                              CPLD-CU sequential FSM
                    reg_we ──► CPLD-DP R0 ──► q_a ──► alu8 A
  MBR / operand latch ──────────────────────────────► alu8 B

  A[15:0] ──► 08/32 mailbox·MAP ──► 74HC138×2 ──► /CE ──► SRAM×2 + SST39
```

Detail: [cpld-sequential-cu.md](cpld-sequential-cu.md) · [cpld-system-controller.md](cpld-system-controller.md) · [cpld-dual-routing.md](cpld-dual-routing.md)

---

## 4. Boot workflow

1. Power on — **MAP_MODE=Boot** (DIP default).
2. **RESET** — fetch @ **`$FFFC`** (**74HC157** addr MUX) → ROM vector → boot @ `$0000–$07FF`.
3. Bootloader: POST → vFDD load (Mailbox) → copy kernel to **RAM `$0800+`** → **`JMP $0800`** or halt.
4. Operator DIP → **Run**, **RESET** → fetch `$FFFC` from **RAM**.

Details: [bootloader.md](../boot/bootloader.md) · [memory-map.md](memory-map.md).

---

## 5. Physical packages

2× CPLD `ATF1504AS-10JU44` + 2× PLCC→DIP; Flash `SST39SF010A`; SRAM `IS62C256`×2; **2.000 MHz** `CLK_SYS` design target (sequential lab validation pending); **574** class for MBR/FLG/IR/ACC plus PC counters. Shopping list: [BOM.md](../project/BOM.md). (Mailbox level-shift / RP2350: [rp2350-coprocessor.md](../copro/rp2350-coprocessor.md).)

**Sequential wiring:** one shared bus, mutually exclusive memory enables and operand hold per [cpld-sequential-cu.md](cpld-sequential-cu.md); keep `net_mbr` → ALU B.

---

## 6. Document index

| Document | Content |
|----------|---------|
| [cpld-sequential-cu.md](cpld-sequential-cu.md) | **Active sequential CU** — states, byte access order, SYS accounting, pending timing/fit |
| [memory-map.md](memory-map.md) | Address map, 138×2 + gate decode |
| [cpld-system-controller.md](cpld-system-controller.md) | Dual CPLD ports; DP R0; CU points to sequential spec |
| [cpld-dual-routing.md](cpld-dual-routing.md) | G-IC, MBR→B wiring |
| [microcode-spec.md](microcode-spec.md) | unchanged ISA + sequential SYS sheet |
| [control-and-decode.md](control-and-decode.md) | Who decodes what |
| [hw-bringup/README.md](../hw-bringup/README.md) | M1–M5 bring-up checklists |

---

## 7. Verification

| Layer | Gate |
|-------|------|
| Spec | [cpld-sequential-cu.md](cpld-sequential-cu.md) |
| Bitstream | WinCUPL **Design fits** on the implemented sequential CU |
| Breadboard | Sequential fetch/execute and shared-bus lab pending; follow sequential CU + M1–M5 |
| Scope | Shared-bus ownership, byte accesses, operand hold, setup/hold, mailbox response; sequential path budgets pending |
