"""Independent architectural checks for the new three-control 74 ALU candidate."""
from collections import Counter
import pytest

from simulators.cyclesim.hybrid.incdec import IncDecCpu, UnitTransfer
from simulators.cyclesim.hybrid.cpu import Transfer
from simulators.cyclesim.hybrid.compare import paired, compare_instruction, run_pair
from simulators.cyclesim.fixtures.rom_builder import build_fib_recursive_rom


@pytest.mark.parametrize("subtract", [False, True])
def test_incdec_physical_lane_all_a_and_varied_mbr(subtract):
    cpu = IncDecCpu()
    for a in range(256):
        for b in (0, 1, 0x55, 0xFF):
            cpu.dp["R0"], cpu.latches["MBR"] = a, b
            value, carry = cpu._drive(UnitTransfer("ALU", "RESULT", subtract=subtract))
            assert value == (a - 1 if subtract else a + 1) & 255
            assert carry == (a > 0 if subtract else a == 255)
            assert cpu.latches["MBR"] == b
    assert Counter(p.part for p in cpu.alu.packages) == {
        "74HC153": 8, "74HC283": 2, "74HC157": 2}


@pytest.mark.parametrize("prefix", ["PC", "RP"])
@pytest.mark.parametrize("amount", [-2, -1, 1])
def test_incdec_word_adjust_carry_borrow_wrap_flags(prefix, amount):
    cpu = IncDecCpu()
    for high in (0, 0xF6, 255):
        for low in range(256):
            value = high * 256 + low
            cpu.reset()
            cpu.dp[prefix + "_LO"], cpu.dp[prefix + "_HI"] = low, high
            cpu.latches["MBR"] = 0xA7
            cpu.z = cpu.c = True
            for i, transfer in enumerate(cpu._adjust(prefix, amount)):
                assert i < 6
                cpu.transfer(transfer, waits=1)
            actual = cpu.dp[prefix + "_LO"] | cpu.dp[prefix + "_HI"] << 8
            assert actual == (value + amount) & 65535
            assert cpu.z and cpu.c
            assert not cpu.accesses and not any(cpu.latch_clocks.values())
            if abs(amount) == 1:
                assert cpu.latches["MBR"] == 0xA7
                assert all(t.destination != "MBR" for t, *_ in cpu.events)


@pytest.mark.parametrize("flags", [0, 3])
@pytest.mark.parametrize("opcode", range(256))
def test_incdec_all_opcodes_and_flags(opcode, flags):
    cpu, reference = paired(bytes([opcode, 0x34, 0x20]),
        {0xF00: 2, 0xF01: 0xF6, 0xF600: 0x78, 0xF601: 0x56},
        base=0x20FF, r0=0xA5, flags=flags, cpu_class=IncDecCpu)
    compare_instruction(cpu, reference, wait_every=3)


@pytest.mark.parametrize("opcode", [6, 7])
@pytest.mark.parametrize("rp", [0, 0xF5FE, 0xF600, 0xF602, 0xF6FE, 0xF700,
                               0xFEEE, 0xFEF0, 0xFEF2, 0xFFFF, 0xF601])
def test_incdec_stack_boundaries(opcode, rp):
    cpu, reference = paired(bytes([opcode, 0, 0x30]),
        {0xF00: rp & 255, 0xF01: rp >> 8,
         (rp - 2) & 65535: 0x34, (rp - 1) & 65535: 0x12},
        base=0x2000, cpu_class=IncDecCpu)
    compare_instruction(cpu, reference, wait_every=2)


@pytest.mark.parametrize("mode", [0, 1])
def test_incdec_boot_run_mmio_and_rom_write_protection(mode):
    blob = bytes([1, 0xA5, 3, 0x42, 15, 0, 0x80, 9, 0xFB, 8, 0xFB, 15, 0xFC, 0xFF, 10])
    cpu, reference = paired(blob, map_mode=mode, cpu_class=IncDecCpu)
    run_pair(cpu, reference, wait_every=4, cap=20)
    assert cpu.mem.mailbox[0xFB] == 0xA5
    assert (0x42 in cpu.mem.ram) == bool(mode)


@pytest.mark.parametrize("base,blob", [(0xFFFF, [1, 1]), (0xFFFE, [5, 0, 0x20]), (0xFFFF, [10])])
def test_incdec_pc_wrap_and_halt(base, blob):
    cpu, reference = paired(bytes([blob[0]]), base=base, cpu_class=IncDecCpu)
    for i, b in enumerate(blob[1:], 1):
        cpu.mem.ram[(base+i) & 65535] = reference.mem.sys.ram[(base+i) & 65535] = b
    compare_instruction(cpu, reference)


@pytest.mark.timeout(15)
def test_incdec_recursive_wait():
    blob, ram, expected = build_fib_recursive_rom(5)
    cpu, reference = paired(blob, ram, cpu_class=IncDecCpu)
    run_pair(cpu, reference, cap=1000, wait_every=5)
    assert cpu.r0 == expected


def test_incdec_fault_reaches_pc_and_broken_control_is_observable():
    cpu = IncDecCpu()
    cpu.alu.forced[cpu.y[0]] = 0
    for transfer in cpu._adjust("PC", 1):
        cpu.transfer(transfer)
    assert cpu.pc == 0  # A real result fault propagates: no host integer increment.
    cpu.alu.forced.clear()
    cpu.alu.forced[cpu.cin[0]] = 0
    assert cpu._drive(UnitTransfer("ALU", "RESULT", "PC_LO"))[0] == 0


def test_incdec_result_capture_hold_and_flags_only_on_architectural_write():
    cpu = IncDecCpu()
    cpu.dp["R0"], cpu.latches["MBR"] = 255, 99
    cpu.transfer(UnitTransfer("ALU", "RESULT"), waits=3)
    assert cpu.dp["R0"] == 255 and cpu.latches["RESULT"] == 0
    assert not cpu.z and not cpu.c and cpu.work_carry
    cpu.transfer(Transfer("RESULT", "DP", flags=True))
    assert cpu.r0 == 0 and cpu.z and cpu.c
    assert cpu.latches["MBR"] == 99 and cpu.ticks == 11
