"""Reproduce architectural/clock comparison of both structured CU executors."""
import hashlib
import json
from pathlib import Path

from simulators.cyclesim.fixtures.rom_builder import build_fib_recursive_rom, build_fib_to_limit_rom
from simulators.cyclesim.hybrid.compare import paired, compare_instruction
from simulators.cyclesim.hybrid.incdec import IncDecCpu
from simulators.cyclesim.hybrid.structured_cu import StructuredCpu, Stage, commands
from simulators.cyclesim.hybrid.structured_model import StructuredEquationCpu
from simulators.cyclesim.hybrid.structured_fit import sequencer_source


def measure():
    cases = [("fib_iterative", build_fib_to_limit_rom(250)[:3]),
             ("fib_recursive_3", build_fib_recursive_rom(3)),
             ("fib_recursive_8", build_fib_recursive_rom(8)),
             ("add_256", (bytes([1, 1])*256 + bytes([10]), {}, 0))]
    rows = []
    for name, (blob, ram, expected) in cases:
        pairs = [paired(blob, ram, cpu_class=cls) for cls in
                 (IncDecCpu, StructuredCpu, StructuredEquationCpu)]
        for _ in range(10000):
            if all(cpu.halted for cpu, _ in pairs):
                break
            for cpu, ref in pairs:
                compare_instruction(cpu, ref)
            baseline = pairs[0][0]
            for cpu, _ in pairs[1:]:
                assert cpu.ticks == baseline.ticks
                assert cpu.accesses == baseline.accesses
                assert cpu.halted == baseline.halted
                assert [e[:3] for e in cpu.events[-64:]] == [e[:3] for e in baseline.events[-64:]]
        else:
            raise AssertionError("structured comparison instruction cap")
        assert all(cpu.r0 == expected and not cpu.fault for cpu, _ in pairs)
        rows.append(dict(name=name, ticks={type(cpu).__name__: cpu.ticks for cpu, _ in pairs},
                         instructions_including_halt=baseline.retired,
                         observed_control_combinations=len(set(pairs[1][0].control_trace)),
                         architectural_and_memory_access_match=True))
    directory = Path(__file__).resolve().parent
    sources = [directory/name for name in ("structured_cu.py", "structured_fit.py", "structured_model.py",
                                          "structured_measure.py", "incdec.py", "cpu.py")]
    return dict(scope="Pre-fit structured sequencer; output decode and flags/guards remain transfer-model abstractions",
                main_continuations=len(Stage), control_register_bits=15,
                distinct_commands_including_idle=len(commands()), control_rom=False,
                full_cpu_fit_verified=False, physical_timing_verified=False, cases=rows,
                generated_fields_source_sha256=hashlib.sha256(sequencer_source("fields").encode("ascii")).hexdigest(),
                source_sha256={p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sources})


if __name__ == "__main__":
    report = measure()
    target = Path("simulators/cyclesim/build/hybrid/structured-comparison.json")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
