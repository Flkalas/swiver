# 컴파일러 타깃 ISA·하드웨어 적합성 답변지 (v1.0)

**대상:** Swiver v1.0 breadboard CPU + software v0.1 macro ISA  
**목적:** 실물 하드웨어에서 구동되는 컴파일러(`plover_cc` 등) 구현 전, 시스템 구현자가 확인할 항목에 대한 **현행 스펙 기준 답변**  
**기준일:** 2026-06-24  
**관련:** [microcode-spec.md](../hardware/microcode-spec.md) · [calling-convention-v0.1.md](calling-convention-v0.1.md) · [software-roadmap.md](software-roadmap.md)

---

## 범례

| 기호 | 의미 |
|------|------|
| **예** | v1.0 하드웨어 + 패킹된 마이크로코드/매크로 ISA로 **실물에서** 직접 사용 가능 |
| **부분** | 하드웨어 자원은 있으나 ISA·데이터 경로가 불완전, 또는 소프트웨어 관례로만 대체 |
| **아니오** | v1.0 normative 경로에 없음 |
| **비실기(미패킹)** | opcode·시나리오에만 존재 — **빵판 실기와 별도** |

**판정 원칙:** 컴파일러 백엔드가 **`.sram.hex`로 내려 실제 CPU에서 실행**하는 것을 기준으로 한다. 비실기 전용 기능은 **아니오** 또는 **비실기(미패킹)**으로 표기한다.

---

## 1. 주소 지정 방식 (Addressing Modes)

| 평가 범주 | 시스템 구현자 대상 질문 | 컴파일러 구현 시 요구 근거 | v1.0 답변 | 근거·비고 |
|-----------|-------------------------|---------------------------|-----------|-----------|
| 주소 지정 | 베이스 레지스터와 오프셋을 결합한 **간접 주소 지정(Base+Offset)** 을 하드웨어 수준에서 지원합니까? | 구조체 멤버 접근, 배열 인덱싱, 스택 프레임 내 지역 변수 참조 시 포인터 연산 오버헤드 최소화 | **아니오** | `LDA`/`STA`는 **8비트 절대 주소** `[imm8]`만 ([microcode-spec.md](../hardware/microcode-spec.md) §LDA/STA). `STA16`은 **16비트 절대** 저장만. `[base+disp]` 형태 없음. 배열·프레임 포인터는 **다중 명령 시퀀스**로 에뮬레이션해야 함. |
| 주소 지정 | 레지스터가 가리키는 메모리 주소를 참조하여 값을 읽고 쓰는 **레지스터 간접(Register Indirect)** 명령어 셋이 구현되어 있습니까? | 컴파일된 코드가 런타임 동적 주소(포인터 역참조)에 접근 | **아니오** | `LDA [Rn]`, `STA [Rn]` 없음. 포인터는 RAM에 16비트로 저장 후 **절대 주소 로드/저장**으로 우회. |

---

## 2. 레지스터 아키텍처 (Register Architecture)

| 평가 범주 | 시스템 구현자 대상 질문 | 컴파일러 구현 시 요구 근거 | v1.0 답변 | 근거·비고 |
|-----------|-------------------------|---------------------------|-----------|-----------|
| 레지스터 | **16비트 포인터**를 담을 **전용 포인터 레지스터** 또는 **8비트 레지스터 쌍(Register Pair)** 이 존재합니까? | 8비트 데이터 버스에서 64 KiB 주소 공간 탐색·포인터 변수 할당 | **부분** | **PC·MBR**는 16비트(574+161)이나 **페치/버스 전용** — 프로그램이 일반 포인터로 쓸 수 없음 ([system-architecture.md](../hardware/system-architecture.md)). normative GPR **R0 only**; **R1/R2는 RAM**. 16비트 값은 **RAM 셀 2바이트** 또는 다중 `LDA`/`STA`/`STA16`로 처리. |
| 레지스터 | 누산기 외 **범용 레지스터 3~4개 이상**이 확보되어 있습니까? | 레지스터 스필링·메모리 접근 감소, 최적화된 코드 생성 | **부분** | CPLD **R0 (AC) only** ([cpld-system-controller.md](../hardware/cpld-system-controller.md)). **ADD** → **R0 ← R0 + imm**. **레지스터 간 복사**는 `LDA`/`STA` 또는 RAM temp (`0x10–0x1F` reserved). [calling-convention-v0.1.md](calling-convention-v0.1.md): R0=인자/반환; 스크래치=RAM. |

