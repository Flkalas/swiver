# Swiver v1.0 P12 — CU·DP 소자·구조 비교 (TTL peers)

**Audience:** learners and external reviewers comparing **Swiver v1.0 P12** control-unit and datapath design to other discrete-logic 8-bit machines (plus commercial / minicomputer baselines).  
**Status:** Archived background (Illustrative) — not Active implementer spec.  
**Related (peers):** [ttl-computer-comparison.md](ttl-computer-comparison.md) · [rom-comparison.md](rom-comparison.md)  
**Active:** [system-architecture.md](../../../reference/hardware/system-architecture.md) · [control-and-decode.md](../../../reference/hardware/control-and-decode.md) · [cpld-pipe-cu.md](../../../reference/hardware/cpld-pipe-cu.md) · [cpld-system-controller.md](../../../reference/hardware/cpld-system-controller.md)

---

## 1. Scope

This report focuses on **control unit (CU)** and **datapath (DP)** — chips, register placement, operand routing, and sequencing — for **eight** machines:

| Machine | Why included |
|---------|----------------|
| **Swiver v1.0 P12** | Normative breadboard target (pipe CU) |
| **Gigatron** | Closest ALU/AC cousin (153 bit-slice) |
| **Ben Eater 8-bit** | Canonical EEPROM horizontal microcode teaching path |
| **Magic-1** | Full-scale TTL with hardware stack and wide ROM microstore |
| **Isetta** | **6502/Z80 emulation** from 24-bit Flash microcode; thin HW register file |
| **Novasaur** | **8080 bytecode** layer; ROM-as-ALU nibble path; dual CPU/GPU Harvard |
| **Apple II** | Commercial **6502 die** baseline — CU·DP on-chip; board TTL is memory/video glue |
| **PDP-11** | Commercial **16-bit minicomputer** baseline — orthogonal GPRs, HW SP=PC in register file, microcoded family |

**Apple II** and **PDP-11** are **not** TTL homebrew CPUs. They are historical CU·DP references: Apple II for 8-bit AC+index ecosystems; PDP-11 for register-rich orthogonal ISA (closest *architecture* cousin among baselines to Magic-1).

For stack growth, hosted `CALL`/`RET`, and emulation ISA summary, see [ttl-computer-comparison.md](ttl-computer-comparison.md).

---

## 2. Executive summary

Swiver Gi1 splits **CU** and **DP** across **two CPLD chips**. Peers use **EEPROM/ROM horizontal microcode** (Ben Eater, Magic-1, Isetta), **combinational ROM decode** (Gigatron), **ROM µprog + ROM ALU LUT** (Novasaur), a **monolithic hardwired PLA** (Apple II / 6502), or a **16-bit microprogrammed minicomputer** (PDP-11 family).

### 2.1 TTL / discrete peers (8-bit class)

| Axis | Swiver Gi1 | Ben Eater | Gigatron | Magic-1 | Isetta | Novasaur |
|------|------------|-----------|----------|---------|--------|----------|
| **CU core** | CPLD idx5 FSM | EEPROM ×2 | Diode ROM matrix | PROM ×5 (56b µword) | **24b Flash µcode** ×3 | ROM µprog + **PAL** |
| **Native / exposed ISA** | Swiver macros | Microcoded 8-bit | Gigatron vCPU | Magic-1 | *(none)* | Novasaur native |
| **Emulated ISA** | — | — | — | — | **6502 + Z80** | **8080** (bytecode) |
| **DP GPR (HW)** | **R0 only** (CPLD-DP) | **A, B** (173) | **AC** + X/Y/D | **A, B, C** + SP… | **A, T**; PC; **DPH/DPL** | **A, HL**; X, Y; PC, Pg |
| **Registers in RAM** | Variables + **RP** | — (SP in HW) | vSP, temps | — | **6502 X,Y,S**; Z80 sets | **8080 model** in firmware |
| **ALU B operand** | **MBR 574 direct** | **B reg** → bus | Bus / D / RAM | MDR / imm (R bus) | Bus (µ-sequenced) | **ROM ALU LUT** (nibble) |
| **Phase / µstep** | 2b phase in CPLD | EEPROM step cnt | 1 cyc / insn | µseq `next` | **4b step** + **4b page** | 4-cycle fetch/read/exec/write |
| **Stack** | RAM `$0F00` + CU assist | **HW SP** | vSP (zero page) | **HW SP** | **6502 S in RAM** | **8080 SP** in interpreter |

### 2.2 Commercial / historical baselines

