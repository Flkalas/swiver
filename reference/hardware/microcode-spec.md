# Microcode Specification v1.0 sequential

**Normative:** v1.0 breadboard intent — **non-pipelined in-order** CU, unified 64 KiB/shared instruction-data bus, RAM execution
**Related:** [cpld-sequential-cu.md](cpld-sequential-cu.md) · [rom-architecture.md](rom-architecture.md) · [cpld-system-controller.md](cpld-system-controller.md)

---

## 1. Architecture

| Axis | Choice | Rationale |
|------|--------|-----------|
| Opcode | Core `0x01–0x0F`; **`0x10–0x1F` reserved** | 5-bit opcode field `[4:0]` |
| Control | **Sequential CU** | FETCH_OPCODE / FETCH_OPERAND / EXECUTE / stack / WAIT — [cpld-sequential-cu.md](cpld-sequential-cu.md) |
| Decode | **Sequential FSM** | Decode and strobes in CPLD-CU |
| CPLD | Dual ATF1504 | **CU:** sequential · **DP:** **R0 (AC) only**; **ALU B from MBR 574** |
| Control store | **CPLD FSM** | Strobes from sequential CU outputs |

Control lives in the CPLD sequential CU ([rom-architecture.md](rom-architecture.md) Flash map).

### 1.1 Sequential schedule

Active schedule = sequential phases and SYS costs in [cpld-sequential-cu.md](cpld-sequential-cu.md). Finish all opcode/operand fetch and execute/stack phases of the current instruction before fetching the next opcode. Operand fetch and execute are separate SYS ticks. Each tick performs one phase or a visible WAIT (the functional `request_wait()` hook; physical WAIT generation remains pending); no prefetch, overlap, branch bubble or pipe fallback.

### 1.2 Operand datapath

| Port | Source |
|------|--------|
| ALU A | CPLD-DP `q_a` ← **R0** |
| ALU B | **MBR / operand latch** `net_mbr[7:0]` → `net_b[7:0]` |
| GPR write | `d_in` → **R0** when `reg_we` (G-IC) |

**MBR/oper hold:** During ADD/CMP EX, operand must **not** reload until the macro retires.

---

## 2. Macro ISA

### 2.0 Instruction formats (encoding)

Opcode field: **bits `[4:0]`** of the first instruction byte. Bits `[7:5]` are **reserved (0)** for normative opcodes.

| Format | Size | Layout |
|--------|------|--------|
| **Implied** | 1 B | `[7:5]=0`, `[4:0]=opcode` — HALT, **RET** |
| **Imm8** | 2 B | byte0: opcode; byte1: imm8 — LDA, STA, CMP, ADD, LDIO, STIO |
| **Abs16** | 3 B | byte0: opcode; bytes1–2: addr LE — BEQ, JMP, CALL, STA16 |

**Opcode group `0x10–0x1F`:** **reserved / trap**.

### 2.1 Core (`0x01–0x0F`)

| Op | Mnemonic | Summary |
|----|----------|---------|
| `0x01` | ADD | **R0 ← R0 + imm** |
| `0x02` | LDA | Load from mem → R0 |
| `0x03` | STA | Store R0 to mem |
| `0x04` | BEQ | Branch if Z |
| `0x05` | JMP | Jump |
| `0x06` | CALL | Subroutine — push return PC; PC ← abs16 |
| `0x07` | RET | Return — pop return PC → PC |
| `0x08` | LDIO | Load MMIO → R0 |
| `0x09` | STIO | Store R0 to MMIO |
| `0x0A` | HALT | Stop |
| `0x0C` | — | **Reserved** |
| `0x0D` | CMP | R0 − imm; flags only |
| `0x0F` | STA16 | Store abs16 (boot) |

### 2.2 Sequential SYS costs

Normative default successful-access schedule: [cpld-sequential-cu.md](cpld-sequential-cu.md) §4. Counts exclude WAIT; these are logical SYS counts, not measured hardware timing.

