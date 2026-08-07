# TTL homebrew CPU comparison (reference)

**Audience:** learners and external reviewers positioning **Swiver v1.0 P12** against other well-known discrete-logic machines (plus commercial / minicomputer baselines).  
**Status:** Archived background (Illustrative) — not Active implementer spec. Active = **P12 pipe**.  
**Related (peers):** [cu-dp-comparison.md](cu-dp-comparison.md) · [rom-comparison.md](rom-comparison.md) · [clock-comparison.md](clock-comparison.md)  
**Active:** [system-architecture.md](../../../reference/hardware/system-architecture.md) · [cpld-pipe-cu.md](../../../reference/hardware/cpld-pipe-cu.md) · [microcode-spec.md](../../../reference/hardware/microcode-spec.md) · [calling-convention-v0.1.md](../../../reference/software/calling-convention-v0.1.md)

---

## 1. Scope

This note compares **Swiver v1.0 P12** with **five** representative TTL (or TTL-class) homebrew CPUs and **two** commercial / historical baselines:

| Machine | Why included |
|---------|----------------|
| **Gigatron** | Closest design cousin — AC-centric ISA, RAM-backed variables, visible breadboard lineage |
| **Ben Eater 8-bit** | Canonical EEPROM **microprogram** teaching path; stack + `CALL`/`RET` in the finished series |
| **Magic-1** | Full-scale TTL with **hardware stack pointer** and wide horizontal microstore |
| **Isetta** | Minimal-chip-count TTL that **emulates 6502 and Z80** from 24-bit Flash microcode |
| **Novasaur** | Dual CPU/GPU Harvard machine; **8080 bytecode** layer for CP/M on ~34 TTL ICs |
| **Apple II** | Commercial **MOS 6502** baseline — CU·DP on one die; ISA that Isetta emulates |
| **PDP-11** | Commercial **16-bit minicomputer** — orthogonal GPRs, HW SP=PC, microcoded family |

Pure-ASIC kits, FPGA-only replicas, and other classic MPU dies (Z80, 8080 as silicon, …) remain out of scope except where a TTL machine **interprets** their instruction sets (Isetta, Novasaur). **Apple II** and **PDP-11** are explicit exceptions: finished commercial systems used as CU·DP / stack / ISA references, not as TTL peers.

---

## 2. Summary tables

### 2.1 TTL / discrete peers

| | **Swiver Gi1 v1.0** | **Gigatron** | **Ben Eater 8-bit** | **Magic-1** | **Isetta** | **Novasaur** |
|---|---------------------|--------------|---------------------|-------------|------------|--------------|
| **Data / address** | 8 / 16 | 8 / 16 | 8 / 16 | 8 / 24 | 8 / 16 (+ banked RAM) | 8 / 16 (+ banks) |
| **Memory model** | **von Neumann** (flat 64 KiB) | **Harvard** (ROM insn / RAM data) | **von Neumann** | **von Neumann** (+ paging) | **von Neumann** (banked RAM) | **Dual Harvard** (CPU+GPU) |
| **Typical clock** | 2 MHz (target) | ~6.25 MHz (vCPU cycle) | ~500 kHz–1 MHz | ~4.09 MHz | **12.5 MHz** (µstep) | **8.25 MHz** native; **~450 kHz** effective 8080 |
| **Control store** | **CPLD idx5 FSM** | ROM + sequencer (GT1 ASIC in prod.) | **EEPROM microcode** | **ROM microcode** | **24-bit Flash µcode** (3 chips, 16 pages) | **ROM** (incl. 96 KiB ALU table) + **PAL** |
| **Native ISA** | Swiver macro (`0x01–0x0F`) | Gigatron vCPU | Microcoded 8-bit | Magic-1 | *(none exposed)* | Novasaur native + drivers |
| **Emulated ISA** | — | — | — | — | **6502 + Z80** (page switch) | **Intel 8080/8085** (bytecode) |
| **Programmer-visible GPR** | **R0 (AC) only** in CPLD | **vAC** | **A**, **B** | **A**, **B**, index, … | **A**, **T**; PC; **DPH/DPL** | Via 8080 model / native regs |
| **Registers in RAM** | Most variables + **RP** | vSP, temps | — (SP in HW) | — | **6502 X, Y, S** (+ Z80 set) | 8080 state in interpreter |
| **Operand B path** | **MBR → ALU B** | Bus / RAM → ALU | Bus → ALU (µ-ops) | Bus → ALU (µ-ops) | Bus → ALU (µ-ops) | **ROM ALU lookup** + nibble path |
| **ALU style** | 74HC 153 bit-slice | 74HC bit-slice | 74LS283 + logic | 74xx bit-slice | 74AC283 + mux (µ-sequenced) | **LUT in ROM** (4-bit slice) |
| **Flags** | **Z, C** | Z, C | Z, C | N, Z, C, V | **N, C**, TC (µcode) | Per 8080 emulation |
| **Conditional branch** | `BEQ` (Z) | Rich vCPU set | Microcoded | Rich set | 6502/Z80 branches | 8080 branches |
| **Memory** | 64 KiB flat | 64 KiB ROM/RAM split | 16-bit + EEPROM µstore | 16 MiB linear | **up to 1 MiB** banked | **512 KiB RAM**, 256 KiB ROM |
| **Video / I/O** | MMIO mailbox; **no IRQ** | On-board VGA; no IRQ | Front-panel hooks | Serial, disk | **VGA**, sound, FS; no IRQ | **VGA GPU**, PS/2, RS-232; expansion **IRQ flags** |
| **Coprocessor** | RP2350 mailbox (opt.) | Self-contained | None | Mass-storage I/F | Self-contained | **GPU** time-slices bus (Harvard) |
| **TTL / chip count (approx.)** | Breadboard + **2× CPLD** | ~36 TTL + GT1 | Build-dependent | Large build | **~42 TTL** | **~34 TTL** (+ ROM/RAM) |