| Axis | Swiver Gi1 | **Apple II** | **PDP-11** |
|------|------------|--------------|------------|
| **CU core** | CPLD idx5 FSM | **On-die PLA** (6502) | **Microcode** (11/40+, LSI-11); early 11/20 combined path |
| **Data / address** | **8 / 16** | **8 / 16** | **16 / 16** (+ MMU on later models) |
| **Native ISA** | Swiver macros | **6502** | **PDP-11** (orthogonal) |
| **DP GPR (HW)** | **R0 only** | **A, X, Y** | **R0–R5**; **R6=SP**; **R7=PC** |
| **ALU** | 153 bit-slice (12 DIP) | On-die | On-board / LSI ALU (model-dependent) |
| **Stack** | RAM RP + CU assist | **HW S** → page `$01` | **HW R6 (SP)**; grows **down** |
| **Interrupts** | **None** (v1.0) | IRQ / NMI | Vectored IRQ via UNIBUS / stack |

**Key difference:** Swiver does **not** use program Flash as a control store. A CPLD FSM emits **14 direct strobes**. The DP keeps a **single GPR (R0)** and routes operand B through **MBR → ALU B** off-chip. Apple II puts CU·DP in one 8-bit die; PDP-11 puts eight **16-bit** GPRs (including SP and PC) in a minicomputer datapath — the opposite of Gi1’s thin AC model.

---

## 3. Swiver Gi1 — CU·DP structure

### 3.1 Block diagram

```text
                    ┌── CPLD-CU (idx5 FSM) ──────────────────────┐
  IR[4:0] ─────────►│  (opcode<<2)|phase  →  14 strobes          │
  FLG_Z ───────────►│  branch: PC_LOAD_EN @ macro_end            │
                    │  CALL/RET: stack assist @ macro_end        │
                    └── reg_we (G-IC, 1-wire) ───────────────────┤
                                                                   │
  d_bus[7:0] ──► CPLD-DP (R0, 8 FF) ── q_a ──► ALU A              │
                                                                   │
  MBR 574 Q ───────────────────────────────────► ALU B (off-CPLD)  │
                                                                   ▼
                    ALU 12 DIP (283×2 + 153×8 + 157×2) ──► Y → bus
```

### 3.2 Control unit (CU)

| Item | Swiver Gi1 |
|------|------------|
| **Chip** | **ATF1504AS** ×1 (CPLD-CU) |
| **Control store** | **CPLD internal PLA/LUT** — Flash `$4000` CW **unused** |
| **FSM index** | `fsm_index = (opcode[4:0] << 2) \| phase[1:0]` → 128 slots |
| **Inputs** | `OPC[4:0]` (IR574), `FLG_Z`, `CLK` (7 pins) |
| **Outputs** | **14 SoC strobes** + **1 G-IC** (`reg_we`) |
| **Strobes** | `MEM_RD/WR`, `Y_OE`, `FLG_WE`, `PC_LOAD_EN`, 9 ALU control nets |
| **Pin budget** | ~21/32 used |
| **Special** | CALL/RET implicit push/pop to RP (`$0F00`) and stack RAM @ macro_end |

The CU does not read a wide horizontal µword each cycle. Each **opcode×phase row** is the control row; ALU controls (`cin`, `bctrl*`, `lgc*`, `s0/s1`) are driven **directly** from the CU (no `alu8_decode` DIP on SoC).

### 3.3 Datapath (DP)

| Item | Swiver Gi1 |
|------|------------|
| **Chip** | **ATF1504AS** ×1 (CPLD-DP) |
| **GPR** | **R0 (AC) — 8 FF** — sole programmer-visible register in CPLD |
| **Inputs** | `d_in[7:0]`, `reg_we`, `CLK` |
| **Outputs** | `q_a[7:0]` → ALU A (async read) |
| **Pin budget** | 17/32 used |
| **Off-CPLD DP parts** | **574×3** (PC/MBR/FLG), **161×3** (PC/phase), **245×1** (bus) |
| **ALU B** | **MBR 574 → `net_mbr` → `net_b`** (no CPLD `q_b`) |

**MBR hold:** For ADD/CMP (ALU_REG macros), imm8 latched at fetch must **not** reload until macro completes — MBR holds ALU B.

### 3.4 Discrete TTL vs CPLD split

| Function | Where |
|----------|-------|
| Fetch, PC | 574 + 161 + 157 MUX + CU strobes |
| Opcode decode | **CPLD-CU** |
| GPR (AC) | **CPLD-DP** |
| Operand B | **MBR 574** (outside DP CPLD) |
| ALU | 74HC 12 DIP (Gigatron 153 bit-slice) |
| Flags Z/C | 574 FLG + CU `FLG_WE` |
| Memory `/CE` | 138×2 + 08/32/04 (off CPLD) |

