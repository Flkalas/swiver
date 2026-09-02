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
