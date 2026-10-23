"""Conservative, four-state-preserving mapping of the existing 74HC network.

No ISA/state/schedule rewrite. Keep the twelve ALU packages intact. Other gates
may share packages across logical groups; all 574s share clock and /OE already.
This is a reproducible candidate, not minimum-area synthesis or timing closure.
"""
from __future__ import annotations

from collections import Counter
from copy import deepcopy

from simulators.cyclesim.ttl.netlist import Package

CAPACITY = {"74HC04": 6, "74HC08": 4, "74HC32": 4, "74HC157": 4,
            "74HC11": 3, "74HC21": 2, "74HC4075": 3,
            "74HC00": 4, "74HC02": 4, "74HC10": 3, "74HC20": 2, "74HC27": 3}


def inputs(op):
    return list(op[1].values()) if op[0] == "ALU" else list(op[1])


def outputs(op):
    return list(op[2].values()) if op[0] == "ALU" else list(op[2])


def optimize(original, *, multi_input=True, multi_or=False):
    c = deepcopy(original)
    source = {p.ref: p for p in c.packages}
    aliases = {}
    cache = {}
    ops = []

    def mapped(n):
        while n in aliases: n = aliases[n]
        return n

    def emit(kind, ins, out, ref):
        ins = tuple(mapped(n) for n in ins)
        if kind in ("74HC08", "74HC32"): ins = tuple(sorted(ins))
        key = (kind, ins)
        if kind in CAPACITY and key in cache:
            aliases[out[0]] = cache[key]
        else:
            ops.append((kind, ins, tuple(out), ref))
            if kind in CAPACITY: cache[key] = out[0]

    def invert(n, ref):
        key = ("74HC04", (mapped(n),))
        if key in cache: return cache[key]
        out = c.wire(f"opt_inv_{len(c.names)}")
        emit("74HC04", [n], [out], ref)
        return out

    for kind, ins, out, ref in c.ops:
        if kind == "ALU":
            ops.append((kind, {pin: mapped(n) for pin, n in ins.items()}, out, ref))
            continue
        ins = tuple(mapped(n) for n in ins)
        if kind == "74HC157":
            a, b, s = ins
            # Keep a real gate even for mux(s,0,1): it normalizes Z to X.
            # These identities are valid over all four logic values.
            if a == 0: kind, ins = "74HC08", (s, b)
            elif b == 0: kind, ins = "74HC08", (invert(s, ref), a)
            elif a == 1: kind, ins = "74HC32", (invert(s, ref), b)
            elif b == 1: kind, ins = "74HC32", (s, a)
        emit(kind, ins, out, ref)

    # Publish aliases in sinks as well as all later consumers.
    c.probes = {name: [mapped(n) for n in bits] for name, bits in c.probes.items()}
    registers = [(p, q, [mapped(n) for n in d]) for p, q, d in c.registers]
    sinks = [n for bits in c.probes.values() for n in bits]
    sinks += [n for _, _, d in registers for n in d]

    if multi_input or multi_or:
        # Collapse single-consumer AND trees only. No duplicate fanout logic.
        users = Counter(sinks + [n for op in ops for n in inputs(op)])
        producers = {n: op for op in ops for n in outputs(op)}
        rewritten = []
        for kind, ins, out, ref in ops:
            if (multi_input and kind == "74HC08") or (multi_or and kind == "74HC32"):
                original_kind = kind
                leaves = list(ins)
                limit = 4 if kind == "74HC08" else 3
                while len(leaves) < limit:
                    child = next((n for n in leaves if users[n] == 1 and n in producers
                                  and producers[n][0] == original_kind), None)
                    if child is None: break
                    leaves.remove(child)
                    leaves.extend(producers[child][1])
                if len(leaves) > 2:
                    kind = {3: "74HC11", 4: "74HC21"}[len(leaves)] if original_kind == "74HC08" else "74HC4075"
                    ins = tuple(leaves)
            rewritten.append((kind, ins, out, ref))
        ops = rewritten

    # Keep observed wires, all register D cones and the frozen ALU assembly.
    live = set(sinks)
    kept = []
    for op in reversed(ops):
        if op[0] == "ALU" or live.intersection(outputs(op)):
            live.update(inputs(op))
            kept.append(op)
    ops = list(reversed(kept))

    # Repack gate channels globally; 157s require the SAME select/strobe.
    packages, pools, packed_ops = [], {}, []

    def package(part, group, label=None):
        p = Package(label or f"O{len(packages):04d}", part, group, {"VCC": 1, "GND": 0})
        packages.append(p)
        return p

    for kind, ins, out, ref in ops:
        if kind in ("RESOLVE", "161_RCO"):
            packed_ops.append((kind, ins, out, ref))
            continue
        old = source[ref]
        if kind == "ALU":
            p = package(old.part, "alu", ref)
            p.pins.update(ins)
            p.pins.update(out)
        elif kind in CAPACITY:
            select = ins[2] if kind == "74HC157" else None
            key = kind, select
            p, count = pools.get(key, (None, CAPACITY[kind]))
            if count == CAPACITY[kind]: p, count = package(kind, old.group), 0
            if p.group != old.group: p.group = "shared"
            channel = count + 1
            data = ins[:2] if kind == "74HC157" else ins
            p.pins.update({f"{channel}{pin}": n for pin, n in zip("ABCD", data)})
            p.pins[f"{channel}Y"] = out[0]
            if kind == "74HC157": p.pins.update(S=select, G=0)
            pools[key] = p, channel
        elif kind == "74HC283":
            p = package(kind, old.group)
            p.pins.update({f"A{i}": ins[i] for i in range(4)})
            p.pins.update({f"B{i}": ins[4 + i] for i in range(4)})
            p.pins.update({f"S{i}": out[i] for i in range(4)})
            p.pins.update(CIN=ins[8], COUT=out[4])
        elif kind in ("74HC245", "74HC244"):
            p = package(kind, old.group)
            p.pins.update({f"A{i}": ins[i] for i in range(8)})
            p.pins.update({f"B{i}": out[i] for i in range(8)})
            if kind == "74HC245": p.pins.update(DIR=1, OE_N=ins[8])
            else: p.pins.update(OE1_N=ins[8], OE2_N=ins[8])
        elif kind == "74HC238":
            p = package(kind, old.group)
            p.pins.update({f"A{i}": ins[i] for i in range(3)})
            p.pins.update(E1_N=ins[3], E2_N=ins[4], E3=ins[5])
            p.pins.update({f"Y{i}": out[i] for i in range(8)})
        else: raise ValueError(f"cannot repack {kind}")
        packed_ops.append((kind, ins, out, p.ref))

    # Same CLK and /OE; independent enables remain in external feedback muxes.
    if any(p.pins["CLK"] != c.clock_net or p.pins["OE_N"] != 0 for p, _, _ in registers):
        raise ValueError("574 packing requires the common SYS clock and always-enabled Q outputs")
    bits = [(qbit, dbit, p.group) for p, q, d in registers for qbit, dbit in zip(q, d)]
    packed_regs = []
    for offset in range(0, len(bits), 8):
        chunk = bits[offset:offset + 8]
        groups = {group for _, _, group in chunk}
        p = package("74HC574", next(iter(groups)) if len(groups) == 1 else "shared")
        q, d = [x[0] for x in chunk], [x[1] for x in chunk]
        p.pins.update({f"Q{i}": n for i, n in enumerate(q)})
        p.pins.update({f"D{i}": n for i, n in enumerate(d)})
        p.pins.update(OE_N=0, CLK=c.clock_net)
        packed_regs.append((p, q, d))

    c.packages, c.ops, c.registers = packages, packed_ops, packed_regs
    c.optimization = dict(baseline_packages=len(original.packages),
                          optimized_packages=len(packages), multi_input=multi_input,
                          preserved_alu_packages=sum(p.group == "alu" for p in original.packages),
                          passes=["constant mux mapping", "cross-group common gates",
                                  "single-consumer AND tree mapping" if multi_input else "two-input gates retained",
                                  "dead gate removal", "shared gate and 574 package packing"])
    c.finalize()
    return c
