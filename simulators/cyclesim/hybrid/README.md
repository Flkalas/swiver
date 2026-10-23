# 공통 8비트 hi/lo 버스 하이브리드 비교 모델

대화의 결정·정정·실험 결과와 ROM 없는 FSM 축소 논의는
[2026-10-23 연구노트](research-notes-2026-10-23.md)에 구간별로 정리했다.
후속 [기가트론 비교 연구](gigatron-lessons-2026-10-23.md)는 적용 가능한 제어·부품 선택과
현재 PC/RP 증감 전송 비용을 원본 회로 및 로컬 실행으로 확인한다.

## INC/DEC ALU 제어 연결 — 첫 구현 단계

`incdec.IncDecCpu`는 기존 12칩 ALU의 **INC/DEC를 실제 부품 연결로 구동하는 실행 후보**다.
아래 절들의 ADD/SUB 전용 `HybridCpu`와 ROM/CUPL fit 조합은 이전 비교 기준으로 유지한다.
이번 단계에서는 새 ALU 제어와 증감 전송을 구현했으며, 공통 절차형 FSM이나 새 CUPL
핀 배치·fit까지 완료한 것은 아니다. 이 후보에 과거 32 IC fit 결과를 적용하지 않는다.

- 칩 구성: **153×8 + 283×2 + 157×2 = 12**, 추가 ALU 패키지 없음.
- `ALU_CIN`, `ALU_BCTRL_LOW`(bctrl0/1), `ALU_BCTRL_HIGH`(bctrl2/3)를 독립 구동한다.
- PC/RP의 ±1은 `ALU→RESULT→대상 바이트`로 실행하여 `MBR ← 1`을 없앤다.
- carry/borrow가 있으면 상위 바이트도 INC/DEC로 처리한다. 16비트 wrap을 유지한다.
- RP −2의 하위 바이트는 MBR=2와 SUB를 유지하고, 상위 borrow만 DEC로 처리한다.
- RESULT 캡처와 공유 버스 전송, 4-phase hold 검사, 명령 플래그의 갱신 시점은 유지한다.

| 연산 | CIN | bctrl0/1 | bctrl2/3 |
|---|---:|---:|---:|
| ADD | 0 | 0 | 1 |
| SUB | 1 | 1 | 0 |
| INC | 1 | 0 | 0 |
| DEC | 0 | 1 | 1 |

제어선은 기존 SUB/SUB_N 두 개에서 독립 세 개로 늘어난다. 현재 `tblaux` 핀을 그대로
사용하는 배치는 아니므로 향후 CU 분할에서 한 신호를 추가 배정하거나 다시 인코딩해야 한다.
제어는 현재 Python 시퀀서가 구동하며, ALU 결과는 74 부품 진리표로 계산한다.

### 실제 실행 비교

WAIT 없는 바이트 버스 모델, 제어 ROM 읽기 제외. 두 후보 각각을 기준 `CpuM3b`와 비교하고,
모든 명령 완료 상태·메모리 내용·접근 주소/값/순서를 확인했다.

| 프로그램 | 이전 tick | INC/DEC tick | tick 감소 | 가정 2 MHz native MIPS |
|---|---:|---:|---:|---:|
| 반복 Fibonacci → 233 | 10,292 | 8,920 | 13.33% | 0.03565 |
| 재귀 Fibonacci(3) | 7,568 | 6,604 | 12.74% | 0.03210 |
| 재귀 Fibonacci(8) | 114,160 | 99,548 | 12.80% | 0.03279 |
| ADD 256회 | 14,372 | 12,316 | 14.31% | 0.04157 |

이는 실행된 후보의 tick 감소다. 클록 향상이나 실측 보드 MIPS를 뜻하지 않는다.
새 후보 테스트는 모든 opcode×두 플래그 조합, PC wrap, RP 경계·오류,
carry/borrow·MBR 보존·플래그 보존, Boot/Run/MMIO, 재귀·WAIT 및 ALU 고장 전파를 확인한다.
새 후보의 550개 테스트와 공용 netlist 4개 테스트가 통과했다.
기존 하이브리드·CUPL·74 CPU·ALU 회귀 2,542개도 통과하여 이번 확인은 총 3,096개다.

```powershell
.\.venv\Scripts\python.exe -X utf8 -m simulators.cyclesim.hybrid.incdec
.\.venv\Scripts\python.exe -X utf8 -m pytest -q simulators/cyclesim/tests/test_hybrid_incdec.py
```

