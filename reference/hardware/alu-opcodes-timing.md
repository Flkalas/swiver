# ALU 명령어 · 조합 지연 (alu8)

**버전:** 1.5 · **기준일:** 2026-07-13  
**블록:** [`hw/netlist/blocks/alu8.yaml`](../../hw/netlist/blocks/alu8.yaml)  
**디코드:** **M1** — DIP / [b3-opcode.md](../hw-bringup/b3-opcode.md) · **SoC** — CPLD sequential CU ([control-and-decode.md](control-and-decode.md), [cpld-sequential-cu.md](cpld-sequential-cu.md))

12개 `alu_sel[3:0]` 연산의 동작·제어·**조합 전파 지연**을 한 표로 정리합니다.  
지연 값은 pre-flight sim [`74hc.yaml`](../../hw/timing/74hc.yaml) **datasheet typ/max** 합산(배선 지연 0)이며, **2.0 MHz** `CLK_SYS` 전주기 **500 ns** 대비 slack을 함께 기록합니다.

실기 치트시트: [`b3-opcode.md`](../hw-bringup/b3-opcode.md) · ISA×phase: [`microcode-spec.md`](microcode-spec.md)

---

## 1. 명령어 요약

| sel | `alu_op` | Mnemonic | 동작 | C / Z 플래그 |
|-----|----------|----------|------|---------------|
| 0 | `0x0` | **NOP** | 물리 Y = A (제로 제어); CPU 상태 유지 | 유지 |
| 1 | `0x1` | **ADD** | Y = A + B | C = carry, Z = (Y==0) |
| 2 | `0x2` | **SUB** | Y = A + ~B + 1 (2의 보수) | C = carry, Z; borrow = ~C_hi |
| 3 | `0x3` | **AND** | Y = A & B | Z |
| 4 | `0x4` | **OR** | Y = A \| B | Z |
| 5 | `0x5` | **XOR** | Y = A ^ B | Z |
| 6 | `0x6` | **NOT** | Y = ~A (B 무시) | Z |
| 7 | `0x7` | **PASS_A** | Y = A (B 무관, LGC=1010) | Z |
| 8 | `0x8` | **PASS_B** | Y = B (A 무관, LGC=1100) | Z |
| 9 | `0x9` | **INC** | Y = A + 1 (`cin=1`, `bctrl=0000` → A+0+1) | C, Z |
| 10 | `0xA` | **DEC** | Y = A − 1 (`bctrl=1111`) | C, Z |
| 11 | `0xB` | **CMP** | SUB와 동일 Y | C, Z — `net_cmp_z`=`Y==0`, `net_cmp_c_ge`=`net_c_hi` |
| 12–15 | — | *(예약)* | NOP 취급 | — |

- **A** · **B**: `net_a0..7`, `net_b0..7`.
- **INC/DEC**: `net_b0..7` 구동 금지 — INC=`cin=1` + `bctrl=0000`; DEC=`bctrl=1111` ([bringup §INC/DEC](../hw-bringup/b3-opcode.md)).

---

## 2. 제어 신호 (`alu_sel` → 하드와이어)

| sel | Op | cin | bctrl3:0 | s1:s0 | lgc3:0 |
|-----|-----|-----|----------|-------|--------|
| 0 | NOP | 0 | 0000 | 00 | 0000 |
| 1 | ADD | 0 | 1100 | 00 | 0000 |
| 2 | SUB | 1 | 0011 | 00 | 0000 |
| 3 | AND | 0 | 0000 | 01 | 1000 |
| 4 | OR | 0 | 0000 | 10 | 1110 |
| 5 | XOR | 0 | 0000 | 11 | 0110 |
| 6 | NOT | 0 | 0000 | 11 | 0101 |
| 7 | PASS_A | 0 | 0000 | 01 | 1010 |
| 8 | PASS_B | 0 | 0000 | 01 | 1100 |
| 9 | INC | 1 | 0000 | 00 | 0000 |
| 10 | DEC | 0 | 1111 | 00 | 0000 |
| 11 | CMP | 1 | 0011 | 00 | 0000 |

`lgc3:0` → `net_lgc3..0` (153 mux1 C3..C0). 153 선택값은 항상 `A_bit + 2 × B_bit`; `s0|s1`은 코어 밖에서 **157_YBP**의 출력 경로만 고른다. 153 `1G/2G`와 157 `G`는 GND에 타이한다.

표 원본은 `simulators/cyclesim/blocks/alu8.py`의 `ALU_PRESETS`이며 `python -m simulators.cyclesim.export.alu8_controls --check`로 정합성을 검사한다. 물리 `net_c_hi`는 논리 출력 선택 중에도 가산기 carry를 유지한다. `net_cmp_z`/`net_cmp_c_ge`는 12칩 밖 관측 경계이고, CMP의 ACC 쓰기 금지와 NOP의 상태 유지는 CPU 정책이다.

---

