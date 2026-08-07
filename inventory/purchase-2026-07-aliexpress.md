# AliExpress 추가 구매 (2026-07)

Swiver **dual CPLD / 보조 모듈** 보완.  
**보유·패키지 해석:** [parts-on-hand.md](parts-on-hand.md) · **현행 BOM:** [BOM.md](../reference/project/BOM.md)  
이전 AliExpress (2026-06-01): [purchase-2026-06-01-followup.md](purchase-2026-06-01-followup.md)

| 항목 | 내용 |
|------|------|
| 대상 | PLCC 어댑터 2번째 · MicroSD · LVC125 · **33Ω SIP-9** |
| 주문일 | **2026-07-01** · 2026-07-03 · 2026-07-06 |
| 결제 | Credit/Debit card (+ Bonus 1건) |

---

## 주문 목록

### `1121478671585950` — 33Ω SIP-9 네트워크 저항 (2026-07-01)

| 항목 | 내용 |
|------|------|
| 주문 | 2026-07-01 · 결제·출하 동시 · **구매** |
| 판매처 | QUANXINFA Store - Global Supplier Store |
| 품목 | DIP network resistor array · 옵션 **9PIN 33R** · **3** packs (목록 10PCS/pack → **30** pcs) |
| 표시가 / 실결제 | US $0.89×3 = $2.67 / **US $3.82** |
| BOM | 버스 댐핑 SIP ([BOM.md](../reference/project/BOM.md) `330 Ω ×8 SIP-9` — EIA **330**=**33 Ω**; 1차는 8pin×10) |

### `1121522432045950` — MicroSD 모듈 (2026-07-03)

| 항목 | 내용 |
|------|------|
| 주문 | 2026-07-03 · 결제 동시 · 출하 2026-07-04 · **구매** |
| 판매처 | HKHJW Hardware+ Store |
| 품목 | TF Micro SD Card Module (Mini SD · ARM/AVR · welding) ×1 |
| 표시가 / 실결제 | US $1.02 / **US $0.89** |
| BOM | 코어 BOM 외 (보조 스토리지) |

### `1121522432065950` — SN74LVC125A (2026-07-03)

| 항목 | 내용 |
|------|------|
| 주문 | 2026-07-03 · 결제 동시 · 출하 2026-07-04 · **구매** |
| 판매처 | shenzhenYida Store |
| 품목 | 옵션 **SN74LVC125ADR** (목록 5PCS · SOP-14) |
| 표시가 / 실결제 | US $1.49 / **US $1.27** |
| BOM | 코어 BOM 외 (버스 버퍼 · 레벨/구동 보조) |

### `1121526644275950` — PLCC-44→DIP-44 (2026-07-06)

| 항목 | 내용 |
|------|------|
| 주문 | 2026-07-06 · 결제 동시 · 출하 2026-07-07 · **구매** |
| 판매처 | Upmall Store |
| 품목 | PLCC44 Adapter Socket + PLCC Extractor (옵션 **PLCC44-DIP44**) ×1 |
| 표시가 / 실결제 | US $3.86 / **US $2.12** (Bonus) |
| BOM | PLCC-44↔DIP ×2 중 **2번째** — dual CPLD 장착 충족 |

**AliExpress 2026-07 실결제 합계:** US $3.82 + $0.89 + $1.27 + $2.12 = **US $8.10**

---

## 누적 영향 (vs 2026-06)

| MPN | 이전 | 본 주문 | 누적 | 비고 |
|-----|------|---------|------|------|
| PLCC-44→DIP | 1 (Sinstar) | +1 (Upmall) | **2** | BOM ✓ |
| MicroSD 모듈 | 0 | +1 | **1** | BOM 외 |
| SN74LVC125ADR | 0 | +5 (pack) | **5** | BOM 외 · SOP |
| 33Ω SIP-9 (9PIN) | 0 | +30 (3×10) | **30** | BOM 댐핑 · 1차 8pin×10과 별도 |

---

## 변경 이력

| 날짜 | 내용 |
|------|------|
| 2026-07-13 | 사용자 주문 영수증 반영 (Jul 3·6) |
| 2026-07-13 | Jul 1 SIP 33R×30 (`1121478671585950`) 추가 |
