/* Read-only topology. All pins, nets, counts and fit resources come from Python. */
"use strict";
window.SwiverCpu = (() => {
  const $ = id => document.getElementById(id);
  const esc = value => String(value).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const short = id => id.replace('U_ALU_', '').replace('157_YBP_', '157_');
  const kindLabel = {data:'데이터', address:'주소', control:'제어', power:'전원·상수', jtag:'JTAG'};
  let data, chips = new Map(), nets = new Map(), buses = new Map(), positions = new Map();
  let selection = {kind:'bus', id:'DB'}, started = false, sequence = 0, pending;
  let box = [0, 0, 1328, 800], drag;
  const zones = [
    ['control', '01  실행 제어', 16, 16, 390, 310],
    ['address', '02  주소 · PC · 페이지', 422, 16, 500, 310],
    ['memory', '03  통합 메모리', 938, 16, 374, 310],
    ['alu', '04  외부 ALU · 12칩', 16, 394, 650, 390],
    ['accumulator', '05  누산기 · 쓰기 경로', 682, 394, 302, 390],
    ['decode', '06  메모리 디코드', 1000, 394, 312, 390],
  ];
  const button = (kind, id, label, cls='') => `<button class="${cls}" data-cpu-kind="${kind}" data-cpu-id="${esc(id)}">${label}</button>`;
  const validSelection = () => selection && ({chip:chips, net:nets, bus:buses}[selection.kind]?.has(selection.id));
  function selectedNets() {
    if (!validSelection()) return [];
    if (selection.kind === 'net') return [nets.get(selection.id)];
    if (selection.kind === 'bus') return buses.get(selection.id).nets.map(id => nets.get(id));
    return [];
  }
  function related() {
    const result = new Set(selectedNets().flatMap(n => n.endpoints.map(e => e.component)));
    if (selection?.kind === 'chip') result.add(selection.id);
    return result;
  }
  function setBox(next) {
    box = next;
    $('cpu-map').setAttribute('viewBox', box.join(' '));
  }
  function fit(ids) {
    const coords = ids?.map(id => positions.get(id)).filter(Boolean);
    if (!coords?.length) return setBox([0, 0, 1328, 800]);
    const x = Math.min(...coords.map(p => p.x))-30, y = Math.min(...coords.map(p => p.y))-35;
    const r = Math.max(...coords.map(p => p.x+p.w))+30, b = Math.max(...coords.map(p => p.y+p.h))+35;
    setBox([x, y, Math.max(320, r-x), Math.max(190, b-y)]);
  }
  function zoom(factor) {
    const [x,y,w,h] = box;
    if (w*factor < 200 || w*factor > 4000) return;
    setBox([x+w*(1-factor)/2, y+h*(1-factor)/2, w*factor, h*factor]);
  }
  function positionComponents() {
    positions = new Map();
    const place = (c,x,y,w=138,h=72) => positions.set(c.id,{x,y,w,h});
    const group = name => data.components.filter(c => c.group === name);
    for (const c of group('control')) {
      if (c.fit) place(c,36,80,190,100);
      else place(c,242,c.id==='IR'?80:166,144,72);
    }
    const addr = group('address');
    for (const c of addr) {
      if (c.fit) place(c,442,80,194,100);
      else if (c.id.startsWith('PC_DRIVER')) place(c,442+Number(c.id.slice(-1))*230,246,214,54);
      else if (c.id.startsWith('PAGE')) place(c,654,80+Number(c.id.slice(-1))*84,244,72);
      else { const i=Number(c.id.slice(-1)); place(c,654+(i%2)*126,80+Math.floor(i/2)*84,116,72); }
    }
    group('memory').forEach((c,i) => place(c,958,80+i*74,334,64));
    group('alu').forEach((c,i) => place(c,36+(i%4)*154,454+Math.floor(i/4)*94,138,76));
    for (const c of group('accumulator')) {
      if (c.id==='AC') place(c,702,454,262,72);
      else if (c.id.startsWith('WRITEBACK')) place(c,702+Number(c.id.slice(-1))*136,546,126,72);
      else place(c,c.id==='AC_DRIVER'?702:838,638,126,72);
    }
    group('decode').forEach((c,i) => place(c,1020,454+i*62,272,54));
  }
  function renderMap() {
    if (!data) return;
    const focus = document.activeElement?.closest('#cpu-scene [data-cpu-kind]')?.dataset.cpuId;
    const linked = related(), chosen = selectedNets();
    let svg = zones.map(([id,title,x,y,w,h]) => {
      const count = data.components.filter(c => c.group===id).length;
      const note = count ? `${count} IC` : 'CPLD 내부';
      return `<rect class="cpu-zone" x="${x}" y="${y}" width="${w}" height="${h}" rx="10"/><text class="cpu-zone-label" x="${x+20}" y="${y+30}">${esc(title)}</text><text class="cpu-zone-note" x="${x+20}" y="${y+h-14}">${note}</text>`;
    }).join('');
    // One displayed branch per participating package. A bus explicitly bundles
    // several distinct nets; a selected single net is one electrical connection.
    if (chosen.length) {
      const ps = [...linked].map(id => positions.get(id));
      const trunk = 360;
      const anchors = ps.map(p => ({x:p.x+p.w/2,y:p.y<330?p.y+p.h:p.y}));
      const cls = `cpu-wire${selection.kind==='bus'?' bus':''}${chosen[0].kind==='power'?' power':''}`;
      if (anchors.length>1) svg += `<path class="${cls}" d="M${Math.min(...anchors.map(p=>p.x))} ${trunk} H${Math.max(...anchors.map(p=>p.x))}"/>`;
      for (const p of anchors) svg += `<path class="${cls}" d="M${p.x} ${p.y} V${trunk}"/><circle class="cpu-wire-dot" cx="${p.x}" cy="${p.y}" r="4"/>`;
    }
    svg += data.components.map(c => {
      const p = positions.get(c.id), selected = selection?.kind==='chip'&&selection.id===c.id;
      const cls = `cpu-chip${linked.has(c.id)?' cpu-linked':''}${selected?' cpu-selected':''}${linked.size&&!linked.has(c.id)?' cpu-muted':''}`;
      const label = short(c.id), part = c.part.replace('AS-10JU44','');
      const hasRole = p.h >= 72;
      return `<g class="${cls}" data-cpu-kind="chip" data-cpu-id="${esc(c.id)}" tabindex="0" role="button" aria-label="${esc(c.id+' '+c.part+' '+c.role)}" aria-pressed="${selected}"><title>${esc(c.id+' · '+c.part+' · '+c.role)}</title><rect x="${p.x}" y="${p.y}" width="${p.w}" height="${p.h}"/><text class="cpu-chip-label" x="${p.x+10}" y="${p.y+23}">${esc(label)}</text><text class="cpu-chip-part" x="${p.x+10}" y="${p.y+43}">${esc(part)}</text>${hasRole?`<text class="cpu-chip-role" x="${p.x+10}" y="${p.y+62}">${esc(c.role.replace('DB / ALU → AC 선택','쓰기 선택'))}</text>`:''}</g>`;
    }).join('');
    $('cpu-scene').innerHTML = svg;
    if (focus) $('cpu-scene').querySelector(`[data-cpu-id="${CSS.escape(focus)}"]`)?.focus({preventScroll:true});
    const name = selection?.kind==='bus' ? buses.get(selection.id)?.label : short(selection?.id || '');
    $('cpu-map-caption').textContent = !selection ? '칩 또는 신호를 선택하세요.' : selection.kind==='chip' ? `${name} · 핀표에서 신호를 선택하세요` : `${name} · ${linked.size}칩 연결${selection.kind==='bus'?' · 버스 묶음':''}`;
  }
  function renderList() {
    if (!data) return;
    const query = $('cpu-search').value.trim().toLowerCase(), filter = $('cpu-filter').value;
    const entries = [];
    if (['all','chips'].includes(filter)) for (const c of data.components) {
      if (`${c.id} ${c.part} ${c.role}`.toLowerCase().includes(query)) entries.push(['chip',c.id,short(c.id),c.part]);
    }
    if (filter!=='chips') for (const n of data.nets) {
      if ((filter==='all'||filter===n.kind) && n.id.toLowerCase().includes(query)) entries.push(['net',n.id,n.id,`${n.endpoints.length}단자`]);
    }
    const scroll = $('cpu-results').scrollTop;
    $('cpu-results').innerHTML = entries.map(([kind,id,label,meta]) => `<button class="cpu-result" data-cpu-kind="${kind}" data-cpu-id="${esc(id)}" aria-pressed="${selection?.kind===kind&&selection?.id===id}"><span>${esc(label)}</span><small>${esc(meta)}</small></button>`).join('') || '<p class="cpu-empty">일치하는 칩이나 신호가 없습니다.</p>';
    $('cpu-results').scrollTop = scroll;
    $('cpu-search-count').textContent = `${entries.length}개`;
  }
  function renderDetail() {
    if (!validSelection()) { $('cpu-detail').innerHTML='<p class="cpu-empty">칩을 누르면 핀표가, 신호를 누르면 연결된 단자가 나옵니다.</p>'; return; }
    let html = '';
    if (selection.kind==='chip') {
      const c=chips.get(selection.id);
      html=`<h3>${esc(short(c.id))}</h3><p class="cpu-detail-meta">${esc(c.part)}<br>${esc(c.role)} · ${Object.keys(c.pins).length} 기능 핀</p><p class="cpu-pin-note">${c.fit?'번호: 저장된 vendor fit의 PLCC44 신호 핀. 전원 번호는 미표시.':'기능 핀명입니다. 실제 패키지 핀 번호는 이 연결표에 없습니다.'}</p><div class="cpu-detail-scroll"><table class="cpu-pin-table"><thead><tr><th>기능 핀</th><th>번호</th><th>연결 신호</th></tr></thead><tbody>`;
      for (const [pin,net] of Object.entries(c.pins)) html+=`<tr data-cpu-pin="${esc(pin)}"><td>${esc(pin)}</td><td class="cpu-pad">${c.signal_pads[pin]??'—'}</td><td>${net===null?'NC':button('net',net,esc(net))}</td></tr>`;
      html+='</tbody></table></div>';
    } else if (selection.kind==='net') {
      const n=nets.get(selection.id), count=new Set(n.endpoints.map(e=>e.component)).size;
      html=`<h3>${esc(n.id)}</h3><p class="cpu-detail-meta">${kindLabel[n.kind]} · ${count}칩 · ${n.endpoints.length}단자<br>${n.inter_ic?'IC 간 신호 집계에 포함':'전원·단일 칩 연결: IC 간 신호 집계에서 제외'}</p><div class="cpu-detail-scroll"><table class="cpu-pin-table"><thead><tr><th>칩</th><th>기능 핀</th><th>번호</th></tr></thead><tbody>`;
      for (const e of n.endpoints) html+=`<tr data-cpu-endpoint="${esc(e.component+'.'+e.pin)}"><td>${button('chip',e.component,esc(short(e.component)))}</td><td>${esc(e.pin)}</td><td class="cpu-pad">${e.pad??'—'}</td></tr>`;
      html+='</tbody></table></div><p class="cpu-pin-note">번호는 CPLD 신호 핀에만 표시합니다. 같은 칩의 여러 단자도 각각 연결해야 합니다.</p>';
    } else {
      const bus=buses.get(selection.id), members=selectedNets(), count=members.reduce((n,b)=>n+b.endpoints.length,0);
      html=`<h3>${esc(bus.label)}</h3><p class="cpu-detail-meta">${members.length}개의 독립 신호 · ${related().size}칩 · ${count}단자<br>비트를 선택하면 정확한 핀 연결을 보여줍니다.</p><div class="cpu-bit-list">${bus.nets.map(n=>button('net',n,esc(n))).join('')}</div><div class="cpu-detail-scroll cpu-chip-list">`;
      for (const id of related()) { const ends=members.flatMap(n=>n.endpoints).filter(e=>e.component===id); html+=button('chip',id,`${esc(short(id))}<small>${ends.length}단자</small>`); }
      html+='</div>';
    }
    $('cpu-detail').innerHTML=html;
  }
  function select(kind,id) {
    selection = kind ? {kind,id} : null;
    if (selection&&!validSelection()) selection=null;
    $('cpu-buses').querySelectorAll('button').forEach(b=>b.setAttribute('aria-pressed',String(selection?.kind==='bus'&&selection.id===b.dataset.cpuId)));
    renderMap(); renderList(); renderDetail();
  }
  function render() {
    const m=data.metrics;
    $('cpu-stats').innerHTML = [
      ['전체 칩',data.total_ic,`74 × ${data.logic_74} + CPLD × 2 + 메모리 × 3`],
      ['IC 간 신호',m.inter_ic_signal_nets,'전원·상수·단일 칩 신호 제외'],
      ['신호 연결 단자',m.signal_pin_endpoints,'칩의 기능 핀 기준'],
      ['최소 연결 수',m.minimum_point_to_point_links,'단자 − 넷 · 실제 점퍼 수 아님'],
    ].map(([label,n,note])=>`<div class="cpu-stat"><span>${label}</span><strong>${n}</strong><small>${note}</small></div>`).join('');
    $('cpu-description').textContent=data.description;
    $('cpu-download').href=`/api/cpu/netlist?variant=${data.variant}`;
    $('cpu-download').download=`swiver-cpu-${data.variant}-netlist.json`;
    $('cpu-buses').innerHTML=data.buses.map(b=>`<button data-cpu-kind="bus" data-cpu-id="${esc(b.id)}" aria-pressed="false">${esc(b.label)}</button>`).join('');
    $('cpu-fits').innerHTML=data.components.filter(c=>c.fit).map(c=>`<div class="cpu-fit-card">${button('chip',c.id,esc(c.id)+' ↗')}<p>저장된 Design fits · JTAG ${esc(c.fit.jtag)}<br><strong>MC ${c.fit.macrocells} / ${c.fit.macrocells_available}</strong></p><meter min="0" max="64" value="${c.fit.macrocells}" aria-label="${esc(c.id)} 매크로셀 사용량"></meter><p>일반 I/O <strong>${c.fit.general_io_excluding_jtag} / 28</strong> · 전용 입력 <strong>${c.fit.dedicated_inputs} / 4</strong></p></div>`).join('');
    $('cpu-parts').innerHTML=Object.entries(data.part_totals).map(([p,n])=>`<div class="cpu-parts-row"><span>${esc(p)}</span><strong>× ${n}</strong></div>`).join('');
    $('cpu-boundaries').innerHTML=[data.boundary,data.pin_boundary,data.count_boundary,data.excluded,'현재 v1.0 규격과 별도로 비교 중인 RAM ISA 구성입니다. 선은 논리 연결이며 실제 빵판 배치나 타이밍 검증을 의미하지 않습니다.'].map(t=>`<p>${esc(t)}</p>`).join('');
    positionComponents();
    if (!validSelection()) selection={kind:'bus',id:'DB'};
    select(selection.kind,selection.id);fit();
  }
  async function load(variant) {
    const token=++sequence;
    pending?.abort();pending=new AbortController();
    const controller=pending;
    let timedOut=false;
    const timer=setTimeout(()=>{timedOut=true;controller.abort();},10000);
    $('cpu-content').hidden=true;$('cpu-retry').hidden=true;
    $('cpu-message').className='cpu-message';$('cpu-message').textContent=`${variant}칩 연결표를 불러옵니다…`;
    const url=new URL(location.href);url.searchParams.set('variant',variant);history.replaceState(null,'',url);
    try {
      const response=await fetch(`/api/cpu/circuit?variant=${variant}`,{signal:controller.signal});
      const next=await response.json();
      if (!response.ok) throw new Error(next.error||'연결표 요청에 실패했습니다.');
      if (token!==sequence) return;
      if (next.schema!=='swiver-cpu-viewer-v1'||next.variant!==variant) throw new Error('연결표 버전이 올바르지 않습니다.');
      data=next;chips=new Map(data.components.map(c=>[c.id,c]));nets=new Map(data.nets.map(n=>[n.id,n]));buses=new Map(data.buses.map(b=>[b.id,b]));
      render();$('cpu-content').hidden=false;
      $('cpu-message').textContent=`${data.title} · ${data.boundary}`;
    } catch (error) {
      if (token!==sequence) return;
      $('cpu-message').className='cpu-message cpu-error';
      $('cpu-message').textContent=timedOut?'연결표 응답 시간이 초과되었습니다. 다시 불러와 주세요.':`연결표를 표시하지 못했습니다. ${error.message}`;
      $('cpu-retry').hidden=false;
    } finally { clearTimeout(timer); }
  }
  function open() {
    if (started) return;
    started=true;
    const requested=new URLSearchParams(location.search).get('variant');
    $('cpu-variant').value=['24','29','35'].includes(requested)?requested:'35';
    load($('cpu-variant').value);
  }
  $('cpu-variant').addEventListener('change',e=>load(e.target.value));
  $('cpu-retry').addEventListener('click',()=>load($('cpu-variant').value));
  $('cpu-search').addEventListener('input',renderList);
  $('cpu-filter').addEventListener('change',renderList);
  $('cpu-clear').addEventListener('click',()=>select(null));
  $('cpu-fit').addEventListener('click',()=>fit());
  $('cpu-focus').addEventListener('click',()=>fit([...related()]));
  $('cpu-zoom-in').addEventListener('click',()=>zoom(.8));
  $('cpu-zoom-out').addEventListener('click',()=>zoom(1.25));
  $('cpu-view').addEventListener('click',e=>{const t=e.target.closest('[data-cpu-kind]');if(t)select(t.dataset.cpuKind,t.dataset.cpuId);});
  $('cpu-view').addEventListener('keydown',e=>{
    if (e.key==='Escape') select(null);
    const target=e.target.closest('g[data-cpu-kind]');
    if (target&&['Enter',' '].includes(e.key)) {e.preventDefault();select(target.dataset.cpuKind,target.dataset.cpuId);}
  });
  const map=$('cpu-map');
  map.addEventListener('keydown',e=>{
    if (e.target!==map) return;
    const moves={ArrowLeft:[-40,0],ArrowRight:[40,0],ArrowUp:[0,-40],ArrowDown:[0,40]};
    if (moves[e.key]) {e.preventDefault();const [dx,dy]=moves[e.key];setBox([box[0]+dx,box[1]+dy,box[2],box[3]]);}
    if (['+','=','-','Home'].includes(e.key)) {e.preventDefault();if(e.key==='Home')fit();else zoom(e.key==='-'?1.25:.8);}
  });
  map.addEventListener('wheel',e=>{if(e.ctrlKey||e.metaKey){e.preventDefault();zoom(e.deltaY>0?1.1:1/1.1);}},{passive:false});
  map.addEventListener('pointerdown',e=>{
    if(e.button!==0||e.target.closest('[data-cpu-kind]'))return;
    const inverse=map.getScreenCTM().inverse(), p=new DOMPoint(e.clientX,e.clientY).matrixTransform(inverse);
    drag={x:p.x,y:p.y,box:[...box],inverse};map.setPointerCapture(e.pointerId);map.classList.add('cpu-dragging');
  });
  map.addEventListener('pointermove',e=>{
    if(!drag)return;const p=new DOMPoint(e.clientX,e.clientY).matrixTransform(drag.inverse);
    setBox([drag.box[0]+drag.x-p.x,drag.box[1]+drag.y-p.y,drag.box[2],drag.box[3]]);
  });
  const endDrag=()=>{drag=null;map.classList.remove('cpu-dragging');};
  map.addEventListener('pointerup',endDrag);map.addEventListener('pointercancel',endDrag);map.addEventListener('lostpointercapture',endDrag);
  return {open};
})();
