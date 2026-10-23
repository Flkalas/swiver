"""All-74 paged-RAM CPU: one 8-bit data bus, a reused 16-bit address path.

The CPU has six fixed clocks per instruction (two fetches and execute, each
setup/capture). RAM can feed A, X, P or the 12-chip ALU directly. No RP, TMP,
MAR, MBR or RESULT storage. Hardware call/stack sequencing is software here.
"""
from copy import deepcopy
from functools import lru_cache

from simulators.cyclesim.hybrid.compact_ttl import PartsCircuit
from simulators.cyclesim.ttl.optimize import optimize
from simulators.cyclesim.ttl.polarity import assign
from simulators.cyclesim.blocks.mem_decode import MemSystem
from simulators.cyclesim.values import Z


@lru_cache(None)
def build(indexed=True, polarity=True):
    c = PartsCircuit()
    wait, reset, mode = [c.bus(n,1)[0] for n in ('WAIT','RESET','MAP_MODE')]
    memory = c.bus('MEMORY_INPUT',8)
    t = c.counter('T')
    ir = c.register('IR')
    halted = c.reg('HALTED',1)
    flags = c.reg('FLAGS',2)
    c.group = 'datapath'
    a, x, page, literal = [c.register(n) for n in ('A','X','P','D')]
    pcs = [c.counter('PC'+str(i)) for i in range(4)]
    pc = sum(pcs,[])
    c.probes['PC'] = pc
    for name,_,_ in c.devices:
        if name == 'T' or name.startswith('PC'):
            c.probes[name+'.RCO'] = [c.wire(name+'_RCO')]
    c.group = 'control'
    execute = t[2]
    fetch = c.inv(execute)
    flow = c.and_(ir[0],ir[1])
    store = ir[4]
    ordinary = c.inv(c.or_(flow,store))
    alu = c.and_(ordinary,ir[3])
    from_mem = c.and_(ordinary,ir[2])
    read = c.or_(fetch,c.and_(execute,from_mem))
    write = c.and_(execute,store)
    active = c.inv(c.or_(halted[0],reset))
    stall = c.all(t[0],wait,c.or_(read,write))
    tick = c.and_(active,c.inv(stall))
    capture = c.and_(tick,t[0])
    commit = c.and_(capture,execute)
    stop = c.all(flow,c.inv(store),ir[2],ir[3])
    take = c.mux(ir[3], [c.or_(c.inv(ir[2]),flags[0])],
                 [c.and_(c.inv(ir[2]),flags[1])])[0]
    branch = c.all(commit,flow,c.inv(store),take)

    c.group = 'address'
    low = c.mux(ir[7],literal,x) if indexed else literal
    address = c.mux(execute,pc,low+page)
    c.probes['ADDRESS'] = address

    c.group = 'bus'
    driver = c.buffer(a,c.and_(active,write))
    bus = c.resolve_bus([driver,memory])
    c.group = 'operand'
    operand = c.mux(from_mem,literal,bus)
    c.group = 'alu_control'
    subtract = c.or_(ir[0],ir[1])
    high = c.inv(subtract)
    c.group = 'alu'
    wiring = {'pwr_gnd':0,'pwr_vcc':1,'net_cin':subtract,'net_y_mux_sel':ir[5]}
    wiring.update({f'net_a{i}':a[i] for i in range(8)})
    wiring.update({f'net_b{i}':operand[i] for i in range(8)})
    wiring.update({f'net_bctrl{i}':subtract if i<2 else high for i in range(4)})
    wiring.update({f'net_lgc{i}':int(i==3) for i in range(4)})  # AND truth table 1000
    y,carry = c._import_alu_wiring(wiring)
    c.group = 'writeback'
    result = c.mux(alu,operand,y)
    c.probes['WRITEBACK'] = result

    c.group = 'control'
    dest = c.decode(ir[:2]+[0],e3=c.all(commit,c.inv(store),c.inv(ir[3])))
    c.bind_enabled('A',result,c.or_(dest[0],c.all(commit,alu,c.inv(ir[1]))))
    c.bind_enabled('X',result,dest[1])
    c.bind_enabled('P',result,dest[2])
    c.bind_enabled('IR',bus,c.all(capture,fetch,c.inv(t[1])))
    c.bind_enabled('D',bus,c.all(capture,fetch,t[1]))
    c.bind(flags,[c.eq(y,0),c.and_(carry,c.inv(ir[5]))],c.and_(commit,alu))
    c.bind(halted,[c.and_(c.inv(reset),c.or_(halted[0],c.and_(commit,stop)))],1)
    c.bind_counter('T',[0]*4,commit,tick,reset)
    cascade = 1
    for i,q in enumerate(pcs):
        name = 'PC'+str(i)
        # Reuse the memory address wires for parallel jump load; no data bus
        # widening and no extra 16-bit target register/mux is hidden here.
        c.bind_counter(name,address[i*4:i*4+4],branch,c.and_(capture,fetch),reset)
        c.pins(name,ENT=cascade)
        cascade = c.probes[name+'.RCO'][0]

    c.group = 'memory_decode'
    top = c.eq(address[8:],255)
    vector = c.all(top,c.eq(address[2:8],63))
    mailbox = c.all(top,c.inv(vector))
    rom = c.all(c.inv(mode),c.or_(c.eq(address[11:],0),vector))
    ram = c.inv(c.or_(rom,mailbox))
    rd,wr = c.and_(active,read),c.and_(capture,write)
    values = dict(CAP=capture,RETIRE=commit,RD=rd,WR=wr,ROM_SEL=rom,
        RAM0_SEL=c.all(ram,c.inv(address[15])),RAM1_SEL=c.and_(ram,address[15]),
        MAILBOX_SEL=mailbox,MEM_WE=c.all(wr,c.inv(rom)),STOP=halted[0])
    # Count real active-low CE/OE/WE outputs for the off-chip memory interface.
    values.update(MEM_OE_N=c.inv(rd),MEM_WE_N=c.inv(values['MEM_WE']),
                  ROM_CE_N=c.inv(rom),RAM0_CE_N=c.inv(values['RAM0_SEL']),
                  RAM1_CE_N=c.inv(values['RAM1_SEL']),MAILBOX_CE_N=c.inv(mailbox))
    c.probes.update({name:[value] for name,value in values.items()})
    rco_ops=[]
    for name in ('T','PC0','PC1','PC2','PC3'):
        rco_ops.append(('161_RCO',tuple(c.probes[name])+tuple(c.probes[name+'.ENT']),
                        tuple(c.probes[name+'.RCO']),'wire'))
    c.ops = rco_ops+c.ops
    c.finalize()
    c = optimize(c,multi_or=True)
    if polarity: c = assign(c)
    c.finish_devices()
    return c


