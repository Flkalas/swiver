"""Local hardware candidates. Only complete fitted combinations are feasible.

Individual block fits are retained as partial candidates, never as working BOMs.
"""
from pathlib import Path
import json

from simulators.cyclesim.hybrid.fit_blocks import header
from simulators.cyclesim.hybrid.partition_probe import fit


def integrated_alu_source(register_count=4):
    """Move the parallel ADD/SUB ALU into the byte-bus register CPLD.

    R0/PClo/PChi[/WORK] are internal. RP requires external bytes. The original
    MBR and RESULT latches remain, exposing B/Y to keep timing independent.
    This is a block feasibility probe, not yet a complete CPU implementation.
    """
    name = f"dpa{register_count}"
    lines = header(name, "f1504plcc44")
    lines += ["PIN 43 = clk;", "PIN 1 = reset;", "PIN 44 = oe;", "PIN 2 = sub;",
              "PIN = [db0..7];", "PIN = [b0..7];", "PIN = [y0..7];",
              "PIN = [sel0..1];", "PIN = we;", "PIN = carry;"]
    for k in range(register_count):
        for bit in range(8): lines.append(f"PINNODE = r{k}_{bit};")
    for bit in range(8): lines += [f"PINNODE = a{bit};", f"PINNODE = c{bit+1};"]
    for k in range(register_count):
        sel = " & ".join(("" if k >> i & 1 else "!") + f"sel{i}" for i in range(2))
        for bit in range(8):
            reg = f"r{k}_{bit}"
            lines += [f"{reg}.ck = clk;", f"{reg}.ar = reset;",
                      f"{reg}.d = (we & ({sel}) & db{bit}.io) # ((!we # !({sel})) & {reg});"]
    for bit in range(8):
        terms = []
        for k in range(register_count):
            sel = " & ".join(("" if k >> i & 1 else "!") + f"sel{i}" for i in range(2))
            terms.append(f"(({sel}) & r{k}_{bit})")
        cin = "sub" if bit == 0 else f"c{bit}"
        bx = f"(b{bit} $ sub)"
        lines += [f"a{bit} = " + " # ".join(terms) + ";",
                  f"db{bit} = a{bit};", f"db{bit}.oe = oe;",
                  f"y{bit} = a{bit} $ {bx} $ {cin};",
                  f"c{bit+1} = (a{bit} & {bx}) # (a{bit} & {cin}) # ({bx} & {cin});"]
    lines.append("carry = c8;")
    return "\n".join(lines) + "\n"


def external_bank_alu_source(device="1504"):
    """All five DP bytes are external 574s. DBUS directly supplies ALU A.

    Two external 3-to-8 decoders expand SEL/WE/OE into five clocks/enables.
    This generator fits the ALU only; that bank is not yet pin-simulated.
    """
    name = "aluext" if device == "1504" else "alu1502"
    lines = header(name, f"f{device}plcc44")
    lines += ["PIN 2 = sub;", "PIN = [a0..7];", "PIN = [b0..7];",
              "PIN = [y0..7];", "PIN = carry;"]
    lines += [f"PINNODE = c{i};" for i in range(1, 9)]
    for bit in range(8):
        cin = "sub" if bit == 0 else f"c{bit}"
        bx = f"(b{bit} $ sub)"
        lines += [f"y{bit} = a{bit} $ {bx} $ {cin};",
                  f"c{bit+1} = (a{bit} & {bx}) # (a{bit} & {cin}) # ({bx} & {cin});"]
    lines.append("carry = c8;")
    return "\n".join(lines) + "\n"


def main():
    from simulators.cyclesim.hybrid.rom_search import (
        sequencer_source, expander_source, guarded_partition_sources,
        lean_sequencer_source, looping_halt_source, shared_target_source, ControlStore)
    root = Path(__file__).resolve().parents[3]
    installed = root / "cpld/tools/wincupl-ii"
    _, ctrl, dp = guarded_partition_sources()
    candidates = [
        (f"dpa{count}", integrated_alu_source(count), "1504", ()) for count in (2, 3, 4)]
    candidates += [("romseq", sequencer_source(), "1504", ()),
        ("romctrl", expander_source(), "1502", ()),
        ("romdir", sequencer_source(direct=True), "1504", ()),
        ("ctrldir", expander_source(direct=True), "1502", ()),
        ("ctrlsplt", ctrl, "1502", ()), ("dprom", dp, "1504", ()),
        ("romlean", lean_sequencer_source(), "1504", ()),
        ("romloop", looping_halt_source(), "1504", ()),
        ("romshare", shared_target_source(), "1504", ()),
        ("aluext", external_bank_alu_source(), "1504", (("XOR_Synthesis", "ON"),)),
        ("alu1502", external_bank_alu_source("1502"), "1502", (("XOR_Synthesis", "ON"),))]
    results = {}
    for name, source, device, strategies in candidates:
        results[name] = fit(name, source, root, installed, device, strategies)
        results[name]["complete_cpu"] = False
    out = root / "simulators/cyclesim/build/hybrid-partition"
    (out / "control.bin").write_bytes(ControlStore().image)
    evidence = dict(scope="Bounded local partition search; block fits are not a complete CPU",
        candidates=results, complete_qualified_combinations=[],
        boundaries=["65/64 resource reports remain unresolved despite fitter success",
                    "External bank needs clock/output-enable decoding and integrated simulation",
                    "No post-fit simulation, reset-vector boot, or board timing acceptance"])
    (out / "local-search.json").write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__": main()
