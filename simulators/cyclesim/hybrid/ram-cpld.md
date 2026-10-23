# 새 RAM ISA의 CPLD 분할 — 18 IC

**2026-10-24 · 실험 결과.** [새 RAM ISA](../../../reference/hardware/ram-isa-experiment.md)의
74 전용 구성 **63 IC → 18 IC**. 45개, 71.43% 감소했다.
보유한 **ATF1504AS-10JU44 두 개와 ATF1502AS-10JU44 한 개**를 사용한다.
기존 v1.0 ISA/CU의 fit 결과로 적용하지 않는다.

## 실제로 남는 칩

| 기능 | 부품 | 수량 |
|---|---|---:|
| 외부 ALU | 74HC153×8 + 74HC283×2 + 74HC157×2 | 12 |
| CU·AC·플래그·데이터 버스 출력 | ATF1504AS | 1 |
| PC·X·주소 선택 | ATF1504AS | 1 |
| P 페이지 레지스터·메모리 디코더 | ATF1502AS | 1 |
| RAM | IS62C256AL | 2 |
| 프로그램 Flash | SST39SF010A | 1 |
| **합계** | **74HC 12 + CPLD 3 + 메모리 3** | **18** |

ALU를 CPLD에 넣지 않는다. 별도 제어 ROM, 외부 바이트 래치, PC 카운터, operand/writeback
MUX, 데이터 버스 244도 이 구성에는 없다. 그 기능을 위 세 CPLD에 배치했다.
발진기·외부 RESET/WAIT 신호원·부하 버퍼·mailbox MCU·수동부품은 이전 63개와 동일하게
제외한다. 18개는 **CPU 논리+메모리 구성**이며 주변회로까지 검증한 보드 전체 BOM은 아니다.

## 용량과 핀 — 실제 vendor fit 결과

세 블록 모두 PLCC44, JTAG ON, tPD 요청 10ns로 WinCUPL/FIT1504/FIT1502를 실행했다.
선택한 결과는 모두 `Design fits successfully`이고 아래 자원 수량도 정격 안이다.
MC 수는 이 실험의 해당 소스·도구 결과이며 일반적인 설계 예산이나 v1.0 정본 수치가 아니다.

| 블록 | MC 사용 | 일반 I/O 사용, JTAG 제외 | 전용 입력 사용 | 결과 |
|---|---:|---:|---:|---|
| CU 1504 | **43/64** | **28/28** | **4/4** | fits |
| 주소 1504 | **63/64** | **28/28** | **3/4** | fits |
| 페이지·디코더 1502 | **15/32** | **27/28** | **4/4** | fits |

