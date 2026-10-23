"""Fit the RAM ISA with an external twelve-package ALU and small ATF CPLDs.

The common data bus also carries immediate operands during execute. The CU
owns A/literal/IR/flags; the selected address CPLD owns PC/X/literal/IR. The
third CPLD owns P and memory decode. CU/address use the same clock/reset/wait
and six-phase schedule. All registers use the common clock; no generated clocks.
"""
from pathlib import Path
from contextlib import redirect_stdout
from io import StringIO
import json

from simulators.cyclesim.hybrid.fit_blocks import header, decode_source
from simulators.cyclesim.hybrid.partition_probe import fit


def hold(lines, name, value, enable):
    lines += [f'{name}.ck = clk;', f'{name}.ar = reset;',
              f'{name}.d = ({enable} & ({value})) # (!({enable}) & {name});']


def sequencer(lines, ir):
    lines += ['PINNODE = [t0..2];', 'PINNODE = halted;',
              f'flow = {ir}0 & {ir}1;', f'store = {ir}4;',
              'ordinary = !(flow # store);', f'frommem = ordinary & {ir}2;',
              f'alu = ordinary & {ir}3;', 'execute = t2;',
              'readreq = !execute # (execute & frommem);',
              'writereq = execute & store;',
              'active = !(halted # reset);',
              'stall = t0 & wait & (readreq # writereq);',
              'tick = active & !stall;', 'cap = tick & t0;', 'commit = cap & execute;',
              'irload = cap & !execute & !t1;',
              'litload = cap & !execute & t1;',
              f'stop = flow & !store & {ir}2 & {ir}3;',
              'halted.ck = clk;', 'halted.ar = reset;',
              'halted.d = halted # (commit & stop);']
    for bit in range(3):
        lower = ' & '.join(f't{i}' for i in range(bit)) or "'b'1"
        lines += [f't{bit}.ck = clk;', f't{bit}.ar = reset;',
                  f't{bit}.d = !commit & ((tick & (t{bit} $ ({lower}))) # (!tick & t{bit}));']


def cu_source():
    lines = header('ramcu', 'f1504plcc44')
    lines += ['PIN 43 = clk;', 'PIN 1 = reset;', 'PIN 44 = wait;', 'PIN 2 = carry;',
              'PIN = [db0..7];', 'PIN = [qa0..7];', 'PIN = [y0..7];',
              'PIN = subcmd;', 'PIN = logsel;', 'PIN = rdn;', 'PIN = wrn;',
              'PINNODE = [ir0..5];', 'PINNODE = [lit0..7];',
              'PINNODE = zflag;', 'PINNODE = cflag;']
    sequencer(lines, 'ir')
    lines += ['aenable = commit & ordinary & ((!ir3 & !ir0 & !ir1) # (ir3 & !ir1));',
              'flagload = commit & alu;',
              'take = (!ir3 & (!ir2 # zflag)) # (ir3 & !ir2 & cflag);',
              'subcmd = (flow & !store & take) # (!(flow & !store) & (ir0 # ir1));',
              'logsel = ir5;', 'rdn = !(active & readreq & t0);', 'wrn = !(cap & writereq);',
              'drive = active & execute & (store # (ordinary & !frommem));']
    hold(lines, 'zflag', ' & '.join(f'!y{i}' for i in range(8)), 'flagload')
    hold(lines, 'cflag', 'carry & !ir5', 'flagload')
    for bit in range(6):
        hold(lines, f'ir{bit}', f'db{bit}.io', 'irload')
    for bit in range(8):
        hold(lines, f'lit{bit}', f'db{bit}.io', 'litload')
        hold(lines, f'qa{bit}', f'(alu & y{bit}) # (!alu & db{bit}.io)', 'aenable')
        lines += [f'db{bit} = (store & qa{bit}) # (!store & lit{bit});',
                  f'db{bit}.oe = drive;']
    return '\n'.join(lines) + '\n'


FIT_NODES = ('branch',)


