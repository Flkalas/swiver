# Swiver Gi1 — ROM count, structure, and roles (peer comparison)

**Audience:** learners and external reviewers comparing how **Swiver Gi1 v1.0** uses non-volatile memory versus peer machines.  
**Status:** Archived background (Illustrative) — not Active implementer spec.  
**Related (peers):** [cu-dp-comparison.md](cu-dp-comparison.md) · [ttl-computer-comparison.md](ttl-computer-comparison.md) · [clock-comparison.md](clock-comparison.md)  
**Active:** [rom-architecture.md](../../../reference/hardware/rom-architecture.md) · [control-and-decode.md](../../../reference/hardware/control-and-decode.md)

---

## 1. Scope and vocabulary

This note answers three questions for each machine:

1. **How many** discrete ROM / Flash / EEPROM / PROM packages hold non-volatile content?
2. **How is that memory structured** (width, address space, **von Neumann vs Harvard**)?
3. **What role** does each region play — **control store**, **program**, **ALU LUT**, **fonts / assets**, or **firmware**?

| Term | Meaning in this document |
|------|--------------------------|
| **von Neumann** | Shared instruction/data address space (also called Princeton) — Swiver’s flat 64 KiB map |
| **Harvard** | Separate instruction and data paths (Gigatron ROM vs RAM; Novasaur dual CPU/GPU) |
| **Control store** | Non-volatile memory (or on-die PLA) that drives **micro-ops / strobes** each cycle or phase — not user program bytes |
| **Program store** | Instruction bytes the programmer / ISA executes (native or guest) |
| **Asset / LUT ROM** | Tables used as **data** (fonts, ALU lookup, cold storage) — not opcode streams |
| **Decode PLA** | Hardwired or fuse-programmed decode **inside** a CPU die or CPLD — counted separately from discrete ROM chips |

**Peers:** Gigatron, Ben Eater 8-bit, Magic-1, Isetta, Novasaur, Apple II, PDP-11 — same set as [ttl-computer-comparison.md](ttl-computer-comparison.md).

---

## 2. Executive summary

| Machine | Discrete ROM/Flash packages | Memory model | Control store? | Program store? | Other ROM roles |
|---------|----------------------------:|:------------:|:--------------:|:--------------:|-----------------|
| **Swiver Gi1** | **1** (SST39SF010A 128K×8) | **von Neumann** (flat 64 KiB) | **No** — CPLD FSM | **Yes** (boot + utility) | `$4000` CW **reserved unused** |
| **Gigatron** | **1** (64K×16 EPROM) + diode matrix | **Harvard** | Diode ROM (CU) | **Yes** (Harvard ROM) | — |
| **Ben Eater** | **2** (µcode EEPROM) + optional prog ROM | **von Neumann** | **Yes** (horizontal µcode) | Usually **RAM** (lab) | — |
| **Magic-1** | **5** (512×8 PROM → 56b µword) + prog mem | **von Neumann** (+ paging) | **Yes** | Separate RAM/ROM | — |
| **Isetta** | **3** (24-bit Flash µcode) + RAM | **von Neumann** (banked) | **Yes** (emu µcode) | Guest code in **RAM** | Video/sound via µcode |
| **Novasaur** | **1** (256 KiB ROM) | **Dual Harvard** | Native µprog in ROM | Native + 8080 VM in ROM | **96 KiB ALU LUT**, fonts |
| **Apple II** | **1–several** system ROMs (model-dep.) | **von Neumann** | **On-die PLA** only | Monitor / BASIC ROMs | Soft-switch firmware |
| **PDP-11** | Multiple µPROMs (model-dep.) + media | **von Neumann** (+ MMU) | **Yes** (most models) | Core / RAM / tape | Console / bootstrap |

**Swiver’s distinctive choice:** one parallel NOR Flash for **lawful program content** (boot, vector, utilities), while **all phase control** lives in the **CPLD** — Flash `$4000–$4FFF` is explicitly **not** a control store in v1.0 ([rom-architecture.md](rom-architecture.md)).

