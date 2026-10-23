"""Check generated CUPL, clock edges, external 574s and 74 ALU together."""
import pytest
from simulators.cyclesim.hybrid.cupl_model import PinCpu
from simulators.cyclesim.hybrid.compare import paired, compare_instruction, run_pair
from simulators.cyclesim.fixtures.rom_builder import build_fib_recursive_rom


def lowered(blob, ram=None, **kwargs):
    h, ref = paired(blob, ram, **kwargs)
    h.__class__ = PinCpu
    return h, ref


@pytest.mark.parametrize("opcode", range(256))
@pytest.mark.parametrize("flags", [0, 3])
def test_cupl_opcodes(opcode, flags):
    h, r = lowered(bytes([opcode, 0x34, 0x20]),
                   {0xF00: 2, 0xF01: 0xF6, 0xF600: 0x78, 0xF601: 0x56},
                   base=0x20FE, r0=0xA5, flags=flags)
    compare_instruction(h, r, wait_every=3)


@pytest.mark.parametrize("opcode", [6, 7])
@pytest.mark.parametrize("rp", [0, 0xF5FE, 0xF600, 0xF602, 0xF6FE, 0xF700, 0xFEEE, 0xFEF0, 0xFEF2, 0xFFFF, 0xF601])
def test_cupl_stack(opcode, rp):
    h, r = lowered(bytes([opcode, 0, 0x30]), {0xF00: rp & 255, 0xF01: rp >> 8,
                   (rp - 2) & 65535: 0x34, (rp - 1) & 65535: 0x12}, base=0x2000)
    compare_instruction(h, r, wait_every=3)


def test_cupl_recursive_program():
    b, ram, expected = build_fib_recursive_rom(5)
    h, r = lowered(b, ram)
    run_pair(h, r, cap=1000)
    assert h.r0 == expected


@pytest.mark.parametrize("base,blob", [(0xFFFF, [1, 1]), (0xFFFE, [5, 0, 0x20]), (0xFFFF, [10])])
def test_cupl_pc_wrap(base, blob):
    h, r = lowered(bytes([blob[0]]), base=base)
    for i, b in enumerate(blob[1:], 1):
        h.mem.ram[(base + i) & 65535] = r.mem.sys.ram[(base + i) & 65535] = b
    compare_instruction(h, r)


@pytest.mark.parametrize("mode", [0, 1])
def test_cupl_memory_map(mode):
    b = bytes([1, 0xA5, 3, 0x42, 15, 0, 0x80, 9, 0xFB, 8, 0xFB, 15, 0xFC, 0xFF, 10])
    h, r = lowered(b, map_mode=mode)
    run_pair(h, r, cap=20)


@pytest.mark.parametrize("mode", [0, 1])
def test_table_rom_integrated_program(mode):
    from simulators.cyclesim.hybrid.cupl_model import TablePinCpu
    b=bytes([1,0xA5,3,0x42,15,0,0x80,9,0xFB,8,0xFB,15,0xFC,0xFF,10])
    h,r=paired(b,map_mode=mode);h.__class__=TablePinCpu
    run_pair(h,r,wait_every=2,cap=20)
    assert h.mem.mailbox[0xFB]==0xA5


def test_decode_rom_all_addresses_and_write_gate():
    from simulators.cyclesim.hybrid.external_partition import decode_image, auxiliary_table
    from simulators.cyclesim.hybrid.cupl_model import Equations
    rom=decode_image(); model=Equations(auxiliary_table())
    assert len(rom)==32768
    for mode in (0,1):
        for a in range(65536):
            entry=rom[(mode<<14)|(a>>2)]
            selected=[i for i in range(4) if not(entry>>i&1)]
            expect=3 if 0xFF00<=a<0xFFFC else 2 if not mode and (a<0x800 or a>=0xFFFC) else int(a>=0x8000)
            assert selected==[expect]
    for romn in (0,1):
        for wr in (0,1):
            model.state['wr']=wr
            assert model.values({'romn':romn})['wen_n']==int(not(wr and romn))


@pytest.mark.parametrize("op,rp", [(10,0xF600),(6,0xFEF0),(7,0xF600),(6,0xF601)])
def test_stopped_sources_and_clocks_remain_quiet(op,rp):
    from simulators.cyclesim.hybrid.cupl_model import TablePinCpu
    h,r=paired(bytes([op,0,0x30]),{0xF00:rp&255,0xF01:rp>>8},base=0x2000)
    h.__class__=TablePinCpu
    compare_instruction(h,r,wait_every=2)
    assert h.halted
    before=(dict(h.dp),dict(h.latches),list(h.accesses))
    for _ in range(16):h.edge()
    assert before==(h.dp,h.latches,h.accesses)


def test_cupl_uses_physical_74_alu():
    h,r=lowered(bytes([1,1,10]))
    h.alu.forced[h.y[0]]=0
    with pytest.raises(AssertionError):compare_instruction(h,r)


def test_cupl_fixture_reset_restarts_control_state():
    h, _ = lowered(bytes([1, 1, 10]))
    for _ in range(2): h.step_instruction()
    assert h.halted and h.r0 == 1
    h.reset()
    assert not hasattr(h, 'seq')
    h.step_instruction()
    assert not h.halted and h.r0 == 1 and h.pc == 2


def test_external_wiring_is_complete_for_fitted_signals(tmp_path):
    from simulators.cyclesim.hybrid.external_wiring import wiring
    w = wiring()
    # A clean checkout can verify the pinned fit evidence without WinCUPL files.
    assert wiring(tmp_path) == w
    assert w['total_ic'] == 32
    assert w['part_totals']['74HC574'] == 11
    assert sum(w['part_totals'][name] for name in ('74HC153','74HC283','74HC157')) == 12
    allowed = {'OSC','RESET_RAW_N','MAP','MAILBOX_CE_N'}
    assert {net for net, pins in w['signal_nets'].items() if len(pins) == 1} == allowed
    for i in range(8):
        assert f'REG_R0.Q{i}' in w['signal_nets'][f'DBUS[{i}]']
        assert f'RESULT.D{i}' in w['signal_nets'][f'ALU_Y[{i}]']
    assert 'tblaux.sub' in w['signal_nets']['SUB']
    assert 'U_ALU_283_LO.CIN' in w['signal_nets']['SUB']
