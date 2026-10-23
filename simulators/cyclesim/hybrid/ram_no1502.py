"""Two ATF1504s with a seven-package 74HC replacement for the page CPLD.

The instruction set and six-clock schedule are unchanged. Page storage uses
two edge-triggered 173s with enable/reset/three-state outputs, not gated clocks.
Decoder evaluation follows the exported package connections and truth tables.
"""
from simulators.cyclesim.hybrid.cupl_model import Equations
from simulators.cyclesim.hybrid.ram_cpld import cu_source, address_source, FIT_NODES
from simulators.cyclesim.hybrid.ram_cpld_cpu import RamCpldCpu


def cu_74_source():
    return cu_source().replace('Name ramcu;', 'Name ramcu74;')


def address_74_source():
    return (address_source(True, FIT_NODES)
            .replace('Name ramaddrfit;', 'Name ramaddr74;')
            .replace('execout = execute & t0;', 'execout = !(execute & t0);')
            .replace('ploadout = pload;', 'ploadout = !pload;'))


def replacement_packages():
    packages = []

    def add(ref, part, **pins):
        packages.append(dict(ref=ref, part=part, group='page_decode_74',
                             pins=dict(VCC='VCC', GND='GND', **pins)))

    for half in range(2):
        add(f'PAGE{half}', '74HC173', CP='SYS', MR='RESET', E1='PAGE_LOAD_N',
            E2='GND', OE1='PAGE_DRIVE_N', OE2='GND',
            **{f'D{i}':f'DB[{4*half+i}]' for i in range(4)},
            **{f'Q{i}':f'ADDRESS[{8+4*half+i}]' for i in range(4)})
    add('DEC_TOP', '74HC30', **{chr(65+i):f'ADDRESS[{8+i}]' for i in range(8)}, Y='TOP_N')
    add('DEC_TAIL', '74HC30', **{chr(65+i):f'ADDRESS[{2+i}]' for i in range(6)},
        G='VCC', H='VCC', Y='TAIL_N')
    add('DEC_BOOT', '74HC138', A='ADDRESS[13]', B='ADDRESS[14]', C='ADDRESS[15]',
        G1='VCC', G2A_N='ADDRESS[11]', G2B_N='ADDRESS[12]',
        **{f'Y{i}':'BOOT_N' if i==0 else None for i in range(8)})
    add('DEC_SPLIT', '74HC139', **{
        '1A':'TAIL_N', '1B':'TOP_N', '1G_N':'GND',
        '1Y0':'VECTOR_N', '1Y1':'MAILBOX_CE_N', '1Y2':None, '1Y3':None,
        '2A':'ADDRESS[15]', '2B':'GND', '2G_N':'RAM_DISABLE',
        '2Y0':'RAM0_CE_N', '2Y1':'RAM1_CE_N', '2Y2':None, '2Y3':None})
    add('DEC_GLUE', '74HC00', **{
        '1A':'BOOT_N', '1B':'VECTOR_N', '1Y':'ROM_REQUEST',
        '2A':'MAP_MODE', '2B':'MAP_MODE', '2Y':'BOOT_MODE',
        '3A':'ROM_REQUEST', '3B':'BOOT_MODE', '3Y':'ROM_CE_N',
        '4A':'ROM_CE_N', '4B':'MAILBOX_CE_N', '4Y':'RAM_DISABLE'})
    assert len(packages)==7
    return packages


class PageDecode74:
    """Adapter for the shared CPU harness; state belongs to the two 173s."""
    def __init__(self):
        self.packages = {p['ref']:p for p in replacement_packages()}
        self.state = {f'page{i}':0 for i in range(8)}
        self.forced = {}

    def decode(self, address, mode):
        nets = {'GND':0, 'VCC':1, 'MAP_MODE':mode,
                **{f'ADDRESS[{i}]':address>>i&1 for i in range(16)}}

        def run(ref, channel=None):
            package = self.packages[ref]
            pins = package['pins']
            get = lambda pin: nets[pins[pin]]
            if package['part']=='74HC30':
                outputs = {'Y':int(not all(get(chr(65+i)) for i in range(8)))}
            elif package['part']=='74HC138':
                enabled = get('G1') and not (get('G2A_N') or get('G2B_N'))
                select = get('A')+2*get('B')+4*get('C')
                outputs = {f'Y{i}':int(not (enabled and i==select)) for i in range(8)}
            elif package['part']=='74HC139':
                enabled = not get(f'{channel}G_N')
                select = get(f'{channel}A')+2*get(f'{channel}B')
                outputs = {f'{channel}Y{i}':int(not (enabled and i==select)) for i in range(4)}
            elif package['part']=='74HC00':
                outputs = {f'{channel}Y':int(not (get(f'{channel}A') and get(f'{channel}B')))}
            else:
                raise ValueError(package['part'])
            for pin,value in outputs.items():
                if pins[pin] is not None:
                    nets[pins[pin]] = self.forced.get(pins[pin],value)

        for ref in ('DEC_TOP','DEC_TAIL','DEC_BOOT'): run(ref)
        run('DEC_SPLIT',1)
        for channel in range(1,5): run('DEC_GLUE',channel)
        run('DEC_SPLIT',2)
        return {name:nets[net] for name,net in (
            ('romn','ROM_CE_N'), ('ram0n','RAM0_CE_N'),
            ('ram1n','RAM1_CE_N'), ('mbn','MAILBOX_CE_N'))}

    def values(self, inputs):
        # The generic CPU harness calls these ports execute/pload. In this
        # variant both physical nets are active LOW, as required by the 173.
        values = {**self.state, **inputs}
        if inputs.get('reset'):
            values.update(dict.fromkeys(self.state,0))
        address = sum(inputs.get(f'addr{i}_io' if i>=8 else f'addr{i}',0)<<i
                      for i in range(2,16))
        values.update(self.decode(address,inputs['mapmode']))
        for half in range(2):
            pins = self.packages[f'PAGE{half}']['pins']
            nets = {'GND':0, 'PAGE_DRIVE_N':inputs['execute']}
            enabled = int(not (nets[pins['OE1']] or nets[pins['OE2']]))
            for bit in range(4):
                i = 4*half+bit
                values[f'addr{i+8}'] = values[f'page{i}']
                values[f'addr{i+8}_oe'] = self.forced.get(f'addr{i+8}_oe',enabled)
        return values

    def next(self, values):
        nets = {'GND':0, 'SYS':1, 'RESET':values['reset'],
                'PAGE_LOAD_N':values['pload'],
                **{f'DB[{i}]':values[f'db{i}'] for i in range(8)}}
        result = dict(self.state)
        for half in range(2):
            pins = self.packages[f'PAGE{half}']['pins']
            for bit in range(4):
                name = f'page{4*half+bit}'
                if nets[pins['MR']]: result[name] = 0
                elif not (nets[pins['E1']] or nets[pins['E2']]):
                    result[name] = nets[pins[f'D{bit}']]
        return result


class RamNo1502Cpu(RamCpldCpu):
    def __init__(self):
        super().__init__()
        self.cu = Equations(cu_74_source())
        self.addr = Equations(address_74_source())
        self.page = PageDecode74()
        self.reset()
