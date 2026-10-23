"""Verify the concrete, interface-preserving replacement for ATF1502."""
import pytest
from simulators.cyclesim.hybrid.control_ablation import (
    RomControl, EncodedControl, EncodedNo1502Cpu, encoded_wiring, encoded_image, comparison)
from simulators.cyclesim.hybrid.external_partition import latch_control
from simulators.cyclesim.hybrid.cupl_model import Equations, bits
from simulators.cyclesim.hybrid.compare import paired, compare_instruction, run_pair
from simulators.cyclesim.fixtures.rom_builder import build_fib_recursive_rom


def test_rom_replacement_matches_all_cupl_inputs():
    original, replacement = Equations(latch_control()), RomControl()
    encoded = EncodedControl()
    assert original.state == replacement.state
    for command in range(64):
        for phase in range(4):
            for wait in (0, 1):
                inputs = dict(bits('cmd', command, 6), **bits('p', phase, 2), waitin=wait)
                assert original.next(original.values(inputs)) == replacement.next(replacement.values(inputs))
                assert original.next(original.values(inputs)) == encoded.next(encoded.values(inputs))


def test_write_decoder_address_is_set_before_capture():
    image = encoded_image()
    for cmd in range(64):
        for wait in (0,1):
            values = [image[cmd | p << 6 | wait << 8] for p in range(4)]
            assert len({v & 15 for v in values}) == 1
            assert not values[0] & 16 and not values[3] & 16


def test_encoded_decoder_package_wiring_all_register_words():
    from simulators.cyclesim.hybrid.external_wiring import signal
    from simulators.cyclesim.hybrid.control_ablation import OUTPUTS
    packages = encoded_wiring()['packages']
    ff = next(p for p in packages if p['ref']=='CTRL_FF')
    decoders = [p for p in packages if p['part'] in ('74HC238','74HC138')]
    for q in range(256):
        nets = {'GND':0,'VCC':1, 'CTRL_PULSE_N':1-(q>>4&1)}
        nets.update({ff['pins'][f'Q{i}']:q>>i&1 for i in range(8)})
        for decoder in decoders:
            pins = decoder['pins']
            selected = sum(nets[pins[name]]<<i for i,name in enumerate(('A','B','C')))
            enabled = nets[pins['G1']] and not nets[pins['G2A_N']] and not nets[pins['G2B_N']]
            low = decoder['part']=='74HC138'
            for i in range(8):
                name = pins[f'Y{i}_N' if low else f'Y{i}']
                if name != 'NC': nets[name] = int(bool(enabled) and i==selected) ^ int(low)
        for i,name in enumerate(OUTPUTS):
            expected = int(bool(q&16) and (q&15)==i) if i<11 else int((q>>5)!=i-11+1)
            assert nets[signal(name)] == expected


@pytest.mark.parametrize('mode', [0, 1])
def test_no1502_memory_and_wait(mode):
    blob = bytes([1,0xA5,3,0x42,15,0,0x80,9,0xFB,8,0xFB,15,0xFC,0xFF,10])
    h, r = paired(blob, map_mode=mode)
    h.__class__ = EncodedNo1502Cpu
    run_pair(h, r, wait_every=2, cap=20)


@pytest.mark.timeout(30)
def test_no1502_recursive_run():
    """Measured about 19s for the first ROM implementation; 30s wall cap."""
    blob, ram, expected = build_fib_recursive_rom(5)
    h, r = paired(blob, ram)
    h.__class__ = EncodedNo1502Cpu
    run_pair(h, r, wait_every=3, cap=1000)
    assert h.r0 == expected


@pytest.mark.parametrize('op,rp', [(6,0xFEF0),(7,0xF600),(6,0xF601)])
def test_no1502_fault_stops_outputs(op, rp):
    h, r = paired(bytes([op,0,0x30]), {0xF00:rp&255,0xF01:rp>>8}, base=0x2000)
    h.__class__ = EncodedNo1502Cpu
    compare_instruction(h,r,wait_every=2)
    assert h.halted
    before = (dict(h.dp), dict(h.latches), list(h.accesses))
    for _ in range(16): h.edge()
    assert before == (h.dp, h.latches, h.accesses)


def test_replacement_wiring_and_counts():
    w = encoded_wiring()
    assert 'ATF1502AS-10JU44' not in w['part_totals']
    assert w['part_totals']['ATF1504AS-10JU44'] == 2
    assert w['part_totals']['74HC273'] == 1
    assert {n for n,p in w['signal_nets'].items() if len(p)==1} == {'OSC','RESET_RAW_N','MAP','MAILBOX_CE_N'}
    assert comparison()['reduction'] == dict(total_ic=4,unique_signal_nets=18,functional_signal_endpoints=41)
