"""Compare ATF1502 with concrete ROM/273/discrete-decoder control blocks.

These are comparators, not a proof of a global discrete-logic minimum. The first
uses two ROMs and two 273s. The smaller-wiring version encodes outputs in one
ROM/273 and expands them with two 238s and one 138; both use five packages.
"""
from collections import Counter
from functools import lru_cache
from pathlib import Path
import json

from simulators.cyclesim.hybrid.cpu import DP_REGS, LATCHES
from simulators.cyclesim.hybrid.rom_search import ControlStore
from simulators.cyclesim.hybrid.cupl_model import TablePinCpu, number
from simulators.cyclesim.hybrid.external_wiring import wiring, signal

OUTPUTS = ([f'dc{i}' for i in range(5)] + [f'lc{i}' for i in range(6)] +
           [f'den{i}' for i in range(5)])


@lru_cache(None)
def images():
    commands = ControlStore().commands
    lo, hi = bytearray(512), bytearray(512)
    for address in range(512):
        cmd, phase, wait = address & 63, address >> 6 & 3, address >> 8
        t = commands[cmd] if cmd < len(commands) else None
        word = 0
        if t is not None:
            stalled = phase == 1 and wait and (t.source == 'MEM' or t.destination == 'MEM')
            capture = phase == 2 or (phase == 1 and not stalled)
            if capture:
                if t.destination == 'DP': word |= 1 << DP_REGS.index(t.select)
                if t.destination in LATCHES: word |= 1 << (5 + LATCHES.index(t.destination))
            if phase != 3 and t.source in ('DP', 'ALU'):
                word |= 1 << (11 + DP_REGS.index(t.select))
        lo[address], hi[address] = word & 255, word >> 8
    return bytes(lo), bytes(hi)


class RomControl:
    def __init__(self):
        # 273 Q=0 after clear; the five inverted OE outputs are therefore 1.
        self.state = {name: int(i >= 11) for i, name in enumerate(OUTPUTS)}

    def values(self, inputs):
        return dict(self.state, **inputs)

    def next(self, values):
        address = number(values, 'cmd', 6) | number(values, 'p', 2) << 6 | values['waitin'] << 8
        lo, hi = images()
        word = lo[address] | hi[address] << 8
        return {name: (word >> i & 1) ^ int(i >= 11) for i, name in enumerate(OUTPUTS)}


class No1502Cpu(TablePinCpu):
    def _ensure(self):
        exists = hasattr(self, 'seq')
        super()._ensure()
        if not exists: self.ctrl = RomControl()


@lru_cache(None)
def encoded_image():
    """4-bit write destination + capture bit + 3-bit read source, in one ROM."""
    lo, hi = images()
    commands = ControlStore().commands
    result = bytearray(512)
    for a in range(512):
        word = lo[a] | hi[a] << 8
        clocks = [i for i in range(11) if word >> i & 1]
        enables = [i for i in range(5) if word >> (11+i) & 1]
        assert len(clocks) <= 1 and len(enables) <= 1
        t = commands[a & 63] if (a & 63) < len(commands) else None
        # Set destination during setup, before the capture pulse rises. Encoding
        # only asserted clocks would change address and pulse on the same edge.
        write = (DP_REGS.index(t.select) if t and t.destination == 'DP' else
                 5 + LATCHES.index(t.destination) if t and t.destination in LATCHES else 0)
        result[a] = write | (16 if clocks else 0) | ((enables[0]+1) << 5 if enables else 0)
    return bytes(result)


class EncodedControl(RomControl):
    def next(self, values):
        a = number(values,'cmd',6) | number(values,'p',2)<<6 | values['waitin']<<8
        q = encoded_image()[a]
        write, pulse, read = q & 15, q >> 4 & 1, q >> 5
        return {name: (int(bool(pulse) and write == i) if i < 11 else
                       int(read != i-11+1)) for i,name in enumerate(OUTPUTS)}


class EncodedNo1502Cpu(TablePinCpu):
    def _ensure(self):
        exists = hasattr(self,'seq')
        super()._ensure()
        if not exists: self.ctrl = EncodedControl()


def alternative_wiring():
    result = wiring()
    result['packages'] = packages = [p for p in result['packages'] if p['ref'] != 'extctrl']
    reset = next(p for p in packages if p['ref'] == 'CLOCK_RESET')
    assert '4A' not in reset['pins']
    reset['pins'].update({'4A': 'RESET', '4Y': 'CTRL_RESET_N'})
    for bank in range(2):
        packages.append(dict(ref=f'CTRL_TABLE{bank}', part='SST39SF010A', role='replacement_decode',
            pins={**{f'A{i}': f'COMMAND[{i}]' for i in range(6)},
                  'A6': 'PHASE[0]', 'A7': 'PHASE[1]', 'A8': 'WAITIN',
                  **{f'A{i}': 'GND' for i in range(9,17)},
                  **{f'D{i}': f'CTRL_D[{bank*8+i}]' for i in range(8)},
                  'CE_N': 'GND', 'OE_N': 'GND', 'WE_N': 'VCC'}))
        packages.append(dict(ref=f'CTRL_FF{bank}', part='74HC273', role='replacement_register',
            pins={**{f'D{i}': f'CTRL_D[{bank*8+i}]' for i in range(8)},
                  **{f'Q{i}': signal(OUTPUTS[bank*8+i]) if bank*8+i < 11
                     else f'CTRL_EN[{bank*8+i-11}]' for i in range(8)},
                  'CLK': 'CLK', 'CLR_N': 'CTRL_RESET_N'}))
    packages.append(dict(ref='CTRL_INV', part='74HC04', role='replacement_enable_polarity',
        pins={**{f'{i+1}A': f'CTRL_EN[{i}]' for i in range(5)},
              **{f'{i+1}Y': signal(f'den{i}') for i in range(5)}, '6A': 'GND', '6Y': 'NC'}))
    nets = {}
    for p in packages:
        for pin, net in p['pins'].items():
            if net not in ('GND','VCC','NC'):
                nets.setdefault(net,[]).append(f"{p['ref']}.{pin}")
    result.update(total_ic=len(packages), part_totals=dict(Counter(p['part'] for p in packages)),
                  signal_nets=nets, unique_signal_nets=len(nets),
                  functional_signal_endpoints=sum(map(len,nets.values())))
    return result


