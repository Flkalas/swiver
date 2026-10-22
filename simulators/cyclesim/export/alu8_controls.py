"""Generate ALU reference tables from the single Python preset definition.

Run with --write to minimally replace the current on-disk tables, or --check
to detect documentation drift. Existing text outside the table is preserved.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from simulators.cyclesim.blocks.alu8 import ALU_PRESETS, eval_alu8

ROOT = Path(__file__).resolve().parents[3]


def control_table() -> str:
    lines = ["| sel | Op | cin | bctrl3:0 | s1:s0 | lgc3:0 |",
             "|-----|-----|-----|----------|-------|--------|"]
    for i, (op, c) in enumerate(ALU_PRESETS.items()):
        lines.append(f"| {i} | {op} | {c.cin} | {c.bctrl:04b} | {c.s1}{c.s0} | {c.lgc:04b} |")
    return "\n".join(lines)


def bench_table() -> str:
    lines = ["| sel | `alu_op` | Op | A | B | cin | bctrl | s1 | s0 | lgc | Y | Y LEDs y7..y0 | Fixed ties |",
             "|-----|----------|-----|---|---|-----|-------|----|----|-----|---|---------------|------------|"]
    for i, (op, c) in enumerate(ALU_PRESETS.items()):
        a, b = 0x12, 0x34
        y = eval_alu8(a, b, c).y
        values = {"cin": c.cin, "153_s0": c.s0, "153_s1": c.s1}
        values.update({f"bctrl{j}": c.bctrl >> j & 1 for j in range(4)})
        values.update({f"lgc{j}": c.lgc >> j & 1 for j in range(4)})
        ties = "; ".join(f"{label}: " + ", ".join(k for k, v in values.items() if v == value)
                         for label, value in (("GND", 0), ("VCC", 1)) if value in values.values())
        lines.append(f"| {i} | `{i:X}` | **{op}** | `{a:02X}` | `{b:02X}` | {c.cin} | `{c.bctrl:04b}` | {c.s1} | {c.s0} | `{c.lgc:04b}` | `{y:02X}` | `{y:08b}` | {ties} |")
    return "\n".join(lines)


def logic_table() -> str:
    notes = {"NOP": "logic=0; sum 선택이므로 물리 Y=A, CPU hold", "AND": "A&B",
             "OR": "A\\|B", "XOR": "A^B", "NOT": "~A, B 무관",
             "PASS_A": "A, B 무관", "PASS_B": "B, A 무관"}
    lines = ["| Op | lgc0 | lgc1 | lgc2 | lgc3 | Notes |",
             "|----|------|------|------|------|-------|"]
    for op, note in notes.items():
        bits = " | ".join(str(ALU_PRESETS[op].lgc >> i & 1) for i in range(4))
        lines.append(f"| {op} | {bits} | {note} |")
    lines.append("| ADD/SUB/INC/DEC/CMP | * | * | * | * | Unused; `157_YBP` selects **sum** |")
    return "\n".join(lines)


def updates():
    for name, heading, prefix, table in (
        ("reference/hardware/alu-opcodes-timing.md", "## 2. 제어 신호", "| sel |", control_table()),
        ("reference/hw-bringup/b3-opcode.md", "## 12 opcodes", "| sel |", bench_table()),
        ("reference/hardware/alu8-phase-b.md", "### Opcode → C0..C3", "| Op |", logic_table()),
        ("reference/hardware/alu8-phase-b.md", "## mux1 logic table", "| sel |",
         "| sel | A | B | Result |\n|-----|---|---|--------|\n" +
         "\n".join(f"| {i} | {i & 1} | {i >> 1} | C{i} |" for i in range(4))),
    ):
        path = ROOT / name
        original = path.read_text(encoding="utf-8")
        start = original.index(prefix, original.index(heading))
        end = original.index("\n\n", start)
        yield path, original, original[:start] + table + original[end:]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    stale = []
    for path, before, after in updates():
        if before != after:
            stale.append(path)
            if args.write:
                path.write_text(after, encoding="utf-8", newline="\n")
        print(f"{'updated' if args.write and before != after else 'drift' if before != after else 'OK'}: {path}")
    return 1 if stale and not args.write else 0


if __name__ == "__main__":
    raise SystemExit(main())
