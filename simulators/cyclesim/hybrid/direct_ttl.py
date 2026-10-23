"""Direct ALU writeback and two-phase byte control; no RESULT or control ROM.

A single shared read/memory bus feeds ALU A. One common eight-bit writeback
mux feeds register D pins, selecting that bus or ALU Y. All bytes share it.
"""
from copy import deepcopy
from functools import lru_cache
from collections import Counter
import hashlib
import json
from pathlib import Path
from simulators.cyclesim.hybrid.compact_ttl import PartsCircuit, CompactTtlCpu
from simulators.cyclesim.hybrid.cpu import DP_REGS, LATCHES
from simulators.cyclesim.ttl.optimize import optimize
from simulators.cyclesim.blocks.mem_decode import MemSystem
from simulators.cyclesim.ttl.polarity import assign

@lru_cache(None)
def build(polarity=True, counter_pc=False):
    c = PartsCircuit()
    wait, reset, mode = [c.bus(n,1)[0] for n in ('WAIT','RESET','MAP_MODE')]
    memory = c.bus('MEMORY_INPUT', 8)
    sl, sh = [c.counter(n) for n in ('S_LO','S_HI')]
    p = c.reg('P',1)
    t = c.reg('BYTE',1)
    s = sl + sh[:1]
    klass = c.register('CLASS')
    second = c.reg('SECOND',1)
    flags = c.reg('FLAGS',2)
    fault = c.reg('FAULT',2)
    # Terminal-count outputs belong to each 161, rather than external ANDs.
    for name,q in [('S_LO',sl),('S_HI',sh)]:
        # Implement after every ENT pin has been bound.
        c.probes[name + '.RCO'] = [c.wire(name + '_RCO')]
    st = []
    for hi in range(4):
        st += c.decode(s[:3], c.inv(s[3]) if hi & 1 else s[3], c.inv(s[4]) if hi & 2 else s[4])
    step = [c.inv(t[0]), t[0]]
    phase = [c.inv(p[0]),p[0]]
    # Store the raw opcode in the already-eight-bit 377. Decode its fields
    # directly instead of building four normalized class bits before storage.
    upper_zero = c.eq(klass[4:],0)
    k = c.decode(klass[:3], klass[3], c.inv(upper_zero)) + c.decode(klass[:3], c.inv(upper_zero), e3=klass[3])
    valid = c.all(upper_zero,c.inv(c.any(k[0],k[11],k[12],k[14])))
    short_reserved = c.or_(klass[4],k[12])
    k[0], k[11] = short_reserved, c.inv(c.or_(valid,short_reserved))
    any_stage = lambda *ids: c.any(*(st[i] for i in ids))
    iscall, isret, aluclass = k[6], k[7], c.or_(k[1],k[13])
    loadclass = c.or_(k[2],k[8])
    io = c.or_(k[8],k[9])
    active = c.inv(c.or_(st[26],c.any(*fault)))
    adjpc = 0 if counter_pc else any_stage(2,4)
    adjrp = any_stage(15,18,21,27)
    adjust = c.or_(adjpc,adjrp)
    neg = c.or_(any_stage(15,27),c.and_(st[21],c.inv(iscall)))
    addrpc, addrtmp, addrrp = any_stage(0,3), st[7], any_stage(16,19)
    addrlit = any_stage(11,13,22,24)
    addr = c.any(addrpc,addrtmp,addrrp,addrlit)
    alur0 = st[9]
    aluwrite = st[9]
    alurun = c.or_(adjust,alur0)
    memload = c.and_(st[8],loadclass)
    memstore = c.and_(st[8],c.inv(loadclass))
    stacklo, stackhi = st[17],st[20]
    stack = c.or_(stacklo,stackhi)
    rd = c.any(any_stage(1,5,12,14),memload,c.and_(stack,c.inv(iscall)))
    write = c.any(memstore,c.and_(stack,iscall),st[23],st[25])
    stall = c.all(phase[1],c.or_(rd,write),wait)
    cap = c.all(phase[1],c.inv(stall),active)
    advance = cap
    wr = c.and_(cap,write)
    c.group = 'datapath'
    regs = {name:c.register(name) for name in DP_REGS+LATCHES
            if name != "RESULT" and (not counter_pc or not name.startswith('PC_'))}
    if counter_pc:
        pc_parts = [c.counter('PC_N'+str(i)) for i in range(4)]
        regs['PC_LO'], regs['PC_HI'] = pc_parts[0]+pc_parts[1], pc_parts[2]+pc_parts[3]
        c.probes.update(PC_LO=regs['PC_LO'],PC_HI=regs['PC_HI'])
    c.group = 'control'
    lo, hi = step[0],step[1]
    pcl = c.any(c.and_(c.or_(addrpc,adjpc),lo), c.and_(stacklo,iscall))
    pch = c.any(c.and_(c.or_(addrpc,adjpc),hi), c.and_(stackhi,iscall))
    rpl = c.any(c.and_(c.or_(addrrp,adjrp),lo),st[23])
    rph = c.any(c.and_(c.or_(addrrp,adjrp),hi),st[25])
    r0 = c.or_(alur0,memstore)
    tmpsrc = c.or_(addrtmp,st[10])
    source = dict(R0=r0,PC_LO=pcl,PC_HI=pch,RP_LO=rpl,RP_HI=rph,
                  TMP_LO=c.and_(tmpsrc,lo),TMP_HI=c.and_(tmpsrc,hi))
    lit15 = c.and_(addrlit,hi)
    lit1 = c.and_(any_stage(13,24),lo)
    lit255 = c.and_(st[6],io)
    const = [c.any(lit255,lit15 if i < 4 else 0,lit1 if i == 0 else 0) for i in range(8)]
    consten = c.or_(addrlit,st[6])
    c.group = 'bus'
    drivers = [c.buffer(regs[name],en) for name,en in source.items()]
    drivers += [c.buffer(const,consten), memory]
    bus = c.resolve_bus(drivers)
    c.probes['CPU_BUS_DRIVER'] = bus  # the same shared bus; no second output buffer
    c.group = 'alu_control'
    sub = c.or_(neg,c.and_(alur0,k[13]))
    unit = adjust
    cin = c.mux(unit,[sub],[c.inv(sub)])[0]
    high = c.inv(cin)
    c.group = 'alu'
    y, carry = c.import_arithmetic_alu(bus,regs['MBR'],cin,sub,high)
    c.group = 'control'
    writeback = c.mux(alurun,bus,y)
    c.probes['WRITEBACK'] = writeback
    operand = st[5]
    dest = dict(
        R0=c.or_(memload,c.and_(aluwrite,c.inv(k[13]))),
        PC_LO=c.or_(c.and_(adjpc,lo),c.and_(st[10],lo)),
        PC_HI=c.or_(c.and_(adjpc,hi),c.and_(st[10],hi)),
        RP_LO=c.or_(st[12],c.and_(adjrp,lo)),
        RP_HI=c.or_(st[14],c.and_(adjrp,hi)),
        ADDR_LO=c.and_(addr,lo),ADDR_HI=c.and_(addr,hi),
        MBR=c.and_(operand,aluclass),
        TMP_LO=c.or_(c.all(operand,c.inv(aluclass),c.inv(second[0])),c.and_(stacklo,c.inv(iscall))),
        TMP_HI=c.any(st[6],c.all(operand,c.inv(aluclass),second[0]),c.and_(stackhi,c.inv(iscall))))
    for name,en in dest.items():
        if counter_pc and name.startswith('PC_'): continue
        c.bind_enabled(name,writeback,c.and_(cap,en))
    if counter_pc:
        pc_inc = c.all(cap,c.or_(c.and_(st[1],c.inv(c.eq(memory,10))),st[5]))
        cascade = 1
        for i,q in enumerate(pc_parts):
            name = 'PC_N'+str(i)
            c.probes[name+'.RCO'] = [c.wire(name+'_RCO')]
            c.bind_counter(name,writeback[4*(i%2):4*(i%2)+4],
                           c.and_(cap,dest['PC_LO' if i<2 else 'PC_HI']),pc_inc,reset)
            c.pins(name, ENT=cascade)
            cascade = c.probes[name+'.RCO'][0]
    c.bind_enabled('CLASS',bus,c.and_(cap,st[1]))
    c.group = 'flags_stack_checks'
    fl = c.and_(cap,aluwrite)
    c.bind(flags,[c.mux(fl,[flags[0]],[c.eq(y,0)])[0],
                  c.mux(fl,[flags[1]],[carry])[0]],1)
    rp = regs['RP_LO']+bus
    invalid = c.any(rp[0],c.lt(rp,0xF600),c.inv(c.lt(rp,0xFEF1)))
    overflow = c.all(c.inv(invalid),iscall,c.eq(rp,0xFEF0))
    underflow = c.all(c.inv(invalid),c.inv(iscall),c.eq(rp,0xF600))
    bad = c.all(cap,st[14],c.any(invalid,overflow,underflow))
    c.bind(fault,[c.or_(invalid,underflow),c.or_(overflow,underflow)],bad)
    c.group = 'control'
    two = c.any(addr,st[10])
    propagation = c.mux(neg,[carry],[c.inv(carry)])[0]
    last = c.any(c.all(c.inv(adjust),c.inv(two)),
                 c.and_(two,step[1]),
                 c.all(adjust,c.or_(step[1],c.inv(propagation))))
    leave = c.and_(advance,last)
    short = c.or_(k[0],isret)
    wide = c.any(k[4],k[5],iscall,k[15])
    more = c.and_(c.inv(second[0]),wide)
    execute = c.or_(c.and_(st[2],short),c.and_(st[5],c.inv(more)))
    targets = {
        26:c.and_(st[1],c.eq(memory,10)), 2:c.and_(st[1],c.inv(c.eq(memory,10))),
        3:c.or_(c.all(st[2],c.inv(short)),c.and_(st[5],more)),
        16:c.and_(st[14],iscall),27:c.and_(st[14],c.inv(iscall)),15:st[27],
        9:c.and_(execute,aluclass),6:c.all(execute,c.any(k[2],k[3],k[8],k[9])),
        7:c.and_(execute,k[15]),
        10:c.or_(st[25],c.all(execute,c.or_(k[5],c.and_(k[4],flags[0])))),
        11:c.all(execute,c.or_(iscall,isret))}
    normal = c.inv(any_stage(1,2,5,8,9,10,14,25,26,27))
    target = [c.any(*(en for val,en in targets.items() if val>>i&1)) for i in range(5)]
    # Both fetch outcomes have bit 1 set; both RP paths have bit 4 set.
    target[1] = c.any(st[1],*(en for val,en in targets.items() if val not in (2,26) and val & 2))
    target[4] = c.or_(targets[26],st[14])
    loadstage = c.all(leave,c.inv(normal))
    incstage = c.and_(leave,normal)
    c.bind_counter('S_LO',target[:4],loadstage,incstage,reset)
    c.bind_counter('S_HI',[target[4],0,0,0],loadstage,c.and_(incstage,c.probes['S_LO.RCO'][0]),reset)
    c.bind(t,[c.all(c.inv(last),c.inv(t[0]))],advance)
    c.bind(p,[c.and_(c.inv(reset),c.inv(p[0]))],c.or_(reset,c.all(active,c.inv(stall))))
    # SECOND is a per-instruction operand latch: reset when IR is captured,
    # set when an operand is captured. No next-fetch target decode is needed.
    c.bind(second,[c.inv(st[1])],c.and_(cap,c.or_(st[1],st[5])))
    c.group = 'memory_decode'
    address = regs['ADDR_LO']+regs['ADDR_HI']
    top = c.eq(address[8:],255)
    vector = c.all(top,c.eq(address[2:8],63))
    mailbox = c.all(top,c.inv(vector))
    rom = c.all(c.inv(mode),c.or_(c.eq(address[11:],0),vector))
    ram = c.inv(c.or_(rom,mailbox))
    for name,value in dict(CAP=cap,RD=c.and_(rd,active),WR=wr,ROM_SEL=rom,
        RAM0_SEL=c.all(ram,c.inv(address[15])),RAM1_SEL=c.and_(ram,address[15]),
        MAILBOX_SEL=mailbox,MEM_WE=c.all(wr,c.inv(rom)),STOP=st[26]).items(): c.probes[name]=[value]
    c.probes.update(PHASE=p,STAGE=s,STEP=t)
    # 161 RCO = ENT & Q0 & Q1 & Q2 & Q3. A device output, no extra IC.
    # Insert before consumers to maintain topological evaluation order.
    rco_ops=[]
    for name in ('S_LO','S_HI') + (tuple('PC_N'+str(i) for i in range(4)) if counter_pc else ()):
        rco_ops.append(('161_RCO',tuple(c.probes[name])+tuple(c.probes[name+'.ENT']),tuple(c.probes[name+'.RCO']),'wire'))
    c.ops = rco_ops+c.ops
    c.finalize()
    c = optimize(c,multi_or=True)
    if polarity:
        c = assign(c)
    c.finish_devices()
    return c