---

## 4. Peer machines — CU·DP detail

### 4.1 Ben Eater 8-bit

**CU**

| Item | Detail |
|------|--------|
| Core parts | **EEPROM** (28C16 class) ×2 — **horizontal microcode** |
| Address | `opcode[3:0]` + **µstep counter** + **flag bits** |
| µword width | ~16 bits — `CO`, `MI`, `RO`, `II`, `CE`, `AI`, `BI`, `EO`, `AO`, `RI`, `SU`, `FI`, `J`, `HLT`, … |
| Steps / insn | Up to **8 micro-steps** per opcode (Arduino EEPROM burn) |
| Patchability | EEPROM reprogram — easy lab control-flow changes |

**DP**

| Register | Part | Role |
|----------|------|------|
| **A** | 74LS173 ×2 | GPR; ALU result target |
| **B** | 74LS173 ×2 | GPR; **ALU B operand** |
| **IR** | 74LS173 ×2 | Current instruction |
| **MAR** | 74LS173/161 | Memory address |
| **SP** | 74LS161/173 | **Hardware stack pointer** |
| **OUT** | 74LS173 | Display output |
| **Flags** | ALU flip-flops | Z, C |

**Structure:** CU and DP connect through a **tri-state bus**. Microcode names who drives the bus and who latches each cycle. **Both A and B** are DP registers; ADD uses `B → ALU B`, `A → ALU A`.

---

### 4.2 Gigatron

**CU**

| Item | Detail |
|------|--------|
| Core parts | **Diode ROM matrix** (combinational) |
| Inputs | 8-bit IR + AC7, carry, etc. |
| Outputs | **19 control signals** — `/DE`, `/OE`, `/AE`, ALU op, `/WE`, `/PL`, … |
| Timing | Mostly combinational; `/WE` etc. synced to clock phase 2 |
| µstore | **None** — opcode bit fields map directly to control patterns |

**DP**

| Register | Part | Role |
|----------|------|------|
| **AC** | 74HCT377/573 | Accumulator — ALU result |
| **X, Y** | 377 | 16-bit **address** (MAU) |
| **D** | 377 | Data / operand |
| **IN, OUT** | 377 + 595 | I/O |
| **PC** | 161 ×4 | Program counter |
| **IR** | 273 | Instruction |

**Structure:** **Harvard** (split ROM/RAM), **one instruction per clock** pipeline. CU is almost a **pure combinational decoder** — no EEPROM sequencer. ALU matches Swiver: **153×8 + 283×2** bit-slice (~10 IC). ~**36 TTL IC** total.

**vs Swiver:** Same AC-centric RAM-backed philosophy and ALU family; Gigatron CU is one ROM table, Swiver uses **CPLD FSM + multi-phase macros**; Gigatron has X/Y address registers in DP, Swiver uses **MBR+PC** for address and operands.

---

### 4.3 Magic-1

**CU**

| Item | Detail |
|------|--------|
| Core parts | **512×8 PROM ×5** → **56-bit micro-instruction** |
| Indexing | Opcode is **direct µstore index** (avoids lookup latency) |
| µword fields | `next`(8), `latch`(4), `lmar`, `e_l`/`e_r`/`e_z`(4 each), `alu`(4), `misc`(4), … |
| Sequencer | `next` field + conditional branch + fetch µop (0x100) + trap/interrupt |
| Patchability | PROM/EPROM burn — most flexible, largest BOM/wiring |

**DP**

| Register | Part | Role |
|----------|------|------|
| **A, B, C** | 74374 ×2 each | GPR — drive L/R buses |
| **PC, SP, DP, SSP** | 74273 + 74241 | 16-bit pointer class |
| **MAR, MDR** | 74273/74374 | Memory interface |
| **MSW** | 74273 | N, Z, C, V + mode bits |
| **IR, PTB, TPC** | 74273 | Control / paging |

**Internal buses:** **L, R** (ALU operands), **Z** (ALU result) — µcode `e_l`/`e_r`/`e_z` ensures **one driver per bus**.

**ALU:** 74F381/382 + 182 (74181 family) — **not** the 153 bit-slice used by Swiver/Gigatron.

**Structure:** Largest CU+DP split. Every register is a **physical 374/273**; microcode bit fields control buses, latches, ALU, and branches together. SP is a **hardware register** (µcode `latch:0x5`).

