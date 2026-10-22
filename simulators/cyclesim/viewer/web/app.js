/* Presentation only. Every ALU result, flag and intermediate signal comes from Python. */
"use strict";
(() => {
  const MODEL = "alu12-v1";
  const $ = (id) => document.getElementById(id);
  const esc = (value) => String(value).replace(/[&<>"']/g, (c) => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
  const hex = (n) => n === null || n === undefined ? "—" : n.toString(16).toUpperCase().padStart(2, "0");
  const bitString = (n, width = 4) => n.toString(2).padStart(width, "0");
  const validInt = (v, max) => Number.isInteger(v) && v >= 0 && v <= max;
  const logic = (v) => ["0", "1", "X", "Z"].includes(v);
  const badge = (v) => `<span class="logic-badge v${esc(v ?? "X")}">${esc(v ?? "—")}</span>`;
  const buses = ["a", "b", "b_add", "logic", "sum", "y"];
  const stages = ["b_add", "logic", "sum", "c_lo", "c_hi", "y"];
  const busNames = {a:"A", b:"B", b_add:"B_ADD", logic:"LOGIC", sum:"SUM", y:"Y"};
  let circuit = null, snapshot = null, selection = null, traceBit = 0, netQuery = "";
  let generation = 0, requestId = 0, lastState = -1, draftValid = true, dirty = false;
  let stale = true, busy = false, queue = [], editTimer = null, reconnecting = false;
  let draft = {a:0, b:0, mode:"preset", operation:"ADD", controls:{cin:0,bctrl:12,lgc:0,y_mux_sel:0}};
  let componentMap = new Map(), netMap = new Map(), busMap = new Map(), positions = new Map();
  let camera = {x:0,y:0,w:1090,h:620}, drag = null, pathStep = -1, detailedPins = false;

  function assert(ok, message) { if (!ok) throw new Error(`모델/스키마 불일치: ${message}`); }
  function controlsValid(c) { return c && validInt(c.cin,1) && validInt(c.bctrl,15) && validInt(c.lgc,15) && validInt(c.y_mux_sel,1); }
  function validateCircuit(c) {
    assert(c && c.model_version === MODEL, "model_version");
    assert(Array.isArray(c.components) && c.components.length === 12, "12개 패키지 필요");
    const ids = new Set();
    for (const p of c.components) {
      assert(typeof p.id === "string" && !ids.has(p.id) && p.pins && typeof p.pins === "object", "패키지 정의");
      ids.add(p.id);
    }
    const expected = [ ...Array.from({length:8}, (_,i) => [`U_ALU_153_${i}`,"74HC153"]), ["U_ALU_283_LO","74HC283"], ["U_ALU_283_HI","74HC283"], ["U_ALU_157_YBP_0","74HC157"], ["U_ALU_157_YBP_1","74HC157"] ];
    for (const [id,part] of expected) assert(c.components.some(p => p.id === id && p.part === part), id);
    assert(Array.isArray(c.nets) && c.nets.length > 0, "넷 정의");
    const nm = new Map(c.nets.map(n => [n.id,n]));
    assert(nm.size === c.nets.length, "중복 넷 ID");
    for (const n of c.nets) {
      assert(typeof n.id === "string" && ["data","control","power"].includes(n.kind) && Array.isArray(n.endpoints), "넷 형식");
      for (const e of n.endpoints) assert(c.components.find(p => p.id === e.component)?.pins[e.pin] === n.id, `연결 ${n.id}`);
    }
    for (const p of c.components) for (const [pin,net] of Object.entries(p.pins)) {
      assert(nm.has(net), `${p.id}.${pin} 넷 누락`);
      assert(nm.get(net).endpoints.some(e => e.component === p.id && e.pin === pin), `${p.id}.${pin} 종단 누락`);
    }
    assert(Array.isArray(c.buses), "버스 정의");
    for (const id of buses) {
      const b = c.buses.find(b => b.id === id);
      assert(b && b.nets?.length === 8 && b.nets.every(n => nm.has(n)), `버스 ${id}`);
    }
    assert(c.presets?.length > 0 && new Set(c.presets.map(p => p.id)).size === c.presets.length, "프리셋");
    for (const p of c.presets) assert(typeof p.id === "string" && controlsValid(p.controls) && typeof p.cpu_policy?.acc_write === "boolean" && Array.isArray(p.cpu_policy?.flags_write), "프리셋 제어");
    assert(Array.isArray(c.boundary), "모델 경계");
    return c;
  }
  function validateSnapshot(s) {
    assert(circuit && s && s.model_version === circuit.model_version, "회로와 관측 버전");
    assert(validInt(s.state_id,Number.MAX_SAFE_INTEGER), "state_id");
    assert(s.inputs && validInt(s.inputs.a,255) && validInt(s.inputs.b,255) && ["preset","direct"].includes(s.inputs.mode) && controlsValid(s.inputs.controls), "입력 관측");
    assert(circuit.presets.some(p => p.id === s.inputs.operation), "연산 ID");
    assert(s.signals && s.components && s.buses, "관측 필드");
    for (const n of circuit.nets) assert(logic(s.signals[n.id]), `신호 ${n.id}`);
    for (const p of circuit.components) {
      const observed = s.components[p.id];
      assert(observed?.pins && typeof observed.active === "boolean", `패키지 ${p.id}`);
      for (const [pin,net] of Object.entries(p.pins)) assert(observed.pins[pin] === s.signals[net], `핀 ${p.id}.${pin}`);
    }
    for (const b of circuit.buses) {
      const v = s.buses[b.id];
      assert(v && /^[01XZ]{8}$/.test(v.bits) && (v.value === null || validInt(v.value,255)), `버스 관측 ${b.id}`);
      assert(v.bits === [...b.nets].reverse().map(n => s.signals[n]).join(""), `버스 비트 ${b.id}`);
      assert(/[XZ]/.test(v.bits) ? v.value === null : v.value !== null, `버스 알려짐 ${b.id}`);
    }
    assert([true,false,null].includes(s.comparison?.match) && s.comparison.expected && s.comparison.actual, "비교 관측");
    for (const stage of stages) assert(validInt(s.comparison.expected[stage],stage.startsWith("c_")?1:255) && (s.comparison.actual[stage] === null || validInt(s.comparison.actual[stage],stage.startsWith("c_")?1:255)), `비교 단계 ${stage}`);
    assert(typeof s.settled === "boolean" && validInt(s.iterations,Number.MAX_SAFE_INTEGER), "안정화 관측");
    assert(Array.isArray(s.diagnostics) && Array.isArray(s.changed_nets) && Array.isArray(s.active_nets), "진단/경로 관측");
    assert([...s.changed_nets,...s.active_nets].every(n => netMap.has(n)), "알 수 없는 경로 넷");
    assert(s.cpu_policy && [true,false,null].includes(s.cpu_policy.acc_write) && Array.isArray(s.cpu_policy.flags_write), "CPU 정책");
    assert(s.comparison_flags && [true,false,null].includes(s.comparison_flags.zero) && [0,1,null].includes(s.comparison_flags.carry_ge), "비교 플래그");
    return s;
  }

  function setStatus(message, kind = "stale") {
    stale = kind !== "live";
    $("gates-view").classList.toggle("stale",stale);
    $("connection-dot").className = `dot ${kind === "live" ? "live" : kind === "error" ? "offline" : ""}`;
    $("connection-text").textContent = kind === "live" ? "모델 연결됨" : kind === "error" ? "연결 / 응답 오류" : "관측 갱신 대기";
    $("status-banner").textContent = message;
    $("status-banner").className = `status-banner ${kind}`;
    $("map-viewport").classList.toggle("stale", stale);
    document.querySelector(".map-readout").classList.toggle("stale",stale);
    $("bus-observations").setAttribute("aria-label", stale ? "이전 관측값, 최신 입력 미반영" : "최신 Python 관측값");
  }
  async function http(path, payload) {
    const abort = new AbortController(), timeout = setTimeout(() => abort.abort(), 6500);
    try {
      const response = await fetch(path, {method:payload ? "POST" : "GET", cache:"no-store", signal:abort.signal, ...(payload ? {headers:{"Content-Type":"application/json"},body:JSON.stringify(payload)} : {})});
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || `HTTP ${response.status}`);
      return result;
    } finally { clearTimeout(timeout); }
  }
  function enqueue(job) { queue.push(job); drain(); }
  async function drain() {
    if (busy) return;
    busy = true;
    while (queue.length) {
      const job = queue.shift();
      if (job.gen !== generation) continue;
      try {
        const result = await http(job.path,job.payload);
        if (job.gen !== generation) continue;
        if (job.kind === "circuit") {
          circuit = validateCircuit(result);
          componentMap = new Map(circuit.components.map(p => [p.id,p]));
          netMap = new Map(circuit.nets.map(n => [n.id,n]));
          busMap = new Map(circuit.buses.map(b => [b.id,b]));
          buildCircuit();
          queue.unshift({path:"/api/snapshot",kind:"initial",gen:generation});
        } else {
          validateSnapshot(result);
          if (job.payload) assert(result.request_id === job.payload.request_id, "request_id 응답 불일치");
          if (result.state_id < lastState) throw new Error("서버 state_id가 이전으로 돌아갔습니다. 다시 연결해 주세요.");
          if (!draftValid || (job.kind === "poll" && dirty)) continue;
          snapshot = result; lastState = result.state_id;
          document.body.dataset.stateId = String(result.state_id);
          if (job.kind === "initial" || job.path === "/api/reset" || (job.kind === "poll" && !dirty && JSON.stringify(draft) !== JSON.stringify(result.inputs))) {
            draft = structuredClone(result.inputs); draftValid = true; clearErrors(); syncInputs();
          }
          if (job.kind === "initial") document.querySelectorAll(".controls input,.controls select,.controls button").forEach(e => e.disabled = false);
          if (job.kind !== "poll") dirty = false;
          renderObservation();
          setStatus(`최신 관측 · 상태 #${result.state_id} · ${result.settled ? "안정화 완료" : "미안정화"} · ${result.changed_nets.length}개 넷 변경`, "live");
        }
      } catch (error) {
        if (job.gen === generation) setStatus(`관측값이 최신이 아닙니다. ${error.name === "AbortError" ? "응답 시간 초과" : error.message} · 다시 연결하거나 입력을 재시도하세요.`, "error");
      }
    }
    busy = false; reconnecting = false;
  }
  function connect() {
    clearTimeout(editTimer); generation++; queue = []; dirty = false; lastState = -1;
    reconnecting = true; draftValid = true; clearErrors();
    document.querySelectorAll(".controls input,.controls select,.controls button").forEach(e => e.disabled = true);
    setStatus("Python 회로 정의와 관측 스키마를 확인하고 있습니다.");
    enqueue({path:"/api/circuit",kind:"circuit",gen:generation});
  }
  function clearErrors() {
    document.querySelectorAll("[aria-invalid=true]").forEach(e => e.removeAttribute("aria-invalid"));
    $("input-error").hidden = true;
  }
  function beginEdit() {
    generation++; dirty = true; queue = []; clearTimeout(editTimer);
    setStatus("입력이 변경되었습니다. Python의 최신 관측을 기다리는 중입니다.");
  }
  function readFields() {
    clearErrors(); let valid = true;
    for (const operand of ["a","b"]) {
      // Decimal and hex fields are kept in sync only after a valid edit.
      for (const kind of ["dec","hex"]) {
        const input = $(`${operand}-${kind}`), raw = input.value.trim();
        const ok = kind === "dec" ? /^\d{1,3}$/.test(raw) && validInt(Number(raw),255) : /^(?:0x)?[\da-f]{1,2}$/i.test(raw);
        if (!ok) { input.setAttribute("aria-invalid","true"); valid = false; }
      }
    }
    if (draft.mode === "direct") for (const key of ["cin","bctrl","lgc","y_mux_sel"]) {
      const raw = $(key).value.trim(), max = ["cin","y_mux_sel"].includes(key) ? 1 : 15;
      if (!/^\d{1,2}$/.test(raw) || !validInt(Number(raw),max)) { $(key).setAttribute("aria-invalid","true"); valid = false; }
      else draft.controls[key] = Number(raw);
    }
    draftValid = valid;
    if (!valid) {
      $("input-error").hidden = false;
      $("input-error").textContent = "입력 범위를 확인하세요: A/B 10진수 0–255 또는 16진수 00–FF, CIN·Y 선택 0–1, BCTRL·LGC 0–15. 이전 관측값은 유지되며 새 입력은 전송되지 않습니다.";
      setStatus("유효하지 않은 입력 · 표시 중인 관측값은 이전 입력의 결과입니다.");
    }
    return valid;
  }
  function submitEdit() {
    if (!circuit || !readFields()) return;
    const gen = generation;
    editTimer = setTimeout(() => {
      if (gen !== generation || !draftValid) return;
      const payload = {...structuredClone(draft),request_id:++requestId};
      enqueue({path:"/api/input",payload,kind:"write",gen});
    },120);
    updateControlSummary();
  }
  function syncOperand(operand) {
    $(`${operand}-dec`).value = String(draft[operand]);
    $(`${operand}-hex`).value = hex(draft[operand]);
    const bits = bitString(draft[operand],8);
    $(`${operand}-bits`).innerHTML = [...bits].map((v,i) => `<button class="bit-toggle" data-operand="${operand}" data-bit="${7-i}" aria-label="${operand.toUpperCase()} 비트 ${7-i}, 값 ${v}" aria-pressed="${v === "1"}"><small>${7-i}</small>${v}</button>`).join("");
  }
  function syncInputs() {
    syncOperand("a"); syncOperand("b");
    $("operation").value = draft.operation;
    for (const key of Object.keys(draft.controls)) if ($(key)) $(key).value = String(draft.controls[key]);
    $("mode-preset").setAttribute("aria-pressed",String(draft.mode === "preset"));
    $("mode-direct").setAttribute("aria-pressed",String(draft.mode === "direct"));
    $("direct-controls").hidden = draft.mode !== "direct";
    $("operation").closest("label").hidden = draft.mode !== "preset";
    updateControlSummary();
  }
  function updateControlSummary() {
    const c = draft.controls;
    $("control-summary").textContent = `CIN ${c.cin} / BCTRL ${bitString(c.bctrl)} / LGC ${bitString(c.lgc)} / Y ${c.y_mux_sel}`;
  }

  function geom(p) {
    if (p.part === "74HC153") return {x:200,y:60 + Number(p.id.split("_").at(-1))*45,w:174,h:37};
    const half = p.id.endsWith("HI") || p.id.endsWith("_1") ? 1 : 0;
    return {x:p.part === "74HC283"?525:825,y:70+half*180,w:132,h:141};
  }
  function pinPoint(p,pin) {
    const g = positions.get(p.id) || geom(p), entries = Object.keys(p.pins);
    if (p.part === "74HC153") {
      if (pin === "A" || pin === "B") return {x:g.x,y:g.y+(pin === "A"?12:27),side:"left"};
      if (pin === "1Y" || pin === "2Y") return {x:g.x+g.w,y:g.y+(pin === "1Y"?12:27),side:"right"};
      const controls = entries.filter(k => !["A","B","1Y","2Y"].includes(k));
      return {x:g.x+10+controls.indexOf(pin)*(g.w-20)/Math.max(1,controls.length-1),y:g.y+g.h,side:"bottom"};
    }
    let left, right, bottom;
    if (p.part === "74HC283") {
      left = entries.filter(k => /^[AB]\d$/.test(k)); right = entries.filter(k => /^S\d$/.test(k)); bottom = entries.filter(k => !left.includes(k) && !right.includes(k));
    } else { left = entries.filter(k => /^[1-4][AB]$/.test(k)); right = entries.filter(k => /^[1-4]Y$/.test(k)); bottom = entries.filter(k => !left.includes(k) && !right.includes(k)); }
    if (left.includes(pin)) return {x:g.x,y:g.y+40+left.indexOf(pin)*12,side:"left"};
    if (right.includes(pin)) return {x:g.x+g.w,y:g.y+47+right.indexOf(pin)*23,side:"right"};
    if (pin === "CIN") return {x:g.x+g.w/2,y:g.y,side:"top"};
    if (pin === "COUT") return {x:g.x+g.w/2,y:g.y+g.h,side:"bottom"};
    return {x:g.x+25+bottom.indexOf(pin)*45,y:g.y+g.h,side:"bottom"};
  }
  function pathBetween(a,b,offset=0) {
    if (a.side === "bottom" && b.side === "top") return `M${a.x} ${a.y} V${(a.y+b.y)/2} H${b.x} V${b.y}`;
    const mid = a.x === b.x ? a.x-25-offset : (a.x+b.x)/2+offset;
    return `M${a.x} ${a.y} H${mid} V${b.y} H${b.x}`;
  }
  function signalClass(net) { return `v${snapshot?.signals[net] || "X"} ${netMap.get(net)?.kind || "data"} ${snapshot?.active_nets.includes(net)?"active":"inactive"}${snapshot?.changed_nets.includes(net)?" changed":""}${selection?.type === "net" && selection.id === net?" selected":""}`; }
  function wire(net,d,label="",labelX=0,labelY=0) {
    return `<g data-net="${esc(net)}" tabindex="0" role="button" aria-label="넷 ${esc(net)}, 값 ${esc(snapshot?.signals[net] ?? "미관측")}"><path class="wire ${signalClass(net)}" d="${d}"/><path class="wire-hit" d="${d}"/>${label?`<text class="wire-label" x="${labelX}" y="${labelY}">${esc(label)}</text>`:""}</g>`;
  }
  function buildCircuit() {
    $("model-version").textContent = circuit.model_version;
    $("operation").innerHTML = circuit.presets.map(p => `<option value="${esc(p.id)}">${esc(p.label)} · ${esc(p.id)}</option>`).join("");
    $("boundary-notes").innerHTML = circuit.boundary.map(b => `<p><strong>${esc(b.label)}</strong> ${esc(b.description)}</p>`).join("");
    positions = new Map(circuit.components.map(p => [p.id,geom(p)]));
    $("map-loading").hidden = true;
    renderMap(); fitAll();
    window.SwiverViews.init(circuit, id => choose("net",id), bit => {traceBit=bit;renderMap();});
  }
  function renderMap() {
    if (!circuit) return;
    const focused = document.activeElement;
    const focusData = focused?.closest("#map-scene") ? {...focused.dataset} : null;
    const chosenNets = new Set(buses.map(id => busMap.get(id)?.nets[traceBit]).filter(Boolean));
    let drawing = `<text class="stage-title" x="55" y="27">01 / 입력</text><text class="stage-title" x="200" y="27">02 / 비트별 진리표</text><text class="stage-title" x="525" y="27">03 / 8비트 가산</text><text class="stage-title" x="825" y="27">04 / 출력 선택</text><text class="stage-subtitle" x="200" y="44">A_bit + 2 × B_bit → C0…C3</text><text class="stage-subtitle" x="525" y="44">LO → C_LO → HI</text><text class="stage-subtitle" x="825" y="44">SUM / LOGIC → Y</text>`;
    const busShapes = {
      a:{d:"M80 52 V426 M80 52 H485 V360",x:43,y:448},
      b:{d:"M125 52 V426",x:101,y:448},
      b_add:{d:"M414 87 V426 M414 153 H490 M414 333 H490",x:386,y:448},
      logic:{d:"M394 72 V466 H786 V153 M786 333 H810",x:664,y:448},
      sum:{d:"M696 117 V400 M696 153 H807 M696 333 H807",x:665,y:419},
      y:{d:"M998 117 V400 M960 153 H998 M960 333 H998",x:969,y:419}
    };
    for (const id of buses) {
      const b = busShapes[id], value = snapshot?.buses[id]?.value;
      const active = busMap.get(id).nets.some(n => snapshot?.active_nets.includes(n));
      drawing += `<g data-bus="${id}" role="button" tabindex="0" aria-label="버스 ${busNames[id]}"><path d="${b.d}" class="bus-line ${active?"active":"inactive"} ${id === "logic"?"logic":""} ${selection?.type === "bus" && selection.id === id?"selected":""}"/><path d="${b.d}" class="bus-hit"/><rect x="${b.x-5}" y="${b.y-15}" width="89" height="32" rx="5" class="bus-label-box"/><text x="${b.x}" y="${b.y-2}" class="bus-label">${busNames[id]} [7:0]</text><text x="${b.x}" y="${b.y+11}" class="bus-value-label">${value === undefined?"—":value === null?"X / Z":`0x${hex(value)}`}</text></g>`;
    }
    // The carry link is an actual exported net, independent of the selected Y path.
    for (const net of ["net_cin","net_c_lo","net_c_hi"]) {
      const n = netMap.get(net); if (!n) continue;
      const ends = n.endpoints.map(e => pinPoint(componentMap.get(e.component),e.pin));
      if (net === "net_c_lo" && ends.length === 2) drawing += wire(net,pathBetween(ends[0],ends[1]),`C_LO · ${snapshot?.signals[net] ?? "—"}`,601,235);
      else if (ends[0]) {
        const e = ends[0], targetY = net === "net_cin"?53:438;
        drawing += wire(net,`M${e.x} ${e.y} V${targetY}`,`${net === "net_cin"?"CIN":"C_HI"} · ${snapshot?.signals[net] ?? "—"}`,e.x+9,targetY+4);
      }
    }
    // Folded bundles meet every real package. Individual selected nets expand below.
    for (const p of circuit.components) {
      const g = positions.get(p.id);
      if (p.part === "74HC153") {
        drawing += `<path class="wire" d="M80 ${g.y+12} H${g.x} M125 ${g.y+27} H${g.x} M${g.x+g.w} ${g.y+12} H394 M${g.x+g.w} ${g.y+27} H414"/>`;
      } else if (p.part === "74HC283") drawing += `<path class="bus-line" d="M485 ${g.y+71} H525 M490 ${g.y+109} H525 M657 ${g.y+91} H696"/>`;
      else drawing += `<path class="bus-line" d="M807 ${g.y+71} H825 M786 ${g.y+109} H825 M957 ${g.y+91} H998"/>`;
    }
    if ($("fanout").checked) for (const id of chosenNets) drawing += expandedNet(id);
    if (selection?.type === "net" && (!$("fanout").checked || !chosenNets.has(selection.id)) && !["net_cin","net_c_lo","net_c_hi"].includes(selection.id)) drawing += expandedNet(selection.id);
    for (const p of circuit.components) {
      const g = positions.get(p.id), selected = selection?.type === "component" && selection.id === p.id;
      const related = selection?.type === "net" && Object.values(p.pins).includes(selection.id);
      const bit = p.part === "74HC153"?Number(p.id.split("_").at(-1)):null;
      const half = p.id.endsWith("HI") || p.id.endsWith("_1") ? "4–7" : "0–3";
      drawing += `<g class="chip ${selected?"selected":""} ${related?"related":""}" data-component="${esc(p.id)}" tabindex="0" role="button" aria-label="${esc(p.id)} ${p.part}"><rect class="chip-body" x="${g.x}" y="${g.y}" width="${g.w}" height="${g.h}" rx="6"/><text x="${g.x+10}" y="${g.y+18}" class="chip-title">${p.part}</text><text x="${g.x+10}" y="${g.y+(bit !== null?31:34)}" class="chip-sub">${bit !== null?"1Y: LOGIC · 2Y: B_ADD":p.part === "74HC283"?"A + B_ADD + CIN":"S=0 SUM · S=1 LOGIC"}</text><text class="chip-bit" text-anchor="end" x="${g.x+g.w-8}" y="${g.y+18}">${bit !== null?`b${bit}`:half}</text>`;
      for (const [pin,net] of Object.entries(p.pins)) {
        const point = pinPoint(p,pin), show = point.side !== "bottom" || selected || (selection?.type === "net" && selection.id === net);
        if (!show) continue;
        drawing += `<g data-pin="${esc(pin)}" data-pin-component="${esc(p.id)}" role="button" tabindex="0" aria-label="${esc(p.id)} 핀 ${esc(pin)} 넷 ${esc(net)}"><title>${esc(pin)} → ${esc(net)} = ${esc(snapshot?.signals[net] ?? "미관측")}</title><circle class="pin-marker ${chosenNets.has(net) || (selection?.type === "net" && selection.id === net)?"selected":""}" cx="${point.x}" cy="${point.y}" r="2.5"/>`;
        if (selected || camera.w < 650) drawing += `<text class="pin-label" x="${point.x+(point.side === "right"?-6:point.side === "left"?6:0)}" y="${point.y-4}" text-anchor="${point.side === "right"?"end":point.side === "left"?"start":"middle"}">${esc(pin)}</text>`;
        drawing += `</g>`;
      }
      drawing += `</g>`;
    }
    drawing += `<rect class="boundary-box" x="200" y="483" width="800" height="25" rx="5"/><text class="boundary-label" x="213" y="499">외부 제어: CIN · BCTRL[3:0] · LGC[3:0] · Y_MUX_SEL / Enable → GND / 비교 프로브는 12개 칩 외부</text>`;
    $("map-scene").innerHTML = drawing;
    renderTracePicker();
    if (focusData) {
      let selector = focusData.pin ? `[data-pin="${CSS.escape(focusData.pin)}"][data-pin-component="${CSS.escape(focusData.pinComponent)}"]` : focusData.component ? `[data-component="${CSS.escape(focusData.component)}"]` : focusData.net ? `[data-net="${CSS.escape(focusData.net)}"]` : focusData.bus ? `[data-bus="${CSS.escape(focusData.bus)}"]` : null;
      if (selector) $("map-scene").querySelector(selector)?.focus({preventScroll:true});
    }
  }
  function expandedNet(id) {
    const n = netMap.get(id); if (!n) return "";
    const endpoints = n.endpoints.map(e => ({...pinPoint(componentMap.get(e.component),e.pin),component:e.component,pin:e.pin}));
    let source = endpoints.find(e => e.side === "right") || endpoints[0];
    if (id.startsWith("net_a") && /^net_a\d$/.test(id)) source = {x:80,y:72+traceBit*45,side:"right"};
    else if (/^net_b\d$/.test(id)) source = {x:125,y:87+traceBit*45,side:"right"};
    if (!source) return "";
    let result = "";
    for (const point of endpoints) if (point !== source) result += wire(id,pathBetween(source,point,point.component?.includes("283")?24:0));
    if (/^net_y\d$/.test(id)) result += wire(id,pathBetween(source,{x:998,y:source.y,side:"left"}));
    if (!result) result = wire(id,`M${source.x-24} ${source.y} H${source.x}`);
    return result;
  }
  function renderTracePicker() {
    $("trace-bits").innerHTML = Array.from({length:8},(_,i) => `<button class="trace-bit" data-trace="${i}" aria-pressed="${i === traceBit}" aria-label="비트 ${i} 추적">${i}</button>`).join("");
  }
  function cameraUpdate() {
    $("circuit-map").setAttribute("viewBox",`${camera.x} ${camera.y} ${camera.w} ${camera.h}`);
    $("zoom-label").textContent = `${Math.round(1090/camera.w*100)}%`;
    if (detailedPins !== (camera.w < 650)) { detailedPins = camera.w < 650; renderMap(); }
  }
  function fitAll() { camera = {x:20,y:0,w:1030,h:523}; cameraUpdate(); }
  function fitSelection() {
    if (!selection || !circuit) { fitAll(); return; }
    let rects = [];
    if (selection.type === "component") rects = [positions.get(selection.id)];
    else if (selection.type === "net") rects = netMap.get(selection.id).endpoints.map(e => positions.get(e.component));
    else if (selection.type === "bus") rects = busMap.get(selection.id).nets.flatMap(n => netMap.get(n).endpoints.map(e => positions.get(e.component)));
    rects = rects.filter(Boolean); if (!rects.length) { fitAll(); return; }
    const x = Math.min(...rects.map(r => r.x))-45, y = Math.min(...rects.map(r => r.y))-40;
    const w = Math.max(...rects.map(r => r.x+r.w))-x+45, h = Math.max(...rects.map(r => r.y+r.h))-y+40;
    const ratio = $("map-viewport").clientWidth/$("map-viewport").clientHeight;
    camera = {x:x-(Math.max(w,h*ratio)-w)/2,y:y-(Math.max(h,w/ratio)-h)/2,w:Math.max(w,h*ratio),h:Math.max(h,w/ratio)};
    cameraUpdate();
  }
  function zoom(factor,cx=.5,cy=.5) {
    const w = Math.max(180,Math.min(2600,camera.w*factor)), ratio = w/camera.w;
    camera = {x:camera.x+camera.w*cx*(1-ratio),y:camera.y+camera.h*cy*(1-ratio),w,h:camera.h*ratio}; cameraUpdate();
  }

  function choose(type,id,pin=null) {
    selection = {type,id,pin};
    $("inspector-body").hidden = false;
    document.querySelector(".inspector").classList.remove("collapsed");
    $("toggle-inspector").setAttribute("aria-expanded","true");
    $("toggle-inspector").textContent = "접기";
    if (type === "net") for (const b of circuit.buses) { const index = b.nets.indexOf(id); if (index >= 0) traceBit = index; }
    if (type === "component" && id.startsWith("U_ALU_153_")) traceBit = Number(id.split("_").at(-1));
    renderMap(); renderInspector(); renderBuses();
    window.SwiverViews.select(type,id);
  }
  function renderInspector(preserve = false) {
    const body = $("inspector-body"), scroll = body.scrollTop;
    const focused = body.contains(document.activeElement) ? document.activeElement : null;
    const focusData = focused ? {id:focused.id,...focused.dataset} : null;
    const start = focused?.selectionStart, end = focused?.selectionEnd;
    renderInspectorContent();
    if (!preserve) { body.scrollTop = 0; return; }
    body.scrollTop = scroll;
    let target = null;
    if (focusData?.id) target = document.getElementById(focusData.id);
    else if (focusData?.inspectNet) target = body.querySelector(`[data-inspect-net="${CSS.escape(focusData.inspectNet)}"]`);
    else if (focusData?.inspectComponent) target = body.querySelector(`[data-inspect-component="${CSS.escape(focusData.inspectComponent)}"][data-select-pin="${CSS.escape(focusData.selectPin)}"]`);
    if (target) { target.focus({preventScroll:true}); if (typeof start === "number" && target.setSelectionRange) target.setSelectionRange(start,end); }
    body.scrollTop = scroll;
  }
  function renderInspectorContent() {
    if (!circuit) return;
    const body = $("inspector-body");
    if (!selection) {
      body.innerHTML = `<div class="empty-state"><span>⌖</span><h3>신호를 자세히 들여다보세요</h3><p>칩과 버스를 클릭하거나, 아래에서 넷을 찾아보세요.</p></div><label class="inspector-subhead" for="net-search">넷 찾기</label><input class="net-search" id="net-search" placeholder="예: c_lo, bctrl, gnd"><div id="net-results" class="net-results"></div>`;
      $("net-search").value = netQuery;
      renderNetSearch(netQuery); return;
    }
    if (selection.type === "component") {
      const p = componentMap.get(selection.id), observed = snapshot?.components[p.id];
      const selectedPin = selection.pin ? `<p class="detail-note">선택 핀 <strong>${esc(selection.pin)}</strong> → ${esc(p.pins[selection.pin])}</p>` : "";
      body.innerHTML = `<h3 class="inspector-title">${esc(p.part)}</h3><div class="inspector-id">${esc(p.id)}</div><span class="tag">기능 핀</span><span class="tag">${observed?.active?"활성 관측":"패키지"}</span>${selectedPin}<p class="detail-note">${esc(observed?.detail || "관측 대기")}</p>${renderInternal(p,observed)}<h3 class="inspector-subhead">전체 기능 핀과 넷</h3><table class="pin-table"><thead><tr><th>핀</th><th>연결 넷</th><th>값</th></tr></thead><tbody>${Object.entries(p.pins).map(([pin,n]) => `<tr><td>${esc(pin)}</td><td><button data-inspect-net="${esc(n)}">${esc(n)}</button></td><td>${badge(snapshot?.signals[n])}</td></tr>`).join("")}</tbody></table><p class="inspector-subhead">정의 출처</p><p class="inspector-id">${esc(typeof p.source === "string"?p.source:JSON.stringify(p.source))}</p>`;
    } else if (selection.type === "net") {
      const n = netMap.get(selection.id);
      body.innerHTML = `<h3 class="inspector-title">넷 연결</h3><div class="inspector-id">${esc(n.id)}</div>${badge(snapshot?.signals[n.id])}<span class="tag">${esc(n.kind)}</span><span class="tag">${snapshot?.changed_nets.includes(n.id)?"변경됨":"유지"}</span><p class="detail-note">실제 정의의 ${n.endpoints.length}개 패키지 종단. 외부 입력과 비교 프로브는 패키지 종단 목록에 포함되지 않을 수 있습니다.</p><h3 class="inspector-subhead">연결된 기능 핀</h3>${n.endpoints.map(e => `<button class="net-link" data-inspect-component="${esc(e.component)}" data-select-pin="${esc(e.pin)}">${esc(e.component)}<br>↳ ${esc(e.pin)} ${badge(snapshot?.signals[n.id])}</button>`).join("") || "<p class='detail-note'>패키지 종단이 없는 외부 / 관측 넷입니다.</p>"}`;
    } else {
      const b = busMap.get(selection.id), v = snapshot?.buses[b.id];
      body.innerHTML = `<h3 class="inspector-title">${busNames[b.id]} [7:0]</h3><div class="inspector-id">${esc(b.label)}</div><p class="detail-note">${v?.value ?? "—"} / 0x${hex(v?.value)}<br><span class="mono">${v?.bits ?? "XXXXXXXX"}</span><br>아래는 LSB → MSB 순서입니다.</p><table class="pin-table"><thead><tr><th>비트</th><th>넷</th><th>값</th></tr></thead><tbody>${b.nets.map((n,i) => `<tr><td>${i}</td><td><button data-inspect-net="${esc(n)}">${esc(n)}</button></td><td>${badge(snapshot?.signals[n])}</td></tr>`).join("")}</tbody></table>`;
    }
  }
  function renderInternal(p,observed) {
    if (!observed) return "";
    const pins = observed.pins;
    if (p.part === "74HC153") {
      // Highlight the observed address; channel outputs remain Python observations.
      const address = `${pins.B}${pins.A}`, addresses = ["00","01","10","11"];
      return `<section class="internal-view"><h3>두 개의 4:1 MUX</h3><p>주소 [B,A] = <strong class="mono">${esc(address)}</strong><br>1번 채널 → LOGIC · 2번 채널 → B_ADD</p><table class="pin-table"><thead><tr><th>주소</th><th>1번 입력</th><th>2번 입력</th></tr></thead><tbody>${addresses.map((bits,i) => `<tr class="${bits === address?"address-selected":""}"><td>${bits === address?"→ ":""}C${i} · ${bits}</td><td>${badge(pins[`1C${i}`])}</td><td>${badge(pins[`2C${i}`])}</td></tr>`).join("")}</tbody></table><p>관측 출력: 1Y ${badge(pins["1Y"])} · 2Y ${badge(pins["2Y"])}<br>Enable: 1G ${badge(pins["1G"])} · 2G ${badge(pins["2G"])} · LOW 활성</p></section>`;
    }
    if (p.part === "74HC283") {
      const nibble = prefix => [3,2,1,0].map(i => pins[`${prefix}${i}`]).join("");
      return `<section class="internal-view"><h3>4비트 가산기 · ${p.id.endsWith("LO")?"하위 [3:0]":"상위 [7:4]"}</h3><p class="mono">A ${esc(nibble("A"))} · B_ADD ${esc(nibble("B"))}<br>SUM ${esc(nibble("S"))}</p><p>CIN ${badge(pins.CIN)} → 가산기 → COUT ${badge(pins.COUT)}</p><p>${p.id.endsWith("LO")?"COUT은 net_c_lo로 상위 283의 CIN에 연결됩니다.":"COUT은 net_c_hi입니다. Y의 논리 경로 선택과 별개인 물리 캐리입니다."}</p></section>`;
    }
    const branch = pins.S === "0" ? "A · SUM" : pins.S === "1" ? "B · LOGIC" : "미확정";
    return `<section class="internal-view"><h3>네 개의 2:1 MUX</h3><p>S ${badge(pins.S)} → <strong>${branch}</strong> 선택<br>G ${badge(pins.G)} · LOW 활성</p><table class="pin-table"><thead><tr><th>채널</th><th>SUM · A</th><th>LOGIC · B</th><th>Y</th></tr></thead><tbody>${[1,2,3,4].map(i => `<tr><td>${i}</td><td>${badge(pins[`${i}A`])}</td><td>${badge(pins[`${i}B`])}</td><td>${badge(pins[`${i}Y`])}</td></tr>`).join("")}</tbody></table></section>`;
  }
  function renderNetSearch(query) {
    if (!$("net-results")) return;
    const found = circuit.nets.filter(n => n.id.toLowerCase().includes(query.toLowerCase()));
    $("net-results").innerHTML = found.slice(0,30).map(n => `<button class="net-link" data-inspect-net="${esc(n.id)}">${badge(snapshot?.signals[n.id])} ${esc(n.id)}</button>`).join("") + (found.length>30?`<p class="muted">${found.length}개 중 30개 · 검색어로 좁히세요</p>`:"");
  }
  function renderBuses() {
    $("bus-observations").innerHTML = buses.map(id => {
      const v = snapshot?.buses[id];
      return `<button data-observe-bus="${id}" class="bus-card ${id === "y"?"output":""} ${selection?.type === "bus" && selection.id === id?"selected":""}" aria-label="${busNames[id]} 버스 검사"><span class="bus-name">${busNames[id]}${id === "y"?" / OUTPUT":""}</span><span class="bus-value">${v?.value ?? "—"}</span><span class="bus-hex">0x${hex(v?.value)}</span><span class="bus-binary">${v?.bits ?? "XXXXXXXX"}</span></button>`;
    }).join("");
  }
  function renderObservation() {
    window.SwiverViews.update(snapshot);
    renderMap(); renderInspector(true); renderBuses();
    $("live-y").textContent = `Y ${snapshot.buses.y.value ?? "X / Z"} · 0x${hex(snapshot.buses.y.value)}`;
    $("live-carries").textContent = `C_LO ${snapshot.signals.net_c_lo} · C_HI ${snapshot.signals.net_c_hi} · Z ${snapshot.comparison_flags.zero === null?"X":snapshot.comparison_flags.zero?1:0}`;
    $("live-policy").textContent = `ACC ${snapshot.cpu_policy.acc_write === null?"정책 없음":snapshot.cpu_policy.acc_write?"쓰기":"유지"}`;
    $("settle-info").textContent = `#${snapshot.state_id} · ${snapshot.settled?"안정화":"미안정화"} · ${snapshot.iterations} passes`;
    const c = snapshot.comparison;
    $("comparison-status").textContent = c.match === true?"✓ 독립 기준과 일치":c.match === false?`불일치 · ${c.first_mismatch || "단계 확인"}`:"비교 불확정 · X / Z 확인";
    $("comparison-status").className = `comparison-status ${c.match === false?"mismatch":""}`;
    $("flag-info").textContent = `Z ${snapshot.comparison_flags.zero === null?"X":snapshot.comparison_flags.zero?"1":"0"} · 물리 C_HI ${snapshot.comparison_flags.carry_ge ?? "X"}`;
    const policy = snapshot.cpu_policy;
    $("cpu-policy").textContent = `CPU: ACC ${policy.acc_write === null?"정책 없음":policy.acc_write?"쓰기":"유지"} · 플래그 ${policy.flags_write.length?policy.flags_write.join(", ")+" 쓰기":"쓰기 없음"}`;
    const comparisonOpen = $("comparison-detail").querySelector("details")?.open;
    const comparisonFocused = $("comparison-detail").querySelector("summary") === document.activeElement;
    $("comparison-detail").innerHTML = `<details ${comparisonOpen?"open":""}><summary>단계별 독립 기준 / 실제값</summary><table><thead><tr><th>단계</th>${stages.map(s => `<th>${s.toUpperCase()}</th>`).join("")}</tr></thead><tbody><tr><th>기준</th>${stages.map(s => `<td>${esc(c.expected[s])}</td>`).join("")}</tr><tr><th>실제</th>${stages.map(s => `<td>${c.actual[s] ?? "X / Z"}</td>`).join("")}</tr></tbody></table></details>`;
    if (comparisonFocused) $("comparison-detail").querySelector("summary").focus({preventScroll:true});
    $("diagnostics").innerHTML = snapshot.diagnostics.map(d => `<p><strong>${esc(d.code)}</strong> · ${esc(d.message)} ${d.nets.map(n => `<button data-diagnostic-net="${esc(n)}">${esc(n)}</button>`).join(" ")}</p>`).join("");
    const ctrl = snapshot.inputs.controls, operation = snapshot.inputs.operation;
    const mode = snapshot.inputs.mode === "direct" ? "직접 제어" : operation;
    $("path-explanation").innerHTML = `<p><span class="step-number">1</span><strong>${esc(mode)}</strong> · 153의 비트 ${traceBit}는 A=${esc(snapshot.signals[busMap.get("a").nets[traceBit]])}, B=${esc(snapshot.signals[busMap.get("b").nets[traceBit]])}로 진리표 입력을 선택합니다.</p><p><span class="step-number">2</span>B_ADD → 하위 283 → C_LO=${esc(snapshot.signals.net_c_lo)} → 상위 283. SUM=${snapshot.buses.sum.value ?? "X / Z"}입니다.</p><p><span class="step-number">3</span>157의 S=${ctrl.y_mux_sel} → <strong>${ctrl.y_mux_sel?"LOGIC":"SUM"}</strong> 경로 → Y=${snapshot.buses.y.value ?? "X / Z"}. ${policy.acc_write === null?"직접 제어에는 CPU 쓰기 정책이 없습니다.":policy.acc_write?"CPU 정책: ACC 쓰기.":"CPU 정책: ACC 유지."}</p>`;
    $("observation-time").textContent = `마지막 관측 ${new Date().toLocaleTimeString("ko-KR")} · 상태 #${snapshot.state_id}`;
  }

  for (const operand of ["a","b"]) for (const kind of ["dec","hex"]) $(`${operand}-${kind}`).addEventListener("input",(event) => {
    beginEdit(); const raw = event.target.value.trim();
    const valid = kind === "dec" ? /^\d{1,3}$/.test(raw) && validInt(Number(raw),255) : /^(?:0x)?[\da-f]{1,2}$/i.test(raw);
    if (valid) { draft[operand] = parseInt(raw.replace(/^0x/i,""),kind === "hex"?16:10); const text = raw; syncOperand(operand); event.target.value = text; }
    submitEdit();
  });
  for (const id of ["cin","bctrl","lgc","y_mux_sel"]) $(id).addEventListener("input",() => {beginEdit();submitEdit();});
  $("operation").addEventListener("change",() => {
    beginEdit(); draft.operation = $("operation").value;
    draft.controls = structuredClone(circuit.presets.find(p => p.id === draft.operation).controls);
    for (const key of Object.keys(draft.controls)) $(key).value = String(draft.controls[key]);
    submitEdit();
  });
  for (const mode of ["preset","direct"]) $(`mode-${mode}`).addEventListener("click",() => {
    if (!circuit) return; beginEdit(); draft.mode = mode;
    if (mode === "preset") draft.controls = structuredClone(circuit.presets.find(p => p.id === draft.operation)?.controls || circuit.presets[0].controls);
    // Preserve invalid operand text across mode edits; it must not be silently accepted.
    $("mode-preset").setAttribute("aria-pressed",String(mode === "preset")); $("mode-direct").setAttribute("aria-pressed",String(mode === "direct"));
    $("direct-controls").hidden = mode !== "direct"; $("operation").closest("label").hidden = mode !== "preset";
    if (mode === "preset") for (const key of Object.keys(draft.controls)) $(key).value = String(draft.controls[key]);
    submitEdit();
  });
  document.addEventListener("click",(event) => {
    const button = event.target.closest("button"); if (!button) return;
    if (button.dataset.operand) {
      beginEdit(); const operand = button.dataset.operand, bit = Number(button.dataset.bit);
      // Input editing only; this never evaluates any ALU stage.
      draft[operand] = draft[operand] ^ (1 << bit); syncOperand(operand); submitEdit();
    } else if (button.dataset.trace !== undefined) {
      traceBit = Number(button.dataset.trace); renderMap(); if (snapshot) renderObservation();
    } else if (button.dataset.inspectNet) choose("net",button.dataset.inspectNet);
    else if (button.dataset.diagnosticNet && netMap.has(button.dataset.diagnosticNet)) choose("net",button.dataset.diagnosticNet);
    else if (button.dataset.inspectComponent) choose("component",button.dataset.inspectComponent,button.dataset.selectPin);
    else if (button.dataset.observeBus) choose("bus",button.dataset.observeBus);
    else if (button.dataset.example && circuit) {
      const example = {zero:{a:0,b:0,op:"ADD"},carry:{a:255,b:1,op:"ADD"},nibble:{a:15,b:1,op:"ADD"},sub:{a:3,b:5,op:"SUB"},cmp:{a:5,b:5,op:"CMP"},borrow:{a:3,b:5,op:"CMP"},logic:{a:170,b:85,op:"XOR"}}[button.dataset.example];
      const preset = circuit.presets.find(p => p.id.toUpperCase() === example.op) || (example.op === "CMP" ? circuit.presets.find(p => p.id.toUpperCase() === "SUB") : null);
      if (!preset) { setStatus(`이 모델에는 ${example.op} 예제 프리셋이 없습니다.`); return; }
      beginEdit(); draft = {a:example.a,b:example.b,mode:"preset",operation:preset.id,controls:structuredClone(preset.controls)};
      syncInputs(); submitEdit();
    }
  });
  $("inspector-body").addEventListener("input",event => {if (event.target.id === "net-search") {netQuery = event.target.value;renderNetSearch(netQuery);}});
  function selectMapTarget(target) {
    const pin = target.closest("[data-pin]");
    if (pin) choose("net",componentMap.get(pin.dataset.pinComponent).pins[pin.dataset.pin]);
    else if (target.closest("[data-component]")) choose("component",target.closest("[data-component]").dataset.component);
    else if (target.closest("[data-net]")) choose("net",target.closest("[data-net]").dataset.net);
    else if (target.closest("[data-bus]")) choose("bus",target.closest("[data-bus]").dataset.bus);
  }
  $("circuit-map").addEventListener("keydown",event => {if (["Enter"," "].includes(event.key)) {event.preventDefault();selectMapTarget(event.target);}});
  $("map-viewport").addEventListener("pointerdown",event => {
    if (event.button !== 0) return;
    drag = {x:event.clientX,y:event.clientY,camera:{...camera},target:event.target,moved:false};
    $("map-viewport").setPointerCapture(event.pointerId);
  });
  $("map-viewport").addEventListener("pointermove",event => {
    if (!drag) return; const dx = event.clientX-drag.x,dy = event.clientY-drag.y;
    if (Math.abs(dx)+Math.abs(dy)>4) drag.moved = true;
    if (!drag.moved) return;
    const svg = $("circuit-map"), ratio = Math.min(svg.clientWidth/drag.camera.w,svg.clientHeight/drag.camera.h);
    camera = {...drag.camera,x:drag.camera.x-dx/ratio,y:drag.camera.y-dy/ratio}; cameraUpdate(); $("map-viewport").classList.add("dragging");
  });
  $("map-viewport").addEventListener("pointerup",event => {
    if (drag && !drag.moved) selectMapTarget(drag.target);
    drag = null; $("map-viewport").classList.remove("dragging");
    if ($("map-viewport").hasPointerCapture(event.pointerId)) $("map-viewport").releasePointerCapture(event.pointerId);
  });
  $("map-viewport").addEventListener("pointercancel",() => {drag = null; $("map-viewport").classList.remove("dragging");});
  $("map-viewport").addEventListener("wheel",event => {event.preventDefault(); const r = $("map-viewport").getBoundingClientRect();zoom(event.deltaY>0?1.13:.885,(event.clientX-r.left)/r.width,(event.clientY-r.top)/r.height);},{passive:false});
  $("zoom-in").addEventListener("click",() => zoom(.8)); $("zoom-out").addEventListener("click",() => zoom(1.25));
  $("fit").addEventListener("click",fitAll); $("fit-selection").addEventListener("click",fitSelection);
  $("fanout").addEventListener("change",renderMap);
  $("clear-selection").addEventListener("click",() => {selection = null;renderMap();renderInspector();renderBuses();});
  $("toggle-inspector").addEventListener("click",() => {
    const collapsed = document.querySelector(".inspector").classList.toggle("collapsed");
    $("inspector-body").hidden = collapsed;
    $("toggle-inspector").setAttribute("aria-expanded",String(!collapsed));
    $("toggle-inspector").textContent = collapsed ? "펼치기" : "접기";
  });
  function followPath(delta) {
    if (!circuit) return;
    pathStep = (pathStep+delta+6)%6;
    const half = traceBit<4?"LO":"HI", muxHalf = traceBit<4?0:1;
    const steps = [["bus","a","입력 A/B 확인"],["component",`U_ALU_153_${traceBit}`,"153 진리표 선택"],["bus","b_add","B_ADD 변환 관측"],["component",`U_ALU_283_${half}`,"283 가산과 캐리"],["component",`U_ALU_157_YBP_${muxHalf}`,"157 출력 경로 선택"],["bus","y","Y 출력 관측"]];
    const step = steps[pathStep]; choose(step[0],step[1]);
    $("path-step").textContent = `${pathStep+1} / 6 · ${step[2]}`;
  }
  $("path-prev").addEventListener("click",() => followPath(-1));
  $("path-next").addEventListener("click",() => followPath(1));
  $("path-clear").addEventListener("click",() => {pathStep=-1;$("path-step").textContent="단계를 선택하세요";selection=null;renderMap();renderInspector();renderBuses();});
  $("reconnect").addEventListener("click",() => {if (!reconnecting) connect();});
  $("reset").addEventListener("click",() => {
    if (!circuit) return; beginEdit(); draftValid = true; clearErrors();
    enqueue({path:"/api/reset",kind:"reset",gen:generation,payload:{request_id:++requestId}});
  });
  setInterval(() => {
    if (busy || queue.length || reconnecting || !circuit) return;
    // Even invalid drafts are probed for disconnects, but never replaced with old state.
    enqueue({path:"/api/snapshot",kind:"poll",gen:generation});
  },3000);
  document.querySelector(".example-gallery").append($("reset"));
  // Observe asset/server revisions without evaluating any circuit state.
  let revision = null;
  setInterval(async () => {
    try {
      const r = await fetch('/api/revision', {cache:'no-store',signal:AbortSignal.timeout(2500)});
      if (!r.ok) return;
      const next = (await r.json()).revision;
      if (revision && revision !== next) location.reload();
      revision = next;
    } catch (_) { /* The main session polling reports connection failures. */ }
  }, 1500);
  syncInputs(); renderTracePicker(); renderBuses(); cameraUpdate(); connect();
})();
