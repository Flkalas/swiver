"""CUPL CPU interconnect versus the independent new-ISA interpreter and TTL CPU."""
import pytest

from simulators.cyclesim.hybrid.cupl_model import bits, number
from simulators.cyclesim.hybrid.ram_cpld_cpu import RamCpldCpu
from simulators.cyclesim.hybrid.ram_isa import RamReference
from simulators.cyclesim.hybrid.ram_programs import (
    RP, ERROR, pointer_copy, iterative_fibonacci, recursive_fibonacci, stack_boundary,
)
from simulators.cyclesim.hybrid.ram_ttl import RamTtlCpu


def state(cpu):
    return (cpu.pc,cpu.a,cpu.x,cpu.p,cpu.z,cpu.c,cpu.halted,cpu.retired)


def pair(blob,base=0x800,a=0,x=0,page=0,flags=0,ram=None):
    cpu,ref=RamCpldCpu(),RamReference()
    for model in (cpu,ref):
        model.mem.map_mode=1
        model.mem.ram.update({(base+i)&65535:b for i,b in enumerate(blob)})
        model.mem.ram.update(ram or {})
    cpu.reset(base)
    cpu.cu.state.update(bits('qa',a,8),zflag=flags&1,cflag=flags>>1&1)
    cpu.addr.state.update(bits('x',x,8))
    cpu.page.state.update(bits('page',page,8))
    ref.pc,ref.a,ref.x,ref.p=base,a,x,page
    ref.z,ref.c=bool(flags&1),bool(flags&2)
    return cpu,ref


def compare(cpu,ref,waits=0):
    cpu.step_instruction(waits)
    ref.step_instruction()
    assert state(cpu)==state(ref)
    assert cpu.accesses==ref.accesses
    assert (cpu.mem.ram,cpu.mem.rom,cpu.mem.mailbox)==(ref.mem.ram,ref.mem.rom,ref.mem.mailbox)


@pytest.mark.parametrize('opcode',range(256))
@pytest.mark.parametrize('flags',[0,1,2,3])
def test_ram_cpld_all_encodings(opcode,flags):
    cpu,ref=pair(bytes([opcode,0xF1]),base=0xFFF,a=0xA5,x=0x33,page=0x20,
                 flags=flags,ram={0x20F1:0x91,0x2033:0x5A})
    compare(cpu,ref,waits=2)


@pytest.mark.parametrize('opcode',[8,9,10,12,13,14,0x28,0x2A,0x2C,0x2E])
@pytest.mark.parametrize('a,b',[(0,0),(0,1),(255,1),(128,128),(0xAA,0x55),(255,255)])
def test_ram_cpld_alu_flags(opcode,a,b):
    cpu,ref=pair(bytes([opcode,b]),a=a,page=0x20,ram={0x2000+b:b},flags=3)
    compare(cpu,ref)


@pytest.mark.parametrize('address',[0,0x7FF,0x800,0x7FFF,0x8000,0xFEFF,0xFF00,0xFFFB,0xFFFC,0xFFFF])
@pytest.mark.parametrize('mode',[0,1])
def test_ram_cpld_boot_run_write_protection(address,mode):
    cpu,ref=pair(bytes([0x90,0,0x84,0]),base=0x9000,a=0x5A,x=address&255,page=address>>8)
    cpu.mem.map_mode=ref.mem.map_mode=mode
    cpu.mem.rom[address]=ref.mem.rom[address]=0xC3
    compare(cpu,ref,waits=3)
    compare(cpu,ref,waits=3)


@pytest.mark.parametrize('base',[0xFE,0xFF,0xFFFE,0xFFFF])
def test_ram_cpld_pc_wrap_and_far_jump(base):
    cpu,ref=pair(bytes([0x83,0]),base=base,x=0x55,page=0x81)
    compare(cpu,ref)
    assert cpu.pc==0x8155


@pytest.mark.parametrize('factory',[pointer_copy,iterative_fibonacci,recursive_fibonacci])
def test_ram_cpld_program_matches_ttl_and_interpreter(factory):
    p,ram,expected=factory()
    cpu,ref=pair(p.bytes(),base=p.base,ram=ram)
    ttl=RamTtlCpu()
    ttl.mem.map_mode=1
    ttl.mem.ram=dict(cpu.mem.ram)
    ttl.reset(p.base)
    for _ in range(2000):
        if cpu.halted:break
        compare(cpu,ref)
        ttl.step_instruction()
        assert state(cpu)==state(ttl)
        assert cpu.accesses==ttl.accesses
        assert cpu.mem.ram==ttl.mem.ram
        assert cpu.ticks==ttl.ticks
    assert cpu.halted and cpu.a==expected and cpu.mem.ram.get(ERROR,0)==0


