"""Package-oriented shared-bus CPU: 161 counters, 238 decode, 377 storage.

Keep the structured CU's legal schedule and ISA. No control ROM or CPLD.
"""
from copy import deepcopy
from functools import lru_cache
from collections import Counter
import hashlib
import json
from pathlib import Path

from simulators.cyclesim.ttl.netlist import Circuit, Package
from simulators.cyclesim.ttl.optimize import optimize
from simulators.cyclesim.values import X, Z
from simulators.cyclesim.hybrid.structured_ttl import StructuredTtlCpu
from simulators.cyclesim.hybrid.cpu import DP_REGS, LATCHES
from simulators.cyclesim.blocks.mem_decode import MemSystem


class PartsCircuit(Circuit):
    def __init__(self):
        super().__init__()
        self.devices = []

    def device(self, name, kind, width):
        q = self.bus(name, width)
        self.devices.append((name, kind, self.group))
        return q

    def pins(self, name, **pins):
        for key, value in pins.items():
            self.probes[name + '.' + key] = list(value) if isinstance(value, (tuple, list)) else [value]

    def register(self, name): return self.device(name, '74HC377', 8)

    def bind_enabled(self, name, data, enable):
        self.pins(name, D=data, EN_N=self.inv(enable))

    def counter(self, name): return self.device(name, '74HC161', 4)

    def bind_counter(self, name, data, load, enable, reset):
        self.pins(name, D=data, LOAD_N=self.inv(load), ENP=enable, ENT=1, CLR_N=self.inv(reset))

    def decode(self, inputs, e1=0, e2=0, e3=1):
        p = self.package('74HC238')
        outs = [self.wire(f'{p.ref}.Y{i}') for i in range(8)]
        ins = list(inputs) + [e1, e2, e3]
        p.pins.update({f'A{i}': n for i,n in enumerate(inputs)})
        p.pins.update(E1_N=e1, E2_N=e2, E3=e3)
        p.pins.update({f'Y{i}': n for i,n in enumerate(outs)})
        self.ops.append(('74HC238', tuple(ins), tuple(outs), p.ref))
        return outs

    def buffer(self, data, enable):
        p = self.package('74HC244')
        en = self.inv(enable)
        outs = [self.wire(f'{p.ref}.B{i}') for i in range(8)]
        p.pins.update({f'A{i}': n for i,n in enumerate(data)})
        p.pins.update({f'B{i}': n for i,n in enumerate(outs)})
        p.pins.update(OE1_N=en, OE2_N=en)
        self.ops.append(('74HC244', tuple(data)+ (en,), tuple(outs), p.ref))
        return outs

    def resolve_bus(self, drivers):
        bus = self.bus('BYTE_BUS', 8)
        for i, out in enumerate(bus):
            self.ops.append(('RESOLVE', tuple(d[i] for d in drivers), (out,), 'wire'))
        return bus

    def finish_devices(self):
        for name, kind, group in self.devices:
            p = Package('R_' + name, kind, group, {'VCC':1, 'GND':0, 'CLK':self.clock_net})
            p.pins.update({f'Q{i}': n for i,n in enumerate(self.probes[name])})
            for key in ('D', 'EN_N') if kind == '74HC377' else ('D','LOAD_N','ENP','ENT','CLR_N'):
                nets = self.probes[name + '.' + key]
                if key == 'D': p.pins.update({f'D{i}': n for i,n in enumerate(nets)})
                else: p.pins[key] = nets[0]
            if kind == '74HC161':
                p.pins['RCO'] = self.probes[name + '.RCO'][0]
            self.packages.append(p)
        self.finalize()

    def clock(self):
        # Sample every device before changing any Q, including enabled banks.
        sampled = []
        for name, kind, _ in self.devices:
            q = self.probes[name]
            def pin(key): return self.read(self.probes[name + '.' + key])
            if kind == '74HC377':
                value = pin('D') if pin('EN_N') == 0 else self.read(q)
            elif pin('CLR_N') == 0: value = 0
            elif pin('LOAD_N') == 0: value = pin('D')
            elif pin('ENP') and pin('ENT'): value = (self.read(q)+1) & 15
            else: value = self.read(q)
            sampled.append((q, value))
        super().clock()
        for q, value in sampled: self.set(q, value)

    def settle(self):
        super().settle()
        cleared = False
        for name,kind,_ in self.devices:
            if kind == '74HC161' and self.read(self.probes[name+'.CLR_N']) == 0:
                if any(self.values[n] != 0 for n in self.probes[name]):
                    self.set(self.probes[name],0)
                    cleared = True
        if cleared: super().settle()

    def export(self):
        out = super().export()
        out['boundary'] = ('Functional pins, actual 377 data enables and 161 load/count controls. '
                           'Common clock. Initial values are a fixture; no board timing or reset-vector boot acceptance.')
        out['wire_resolution'] = [{'inputs':[self.names[n] for n in ins], 'output':self.names[outs[0]]}
                                  for kind,ins,outs,_ in self.ops if kind == 'RESOLVE']
        return out


