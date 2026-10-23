# 74HC 순차 CPU 비교 모델

현재 ISA와 비파이프라인 순차 실행 계약을 **74HC 부품 연결로 구현한 실험 모델**이다.
정본 하드웨어의 CPLD-CU/DP 구성을 변경하지 않는다. 비교 기준은
[순차 CU 계약](../../../reference/hardware/cpld-sequential-cu.md)과 독립적인
`CpuM3b` 기능 모델이다. 기존 ALU 뷰어는 ALU 전용으로 유지한다.

## 실행

저장소 루트의 Windows PowerShell에서 실행한다.

```powershell
# 모든 SYS의 상태·버스 접근·메모리 결과를 두 구현 사이에서 비교
.\.venv\Scripts\python.exe -X utf8 -m simulators.cyclesim.ttl.compare

# ALU 12개와 SYS 계약을 유지하면서 게이트·패키지를 최적화한 후보
.\.venv\Scripts\python.exe -X utf8 -m simulators.cyclesim.ttl.compare --optimized

# WAIT를 5번째 호스트 tick마다 삽입하여 부작용 중복 여부도 비교
.\.venv\Scripts\python.exe -X utf8 -m simulators.cyclesim.ttl.compare --wait-every 5 --output simulators/cyclesim/build/ttl-wait

# 부품 모델 및 CPU 회귀 테스트
.\.venv\Scripts\python.exe -X utf8 -m pytest -q simulators/cyclesim/tests/test_ttl_cpu.py simulators/cyclesim/tests/test_ttl_netlist.py simulators/cyclesim/tests/test_ttl_optimize.py
```

기본 출력:

- `simulators\cyclesim\build\ttl\netlist.json`: 기능 핀 연결, 부품별 그룹, 관측 신호.
- `simulators\cyclesim\build\ttl\comparison.json`: 실행 결과, 부품 집계, 통합 후보 경계,
  조합 논리 깊이, 소스와 넷리스트 SHA-256.

출력은 gitignored이며 명령으로 재생성한다. 호스트 실행 시간은 CPU MIPS와 분리한다.
CLI는 불일치, SYS 상한 또는 실행시간 상한에 도달하면 실패한다.

## 실제 회로 계산 범위

`cpu.py`는 회로를 **구축**하며, 런타임 opcode별 Python 실행 함수는 없다.
`netlist.py`가 각 부품의 진리표를 위상 순서로 평가하고 공통 클록에서 모든 D를
동시에 샘플한 뒤 Q를 갱신한다. 제어 논리도 04/08/32 게이트와 574 상태 레지스터다.

| 경로 | 구현 |
|---|---|
| 명령/상태 디코드·다음 상태·분기·WAIT | 74HC04/08/32, 574, 157 |
| R0, IR, MBR, 상위 operand, PC, flags | 74HC574 + 외부 157 feedback mux |
| ALU | 기존 연결표의 153×8 + 283×2 + 157×2 그대로 |
| Z 판정·ALU 제어 glue | 별도 04/08, ALU 12개 집계 밖 |
| PC+1, RP±2, stack byte 주소 | 16비트 283 연결 + 157 선택 |
| 스택 경계/정렬·overflow·underflow | 04/08/32 비교 논리 |
| CALL/RET 임시 RP·복귀 주소 | 574; RAM의 RP가 architected 상태 |
| 주소 및 쓰기 데이터 선택 | 157 + gate glue |
| 공유 데이터 버스 | CPU측 245와 외부 메모리 드라이버의 4상태 해석 |
| Boot/Run·RAM·ROM·Mailbox 선택 | 04/08/32 주소 논리 |

574에는 없는 enable/reset 기능을 가정하지 않는다. 유지 동작은 외부 157 feedback이다.
245의 DIR은 A→B로 고정하며 출력 금지 시 Z가 된다. 사용하지 않는 게이트 입력과
574 D는 LOW, 출력은 NC로 export한다. 기능 핀 이름은 DIP 핀 번호가 아니다.

