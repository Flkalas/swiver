# Swiver v1.0 P12 — System clock comparison (peer set)

**Audience:** learners comparing **what “MHz” means** on Swiver versus peer machines — master clock, micro-step, ISA throughput, and what limits Fmax.  
**Status:** Archived background (Illustrative for peers) — not Active implementer spec. Swiver timing: Active pipe CU.  
**Related (peers):** [rom-comparison.md](rom-comparison.md) · [cu-dp-comparison.md](cu-dp-comparison.md) · [ttl-computer-comparison.md](ttl-computer-comparison.md)  
**Active:** [cpld-pipe-cu.md](../../../reference/hardware/cpld-pipe-cu.md) · [cpld-dual-timing.md](../../../reference/hardware/cpld-dual-timing.md) · [alu-opcodes-timing.md](../../../reference/hardware/alu-opcodes-timing.md)

---

## 1. Why a clock comparison

Raw oscillator frequency is a poor peer metric. Machines differ in:

- whether **one clock edge = one ISA instruction** or one **µstep / phase**
- whether **control** is combinational, CPLD FSM, or **ROM µfetch** (ROM `t_ACC` on the critical path)
- **effective** guest-ISA rate after interpretation (Novasaur 8080, Isetta 6502/Z80)

This note separates those layers so “Isetta is 12.5 MHz, Swiver is 2 MHz” is not read as a pure performance ranking.

---

## 2. Vocabulary

| Term | Meaning |
|------|---------|
| **Master / board clock** | Oscillator or divided clock distributed on the board |
| **CPU / phase clock** | Clock that advances the sequencer (Swiver phase FSM, Ben Eater µstep, …) |
| **µstep / T-state** | Smallest control quantum (one µword, one 6502 T-cycle, one Novasaur process cycle) |
| **Macro / ISA instruction** | Programmer-visible opcode (may take many µsteps) |
| **Effective ISA rate** | Guest or native instructions completed per second after multi-cycle / interpretation cost |
| **Critical path** | Longest combinational or memory path that must fit in one clock (or half-cycle) budget |

---

## 3. Summary tables

### 3.1 Clock layers

| Machine | Master / board | CPU / µstep clock | Cycle time | Phases per native macro (typ.) | Effective “useful” rate |
|---------|----------------|-------------------|------------|--------------------------------|-------------------------|
| **Swiver Gi1** | **4 MHz** osc → **÷2** | **2.0 MHz** (normative) | **500 ns** full; **250 ns** half | **2–3** phases (ADD, LDA, …) | ~0.7–1 M native macro/s (order) |
| **Gigatron** | ~**6.25 MHz** | Same (1 insn / clk) | **160 ns** | **1** (pipelined) | ~6.25 M native insn/s |
| **Ben Eater** | Build-dep. | ~**0.5–1 MHz** typ. | 1–2 µs | Up to **8** µsteps / insn | Much lower than MHz |
| **Magic-1** | ~**4.09 MHz** | Same + µseq | ~244 ns | Variable µops | Model / µcode dependent |
| **Isetta** | — | **12.5 MHz** µstep | **80 ns** | Up to **16** µsteps / guest insn (page) | Guest ≪ 12.5 MHz |
| **Novasaur** | **33 MHz** dot | **8.25 MHz** / CPU | ~121 ns CPU clk; **~60 ns** mem | **1–4** native; ~**137** native / 8080 | Native ~3.5 MIPS; **~450 kHz** 8080 |
| **Apple II** | Colorburst-derived | **~1.023 MHz** 6502 | ~978 ns | **2–7** T-states / insn | ~0.3–0.5 M insn/s typ. |
| **PDP-11** | Model-dep. | µcycle / core cycle | µs-class (core era) → faster LSI | Many µops | Handbook / model |

### 3.2 What usually limits Fmax

| Machine | Dominant limit on raising the clock |
|---------|-------------------------------------|
| **Swiver Gi1** | **ALU + CPLD + bus** in execute half-cycle; BEQ path **212 ns** vs **250 ns** budget; Flash **not** on control path |
| **Gigatron** | Combinational CU + ALU + RAM/video timing (VGA-driven historically) |
| **Ben Eater** | Breadboard + LS prop; µcode EEPROM access each µstep |
| **Magic-1** | Wide µROM + multi-bus setup; discrete FF farms |
| **Isetta** | **24-bit µcode Flash `t_ACC`** (+ pipeline) each **80 ns** |
| **Novasaur** | **Shared ROM** for fetch / **ALU LUT** / fonts (~60 ns mem window) |
| **Apple II** | **6502 die** + DRAM refresh / video steal (system timing) |
| **PDP-11** | Core memory / UNIBUS / µROM (era- and model-dependent) |

