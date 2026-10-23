# 두 ATF1504에서 IR·카운터를 외부로 꺼낸 비교

2026-10-24. [새 RAM ISA](../../../reference/hardware/ram-isa-experiment.md)를 그대로 실행하면서
**IR + 실행 단계 카운터**, 그리고 **IR + 단계 카운터 + PC**의 두 안을 구현했다.
둘 다 ATF1504AS-10JU44 두 개만 사용하고 ALU 12칩은 외부에 유지한다.
ATF1502와 제어 ROM은 사용하지 않는다. 정본 v1.0의 ISA·CU를 변경한 결과는 아니다.

**전체 연결도:** 저장소 루트에서 `.\.venv\Scripts\python.exe -m simulators.cyclesim viewer`를
실행하고 [CPU 전체 연결도](http://127.0.0.1:8765/?view=cpu&variant=35)를 연다.
24·29·35칩 구성 전환, 버스 비트별 연결, 칩별 기능 핀표, CPLD 최종 fit 핀 번호,
MC/I/O 사용량과 연결표 JSON 내보내기를 제공한다. 이 문서의 검증 자료와 연결표를
그대로 사용하며, 실제 점퍼 배치나 보드 타이밍 화면은 아니다.

## 결과

| 같은 CPU 논리 + 메모리 범위 | 기존 두 1504 | 외부 IR·단계 | 외부 IR·단계·PC |
|---|---:|---:|---:|
| 전체 IC | **24** | **29** | **35** |
| 외부 74HC | 19 | 24 | 30 |
| ATF1504 | 2 | 2 | 2 |
| 프로그램 Flash + SRAM | 3 | 3 | 3 |
| IC 사이 신호 net | 85 | 109 | 131 |
| 위 net의 기능 핀 접점 | 318 | 385 | 477 |
| 점대점 연결 하한, 아래 정의 | **233** | **276** | **346** |
| 기존 대비 연결 하한 증가 | — | 43 / 18.45% | 113 / 48.50% |
| WAIT 없는 명령당 클록 | 6 | 6 | 6 |

**배선 수의 정의:** 두 개 이상의 IC에 닿는 신호 net에 대해 기능 핀 접점이 N개면
N−1개의 점대점 트리 연결을 합산했다. 같은 IC의 두 입력을 묶는 접점도 포함한다.
전원·상수 연결, 사용하지 않는 출력, 외부 신호원·커넥터 접점과 개별 JTAG 포트는 제외한다.
SYS와 RESET처럼 여러 IC를 연결하는 신호의 IC 간 연결은 포함한다.
브레드보드 공통 열, PCB 배치·라우팅, 점퍼 길이·교차를 반영한 **실제 점퍼 개수는 아니다**.
`*-connections.json`에 합산한 net과 모든 기능 핀 접점을 내보내므로 수량을 추적할 수 있다.

세 구성 모두 발진기, 정리된 RESET/WAIT 신호원, 부하 버퍼, mailbox MCU, 수동부품을 제외한다.
검증한 분할의 수량이며 모든 가능한 재설계의 최소 칩 수를 증명하지 않는다.

## 무엇이 추가되고 어디가 보이는가

| 기능 | IR·단계 외부화 | PC까지 외부화 |
|---|---|---|
| 기존 외부 ALU | HC153×8 + HC283×2 + HC157×2 = 12 | 동일 |
| IR 8비트 | HC377×1 | 동일 |
| 실행 단계 0…5 | HC161×1 | 동일 |
| AC 저장 | HC377×1 | 동일 |
| DB/ALU Y → AC 선택 | HC157×2 | 동일 |
| AC → 공통 DB 출력 | HC244×1 | 동일 |
| ALU Y == 0 검출 | HC688×1 | 동일 |
| PC 16비트 | 주소 CPLD 내부 | HC161×4 |
| PC → 주소 버스 출력 | 주소 CPLD 내부 | HC244×2 |
| 메모리 디코더 | HC30×2 + HC138×1 + HC139×1 + HC00×1 = 5 | 동일 |
| CPLD + 메모리 | 2 + 3 | 동일 |
| **합계** | **29** | **35** |

IR과 단계 저장만 2칩 추가하는 방식으로 끝나지 않는다. 기존 CU의 일반 I/O 28개는 이미
모두 사용 중이다. 외부 IR·단계의 Q를 받는 입력이 늘어나므로 역할을 다시 분할했다.
새 CU에는 명령·단계 해독과 Z/C/HALT만 남기고, AC·쓰기 선택·버스 출력·zero 검출을
외부로 옮겼다. 반대로 기존 외부 HC173×2의 **P 페이지 저장은 주소 CPLD에 흡수**했다.
따라서 외부 IR/단계/AC 관련 7칩을 추가하고 P 저장 2칩을 제거해 24 → 29가 된다.

29칩 안에서는 IR Q → CU 해독 → 단계 Q → 제어선 → ALU → writeback → AC → DB 흐름을
실제 칩 핀에서 관찰할 수 있다. IR[3]은 AC 쓰기 MUX, IR[5]는 ALU 논리 결과 선택에 직접
연결한다. CPLD에 관찰용 IR·단계 복사본을 추가한 것이 아니라 **실행에 쓰는 저장소 자체**다.
이전 SUB/분기 조건의 핀 공유도 없앴다. SUB는 ALU에만, PC 적재는 별도 제어선에 전달한다.

35칩 안은 여기에 16비트 PC의 네 자리 carry 연쇄, +1, 병렬 분기 주소 적재와 주소 버스
구동까지 외부 칩으로 드러낸다. 그 추가 비용은 HC161×4 + HC244×2, **6칩과 연결 70개**다.
교육 효과와 배선량을 함께 보면 **29칩 안을 기본안으로 권한다**. PC의 carry·분기 적재까지
실물로 실험하는 것이 목적이면 35칩 안을 선택할 수 있다.

## 실제 fit과 핀

WinCUPL/FIT1504, PLCC44, JTAG ON, tPD 요청 10ns. 다음 네 블록 모두
`Design fits successfully`와 정격 안의 자원 보고, 최종 핀 배치와 JED 생성을 확인했다.
10ns는 fitter 요청 조건이며 보드 전체 경로가 10ns라는 뜻이 아니다.
아래 MC 사용량은 해당 실험 소스·도구의 결과로만 기록한다.

| 구성 / 블록 | MC | 일반 I/O, JTAG 제외 | 전용 입력 |
|---|---:|---:|---:|
| 29칩 CU `educu` | **21/64** | **23/28** | 4/4 |
| 29칩 주소 `eduaddr` | **59/64** | **28/28** | 4/4 |
| 35칩 CU `edupccu` | **24/64** | **26/28** | 4/4 |
| 35칩 주소 `edupcaddr` | **33/64** | **27/28** | 4/4 |

29칩 주소부는 PC16 + X8 + P8 + literal8을 저장한다. literal 레지스터는 DB 출력
macrocell의 등록 Q를 사용하고, 입력 캡처는 실제 `dbN.io`에서 받는다.
주소 출력 16핀과 공통 DB 8핀 때문에 **일반 I/O 여유는 없다**.
35칩 주소부는 PC가 없어져 MC 여유가 늘지만 일반 I/O는 한 핀만 남는다.
CU의 MC 여유를 다른 기능으로 채우려면 필요한 입력·출력 핀도 함께 확보해야 한다.

초기 29칩 주소부의 분기 목표를 내부 식으로 모두 펼친 안은 성공 문구와 **65/64 MC**가
동시에 나와 채택하지 않았다. 수정안은 분기 capture 때 이미 구동하는 ADDRESS[7:0]을
실제 pad 입력으로 읽어 PC low D에 전달한다. 별도 외부 점퍼 없이 같은 입출력 pad를
사용하며, 상위 바이트는 P에서 직접 받는다. 이 소스는 **59/64**로 자원 보고가 일관된다.
주소 pad를 거쳐 PC로 돌아오는 경로의 전기적 setup/hold 검증은 남는다.

두 안 모두 `COMMAND[1:0]`은 00=hold, 01=X 적재, 10=P 적재, 11=literal 적재다.
IR[7]은 literal/X 주소 선택을 직접 제어한다. 따라서 별도 8비트 제어 버스를 추가하지 않는다.
최종 배선 pad 번호는 `.pld`의 초기 제안이 아니라 **성공한 `.fit`의 Pin 표**를 따른다.
JSON의 `signal_pad_numbers`에도 그 배치를 보존한다. 74/메모리 핀은 기능 이름이다.

## 클록·reset·실행 확인

T0/T1은 opcode setup/capture, T2/T3는 literal setup/capture, T4/T5는 execute
setup/capture다. HC161은 T5 완료 에지에서 동기 load로 0을 적재하고, WAIT 또는 HALT에서는
count를 멈춘다. 모든 377/161/CPLD 저장소는 같은 SYS 상승 에지를 사용한다.
외부 PC의 HC161은 RCO → 다음 ENT로 연쇄하고, branch 병렬 load가 count보다 우선한다.
PC와 주소 CPLD의 출력은 T1/T3와 T5를 나눠 쓰며 중간 단계에서는 모두 해제한다.
29칩 안에서는 주소 CPLD 한 개가 주소 버스를 계속 구동한다.

물리 RESET_N은 161과 CPLD를 초기화하지만 **HC377에는 reset 핀이 없다**.
IR과 AC의 전원 초기값을 0이라고 가정하지 않는다. IR은 첫 fetch에서 덮어쓰고 boot 코드가
AC를 초기화해야 한다. 테스트용 `reset(pc)` 초기값 설정과 실제 RESET_N 경로를 구분한다.
기존 실험과 같이 `$0000`부터 시작하며 v1.0의 reset-vector fetch를 구현한 것은 아니다.

부품 기능은 제조사의 [HC377](https://www.ti.com/lit/ds/symlink/sn74hc377.pdf),
[HC161](https://www.ti.com/lit/ds/symlink/sn74hc161.pdf),
[HC244](https://www.ti.com/lit/ds/symlink/sn74hc244.pdf),
[HC688](https://www.ti.com/lit/ds/symlink/sn74hc688.pdf) 데이터시트의 기능표를 따른다.
메모리 디코더는 [24칩 구성](ram-cpld.md#1502를-빼는-직접-대체안--24-ic)과 같은 다섯 칩이다.

| 프로그램 | 두 외부화 안 모두 완료 명령 | 두 외부화 안 모두 tick | 결과 |
|---|---:|---:|---|
| 반복 Fibonacci(13) | 205 | 1,230 | A=233 |
| RAM 포인터 페이지 경계 복사 | 64 | 384 | A0…A3 복사, 포인터 $2102 |
| 검사 포함 재귀 Fibonacci(3) | 684 | 4,104 | A=2, RP=$F600 복구 |

각 명령의 PC/A/X/P/Z/C/HALT, 전체 메모리, 접근 주소·값·순서를 기존 24칩 구성과
독립 ISA 해석기에 대조했다. 두 안 모두 결과와 tick이 같았다.
native MIPS는 동일 클록을 가정하면 MHz/6이며 2MHz에서는 약 0.333 MIPS다.
외부화로 클록 수가 늘지는 않지만, **실제 최대 클록이 같다는 의미는 아니다**.

전체 opcode×플래그, ALU 경계, Boot/Run/MMIO, 네 자리 PC carry와 wrap, branch,
소프트웨어 스택 경계, WAIT/HALT 정지, 여러 IR/AC 초기값에서 reset·boot를 검사한다.
IR Q·단계 counter enable·PC carry·ALU Y·zero 검출의 고장을 주입해 실제 외부 부품이
실행을 바꾸는 것도 확인한다. 부품 고장을 호스트의 명령 실행으로 우회하지 않는다.

새 두 구성과 배선 집계 **2,297개**, 기존 CPLD 구성·외부 디코더 회귀 **2,284개**,
합계 **4,581개 테스트가 134.15초에 통과**했다. 가장 긴 새 재귀 실행 테스트는 8.00초로
기본 30초 제한 안이며 모든 CPU 실행 반복에 명령/클록 상한이 있다.

검증 범위는 **vendor block fit + CUPL 소스 식과 외부 부품의 기능 실행**이다.
post-fit 지연 시뮬레이션, JED를 기록한 보드, 글리치·출력 부하·setup/hold·실측 주파수는
포함하지 않는다. 논리적 tri-state ownership과 WAIT 중 부작용 억제는 검사한다.

## 재현·연결표

저장소 루트 `D:\Github\swiver`에서 실행한다.

```powershell
.\.venv\Scripts\python.exe -X utf8 -m simulators.cyclesim.hybrid.ram_educational_measure
.\.venv\Scripts\python.exe -X utf8 -m pytest -q simulators/cyclesim/tests/test_ram_educational.py simulators/cyclesim/tests/test_ram_educational_wiring.py simulators/cyclesim/tests/test_ram_cpld.py simulators/cyclesim/tests/test_ram_no1502.py
```

- `simulators\cyclesim\build\ram-educational\comparison.json`: fit·수량·배선 집계·프로그램 대조.
- 같은 폴더의 `baseline-netlist.json`, `ir_step-netlist.json`, `ir_step_pc-netlist.json`: 전체 IC 연결.
- 같은 이름의 `*-connections.json`: 배선 비교에 합산한 net별 기능 핀 목록.
- `simulators\cyclesim\build\hybrid-partition\educu`, `eduaddr`, `edupccu`, `edupcaddr`: PLD/TT2/FIT/JED.
- [ram-educational-evidence.json](ram-educational-evidence.json): 실행 당시 결과와 소스·도구·산출물 SHA-256.

[ram_educational.py](ram_educational.py)는 소스·외부 부품 연결,
[ram_educational_cpu.py](ram_educational_cpu.py)는 실행 모델,
[ram_educational_measure.py](ram_educational_measure.py)는 fit·비교·내보내기를 담당한다.