| Op | SYS | Breakdown |
|----|----:|-----------|
| ADD/CMP/LDA/STA/LDIO/STIO | **3** | opcode + operand + execute |
| BEQ taken or not / JMP / STA16 | **4** | opcode + two operands + execute |
| HALT / reserved-op trap | **2** | opcode + execute (HALT stops; reserved trap retires as no-op) |
| CALL | **9** | three instruction bytes + six stack byte accesses |
| RET | **7** | one instruction byte + six stack byte accesses |

There is no warm-stream discount or taken-branch tax. Additional WAIT ticks are counted separately. HALT retains PC at its opcode and stops after retirement. Reserved-op trap preserves the existing no-op retirement policy and advances to the next byte.

### 2.3 Return stack (CU-assisted)

No hardware RP register. CALL/RET push/pop is performed by **CPLD-CU** using six sequential `MEM_RD`/`MEM_WR` byte accesses: RP low/high reads, return-PC low/high accesses, RP low/high writes. The final successful RP-high write completes the instruction and commits its PC redirect.

| Item | Normative value |
|------|-----------------|
| RP cell | `$0F00` / `$0F01` (16-bit LE) |
| Stack body | `$F600`–`$FEEF`, upward growth |
| Boot initial RP | `$F600` ([boot-jmp-handoff.md](../boot/boot-jmp-handoff.md)) |
| CALL | `return_pc` after 3-byte insn; push; `PC←abs16` |
| RET | pop → `PC`; **`PC_in` ≠ MBR** |
| Overflow / underflow / invalid RP | execution **stops** after RP validation, before stack writes |

---

## 3. Control (sequential CU)

| Mechanism | Source |
|-----------|--------|
| GPR write | G-IC **`reg_we`** only — DP hardwires **R0** |
| `PC_LOAD_EN` | Opcode + `FLG_Z` on redirect EX |
| Operand imm8 | **MBR / oper latch** from FETCH_OPERAND |
| ALU / bus strobes | **CPLD-CU** sequential outputs |

Verify: [cpld-sequential-cu.md](cpld-sequential-cu.md).

---

## 4. Per-op strobes (separate execute phase)

See [cpld-sequential-cu.md](cpld-sequential-cu.md) §5.

| Class | Key EX strobes |
|-------|----------------|
| ADD | `Y_OE`, `REG_WE`→R0, `FLG_WE`, ALU ADD in separate execute SYS |
| CMP | `FLG_WE`, ALU CMP; B from MBR/oper |
| MEM_LD | `MEM_RD` + `REG_WE` (one default execute SYS) |
| MEM_ST | `Y_OE` + `MEM_WR` (one default execute SYS) |
| BEQ | flags path; `PC_LOAD_EN` if Z; no bubble |
| JMP / CALL / RET | `PC_LOAD_EN`; CALL/RET use six ordered stack accesses |

Bus and ALU strobes are **direct CPLD-CU outputs**. `REG_WE` reaches CPLD-DP via **G-IC**.

---

## 5. G-IC (CPLD-CU → DP)

| Signal | Function |
|--------|----------|
| `reg_we` | GPR write strobe — **always targets R0** in DP |

G-IC is a single wire: `reg_we`.

---

## 6. Branch macros

| Op | `PC_LOAD_EN` | Operand / PC source |
|----|--------------|---------------------|
| BEQ | `FLG_Z` | abs16 latch |
| JMP | unconditional | abs16 latch |
| CALL | unconditional | abs16; stack push |
| RET | unconditional | **popped return PC** |
| HALT | — | — |

---

## 7. ALU controls

CPLD drives `cin`, `bctrl0..3`, `lgc3:0`, `y_mux_sel` ([control-and-decode.md](control-and-decode.md)). M1 bench may use DIP decode separately.

**Timing boundary:** the earlier P12 pipe EX ADD estimate (148 ns) is superseded historical evidence in [cpld-pipe-cu.md](cpld-pipe-cu.md) §7. ALU-only combinational figures in [alu-opcodes-timing.md](alu-opcodes-timing.md) do not validate sequential shared-bus timing. The 2 MHz target, sequential timing and WinCUPL Design fits remain pending.

---

## 8. `/NMI`

Inactive (pull-up). No MMU/IRQ.
