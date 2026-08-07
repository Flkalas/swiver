# Swiver v1.0 P12 — System Architecture

**Version:** 1.0 P12 · **Hardware:** dual-CPLD + IF\|EX pipe · **Date:** 2026-07-13  
**Status:** Active normative specification

**v1.0 P12:** PE1-class **IF\|EX** pipeline with Harvard-like **PROG∥DATA** ports; **P12** discipline (stretch-on-fail, named FE2 fallback). Datapath keeps **R0 (AC)** + **MBR→ALU B**, G-IC **`reg_we`**.

**CU truth:** [cpld-pipe-cu.md](cpld-pipe-cu.md) (bitstream Design fits pending).

---

## 1. Overview

| Item | Specification |
|------|---------------|
| **CPU** | 8-bit TTL datapath: alu8 (12×74HC DIP) + **R0 in CPLD-DP**; **MBR 574 → ALU B** |
| **Control** | **Pipe CU** in **CPLD-CU** — IF\|EX / stall / stretch / fallback; **direct strobes** |
| **ISA** | Opcode **`[4:0]`**; core `0x01–0x0F`; **`0x10–0x1F` reserved**; `0x0C` reserved |
| **System CPLD** | **2× ATF1504AS-10JU44** — CPLD-CU (pipe) + CPLD-DP (R0) |
| **CE decode** | **74HC138×2** + **74HC08/32/04** glue → RAM/ROM `/CE` |
| **Flags / branch** | **574×1 FLG** (Z/C) + CPLD-CU `PC_LOAD_EN` (bubble on taken) |
| **RAM** | **2× IS62C256AL** — 64 KB via **A15** bank (**DATA** port) |
| **ROM** | **1× SST39SF010A** — boot + program (**PROG** port) |
| **I/O** | MMIO **Mailbox** @ `$FF00–$FFFB` — polling only, **no IRQ** |
| **Coprocessor** | **RP2350B** — GPU, HID, virtual FDD (separate board) |
| **Pipe BOM delta** | ~6–10 DIP-class parts (IR/operand latches, PROG buffers, mux/CE glue) vs shared-bus baseline |

### Metrics (v1.0 P12)

| Metric | **v1.0 P12** |
|--------|--------------|
| CU schedule | **IF\|EX pipe** |
| Steady ALU IPC @ 2 MHz | **~1.0** (optimistic stream) |
| G-IC wires | **1** (`reg_we`) |
| GPR in CPLD | **R0** |
| Opcode `0x10–0x1F` | **Reserved** |
| Pipe CU bitstream | **Design fits pending** |

---

## 2. Design philosophy

- **Transparent timing:** SYS cost is on the pipe/stretch sheet.
- **Overlap fetch and execute** when PROG∥DATA isolation holds.
- **Deterministic:** no IRQ; no branch prediction.
- **AC-centric:** single visible GPR; extra state in **RAM**.
- **ROM as law:** boot + program; control in the CPLD pipe CU.
- **Flat memory:** 64 KiB linear map; **no MMU**.
- **P12 discipline:** stretch before clock hope; FE2 fallback if ports fail.

---

## 3. Block diagram

```text
  PROG Flash ──► IF latch (IR / operand) ──► CPLD-CU pipe FSM
  DATA SRAM/MMIO ◄─ EX strobes (MEM_RD/WR, Y_OE, …) ◄─┘
                    reg_we ──► CPLD-DP R0 ──► q_a ──► alu8 A
  MBR / oper latch ─────────────────────────────────► alu8 B

  A[15:0] ──► 08/32 mailbox·MAP ──► 74HC138×2 ──► /CE ──► SRAM×2 + SST39
```

Detail: [cpld-pipe-cu.md](cpld-pipe-cu.md) · [cpld-system-controller.md](cpld-system-controller.md) · [cpld-dual-routing.md](cpld-dual-routing.md)

---

## 4. Boot workflow

1. Power on — **MAP_MODE=Boot** (DIP default).
2. **RESET** — fetch @ **`$FFFC`** (**74HC157** addr MUX) → ROM vector → boot @ `$0000–$07FF`.
3. Bootloader: POST → vFDD load (Mailbox) → copy kernel to **RAM `$0800+`** → **`JMP $0800`** or halt.
4. Operator DIP → **Run**, **RESET** → fetch `$FFFC` from **RAM**.

Details: [bootloader.md](../boot/bootloader.md) · [memory-map.md](memory-map.md).

---

## 5. Physical packages

2× CPLD `ATF1504AS-10JU44` + 2× PLCC→DIP; Flash `SST39SF010A`; SRAM `IS62C256`×2; **2.000 MHz** `CLK_SYS`; **574** class for MBR/FLG/IR/ACC plus PC counters. Shopping list: [BOM.md](../project/BOM.md). (Mailbox level-shift / RP2350: [rp2350-coprocessor.md](../copro/rp2350-coprocessor.md).)

**Pipe wiring:** PROG isolation / pipe latches per [cpld-pipe-cu.md](cpld-pipe-cu.md); keep `net_mbr` → ALU B.

---

## 6. Document index

| Document | Content |
|----------|---------|
| [cpld-pipe-cu.md](cpld-pipe-cu.md) | **Active pipe CU** — states, bubbles, stretch, timing |
| [memory-map.md](memory-map.md) | Address map, 138×2 + gate decode |
| [cpld-system-controller.md](cpld-system-controller.md) | Dual CPLD ports; DP R0; CU points to pipe |
| [cpld-dual-routing.md](cpld-dual-routing.md) | G-IC, MBR→B wiring |
| [microcode-spec.md](microcode-spec.md) | ISA + pipe SYS sheet |
| [control-and-decode.md](control-and-decode.md) | Who decodes what |
| [hw-bringup/README.md](../hw-bringup/README.md) | M1–M5 bring-up checklists |

---

## 7. Verification

| Layer | Gate |
|-------|------|
| Spec | [cpld-pipe-cu.md](cpld-pipe-cu.md) |
| Bitstream | WinCUPL **Design fits** (pipe CU when written) |
| Breadboard | IF\|EX lab pending; follow pipe CU + M1–M5 |
| Scope | BEQ slack; PROG vs DATA isolation; mailbox RP ≤ 80 ns desk |
