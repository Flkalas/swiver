"""Byte-bus transfers: compare architectural outcomes, not unequal SYS clocks."""
import pytest

from simulators.cyclesim.hybrid.cpu import Transfer
from simulators.cyclesim.hybrid.compare import paired, compare_instruction, run_pair
from simulators.cyclesim.hybrid.hardware import decoder, manifest
from simulators.cyclesim.fixtures.rom_builder import build_fib_to_limit_rom, build_fib_recursive_rom


@pytest.mark.parametrize("opcode", range(256))
def test_hybrid_opcode(opcode):
    h, r = paired(bytes([opcode, 0x34, 0x20]),
                  {0xF00: 2, 0xF01: 0xF6, 0xF600: 0x78, 0xF601: 0x56},
                  base=0x2000, r0=0xA5, flags=3)
    compare_instruction(h, r)


@pytest.mark.parametrize("opcode", [6, 7])
@pytest.mark.parametrize("rp", [0, 0xF5FE, 0xF600, 0xF602, 0xF6FE, 0xF700, 0xFEEE, 0xFEF0, 0xFEF2, 0xFFFF, 0xF601])
def test_hybrid_stack(opcode, rp):
    h, r = paired(bytes([opcode, 0, 0x30]), {0xF00: rp & 255, 0xF01: rp >> 8,
                  (rp - 2) & 65535: 0x34, (rp - 1) & 65535: 0x12}, base=0x2000)
    compare_instruction(h, r, wait_every=3)


@pytest.mark.parametrize("recursive", [False, True])
def test_hybrid_fibonacci(recursive):
    if recursive:
        b, ram, expected = build_fib_recursive_rom(5)
    else:
        b, ram, expected, _ = build_fib_to_limit_rom(250)
    h, r = paired(b, ram)
    run_pair(h, r, wait_every=5, cap=1000)
    assert h.r0 == expected


@pytest.mark.parametrize("mode", [0, 1])
def test_hybrid_map_and_ram_execution(mode):
    b = bytes([1, 0xA5, 3, 0x42, 15, 0, 0x80, 9, 0xFB, 8, 0xFB, 15, 0xFC, 0xFF, 10])
    h, r = paired(b, map_mode=mode)
    run_pair(h, r, cap=20)
    assert h.mem.mailbox[0xFB] == 0xA5
    assert (0x42 in h.mem.ram) == bool(mode)


@pytest.mark.parametrize("base,blob", [(0xFFFF, [1, 1]), (0xFFFE, [5, 0, 0x20]), (0xFFFF, [10])])
def test_hybrid_pc_wrap(base, blob):
    h, r = paired(bytes([blob[0]]), base=base)
    for i, b in enumerate(blob[1:], 1):
        h.mem.ram[(base + i) & 65535] = r.mem.sys.ram[(base + i) & 65535] = b
    compare_instruction(h, r)


def test_hybrid_latches_hold_address_while_bus_changes():
    h, _ = paired(bytes([10]))
    h.transfer(Transfer("CU", "ADDR_LO", constant=0x34))
    h.transfer(Transfer("CU", "ADDR_HI", constant=0x12))
    h.transfer(Transfer("CU", "MBR", constant=0xAB), waits=7)
    assert h.address == 0x1234 and h.latches["MBR"] == 0xAB
    assert not any(h.latch_clocks.values())
    assert h.ticks == 19 and not h.accesses


def test_hybrid_alu_fault_is_visible():
    h, r = paired(bytes([1, 1, 10]))
    h.alu.forced[h.y[0]] = 0
    with pytest.raises(AssertionError): compare_instruction(h, r)


@pytest.mark.timeout(60)
def test_hybrid_decode_full_address_space():
    """All address bits consumed by decoder; A0/A1 are intentionally irrelevant."""
    c = decoder()
    for mode in (0, 1):
        c.set(c.probes["MAP"], mode)
        c.set(c.probes["MEM_RD"], 1)
        c.set(c.probes["MEM_WR"], 1)
        for a in range(0, 65536, 4):
            c.set(c.probes["ADDRESS"], a)
            c.settle()
            mb = 0xFF00 <= a < 0xFFFC
            rom = not mode and (a < 0x800 or a >= 0xFFFC)
            ram = not (mb or rom)
            expected = [ram and a < 0x8000, ram and a >= 0x8000, rom, mb]
            actual = [not c.read(c.probes[n]) for n in ("RAM0_CE_N", "RAM1_CE_N", "ROM_CE_N", "MAILBOX_CE_N")]
            assert actual == expected and sum(actual) == 1
            assert c.read(c.probes["MEM_WE_N"]) == bool(rom)


def test_hybrid_inventory_counts_real_decoder_packages():
    bare, assisted = manifest(False), manifest(True)
    assert bare["total_ic"] == assisted["total_ic"] - 1 + len(decoder().packages)
    assert assisted["part_totals"]["74HC574"] == 6
    assert assisted["part_totals"]["ATF1504AS-10JU44"] == 2
    assert assisted["dp_state_bits"] == 40
    assert all(p["general_io_used"] <= p["general_io_available_with_jtag"]
               for p in assisted["cpld_budgets"].values())
