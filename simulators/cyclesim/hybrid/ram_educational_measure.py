"""Fit both visible-state candidates and compare packages and signal endpoints."""
from collections import Counter, defaultdict
from contextlib import redirect_stdout
from io import StringIO
import hashlib
import json
from pathlib import Path
import re

from simulators.cyclesim.hybrid.partition_probe import fit
from simulators.cyclesim.hybrid.ram_cpld_measure import fitted_block, state
from simulators.cyclesim.hybrid.ram_educational import cu_source, address_source, external_packages
from simulators.cyclesim.hybrid.ram_educational_cpu import EducationalCpu, CONTROL_NETS
from simulators.cyclesim.hybrid.ram_no1502 import (
    RamNo1502Cpu, cu_74_source, address_74_source, replacement_packages,
)
from simulators.cyclesim.hybrid.ram_no1502_measure import manifest as baseline_manifest
from simulators.cyclesim.hybrid.ram_isa import RamReference
from simulators.cyclesim.hybrid.ram_programs import (
    ERROR, RP, iterative_fibonacci, pointer_copy, recursive_fibonacci,
)

ROOT=Path(__file__).resolve().parents[3]


def signal_net(block,signal):
    if signal in ('TDI','TMS','TCK','TDO'):return block+'_'+signal
    for prefix,net in (('db','DB'),('addr','ADDRESS'),('ir','IR'),('t','STEP')):
        if re.fullmatch(prefix+r'\d+',signal):return f'{net}[{signal[len(prefix):]}]'
    if signal in CONTROL_NETS:return CONTROL_NETS[signal]
    return dict(clk='SYS',resetn='RESET_N',wait='WAIT',carry='ALU_C',zeron='ZERO_N',
                indexed='IR[7]',execute='STEP[2]')[signal]


def manifest(fitted,baseline,external_pc):
    # Copy shared ALU and memories so all three variants use exactly the same
    # functional pin convention. IR[5] directly controls the external ALU mux.
    packages=json.loads(json.dumps([p for p in baseline['packages']
                                   if p['group'] in ('external_alu','memory')]))
    for p in packages:
        p['pins']={pin:('IR[5]' if net=='ALU_LOGICAL' else net) for pin,net in p['pins'].items()}
    for name,block in fitted.items():
        pins={signal:signal_net(name,signal) for signal in block['signal_pads']}
        packages.append(dict(ref=name,part='ATF1504AS-10JU44',group='cpld',
                             pins=dict(VCC='VCC',GND='GND',**pins),
                             signal_pad_numbers=block['signal_pads']))
    packages.extend(external_packages(external_pc))
    packages.extend(replacement_packages()[2:])  # Five gates only; P is now in the 1504.
    total=35 if external_pc else 29
    assert len(packages)==len({p['ref'] for p in packages})==total
    return dict(schema='swiver-ram-educational-interconnect-v1',external_pc=external_pc,
                packages=packages,total_ic=total,
                part_totals=dict(sorted(Counter(p['part'] for p in packages).items())),
                boundaries=['CPLD pad numbers from successful vendor reports; other pins functional.',
                            'Physical jumper count/length requires placement and routing.',
                            'SYS/RESET_N/WAIT/MAP_MODE sources, mailbox MCU, buffers and passives excluded.'])


def wiring(board):
    """Topology metric, not a placed-board jumper estimate.

    Count functional signal pin occurrences on nets spanning at least two ICs.
    N terminals require N-1 abstract point-to-point tree connections. Exclude
    power/tied constants and single-package nets (including separate JTAG ports).
    External connector/source endpoints are excluded consistently in all cases.
    """
    nets=defaultdict(list)
    ties=0
    for package in board['packages']:
        for pin,net in package['pins'].items():
            if net in ('VCC','GND'):
                ties+=1
            elif net is not None:nets[net].append((package['ref'],pin))
    connected={net:ends for net,ends in nets.items() if len({ref for ref,_ in ends})>=2}
    endpoints=sum(len(ends) for ends in connected.values())
    return dict(inter_ic_signal_nets=len(connected),signal_pin_endpoints=endpoints,
                minimum_point_to_point_links=endpoints-len(connected),
                power_and_constant_pin_endpoints=ties,
                maximum_signal_terminal_count=max(map(len,connected.values())),
                net_endpoints={net:[f'{ref}.{pin}' for ref,pin in ends]
                               for net,ends in sorted(connected.items())})


def run_checked(external_pc,program,ram,expected):
    cpu,baseline,ref=EducationalCpu(external_pc),RamNo1502Cpu(),RamReference()
    for model in (cpu,baseline,ref):
        model.mem.map_mode=1
        model.mem.ram.update({program.base+i:b for i,b in enumerate(program.bytes())})
        model.mem.ram.update(ram)
    cpu.reset(program.base);baseline.reset(program.base);ref.pc=program.base
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
                    ticks=cpu.ticks,result_a=cpu.a,baseline_and_reference_trace_match=True)