요약과 소스 해시는 [incdec-evidence.json](incdec-evidence.json)에 보존한다.
재현 출력 `simulators\cyclesim\build\hybrid\incdec-comparison.json`에는
12칩의 변경된 기능 핀 연결표도 포함된다. CPLD pad와 전기적 타이밍 검증은 포함하지 않는다.

## 이전 ADD/SUB 전용 후보

ATF1504 **2개**를 기본으로, 보유 ATF1502를 메모리 디코더로 추가하는 실험이다.
현재 정본의 SYS 스케줄과 배선 사양을 교체하지 않는다. **ISA 결과와 메모리 접근
순서는 유지하지만, 전송용 마이크로클록이 추가되는 후보**다.

## 실행과 재현

저장소 루트에서:

```powershell
.\.venv\Scripts\python.exe -X utf8 -m simulators.cyclesim.hybrid.fit_blocks
.\.venv\Scripts\python.exe -X utf8 -m simulators.cyclesim.hybrid.fit_cu
.\.venv\Scripts\python.exe -X utf8 -m simulators.cyclesim.hybrid.compare
.\.venv\Scripts\python.exe -X utf8 -m pytest -q simulators/cyclesim/tests/test_hybrid_cpu.py
```

첫 명령은 설치된 `cpld\tools\wincupl-ii`를 사용한다. 아카이브 HDL을 복원하지 않고
DP·디코더 CUPL을 현재 모델에서 생성한다. 출력은 gitignored
`simulators\cyclesim\build\hybrid-fit`에 PLD/TT2/JED/fit 로그와 `summary.json`,
`simulators\cyclesim\build\hybrid`에 `comparison.json`으로 저장한다.
소스 해시가 다르면 예전 fit 결과를 비교 보고서에 합치지 않는다.

## 실제로 바꾼 데이터 경로

- DP 저장 상태: R0 8비트 + PC 16비트 + 임시 RP 16비트 = **40비트**.
- DP는 선택한 바이트를 ALU A와 공통 DBUS로 출력한다. 16비트 주소 출력은 없다.
- PC/RP 증감은 **기존 12칩 ALU**를 바이트별로 재사용한다. 별도 16비트 가산기나
  Python의 PC/RP 정수 덧셈으로 실행하지 않는다.
- 주소 low/high는 DBUS로 전송해 외부 574 두 개에 저장한다. 주소를 유지하면서
  같은 DBUS로 메모리 데이터를 읽고 쓴다.
- TMP low/high 두 래치는 분기 대상과 RET 복귀 주소를 재사용한다. CALL target을
  보존하는 동안 반환 PC는 DP에 남아 있으며, RP는 별도 DP 상태에 저장한다.
- MBR 574 하나는 ALU B 입력이다. 내부 증감이 MBR을 덮어쓰므로 operand fetch
  전에 PC 증가를 끝내고, 주소 래치가 그동안 원래 fetch 주소를 유지한다.
- **RESULT 574 하나**가 ALU 결과를 잡은 뒤 DBUS를 구동한다. 직접 ALU→R0 쓰기는
  capture 직후 ALU A가 바뀌어 hold 중 소스가 달라지므로 사용하지 않는다.
  이 래치가 버스 OE도 맡아 ALU용 245를 별도로 세지 않는다.

574는 enable/reset이 있다고 가정하지 않는다. 각 적재는 CU의 등록된 클록 펄스로
setup → capture → hold → release **4 tick**을 소비한다. 입력 유지 MUX를 숨기지
않으며, 조합 논리로 클록을 단순 AND하지 않는다. 아날로그 setup/hold·skew와
전원 투입 reset은 여전히 실물 검증 대상이다.

## 생성된 부품 수

| 기능 | ATF1504×2 | ATF1504×2 + ATF1502×1 |
|---|---:|---:|
| ALU: 153×8 + 283×2 + 157×2 | 12 | 12 |
| 574: 주소×2, TMP×2, MBR, RESULT | 6 | 6 |
| 클록·리셋 정형 74HC14 | 1 | 1 |
| CU/DP ATF1504 | 2 | 2 |
| 메모리 선택 | 10개 74HC | 1개 ATF1502 |
| SRAM×2 + Flash×1 | 3 | 3 |
| **IC 합계** | **34** | **25** |
| 별도 발진기 모듈 포함 | **35** | **26** |

수량은 `hardware.manifest()`의 실제 후보 목록에서 계산한다. 두 칩 기본안의
디코더는 **04×3 + 08×6 + 32×1**로 생성·실행한 gate-only 회로다. 기존 138 BOM을
그대로 더한 값이나 최소 디코더 수량이 아니다. 1502안은 같은 디코드식을 통합한다.
어댑터·전원·수동부품·메일박스 코프로세서는 위 IC 합계에서 제외한다.