RAM/ROM/메일박스 저장소, 클록 공급, WAIT 입력, 초기 레지스터 설정은 테스트벤치
경계다. 특히 **574 초기값을 설정하는 reset fixture는 물리 reset 회로가 아니다.**
이 모델의 메모리 선택 회로는 정본의 138×2 구현과 다른 gate-only 비교 후보다.
메모리 읽기/쓰기는 회로의 주소·선택·RD/WR·버스 신호만 소비하며 정답 CPU의
`MemSystem.read/write` 디코드 함수를 실행에 재사용하지 않는다.

## 측정 결과와 복잡성 비교

2026-10-23 실행: 아래 다섯 프로그램의 **매 SYS 전체 trace와 메모리 내용이 일치**했다.
MIPS 분자는 HALT/TRAP을 제외한 native retirement, 분모는 종료 HALT까지의 모든 SYS다.

| 프로그램 | SYS | 유효 native 명령 | 가정 2 MHz에서 MIPS |
|---|---:|---:|---:|
| 반복 Fibonacci → 233 | 504 | 159 | 0.631 |
| 재귀 Fibonacci(3) | 379 | 106 | 0.559 |
| 재귀 Fibonacci(8) | 5,689 | 1,632 | 0.574 |
| ADD 4,096회 | 12,290 | 4,096 | 0.667 |
| CALL/RET 256쌍 | 4,098 | 512 | 0.250 |

같은 SYS 계약이므로 두 구현의 논리적 CPI는 같다. 2 MHz는 가정이며 실제 도달
클록을 측정한 결과가 아니다. `--wait-every 5`에서도 결과는 일치했고, 예를 들어
반복 Fibonacci는 126 WAIT를 포함해 630 SYS가 된다. 이는 인위적인 검증 입력이다.

기본 모드의 **단순 gate 구현 후보는 185개 74HC 패키지**다. 메모리 IC, 전원, 클록,
reset, 부하용 버퍼는 제외한다. 최소 BOM이나 정본 BOM을 뜻하지 않는다.
동일 논리식과 상수는 공유/단순화하지만, 138 디코더·카운터·다른 게이트 계열 선택,
그룹 간 spare gate 공유, 레지스터 재사용에 의한 최적화는 하지 않았다.
157 채널은 **동일 select를 공유하는 경우에만** 한 패키지에 묶는다.

| 회로 그룹 | 74HC 패키지 |
|---|---:|
| 제어 | 55 |
| 스택 임시 상태·계산·검사 | 43 |
| 주소·PC 입력 경로 | 34 |
| 일반 레지스터·입력 mux | 18 |
| ALU 코어 | 12 |
| ALU 제어·Z glue | 4 |
| 데이터 버스 경로 | 11 |
| 메모리 선택 | 8 |
| 합계 | 185 |

`comparison.json`은 그룹을 통합했을 때 제거되는 부품과 남는 부품, 경계를 가로지르는
신호도 집계한다. 제어 그룹만 옮기면 이 후보에서 **55개가 통합 대상, 130개가 잔류**한다.
제어+스택은 **98개가 통합 대상, 87개가 잔류**한다. 따라서 이번 후보에서는 ALU보다
제어·스택·주소 경로가 부품 수의 큰 부분이다.

이 숫자는 **대체 CPLD/FPGA를 더하기 전의 74HC 수**다. CPLD 한 개로 들어간다는
뜻이 아니며, 핀 수·전압·합성·배치·Design fits는 별도다. ROM 테이블로 대체할 때도
상태 레지스터·출력 안정화·필요한 다음 상태 로직까지 자동으로 사라지지 않는다.

## 1차 최적화 결과

`--optimized`는 원본을 복제한 뒤 **185 → 167개**, **18개(9.7%) 감소**한
별도 회로를 만든다. 기본 185개 모델과 그 보고서는 비교 기준으로 유지한다.
출력은 `simulators\cyclesim\build\ttl-optimized` 아래에 저장한다.

