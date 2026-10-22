"""Physical ALU plus explicit CPU bus-enable glue (outside the 12 chips)."""

from __future__ import annotations
from simulators.cyclesim.blocks.alu8 import Alu8, ChipBlock, ComparisonProbe
from simulators.cyclesim.engine import Block, SimContext
from simulators.cyclesim.export.alu8_netlist import build_alu8_func_netlist
from simulators.cyclesim.values import H, L, X, Z, logic_and, logic_not, logic_or


class Alu8Block(Block):
    def __init__(self, name: str = "alu8_blk") -> None:
        super().__init__(name)
        self.alu = Alu8(name)
        self.chips = [ChipBlock(i) for i in build_alu8_func_netlist()["instances"]]
        self.observer = ComparisonProbe(name + ".observer")

    def eval_comb(self, ctx: SimContext) -> bool:
        changed = ctx.drive("pwr_vcc", H, self.name + ".ties")
        changed |= ctx.drive("pwr_gnd", L, self.name + ".ties")
        changed |= ctx.drive(
            "net_y_mux_sel",
            logic_or(ctx.get("net_153_s0"), ctx.get("net_153_s1")),
            self.name + ".control",
        )
        for chip in self.chips:
            changed |= chip.eval_comb(ctx)
        changed |= self.observer.eval_comb(ctx)
        enable = logic_and(ctx.get("net_y_oe"), logic_not(ctx.get("net_y_src_a")))
        for i in range(8):
            value = Z if enable == L else ctx.get(f"net_y{i}") if enable == H else X
            changed |= ctx.drive(f"net_d{i}", value, self.name + ".bus")
        return changed