### 2.2 Commercial / historical baselines

| | **Swiver Gi1 v1.0** | **Apple II** | **PDP-11** |
|---|---------------------|--------------|------------|
| **Data / address** | 8 / 16 | 8 / 16 | **16 / 16** (+ MMU on later models) |
| **Memory model** | **von Neumann** (flat 64 KiB) | **von Neumann** | **von Neumann** (+ MMU on later models) |
| **Typical clock** | 2 MHz (target) | **~1.023 MHz** (6502) | Model-dependent (µs-class core / LSI) |
| **Control store** | **CPLD idx5 FSM** | **On-die PLA** (6502) | **Microcode** (11/40+, LSI-11); early 11/20 combined |
| **Native ISA** | Swiver macros | **6502** | **PDP-11** (orthogonal) |
| **Programmer-visible GPR** | **R0 only** | **A, X, Y** | **R0–R5**; **R6=SP**; **R7=PC** |
| **ALU** | 74HC 153 bit-slice | On-die | 16-bit ALU (board / LSI) |
| **Flags** | Z, C | N, V, B, D, I, Z, C | **N, Z, V, C** (PS) |
| **Stack** | RAM `$0F00` + CU assist | **HW S** → page `$01` | **HW R6 (SP)**; grows down |
| **Interrupts** | **None** (v1.0) | IRQ / NMI | Vectored IRQ (UNIBUS / stack) |
| **Bus** | 8-bit + MMIO mailbox | 6502 bus + soft switches | **UNIBUS** / **Q-bus** |
| **Chip model** | Discrete + 2× CPLD | **1× 6502** + board TTL glue | Minicomputer / LSI set |

*Memory model:* **von Neumann** = shared instruction/data space (Princeton); **Harvard** = separate instruction and data paths. Same classification in [cu-dp-comparison.md](cu-dp-comparison.md) §6.3 and [rom-comparison.md](rom-comparison.md) §2.

---

## 3. Subroutine and stack comparison

Gi1 normative **CALL/RET** ([microcode-spec.md](microcode-spec.md) §2.3) sits between “native thin registers” and “emulated classic ISAs”:

| | **Swiver Gi1** | **Gigatron** | **Ben Eater** | **Magic-1** | **Isetta** | **Novasaur** | **Apple II** | **PDP-11** |
|---|----------------|--------------|---------------|-------------|------------|--------------|--------------|------------|
| **`CALL` / `RET` (native)** | **Yes** — `0x06` / `0x07` | **Yes** (vCPU) | **Yes** (µprogram) | **Yes** | — | Native HAL | **JSR / RTS** | **JSR / RTS** |
| **`CALL` / `RET` (hosted)** | — | — | — | — | **6502 / Z80** | **8080** | — | — |
| **Stack pointer** | RAM **`$0F00`** | **`vSP`** zp | **SP reg** | **HW SP** | **S in RAM** | 8080 SP in VM | **HW S** | **R6 (SP)** |
| **Stack growth** | **Upward** | Downward | Downward | Downward | Downward | Downward | Downward | **Downward** |
| **Push/pop actor** | **CPLD-CU** | Sequencer | Microcode | Microcode+SP | Flash µcode | Bytecode | On-die S | µcode + SP |
| **Return address** | 16-bit LE | 16-bit | 16-bit | 16-bit | 16-bit | 16-bit | 16-bit LE | **16-bit** |
| **Dedicated `PUSH`/`POP`** | **No** | Compiler | Via µ-ops | **Yes** | 6502/Z80 | 8080 | **PHA/PLA** | Modes / MOV |

