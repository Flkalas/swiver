# cyclesim P12 IF|EX migration plan

## Purpose

Bring `simulators/cyclesim/` into alignment with the active v1.0 P12
hardware specification. The simulator is a pre-hardware executable model; it
must validate the documented IF|EX schedule, operand holding, stalls,
bubbles, stack assistance, and visible SYS accounting without requiring a
breadboard.

## Source of truth

Use these files in this order:

1. `swiver-whitepaper.md` sections 3 and 6.
2. `reference/hardware/cpld-pipe-cu.md`, especially sections 1-5 and 7-8.
3. `reference/hardware/microcode-spec.md`, especially sections 2-6.
4. `reference/hw-bringup/M3b-fetch-execute.md` for observable fetch and
   datapath behavior.

Do not use archived Gi1 or rev-G material as P12 behavior. Existing
`data/fsm_table.py` and its idx5 tests are explicitly legacy lag.

## Findings from the current tree

- `CpuM3b.step()` currently performs either a fetch tick or a legacy phase
  execution tick; IF and EX are not modeled as concurrent stage activity.
- `data/isa.py` exposes legacy `phase_count()` and instruction-length logic.
- The current reserved-opcode helper covers `0x10-0x1F` but does not
  explicitly identify reserved `0x0C`; the P12 decoder must handle both
  reserved cases consistently.
- `data/fsm_table.py`, `blocks/fsm.py`, and the CPLD CU blocks are keyed by
  `(opcode, phase)` and include Gi1 multiphase rows.
- Fetch currently increments PC and loads IR/MBR through separate internal
  ticks, so existing step counts are not P12 SYS counts.
- CALL/RET functional behavior exists through `ReturnStack`, but its timing is
  not represented as P12 `STACK_EX` cycles.
- Existing tests mainly assert functional results and legacy idx5 strobes;
  they do not assert IF|EX overlap, state transitions, or the P12 SYS tax.
- `pytest.ini` and `conftest.py` already provide the required 30-second test
  default, 15-second `run_until_halt` wall cap, and loop safeguards.

## Target model

### Public simulation unit

Define one public CPU advancement as one counted `CLK_SYS`/SYS tick. Each
tick emits an immutable trace record containing at least:

- SYS index and active CU state
- IF activity and program address
- EX activity and current opcode
- PC before/after
- IR, MBR, R0, and flags snapshots
- memory/MMIO read or write activity
- `reg_we`, `FLG_WE`, `PC_LOAD_EN`, and relevant ALU/bus strobes
- whether the tick retires a macro, stalls, bubbles, stretches, or falls back

Internal combinational settling and latch details may remain structural, but
must not create additional public SYS counts.

### P12 states

Implement the documented state vocabulary:

- `FILL`
- `IF_EX`
- `OPERAND_IF`
- `MEM_STALL`
- `BRANCH_BUBBLE`
- `STACK_EX`
- `STRETCH`
- `FALLBACK_FE2`

Reset enters `FILL`. Normal operation reaches `IF_EX`. A memory conflict
holds IF in `MEM_STALL`; a taken redirect squashes IF through
`BRANCH_BUBBLE`; CALL/RET use `STACK_EX`. `STRETCH` and `FALLBACK_FE2` must
be explicit modes, not implicit extra ticks.

### Instruction behavior

Implement the active core ISA from `microcode-spec.md`:

- Imm8: ADD, LDA, STA, CMP, LDIO, STIO
- Abs16: BEQ, JMP, CALL, STA16
- Implied: RET, HALT
- `0x0C` and `0x10-0x1F`: reserved/trap behavior as documented

Preserve the active datapath contract: R0 is ALU A, MBR is ALU B, ADD/CMP
hold MBR through EX, and `reg_we` always writes R0.

### SYS accounting

Encode the P12 table as executable expectations, not comments only:

| Operation | Typical SYS |
|---|---:|
| ADD/CMP cold | 2 |
| ADD/CMP steady stream | 1 |
| LDA/STA/LDIO/STIO | 3 |
| BEQ not taken | 3 |
| BEQ taken / JMP | 4 |
| CALL | 6 |
| RET | 4 |
| STA16 | 4 |
| HALT | 1 |

