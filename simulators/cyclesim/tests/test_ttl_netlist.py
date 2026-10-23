"""Package connectivity/clock/unknown-state checks for the 74HC backend."""
import pytest

from simulators.cyclesim.ttl.cpu import build_cpu
from simulators.cyclesim.ttl.netlist import Circuit
from simulators.cyclesim.values import X, Z


def test_574_simultaneous_capture_and_external_enable_mux():
    c = Circuit()
    enable = c.bus("enable", 1)
    a, b = c.reg("a", 8), c.reg("b", 8)
    c.bind(a, b, enable[0])
    c.bind(b, a, enable[0])
    c.finalize()
    c.set(a, 0x12)
    c.set(b, 0x34)
    c.set(enable, 1)
    c.settle()
    c.clock()
    assert (c.read(a), c.read(b)) == (0x34, 0x12)
    c.set(enable, 0)
    c.settle()
    c.clock()
    assert (c.read(a), c.read(b)) == (0x34, 0x12)
    assert sum(p.part == "74HC157" for p in c.packages) == 4


def test_245_disabled_releases_bus_and_unknown_enable_propagates():
    c = Circuit()
    data, en = c.bus("data", 8), c.bus("en", 1)
    out = c.driver(data, en[0])
    c.finalize()
    c.set(data, 0xA5)
    c.set(en, 1)
    c.settle()
    assert c.read(out) == 0xA5
    c.set(en, 0)
    c.settle()
    assert all(c.values[n] == Z for n in out)
    c.values[en[0]] = X
    c.settle()
    assert all(c.values[n] == X for n in out)


def test_export_has_twelve_alu_packages_and_only_74hc_logic():
    c, _ = build_cpu()
    export = c.export()
    assert sum(p["group"] == "alu" for p in export["packages"]) == 12
    assert all(p["part"].startswith("74HC") for p in export["packages"])
    assert sum(sum(parts.values()) for parts in c.inventory().values()) == len(c.packages)
    for p in export["packages"]:
        assert all(n is None or n in export["nets"] for n in p["pins"].values())
        if p["part"] == "74HC574":
            assert p["pins"]["CLK"] == "CLK_SYS"
            assert all(f"D{i}" in p["pins"] for i in range(8))
    assert c.depth_report()[0]["levels"] > 0


def test_unbound_register_fails_instead_of_becoming_behavioral_state():
    c = Circuit()
    c.reg("unbound", 1)
    with pytest.raises(ValueError, match="unbound"):
        c.finalize()
