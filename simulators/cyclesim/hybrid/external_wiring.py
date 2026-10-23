"""Signal interconnect and complete package count for the fitted 74-ALU candidate."""
from collections import Counter
from pathlib import Path
import json
import re
import hashlib

from simulators.cyclesim.hybrid.cpu import DP_REGS, LATCHES
from simulators.cyclesim.hybrid.hardware import manifest
from simulators.cyclesim.hybrid.external_partition import sequencer, auxiliary_table, latch_control


def fitted_pins(name, source, build):
    source_hash = hashlib.sha256(source.encode('ascii')).hexdigest()
    expected = set()
    for decl in re.findall(r'\bPIN\s*(?:\d+)?\s*=\s*([^;]+);', source):
        match = re.fullmatch(r'\[(\w+?)(\d+)\.\.(\d+)\]', decl)
        if match:
            prefix, start, stop = match.groups()
            expected.update(f'{prefix}{i}' for i in range(int(start), int(stop)+1))
        else:
            expected.add(decl.strip())
    report_path = build/name/(name+'_fit.fit')
    if not report_path.exists():
        evidence = json.loads(Path(__file__).with_name('external-fit-evidence.json').read_text(encoding='utf-8'))
        saved = evidence['blocks'][name]
        assert saved['source_sha256'] == source_hash, 'Stored fit evidence is stale; rerun external_partition'
        result = saved['physical_signal_pads']
        assert set(result) == expected
        return result
    summary = json.loads((build/name/'summary.json').read_text(encoding='utf-8'))
    assert summary['source_sha256'] == source_hash and summary['design_fits']
    report = report_path.read_text(errors='replace')
    result = {}
    for line in report.splitlines():
        if not re.match(r'^MC\d+\s', line):
            continue
        fields = line.split()
        if fields[1] == '0':
            continue
        for token in fields[2:]:
            if token in expected:
                result[token] = int(fields[1])
                break
    assert set(result) == expected, (name, expected-set(result))
    assert len(set(result.values())) == len(result), (name, result)
    assert not ({7, 13, 32, 38} & set(result.values())), 'JTAG pads must remain reserved'
    assert result['clk'] == 43 and result['reset'] == 1
    return result


def signal(name):
    if name in ('clk', 'reset', 'waitin', 'zf', 'wc', 'fault'):
        return name.upper()
    for prefix, bus in [('db', 'DBUS'), ('cmd', 'COMMAND'), ('p', 'PHASE'), ('u', 'MICRO_ADDR')]:
        match = re.fullmatch(prefix+r'(\d+)', name)
        if match:
            return f'{bus}[{match[1]}]'
    for prefix, names, kind in [('dc', DP_REGS, 'RCLK'), ('den', DP_REGS, 'ROEN'), ('lc', LATCHES, 'LCLK')]:
        match = re.fullmatch(prefix+r'(\d+)', name)
        if match:
            return kind+'_'+names[int(match[1])]
    return {'ac': 'ALU_C', 'rd': 'MEM_RD', 'wen_n': 'MEM_WE_N', 'romn': 'SYS_ROM_N',
            'romen_n': 'CTRL_ROM_N', 'tloen': 'OE_TMP_LO', 'thien': 'OE_TMP_HI',
            'resen': 'OE_RESULT', 'sub': 'SUB', 'subn': 'SUB_N'}[name]


