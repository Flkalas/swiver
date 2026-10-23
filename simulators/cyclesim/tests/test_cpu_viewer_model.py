"""The CPU browser must preserve verified connectivity and never invent pads."""
from collections import Counter
import json

import pytest

from simulators.cyclesim import cpu_viewer_model as model


@pytest.mark.parametrize("variant,signals,ends,links", [
    ("24", 85, 318, 233), ("29", 109, 385, 276), ("35", 131, 477, 346),
])
def test_topology_preserves_every_pin_and_comparison_boundary(variant, signals, ends, links):
    c = model.cpu_circuit(variant)
    assert len(c["components"]) == c["total_ic"] == int(variant)
    assert c["metrics"]["inter_ic_signal_nets"] == signals
    assert c["metrics"]["signal_pin_endpoints"] == ends
    assert c["metrics"]["minimum_point_to_point_links"] == links
    original = Counter((p["ref"], pin, net) for p in c["board"]["packages"]
                       for pin, net in p["pins"].items() if net is not None)
    displayed = Counter((e["component"], e["pin"], n["id"])
                        for n in c["nets"] for e in n["endpoints"])
    assert original == displayed
    nets = {n["id"]: n for n in c["nets"]}
    assert not nets["VCC"]["inter_ic"] and not nets["GND"]["inter_ic"]
    assert all(not n["inter_ic"] for n in c["nets"] if n["kind"] == "jtag")
    parts = {p["id"]: p for p in c["components"]}
    for p in parts.values():
        if p["part"].startswith("ATF"):
            assert p["signal_pads"]
            assert len(set(p["signal_pads"].values())) == len(p["signal_pads"])
        else:
            assert p["signal_pads"] == {}
    for n in c["nets"]:
        for e in n["endpoints"]:
            assert e["pad"] == parts[e["component"]]["signal_pads"].get(e["pin"])


def test_external_state_bus_membership_and_actual_fitted_pads():
    c = model.cpu_circuit("35")
    buses = {b["id"]: b["nets"] for b in c["buses"]}
    assert buses["PC"] == [f"PC[{i}]" for i in range(16)]
    assert buses["PC_CARRY"] == [f"PC_CARRY[{i}]" for i in range(3)]
    assert buses["A"] == [f"A[{i}]" for i in range(8)]  # not ADDRESS
    nets = {n["id"]: n for n in c["nets"]}
    assert {tuple(e.values()) for e in nets["PC_CARRY[0]"]["endpoints"]} == {
        ("PC0", "RCO", None), ("PC1", "ENT", None)}
    assert {tuple(e.values()) for e in nets["IR[0]"]["endpoints"]} == {
        ("edupccu", "ir0", 25), ("IR", "Q0", None)}
    p = {p["id"]: p for p in c["components"]}
    assert p["PC3"]["pins"]["RCO"] is None
    assert not any(e["component"] == "PC3" and e["pin"] == "RCO"
                   for n in c["nets"] for e in n["endpoints"])
    assert p["ZERO"]["pins"]["P0"] == "Y[0]"
    assert "Y" in p["ZERO"]["role"]


@pytest.mark.parametrize("corruption", ["source", "pad", "fit", "metrics"])
def test_rejects_stale_sources_and_tampered_saved_fit(tmp_path, monkeypatch, corruption):
    evidence = json.loads(model.EVIDENCE.read_text(encoding="utf-8"))
    fit = evidence["variants"]["ir_step_pc"]["fits"]["edupccu"]
    if corruption == "source":
        fit["source_sha256"] = "0" * 64
    elif corruption == "pad":
        fit["signal_pads"]["ir0"] = 24
    elif corruption == "fit":
        fit["design_fits"] = False
    else:
        evidence["wiring"]["ir_step_pc"]["signal_pin_endpoints"] = 1
    path = tmp_path / "evidence.json"
    path.write_text(json.dumps(evidence), encoding="utf-8")
    monkeypatch.setattr(model, "EVIDENCE", path)
    with pytest.raises(ValueError):
        model.cpu_circuit("35")
