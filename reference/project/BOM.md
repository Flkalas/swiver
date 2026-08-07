# Swiver — 구매 목록 (v1.0 breadboard, 1세트)

**Normative:** [../hardware/system-architecture.md](../hardware/system-architecture.md) v1.0  
**1세트 부품 명세** · 5 V · 74HC DIP 빵판 · **dual CPLD** + **pipe CU**  
PCB 3.3 V 대응 목록: [BOM-3v3.md](BOM-3v3.md) (**중복 주문 금지**)

**범위:** M1–M4 빵판 브링업(ALU → CPLD → CPU → Flash/RAM). 메일박스 레벨 시프트·코프로는 본 목록에 **없음**.

| 부품 | Qty | 구분 | 기능 | 역할·목적 | 확인 |
|------|-----|------|------|-----------|------|
| 74HC283 | 2 | ALU | 4-bit full adder | 덧셈·뺄셈·증감 경로 |  |
| 74HC153 | 8 | ALU | Dual 4-to-1 mux | 비트슬라이스 (mux1 논리 + mux2 B경로) |  |
| 74HC157 | **4** | ALU · 주소 | Quad 2-to-1 mux | 산술/논리 → Y 선택 + 주소 버스 하위 |  |
| 74HC574 | **4** | CPU | Octal D FF, 3-state | MBR / FLG / IR / ACC(M1) |  |
| 74HC138 | **2** | CPU | 3-to-8 decoder | CE half-select + coarse map |  |
| 74HC08 | 2 | CPU | Quad AND | CE glue + MAP |  |
| 74HC32 | 2 | CPU | Quad OR | CE glue + BEQ |  |
| 74HC161 | 3 | CPU | 4-bit sync counter | PC 하위 |  |
| ATF1504AS-10JU44 | **2** | CPLD | CPLD, 64 MC, PLCC-44 | **CPLD-CU** pipe + **CPLD-DP** GPR |  |
| PLCC-44↔DIP adapter | **2** | CPLD | PLCC-44 → 2.54 mm DIP | ATF1504×2 빵판 장착 |  |
| 74HC245 | 1 | 메모리 | Octal bus transceiver | SRAM ↔ CPU 데이터 버스 |  |
| SST39SF010A-70-4C-PHE | 1 | 메모리 | 128K×8 parallel NOR Flash, PDIP-32 | 부트·유틸리티 |  |
| IS62C256AL-45ULI-TR | 2 | 메모리 | 32K×8 SRAM, SOP | 실행 RAM 64 KB (adapter 필요) |  |
| SOP28↔DIP adapter | 2 | 메모리 | SOP28 → DIP | SRAM 빵판 장착 |  |
| 2.000 MHz oscillator | 1 | 클록 | — | **`CLK_SYS`** 단일 소스 (`IF\|EX`) |  |
| 74HC14 | 1 | 클록 | Hex Schmitt inverter | `CLK_SYS` 배포·정형 |  |
| Breadboard power supply | 1 | 전원 | — | 전원 공급 |  |
| Breadboard | — | 인프라 | — | CPU·ALU·메모리·CPLD 작업 면 |  |
| 0.6 mm 단선 와이어 (≈22 AWG) | — | 인프라 | 단선 (Single Core) | 전원·점퍼·버스 배선 (다색, 필요량) |  |
| Tactile / pushbutton | 1 | 인프라 | — | CPU RESET |  |
| Slide / DIP switch (1극) | 1 | 인프라 | — | Boot/Run MAP_MODE |  |
| 0.1 µF ceramic | — | 패시브 | — | Decoupling capacitor |  |
| 10 µF tantal / electrolytic | — | 패시브 | — | Bulk capacitor |  |
| 330 Ω ×8 SIP-9 | — | 패시브 | — | 버스 댐핑 |  |
| 10 kΩ ×8 SIP-9 | — | 패시브 | — | 풀업 |  |
| 10 kΩ | — | 패시브 | — | RESET·스위치 풀업 |  |
| ATF1504 JTAG/ISP programmer | 1 | 장비 | — | CPLD 소각 |  |
| NOR Flash programmer | 1 | 장비 | — | Flash 내용 기록 |  |
