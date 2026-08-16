# Agent instructions (Swiver)

Repository-wide guidance for coding agents. Cursor users: local mirrors in `.cursor/rules/` (`git-workflow-safety.mdc`, `korean-markdown-encoding.mdc`, `read-on-disk-only.mdc`; `.cursor/` is gitignored).

---

## Git workflow safety

### Commits after work units

When a **plan, user message, or session goal** says to finish with commits (e.g. “의미 단위 커밋”, “작업 단위가 끝나면 커밋”), **commit before ending the turn** — do not leave completed work uncommitted.

Split into **separate commits** when changes belong to different concerns (e.g. UTF-8 recovery vs a new feature).

### Plan execution (auto-commit)

When **implementing an attached Cursor plan** (`.plan.md` with todos — e.g. “Implement the plan as specified”):

- **Commit without a separate “커밋하세요” request** — plan execution is sufficient permission.
- Finish with commits **before ending the turn** when plan todos are done (or at each logical unit if the plan lists “권장 커밋 단위”).
- Follow the plan’s suggested commit splits when present; otherwise split by concern (netlist/sim, decode/tests, units, docs).
- Exclude unrelated dirty files (e.g. fixtures touched by another task) unless the plan covers them.

For work **outside** an active plan, only commit when the user asks or the session goal explicitly requires it.

### Never run without explicit user request

- `git checkout -- .` or `git restore .` on tracked files (especially Korean markdown)
- `git reset --hard`
- Bulk encoding replace on `docs/**/*.md`

### Korean / UTF-8 markdown — no StrReplace; preserve user edits

On Windows this repo’s Hangul markdown is repeatedly corrupted by partial edits **and** by agents rewriting whole files from memory (wiping the user’s Qty/wording).

**Do not** use the `StrReplace` tool on:

- `reference/**/*.md`
- `plover-whitepaper.md`
- `AGENTS.md` when the edit touches Hangul
- any other tracked `.md` that contains Korean

**Do not** pipe those files through PowerShell `Set-Content` / `Out-File` without `utf8` (prefer Python).

**Do not** restore older assistant wording over the user’s edits (examples: forcing Breadboard Qty `4`, re-adding `830-pin`, changing `` `IF\|EX` `` back to `` `IF|EX` ``).

**Do:**

1. Read the **current on-disk** file first.
2. Apply **only** the change requested this turn.
3. If a full rewrite is required for UTF-8 safety: load → mutate → write (never paste an old chat draft).

```python
path = Path(...)
text = path.read_text(encoding="utf-8")
# minimal mutation only
path.write_text(text, encoding="utf-8", newline="\n")
```

After writing, verify Hangul still decodes. Local mirror: `.cursor/rules/korean-markdown-encoding.mdc` (`alwaysApply: true`).

### Commit procedure

1. `git status` and `git diff` — confirm scope
2. Stage only files for **one** logical unit
3. Commit with a clear message (why, not a file list)
4. Repeat until the working tree is clean for finished work
5. Run relevant tests before feature commits when applicable

### When unsure

If the user asked for commits in the **same thread or plan**, treat that as permission for those commits. If scope is mixed, **split commits** rather than skipping.

When implementing a **Cursor plan**, commit in-session per **Plan execution (auto-commit)** above — do not defer to a later turn or wait for an extra commit message from the user.

---

## Brand / package rename

