"""Execute the educational partition's CUPL and explicit external 74 packages.

Only memory/bus wiring and clock edges are supplied by the harness. No host
opcode dispatch. Source equations plus functional packages, not post-fit timing.
"""
from copy import deepcopy

from simulators.cyclesim.blocks.mem_decode import MemSystem
from simulators.cyclesim.hybrid.cupl_model import Equations, bits, number
from simulators.cyclesim.hybrid.ram_cpld_cpu import alu_circuit
from simulators.cyclesim.hybrid.ram_educational import cu_source, address_source, external_packages
from simulators.cyclesim.hybrid.ram_no1502 import PageDecode74
from simulators.cyclesim.values import resolve, Z


CONTROL_NETS = dict(cmd0='COMMAND[0]', cmd1='COMMAND[1]', immdrive='IMM_DRIVE',
    irloadn='IR_LOAD_N', stepen='STEP_ENABLE', steploadn='STEP_LOAD_N',
    acloadn='AC_LOAD_N', acdriven='AC_DRIVE_N', subcmd='ALU_SUB_COMMAND',
    subn='ALU_SUB_N', rdn='MEM_OE_N', wrn='MEM_WE_N', pcwrite='PC_WRITE',
    pcenable='PC_ENABLE', pcloadn='PC_LOAD_N', pcdriven='PC_DRIVE_N', addrdrive='ADDR_DRIVE')


class External74:
    def __init__(self, external_pc):
        self.packages = {p['ref']:p for p in external_packages(external_pc)}
        self.state = {ref:0 for ref,p in self.packages.items()
                      if p['part'] in ('74HC377','74HC161')}
        self.forced = {}

    def outputs(self, nets):
        # Asynchronous clear exists on 161, never on 377.
        for ref,value in self.state.items():
            p = self.packages[ref]
            if p['part']=='74HC161' and not nets[p['pins']['CLR_N']]:
                self.state[ref] = value = 0
            for i in range(8 if p['part']=='74HC377' else 4):
                net = p['pins'][f'Q{i}']
                nets[net] = self.forced.get(net,value>>i&1)
        # Cascaded RCO depends on ENT and Q, not ENP. All counters share SYS.
        for ref,p in self.packages.items():
            if p['part']=='74HC161' and p['pins']['RCO'] is not None:
                pins=p['pins']
                nets[pins['RCO']] = int(nets[pins['ENT']] and
                    all(nets[pins[f'Q{i}']] for i in range(4)))

    def driver(self, ref, nets):
        p=self.packages[ref]['pins']
        return {p[f'Y{i}']:self.forced.get(p[f'Y{i}'],
                    Z if nets[p['OE1_N' if i<4 else 'OE2_N']] else nets[p[f'A{i}']])
                for i in range(8)}

    def writeback(self, nets):
        for half in range(2):
            p=self.packages[f'WRITEBACK{half}']['pins']
            for i in range(1,5):
                net=p[f'{i}Y']
                value=0 if nets[p['G_N']] else nets[p[f'{i}'+('B' if nets[p['S']] else 'A')]]
                nets[net]=self.forced.get(net,value)
        p=self.packages['ZERO']['pins']
        value=int(nets[p['OE_N']] or any(nets[p[f'P{i}']]!=nets[p[f'Q{i}']] for i in range(8)))
        nets[p['EQ_N']]=self.forced.get(p['EQ_N'],value)

    def next(self, nets):
        result=dict(self.state)
        for ref,value in self.state.items():
            p=self.packages[ref]
            pins=p['pins']
            width=8 if p['part']=='74HC377' else 4
            if p['part']=='74HC161' and not nets[pins['CLR_N']]: result[ref]=0
            elif not nets[pins['EN_N' if width==8 else 'LOAD_N']]:
                data=[nets[pins[f'D{i}']] for i in range(width)]
                assert all(bit in (0,1) for bit in data), ('floating register D',ref)
                result[ref]=sum(bit<<i for i,bit in enumerate(data))
            elif width==4 and nets[pins['ENP']] and nets[pins['ENT']]:
                result[ref]=(value+1)&15
        return result


