"""Functional interconnect and package inventory for the byte-bus experiment.

Counts are generated from this manifest. CPLD ports are functional nets, not
assigned PLCC pads; MC budgets are transparent engineering estimates, not fits.
"""
from collections import Counter

from simulators.cyclesim.ttl.netlist import Circuit
from simulators.cyclesim.hybrid.cpu import DP_REGS, LATCHES


def decoder():
    c = Circuit()
    a = c.bus("ADDRESS", 16)
    mode, rd, wr = (c.bus(n, 1)[0] for n in ("MAP", "MEM_RD", "MEM_WR"))
    c.group = "memory_decode"
    top = c.eq(a[8:], 255)
    vector = c.all(top, c.eq(a[2:8], 63))
    mailbox = c.all(top, c.inv(vector))
    rom = c.all(c.inv(mode), c.or_(c.eq(a[11:], 0), vector))
    ram = c.inv(c.or_(rom, mailbox))
    for name, net in {
        "RAM0_CE_N": c.inv(c.all(ram, c.inv(a[15]))),
        "RAM1_CE_N": c.inv(c.all(ram, a[15])),
        "ROM_CE_N": c.inv(rom), "MAILBOX_CE_N": c.inv(mailbox),
        "MEM_OE_N": c.inv(rd), "MEM_WE_N": c.inv(c.all(wr, c.inv(rom))),
    }.items(): c.probes[name] = [net]
    c.finalize()
    return c


def port_budget():
    cu = dict(DBUS=8, DP_SEL=3, DP_WE=1, DP_OE=1, LATCH_CLK=6,
              TMP_OE_N=2, SUB=1, SUB_N=1, ALU_OE_N=1, MEM_RD=1, MEM_WR=1, ALU_C=1)
    dp = dict(DBUS=8, ALU_A=8, DP_SEL=3, DP_WE=1, DP_OE=1)
    dec = dict(ADDRESS_A2_A15=14, MAP=1, MEM_RD=1, MEM_WR=1, CE_N=4, OE_N=1, WE_N=1)
    result = {}
    for name, ports, capacity, dedicated in (
        ("CU", cu, 64, ["CLK", "RESET", "WAIT"]),
        ("DP", dp, 64, ["CLK", "RESET"]),
        ("DECODE", dec, 32, []),
    ):
        result[name] = dict(ports=ports, general_io_used=sum(ports.values()),
                            general_io_available_with_jtag=28, dedicated_inputs=dedicated,
                            macrocells_capacity=capacity, physical_pad_assignment=None)
        assert result[name]["general_io_used"] <= 28
    result["DP"]["mc_budget"] = dict(state_bits=40, alu_a_mux=8, bus_output=8,
                                      select_decode_allowance=[5, 8], total=[61, 64])
    # CU control outputs are registered for safe latch pulses. Reserve explicit
    # state for sequencing and guard facts; never count them as free host state.
    result["CU"]["mc_budget"] = dict(ir=8, architectural_flags=2, work_carry=1,
        guard_facts=4, micro_pc_allowance=6, transfer_phase=2, halted=1,
        registered_control_outputs=18, constant_bus_output=8,
        combinational_expansion_allowance=[8, 20], total=[58, 70])
    result["DECODE"]["mc_budget"] = dict(outputs=6, shared_terms_allowance=[2, 10], total=[8, 16])
    return result


def manifest(use_1502=True):
    # Import the frozen ALU so twelve packages are counted from actual wiring.
    c = Circuit()
    a, b, sub = c.bus("ALU_A", 8), c.bus("MBR", 8), c.bus("SUB", 1)
    y, carry = c.import_alu(a, b, sub[0])
    c.finalize()
    packages = []
    # The imported inverter is implemented by CU.SUB_N, not an extra HC04.
    inverse = {out[0]: "SUB_N" for kind, _, out, _ in c.ops if kind == "74HC04"}
    inverse.update({net: f"ALU_Y[{i}]" for i, net in enumerate(y)})
    inverse[carry] = "ALU_C"
    for p in c.packages:
        if p.part == "74HC04": continue
        packages.append(dict(ref=p.ref, part=p.part, role="ALU",
            pins={k: inverse.get(v, c.names[v]) for k, v in p.pins.items()}))
    for name in LATCHES:
        q = ([f"ADDRESS[{i + (8 if name == 'ADDR_HI' else 0)}]" for i in range(8)]
             if name.startswith("ADDR") else
             [f"MBR[{i}]" for i in range(8)] if name == "MBR" else [f"DBUS[{i}]" for i in range(8)])
        packages.append(dict(ref=name, part="74HC574", role="external_latch",
            pins={**{f"D{i}": f"{'ALU_Y' if name == 'RESULT' else 'DBUS'}[{i}]" for i in range(8)},
                  **{f"Q{i}": q[i] for i in range(8)}, "CLK": f"CU.{name}_CLK",
                  "OE_N": f"CU.{name}_OE_N" if name.startswith("TMP") or name == "RESULT" else "GND"}))
    packages += [dict(ref="CU", part="ATF1504AS-10JU44", role="sequencer"),
                 dict(ref="DP", part="ATF1504AS-10JU44", role="five_byte_register_bank"),
                 dict(ref="CLOCK_RESET", part="74HC14", role="clock_reset_conditioning"),
                 dict(ref="RAM0", part="IS62C256", role="memory"),
                 dict(ref="RAM1", part="IS62C256", role="memory"),
                 dict(ref="ROM", part="SST39SF010A", role="memory")]
    d = decoder()
    if use_1502:
        packages.append(dict(ref="DECODE", part="ATF1502AS-10JU44", role="memory_decode"))
    else:
        packages += [dict(ref="DEC_" + p["ref"], part=p["part"], role="memory_decode", pins=p["pins"])
                     for p in d.export()["packages"]]
    totals = dict(sorted(Counter(p["part"] for p in packages).items()))
    budgets = port_budget()
    if not use_1502: del budgets["DECODE"]
    return dict(schema="swiver-byte-bus-hybrid-v1", experimental=True,
                packages=packages, part_totals=totals, total_ic=len(packages),
                oscillator_modules=1, external_latch_bits=8 * len(LATCHES),
                dp_state_bits=8 * len(DP_REGS), cpld_budgets=budgets,
                cpld_fit="full CU not implemented; block fit evidence is reported separately",
                decoder_equations=d.export(),
                boundaries=["CPLDs are functional Python blocks, not gate/fitter models.",
                    "CU instruction generator has not been lowered to a complete finite-state netlist.",
                    "Six micro-PC bits are a budget, not a measured compiled state count.",
                    "Registered latch clocks use setup/capture/hold/release; no combinational clock gating.",
                    "Functional interconnect only: power pins, PLCC pad placement and PCB routing not exported.",
                    "Memory dictionaries and initial fixture state are simulation boundaries.",
                    "Clock/reset conditioning allocation is not a power-on-reset or timing acceptance.",
                    "Oscillator, adapters, mailbox coprocessor and passive components excluded from total_ic."])