@lru_cache(None)
def build():
    c = PartsCircuit()
    wait, reset, mode = [c.bus(n,1)[0] for n in ('WAIT','RESET','MAP_MODE')]
    memory = c.bus('MEMORY_INPUT', 8)
    sl, sh, t, p = [c.counter(n) for n in ('S_LO','S_HI','T','P')]
    s = sl + sh[:1]
    klass = c.register('CLASS')
    second = c.reg('SECOND',1)
    flags = c.reg('FLAGS',3)
    fault = c.reg('FAULT',2)
    # Counter ripple outputs belong to each 161, rather than external ANDs.
    for name,q in [('S_LO',sl),('S_HI',sh),('T',t),('P',p)]:
        # RCO is only consumed on the stage low nibble; implement as a device
        # output operation below when all ENT pins have been bound.
        c.probes[name + '.RCO'] = [c.wire(name + '_RCO')]
    st = []
    for hi in range(4):
        st += c.decode(s[:3], c.inv(s[3]) if hi & 1 else s[3], c.inv(s[4]) if hi & 2 else s[4])
    step = c.decode(t[:3])
    phase = c.decode(p[:2]+[0])
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
    adjpc = any_stage(2,4)
    adjrp = any_stage(15,18,21)
    adjust = c.or_(adjpc,adjrp)
    neg = c.or_(st[15],c.and_(st[21],c.inv(iscall)))
    alolo, alohi = c.and_(adjust,step[1]), c.and_(adjust,step[3])
    writelo, writehi = c.and_(adjust,step[2]), c.and_(adjust,step[4])
    addrpc, addrtmp, addrrp = any_stage(0,3), st[7], any_stage(16,19)
    addrlit = any_stage(11,13,22,24)
    addr = c.any(addrpc,addrtmp,addrrp,addrlit)
    alur0 = c.and_(st[9],step[0])
    aluwrite = c.and_(st[9],step[1])
    alurun = c.any(alolo,alohi,alur0)
    memload = c.and_(st[8],loadclass)
    memstore = c.and_(st[8],c.inv(loadclass))
    stacklo, stackhi = st[17],st[20]
    stack = c.or_(stacklo,stackhi)
    rd = c.any(any_stage(1,5,12,14),memload,c.and_(stack,c.inv(iscall)))
    write = c.any(memstore,c.and_(stack,iscall),st[23],st[25])
    stall = c.all(phase[1],c.or_(rd,write),wait)
    cap = c.all(phase[1],c.inv(stall),active)
    advance = c.and_(phase[3],active)
    wr = c.and_(cap,write)
    c.group = 'datapath'
    regs = {name:c.register(name) for name in DP_REGS+LATCHES}
    c.group = 'control'
    lo, hi = step[0],step[1]
    pcl = c.any(c.and_(addrpc,lo), c.and_(adjpc,alolo), c.and_(stacklo,iscall))
    pch = c.any(c.and_(addrpc,hi), c.and_(adjpc,alohi), c.and_(stackhi,iscall))
    rpl = c.any(c.and_(addrrp,lo),c.and_(adjrp,alolo),st[23])
    rph = c.any(c.and_(addrrp,hi),c.and_(adjrp,alohi),st[25])
    r0 = c.or_(alur0,memstore)
    tmpsrc = c.or_(addrtmp,st[10])
    source = dict(R0=r0,PC_LO=pcl,PC_HI=pch,RP_LO=rpl,RP_HI=rph,
                  TMP_LO=c.and_(tmpsrc,lo),TMP_HI=c.and_(tmpsrc,hi),
                  RESULT=c.any(writelo,writehi,aluwrite))
    lit2 = c.and_(st[15],step[0])
    lit15 = c.and_(addrlit,hi)
    lit1 = c.and_(any_stage(13,24),lo)
    lit255 = c.and_(st[6],io)
    const = [c.any(lit255,lit15 if i < 4 else 0,lit1 if i == 0 else 0,lit2 if i == 1 else 0) for i in range(8)]
    consten = c.any(addrlit,st[6],lit2)
    c.group = 'bus'
    drivers = [c.buffer(regs[name],c.and_(active,en)) for name,en in source.items()]
    drivers += [c.buffer(const,c.and_(active,consten)), memory]
    bus = c.resolve_bus(drivers)
    c.probes['CPU_BUS_DRIVER'] = bus  # the same shared bus; no second output buffer
    c.group = 'alu_control'
    sub = c.or_(neg,c.and_(alur0,k[13]))
    unit = c.or_(alohi,c.and_(alolo,c.inv(st[15])))
    cin = c.mux(unit,[sub],[c.inv(sub)])[0]
    high = c.inv(cin)
    c.group = 'alu'
    y, carry = c.import_arithmetic_alu(bus,regs['MBR'],cin,sub,high)
    c.group = 'control'
    operand = st[5]
    dest = dict(
        R0=c.or_(memload,c.and_(aluwrite,c.inv(k[13]))),
        PC_LO=c.or_(c.and_(adjpc,writelo),c.and_(st[10],lo)),
        PC_HI=c.or_(c.and_(adjpc,writehi),c.and_(st[10],hi)),
        RP_LO=c.or_(st[12],c.and_(adjrp,writelo)),
        RP_HI=c.or_(st[14],c.and_(adjrp,writehi)),
        ADDR_LO=c.and_(addr,lo),ADDR_HI=c.and_(addr,hi),
        MBR=c.or_(lit2,c.and_(operand,aluclass)),
        TMP_LO=c.or_(c.all(operand,c.inv(aluclass),c.inv(second[0])),c.and_(stacklo,c.inv(iscall))),
        TMP_HI=c.any(st[6],c.all(operand,c.inv(aluclass),second[0]),c.and_(stackhi,c.inv(iscall))),
        RESULT=alurun)
    for name,en in dest.items(): c.bind_enabled(name,y if name=='RESULT' else bus,c.and_(cap,en))
    c.bind_enabled('CLASS',bus,c.and_(cap,st[1]))
    c.group = 'flags_stack_checks'
    fl = c.and_(cap,aluwrite)
    wc = c.and_(cap,alurun)
    c.bind(flags,[c.mux(fl,[flags[0]],[c.eq(bus,0)])[0],
                  c.mux(fl,[flags[1]],[flags[2]])[0],
                  c.mux(wc,[flags[2]],[carry])[0]],1)
    rp = regs['RP_LO']+bus
    invalid = c.any(rp[0],c.lt(rp,0xF600),c.inv(c.lt(rp,0xFEF1)))
    overflow = c.all(c.inv(invalid),iscall,c.eq(rp,0xFEF0))
    underflow = c.all(c.inv(invalid),c.inv(iscall),c.eq(rp,0xF600))
    bad = c.all(cap,st[14],c.any(invalid,overflow,underflow))
    c.bind(fault,[c.or_(invalid,underflow),c.or_(overflow,underflow)],bad)
    c.group = 'control'
    two = c.any(addr,st[9],st[10])
    propagation = c.mux(neg,[flags[2]],[c.inv(flags[2])])[0]
    last = c.any(c.all(c.inv(adjust),c.inv(two)),c.and_(two,step[1]),
                 c.all(adjust,c.or_(step[4],c.all(step[2],c.inv(propagation)))))
    leave = c.and_(advance,last)
    short = c.or_(k[0],isret)
    wide = c.any(k[4],k[5],iscall,k[15])
    more = c.and_(c.inv(second[0]),wide)
    execute = c.or_(c.and_(st[2],short),c.and_(st[5],c.inv(more)))
    targets = {
        26:c.and_(st[1],k[10]), 2:c.and_(st[1],c.inv(k[10])),
        3:c.or_(c.all(st[2],c.inv(short)),c.and_(st[5],more)),
        16:c.and_(st[14],iscall),15:c.and_(st[14],c.inv(iscall)),
        9:c.and_(execute,aluclass),6:c.all(execute,c.any(k[2],k[3],k[8],k[9])),
        7:c.and_(execute,k[15]),
        10:c.or_(st[25],c.all(execute,c.or_(k[5],c.and_(k[4],flags[0])))),
        11:c.all(execute,c.or_(iscall,isret))}
    normal = c.inv(any_stage(1,2,5,8,9,10,14,25,26))
    target = [c.any(*(en for val,en in targets.items() if val>>i&1)) for i in range(5)]
    loadstage = c.all(leave,c.inv(normal))
    incstage = c.and_(leave,normal)
    c.bind_counter('S_LO',target[:4],loadstage,incstage,reset)
    c.bind_counter('S_HI',[target[4],0,0,0],loadstage,c.and_(incstage,c.probes['S_LO.RCO'][0]),reset)
    unitstart = c.any(st[3],st[17],st[20],targets[2])
    c.bind_counter('T',[unitstart,0,0,0],leave,advance,reset)
    c.bind_counter('P',[0]*4,0,c.all(active,c.inv(stall)),reset)
    nextfetch = c.all(leave,c.inv(normal),c.inv(c.any(*targets.values())))
    c.bind(second,[c.and_(c.inv(nextfetch),c.or_(second[0],c.and_(leave,st[5])))],1)
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
    c.probes.update(PHASE=p[:2],STAGE=s,STEP=t[:3])
    # 161 RCO = ENT & Q0 & Q1 & Q2 & Q3. A device output, no extra IC.
    # Insert before consumers to maintain topological evaluation order.
    rco_ops=[]
    for name in ('S_LO','S_HI','T','P'):
        rco_ops.append(('161_RCO',tuple(c.probes[name])+tuple(c.probes[name+'.ENT']),tuple(c.probes[name+'.RCO']),'wire'))
    c.ops = rco_ops+c.ops
    c.finalize()
    c = optimize(c,multi_or=True)
    c.finish_devices()
    return c


