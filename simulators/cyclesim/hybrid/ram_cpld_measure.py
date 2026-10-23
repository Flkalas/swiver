"""Fit, execute and export the complete 18-IC RAM-ISA CPLD candidate."""
from collections import Counter
import hashlib
import json
from pathlib import Path
import re

from simulators.cyclesim.hybrid.ram_cpld import (
    cu_source, address_source, decoder_source, FIT_NODES, fit_sources,
)
from simulators.cyclesim.hybrid.ram_cpld_cpu import RamCpldCpu, alu_circuit
from simulators.cyclesim.hybrid.ram_isa import RamReference
from simulators.cyclesim.hybrid.ram_programs import (
    RP, ERROR, iterative_fibonacci, pointer_copy, recursive_fibonacci,
)
from simulators.cyclesim.hybrid.ram_ttl import RamTtlCpu, build as ttl_build


ROOT = Path(__file__).resolve().parents[3]
SELECTED = ('ramcu','ramaddrfit','rampagedec')


def state(cpu):
    return (cpu.pc,cpu.a,cpu.x,cpu.p,cpu.z,cpu.c,cpu.halted,cpu.retired)


def run_checked(program,ram,expected,limit=2500):
    cpu,ttl,ref = RamCpldCpu(),RamTtlCpu(),RamReference()
    for model in (cpu,ttl,ref):
        model.mem.map_mode = 1
        model.mem.ram.update({program.base+i:b for i,b in enumerate(program.bytes())})
        model.mem.ram.update(ram)
    cpu.reset(program.base)
    ttl.reset(program.base)
    ref.pc = program.base
    for _ in range(limit):
        if cpu.halted: break
        for model in (cpu,ttl,ref): model.step_instruction()
        assert state(cpu)==state(ttl)==state(ref)
        assert cpu.accesses==ttl.accesses==ref.accesses
        assert cpu.mem.ram==ttl.mem.ram==ref.mem.ram
        assert cpu.mem.mailbox==ttl.mem.mailbox==ref.mem.mailbox
        assert cpu.ticks==ttl.ticks
    assert cpu.halted and cpu.a==expected and cpu.mem.ram.get(ERROR,0)==0
    return cpu,dict(program_bytes=len(program.bytes()),instructions=cpu.retired,
                    ticks=cpu.ticks,result_a=cpu.a,
                    ttl_and_reference_state_trace_match=True)


def pad_map(report_text):
    return {name:int(pin) for pin,name in
            re.findall(r'^Pin\s+(\d+)\s*=\s*(\w+);',report_text,re.MULTILINE|re.IGNORECASE)}


def fitted_block(name,source,result):
    assert result['design_fits'] and result['resource_report_consistent'],name
    out = ROOT/'simulators/cyclesim/build/hybrid-partition'/name
    assert (out/(name+'.pld')).read_text(encoding='ascii')==source
    result = dict(result)
    result['signal_pads'] = pad_map((out/(name+'_fit.fit')).read_text(errors='replace'))
    result['general_io_excluding_jtag'] = result['io_including_jtag']-4
    result['dedicated_input_assignments'] = {signal:pad for signal,pad in result['signal_pads'].items()
                                            if pad in (1,2,43,44)}
    result['macrocells_available'] = 32 if result['device']=='ATF1502AS' else 64
    result['artifact_sha256'] = {p.name:hashlib.sha256(p.read_bytes()).hexdigest()
        for p in (out/(name+'.pld'),out/(name+'.tt2'),out/(name+'_fit.fit'),out/(name+'_fit.jed'))}
    result['validation_boundary'] = 'Vendor block fit plus source-equation CPU simulation; no post-fit or board timing'
    assert len(set(result['signal_pads'].values()))==len(result['signal_pads'])
    assert all(result['signal_pads'][pin] in (7,13,32,38) for pin in ('TDI','TMS','TCK','TDO'))
    return result


