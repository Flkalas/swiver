# cyclesim — executable P12 model

**Active normative hardware:** **v1.0 P12** pipe CU — [reference/hardware/cpld-pipe-cu.md](../../reference/hardware/cpld-pipe-cu.md).

`CpuM3b.step()` advances one counted `CLK_SYS` tick and emits an immutable
`SysTrace`. The executable path models the P12 states `FILL`, `IF_EX`,
`OPERAND_IF`, `MEM_STALL`, `BRANCH_BUBBLE`, `STACK_EX`, `STRETCH`, and
`FALLBACK_FE2`. Functional effects are retained for the active M3b ISA,
including R0/MBR ALU operands, memory/MMIO, redirects, and return-stack errors.

The idx5 table and tests under `tests/legacy/` are historical fixtures only.
This model is an executable P12 abstraction, not physical breadboard validation;
use [cpld-pipe-cu.md](../../reference/hardware/cpld-pipe-cu.md) §4 for the
normative timing desk.


## 실시간 ALU 뷰어

저장소 루트에서 실행한다. `.venv`를 사용하고 기존 `uv.toml`의
`link-mode = "symlink"` 설정을 유지한다.

```powershell
uv pip install --python .venv\Scripts\python.exe -r simulators\cyclesim\requirements-dev.txt
uv run --python .venv\Scripts\python.exe -m simulators.cyclesim viewer
```

브라우저에서 `http://127.0.0.1:8765`를 연다. 포트가 사용 중이면
`viewer --port 8766`으로 실행하고 출력된 주소를 연다. `Ctrl+C`로 종료한다.
서버는 `127.0.0.1`에만 바인딩하며 Python 표준 라이브러리만 사용한다.
서버 한 개가 ALU 세션 하나를 제공하므로 여러 탭은 상태를 공유한다.

- 실제 코어는 **74HC153×8 + 74HC283×2 + 74HC157×2**다.
  전기 연결은 export 넷리스트에서 읽고 화면 배치와 분리한다.
- A/B, 프리셋 또는 직접 CIN/BCTRL/LGC/출력 선택을 바꾸면 Python에서
  회로를 안정화하고 중간 B, 논리, 합, 캐리, Y를 반환한다.
  브라우저는 ALU를 다시 계산하지 않는다.
- 숫자 입력은 0..255 정수만 허용한다. X/Z는 숫자 0으로 변환하지 않으며,
  불확정 버스의 수치는 null로 전달한다. 충돌·미연결·수렴 실패는 진단이다.
- 칩/핀/넷 선택과 비트 펼치기는 연결 관측용이다. 핀은 **기능 이름**이며
  DIP 핀 번호는 칩 배선도 탭의 별도 package 매핑에서 확인한다. 153의 1G/2G와 157의 G는 LOW에 타이한다.
- 코어 밖 제어 glue와 비교 관측은 별도 경계다. 가상의 비교기 칩이나
  추가 A/B 선택 MUX를 12칩에 숨겨 넣지 않는다.
- `경로 따라보기`와 안정화 반복은 교육용 표시다. CPU 클럭이나 실제 ns가
  아니며 계산 결과를 지연하지 않는다. 연결이 끊기면 마지막 관측이 오래된
  상태임을 표시한다.

회로/스냅샷/입력 API는 [viewer_contract.md](viewer_contract.md)에 정의한다.
서버 모듈은 `viewer_server.py`, 모델은 `viewer_model.py`, 화면은
`viewer\web`에 있다. 예제의 산술 기대값과 실제 넷리스트 중간값을 비교한다.

## ALU 정합화 내용

153 선택값은 모든 연산에서 `A_bit + 2 × B_bit`다. C0..C3가 제어워드의
bit0..bit3에 대응한다. `s0/s1`은 출력 선택 OR에만 쓰며 153 선택 핀을
덮어쓰지 않는다. LGC는 AND=`1000`, OR=`1110`, XOR=`0110`, NOT=`0101`,
PASS_A=`1010`, PASS_B=`1100`이다. NOT/PASS의 다른 피연산자는 자유롭다.

`ALU_PRESETS`를 제어값의 단일 Python 정의로 사용한다. 다음 명령으로
관련 문서의 제어표·벤치표만 재생성하거나 현재 표의 차이를 검사한다.

```powershell
uv run --python .venv\Scripts\python.exe -m simulators.cyclesim.export.alu8_controls --check
# 의도적으로 표를 갱신할 때만 --write
```

NOP의 기존 제로 제어는 **물리 Y=A**다. CPU 상태 유지는 쓰기 정책이다.
CMP는 **물리 SUB 출력**을 만들고 CPU ACC 쓰기를 막는다. 비교 관측과
CPU 플래그 쓰기도 분리한다. `net_c_hi`는 논리 연산 선택 중에도 물리
가산기의 carry이며, unsigned >= 의미는 SUB/CMP에서만 성립한다.

기존 `export alu8` CLI와 정적 `build\alu8-schematic.html`은 유지한다.
기존 화면은 비교용 토폴로지 뷰어이고 실시간 뷰어의 전기적 판정 기준이
아니다. 스크린샷은 `build\viewer-evidence`에 보존한다.

## 범위와 검증

이번 모델은 **제로 지연 기능 시뮬레이션**이다. 기존 P12 ISA/FSM은
변경하지 않는다. CPU는 기존 실행 경로를 유지하며 실시간 뷰어와 연결된
CPU 세션은 아직 없다. 데이터패스, 제어 FSM, 전체 CPU의 공통 세션 연결,
전파 지연·글리치·setup/hold는 후속 단계다. 기존 문서의 동결 ns 수치는
이번 기능 테스트로 재검증되지 않는다. 실기 배선·부하·타이밍 합격을
의미하지 않는다.