---

## 3. 스택 및 서브루틴 (Stack & Subroutines)

| 평가 범주 | 시스템 구현자 대상 질문 | 컴파일러 구현 시 요구 근거 | v1.0 답변 | 근거·비고 |
|-----------|-------------------------|---------------------------|-----------|-----------|
| 스택 | **16비트 하드웨어 SP**와 **PUSH/POP**, **CALL/RET** 명령이 구현되어 있습니까? | 복귀 주소 저장, 인자 전달, 호출 규약·컨텍스트 스위칭 | **부분** | **SP:** RAM 셀 **`$0E00`** (16-bit LE), Boot ROM이 초기값 기록 — **하드웨어 SP 레지스터 없음** ([software-memory-layout.md](software-memory-layout.md), [boot-jmp-handoff.md](../boot/boot-jmp-handoff.md)). **PUSH/POP:** 전용 opcode 없음. **CALL/RET:** CU return-stack assist ([microcode-spec.md](../hardware/microcode-spec.md) §2.3). **RP** @ `$0F00`; stack body `$F600+` ([calling-convention-v0.1.md](calling-convention-v0.1.md)). CU fit desk: [cpld-pipe-cu.md](../hardware/cpld-pipe-cu.md) §5.1. |
| 스택 | **SP 값**을 범용 레지스터로 복사하거나 **산술 연산**할 데이터 경로가 있습니까? | 프레임 포인터 설정, `SP+offset` 지역 변수 주소 | **부분** | `LDA`/`STA`로 **`$0E00`/`$0E01`** 읽기·쓰기 가능. **단일 명령 `ADD SP, imm`** 없음. 16비트 SP 증감은 **8비트 ALU 다중 스텝** 소프트웨어 다중 스텝으로 처리. FP = SP 복사본을 GPR·RAM에 유지하는 **소프트웨어 관례**로만 가능. |

---

## 4. 산술 및 논리 연산 (ALU & Logic)

| 평가 범주 | 시스템 구현자 대상 질문 | 컴파일러 구현 시 요구 근거 | v1.0 답변 | 근거·비고 |
|-----------|-------------------------|---------------------------|-----------|-----------|
| ALU | **캐리 플래그 반영 ADC/SBC** 명령을 지원합니까? | 16비트 포인터 산술·32비트 정수 소프트웨어 에뮬레이션 | **아니오** | `alu_sel`: **ADD** (cin=0), **SUB** (2의 보수, cin=1), **INC/DEC**만 ([alu-opcodes-timing.md](../hardware/alu-opcodes-timing.md)). **이전 캐리를 이어 받는 ADC/SBC** opcode 없음. 16비트 덧셈은 루프·다중 ADD+조건 분기로 구현 (`fib_to_200.pls` 등은 **VM fast** + `BCS`). |
| ALU | **비트 시프트·순환(Shift/Rotate)** 이 독립 명령으로 지원됩니까? | 배열 인덱스×2ⁿ, 비트마스킹 속도 | **아니오** | `alu_sel` 12개(NOP~CMP)에 SHL/SHR/ROL/ROR 없음. 곱셈/나눗셈·시프트는 **소프트웨어 루프** 또는 Forth 스택 연산. |

---

## 5. 제어 흐름 (Control Flow)