기록된 재고 기준 1502안의 IC 수량은 모두 보유 범위다. 574는 7개 중 6개를 사용한다.
PLCC44 어댑터는 2개뿐이므로 **1502 장착용 1개가 추가로 필요**하다.
34개 기본안은 HC08 6개가 필요해 보유 2개보다 4개 많다.

## 핀과 fit 근거

| 블록 | 일반 I/O 사용 / JTAG 유지 시 예산 | 전용 입력 | 확인 |
|---|---:|---|---|
| CU 1504 | **27 / 28** | CLK, RESET, WAIT | 직접 전개 FSM의 CUPL 컴파일 성공, **Design does not fit** |
| DP 1504 | **21 / 28** | CLK, RESET | 생성한 40비트 bank + ALU A/DBUS mux가 **Design fits successfully** |
| 디코더 1502 | **23 / 28** | 없음 | 생성한 메모리 디코드가 **Design fits successfully** |

DP의 21핀 = DBUS 8 + ALU A 8 + 선택 3 + WE 1 + OE 1.
CU의 27핀 = DBUS 8 + DP 제어 5 + 래치 클록 6 + TMP OE 2 + SUB/SUB_N 2 +
RESULT OE 1 + MEM_RD/MEM_WR 2 + ALU carry 1.
디코더의 23핀 = 주소 A2..A15 14 + MAP 1 + RD/WR 2 + CE 4 + OE/WE 2.