class CompactTtlCpu(StructuredTtlCpu):
    def __init__(self):
        self.mem=MemSystem()
        self.circuit=deepcopy(build())
        self.reset()

    def reset(self,pc=0):
        super().reset(pc)
        for name,_,_ in self.circuit.devices: self.circuit.set(self.circuit.probes[name],0)

    def _settle(self,wait=0):
        c=self.circuit
        c.set(c.probes['WAIT'],wait)
        c.set(c.probes['RESET'],0)
        c.set(c.probes['MAP_MODE'],self.mem.map_mode)
        for net in c.probes['MEMORY_INPUT']: c.values[net]=Z
        c.settle()
        a=self.read('ADDR_LO') | self.read('ADDR_HI')<<8
        if self.read('MAILBOX_SEL'): mem,key,writable=self.mem.mailbox,a&255,True
        elif self.read('ROM_SEL'): mem,key,writable=self.mem.rom,a,False
        else: mem,key,writable=self.mem.ram,a,True
        if self.read('RD'): c.set(c.probes['MEMORY_INPUT'],mem.get(key,0)&255)
        c.settle()
        enabled = sum(c.values[p.pins['OE1_N']] == 0 for p in c.packages if p.part == '74HC244')
        assert enabled + self.read('RD') <= 1, 'shared bus driver collision'
        return mem,key,writable,a