**Takeaway:** Swiver keeps a **native** thin-register machine like Gigatron but adds **hardware-assisted CALL/RET** without a dedicated SP register — similar *problem* to Isetta, solved with **Gi1 CU stack assist**. **Apple II** and **PDP-11** are the opposite extreme: **HW stack pointer + first-class JSR/RTS** (PDP-11 also vectors interrupts through the same stack). Novasaur targets **CP/M via 8080** at bytecode cost.

---

## 4. Control-model contrast

```text
Ben Eater / Magic-1 / PDP-11   Isetta                 Novasaur
────────────────────────────   ──────                 ────────
EEPROM/ROM / µROM µword        24-bit Flash µword     ROM µprog + ALU LUT
  native ISA steps               emulates 6502/Z80      native + 8080 bytecode
  SP in register file            X/Y/S in RAM           dual CPU/GPU Harvard

Gigatron                    Swiver Gi1                 Apple II
────────                    ──────────                 ────────
ROM table + glue            CPLD idx5 row              On-die PLA (6502)
vCPU fetch/exec             few phases / macro         Φ1/Φ2 T-states
vSP in zero page            RP in RAM @ $0F00          HW S → page $01
```

| Style | Strength | Gi1 trade-off |
|-------|----------|---------------|
| **EEPROM microcode** (Ben Eater) | Patch control flow in the lab | Fitter-bound CPLD FSM; no breadboard EEPROM µstore |
| **Horizontal ROM** (Magic-1) | Flexible µsequences per ISA insn | BOM/wiring beyond v1.0 breadboard scope |
| **ROM sequencer** (Gigatron) | Proven AC machine at hobby scale | Swiver adds mailbox copro + frozen **M3a** LUT |
| **Flash µcode emulator** (Isetta) | Run **existing** 6502/Z80 binaries | ~42 TTL + 3 Flash; not a small student FSM lab |
| **8080 bytecode** (Novasaur) | **CP/M** and games without a real 8080 | Effective ~450 kHz 8080; dual-processor complexity |
| **Monolithic PLA** (Apple II / 6502) | Dense ISA + IRQ + ecosystem | Not discrete; no breadboard CU visibility |
| **16-bit µcode minicomputer** (PDP-11) | Orthogonal GPRs + HW SP + vectored IRQ | Far beyond v1.0 8-bit breadboard scope |
| **CPLD FSM-only** (Swiver) | Direct strobes; no µstore burn | CALL/RET needs **CU stack assist** — [call-ret-cu-fit.md](call-ret-cu-fit.md) |

---

## 5. When Swiver is the better teaching match

| Goal | Favor |
|------|-------|
| **Microcode EEPROM lab** from first principles | Ben Eater 8-bit |
| **Maximum native ISA richness on TTL** | Magic-1 |
| **Minimal registers + game/video on one board** | Gigatron |
| **Run 6502 / Z80 binaries on TTL** | **Isetta** |
| **CP/M and 8080 software on minimal TTL** | **Novasaur** |
| **Commercial 6502 software / IRQ / HW stack baseline** | **Apple II** |
| **Orthogonal multi-GPR / UNIBUS-class ISA baseline** | **PDP-11** |
| **FSM-in-CPLD + frozen idx5 golden + copro OS path** | **Swiver Gi1** |

Swiver intentionally keeps **IRQ, MMU, multi-GPR, and ISA emulation** off the v1.0 normative path ([plover-whitepaper.md](../../plover-whitepaper.md) §2.3) while still providing **native CALL/RET** for functions, Forth, and Subset C bring-up.

---

## 6. External references (non-normative)

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
| 2026-07-13 | Add **Memory model** (von Neumann / Harvard) to §2 summary tables |
| 2026-07-13 | Add **PDP-11**; split §2 into TTL peers vs commercial baselines |
| 2026-07-13 | Add **Apple II** (MOS 6502 monolithic baseline) |
| 2026-07-07 | Add **Isetta**, **Novasaur** — emulation / CP/M peers |
| 2026-07-07 | Initial comparison — Gi1 vs Gigatron, Ben Eater 8-bit, Magic-1 |
