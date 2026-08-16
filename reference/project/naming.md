# Swiver — 프로젝트 이름

**Status:** Normative brand note  
**Audience:** 기여자, 외부 검토자, 에이전트

대외 브랜드명은 **Swiver**입니다. GitHub 원격은 [Flkalas/swiver](https://github.com/Flkalas/swiver)입니다. `plover_*` 패키지·포맷 식별자는 당분간 유지합니다 — [AGENTS.md](../../AGENTS.md) § Brand / package rename.

---

## 1. 이유

이전 브랜드 **Plover**는 검색·발견성에서 불리했습니다.

- OpenSteno **Plover**(속기 엔진) 등 동명 프로젝트가 SEO를 잠식함
- 구글에 이름만 검색하면 이 레포가 잘 보이지 않음
- 완전 조어에 가까운 **고유명사**를 원했으나, `Plover`는 실존 영어 단어(도요새과 조류)이기도 함

채택 기준은 절대적 유니크함이 아니라, **`이름` + `github`(또는 TTL/CPU/breadboard 등 관심사 키워드)** 검색 시 첫 페이지에 노출될 수 있으면 충분하다는 것이었습니다.

---

## 2. 과정

1. **Simpleover → Plover** — 초기 작업명 `Simpleover`를 축약해 `Plover`를 제안(아카이브 Gemini 세션, 2026-05). 우연히 영어 조류명과 일치함.
2. **충돌 인식** — 동명 대형 프로젝트·실존 단어로 검색 경쟁이 큼.
3. **후보 논의** — 조어·합성어·고유명사 톤을 검토. 제미니 세션의 SWIMS(흐르는 연산) 잔향과 2음절 발음을 살린 **Swiver**를 검토.
4. **채택** — `Swiver github` 및 관심사 결합 검색에서 초대형 동명 프로젝트가 없음을 확인하고 브랜드로 확정.

역사 원문: `archive/docs_archive.tar.gz` → `docs/archive/gemini/Gemini-_38.md` (이름 후보·Plover 평가).

---

## 3. 결론

| 항목 | 결정 |
|------|------|
| **대외·문서 브랜드** | **Swiver** |
| **GitHub 레포/원격 이름** | [Flkalas/swiver](https://github.com/Flkalas/swiver) |
| **패키지·도구·포맷** (`plover_asm`, `plover_cc`, `.PLR`, `PL-DOS` 등) | **점진 이전** — 해당 패키지를 손대는 작업 단위에서 `swiver_*` 등으로 함께 변경 ([AGENTS.md](../../AGENTS.md)) |
| **문서 파일 경로** (`plover-whitepaper.md`, `plover-asm.md` 등) | 패키지 이전과 맞춰 나중에; 이번 리브랜드에서는 **경로 유지** |

문서 본문의 프로젝트 호칭은 Swiver로 쓰고, 코드 식별자·파일명은 마이그레이션 전까지 `plover_*` / `plover-*.md`를 그대로 둡니다.
