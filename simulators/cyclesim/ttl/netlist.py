"""Functional-pin 74HC netlist builder and four-state synchronous evaluator.

Combinational operations are topologically ordered. State lives exclusively in
574 packages; enables are external 157 feedback muxes (574 has no enable/reset).
No timing, drive-strength, power-up or physical pin-number claim is made.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from simulators.cyclesim.blocks.alu8 import chip_outputs
from simulators.cyclesim.blocks.mux import mux2
from simulators.cyclesim.values import X, Z, from_bits, logic_and, logic_not, logic_or, resolve


@dataclass
class Package:
    ref: str
    part: str
    group: str
    pins: dict[str, int] = field(default_factory=dict)


class Circuit:
    def __init__(self):
        self.names = ["GND", "VCC"]
        self.values = [0, 1]
        self.packages: list[Package] = []
        self.ops = []
        self.registers = []
        self.group = "control"
        self._pools = {}
        self._cache = {}
        self.forced: dict[int, int] = {}
        self.probes: dict[str, list[int]] = {}
        self.clock_net = self.wire("CLK_SYS")
        self.values[self.clock_net] = 0

    def wire(self, name):
        if name in self.names:
            raise ValueError(f"duplicate wire {name}")
        self.names.append(name)
        self.values.append(X)
        return len(self.names) - 1

    def bus(self, name, width):
        bits = [self.wire(f"{name}[{i}]") for i in range(width)]
        self.probes[name] = bits
        return bits

    def constant(self, value, width):
        return [(value >> i) & 1 for i in range(width)]

    def package(self, part, label=None):
        p = Package(label or f"U{len(self.packages):04d}", part, self.group,
                    {"VCC": 1, "GND": 0})
        if any(existing.ref == p.ref for existing in self.packages):
            raise ValueError(f"duplicate package {p.ref}")
        self.packages.append(p)
        return p

    def _gate(self, kind, inputs, capacity, select=None):
        # Identical functions may share gates, but never across partition groups.
        key = (self.group, kind, tuple(inputs), select)
        if key in self._cache:
            return self._cache[key]
        pool = (self.group, kind, select)
        p, used = self._pools.get(pool, (None, capacity))
        if used == capacity:
            p, used = self.package(kind), 0
        ch = used + 1
        self._pools[pool] = (p, ch)
        output = self.wire(f"{p.ref}.{ch}Y")
        for pin, net in zip(("A", "B"), inputs):
            p.pins[f"{ch}{pin}"] = net
        p.pins[f"{ch}Y"] = output
        if select is not None:
            p.pins.update(S=select, G=0)
        self.ops.append((kind, tuple(inputs) + (() if select is None else (select,)), (output,), p.ref))
        self._cache[key] = output
        return output

    def inv(self, a):
        return 1 - a if a in (0, 1) else self._gate("74HC04", [a], 6)

    def and_(self, a, b):
        if 0 in (a, b): return 0
        if a == 1: return b
        if b == 1 or a == b: return a
        return self._gate("74HC08", sorted((a, b)), 4)

    def or_(self, a, b):
        if 1 in (a, b): return 1
        if a == 0: return b
        if b == 0 or a == b: return a
        return self._gate("74HC32", sorted((a, b)), 4)

    def reduce(self, fn, bits, identity):
        bits = list(bits)
        if not bits: return identity
        while len(bits) > 1:
            bits = [fn(bits[i], bits[i + 1]) if i + 1 < len(bits) else bits[i]
                    for i in range(0, len(bits), 2)]
        return bits[0]

    def all(self, *bits): return self.reduce(self.and_, bits, 1)
    def any(self, *bits): return self.reduce(self.or_, bits, 0)

    def eq(self, bits, value):
        return self.all(*(b if (value >> i) & 1 else self.inv(b) for i, b in enumerate(bits)))

    def lt(self, bits, value):
        result = 0
        for i, bit in enumerate(bits):
            result = (self.or_(self.inv(bit), result) if (value >> i) & 1
                      else self.and_(self.inv(bit), result))
        return result

    def mux(self, select, a, b):
        if len(a) != len(b): raise ValueError("mux widths")
        return [ai if ai == bi else self._gate("74HC157", [ai, bi], 4, select)
                for ai, bi in zip(a, b)]

    def add(self, a, b, carry=0):
        if len(a) != len(b) or len(a) % 4: raise ValueError("adder widths")
        outputs = []
        for offset in range(0, len(a), 4):
            p = self.package("74HC283")
            ins = list(a[offset:offset + 4]) + list(b[offset:offset + 4]) + [carry]
            out = [self.wire(f"{p.ref}.S{i}") for i in range(4)]
            carry = self.wire(f"{p.ref}.COUT")
            p.pins.update({f"A{i}": ins[i] for i in range(4)})
            p.pins.update({f"B{i}": ins[4 + i] for i in range(4)})
            p.pins.update({f"S{i}": out[i] for i in range(4)})
            p.pins.update(CIN=ins[8], COUT=carry)
            self.ops.append(("74HC283", tuple(ins), tuple(out + [carry]), p.ref))
            outputs.extend(out)
        return outputs, carry

    def driver(self, data, enable):
        if len(data) != 8: raise ValueError("245 width")
        p = self.package("74HC245")
        oe = self.inv(enable)
        out = [self.wire(f"{p.ref}.B{i}") for i in range(8)]
        p.pins.update(DIR=1, OE_N=oe)
        p.pins.update({f"A{i}": n for i, n in enumerate(data)})
        p.pins.update({f"B{i}": n for i, n in enumerate(out)})
        self.ops.append(("74HC245", tuple(data) + (oe,), tuple(out), p.ref))
        return out

    def reg(self, name, width):
        bits = self.bus(name, width)
        for offset in range(0, width, 8):
            p = self.package("74HC574")
            q = bits[offset:offset + 8]
            p.pins.update({f"Q{i}": bit for i, bit in enumerate(q)})
            p.pins.update(OE_N=0, CLK=self.clock_net)
            self.registers.append((p, q, None))
        return bits

    def bind(self, q, d, enable):
        if len(q) != len(d): raise ValueError("register widths")
        data = self.mux(enable, q, d)
        for index, (p, qb, old) in enumerate(self.registers):
            if qb[0] in q:
                if old is not None: raise ValueError("register already bound")
                offset = q.index(qb[0])
                db = data[offset:offset + len(qb)]
                p.pins.update({f"D{i}": bit for i, bit in enumerate(db)})
                self.registers[index] = (p, qb, db)

    def import_alu(self, a, b, cmp):
        wiring = {"pwr_gnd": 0, "pwr_vcc": 1, "net_cin": cmp,
                  "net_y_mux_sel": 0}
        wiring.update({f"net_a{i}": a[i] for i in range(8)})
        wiring.update({f"net_b{i}": b[i] for i in range(8)})
        previous_group = self.group
        self.group = "alu_glue"
        ncmp = self.inv(cmp)
        self.group = previous_group
        wiring.update({f"net_bctrl{i}": cmp if i < 2 else ncmp for i in range(4)})
        wiring.update({f"net_lgc{i}": 0 for i in range(4)})
        return self._import_alu_wiring(wiring)

    def import_arithmetic_alu(self, a, b, cin, bctrl_low, bctrl_high):
        """Same twelve packages; independent CU controls for ADD/SUB/INC/DEC.

        bctrl_low drives C0/C1 and bctrl_high C2/C3. No added decoder or
        inverter is hidden here: the caller supplies all three control nets.
        """
        if len(a) != 8 or len(b) != 8:
            raise ValueError("ALU operand widths must be eight")
        wiring = {"pwr_gnd": 0, "pwr_vcc": 1, "net_cin": cin,
                  "net_y_mux_sel": 0}
        wiring.update({f"net_a{i}": a[i] for i in range(8)})
        wiring.update({f"net_b{i}": b[i] for i in range(8)})
        wiring.update({f"net_bctrl{i}": bctrl_low if i < 2 else bctrl_high for i in range(4)})
        wiring.update({f"net_lgc{i}": 0 for i in range(4)})
        return self._import_alu_wiring(wiring)

    def _import_alu_wiring(self, wiring):
        from simulators.cyclesim.export.alu8_netlist import build_alu8_func_netlist
        for inst in build_alu8_func_netlist()["instances"]:
            p = self.package(inst["part"], inst["ref"])
            output_names = (["1Y", "2Y"] if p.part == "74HC153" else
                            [f"S{i}" for i in range(4)] + ["COUT"] if p.part == "74HC283" else
                            [f"{i}Y" for i in range(1, 5)])
            for pin, name in inst["pins"].items():
                if name not in wiring:
                    if pin not in output_names: raise ValueError(f"undriven ALU {name}")
                    wiring[name] = self.wire(name)
                p.pins[pin] = wiring[name]
            ins = {pin: net for pin, net in p.pins.items() if pin not in output_names}
            outs = {pin: p.pins[pin] for pin in output_names}
            self.ops.append(("ALU", ins, outs, p.ref))
        return [wiring[f"net_y{i}"] for i in range(8)], wiring["net_c_hi"]

    def set(self, bits, value):
        for i, bit in enumerate(bits): self.values[bit] = (value >> i) & 1

    def read(self, bits):
        value = from_bits(self.values[b] for b in bits)
        if value is None: raise ValueError(f"unknown bus {[self.names[b] for b in bits]}")
        return value

    def settle(self):
        v = self.values
        for net, value in self.forced.items(): v[net] = value
        for kind, ins, outs, ref in self.ops:
            if kind == "ALU":
                p = self._by_ref[ref]
                result = chip_outputs(p.part, {name: v[net] for name, net in ins.items()})
                pairs = [(net, result[name]) for name, net in outs.items()]
            else:
                x = [v[i] for i in ins]
                if kind == "74HC04": result = [logic_not(x[0])]
                elif kind in ("74HC00", "74HC10", "74HC20"):
                    value = 1
                    for bit in x: value = logic_and(value, bit)
                    result = [logic_not(value)]
                elif kind in ("74HC02", "74HC27"):
                    value = 0
                    for bit in x: value = logic_or(value, bit)
                    result = [logic_not(value)]
                elif kind in ("74HC08", "74HC11", "74HC21"):
                    value = 1
                    for bit in x: value = logic_and(value, bit)
                    result = [value]
                elif kind == "74HC32": result = [logic_or(*x)]
                elif kind == "74HC4075": result = [logic_or(logic_or(x[0],x[1]),x[2])]
                elif kind == "74HC157": result = [mux2(x[2], x[0], x[1])]
                elif kind == "74HC245":
                    result = [Z if x[8] == 1 else bit if x[8] == 0 else X for bit in x[:8]]
                elif kind == "74HC244":
                    result = [Z if x[8] == 1 else bit if x[8] == 0 else X for bit in x[:8]]
                elif kind == "74HC238":
                    enabled = logic_and(logic_and(logic_not(x[3]), logic_not(x[4])), x[5])
                    address = from_bits(x[:3])
                    result = [0 if enabled == 0 else int(i == address)
                              if enabled == 1 and address is not None else X for i in range(8)]
                elif kind == "RESOLVE":
                    result = [resolve(x)]
                elif kind == "161_RCO":
                    value = 1
                    for bit in x: value = logic_and(value, bit)
                    result = [value]
                elif kind == "74HC283":
                    pins = {f"A{i}": x[i] for i in range(4)}
                    pins.update({f"B{i}": x[i + 4] for i in range(4)})
                    pins.update(CIN=x[8], VCC=1, GND=0)
                    r = chip_outputs(kind, pins)
                    result = [r[f"S{i}"] for i in range(4)] + [r["COUT"]]
                else: raise ValueError(kind)
                pairs = zip(outs, result)
            for net, value in pairs: v[net] = self.forced.get(net, value)

    def clock(self):
        # All D pins sampled before any Q output changes.
        self.values[self.clock_net] = 1
        sampled = [(q, [self.values[d] for d in db]) for _, q, db in self.registers]
        for q, values in sampled:
            for bit, value in zip(q, values): self.values[bit] = self.forced.get(bit, value)
        self.values[self.clock_net] = 0

    def finalize(self):
        if any(d is None for _, _, d in self.registers): raise ValueError("unbound register")
        self._by_ref = {p.ref: p for p in self.packages}
        # Construction order is topological, including imported ALU packages.
        produced = set()
        outputs = {n for kind, _, out, _ in self.ops for n in (out.values() if kind == "ALU" else out)}
        for kind, ins, out, _ in self.ops:
            inputs = ins.values() if kind == "ALU" else ins
            if any(n in outputs and n not in produced for n in inputs):
                raise ValueError("combinational cycle or non-topological connection")
            produced.update(out.values() if kind == "ALU" else out)

    def export(self):
        def pins(p):
            result = {pin: self.names[n] for pin, n in p.pins.items()}
            if p.part in ("74HC04", "74HC08", "74HC32", "74HC157", "74HC11", "74HC21", "74HC4075",
                          "74HC00", "74HC02", "74HC10", "74HC20", "74HC27"):
                channels = {"74HC04": 6, "74HC11": 3, "74HC21": 2, "74HC4075": 3,
                            "74HC10": 3, "74HC20": 2, "74HC27": 3}.get(p.part, 4)
                letters = {"74HC04": "A", "74HC11": "ABC", "74HC21": "ABCD", "74HC4075": "ABC",
                           "74HC10": "ABC", "74HC20": "ABCD", "74HC27": "ABC"}.get(p.part, "AB")
                for ch in range(1, channels + 1):
                    for letter in letters: result.setdefault(f"{ch}{letter}", "GND")
                    result.setdefault(f"{ch}Y", None)
            elif p.part == "74HC574":
                for ch in range(8):
                    result.setdefault(f"D{ch}", "GND")
                    result.setdefault(f"Q{ch}", None)
            return result
        return {"schema": "swiver-ttl-cpu-netlist-v1", "nets": self.names,
                "packages": [dict(ref=p.ref, part=p.part, group=p.group,
                                   pins=pins(p))
                             for p in self.packages],
                "probes": {k: [self.names[n] for n in v] for k, v in self.probes.items()},
                "boundary": "Functional pins; unused gate inputs tie LOW, unused outputs NC. All 574 CLK pins share SYS. Initial register values supplied by fixture, not a reset circuit."}

    def inventory(self):
        return {g: dict(sorted(Counter(p.part for p in self.packages if p.group == g).items()))
                for g in sorted({p.group for p in self.packages})}

    def depth_report(self):
        depth = [0] * len(self.names)
        path = [[] for _ in self.names]
        for kind, ins, outs, ref in self.ops:
            inputs = list(ins.values()) if kind == "ALU" else ins
            source = max(inputs, key=lambda n: depth[n])
            for n in (outs.values() if kind == "ALU" else outs):
                depth[n], path[n] = depth[source] + 1, path[source] + [ref]
        endpoints = [(f"{p.ref}.D{i}", n) for p, _, d in self.registers for i, n in enumerate(d)]
        return [dict(endpoint=ref, net=self.names[n], levels=depth[n],
                     packages=path[n]) for ref, n in sorted(endpoints, key=lambda x: depth[x[1]], reverse=True)[:8]]