def signal_net(block,signal):
    if signal in ('TDI','TMS','TCK','TDO'): return block+'_'+signal
    for prefix,net in (('db','DB'),('qa','A'),('y','Y'),('addr','ADDRESS')):
        if re.fullmatch(prefix+r'\d+',signal): return f'{net}[{signal[len(prefix):]}]'
    return dict(clk='SYS',reset='RESET',wait='WAIT',carry='ALU_C',
                subcmd='ALU_SUB_COMMAND',subn='ALU_SUB_N',logsel='ALU_LOGICAL',
                rdn='MEM_OE_N',wrn='MEM_WE_N',execout='PAGE_DRIVE',execute='PAGE_DRIVE',
                ploadout='PAGE_LOAD',pload='PAGE_LOAD',mapmode='MAP_MODE',
                ram0n='RAM0_CE_N',ram1n='RAM1_CE_N',romn='ROM_CE_N',mbn='MAILBOX_CE_N')[signal]


def manifest(fitted):
    c = alu_circuit()
    aliases = {}
    for probe,net in (('A','A'),('DB','DB'),('Y','Y')):
        aliases.update({c.names[n]:f'{net}[{i}]' for i,n in enumerate(c.probes[probe])})
    for probe,net in (('SUB','ALU_SUB_COMMAND'),('SUB_N','ALU_SUB_N'),
                      ('LOGICAL','ALU_LOGICAL'),('CARRY','ALU_C')):
        aliases[c.names[c.probes[probe][0]]] = net
    packages = c.export()['packages']
    for package in packages:
        package['pins'] = {pin:aliases.get(net,net) for pin,net in package['pins'].items()}
        package['group'] = 'external_alu'
    for name in SELECTED:
        block = fitted[name]
        pins = {signal:signal_net(name,signal) for signal in block['signal_pads']}
        packages.append(dict(ref=name,part=block['device']+'-10JU44',group='cpld',
                             pins={**pins,'VCC':'VCC','GND':'GND'},
                             signal_pad_numbers=block['signal_pads']))
    common = {**{f'DQ{i}':f'DB[{i}]' for i in range(8)},
              'OE_N':'MEM_OE_N','VCC':'VCC','GND':'GND'}
    for i in range(2):
        packages.append(dict(ref=f'RAM{i}',part='IS62C256AL',group='memory',pins={
            **common,**{f'A{j}':f'ADDRESS[{j}]' for j in range(15)},
            'CE_N':f'RAM{i}_CE_N','WE_N':'MEM_WE_N'}))
    packages.append(dict(ref='ROM',part='SST39SF010A',group='memory',pins={
        **common,**{f'A{j}':f'ADDRESS[{j}]' for j in range(16)},
        'A16':'GND','CE_N':'ROM_CE_N','WE_N':'VCC'}))
    assert len(packages)==18
    return dict(schema='swiver-ram-cpld-interconnect-v1',packages=packages,
                part_totals=dict(sorted(Counter(p['part'] for p in packages).items())),
                total_ic=len(packages),
                external_nets=['SYS','RESET','WAIT','MAP_MODE','MAILBOX_CE_N',
                               'MEM_OE_N','MEM_WE_N']+[f'DB[{i}]' for i in range(8)]+
                              [f'ADDRESS[{i}]' for i in range(16)],
                boundaries=['CPLD signal pad numbers are from the successful vendor fit.',
                            'ALU and memory pins and power connections use functional names.',
                            'JTAG signals are exposed per CPLD; no physical programming performed.',
                            'No physical clock/reset/wait source, load buffers or mailbox coprocessor.'])