### 3.3 Control-store vs clock (ties to [rom-comparison.md](rom-comparison.md))

| Machine | Control on every µstep? | Memory on that path? |
|---------|-------------------------|----------------------|
| **Swiver** | CPLD LUT | **No Flash** |
| **Gigatron** | Diode ROM (comb) | No EEPROM µstore |
| **Ben Eater** | EEPROM µword | **Yes** |
| **Magic-1** | PROM µword | **Yes** |
| **Isetta** | Flash µword (pipelined) | **Yes** |
| **Novasaur** | ROM native op / ALU table | **Yes** (same chip) |
| **Apple II** | On-die PLA | No board µROM |
| **PDP-11** | µROM (most models) | **Yes** |

---

## 4. Swiver Gi1 — normative clock detail

### 4.1 Generation

| Stage | Part / net | Frequency |
|-------|------------|-----------|
| Crystal | 4.000 MHz half-can | 4 MHz |
| Divide | 74HC74 | **2.0 MHz** → CPU / CPLD `CLK` |
| Buffer | 74HC04 / 74HC14 | Distribution |

BOM: [parts / BOM.md](../project/BOM.md) (#20–#23).

### 4.2 Budget

| Quantity | Value | Source |
|----------|------:|--------|
| Normative clock | **2.0 MHz** | [cpld-dual-timing.md](cpld-dual-timing.md) |
| Full period | **500 ns** | |
| Execute half-cycle | **250 ns** | ALU / ph2 budget |
| Desk ph2 ADD (Gi1) | **~133 ns** | R0∥MBR → ALU |
| BEQ path | **212 ns** | slack **38 ns** @ 250 ns |
| Desk Fmax (ph2 ADD) | **> ~3.7 MHz** | 2 MHz kept for margin + multi-phase macros |

ALU opcode delays vs 250 ns: [alu-opcodes-timing.md](alu-opcodes-timing.md) (INC max **153 ns**, logic **46 ns**).

### 4.3 Macro vs clock

```text
  2 MHz CLK ──► CPLD phase FSM (phase 0..2)
                  │
                  ├─ ph0/ph1: fetch / mem / setup
                  └─ ph2: ALU execute + REG_WE / FLG_WE / PC_LOAD

  One ADD macro ≈ 3 clocks ≈ 1.5 µs @ 2 MHz
  (not “2 MIPS”)
```

Flash appears on **instruction fetch** cycles, not on every control strobe. Raising the oscillator still requires **ALU+CPLD** slack and multi-phase macros to stay correct — not a faster µcode Flash.

---

## 5. Peer clock architectures

### 5.1 Gigatron (~6.25 MHz)

- **One native instruction per clock** (simple pipeline).
- Clock historically tied to **video** timing needs.
- CU is combinational (diode ROM) — no µROM `t_ACC` in the control path; RAM/ROM ports and ALU still bound the period.

### 5.2 Ben Eater (~0.5–1 MHz typical)

- Clock often adjustable; teaching builds stay slow for probes.
- Each µstep: EEPROM address → data → control lines. **µcode access ⊆ cycle budget.**
- Up to **8 µsteps / opcode** → ISA rate ≪ oscillator.

### 5.3 Magic-1 (~4.09 MHz)

- Master clock into microsequencer; **variable-length** µsequences per ISA insn.
- Horizontal µROM width buys flexibility at the cost of PROM timing and wiring.

### 5.4 Isetta (12.5 MHz µstep)

```text
  80 ns cycle:
    [pipelined] read next 24-bit µword from Flash×3
    execute current µword (bus / ALU / latch)
```

- **Board MHz looks high** because the quantum is a **µstep**, not a 6502 instruction.
- A guest `LDA` / `ADD` may consume many of 16 µsteps (or jumped blocks).
- **Flash speed sets the µstep ceiling**; pipeline hides latency but does not remove `t_ACC` from the design.

### 5.5 Novasaur (33 → 8.25 MHz + ~450 kHz 8080)

```text
  33 MHz ──÷4──► 8.25 MHz per CPU/GPU slice
  Mem window ~60 ns (16.5 MHz datapath)
  ROM address mux: program | ALU LUT | font
```

- Native average ~**2.35** process cycles / insn → ~**3.5 MIPS** class.
- **8080 bytecode** ≈ **137** native cycles → **~450 kHz** effective.
- Raising clock stresses **ROM + bus turnaround** (documented overclock caution in project logs).

### 5.6 Apple II (~1.023 MHz)

- 6502 Φ1/Φ2; instructions **2–7** T-states.
- System clock locked to **NTSC-related** timing; video DMA steals cycles.
- Control PLA is **on-die** — board ROM firmware is not the µstep path.

### 5.7 PDP-11 (model-dependent)

- Early machines: **core cycle** (sub-µs to µs) dominates.
- Microcoded models: µROM cycle + UNIBUS arbitration.
- Compare to Magic-1 / Ben Eater in *structure*, not to Swiver’s 2 MHz breadboard number.

---

## 6. Apples-to-apples views

### 6.1 Do not compare raw MHz alone

| Misleading claim | Better framing |
|------------------|----------------|
| “Isetta is 6× faster than Swiver (12.5 vs 2)” | Isetta’s 12.5 MHz is **µsteps**; Swiver’s 2 MHz is **macro phases** — guest 6502 rate is much lower than 12.5 M |
| “Novasaur is 33 MHz” | Dot clock; **CPU slice is 8.25 MHz**; **8080 ≈ 0.45 MHz** |
| “Swiver desk Fmax > 3.7 MHz so raise the crystal” | Normative **2 MHz** keeps BEQ / multi-phase / breadboard margin |

### 6.2 Rough native-throughput sketch (order of magnitude)

```text
  Gigatron     ████████████  ~6 M insn/s (1/clk)
  Novasaur nat ██████        ~3.5 M native/s
  Magic-1      ████          ~few M (µseq)
  Isetta µ     ████████████  12.5 M µstep/s  → guest << that
  Swiver       ██            ~0.7–1 M macro/s @ 2 MHz, 2–3 ph
  Apple II     █             ~0.3–0.5 M insn/s
  Novasaur 8080 ▏            ~0.45 M 8080/s
  Ben Eater    ▏             teaching rates
```

(Bars are illustrative, not lab-measured cross-benchmarks.)

### 6.3 Where Swiver sits

- **Slower raw clock** than Isetta/Novasaur/Gigatron by design (breadboard HC, 250 ns execute budget).
- **Control path without Flash** → raising clock is an **ALU/CPLD/wiring** problem, not a “buy faster µcode Flash” problem ([rom-comparison.md](rom-comparison.md) §5).
- **ISA throughput** is intentionally modest; mailbox / RP2350 covers GPU-class work off-CPU.

---

## 7. Design takeaways

1. Always state **which clock** (dot, CPU, µstep, guest).
2. **ROM-based CU/ALU** machines (Isetta, Novasaur, Ben Eater, Magic-1, PDP-11 µcode) couple **memory `t_ACC`** to Fmax; Swiver couples **combinational ALU + CPLD**.
3. **Interpretation** (Novasaur 8080, Isetta 6502/Z80) makes board MHz a weak proxy for software speed.
4. Swiver’s **2 MHz** is a **margin policy**, not the desk Fmax ceiling (~3.7 MHz on ph2 ADD).
5. Active CU is **pipe** ([cpld-pipe-cu.md](cpld-pipe-cu.md)) — not a dual-clock CPLD-only µstep schedule.

---

## 8. Document index

| Topic | Document |
|-------|----------|
| Gi1 half-cycle paths | [cpld-dual-timing.md](cpld-dual-timing.md) |
| ALU vs 250 ns | [alu-opcodes-timing.md](alu-opcodes-timing.md) |
| ROM roles vs peers | [rom-comparison.md](rom-comparison.md) |
| CU·DP structure | [cu-dp-comparison.md](cu-dp-comparison.md) |
| ISA / stack peers | [ttl-computer-comparison.md](ttl-computer-comparison.md) |
| Pipe CU timing desk | [cpld-pipe-cu.md](cpld-pipe-cu.md) §7 |

---

## Change log

| Date | Note |
|------|------|
| 2026-07-13 | Link dual-clock CU research (`cpld-ustep`) |
| 2026-07-13 | Initial system clock comparison across peer set |
