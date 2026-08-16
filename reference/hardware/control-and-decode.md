# Control and decode (v1.0 P12)

**Related:** [system-architecture.md](system-architecture.md) · [cpld-pipe-cu.md](cpld-pipe-cu.md) · [microcode-spec.md](microcode-spec.md) · [cpld-system-controller.md](cpld-system-controller.md) · [rom-architecture.md](rom-architecture.md)

This document is the **single normative reference** for who decodes what on the v1.0 P12 CPU.

---

## 1. Layered responsibilities

| Layer | Block | Input | Output / effect | On v1.0 SoC? |
|-------|-------|-------|-----------------|--------------|
| **Program store (PROG)** | SST39 Flash + IF path | PC / offset | Instruction bytes | Yes |
| **Macro sequencer** | **CPLD-CU pipe** | IR, flags, stall sense | Direct strobes + G-IC `reg_we`; stack EX | Yes |
| **GPR datapath** | **CPLD-DP** | `d_in`, `reg_we` | `q_a` ← R0; write R0 | Yes |
| **Operand B** | MBR / oper latch | IF | `net_mbr` → ALU B | Yes |
| **ALU control** | Pipe EX constants on CU | CU outputs | `net_cin`, `net_bctrl0..3`, `net_lgc0..3`, `net_153_s0/s1` | Yes |
| **ALU execute** | alu8 (12 DIP) | A, B, control nets | `net_y*`, `net_c_hi` | Yes |
| **Memory CE (DATA)** | 74HC138×2 + glue | `A[15:0]`, MAP, mailbox | `/CE` to SRAM×2 + Flash | Yes (off CPLD) |
| **12-opcode comb decode** | DIP / tie or bench block | `alu_sel[3:0]` | Control nets | **M1 bench only** |

```text
  PROG Flash ──► IF latch ──► CPLD-CU pipe FSM ──► strobes ──► alu8 / DATA / PC
  boot, vector                 reg_we ───────────► R0, q_a ──► alu8 A
                               oper/MBR ─────────────────────► alu8 B
  A[15:0] ──────────────────────────────────────────────► 138×2 ──► /CE
```

**CU detail:** [cpld-pipe-cu.md](cpld-pipe-cu.md).

---

## 2. Flash vs CPLD

### Flash (SST39SF010)

| Region | Role |
|--------|------|
| `$0000+` | Program, bootloader, utility tables (**PROG**) |
| `$FFFC` | Reset vector image |

### CPLD pair (P12)

| Chip | Function |
|------|----------|
| **CPLD-CU** | Pipe / stall / stretch / fallback FSM; branch `PC_LOAD_EN`; CALL/RET **STACK_EX**; direct strobes |
| **CPLD-DP** | **R0 (8 FF)**; async `q_a`; `reg_we` → R0 from `d_in` |

**Not in CPLD:** memory `/CE`, mailbox MAP, **ALU B operand wire** (MBR/oper). See [memory-map.md](memory-map.md).

---

## 3. ALU control signals (normative naming)

| Net | Role |
|-----|------|
| `net_cin` | 283 carry in (1 for SUB/CMP/**INC**) |
| `net_bctrl0..3` | 153 mux2 data pattern |
| `net_lgc0..3` | 153 mux1 logic pattern |
| `net_153_s0`, `net_153_s1` | Operand select → `y_mux_sel` |

**Fanout at 153:** `bctrl1` ← `bctrl0`, `bctrl3` ← `bctrl2` (CU ties internally).

**INC (opcode 9):** `cin=1`, `bctrl=0000` → A+0+1. See [b3-opcode.md](../hw-bringup/b3-opcode.md).

### CALL / RET (software return stack)

No dedicated RP register. **CPLD-CU** performs push/pop in **STACK_EX** using `MEM_RD`/`MEM_WR` — RP cell `$0F00`, stack body `$F600+` ([microcode-spec.md](microcode-spec.md) §2.3). RET loads PC from the popped word, not from MBR.

---

## 4. M1 bench vs SoC

| Context | Who drives ALU control? |
|---------|-------------------------|
| **M1 ALU bring-up** | Manual DIP / [b3-opcode.md](../hw-bringup/b3-opcode.md) |
| **Integrated CPU** | **CPLD-CU** pipe outputs only |

---

## 5. Document index

| Topic | Document |
|-------|----------|
| Pipe CU states / SYS tax | [cpld-pipe-cu.md](cpld-pipe-cu.md) |
| ISA opcodes | [microcode-spec.md](microcode-spec.md) |
| Dual CPLD ports, G-IC | [cpld-system-controller.md](cpld-system-controller.md) |
| Routing, JTAG | [cpld-dual-routing.md](cpld-dual-routing.md), [cpld-dual-jtag.md](cpld-dual-jtag.md) |
| Pipe timing / CALL-RET fit | [cpld-pipe-cu.md](cpld-pipe-cu.md) §7 / §5.1 |
| Flash layout | [rom-architecture.md](rom-architecture.md) |

### Truth cascade (edit order)

| Tier | Path | Role |
|------|------|------|
| **Root** | [swiver-whitepaper.md](../../swiver-whitepaper.md) §6 | ISA / pipe narrative |
| **Reference** | `reference/**` | Normative detail; **CU = cpld-pipe-cu** |
| **Machine** | cyclesim golden | Executable golden (pipe rewrite in progress) |
| **CPLD** | pipe CU PLD | **Design fits pending** |
