"""Fit the explicit experimental CU; report failures as evidence, not estimates."""
import hashlib
import json
import os
import re
from pathlib import Path
import subprocess

from simulators.cyclesim.hybrid.cu_fsm import cu_source, graph


def main():
    root = Path(__file__).resolve().parents[3]
    installed = root / "cpld/tools/wincupl-ii"
    out = root / "simulators/cyclesim/build/hybrid-cu-fit"
    out.mkdir(parents=True, exist_ok=True)
    source = cu_source()
    (out / "bytecu.pld").write_text(source, encoding="ascii")
    for name in ("bytecu.tt2", "bytecu_fit.jed", "bytecu_fit.fit", "summary.json", "compile.log", "fit.log"):
        p = out / name
        if p.exists(): p.unlink()
    env = dict(os.environ)
    env["PATH"] = str(installed / "Fitters") + os.pathsep + env.get("PATH", "")
    compile_result = subprocess.run([str(installed / "Shared/cupl.exe"), "-jlm1u",
        str(installed / "Shared/cupl.dl"), "bytecu.pld"], cwd=out, env=env, capture_output=True, timeout=180)
    log = compile_result.stdout + compile_result.stderr
    (out / "compile.log").write_bytes(log)
    summary = dict(source_sha256=hashlib.sha256(source.encode("ascii")).hexdigest(),
                   states=len(graph().nodes), state_bits=graph().bits,
                   compile_exit=compile_result.returncode, design_fits=False,
                   device="ATF1504AS", package="PLCC44", jtag="ON", requested_tpd_ns=10,
                   fitter_sha256=hashlib.sha256((installed / "Fitters/fit1504.exe").read_bytes()).hexdigest(),
                   scope="Direct binary CU FSM candidate; not a minimum-area proof or board qualification")
    print(log.decode(errors="replace")[-2500:])
    tt2 = out / "bytecu.tt2"
    if compile_result.returncode == 0 and tt2.exists():
        result = subprocess.run([str(installed / "Fitters/fit1504.exe"), str(tt2),
            "-o", str(out / "bytecu_fit"), "-device", "PLCC44", "-strategy", "JTAG", "ON",
            "-strategy", "tPD", "10"], cwd=installed / "Fitters", capture_output=True, timeout=180)
        log = result.stdout + result.stderr
        (out / "fit.log").write_bytes(log)
        summary.update(fit_exit=result.returncode, fit_output=log.decode(errors="replace").replace("\r", ""),
                       design_fits=result.returncode == 0 and b"Design fits successfully" in log)
        report = (out / "bytecu_fit.fit").read_text(errors="replace")
        abort = re.search(r"# Aborting : Design is large, it contains (\d+) Logic Cell", report)
        if abort:
            summary["preplacement_logic_cells"] = int(abort[1])
            summary["failure_detail"] = abort[0]
        summary["validation_boundary"] = "Transfer graph tested against CpuM3b; generated CUPL is not pin-level or post-fit simulated."
        print(summary["fit_output"][-4000:])
    (out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in summary.items() if k != "fit_output"}))
    if not summary["design_fits"]: raise SystemExit(1)


if __name__ == "__main__": main()