WinCUPL compiler와 FIT1504/FIT1502에 **PLCC44, JTAG ON, tPD 요청 10ns**를 지정했다.
이는 칩 내부 블록 fit 근거이며 전체 CPU 2MHz 동작 합격이나 보드 타이밍 근거가 아니다.
관측 로그와 소스 해시는 [block-fit-evidence.json](block-fit-evidence.json)에 보관했다.
제품의 MC 정격과 JTAG 핀 공유는
[1504 데이터시트](https://ww1.microchip.com/downloads/en/DeviceDoc/ATF1504AS%28L%29-5V-64-Macrocell-CPLD-Data-Sheet-20006580A.pdf),
[1502 데이터시트](https://ww1.microchip.com/downloads/aemDocuments/documents/MPD/ProductDocuments/DataSheets/ATF1502AS-ATF1502ASL-5V-32-Macrocell-CPLD-Data-Sheet-20006619A.pdf)를 따른다.

**CU 직접 구현의 첫 fit 결과는 실패다.** `cu_fsm.py`에서 공통 suffix를 공유하는
명시적 전송 FSM과 CUPL을 생성했다. 292개 전송 상태에 9비트 상태 레지스터와
2비트 전송 phase가 필요하다. WinCUPL 컴파일은 성공했지만 FIT1504는 logic doubling도
시도한 뒤 **`Design does not fit` (exit 402)** 을 반환했다.

실패 보고서는 배치 전 **251 Logic Cell**로 중단했다고 기록한다. 이는 성공한 배치의
사용 MC 수나 최적화된 구현의 최소 MC 수가 아니다. 실패 보고서 하단의 `1/64`는
중단 후 불완전 배치 통계이므로 CU 사용량으로 읽으면 안 된다.
기존 **58~70 MC / 6비트 상태 주소는 사전 추정치였으며 이 구현으로 확인되지 않았다.**
따라서 위 25개/34개는 여전히 CU 한 칩 수용을 전제로 한 후보 수량이며, 현재 구현으로
동작 가능한 완성 하드웨어 수량으로 확정할 수 없다.

`fit_cu`는 실패 시 종료 코드 1을 반환하고 `build/hybrid-cu-fit`에 생성 소스와 로그를
남긴다. 재현 근거는 [cu-fit-evidence.json](cu-fit-evidence.json)에 보관한다.
전송 FSM의 명령 결과·메모리 순서는 기준 CPU와 비교했지만, 생성 CUPL의 핀 단위
시뮬레이션과 post-fit 검증은 수행하지 않았다. reset-vector 부팅도 기존 후보처럼
미구현이다. 이 실패는 직접 전개 방식에 대한 결과이며, ISA 자체의 수용 불가능 증명이 아니다.

### 스택 검사 분리 실험

`python -m simulators.cyclesim.hybrid.partition_probe`는 원본 후보를 유지하면서
스택 검사를 DP에 통합한 별도 후보를 생성·피팅한다. RP 하위 바이트가 이미 DP에
있으므로 CU의 odd/above/equal/zero 기억 비트를 없애고, DP가 RP_LO와 DBUS의
상위 바이트를 직접 비교한다. CU는 검사 enable과 CALL/RET 구분을 보내고,
DP는 sticky fault를 CU 전용 입력 44번으로 돌려준다. CU 출력 핀을 확보하기 위해
SUB 반전 출력도 DP로 옮긴다. 새로운 IC를 추가하는 실험은 아니다.

| 블록 | 원본 | 검사 분리 후 | 결과 |
|---|---:|---:|---|
| DP | 57/64 MC | **61/64 MC** | 실제 Design fits |
| DP 일반 I/O (JTAG 제외) | 20/28 | **25/28** | 전용 입력 3/4도 사용 |
| CU 배치 전 논리 셀 | 251 | **239** | 여전히 Design does not fit |
| CU 핀 예산 | 일반 27, 전용 3 | 일반 **28**, 전용 **4** | 실패로 실제 CU 배치 미확정 |

실험 결과는 [partition-fit-evidence.json](partition-fit-evidence.json)에 기록한다.
생성된 검사 논리식은 모든 65,536개 RP × CALL/RET에 대해 독립적인 범위 검사와
비교한다. 핀 단위 통합·타이밍 검증은 별도다.

이 분리만으로 CU가 수용되지는 않는다. 직접 전개 FSM의 292개 상태는 서로 다른
전송 43종류를 반복한다. 특히 PC 증감 시퀀스가 호출 위치별로 복제되어 있다.
큰 축소 대상은 **다음 상태 선택과 전송 제어표**다. 공통 마이크로시퀀스와 복귀 상태로
재구성하거나 해당 표를 제어 ROM으로 옮기는 후보가 이에 해당한다. ROM 후보는
주소·데이터·제어 핀과 추가 래치까지 설계·피팅하지 않았으므로 칩 수나 fit을 확정하지 않는다.

## 실행 검증과 속도

289개 테스트: 모든 opcode 바이트, CALL/RET 경계·carry·잘못된 RP, PC wrap,
Boot/Run·MMIO·RAM 실행, WAIT 삽입, ALU 고장 전파, 주소 래치 유지,
모든 메모리 디코드 주소 조합을 확인했다. 기존 `CpuM3b`와 명령 완료 상태와
**메모리 읽기/쓰기의 주소·값·순서 전체**를 비교한다. SYS별 trace 일치를 주장하지 않는다.

| 프로그램 | 후보 tick | 기존 SYS | 가정 2MHz native MIPS |
|---|---:|---:|---:|
| 반복 Fibonacci → 233 | 10,292 | 504 | 0.0309 |
| 재귀 Fibonacci(3) | 7,568 | 379 | 0.0280 |
| 재귀 Fibonacci(8) | 114,160 | 5,689 | 0.0286 |
| ADD 256회 | 14,372 | 770 | 0.0356 |

분자는 HALT를 제외한 명령 수, 분모는 HALT까지 모든 후보 tick이다. 2MHz는 가정이다.
이 첫 구현은 배선·상태 수 절감을 우선해 매 전송에 네 phase를 사용하는 느린 후보다.
이 수치를 기존 0.6 MIPS와 혼용하지 않는다. 초기 PC·레지스터 값은 테스트 fixture이고,
reset-vector를 실제 버스로 읽는 초기화 시퀀스는 이 후보에서 아직 구현하지 않았다.

## 이전 탐색 기록 — 미채택 CPLD ALU 실험

**아래 CPLD ALU 후보는 사용자의 74 ALU 유지 조건에 따라 채택하지 않는다.**
현재 조건에 맞는 fit 조합은 다음 절의 외부 래치 + 74 ALU 구성이다.

인터넷 사례 수집 대신 `python -m simulators.cyclesim.hybrid.local_search`로
14개 블록 후보의 CUPL 생성·컴파일·실제 fit을 반복한다. 현재 ISA와 공통 DBUS를
유지하며 레지스터 수, ALU 통합, 제어 ROM, 스택 검사 위치, 제어 출력 방식을 바꾼다.
결과는 [local-search-evidence.json](local-search-evidence.json)에 보관했다.
**완성 CPU를 검증한 조합이나 전역 최소 칩 수를 찾았다는 뜻은 아니다.**

단순 8비트 저장을 외부 74HC574로 분리하는 방향이 유효하다. 기존 후보에서도
ADDR_LO/HI, MBR, TMP_LO/HI, RESULT의 6바이트는 이미 외부 574다.
새 후보는 R0/PC_LO/PC_HI/RP_LO/RP_HI까지 외부로 빼고, DBUS를 ALU A에
직접 연결한다. B는 기존 MBR, Y는 기존 RESULT 래치에 연결한다.
ALU 계산 중 선택한 외부 레지스터가 DBUS를 구동해야 하므로 기존 DP OE 조건도
바꿔야 한다. 이 외부 bank의 전체 핀 시뮬레이션은 아직 수행하지 않았다.

| 실제 피팅한 블록 | 장치 | 보고된 MC | 일반 I/O / 28 | 전용 입력 / 4 |
|---|---|---:|---:|---:|
| 레지스터 2바이트 + ALU | ATF1504 | 63/64 | 28 | 4 |
| 레지스터 없는 ADD/SUB ALU | ATF1504 | 17/64 | 25 | 1 |
| 레지스터 없는 ADD/SUB ALU | ATF1502 | **17/32** | **25** | **1** |
| 기존 5바이트 bank + 스택 검사, SUB 반전 제외 | ATF1504 | 60/64 | 23 | 3 |
| ROM 제어 출력 + 검사 enable/종류 | ATF1502 | 32/32 | 27 | 3 |

모든 결과는 PLCC44, JTAG ON이다. 외부 bank ALU는 XOR_Synthesis ON으로
실제 `Design fits successfully`를 받았다. ADD/SUB의 모든 131,072개 입력 조합에
대해 생성 CUPL 논리식을 독립적인 정수 연산과 비교했다. 이는 post-fit 검증은 아니다.
ALU를 1502에 넣으면 1504 두 개를 제어용으로 재배치할 수 있으나, 그 전체 조합의
제어·디코드·핀 연결을 완성했다고 주장하지 않는다.

외부 bank는 저장용 574 **5개**를 추가한다. 공통 DBUS를 사용하므로 별도 ALU A
8선 묶음은 없어지지만, 각 레지스터의 클록/OE 선택과 부하가 생긴다. 선택 신호를
그대로 확장하려면 쓰기/읽기용 외부 디코더도 필요하다. 따라서 MC 절감만으로
총 칩 수나 배선 길이가 줄었다고 판정하지 않는다. 단순 저장은 외부 IC, 연산과
제어는 CPLD로 나누는 후보를 비교 대상으로 삼는다.

제어 ROM 후보는 292개 전송 상태를 2 KiB 이미지에 저장하며, 전송마다 4바이트를
읽는다. CPU 메모리 주소를 덮어쓰지 않도록 **전용 ROM 주소 11선**을 추가하고
DBUS 8선을 공유한다. 명령 완료 상태와 메모리 접근 순서는 540개 사례에서 기준
CPU와 일치했다. 생성한 CU/출력 디코더의 핀 단위 통합 검증은 별도다.

일부 CU와 3/4바이트 통합 ALU 후보는 fitter가 성공을 반환하면서 통계는 **65/64**로
표시했다. MC56 행에 TDO와 사용자 buried node가 함께 기록되어 있지만, 이것만으로
통계 오류라고 확정하지 않았다. `resource_report_consistent=false`로 보존하고
완전히 검증된 조합에 넣지 않는다. 단순 ROM CU는 grouping 실패, 중복 차단 조건을
줄인 CU는 fitter 성공까지 진행했다. 실패 보고서의 불완전 MC 통계도 사용량으로
집계하지 않는다.

관련 네 pytest 파일에서 **1,372개 테스트가 통과**했다. reset-vector 부팅, post-fit
시뮬레이션, 실제 보드 클록/hold 타이밍은 이 결과에 포함하지 않는다.


## 74 ALU 유지: 세 CPLD가 모두 fit되는 외부 래치 구성

`external_partition.py`는 **기존 12-chip 74 ALU를 그대로 유지**하고, 단순 저장
R0/PC_LO/PC_HI/RP_LO/RP_HI를 외부 574로 옮긴다. 기존 여섯 래치를 합쳐
574는 11개다. DBUS가 ALU A에도 연결되며, ALU 계산 동안 선택한 레지스터가
DBUS를 구동한다. RESULT는 ALU Y를 별도로 받아 다음 전송에서 DBUS에 출력한다.
공통 8비트 hi/lo 전송과 기존 ISA·비중첩 실행을 유지한다.

| 실제 조합 | 역할 | MC | 일반 I/O / 28 | 전용 입력 / 4 |
|---|---|---:|---:|---:|
| ATF1504 `extseq` | 제어 ROM 주소·다음 상태·opcode 분기·WAIT·HALT | **55/64** | **27** | **4** |
| ATF1504 `tblaux` | 상수 DBUS·플래그·스택 검사·메모리 쓰기 보호·SUB/OE | **53/64** | **28** | **4** |
| ATF1502 `extctrl` | 11개 래치의 클록과 레지스터 bank OE | **27/32** | **24** | **3** |

세 장치 모두 **PLCC44, JTAG ON, 실제 Design fits successfully**다. 이전 65/64
통계 후보를 재사용하지 않는다. 1502는 bank용 클록 5개, OE 5개, 기존 래치 클록
6개를 직접 출력하므로 외부 bank 선택 디코더가 필요하지 않다. AUX가 TMP/RESULT
OE를 맡는다. 실제 fitter pad 번호는 [external-wiring.json](external-wiring.json)에 있다.

### IC 수량과 두 조합

| 부품 묶음 | 수량 |
|---|---:|
| 74 ALU: 153×8 + 283×2 + 157×2 | 12 |
| 74HC574 저장 래치 | 11 |
| ATF1504×2 + ATF1502×1 | 3 |
| 프로그램 Flash + SRAM×2 | 3 |
| 제어 ROM | 1 |
| 메모리 디코드 테이블 ROM | 1 |
| 74HC14: 클록/리셋 조건화 및 RD 반전 | 1 |
| **합계** | **32 IC** |

발진기 모듈 1개, 어댑터·수동부품·메일박스 코프로세서는 별도다. 전역 최소나
재고만으로 제작 가능하다는 주장은 아니다. 프로그램 Flash와 별개로 제어 ROM과
디코드 ROM이 필요하며, 이 manifest에서는 세 ROM 모두 SST39SF010A로 배정한다.

메모리 디코더를 기존 74 gate-only 회로 10개로 유지하는 조합도 `extseq + extaux +
extctrl`에서 모두 fit된다. AUX는 52/64 MC, 일반 I/O 27핀이고 **총 41 IC**다.
디코드 ROM 조합은 여기서 9 IC를 줄인다. 25개였던 과거 후보는 CU fit 실패 상태였으므로
이 32개와 동등한 검증 수준의 완성 구성으로 비교하지 않는다.

제어 ROM은 2 KiB, 전용 주소선은 uPC 9 + phase 2 = 11선이며 DBUS를 공유한다.
디코드 ROM은 주소 A2..A15 + MAP의 15선을 입력으로 받아 32 KiB 표에서
RAM0/RAM1/program-ROM/mailbox CE 네 개를 출력한다. A0/A1은 디코드에 불필요하다.
ROM 테이블이 WE를 직접 만들지 않고 **AUX의 `wen_n = !(wr & romn)`**이 실제 쓰기
구간에서만 허용한다. MEM_OE_N은 HC14가 RD를 반전한다. 이로써 주소 변경 중
ROM 출력 변동만으로 WE가 활성화되지 않는다. 아날로그 글리치/hold 검증은 별도다.

신호 연결표에는 **121개 신호 net, 524개 기능 핀 접점**이 있다. 이는 필요한 점퍼선
개수나 길이가 아니다. DBUS 공유로 ALU A 전용 8선은 없어지지만, 래치 클록/OE와
ROM 주소선 및 fan-out이 생기므로 전체 배선이 감소했다고 단정하지 않는다.

### 실제 검증 범위와 재현

`cupl_model.py`는 생성된 세 CUPL 소스의 논리식을 읽고, 각 클록에서 모든 D 식을
동시에 평가한 뒤 외부 574의 상승 에지 캡처를 수행한다. Python Transfer 실행을
호출하지 않는다. 74 ALU는 기존 패키지 회로 모델을 사용한다. 각 settle에서 DBUS
다중 구동과 캡처 전후 값 변화도 검사한다.

- **540개** opcode/flag·WAIT·stack·PC wrap·재귀·Boot/Run 사례에서 명령 완료 상태와
  메모리 접근 주소·값·순서가 기준 CPU와 일치했다.
- **10개 추가 검사**에서 테이블 ROM 통합 실행, 전체 주소/모드 디코드, ROM 쓰기 보호,
  HALT/스택 오류 뒤 정지, ALU 고장 전파, fixture 재초기화, 실제 pad/연결표를 확인했다.
- 전원 투입 상태는 시험 fixture다. **reset-vector 부팅은 아직 미구현**이며,
  post-fit 시뮬레이션과 실물 타이밍/동작 클록은 아직 검증하지 않았다.
  따라서 확인된 것은 **전체 기능 배분의 fit와 pre-fit 클록 에지 모델**이다.

```powershell
.\.venv\Scripts\python.exe -m simulators.cyclesim.hybrid.external_partition
.\.venv\Scripts\python.exe -m simulators.cyclesim.hybrid.external_wiring
.\.venv\Scripts\python.exe -m pytest simulators/cyclesim/tests/test_hybrid_cupl.py -q
```

생성 PLD/JEDEC/fit 보고서/ROM 이미지는 `simulators\cyclesim\build\hybrid-partition`에
저장한다. 소스·도구·보고서·JEDEC 해시와 핀 배치는
[external-fit-evidence.json](external-fit-evidence.json), 기능 연결표는
[external-wiring.json](external-wiring.json)에 보존한다.


## ATF1502 제거 비교: 필수 여부와 실제 절감 효과

**1502 자체는 기능상 필수는 아니다.** 현재 역할은 조합 디코드만이 아니라
11개 래치 클록 + bank OE 5개를 클록에 맞춰 출력하는 것이다. 이를 다른 부품으로
대체할 수 있다. 다만 현재 두 1504는 일반 I/O를 27/28, 28/28 사용하므로,
16개 출력을 그대로 두 칩에 옮길 여유는 없다. 인코딩·기능 분할까지 바꾼 설계의
불가능성이나 최소 칩 수를 증명한 것은 아니다.

`control_ablation.py`에서 실제 제거 후보 두 개를 만들었다. 먼저 16비트를 직접
출력하는 ROM×2 + 273×2 + 04×1로 대체했고, 배선을 줄이기 위해 아래 인코딩형으로
개선했다. 둘 다 5 IC이며, 아래 표는 **배선이 더 적은 인코딩형**과 비교한다.

- ROM×1: COMMAND 6 + phase 2 + WAIT 1 = 9비트 주소, 512바이트 제어표.
- 74HC273×1: 쓰기 목적지 4비트 + 캡처 1비트 + 읽기 소스 3비트를 저장.
- 74HC238×2: 11개 양극성 래치 클록을 생성.
- 74HC138×1: 5개 음극성 bank OE를 생성. 코드 0 출력은 미접속하여 reset 뒤 비활성.
- 기존 HC14의 빈 게이트 2개: reset 및 캡처 반전. HC14 패키지 추가 없음.

273의 직접 clear 및 238/138 출력 극성은
[TI 273](https://www.ti.com/lit/ds/symlink/sn74hc273.pdf),
[Nexperia 238](https://assets.nexperia.com/documents/data-sheet/74HC_HCT238.pdf),
[TI 138](https://www.ti.com/lit/ds/symlink/sn74hc138.pdf)의 기능표에 따른다.
쓰기 디코더 주소는 setup에서 먼저 설정하고 캡처 펄스 동안 유지한다. 디코더의
전파 지연과 실제 글리치는 Boolean 검증에 포함하지 않는다.

| 같은 전체 CPU 기준 | 1502 사용 | 인코딩형 대체 | 1502의 절감 |
|---|---:|---:|---:|
| 전체 IC | 32 | 36 | **4 IC** |
| 고유 신호 net | 121 | 139 | **18개** |
| 기능 신호 핀 접점 | 524 | 565 | **41개** |

접점은 전원·GND·NC를 제외하고 연결표에서 센 값이며 점퍼선 개수/길이가 아니다.
래치로 나가는 16개 클록/OE 선은 양쪽에서 그대로 필요하다. 감소분은 주로 제어
블록 내부의 ROM→레지스터→디코더 연결이다. 인코딩형 대체안의 부품/접점 비용이
유일한 대안 또는 전역 최소라고 주장하지 않는다. 현재 검증된 분할에서는 1502가
부품과 제어부 연결을 줄인다는 근거가 된다.

모든 512 입력 조합에서 기존 CUPL의 다음 출력과 두 대체안이 일치하고, 256개
레지스터 출력값에 대해 실제 디코더 연결의 Boolean 결과를 확인했다. 재귀 CALL/RET,
WAIT, Boot/Run·MMIO, 스택 오류 뒤 정지를 포함한 10개 테스트가 통과했다.
CPU 동작 비교는 pre-fit 클록 에지 모델이며, 보드 타이밍은 여전히 미검증이다.

```powershell
.\.venv\Scripts\python.exe -m simulators.cyclesim.hybrid.control_ablation
.\.venv\Scripts\python.exe -m pytest simulators/cyclesim/tests/test_hybrid_control_ablation.py -q
```

요약은 [1502-comparison.json](1502-comparison.json), 대체 연결표와 ROM 이미지는
`simulators\cyclesim\build\hybrid-partition`에 생성한다.

## PC/RP 공통 증감과 명령 종류·단계 카운터 CU (2026-10-23)

`structured_cu.py`는 기존 INC/DEC 12-chip 74 ALU 후보 위에서 실행하는 새
시퀀서다. PC/RP 대상, 증감 방향과 복귀 위치는 주 절차 코드에서 해석하며,
각 호출 위치에 저·고 바이트 실행 상태를 복제하지 않는다. 공통 단계가
저 바이트 계산 → 쓰기 → carry/borrow가 있을 때 고 바이트 계산 → 쓰기를
실행한다. RET의 −2만 MBR에 2를 적재한 뒤 SUB하고, ±1은 기존 INC/DEC를 쓴다.

명령 종류 4비트, 주 절차 5비트, 공통 단계 3비트, 두 번째 피연산자 여부 1비트,
버스 위상 2비트로 구성했다. 27개 주 절차는 **전체 FSM 상태 수가 아니다**.
종류·단계·피연산자·위상을 합친 제어 레지스터는 15비트이며, 실제 상태 조합은
더 많다. 주소의 lo/hi 전송, PC/RP 증감, CALL/RET 스택 접근을 공유한다.
43개 명령 코드(비활성 포함)를 출력하며, `fields` 인코딩은 7비트다.

`structured_fit.py`는 이를 Boolean 식으로 낮춰 CUPL을 생성한다. Python 표는
생성 시 사용하며 **실행 중 제어 ROM 읽기는 없다**. `structured_model.py`는
생성된 CUPL 식을 매 클록 평가하여 실행한다. 출력 코드의 래치/OE 디코드와
플래그·스택 검사는 아직 기존 Transfer 모델이 담당한다. 따라서 새 3-CPLD
전체 배선 모델이나 전체 CPU fit 완료를 뜻하지 않는다. 기존 ROM형 분할은
비교 기준으로 보존했다. reset-vector 부팅과 실물 타이밍도 계속 미검증이다.

| WAIT 없는 프로그램 | 기존 INC/DEC | 공통 CU | 생성 CUPL 실행 |
|---|---:|---:|---:|
| 반복 Fibonacci | 8,920 | 8,920 | 8,920 |
| 재귀 Fibonacci(3) | 6,604 | 6,604 | 6,604 |
| 재귀 Fibonacci(8) | 99,548 | 99,548 | 99,548 |
| ADD 256회 | 12,316 | 12,316 | 12,316 |

단위는 후보 모델의 4위상 전송 클록이다. 규범 모델의 논리 SYS 수와 다르며,
실측 MHz/MIPS가 아니다. ISA 상태와 모든 메모리 접근 순서를 매 명령마다
독립 참조 CPU와 대조했다. 제어 공유에 따른 추가 호출/복귀 클록은 없다.
256 opcode × 플래그 조합, 스택 경계 오류, PC wrap, Boot/Run·MMIO, WAIT,
재귀 CALL/RET 및 생성 식의 모든 합법 단계 출력을 별도 테스트한다.

**ATF1504AS PLCC44, JTAG ON의 Design fits는 아직 실패**다. 기본 `fields`
인코딩은 배치 전 69 Logic Cell로 용량 초과했다. 이는 사용 MC 확정값이 아니다.
중간 논리 노드를 명시하는 후보들도 용량 초과 또는 grouping/placement 실패였다.
이 결과는 명령 코드 출력 시퀀서만의 결과이므로, 예전 출력·검사 로직 포함 CU의
셀 수와 직접 비교하여 절감률을 계산할 수 없다. 새 구성의 전체 칩 수·배선 수와
핀 배치는 아직 확정하지 않는다. ISA나 스택 검사를 빼서 fit한 결과도 아니다.

```powershell
.\.venv\Scripts\python.exe -m simulators.cyclesim.hybrid.structured_measure
.\.venv\Scripts\python.exe -m simulators.cyclesim.hybrid.structured_fit
.\.venv\Scripts\python.exe -m simulators.cyclesim.hybrid.structured_fit --order fields --nodes leave last
.\.venv\Scripts\python.exe -m pytest simulators/cyclesim/tests/test_hybrid_structured.py -q
```

측정은 `build\hybrid\structured-comparison.json`, 피팅 PLD·로그·보고서는
`build\hybrid-partition\strucseq\`에 생성한다(위 경로는 cyclesim 기준).
재현 당시 측정 및 기본 fit 요약은 [structured-evidence.json](structured-evidence.json)에
보존한다. 실패한 fit 요약은 성공한 JEDEC 또는 배치 완료 핀 배치를 제공하지 않는다.