The implementation must make the decomposition visible: retire slot,
operand fetch, memory stall, branch bubble, stack extra, and stretch.

## Implementation stages

### 1. Define P12 data types and trace contract

- Add state, stage-activity, and SYS-trace representations.
- Define what reset, HALT, trap, and a non-retiring tick report.
- Keep trace data independent from the legacy idx5 table.

### 2. Replace legacy control lookup with P12 control intent

- Add a P12 control description for opcode class, operand format, EX action,
  memory use, redirect behavior, and stack use.
- Remove CPU dependence on `phase_count()`, `lookup_row()`, `PhaseCounter`,
  and idx5 decoding.
- Keep low-level ALU and dual-CPLD datapath blocks where their P12 behavior
  remains valid; rename or isolate legacy-only interfaces rather than
  silently giving them P12 meaning.

### 3. Implement the IF|EX scheduler

- Add an explicit fill/prime path after reset.
- Fetch the next opcode/operand on PROG while the current ALU macro executes
  when overlap is legal.
- Model operand lookahead and MBR hold for ADD/CMP.
- Model DATA ownership and one visible `MEM_STALL` for memory/MMIO operations.
- Model taken-branch squash/refetch and CALL/RET stack sequencing.
- Add explicit hooks for forced stretch and shared-bus FE2 fallback, with the
  normal path remaining PROG||DATA.

### 4. Update functional runner and fixtures

- Make `ProgramRunner.run_until_halt()` count SYS ticks.
- Update or replace fixture programs whose assumptions are tied to legacy
  phase counts.
- Preserve architectural results for R0, memory, MMIO, branches, and stack
  errors while changing only timing/control semantics.

### 5. Replace the test contract

Add focused P12 tests for:

- reset `FILL` and pipeline priming
- steady ADD/CMP one-retire-per-SYS behavior
- MBR hold during ADD/CMP EX
- operand fetch and cold-vs-steady counts
- memory/MMIO `MEM_STALL` with IF held
- BEQ taken bubble and not-taken path
- JMP/CALL/RET redirect and `STACK_EX` counts
- RET loading PC from popped stack data, never MBR
- HALT and reserved opcode handling
- explicit STRETCH and FALLBACK_FE2 traces
- full mini-program functional parity and bounded long-loop execution

Legacy idx5 tests should be removed or moved to an explicitly legacy test
module. They must not be used as the P12 acceptance gate.

### 6. Verification and documentation

- Run the cyclesim suite with the repository timeout configuration.
- Compare every opcode's trace and SYS total against
  `cpld-pipe-cu.md` section 4.
- Update `simulators/cyclesim/README.md` from “legacy lag” to its actual
  status only after the P12 tests pass.
- Record any intentional simulator abstraction or unresolved hardware
  qualification in the README; do not claim breadboard validation.

## Acceptance criteria

- No production CPU execution path depends on Gi1 idx5 phases.
- P12 state names and transitions are visible in traces.
- All typical SYS totals in the normative table have executable tests.
- Functional tests cover the full active ISA and retain bounded loop guards.
- `pytest-timeout` remains mandatory and all new tests fit the existing
  timeout policy.
- The simulator README clearly distinguishes executable P12 behavior from
  unverified physical hardware behavior.

## Non-goals

- Generating or fitting the CPLD `.pld` bitstream.
- Proving electrical timing, PROG/DATA isolation, or breadboard behavior.
- Implementing non-normative opcodes or rev-G three-GPR/TFR behavior.
- Reusing archived HDL or archived simulator schedules as an oracle.
- Preserving internal legacy phase APIs without a current consumer.

## Suggested commit units

1. Add P12 control/state/trace model and unit tests.
2. Migrate CPU scheduling and runner to SYS ticks.
3. Update functional fixtures and P12 integration tests.
4. Remove or isolate legacy acceptance tests and update simulator docs.