def main():
    out=ROOT/'simulators/cyclesim/build/ram-educational'
    out.mkdir(parents=True,exist_ok=True)
    sources=dict(ramcu74=cu_74_source(),ramaddr74=address_74_source())
    for external_pc in (False,True):
        prefix='edupc' if external_pc else 'edu'
        sources[prefix+'cu']=cu_source(external_pc)
        sources[prefix+'addr']=address_source(external_pc)
    # Preserve the rejected direct-feedback trial; do not accept a success
    # banner when its macrocell report exceeds the device rating.
    initial=address_source().replace('Name eduaddr;','Name edudirect;')
    for i in range(8):initial=initial.replace(f'(branch & addr{i}.io)',f'(branch & target{i})')
    with redirect_stdout(StringIO()):
        initial_result=fit('edudirect',initial,ROOT,ROOT/'cpld/tools/wincupl-ii')
    fitted={}
    for name,source in sources.items():
        with redirect_stdout(StringIO()):
            result=fit(name,source,ROOT,ROOT/'cpld/tools/wincupl-ii')
        fitted[name]=fitted_block(name,source,result)
        print(name,{k:fitted[name][k] for k in ('macrocells','general_io_excluding_jtag','dedicated_inputs')},flush=True)
    baseline=baseline_manifest({name:fitted[name] for name in ('ramcu74','ramaddr74')})
    boards={'baseline':baseline}
    variants={}
    for external_pc in (False,True):
        name='ir_step_pc' if external_pc else 'ir_step'
        prefix='edupc' if external_pc else 'edu'
        blocks={prefix+role:fitted[prefix+role] for role in ('cu','addr')}
        board=manifest(blocks,baseline,external_pc)
        boards[name]=board
        cases=[]
        for label,args in (('iterative_fibonacci_13',iterative_fibonacci(13)),
                           ('ram_pointer_cross_page_copy',pointer_copy()),
                           ('recursive_fibonacci_3_checked_stack',recursive_fibonacci(3))):
            cpu,record=run_checked(external_pc,*args)
            if label.startswith('ram_pointer'):
                assert [cpu.mem.ram[0x3000+i] for i in range(4)]==list(range(0xA0,0xA4))
                assert (cpu.mem.ram[0x2200],cpu.mem.ram[0x2201])==(2,0x21)
            if label.startswith('recursive'):assert (cpu.mem.ram[RP],cpu.mem.ram[RP+1])==(0,0xF6)
            cases.append(dict(name=label,**record))
        variants[name]=dict(total_ic=board['total_ic'],part_totals=board['part_totals'],
                           fits=blocks,cases=cases,clocks_per_instruction=6)
    report=dict(scope='Two ATF1504s; external IR/phase counter; optional external PC',
        variants=variants,baseline_fits={name:fitted[name] for name in ('ramcu74','ramaddr74')},
        initial_direct_feedback_trial={k:initial_result.get(k) for k in
            ('source_sha256','compile_exit','design_fits','macrocells','resource_report_consistent')},
        wiring_definition=wiring.__doc__,wiring={},netlist_sha256={},
        limits=['Experimental RAM ISA; no change to normative v1.0.',
                'No ATF1502 or control ROM; same 12-chip external ALU.',
                'AC is also external to meet I/O limits; boot must initialize 377 registers.',
                'Internal-PC variant reads low branch target through ADDRESS pads.',
                'Source-equation and functional-package simulation, not post-fit or board timing.',
                'Not a proof of globally minimum package count.'])
    for name,board in boards.items():
        text=json.dumps(board,indent=2)+'\n'
        (out/(name+'-netlist.json')).write_text(text,encoding='utf-8',newline='\n')
        metric=wiring(board)
        (out/(name+'-connections.json')).write_text(json.dumps(metric,indent=2)+'\n',encoding='utf-8',newline='\n')
        report['wiring'][name]={k:v for k,v in metric.items() if k!='net_endpoints'}
        report['netlist_sha256'][name]=hashlib.sha256(text.encode()).hexdigest()
    paths=['hybrid/'+p for p in ('ram_educational.py','ram_educational_cpu.py',
        'ram_educational_measure.py','ram_cpld.py','ram_cpld_cpu.py','ram_cpld_measure.py',
        'ram_no1502.py','ram_no1502_measure.py','cupl_model.py','partition_probe.py',
        'fit_blocks.py','ram_isa.py','ram_programs.py')]
    paths+=['tests/test_ram_educational.py','tests/test_ram_educational_wiring.py',
            'ttl/netlist.py','blocks/alu8.py','export/alu8_netlist.py','values.py']
    report['source_sha256']={f'simulators/cyclesim/{p}':hashlib.sha256((ROOT/'simulators/cyclesim'/p).read_bytes()).hexdigest() for p in paths}
    report['tool_sha256']={p:hashlib.sha256((ROOT/'cpld/tools/wincupl-ii'/p).read_bytes()).hexdigest()
                          for p in ('Shared/cupl.exe','Fitters/fit1504.exe')}
    (out/'comparison.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8',newline='\n')
    print(json.dumps(dict(counts={k:b['total_ic'] for k,b in boards.items()},
                         wiring=report['wiring'],programs={k:v['cases'] for k,v in variants.items()}),indent=2))


if __name__=='__main__':main()