| 평가 범주 | 시스템 구현자 대상 질문 | 컴파일러 구현 시 요구 근거 | v1.0 답변 | 근거·비고 |
|-----------|-------------------------|---------------------------|-----------|-----------|
| 제어 | **Zero, Carry, Sign, Overflow** 개별 플래그 조건 분기가 완전히 지원됩니까? | `if`/`while`/`for` 등을 조건부 점프로 번역 | **부분** | **하드웨어 플래그:** **Z, C** 만 — **574 FLG** 래치 ([microcode-spec.md](../hardware/microcode-spec.md)). **Sign(N)·Overflow(V) 없음.** **조건 분기:** **`BEQ`** (Z) — 마이크로코드 패킹됨. **`BCS`** (C, unsigned ≥) — opcode·미패킹 상태. **`BNE`/`BLT`/`BGT` 등 없음** — `CMP`+`BEQ`/`JMP` 조합으로 일부 대체. 부호 있는 비교는 **추가 런타임 루틴** 필요. |

---

## 6. 요약 매트릭스

| 영역 | 컴파일러 관점 “쓸만함” 요구 | v1.0 종합 | 실물 Subset C 백엔드 영향 |
|------|---------------------------|-----------|---------------------------|
| Base+Offset | 예 | **아니오** | 배열·구조체·`local[n]` 코드 길이·사이클 증가 |
| Register Indirect | 예 | **아니오** | `*p` 역참조 불편 |
| 16비트 포인터 레지 | 예 | **부분** (PC/MBR 전용) | 포인터는 RAM·다중 명령 |
| GPR 4개 (할당 가능) | 예 | **부분** (R0 HW + RAM) | 고정 호출 규약·RAM temps |
| HW SP + PUSH/POP/CALL/RET | 예 | **부분** (CALL/RET packed; no PUSH/POP) |
| SP 산술 데이터 경로 | 예 | **부분** | FP·동적 프레임 = 소프트웨어 시퀀스 |
| ADC/SBC | 예 | **아니오** | 16/32비트 정수 = 긴 헬퍼 |
| Shift/Rotate | 예 | **아니오** | 인덱스 스케일링 = 루프 |
| Z/C/S/O 조건 분기 | 예 (최소 Z+부호/무부호) | **부분** (Z,C만) | `if (a<b)` 부호 비교 비용 큼 |

---

## 7. 언어 타깃별 판정

| 타깃 | v1.0으로 실물 컴파일 가능? | 비고 |
|------|---------------------------|------|
| Swiver Assembly (S1) | **예** | ISA 1:1 |
| Forth primitives (S3) | **예** (스택=RAM 관례) | HW PUSH 불필요 |
| Tiny C — `return` 상수만 (S5 smoke) | **예** | [codegen.py](../../plover_cc/codegen.py) |
| Subset C — 포인터·배열·다중 로컬 | **아니오** (우회만) | §1–§5 갭 다수 |
| 레지스터 할당 교육용 백엔드 | **아니오** | GPR ISA·3-address 부재 |

---

## 8. v1.0 → 컴파일러 친화 ISA 최소 확장 (권장 우선순위)

실물 Subset C를 “쓸만한” 수준으로 올리기 위한 **하드웨어·ISA** 후보. 디코드 방식(`hc154` vs `cw_direct`)과 독립적으로 **먼저** 고정할 항목.

| 순위 | 항목 | 효과 |
|------|------|------|
| 1 | `CALL`/`RET` — **문서 완료**; pipe CU fit → breadboard burn | 함수 호출 실물 경로 |
| 2 | `LDA16` / `LDA [abs16]` (간접 로드) | 포인터 역참조 |
| 3 | `LDA [R+imm8]` 또는 인덱스 레지 1개 | 배열·오프셋 |
| 4 | `PUSH R` / `POP R` (SP=RAM 셀 또는 HW SP) | 프롤로그 단순화 |
| 5 | operand 2바이트 + ALU에 Rs/Rd 필드 | 레지스터 할당·다항 연산 |
| 6 | `ADC`/`SBC` 또는 명시적 16비트 carry 체인 | 포인터·`int` 연산 |
| 7 | `SHR`/`SHL` (최소 1방향) | 인덱스 스케일 |
| 8 | `BNE` + 부호 비교용 N/V 또는 비교 루틴 ABI | 완전한 `if`/`while` |
