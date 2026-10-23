"""Reproduce the new RAM ISA's executed package count and program evidence.

Run from the repository root with ``python -m simulators.cyclesim.hybrid.ram_measure``.
The reference interpreter checks outcomes; it never supplies CPU control signals.
"""
from collections import Counter
import hashlib
import json
from pathlib import Path

from simulators.cyclesim.hybrid.direct_ttl import build as old_build
from simulators.cyclesim.hybrid.ram_isa import RamReference
from simulators.cyclesim.hybrid.ram_programs import (
    RP, ERROR, iterative_fibonacci, pointer_copy, recursive_fibonacci, stack_boundary,
)
from simulators.cyclesim.hybrid.ram_ttl import RamTtlCpu, build


def run_checked(program, ram, expected_a, limit=2500):
    cpu, ref = RamTtlCpu(), RamReference()
    blob = program.bytes()
    for model in (cpu, ref):
        model.mem.map_mode = 1
        model.mem.ram.update({program.base + i: b for i, b in enumerate(blob)})
        model.mem.ram.update(ram)
    cpu.reset(program.base)
    ref.pc = program.base
    for _ in range(limit):
        if cpu.halted:
            break
        cpu.step_instruction()
        ref.step_instruction()
        assert (cpu.pc, cpu.a, cpu.x, cpu.p, cpu.z, cpu.c, cpu.halted, cpu.retired) == (
            ref.pc, ref.a, ref.x, ref.p, ref.z, ref.c, ref.halted, ref.retired)
        assert cpu.accesses == ref.accesses
        assert (cpu.mem.ram, cpu.mem.rom, cpu.mem.mailbox) == (
            ref.mem.ram, ref.mem.rom, ref.mem.mailbox)
    assert cpu.halted and cpu.a == expected_a and cpu.mem.ram.get(ERROR, 0) == 0
    assert cpu.ticks == 6 * cpu.retired
    return cpu, dict(program_bytes=len(blob), instructions=cpu.retired,
                    ticks=cpu.ticks, result_a=cpu.a,
                    memory_transactions=len(cpu.accesses),
                    reference_state_and_memory_trace_match=True)


def export_netlist(circuit):
    """Merge logical tri-state driver nodes into the physical data bus wires."""
    out = circuit.export()
    aliases = {}
    for connection in out.pop('wire_resolution'):
        for net in connection['inputs']:
            aliases[net] = connection['output']
    for package in out['packages']:
        package['pins'] = {pin: aliases.get(net, net)
                           for pin, net in package['pins'].items()}
    out['nets'] = list(dict.fromkeys(aliases.get(net, net) for net in out['nets']))
    out['probes'] = {name: [aliases.get(net, net) for net in nets]
                     for name, nets in out['probes'].items()}
    nets = out['probes']
    common = {**{f'DQ{i}': n for i, n in enumerate(nets['BYTE_BUS'])},
              'OE_N': nets['MEM_OE_N'][0], 'VCC': 'VCC', 'GND': 'GND'}
    for i in range(2):
        out['packages'].append(dict(ref=f'RAM{i}', part='IS62C256AL', group='memory', pins={
            **common, **{f'A{j}': n for j, n in enumerate(nets['ADDRESS'][:15])},
            'CE_N': nets[f'RAM{i}_CE_N'][0], 'WE_N': nets['MEM_WE_N'][0]}))
    out['packages'].append(dict(ref='ROM', part='SST39SF010A', group='memory', pins={
        **common, **{f'A{j}': n for j, n in enumerate(nets['ADDRESS'])},
        'A16': 'GND', 'CE_N': nets['ROM_CE_N'][0], 'WE_N': 'VCC'}))
    out['external_interface'] = {name: nets[name] for name in (
        'ADDRESS', 'BYTE_BUS', 'MAILBOX_CE_N', 'MEM_OE_N', 'MEM_WE_N',
        'WAIT', 'RESET', 'MAP_MODE')}
    out['external_interface']['SYS'] = [circuit.names[circuit.clock_net]]
    out['bus_aliases'] = aliases
    out['boundary'] = (
        f'{len(out["packages"])} functional-pin ICs including two SRAMs and read-only program Flash; '
        'no package-pad layout, analog timing, load buffering or clock/reset source. '
        'External RESET held through a clock clears PC/T/HALT; boot code starts at '
        '0000 and initializes A/X/P/flags. No hardware reset-vector fetch.')
    return out