@pytest.mark.parametrize('push',[False,True])
@pytest.mark.parametrize('rp',[0xF5FE,0xF600,0xF601,0xF602,0xF6FE,0xF700,
                               0xFE00,0xFEEE,0xFEF0,0xFEF1,0xFEF2,0xFF00])
def test_ram_cpld_software_stack_bounds(push,rp):
    p,ram=stack_boundary(push,rp)
    cpu,ref=pair(p.bytes(),base=p.base,ram=ram)
    for _ in range(150):
        if cpu.halted:break
        compare(cpu,ref)
    assert cpu.halted
    error=(1 if rp&1 or not 0xF600<=rp<=0xFEF0 else
           2 if push and rp==0xFEF0 else 3 if not push and rp==0xF600 else 0)
    assert cpu.mem.ram.get(ERROR,0)==error
    assert cpu.mem.ram[RP]+256*cpu.mem.ram[RP+1]==(rp if error else rp+(2 if push else -2))


def test_ram_cpld_wait_and_halt_freeze():
    cpu,ref=pair(bytes([16,0x42,15,0]),a=0x99,page=0x20)
    for _ in range(5):cpu.clock()
    before=[dict(model.state) for model in (cpu.cu,cpu.addr,cpu.page)]
    accesses=list(cpu.accesses)
    for _ in range(10):cpu.clock(wait=1)
    assert before==[model.state for model in (cpu.cu,cpu.addr,cpu.page)]
    assert cpu.accesses==accesses and 0x2042 not in cpu.mem.ram
    cpu.clock();ref.step_instruction()
    assert state(cpu)==state(ref) and cpu.mem.ram[0x2042]==0x99
    compare(cpu,ref)
    before=state(cpu)
    for _ in range(6):cpu.clock()
    assert before==state(cpu) and cpu.accesses==ref.accesses


def test_ram_cpld_reset_restarts_and_initializes_shared_phase():
    cpu=RamCpldCpu()
    for model in (cpu.cu,cpu.addr,cpu.page):model.state=dict.fromkeys(model.state,1)
    cpu.mem.rom.update(enumerate(bytes([0,0,1,0,2,0,10,0,15,0])))
    cpu.clock(reset=1)
    assert cpu.pc==0 and not cpu.halted and not cpu.accesses
    assert number(cpu.cu.state,'t',3)==number(cpu.addr.state,'t',3)==0
    for _ in range(5):cpu.step_instruction()
    assert cpu.halted and cpu.pc==10 and (cpu.a,cpu.x,cpu.p)==(0,0,0)


def test_ram_cpld_external_alu_and_cupl_state_are_executed():
    cpu,_=pair(bytes([8,1]))
    cpu.alu.forced[cpu.alu.probes['Y'][0]]=0
    cpu.step_instruction()
    assert cpu.a==0
    cpu,_=pair(bytes([0,0]))
    cpu.addr.ds=dict(cpu.addr.ds)
    cpu.addr.ds['pc0']=compile('pc0','<stuck counter>','eval')
    cpu.step_instruction()
    assert cpu.pc==0x800


def test_ram_cpld_address_driver_loss_is_detected():
    cpu,_=pair(bytes([0,1]))
    for _ in range(5):cpu.clock()
    cpu.page.comb=dict(cpu.page.comb)
    cpu.page.comb['addr8_oe']=compile('0','<disabled address driver>','eval')
    with pytest.raises(AssertionError,match='address bus ownership'):
        cpu.clock()


def test_ram_cpld_blank_tick_separates_high_address_bus_drivers():
    cpu,_=pair(bytes([0,1]))
    owners=[]
    for _ in range(6):
        cv,av,pv,*_=cpu._settle()
        owners.append((av['addr8_oe'],pv['addr8_oe']))
        if cv['t0']==0: assert cv['rdn']==cv['wrn']==1
        cpu.clock()
    assert owners==[(0,0),(1,0),(0,0),(1,0),(0,0),(0,1)]