**검증 경계 (2026-10):** 아래 지연 수치는 기존 동결 타이밍 자료를 유지한다. 새 뷰어의 제로 지연 기능 검증은 이 ns 수치를 재측정하거나 보증하지 않는다. LUT 정합화 이후의 실제 지연·배선·전기적 fanout 검증은 별도 브링업 항목이다.

## 3. 조합 전파 지연 (operand → Y)

비교 기준: **500 ns** = 명목 2.0 MHz `CLK_SYS` 전주기. 아래 ALU 단독 동결 수치는 유지하며, 새 순차 CU 전체 경로의 타이밍 합격은 [cpld-sequential-cu.md](cpld-sequential-cu.md)의 별도 실기 게이트다.

### 3.1 opcode별 지연 · slack

<!-- TIMING_TABLE_START -->
| sel | Op | 경로 등급 | max (ns) | slack @ max (ns) | 비고 |
|-----|-----|-----------|----------|------------------|------|
| 0 | NOP | adder | **108** | 392 | sum path (물리 Y=A) |
| 1 | ADD | adder | **108** | 392 | 283 → **157_YBP** |
| 2 | SUB | arith B-path | **136** | 364 | 153 mux2 → 283 |
| 3 | AND | logic | **46** | 454 | `U_ALU_153_0` mux1 → 157_YBP |
| 4 | OR | logic | **46** | 454 |  |
| 5 | XOR | logic | **46** | 454 |  |
| 6 | NOT | logic | **46** | 454 |  |
| 7 | PASS_A | logic | **46** | 454 | 기존 측정: AND pattern + B=FF; 새 PASS LUT 재측정 아님 |
| 8 | PASS_B | logic | **46** | 454 | 기존 측정: AND pattern + A=FF; 새 PASS LUT 재측정 아님 |
| 9 | INC | **critical** | **153** | 347 | `net_cin` → 283 ripple |
| 10 | DEC | adder | **108** | 392 | 283-only test path; full path = SUB class |
| 11 | CMP | arith B-path | **136** | 364 | Y = SUB; flags §3.5 |
<!-- TIMING_TABLE_END -->

측정: [`alu8_opcode_timing`](../../hw/tests/alu8_opcode_timing.yaml) · pre-flight sim artifact `alu8_opcode_timing/timing_report.json` (@ **max**).

**worst-case (Y):** **INC** — **153 ns** (slack **347 ns** @ 500 ns).  
**SUB / CMP:** **136 ns** (slack **364 ns**).  
**fastest:** logic opcodes — **46 ns**.

**Comb-limited Fmax (INC 기준):** \(F \approx 1 / 153\,\text{ns} \approx 6.5\,\text{MHz}\). 명목 **2 MHz:** slack = 500 − 153 = **347 ns**.

### 3.2 canonical critical path (bit0, @ max)

| Op | ref.pin hop chain |
|----|-------------------|
| **INC** | `net_cin` → `U_ALU_283_LO.C0` → `C4` → `U_ALU_283_HI.C4` → `U_ALU_157_YBP_0.1A` → `1Y` |
| **SUB / CMP** | `net_b0` → `U_ALU_153_0.B` → `2Y` → `U_ALU_283_LO.B0` → `C4` → `U_ALU_283_HI.C4` → `U_ALU_157_YBP_0.1A` → `1Y` |
| **ADD / NOP / DEC*** | `U_ALU_283_LO.A0` → `C4` → `U_ALU_283_HI.C4` → `U_ALU_157_YBP_0.1A` → `1Y` |
| **AND / OR / XOR / NOT / PASS** | `U_ALU_153_0.1Y` → `U_ALU_157_YBP_0.4B` → `4Y` |

\* DEC timing vector uses 283-only path; normative full datapath delay class = SUB (**136 ns**).

### 3.3 ACC 래치 (Y → 574.Q)

B3c 브링업 경로 — ALU 출력이 **다음 posedge** 전에 setup 만족해야 함.

| 구간 | typ (ns) | max (ns) | slack @ max (ns) |
|------|----------|----------|------------------|
| `157_YBP_0.1Y` → `574_ACC.D0` (+ setup) | 17 | 28 | 472 |

전체 **operand → ACC.Q** (max): INC 기준 **153 + 23 (574 t_pd)** ≈ **176 ns** (ACC.Q 직결 A-side, CPLD async read 미포함).

### 3.5 CMP 플래그 (SUB 유도, no 7485)

`ALU_CMP_SUB`: CMP/SUB 시 (`bctrl` SUB pattern, `cin=1`) **Z** = all `net_y==0`, **C_GE** = `net_c_hi`.  
pre-flight sim [`alu8_cmp_sub`](../../hw/tests/alu8_cmp_sub.yaml) — 플래그 behavioral 상한 **151 ns** @ max (`74hc.yaml` `ALU_CMP_SUB`); pin-chain SUB Y = **136 ns**.

| 구간 | typ (ns) | max (ns) | 비고 |
|------|----------|----------|------|
| `net_b0` → `net_cmp_z` | — | **≤151** | behavioral upper bound |
| `net_b0` → `net_cmp_c_ge` | — | **≤151** | via `net_c_hi` @ 283 |

