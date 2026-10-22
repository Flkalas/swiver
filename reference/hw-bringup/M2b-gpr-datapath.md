# M2b — CPLD GPR datapath (v1.0)

| Field | Value |
|-------|-------|
| **Milestone** | M2b (datapath) |
| **Normative** | [cpld-system-controller.md](../hardware/cpld-system-controller.md) v1.0 sequential |
| **Goal** | **CPLD-only R0 (AC)** + MBR→ALU B + ADD (no external 574 GPR) |

---

## 1. 아키텍처 요약

| 항목 | v1.0 |
|------|------|
| GPR | **ATF1504 내부 R0 only** |
| Read | **R0→`q_a`→ALU A** |
| Operand B | **MBR 574 → `net_mbr` → ALU B** |
| Write | `REG_WE` → **R0** from `d_in` |
| ALU ctrl | CPLD FSM → `cin`/`bctrl*`/`lgc*` **직접** |
| Decode | SoC: CPLD-CU; M1 bench may use DIP |

공유 버스: `net_d0..7` — [breadboard-wiring.md](breadboard-wiring.md).

---

## 2. CPLD ↔ ALU 결선

| CPLD / MBR | ALU 입력 |
|------------|----------|
| `q_a0..7` (DP) | `net_a0..7` |
| `net_mbr0..7` (MBR 574) | `net_b0..7` |
| `cin`, `bctrl0..3` (CU) | 283 / 153 mux2 |
| `lgc3..0` (CU) | 153 mux1 |
| `y_mux_sel` (CU) | 157_YBP select |

| ALU 출력 | 목적지 |
|----------|--------|
| `net_y0..7` | 버스 (`Y_OE` 시) → CPLD `d_in` (R0 write) |

---

## 3. GPR 쓰기 규칙

```text
REG_WE=1 @ CLK↑ → R0 <= d_in
```

- 한 사이클에 **REG_WE 1회**만 (FSM 보장).
- `d_in` 구동원: ALU Y (`Y_OE=1`) 또는 SRAM (`MEM_RD=1` via 245).

---

## 4. 단계별 검증 (G0–G4)

### G0 — MBR → ALU B

**작업:** MBR에 imm8 프리로드; scope on `net_b*` = `net_mbr*`.

**Pass:** ALU B matches MBR.

### G1 — R0 프리로드

**작업:** `REG_WE` + `d_in` → R0에 `0x12` 래치.

**Pass:** `q_a` = `0x12`.

### G2 — q_a 관측

**Pass:** `q_a` = R0 async (~10 ns typ).

### G3 — CMP 플래그

**작업:** R0=`0x12`, MBR=`0x34`; ALU CMP; `FLG_WE`.

**Pass:** Z/C from ALU (B from MBR).

### G4 — Sequential ADD execute

**작업:** R0=`0x12`, MBR=`0x34`; operand fetch 완료 뒤 ADD EX; `Y_OE`, `REG_WE`.

**Pass:** **R0** = `0x46` (ADD writeback to AC). opcode/operand fetch와 EX가 겹치지 않고, 다음 명령 fetch는 이 명령 완료 뒤 시작한다 ([순차 CU](../hardware/cpld-sequential-cu.md)).

---

## 5. 버스 규칙

| 구동원 | 조건 |
|--------|------|
| ALU Y | `Y_OE`=1 |
| SRAM | `MEM_RD`=1 (245 경유) |

**버스 충돌:** `Y_OE`와 `MEM_RD` 동시 1 금지.
