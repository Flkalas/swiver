"""Reproduce the 24-IC, two-1504 alternative with explicit 74HC replacements."""
from collections import Counter
from contextlib import redirect_stdout
from io import StringIO
import hashlib
import json
from pathlib import Path

from simulators.cyclesim.hybrid.ram_cpld import address_source
from simulators.cyclesim.hybrid.ram_cpld_cpu import RamCpldCpu,alu_circuit
from simulators.cyclesim.hybrid.ram_cpld_measure import fitted_block,signal_net,state
from simulators.cyclesim.hybrid.ram_no1502 import (
    RamNo1502Cpu,cu_74_source,address_74_source,replacement_packages,
)
from simulators.cyclesim.hybrid.partition_probe import fit
from simulators.cyclesim.hybrid.ram_isa import RamReference
from simulators.cyclesim.hybrid.ram_programs import (
    RP,ERROR,iterative_fibonacci,pointer_copy,recursive_fibonacci,
)

ROOT=Path(__file__).resolve().parents[3]


def manifest(fitted):
    c=alu_circuit()
    aliases={}
    for probe,net in (('A','A'),('DB','DB'),('Y','Y')):
        aliases.update({c.names[n]:f'{net}[{i}]' for i,n in enumerate(c.probes[probe])})
    for probe,net in (('SUB','ALU_SUB_COMMAND'),('SUB_N','ALU_SUB_N'),
                      ('LOGICAL','ALU_LOGICAL'),('CARRY','ALU_C')):
        aliases[c.names[c.probes[probe][0]]]=net
    packages=c.export()['packages']
    for package in packages:
        package['pins']={pin:aliases.get(net,net) for pin,net in package['pins'].items()}
        package['group']='external_alu'
    for name,block in fitted.items():
        pins={signal:signal_net(name,signal) for signal in block['signal_pads']}
        for signal in ('execout','ploadout'):
            if signal in pins:pins[signal]+='_N'
        packages.append(dict(ref=name,part='ATF1504AS-10JU44',group='cpld',
                             pins=dict(VCC='VCC',GND='GND',**pins),
                             signal_pad_numbers=block['signal_pads']))
    packages.extend(replacement_packages())
    common={**{f'DQ{i}':f'DB[{i}]' for i in range(8)},
            'OE_N':'MEM_OE_N','VCC':'VCC','GND':'GND'}
    for bank in range(2):
        packages.append(dict(ref=f'RAM{bank}',part='IS62C256AL',group='memory',pins={
            **common,**{f'A{i}':f'ADDRESS[{i}]' for i in range(15)},
            'CE_N':f'RAM{bank}_CE_N','WE_N':'MEM_WE_N'}))
    packages.append(dict(ref='ROM',part='SST39SF010A',group='memory',pins={
        **common,**{f'A{i}':f'ADDRESS[{i}]' for i in range(16)},
        'A16':'GND','CE_N':'ROM_CE_N','WE_N':'VCC'}))
    assert len(packages)==24 and len({p['ref'] for p in packages})==24
    return dict(schema='swiver-ram-two-cpld-interconnect-v1',packages=packages,total_ic=24,
                part_totals=dict(sorted(Counter(p['part'] for p in packages).items())),
                boundary='CPLD pads from vendor fit; 74 and memory functional pins; no board timing acceptance')


def run_checked(program,ram,expected):
    cpu,baseline,ref=RamNo1502Cpu(),RamCpldCpu(),RamReference()
    for model in (cpu,baseline,ref):
        model.mem.map_mode=1
        model.mem.ram.update({program.base+i:b for i,b in enumerate(program.bytes())})
        model.mem.ram.update(ram)
    cpu.reset(program.base)
    baseline.reset(program.base)
    ref.pc=program.base
    for _ in range(2500):
        if cpu.halted:break
        for model in (cpu,baseline,ref):model.step_instruction()
        assert state(cpu)==state(baseline)==state(ref)
        assert cpu.accesses==baseline.accesses==ref.accesses
        assert cpu.mem.ram==baseline.mem.ram==ref.mem.ram
        assert cpu.mem.mailbox==baseline.mem.mailbox==ref.mem.mailbox
        assert cpu.ticks==baseline.ticks
    assert cpu.halted and cpu.a==expected and cpu.mem.ram.get(ERROR,0)==0
    return cpu,dict(program_bytes=len(program.bytes()),instructions=cpu.retired,
                    ticks=cpu.ticks,result_a=cpu.a,three_cpld_and_reference_match=True)


