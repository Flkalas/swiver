# v1.0 breadboard — 보유·실구매 (패키지·어댑터)

**Normative architecture:** [../reference/hardware/system-architecture.md](../reference/hardware/system-architecture.md)  
**구매 목록:** [../reference/project/BOM.md](../reference/project/BOM.md)

본 문서는 **물리 패키지, 어댑터, 보유 수량**만 기록한다. 발주·쇼핑 Qty는 BOM을 따른다.

**발주 이력:** [purchase-devicesmart.md](purchase-devicesmart.md) (1차) · [purchase-2026-06-01-followup.md](purchase-2026-06-01-followup.md) (2·3차 + Ali 6월) · [purchase-2026-07-aliexpress.md](purchase-2026-07-aliexpress.md) (Ali 7월) · [purchase-2026-07-devicesmart.md](purchase-2026-07-devicesmart.md) (DS 7월) · [purchase-2026-08-devicesmart.md](purchase-2026-08-devicesmart.md) (DS 8/13)

---

## v1.0 breadboard (목표 구성)

CPLD **2×** `ATF1504AS-10JU44` + **2×** PLCC→DIP (#13); Flash PDIP 직결; SRAM SOP28×2; **2.000 MHz** `CLK_SYS`. **Dual CPLD / pipe CU.**

---

## 발주 누적 요약

| 주문 | 일자 | 판매처 | 비고 |
|------|------|--------|------|
| **1차** | ~2026-06-01 | 디바이스마트 | TTL·Flash·SRAM×1·LVC245×3·SOP28×4 등 — [purchase-devicesmart.md](purchase-devicesmart.md) |
| **2차 A** | 2026-06-01 | 디바이스마트 | ATF1504×1, 86/157/04/14, OSC 2M·1M |
| **2차 B** | 2026-06-01 | 디바이스마트 | IS62C256 ×1 (SRAM 2번째) |
| **3차 C** | 2026-06-02 | 디바이스마트 | 153×4, MAP slide×10, RESET tact×10 |
| **AliExpress** | 2026-06-01 | 다수 | PLCC×1, SOP28×10, 0.1 µF×100, FT232H, 74HC02×10 등 |
| **AliExpress** | 2026-07-01·03·06 | 다수 | SIP 33R×30, MicroSD, LVC125×5, PLCC×1 — [purchase-2026-07-aliexpress.md](purchase-2026-07-aliexpress.md) |
| **4차 D·E·F·G** | 2026-07-06·08·13 | 디바이스마트 | ATF1504×1, SIP, 소켓, MB-102×5, OSC 3.6864M, **74HC138×1** — [purchase-2026-07-devicesmart.md](purchase-2026-07-devicesmart.md) |
| **5차 H** | 2026-08-13 | 디바이스마트 | ATF1504×1 (thumb-handle mixed cart) — [purchase-2026-08-devicesmart.md](purchase-2026-08-devicesmart.md) |

누적: **ATF1504 ×3** · **PLCC ×2** · **74HC138 ×2** — 코어 BOM 수량 충족 (ATF 여유 1).

---

## 어댑터 역할

| BOM # | 어댑터 | 보유 (누적) | 장착 대상 / 비고 |
|-------|--------|-------------|------------------|
| **3** | SOP28↔DIP (SOP4-28Pin · 1.27mm) | **14** (1차 4 + Ali 10) | SRAM×2 · **LVC245도 가능** (24/28 패드, 4핀 비움) |
| **13** | PLCC-44→DIP | **2** (Sinstar + Upmall) | ATF1504 (#12)×2 |
| *(BOM 외)* | SIC-DIP 소켓 | 14×10 · 16×30 · 20×10 · 32×10 | DS 4차 · 재사용·보호용 |

Flash (#16)는 **PDIP-32** — 빵판에 **직결** (SIC-DIP-32 보유).

---

## 보유 MPN (구매 누적)

| BOM # | MPN | Package | Qty | 역할 / 비고 |
|-------|-----|---------|-----|-------------|
| 12 | ATF1504AS-10JU44 | PLCC-44 | **3** | 2차 A + DS 4차 D + DS 5차 H `2026081318371118368` (여유 1) |
| 13 | PLCC-44→DIP 어댑터 | — | **2** | Sinstar + Upmall `1121526644275950` |
| 16 | SST39SF010A-70-4C-PHE | PDIP-32 | **2** | 부트·program ROM (1차; BOM 1 · 여유 1) |
| 17 | IS62C256AL-45ULI-TR | SOP | **2** | 64 KB RAM (1차 1 + 2차 B 1) |
| — | SN74LVC8T245DWR | SOIC-24 (1.27mm) | **3** | 메일박스 · SOP4-28Pin에 실장 (4패드 미사용) |
| 8 | 74HC138N | DIP | **2** | CE tree (1차 + G `2026071307030217559`) |
| — | 74HC283N | DIP | **2** | ALU |
| — | 74HC153 | DIP | **8** | ALU (1차 4 + 주문 C 4) |
| — | 74HC157 | DIP | **8** | ALU·주소 (1차 5 + 2차 A 3) |
| — | 74HC574 | DIP | **7** | 래치 여유 |
| — | 74HC161 | DIP | **4** | PC (BOM 3 · 여유 1) |
| — | 74HC245 | DIP | **2** | 버스 (BOM 1 · 여유 1) |
| — | 74HC08 / 32 | DIP | **2** / **2** | CE glue |
| — | 74HC86 | DIP | **4** | 1차 2 + 2차 A 2 (현 ALU BOM 미사용 여유) |
| — | 74HC04 | DIP | **3** | 1차 1 + 2차 A 2 |
| — | 74HC14 | DIP | **2** | Schmitt (BOM 1 · 여유 1) |
| — | 74HC74 | DIP | **1** | 클록 분주 등 |
| — | 74HC595 | DIP | **3** | Flash 프로그래밍 보조 (Nano 비트뱅) |
| — | OSC 4M / 2M / 1M / **3.6864M** | half-can | **1** each | BOM `CLK_SYS` **2.000 MHz** (2M) · F=`2026071304421517554` |
| — | MAP slide (MSL-1C2P) | — | **10** | 주문 C · 조립 1 |
| — | RESET tact (ITS-1103) | — | **10** | 주문 C · 조립 1 |
| — | MB-102 830 | — | **9** | 1차 4 + DS E×5 · Ali kit 추가 가능 |
| — | 0.1 µF ceramic | — | **~130** | 1차 30 + Ali 100 |
| — | FT232H USB (TYPE-C) | — | **1** | Ali `1120935566415950` — CPLD JTAG/ISP (BOM 충족) |
| — | Arduino Nano 호환 | — | **1** | NOR Flash 비트뱅 (BOM 충족) |
| — | 74HC02N | DIP | **10** | Ali · BOM 외 실험용 |
| — | MicroSD 모듈 | — | **1** | Ali `1121522432045950` · BOM 외 |
| — | SN74LVC125ADR | SOP-14 | **5** | Ali `1121522432065950` · BOM 외 |
| — | 33Ω ×8 SIP-9 (9PIN) | SIP | **30** | Ali `1121478671585950` · 버스 댐핑 |
| — | 100Ω SIP-9 (9×101J) | SIP | **10** | DS 4차 |
| — | 220Ω SIP-9 (9×221J) | SIP | **10** | DS 4차 |
| — | 470Ω SIP-9 (9×471J) | SIP | **10** | DS 4차 · Bourns 4709 |
| — | SIC-DIP-14 / 16 / 20 / 32 | 소켓 | 10 / 30 / 10 / 10 | DS 4차 |

상세 단가·주문번호: 위 발주 문서.

---

## 재주문 (현행 BOM 대비)

코어 BOM 수량 부족 **없음** (발주 누적 기준).

LVC245용 전용 SOIC-24 어댑터 **불필요** — 보유 SOP4-28Pin (1.27mm)에 24핀만 사용.

ATF1504 · PLCC · 74HC138은 발주 누적 충족.

---

## ATF1504 dual CPLD I/O (desk)

See [cpld-dual-jtag.md](../reference/hardware/cpld-dual-jtag.md).

---

## Change log

| Date | Note |
|------|------|
| 2026-06-10 | Initial — v1.0 breadboard package matrix |
| 2026-07-13 | 아카이브 발주 문서 복원 · 구매 누적 Qty·재주문 반영 |
| 2026-07-13 | Ali 7월 추가 — PLCC·MicroSD·LVC125·SIP 33R×30 |
| 2026-07-13 | DS 4차 D `2026070621281618712` — ATF1504×2·SIP·소켓 |
| 2026-07-13 | DS 4차 E `2026070822324319438` (묶음) — MB-102×5 |
| 2026-07-13 | DS 4차 F `2026071304421517554` (묶음) — OSC 3.6864M |
| 2026-07-13 | DS 4차 G `2026071307030217559` (묶음) — 74HC138×1 |
| 2026-08-25 | DS 5차 H `2026081318371118368` — ATF1504×1 (여분, mixed cart) |
