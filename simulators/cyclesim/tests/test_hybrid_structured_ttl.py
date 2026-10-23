"""All-74 structured CU: actual gates, not Transfer or equation execution."""
import pytest

from simulators.cyclesim.hybrid.structured_ttl import StructuredTtlCpu, build
from simulators.cyclesim.hybrid.compare import paired, compare_instruction, run_pair
from simulators.cyclesim.fixtures.rom_builder import build_fib_recursive_rom


@pytest.mark.parametrize('opcode', range(256))
@pytest.mark.parametrize('flags', [0, 3])
def test_structured_ttl_opcodes(opcode, flags):
    cpu, ref = paired(bytes([opcode, 0x34, 0x20]),
        {0xF00: 2, 0xF01: 0xF6, 0xF600: 0x78, 0xF601: 0x56},
        base=0x20FF, r0=0xA5, flags=flags, cpu_class=StructuredTtlCpu)
    compare_instruction(cpu, ref, wait_every=3)


@pytest.mark.parametrize('opcode', [6, 7])
@pytest.mark.parametrize('rp', [0, 0xF5FE, 0xF600, 0xF602, 0xF6FE, 0xF700,
                               0xFEEE, 0xFEF0, 0xFEF2, 0xFFFF, 0xF601])
def test_structured_ttl_stack(opcode, rp):
    cpu, ref = paired(bytes([opcode, 0, 0x30]),
        {0xF00: rp & 255, 0xF01: rp >> 8,
         (rp-2) & 65535: 0x34, (rp-1) & 65535: 0x12},
        base=0x2000, cpu_class=StructuredTtlCpu)
    compare_instruction(cpu, ref, wait_every=2)


@pytest.mark.parametrize('mode', [0, 1])
def test_structured_ttl_memory_map(mode):
    blob = bytes([1, 0xA5, 3, 0x42, 15, 0, 0x80, 9, 0xFB, 8, 0xFB, 15, 0xFC, 0xFF, 10])
    cpu, ref = paired(blob, map_mode=mode, cpu_class=StructuredTtlCpu)
    run_pair(cpu, ref, wait_every=4, cap=20)
    assert cpu.mem.mailbox[0xFB] == 0xA5
    assert (0x42 in cpu.mem.ram) == bool(mode)


@pytest.mark.parametrize('base,blob', [(0xFFFF, [1, 1]), (0xFFFE, [5, 0, 0x20]), (0xFFFF, [10])])
def test_structured_ttl_pc_wrap(base, blob):
    cpu, ref = paired(bytes([blob[0]]), base=base, cpu_class=StructuredTtlCpu)
    for i, b in enumerate(blob[1:], 1):
        cpu.mem.ram[(base+i) & 65535] = ref.mem.sys.ram[(base+i) & 65535] = b
    compare_instruction(cpu, ref)


@pytest.mark.timeout(60)
def test_structured_ttl_recursive_wait():
    blob, ram, expected = build_fib_recursive_rom(3)
    cpu, ref = paired(blob, ram, cpu_class=StructuredTtlCpu)
    run_pair(cpu, ref, cap=1000, wait_every=5)
    assert cpu.r0 == expected


def test_structured_ttl_no_hidden_control_or_pc_adder():
    from collections import Counter
    counts = Counter(p.part for p in build().packages)
    assert all(part.startswith('74HC') for part in counts)
    assert counts['74HC283'] == 2  # only the shared 8-bit ALU's two adders
    assert sum(p.group == 'alu' for p in build().packages) == 12
    assert 'COMMAND' not in build().probes  # direct output strobes, no encode/decode round trip


def test_structured_ttl_alu_fault_reaches_pc():
    cpu = StructuredTtlCpu()
    cpu.mem.map_mode = 1
    cpu.mem.load_bytes(0, bytes([1, 1]), target='ram')
    # Force bit 0 of the actual ALU output. A host integer PC increment would
    # conceal this defect; the circuit must instead write the damaged result.
    net = cpu.circuit.names.index('net_y0')
    cpu.circuit.forced[net] = 0
    cpu.step_instruction()
    assert cpu.pc == 0