---

### 4.4 Isetta

**CU**

| Item | Detail |
|------|--------|
| Core parts | **24-bit Flash microcode** in **3 Flash chips** (pipelined fetch, Harvard-style) |
| µaddress | `IR[7:0]` + **4-bit step counter** + **4-bit page register** + **1-bit F flag** (two µ-tracks) |
| Pages | **16 pages** (expandable to 32) — page 1 = 6502, page 2+ = Z80; on-the-fly ISA switch via page load at insn end |
| µword / cycle | One **24-bit µ-instruction per 80 ns cycle** (12.5 MHz µstep clock) |
| Scope | CPU plus **microcoded video, sound, and I/O** processors (additional ~9 TTL on I/O board) |
| Patchability | Flash reburn — retargetable to other ISAs in principle |
| Design rule | **No CPLD, PAL, GAL, FPGA, or 74181** — only discrete TTL + Flash |

**DP (hardware registers)**

| Register | Role |
|----------|------|
| **A** | Accumulator — shared by 6502 and Z80 emulation |
| **T** | Temp — enables RMW ops without disturbing A |
| **PCH/PCL** | 16-bit program counter |
| **DPH/DPL** | 16-bit data pointer (primary memory address source) |
| **IR** | Instruction register (fetched opcode byte) |
| **CGL/CGH** | Constant generators on address bus (zero page / small immediates) |
| **MBANK** | RAM bank select (up to 1 MiB) |

**Registers in RAM (not HW):** 6502 **X, Y, S**; Z80 register sets (**BC, DE, HL**, alternate banks in 64-byte scratch ranges via `EXX`).

**ALU:** **74AC283** ×2 + multiplexers — µcode-sequenced, **not** the 153 Gigatron bit-slice. Flags **N, C**, plus internal **TC**; conditionals use µcode **F** track select.

**Structure:** ~**42 TTL IC** total. Minimal HW register file by design — most 6502/Z80 state lives in **banked RAM**. CU is entirely **Flash microcode**; each guest opcode maps to up to **16 µsteps** per page (longer sequences via µjump). Similar *thin HW pointer* philosophy to Swiver (one data pointer + AC), but **emulation** is the goal, not a native macro ISA.

**vs Swiver:** Both keep stack/index state in RAM without HW SP/S. Swiver uses **CPLD FSM + native idx5**; Isetta uses **3× wider Flash µstore** to **be** 6502/Z80. Operand B comes from bus/RAM under µcode, not a dedicated MBR→ALU wire.

---

### 4.5 Novasaur

**CU**

| Item | Detail |
|------|--------|
| Core parts | **256 KiB ROM** (program + **96 KiB ALU LUT** + fonts/cold storage) + **1 PAL** glue |
| Architecture | **Dual Harvard** — **CPU** and **GPU** (DMA video) on alternating 4-phase clock cycles |
| Native sequencing | **4-cycle** macro per native insn: fetch → read → execute → write |
| Clock | 33 MHz dot clock → **8.25 MHz** per processor (~60 ns memory cycle) |
| 8080 path | **Bytecode interpreter** in ROM firmware — guest 8080 is **not** direct µcode |
| Chip count | **~22 TTL** (CPU proper) + **~12 TTL** (GPU/DMA) + ROM + RAM + PAL |

**DP (native CPU registers)**

| Register | Width | Role |
|----------|-------|------|
| **A** | 8b | Accumulator — ALU result default |
| **HL** | 4b+4b | Dual nibble operand / secondary acc |
| **X, Y** | 8b each | Address index (16-bit effective) |
| **V** | 8b | Vertical line counter (GPU assist) |
| **E** | 8b | Expansion / system state |
| **PC, Pg** | 8b+8b | Program counter + page |

**ALU:** **Not a discrete arithmetic chip** — **ROM lookup table** performs **76 functions** on **4-bit nibbles** over 1–4 native cycles (FN8/FN4/FNH sets: ADD, SUB, MUL, DIV, unary, etc.). Same ROM serves **program fetch** and **ALU execute** (time-multiplexed address bus).

**8080 emulation DP:** Full **8080 register file, stack, and flags** live in **interpreter state** (RAM/firmware), not as 74xx register chips. Effective 8080 speed ~**450 kHz** (~137 native cycles per 8080 instruction).

**Structure:** Software-defined CPU — schematic shows buses and latches; behavior is in **ROM microprogram + ALU tables**. GPU is a **transparent-mode DMA controller**, not a second GPR file. Opposite extreme from Magic-1’s per-register 374 farm: **minimal TTL, maximal ROM**.

