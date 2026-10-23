"""Check mapped circuits rather than comparing only package totals."""
from itertools import product
import random

import pytest

from simulators.cyclesim.ttl.cpu import build_cpu
from simulators.cyclesim.ttl.netlist import Circuit
from simulators.cyclesim.ttl.optimize import optimize


@pytest.mark.parametrize("side,constant", list(product([0, 1], [0, 1])))
def test_constant_mux_mapping_preserves_all_four_states(side, constant):
    c = Circuit()
    s, data = c.bus("select", 1), c.bus("data", 1)
    a, b = ([constant], data) if side == 0 else (data, [constant])
    c.probes["out"] = c.mux(s[0], a, b)
    c.finalize()
    o = optimize(c)
    for sv, dv in product(range(4), repeat=2):
        for circuit in (c, o):
            circuit.values[s[0]], circuit.values[data[0]] = sv, dv
            circuit.settle()
        assert c.values[c.probes["out"][0]] == o.values[o.probes["out"][0]]


def test_optimized_network_preserves_unknowns_and_simultaneous_state():
    c, _ = build_cpu()
    o = optimize(c)
    rng = random.Random(7400)
    sources = {n for _, q, _ in c.registers for n in q}
    sources.update(n for name in ("DBUS", "WAIT", "MAP_MODE") for n in c.probes[name])
    for _ in range(100):
        # Include X/Z, illegal phase codes and invalid pointers deliberately.
        for n in sources:
            c.values[n] = o.values[n] = rng.randrange(4)
        c.settle()
        o.settle()
        for name in c.probes:
            assert [c.values[n] for n in c.probes[name]] == [o.values[n] for n in o.probes[name]], name
        c.clock()
        o.clock()
        for _, q, _ in c.registers:
            assert [c.values[n] for n in q] == [o.values[n] for n in q]


def test_repacking_respects_selects_clocks_and_alu_boundary():
    c, _ = build_cpu()
    o = optimize(c)
    assert len(o.packages) < len(c.packages)
    assert len(c.packages) == 185  # frozen baseline, still independently runnable
    assert sum(p.group == "alu" for p in o.packages) == 12
    assert sum(len(q) for _, q, _ in c.registers) == sum(len(q) for _, q, _ in o.registers)
    assert len({n for _, q, _ in o.registers for n in q}) == sum(len(q) for _, q, _ in o.registers)
    by_ref = {p.ref: p for p in o.packages}
    for kind, ins, _, ref in o.ops:
        if kind == "74HC157":
            assert ins[2] == by_ref[ref].pins["S"]
    for p, q, d in o.registers:
        assert len(q) == len(d) <= 8
        assert p.pins["CLK"] == o.clock_net and p.pins["OE_N"] == 0
    # Optimization does not modify the old exported package connections.
    fresh, _ = build_cpu()
    assert c.export() == fresh.export()