def comparison():
    base, alternative = wiring(), encoded_wiring()
    keys = ('total_ic','unique_signal_nets','functional_signal_endpoints')
    return dict(with_1502={k:base[k] for k in keys},
                without_1502={k:alternative[k] for k in keys},
                reduction={k:alternative[k]-base[k] for k in keys},
                replacement_parts={'SST39SF010A':1,'74HC273':1,'74HC238':2,'74HC138':1},
                extra_existing_hc14_gates=2,
                boundary='Same Boolean edge outputs; decoder delay/glitches require timing checks; not a global minimum or wire-length proof')


def encoded_wiring():
    result = wiring()
    result['packages'] = packages = [p for p in result['packages'] if p['ref'] != 'extctrl']
    reset = next(p for p in packages if p['ref']=='CLOCK_RESET')
    reset['pins'].update({'4A':'RESET','4Y':'CTRL_RESET_N','5A':'CTRL_PULSE','5Y':'CTRL_PULSE_N'})
    packages.append(dict(ref='CTRL_TABLE',part='SST39SF010A',role='encoded_control',pins={
        **{f'A{i}':f'COMMAND[{i}]' for i in range(6)},'A6':'PHASE[0]','A7':'PHASE[1]','A8':'WAITIN',
        **{f'A{i}':'GND' for i in range(9,17)},**{f'D{i}':f'CTRL_D[{i}]' for i in range(8)},
        'CE_N':'GND','OE_N':'GND','WE_N':'VCC'}))
    qnets=[f'CTRL_WRITE[{i}]' for i in range(4)]+['CTRL_PULSE']+[f'CTRL_READ[{i}]' for i in range(3)]
    packages.append(dict(ref='CTRL_FF',part='74HC273',role='encoded_control',pins={
        **{f'D{i}':f'CTRL_D[{i}]' for i in range(8)},**{f'Q{i}':n for i,n in enumerate(qnets)},
        'CLK':'CLK','CLR_N':'CTRL_RESET_N'}))
    for bank in range(2):
        pins={**{n:f'CTRL_WRITE[{i}]' for i,n in enumerate(('A','B','C'))},'G2B_N':'GND'}
        pins.update(G1='CTRL_PULSE' if bank==0 else 'CTRL_WRITE[3]',
                    G2A_N='CTRL_WRITE[3]' if bank==0 else 'CTRL_PULSE_N')
        pins.update({f'Y{i}':signal(OUTPUTS[bank*8+i]) if bank*8+i<11 else 'NC' for i in range(8)})
        packages.append(dict(ref=f'CTRL_WRITE{bank}',part='74HC238',role='encoded_control',pins=pins))
    packages.append(dict(ref='CTRL_READ',part='74HC138',role='encoded_control',pins={
        **{n:f'CTRL_READ[{i}]' for i,n in enumerate(('A','B','C'))},'G1':'VCC','G2A_N':'GND','G2B_N':'GND',
        **{f'Y{i}_N':signal(f'den{i-1}') if 1<=i<=5 else 'NC' for i in range(8)}}))
    nets={}
    for p in packages:
        for pin,net in p['pins'].items():
            if net not in ('GND','VCC','NC'): nets.setdefault(net,[]).append(f"{p['ref']}.{pin}")
    result.update(total_ic=len(packages),part_totals=dict(Counter(p['part'] for p in packages)),
                  signal_nets=nets,unique_signal_nets=len(nets),functional_signal_endpoints=sum(map(len,nets.values())))
    return result


if __name__ == '__main__':
    out=Path(__file__).resolve().parents[1]/'build/hybrid-partition'
    out.mkdir(parents=True,exist_ok=True)
    for i,data in enumerate(images()): (out/f'control-replacement-{i}.bin').write_bytes(data)
    (out/'control-encoded.bin').write_bytes(encoded_image())
    (out/'without-1502-wiring.json').write_text(json.dumps(encoded_wiring(),indent=2)+'\n',encoding='utf-8')
    (out/'1502-comparison.json').write_text(json.dumps(comparison(),indent=2)+'\n',encoding='utf-8')
    print(json.dumps(comparison(),indent=2))