```text
Role spectrum (who owns “what happens next”)

  Control in silicon/CPLD     Control in discrete ROM        Control + ALU in same ROM
  ─────────────────────       ──────────────────────         ─────────────────────────
  Apple II (PLA)              Ben Eater (EEPROM×2)           Novasaur (prog + ALU LUT)
  Swiver (CPLD FSM)           Magic-1 (PROM×5)               Gigatron (prog ROM + diode CU)
                              Isetta (Flash×3)               PDP-11 (µROM + program media)
                              PDP-11 (µROM)
```

---

## 3. Swiver Gi1 — normative ROM model

### 3.1 Physical count

| Package | Part | Size | Role |
|---------|------|------|------|
| **1× Flash** | SST39SF010A-70-4C-PHE | **128K×8** parallel NOR | Boot, utility assets, reset vector image |
| **0× CW Flash** | — | `$4000–$4FFF` **unused** | Control store **retired** (FSM-only) |
| **CPLD “ROM”** | ATF1504AS ×2 (CU + DP) | On-chip PLA/LUT | **idx5** phase strobes (not a discrete ROM) |

So in BOM language: **one** non-volatile memory chip for the CPU system. Control is **not** counted as a Flash package.

### 3.2 Logical segments

| Segment | Where | Role |
|---------|-------|------|
| **Control** | **CPLD-CU** idx5 FSM | Opcode×phase → 14 strobes + `reg_we`; CALL/RET stack assist |
| **Boot** | Flash `$0000–$07FF` (+ `$FFFC` vector) | POST, mailbox load, handoff to RAM `$0800` |
| **Utility** | Flash `$0800–$3FFF` | Fonts, tables — shadowed to RAM |
| **Reserved CW** | Flash `$4000–$4FFF` | **Empty** in v1.0 — was prototype 10b CW region |

Detail: [rom-architecture.md](rom-architecture.md) · [memory-map.md](memory-map.md).

### 3.3 What Flash is *not*

- Not a horizontal microcode EEPROM (unlike Ben Eater / Magic-1 / Isetta).
- Not an ALU lookup table (unlike Novasaur).
- Not a Harvard instruction ROM clocked every cycle independent of data RAM (unlike Gigatron’s 16-bit ROM port) — Swiver uses a **flat 64 KiB map** with Boot/Run MAP modes.

---

## 4. Peer machines — ROM inventory

### 4.1 Gigatron

| Package / structure | Typical size | Role |
|---------------------|--------------|------|
| **Program ROM** | **64K×16** EPROM | Harvard instruction stream (native opcodes) |
| **Diode ROM matrix** | Discrete diodes / small glue | **CU decode** — IR → ~19 control lines (combinational) |
| Production | GT1 ASIC may absorb logic | Same roles, fewer packages |

**Structure:** True **Harvard** — ROM address from PC; RAM for data/video. CU is **not** a wide EEPROM µstore; the diode matrix is a fixed decode table.

**vs Swiver:** Both avoid EEPROM µcode. Gigatron still needs a **large program ROM** as the only instruction source; Swiver’s Flash is boot/utility and can yield to RAM after handoff. Swiver’s CU is **stateful CPLD FSM**; Gigatron’s is **combinational diode ROM**.

---

### 4.2 Ben Eater 8-bit

| Package / structure | Typical size | Role |
|---------------------|--------------|------|
| **Microcode EEPROM ×2** | e.g. 28C16 class | **Horizontal control store** — opcode + µstep (+ flags) → ~16 control bits |
| **Program memory** | Usually **RAM** on the teaching build | User machine code |
| Optional | Extra EEPROM for “ROM programs” | Demo firmware |

**Structure:** µcode address = `{flags, byte_sel, instruction, step}`. Two chips provide high/low control bytes. Lab workflow = Arduino burn of EEPROMs.

**vs Swiver:** Ben Eater puts **control** in reprogrammable ROM; Swiver puts **control** in CPLD and **program/boot** in one Flash. Swiver has **zero** discrete µcode EEPROMs.

---

### 4.3 Magic-1

| Package / structure | Typical size | Role |
|---------------------|--------------|------|
| **PROM ×5** | **512×8** each → **56-bit** µ-instruction | **Control store** — opcode indexes first µop; `next` field sequences |
| **Program / data memory** | Separate RAM (and optional ROM) | User / OS code |

