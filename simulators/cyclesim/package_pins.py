"""TI 16-pin PDIP top-view pinouts; functional names stay identical to the netlist.

Sources: SN74HC153 SCLS112E p3, SN74HC157 SCLS113F p3,
CD74HC283 SCHS176E p3. 283 uses TI's zero-based A0/B0/S0 names.
"""

PIN_ORDER = {
    "74HC153": ("1G", "B", "1C3", "1C2", "1C1", "1C0", "1Y", "GND",
                "2Y", "2C0", "2C1", "2C2", "2C3", "A", "2G", "VCC"),
    "74HC157": ("S", "1A", "1B", "1Y", "2A", "2B", "2Y", "GND",
                "3Y", "3B", "3A", "4Y", "4B", "4A", "G", "VCC"),
    "74HC283": ("S1", "B1", "A1", "S0", "A0", "B0", "CIN", "GND",
                "COUT", "S3", "B3", "A3", "S2", "A2", "B2", "VCC"),
}
SOURCES = {part: f"https://www.ti.com/lit/ds/symlink/{prefix}{part[2:].lower()}.pdf#page=3"
           for part, prefix in (("74HC153", "sn74"), ("74HC157", "sn74"), ("74HC283", "cd74"))}


def package_definition(part):
    outputs = ({"1Y", "2Y"} if part == "74HC153" else
               {"1Y", "2Y", "3Y", "4Y"} if part == "74HC157" else
               {"S0", "S1", "S2", "S3", "COUT"})
    return {
        "type": "PDIP-16", "view": "top", "source": SOURCES[part],
        "pins": {pin: {"number": i, "label": "A/B" if part == "74HC157" and pin == "S" else pin,
                       "direction": "power" if pin in ("VCC", "GND") else "output" if pin in outputs else "input"}
                 for i, pin in enumerate(PIN_ORDER[part], 1)},
    }