```powershell
uv run --python .venv\Scripts\python.exe -m simulators.cyclesim test
```

pytest-timeout이 필요하며 기본 테스트 제한은 30초다. 전수검사는 연산과
입력 범위로 분할하거나 명시적 제한을 둔다. 브라우저 검증에는 별도 개발
도구 Playwright/Chromium을 사용하며, 뷰어 실행 자체에는 필요하지 않다.


기능표 출처: TI [SN74HC153, §7.3](https://www.ti.com/lit/ds/symlink/sn74hc153.pdf),
[SN74HC157, §6.4](https://www.ti.com/lit/ds/symlink/sn74hc157.pdf),
[CD74HC283, §7](https://www.ti.com/lit/ds/symlink/cd74hc283.pdf).
153의 A/B 주소 순서, 153/157의 HIGH strobe 시 LOW 출력, 283의 4비트
합·캐리 연결을 기능 기준으로 삼는다. X/Z는 디지털 불확정값 모델이며
실제 아날로그 입력 전압을 예측하는 모델이 아니다.


브라우저 개발 도구 설치:

```powershell
uv pip install --python .venv\Scripts\python.exe -r simulators\cyclesim\requirements-viewer-dev.txt
uv run --python .venv\Scripts\python.exe -m playwright install chromium
```


```powershell
uv run --python .venv\Scripts\python.exe -m simulators.cyclesim.verify_viewer
```

브라우저 검증은 임시 loopback 서버를 시작하고 종료한다. 입력·프리셋·직접
제어·핀/넷 선택·초기화·잘못된 입력·지연 응답·연결 끊김·재연결을 검사하고
1440×900, 1280×800 스크린샷과 `browser-checks.json`을
`simulators\cyclesim\build\viewer-evidence`에 남긴다.

ALU 전수검사는 **12 × 65,536 = 786,432** 입력 조합을 실제 export 배선과
생산용 칩 방정식의 비트 병렬 실행으로 평가한다. 독립 정수 산술/진리표와
B_ADD·LOGIC·SUM·C_LO·C_HI·Y를 비교하고, 일반 4상태 엔진으로 **1,056**쌍을
별도 대조한다. 이 구분은 786,432번의 HTTP 요청이나 CPU 클럭 실행을
의미하지 않는다.


## 조립용 칩 배선도와 시뮬레이션용 게이트 배선도

기본 **칩 배선도**는 TI PDIP-16 윗면 핀 번호와 홈 방향을 보여 준다.
왼쪽에서 넷을 선택하면 출발·도착 칩/핀 배선표와 연결할 핀만 강조된다.
전원(Enable GND 포함), 제어, 데이터·캐리별로 좁힐 수 있다. 외부
입력은 외부 연결점으로 표시하며, 비교 전용 프로브를 칩 핀으로 만들지 않는다.
브레드보드 중앙 홈 배치와 5 V/디커플링은 조립 시방서를 따르며,
구체적인 빵판 구멍 번호·점퍼 길이·물리 장착 검증은 포함하지 않는다.

**게이트 배선도**는 선택 비트의 두 4:1 MUX, 4비트 가산기, 출력 2:1 MUX를
펼친 기능 블록 연결이다. 선택 주소·경로와 값은 Python 관측에서 읽는다.
트랜지스터나 개별 AND/OR 수준의 내부 회로 모델은 아니다.
두 탭은 같은 넷을 선택하며, 기존 **12칩 전체 구조** 지도도 별도로 남는다.

개발 중 자동 리로드:

```powershell
uv run --python .venv\Scripts\python.exe -m simulators.cyclesim viewer --reload
```

Python 파일 변경 시 자식 서버를 다시 시작하므로 시뮬레이션 입력은 초기화된다.
HTML/CSS/JS는 서버 재시작 없이 읽고 브라우저가 변경 감지 후 새로고침한다.
서버는 계속 loopback에만 바인딩한다. `--reload`에는 0이 아닌 고정 포트를 쓴다.


## 830 빵판 배치 탐색

**830 배치 탐색** 탭에서 2–8장 빵판의 가로·세로·격자·지그재그 배열,
DIP 칩 행·방향, 칩 간 신호 경로를 비교한다. 기본은 **5장 2–2–1: 4–1 / 4–1 / 2**다.
B3·B4의 가산기를 마주 보는 끝으로 모으고 B5의 출력 MUX 두 개를 높이에 맞춘다.
보드는 돌기 결합을 전제로 **0 mm 간격으로 고정**한다.
**가산기 안쪽 여유 행**으로 칩 사이 공간을 조절하고 **가산기·출력 확대**로 확인한다.
칩 고정 후 재탐색, 보드 좌표 직접 편집, JSON 저장·불러오기, 신호 점퍼 CSV를 제공한다.
점퍼마다 번호와 별도 구멍을 배정하고, 겹친 구간·T자 접촉을 피한다.
점퍼를 선택하면 양 끝 주소를 추적하며, 짧은 끊김 표시는 접속 없는 교차를 뜻한다.
범용 830 치수·구멍 가정과 비용식, 전원/외부 배선 제외 범위는
[breadboard-explorer.md](breadboard-explorer.md)에 명시했다.

```powershell
uv run --python .venv\Scripts\python.exe -m simulators.cyclesim.verify_placement
```