def main():
    trials = fit_sources()
    sources = dict(ramcu=cu_source(),ramaddrfit=address_source(True,FIT_NODES),
                   rampagedec=decoder_source(True))
    fitted = {name:fitted_block(name,sources[name],trials[name]) for name in SELECTED}
    board = manifest(fitted)
    cases = []
    for name,args in (('iterative_fibonacci_13',iterative_fibonacci(13)),
                      ('ram_pointer_cross_page_copy',pointer_copy()),
                      ('recursive_fibonacci_3_checked_stack',recursive_fibonacci(3))):
        cpu,record = run_checked(*args)
        if name.startswith('ram_pointer'):
            assert [cpu.mem.ram[0x3000+i] for i in range(4)]==list(range(0xA0,0xA4))
            assert (cpu.mem.ram[0x2200],cpu.mem.ram[0x2201])==(2,0x21)
        if name.startswith('recursive'):
            assert (cpu.mem.ram[RP],cpu.mem.ram[RP+1])==(0,0xF6)
        cases.append(dict(name=name,**record))
    netlist = json.dumps(board,indent=2)+'\n'
    paths = [ROOT/'simulators/cyclesim'/name for name in (
        'hybrid/ram_cpld.py','hybrid/ram_cpld_cpu.py','hybrid/ram_cpld_measure.py',
        'hybrid/cupl_model.py','hybrid/fit_blocks.py','hybrid/partition_probe.py',
        'hybrid/ram_ttl.py','hybrid/ram_isa.py','hybrid/ram_programs.py',
        'ttl/netlist.py','export/alu8_netlist.py','blocks/alu8.py','values.py',
        'tests/test_ram_cpld.py')]
    report = dict(scope='18-IC experimental RAM ISA: successful block fits and integrated source-equation execution',
        baseline_74_packages=len(ttl_build().packages),baseline_total_ic=len(ttl_build().packages)+3,
        logic_74_packages=12,cplds=3,program_memory_packages=3,total_ic=board['total_ic'],
        control_roms=0,external_register_packages=0,part_totals=board['part_totals'],
        selected_fits=fitted,
        trial_results={name:{k:r.get(k) for k in (
            'compile_exit','fit_exit','design_fits','macrocells','preplacement_logic_cells',
            'resource_report_consistent','source_sha256')} for name,r in trials.items()},
        timing=dict(clocks_per_instruction=6,wait_supported=True,native_mips_per_mhz=1/6,
                    high_address_blank_setup_ticks=True,
                    board_verified=False,post_fit_simulated=False),
        cases=cases,
        changed_wiring=['CU drives literal onto DB during immediate execute; ALU B directly uses DB.',
                        'Page CPLD drives ADDRESS high on T5; address CPLD on T1/T3; both off on T0/T2/T4.',
                        'SUB command also carries taken-branch condition during branch execute.',
                        'CU directly drives memory OE/WE; Flash WE tied high, SRAM writes qualified by CE.'],
        limits=['Same experimental ISA and software stack checks; not v1 binary compatible.',
                'All 28 general I/O pads are used on both ATF1504s with JTAG retained.',
                'Address CPLD uses nearly all macrocell capacity; future changes require refitting.',
                'Logical blank ticks are tested; analog OE/decode glitches, setup/hold and load remain unqualified.'],
        excludes=['oscillator','clean external reset/wait sources','load buffers','mailbox coprocessor','power/passives'],
        source_sha256={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},
        tool_sha256={name:hashlib.sha256((ROOT/'cpld/tools/wincupl-ii'/name).read_bytes()).hexdigest()
                     for name in ('Shared/cupl.exe','Fitters/fit1504.exe','Fitters/fit1502.exe')},
        netlist_sha256=hashlib.sha256(netlist.encode()).hexdigest())
    out = ROOT/'simulators/cyclesim/build/ram-cpld'
    out.mkdir(parents=True,exist_ok=True)
    (out/'netlist.json').write_text(netlist,encoding='utf-8',newline='\n')
    (out/'comparison.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8',newline='\n')
    print(json.dumps(dict(total_ic=report['total_ic'],parts=report['part_totals'],cases=cases),indent=2))


if __name__=='__main__': main()
