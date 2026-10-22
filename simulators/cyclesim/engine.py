"""Zero-delay, equal-strength four-state resolution and synchronous ticks."""

from __future__ import annotations
from abc import ABC
from dataclasses import dataclass, field
from simulators.cyclesim.values import H, L, X, Z, resolve, validate

FIXPOINT_LIMIT = 64


class Block(ABC):
    def __init__(self, name: str) -> None:
        self.name = name

    def eval_comb(self, ctx: SimContext) -> bool:
        return False

    def tick(self, ctx: SimContext) -> None:
        pass


@dataclass
class SimContext:
    nets: dict[str, int] = field(default_factory=dict)
    blocks: list[Block] = field(default_factory=list)
    clk: int = L
    violations: list[str] = field(default_factory=list)
    settled: bool = False
    iterations: int = 0
    contentions: list[str] = field(default_factory=list)
    _pending: dict[tuple[str, str], int] = field(default_factory=dict, repr=False)
    _drivers: dict[tuple[str, str], int] = field(default_factory=dict, repr=False)
    _comb_drivers: set[tuple[str, str]] = field(default_factory=set, repr=False)
    _seen_comb: set[tuple[str, str]] | None = field(default=None, repr=False)
    _driven_nets: set[str] = field(default_factory=set, repr=False)
    _stuck: set[str] = field(default_factory=set, repr=False)

    def add_block(self, block: Block) -> None:
        self.blocks.append(block)

    def get(self, net: str, default: int = X) -> int:
        return self.nets.get(net, default)

    def set(self, net: str, value: int, *, stuck: bool = False) -> None:
        """Set an input/initial condition; stuck=True forces a fault/tie."""
        self.nets[net] = validate(value)
        if stuck:
            self._stuck.add(net)

    def drive(self, net: str, value: int, driver: str) -> bool:
        validate(value)
        key = (net, driver)
        if self._seen_comb is not None:
            self._seen_comb.add(key)
        previous = self._pending.get(key, self._drivers.get(key, Z))
        self._pending[key] = value
        return net not in self._stuck and previous != value

    def _flush_pending(self) -> bool:
        self._drivers.update(self._pending)
        self._driven_nets.update(net for net, _ in self._pending)
        self._pending.clear()
        by_net: dict[str, list[int]] = {n: [] for n in self._driven_nets}
        for (net, _), value in self._drivers.items():
            by_net[net].append(value)
        changed = False
        self.contentions = []
        for net, values in by_net.items():
            if net in self._stuck:
                continue
            if L in values and H in values:
                self.contentions.append(net)
            value = resolve(values)
            changed |= self.get(net) != value
            self.nets[net] = value
        self.contentions.sort()
        return changed

    def reset_floats(self) -> None:
        for name in self.nets:
            if name not in self._stuck:
                self.nets[name] = X
        self._pending.clear()
        self._drivers.clear()
        self._comb_drivers.clear()
        self._driven_nets.clear()
        self.contentions.clear()
        self.settled = False

    def clear_stuck(self) -> None:
        self._stuck.clear()

    def flush_pending(self) -> bool:
        return self._flush_pending()

    def comb_fixup(self) -> bool:
        # Commit external/tick drives before the first evaluation.
        self._flush_pending()
        self.settled = False
        for iteration in range(1, FIXPOINT_LIMIT + 1):
            before = self.nets.copy()
            self._seen_comb = set()
            try:
                for block in self.blocks:
                    block.eval_comb(self)
                for key in self._comb_drivers - self._seen_comb:
                    self._drivers.pop(key, None)
                self._comb_drivers = self._seen_comb
            finally:
                self._seen_comb = None
            self._flush_pending()
            self.iterations = iteration
            # Resolved nets, not return-value hints, determine convergence.
            if self.nets == before:
                self.settled = True
                return True
        message = "comb fixpoint limit exceeded"
        if message not in self.violations:
            self.violations.append(message)
        return False

    def pulse_clock(self) -> None:
        self.clk = L
        self.comb_fixup()
        self.clk = H
        for block in self.blocks:
            block.tick(self)
        self._flush_pending()
        self.comb_fixup()
        self.clk = L
        self.comb_fixup()