**Structure:** Wide horizontal microstore; opcode is a **direct index** into the low half of µROM. Classic “many PROMs = one fat µword” design.

**vs Swiver:** Magic-1 maximizes **ROM as control**. Swiver maximizes **CPLD as control** and keeps Flash for **program law** only. Closest *control-store philosophy* peer is Ben Eater / PDP-11, not Gi1.

---

### 4.4 Isetta

| Package / structure | Typical size | Role |
|---------------------|--------------|------|
| **Flash ×3** | Form **24-bit** µ-instruction | **Control store** — emulates 6502 / Z80 (and I/O, video, sound µcode) |
| µaddress | IR + **4b step** + **4b page** + F flag | Up to 16 pages (expandable); page selects ISA |
| **Program store** | **RAM** (banked, up to 1 MiB) | Guest 6502/Z80 binaries — **not** in the µcode Flash |

**Structure:** Harvard-style µfetch (µcode read while data bus moves). Control Flash is the CPU; application code lives in RAM.

**vs Swiver:** Isetta uses **three** Flashes purely as **µcode**. Swiver uses **one** Flash purely as **program/boot**. Same “thin HW register” spirit; opposite ROM role.

---

### 4.5 Novasaur

| Package / structure | Typical size | Role |
|---------------------|--------------|------|
| **ROM ×1** | **256 KiB** (e.g. SST39SF020A class) | **Multiplexed** control + program + ALU + assets |
| Region (approx.) | **96 KiB** | **ALU LUT** (nibble ops, 76 functions) |
| | **64 KiB** | Native program / firmware |
| | **64 KiB** | Cold storage |
| | **32 KiB** | Fonts |
| **PAL ×1** | Glue | Timing / decode assist (not bulk ROM) |

**Structure:** One physical ROM, **time-multiplexed address bus** — fetch cycle vs ALU execute cycle vs font lookup. Maximal “ROM does everything” design among TTL peers.

**vs Swiver:** Novasaur’s ROM **is** the ALU and the OS; Swiver’s Flash **never** participates in ALU. Swiver ALU is **12 DIP combinational**; Novasaur ALU is **ROM lookup**.

---

### 4.6 Apple II (commercial baseline)

| Package / structure | Typical size | Role |
|---------------------|--------------|------|
| **6502 on-die PLA** | Internal | **Instruction decode / T-state control** — not a board ROM |
| **Monitor / BASIC ROMs** | Model-dependent (often ~2–12 KiB class) | Firmware: Monitor, Applesoft / Integer BASIC |
| **Program** | RAM (+ ROM cartridges / language card) | User code |

**Structure:** Control is **inside the MPU**. Board ROMs are **system firmware**, analogous to Swiver’s boot/utility Flash — **not** a microcode store.

**vs Swiver:** Closest *role* match for Flash: both use discrete ROM/Flash for **boot/firmware**, not for µcode. Difference: Apple II CU is **on-die PLA**; Swiver CU is **CPLD FSM**. Apple II may ship **multiple** firmware ROMs; Swiver ships **one** NOR.

---

### 4.7 PDP-11 (commercial baseline)

| Package / structure | Typical size | Role |
|---------------------|--------------|------|
| **Microcode PROMs / ROMs** | Model-dependent (often several chips → wide µword) | **Control store** (11/40, LSI-11, …) |
| **Early 11/20** | Less discrete µROM | Datapath/control more tightly combined |
| **Program media** | Core, RAM, paper tape, disk, bootstrap ROM | User / OS code |
| **Console / bootstrap** | Small ROM on some models | Loaders |

**Structure:** Classic minicomputer split — **µROM runs the processor**; **separate memory hierarchy** holds programs. UNIBUS maps devices into the same address space as RAM.

**vs Swiver:** PDP-11 is the commercial form of Magic-1’s “wide µstore + rich ISA.” Swiver rejects external control ROM entirely for v1.0.

---

## 5. Cross-cutting analysis

### 5.1 ROM package count (CPU-relevant)

