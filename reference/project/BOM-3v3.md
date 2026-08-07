# Swiver — 구매 목록 (v0.1, 1세트 · 3.3 V PCB)

**1세트 부품 명세** · 단일 **3.3 V** · **PCB SMD**  
5 V 빵판 구매 목록: [BOM.md](BOM.md) (**중복 주문 금지**)

**범위:** [BOM.md](BOM.md)와 동일 — 브링업 CPU 코어. 메일박스 레벨 시프트·Flash 비트뱅·코프로는 **선택/별도**.

| # | 구분 | MPN | Description | Pkg | Qty | 역할 · 목적 | 비고 |
|---|------|-----|-------------|-----|-----|-------------|------|
| 0 | PCB | *(Swiver v0.1 CPU PCB)* | Bare PCB, 2–4 layer FR4 | — | 1 | 모든 SMD·커넥터 | [BOM.md](BOM.md) 빵판·어댑터 **대체** |
| 0b | PCB | *(SMD stencil, 선택)* | Stencil | — | 0–1 | 납땜 보조 | |
| P1 | 전원 | USB-C receptacle (USB 2.0) | — | SMD | 1 | 외부 5 V 입력 | ↔ BOM #20 |
| P2 | 전원 | AP2112K-3.3TRG1 (또는 동급 ≥600 mA) | LDO | SOT-23-5 | 1 | **3.3 V** 레일 | |
| P2b | 전원 | *(선택)* buck | — | SOT-23-6 | 0–1 | 전류·발열 여유 | |
| P3 | 전원 | 10 µF + 22 µF ceramic | — | 0805 | 6 | LDO 벌크 | |
| 4 | ALU | SN74LVC283APWR | 4-bit adder | TSSOP-16 | 2 | ↔ #4 |
| 5 | ALU | SN74LVC153APWR | Dual 4-to-1 mux | TSSOP-16 | 8 | ↔ #5 |
| 6 | ALU | SN74LVC157APWR | Quad 2-to-1 mux | TSSOP-16 | 2 | ↔ #6 · **12 IC** ALU |
| 7 | CPU | SN74LVC574APWR | Octal D FF | TSSOP-20 | **4** | MBR / FLG / IR / ACC | ↔ #7 |
| 8 | CPU | SN74LVC138APWR | 3-to-8 decoder | TSSOP-16 | **2** | CE / map | ↔ #8 |
| 9 | CPU | SN74LVC08APWR / SN74LVC32APWR | AND / OR | TSSOP-14 | 2 each | CE glue + MAP + BEQ | ↔ #9 |
| 10 | CPU | SN74LVC161APWR | 4-bit counter | TSSOP-16 | 3 | PC 하위 | ↔ #10 |
| 11 | CPU | SN74LVC157APWR | Quad 2-to-1 mux | TSSOP-16 | 2 | 주소 하위 | ↔ #11 · #6과 합산 4 |
| 12 | CPLD | ATF1504AS-10JU44 | CPLD, 64 MC | PLCC-44 | **2** | pipe CU + DP | ↔ #12 |
| 13 | CPLD | *(JTAG 2×5, 1.27 mm)* | Pin header | TH | 1 | 구성 포트 | |
| 14 | CPLD | *(SMD slide or tact)* | MAP switch | SMD | 1 | Boot/Run MAP | ↔ #14 |
| 15 | 메모리 | SN74LVC245APWR | Octal transceiver | TSSOP-20 | 1 | SRAM ↔ CPU | ↔ #15 |
| 16 | 메모리 | SST39SF010A-70-4C-PHE | 128K×8 NOR Flash | TSOP-32 | 1 | 부트·유틸 | ↔ #16 |
| 17 | 메모리 | IS62C256AL-45ULI-TR | 32K×8 SRAM | SOP-28 | 2 | 64 KB RAM | ↔ #17 |
| 18 | 클록 | *(2.000 MHz CMOS XO, 3.3 V)* | Crystal oscillator | 3225 / 5032 | 1 | **`CLK_SYS`** 단일 소스 | ↔ #18 |
| 19 | 클록 | SN74LVC14APWR | Hex Schmitt inverter | TSSOP-14 | 1 | `CLK_SYS` 배포 | ↔ #19 |
| 21 | 패시브 | 0.1 µF 50 V X7R | Ceramic | 0603 | 40 | 디커플 | |
| 22 | 패시브 | 10 µF 10 V X5R | Ceramic | 0805 | 12 | 벌크 | |
| 23 | 패시브 | 33 Ω 1% | Resistor | 0603 | 32 | 버스 댐핑 | |
| 24 | 패시브 | 10 kΩ 1% | Resistor | 0603 | 40 | 풀업 | |
| 25 | 패시브 | 1N4148W | Diode | SOD-123 | 6 | 클램프 | |
| — | 장비 | *(ATF1504 JTAG/ISP)* | CPLD programmer | — | 1 | CPLD 소각 | |
| — | 장비 | *(TACT)* | Reset | SMD | 1 | CPU RESET | |
| — | 장비 | *(NOR Flash programmer)* | External / header | — | 1 | #16 기록 | 비트뱅 **없음** |

*[BOM.md](BOM.md)의 빵판·점퍼·SOP 어댑터·5 V half-can OSC는 본 PCB 목록에 **없음**.*
