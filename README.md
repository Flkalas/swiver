# Swiver

74HC discrete-logic 8-bit breadboard CPU — **v1.0 sequential** (non-pipelined in-order CU, unified 64 KiB memory/shared instruction-data bus, RAM execution, R0 + MBR→ALU B, 12-DIP alu8).

| Start | Document |
|-------|----------|
| **Overview** | [swiver-whitepaper.md](swiver-whitepaper.md) |
| **Naming** | [reference/project/naming.md](reference/project/naming.md) |
| **Specs + L0→L10 ladder** | [reference/README.md](reference/README.md) |
| **Bring-up** | [reference/hw-bringup/README.md](reference/hw-bringup/README.md) |
| **Active CU** | [reference/hardware/cpld-sequential-cu.md](reference/hardware/cpld-sequential-cu.md) |

## 실행 방법 (Windows PowerShell)

74HC로 제어·데이터패스를 구성한 전체 CPU 실험과 기존 기능 모델의 비교는
[74HC CPU 비교 안내](simulators/cyclesim/ttl/README.md)를 참고한다.
가상환경 설치 후 `.\.venv\Scripts\python.exe -X utf8 -m simulators.cyclesim.ttl.compare`로 실행한다.

아래 명령은 **저장소 루트**에서 실행한다. 설치 위치가 다르면 첫 경로를 바꾼다.
Python 3.12와 `uv` 명령을 사용하며, 기존 `uv.toml`의 `link-mode = "symlink"`는 유지한다.

```powershell
Set-Location D:\Github\swiver

# 최초 1회: .venv가 없을 때만 생성
if (-not (Test-Path .venv\Scripts\python.exe)) {
    uv venv --python 3.12 .venv
}

# 테스트까지 사용할 개발 환경 설치
uv pip install --python .venv\Scripts\python.exe -r simulators\cyclesim\requirements-dev.txt
```

뷰어 서버 자체는 Python 표준 라이브러리로 동작한다. Playwright 설치는 아래의
브라우저 자동 검증을 실행할 때만 필요하다.

### 1. 일반 실행

```powershell
uv run --python .venv\Scripts\python.exe -m simulators.cyclesim viewer
```

브라우저 또는 Orca 브라우저에서 **http://127.0.0.1:8765/** 를 연다.
화면에서 **CPU 전체 연결도**, **ALU 칩 배선도**, **게이트 배선도**, **830 배치 탐색**,
**ALU 12칩 전체 구조**를 선택한다. 빵판 탐색기도 같은 서버에서 사용하므로 별도 실행 명령은 없다.
실행한 터미널에서 `Ctrl+C`를 누르면 종료된다.

