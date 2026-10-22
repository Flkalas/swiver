"""JSON-safe observations of the physical ALU; no HTTP or presentation state."""

from __future__ import annotations
from copy import deepcopy
from simulators.cyclesim.blocks.alu8 import ALU_PRESETS, AluControls, PhysicalAlu
from simulators.cyclesim.export.alu8_netlist import build_alu8_func_netlist
from simulators.cyclesim.values import H, L, X, Z, VALUE_NAMES, from_bits

MODEL_VERSION = "alu12-v1"
BUS_PREFIXES = {
    "a": "net_a",
    "b": "net_b",
    "b_add": "net_b_add",
    "logic": "net_y_logic",
    "sum": "net_sum",
    "y": "net_y",
}
STAGES = ("b_add", "logic", "sum", "c_lo", "c_hi", "y")
CONTROL_LIMITS = {"cin": 1, "bctrl": 15, "lgc": 15, "y_mux_sel": 1}


def controls_dict(ctrl: AluControls) -> dict:
    return {"cin": ctrl.cin, "bctrl": ctrl.bctrl, "lgc": ctrl.lgc, "y_mux_sel": ctrl.y_mux_sel}


def cpu_policy(operation: str, mode: str = "preset") -> dict:
    if mode == "direct":
        return {"acc_write": None, "flags_write": []}
    return {
        "acc_write": operation not in ("NOP", "CMP"),
        "flags_write": []
        if operation == "NOP"
        else ["C", "Z"]
        if operation in ("ADD", "SUB", "CMP", "INC", "DEC")
        else ["Z"],
    }


def circuit_definition() -> dict:
    netlist = build_alu8_func_netlist()
    components = [
        {
            "id": inst["ref"],
            "part": inst["part"],
            "pins": dict(inst["pins"]),
            "source": "simulators/cyclesim/export/alu8_netlist.py",
        }
        for inst in netlist["instances"]
    ]
    endpoints = {net["name"]: [] for net in netlist["nets"]}
    for component in components:
        for pin, net in component["pins"].items():
            endpoints[net].append({"component": component["id"], "pin": pin})
    controls = {"net_cin", "net_153_s0", "net_153_s1", "net_y_mux_sel"} | {
        f"net_{prefix}{i}" for prefix in ("lgc", "bctrl") for i in range(4)
    }
    nets = [
        {
            "id": name,
            "kind": "power"
            if name.startswith("pwr_")
            else "control"
            if name in controls
            else "data",
            "endpoints": ends,
        }
        for name, ends in endpoints.items()
    ]
    return {
        "model_version": MODEL_VERSION,
        "title": "Swiver ALU · 물리 패키지 12개",
        "components": components,
        "nets": nets,
        "buses": [
            {"id": name, "label": name.upper(), "nets": [f"{prefix}{i}" for i in range(8)]}
            for name, prefix in BUS_PREFIXES.items()
        ],
        "presets": [
            {
                "id": name,
                "label": name,
                "controls": controls_dict(ctrl),
                "cpu_policy": cpu_policy(name),
            }
            for name, ctrl in ALU_PRESETS.items()
        ],
        "boundary": [
            {
                "id": "controls",
                "label": "제어 입력",
                "description": "프리셋·직접 제어와 s0 OR s1 회로는 12개 패키지 외부에 있습니다.",
            },
            {
                "id": "comparison",
                "label": "비교 관측",
                "description": "독립 기대값과 영·캐리 관측은 물리 ALU 칩 외부에서 계산합니다.",
            },
            {
                "id": "cpu",
                "label": "CPU 쓰기 정책",
                "description": "NOP는 CPU 상태를 유지하고 CMP는 ACC 쓰기를 억제합니다. 물리 Y와 캐리는 계속 관측합니다.",
            },
            {
                "id": "time",
                "label": "지연 없는 기능 모델",
                "description": "정착 반복은 CPU 클럭이나 ns가 아닙니다. 핀은 DIP 번호가 아닌 기능 이름입니다.",
            },
        ],
    }