```text
  Packages (approx.)
  0 control ROM + 1 prog Flash     Swiver Gi1
  0 board µROM (PLA on die)        Apple II (+ firmware ROMs)
  1 prog ROM + diode CU            Gigatron
  1 mega-ROM (prog+ALU+font)       Novasaur
  2 µcode EEPROM                   Ben Eater
  3 µcode Flash                    Isetta
  5 µcode PROM                     Magic-1
  N µPROMs (board)                 PDP-11 (model-dependent)
```

### 5.2 Role matrix

| Role | Swiver | Gigatron | Ben Eater | Magic-1 | Isetta | Novasaur | Apple II | PDP-11 |
|------|:------:|:--------:|:---------:|:-------:|:------:|:--------:|:--------:|:------:|
| **Discrete µcode / CW ROM** | — | — | **●** | **●** | **●** | △ native in ROM | — | **●** |
| **On-die / CPLD control** | **●** CPLD | △ diode | — | — | — | △ PAL | **●** PLA | △ early |
| **Program / firmware ROM** | **●** | **●** | △ opt. | △ | — (RAM) | **●** | **●** | △ boot |
| **ALU implemented in ROM** | — | — | — | — | — | **●** | — | — |
| **Fonts / assets in ROM** | **●** util | — | — | — | via µcode | **●** | ROM charset | — |

**●** = primary path · **△** = partial / model-dependent · **—** = not used that way

### 5.3 Structure patterns

| Pattern | Machines | Implication |
|---------|----------|-------------|
| **Split: µROM ≠ program** | Ben Eater, Magic-1, Isetta, PDP-11 | Two non-volatile worlds; patch µcode without touching apps (or vice versa) |
| **Harvard program ROM** | Gigatron | Instruction width can exceed data width (16b insn ROM) |
| **Single ROM, many roles** | Novasaur | Address mux + timing critical; one chip burn updates ALU+OS+fonts |
| **Firmware Flash + FSM control** | **Swiver** | One Flash burn for boot/assets; CU change needs **CPLD JTAG** |
| **Firmware ROMs + MPU PLA** | Apple II | CU invisible; only firmware ROMs on the board |

### 5.4 Patch / bring-up implications

| If you change… | Swiver | Ben Eater / Magic-1 / Isetta | Novasaur | Apple II |
|----------------|--------|------------------------------|----------|----------|
| Instruction timing / strobes | **CPLD reburn** | µROM / Flash reburn | ROM / PAL | Impossible (die) |
| Bootloader / fonts | **Flash reburn** | Program media | Same ROM chip | System ROM swap |
| ALU function set | Rewire / CU nets | µcode sequences | **ALU LUT region** | N/A (die ALU) |
| Guest ISA (6502/Z80) | Out of v1.0 scope | Isetta: **µpage** | 8080 VM in ROM | Native 6502 |

---

## 6. Design takeaways for Swiver

1. **ROM count is intentionally minimal (1).** Control complexity moved into **2× CPLD**, not into EEPROM farms.
2. **Flash `$4000` CW is a non-role** in v1.0 — documents must not treat program Flash as a microstore ([control-and-decode.md](control-and-decode.md)).
3. **Closest ROM-*role* cousins:** Apple II (firmware ROMs + non-ROM control) and Gigatron (no EEPROM µcode). **Farthest:** Magic-1 / Isetta / Ben Eater (ROM *is* the CU) and Novasaur (ROM *is* the ALU).
4. **Trade-off:** Lab µcode patching is harder than Ben Eater; bring-up depends on **WinCUPL Design fits** + Flash boot images, not Arduino EEPROM burns.

---

## 7. Document index

| Topic | Document |
|-------|----------|
| Normative Flash map | [rom-architecture.md](rom-architecture.md) |
| Who decodes what | [control-and-decode.md](control-and-decode.md) |
| CU·DP chip structure | [cu-dp-comparison.md](cu-dp-comparison.md) |
| ISA / stack peers | [ttl-computer-comparison.md](ttl-computer-comparison.md) |
| Archived Flash CW prototype | [archive/prototype-flash-cw](../../archive/prototype-flash-cw/README.md) |

---

## Change log

| Date | Note |
|------|------|
| 2026-07-13 | Add **Memory model** (von Neumann / Harvard) to §2 executive summary |
| 2026-07-13 | Initial ROM count / structure / role analysis vs peer set |