def main():
    from simulators.cyclesim.hybrid.compare import paired, run_pair
    from simulators.cyclesim.fixtures.rom_builder import build_fib_recursive_rom, build_fib_to_limit_rom
    c=build()
    cases=[]
    programs=[('fib_iterative',build_fib_to_limit_rom(250)[:3],8920),
              ('fib_recursive_3',build_fib_recursive_rom(3),6604),
              ('add_256',(bytes([1,1])*256+bytes([10]),{},0),12316)]
    for name,(blob,ram,expected),ticks in programs:
        cpu,ref=paired(blob,ram,cpu_class=CompactTtlCpu)
        run_pair(cpu,ref,cap=10000)
        assert cpu.r0==expected and cpu.ticks==ticks and not cpu.fault
        cases.append(dict(name=name,ticks=cpu.ticks,instructions=cpu.retired,
                          architectural_and_memory_access_match=True))
    root=Path(__file__).resolve().parents[3]
    files=[Path(__file__),Path(__file__).with_name('structured_ttl.py'),
           root/'simulators/cyclesim/ttl/netlist.py',root/'simulators/cyclesim/ttl/optimize.py']
    netlist=json.dumps(c.export(),indent=2)+'\n'
    report=dict(scope='Package-oriented all-74 shared-adjust and class/step CPU; no timing acceptance',
                baseline_logic_packages=247,logic_packages=len(c.packages),
                saved_packages=247-len(c.packages),reduction_fraction=(247-len(c.packages))/247,
                program_memory_packages=3,logic_plus_program_memory=len(c.packages)+3,
                parts=dict(sorted(Counter(p.part for p in c.packages).items())),
                groups=c.inventory(),cplds=0,control_roms=0,
                isa_and_stack_checks_preserved=True,cases=cases,
                physical_timing_verified=False,procurement_availability_verified=False,
                excludes=['oscillator','physical reset/boot circuit','load buffers','mailbox coprocessor','power/passives'],
                source_sha256={p.relative_to(root).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in files},
                netlist_sha256=hashlib.sha256(netlist.encode('utf-8')).hexdigest())
    out=root/'simulators/cyclesim/build/compact-ttl'
    out.mkdir(parents=True,exist_ok=True)
    (out/'netlist.json').write_text(netlist,encoding='utf-8')
    (out/'comparison.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,indent=2))


if __name__=='__main__': main()
