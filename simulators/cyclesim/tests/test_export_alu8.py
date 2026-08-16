"""Export alu8 12-DIP assembly netlist tests."""

from __future__ import annotations

import re
from pathlib import Path

from simulators.cyclesim.export.alu8_netlist import (
    build_alu8_func_netlist,
    build_alu8_func_units,
    export_alu8_func,
    port_net_names,
    write_alu8_func_netlist,
)
from simulators.cyclesim.export.alu8_viewer import (
    build_alu8_gate_graph,
    write_alu8_viewer_html,
)


def _part_counts(netlist: dict) -> dict[str, int]:
    counts: dict[str, int] = {}
    for inst in netlist["instances"]:
        part = inst["part"]
        counts[part] = counts.get(part, 0) + 1
    return counts


def test_instance_counts() -> None:
    counts = _part_counts(build_alu8_func_netlist())
    assert len(build_alu8_func_netlist()["instances"]) == 12
    assert counts["74HC153"] == 8
    assert counts["74HC283"] == 2
    assert counts["74HC157"] == 2


def test_port_nets_present() -> None:
    netlist = build_alu8_func_netlist()
    names = {n["name"] for n in netlist["nets"]}
    assert port_net_names() <= names


def test_topology_edges() -> None:
    nl = build_alu8_func_netlist()
    by_ref = {i["ref"]: i for i in nl["instances"]}
    assert by_ref["U_ALU_153_0"]["pins"]["2Y"] == "net_b_add0"
    assert by_ref["U_ALU_283_LO"]["pins"]["B0"] == "net_b_add0"
    assert by_ref["U_ALU_283_LO"]["pins"]["CIN"] == "net_cin"
    assert by_ref["U_ALU_283_LO"]["pins"]["COUT"] == "net_c_lo"
    assert by_ref["U_ALU_283_HI"]["pins"]["CIN"] == "net_c_lo"
    assert by_ref["U_ALU_157_YBP_0"]["pins"]["1A"] == "net_sum0"
    assert by_ref["U_ALU_157_YBP_0"]["pins"]["1B"] == "net_y_logic0"
    assert by_ref["U_ALU_157_YBP_0"]["pins"]["1Y"] == "net_y0"
    assert by_ref["U_ALU_157_YBP_0"]["pins"]["S"] == "net_y_mux_sel"
    assert "U_Y_MUX_SEL" not in by_ref
    assert "U_CMP_SUB" not in by_ref


def test_units_catalog() -> None:
    units = build_alu8_func_units()
    assert len(units["units"]) == 12
    kinds = {u["kind"] for u in units["units"]}
    assert kinds == {"hc153", "hc283", "hc157"}


def test_dump_and_export_files(tmp_path: Path) -> None:
    nl_path = tmp_path / "alu8_func.yaml"
    units_path = tmp_path / "alu8_func.units.yaml"
    sc_path = tmp_path / "alu8_func.schematic.yaml"
    vw_path = tmp_path / "alu8-schematic.html"
    export_alu8_func(nl_path, units_path, sc_path, vw_path)
    text = nl_path.read_text(encoding="utf-8")
    assert "74HC153" in text
    assert "1C0" in text
    assert "net_bctrl0" in text
    assert "block: alu8_func" in text
    assert "port_groups:" not in text
    assert units_path.read_text(encoding="utf-8").count("package_ref:") == 12
    assert "template: alu8_row_grid" in sc_path.read_text(encoding="utf-8")
    html = vw_path.read_text(encoding="utf-8")
    assert "ALU8 gate viewer" in html
    assert "12 DIP" in html
    assert "mux1_bit_0" in html


def test_gate_graph_12_dip() -> None:
    g = build_alu8_gate_graph()
    assert g["dip_count"] == 12
    assert len(g["packages"]) == 12
    kinds = {n["kind"] for n in g["nodes"]}
    assert {"mux4", "mux2", "add4", "port"} <= kinds
    assert g["gate_count"] == 8 + 8 + 2 + 8  # mux1 + mux2 + add4 + ymux
    mux1 = next(n for n in g["nodes"] if n["id"] == "mux1_bit_0")
    assert set(mux1["pins"]) == {"0", "1", "2", "3", "S0", "S1", "Y"}
    ymux = next(n for n in g["nodes"] if n["id"] == "ymux_bit_0")
    assert set(ymux["pins"]) == {"0", "1", "S", "Y"}
    assert any(e["dst_pin"] == "S0" for e in g["edges"])
    assert any(e["dst_pin"] == "S" and e["net"] == "net_y_mux_sel" for e in g["edges"])
    assert any(e["net"] == "net_b_add0" for e in g["edges"])


def test_write_viewer_html(tmp_path: Path) -> None:
    path = write_alu8_viewer_html(tmp_path / "v.html")
    assert path.is_file()
    assert "application/json" in path.read_text(encoding="utf-8")


def test_write_roundtrip_keys(tmp_path: Path) -> None:
    path = tmp_path / "out.yaml"
    write_alu8_func_netlist(path)
    raw = path.read_text(encoding="utf-8")
    assert re.search(r"^version: 1$", raw, re.M)
    assert "instances:" in raw
    assert "nets:" in raw