def main():
    sources=dict(ramcu74=cu_74_source(),ramaddr74=address_74_source())
    trials={}
    # Test simple absorption of P as well; failed candidates are evidence of
    # these exact partitions, not a proof that all two-CPLD redesigns fail.
    for i,nodes in enumerate((('branch',),('pcinc',),('branch','pcinc'),
                              ('pload','xload'),('branch','pload','xload'),
                              ('pcinc','pload','xload'))):
        name=f'ram2probe{i}'
        sources[name]=address_source(False,nodes).replace('Name ramaddrfit;',f'Name {name};')
    for name,source in sources.items():
        with redirect_stdout(StringIO()):
            result=fit(name,source,ROOT,ROOT/'cpld/tools/wincupl-ii')
        trials[name]=result
        print(name,{k:result.get(k) for k in ('design_fits','macrocells','preplacement_logic_cells')},flush=True)
    fitted={name:fitted_block(name,sources[name],trials[name]) for name in ('ramcu74','ramaddr74')}
    board=manifest(fitted)
    cases=[]
    for name,args in (('iterative_fibonacci_13',iterative_fibonacci(13)),
                      ('ram_pointer_cross_page_copy',pointer_copy()),
                      ('recursive_fibonacci_3_checked_stack',recursive_fibonacci(3))):
        cpu,record=run_checked(*args)
        if name.startswith('ram_pointer'):
            assert [cpu.mem.ram[0x3000+i] for i in range(4)]==list(range(0xA0,0xA4))
            assert (cpu.mem.ram[0x2200],cpu.mem.ram[0x2201])==(2,0x21)
        if name.startswith('recursive'):assert (cpu.mem.ram[RP],cpu.mem.ram[RP+1])==(0,0xF6)
        cases.append(dict(name=name,**record))
    out=ROOT/'simulators/cyclesim/build/ram-no1502'
    out.mkdir(parents=True,exist_ok=True)
    netlist=json.dumps(board,indent=2)+'\n'
    paths=['hybrid/'+name for name in ('ram_no1502.py','ram_no1502_measure.py',
        'ram_cpld.py','ram_cpld_cpu.py','ram_cpld_measure.py','cupl_model.py',
        'partition_probe.py','fit_blocks.py','ram_isa.py','ram_programs.py')]
    paths+=['tests/test_ram_cpld.py','tests/test_ram_no1502.py','ttl/netlist.py',
            'export/alu8_netlist.py','blocks/alu8.py','values.py']
    report=dict(scope='Direct seven-74 replacement for the page/decoder ATF1502',
        total_ic=24,baseline_total_ic=18,additional_ic=6,logic_74_packages=19,
        cplds=2,program_memory_packages=3,part_totals=board['part_totals'],
        selected_fits=fitted,trial_results={name:{k:r.get(k) for k in (
            'source_sha256','compile_exit','fit_exit','design_fits','macrocells',
            'preplacement_logic_cells','resource_report_consistent')} for name,r in trials.items()},
        cases=cases,clocks_per_instruction=6,
        limits=['This is a verified direct replacement, not a proven global minimum.',
                'CU and address general I/O remain full with JTAG enabled.',
                'Source equations and functional 74 packages, not post-fit timing or physical hardware.'],
        excludes=['oscillator','clean external reset/wait sources','load buffers','mailbox coprocessor','power/passives'],
        source_sha256={f'simulators/cyclesim/{p}':hashlib.sha256((ROOT/'simulators/cyclesim'/p).read_bytes()).hexdigest() for p in paths},
        tool_sha256={p:hashlib.sha256((ROOT/'cpld/tools/wincupl-ii'/p).read_bytes()).hexdigest()
                     for p in ('Shared/cupl.exe','Fitters/fit1504.exe')},
        netlist_sha256=hashlib.sha256(netlist.encode()).hexdigest())
    (out/'netlist.json').write_text(netlist,encoding='utf-8',newline='\n')
    (out/'comparison.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8',newline='\n')
    print(json.dumps(dict(total_ic=24,part_totals=board['part_totals'],cases=cases),indent=2))


if __name__=='__main__':main()