| 단계 | 74HC 패키지 |
|---|---:|
| 기본 후보 | 185 |
| 상수 MUX의 gate 변환·그룹 간 공통식 공유·dead gate 제거·채널/574 재배치 | 174 |
| 단일 소비자 AND tree를 74HC11/21로 치환 | **167** |

여기서 채널 공유는 실제 패키지 제약을 지킨다. 157은 동일 select를 사용하는
채널끼리만 묶고, 574는 동일 CLK 및 항상 활성인 Q 출력을 갖는 bit끼리 묶는다.
각 레지스터의 enable은 외부 feedback mux에 남는다. 574 패키지는 14 → 12개,
157은 65 → 56개다. ALU 코어 12개, ISA, 상태 비트 수, SYS 스케줄은 유지한다.

최적화된 회로도 정답 모델과 매 SYS·메모리 결과를 비교한다. 모든 opcode 및 스택,
WAIT 회귀 검증을 두 후보에 모두 적용하며, 상수 MUX 변환은 4상태 입력 전체,
전체 회로는 X/Z를 포함한 임의 상태에서 관측값과 동시 register update를 비교한다.
위 다섯 프로그램의 SYS와 MIPS 환산값은 최적화 전과 같다.

**167개는 이번에 구현·실행한 1차 최적화 후보이며 최소값이 아니다.** 138/154
디코더나 카운터로의 구조 변경, 임시 레지스터 재사용, 상태 인코딩 재설계는
포함하지 않는다. 그룹 간 공통 gate 공유는 fanout과 배선 배치를 바꾸므로 실제
보드에서 필요한 buffer 수와 속도는 별도 검증 대상이다. 메모리·reset·클록 등
집계 제외 범위는 기본 후보와 같다.

최적화 후에는 한 패키지가 여러 논리 그룹에 걸칠 수 있어 `shared`로 표시한다.
따라서 기본 모델의 제어 55개/스택 43개 같은 단순 그룹 제거 수를 최적화 후보에
그대로 적용하지 않으며, 최적화 보고서의 `partitions`는 비워 둔다.

추가 부품 기능 출처:
[Nexperia 74HC11, triple 3-input AND](https://assets.nexperia.com/documents/data-sheet/74HC_HCT11.pdf),
[TI 74HC21, dual 4-input AND](https://www.ti.com/lit/ds/symlink/sn74hc21.pdf).

## 검증과 남은 경계

테스트는 256개 opcode 바이트, CALL/RET 경계와 carry, PC wrap, Boot/Run 보호,
MMIO, self-modifying RAM 프로그램, 반복/재귀 Fibonacci, WAIT, ALU stuck-at
고장 전파, 동시 레지스터 샘플, 245의 Z/X 동작을 포함한다.

이 구현은 **4상태·제로 지연 기능 시뮬레이션**이다. 게이트 연결과 cycle count를
비교할 수 있지만 ns 지연·글리치·setup/hold·clock skew·부하·버스 turnaround를
검증하지 않는다. `deepest_register_paths`는 패키지 내부 게이트도 각각 세는
조합 논리 단계 수이며, DBUS와 Q를 출발점으로 삼는다. 외부 메모리를 왕복하는
전체 경로 및 false path 제거는 포함하지 않는다. 이 값을 Fmax로 환산하지 않는다.

부품 기능 확인 출처:
[TI 574](https://www.ti.com/lit/ds/symlink/sn74hc574.pdf),
[157](https://www.ti.com/lit/ds/symlink/sn74hc157.pdf),
[283](https://www.ti.com/lit/ds/symlink/cd74hc283.pdf),
[245](https://www.ti.com/lit/ds/symlink/sn74hc245.pdf),
[08](https://www.ti.com/lit/ds/symlink/sn74hc08.pdf),
[04](https://www.ti.com/lit/ds/symlink/sn74hc04.pdf).
