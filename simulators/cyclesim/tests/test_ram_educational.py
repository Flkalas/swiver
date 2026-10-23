"""External-state variants against an independent ISA model and current CPU."""
import pytest

from simulators.cyclesim.hybrid.cupl_model import bits
from simulators.cyclesim.hybrid.ram_educational import external_packages
from simulators.cyclesim.hybrid.ram_educational_cpu import EducationalCpu
from simulators.cyclesim.hybrid.ram_isa import RamReference
from simulators.cyclesim.hybrid.ram_no1502 import RamNo1502Cpu
from simulators.cyclesim.hybrid.ram_programs import (
    RP, ERROR, iterative_fibonacci, pointer_copy, recursive_fibonacci, stack_boundary,
)


@pytest.fixture(params=[False,True],ids=['external_ir_step','external_ir_step_pc'])
def external_pc(request):return request.param


def state(cpu):
    return cpu.pc,cpu.a,cpu.x,cpu.p,cpu.z,cpu.c,cpu.halted,cpu.retired


def pair(external_pc,blob,base=0x800,a=0,x=0,page=0,flags=0,ram=None):
    cpu,ref=EducationalCpu(external_pc),RamReference()
    for model in (cpu,ref):
        model.mem.map_mode=1
        model.mem.ram.update({(base+i)&65535:b for i,b in enumerate(blob)})
        model.mem.ram.update(ram or {})
    cpu.reset(base)
    cpu.external.state['AC']=a
    cpu.addr.state.update({**bits('x',x,8),**bits('page',page,8)})
    cpu.cu.state.update(zflag=flags&1,cflag=flags>>1&1)
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
def test_educational_all_encodings(external_pc,opcode,flags):
    cpu,ref=pair(external_pc,bytes([opcode,0xF1]),base=0xFFF,a=0xA5,x=0x33,
                 page=0x20,flags=flags,ram={0x20F1:0x91,0x2033:0x5A})
    compare(cpu,ref,waits=2)


@pytest.mark.parametrize('opcode',[8,9,10,12,13,14,0x28,0x2A,0x2C,0x2E])
@pytest.mark.parametrize('a,b',[(0,0),(0,1),(255,1),(128,128),(0xAA,0x55),(255,255)])
def test_educational_alu_flags(external_pc,opcode,a,b):
    cpu,ref=pair(external_pc,bytes([opcode,b]),a=a,page=0x20,ram={0x2000+b:b},flags=3)
    compare(cpu,ref)


@pytest.mark.parametrize('address',[0,0x7FF,0x800,0x7FFF,0x8000,0xFEFF,0xFF00,0xFFFB,0xFFFC,0xFFFF])
@pytest.mark.parametrize('mode',[0,1])
def test_educational_memory_mapping(external_pc,address,mode):
    cpu,ref=pair(external_pc,bytes([0x90,0,0x84,0]),base=0x9000,a=0x5A,x=address&255,page=address>>8)
    cpu.mem.map_mode=ref.mem.map_mode=mode
    cpu.mem.rom[address]=ref.mem.rom[address]=0xC3
    compare(cpu,ref,waits=3)
    compare(cpu,ref,waits=3)


@pytest.mark.parametrize('base',[0xE,0xF,0xFE,0xFF,0xFFE,0xFFF,0xFFFE,0xFFFF])
def test_educational_counter_cascade_and_branch(external_pc,base):
    cpu,ref=pair(external_pc,bytes([0,0xAA,0x83,0]),base=base,x=0x55,page=0x81)
    compare(cpu,ref)
    assert cpu.pc==(base+2)&65535
    compare(cpu,ref)
    assert cpu.pc==0x8155


@pytest.mark.parametrize('factory',[pointer_copy,iterative_fibonacci,recursive_fibonacci])
def test_educational_program(external_pc,factory):
    p,ram,expected=factory()
    cpu,ref=pair(external_pc,p.bytes(),base=p.base,ram=ram)
    baseline=RamNo1502Cpu()
    baseline.mem.map_mode=1
    baseline.mem.ram=dict(cpu.mem.ram)
    baseline.reset(p.base)
    for _ in range(2500):
        if cpu.halted:break
        compare(cpu,ref)
        baseline.step_instruction()
        assert state(cpu)==state(baseline)
        assert cpu.accesses==baseline.accesses
        assert cpu.mem.ram==baseline.mem.ram
        assert cpu.ticks==baseline.ticks
    assert cpu.halted and cpu.a==expected and cpu.mem.ram.get(ERROR,0)==0


@pytest.mark.parametrize('push',[False,True])
@pytest.mark.parametrize('rp',[0xF5FE,0xF600,0xF601,0xF602,0xF6FE,0xF700,
                               0xFE00,0xFEEE,0xFEF0,0xFEF1,0xFEF2,0xFF00])