class DirectTtlCpu(CompactTtlCpu):
    counter_pc = False

    def __init__(self):
        self.mem = MemSystem()
        self.circuit = deepcopy(build(counter_pc=self.counter_pc))
        self.reset()

    def reset(self, pc=0):
        super().reset(pc)
        self.latches.pop('RESULT')

    def step_instruction(self, *, wait_every=0):
        if self.halted: return
        c = self.circuit
        if not self._initialized:
            for name, value in self.dp.items(): c.set(c.probes[name], value)
            c.set(c.probes['FLAGS'], int(self.z) | int(self.c) << 1)
            self._initialized = True
        waited = False
        for _ in range(2048):
            self._settle()
            if self.read('STOP'):
                self.halted = True
                self.retired += 1
                return
            phase = self.read('PHASE')
            wait = bool(phase == 1 and wait_every and not waited and self.transfers % wait_every == 0)
            if wait: waited = True
            mem, key, writable, address = self._settle(int(wait))
            committed = self.read('CAP')
            if committed:
                value = self.read('BYTE_BUS') if self.read('RD') or self.read('WR') else 0
                if self.read('RD'): self.accesses.append(('read', address, value))
                if self.read('WR'):
                    assert bool(self.read('MEM_WE')) == writable
                    if writable: mem[key] = value
                    self.accesses.append(('write', address, value))
                self.transfers += 1
            c.clock()
            self.ticks += 1
            for name in self.dp: self.dp[name] = self.read(name)
            for name in self.latches: self.latches[name] = self.read(name)
            flags = self.read('FLAGS')
            self.z, self.c, self.work_carry = bool(flags & 1), bool(flags & 2), bool(flags & 4)
            fault = self.read('FAULT')
            if fault:
                self.fault = (None, 'invalid return stack pointer', 'return stack overflow', 'return stack underflow')[fault]
                self.halted = True
                return
            if phase == 1 and committed:
                waited = False
                if self.read('STAGE') == 0 and self.read('STEP') == 0:
                    self.retired += 1
                    return
        raise AssertionError('74 direct-writeback CU clock cap')


