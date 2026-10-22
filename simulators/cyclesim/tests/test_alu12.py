"""Actual exported-pin chip truth tables, exhaustive lanes, and JSON contract."""

from itertools import product
import json
import random
import pytest
from simulators.cyclesim.blocks.alu8 import (
    ALU_PRESETS,
    AluControls,
    PhysicalAlu,
    chip_outputs,
)
from simulators.cyclesim.blocks.alu8_block import Alu8Block
from simulators.cyclesim.blocks.adder import add4, full_adder
from simulators.cyclesim.blocks.mux import mux2, mux4, mux4_bits
from simulators.cyclesim.engine import SimContext
from simulators.cyclesim.export.alu8_netlist import build_alu8_func_netlist
from simulators.cyclesim.values import H, L, X, Z, from_bits
from simulators.cyclesim.viewer_model import AluSession, circuit_definition, expected_stages


def independent_math(a, b, op):
    b_add = b if op == "ADD" else (255 - b) if op in ("SUB", "CMP") else 255 if op == "DEC" else 0
    logic = {"AND": a & b, "OR": a | b, "XOR": a ^ b, "NOT": 255 - a, "PASS_A": a, "PASS_B": b}.get(
        op, 0
    )
    cin = int(op in ("SUB", "CMP", "INC"))
    total = a + b_add + cin
    y = {"NOP": a, "ADD": a + b, "SUB": a - b, "CMP": a - b, "INC": a + 1, "DEC": a - 1}.get(
        op, logic
    ) & 255
    return {
        "b_add": b_add,
        "logic": logic,
        "sum": total & 255,
        "c_lo": int((a & 15) + (b_add & 15) + cin > 15),
        "c_hi": int(total > 255),
        "y": y,
    }