def expected_stages(a: int, b: int, controls: dict, operation: str | None) -> dict[str, int]:
    """Independent arithmetic/table oracle, never used to drive circuit nets."""
    if operation is None:
        b_add = sum(
            ((controls["bctrl"] >> (((a >> i) & 1) + 2 * ((b >> i) & 1))) & 1) << i
            for i in range(8)
        )
        logic = sum(
            ((controls["lgc"] >> (((a >> i) & 1) + 2 * ((b >> i) & 1))) & 1) << i for i in range(8)
        )
        cin, select_logic = controls["cin"], controls["y_mux_sel"]
    else:
        b_add = (
            b
            if operation == "ADD"
            else 255 - b
            if operation in ("SUB", "CMP")
            else 255
            if operation == "DEC"
            else 0
        )
        logic = {
            "AND": a & b,
            "OR": a | b,
            "XOR": a ^ b,
            "NOT": 255 - a,
            "PASS_A": a,
            "PASS_B": b,
        }.get(operation, 0)
        cin = int(operation in ("SUB", "CMP", "INC"))
        select_logic = operation in ("AND", "OR", "XOR", "NOT", "PASS_A", "PASS_B")
    total = a + b_add + cin
    return {
        "b_add": b_add,
        "logic": logic,
        "sum": total & 255,
        "c_lo": int((a & 15) + (b_add & 15) + cin > 15),
        "c_hi": int(total > 255),
        "y": logic if select_logic else total & 255,
    }


def _integer(value, name: str, maximum: int) -> int:
    if type(value) is not int or not 0 <= value <= maximum:
        raise ValueError(f"{name} 값은 0~{maximum} 범위의 정수여야 합니다.")
    return value