**vs Swiver:** Both avoid exposing a rich GPR file in silicon. Swiver’s ALU is **combinational 153+283** with CPLD strobes; Novasaur’s ALU is **ROM LUT** with nibble serialization. Swiver targets **native** bring-up; Novasaur trades native speed for **8080/CP/M compatibility**.

---

### 4.6 Apple II (MOS 6502 baseline)

**Not a TTL CPU.** Included as the commercial reference that Isetta emulates and that many AC-centric homebrew designs compare against in software.

**CU (inside 6502 die)**

| Item | Detail |
|------|--------|
| Core | **Hardwired PLA / decode ROM** on the MOS 6502 die — not an external EEPROM/Flash µstore |
| Timing | Two-phase clock (**Φ1 / Φ2**); instructions take a fixed number of **T-states** (typically 2–7 cycles) |
| Sequencing | On-die state machine driven by decode PLA; no breadboard-visible µword |
| Interrupts | **IRQ**, **NMI**, **RESET** — first-class (unlike Swiver / Gigatron v1.0 path) |
| Patchability | None at board level — change the die or run different machine code |

**DP (inside 6502 die)**

| Register | Width | Role |
|----------|-------|------|
| **A** | 8b | Accumulator — primary ALU operand / result |
| **X, Y** | 8b each | Index registers (addressing, loops, zp,X / abs,Y) |
| **S** | 8b | **Hardware stack pointer** — stack fixed in page `$01` |
| **PC** | 16b | Program counter |
| **P** | 8b | Status: **N, V, B, D, I, Z, C** |

**ALU:** On-die arithmetic/logic unit; operands from A and internal buses (memory / imm), not discrete 153/283 DIPs.

**Board-level TTL (not CU·DP):** Apple II motherboard uses discrete logic for **video timing**, soft switches, DRAM refresh, and I/O decoding (Wozniak design). Those chips are **system glue**, not the processor CU/DP.

**Structure:** Entire programmer-visible CU·DP is **one 40-pin DIP**. Contrast with Swiver (2× CPLD + 12 DIP ALU + 574s), Gigatron (~36 TTL), and Isetta (~42 TTL emulating this same ISA).

**vs Swiver:** Apple II has **HW S + X/Y + full flags + IRQ**; Swiver has **R0 only**, **RAM RP**, **Z/C**, **no IRQ**. Closest *software* peer for 6502 code is **Isetta** (emulation), not Gi1.

**vs Isetta:** Same guest ISA family; Apple II implements it in **silicon**, Isetta in **24-bit Flash µcode** with X/Y/S in RAM.

---

### 4.7 PDP-11 (DEC minicomputer baseline)

**Not an 8-bit TTL homebrew.** Included as the register-rich orthogonal ISA baseline — closest *architecture* peer among commercial machines to Magic-1’s multi-GPR + HW SP + microcode style.

**CU (family-dependent)**

| Item | Detail |
|------|--------|
| Early (e.g. **11/20**) | Datapath and control closely coupled; limited / early microprogramming |
| Mid/late (e.g. **11/40**, **LSI-11**) | **Horizontal microcode** ROM drives ALU, register file, and **UNIBUS** cycles |
| Sequencing | Fetch → address-mode evaluation → execute; µbranches on condition codes and IR bits |
| Interrupts | **Vectored** IRQ/traps push **PC + PS** on system stack; priority in Processor Status |
| Patchability | Field service µcode / board replacement — not a breadboard EEPROM lab |

**DP**

| Register | Width | Role |
|----------|-------|------|
| **R0–R5** | 16b each | General-purpose — accumulators, indexes, autoinc/dec |
| **R6 (SP)** | 16b | **Hardware stack pointer** (kernel/user stacks on richer models) |
| **R7 (PC)** | 16b | **Program counter** — also a general register (relative addressing) |
| **PS / PSW** | 16b | Condition codes **N, Z, V, C**; priority; mode bits |

**ALU:** 16-bit arithmetic/logic (implementation varies by model — discrete MSI or LSI). **Eight addressing modes** apply to any GPR (register, deferred, auto±, indexed, etc.) — operands often come from memory *as if* registers (memory-memory ops).

**Bus:** **UNIBUS** (later **Q-bus** on LSI-11) — memory and device registers share one address space.

**Structure:** Full minicomputer board set (or LSI chip set). Opposite of Swiver: **eight 16-bit GPRs**, SP and PC in the register file, rich orthogonal ISA, interrupts first-class.

