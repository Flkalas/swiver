"""Clock-edge evaluation of fitted RAM-ISA CUPL sources plus the external ALU.

This evaluates source equations, not a post-fit timing netlist. All CPU state
updates come from the CUPL .d/.ar equations. Host code connects physical buses,
supplies asynchronous memory and advances the shared clock.
"""
from copy import deepcopy
from functools import lru_cache

from simulators.cyclesim.blocks.mem_decode import MemSystem
from simulators.cyclesim.hybrid.cupl_model import Equations, bits, number
from simulators.cyclesim.hybrid.ram_cpld import cu_source, address_source, decoder_source, FIT_NODES
from simulators.cyclesim.ttl.netlist import Circuit
from simulators.cyclesim.values import resolve, Z


@lru_cache(None)
def alu_circuit():
    c = Circuit()
    a, b = c.bus('A',8), c.bus('DB',8)
    sub, subn, logical = [c.bus(name,1)[0] for name in ('SUB','SUB_N','LOGICAL')]
    wiring = {'pwr_gnd':0,'pwr_vcc':1,'net_cin':sub,'net_y_mux_sel':logical}
    wiring.update({f'net_a{i}':a[i] for i in range(8)})
    wiring.update({f'net_b{i}':b[i] for i in range(8)})
    wiring.update({f'net_bctrl{i}':sub if i<2 else subn for i in range(4)})
    wiring.update({f'net_lgc{i}':int(i==3) for i in range(4)})
    y, carry = c._import_alu_wiring(wiring)
    c.probes['Y'], c.probes['CARRY'] = y, [carry]
    c.finalize()
    assert len(c.packages)==12
    return c


