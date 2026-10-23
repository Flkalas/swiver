# CPLD System Controller v1.0 sequential

**Devices:** 2× **ATF1504AS-10JU44** (PLCC-44)  
**Roles:** **CPLD-CU** — **sequential FSM** (see [cpld-sequential-cu.md](cpld-sequential-cu.md)) + direct strobes + branch · **CPLD-DP** — **R0 (AC) only** + `q_a`<br>
**CE tree:** 74HC138×2 + 08/32/04 (off-chip)

**Related:** [control-and-decode.md](control-and-decode.md) · [cpld-dual-routing.md](cpld-dual-routing.md) · [cpld-dual-jtag.md](cpld-dual-jtag.md) · [microcode-spec.md](microcode-spec.md)

**Implementation:** CU and R0-only DP (`q_a`) are specifications. No active tracked PLD/HDL or fitted bitstream is supplied under `cpld/`; sequential **Design fits pending**. The Python DP model is not a fitted PLD.

---

## 1. Design rules

1. **ALU A:** `q_a` ← **R0** only (CPLD-DP).
2. **ALU B:** **`net_mbr[7:0]`** (MBR / oper latch) → `net_b[7:0]`.
3. **Write target:** **`reg_we` → R0** only (G-IC is one wire).
4. **Sequential FSM** on CPLD-CU — [cpld-sequential-cu.md](cpld-sequential-cu.md).
5. **Strobes:** CU drives memory/ALU/PC nets directly to SoC.
6. **Branch:** `PC_LOAD_EN` commits an accepted redirect after the current instruction completes.
7. **Return stack assist:** CALL/RET serialize RP low/high reads, return-PC low/high access, then RP low/high writes; redirect commits last. RP `$0F00`, stack RAM via `MEM_RD`/`MEM_WR` ([microcode-spec.md](microcode-spec.md) §2.3 · [cpld-sequential-cu.md](cpld-sequential-cu.md)).
8. **Opcodes `0x10–0x1F`:** reserved / trap.
9. **Mailbox, MAP, `/CE`** — outside CPLD.

---

## 2. CPLD-CU port list

This is an incomplete interface sketch, not a complete sequential pin assignment.
`OPC[4:0]` alone aliases valid `0x01` with reserved `0x21`; upper-bit qualification
or a wider decode input is required. Stack-pointer guard inputs, temporary-state
allocation and address-path controls also need an explicit implementation.
See [implementation audit](cpld-integration-audit.md).

### Inputs

| Signal | Source | Role |
|--------|--------|------|
| `OPC[4:0]` | IR latch | Sequential decode |
| `FLG_Z` | FLG574 | BEQ |
| `CLK` | 2 MHz `CLK_SYS` | Sequential FSM |
| WAIT / ready (hardware design pending) | Functional `request_wait()` hook today | Extend the pending phase; physical ready/timeout sensing is unimplemented |

### Outputs — SoC

| Signal | Function |
|--------|----------|
| `MEM_RD`, `MEM_WR` | Memory strobes |
| `Y_OE` | Bus drive |
| `FLG_WE` | Flag latch write |
| `PC_LOAD_EN` | Branch / redirect commit |
| `cin`, `bctrl0`, `bctrl2`, `lgc0..3`, `s0`, `s1` | ALU controls |
| Fetch / data selects | One shared address/data bus; mutually exclusive accesses |

`bctrl1`/`bctrl3` fan out at 153 from `bctrl0`/`bctrl2`.

### Outputs — G-IC to CPLD-DP (1)

| Signal | Function |
|--------|----------|
| `reg_we` | GPR write (→ R0) |

Full state machine, counted SYS schedule, validation boundary: **[cpld-sequential-cu.md](cpld-sequential-cu.md)**.

---

## 3. CPLD-DP port list

### Inputs (9)

| Signal | Source | Role |
|--------|--------|------|
| `d_in[7:0]` | Data bus | LDA / ALU writeback |
| `reg_we` | CPLD-CU G-IC | R0 write strobe |
| `CLK` | 2 MHz | R0 FF clock |

### Outputs (8)

| Signal | Function |
|--------|----------|
| `q_a[7:0]` | Async read → ALU A |

ALU B comes from **MBR / oper latch** off-chip (`net_mbr` → `net_b`).

**Pin budget (desk):** **17/32** used (15 spare).

---

## 4. G-IC bundle

| ID | Signal | DP pin (desk) |
|----|--------|---------------|
| G01 | `reg_we` | 12 |

**CLK:** pin 43 both chips (parallel).

Detail: [cpld-dual-routing.md](cpld-dual-routing.md)

---

## 5. Extra program state

Additional variables live in **RAM**. Normative visible GPR is **R0** only.

---

## 6. JTAG / programming

Daisy chain: programmer → **CU (TDI first)** → **DP** → programmer TDO.  
TCK/TMS paralleled. See [cpld-dual-jtag.md](cpld-dual-jtag.md).

---

## 7. Sequential execution policy

Fetch the opcode and all operands, execute, then retire before fetching the next instruction. Opcode fetch, operand fetch, and EX never overlap. The unified 64 KiB instruction/data space supports RAM execution on one shared bus. MBR/operand latches hold throughout ADD/CMP EX. The functional `request_wait()` hook adds visible counted WAIT ticks to the pending phase; physical ready/timeout sensing and WAIT generation remain pending. Detail: [cpld-sequential-cu.md](cpld-sequential-cu.md).

Default successful SYS counts: ADD/CMP/LDA/STA/LDIO/STIO **3**; BEQ (both outcomes)/JMP/STA16 **4**; HALT/TRAP **2**; CALL **9** (3 fetch + 6 stack byte accesses); RET **7** (1 fetch + 6 stack byte accesses). Reset-vector loading remains explicitly abstract initialization, outside these counts.

### PC load path

| Op | `PC_in` source @ `PC_LOAD_EN` |
|----|-------------------------------|
| JMP, CALL, BEQ | abs16 from operand latch |
| RET | **popped 16-bit return address** (not MBR) |

---

## 8. MC / fit gate

| Chip | Gate |
|------|------|
| CPLD-CU (sequential) | WinCUPL **Design fits** when `.pld` exists |
| CPLD-DP | WinCUPL Design fits |

Do not record fitter used-MC counts as normative BOM gates.
