"""INC/DEC byte-bus candidate; real 74 ALU, abstract CU controls, fit pending.

Keep the earlier ADD/SUB-only CPU and its fitted ROM partition as a baseline.
This step changes ALU control wiring and unit adjustments, not the CU FSM.
"""
from collections import Counter
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path

from simulators.cyclesim.blocks.mem_decode import MemSystem
from simulators.cyclesim.hybrid.cpu import HybridCpu, Transfer
from simulators.cyclesim.hybrid.compare import paired, compare_instruction
from simulators.cyclesim.fixtures.rom_builder import build_fib_to_limit_rom, build_fib_recursive_rom
from simulators.cyclesim.ttl.netlist import Circuit


@dataclass(frozen=True)
class UnitTransfer(Transfer):
    """ALU A +/- 1 using B-function constants; MBR is not read or modified."""


class IncDecCpu(HybridCpu):
    def __init__(self):
        self.mem = MemSystem()
        self.alu = Circuit()
        self.a, self.b = self.alu.bus("A", 8), self.alu.bus("B", 8)
        self.cin = self.alu.bus("ALU_CIN", 1)
        self.blo = self.alu.bus("ALU_BCTRL_LOW", 1)
        self.bhi = self.alu.bus("ALU_BCTRL_HIGH", 1)
        self.y, self.carry = self.alu.import_arithmetic_alu(
            self.a, self.b, self.cin[0], self.blo[0], self.bhi[0])
        self.alu.finalize()
        self.reset()

    def _drive(self, transfer):
        if transfer.source != "ALU":
            return super()._drive(transfer)
        unit, subtract = isinstance(transfer, UnitTransfer), transfer.subtract
        # (CIN, C0/C1, C2/C3): ADD=001, SUB=110, INC=100, DEC=011.
        cin, low, high = ((not subtract, subtract, subtract) if unit
                          else (subtract, subtract, not subtract))
        self.alu.set(self.a, self.dp[transfer.select])
        self.alu.set(self.b, self.latches["MBR"])
        for net, value in ((self.cin, cin), (self.blo, low), (self.bhi, high)):
            self.alu.set(net, int(value))
        self.alu.settle()
        return self.alu.read(self.y), bool(self.alu.read([self.carry]))

    def _unit_write(self, register, subtract):
        yield UnitTransfer("ALU", "RESULT", register, subtract=subtract)
        yield Transfer("RESULT", "DP", register)

    def _adjust(self, prefix, amount):
        if abs(amount) == 1:
            yield from self._unit_write(prefix + "_LO", amount < 0)
        else:
            yield from self._literal(abs(amount), "MBR")
            yield from self._alu_write(prefix + "_LO", "DP", amount < 0)
        propagate = not self.work_carry if amount < 0 else self.work_carry
        if propagate:
            yield from self._unit_write(prefix + "_HI", amount < 0)


def measure():
    cases = [("fib_iterative", build_fib_to_limit_rom(250)[:3]),
             ("fib_recursive_3", build_fib_recursive_rom(3)),
             ("fib_recursive_8", build_fib_recursive_rom(8)),
             ("add_256", (bytes([1, 1]) * 256 + bytes([10]), {}, 0))]
    rows = []
    for name, (blob, ram, expected) in cases:
        baseline, old_ref = paired(blob, ram)
        candidate, new_ref = paired(blob, ram, cpu_class=IncDecCpu)
        for _ in range(10000):
            assert baseline.halted == candidate.halted
            if candidate.halted:
                break
            compare_instruction(baseline, old_ref)
            compare_instruction(candidate, new_ref)
            assert baseline.accesses == candidate.accesses
        else:
            raise AssertionError("INC/DEC comparison instruction cap")
        assert candidate.r0 == baseline.r0 == expected
        assert not candidate.fault and candidate.retired == baseline.retired
        saved = baseline.ticks - candidate.ticks
        rows.append(dict(name=name, baseline_ticks=baseline.ticks, candidate_ticks=candidate.ticks,
                         saved_ticks=saved, reduction_fraction=saved / baseline.ticks,
                         instructions_including_halt=candidate.retired,
                         mips_at_assumed_2mhz=2 * (candidate.retired-1) / candidate.ticks,
                         state_and_all_memory_accesses_match=True))
    cpu = IncDecCpu()
    sources = [Path(__file__), Path(__file__).with_name("cpu.py"),
               Path(__file__).with_name("compare.py"), Path(__file__).parents[1] / "ttl/netlist.py"]
    root = Path(__file__).resolve().parents[3]
    return dict(scope="Executed INC/DEC ALU wiring and transfer candidate; no revised CUPL fit or board timing",
                cu_fit_verified=False, cases=rows,
                alu_packages=dict(Counter(p.part for p in cpu.alu.packages)),
                control_signals=["ALU_CIN", "ALU_BCTRL_LOW", "ALU_BCTRL_HIGH"],
                control_table={"ADD": [0, 0, 1], "SUB": [1, 1, 0], "INC": [1, 0, 0], "DEC": [0, 1, 1]},
                alu_functional_wiring=cpu.alu.export(),
                source_sha256={p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                               for p in sources})


if __name__ == "__main__":
    report = measure()
    target = Path("simulators/cyclesim/build/hybrid/incdec-comparison.json")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "alu_functional_wiring"}, indent=2))
