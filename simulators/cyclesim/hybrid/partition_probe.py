"""Fit a concrete stack-check relocation, without claiming full CPU acceptance.

DP owns RP_LO, so it can inspect that byte without four duplicate CU flags.
CU sends guard-enable and call/ret, receives sticky fault on dedicated pin 44.
Moving SUB inversion to DP releases the second required CU output pad.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

from simulators.cyclesim.hybrid.cu_fsm import cu_source
from simulators.cyclesim.hybrid.fit_blocks import dp_source


def dp_guard_source():
    source = dp_source().replace("Name bytedp;", "Name dpguard;")
    source += "PIN = guardena;\nPIN = iscall;\nPIN = fault;\nPIN = alusub;\nPIN = subn;\n"
    source += "subn = !alusub;\nfault.ck = clk;\nfault.ar = reset;\n"
    source += "hiok = db7.io & db6.io & db5.io & db4.io & (db3.io # (db2.io & db1.io)) & !(db3.io & db2.io & db1.io & db0.io);\n"
    source += "hife = db7.io & db6.io & db5.io & db4.io & db3.io & db2.io & db1.io & !db0.io;\n"
    source += "hif6 = db7.io & db6.io & db5.io & db4.io & !db3.io & db2.io & db1.io & !db0.io;\n"
    source += "lozero = " + " & ".join(f"!RP_LO_{i}" for i in range(8)) + ";\n"
    source += "lof0 = " + " & ".join(("" if i >= 4 else "!") + f"RP_LO_{i}" for i in range(8)) + ";\n"
    source += "loabove = RP_LO_7 & RP_LO_6 & RP_LO_5 & RP_LO_4 & (RP_LO_3 # RP_LO_2 # RP_LO_1 # RP_LO_0);\n"
    source += "fault.d = fault # (guardena & (RP_LO_0 # !hiok # (hife & loabove) # (iscall & hife & lof0) # (!iscall & hif6 & lozero)));\n"
    return source


def cu_without_guard_source():
    # Parse the generated statement boundaries, not arbitrary file text.
    statements = [" ".join(s.split()) for s in cu_source().split(";") if s.strip()]
    removed = {"odd", "above", "equal", "zero", "fault", "subn"}
    result = []
    for s in statements:
        if s == "Name bytecu": s = "Name cuguard"
        if s in {f"PINNODE = {n}" for n in removed} or s == "PIN = subn": continue
        if re.match(r"(?:odd|above|equal|zero|fault|subn)\.(?:d|ck|ar|ap)\s*=", s): continue
        if re.match(r"(?:guardload|badstack|dbfe|dbf6|validhi)\s*=", s): continue
        result.append(s + ";")
    result[10:10] = ["PIN 44 = fault;", "PIN = guardena;", "PIN = iscall;"]
    result += ["guardena = callcheck # retcheck;", "iscall = callcheck;"]
    import textwrap
    return "\n".join(textwrap.fill(s, width=100, break_long_words=False,
                                   break_on_hyphens=False) for s in result) + "\n"


def fit(name, source, root, installed, device="1504", strategies=()):
    out = root / "simulators/cyclesim/build/hybrid-partition" / name
    out.mkdir(parents=True, exist_ok=True)
    for filename in (name + ".tt2", name + "_fit.fit", name + "_fit.jed", "summary.json"):
        path = out / filename
        if path.exists(): path.unlink()
    (out / (name + ".pld")).write_text(source, encoding="ascii")
    env = dict(os.environ)
    env["PATH"] = str(installed / "Fitters") + os.pathsep + env.get("PATH", "")
    compiled = subprocess.run([str(installed / "Shared/cupl.exe"), "-jlm1u",
        str(installed / "Shared/cupl.dl"), name + ".pld"], cwd=out, env=env, capture_output=True, timeout=180)
    (out / "compile.log").write_bytes(compiled.stdout + compiled.stderr)
    summary = dict(source_sha256=hashlib.sha256(source.encode("ascii")).hexdigest(),
                   compile_exit=compiled.returncode, design_fits=False)
    if compiled.returncode == 0 and (out / (name + ".tt2")).exists():
        fitted = subprocess.run([str(installed / f"Fitters/fit{device}.exe"), str(out / (name + ".tt2")),
            "-o", str(out / (name + "_fit")), "-device", "PLCC44", "-strategy", "JTAG", "ON",
            "-strategy", "tPD", "10"] + [item for key, value in strategies for item in ("-strategy", key, value)], cwd=installed / "Fitters", capture_output=True, timeout=180)
        (out / "fit.log").write_bytes(fitted.stdout + fitted.stderr)
        report = (out / (name + "_fit.fit")).read_text(errors="replace")
        summary.update(fit_exit=fitted.returncode,
                       design_fits=fitted.returncode == 0 and b"Design fits successfully" in fitted.stdout)
        abort = re.search(r"# Aborting : Design is large, it contains (\d+) Logic Cell", report)
        if abort: summary["preplacement_logic_cells"] = int(abort[1])
        if summary["design_fits"]:
            for key, pattern in (("macrocells", r"Total Macro cells used\s+(\d+)/\d+"),
                                 ("io_including_jtag", r"Total I/O pins used\s+(\d+)/32"),
                                 ("dedicated_inputs", r"Total dedicated input used:\s+(\d+)/4")):
                summary[key] = int(re.search(pattern, report)[1])
        summary["resource_report_consistent"] = bool(summary["design_fits"] and summary["macrocells"] <= (64 if device == "1504" else 32))
        summary["fit_output"] = (fitted.stdout + fitted.stderr).decode(errors="replace").replace("\r", "")
    else: summary["compile_output"] = compiled.stdout.decode(errors="replace")
    summary.update(strategies=list(strategies), device=f"ATF{device}AS", package="PLCC44", jtag="ON", requested_tpd_ns=10,
                   validation_boundary="Partition fit experiment only; no pin-level CPU simulation or timing acceptance")
    (out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(name, json.dumps(summary), flush=True)
    return summary


def main():
    root = Path(__file__).resolve().parents[3]
    installed = root / "cpld/tools/wincupl-ii"
    # Legacy tools share working files in their installed fitter directory.
    results = {}
    for name, source in (("dpguard", dp_guard_source()), ("cuguard", cu_without_guard_source())):
        results[name] = fit(name, source, root, installed)
    out = root / "simulators/cyclesim/build/hybrid-partition/summary.json"
    out.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__": main()