**CPU 전체 연결도 바로 열기:** [35칩 구성](http://127.0.0.1:8765/?view=cpu&variant=35),
[29칩 구성](http://127.0.0.1:8765/?view=cpu&variant=29),
[24칩 구성](http://127.0.0.1:8765/?view=cpu&variant=24).
화면 오른쪽 위에서 구성을 전환하고, 버스 → 비트 → 연결된 칩의 핀 순서로 따라간다.
칩을 누르면 기능 핀별 연결표가 나온다. 검색, 신호 종류 필터, 드래그 이동,
확대/축소, 선택 확대와 연결표 JSON 다운로드를 지원한다.

이 화면은 [실험용 RAM ISA의 두 CPLD 비교](simulators/cyclesim/hybrid/ram-educational.md)에
사용한 연결표다. CPLD 신호 핀은 저장된 vendor fit의 PLCC44 번호를 표시하고,
74·메모리는 기능 핀명을 표시한다. 논리 연결과 칩/단자 수를 보는 화면이며,
CPU 실행 파형·실제 점퍼 배치·보드 타이밍은 표시하지 않는다.

### 2. 수정하면서 실행 — 자동 리로드

```powershell
uv run --python .venv\Scripts\python.exe -m simulators.cyclesim viewer --reload
```

Python 파일이 바뀌면 서버를 다시 시작하고 시뮬레이션 입력을 초기화한다.
HTML/CSS/JavaScript 변경도 브라우저에서 감지해 새로고침한다.

### 3. 다른 포트로 실행

기본 8765 포트를 이미 사용 중이거나 다른 세션을 따로 열 때 사용한다.

```powershell
uv run --python .venv\Scripts\python.exe -m simulators.cyclesim viewer --port 8766 --reload
```

접속 주소는 **http://127.0.0.1:8766/** 이다. `--reload`는 생략할 수 있다.
서버는 로컬 컴퓨터의 `127.0.0.1`에만 바인딩한다. 같은 서버를 연 여러 탭은
ALU 상태를 공유하며, 다른 포트로 실행한 서버는 별도 상태를 가진다.

### 4. uv 대신 .venv의 Python으로 실행

가상환경을 이미 만들었다면 활성화 없이 직접 실행할 수 있다.

```powershell
.\.venv\Scripts\python.exe -m simulators.cyclesim viewer --reload
```

가상환경을 활성화해서 사용하는 방법도 있다.

```powershell
.\.venv\Scripts\Activate.ps1
python -m simulators.cyclesim viewer --reload
# 서버를 Ctrl+C로 종료한 뒤 가상환경에서 나오기
deactivate
```

PowerShell 실행 정책 때문에 `Activate.ps1`이 막히면 위의 Python 직접 실행 방법을 쓴다.

### 5. 백그라운드 실행 — 창 숨김, 자동 리로드, 로그 저장

다음 예제는 8766 포트로 실행한다. 이미 사용 중이면 `--port` 값과 접속 주소를
함께 바꾼다. 이 블록은 서버 한 개를 새로 시작하므로 중복 실행하지 않는다.

```powershell
$viewerRoot = (Get-Location).Path
$viewerPython = (Resolve-Path .venv\Scripts\python.exe).Path
$viewerLogs = Join-Path $viewerRoot 'simulators\cyclesim\build'
New-Item -ItemType Directory -Path $viewerLogs -Force | Out-Null

$viewerProcess = Start-Process -FilePath $viewerPython -ArgumentList @(
    '-u', '-m', 'simulators.cyclesim', 'viewer', '--port', '8766', '--reload'
) -WorkingDirectory $viewerRoot -WindowStyle Hidden -PassThru `
  -RedirectStandardOutput (Join-Path $viewerLogs 'viewer.stdout.log') `
  -RedirectStandardError (Join-Path $viewerLogs 'viewer.stderr.log')

$viewerProcess.Id
```

브라우저에서 **http://127.0.0.1:8766/** 을 연다. 로그 확인:

```powershell
Get-Content (Join-Path $viewerLogs 'viewer.stdout.log') -Tail 30
Get-Content (Join-Path $viewerLogs 'viewer.stderr.log') -Tail 30
```

**같은 PowerShell 세션**에서 다음 명령으로 방금 시작한 프로세스와 자식 서버를
함께 종료한다. `$viewerProcess`는 해당 실행의 프로세스이므로 이 변수를 유지한다.

```powershell
if (-not $viewerProcess.HasExited) {
    taskkill /PID $viewerProcess.Id /T /F
}
```

### 6. 테스트와 브라우저 검증

```powershell
# 전체 시뮬레이터 테스트
uv run --python .venv\Scripts\python.exe -m simulators.cyclesim test

# 빵판 배치·점퍼 경로 테스트만 실행
uv run --python .venv\Scripts\python.exe -m pytest simulators/cyclesim/tests/test_breadboard.py simulators/cyclesim/tests/test_wire_router.py -q
```

브라우저 자동 검증은 최초 1회 Playwright와 Chromium을 설치한 뒤 실행한다.

```powershell
uv pip install --python .venv\Scripts\python.exe -r simulators\cyclesim\requirements-viewer-dev.txt
uv run --python .venv\Scripts\python.exe -m playwright install chromium

# CPU 전체 연결도 / ALU 뷰어 / 830 배치 탐색기 검증
uv run --python .venv\Scripts\python.exe -m simulators.cyclesim.verify_cpu_viewer
uv run --python .venv\Scripts\python.exe -m simulators.cyclesim.verify_viewer
uv run --python .venv\Scripts\python.exe -m simulators.cyclesim.verify_placement
```

검증 명령은 임시 로컬 서버를 직접 열고 닫는다. 스크린샷과 결과는
ALU는 `simulators\cyclesim\build\viewer-evidence`, CPU 연결도는
`simulators\cyclesim\build\cpu-viewer-evidence`에 저장한다.

### 7. CPU 예제 프로그램 실행 (CLI)

```powershell
uv run --python .venv\Scripts\python.exe -m simulators.cyclesim run m3b_mini.hex --ram-init 0x42=0x42 --max-steps 500
```

ROM fixture를 실행하고 HALT 여부·실행 단계 수·PC·R0를 출력한다.
이 CLI 실행은 웹 ALU 뷰어의 세션과 별개다.

### 8. 넷리스트와 정적 배선도 내보내기

```powershell
uv run --python .venv\Scripts\python.exe -m simulators.cyclesim export alu8
```

`simulators\cyclesim\build`에 `alu8_func.yaml`, `alu8_func.units.yaml`,
`alu8_func.schematic.yaml`, `alu8-schematic.html`을 생성한다.
`alu8-schematic.html`은 서버 없이 브라우저로 여는 비교용 정적 배선도다.
실시간 ALU 조작과 830 배치 탐색은 위의 `viewer` 명령을 사용한다.

명령 옵션 전체 확인:

```powershell
uv run --python .venv\Scripts\python.exe -m simulators.cyclesim --help
uv run --python .venv\Scripts\python.exe -m simulators.cyclesim viewer --help
uv run --python .venv\Scripts\python.exe -m simulators.cyclesim run --help
uv run --python .venv\Scripts\python.exe -m simulators.cyclesim export alu8 --help
```

모델 범위와 ALU 설명: [cyclesim README](simulators/cyclesim/README.md).
배치·배선 탐색 사용법: [830 빵판 배치 탐색기](simulators/cyclesim/breadboard-explorer.md).

Local build trees (`build/`, `target/`, `.venv/`) are not in git — safe to delete.