class RamTtlCpu:
    """Host supplies memory and clock only; all CPU decisions are wired gates."""
    def __init__(self):
        self.mem = MemSystem()
        self.circuit = deepcopy(build())
        self.reset()

    def read(self,name): return self.circuit.read(self.circuit.probes[name])
    @property
    def pc(self): return self.read('PC')
    @property
    def a(self): return self.read('A')
    @property
    def x(self): return self.read('X')
    @property
    def p(self): return self.read('P')
    @property
    def z(self): return bool(self.read('FLAGS') & 1)
    @property
    def c(self): return bool(self.read('FLAGS') & 2)
    @property
    def halted(self): return bool(self.read('HALTED'))

    def reset(self,pc=0):
        c = self.circuit
        for name,_,_ in c.devices: c.set(c.probes[name],0)
        for _,q,_ in c.registers: c.set(q,0)
        c.set(c.probes['PC'],pc)
        self.ticks = self.retired = 0
        self.accesses = []

    def _settle(self,wait=0,reset=0):
        c = self.circuit
        c.set(c.probes['WAIT'],wait)
        c.set(c.probes['RESET'],reset)
        c.set(c.probes['MAP_MODE'],self.mem.map_mode)
        for n in c.probes['MEMORY_INPUT']: c.values[n] = Z
        c.settle()
        address = self.read('ADDRESS')
        if self.read('MAILBOX_SEL'): mem,key,writable=self.mem.mailbox,address&255,True
        elif self.read('ROM_SEL'): mem,key,writable=self.mem.rom,address,False
        else: mem,key,writable=self.mem.ram,address,True
        if self.read('RD'): c.set(c.probes['MEMORY_INPUT'],mem.get(key,0)&255)
        c.settle()
        drivers=sum(c.values[p.pins['OE1_N']]==0 for p in c.packages if p.part=='74HC244')
        assert drivers+self.read('RD') <= 1, 'data bus contention'
        return mem,key,writable,address

    def clock(self,wait=0,reset=0):
        mem,key,writable,address = self._settle(wait,reset)
        retire = self.read('RETIRE')
        if self.read('CAP'):
            if self.read('RD'):
                self.accesses.append(('read',address,self.read('BYTE_BUS')))
            if self.read('WR'):
                value = self.read('BYTE_BUS')
                assert bool(self.read('MEM_WE')) == writable
                if writable: mem[key] = value
                self.accesses.append(('write',address,value))
        self.circuit.clock()
        self.ticks += 1
        self.retired += retire
        return bool(retire)

    def step_instruction(self,waits=0):
        if self.halted: return
        if not 0 <= waits <= 32: raise ValueError('waits must be 0..32')
        remaining=waits
        for _ in range(3*(waits+1)+6):
            self._settle()
            pending = bool(self.read('T')&1 and (self.read('RD') or self.read('WR')))
            wait = pending and remaining>0
            if wait: remaining-=1
            if self.clock(int(wait)): return
            if not (self.read('T')&1): remaining=waits
        raise AssertionError('paged RAM instruction clock cap')
