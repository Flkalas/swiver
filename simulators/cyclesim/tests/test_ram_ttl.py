"""New RAM ISA: compare actual 74 circuit with an independent interpreter."""
import random

import pytest

from simulators.cyclesim.hybrid.ram_isa import RamReference, ANDI, TESTI, AND, TEST
from simulators.cyclesim.hybrid.ram_ttl import RamTtlCpu, build
from simulators.cyclesim.hybrid.ram_programs import (
    RP, ERROR, Software, iterative_fibonacci, pointer_copy, recursive_fibonacci,
    stack_boundary,
)


def pair(blob, *, base=0x800, mode=1, a=0, x=0, page=0, flags=0, ram=None):
    cpu,ref=RamTtlCpu(),RamReference()
    for model in (cpu,ref):
        model.mem.map_mode=mode
        for i,b in enumerate(blob):
            (model.mem.ram if mode else model.mem.rom)[(base+i)&65535]=b
        model.mem.ram.update(ram or {})
    cpu.reset(base)
    for name,value in [('A',a),('X',x),('P',page),('FLAGS',flags)]:
        cpu.circuit.set(cpu.circuit.probes[name],value)
    ref.pc,ref.a,ref.x,ref.p=base,a,x,page
    ref.z,ref.c=bool(flags&1),bool(flags&2)
    return cpu,ref


def compare(cpu,ref,waits=0):
    cpu.step_instruction(waits=waits)
    ref.step_instruction()
    assert (cpu.pc,cpu.a,cpu.x,cpu.p,cpu.z,cpu.c,cpu.halted,cpu.retired)==(
        ref.pc,ref.a,ref.x,ref.p,ref.z,ref.c,ref.halted,ref.retired)
    assert cpu.accesses==ref.accesses
    assert (cpu.mem.ram,cpu.mem.rom,cpu.mem.mailbox)==(ref.mem.ram,ref.mem.rom,ref.mem.mailbox)


@pytest.mark.parametrize('opcode',range(256))
@pytest.mark.parametrize('flags',[0,1,2,3])
def test_ram_all_encodings(opcode,flags):
    cpu,ref=pair(bytes([opcode,0xF1]),base=0x0FFF,a=0xA5,x=0x33,page=0x20,
                 flags=flags,ram={0x20F1:0x91,0x2033:0x5A})
    compare(cpu,ref,waits=2)


@pytest.mark.parametrize('opcode',[8,9,10,12,13,14])
@pytest.mark.parametrize('a,b',[(0,0),(0,1),(1,255),(255,1),(128,128),(127,128),(255,255)])
def test_ram_arithmetic_flags(opcode,a,b):
    cpu,ref=pair(bytes([opcode,b]),a=a,page=0x20,ram={0x2000+b:b})
    compare(cpu,ref)


@pytest.mark.parametrize('address',[0,0x7FF,0x800,0x7FFF,0x8000,0xFEFF,0xFF00,0xFFFB,0xFFFC,0xFFFF])
@pytest.mark.parametrize('mode',[0,1])
def test_ram_map_and_write_protection(address,mode):
    # Execute from RAM in both modes; access the same target through page+X.
    cpu,ref=pair(bytes([0x90,0,0x84,0]),base=0x9000,a=0x5A,x=address&255,page=address>>8)
    cpu.mem.map_mode=ref.mem.map_mode=mode
    cpu.mem.rom[address]=ref.mem.rom[address]=0xC3
    compare(cpu,ref,waits=3)
    compare(cpu,ref,waits=3)


@pytest.mark.parametrize('base',[0xFE,0xFF,0xFFFE,0xFFFF])
def test_ram_pc_increment_wrap_and_far_jump(base):
    cpu,ref=pair(bytes([0x83,0]),base=base,x=0x55,page=0x81)
    compare(cpu,ref)
    assert cpu.pc==0x8155


def test_ram_random_linear_program():
    rng=random.Random(1024)
    ops=[0,1,2,4,5,6,8,9,10,12,13,14,16]
    blob=bytes(b for _ in range(100) for b in (rng.choice(ops)|rng.choice([0,128]),rng.randrange(256)))+bytes([15,0])
    # Keep arbitrary data stores from modifying this test's instruction bytes.
    cpu,ref=pair(blob,base=0,mode=0,
                 ram={a:rng.randrange(256) for a in range(0x2000,0x2100)})
    for _ in range(110):
        if cpu.halted: break
        compare(cpu,ref,waits=1)
    assert cpu.halted