def main():
    """Rebuild both physical candidates and compare complete memory traces."""
    from simulators.cyclesim.hybrid.compact_ttl import build as baseline
    from simulators.cyclesim.hybrid.compare import paired, run_pair
    from simulators.cyclesim.fixtures.rom_builder import build_fib_to_limit_rom, build_fib_recursive_rom

    class CounterPcCpu(DirectTtlCpu):
        counter_pc = True

    cases = [('fib_iterative',build_fib_to_limit_rom(250)[:3]),
             ('fib_recursive_3',build_fib_recursive_rom(3)),
             ('add_256',(bytes([1,1])*256+bytes([10]),{},0))]
    variants = []
    for cls in (DirectTtlCpu,CounterPcCpu):
        circuit=build(counter_pc=cls.counter_pc)
        measured=[]
        for name,(blob,ram,expected) in cases:
            cpu,ref=paired(blob,ram,cpu_class=cls)
            run_pair(cpu,ref,cap=10000)
            assert cpu.r0==expected and not cpu.fault
            measured.append(dict(name=name,ticks=cpu.ticks,instructions=cpu.retired,
                architectural_and_memory_access_match=True))
        variants.append(dict(counter_pc=cls.counter_pc,logic_packages=len(circuit.packages),
            logic_plus_program_memory=len(circuit.packages)+3,
            parts=dict(sorted(Counter(p.part for p in circuit.packages).items())),
            groups=circuit.inventory(),cases=measured))
    out=Path('simulators/cyclesim/build/direct-ttl')
    out.mkdir(parents=True,exist_ok=True)
    netlist=json.dumps(build().export(),indent=2)+'\n'
    (out/'netlist.json').write_text(netlist,encoding='utf-8')
    paths=[Path(__file__),Path(__file__).with_name('compact_ttl.py'),
           Path('simulators/cyclesim/ttl/polarity.py'),Path('simulators/cyclesim/ttl/netlist.py'),
           Path('simulators/cyclesim/ttl/optimize.py')]
    root=Path.cwd().resolve()
    report=dict(scope='Functional-pin all-74 redesign; not physical timing acceptance',
        baseline_logic_packages=len(baseline().packages),selected_counter_pc=False,
        variants=variants,cplds=0,control_roms=0,phase_count=2,
        read_memory_bus_bits=8,additional_shared_writeback_bits=8,
        isa_and_stack_checks_preserved=True,physical_timing_verified=False,
        excludes=['oscillator','physical reset/boot circuit','load buffers',
                  'mailbox coprocessor','power/passives'],
        source_sha256={p.resolve().relative_to(root).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},
        netlist_sha256=hashlib.sha256(netlist.encode()).hexdigest())
    (out/'comparison.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,indent=2))


if __name__=='__main__': main()
