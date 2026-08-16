"""Self-contained ALU8 interactive viewer (12 DIP + functional gates).

Generated from cyclesim netlist — no archived hwsim/tools required.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from simulators.cyclesim.export.alu8_netlist import (
    DESCRIPTION,
    build_alu8_func_netlist,
    port_net_names,
)

CONTROL_PREFIXES = (
    "net_cin",
    "net_153_s",
    "net_bctrl",
    "net_lgc",
    "net_y_mux_sel",
)


def _is_control_net(name: str) -> bool:
    return any(name.startswith(p) or name == p for p in CONTROL_PREFIXES)


def build_alu8_gate_graph() -> dict[str, Any]:
    """Functional-gate graph: 153→mux1+mux2, 283→add4, 157→4×mux2."""
    nl = build_alu8_func_netlist()
    by_ref = {i["ref"]: i for i in nl["instances"]}
    ports = port_net_names()

    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    packages: list[dict[str, Any]] = []

    def add_edge(net: str, src: str, src_pin: str, dst: str, dst_pin: str) -> None:
        edges.append(
            {
                "net": net,
                "src": src,
                "src_pin": src_pin,
                "dst": dst,
                "dst_pin": dst_pin,
                "control": _is_control_net(net),
            }
        )

    for i in range(8):
        nodes.append(
            {
                "id": f"port_a{i}",
                "kind": "port",
                "label": f"A{i}",
                "net": f"net_a{i}",
                "col": 0,
                "row": i,
                "package": None,
            }
        )
        nodes.append(
            {
                "id": f"port_b{i}",
                "kind": "port",
                "label": f"B{i}",
                "net": f"net_b{i}",
                "col": 0,
                "row": i + 0.35,
                "package": None,
            }
        )
        nodes.append(
            {
                "id": f"port_y{i}",
                "kind": "port",
                "label": f"Y{i}",
                "net": f"net_y{i}",
                "col": 4,
                "row": i,
                "package": None,
            }
        )

    ctrl_ports = [
        ("port_cin", "CIN", "net_cin", 8.0),
        ("port_s0", "S0", "net_153_s0", 8.4),
        ("port_s1", "S1", "net_153_s1", 8.8),
        ("port_ymux", "Y_MUX", "net_y_mux_sel", 9.2),
    ]
    for pid, label, net, row in ctrl_ports:
        nodes.append(
            {
                "id": pid,
                "kind": "port",
                "label": label,
                "net": net,
                "col": 0,
                "row": row,
                "package": None,
                "control": True,
            }
        )
    for i in range(4):
        nodes.append(
            {
                "id": f"port_bctrl{i}",
                "kind": "port",
                "label": f"BCTRL{i}",
                "net": f"net_bctrl{i}",
                "col": 0,
                "row": 9.6 + i * 0.35,
                "package": None,
                "control": True,
            }
        )
        nodes.append(
            {
                "id": f"port_lgc{i}",
                "kind": "port",
                "label": f"LGC{i}",
                "net": f"net_lgc{i}",
                "col": 0,
                "row": 11.2 + i * 0.35,
                "package": None,
                "control": True,
            }
        )

    nodes.append(
        {
            "id": "port_c_hi",
            "kind": "port",
            "label": "C_HI",
            "net": "net_c_hi",
            "col": 4,
            "row": 8.2,
            "package": None,
        }
    )
    nodes.append(
        {
            "id": "port_cmp_z",
            "kind": "port",
            "label": "CMP_Z",
            "net": "net_cmp_z",
            "col": 4,
            "row": 8.6,
            "package": None,
        }
    )
    nodes.append(
        {
            "id": "port_cmp_c",
            "kind": "port",
            "label": "CMP_C",
            "net": "net_cmp_c_ge",
            "col": 4,
            "row": 9.0,
            "package": None,
        }
    )

    # 153: data 0..3 + select S0/S1 (operand A→S0, B→S1 per alu8-phase-b)
    for i in range(8):
        ref = f"U_ALU_153_{i}"
        inst = by_ref[ref]
        packages.append(
            {
                "id": ref,
                "part": "74HC153",
                "label": f"74HC153[{i}]",
                "gates": [f"mux1_bit_{i}", f"mux2_bit_{i}"],
            }
        )
        mux1 = f"mux1_bit_{i}"
        mux2 = f"mux2_bit_{i}"
        nodes.append(
            {
                "id": mux1,
                "kind": "mux4",
                "label": f"mux1[{i}]",
                "subtitle": "logic",
                "col": 1,
                "row": i,
                "package": ref,
                "pins": {
                    "0": inst["pins"]["1C0"],
                    "1": inst["pins"]["1C1"],
                    "2": inst["pins"]["1C2"],
                    "3": inst["pins"]["1C3"],
                    "S0": inst["pins"]["A"],
                    "S1": inst["pins"]["B"],
                    "Y": inst["pins"]["1Y"],
                },
            }
        )
        nodes.append(
            {
                "id": mux2,
                "kind": "mux4",
                "label": f"mux2[{i}]",
                "subtitle": "B_CTRL",
                "col": 1.55,
                "row": i,
                "package": ref,
                "pins": {
                    "0": inst["pins"]["2C0"],
                    "1": inst["pins"]["2C1"],
                    "2": inst["pins"]["2C2"],
                    "3": inst["pins"]["2C3"],
                    "S0": inst["pins"]["A"],
                    "S1": inst["pins"]["B"],
                    "Y": inst["pins"]["2Y"],
                },
            }
        )
        # Select: A→S0, B→S1 (operand select)
        add_edge(inst["pins"]["A"], f"port_a{i}", "out", mux1, "S0")
        add_edge(inst["pins"]["B"], f"port_b{i}", "out", mux1, "S1")
        add_edge(inst["pins"]["A"], f"port_a{i}", "out", mux2, "S0")
        add_edge(inst["pins"]["B"], f"port_b{i}", "out", mux2, "S1")
        # Optional force-select from package control nets (behavioral override)
        add_edge("net_153_s0", "port_s0", "out", mux1, "S0")
        add_edge("net_153_s1", "port_s1", "out", mux1, "S1")
        add_edge("net_153_s0", "port_s0", "out", mux2, "S0")
        add_edge("net_153_s1", "port_s1", "out", mux2, "S1")
        for c in range(4):
            add_edge(f"net_lgc{c}", f"port_lgc{c}", "out", mux1, str(c))
            add_edge(f"net_bctrl{c}", f"port_bctrl{c}", "out", mux2, str(c))

    for half, ref, row, a_lo in (
        ("lo", "U_ALU_283_LO", 1.5, 0),
        ("hi", "U_ALU_283_HI", 5.5, 4),
    ):
        inst = by_ref[ref]
        gid = f"add4_{half}"
        packages.append({"id": ref, "part": "74HC283", "label": ref, "gates": [gid]})
        nodes.append(
            {
                "id": gid,
                "kind": "add4",
                "label": f"ADD4 {half.upper()}",
                "subtitle": f"a{a_lo}..{a_lo + 3}",
                "col": 2.4,
                "row": row,
                "package": ref,
                "pins": dict(inst["pins"]),
            }
        )
        cin = inst["pins"]["CIN"]
        if cin == "net_cin":
            add_edge(cin, "port_cin", "out", gid, "CIN")
        else:
            add_edge(cin, "add4_lo", "COUT", gid, "CIN")
        for n in range(4):
            i = a_lo + n
            add_edge(f"net_a{i}", f"port_a{i}", "out", gid, f"A{n}")
            add_edge(f"net_b_add{i}", f"mux2_bit_{i}", "Y", gid, f"B{n}")

    # 157 YMUX: data 0=sum, 1=logic; select S
    for half, ref, y_lo in (("0", "U_ALU_157_YBP_0", 0), ("1", "U_ALU_157_YBP_1", 4)):
        inst = by_ref[ref]
        gate_ids: list[str] = []
        for n in range(4):
            i = y_lo + n
            gid = f"ymux_bit_{i}"
            gate_ids.append(gid)
            ch = n + 1
            nodes.append(
                {
                    "id": gid,
                    "kind": "mux2",
                    "label": f"YMUX[{i}]",
                    "subtitle": "0=sum 1=logic",
                    "col": 3.3,
                    "row": i,
                    "package": ref,
                    "pins": {
                        "0": inst["pins"][f"{ch}A"],
                        "1": inst["pins"][f"{ch}B"],
                        "S": inst["pins"]["S"],
                        "Y": inst["pins"][f"{ch}Y"],
                    },
                }
            )
            add_edge(f"net_sum{i}", f"add4_{'lo' if i < 4 else 'hi'}", f"S{i % 4}", gid, "0")
            add_edge(f"net_y_logic{i}", f"mux1_bit_{i}", "Y", gid, "1")
            add_edge("net_y_mux_sel", "port_ymux", "out", gid, "S")
            add_edge(f"net_y{i}", gid, "Y", f"port_y{i}", "in")
        packages.append(
            {
                "id": ref,
                "part": "74HC157",
                "label": ref,
                "gates": gate_ids,
            }
        )

    add_edge("net_c_hi", "add4_hi", "COUT", "port_c_hi", "in")

    dip_count = len(packages)
    assert dip_count == 12, dip_count
    gate_count = sum(1 for n in nodes if n["kind"] not in ("port",))

    return {
        "version": 1,
        "block": "alu8_func",
        "description": DESCRIPTION,
        "dip_count": dip_count,
        "gate_count": gate_count,
        "note": (
            "ALU core = 12 DIP (153×8, 283×2, 157×2). "
            "mux4: data 0..3, select S0/S1 (A/B or force net_153_s*). "
            "mux2: data 0/1, select S. CMP observe only (no 7485)."
        ),
        "nodes": nodes,
        "edges": edges,
        "packages": packages,
        "port_nets": sorted(ports),
    }


def _html_template(graph: dict[str, Any]) -> str:
    payload = json.dumps(graph, ensure_ascii=False, separators=(",", ":"))
    payload = payload.replace("</", "<\\/")
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>ALU8 gate viewer — 12 DIP</title>
<style>
:root {{
  --bg: #0d1117; --panel: #161b22; --border: #30363d; --text: #e6edf3;
  --muted: #8b949e; --accent: #58a6ff; --ctrl: #f0883e; --wire: #6e7681;
  --chip: #21262d; --hi: #3fb950; --sel: #d2a8ff;
}}
* {{ box-sizing: border-box; }}
html, body {{ margin: 0; height: 100%; background: var(--bg); color: var(--text);
  font: 13px/1.4 ui-sans-serif, system-ui, Segoe UI, sans-serif; }}
body {{ display: grid; grid-template-columns: 260px 1fr; }}
#sidebar {{ background: var(--panel); border-right: 1px solid var(--border);
  padding: 12px; overflow: auto; }}
#sidebar h1 {{ font-size: 15px; margin: 0 0 6px; }}
#sidebar .meta {{ color: var(--muted); font-size: 11px; margin-bottom: 12px; white-space: pre-wrap; }}
.btn {{ display: block; width: 100%; text-align: left; margin: 2px 0; padding: 6px 8px;
  background: var(--chip); color: var(--text); border: 1px solid var(--border);
  border-radius: 4px; cursor: pointer; font: inherit; }}
.btn:hover {{ border-color: var(--accent); }}
.btn.active {{ background: #1f3a5f; border-color: var(--accent); }}
.cat {{ margin: 10px 0 4px; font-size: 10px; text-transform: uppercase;
  letter-spacing: .04em; color: var(--muted); }}
#main {{ display: flex; flex-direction: column; min-width: 0; }}
#toolbar {{ padding: 8px 12px; border-bottom: 1px solid var(--border); color: var(--muted);
  display: flex; gap: 10px; flex-wrap: wrap; align-items: center; }}
#toolbar strong {{ color: var(--text); }}
#toolbar button {{ background: var(--chip); color: var(--text); border: 1px solid var(--border);
  border-radius: 4px; padding: 4px 10px; cursor: pointer; }}
#host {{ flex: 1; overflow: auto; background: var(--bg); }}
svg {{ display: block; user-select: none; -webkit-user-select: none; }}
.node {{ cursor: grab; }}
.node.dragging {{ cursor: grabbing; }}
.node-box {{ fill: var(--chip); stroke: var(--border); stroke-width: 1.2; }}
.node-box.port {{ fill: #0d1117; }}
.node-box.control {{ stroke: var(--ctrl); }}
.node-box.hi {{ stroke: var(--hi); stroke-width: 2; }}
.node-box.dim {{ opacity: .25; }}
.mux-body {{ fill: var(--chip); stroke: var(--border); stroke-width: 1.4; }}
.mux-body.hi {{ stroke: var(--hi); stroke-width: 2.2; }}
.mux-body.dim {{ opacity: .25; }}
.pin-label {{ fill: var(--text); font: 10px ui-monospace, Consolas, monospace; pointer-events: none; }}
.pin-label.sel {{ fill: var(--sel); font-weight: 700; }}
.pin-label.data {{ fill: #79c0ff; }}
.pin-dot {{ fill: #c9d1d9; stroke: none; }}
.pin-dot.sel {{ fill: var(--sel); }}
.pin-dot.data {{ fill: #79c0ff; }}
.pin-dot.out {{ fill: #3fb950; }}
.sep {{ stroke: #484f58; stroke-width: 1; stroke-dasharray: 3 3; }}
.node-label {{ fill: var(--text); font: 11px ui-monospace, Consolas, monospace; pointer-events: none; }}
.node-sub {{ fill: var(--muted); font: 9px ui-monospace, Consolas, monospace; pointer-events: none; }}
.wire {{ fill: none; stroke: var(--wire); stroke-width: 1.4; opacity: .85; cursor: pointer; }}
.wire.control {{ stroke: var(--ctrl); }}
.wire.hi {{ stroke: var(--hi); stroke-width: 2.6; opacity: 1; }}
.wire.dim {{ opacity: .08; }}
.legend span {{ margin-right: 12px; }}
.dot {{ display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin-right: 4px; }}
.dot.ctrl {{ background: var(--ctrl); }}
.dot.data {{ background: #79c0ff; }}
.dot.sel {{ background: var(--sel); }}
.dot.hi {{ background: var(--hi); }}
</style>
</head>
<body>
<aside id="sidebar">
  <h1>ALU8 gates</h1>
  <div class="meta" id="meta"></div>
  <button type="button" class="btn active" id="btn-all">All gates</button>
  <div class="cat">Packages (12 DIP)</div>
  <div id="pkg-list"></div>
  <div class="cat">Filter</div>
  <button type="button" class="btn" id="btn-ctrl">Control nets only</button>
  <button type="button" class="btn" id="btn-clear">Clear highlight</button>
</aside>
<main id="main">
  <div id="toolbar">
    <strong id="title">All gates</strong>
    <span id="sel"></span>
    <span class="legend">
      <span><i class="dot data"></i>data 0..n</span>
      <span><i class="dot sel"></i>select S*</span>
      <span><i class="dot ctrl"></i>control</span>
      <span><i class="dot hi"></i>selected</span>
    </span>
    <button type="button" id="zin">Zoom +</button>
    <button type="button" id="zout">Zoom −</button>
    <button type="button" id="zreset">Reset zoom</button>
    <button type="button" id="layout-reset">Reset layout</button>
    <span style="opacity:.75">Drag nodes · click wire/node to highlight</span>
  </div>
  <div id="host"></div>
</main>
<script id="graph-data" type="application/json">{payload}</script>
<script>
(function () {{
  const G = JSON.parse(document.getElementById('graph-data').textContent);
  const host = document.getElementById('host');
  const titleEl = document.getElementById('title');
  const selEl = document.getElementById('sel');
  const meta = document.getElementById('meta');
  meta.textContent = G.dip_count + ' DIP · ' + G.gate_count + ' functional gates\\n' + G.note;

  const COL_X = [60, 420, 980, 1520, 2060];
  const ROW_Y0 = 60;
  const ROW_H = 170;
  const PORT_W = 72;
  const PORT_H = 40;
  const ADD_W = 130;
  const ADD_H = 72;
  const MUX4_W = 112;
  const MUX4_H = 150;
  const MUX2_W = 112;
  const MUX2_H = 100;
  const PAD = 140;
  const DRAG_THRESH = 5;

  function xOf(col) {{
    const c0 = Math.floor(col);
    const f = col - c0;
    const x0 = COL_X[Math.min(c0, COL_X.length - 1)];
    const x1 = COL_X[Math.min(c0 + 1, COL_X.length - 1)];
    return x0 + (x1 - x0) * f;
  }}
  function yOf(row) {{ return ROW_Y0 + row * ROW_H; }}

  function nodeSize(n) {{
    if (n.kind === 'mux4') return {{ w: MUX4_W, h: MUX4_H }};
    if (n.kind === 'mux2') return {{ w: MUX2_W, h: MUX2_H }};
    if (n.kind === 'add4') return {{ w: ADD_W, h: ADD_H }};
    return {{ w: PORT_W, h: PORT_H }};
  }}

  // Local pin offsets inside node (relative to top-left)
  function pinLocal(n, pin) {{
    const {{ w, h }} = nodeSize(n);
    if (n.kind === 'mux4') {{
      const dataY = {{ '0': 28, '1': 52, '2': 76, '3': 100 }};
      if (pin in dataY) return {{ x: 0, y: dataY[pin], side: 'left' }};
      if (pin === 'S0') return {{ x: w * 0.32, y: h, side: 'bottom' }};
      if (pin === 'S1') return {{ x: w * 0.68, y: h, side: 'bottom' }};
      if (pin === 'Y') return {{ x: w, y: h * 0.45, side: 'right' }};
    }}
    if (n.kind === 'mux2') {{
      if (pin === '0') return {{ x: 0, y: 32, side: 'left' }};
      if (pin === '1') return {{ x: 0, y: 58, side: 'left' }};
      if (pin === 'S') return {{ x: w * 0.5, y: h, side: 'bottom' }};
      if (pin === 'Y') return {{ x: w, y: h * 0.42, side: 'right' }};
    }}
    if (n.kind === 'add4') {{
      if (pin === 'CIN') return {{ x: w * 0.5, y: 0, side: 'top' }};
      if (pin === 'COUT') return {{ x: w * 0.5, y: h, side: 'bottom' }};
      if (String(pin).charAt(0) === 'S') return {{ x: w, y: h * 0.5, side: 'right' }};
      return {{ x: 0, y: h * 0.5, side: 'left' }};
    }}
    // port
    if (pin === 'in') return {{ x: 0, y: h * 0.5, side: 'left' }};
    return {{ x: w, y: h * 0.5, side: 'right' }}; // out
  }}

  function pinWorld(nodeId, pin) {{
    const n = byId[nodeId];
    const p = pos[nodeId];
    if (!n || !p) return {{ x: 0, y: 0 }};
    const loc = pinLocal(n, pin || (n.kind === 'port' ? 'out' : 'Y'));
    return {{ x: p.x + loc.x, y: p.y + loc.y, side: loc.side }};
  }}

  const byId = Object.fromEntries(G.nodes.map(n => [n.id, n]));
  const edgeByKey = {{}};
  G.edges.forEach((e, i) => {{ edgeByKey[i] = e; }});
  const pos = {{}};
  const defaultPos = {{}};

  function initLayout() {{
    G.nodes.forEach(n => {{
      const p = {{ x: xOf(n.col), y: yOf(n.row) }};
      defaultPos[n.id] = {{ x: p.x, y: p.y }};
      pos[n.id] = {{ x: p.x, y: p.y }};
    }});
  }}
  initLayout();

  let scale = 1;
  let focusPkg = null;
  let hiNet = null;
  let ctrlOnly = false;
  let drag = null;

  function packageOf(nodeId) {{
    const n = byId[nodeId];
    return n && n.package ? n.package : null;
  }}

  function visibleNode(n) {{
    if (focusPkg && n.package && n.package !== focusPkg) {{
      if (n.kind === 'port') {{
        const touch = G.edges.some(e => {{
          const a = packageOf(e.src) === focusPkg || packageOf(e.dst) === focusPkg;
          return a && (e.src === n.id || e.dst === n.id || e.net === n.net);
        }});
        return touch;
      }}
      return false;
    }}
    if (focusPkg && n.kind !== 'port' && n.package !== focusPkg) return false;
    return true;
  }}

  function visibleEdge(e) {{
    if (ctrlOnly && !e.control) return false;
    if (!focusPkg) return true;
    return packageOf(e.src) === focusPkg || packageOf(e.dst) === focusPkg;
  }}

  function wirePath(e) {{
    const a = pinWorld(e.src, e.src_pin);
    const b = pinWorld(e.dst, e.dst_pin);
    let mx = (a.x + b.x) / 2;
    if (a.side === 'bottom' || a.side === 'top') {{
      const stub = a.side === 'bottom' ? 28 : -28;
      const midY = a.y + stub;
      return 'M' + a.x + ',' + a.y + ' L' + a.x + ',' + midY +
        ' C' + a.x + ',' + midY + ' ' + b.x + ',' + midY + ' ' + b.x + ',' + b.y;
    }}
    if (b.side === 'bottom' || b.side === 'top') {{
      const stub = b.side === 'bottom' ? 28 : -28;
      const midY = b.y + stub;
      return 'M' + a.x + ',' + a.y +
        ' C' + mx + ',' + a.y + ' ' + mx + ',' + midY + ' ' + b.x + ',' + midY +
        ' L' + b.x + ',' + b.y;
    }}
    return 'M' + a.x + ',' + a.y + ' C' + mx + ',' + a.y + ' ' + mx + ',' + b.y + ' ' + b.x + ',' + b.y;
  }}

  function canvasSize(nodes) {{
    let maxX = 400, maxY = 400;
    nodes.forEach(n => {{
      const p = pos[n.id];
      const s = nodeSize(n);
      maxX = Math.max(maxX, p.x + s.w + PAD);
      maxY = Math.max(maxY, p.y + s.h + PAD);
    }});
    return {{ W: Math.max(2300, maxX), H: Math.max(1400, maxY) }};
  }}

  function clientToSvg(svg, clientX, clientY) {{
    const pt = svg.createSVGPoint();
    pt.x = clientX;
    pt.y = clientY;
    const ctm = svg.getScreenCTM();
    if (!ctm) return {{ x: 0, y: 0 }};
    return pt.matrixTransform(ctm.inverse());
  }}

  function muxBodyPath(kind) {{
    // Trapezoid MUX symbol: wide left (data), narrow right (Y)
    if (kind === 'mux4') {{
      const w = MUX4_W, h = MUX4_H;
      return 'M0,8 L' + (w - 18) + ',28 L' + (w - 18) + ',' + (h - 38) +
        ' L0,' + (h - 18) + ' Z';
    }}
    const w = MUX2_W, h = MUX2_H;
    return 'M0,8 L' + (w - 18) + ',24 L' + (w - 18) + ',' + (h - 34) +
      ' L0,' + (h - 18) + ' Z';
  }}

  function renderMuxPins(n) {{
    let html = '';
    const pins = n.kind === 'mux4' ? ['0', '1', '2', '3', 'S0', 'S1', 'Y'] : ['0', '1', 'S', 'Y'];
    pins.forEach(pin => {{
      const loc = pinLocal(n, pin);
      const isSel = pin === 'S' || pin === 'S0' || pin === 'S1';
      const isOut = pin === 'Y';
      const cls = isSel ? 'sel' : (isOut ? 'out' : 'data');
      html += '<circle class="pin-dot ' + cls + '" cx="' + loc.x + '" cy="' + loc.y + '" r="3.5"/>';
      let tx = loc.x, ty = loc.y + 3, anchor = 'start';
      if (loc.side === 'left') {{ tx = 10; anchor = 'start'; }}
      else if (loc.side === 'right') {{ tx = loc.x - 8; anchor = 'end'; }}
      else if (loc.side === 'bottom') {{ ty = loc.y - 8; tx = loc.x; anchor = 'middle'; }}
      html += '<text class="pin-label ' + (isSel ? 'sel' : (isOut ? '' : 'data')) +
        '" x="' + tx + '" y="' + ty + '" text-anchor="' + anchor + '">' + pin + '</text>';
    }});
    // separator between data bank and select bank
    const h = nodeSize(n).h;
    const w = nodeSize(n).w;
    const sepY = n.kind === 'mux4' ? 118 : 78;
    html += '<line class="sep" x1="8" y1="' + sepY + '" x2="' + (w - 28) + '" y2="' + sepY + '"/>';
    html += '<text class="node-sub" x="8" y="14">' + n.label + '</text>';
    if (n.subtitle) html += '<text class="node-sub" x="8" y="' + (h - 6) + '">' + n.subtitle + '</text>';
    return html;
  }}

  function renderNodeInner(n, isHi) {{
    const dim = hiNet && !isHi ? ' dim' : '';
    const hi = isHi ? ' hi' : '';
    if (n.kind === 'mux4' || n.kind === 'mux2') {{
      return '<path class="mux-body' + hi + dim + '" d="' + muxBodyPath(n.kind) + '"/>' +
        renderMuxPins(n);
    }}
    const s = nodeSize(n);
    const cls = 'node-box' + (n.kind === 'port' ? ' port' : '') +
      (n.control ? ' control' : '') + hi + dim;
    let html = '<rect class="' + cls + '" width="' + s.w + '" height="' + s.h + '" rx="6"/>';
    html += '<text class="node-label" x="8" y="20">' + n.label + '</text>';
    if (n.subtitle) html += '<text class="node-sub" x="8" y="36">' + n.subtitle + '</text>';
    return html;
  }}

  function updateWires() {{
    host.querySelectorAll('.wire').forEach(el => {{
      const idx = +el.getAttribute('data-ei');
      const e = G.edges[idx];
      if (e) el.setAttribute('d', wirePath(e));
    }});
    const nodes = G.nodes.filter(visibleNode);
    const {{ W, H }} = canvasSize(nodes);
    const svg = host.querySelector('svg');
    if (svg) {{
      svg.setAttribute('data-base-w', W);
      svg.setAttribute('data-base-h', H);
      svg.setAttribute('viewBox', '0 0 ' + W + ' ' + H);
      applyScale();
    }}
  }}

  function render() {{
    const nodes = G.nodes.filter(visibleNode);
    const edges = G.edges.filter(visibleEdge);
    const {{ W, H }} = canvasSize(nodes);

    let svg = '<svg xmlns="http://www.w3.org/2000/svg" width="' + W + '" height="' + H +
      '" viewBox="0 0 ' + W + ' ' + H +
      '" data-base-w="' + W + '" data-base-h="' + H + '">';
    svg += '<g id="wires">';
    G.edges.forEach((e, ei) => {{
      if (!visibleEdge(e)) return;
      const s = byId[e.src], d = byId[e.dst];
      if (!s || !d || !visibleNode(s) || !visibleNode(d)) return;
      const cls = ['wire', e.control ? 'control' : '',
        (hiNet && e.net === hiNet) ? 'hi' : (hiNet ? 'dim' : '')].filter(Boolean).join(' ');
      svg += '<path class="' + cls + '" data-net="' + e.net + '" data-ei="' + ei +
        '" data-src="' + e.src + '" data-dst="' + e.dst +
        '" d="' + wirePath(e) + '"/>';
    }});
    svg += '</g><g id="nodes">';
    nodes.forEach(n => {{
      const p = pos[n.id];
      const isHi = !!(hiNet && (n.net === hiNet || (n.pins && Object.values(n.pins).includes(hiNet))));
      svg += '<g class="node" data-id="' + n.id + '" transform="translate(' + p.x + ',' + p.y + ')">' +
        renderNodeInner(n, isHi) + '</g>';
    }});
    svg += '</g></svg>';
    host.innerHTML = svg;
    applyScale();
    bindInteractions();
  }}

  function selectNode(id) {{
    const n = byId[id];
    if (!n) return;
    if (n.net) {{
      hiNet = n.net;
      selEl.textContent = 'net: ' + hiNet + ' · ' + id;
    }} else if (n.pins) {{
      const parts = Object.entries(n.pins).map(([k, v]) => k + '=' + v);
      hiNet = n.pins.Y || n.pins['0'] || Object.values(n.pins)[0] || null;
      selEl.textContent = id + ' · ' + parts.join(' · ');
    }}
    render();
  }}

  function bindInteractions() {{
    const svg = host.querySelector('svg');
    host.querySelectorAll('.wire').forEach(el => {{
      el.addEventListener('click', (ev) => {{
        ev.stopPropagation();
        hiNet = el.getAttribute('data-net');
        selEl.textContent = 'net: ' + hiNet;
        render();
      }});
    }});
    host.querySelectorAll('.node').forEach(el => {{
      el.addEventListener('pointerdown', (ev) => {{
        if (ev.button !== 0) return;
        ev.preventDefault();
        ev.stopPropagation();
        const id = el.getAttribute('data-id');
        const p = pos[id];
        const local = clientToSvg(svg, ev.clientX, ev.clientY);
        drag = {{
          id: id,
          el: el,
          startClient: {{ x: ev.clientX, y: ev.clientY }},
          grab: {{ x: local.x - p.x, y: local.y - p.y }},
          moved: false,
        }};
        el.classList.add('dragging');
        el.setPointerCapture(ev.pointerId);
      }});
      el.addEventListener('pointermove', (ev) => {{
        if (!drag || drag.id !== el.getAttribute('data-id')) return;
        const dx = ev.clientX - drag.startClient.x;
        const dy = ev.clientY - drag.startClient.y;
        if (!drag.moved && (Math.abs(dx) > DRAG_THRESH || Math.abs(dy) > DRAG_THRESH)) {{
          drag.moved = true;
        }}
        if (!drag.moved) return;
        const local = clientToSvg(svg, ev.clientX, ev.clientY);
        const nx = Math.max(0, local.x - drag.grab.x);
        const ny = Math.max(0, local.y - drag.grab.y);
        pos[drag.id].x = nx;
        pos[drag.id].y = ny;
        el.setAttribute('transform', 'translate(' + nx + ',' + ny + ')');
        updateWires();
      }});
      el.addEventListener('pointerup', (ev) => {{
        if (!drag || drag.id !== el.getAttribute('data-id')) return;
        const wasDrag = drag.moved;
        const id = drag.id;
        el.classList.remove('dragging');
        try {{ el.releasePointerCapture(ev.pointerId); }} catch (_) {{}}
        drag = null;
        if (!wasDrag) selectNode(id);
        else updateWires();
      }});
      el.addEventListener('pointercancel', () => {{
        if (!drag) return;
        drag.el.classList.remove('dragging');
        drag = null;
      }});
    }});
  }}

  function applyScale() {{
    const svg = host.querySelector('svg');
    if (!svg) return;
    const W = +svg.getAttribute('data-base-w');
    const H = +svg.getAttribute('data-base-h');
    svg.setAttribute('width', Math.round(W * scale));
    svg.setAttribute('height', Math.round(H * scale));
  }}

  const pkgList = document.getElementById('pkg-list');
  G.packages.forEach(p => {{
    const b = document.createElement('button');
    b.type = 'button';
    b.className = 'btn';
    b.textContent = p.label + ' (' + p.part + ')';
    b.onclick = () => {{
      focusPkg = p.id;
      ctrlOnly = false;
      titleEl.textContent = p.label;
      document.querySelectorAll('#sidebar .btn').forEach(x => x.classList.remove('active'));
      b.classList.add('active');
      render();
    }};
    pkgList.appendChild(b);
  }});

  document.getElementById('btn-all').onclick = () => {{
    focusPkg = null; ctrlOnly = false; hiNet = null;
    titleEl.textContent = 'All gates';
    selEl.textContent = '';
    document.querySelectorAll('#sidebar .btn').forEach(x => x.classList.remove('active'));
    document.getElementById('btn-all').classList.add('active');
    render();
  }};
  document.getElementById('btn-ctrl').onclick = () => {{
    ctrlOnly = true; focusPkg = null;
    titleEl.textContent = 'Control nets';
    document.querySelectorAll('#sidebar .btn').forEach(x => x.classList.remove('active'));
    document.getElementById('btn-ctrl').classList.add('active');
    render();
  }};
  document.getElementById('btn-clear').onclick = () => {{
    hiNet = null; selEl.textContent = ''; render();
  }};
  document.getElementById('zin').onclick = () => {{ scale *= 1.15; applyScale(); }};
  document.getElementById('zout').onclick = () => {{ scale /= 1.15; applyScale(); }};
  document.getElementById('zreset').onclick = () => {{ scale = 1; applyScale(); }};
  document.getElementById('layout-reset').onclick = () => {{
    Object.keys(defaultPos).forEach(id => {{
      pos[id].x = defaultPos[id].x;
      pos[id].y = defaultPos[id].y;
    }});
    render();
  }};

  render();
}})();
</script>
</body>
</html>
"""


def write_alu8_viewer_html(path: Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    graph = build_alu8_gate_graph()
    path.write_text(_html_template(graph), encoding="utf-8", newline="\n")
    return path
