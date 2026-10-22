"""Four-state resolution, propagation, release and simultaneous clock edges."""

from itertools import permutations
import pytest
from simulators.cyclesim.engine import Block, FIXPOINT_LIMIT, SimContext
from simulators.cyclesim.values import H, L, X, Z, from_bits, logic_not, resolve


@pytest.mark.parametrize(
    "drivers,expected",
    [
        ([], Z),
        ([Z, Z], Z),
        ([L, Z], L),
        ([H, Z], H),
        ([H, L], X),
        ([X, Z], X),
        ([H, X], X),
        ([H, H], H),
    ],
)
def test_resolve_order_independent(drivers, expected):
    for sequence in permutations(drivers):
        assert resolve(sequence) == expected
        ctx = SimContext()
        for i, value in enumerate(sequence):
            ctx.drive("bus", value, str(i))
        ctx.flush_pending()
        assert ctx.get("bus", Z) == expected


def test_driver_identity_release_and_force():
    ctx = SimContext()
    assert ctx.drive("bus", H, "one")
    assert not ctx.drive("bus", H, "one")
    ctx.drive("bus", L, "one")
    ctx.flush_pending()
    assert ctx.get("bus") == L  # a driver replacing itself is not contention
    ctx.drive("bus", H, "two")
    ctx.flush_pending()
    assert ctx.get("bus") == X and ctx.contentions == ["bus"]
    ctx.drive("bus", Z, "one")
    ctx.flush_pending()
    assert ctx.get("bus") == H and not ctx.contentions
    ctx.set("bus", L, stuck=True)
    ctx.flush_pending()
    assert ctx.get("bus") == L
    ctx.clear_stuck()
    ctx.flush_pending()
    assert ctx.get("bus") == H
    ctx.drive("bus", Z, "two")
    ctx.flush_pending()
    assert ctx.get("bus") == Z


class Wire(Block):
    def __init__(self, name, source, dest):
        super().__init__(name)
        self.source, self.dest, self.enabled = source, dest, True

    def eval_comb(self, ctx):
        if self.enabled:
            ctx.drive(self.dest, ctx.get(self.source), self.name)
        return True  # intentionally unhelpful hints must not prevent settling


def test_chain_converges_in_both_orders_and_releases():
    for reverse in (False, True):
        ctx = SimContext()
        wires = [Wire("first", "input", "mid"), Wire("second", "mid", "output")]
        ctx.blocks = list(reversed(wires)) if reverse else wires
        ctx.set("input", H)
        assert ctx.comb_fixup() and ctx.get("output") == H
        assert ctx.iterations < FIXPOINT_LIMIT and not ctx.violations
        wires[0].enabled = False
        assert ctx.comb_fixup()
        assert ctx.get("mid") == ctx.get("output") == Z


def test_queued_drive_survives_comb_entry_and_stable_driver_returns_false():
    ctx = SimContext(blocks=[Wire("w", "q", "out")])
    ctx.drive("q", H, "external")
    assert ctx.comb_fixup() and ctx.get("out") == H
    assert not ctx.drive("q", H, "external")


class Register(Block):
    def __init__(self, name, d, q):
        super().__init__(name)
        self.d, self.q = d, q

    def tick(self, ctx):
        ctx.drive(self.q, ctx.get(self.d), self.name)


@pytest.mark.parametrize("reverse", [False, True])
def test_ticks_sample_before_simultaneous_commit(reverse):
    regs = [Register("r0", "d", "q0"), Register("r1", "q0", "q1")]
    ctx = SimContext(blocks=list(reversed(regs)) if reverse else regs)
    ctx.set("d", H)
    ctx.set("q0", L)
    ctx.pulse_clock()
    assert ctx.get("q0") == H and ctx.get("q1") == L and ctx.clk == L
    ctx.pulse_clock()
    assert ctx.get("q1") == H


def test_bounded_oscillator_and_recovery():
    class Oscillator(Block):
        def eval_comb(self, ctx):
            return ctx.drive("loop", logic_not(ctx.get("loop")), self.name)

    ctx = SimContext(blocks=[Oscillator("osc")])
    ctx.set("loop", L)
    assert not ctx.comb_fixup()
    assert ctx.iterations == FIXPOINT_LIMIT and ctx.violations == ["comb fixpoint limit exceeded"]
    ctx.set("loop", H, stuck=True)
    assert ctx.comb_fixup()


def test_unknown_bus_never_becomes_zero():
    assert from_bits([L, H]) == 2
    assert from_bits([H, H]) == 3
    for unknown in (X, Z):
        assert from_bits([L, unknown]) is None
    with pytest.raises(ValueError):
        SimContext().drive("bad", 4, "driver")
