"""Direct-writeback control, alternative PC wiring, and polarity equivalence."""
from copy import deepcopy
from itertools import product

import pytest

from simulators.cyclesim.hybrid.direct_ttl import DirectTtlCpu, build
from simulators.cyclesim.hybrid.compare import paired, compare_instruction, run_pair
from simulators.cyclesim.ttl.netlist import Circuit
from simulators.cyclesim.ttl.optimize import optimize
from simulators.cyclesim.ttl.polarity import assign
from simulators.cyclesim.values import X, Z, logic_and, logic_or, logic_not


class CounterPcCpu(DirectTtlCpu):
    counter_pc = True


@pytest.mark.parametrize('opcode', range(256))
def test_direct_counter_pc_alternative(opcode):
    cpu, ref = paired(bytes([opcode,0x34,0x20]),
        {0xF00:2,0xF01:0xF6,0xF600:0x78,0xF601:0x56},
        base=0x20FF, r0=0xA5, flags=3, cpu_class=CounterPcCpu)
    compare_instruction(cpu,ref,wait_every=2)


@pytest.mark.parametrize('cls',[DirectTtlCpu,CounterPcCpu])
def test_direct_operand_latch_resets_between_instruction_formats(cls):
    # Wide taken jump -> immediate -> short trap -> narrow memory -> wide store.
    blob=bytes([5,3,0x20,1,0xFF,0x10,2,0x42,15,0,0x80,13,0xA5,10])
    cpu,ref=paired(blob,{0x42:0xA5},base=0x2000,cpu_class=cls)
    run_pair(cpu,ref,wait_every=1,cap=20)
    assert cpu.mem.ram[0x8000]==0xA5 and cpu.z
    before=(dict(cpu.mem.ram),list(cpu.accesses),cpu.ticks)
    cpu.step_instruction(wait_every=1)
    assert before==(cpu.mem.ram,cpu.accesses,cpu.ticks)


def test_direct_wait_freezes_all_state_and_has_no_memory_side_effect():
    cpu=DirectTtlCpu()
    cpu.mem.map_mode=1
    cpu.circuit.set(cpu.circuit.probes['STAGE'],1)
    cpu.circuit.set(cpu.circuit.probes['PHASE'],1)
    before=[cpu.circuit.read(q) for _,q,_ in cpu.circuit.registers]
    devices=[cpu.read(name) for name,_,_ in cpu.circuit.devices]
    for _ in range(8):
        cpu._settle(wait=1)
        assert cpu.read('CAP')==0 and cpu.read('WR')==0
        cpu.circuit.clock()
    assert before==[cpu.circuit.read(q) for _,q,_ in cpu.circuit.registers]
    assert devices==[cpu.read(name) for name,_,_ in cpu.circuit.devices]


@pytest.mark.parametrize('part,width,combine',[
    ('74HC00',2,logic_and),('74HC10',3,logic_and),('74HC20',4,logic_and),
    ('74HC02',2,logic_or),('74HC27',3,logic_or)])
def test_direct_negative_gates_all_four_state_inputs(part,width,combine):
    c=Circuit(); ins=c.bus('IN',width); out=c.wire('OUT'); p=c.package(part)
    c.ops.append((part,tuple(ins),(out,),p.ref)); c.finalize()
    for row in product((0,1,X,Z),repeat=width):
        for n,v in zip(ins,row): c.values[n]=v
        c.settle()
        expected=row[0]
        for v in row[1:]: expected=combine(expected,v)
        assert c.values[out]==logic_not(expected)


def test_direct_polarity_mapping_four_state_equivalence():
    c=Circuit(); a,b,d,e=c.bus('IN',4)
    c.probes['OUT']=[c.inv(c.or_(c.and_(a,b),c.and_(d,e))),
                     c.inv(c.inv(a)),c.any(a,b,d),c.all(a,b,d,e)]
    c.finalize(); mapped=assign(optimize(c,multi_or=True))
    for row in product((0,1,X,Z),repeat=4):
        outputs=[]
        for model in (c,mapped):
            for n,v in zip(model.probes['IN'],row): model.values[n]=v
            model.settle(); outputs.append([model.values[n] for n in model.probes['OUT']])
        assert outputs[0]==outputs[1]


def test_direct_storage_and_package_boundary():
    c=build()
    assert len(c.packages)<=115
    assert len(c.packages)<len(build(counter_pc=True).packages)
    assert 'RESULT' not in c.probes
    assert len(c.probes['STEP'])==len(c.probes['PHASE'])==1
    assert len(c.probes['FLAGS'])==2
    assert sum(p.group=='alu' for p in c.packages)==12
    assert all(p.part.startswith('74HC') for p in c.packages)
    assert len(c.probes['WRITEBACK'])==8
