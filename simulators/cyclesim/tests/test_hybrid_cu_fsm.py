"""Check lowered CU transfer graph against the executable sequential CPU."""
import pytest
from simulators.cyclesim.hybrid.cu_fsm import FsmCpu, graph
from simulators.cyclesim.hybrid.compare import paired, compare_instruction, run_pair
from simulators.cyclesim.fixtures.rom_builder import build_fib_recursive_rom


def lowered(blob, ram=None, **kwargs):
    h, ref = paired(blob, ram, **kwargs)
    h.__class__ = FsmCpu
    return h, ref


@pytest.mark.parametrize("opcode", range(256))
@pytest.mark.parametrize("flags", [0, 3])
def test_cu_fsm_opcodes(opcode, flags):
    h, r = lowered(bytes([opcode, 0x34, 0x20]),
                   {0xF00: 2, 0xF01: 0xF6, 0xF600: 0x78, 0xF601: 0x56},
                   base=0x20FE, r0=0xA5, flags=flags)
    compare_instruction(h, r, wait_every=3)


@pytest.mark.parametrize("opcode", [6, 7])
@pytest.mark.parametrize("rp", [0, 0xF5FE, 0xF600, 0xF602, 0xF6FE, 0xF700, 0xFEEE, 0xFEF0, 0xFEF2, 0xFFFF, 0xF601])
def test_cu_fsm_stack(opcode, rp):
    h, r = lowered(bytes([opcode, 0, 0x30]), {0xF00: rp & 255, 0xF01: rp >> 8,
                   (rp - 2) & 65535: 0x34, (rp - 1) & 65535: 0x12}, base=0x2000)
    compare_instruction(h, r, wait_every=3)


def test_cu_fsm_recursive_program():
    b, ram, expected = build_fib_recursive_rom(5)
    h, r = lowered(b, ram)
    run_pair(h, r, cap=1000)
    assert h.r0 == expected


def test_cu_state_budget_is_measured():
    g = graph()
    assert len(g.nodes) <= 2 ** g.bits
    assert len(g.nodes) > 2 ** (g.bits - 1)


@pytest.mark.parametrize("base,blob", [(0xFFFF, [1, 1]), (0xFFFE, [5, 0, 0x20]), (0xFFFF, [10])])
def test_cu_fsm_pc_wrap(base, blob):
    h, r = lowered(bytes([blob[0]]), base=base)
    for i, b in enumerate(blob[1:], 1):
        h.mem.ram[(base + i) & 65535] = r.mem.sys.ram[(base + i) & 65535] = b
    compare_instruction(h, r)


@pytest.mark.parametrize("mode", [0, 1])
def test_cu_fsm_memory_map(mode):
    b = bytes([1, 0xA5, 3, 0x42, 15, 0, 0x80, 9, 0xFB, 8, 0xFB, 15, 0xFC, 0xFF, 10])
    h, r = lowered(b, map_mode=mode)
    run_pair(h, r, cap=20)
