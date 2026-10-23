"""Run both independent executors, compare every SYS and export evidence.

python -m simulators.cyclesim.ttl.compare --output simulators/cyclesim/build/ttl
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import time

from simulators.cyclesim.cpu import CpuM3b
from simulators.cyclesim.data.sequential import control_for
from simulators.cyclesim.fixtures.rom_builder import build_fib_recursive_rom, build_fib_to_limit_rom
from simulators.cyclesim.ttl.cpu import TtlCpu


def paired(blob, ram=None, *, base=0, map_mode=1, r0=0, flags=0, optimized=False):
    ttl, reference = TtlCpu(optimized=optimized), CpuM3b()
    for mem in (ttl.mem, reference.mem.sys):
        mem.map_mode = map_mode
        mem.load_bytes(base, blob, target="ram" if map_mode else "rom")
        mem.ram.update(ram or {})
    ttl.reset(base)
    reference.reset(base)
    ttl.set("R0", r0)
    ttl.set("FLAGS", flags)
    reference.gpr.regs[0] = r0
    reference.flg.z, reference.flg.c = bool(flags & 1), bool(flags & 2)
    return ttl, reference


def compare_step(ttl, reference, *, wait=False):
    if wait:
        ttl.request_wait()
        reference.request_wait()
    ttl.step()
    reference.step()
    if ttl.last_trace != reference.last_trace or ttl.halted != reference.halted:
        raise AssertionError(f"SYS {ttl.sys_ticks}:\n74HC: {ttl.last_trace}\nreference: {reference.last_trace}")
    if (ttl.mem.ram, ttl.mem.mailbox, ttl.mem.rom) != (
            reference.mem.sys.ram, reference.mem.sys.mailbox, reference.mem.sys.rom):
        raise AssertionError(f"memory diverged at SYS {ttl.sys_ticks}")


def run_pair(ttl, reference, *, max_steps=100_000, wall_s=60, wait_every=0):
    deadline = time.monotonic() + wall_s
    for tick in range(max_steps):
        if ttl.halted: return ttl.sys_ticks
        if time.monotonic() > deadline: raise TimeoutError("74HC differential wall cap")
        compare_step(ttl, reference, wait=bool(wait_every and tick % wait_every == 0))
    raise TimeoutError(f"74HC differential step cap {max_steps}")


def model_group_cut(circuit, removed):
    """Bookkeeping over model groups; never a realizable hybrid BOM."""
    inside = [p for p in circuit.packages if p.group in removed]
    outside = [p for p in circuit.packages if p.group not in removed]
    internal_nets = {n for p in inside for n in p.pins.values()} - {0, 1, circuit.clock_net}
    external_nets = {n for p in outside for n in p.pins.values()} - {0, 1, circuit.clock_net}
    return dict(groups=sorted(removed), inside_model_packages=len(inside),
                outside_model_packages=len(outside), is_hybrid_bom=False,
                shared_signal_nets_excluding_clock_power=len(internal_nets & external_nets),
                shared_signals=sorted(circuit.names[n] for n in internal_nets & external_nets),
                hybrid_bom_count=None, fit="not synthesized or fitted")


def benchmark(*, wait_every=0, optimized=False):
    blob, ram, target, _ = build_fib_to_limit_rom(250)
    cases = [("fibonacci_iterative_233", blob, ram, 0, target)]
    for n in (3, 8):
        blob, ram, expected = build_fib_recursive_rom(n)
        cases.append((f"fibonacci_recursive_{n}", blob, ram, 0, expected))
    cases.append(("add_stream_4096", bytes([1, 1]) * 4096 + bytes([10]), {}, 0x2000, 0))
    calls, base = 256, 0x2000
    target = base + calls * 3 + 1
    blob = bytes([6, target & 255, target >> 8]) * calls + bytes([10, 7])
    cases.append(("call_ret_pairs_256", blob, {0x0F00: 0, 0x0F01: 0xF6}, base, 0))
    results = []
    for name, blob, ram, base, expected in cases:
        ttl, reference = paired(blob, ram, base=base, optimized=optimized)
        started = time.perf_counter()
        run_pair(ttl, reference, wall_s=180, wait_every=wait_every)
        if ttl.fault or ttl.r0 != expected:
            raise AssertionError(f"{name}: incorrect mathematical result")
        # Also check independent memory outcomes, including stack restoration.
        if "recursive" in name or "call_ret" in name:
            if ttl.mem.ram[0x0F00] != 0 or ttl.mem.ram[0x0F01] != 0xF6:
                raise AssertionError("return stack not restored")
        if name == "fibonacci_iterative_233":
            if [ttl.mem.ram[a] for a in sorted(ram)] != [144, 233]:
                raise AssertionError("wrong Fibonacci memory pair")
        useful = sum(t.retired and t.ir != 10 and control_for(t.ir).name != "TRAP" for t in ttl.trace)
        result = dict(name=name, sys_ticks=ttl.sys_ticks, useful_native_instructions=useful,
                      wait_ticks=sum(t.waiting for t in ttl.trace), r0=ttl.r0,
                      mips_at_assumed_2mhz=2 * useful / ttl.sys_ticks,
                      all_sys_and_memory_equal=True,
                      program_sha256=hashlib.sha256(blob).hexdigest(),
                      host_comparison_seconds=time.perf_counter() - started)
        print(json.dumps(result), flush=True)
        results.append(result)
    return results, ttl.circuit


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("simulators/cyclesim/build/ttl"))
    parser.add_argument("--wait-every", type=int, default=0, help="Insert WAIT every N host ticks (N>=2)")
    parser.add_argument("--optimized", action="store_true", help="Map and repack 74HC gates; retain the 12-package ALU")
    args = parser.parse_args()
    if args.wait_every < 0 or args.wait_every == 1: parser.error("--wait-every must be 0 or >=2")
    if args.optimized and args.output == Path("simulators/cyclesim/build/ttl"):
        args.output = Path("simulators/cyclesim/build/ttl-optimized")
    rows, circuit = benchmark(wait_every=args.wait_every, optimized=args.optimized)
    inventory = circuit.inventory()
    netlist = circuit.export()
    source_paths = [Path(__file__).with_name(name) for name in ("cpu.py", "netlist.py", "compare.py", "optimize.py")]
    source_paths += [Path("simulators/cyclesim") / name for name in
                     ("cpu.py", "blocks/alu8.py", "blocks/adder.py", "blocks/mux.py", "values.py",
                      "export/alu8_netlist.py", "data/isa.py", "data/sequential.py", "fixtures/rom_builder.py")]
    report = dict(schema="swiver-ttl-comparison-v2", cases=rows, inventory=inventory,
                  count_scope="all_74hc_comparison_model_including_diagnostic_logic",
                  is_hybrid_bom=False, hybrid_bom_count=None,
                  source_sha256={str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in source_paths},
                  netlist_sha256=hashlib.sha256(json.dumps(netlist, sort_keys=True).encode()).hexdigest(),
                  optimization=getattr(circuit, "optimization", None),
                  total_74hc_packages=len(circuit.packages),
                  part_totals=dict(sorted(Counter(p.part for p in circuit.packages).items())),
                  model_group_cuts=None if args.optimized else {"control_only": model_group_cut(circuit, {"control"}),
                              "control_and_stack": model_group_cut(circuit, {"control", "stack"}),
                              "everything_except_alu": model_group_cut(circuit, set(inventory) - {"alu", "alu_glue"})},
                  deepest_register_paths=circuit.depth_report(),
                  assumptions=["Zero-delay four-state package equations; counts are this candidate, not a minimum BOM.",
                               "Optimized shared packages cross logical groups, so simple per-group device-cut counts are omitted for that profile.",
                               "Memory storage/MMIO devices and initial reset state remain testbench boundaries.",
                               "Same native ISA and SYS schedule; HALT/TRAP excluded from MIPS numerator, all SYS included.",
                               "2 MHz is assumed, not timing-qualified. Logic levels are not nanoseconds.",
                               "Depth paths treat register Q and DBUS as independent launch boundaries; external memory round trip and false-path pruning are omitted.",
                               "Model group cuts are bookkeeping only, not a hybrid BOM or a replacement device estimate.",
                               "Trace-only outputs and a two-bit diagnostic fault register are included; required stack guards are distinct from diagnostic reporting."])
    args.output.mkdir(parents=True, exist_ok=True)
    for filename, obj in (("comparison.json", report), ("netlist.json", netlist)):
        (args.output / filename).write_text(json.dumps(obj, indent=2) + "\n", encoding="utf-8")
    print(f"74HC packages: {len(circuit.packages)}; report: {args.output / 'comparison.json'}")


if __name__ == "__main__": main()