def pack_values(values, width):
    """LSB-first lane packing, with no arithmetic circuit behavior."""
    buffers = [bytearray((len(values) + 7) // 8) for _ in range(width)]
    for lane, value in enumerate(values):
        byte, bit = divmod(lane, 8)
        for i in range(width):
            buffers[i][byte] |= ((value >> i) & 1) << bit
    return [int.from_bytes(buf, "little") for buf in buffers]


class PackedLogic:
    """Independent lanes of four-state gate truth tables (known-zero/one masks).

    A tuple is (known zero lanes, known one lanes). Neither bit means unknown;
    Z at a gate input is also unknown. chip_outputs is the production circuit.
    """

    def __init__(self, lanes):
        self.mask = (1 << lanes) - 1
        self.low = (self.mask, 0)
        self.unknown = (0, 0)

    def constant(self, value):
        return self.low if value == 0 else (0, self.mask) if value == 1 else self.unknown

    def inv(self, a):
        return a[1], a[0]

    def and_(self, a, b):
        return a[0] | b[0], a[1] & b[1]

    def or_(self, a, b):
        return a[0] & b[0], a[1] | b[1]

    def xor(self, a, b):
        return (a[0] & b[0]) | (a[1] & b[1]), (a[0] & b[1]) | (a[1] & b[0])

    def mux2(self, sel, a, b):
        return (
            (sel[0] & a[0]) | (sel[1] & b[0]) | (a[0] & b[0]),
            (sel[0] & a[1]) | (sel[1] & b[1]) | (a[1] & b[1]),
        )

    def mux4(self, s0, s1, c0, c1, c2, c3):
        return self.mux2(s1, self.mux2(s0, c0, c1), self.mux2(s0, c2, c3))

    def full_adder(self, a, b, c):
        return self.xor(self.xor(a, b), c), self.or_(
            self.or_(self.and_(a, b), self.and_(a, c)), self.and_(b, c)
        )


@pytest.fixture(scope="module")
def all_operand_lanes():
    # Lane number is a*256+b: every possible ordered byte pair, exactly once.
    ops = PackedLogic(65536)
    nets = {}
    for prefix, values in (
        ("a", [i // 256 for i in range(65536)]),
        ("b", [i % 256 for i in range(65536)]),
    ):
        for i, ones in enumerate(pack_values(values, 8)):
            nets[f"net_{prefix}{i}"] = (ops.mask ^ ones, ones)
    return ops, nets


@pytest.mark.timeout(20)
@pytest.mark.parametrize("operation", list(ALU_PRESETS))
def test_all_65536_pairs_per_preset_actual_chips(operation, all_operand_lanes):
    """Each lane evaluates the exported 8 HC153 + 2 HC283 + 2 HC157 circuit."""
    ops, base = all_operand_lanes
    nets = dict(base)
    ctrl = ALU_PRESETS[operation]
    nets.update(
        pwr_vcc=ops.constant(1),
        pwr_gnd=ops.constant(0),
        net_cin=ops.constant(ctrl.cin),
        net_y_mux_sel=ops.constant(ctrl.y_mux_sel),
    )
    for prefix, pattern in (("bctrl", ctrl.bctrl), ("lgc", ctrl.lgc)):
        for i in range(4):
            nets[f"net_{prefix}{i}"] = ops.constant((pattern >> i) & 1)
    for instance in build_alu8_func_netlist()["instances"]:
        pins = {pin: nets.get(net, ops.unknown) for pin, net in instance["pins"].items()}
        for pin, value in chip_outputs(instance["part"], pins, ops).items():
            nets[instance["pins"][pin]] = value
    expected = [independent_math(a, b, operation) for a in range(256) for b in range(256)]
    for stage, prefix in (
        ("b_add", "net_b_add"),
        ("logic", "net_y_logic"),
        ("sum", "net_sum"),
        ("y", "net_y"),
        ("c_lo", "net_c_lo"),
        ("c_hi", "net_c_hi"),
    ):
        width = 1 if stage.startswith("c_") else 8
        for i, ones in enumerate(pack_values([row[stage] for row in expected], width)):
            value = nets[prefix if width == 1 else f"{prefix}{i}"]
            assert value == (ops.mask ^ ones, ones), (operation, stage, i)
    # Differential checks exercise the ordinary four-state engine, including
    # fixed carry/borrow edges plus reproducible samples from the packed lanes.
    rng = random.Random(953)
    pairs = list(product((0, 1, 15, 16, 127, 128, 254, 255), repeat=2)) + [
        (rng.randrange(256), rng.randrange(256)) for _ in range(24)
    ]
    circuit = PhysicalAlu()
    for a, b in pairs:
        circuit.set_inputs(a, b, ctrl)
        assert circuit.settle()
        row = expected[a * 256 + b]
        for stage, prefix in (
            ("b_add", "net_b_add"),
            ("logic", "net_y_logic"),
            ("sum", "net_sum"),
            ("y", "net_y"),
        ):
            assert from_bits(circuit.ctx.get(f"{prefix}{i}") for i in range(8)) == row[stage]
        assert circuit.ctx.get("net_c_lo") == row["c_lo"]
        assert circuit.ctx.get("net_c_hi") == row["c_hi"]


def test_complete_mux_truth_tables_and_unknown_selection():
    for pattern in range(16):
        bits = [(pattern >> i) & 1 for i in range(4)]
        for address in range(4):
            assert mux4(address, *bits) == bits[address]
            assert mux4_bits(address & 1, address >> 1, *bits) == bits[address]
    for sel, a, b in product((L, H, X, Z), repeat=3):
        if sel in (L, H):
            selected = (a, b)[sel]
            expected = selected if selected in (L, H) else X
        else:
            expected = a if a == b and a in (L, H) else X
        assert mux2(sel, a, b) == expected
    assert mux4_bits(X, H, X, Z, H, H) == H
    assert mux4_bits(Z, L, L, L, X, Z) == L
    assert mux4(2, X, Z, H, X) == H
    assert mux4(3, X, Z, X, L) == L


def test_full_adder_truth_table_and_known_carry_through_unknown():
    for a, b, c in product((L, H), repeat=3):
        assert full_adder(a, b, c) == ((a + b + c) & 1, int(a + b + c > 1))
    for a, b, c in product((L, H, X, Z), repeat=3):
        assert full_adder(a, b, c)[1] == (
            H if (a, b, c).count(H) >= 2 else L if (a, b, c).count(L) >= 2 else X
        )
    for a, b, c in product(range(16), range(16), (0, 1)):
        assert add4(a, b, c) == ((a + b + c) & 15, (a + b + c) >> 4)
    assert add4(0, 0, X) == (None, L)


@pytest.mark.parametrize("part", ["74HC153", "74HC157", "74HC283"])
def test_package_power_enable_and_packed_scalar_unknown_differential(part):
    instance = next(i for i in build_alu8_func_netlist()["instances"] if i["part"] == part)
    rng = random.Random(111)
    ops = PackedLogic(1)
    for _ in range(150):
        pins = {pin: rng.choice((L, H, X, Z)) for pin in instance["pins"]}
        pins.update(VCC=H, GND=L)
        scalar = chip_outputs(part, pins)
        packed = chip_outputs(part, {p: ops.constant(v) for p, v in pins.items()}, ops)
        assert packed == {p: ops.constant(v) for p, v in scalar.items()}
    pins = {pin: X for pin in instance["pins"]}
    pins.update(VCC=H, GND=L)
    if part == "74HC153":
        pins.update({"1G": H, "2G": H})
        assert set(chip_outputs(part, pins).values()) == {L}
    elif part == "74HC157":
        pins["G"] = H
        assert set(chip_outputs(part, pins).values()) == {L}
    for vcc, gnd in ((L, L), (X, L), (Z, L), (H, H), (H, Z)):
        pins.update(VCC=vcc, GND=gnd)
        assert set(chip_outputs(part, pins).values()) == {X}


def test_all_direct_truth_patterns_and_independent_session_oracle():
    session = AluSession()
    for pattern in range(16):
        for a, b in ((0, 0), (255, 0), (0, 255), (255, 255), (0x96, 0x3C)):
            for selected in (0, 1):
                snapshot = session.update(
                    {
                        "a": a,
                        "b": b,
                        "mode": "direct",
                        "controls": {
                            "cin": 1,
                            "bctrl": pattern,
                            "lgc": pattern,
                            "y_mux_sel": selected,
                        },
                    }
                )
                table = sum(
                    ((pattern >> (((a >> i) & 1) + 2 * ((b >> i) & 1))) & 1) << i for i in range(8)
                )
                assert snapshot["buses"]["b_add"]["value"] == table
                assert snapshot["buses"]["logic"]["value"] == table
                assert snapshot["buses"]["y"]["value"] == (
                    table if selected else (a + table + 1) & 255
                )
                assert snapshot["comparison"]["match"] is True
                assert snapshot["cpu_policy"] == {"acc_write": None, "flags_write": []}
    # Logic result selection must not erase physical adder carry.
    snapshot = session.update(
        {
            "a": 255,
            "b": 3,
            "mode": "direct",
            "controls": {"cin": 1, "bctrl": 15, "lgc": 10, "y_mux_sel": 1},
        }
    )
    assert snapshot["buses"]["y"]["value"] == 255 and snapshot["signals"]["net_c_hi"] == "1"


def test_export_definition_and_connectivity_are_the_executed_circuit():
    definition = circuit_definition()
    assert definition["model_version"] == "alu12-v1" and len(definition["components"]) == 12
    netlist = build_alu8_func_netlist()
    for c, i in zip(definition["components"], netlist["instances"]):
        assert c["id"] == i["ref"] and c["pins"] == i["pins"]
        assert c["pins"]["VCC"] == "pwr_vcc" and c["pins"]["GND"] == "pwr_gnd"
        for enable in {"74HC153": ("1G", "2G"), "74HC157": ("G",), "74HC283": ()}[c["part"]]:
            assert c["pins"][enable] == "pwr_gnd"
    # Changing an exported input wire must change the simulation result.
    netlist["instances"][0]["pins"]["1C0"] = "pwr_vcc"
    circuit = PhysicalAlu(netlist)
    circuit.set_inputs(0, 0, ALU_PRESETS["AND"])
    circuit.settle()
    assert circuit.ctx.get("net_y0") == H


def test_unknown_inputs_partial_bits_bus_release_and_contention():
    circuit = PhysicalAlu()
    circuit.set_inputs(0, 0, ALU_PRESETS["ADD"])
    circuit.ctx.set("net_a0", X)
    circuit.settle()
    assert circuit.ctx.get("net_y0") == X
    assert circuit.ctx.get("net_y1") == L  # a controlling zero resolves carry
    circuit.ctx.set("net_a0", Z)
    circuit.settle()
    assert circuit.ctx.get("net_y0") == X
    circuit.ctx.set("net_a0", L)
    circuit.ctx.set("net_bctrl0", X)
    circuit.settle()
    assert from_bits(circuit.ctx.get(f"net_y{i}") for i in range(8)) is None
    ctx = SimContext(blocks=[Alu8Block()])
    inputs = PhysicalAlu()
    inputs.set_inputs(0x12, 0x34, ALU_PRESETS["ADD"])
    for net, value in inputs.ctx.nets.items():
        ctx.set(net, value)
    ctx.set("net_y_oe", H)
    ctx.set("net_y_src_a", L)
    assert ctx.comb_fixup()
    assert from_bits(ctx.get(f"net_d{i}") for i in range(8)) == 0x46
    ctx.set("net_y_oe", L)
    ctx.comb_fixup()
    assert all(ctx.get(f"net_d{i}") == Z for i in range(8))
    ctx.set("net_y_oe", X)
    ctx.comb_fixup()
    assert all(ctx.get(f"net_d{i}") == X for i in range(8))
    ctx.set("net_y_src_a", H)
    ctx.comb_fixup()
    assert all(ctx.get(f"net_d{i}") == Z for i in range(8))


def test_snapshot_validation_atomicity_state_and_policies():
    session = AluSession()
    initial = session.snapshot()
    assert (
        initial["inputs"]["operation"] == "ADD"
        and initial["settled"]
        and not initial["diagnostics"]
    )
    invalid = [{"a": v} for v in (-1, 256, True, None, "2", 1.5)] + [
        {"mode": []},
        {"operation": {}},
        {"operation": "BAD"},
        {"controls": None},
        {"controls": {"cin": 0}},
        {"mode": "direct"},
        {"unrecognized": 1},
    ]
    invalid += [
        {"mode": "direct", "controls": {"cin": 0, "bctrl": False, "lgc": 0, "y_mux_sel": 0}}
    ]
    for payload in invalid:
        with pytest.raises(ValueError):
            session.update(payload)
        assert session.snapshot() == initial
    snapshot = session.update({"a": 23, "b": 80, "operation": "NOP"})
    assert snapshot["buses"]["y"]["value"] == 23 and snapshot["cpu_policy"] == {
        "acc_write": False,
        "flags_write": [],
    }
    snapshot = session.update({"operation": "CMP"})
    assert snapshot["buses"]["y"]["value"] == (23 - 80) & 255
    assert snapshot["cpu_policy"] == {"acc_write": False, "flags_write": ["C", "Z"]}
    snapshot["inputs"]["controls"]["cin"] = 0
    assert session.snapshot()["inputs"]["controls"]["cin"] == 1
    stable = session.update({})
    assert stable["changed_nets"] == []
    reset = session.reset()
    assert reset["state_id"] > stable["state_id"] and reset["inputs"] == initial["inputs"]
    json.dumps(reset, allow_nan=False)


def test_snapshot_observes_unknown_contention_and_first_stage_mismatch():
    session = AluSession()
    session.update({"a": 2, "b": 1})
    session.ctx.set("net_a0", X)
    session.circuit.settle()
    snap = session.snapshot()
    assert snap["buses"]["y"]["value"] is None and "X" in snap["buses"]["y"]["bits"]
    assert snap["comparison"]["match"] is None
    assert any(d["code"] == "unknown" for d in snap["diagnostics"])
    session.reset()
    session.ctx.drive("net_y0", H, "fault")
    session.circuit.settle()
    snap = session.snapshot()
    assert snap["signals"]["net_y0"] == "X"
    assert any(d["code"] == "contention" for d in snap["diagnostics"])
    session.reset()
    session.ctx.set("net_b_add0", H, stuck=True)
    session.circuit.settle()
    snap = session.snapshot()
    assert snap["comparison"]["match"] is False and snap["comparison"]["first_mismatch"] == "b_add"


def test_preset_observer_does_not_trust_the_controls_under_test():
    bad_controls = {"cin": 0, "bctrl": 0, "lgc": 0, "y_mux_sel": 1}
    for operation in ALU_PRESETS:
        assert expected_stages(17, 63, bad_controls, operation) == independent_math(
            17, 63, operation
        )


def test_every_direct_control_combination():
    circuit = PhysicalAlu()
    a, b = 0x96, 0x3C  # Includes all four operand selector addresses.
    for cin, bctrl, lgc, selected in product((0, 1), range(16), range(16), (0, 1)):
        circuit.set_inputs(a, b, AluControls(cin, bctrl, lgc, selected, 0))
        assert circuit.settle()
        b_add = sum(((bctrl >> (((a >> i) & 1) + 2 * ((b >> i) & 1))) & 1) << i for i in range(8))
        logic = sum(((lgc >> (((a >> i) & 1) + 2 * ((b >> i) & 1))) & 1) << i for i in range(8))
        assert from_bits(circuit.ctx.get(f"net_y{i}") for i in range(8)) == (
            logic if selected else (a + b_add + cin) & 255
        )
        assert circuit.ctx.get("net_c_hi") == int(a + b_add + cin > 255)