def address_source(external_page=False, synthesis_nodes=()):
    name = 'ramaddrfit' if synthesis_nodes else 'ramaddrp' if external_page else 'ramaddr'
    lines = header(name, 'f1504plcc44')
    lines += [f'PINNODE = {node};' for node in synthesis_nodes]
    lines += ['PIN 43 = clk;', 'PIN 1 = reset;', 'PIN 44 = wait;',
              'PIN = [db0..7];', 'PIN = [addr0..15];', 'PIN = subcmd;', 'PIN = subn;',
              'PINNODE = [ir0..4];', 'PINNODE = ir7;',
              'PINNODE = [lit0..7];', 'PINNODE = [x0..7];', 'PINNODE = [pc0..15];']
    if external_page:
        lines += ['PIN = execout;', 'PIN = ploadout;']
    else:
        lines += ['PINNODE = [page0..7];']
    sequencer(lines, 'ir')
    lines += ['xload = commit & !store & !ir3 & ir0 & !ir1;',
              'pload = commit & !store & !ir3 & !ir0 & ir1;',
              'branch = commit & flow & !store & subcmd;',
              'pcinc = cap & !execute;', 'subn = !subcmd;']
    if external_page:
        # Both high-address drivers release the bus on even setup ticks. A full
        # blank tick separates logical owners; analog OE glitches remain unqualified.
        lines += ['execout = execute & t0;', 'ploadout = pload;']
    for bit in (0,1,2,3,4,7):
        hold(lines, f'ir{bit}', f'db{bit}', 'irload')
    for bit in range(8):
        hold(lines, f'lit{bit}', f'db{bit}', 'litload')
        hold(lines, f'x{bit}', f'db{bit}', 'xload')
        if not external_page:
            hold(lines, f'page{bit}', f'db{bit}', 'pload')
        lines += [f'target{bit} = (ir7 & x{bit}) # (!ir7 & lit{bit});',
                  f'target{bit+8} = '+(f'addr{bit+8}.io;' if external_page else f'page{bit};')]
    for bit in range(16):
        lower = ' & '.join(f'pc{i}' for i in range(bit)) or "'b'1"
        lines += [f'pc{bit}.ck = clk;', f'pc{bit}.ar = reset;',
                  f'pc{bit}.d = (branch & target{bit}) # (!branch & (pc{bit} $ (pcinc & ({lower}))));']
        if external_page and bit>=8:
            lines += [f'addr{bit} = pc{bit};',f'addr{bit}.oe = !execute & t0;']
        else:
            lines += [f'addr{bit} = (execute & target{bit}) # (!execute & pc{bit});']
    return '\n'.join(lines) + '\n'


def decoder_source(external_page=False):
    if not external_page:
        return decode_source().replace('Name bytedec;', 'Name ramdec;')
    lines = header('rampagedec','f1502plcc44')
    lines += ['PIN 43 = clk;', 'PIN 1 = reset;', 'PIN 44 = execute;', 'PIN 2 = pload;',
              'PIN = [db0..7];', 'PIN = [addr2..15];', 'PIN = mapmode;',
              'PIN = romn;', 'PIN = ram0n;', 'PIN = ram1n;', 'PIN = mbn;',
              'PINNODE = [page0..7];']
    for bit in range(8):
        hold(lines,f'page{bit}',f'db{bit}','pload')
        lines += [f'addr{bit+8} = page{bit};', f'addr{bit+8}.oe = execute;']
    addr = lambda i: f'addr{i}.io' if i>=8 else f'addr{i}'
    lines += ['top = '+' & '.join(addr(i) for i in range(8,16))+';',
              'vec = '+' & '.join(addr(i) for i in range(2,16))+';',
              'boot = '+' & '.join('!'+addr(i) for i in range(11,16))+';',
              'mb = top & !vec;', 'rom = !mapmode & (boot # vec);',
              'ram = !(rom # mb);', f'ram0n = !(ram & !{addr(15)});',
              f'ram1n = !(ram & {addr(15)});', 'romn = !rom;', 'mbn = !mb;']
    return '\n'.join(lines)+'\n'


def fit_sources():
    root = Path(__file__).resolve().parents[3]
    installed = root / 'cpld/tools/wincupl-ii'
    results = {}
    for name, device, source in (
        ('ramcu','1504',cu_source()), ('ramaddr','1504',address_source()),
        ('ramdec','1502',decoder_source()), ('ramaddrp','1504',address_source(True)),
        ('rampagedec','1502',decoder_source(True)),
        ('ramaddrfit','1504',address_source(True,FIT_NODES)),
        ('ramaddr_pcnode','1504',address_source(True,('pcinc',)).replace(
            'Name ramaddrfit;','Name ramaddr_pcnode;')),
    ):
        with redirect_stdout(StringIO()):
            result = fit(name, source, root, installed, device)
        results[name] = result
        print(name, json.dumps({k:v for k,v in result.items()
                               if k not in ('fit_output','compile_output')}), flush=True)
        if not result.get('design_fits'):
            print(result.get('fit_output',result.get('compile_output')), flush=True)
    return results


if __name__ == '__main__':
    fit_sources()
