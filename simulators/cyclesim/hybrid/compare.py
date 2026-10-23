"""Run the byte-bus candidate and export counts plus architectural comparisons."""
import argparse
import hashlib
import json
from pathlib import Path

from simulators.cyclesim.cpu import CpuM3b
from simulators.cyclesim.fixtures.rom_builder import build_fib_to_limit_rom, build_fib_recursive_rom
from simulators.cyclesim.hybrid.cpu import HybridCpu
from simulators.cyclesim.hybrid.hardware import manifest


def paired(blob, ram=None, *, base=0, map_mode=1, r0=0, flags=0):
    h, ref = HybridCpu(), CpuM3b()
    for mem in (h.mem, ref.mem.sys):
        mem.map_mode = map_mode
        mem.load_bytes(base, blob, target="ram" if map_mode else "rom")
        mem.ram.update(ram or {})
    h.reset(base)
    ref.reset(base)
    h.dp["R0"] = ref.gpr.regs[0] = r0
    h.z = ref.flg.z = bool(flags & 1)
    h.c = ref.flg.c = bool(flags & 2)
    return h, ref


def compare_instruction(h, ref, *, wait_every=0):
    start = len(h.accesses)
    h.step_instruction(wait_every=wait_every)
    accesses = []
    for _ in range(20):
        ref.step()
        t = ref.last_trace
        if t.bus_access:
            b = t.bus_access
            accesses.append((b.kind, b.address, b.value))
        if t.retired or ref.halted: break
    else: raise AssertionError("reference instruction cap")
    assert (h.pc, h.r0, h.z, h.c, h.halted, h.fault) == (
        ref.pc.pc, ref.gpr.qa(), ref.flg.z, ref.flg.c, ref.halted, ref.fault)
    assert h.accesses[start:] == accesses
    assert (h.mem.ram, h.mem.rom, h.mem.mailbox) == (ref.mem.sys.ram, ref.mem.sys.rom, ref.mem.sys.mailbox)


def run_pair(h, ref, *, wait_every=0, cap=10000):
    for _ in range(cap):
        if h.halted: return
        compare_instruction(h, ref, wait_every=wait_every)
    raise AssertionError("program instruction cap")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("simulators/cyclesim/build/hybrid"))
    args = parser.parse_args()
    b, ram, expected, _ = build_fib_to_limit_rom(250)
    cases = [("fib_iterative", b, ram, expected)]
    for n in (3, 8):
        b, ram, expected = build_fib_recursive_rom(n)
        cases.append((f"fib_recursive_{n}", b, ram, expected))
    cases.append(("add_256", bytes([1, 1]) * 256 + bytes([10]), {}, 0))
    rows = []
    for name, b, ram, expected in cases:
        h, ref = paired(b, ram)
        run_pair(h, ref)
        assert h.r0 == expected and not h.fault
        rows.append(dict(name=name, r0=h.r0, instructions_including_halt=h.retired,
                         transfers=h.transfers, candidate_ticks=h.ticks, reference_sys=ref.sys_ticks,
                         mips_at_assumed_2mhz=2 * (h.retired - 1) / h.ticks,
                         architectural_state_and_memory_access_sequence_equal=True))
    report = dict(cases=rows, variants={"two_1504": manifest(False), "two_1504_plus_1502": manifest(True)},
                  source_sha256={str(p): hashlib.sha256(p.read_bytes()).hexdigest()
                                 for p in Path(__file__).parent.glob("*.py")})
    # Accept fit evidence only when it corresponds to the current generators.
    from simulators.cyclesim.hybrid.fit_blocks import dp_source, decode_source
    fit_path = args.output.parent / "hybrid-fit/summary.json"
    if fit_path.exists():
        fit = json.loads(fit_path.read_text(encoding="utf-8"))
        for name, source in (("bytedp", dp_source()), ("bytedec", decode_source())):
            if fit.get(name, {}).get("source_sha256") != hashlib.sha256(source.encode("ascii")).hexdigest():
                raise ValueError("Stale fit evidence: rerun hybrid.fit_blocks")
        report["block_fit_evidence"] = fit
        report["full_cu_fit"] = "not implemented"
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "comparison.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    for row in rows: print(json.dumps(row))
    for name, variant in report["variants"].items():
        print(name, variant["total_ic"], variant["part_totals"])


if __name__ == "__main__": main()