**vs Swiver:** PDP-11 is **16-bit**, multi-GPR, HW SP, IRQ; Gi1 is **8-bit**, **R0 only**, RAM RP, no IRQ.

**vs Magic-1:** Same *class* of design goals (HW SP, wide microstore, rich native ISA). Magic-1 is a homebrew TTL realization; PDP-11 is the commercial ancestor of that style.

**vs Apple II:** Both commercial; Apple II is AC+index 8-bit; PDP-11 is general-register 16-bit.

---

## 5. CU structure contrast

```text
Ben Eater / Magic-1          Isetta                     Novasaur
──────────────────          ──────                     ────────
EEPROM/ROM µword            24-bit Flash µword         ROM µprog + 96k ALU LUT
  native ISA steps            emulates 6502/Z80          native + 8080 bytecode
  SP in register file         X/Y/S in RAM               8080 SP in interpreter

Gigatron                    Swiver Gi1                 Apple II / PDP-11
────────                    ──────────                 ─────────────────
Diode ROM matrix            CPLD idx5 row              PLA (8b) / µcode (16b)
IR → 19 ctrl lines          few phases / macro         T-states / µseq
vSP in zero page            RP in RAM @ $0F00          HW S / HW R6=SP
```

| Item | Swiver | Ben Eater | Gigatron | Magic-1 | Isetta | Novasaur | Apple II | **PDP-11** |
|------|--------|-----------|----------|---------|--------|----------|----------|------------|
| **Control medium** | CPLD LUT | EEPROM | Diode ROM | PROM | Flash µcode | ROM + PAL | On-die PLA | **µROM** (typ.) |
| **µword width** | Per-row constants | ~16b × 8 | Combinational | **56 bits** | **24 bits** | Native + ALU LUT | *(internal)* | **Wide** (model-dep.) |
| **Opcode → control** | FSM index | EEPROM addr | IR fields | PROM index | IR+page+step | Native / 8080 VM | Die decode | µseq + IR |
| **Phase / µstep** | 2b in CPLD | Ext. counter | Pipeline | µseq `next` | 4b step+page | 4-cycle macro | Φ1/Φ2 | µcycles |
| **Conditional branch** | `FLG_Z` | µaddr flags | IR cond | MSW + µbranch | F-track | Native/8080 | **Bcc** | **Bcc** on NZVC |
| **Lab patch** | JTAG CPLD | Arduino EEPROM | ROM rewire | PROM | Flash | ROM | Replace CPU | Field µcode / board |
| **CU BOM** | 1 CPLD | EEPROM+cnt | Diodes | 5 PROM | 3 Flash | ROM+PAL | 1× 6502 | Board / LSI set |

---

## 6. DP structure contrast

### 6.1 Register file

| | Swiver Gi1 | Ben Eater | Gigatron | Magic-1 | Isetta | Novasaur | Apple II | **PDP-11** |
|---|------------|-----------|----------|---------|--------|----------|----------|------------|
| **GPR count (HW)** | **1** (R0) | **2** (A, B) | **1** (AC)+D | **3+** | **2** (A, T) | A+HL | **3** (A,X,Y) | **8** (R0–R7) |
| **GPR implementation** | CPLD MC | 74LS173 | 74HCT377 | 74374 | 74xx | 74xx | On-die | Board / LSI |
| **SP / stack index** | RAM `$0F00` | **HW SP** | RAM vSP | **HW SP** | S in RAM | 8080 SP in VM | **HW S** | **R6 (SP)** |
| **Address regs** | PC + MBR | MAR | X, Y | MAR, DP, PTB | PC + DP | X, Y, PC, Pg | PC + X/Y | **Any Rn** + modes |
| **IR** | 574 | 173 | 273 | 273 | 74xx | ROM fetch | On-die | Processor IR |
| **Flags** | Z, C | Z, C | Z, C | N,Z,C,V | N, C, TC | Per 8080 | N,V,B,D,I,Z,C | **N, Z, V, C** (PS) |

### 6.2 ALU and operand paths

| | Swiver | Ben Eater | Gigatron | Magic-1 | Isetta | Novasaur | Apple II | **PDP-11** |
|---|--------|-----------|----------|---------|--------|----------|----------|------------|
| **ALU style** | 153 bit-slice | 283 + logic | 153 bit-slice | 381/382 | 283×2 + mux | ROM LUT | On-die | **16-bit** ALU |
| **ALU A** | CPLD `q_a` | A → bus | AC / bus | A → L | A | A | A | Any Rn / mem |
| **ALU B** | **MBR direct** | B → bus | D / RAM | MDR / imm | Bus (µcode) | HL / ROM | Mem / imm | Any Rn / mem |
| **Result latch** | `reg_we`→R0 | AI→A | /AE→AC | latch→A | µcode→A/T | →A | A / RMW | Rn / mem |
| **Immediate** | MBR hold | Bus | IR / D | MDR | CGL | ROM field | Opcode stream | Immediate mode |