def main():
    from simulators.cyclesim.hybrid.direct_ttl import DirectTtlCpu
    from simulators.cyclesim.hybrid.compare import paired, run_pair
    from simulators.cyclesim.fixtures.rom_builder import build_fib_recursive_rom

    circuit, old = build(), old_build()
    cases = []
    for name, case in (
        ('iterative_fibonacci_13', iterative_fibonacci(13)),
        ('ram_pointer_cross_page_copy', pointer_copy()),
        ('recursive_fibonacci_3_checked_stack', recursive_fibonacci(3)),
    ):
        cpu, result = run_checked(*case)
        if name.startswith('iterative'):
            assert cpu.mem.ram[0x2000] == 233
        elif name.startswith('ram_pointer'):
            assert [cpu.mem.ram[0x3000 + i] for i in range(4)] == list(range(0xA0, 0xA4))
            assert (cpu.mem.ram[0x2200], cpu.mem.ram[0x2201]) == (2, 0x21)
        else:
            assert (cpu.mem.ram[RP], cpu.mem.ram[RP + 1]) == (0, 0xF6)
        cases.append(dict(name=name, **result))
    call_return_costs = []
    for push, rp in ((True, 0xF600), (True, 0xF6FE), (False, 0xF602), (False, 0xF700)):
        program, ram = stack_boundary(push, rp)
        cpu, _ = run_checked(program, ram, 0x5A)
        end = program.labels['check_return' if push else 'finish']
        call_return_costs.append(dict(
            operation='CALL' if push else 'RET', initial_rp=rp,
            expansion_bytes=end - program.base - 2,
            instructions=cpu.retired - 2, ticks=cpu.ticks - 12,
            shared_error_handlers_bytes=24,
            note='Excludes surrounding LDI/HALT; includes bounds/alignment checks'))
    old_blob, old_ram, old_expected = build_fib_recursive_rom(3)
    old_cpu, old_ref = paired(old_blob, old_ram, cpu_class=DirectTtlCpu)
    run_pair(old_cpu, old_ref, cap=2500)
    assert old_cpu.r0 == old_expected == 2 and not old_cpu.fault
    recursive = next(case for case in cases if case['name'].startswith('recursive'))
    netlist = json.dumps(export_netlist(circuit), indent=2) + '\n'
    root = Path(__file__).resolve().parents[3]
    paths = [Path(__file__), Path(__file__).with_name('ram_ttl.py'),
             Path(__file__).with_name('ram_isa.py'), Path(__file__).with_name('ram_programs.py'),
             Path(__file__).with_name('direct_ttl.py'), Path(__file__).with_name('compact_ttl.py')]
    paths += [root / 'simulators/cyclesim' / p for p in (
        'ttl/netlist.py', 'ttl/optimize.py', 'ttl/polarity.py', 'blocks/mem_decode.py',
        'export/alu8_netlist.py', 'blocks/alu8.py', 'blocks/mux.py',
        'values.py', 'fixtures/rom_builder.py', 'hybrid/compare.py', 'tests/test_ram_ttl.py')]
    report = dict(
        scope='Experimental incompatible RAM ISA, all-74 functional-pin execution',
        logic_packages=len(circuit.packages), program_memory_packages=3,
        logic_plus_program_memory=len(circuit.packages) + 3,
        baseline_logic_packages=len(old.packages),
        logic_packages_saved=len(old.packages) - len(circuit.packages),
        reduction_percent=round(100 * (1 - len(circuit.packages) / len(old.packages)), 2),
        parts=dict(sorted(Counter(p.part for p in circuit.packages).items())),
        groups=circuit.inventory(), baseline_parts=dict(sorted(Counter(p.part for p in old.packages).items())),
        no_index_mux_ablation=dict(logic_packages=len(build(indexed=False).packages),
                                  note='Only removes X/literal address mux; X register retained; not selected'),
        cplds=0, control_roms=0, alu_packages=12,
        instruction_bytes=2, clocks_per_instruction_without_wait=6,
        data_bus_bits=8, address_bus_bits=16, native_mips_per_mhz=1/6,
        v1_binary_compatible=False, hardware_stack_guards=False,
        software_checked_call_return=True, memory_map_preserved=True,
        physical_timing_verified=False, reset_entry_address=0,
        limits=['Software CALL/RET preserves A but clobbers X/P/Z/C and uses scratch 0F02..0F05.',
                'Arbitrary programs can bypass software stack bounds checks.',
                'Hardware reset does not fetch the v1 reset vector; starts at 0000.',
                'HALT leaves post-fetch PC; all opcode bit patterns have defined aliases.',
                'RAM-to-ALU capture and memory write hold require physical timing qualification.'],
        excludes=['oscillator', 'external clean reset/wait sources', 'load buffers',
                  'mailbox coprocessor', 'power/passives'],
        cases=cases, software_call_return_costs=call_return_costs,
        recursive_fibonacci_3_comparison=dict(
            old_instructions=old_cpu.retired, old_ticks=old_cpu.ticks,
            new_instructions=recursive['instructions'], new_ticks=recursive['ticks'],
            tick_increase_percent=round(100 * (recursive['ticks']/old_cpu.ticks - 1), 2),
            note='Same Fibonacci input/output; different ISA, ABI and instruction stream'),
        source_sha256={p.resolve().relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                       for p in paths},
        netlist_sha256=hashlib.sha256(netlist.encode()).hexdigest(),
    )
    out = root / 'simulators/cyclesim/build/ram-ttl'
    out.mkdir(parents=True, exist_ok=True)
    (out / 'netlist.json').write_text(netlist, encoding='utf-8', newline='\n')
    (out / 'comparison.json').write_text(json.dumps(report, indent=2) + '\n',
                                         encoding='utf-8', newline='\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
