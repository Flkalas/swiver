# Inventory (lab stock)

보유·실구매·패키지 확정. **구매할 목록(정본 BOM)은 여기 두지 않습니다.**

| Document | Role |
|----------|------|
| [parts-on-hand.md](parts-on-hand.md) | 보유 MPN · 어댑터 · 재주문 메모 |
| [purchase-devicesmart.md](purchase-devicesmart.md) | 디바이스마트 **1차** 주문 (아카이브 복원) |
| [purchase-2026-06-01-followup.md](purchase-2026-06-01-followup.md) | 디바이스마트 **2·3차** · AliExpress 6월 (아카이브 복원) |
| [purchase-2026-07-aliexpress.md](purchase-2026-07-aliexpress.md) | AliExpress **2026-07** 추가 (SIP·PLCC·MicroSD·LVC125) |
| [purchase-2026-07-devicesmart.md](purchase-2026-07-devicesmart.md) | 디바이스마트 **4차** D–G (ATF1504·SIP·소켓·MB-102·OSC·74HC138) |
| [purchase-2026-08-devicesmart.md](purchase-2026-08-devicesmart.md) | 디바이스마트 **5차** H (ATF1504×1 여분 · mixed cart) |
| Shopping list (Active) | [reference/project/BOM.md](../reference/project/BOM.md) |
| PCB 3.3 V shopping | [reference/project/BOM-3v3.md](../reference/project/BOM-3v3.md) |

보유 Qty 근거: [parts-on-hand.md](parts-on-hand.md) (발주 누적). BOM Qty: [BOM.md](../reference/project/BOM.md) (v1.0 breadboard 1세트).

---

## BOM ↔ 보유 대조

| 부품 | BOM | 보유 | Δ | 판정 |
|------|-----|------|---|------|
| 74HC283 | 2 | 2 | 0 | ✓ |
| 74HC153 | 8 | 8 | 0 | ✓ |
| 74HC157 | **4** | 8 | +4 | ✓ 여유 |
| 74HC574 | **4** | 7 | +3 | ✓ 여유 |
| 74HC138 | **2** | **2** | 0 | ✓ |
| 74HC08 | 2 | 2 | 0 | ✓ |
| 74HC32 | 2 | 2 | 0 | ✓ |
| 74HC161 | 3 | 4 | +1 | ✓ 여유 |
| ATF1504AS-10JU44 | **2** | **3** | +1 | ✓ 여유 |
| PLCC-44↔DIP adapter | **2** | **2** | 0 | ✓ |
| 74HC245 | 1 | 2 | +1 | ✓ 여유 |
| SST39SF010A-70-4C-PHE | 1 | 2 | +1 | ✓ 여유 |
| IS62C256AL-45ULI-TR | 2 | 2 | 0 | ✓ |
| SOP28↔DIP adapter | 2 | 14 | +12 | ✓ 여유 |
| 2.000 MHz oscillator | 1 | 1 (OSC 2M) | 0 | ✓ (4M·1M·3.6864M도 보유) |
| 74HC14 | 1 | 2 | +1 | ✓ 여유 |
| Breadboard power supply | 1 | 1 | 0 | ✓ |
| Breadboard | — | **9** (1차 4 + E×5) | — | ✓ |
| 0.6 mm 단선 와이어 | — | 6 m (1차) | — | ✓ |
| Tactile / pushbutton | 1 | 10 | +9 | ✓ |
| Slide / DIP switch (1극) | 1 | 10 | +9 | ✓ |
| 0.1 µF ceramic | — | ~130 | — | ✓ |
| 10 µF tantal / electrolytic | — | 10+10 | — | ✓ |
| 330 Ω ×8 SIP-9 (=**33 Ω**, EIA 330) | — | 1차 8pin×10 + Ali 9PIN×**30** | — | ✓ |
| 10 kΩ ×8 SIP-9 | — | 10 (Bourns 4708) | — | ✓ |
| 10 kΩ (axial) | — | 10 | — | ✓ |
| ATF1504 JTAG/ISP programmer | 1 | FT232H TYPE-C×1 | 0 | ✓ |
| NOR Flash programmer | 1 | Arduino Nano×1 + 74HC595×3 | 0 | ✓ (비트뱅) |

ATF1504 JTAG/ISP programmer BOM 항: AliExpress **FT232H** (FAR EAST ELECTRONICS, `1120935566415950`, 2026-06-01) — 실물 사진 [`photo_2026-07-06_01-27-43.jpg`](../cpld/tools/images/photo_2026-07-06_01-27-43.jpg) · [purchase-2026-06-01-followup.md](purchase-2026-06-01-followup.md).

NOR Flash programmer BOM 항: 별도 전용 기기 없음 — **Arduino Nano + 74HC595×3** 비트뱅으로 충족 ([purchase-devicesmart.md](purchase-devicesmart.md)).

PLCC-44↔DIP: 2026-06 Sinstar ×1 + 2026-07-06 Upmall ×1 (`1121526644275950`) — [purchase-2026-07-aliexpress.md](purchase-2026-07-aliexpress.md).

ATF1504 dual: DS 4차 D (`2026070621281618712`) · E MB-102×5 · F OSC 3.6864M · **G 74HC138×1** (`2026071307030217559`, 550원) — D–G **30,530원** — [purchase-2026-07-devicesmart.md](purchase-2026-07-devicesmart.md).

ATF1504 여분: DS 5차 H (`2026081318371118368`, 2026-08-13, VAT별 7,340원) — thumb-handle mixed cart · Swiver만 반영 — [purchase-2026-08-devicesmart.md](purchase-2026-08-devicesmart.md).

### 부족 요약 (발주 후보)

코어 BOM 대비 **수량 부족 없음** (발주 누적).

### BOM 외 보유 (참고)

코어 BOM에 없으나 실험·메일박스·구설계용으로 보유.

| MPN | 보유 | 비고 |
|-----|------|------|
| SN74LVC8T245DWR | 3 | 5 V↔3.3 V · SOP4-28Pin(1.27mm)에 실장 (4패드 비움) |
| SN74LVC125ADR | 5 | Ali `1121522432065950` · SOP-14 |
| MicroSD 모듈 | 1 | Ali `1121522432045950` |
| 100 / 220 / 470 Ω SIP-9 | 각 10 | DS 4차 |
| SIC-DIP-14/16/20/32 | 10/30/10/10 | DS 4차 |
| 74HC86 | 4 | 현 ALU BOM 미사용 |
| 74HC04 | 3 | 클록·실험 |
| 74HC74 | 1 | 분주 등 |
| 74HC02N | 10 | Ali · 실험 |

대조 기준일: **2026-08-25** (발주 문서 누적 vs 현행 BOM · 8월 DS 5차 H 포함).