def test_ram_wait_freezes_state_and_memory():
    cpu,_=pair(bytes([16,0x42]),a=0x99,page=0x20)
    for _ in range(5): cpu.clock()
    assert cpu.read('T')==5
    registers=[(tuple(q),cpu.circuit.read(q)) for _,q,_ in cpu.circuit.registers]
    devices={name:cpu.read(name) for name,_,_ in cpu.circuit.devices}
    accesses=list(cpu.accesses)
    for _ in range(8): cpu.clock(wait=1)
    assert accesses==cpu.accesses and 0x2042 not in cpu.mem.ram
    assert devices=={name:cpu.read(name) for name,_,_ in cpu.circuit.devices}
    assert all(cpu.circuit.read(q)==v for q,v in registers)
    cpu.clock()
    assert cpu.mem.ram[0x2042]==0x99 and cpu.accesses[-1]==('write',0x2042,0x99)


def test_ram_alu_and_counter_are_not_host_shortcuts():
    cpu,_=pair(bytes([8,1]),a=0)
    cpu.circuit.forced[cpu.circuit.names.index('net_y0')]=0
    cpu.step_instruction()
    assert cpu.a==0  # ADD 1 would otherwise be 1.
    cpu,_=pair(bytes([0,0]))
    cpu.circuit.pins('PC0',ENP=0)
    # pins() changes probes only; the executable counter consumes these pins.
    cpu.step_instruction()
    assert cpu.pc==0x800


def test_ram_count_and_architecture_boundary():
    c=build()
    assert len(c.packages)<=60
    assert sum(p.group=='alu' for p in c.packages)==12
    assert all(p.part.startswith('74HC') for p in c.packages)
    assert not {'MBR','RESULT','RP_LO','RP_HI','TMP_LO','ADDR_LO'} & c.probes.keys()
    assert len(c.probes['BYTE_BUS'])==8 and len(c.probes['ADDRESS'])==16
    assert len(c.devices)==10  # five byte registers, five 4-bit counters


@pytest.mark.parametrize('opcode',[ANDI,TESTI,AND,TEST])
@pytest.mark.parametrize('a,b',[(0,255),(255,0),(0xAA,0x55),(0xA5,0x81),(255,255)])
def test_ram_logical_flags(opcode,a,b):
    cpu,ref=pair(bytes([opcode,b]),a=a,page=0x20,flags=3,ram={0x2000+b:b})
    compare(cpu,ref)
    assert cpu.z == ((a&b)==0) and not cpu.c
    assert cpu.a == (a if opcode in (TESTI,TEST) else a&b)


def run_program(program,ram,limit):
    cpu,ref=pair(program.bytes(),base=program.base,ram=ram)
    for _ in range(limit):
        if cpu.halted: break
        compare(cpu,ref)
    assert cpu.halted, 'bounded program did not halt'
    assert cpu.ticks == 6*cpu.retired
    return cpu


@pytest.mark.parametrize('n',[0,1,2,10,13])
def test_ram_iterative_fibonacci(n):
    p,ram,expected=iterative_fibonacci(n)
    cpu=run_program(p,ram,250)
    assert cpu.a==expected
    assert cpu.mem.ram[0x2000]==expected


def test_ram_pointer_copy_crosses_page():
    p,ram,expected=pointer_copy()
    cpu=run_program(p,ram,100)
    assert cpu.a==expected
    assert [cpu.mem.ram[0x3000+i] for i in range(4)]==[0xA0,0xA1,0xA2,0xA3]
    assert (cpu.mem.ram[0x2200],cpu.mem.ram[0x2201])==(2,0x21)


def test_ram_pointer_fields_cross_storage_page():
    p=Software()
    p.pointer(0x22FF)
    p.emit(0x84)
    p.emit(15)
    cpu=run_program(p,{0x22FF:0x34,0x2300:0x45,0x4534:0xA9},10)
    assert (cpu.a,cpu.x,cpu.p)==(0xA9,0x34,0x45)


@pytest.mark.parametrize('n',[0,1,3,4])
def test_ram_recursive_fibonacci_checked_software_stack(n):
    p,ram,expected=recursive_fibonacci(n)
    cpu=run_program(p,ram,2000)
    assert cpu.a==expected and cpu.mem.ram.get(ERROR,0)==0
    assert (cpu.mem.ram[RP],cpu.mem.ram[RP+1])==(0,0xF6)


@pytest.mark.parametrize('push',[False,True])
@pytest.mark.parametrize('rp',[0xF5FE,0xF600,0xF601,0xF602,0xF6FE,0xF700,
                               0xFE00,0xFEEE,0xFEF0,0xFEF1,0xFEF2,0xFF00])
