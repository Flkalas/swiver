> **SUPERSEDED — historical P12 design (2026-10-23).** This complete prior document is retained as historical design evidence, including its original status labels, estimates and pending gates. None of its Active/normative labels applies to the current CPU. The current normative CU is [cpld-sequential-cu.md](cpld-sequential-cu.md): unified 64 KiB/shared instruction-data bus, RAM execution, non-pipelined in-order execution. P12 overlap, bubble/stretch/fallback schedules, timing and fit projections do not validate the sequential design.

---

# CPLD Pipe CU — v1.0 P12 (Active)

**Status:** Active normative CU specification (**v1.0 P12**)  
**Bitstream:** WinCUPL **Design fits pending** — no Active pipe CU PLD yet  
**Devices:** CPLD-CU on **ATF1504AS-10JU44** (pair with CPLD-DP; DP role unchanged)  
**Related:** [system-architecture.md](system-architecture.md) · [control-and-decode.md](control-and-decode.md) · [cpld-system-controller.md](cpld-system-controller.md) · [microcode-spec.md](microcode-spec.md)

This document is the **single Active CU truth** for v1.0 P12 (IF\|EX pipe).

---

## 1. Design rules

1. **IF\|EX** on each `CLK_SYS` when not stalled — program fetch overlaps execute.
2. **PROG∥DATA** ports — IF must not share the DATA SRAM cycle with EX without a stall.
3. **Every counted SYS** does IF work, EX work, a documented stall/bubble, or stretch.
4. **CPLD FSM** — pipe/stall PLA in CPLD-CU.
5. **Datapath:** ALU A ← R0 (`q_a`); ALU B ← **MBR** `net_mbr`; G-IC **`reg_we` only**.
6. **No branch prediction** — taken redirect = visible bubble.
7. **P12 discipline:** lab fail → **stretch** (+1 visible SYS); ports fail → named **FALLBACK_FE2**; stretch before raising `f_SYS`.
8. **Fit gate:** Design fits when PLD exists — do not publish fitter used-MC counts as normative.

---

## 2. Pipeline model

```text
          SYS tick
             |
    +--------v--------+
    |  IF: PC -> PROG |----> IR / operand latch
    |  (program port) |
    +--------+--------+
             | overlap
    +--------v--------+
    |  EX: ALU / MEM  |----> retire (or stall / stretch)
    |  (data port)    |
    +-----------------+
```

| Stage | Owns | Clock |
|-------|------|-------|
| **IF** | PROG address = PC (or operand offset); latch IR / imm / abs bytes | `CLK_SYS` |
| **EX** | ALU, DATA SRAM / MMIO, `PC_LOAD_EN`, CALL/RET stack assist | `CLK_SYS` |
| **ID** | Decode inside CPLD-CU (combinational or same-edge) | — |

Steady ALU stream (imm already in operand latch from prior IF shadow): **one macro retired per SYS** while IF loads the next opcode.

### Ports

| Port | Device (normative intent) | Use |
|------|---------------------------|-----|
| **PROG** | NOR Flash (insn) via dedicated enable / latch path | IF |
| **DATA** | SRAM (and mailbox window) via existing 245 path | EX loads/stores / stack |

Same physical Flash package may remain on the board; it **must not** contend with DATA on the same SYS without entering **MEM_STALL** or **FALLBACK_FE2**.

---

## 3. State machine (desk-normative)

States are CU modes. Transitions are on `CLK_SYS` unless noted.

| State | Meaning |
|-------|---------|
| **FILL** | Pipe empty after reset / squash; IF only; no retire |
| **IF_EX** | Steady overlap: IF next byte/op; EX current macro (ALU-only) |
| **OPERAND_IF** | Extra format byte on PROG; EX may be idle of DP work this tick (still counted — not “hidden idle phase,” it is IF work) |
| **MEM_STALL** | EX uses DATA; IF held |
| **BRANCH_BUBBLE** | Taken BEQ/JMP/CALL redirect; squash IF; refetch |
| **STACK_EX** | CALL/RET multi-cycle DATA EX (push/pop) |
| **STRETCH** | Lab-driven +1 SYS on a named path (visible) |
| **FALLBACK_FE2** | Serial F then E on shared bus — **named degrade**, not wishful one-tick FE1 |

```text
RESET ──► FILL ──► IF_EX
IF_EX ──operand byte needed──► OPERAND_IF ──► IF_EX
IF_EX ──MEM/MMIO EX──────────► MEM_STALL ──► IF_EX
IF_EX ──taken redirect───────► BRANCH_BUBBLE ──► FILL/IF_EX
IF_EX ──CALL/RET─────────────► STACK_EX (+ BRANCH as needed) ──► IF_EX
any pipe state ──lab fail────► STRETCH ──► prior state
ports isolation fail ────────► FALLBACK_FE2
```

