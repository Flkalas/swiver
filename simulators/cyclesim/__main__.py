"""CLI entry: python -m simulators.cyclesim"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from simulators.cyclesim.export.alu8_netlist import export_alu8_func
from simulators.cyclesim.program import ProgramRunner

FIXTURES = Path(__file__).resolve().parent / "fixtures"
CYCLESIM_ROOT = Path(__file__).resolve().parent
DEFAULT_BUILD = CYCLESIM_ROOT / "build"


def cmd_run(args: argparse.Namespace) -> int:
    runner = ProgramRunner()
    hex_path = Path(args.rom)
    if not hex_path.is_file():
        hex_path = FIXTURES / args.rom
    runner.load_rom_hex(hex_path, base=args.base)
    if args.ram_init:
        for pair in args.ram_init.split(","):
            addr_s, val_s = pair.split("=")
            runner.load_ram(int(addr_s, 0), int(val_s, 0))
    runner.reset(pc=args.pc)
    steps = runner.run_until_halt(max_steps=args.max_steps)
    print(f"steps={steps} halted={runner.halted} pc=0x{runner.pc:04X}")
    print(f"R0=0x{runner.r0:02X}")
    return 0 if runner.halted else 1


def cmd_test(_: argparse.Namespace) -> int:
    import pytest

    cyclesim_tests = Path(__file__).resolve().parent
    return pytest.main([str(cyclesim_tests / "tests"), "-q", "-c", str(cyclesim_tests / "pytest.ini")])


def cmd_export_alu8(args: argparse.Namespace) -> int:
    out = Path(args.output) if args.output else DEFAULT_BUILD / "alu8_func.yaml"
    units = Path(args.units) if args.units else DEFAULT_BUILD / "alu8_func.units.yaml"
    schematic = (
        Path(args.schematic) if args.schematic else DEFAULT_BUILD / "alu8_func.schematic.yaml"
    )
    viewer = Path(args.viewer) if args.viewer else DEFAULT_BUILD / "alu8-schematic.html"
    if args.no_units:
        units = None
    if args.no_schematic:
        schematic = None
    if args.no_viewer:
        viewer = None
    nl, up, sc, vw = export_alu8_func(out, units, schematic, viewer)
    print(f"wrote {nl}")
    if up:
        print(f"wrote {up}")
    if sc:
        print(f"wrote {sc}")
    if vw:
        print(f"wrote {vw}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="simulators.cyclesim")
    sub = parser.add_subparsers(dest="cmd", required=True)

    run_p = sub.add_parser("run", help="Run ROM program until HALT")
    run_p.add_argument("rom", help="ROM hex file or fixture name")
    run_p.add_argument("--pc", type=lambda x: int(x, 0), default=0)
    run_p.add_argument("--base", type=lambda x: int(x, 0), default=0)
    run_p.add_argument("--max-steps", type=int, default=500)
    run_p.add_argument("--ram-init", default="", help="addr=val,... e.g. 0x42=0x42")
    run_p.set_defaults(func=cmd_run)

    test_p = sub.add_parser("test", help="Run pytest suite")
    test_p.set_defaults(func=cmd_test)

    exp_p = sub.add_parser("export", help="Export netlists")
    exp_sub = exp_p.add_subparsers(dest="export_target", required=True)
    alu_p = exp_sub.add_parser("alu8", help="Export alu8 functional-block netlist")
    alu_p.add_argument("-o", "--output", help="Netlist YAML path")
    alu_p.add_argument("--units", help="Units catalog YAML path")
    alu_p.add_argument("--no-units", action="store_true", help="Skip units file")
    alu_p.add_argument(
        "--schematic",
        help="Schematic layout YAML path (default: build/alu8_func.schematic.yaml)",
    )
    alu_p.add_argument("--no-schematic", action="store_true", help="Skip schematic file")
    alu_p.add_argument(
        "--viewer",
        help="Interactive gate viewer HTML (default: build/alu8-schematic.html)",
    )
    alu_p.add_argument("--no-viewer", action="store_true", help="Skip HTML viewer")
    alu_p.set_defaults(func=cmd_export_alu8)

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