Gi1 **MBR → ALU B** (vs rev G CPLD `q_b`) cuts DP CPLD pins to **17/32** and eliminates a separate B register for imm8 ops.

### 6.3 Bus and memory interface

| | Swiver | Ben Eater | Gigatron | Magic-1 | Isetta | Novasaur | Apple II | **PDP-11** |
|---|--------|-----------|----------|---------|--------|----------|----------|------------|
| **Data bus** | 8b + 245 | 8b | 8b | L/R/Z | 8b | 8b CPU/GPU | 8b | **16b UNIBUS** |
| **Address width** | 16b | 16b | 16b | **24b** | 16b+bank | 16b+Pg | 16b | **16b** (+MMU) |
| **Memory model** | von Neumann | von Neumann | Harvard | von Neumann (+page) | von Neumann (banked) | Dual Harvard | von Neumann | von Neumann (+MMU) |
| **`/CE` decode** | 138×2 + glue | µcode CE | 138/139 | µcode+PTB | MBANK | ROM/RAM mux | Soft switches | UNIBUS map |

*Memory model:* **von Neumann** = shared instruction/data address space (also called Princeton); **Harvard** = separate instruction and data paths. Detail and chip-level context: [ttl-computer-comparison.md](ttl-computer-comparison.md) §2 · [rom-comparison.md](rom-comparison.md) §2.

---

## 7. Design philosophy

### 7.1 Control-model spectrum

```text
  Fixed / minimal ◄──────────────────────────────────────────────────────────► Flexible / complex

  Gigatron  Swiver   Apple II  Ben Eater  Isetta    Magic-1   PDP-11      Novasaur
  comb ROM  CPLD FSM on-die    EEPROM µ   Flash µ   horiz µ   µROM 16b    ROM µ+ALU LUT
            native   6502      native     6502/Z80  native    orthogonal  + 8080 VM
```

- **Gigatron:** Thinnest CU — IR is the control pattern; more DP registers, fewer CU chips.
- **Swiver:** Phase FSM in CPLD, **no µstore**; native macro ISA; CALL/RET via CU stack assist.
- **Apple II:** **Monolithic** 8-bit CU·DP — richest hobby software ecosystem of its era.
- **Ben Eater:** Best teaching EEPROM lab — one µcode line per bus cycle; standard A/B/IR/SP DP.
- **Magic-1:** Maximum native TTL visibility — every register and bus is a physical chip.
- **Isetta:** **Retargetable Flash µcode** — thin HW emulates full 6502/Z80 register sets in RAM.
- **PDP-11:** Commercial **16-bit** orthogonal register machine — HW SP=PC in GPR file; microcoded family.
- **Novasaur:** **Minimal native TTL** — ALU is ROM; 8080 compatibility via **bytecode interpreter**.

### 7.2 Swiver-specific traits

1. **Dual CPLD split:** CU (sequencer + decode) / DP (GPR) — G-IC is **`reg_we` only** (1 wire).
2. **GPR inside CPLD, B outside:** Operand B separated from register file — smaller DP area and wiring.
3. **FSM-only idx5:** Flash `$4000` CW path retired — program ROM holds code only.
4. **CU stack assist:** CALL/RET without HW SP — Magic-1-grade subroutines, Gigatron-thin registers.

### 7.3 Trade-offs

| Swiver choice | Benefit | Cost |
|---------------|---------|------|
| CPLD FSM (not EEPROM) | Single-chip phase control; no breadboard CW latch | WinCUPL fit limit; no lab µcode EEPROM patch |
| R0 only + MBR→B | DP 17 pins; ph2 ADD ~133 ns | No `PUSH`/`POP`; variables in RAM |
| RAM RP (no HW SP) | No SP register / dec glue | Stack overflow → Halt; SW convention |
| 153 ALU (Gigatron class) | Proven bit-slice vs 74181 | Less per-op ALU richness than Magic-1 |

---

## 8. CU·DP BOM snapshot