**FALLBACK_FE2** is not the normal Active schedule. Prefer fixing PROG∥DATA isolation; fallback is honesty if isolation cannot hold.

---

## 4. Bubble / SYS tax (optimistic)

```text
SYS ≈ 1                 # retire slot in steady ALU stream
    + operand_extra     # imm/abs bytes not hidden in overlap
    + mem_stall         # DATA conflict (default 1 for MEM/MMIO)
    + branch_bubble     # taken redirect (default 1)
    + stack_extra       # CALL/RET multi-cycle EX
    + stretch           # after lab fail (P12)
```

| Op | Retire | +op | +mem | +br t | +stack | Typical SYS | First stretch |
|----|-------:|----:|-----:|------:|-------:|------------:|---------------|
| ADD | 1 | 1 | 0 | 0 | 0 | **2** (stream → **1**) | rarely |
| CMP | 1 | 1 | 0 | 0 | 0 | **2** (stream → **1**) | split FLG if late |
| LDA / LDIO | 1 | 1 | 1 | 0 | 0 | **3** | +1 → **4** |
| STA / STIO | 1 | 1 | 1 | 0 | 0 | **3** | +1 → **4** |
| BEQ nt | 1 | 2 | 0 | 0 | 0 | **3** | +1 → **4** |
| BEQ t | 1 | 2 | 0 | 1 | 0 | **4** | +1 → **5** |
| JMP | 1 | 2 | 0 | 1 | 0 | **4** | rarely |
| CALL | 1 | 2 | 0 | 1 | 2 | **6** | +1 → **7** |
| RET | 1 | 0 | 0 | 1 | 2 | **4** | +1 → **5** |
| STA16 | 1 | 2 | 1 | 0 | 0 | **4** | +1 → **5** |
| HALT | 1 | 0 | 0 | 0 | 0 | **1** | — |

Optimistic packing: MEM EX packs MEM_RD+REG_WE (or Y_OE+MEM_WR) in **one** EX when lab allows.

---

## 5. Per-op control intent

| Class | IF | EX |
|-------|----|----|
| ADD/CMP | Fetch opcode/imm on PROG (imm may shadow prior EX) | ALU + `Y_OE`/`REG_WE` and/or `FLG_WE`; **MBR hold** for B |
| LDA/LDIO | Operand IF as needed | `MEM_RD` (+ `reg_we`); **MEM_STALL** |
| STA/STIO/STA16 | Operand / abs IF | `Y_OE` + `MEM_WR`; **MEM_STALL** |
| BEQ | Abs16 IF | ALU toward flags; `PC_LOAD_EN` if Z; taken → **BRANCH_BUBBLE** |
| JMP | Abs16 IF | `PC_LOAD_EN`; **BRANCH_BUBBLE** |
| CALL | Abs16 IF | Stack push EX×k + `PC_LOAD_EN`; bubble |
| RET | — | Stack pop EX×k + `PC_LOAD_EN`; bubble |
| HALT | — | Halt hold |

**CALL/RET** stack assist (RP cell `$0F00`, body `$F600–$FEEF`) remains CU-owned — see [microcode-spec.md](microcode-spec.md) §2.3. Multi-cycle DATA EX maps to **STACK_EX**.

**PC_in:** JMP/CALL/BEQ from abs latch; RET from popped stack word (not MBR).

### 5.1 CALL/RET fit desk (Conditional Go)

CALL/RET return-stack assist is **architecturally compatible** with dual-CPLD (R0 + MBR→B, G-IC `reg_we`). Desk budget projects **0 additional I/O pins** and CU MC within the ATF1504AS **64 MC / 32 I/O** part rating with margin.

**Bring-up gate = WinCUPL Design fits** — MC numbers below are **estimates only**, not normative BOM gates.

| Condition | Gate |
|-----------|------|
| Pipe CU **Design fits = Yes** on ATF1504AS | before CU reburn |
| Lab confirms **STACK_EX** push/pop @ **2 MHz** (stretch if needed) | before PASS |
| M2a CALL/RET smoke + M3b fetch/execute on programmed JED | before PASS |

Part rating: ATF1504AS **64 MC**, **32 I/O**. Baseline CU desk ~24–30 MC, ~21/32 I/O ([cpld-system-controller.md](cpld-system-controller.md)).

