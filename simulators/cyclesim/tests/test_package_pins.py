"""Assembly endpoints checked against TI PDIP drawings, not diagram geometry."""
from simulators.cyclesim.viewer_model import circuit_definition


def test_all_exported_pins_have_unique_physical_contacts():
    c = circuit_definition()
    for part in c["components"]:
        physical = part["package"]["pins"]
        assert set(physical) == set(part["pins"])
        assert sorted(v["number"] for v in physical.values()) == list(range(1, 17))
        assert physical["VCC"]["number"] == 16
        assert physical["GND"]["number"] == 8


def test_critical_assembly_connections():
    c = circuit_definition()
    parts = {p["id"]: p for p in c["components"]}
    def contacts(net):
        n = next(n for n in c["nets"] if n["id"] == net)
        return {(e["component"], parts[e["component"]]["package"]["pins"][e["pin"]]["number"])
                for e in n["endpoints"]}
    assert contacts("net_c_lo") == {("U_ALU_283_LO", 9), ("U_ALU_283_HI", 7)}
    assert contacts("net_b_add0") == {("U_ALU_153_0", 9), ("U_ALU_283_LO", 6)}
    assert contacts("net_y_logic0") == {("U_ALU_153_0", 7), ("U_ALU_157_YBP_0", 3)}
    assert contacts("net_sum0") == {("U_ALU_283_LO", 4), ("U_ALU_157_YBP_0", 2)}
    assert contacts("net_a0") == {("U_ALU_153_0", 14), ("U_ALU_283_LO", 5)}
    assert contacts("net_b0") == {("U_ALU_153_0", 2)}
    assert contacts("net_y_mux_sel") == {("U_ALU_157_YBP_0", 1), ("U_ALU_157_YBP_1", 1)}
    assert len(contacts("pwr_gnd")) == 30  # 12 ground + 16 HC153 enables + 2 HC157 enables.