class RamCpldCpu:
    def __init__(self):
        self.mem = MemSystem()
        self.cu = Equations(cu_source())
        self.addr = Equations(address_source(True,FIT_NODES))
        self.page = Equations(decoder_source(True))
        self.alu = deepcopy(alu_circuit())
        self.reset()

    @property
    def pc(self): return number(self.addr.state,'pc',16)
    @property
    def a(self): return number(self.cu.state,'qa',8)
    @property
    def x(self): return number(self.addr.state,'x',8)
    @property
    def p(self): return number(self.page.state,'page',8)
    @property
    def z(self): return bool(self.cu.state['zflag'])
    @property
    def c(self): return bool(self.cu.state['cflag'])
    @property
    def halted(self): return bool(self.cu.state['halted'])

    def reset(self,pc=0):
        # Fixture initialization, separate from the actual reset-pin path below.
        for model in (self.cu,self.addr,self.page):
            model.state = dict.fromkeys(model.state,0)
        self.addr.state.update(bits('pc',pc,16))
        self.ticks = self.retired = 0
        self.accesses = []

    def _settle(self,wait=0,reset=0):
        if reset:
            # Every generated register has .ar=reset on the shared physical pin.
            for model in (self.cu,self.addr,self.page):
                model.state = dict.fromkeys(model.state,0)
        assert number(self.cu.state,'t',3)==number(self.addr.state,'t',3)
        assert self.cu.state['halted']==self.addr.state['halted']
        common = dict(clk=0,reset=reset,wait=wait)
        cv = self.cu.values({**common,**{f'db{i}_io':0 for i in range(8)},
                             **bits('y',0,8),'carry':0})
        av = self.addr.values({**common,'subcmd':cv['subcmd'],**bits('db',0,8)})
        pv = self.page.values({**common,'execute':av['execout'],'pload':av['ploadout'],
                              **bits('db',0,8),'mapmode':self.mem.map_mode})
        low = [av[f'addr{i}'] for i in range(8)]
        high = []
        for i in range(8,16):
            enabled = [av[f'addr{i}_oe'],pv[f'addr{i}_oe']]
            assert sum(enabled)==cv['t0'], 'high address bus ownership'
            high.append(resolve([av[f'addr{i}'] if enabled[0] else Z,
                                 pv[f'addr{i}'] if enabled[1] else Z]))
        address_bits = low+high
        # Both drivers are off on setup ticks. Memory OE/WE must also be off;
        # arbitrary Boolean values here cannot be captured by an enabled register.
        if not cv['t0']:
            assert cv['rdn']==cv['wrn']==1
        address_bits = [bit if bit in (0,1) else 0 for bit in address_bits]
        address = sum(bit<<i for i,bit in enumerate(address_bits))
        page_inputs = {**common,'execute':av['execout'],'pload':av['ploadout'],
                       'mapmode':self.mem.map_mode,**bits('db',0,8),
                       **{f'addr{i}':address_bits[i] for i in range(2,8)},
                       **{f'addr{i}_io':address_bits[i] for i in range(8,16)}}
        pv = self.page.values(page_inputs)
        select = [pv[name]==0 for name in ('romn','ram0n','ram1n','mbn')]
        assert sum(select)==1, 'memory select ownership'
        if select[0]: mem,key,writable = self.mem.rom,address,False
        elif select[3]: mem,key,writable = self.mem.mailbox,address&255,True
        else:
            key = (address&0x7FFF) | (0x8000 if select[2] else 0)
            mem,writable = self.mem.ram,True
        reading = cv['rdn']==0
        cu_drives = [cv[f'db{i}_oe'] for i in range(8)]
        assert len(set(cu_drives))==1
        assert int(reading)+cu_drives[0]<=1, 'data bus ownership'
        memory_value = mem.get(key,0)&255
        bus = [resolve([memory_value>>i&1 if reading else Z,
                        cv[f'db{i}'] if cu_drives[i] else Z]) for i in range(8)]
        if cv['commit'] and cv['ordinary'] or cv['wrn']==0 or reading:
            assert all(bit in (0,1) for bit in bus), 'consumed floating bus'
        # Undriven Boolean inputs cannot be sampled by any enabled register.
        byte = sum((int(bit) if bit in (0,1) else 0)<<i for i,bit in enumerate(bus))
        self.alu.set(self.alu.probes['A'],self.a)
        self.alu.set(self.alu.probes['DB'],byte)
        self.alu.set(self.alu.probes['SUB'],cv['subcmd'])
        self.alu.set(self.alu.probes['SUB_N'],av['subn'])
        self.alu.set(self.alu.probes['LOGICAL'],cv['logsel'])
        self.alu.settle()
        y = self.alu.read(self.alu.probes['Y'])
        carry = self.alu.read(self.alu.probes['CARRY'])
        cv = self.cu.values({**common,**{f'db{i}_io':byte>>i&1 for i in range(8)},
                             **bits('y',y,8),'carry':carry})
        av = self.addr.values({**common,'subcmd':cv['subcmd'],**bits('db',byte,8),
                               **{f'addr{i}_io':address_bits[i] for i in range(8,16)}})
        pv = self.page.values({**page_inputs,**bits('db',byte,8)})
        return cv,av,pv,mem,key,writable,address,byte

    def clock(self,wait=0,reset=0):
        cv,av,pv,mem,key,writable,address,byte = self._settle(wait,reset)
        if cv['cap']:
            if cv['rdn']==0: self.accesses.append(('read',address,byte))
            if cv['wrn']==0:
                # Flash WE is tied high; SRAM /CE and mailbox /CE qualify writes.
                if writable: mem[key] = byte
                self.accesses.append(('write',address,byte))
        next_states = [model.next(values) for model,values in
                       ((self.cu,cv),(self.addr,av),(self.page,pv))]
        for model,state in zip((self.cu,self.addr,self.page),next_states):
            model.state = dict.fromkeys(state,0) if reset else state
        self.ticks += 1
        self.retired += cv['commit']
        return bool(cv['commit'])

    def step_instruction(self,waits=0):
        if self.halted: return
        if not 0<=waits<=32: raise ValueError('waits must be 0..32')
        remaining = waits
        for _ in range(3*(waits+1)+6):
            cv,*_ = self._settle()
            pending = cv['t0'] and (cv['readreq'] or cv['writereq'])
            wait = pending and remaining>0
            if wait: remaining-=1
            if self.clock(int(wait)): return
            if not self.cu.state['t0']: remaining=waits
        raise AssertionError('CPLD RAM instruction clock cap')