def wiring(root=None):
    root = Path(root or Path(__file__).resolve().parents[3])
    build = root/'simulators/cyclesim/build/hybrid-partition'
    packages = [p for p in manifest(False)['packages']
                if p['role'] not in ('sequencer', 'five_byte_register_bank', 'memory_decode')]
    for p in packages:
        if p['role'] == 'ALU':
            p['pins'] = {k: v.replace('ALU_A[', 'DBUS[').replace('SUB[0]', 'SUB')
                         for k, v in p['pins'].items()}
        elif p['role'] == 'external_latch':
            p['pins']['CLK'] = 'LCLK_'+p['ref']
            if p['ref'] in ('TMP_LO', 'TMP_HI', 'RESULT'):
                p['pins']['OE_N'] = 'OE_'+p['ref']
        elif p['role'] == 'memory':
            rom = p['ref'] == 'ROM'
            p['pins'] = {**{f'A{i}': f'ADDRESS[{i}]' for i in range(16 if rom else 15)},
                         **{f'D{i}': f'DBUS[{i}]' for i in range(8)},
                         'CE_N': 'SYS_ROM_N' if rom else p['ref']+'_N',
                         'OE_N': 'MEM_OE_N', 'WE_N': 'VCC' if rom else 'MEM_WE_N'}
            if rom:
                p['pins']['A16'] = 'GND'
        elif p['role'] == 'clock_reset_conditioning':
            p['pins'] = {'1A': 'OSC', '1Y': 'CLK', '2A': 'RESET_RAW_N', '2Y': 'RESET',
                         '3A': 'MEM_RD', '3Y': 'MEM_OE_N'}
    for name in DP_REGS:
        packages.append(dict(ref='REG_'+name, part='74HC574', role='external_register',
            pins={**{f'D{i}': f'DBUS[{i}]' for i in range(8)},
                  **{f'Q{i}': f'DBUS[{i}]' for i in range(8)},
                  'CLK': 'RCLK_'+name, 'OE_N': 'ROEN_'+name}))
    for name, source, part in [('extseq', sequencer(), 'ATF1504AS-10JU44'),
                               ('tblaux', auxiliary_table(), 'ATF1504AS-10JU44'),
                               ('extctrl', latch_control(), 'ATF1502AS-10JU44')]:
        pads = fitted_pins(name, source, build)
        packages.append(dict(ref=name, part=part, role='fitted_control',
            pins={n: signal(n) for n in pads}, physical_signal_pads=pads))
    packages.append(dict(ref='CONTROL_ROM', part='SST39SF010A', role='microcode_rom',
        pins={**{f'A{i}': f'PHASE[{i}]' for i in range(2)},
              **{f'A{i+2}': f'MICRO_ADDR[{i}]' for i in range(9)},
              **{f'A{i}': 'GND' for i in range(11,17)},
              **{f'D{i}': f'DBUS[{i}]' for i in range(8)},
              'CE_N': 'CTRL_ROM_N', 'OE_N': 'GND', 'WE_N': 'VCC'}))
    packages.append(dict(ref='DECODE_ROM', part='SST39SF010A', role='memory_decode_rom',
        pins={**{f'A{i}': f'ADDRESS[{i+2}]' for i in range(14)},
              'A14': 'MAP', 'A15': 'GND', 'A16': 'GND',
              'D0': 'RAM0_N', 'D1': 'RAM1_N', 'D2': 'SYS_ROM_N', 'D3': 'MAILBOX_CE_N',
              **{f'D{i}': 'NC' for i in range(4,8)},
              'CE_N': 'GND', 'OE_N': 'GND', 'WE_N': 'VCC'}))
    nets = {}
    for p in packages:
        for pin, net in p.get('pins', {}).items():
            if net not in ('GND', 'VCC', 'NC'):
                nets.setdefault(net, []).append(f"{p['ref']}.{pin}")
    assert len(packages) == 32
    assert len({p['ref'] for p in packages}) == 32
    return dict(schema='swiver-external-register-fit-v1', total_ic=len(packages),
                part_totals=dict(Counter(p['part'] for p in packages)), packages=packages,
                signal_nets=nets, unique_signal_nets=len(nets),
                functional_signal_endpoints=sum(map(len, nets.values())),
                excluded=['oscillator module (1)', 'PLCC adapters', 'passives', 'mailbox coprocessor'],
                limitations=['Signal interconnect, not PCB layout or wire-length estimate',
                             'Power and unused-pin termination require board design',
                             'Fixture initialization; reset-vector boot not implemented',
                             'Pre-fit Boolean clock-edge tests, not post-fit or electrical timing'])


if __name__ == '__main__':
    result = wiring()
    target = Path(__file__).resolve().parents[1]/'build/hybrid-partition/external-wiring.json'
    target.write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({k: result[k] for k in ('total_ic', 'part_totals', 'unique_signal_nets', 'functional_signal_endpoints')}))
