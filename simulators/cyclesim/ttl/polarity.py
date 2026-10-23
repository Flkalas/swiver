"""Deterministic polarity assignment for a physical NAND/NOR implementation.

Search happens at construction time. Execution still evaluates individual 74
channels. No truth-table ROM, hidden PLA, or host control is introduced.
"""
from collections import Counter
from copy import deepcopy
from math import ceil

from simulators.cyclesim.ttl.optimize import optimize, inputs

AND = {2: '74HC08', 3: '74HC11', 4: '74HC21'}
OR = {2: '74HC32', 3: '74HC4075'}
NAND = {2: '74HC00', 3: '74HC10', 4: '74HC20'}
NOR = {2: '74HC02', 3: '74HC27'}
CAP = {**dict.fromkeys(['74HC08','74HC32','74HC00','74HC02'],4),
       **dict.fromkeys(['74HC11','74HC4075','74HC10','74HC27'],3),
       '74HC21':2, '74HC20':2}


def assign(original):
    c = deepcopy(original)
    aliases = {}
    gates = {}
    def root(n):
        phase = 0
        while n in aliases:
            n, p = aliases[n]
            phase ^= p
        return n, phase
    for kind, ins, out, ref in c.ops:
        if kind == '74HC04':
            n, phase = root(ins[0])
            aliases[out[0]] = n, phase ^ 1
        elif kind in set(AND.values()) | set(OR.values()):
            gates[out[0]] = (kind in AND.values(), ins, ref)
    choices = {n: (0,0) for n in gates}
    options = {}
    for n,(is_and,ins,_) in gates.items():
        options[n] = []
        for ip in (0,1):
            for op in (0,1):
                # De Morgan: complementing every input swaps AND and OR.
                table = ((NAND if op else AND) if is_and else (NOR if op else OR)) if not ip else (
                    (OR if op else NOR) if is_and else (AND if op else NAND))
                if len(ins) in table:
                    options[n].append(((ip,op),table[len(ins)]))
    def score():
        inversions = set()
        counts = Counter()
        def need(net, polarity=0):
            n,p = root(net)
            if n in (0,1): return
            if (p ^ polarity) != choices.get(n,(0,0))[1]: inversions.add(n)
        for kind,ins,out,_ in c.ops:
            if kind == '74HC04': continue
            if isinstance(out,tuple) and out[0] in gates:
                ip,_ = choices[out[0]]
                part = dict(options[out[0]])[choices[out[0]]]
                counts[part] += 1
                for n in ins: need(n,ip)
            else:
                for n in inputs((kind,ins,out,'')): need(n)
        for bits in c.probes.values():
            for n in bits: need(n)
        for _,_,ds in c.registers:
            for n in ds: need(n)
        packages = ceil(len(inversions)/6) + sum(ceil(v/CAP[k]) for k,v in counts.items())
        # Fractional package occupancy avoids local minima at package boundaries.
        return len(inversions)/6 + sum(v/CAP[k] for k,v in counts.items()), packages
    best = score()
    for _ in range(8):
        changed = False
        for n in reversed(list(gates)):
            previous = winner = choices[n]
            for option,_ in options[n]:
                choices[n] = option
                candidate = score()
                if candidate < best:
                    best, winner = candidate, option
            choices[n] = winner
            changed |= winner != previous
        if not changed: break

    # Emit positive/negative wires on demand, sharing each inversion.
    ops, mapping = [], {0:(0,0),1:(1,0)}
    inverted = {}
    normalized = {}
    driven = {n for op in c.ops for n in (op[2].values() if isinstance(op[2],dict) else op[2])}
    tristate = {n for op in c.ops if op[0] in ('RESOLVE','74HC244','74HC245') for n in op[2]}
    source = {p.ref:p for p in c.packages}
    def wire(net, polarity, ref):
        n,p = root(net)
        p ^= polarity
        actual, phase = mapping.get(n,(n,0))
        if p == phase:
            # Removing two NOTs must not turn a normalized X back into Z.
            if polarity == 0 and net in aliases and (n not in driven or n in tristate) and actual not in (0,1):
                if actual not in normalized:
                    buf = c.wire('polarity_normalized_'+str(actual))
                    normalized[actual] = buf
                    ops.append(('74HC08',(actual,actual),(buf,),ref))
                return normalized[actual]
            return actual
        if actual in (0,1): return 1-actual
        if actual not in inverted:
            inv = c.wire('polarity_inv_'+str(actual))
            inverted[actual] = inv
            ops.append(('74HC04',(actual,),(inv,),ref))
        return inverted[actual]
    for kind,ins,out,ref in c.ops:
        if kind == '74HC04': continue
        if isinstance(out,tuple) and out[0] in gates:
            ip,op = choices[out[0]]
            part = dict(options[out[0]])[choices[out[0]]]
            args = tuple(wire(n,ip,ref) for n in ins)
            actual = c.wire('polarity_'+str(out[0])) if op else out[0]
            ops.append((part,args,(actual,),ref))
            mapping[out[0]] = actual,op
        else:
            args = {k:wire(v,0,ref) for k,v in ins.items()} if isinstance(ins,dict) else tuple(wire(n,0,ref) for n in ins)
            ops.append((kind,args,out,ref))
    # Use a real package's group for new inversions at register/probe sinks.
    ref = next(iter(source))
    c.probes = {k:[wire(n,0,ref) for n in bits] for k,bits in c.probes.items()}
    c.registers = [(p,q,[wire(n,0,ref) for n in ds]) for p,q,ds in c.registers]
    c.ops = ops
    c = optimize(c, multi_input=False)
    c.polarity_search = {'method':'bounded coordinate descent', 'gate_packages':best[1]}
    return c