실기: `net_cmp_z` / `net_cmp_c_ge` → FLG 574 또는 CPLD; Execute 말 샘플 ([`alu8.md`](../../hw/netlist/blocks/alu8.md)).

### 3.4 CPLD datapath 구성요소 (동결 참고치)

현재 CPU 제어는 **순차 CU** ([cpld-sequential-cu.md](cpld-sequential-cu.md))다. 아래는 기존 설계의 구성요소별 동결 참고치이며 새 순차 스케줄의 E2E 실측이나 타이밍 합격이 아니다. ALU 경로에는 CPLD `q_a`와 래치 경로가 추가되므로 별도 setup/hold·부하·배선 검증이 필요하다.

| 구간 | typ (ns) | max (ns) | 비고 |
|------|----------|----------|------|
| CPLD `q_a` → ALU A | 10 | 15 | [`cpld.yaml`](../../hw/timing/cpld.yaml); B from MBR |
| ALU comb (worst INC) | — | **153** | §3.1 |
| ALU comb (SUB/CMP Y) | — | **136** | §3.1 |
| Y → 574 latch setup | 17 | 28 | §3.3 |

---

## 4. pre-flight sim 검증 · 파형 측정

| 테스트 | 검증 opcode / 구간 | 리포트 delay (max) |
|--------|-------------------|-------------------|
| [`alu8_full`](../../hw/tests/alu8_full.yaml) | 12 opcode 기능 | — |
| [`alu8_opcode_timing`](../../hw/tests/alu8_opcode_timing.yaml) | 12 opcode slack | INC **153**, SUB **136**, logic **46**, ADD **108** |
| [`alu8_timing`](../../hw/tests/alu8_timing.yaml) | ADD carry · logic hop | ADD **108** ns, `U_ALU_153_0` logic **46** ns |
| [`alu8_cmp_sub`](../../hw/tests/alu8_cmp_sub.yaml) | CMP flags | behavioral **≤151** ns |
| [`alu_b3_sub_critical`](../../hw/tests/alu_b3_sub_critical.yaml) | SUB | **136** ns @ max; slack **364** ns |
| [`alu_b3_xor_critical`](../../hw/tests/alu_b3_xor_critical.yaml) | XOR | **46** ns |
| [`alu_b3_latch`](../../hw/tests/alu_b3_latch.yaml) | ACC setup | **51** ns (153→574 CP) |
| [`alu283_carry`](../../hw/tests/alu283_carry.yaml) | 283 only | ripple **90** ns |

---

## 5. CPU 맥락 — 명령 “지연” (macro-cycle)

ALU 블록 자체는 **순수 조합**입니다. ISA 수준 지연은 [순차 CU](cpld-sequential-cu.md)의 fetch → execute → retire SYS 스케줄에 따릅니다. opcode/operand fetch와 EX는 겹치지 않습니다.

| 계층 | 지연 / 횟수 | 설명 |
|------|-------------|------|
| ALU comb | **≤ 153 ns** | 위 §3의 ALU 단독 동결 참고치 (worst INC) |
| ADD/CMP/LDA/STA/LDIO/STIO | **3 SYS** | 기본 성공 경로; fetch와 EX 직렬화 |
| BEQ (양쪽 결과)/JMP/STA16 | **4 SYS** | 3-byte fetch 후 실행 |
| HALT/TRAP | **2 SYS** | opcode fetch 후 실행 |
| CALL / RET | **9 / 7 SYS** | 각각 3 / 1 fetch + 6 stack byte accesses |
| WAIT | **추가 SYS** | 지연된 접근을 trace에 노출 |
| 시스템 클록 | **명목 2.0 MHz** | **500 ns** period; 전체 CPU 실기 합격 별도 |

CALL/RET는 RP low/high 읽기 → return-PC low/high 접근 → RP low/high 쓰기를 직렬화하고 redirect를 마지막에 커밋한다. reset-vector helper는 SYS 횟수 밖의 추상 초기화다.

### 이전 pipeline 경로 예산 (역사적 참고)

아래 합산치는 이전 [P12 pipe CU](cpld-pipe-cu.md)의 desk 참고치로 보존한다. 현재 순차 CU의 클록 한계나 실기 타이밍을 입증하지 않는다. 제로 지연 CPU 기능 테스트 역시 전파 지연·글리치·setup/hold 검증이 아니다.

| Path | ns | Note |
|------|---:|------|
| Branch BEQ | **212** | 이전 pipe desk: **288 ns** slack @ 500 ns |
| Operand path | **~133** | 이전 pipe desk: MBR→B + `q_a` |

---

## 6. 스모크 벡터

| Op | A | B | Y |
|----|---|---|---|
| SUB | `0x12` | `0x34` | `0xDE` |
| XOR | `0x12` | `0x34` | `0x26` |
| INC | `0x12` | — | `0x13` |