**용량과 핀은 맞지만 여유가 작다.** 두 1504는 일반 I/O가 남지 않으며 주소부는 MC 하나만 남는다.
기능이나 핀 배치를 바꾸면 다시 fit해야 한다. 1502도 MC는 남지만 일반 I/O는 하나만 남는다.
fitter 원본의 `Total I/O pins used`는 JTAG 네 핀을 포함하므로 위 표보다 4 크다.
부품 구조의 정격은 [1504 데이터시트](https://ww1.microchip.com/downloads/en/DeviceDoc/ATF1504AS%28L%29-5V-64-Macrocell-CPLD-Data-Sheet-20006580A.pdf),
[1502 데이터시트](https://ww1.microchip.com/downloads/aemDocuments/documents/MPD/ProductDocuments/DataSheets/ATF1502AS-ATF1502ASL-5V-32-Macrocell-CPLD-Data-Sheet-20006619A.pdf)를 따른다.

fitter가 일반 입력의 초기 pin 제안을 재배치할 수 있다. **실제 배선은 `.pld`의 초기 제안보다
성공한 `.fit`의 최종 `Pin = signal` 표를 따른다.** 내보낸 `netlist.json`의
`signal_pad_numbers`와 보존 결과의 `signal_pads`에 그 최종 배치를 저장한다.
전원은 기능 핀 이름으로 표시하며 ALU·메모리의 물리 pad 번호와 PCB 배치는 이 출력의 범위 밖이다.

## 1502가 맡는 기능과 fit 과정

주소 1504에 PC/X/P/literal/IR과 주소 선택을 전부 넣는 첫 구성은 배치 전 **70 Logic Cell**로 실패했다.
P 8비트와 상위 주소 출력을 메모리 디코더가 있는 1502로 옮기면 주소부의 저장 상태를 줄일 수 있다.
그 뒤 공통 branch 조건을 명시적인 내부 노드로 분리해 실제 fit을 통과했다.
1502는 단순 추가 디코더가 아니라 **주소부가 수용되도록 상태와 출력 기능을 나누는 칩**이다.

선택 구성은 성공 문구, 정격 안의 자원 수량, 최종 핀 배치와 생성된 JED 파일을 함께 확인한다.
재현 코드는 `design_fits`와 `resource_report_consistent`가 모두 참인 블록만 합산한다.

## 바뀐 연결과 유지한 동작

- **CU**가 A, 플래그, opcode와 literal을 저장한다. 즉시값 실행 때 literal을 DB로,
  STORE 때 A를 DB로 내보낸다. ALU B는 DB에 직접 연결하므로 앞단 MUX가 필요 없다.
- **주소 1504**가 PC, X, opcode와 literal을 저장한다. opcode/literal의 일부 저장은
  CU와 중복되지만, 별도 8비트 칩 간 전송선 대신 공통 DB의 동일 fetch를 함께 캡처한다.
- **1502**가 P를 저장하고 Boot/Run ROM·RAM 두 뱅크·mailbox CE를 생성한다.
  LPI/LDP의 P 적재는 주소 1504에서 보낸 `PAGE_LOAD`로 제어한다.
- PC의 상위 바이트와 P 출력은 같은 주소선을 공유한다. T1/T3은 PC, T5는 P가 구동하고
  T0/T2/T4는 둘 다 해제한다. setup 단계에서는 메모리 OE/WE도 비활성이다.
  한 번의 메모리 접근에 유효한 주소·읽기 구간은 capture 단계의 한 클록이며 WAIT로 연장된다.
- ALU의 `SUB` 제어선은 분기 명령에서 taken 조건도 전달한다. 분기는 ALU 결과를 저장하지
  않으므로 같은 핀을 쓸 수 있다. 주소 1504는 분기 종류일 때만 이를 PC 적재 조건으로 사용한다.
- CU의 active-low OE/WE를 메모리에 직접 연결한다. Flash WE는 HIGH 고정이고, SRAM 쓰기는
  해당 CE와 WE가 모두 활성일 때만 수행한다. Boot ROM 영역 쓰기는 RAM을 변경하지 않는다.

모든 저장소는 같은 SYS 클록을 사용한다. 조합 로직으로 외부 래치 클록을 만들지 않는다.
명령별 메모리 접근·완료 시점, WAIT, 새 ISA의 소프트웨어 CALL/RET·스택 검사는 유지한다.

## 실행 검증과 경계

생성한 CUPL의 `.d`·`.ar`·`.oe` 식과 실제 12칩 ALU 모델을 연결해 실행했다.
PC 덧셈이나 opcode 실행을 Python의 CPU 명령 해석으로 대신하지 않는다.
메모리 소자는 기능 모델이며, 비교용 독립 ISA 해석기는 회로 제어에 사용하지 않는다.

| 프로그램 | 완료 명령 | CPLD tick | 74 전용 tick | 결과 |
|---|---:|---:|---:|---|
| 반복 Fibonacci(13) | 205 | 1,230 | 1,230 | 233 |
| RAM 포인터 페이지 경계 복사 | 64 | 384 | 384 | A0..A3 복사, 포인터 `$2102` |
| 재귀 Fibonacci(3), 검사 포함 | 684 | 4,104 | 4,104 | 2, RP `$F600` 복구 |

각 명령의 상태·메모리·접근 주소/값/순서를 74 모델 및 독립 해석기와 대조했다.
전 opcode×플래그, 산술·논리 경계, Boot/Run/MMIO, PC wrap, WAIT/HALT/reset,
스택 오류, ALU/PC 고장 주입, 상위 주소 driver 누락과 논리적 빈 구간을 테스트한다.
새 CPLD 후보 1,140개와 기존 RAM-ISA 74 후보 1,157개, **총 2,297개 테스트가 통과**했다.

**명령당 6tick은 그대로다.** CPLD를 넣었다고 이 프로그램의 tick 수가 줄지는 않는다.
native MIPS는 가정한 클록 MHz / 6이며, 실물의 최대 클록 향상은 아직 검증하지 않았다.

이 검증은 **vendor block fit + 연결된 소스 식의 기능 실행**이다. JED로 프로그래밍한 보드나
post-fit 지연 시뮬레이션은 아니다. 논리적 driver 빈 구간은 검사했지만 실제 OE/decode glitch,
RAM→ALU setup/hold, write strobe/주소 hold, 출력 부하·clock skew는 전기적 검증이 남는다.

## 재현과 산출물

저장소 루트에서:

```powershell
.\.venv\Scripts\python.exe -X utf8 -m simulators.cyclesim.hybrid.ram_cpld_measure
.\.venv\Scripts\python.exe -X utf8 -m pytest -q simulators/cyclesim/tests/test_ram_cpld.py
```

첫 명령은 설치된 `cpld\tools\wincupl-ii`로 후보들을 fit하고 선택한 세 블록의 조합을 실행한다.
실패 비교 후보도 출력하지만 선택한 블록의 fit·자원 일관성·프로그램 검사가 실패하면 중단한다.
출력은 `simulators\cyclesim\build\ram-cpld\comparison.json`, `netlist.json`이며,
PLD/TT2/FIT/JED는 `simulators\cyclesim\build\hybrid-partition\ramcu`, `ramaddrfit`,
`rampagedec` 각각에 저장된다.

[ram-cpld-evidence.json](ram-cpld-evidence.json)에 수량·자원·최종 핀 배치·프로그램 실행 결과와
소스·도구·산출물 SHA-256을 보존한다. [ram_cpld.py](ram_cpld.py)는 CUPL 생성,
[ram_cpld_cpu.py](ram_cpld_cpu.py)는 연결 실행, [ram_cpld_measure.py](ram_cpld_measure.py)는 재현·집계를 담당한다.
