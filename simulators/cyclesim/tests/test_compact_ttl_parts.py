"""Package semantics and area boundary for the compact all-74 implementation."""
from itertools import product
from collections import Counter

from simulators.cyclesim.hybrid.compact_ttl import PartsCircuit, build
from simulators.cyclesim.ttl.netlist import Circuit
from simulators.cyclesim.ttl.optimize import optimize
from simulators.cyclesim.values import X, Z


def test_compact_377_enable_and_simultaneous_sampling():
    c = PartsCircuit()
    a,b = c.register('A'),c.register('B')
    data,en = c.bus('DATA',8),c.bus('EN',1)
    c.bind_enabled('A',data,en[0])
    c.bind_enabled('B',a,en[0])
    c.finish_devices()
    for value in range(256):
        for enable in (0,1):
            c.set(a,0xA5); c.set(b,0x5A); c.set(data,value); c.set(en,enable)
            c.settle(); c.clock()
            assert c.read(a) == (value if enable else 0xA5)
            assert c.read(b) == (0xA5 if enable else 0x5A)


def test_compact_161_load_enable_clear_and_rco():
    c = PartsCircuit()
    q = c.counter('N')
    data = c.bus('DATA',4)
    load,en,reset,ent = [c.bus(n,1)[0] for n in ('LOAD','EN','RESET','ENT')]
    c.bind_counter('N',data,load,en,reset)
    c.pins('N',ENT=ent,RCO=c.wire('RCO'))
    c.ops.insert(0,('161_RCO',tuple(q)+ (ent,),tuple(c.probes['N.RCO']),'wire'))
    c.finish_devices()
    for old,new,ld,pe,te,clear in product(range(16),range(16),(0,1),(0,1),(0,1),(0,1)):
        c.set(q,old); c.set(data,new)
        for net,value in ((load,ld),(en,pe),(ent,te),(reset,clear)): c.set([net],value)
        c.settle()
        assert c.read(q) == (0 if clear else old)  # asynchronous clear, no edge
        assert c.read(c.probes['N.RCO']) == int(not clear and old==15 and te)
        c.clock()
        assert c.read(q) == (0 if clear else new if ld else (old+1)&15 if pe and te else old)


def test_compact_238_all_address_and_enable_combinations():
    c = PartsCircuit()
    inputs = c.bus('INPUTS',6)
    outputs = c.decode(inputs[:3],*inputs[3:])
    c.finalize()
    for value in range(64):
        c.set(inputs,value); c.settle()
        enabled = not(value & 8) and not(value & 16) and bool(value & 32)
        assert c.read(outputs) == (1 << (value & 7) if enabled else 0)
    for net in inputs[:3]: c.values[net]=X
    c.set(inputs[3:],0); c.settle()
    assert c.read(outputs)==0


def test_compact_244_shared_bus_is_tristate_and_detects_contention():
    c = PartsCircuit()
    a,b = c.bus('A',8),c.bus('B',8)
    ea,eb = c.bus('EA',1),c.bus('EB',1)
    bus = c.resolve_bus([c.buffer(a,ea[0]),c.buffer(b,eb[0])])
    c.finalize()
    c.set(a,0x55); c.set(b,0xAA)
    for va,vb in product((0,1),repeat=2):
        c.set(ea,va); c.set(eb,vb); c.settle()
        if not va and not vb: assert all(c.values[n]==Z for n in bus)
        elif va and vb: assert all(c.values[n]==X for n in bus)
        else: assert c.read(bus)==(0x55 if va else 0xAA)


def test_compact_multi_or_mapping_preserves_four_states():
    c = Circuit()
    inputs=c.bus('INPUTS',3)
    c.probes['OUT']=[c.any(*inputs)]
    c.finalize()
    opt=optimize(c,multi_or=True)
    assert any(p.part=='74HC4075' for p in opt.packages)
    for row in product((0,1,X,Z),repeat=3):
        for model in (c,opt):
            for net,value in zip(model.probes['INPUTS'],row): model.values[net]=value
            model.settle()
        assert c.values[c.probes['OUT'][0]]==opt.values[opt.probes['OUT'][0]]


def test_compact_package_budget_and_real_devices():
    c=build()
    counts=Counter(p.part for p in c.packages)
    assert len(c.packages)<=131
    assert counts['74HC161']==4 and counts['74HC377']==12
    assert counts['74HC238']==8 and counts['74HC244']==9
    assert counts['74HC283']==2  # no private PC/RP adders
    assert sum(p.group=='alu' for p in c.packages)==12
    assert all(p.part.startswith('74HC') for p in c.packages)
    assert not any(p.part=='74HC157' and p.group=='datapath' for p in c.packages)
