"""Architectural and generated-equation checks for the shared sequential CU."""
import pytest

from simulators.cyclesim.hybrid.compare import paired, compare_instruction, run_pair
from simulators.cyclesim.hybrid.incdec import IncDecCpu
from simulators.cyclesim.hybrid.structured_cu import (
    StructuredCpu, Stage, Action, action, steps, command, action_done, next_stage)
from simulators.cyclesim.hybrid.structured_model import StructuredEquationCpu
from simulators.cyclesim.hybrid.structured_fit import command_set, sequencer_source
from simulators.cyclesim.hybrid.cupl_model import Equations, bits, number
from simulators.cyclesim.fixtures.rom_builder import build_fib_recursive_rom


@pytest.fixture(params=[StructuredCpu, StructuredEquationCpu])
def cpu_class(request):
    return request.param


@pytest.mark.parametrize("opcode", range(256))
@pytest.mark.parametrize("flags", [0, 3])
def test_structured_all_opcodes(cpu_class, opcode, flags):
    cpu, ref = paired(bytes([opcode, 0x34, 0x20]),
        {0xF00: 2, 0xF01: 0xF6, 0xF600: 0x78, 0xF601: 0x56},
        base=0x20FF, r0=0xA5, flags=flags, cpu_class=cpu_class)
    compare_instruction(cpu, ref, wait_every=3)


@pytest.mark.parametrize("opcode", [6, 7])
@pytest.mark.parametrize("rp", [0, 0xF5FE, 0xF600, 0xF602, 0xF6FE, 0xF700,
                               0xFEEE, 0xFEF0, 0xFEF2, 0xFFFF, 0xF601])
def test_structured_stack_boundaries(cpu_class, opcode, rp):
    cpu, ref = paired(bytes([opcode, 0, 0x30]),
        {0xF00: rp & 255, 0xF01: rp >> 8,
         (rp-2) & 65535: 0x34, (rp-1) & 65535: 0x12},
        base=0x2000, cpu_class=cpu_class)
    compare_instruction(cpu, ref, wait_every=2)


@pytest.mark.parametrize("mode", [0, 1])
def test_structured_memory_map(cpu_class, mode):
    blob = bytes([1, 0xA5, 3, 0x42, 15, 0, 0x80, 9, 0xFB, 8, 0xFB, 15, 0xFC, 0xFF, 10])
    cpu, ref = paired(blob, map_mode=mode, cpu_class=cpu_class)
    run_pair(cpu, ref, wait_every=4, cap=20)
    assert cpu.mem.mailbox[0xFB] == 0xA5
    assert (0x42 in cpu.mem.ram) == bool(mode)


@pytest.mark.parametrize("base,blob", [(0xFFFF, [1, 1]), (0xFFFE, [5, 0, 0x20]), (0xFFFF, [10])])
def test_structured_pc_wrap(cpu_class, base, blob):
    cpu, ref = paired(bytes([blob[0]]), base=base, cpu_class=cpu_class)
    for i, b in enumerate(blob[1:], 1):
        cpu.mem.ram[(base+i) & 65535] = ref.mem.sys.ram[(base+i) & 65535] = b
    compare_instruction(cpu, ref)


@pytest.mark.timeout(30)
def test_structured_recursive_wait(cpu_class):
    blob, ram, expected = build_fib_recursive_rom(5)
    cpu, ref = paired(blob, ram, cpu_class=cpu_class)
    run_pair(cpu, ref, cap=1000, wait_every=5)
    assert cpu.r0 == expected


@pytest.mark.timeout(30)
def test_structured_transfer_sequence_unchanged(cpu_class):
    blob, ram, _ = build_fib_recursive_rom(5)
    cpu, ref = paired(blob, ram, cpu_class=cpu_class)
    old, oldref = paired(blob, ram, cpu_class=IncDecCpu)
    for _ in range(1000):
        if cpu.halted:
            break
        compare_instruction(cpu, ref)
        compare_instruction(old, oldref)
        # Equation execution captures on an edge; transfer execution logs at
        # the end of its four-phase helper. Compare transfers/data, not stamps.
        assert [e[:3] for e in cpu.events] == [e[:3] for e in old.events]
        assert cpu.ticks == old.ticks
    else:
        pytest.fail("instruction cap")
    assert old.halted and cpu.ticks == 21588


@pytest.mark.parametrize("stage", list(Stage))
def test_structured_generated_commands_and_continuations(stage):
    seq = Equations(sequencer_source("fields"))
    table = command_set("fields")
    for klass in range(16):
        for second in (0, 1):
            a = action(stage, klass, second)
            for step in steps(a):
                for carry in (0, 1):
                    for z in (0, 1):
                        seq.state.update(bits("s", int(stage), 5) | bits("t", step, 3) |
                                         bits("k", klass, 4) | bits("p", 3, 2) | {"b0": second})
                        v = seq.values(dict(reset=0, clk=0, waitin=0, fault=0, wc0=carry, zf0=z))
                        assert table[number(v, "cmd", 7)] == command(a, step)
                        if stage == Stage.STOP:
                            assert v["stopped"]
                            continue
                        assert bool(v["last"]) == action_done(a, step, carry)
                        assert number(v, "n", 5) == int(next_stage(stage, klass, second, z))


def test_structured_fault_quiets_command_and_capture():
    seq = Equations(sequencer_source("fields"))
    for phase in range(4):
        seq.state.update(bits("p", phase, 2))
        v = seq.values(dict(reset=0, clk=0, waitin=0, fault=1, wc0=0, zf0=0))
        assert number(v, "cmd", 7) == 0
        assert not v["capture"] and not v["advance"]


@pytest.mark.parametrize("target,amount", [("PC", 1), ("RP", 1), ("RP", -1), ("RP", -2)])
def test_structured_shared_adjust_word_boundaries(target, amount):
    cpu = StructuredCpu()
    a = Action("adjust", target, amount)
    for high in (0, 0xF6, 255):
        for low in range(256):
            cpu.reset()
            cpu.dp[target + "_LO"], cpu.dp[target + "_HI"] = low, high
            cpu.latches["MBR"] = 0xA7
            cpu.z = cpu.c = True
            for step in steps(a):
                cpu.transfer(command(a, step))
                if action_done(a, step, cpu.work_carry):
                    break
            actual = cpu.dp[target + "_LO"] | cpu.dp[target + "_HI"] << 8
            assert actual == ((high << 8) + low + amount) & 65535
            assert cpu.z and cpu.c
            if abs(amount) == 1:
                assert cpu.latches["MBR"] == 0xA7
