# Simulators

Developer-only hardware simulators. Not cited in `reference/**`.

## cyclesim

Functional-block cycle simulator for v1.0 **rev G dual CPLD** (CU + DP) + ALU + M3b fetch/execute.

```bash
pip install -r simulators/cyclesim/requirements-dev.txt
python -m simulators.cyclesim test
python -m simulators.cyclesim run m3b_mini.hex --ram-init 0x42=0x42
python -m simulators.cyclesim export alu8
python -m pytest simulators/cyclesim/tests -q
```

**Test timeouts:** every test has a `pytest-timeout` budget (default **30s** in [`pytest.ini`](cyclesim/pytest.ini)). Slow or hang-prone tests declare `@pytest.mark.timeout(N)` and/or CPU step caps. See [`tests/conftest.py`](cyclesim/tests/conftest.py) and **AGENTS.md** § Test timeouts.

`export alu8` writes `simulators/cyclesim/build/alu8_func.yaml`, `alu8_func.units.yaml`, `alu8_func.schematic.yaml`, and interactive **`alu8-schematic.html`** — **12 DIP** assembly (`74HC153`×8, `74HC283`×2, `74HC157`×2). Viewer expands each DIP into functional gates (153→mux1+mux2, 283→ADD4, 157→per-bit YMUX). Control nets and CMP flags are ports (CPLD / observe); no behavioral glue instances. Open the HTML in a browser (no server).

Blocks: **CpldCu** (LUT + TFR + G-IC), **CpldDp** (GPR + TFR mux), Idx5Decoder, PhaseCounter, ALU8, PC/IR/MBR, memory array.

Normative source: `reference/hardware/`, `reference/hw-bringup/M3a`, `M3b`.

CPLD JTAG toolchain (active): [cpld/tools/README.md](../cpld/tools/README.md). WinCUPL HDL tests: `archive/cpld-rev-g-hdl.tar.gz`.

## Strobe layers (rev G dual)

| Layer | Chip | Signals | Verified by |
|-------|------|---------|-------------|
| **LUT** | CPLD-CU | `reg_we_lut`, `w_sel*_lut`, SoC strobes | `test_cpld_dual.py` |
| **G-IC** | CU → DP | `reg_we`, `w_sel*`, `tfr_valid`, `src[1:0]` | `test_cpld_dual.py` |
| **Merged / bench** | SoC boundary | `net_reg_we`, `net_w_sel*`, `bctrl0..3` | `test_cpu_m3b.py` |

Merge rules: [control-and-decode.md](../reference/hardware/control-and-decode.md) §6.

## Parity matrix (functional)

Golden: `simulators/cyclesim/data/{isa,fsm_table}.py`. Timing (2 MHz) is **bench-only** — not simulated.

| Area | fsm_table | dual CU/DP | CpuM3b e2e | Breadboard |
|------|-----------|------------|--------------|------------|
| idx5 FSM (20 rows) | source | `test_fsm_idx5` | macro tests | M3a §4 |
| TFR comb + G-IC | `isa.py` | `test_cpld_dual` | `test_tfr_*` | M2a |
| LUT vs legacy merge | rows | `test_merged_equals_legacy_*` | — | — |
| ALU macro ops | ALU rows | — | `test_alu8`, ADD/CMP ph1 | M1 |
| Instruction fetch | — | — | `test_fetch_nets` | M3b F1–F3 |
| BEQ / JMP branch | rows | `BranchAnd` | `test_beq_*`, fib | M3b F5 |
| LDA / STA / CMP | rows | — | `test_m3b_mini` | M3b F4 |
| LDIO / STIO / mailbox | rows | — | `test_ldio_stio_mailbox` | M2b |
| 2 MHz timing | — | — | — | scope |

Full regression: `python -m pytest simulators/cyclesim/tests -q` (requires `pytest-timeout`; see `simulators/cyclesim/requirements-dev.txt`)

Pre-flash gate (Windows + WinCUPL): restore `archive/cpld-rev-g-hdl.tar.gz`, then `cpld/hdl/verify-cpld.ps1`.