class EducationalCpu:
    def __init__(self, external_pc=False):
        self.external_pc=external_pc
        self.mem=MemSystem()
        self.cu=Equations(cu_source(external_pc))
        self.addr=Equations(address_source(external_pc))
        self.external=External74(external_pc)
        self.decoder=PageDecode74()
        self.alu=deepcopy(alu_circuit())
        self.reset()

    @property
    def pc(self):
        return (sum(self.external.state[f'PC{i}']<<(4*i) for i in range(4))
                if self.external_pc else number(self.addr.state,'pc',16))
    @property
    def a(self): return self.external.state['AC']
    @property
    def x(self): return number(self.addr.state,'x',8)
    @property
    def p(self): return number(self.addr.state,'page',8)
    @property
    def z(self): return bool(self.cu.state['zflag'])
    @property
    def c(self): return bool(self.cu.state['cflag'])
    @property
    def halted(self): return bool(self.cu.state['halted'])
    @property
    def phase(self): return self.external.state['STEP']

    def reset(self,pc=0):
        """Test fixture initialization; physical RESET_N does not reset IR/AC."""
        for model in (self.cu,self.addr): model.state=dict.fromkeys(model.state,0)
        self.external.state=dict.fromkeys(self.external.state,0)
        if self.external_pc:
            for i in range(4): self.external.state[f'PC{i}']=pc>>(4*i)&15
        else: self.addr.state.update(bits('pc',pc,16))
        self.ticks=self.retired=0
        self.accesses=[]

    def _settle(self,wait=0,reset=0):
        if reset:
            for model in (self.cu,self.addr):model.state=dict.fromkeys(model.state,0)
        nets=dict(GND=0,VCC=1,SYS=0,RESET_N=1-reset)
        self.external.outputs(nets)
        common=dict(clk=0,resetn=1-reset,wait=wait)
        cu_inputs={**common,'zeron':1,'carry':0,
                   **{f'ir{i}':nets[f'IR[{i}]'] for i in range(6)},
                   **{f't{i}':nets[f'STEP[{i}]'] for i in range(3)}}
        cv=self.cu.values(cu_inputs)
        for signal,net in CONTROL_NETS.items():
            if signal in self.cu.comb:nets[net]=cv[signal]
        addr_inputs={**common,'cmd0':cv['cmd0'],'cmd1':cv['cmd1'],
                     'indexed':nets['IR[7]'],'immdrive':cv['immdrive'],
                     **{f'db{i}_io':0 for i in range(8)}}
        if self.external_pc:addr_inputs['addrdrive']=cv['addrdrive']
        else:addr_inputs.update(execute=nets['STEP[2]'],pcwrite=cv['pcwrite'])
        av=self.addr.values(addr_inputs)
        pc_drivers={}
        if self.external_pc:
            for half in range(2):pc_drivers.update(self.external.driver(f'PC_DRIVER{half}',nets))
        for i in range(16):
            net=f'ADDRESS[{i}]'
            if self.external_pc:
                owners=int(not cv['pcdriven'])+av[f'addr{i}_oe']
                assert owners==int(cv['active'] and cv['t0']), 'address bus ownership'
                nets[net]=resolve([pc_drivers[net],av[f'addr{i}'] if av[f'addr{i}_oe'] else Z])
            else:nets[net]=av[f'addr{i}']
        if cv['rdn']==0 or cv['wrn']==0 or cv['branch']:
            assert all(nets[f'ADDRESS[{i}]'] in (0,1) for i in range(16)), 'floating address'
        address=sum((nets[f'ADDRESS[{i}]'] if nets[f'ADDRESS[{i}]'] in (0,1) else 0)<<i
                    for i in range(16))
        select=self.decoder.decode(address,self.mem.map_mode)
        assert sum(v==0 for v in select.values())==1, 'memory select ownership'
        if select['romn']==0:mem,key,writable=self.mem.rom,address,False
        elif select['mbn']==0:mem,key,writable=self.mem.mailbox,address&255,True
        else:
            key=(address&0x7FFF)|(0x8000 if select['ram1n']==0 else 0)
            mem,writable=self.mem.ram,True
        reading=cv['rdn']==0
        ac_driver=self.external.driver('AC_DRIVER',nets)
        memory_value=mem.get(key,0)&255
        for i in range(8):
            assert int(reading)+av[f'db{i}_oe']+int(not cv['acdriven'])<=1, 'data bus ownership'
            nets[f'DB[{i}]']=resolve([memory_value>>i&1 if reading else Z,
                av[f'db{i}'] if av[f'db{i}_oe'] else Z, ac_driver[f'DB[{i}]']])
        if reading or cv['wrn']==0 or cv['commit'] and cv['ordinary']:
            assert all(nets[f'DB[{i}]'] in (0,1) for i in range(8)), 'floating data'
        byte=sum((nets[f'DB[{i}]'] if nets[f'DB[{i}]'] in (0,1) else 0)<<i for i in range(8))
        # Only unused combinational inputs are coerced. Capture assertions above
        # reject floating buses before any memory, flag or register write.
        a_pins=sum(nets[f'A[{i}]']<<i for i in range(8))
        for probe,value in (('A',a_pins),('DB',byte),('SUB',cv['subcmd']),
                            ('SUB_N',cv['subn']),('LOGICAL',nets['IR[5]'])):
            self.alu.set(self.alu.probes[probe],value)
        self.alu.settle()
        y=self.alu.read(self.alu.probes['Y'])
        for i in range(8):nets[f'Y[{i}]']=y>>i&1
        self.external.writeback(nets)
        cv=self.cu.values({**cu_inputs,'zeron':nets['ZERO_N'],
                           'carry':self.alu.read(self.alu.probes['CARRY'])})
        av=self.addr.values({**addr_inputs,**{f'db{i}_io':byte>>i&1 for i in range(8)},
                             **{f'addr{i}_io':address>>i&1 for i in range(16)}})
        return cv,av,nets,mem,key,writable,address,byte

    def clock(self,wait=0,reset=0):
        cv,av,nets,mem,key,writable,address,byte=self._settle(wait,reset)
        if cv['cap']:
            if cv['rdn']==0:self.accesses.append(('read',address,byte))
            if cv['wrn']==0:
                if writable:mem[key]=byte
                self.accesses.append(('write',address,byte))
        nc,na,ne=self.cu.next(cv),self.addr.next(av),self.external.next(nets)
        self.cu.state=dict.fromkeys(nc,0) if reset else nc
        self.addr.state=dict.fromkeys(na,0) if reset else na
        self.external.state=ne
        self.ticks+=1
        self.retired+=cv['commit']
        return bool(cv['commit'])

    def step_instruction(self,waits=0):
        if self.halted:return
        if not 0<=waits<=32:raise ValueError('waits must be 0..32')
        remaining=waits
        for _ in range(3*(waits+1)+6):
            cv,*_=self._settle()
            pending=cv['t0'] and (cv['readreq'] or cv['writereq'])
            wait=pending and remaining>0
            if wait:remaining-=1
            if self.clock(int(wait)):return
            if not self.phase&1:remaining=waits
        raise AssertionError('educational CPU instruction clock cap')
