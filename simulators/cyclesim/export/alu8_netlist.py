"""Generate alu8 12-DIP assembly YAML netlist (reference/alu8-phase-b.md)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

BLOCK_NAME = "alu8_func"
DESCRIPTION = "v1.0 ALU — 12 DIP assembly (153×8, 283×2, 157×2)"


def _153_instance(bit: int) -> dict[str, Any]:
    i = bit
    return {
        "ref": f"U_ALU_153_{i}",
        "part": "74HC153",
        "pins": {
            "A": f"net_a{i}",
            "B": f"net_b{i}",
            "1C0": "net_lgc0",
            "1C1": "net_lgc1",
            "1C2": "net_lgc2",
            "1C3": "net_lgc3",
            "2C0": "net_bctrl0",
            "2C1": "net_bctrl1",
            "2C2": "net_bctrl2",
            "2C3": "net_bctrl3",
            "1Y": f"net_y_logic{i}",
            "2Y": f"net_b_add{i}",
        },
    }


def _283_instance(ref: str, a_lo: int, b_lo: int, s_lo: int, cin: str, cout: str) -> dict[str, Any]:
    pins: dict[str, str] = {
        "CIN": cin,
        "COUT": cout,
    }
    for n in range(4):
        pins[f"A{n}"] = f"net_a{a_lo + n}"
        pins[f"B{n}"] = f"net_b_add{b_lo + n}"
        pins[f"S{n}"] = f"net_sum{s_lo + n}"
    return {"ref": ref, "part": "74HC283", "pins": pins}


def _157_ybp_instance(ref: str, y_lo: int) -> dict[str, Any]:
    pins: dict[str, str] = {"S": "net_y_mux_sel"}
    for n in range(4):
        i = y_lo + n
        ch = n + 1
        pins[f"{ch}A"] = f"net_sum{i}"
        pins[f"{ch}B"] = f"net_y_logic{i}"
        pins[f"{ch}Y"] = f"net_y{i}"
    return {"ref": ref, "part": "74HC157", "pins": pins}


def build_alu8_func_netlist() -> dict[str, Any]:
    instances: list[dict[str, Any]] = []
    for i in range(8):
        instances.append(_153_instance(i))
    instances.append(_283_instance("U_ALU_283_LO", 0, 0, 0, "net_cin", "net_c_lo"))
    instances.append(_283_instance("U_ALU_283_HI", 4, 4, 4, "net_c_lo", "net_c_hi"))
    instances.append(_157_ybp_instance("U_ALU_157_YBP_0", 0))
    instances.append(_157_ybp_instance("U_ALU_157_YBP_1", 4))

    nets: list[dict[str, Any]] = []
    for i in range(8):
        nets.append({"name": f"net_a{i}", "width": 1})
        nets.append({"name": f"net_b{i}", "width": 1})
    nets.append({"name": "net_cin", "width": 1})
    nets.append({"name": "net_153_s0", "width": 1})
    nets.append({"name": "net_153_s1", "width": 1})
    for i in range(4):
        nets.append({"name": f"net_bctrl{i}", "width": 1})
        nets.append({"name": f"net_lgc{i}", "width": 1})
    nets.append({"name": "net_y_mux_sel", "width": 1})
    nets.append({"name": "net_cmp_z", "width": 1, "probes": ["cmp_z"]})
    nets.append({"name": "net_cmp_c_ge", "width": 1, "probes": ["cmp_c_ge"]})
    for i in range(8):
        nets.append({"name": f"net_b_add{i}", "width": 1})
        nets.append({"name": f"net_sum{i}", "width": 1})
        nets.append({"name": f"net_y_logic{i}", "width": 1})
    for i in range(8):
        probes = ["y0"] if i == 0 else (["y7"] if i == 7 else None)
        entry: dict[str, Any] = {"name": f"net_y{i}", "width": 1}
        if probes:
            entry["probes"] = probes
        nets.append(entry)
    nets.append({"name": "net_c_lo", "width": 1})
    nets.append({"name": "net_c_hi", "width": 1, "probes": ["carry_hi"]})
    nets.append({"name": "pwr_vcc", "width": 1})
    nets.append({"name": "pwr_gnd", "width": 1})

    return {
        "version": 1,
        "block": BLOCK_NAME,
        "description": DESCRIPTION,
        "instances": instances,
        "nets": nets,
    }


def build_alu8_func_units() -> dict[str, Any]:
    units: list[dict[str, Any]] = []
    for i in range(8):
        units.append(
            {
                "id": f"153_bit_{i}",
                "kind": "hc153",
                "label": f"74HC153[{i}]",
                "stage": 2,
                "package_ref": f"U_ALU_153_{i}",
            }
        )
    units.append(
        {
            "id": "283_lo",
            "kind": "hc283",
            "label": "74HC283 LO (a0-3)",
            "stage": 1,
            "package_ref": "U_ALU_283_LO",
        }
    )
    units.append(
        {
            "id": "283_hi",
            "kind": "hc283",
            "label": "74HC283 HI (a4-7)",
            "stage": 1,
            "package_ref": "U_ALU_283_HI",
        }
    )
    units.append(
        {
            "id": "157_ybp_0",
            "kind": "hc157",
            "label": "74HC157 YBP y[0-3]",
            "stage": 4,
            "package_ref": "U_ALU_157_YBP_0",
        }
    )
    units.append(
        {
            "id": "157_ybp_1",
            "kind": "hc157",
            "label": "74HC157 YBP y[4-7]",
            "stage": 4,
            "package_ref": "U_ALU_157_YBP_1",
        }
    )
    return {"version": 1, "block": BLOCK_NAME, "units": units}


def _yaml_lines_mapping(mapping: dict[str, Any], indent: int) -> list[str]:
    sp = " " * indent
    lines: list[str] = []
    for key, val in mapping.items():
        if isinstance(val, dict):
            lines.append(f"{sp}{key}:")
            lines.extend(_yaml_lines_mapping(val, indent + 2))
        elif isinstance(val, list):
            lines.append(f"{sp}{key}:")
            for item in val:
                if isinstance(item, dict):
                    lines.append(f"{sp}  -")
                    lines.extend(_yaml_lines_mapping(item, indent + 4))
                else:
                    lines.append(f"{sp}  - {item}")
        else:
            lines.append(f"{sp}{key}: {val}")
    return lines


def dump_yaml(data: dict[str, Any]) -> str:
    """Minimal YAML emitter for netlist/units dicts (no external deps)."""
    lines: list[str] = []

    for key, val in data.items():
        if isinstance(val, dict):
            lines.append(f"{key}:")
            lines.extend(_yaml_lines_mapping(val, 2))
        elif isinstance(val, list):
            lines.append(f"{key}:")
            for item in val:
                if not isinstance(item, dict):
                    lines.append(f"  - {item}")
                    continue
                lines.append("  -")
                for ik, iv in item.items():
                    if isinstance(iv, dict):
                        lines.append(f"    {ik}:")
                        lines.extend(_yaml_lines_mapping(iv, 6))
                    elif isinstance(iv, list):
                        lines.append(f"    {ik}:")
                        for sub in iv:
                            lines.append(f"      - {sub}")
                    else:
                        lines.append(f"    {ik}: {iv}")
        else:
            lines.append(f"{key}: {val}")

    return "\n".join(lines) + "\n"


def write_alu8_func_netlist(path: Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dump_yaml(build_alu8_func_netlist()), encoding="utf-8")
    return path


def write_alu8_func_units(path: Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dump_yaml(build_alu8_func_units()), encoding="utf-8")
    return path


def export_alu8_func(
    netlist_path: Path,
    units_path: Path | None = None,
    schematic_path: Path | None = None,
    viewer_path: Path | None = None,
) -> tuple[Path, Path | None, Path | None, Path | None]:
    from simulators.cyclesim.export.alu8_schematic_doc import write_alu8_schematic_doc
    from simulators.cyclesim.export.alu8_viewer import write_alu8_viewer_html

    write_alu8_func_netlist(netlist_path)
    units_out = None
    if units_path is not None:
        units_out = write_alu8_func_units(units_path)
    schematic_out = None
    if schematic_path is not None:
        schematic_out = write_alu8_schematic_doc(schematic_path)
    viewer_out = None
    if viewer_path is not None:
        viewer_out = write_alu8_viewer_html(viewer_path)
    return netlist_path, units_out, schematic_out, viewer_out


def port_net_names() -> set[str]:
    """External port nets (CPLD drive + ALU boundary)."""
    names: set[str] = set()
    for i in range(8):
        names.add(f"net_a{i}")
        names.add(f"net_b{i}")
        names.add(f"net_y{i}")
    names.update(
        {
            "net_cin",
            "net_153_s0",
            "net_153_s1",
            "net_bctrl0",
            "net_bctrl1",
            "net_bctrl2",
            "net_bctrl3",
            "net_lgc0",
            "net_lgc1",
            "net_lgc2",
            "net_lgc3",
            "net_y_mux_sel",
            "net_cmp_z",
            "net_cmp_c_ge",
            "net_c_hi",
        }
    )
    return names
