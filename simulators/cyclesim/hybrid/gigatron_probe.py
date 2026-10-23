"""Measure existing byte-bus overhead; this is not an optimized CPU or fit result."""
from collections import Counter
import hashlib
import json
from pathlib import Path

from simulators.cyclesim.fixtures.rom_builder import build_fib_to_limit_rom, build_fib_recursive_rom
from simulators.cyclesim.hybrid.compare import paired, run_pair
from simulators.cyclesim.hybrid.cpu import HybridCpu
from simulators.cyclesim.hybrid.cu_fsm import graph


class ProfiledCpu(HybridCpu):
    def _adjust(self, prefix, amount):
        self.adjust_calls[prefix] += 1
        for transfer in super()._adjust(prefix, amount):
            self.adjust_transfers[prefix] += 1
            if (transfer.source == "CU" and transfer.destination == "MBR"
                    and transfer.constant == 1):
                self.unit_constant_loads[prefix] += 1
            yield transfer


def measure():
    cases = []
    for name, fixture in [("fib_iterative", build_fib_to_limit_rom(250)),
                          ("fib_recursive_3", build_fib_recursive_rom(3)),
                          ("fib_recursive_8", build_fib_recursive_rom(8))]:
        blob, ram, expected = fixture[:3]
        cases.append((name, blob, ram, expected))
    cases.append(("add_256", bytes([1, 1]) * 256 + bytes([10]), {}, 0))
    rows = []
    for name, blob, ram, expected in cases:
        cpu, reference = paired(blob, ram)
        cpu.__class__ = ProfiledCpu
        cpu.adjust_calls = Counter()
        cpu.adjust_transfers = Counter()
        cpu.unit_constant_loads = Counter()
        run_pair(cpu, reference, cap=10000)
        assert cpu.r0 == expected and not cpu.fault
        unit_loads = sum(cpu.unit_constant_loads.values())
        rows.append(dict(name=name, transfers=cpu.transfers, ticks=cpu.ticks,
                         adjust_calls=dict(cpu.adjust_calls),
                         adjust_transfers=dict(cpu.adjust_transfers),
                         unit_constant_loads=dict(cpu.unit_constant_loads),
                         unit_constant_load_ticks=4 * unit_loads,
                         unit_constant_load_tick_fraction=4 * unit_loads / cpu.ticks,
                         state_and_all_memory_accesses_match=True))
    g = graph()
    counts = Counter(t for t, _ in g.nodes)
    repeated = sum(n for t, n in counts.items() if t and t.source == "CU"
                   and t.destination == "MBR" and t.constant == 1)
    root = Path(__file__).resolve().parents[3]
    paths = [Path(__file__), Path(__file__).with_name("cpu.py"),
             Path(__file__).with_name("cu_fsm.py"), Path(__file__).with_name("compare.py"),
             root / "simulators/cyclesim/fixtures/rom_builder.py"]
    return dict(scope="Profile of unchanged HybridCpu, no WAIT; no counter or INC/DEC replacement implemented",
                graph_states=len(g.nodes), unique_transfer_or_stop_entries=len(counts),
                unit_constant_load_states=repeated, cases=rows,
                interpretation="Removing unit-constant loads requires new ALU controls and CU fit; measured fraction is removable-work opportunity, not achieved speedup or MC reduction",
                source_sha256={p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                               for p in paths})


if __name__ == "__main__":
    report = measure()
    target = Path("simulators/cyclesim/build/hybrid/gigatron-profile.json")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