- **Document brand:** **Swiver** — see [reference/project/naming.md](reference/project/naming.md).
- **Do not** bulk-rename `plover_*` packages, modules, or format magics (`.PLR`, `PL-DOS`, etc.) in one shot.
- When you **actually edit** a still-`plover_*` package or module, migrate that unit to `swiver_*` (or the agreed prefix) **in the same work unit**, and update related docs/identifiers/links with it.
- **GitHub remote:** [Flkalas/swiver](https://github.com/Flkalas/swiver). Do not change the remote again until the user explicitly asks.
- Keep existing Hangul / UTF-8 markdown rules above.

## Test timeouts (cyclesim and new pytest suites)

**Mandatory** for `simulators/cyclesim/tests/**` and any **new** pytest tree in this repo:

1. **Install** `pytest-timeout` (`simulators/cyclesim/requirements-dev.txt`).
2. **Default** per-test wall limit: **30s** via `simulators/cyclesim/pytest.ini` (`timeout_method = thread` for Windows).
3. **Every new test** must either stay well under 30s or carry an explicit `@pytest.mark.timeout(N)` with margin over measured runtime.
4. **CPU integration tests** (`ProgramRunner`, `CpuM3b.step` loops):
   - Prefer `run_until_halt` (autouse **15s** wall cap in `conftest.py`).
   - Any manual `while not runner.halted` **must** include a **step counter** assert (no unbounded spin).
   - Infinite-loop guards (e.g. `test_jmp_to_zero`): bounded steps **and** `@pytest.mark.timeout(10)` or similar.
5. **Register slow tests** in `TIMEOUT_OVERRIDES_S` in [`simulators/cyclesim/tests/conftest.py`](simulators/cyclesim/tests/conftest.py) when adding hang-prone cases.
6. **`conftest.py` fails fast** if `pytest-timeout` is missing — do not disable this check.

Agents adding tests: run the suite locally; if a test needs >30s, document why in the test docstring and set the mark.

---

## On-disk read only (no index / cache)

For architecture, ISA, decode, CPLD, Flash, ALU, bring-up, BOM, MMIO, or any normative claim about this repo:

1. **Read the current on-disk file** with the Read tool before answering or editing.
2. Treat **codebase index / semantic search / RAG snippets**, **chat cache**, and **prior-session memory** as non-authoritative — never cite them as truth.
3. Glob/Grep may **locate** paths only; content must come from a fresh Read in the same turn.
4. Local mirror: `.cursor/rules/read-on-disk-only.mdc` (`alwaysApply: true`).

If you have not Read it this turn, you do not know it.

---

## Document tiers (truth cascade)

When answering **hardware architecture**, **bring-up**, or **decode/CPLD/ALU** questions, edit and cite in this order:

| Tier | Path | Role |
|------|------|------|
| **Root** | [plover-whitepaper.md](plover-whitepaper.md) §6 | ISA / FSM narrative |
| **Reference** | `reference/**` | Normative detail, bring-up, frozen fixtures |
| **Machine** | `simulators/cyclesim/data/isa.py`, `fsm_table.py` | Executable golden |
| **CPLD** | `cpld/tools/` — WinCUPL, OpenOCD, JTAG probe | Toolchain (active); HDL archived |
| **Archive** | `archive/*.tar.gz` (+ [MANIFEST.md](archive/MANIFEST.md)) | Historical — **do not** cite for SoC unless user asks |

**Anchor docs:** [cpld-pipe-cu.md](reference/hardware/cpld-pipe-cu.md), [control-and-decode.md](reference/hardware/control-and-decode.md), [system-architecture.md](reference/hardware/system-architecture.md), [plover-whitepaper.md](plover-whitepaper.md).

**Active hardware truth:** whitepaper root → reference cascade → machine code → CPLD artifacts. **v1.0 normative = P12** (IF\|EX pipe CU, PROG∥DATA intent, R0/AC + MBR→ALU B, TFR removed, G-IC 1-wire, no idle). **Gi1** (idx5 multiphase) is archived — `archive/gi1-v1.0-normative.tar.gz`. **rev G** (3-GPR·TFR) is archived — `archive/rev-g-dual-3gpr.tar.gz`. Restore guide: [archive/MANIFEST.md](archive/MANIFEST.md).

**Strobe layers:** LUT/csim tests may still use Gi1-era `reg_we_lut` / multiphase tables — treat as **legacy golden lag**. Bench merged pin `net_reg_we`. Active reference tables describe **P12 pipe** behavior ([cpld-pipe-cu.md](reference/hardware/cpld-pipe-cu.md)).

**MC policy:** ATF1504 **64 macrocell** is a BOM chip rating only. Bring-up gate = WinCUPL **Design fits** — do not record fitter used-MC counts in normative prose. Pipe CU PLD is **Design fits pending**.

**Forbidden for SoC / bring-up answers** (unless user asks for history):

- Citing or executing restored content from `archive/*.tar.gz` or restored `cpld/` HDL/fit-study trees
- Treating **`alu8_decode`** as the breadboard decode path
- Flash **`$4000`** control-word burn, **`cpu_cw_direct`**, pareto MC as v1.0 gates
- Treating **Gi1 idx5 idle phases** as Active v1.0 schedule

**No feasibility from archived sim** — timing and fit use reference frozen numbers ([alu-opcodes-timing.md](reference/hardware/alu-opcodes-timing.md), [cpld-pipe-cu.md](reference/hardware/cpld-pipe-cu.md) §7) and lab checklists.

**Do not** implement bring-up or reference edits based on archived tarball content unless the user explicitly requests historical comparison.

**Stale terms** (after 2026-07 P12 adoption): Gi1 **idx5 multiphase idle** as Active, `inc_en`, `INC_B_SEL`, `INC_2C2`, `14 IC` for ALU BOM, `b_sel`/`b_const_sel` as SoC signal names (use `net_bctrl0..3`), **`cpld_3fixed` / rev G normative**, **`tfr_valid` / TFR opcodes** as v1.0 (reserved `0x10–0x1F`).
