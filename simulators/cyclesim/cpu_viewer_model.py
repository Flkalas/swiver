"""Read-only CPU topology built from the same manifests as the fit comparison.

No fitter, ignored build artifacts, or CPU simulation runs at HTTP request time.
The saved source and manifest hashes prevent displaying stale fitted pad numbers.
"""
from __future__ import annotations

from collections import defaultdict
import hashlib
import json
from pathlib import Path
import re

from simulators.cyclesim.hybrid.ram_no1502 import cu_74_source, address_74_source
from simulators.cyclesim.hybrid.ram_no1502_measure import manifest as baseline_manifest
from simulators.cyclesim.hybrid.ram_educational import cu_source, address_source
from simulators.cyclesim.hybrid.ram_educational_measure import manifest, wiring

EVIDENCE = Path(__file__).with_name("hybrid") / "ram-educational-evidence.json"
VARIANTS = {
    "24": ("baseline", "기본형", "IR·단계·PC·AC 내부 / P 외부"),
    "29": ("ir_step", "IR·단계 외부", "IR·단계·AC 외부 / PC·P 내부"),
    "35": ("ir_step_pc", "IR·단계·PC 외부", "IR·단계·PC·AC 외부 / P 내부"),
}


def catalog():
    return [dict(id=k, title=f"{k}칩 · {v[1]}", description=v[2])
            for k, v in VARIANTS.items()]


def natural(value):
    return tuple(int(s) if s.isdigit() else s for s in re.split(r"(\d+)", value))


def group_for(package):
    ref = package["ref"]
    if package["group"] == "external_alu":
        return "alu"
    if package["group"] == "memory":
        return "memory"
    if ref.startswith("DEC_"):
        return "decode"
    if "addr" in ref or ref.startswith(("PC", "PAGE")):
        return "address"
    if ref in ("IR", "STEP") or package["group"] == "cpld":
        return "control"
    return "accumulator"


def role_for(package):
    ref = package["ref"]
    if ref.startswith("U_ALU_153_"):
        return f"논리·B 선택 · bit {ref.rsplit('_', 1)[1]}"
    if ref.startswith("U_ALU_283_"):
        return "4비트 가산기 · " + ("하위" if ref.endswith("LO") else "상위")
    if ref.startswith("U_ALU_157_"):
        return "ALU 출력 선택"
    if "addr" in ref:
        return "주소·페이지 제어"
    if package["group"] == "cpld":
        return "실행 제어"
    if ref.startswith("WRITEBACK"):
        return "DB / ALU → AC 선택"
    if ref.startswith("PC_DRIVER"):
        return "PC → 주소 버스"
    if re.fullmatch(r"PC\d", ref):
        i = int(ref[-1])
        return f"PC [{4*i+3}:{4*i}]"
    if ref.startswith("PAGE"):
        return "P 페이지 레지스터"
    return {"IR": "명령 레지스터", "STEP": "실행 단계 카운터",
            "AC": "누산기", "AC_DRIVER": "AC → DB", "ZERO": "ALU Y = 0 검사",
            "RAM0": "하위 32 KiB RAM", "RAM1": "상위 32 KiB RAM",
            "ROM": "부트 Flash", "DEC_TOP": "상위 주소 검사",
            "DEC_TAIL": "하위 주소 검사", "DEC_BOOT": "부트 영역 디코드",
            "DEC_SPLIT": "RAM / ROM 선택", "DEC_GLUE": "디코드 결합"}.get(ref, ref)


def net_kind(net):
    if net in ("VCC", "GND"):
        return "power"
    if re.search(r"_T(?:DI|DO|CK|MS)$", net):
        return "jtag"
    if net.startswith(("ADDRESS[", "PC[")):
        return "address"
    if net.startswith(("DB[", "A[", "Y[", "WRITEBACK[", "net_b_add", "net_sum", "net_y_logic")):
        return "data"
    return "control"


