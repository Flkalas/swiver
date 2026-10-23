# 공통 8비트 hi/lo 버스 하이브리드 비교 모델

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

## 로컬 기능 배치 탐색 — 외부 레지스터 후보

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