class AluSession:
    def __init__(self) -> None:
        self.circuit = PhysicalAlu()
        self.ctx = self.circuit.ctx
        self.state_id = 0
        self.inputs = self._initial_inputs()
        self.changed_nets: list[str] = []
        self._apply()

    @staticmethod
    def _initial_inputs() -> dict:
        return {
            "a": 0,
            "b": 0,
            "mode": "preset",
            "operation": "ADD",
            "controls": controls_dict(ALU_PRESETS["ADD"]),
        }

    def _apply(self) -> None:
        if self.inputs["mode"] == "preset":
            ctrl = ALU_PRESETS[self.inputs["operation"]]
        else:
            c = self.inputs["controls"]
            ctrl = AluControls(c["cin"], c["bctrl"], c["lgc"], c["y_mux_sel"], 0)
        self.circuit.set_inputs(self.inputs["a"], self.inputs["b"], ctrl)
        self.circuit.settle()

    def update(self, payload: dict) -> dict:
        if not isinstance(payload, dict):
            raise ValueError("입력은 JSON 객체여야 합니다.")
        unknown = set(payload) - {"a", "b", "mode", "operation", "controls", "request_id"}
        if unknown:
            raise ValueError("알 수 없는 입력 항목: " + ", ".join(sorted(map(str, unknown))))
        if "request_id" in payload:
            _integer(payload["request_id"], "request_id", 2**63 - 1)
        candidate = deepcopy(self.inputs)
        for name in ("a", "b"):
            if name in payload:
                candidate[name] = _integer(payload[name], name, 255)
        mode = payload.get("mode", candidate["mode"])
        operation = payload.get("operation", candidate["operation"])
        if not isinstance(mode, str) or mode not in ("preset", "direct"):
            raise ValueError("mode는 preset 또는 direct여야 합니다.")
        if not isinstance(operation, str) or operation not in ALU_PRESETS:
            raise ValueError("알 수 없는 ALU 연산입니다.")
        supplied = payload.get("controls")
        if "controls" in payload:
            if not isinstance(supplied, dict) or set(supplied) != set(CONTROL_LIMITS):
                raise ValueError("controls에는 cin, bctrl, lgc, y_mux_sel이 모두 필요합니다.")
            for name, maximum in CONTROL_LIMITS.items():
                _integer(supplied[name], name, maximum)
        if mode == "direct" and candidate["mode"] != "direct" and supplied is None:
            raise ValueError("직접 제어 모드로 전환할 때 controls가 필요합니다.")
        candidate.update(mode=mode, operation=operation)
        candidate["controls"] = (
            controls_dict(ALU_PRESETS[operation])
            if mode == "preset"
            else deepcopy(supplied)
            if supplied is not None
            else candidate["controls"]
        )
        before = self.ctx.nets.copy()
        self.inputs = candidate
        self._apply()
        self.state_id += 1
        self.changed_nets = sorted(
            name for name, value in self.ctx.nets.items() if before.get(name, Z) != value
        )
        return self.snapshot()

    def reset(self) -> dict:
        before = self.ctx.nets.copy()
        self.circuit = PhysicalAlu()
        self.ctx = self.circuit.ctx
        self.inputs = self._initial_inputs()
        self._apply()
        self.state_id += 1
        self.changed_nets = sorted(
            name for name, value in self.ctx.nets.items() if before.get(name, Z) != value
        )
        return self.snapshot()

    def snapshot(self) -> dict:
        signals = {name: VALUE_NAMES[value] for name, value in self.ctx.nets.items()}
        buses = {}
        for name, prefix in BUS_PREFIXES.items():
            bits = [self.ctx.get(f"{prefix}{i}") for i in range(8)]
            buses[name] = {
                "bits": "".join(VALUE_NAMES[v] for v in reversed(bits)),
                "value": from_bits(bits),
            }
        expected = expected_stages(
            self.inputs["a"],
            self.inputs["b"],
            self.inputs["controls"],
            self.inputs["operation"] if self.inputs["mode"] == "preset" else None,
        )
        actual = {name: buses[name]["value"] for name in ("b_add", "logic", "sum", "y")}
        actual.update(
            {
                name: self.ctx.get("net_" + name) if self.ctx.get("net_" + name) in (L, H) else None
                for name in ("c_lo", "c_hi")
            }
        )
        mismatch = next(
            (
                name
                for name in STAGES
                if actual[name] is not None and actual[name] != expected[name]
            ),
            None,
        )
        match = (
            False
            if mismatch
            else None
            if not self.ctx.settled or any(v is None for v in actual.values())
            else True
        )
        path = self.ctx.get("net_y_mux_sel")
        active = {"net_y_mux_sel"} | {
            f"net_{prefix}{i}" for prefix in ("a", "b", "y") for i in range(8)
        }
        if path != L:
            active |= {f"net_y_logic{i}" for i in range(8)} | {f"net_lgc{i}" for i in range(4)}
        if path != H:
            active |= (
                {f"net_{prefix}{i}" for prefix in ("sum", "b_add") for i in range(8)}
                | {f"net_bctrl{i}" for i in range(4)}
                | {"net_cin", "net_c_lo", "net_c_hi"}
            )
        components = {}
        for chip in self.circuit.chips:
            pins = {pin: signals[net] for pin, net in chip.pins.items()}
            enabled = chip.part != "74HC283" or path != H
            detail = (
                f"선택 주소 A+2B · A={pins['A']}, B={pins['B']}"
                if chip.part == "74HC153"
                else f"CIN={pins['CIN']} COUT={pins['COUT']}"
                if chip.part == "74HC283"
                else f"S={pins['S']} G={pins['G']}"
            )
            components[chip.name] = {"pins": pins, "active": enabled, "detail": detail}
        diagnostics = []
        for value, code, message in (
            (X, "unknown", "값을 확정할 수 없는 신호입니다."),
            (Z, "floating", "구동되지 않은 신호입니다."),
        ):
            affected = sorted(name for name, v in self.ctx.nets.items() if v == value)
            if affected:
                diagnostics.append({"code": code, "message": message, "nets": affected})
        if self.ctx.contentions:
            diagnostics.append(
                {
                    "code": "contention",
                    "message": "동일 강도의 드라이버가 충돌합니다.",
                    "nets": list(self.ctx.contentions),
                }
            )
        if not self.ctx.settled:
            diagnostics.append(
                {
                    "code": "unsettled",
                    "message": "조합 회로 정착 반복 한도를 초과했습니다.",
                    "nets": [],
                }
            )
        if mismatch:
            diagnostics.append(
                {
                    "code": "mismatch",
                    "message": "첫 불일치 단계: " + mismatch,
                    "nets": ["net_" + mismatch]
                    if mismatch.startswith("c_")
                    else [f"{BUS_PREFIXES[mismatch]}{i}" for i in range(8)],
                }
            )
        zero = self.ctx.get("net_cmp_z")
        return {
            "model_version": MODEL_VERSION,
            "state_id": self.state_id,
            "inputs": deepcopy(self.inputs),
            "signals": signals,
            "buses": buses,
            "changed_nets": list(self.changed_nets),
            "active_nets": sorted(active),
            "components": components,
            "comparison": {
                "expected": expected,
                "actual": actual,
                "match": match,
                "first_mismatch": mismatch,
            },
            "cpu_policy": cpu_policy(self.inputs["operation"], self.inputs["mode"]),
            "comparison_flags": {
                "zero": bool(zero) if zero in (L, H) else None,
                "carry_ge": actual["c_hi"],
            },
            "diagnostics": diagnostics,
            "settled": self.ctx.settled,
            "iterations": self.ctx.iterations,
        }
