# Swiver

74HC discrete-logic 8-bit breadboard CPU — **v1.0 P12** (IF|EX pipe CU, R0 + MBR→ALU B, 12-DIP alu8).

| Start | Document |
|-------|----------|
| **Overview** | [swiver-whitepaper.md](swiver-whitepaper.md) |
| **Naming** | [reference/project/naming.md](reference/project/naming.md) |
| **Specs + L0→L10 ladder** | [reference/README.md](reference/README.md) |
| **Bring-up** | [reference/hw-bringup/README.md](reference/hw-bringup/README.md) |
| **Active CU** | [reference/hardware/cpld-pipe-cu.md](reference/hardware/cpld-pipe-cu.md) |

## Local ALU viewer

```powershell
uv run --python .venv\Scripts\python.exe -m simulators.cyclesim viewer
```

Open `http://127.0.0.1:8765`. The Korean live viewer follows the twelve ALU
packages, using Python zero-delay simulation. Setup, validation, and model
limits: [cyclesim README](simulators/cyclesim/README.md).

Local build trees (`build/`, `target/`, `.venv/`) are not in git — safe to delete.