def cpu_circuit(variant="35"):
    if variant not in VARIANTS:
        raise ValueError("variant는 24, 29, 35 중 하나여야 합니다.")
    # Read fresh on every request: replacing an evidence file must not leave a
    # cached old pin map visible. These small manifests take milliseconds.
    evidence = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    key, title, description = VARIANTS[variant]
    base = baseline_manifest(evidence["baseline_fits"])
    if variant == "24":
        fits = evidence["baseline_fits"]
        sources = dict(ramcu74=cu_74_source(), ramaddr74=address_74_source())
        board = base
    else:
        fits = evidence["variants"][key]["fits"]
        external_pc = variant == "35"
        prefix = "edupc" if external_pc else "edu"
        sources = {prefix+"cu": cu_source(external_pc), prefix+"addr": address_source(external_pc)}
        board = manifest(fits, base, external_pc)
    for name, report in fits.items():
        if (not report["design_fits"] or not report["resource_report_consistent"]
                or report["compile_exit"] != 0 or report["fit_exit"] != 0
                or hashlib.sha256(sources[name].encode()).hexdigest() != report["source_sha256"]):
            raise ValueError(f"{name}: 현재 소스와 저장된 fit 검증 자료가 일치하지 않습니다.")
    digest = hashlib.sha256((json.dumps(board, indent=2)+"\n").encode()).hexdigest()
    if digest != evidence["netlist_sha256"][key]:
        raise ValueError("현재 연결표와 저장된 검증 자료가 일치하지 않습니다. 연결표를 재검증해 주세요.")
    measured = wiring(board)
    metrics = {k: v for k, v in measured.items() if k != "net_endpoints"}
    if metrics != evidence["wiring"][key]:
        raise ValueError("연결표의 배선 집계가 저장된 검증 자료와 다릅니다.")
    components, endpoints = [], defaultdict(list)
    for package in board["packages"]:
        pads = package.get("signal_pad_numbers", {})
        component = dict(id=package["ref"], part=package["part"], group=group_for(package),
                         role=role_for(package), pins=package["pins"], signal_pads=pads)
        if package["ref"] in fits:
            report = fits[package["ref"]]
            component["fit"] = {k: report[k] for k in (
                "macrocells", "macrocells_available", "general_io_excluding_jtag",
                "dedicated_inputs", "jtag", "device", "package")}
        components.append(component)
        for pin, net in package["pins"].items():
            if net is not None:
                endpoints[net].append(dict(component=component["id"], pin=pin, pad=pads.get(pin)))
    nets = [dict(id=net, kind=net_kind(net), endpoints=ends,
                 inter_ic=net not in ("VCC", "GND") and len({e["component"] for e in ends}) >= 2)
            for net, ends in sorted(endpoints.items(), key=lambda item: natural(item[0]))]
    buses = []
    for name in ("DB", "ADDRESS", "A", "Y", "IR", "STEP", "PC", "WRITEBACK", "COMMAND", "PC_CARRY"):
        bits = sorted((n for n in endpoints if re.fullmatch(re.escape(name)+r"\[\d+\]", n)), key=natural)
        if bits:
            buses.append(dict(id=name, nets=bits, label=f"{name}[{len(bits)-1}:0]"))
    return dict(schema="swiver-cpu-viewer-v1", variant=variant, variants=catalog(),
                title=f"{variant}칩 · {title}", description=description,
                total_ic=board["total_ic"], logic_74=sum(n for p, n in board["part_totals"].items() if p.startswith("74")),
                part_totals=board["part_totals"], metrics=metrics, components=components,
                nets=nets, buses=buses, netlist_sha256=digest, board=board,
                boundary="실험용 RAM ISA 연결도 · 전압/시간 시뮬레이션 아님",
                pin_boundary="CPLD 신호 핀만 vendor fit의 PLCC44 번호. 74·메모리는 기능 핀명이며, 전원 핀 전체 배치는 포함하지 않습니다.",
                count_boundary="IC 간 신호만 집계. 전원·상수·외부 커넥터 제외. 최소 연결 수는 단자 수 − 넷 수이며 실제 점퍼 수가 아닙니다.",
                excluded="발진기·리셋/WAIT/MAP_MODE 입력원·mailbox MCU·부하 버퍼·수동소자는 칩 수에 포함하지 않습니다.")
