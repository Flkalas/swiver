# M3b — Fetch path and macro execution (v1.0 sequential)

| Field | Value |
|-------|-------|
| **Milestone** | M3b |
| **Goal** | Unified ROM/RAM fetch → **sequential CU** → operand via MBR → 첫 프로그램 HALT |
| **선행** | [M2b G4](M2b-gpr-datapath.md#g4--sequential-add-execute), [M3a](M3a-control-store.md) |
| **Normative** | [cpld-sequential-cu.md](../hardware/cpld-sequential-cu.md) · [cpld-system-controller.md](../hardware/cpld-system-controller.md) |

---

## 1. 추가되는 블록

| 블록 | IC | 넷 | 역할 |
|------|-----|-----|------|
| **PC** | 574+161 | `net_pc0..15` | instruction address |
| **IR** | 574 | `net_ir0..7` | opcode byte → CPLD `OPC[4:0]` |
| **MBR** | 574 | `net_mbr0..7` | operand imm8 / abs16 lo; **ALU B** |
| **MBR hi** | 574 or PC+2 path | — | abs16 high byte (BEQ/JMP/CALL) |
| **Sequential CU** | CPLD-CU | fetch → execute → retire | [cpld-sequential-cu.md](../hardware/cpld-sequential-cu.md) |
| **FLG** | 574 | Z, C | BEQ / flags |
| **PC+1** | 283 (low) | — | sequential fetch |

Datapath: ALU A ← R0 (`q_a`); ALU B ← MBR.

---

## 2. 주소 MUX · 오퍼랜드 데이터 경로

One **64 KiB instruction/data address space** uses one shared address/data bus. RAM is executable. Opcode fetch, operand fetch, data access, and ALU EX are sequential; no operand fetch overlaps a previous EX.

| 모드 | A 버스 소스 | 데이터 → |
|------|-------------|----------|
| Opcode / operand fetch | PC → mapped Flash or RAM | IR (byte0), MBR / abs16 latch (byte1+) |
| Data execution | MBR / abs16 latch / stack address | MEM_RD / MEM_WR, ALU, or MMIO |

### 오퍼랜드 취득

| 명령 | Fetch bytes | MBR / latch | Sequential execute |
|------|-------------|-------------|--------------------|
| LDA `02 imm` | PC, PC+1 | imm8 → MBR (address) | MEM_RD + REG_WE |
| STA `03 imm` | PC, PC+1 | imm8 → MBR | MEM_WR |
| LDIO/STIO | 2-byte | imm8 → MBR | MMIO access; visible WAIT if required |
| BEQ/JMP/CALL | 3-byte | abs16 LE → MBR+hi | Execute after all operand bytes are latched |
| RET | 1-byte | — | Serialized stack reads/writes, redirect last |
| ADD `01 imm` | PC, PC+1 | imm8 → **MBR (held → ALU B)** | EX → **R0** after both fetches |
| `0x10–0x1F` | opcode | — | **trap / invalid** after fetch |

### MBR hold (ALU EX)

During ADD/CMP EX: **do not reload MBR** — operand imm8 must remain on `net_mbr` for ALU B.

RESET vector: `$FFFC/$FFFD` → PC `$0000` (Boot). CPU functional helper treats this as abstract, uncounted initialization; hardware vector sequencing requires separate validation.

---

## 3. 분기 · 플래그 타이밍

| 단계 | 동작 |
|------|------|
| CMP EX | FLG 574에 Z/C 커밋; R0 유지 |
| BEQ EX | 이미 래치된 FLG_Z만 검사; taken이면 `PC_LOAD_EN`, PC ← abs16 |
| JMP | `PC_LOAD_EN`; PC ← abs16 |
| CALL | RP low/high 읽기 → return-PC low/high 쓰기 → RP low/high 쓰기 → redirect |
| RET | RP low/high 읽기 → return-PC low/high 읽기 → RP low/high 쓰기 → redirect |
| Non-branch retire | fetch 동안 증가한 PC를 유지; 다음 opcode는 retire 뒤 fetch |

**관측:** 스코프 on `FLG_Z`, `PC_LOAD_EN`, PC transition. BEQ는 플래그를 갱신하지 않는다. PC redirect는 현재 명령의 마지막에만 커밋한다.

---

## 4. 매크로 타임라인 (@ nominal 2 MHz)

Active SYS schedule: [cpld-sequential-cu.md](../hardware/cpld-sequential-cu.md). Every counted tick belongs to fetch, execute, a serialized stack byte access, or visible WAIT. There are no pipeline fill, bubbles, stalls, or fallback modes.

| 명령 | 기본 성공 경로 | SYS |
|------|----------------|-----|
| ADD / CMP | opcode fetch → imm8 fetch → ALU EX | **3** |
| LDA / STA / LDIO / STIO | opcode fetch → imm8 fetch → data/MMIO EX | **3** |
| BEQ (taken / not taken) / JMP / STA16 | opcode → low byte → high byte → EX | **4** |
| HALT / TRAP | opcode fetch → EX | **2** |
| CALL | 3 fetch + 6 serialized stack byte accesses | **9** |
| RET | 1 fetch + 6 serialized stack byte accesses | **7** |

ADD writes R0 and flags; CMP writes flags only. HALT retires and stops with PC at its opcode; reserved-op TRAP follows the existing no-op retirement policy and continues at the next byte. MBR holds throughout ALU EX. CALL/RET access each RP and return-PC byte separately; no multi-byte access is hidden in one tick. The functional `request_wait()` hook inserts visible WAIT ticks without repeating committed effects or starting a later instruction. Physical ready/timeout sensing and WAIT generation remain pending; the hook does not qualify a hardware handshake. Return-stack errors retain the ISA error policy ([microcode-spec.md](../hardware/microcode-spec.md) §2.3).

The CPU simulator is a zero-delay functional model of this schedule. These counts do not validate memory response times, bus drive, glitches, or setup/hold. Reset-vector initialization is abstract and excluded from the counts.

---

## 5. 단계별 실장 (F0–F5)

### F0 — RESET → PC

`MAP_MODE=0`, RESET vector `$FFFC/$FFFD` → **`$0000`**. Validate hardware vector loading separately from the simulator’s abstract reset helper.

### F1 — Instruction fetch

**테스트 ROM (`$0000`):**

```hex
02 42    ; LDA $42
01 00    ; ADD $00  → R0 = mem[$42] + 0
0A       ; HALT
```

**Pass:** IR = `0x02`; after 2nd fetch MBR = `0x42`.

### F2 — Sequential CU → datapath

1. IR=`0x02` → MEM load path.
2. EX: `MEM_RD` @ MBR=`$42` (visible WAIT as needed).
3. `REG_WE` → R0.

### F3 — PC advance

LDA: PC advances through its two fetch bytes, then holds through data EX. Next opcode fetch follows retire.

### F4 — Full mini-program

LDA → ADD → HALT. **Pass:** R0 holds final sum.

### F5 — BEQ smoke (optional)

ROM: CMP + BEQ; verify `PC_LOAD_EN` only when Z=1; both outcomes cost 4 SYS before visible WAIT; taken redirect commits at instruction completion.

---

## 6. M3b sign-off

- [ ] F0–F4 Pass on **breadboard**
- [ ] Align with [cpld-sequential-cu.md](../hardware/cpld-sequential-cu.md) SYS sheet
- [ ] MBR hold during ADD/CMP EX
- [ ] BEQ: FLG_Z gates `PC_LOAD_EN`

---

## 7. 다음

→ [M4a-boot-sim.md](M4a-boot-sim.md) · [M4b-boot-hardware.md](M4b-boot-hardware.md)