| Block | Swiver Gi1 | Ben Eater | Gigatron | Magic-1 | Isetta | Novasaur | Apple II | **PDP-11** |
|-------|------------|-----------|----------|---------|--------|----------|----------|------------|
| **Control** | ATF1504 CU | EEPROM ×2 | Diode ROM | PROM ×5 | Flash ×3 | ROM+PAL | Inside 6502 | **µROM board/LSI** |
| **GPR / latch** | ATF1504 DP | 173 ×6 | 377 ×5+ | 374/273 ×20+ | 74xx | 74xx | Inside 6502 | **R0–R7 file** |
| **ALU** | 12 DIP 153 | 283×2 | 10 IC 153 | 381/382 | 283×2 | ROM LUT | Inside 6502 | **16-bit ALU** |
| **Bus** | 245×1 | Tri-state | 240/244 | 241 | Tri-state | CPU/GPU mux | 6502 pins | **UNIBUS / Q-bus** |
| **System scale** | ~40+ IC + 2 CPLD | ~30 IC | ~36 IC | 100+ IC | ~42 TTL | ~34 TTL | 1 MPU + glue | **Minicomputer** |

---

## 9. Conclusion

| View | Closest peer | Swiver Gi1 differentiator |
|------|--------------|---------------------------|
| **ALU / AC model** | Gigatron | Same 153 bit-slice; CU is **CPLD FSM** not ROM table |
| **Microcode teaching** | Ben Eater | **idx5 FSM** instead of EEPROM; patch via JTAG CPLD |
| **Subroutines / stack** | Magic-1 / Ben Eater / Apple II / **PDP-11** | CALL/RET present; **no HW SP** — CU manipulates RAM stack |
| **6502 software richness** | Apple II / Isetta | Native Swiver macros only; **no 6502 die or emu** on v1.0 |
| **Orthogonal multi-GPR** | **PDP-11** / Magic-1 | **R0 only**; 8-bit; no UNIBUS-class ISA |
| **Thin HW + RAM state** | Isetta | Native ISA (not 6502/Z80 emu); **CU stack assist** not Flash µpages |
| **ROM-heavy minimal TTL** | Novasaur | **Combinational ALU** (not ROM LUT); no 8080 bytecode layer |
| **DP simplicity** | Gigatron / Isetta | **One GPR** + MBR→B; no X/Y or R0–R7 file |
| **CU·DP integration** | *(unique among TTL peers)* | **2-CPLD split** — opposite of Apple II **1-die** and PDP-11 **board/LSI** |

Swiver Gi1 is a hybrid: **Gigatron-minimal DP** plus **CPLD multi-phase sequencer CU**. Unlike Apple II’s **monolithic 6502**, PDP-11’s **16-bit orthogonal register machine**, Ben Eater/Magic-1 **EEPROM/PROM horizontal microcode**, Isetta **Flash emulation µcode**, Novasaur **ROM ALU + bytecode**, or Gigatron **combinational CU**, Gi1 places **control in CPLD-CU**, **operand B in MBR**, and the **sole GPR in CPLD-DP** — that three-way split is the structural identity of v1.0.

---

## 10. External references (non-normative)

| Machine | Primary public source |
|---------|------------------------|
| Gigatron | [gigatron.io](https://gigatron.io) |
| Ben Eater 8-bit | 8-bit computer series — EEPROM microcode finale |
| Magic-1 | [homebrewcpu.com](http://www.homebrewcpu.com) |
| Isetta | [Hackaday.io — Isetta TTL computer](https://hackaday.io/project/190345-isetta-ttl-computer) |
| Novasaur | [GitHub — ajhewitt/novasaur](https://github.com/ajhewitt/novasaur) · [Hackaday.io project](https://hackaday.io/project/164212-novasaur-cpm-ttl-retrocomputer) |
| Apple II / 6502 | [6502.org](https://6502.org) · MOS 6500 MPU datasheets · Apple II Technical Reference |
| PDP-11 | [PDP-11 architecture (Wikipedia)](https://en.wikipedia.org/wiki/PDP-11_architecture) · DEC processor handbooks (Bitsavers) |

---

## Change log

| Date | Note |
|------|------|
| 2026-07-13 | Rename §6.3 **Architecture** → **Memory model**; use von Neumann (was Princeton) |
| 2026-07-13 | Add **PDP-11** (16-bit minicomputer CU·DP baseline); split §2 TTL vs commercial tables |
| 2026-07-13 | Add **Apple II** (MOS 6502 monolithic CU·DP baseline) |
| 2026-07-07 | Add **Isetta**, **Novasaur** — CU·DP sections and contrast tables |
| 2026-07-07 | Initial CU·DP comparison — Gi1 vs Gigatron, Ben Eater, Magic-1 |
