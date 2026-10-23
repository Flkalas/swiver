# CPLD 통합 구현 감사 — 2026-10-23

현재 문서와 실행 코드를 대조했다. **전체 데이터패스를 CPLD로 통합한 CPU는 아직
구현되지 않았다.** 74HC 비교 모델의 패키지를 빼서 하이브리드 BOM을 계산할 수 없다.
ISA와 순차 실행 계약은 변경하지 않는다.

## 설계 의도와 구현

| 대상 | 현재 확인한 범위 |
|---|---|
| CPLD-CU | 순차 FSM·ALU 제어·메모리 strobe를 맡는 사양. 완성된 핀 할당과 PLD/fit 없음 |
| CPLD-DP | R0 8비트 저장과 `q_a` 출력만 정의. PC/주소 연산/MBR/스택 임시 상태 통합은 정의되지 않음 |
| 기능 CPU | Python 순차 실행 모델. `blocks/cpld/dp.py`의 `regs=[0]` 사용 |
| `blocks/cpld/cu.py` | 이전 Gi1 LUT 모델. 현재 순차 CU의 물리 구현 근거가 아님 |
| 74HC 모델 | 제어·데이터경로를 74HC 기능식으로 만든 별도 후보. 185개, 최적화 167개 |

근거: [백서 §3–6](../../swiver-whitepaper.md), [CU/DP 사양](cpld-system-controller.md),
[기능 CPU](../../simulators/cyclesim/cpu.py), [DP 코드](../../simulators/cyclesim/blocks/cpld/dp.py),
[74HC 코드](../../simulators/cyclesim/ttl/cpu.py). 추적되는 `cpld/` 파일은 README와
도구 파일이며 활성 `.pld`/HDL/JEDEC 산출물이 없다. 보관 아카이브는 조사하지 않았다.

## 제어와 검사를 구분해야 한다

명령 디코드, 상태 전이, 레지스터 write-enable, 버스 선택은 CPU 실행에 필요하다.
하이브리드에서 CPLD가 담당할 기능을 all-74 모델에서는 외부 게이트로 구현한 것이다.
**따라서 하이브리드에도 제어 55개를 별도로 추가해야 한다는 뜻이 아니다.**

스택 정렬·범위·overflow/underflow 검사는 [순차 계약](cpld-sequential-cu.md)의
잘못된 RAM 쓰기를 막는 동작이다. 이를 유지하되 CPLD 내부로 옮기는 것은 가능한
설계 방향이며, 외부 74 게이트여야 할 이유는 없다. 실제 수용 여부는 fit으로 확인해야 한다.

한편 all-74 코드의 2비트 `fault` 레지스터와 TRAP/STACK_PUSH/STACK_POP 등의
trace 관측 신호는 진단 목적도 포함한다. 기능에 필요한 오류 검출과 진단 출력은
다르다. 관측 논리를 제거했을 때 공유 게이트·패키지까지 얼마나 줄어드는지는
별도 회로 생성·검증 없이 숫자로 단정하지 않는다.

## 구매 목록과 해결되지 않은 배선

[현재 구매 목록](../project/BOM.md)의 Qty 합은 **74HC 29개 + CPLD 2개 + 메모리 3개**다.
74HC에는 클록용 HC14와 M1용 ACC가 포함된다. 이는 보존된 구매 수량이며 완성 CPU의
확정 BOM이나 185개에서 줄어든 결과가 아니다. Qty는 변경하지 않았다.

- CU 입력 `OPC[4:0]`만으로는 ADD `0x01`과 reserved `0x21`이 동일하다.
  실행 모델은 8비트를 구분한다. 상위 비트 검증 또는 입력 확장이 필요하다.
- PC 16비트, abs16 상위 바이트, RP와 popped return-PC 임시 상태 및 스택 검사
  입력을 어느 칩·핀에 둘지 완성된 할당표가 없다.
- 백서 574×3/161 역할 요약과 구매 목록 574×4/161×3을 대조해야 한다.
  161×3은 12비트이므로 나머지 PC 비트 경로까지 명시해야 한다.
- CE 사양에는 04 glue가 있지만 구매 목록에는 HC04 행이 없다. 다른 부품으로
  흡수할지 추가할지 회로로 확정해야 한다.
- reset/WAIT 물리 회로, 실제 핀 연결, Design fits, 부하·setup/hold를 포함한
  타이밍은 검증되지 않았다. 기능 시뮬레이션과 가정 2 MHz MIPS는 이를 대신하지 않는다.

## 보고서 정정

이전 130/87/16은 all-74 모델의 그룹별 단순 차감 값이며 하이브리드 잔여 칩 수가 아니다.
보고서 v2는 이를 `model_group_cuts`로 명명하고 `is_hybrid_bom=false`,
`hybrid_bom_count=null`을 기록한다. 정확한 CPLD 통합 수량은 데이터패스 분할,
핀 연결 및 합성/fit을 마친 뒤 산출해야 한다.
