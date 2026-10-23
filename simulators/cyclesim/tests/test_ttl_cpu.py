"""Structural CPU differential tests; every run has a hard step and wall cap."""
import random

import pytest

from simulators.cyclesim.data.sequential import control_for
from simulators.cyclesim.fixtures.rom_builder import build_fib_recursive_rom, build_fib_to_limit_rom
from simulators.cyclesim.ttl.compare import compare_step, paired, run_pair


@pytest.mark.parametrize("opcode", range(256))
def test_ttl_all_opcode_bytes(opcode):
    # One instruction only: branches, traps and stack instructions may redirect.
    ttl, ref = paired(bytes([opcode, 0x34, 0x20]), {0x0F00: 2, 0x0F01: 0xF6,
                     0xF600: 0x78, 0xF601: 0x56}, base=0x2000, r0=0xA5, flags=3)
    for _ in range(control_for(opcode).typical_sys):
        compare_step(ttl, ref)
    assert ttl.last_trace.retired


@pytest.mark.parametrize("opcode", [6, 7])
@pytest.mark.parametrize("rp", [0, 0xF5FE, 0xF600, 0xF602, 0xF6FE, 0xF700, 0xFEEE, 0xFEF0, 0xFEF2, 0xFFFF, 0xF601])
def test_ttl_stack_bounds_and_carries(opcode, rp):
    ttl, ref = paired(bytes([opcode, 0, 0x30]), {0x0F00: rp & 255, 0x0F01: rp >> 8,
                     (rp - 2) & 65535: 0x34, (rp - 1) & 65535: 0x12}, base=0x2000)
    for _ in range(control_for(opcode).typical_sys):
        if ttl.halted: break
        compare_step(ttl, ref)
    assert ttl.halted or ttl.last_trace.retired


@pytest.mark.parametrize("n", [0, 3, 8])
@pytest.mark.timeout(60)
def test_ttl_recursive_fib(n):
    """Thousands of full package-network evaluations; measured budget <60s."""
    blob, ram, expected = build_fib_recursive_rom(n)
    ttl, ref = paired(blob, ram)
    run_pair(ttl, ref, max_steps=10_000, wall_s=50)
    assert ttl.r0 == expected and not ttl.fault
    assert ttl.mem.ram[0x0F00] == 0 and ttl.mem.ram[0x0F01] == 0xF6


def test_ttl_iterative_fib_and_wait_every_phase():
    blob, ram, expected, _ = build_fib_to_limit_rom(250)
    ttl, ref = paired(blob, ram)
    run_pair(ttl, ref, max_steps=2000, wall_s=20, wait_every=2)
    assert ttl.r0 == expected == 233
    assert ttl.sys_ticks == 1008


@pytest.mark.parametrize("base,blob", [(0xFFFF, bytes([1, 1])), (0xFFFE, bytes([5, 0, 0x20])), (0xFFFF, bytes([10]))])
def test_ttl_pc_wrap(base, blob):
    ttl, ref = paired(bytes([blob[0]]), base=base)
    for i, b in enumerate(blob[1:], 1):
        ttl.mem.ram[(base + i) & 65535] = ref.mem.sys.ram[(base + i) & 65535] = b
    for _ in range(control_for(blob[0]).typical_sys): compare_step(ttl, ref)


@pytest.mark.parametrize("map_mode", [0, 1])
def test_ttl_memory_map_and_mmio(map_mode):
    # Writes to boot overlay, regular RAM, mailbox and vector boundary.
    blob = bytes([1, 0xA5, 3, 0x42, 15, 0, 0x80, 9, 0xFB, 8, 0xFB,
                  15, 0xFC, 0xFF, 10])
    ttl, ref = paired(blob, base=0, map_mode=map_mode)
    run_pair(ttl, ref, max_steps=100, wall_s=10)
    assert ttl.mem.mailbox[0xFB] == 0xA5
    assert ttl.mem.ram[0x8000] == 0xA5
    assert (0x42 in ttl.mem.ram) == bool(map_mode)
    assert (0xFFFC in ttl.mem.ram) == bool(map_mode)


def test_ttl_random_alu_and_conditional_branch():
    rng = random.Random(74)
    blob = bytearray()
    for _ in range(100):
        blob.extend([rng.choice([1, 13]), rng.randrange(256)])
    blob.append(10)
    ttl, ref = paired(bytes(blob), base=0x2000)
    run_pair(ttl, ref, max_steps=700, wall_s=15, wait_every=7)


def test_ttl_gate_fault_changes_execution():
    ttl, ref = paired(bytes([1, 1, 10]))
    compare_step(ttl, ref)
    compare_step(ttl, ref)
    # Break an actual ALU result net. The CPU must consume the broken circuit.
    net = ttl.circuit.names.index("net_y0")
    ttl.circuit.forced[net] = 0
    with pytest.raises(AssertionError, match="SYS"):
        compare_step(ttl, ref)
    assert ttl.r0 == 0


def test_ttl_wait_suppresses_every_stack_side_effect():
    ttl, ref = paired(bytes([6, 4, 0, 10, 7]), {0x0F00: 0, 0x0F01: 0xF6})
    run_pair(ttl, ref, max_steps=50, wall_s=10, wait_every=2)
    assert ttl.sys_ticks == 36
    assert sum(t.bus_access is not None and t.bus_access.kind == "write" for t in ttl.trace) == 6
