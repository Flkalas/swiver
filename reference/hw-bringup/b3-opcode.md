# B3 — opcode → control line cheat sheet

Breadboard **DIP / tie** settings for 12 `alu_op[3:0]` operations. **현재 제어표** — `simulators/cyclesim/blocks/alu8.py`의 `ALU_PRESETS`에서 생성한다. 기존 2026-07-04 예제의 입력 제한을 제거하고, NOP의 물리 출력과 CPU hold를 분리했다.

**Netlist has no `alu_sel` bus** — set each control net manually (DIP/tie) for M1 bench.

INC: `cin=1` and `bctrl=0000` (B_add=0) — A+0+1. DEC: `bctrl=1111` (B=0xFF). Do not repurpose `net_b0..7` for INC/DEC — see [alu8.md](../hw/netlist/blocks/alu8.md).

## Control nets (quick ref)

| Net | Role |
|-----|------|
| `net_cin` | 283 carry in (1 for SUB/CMP/**INC**) |
| `net_bctrl0..3` | 153 mux2 data (2C0..2C3); B_CTRL pattern |
| `net_cmp_z`, `net_cmp_c_ge` | SUB-derived CMP flags (`Y==0`, `net_c_hi`) |
| `net_153_s0/s1` | Logic enable → `157_YBP` selects `net_y_logic` |
| `net_lgc0..3` | 153 mux1 data (1C0..1C3) |

## 12 opcodes

| sel | `alu_op` | Op | A | B | cin | bctrl | s1 | s0 | lgc | Y | Y LEDs y7..y0 | Fixed ties |
|-----|----------|-----|---|---|-----|-------|----|----|-----|---|---------------|------------|
| 0 | `0` | **NOP** | `12` | `34` | 0 | `0000` | 0 | 0 | `0000` | `12` | `00010010` | GND: cin, 153_s0, 153_s1, bctrl0, bctrl1, bctrl2, bctrl3, lgc0, lgc1, lgc2, lgc3 |
| 1 | `1` | **ADD** | `12` | `34` | 0 | `1100` | 0 | 0 | `0000` | `46` | `01000110` | GND: cin, 153_s0, 153_s1, bctrl0, bctrl1, lgc0, lgc1, lgc2, lgc3; VCC: bctrl2, bctrl3 |
| 2 | `2` | **SUB** | `12` | `34` | 1 | `0011` | 0 | 0 | `0000` | `DE` | `11011110` | GND: 153_s0, 153_s1, bctrl2, bctrl3, lgc0, lgc1, lgc2, lgc3; VCC: cin, bctrl0, bctrl1 |
| 3 | `3` | **AND** | `12` | `34` | 0 | `0000` | 0 | 1 | `1000` | `10` | `00010000` | GND: cin, 153_s1, bctrl0, bctrl1, bctrl2, bctrl3, lgc0, lgc1, lgc2; VCC: 153_s0, lgc3 |
| 4 | `4` | **OR** | `12` | `34` | 0 | `0000` | 1 | 0 | `1110` | `36` | `00110110` | GND: cin, 153_s0, bctrl0, bctrl1, bctrl2, bctrl3, lgc0; VCC: 153_s1, lgc1, lgc2, lgc3 |
| 5 | `5` | **XOR** | `12` | `34` | 0 | `0000` | 1 | 1 | `0110` | `26` | `00100110` | GND: cin, bctrl0, bctrl1, bctrl2, bctrl3, lgc0, lgc3; VCC: 153_s0, 153_s1, lgc1, lgc2 |
| 6 | `6` | **NOT** | `12` | `34` | 0 | `0000` | 1 | 1 | `0101` | `ED` | `11101101` | GND: cin, bctrl0, bctrl1, bctrl2, bctrl3, lgc1, lgc3; VCC: 153_s0, 153_s1, lgc0, lgc2 |
| 7 | `7` | **PASS_A** | `12` | `34` | 0 | `0000` | 0 | 1 | `1010` | `12` | `00010010` | GND: cin, 153_s1, bctrl0, bctrl1, bctrl2, bctrl3, lgc0, lgc2; VCC: 153_s0, lgc1, lgc3 |
| 8 | `8` | **PASS_B** | `12` | `34` | 0 | `0000` | 0 | 1 | `1100` | `34` | `00110100` | GND: cin, 153_s1, bctrl0, bctrl1, bctrl2, bctrl3, lgc0, lgc1; VCC: 153_s0, lgc2, lgc3 |
| 9 | `9` | **INC** | `12` | `34` | 1 | `0000` | 0 | 0 | `0000` | `13` | `00010011` | GND: 153_s0, 153_s1, bctrl0, bctrl1, bctrl2, bctrl3, lgc0, lgc1, lgc2, lgc3; VCC: cin |
| 10 | `A` | **DEC** | `12` | `34` | 0 | `1111` | 0 | 0 | `0000` | `11` | `00010001` | GND: cin, 153_s0, 153_s1, lgc0, lgc1, lgc2, lgc3; VCC: bctrl0, bctrl1, bctrl2, bctrl3 |
| 11 | `B` | **CMP** | `12` | `34` | 1 | `0011` | 0 | 0 | `0000` | `DE` | `11011110` | GND: 153_s0, 153_s1, bctrl2, bctrl3, lgc0, lgc1, lgc2, lgc3; VCC: cin, bctrl0, bctrl1 |

Columns: **bctrl** = `net_bctrl3..0` (mux2 2C3..2C0), **lgc** = `net_lgc3..0` (mux1 1C3..1C0), **Y LEDs** = MSB left (y7) … LSB (y0).

NOP는 A=12일 때 물리 Y=12이며 CPU 상태를 유지한다. NOT/PASS는 반대편 입력을 고정할 필요가 없다. CMP는 SUB 출력을 만들지만 CPU ACC는 쓰지 않는다. 153 선택값은 `A_bit + 2 × B_bit`이며 `s0/s1`으로 덮어쓰지 않는다.

재생성: `python -m simulators.cyclesim.export.alu8_controls --write` (표만 변경). 검사: 같은 명령의 `--check`.

## Smoke vectors (B3a first)

| Op | A | B | Expected Y |
|----|---|---|------------|
| SUB | 0x12 | 0x34 | 0xDE |
| XOR | 0x12 | 0x34 | 0x26 |
| INC | 0x12 | — | 0x13 |

See phased bring-up: [M1-b3-procedure.md](M1-b3-procedure.md).
