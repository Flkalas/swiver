"""Physical 12-package ALU, instantiated from the exported functional pins.

The 153 address is A + 2*B. Opcode controls populate its data inputs;
CPU write/flag policy and comparison observers are outside these packages.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Any
from simulators.cyclesim.blocks.adder import full_adder
from simulators.cyclesim.blocks.mux import mux2, mux4_bits
from simulators.cyclesim.engine import Block, SimContext
from simulators.cyclesim.values import (
    H,
    L,
    X,
    Z,
    from_bits,
    logic_and,
    logic_not,
    logic_or,
    to_bits,
)


@dataclass(frozen=True)
class AluControls:
    cin: int = 0
    bctrl: int | None = 0
    lgc: int | None = 0
    s0: int = 0
    s1: int = 0

    @property
    def y_mux_sel(self) -> int:
        return logic_or(self.s0, self.s1)


ALU_NOP = AluControls()
ALU_ADD = AluControls(bctrl=0xC)
ALU_SUB = AluControls(cin=1, bctrl=0x3)
ALU_CMP = ALU_SUB
ALU_PRESETS = {
    "NOP": ALU_NOP,
    "ADD": ALU_ADD,
    "SUB": ALU_SUB,
    "AND": AluControls(lgc=0x8, s0=1),
    "OR": AluControls(lgc=0xE, s1=1),
    "XOR": AluControls(lgc=0x6, s0=1, s1=1),
    "NOT": AluControls(lgc=0x5, s0=1, s1=1),
    "PASS_A": AluControls(lgc=0xA, s0=1),
    "PASS_B": AluControls(lgc=0xC, s0=1),
    "INC": AluControls(cin=1),
    "DEC": AluControls(bctrl=0xF),
    "CMP": ALU_CMP,
}


class ScalarLogic:
    """Gate operations used by the physical package truth tables."""

    low = L
    unknown = X
    inv = staticmethod(logic_not)
    and_ = staticmethod(logic_and)
    mux2 = staticmethod(mux2)
    mux4 = staticmethod(mux4_bits)
    full_adder = staticmethod(full_adder)


SCALAR_LOGIC = ScalarLogic()


def chip_outputs(part: str, pins: dict[str, Any], logic=SCALAR_LOGIC) -> dict[str, Any]:
    """Evaluate functional pins, using scalar or bit-parallel gate operations.

    A packed backend evaluates independent lanes of these same package equations;
    it cannot replace the exported wiring or dispatch on ALU operation names.
    HC153/HC157 strobes force LOW, not high impedance. Unpowered outputs are X.
    """
    out = {}
    if part == "74HC153":
        for ch in (1, 2):
            selected = logic.mux4(pins["A"], pins["B"], *(pins[f"{ch}C{i}"] for i in range(4)))
            out[f"{ch}Y"] = logic.and_(logic.inv(pins[f"{ch}G"]), selected)
    elif part == "74HC157":
        for ch in range(1, 5):
            selected = logic.mux2(pins["S"], pins[f"{ch}A"], pins[f"{ch}B"])
            out[f"{ch}Y"] = logic.and_(logic.inv(pins["G"]), selected)
    elif part == "74HC283":
        carry = pins["CIN"]
        for i in range(4):
            out[f"S{i}"], carry = logic.full_adder(pins[f"A{i}"], pins[f"B{i}"], carry)
        out["COUT"] = carry
    else:
        raise ValueError(f"unsupported ALU part: {part}")
    powered = logic.and_(pins["VCC"], logic.inv(pins["GND"]))
    return {pin: logic.mux2(powered, logic.unknown, value) for pin, value in out.items()}


class ChipBlock(Block):
    def __init__(self, instance: dict) -> None:
        super().__init__(instance["ref"])
        self.part = instance["part"]
        self.pins = dict(instance["pins"])

    def eval_comb(self, ctx: SimContext) -> bool:
        inputs = {pin: ctx.get(net) for pin, net in self.pins.items()}
        changed = False
        for pin, value in chip_outputs(self.part, inputs).items():
            changed |= ctx.drive(self.pins[pin], value, self.name)
        return changed


class ComparisonProbe(Block):
    """Observation glue; never counted as a physical ALU package."""

    def eval_comb(self, ctx: SimContext) -> bool:
        y = [ctx.get(f"net_y{i}") for i in range(8)]
        zero = L if H in y else H if all(v == L for v in y) else X
        changed = ctx.drive("net_cmp_z", zero, self.name)
        return ctx.drive("net_cmp_c_ge", ctx.get("net_c_hi"), self.name) | changed


class PhysicalAlu:
    """Reusable SimContext and twelve packages sourced from exported pins."""

    def __init__(self, netlist: dict | None = None) -> None:
        from simulators.cyclesim.export.alu8_netlist import build_alu8_func_netlist

        self.netlist = netlist if netlist is not None else build_alu8_func_netlist()
        self.ctx = SimContext({n["name"]: Z for n in self.netlist["nets"]})
        self.chips = [ChipBlock(instance) for instance in self.netlist["instances"]]
        for chip in self.chips:
            self.ctx.add_block(chip)
        self.ctx.add_block(ComparisonProbe("comparison_observer"))
        self.ctx.set("pwr_vcc", H)
        self.ctx.set("pwr_gnd", L)

    def set_inputs(self, a: int | None, b: int | None, ctrl: AluControls) -> None:
        for prefix, value, width in (
            ("a", a, 8),
            ("b", b, 8),
            ("bctrl", ctrl.bctrl, 4),
            ("lgc", ctrl.lgc, 4),
        ):
            for i, value_bit in enumerate([X] * width if value is None else to_bits(value, width)):
                self.ctx.set(f"net_{prefix}{i}", value_bit)
        for name, value in (
            ("cin", ctrl.cin),
            ("153_s0", ctrl.s0),
            ("153_s1", ctrl.s1),
            ("y_mux_sel", ctrl.y_mux_sel),
        ):
            self.ctx.set(f"net_{name}", value)

    def settle(self) -> bool:
        return self.ctx.comb_fixup()


@dataclass
class AluResult:
    y: int | None
    z: bool | None
    c_hi: int


def eval_alu8(a: int | None, b: int | None, ctrl: AluControls) -> AluResult:
    circuit = PhysicalAlu()
    circuit.set_inputs(a, b, ctrl)
    circuit.settle()
    zero = circuit.ctx.get("net_cmp_z")
    return AluResult(
        from_bits(circuit.ctx.get(f"net_y{i}") for i in range(8)),
        bool(zero) if zero in (L, H) else None,
        circuit.ctx.get("net_c_hi"),
    )


class Alu8:
    """Compatibility adapter; the SimContext block below preserves bit detail."""

    def __init__(self, name: str = "alu8") -> None:
        self.name = name

    def read_ctrl(self, ctx: SimContext) -> AluControls:
        return AluControls(
            ctx.get("net_cin"),
            from_bits(ctx.get(f"net_bctrl{i}") for i in range(4)),
            from_bits(ctx.get(f"net_lgc{i}") for i in range(4)),
            ctx.get("net_153_s0"),
            ctx.get("net_153_s1"),
        )

    def eval(self, ctx: SimContext, a: int | None, b: int | None) -> AluResult:
        return eval_alu8(a, b, self.read_ctrl(ctx))

    def drive_outputs(self, ctx: SimContext, res: AluResult) -> None:
        for i, value in enumerate([X] * 8 if res.y is None else to_bits(res.y)):
            ctx.drive(f"net_y{i}", value, self.name)
        ctx.drive("net_cmp_z", X if res.z is None else int(res.z), self.name)
        ctx.drive("net_c_hi", res.c_hi, self.name)