| Block | MC delta (desk) | Pin delta | Notes |
|-------|----------------:|----------:|-------|
| CALL/RET decode / load path | ~0–2 | 0 | Shares redirect strobes with JMP |
| Stack assist FSM (**STACK_EX**) | ~4–8 | 0 | Reuses `MEM_RD` / `MEM_WR` |
| RP / return_pc internal latch | ~2–4 | 0 | No new addr pins |
| 16-bit push/pop sequencing | ~2 | 0 | Byte bus; multi-cycle EX |
| RET `PC_in` mux | ~1 | **0** | Internal mux |
| Overflow / underflow compare | ~1 | 0 | vs `$F600` / `$FEEF` |
| **Projected CU total** | **~34±2 MC** | **~21/32** | Headroom vs 64 MC rating |

Stack assist must **not** add new `net_addr` outputs or new PC bus pins (RET pop feeds internal `PC_in`).

| Risk | Mitigation |
|------|------------|
| MC overflow on ATF1504 | Design fits on pipe CU PLD |
| STACK_EX longer than one SYS | Stretch / multi-cycle EX; re-lab at low clock first |
| RP race with program stores | Keep `$0F00` CU-only; not a normal LDA/STA target |

---

## 6. Pin / port sketch

### Clock

| Signal | Role |
|--------|------|
| `CLK_SYS` | 2.0 MHz normative desk; IF and EX edge |

### CU inputs (desk)

| Signal | Source | Role |
|--------|--------|------|
| `OPC[4:0]` / IR | IR latch | Decode |
| `FLG_Z` | FLG 574 | BEQ |
| Port / stall sense | PROG vs DATA qualify (glue or CU) | MEM_STALL / FALLBACK |

### CU outputs — SoC strobes

| Signal | Function |
|--------|----------|
| `MEM_RD`, `MEM_WR` | DATA / stack / mailbox |
| `Y_OE` | Bus drive |
| `FLG_WE` | Flag latch |
| `PC_LOAD_EN` | Redirect commit |
| `cin`, `bctrl0`, `bctrl2`, `lgc0..3`, `s0`, `s1` | ALU controls |
| PROG enable / IF latch enables | Isolate program fetch |
| DATA enable qualify | MEM path |

### G-IC (unchanged)

| Signal | Function |
|--------|----------|
| `reg_we` | R0 write → CPLD-DP |

CPLD-DP pin list and R0-only datapath: [cpld-system-controller.md](cpld-system-controller.md).

---

## 7. Timing desk (`CLK_SYS` = 2.0 MHz, T = 500 ns)

Primary budget = **full period 500 ns** (`CLK_SYS` = 2.000 MHz, `IF|EX`).

| Path | path ns | Slack @ 500 |
|------|--------:|------------:|
| IF (Flash→IR) | 165 | **335** |
| EX ADD | 148 | **352** |
| EX MEM | 130 | 370 |
| EX mailbox (RP ≤ 80 ns assume) | 170 | **330** |
| EX BEQ + squash | 227 | **273** |

Desk limiter: **BEQ** (still comfortable @ 500 ns). Mailbox is not the limiter if RP response ≤ 80 ns; else stretch MMIO EX.

Preferred trial above 2 MHz after measured BEQ slack ≥ **50 ns**: **3.6864 MHz**. Prefer stretch before clock hope.

### 7.1 Operand / ADD path (desk, frozen)

R0→A (`q_a`) and MBR→B in **parallel**; ALU Y ≈ **133 ns** on the EX ADD path (see also [alu-opcodes-timing.md](alu-opcodes-timing.md)).

**Branch BEQ:**  
`t_ALU(SUB) + t_FLG + t_CU_merge + t_SETUP(PC) + wire` = 136 + 23 + 15 + 28 + 10 = **212 ns** (slack **288 ns** @ 500 ns).

Normative clock remains **2.0 MHz**; raise only after measured BEQ slack ≥ **50 ns**.

---

## 8. P12 caveats (normative discipline)

1. **Packed ADD/CMP EX** — every counted SYS is IF, EX, stall/bubble, or stretch.
2. **Stretch on fail** — unstable at low SYS → +1 visible SYS; update §4 table.
3. **FALLBACK_FE2** — only if PROG∥DATA isolation fails; serial F+E; IPC drops (ALU stream ~0.33 vs ~1.0).
4. **Optimistic IPC** — P12 does not add a faster schedule than the pipe in §2–§4.

---

## 9. Fit / bitstream

| Item | Status |
|------|--------|
| Active **specification** | This document |
| WinCUPL pipe CU `.pld` | **Not yet** — Design fits when written |
| Machine golden | Pipe golden TBD |

MC desk estimates are non-normative; bring-up gate = **Design fits** only.

---

## 10. Explicit non-claims

- No claim that breadboard already runs IF\|EX lab PASS.
- No Active pipe CU bitstream.
- Executable cyclesim golden may lag the pipe until rewritten — treat as **non-Active** until pipe golden lands.