def test_ram_software_stack_bounds(push,rp):
    p,ram=stack_boundary(push,rp)
    cpu=run_program(p,ram,150)
    error=(1 if rp&1 or not 0xF600<=rp<=0xFEF0 else
           2 if push and rp==0xFEF0 else
           3 if not push and rp==0xF600 else 0)
    assert cpu.mem.ram.get(ERROR,0)==error
    final_rp=cpu.mem.ram[RP]+256*cpu.mem.ram[RP+1]
    assert final_rp==(rp if error else rp+(2 if push else -2))
    if error:
        assert not any(kind=='write' and 0xF600<=address<0xFEF0
                       for kind,address,_ in cpu.accesses)
    else:
        assert cpu.a==0x5A


@pytest.mark.parametrize('pointer,delta,expected',[(0xFFFF,1,0),(0,-1,0xFFFF),
                                                  (0x2000,-1,0x1FFF),(0x20FF,1,0x2100)])
def test_ram_software_pointer_wrap(pointer,delta,expected):
    p=Software()
    p.adjust_pointer(0x2200,delta,'adjust')
    p.emit(15)
    cpu=run_program(p,{0x2200:pointer&255,0x2201:pointer>>8},30)
    assert cpu.mem.ram[0x2200]+256*cpu.mem.ram[0x2201]==expected


def test_ram_halt_freezes_cpu_and_bus():
    cpu,ref=pair(bytes([15,0]),a=0x5A,x=0x33,page=0x21,flags=3)
    compare(cpu,ref)
    before=(cpu.pc,cpu.a,cpu.x,cpu.p,cpu.z,cpu.c,cpu.retired,list(cpu.accesses))
    for _ in range(8): cpu.clock()
    after=(cpu.pc,cpu.a,cpu.x,cpu.p,cpu.z,cpu.c,cpu.retired,cpu.accesses)
    assert before==after
    assert cpu.read('RD')==cpu.read('WR')==0


def test_ram_wired_reset_restarts_at_zero_without_hidden_register_clears():
    cpu=RamTtlCpu()
    cpu.mem.map_mode=0
    # Boot code initializes the registers without relying on their power-up state.
    boot=bytes([0,0,1,0,2,0,10,0,15,0])
    cpu.mem.rom.update(enumerate(boot))
    for name,_,_ in cpu.circuit.devices:
        cpu.circuit.set(cpu.circuit.probes[name],(1<<len(cpu.circuit.probes[name]))-1)
    cpu.circuit.set(cpu.circuit.probes['FLAGS'],3)
    cpu.circuit.set(cpu.circuit.probes['HALTED'],1)
    cpu.clock(reset=1)
    assert cpu.pc==cpu.read('T')==0 and not cpu.halted and not cpu.accesses
    assert (cpu.a,cpu.x,cpu.p)==(255,255,255)  # 377 has no reset pin.
    for _ in range(5): cpu.step_instruction()
    assert cpu.halted and cpu.pc==10
    assert (cpu.a,cpu.x,cpu.p,cpu.z,cpu.c)==(0,0,0,True,True)
    assert cpu.retired==5


def test_ram_memory_select_pins_cover_all_pages_and_vector_edges():
    cpu=RamTtlCpu()
    cpu.circuit.set(cpu.circuit.probes['IR'],0x84)
    cpu.circuit.set(cpu.circuit.probes['T'],4)
    for mode in (0,1):
        cpu.mem.map_mode=mode
        for page in range(256):
            cpu.circuit.set(cpu.circuit.probes['P'],page)
            for low in (0,0xFB,0xFC,0xFF):
                cpu.circuit.set(cpu.circuit.probes['X'],low)
                cpu._settle()
                address=256*page+low
                mailbox=0xFF00<=address<=0xFFFB
                rom=not mode and (address<0x800 or address>=0xFFFC)
                expected=[rom,not(mailbox or rom) and address<0x8000,
                          not(mailbox or rom) and address>=0x8000,mailbox]
                actual=[cpu.read(name)==0 for name in
                        ('ROM_CE_N','RAM0_CE_N','RAM1_CE_N','MAILBOX_CE_N')]
                assert actual==expected and sum(actual)==1


def test_ram_export_contains_memory_and_one_physical_data_bus():
    from simulators.cyclesim.hybrid.ram_measure import export_netlist
    netlist=export_netlist(build())
    packages={p['ref']:p for p in netlist['packages']}
    assert len(packages)==63
    assert packages['ROM']['pins']['WE_N']=='VCC'
    assert packages['ROM']['pins']['A16']=='GND'
    bus=netlist['probes']['BYTE_BUS']
    for name in ('ROM','RAM0','RAM1'):
        assert [packages[name]['pins'][f'DQ{i}'] for i in range(8)]==bus
    driver=next(p for p in packages.values() if p['part']=='74HC244')
    assert [driver['pins'][f'B{i}'] for i in range(8)]==bus
    assert set(driver['pins'].values())<=set(netlist['nets'])
