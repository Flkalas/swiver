"""Generate and fit only the DP bank and memory decoder, never the Python CU.

Uses the repository's installed WinCUPL without restoring archived sources.
Writes all generated files under ignored build/hybrid-fit.
"""
from pathlib import Path
import json
import os
import hashlib
import subprocess

from simulators.cyclesim.hybrid.cpu import DP_REGS


def header(name, device):
    return [f"Name {name};", "Partno 00;", "Date 10/23/26;", "Assembly None;", "Location None;", "Revision 01;", "Designer Swiver;",
            "Company Swiver;", f"Device {device};", "PROPERTY ATMEL {JTAG=ON};"]


def dp_source():
    lines = header("bytedp", "f1504plcc44")
    lines += ["PIN 43 = clk;", "PIN 1 = reset;", "PIN = [db0..7];",
              "PIN = [qa0..7];", "PIN = [sel0..2];", "PIN = we;", "PIN = oe;"]
    for k, name in enumerate(DP_REGS):
        lines += [f"PINNODE = {name}_{bit};" for bit in range(8)]
    for k, name in enumerate(DP_REGS):
        sel = " & ".join(("" if k >> i & 1 else "!") + f"sel{i}" for i in range(3))
        for bit in range(8):
            reg = f"{name}_{bit}"
            lines += [f"{reg}.ck = clk;", f"{reg}.ar = reset;",
                      f"{reg}.d = (we & ({sel}) & db{bit}.io) # ((!we # !({sel})) & {reg});"]
    for bit in range(8):
        terms = []
        for k, name in enumerate(DP_REGS):
            sel = " & ".join(("" if k >> i & 1 else "!") + f"sel{i}" for i in range(3))
            terms.append(f"(({sel}) & {name}_{bit})")
        lines += [f"qa{bit} = " + " # ".join(terms) + ";",
                  f"db{bit} = qa{bit};", f"db{bit}.oe = oe;"]
    return "\n".join(lines) + "\n"


def decode_source():
    lines = header("bytedec", "f1502plcc44")
    lines += ["PIN = [a2..15];", "PIN = mapmode;", "PIN = rd;", "PIN = wr;",
              "PIN = ram0n;", "PIN = ram1n;", "PIN = romn;", "PIN = mbn;",
              "PIN = oen;", "PIN = wen;"]
    top = " & ".join(f"a{i}" for i in range(8, 16))
    vector = " & ".join(f"a{i}" for i in range(2, 16))
    boot = " & ".join(f"!a{i}" for i in range(11, 16))
    lines += [f"top = {top};", f"vec = {vector};", f"boot = {boot};",
              "mb = top & !vec;", "rom = !mapmode & (boot # vec);", "ram = !(rom # mb);",
              "ram0n = !(ram & !a15);", "ram1n = !(ram & a15);",
              "romn = !rom;", "mbn = !mb;", "oen = !rd;", "wen = !(wr & !rom);"]
    return "\n".join(lines) + "\n"


def main():
    root = Path(__file__).resolve().parents[3]
    installed = root / "cpld/tools/wincupl-ii"
    out = root / "simulators/cyclesim/build/hybrid-fit"
    out.mkdir(parents=True, exist_ok=True)
    summary = {}
    env = dict(os.environ)
    env["PATH"] = str(installed / "Fitters") + os.pathsep + env.get("PATH", "")
    for name, device, source in (("bytedp", "1504", dp_source()), ("bytedec", "1502", decode_source())):
        pld = out / (name + ".pld")
        pld.write_text(source, encoding="ascii")
        tt2 = out / (name + ".tt2")
        if tt2.exists(): tt2.unlink()  # Exact generated output only; reject stale compile evidence.
        cmd = [str(installed / "Shared/cupl.exe"), "-jlm1u", str(installed / "Shared/cupl.dl"), pld.name]
        compiled = subprocess.run(cmd, cwd=out, env=env, capture_output=True, timeout=60)
        (out / (name + "-compile.log")).write_bytes(compiled.stdout + compiled.stderr)
        print(name, "compiler", compiled.returncode, compiled.stdout.decode(errors="replace")[-1400:])
        if compiled.returncode or not tt2.exists():
            summary[name] = {"compile_exit": compiled.returncode, "fit": "no TT2 produced"}
            continue
        cmd = [str(installed / f"Fitters/fit{device}.exe"), str(tt2), "-o", str(out / (name + "_fit")), "-device", "PLCC44",
               "-strategy", "JTAG", "ON", "-strategy", "tPD", "10"]
        # Legacy fitters resolve atmel.std relative to their working directory.
        fitted = subprocess.run(cmd, cwd=installed / "Fitters", capture_output=True, timeout=60)
        log = fitted.stdout + fitted.stderr
        (out / (name + "-fit.log")).write_bytes(log)
        text = log.decode(errors="replace")
        print(name, "fitter", fitted.returncode, text[-1800:])
        summary[name] = {"compile_exit": compiled.returncode, "fit_exit": fitted.returncode,
                         "design_fits": fitted.returncode == 0 and "Design fits successfully" in text,
                         "source_sha256": hashlib.sha256(source.encode("ascii")).hexdigest(),
                         "tool_sha256": hashlib.sha256(Path(cmd[0]).read_bytes()).hexdigest(),
                         "package": "PLCC44", "jtag": "ON", "requested_tpd_ns": 10,
                         "fit_output": text.replace("\r", "").strip(),
                         "scope": "DP register bank" if device == "1504" else "memory decoder"}
    (out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    if not all(v.get("design_fits") for v in summary.values()):
        raise SystemExit("One or more block fits failed; see summary.json")


if __name__ == "__main__": main()