def test_educational_stack_bounds(external_pc,push,rp):
    p,ram=stack_boundary(push,rp)
    cpu,ref=pair(external_pc,p.bytes(),base=p.base,ram=ram)
    for _ in range(150):
        if cpu.halted:break
        compare(cpu,ref)
    assert cpu.halted
    error=(1 if rp&1 or not 0xF600<=rp<=0xFEF0 else
           2 if push and rp==0xFEF0 else 3 if not push and rp==0xF600 else 0)
    assert cpu.mem.ram.get(ERROR,0)==error
    assert cpu.mem.ram[RP]+256*cpu.mem.ram[RP+1]==(rp if error else rp+(2 if push else -2))


def test_educational_wait_and_halt(external_pc):
    cpu,ref=pair(external_pc,bytes([16,0x42,15,0]),a=0x99,page=0x20)
    for _ in range(5):cpu.clock()
    before=[dict(m.state) for m in (cpu.cu,cpu.addr,cpu.external)]
    accesses=list(cpu.accesses)
    for _ in range(10):cpu.clock(wait=1)
    assert before==[m.state for m in (cpu.cu,cpu.addr,cpu.external)]
    assert cpu.accesses==accesses and 0x2042 not in cpu.mem.ram
    cpu.clock();ref.step_instruction()
    assert state(cpu)==state(ref) and cpu.mem.ram[0x2042]==0x99
    compare(cpu,ref)
    before=state(cpu)
    for _ in range(6):cpu.clock()
    assert before==state(cpu) and cpu.accesses==ref.accesses


@pytest.mark.parametrize('initial_ir_ac',[0,1,0x55,0xAA,255])
def test_educational_physical_reset_retains_377(external_pc,initial_ir_ac):
    cpu=EducationalCpu(external_pc)
    for model in (cpu.cu,cpu.addr):model.state=dict.fromkeys(model.state,1)
    cpu.external.state['IR']=cpu.external.state['AC']=initial_ir_ac
    cpu.external.state['STEP']=15
    if external_pc:
        for i in range(4):cpu.external.state[f'PC{i}']=15
    cpu.mem.rom.update(enumerate(bytes([0,0,1,0,2,0,10,0,15,0])))
    cpu.clock(reset=1)
    assert cpu.phase==0 and cpu.pc==0 and not cpu.halted and not cpu.accesses
    assert cpu.a==cpu.external.state['IR']==initial_ir_ac
    for _ in range(5):cpu.step_instruction()
    assert cpu.halted and cpu.pc==10 and (cpu.a,cpu.x,cpu.p)==(0,0,0)


def test_educational_external_parts_drive_execution(external_pc):
    cpu,_=pair(external_pc,bytes([0,0x55]))
    cpu.external.forced['IR[0]']=1  # Actual IR pin changes LDI A into LXI.
    cpu.step_instruction()
    assert (cpu.a,cpu.x)==(0,0x55)
    cpu,_=pair(external_pc,bytes([8,1]))
    cpu.alu.forced[cpu.alu.probes['Y'][0]]=0
    cpu.step_instruction()
    assert cpu.a==0 and cpu.z
    cpu,_=pair(external_pc,bytes([8,1]))
    cpu.external.forced['ZERO_N']=0
    cpu.step_instruction()
    assert cpu.a==1 and cpu.z
    cpu,_=pair(external_pc,bytes([0,1]))
    cpu.external.packages['STEP']['pins']['ENT']='GND'
    with pytest.raises(AssertionError,match='clock cap'):cpu.step_instruction()


def test_educational_phase_owners_and_no_hidden_state(external_pc):
    cpu,_=pair(external_pc,bytes([0,1]))
    assert set(cpu.cu.state)=={'zflag','cflag','halted'}
    assert not any(name.startswith(('ir','t')) for name in cpu.addr.state)
    phases=[]
    for _ in range(6):
        cv,av,*_=cpu._settle()
        phases.append(cpu.phase)
        if external_pc:
            assert (int(not cv['pcdriven']),av['addr0_oe'])==(
                (1,0) if cpu.phase in (1,3) else (0,1) if cpu.phase==5 else (0,0))
        cpu.clock()
    assert phases==list(range(6)) and cpu.phase==0
    assert len(external_packages(external_pc))==(13 if external_pc else 7)


def test_educational_pc_packages_are_not_shadowed():
    cpu,_=pair(True,bytes([0,0x55]),base=0x80F)
    cpu.external.packages['PC1']['pins']['ENT']='GND'
    cpu.step_instruction()
    assert cpu.pc==0x801  # Low nibble wraps; broken carry never advances PC1.
