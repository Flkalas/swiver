"use strict";
window.SwiverPlacement = (() => {
  const $=id=>document.getElementById(id);
  const esc=v=>String(v).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const short=id=>id.replace('U_ALU_','').replace('157_YBP_','157_');
  const defaults={board_count:5,topology:'compact221',gap_mm:0,stagger_mm:55,orientation:'0',row_gap:2,edge_rows:0,iterations:400,seed:830,priority:'balanced',grouping:'compact221',rail_split:true};
  let circuit=null,result=null,candidate=null,locks=[],customBoards=[],onNet,selectedNet='net_c_lo',selectedChip=null;
  let generation=0,requestId=0,busy=false,drag=null,camera=null,dirty=false;
  const numeric=['board_count','gap_mm','stagger_mm','row_gap','edge_rows','iterations','seed'];
  function status(text,error=false){$('placement-status').textContent=text;$('placement-status').classList.toggle('error',error);}
  function readSettings(){
    const s={};
    for(const key of Object.keys(defaults)) s[key]=key==='rail_split'?$('place-'+key).checked:numeric.includes(key)?Number($('place-'+key).value):$('place-'+key).value;
    for(const key of numeric)if($('place-'+key).value.trim()===''||!Number.isFinite(s[key]))throw new Error('탐색 설정에 유효한 숫자를 입력하세요.');
    return {...s,locks:structuredClone(locks),custom_boards:structuredClone(customBoards)};
  }
  function writeSettings(s){
    for(const key of Object.keys(defaults))if(key==='rail_split')$('place-'+key).checked=s[key];else $('place-'+key).value=String(s[key]??defaults[key]);
    locks=structuredClone(s.locks||[]);customBoards=structuredClone(s.custom_boards||[]);lockSummary();
  }
  function lockSummary(){$('placement-locks').textContent=locks.length?`${locks.length}개 칩 고정: ${locks.map(p=>short(p.id)).join(', ')}`:'고정한 칩 없음 · 칩을 선택해 위치를 편집하거나 고정하세요.';}
  function invalidate(){generation++;dirty=true;if(candidate)status('설정 변경됨 — 현재 그림은 이전 결과입니다. 다시 탐색하세요.');}
  async function api(path,payload){
    const id=++requestId, response=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({...payload,request_id:id}),signal:AbortSignal.timeout(30000)});
    const data=await response.json();if(!response.ok)throw new Error(data.error||`HTTP ${response.status}`);
    if(data.request_id!==id||data.version!=='bb830-search-v1')throw new Error('배치 응답 버전/요청 번호 불일치');
    return data;
  }
  function setBusy(value){busy=value;for(const id of ['placement-search','placement-apply-chip','placement-apply-boards'])$(id).disabled=value;}
  async function run(){
    if(!circuit||busy)return;
    const gen=++generation;
    try{
      const settings=readSettings();setBusy(true);status('배치 탐색 중… 보드와 칩의 겹침을 검사하고 신호 배선 길이를 비교합니다.');
      const data=await api('/api/placement/search',{settings});if(gen!==generation)return;
      result=data;writeSettings(data.settings);dirty=false;
      selectCandidate(data.candidates[0]);renderCandidates();
      status(`${data.statistics.evaluated}개 배치 평가 · 제약 위반 ${data.statistics.rejected}회 제외 · ${data.statistics.wall_seconds.toFixed(2)}초${data.statistics.bounded_early?' · 시간 상한에 도달하여 중단':''}`);
      $('placement-assumptions').textContent=data.profile.notes.join(' ');
      $('placement-limits').innerHTML=data.limitations.map(x=>`<li>${esc(x)}</li>`).join('');
    }catch(error){if(gen===generation)status(`탐색 실패: ${error.message}`,true);}finally{setBusy(false);}
  }
  function renderCandidates(){
    if(!result)return;
    const bestLength=Math.min(...result.candidates.map(c=>c.metrics.estimated_mm)),bestRead=Math.min(...result.candidates.map(c=>c.metrics.readability_penalty));
    $('placement-candidates').innerHTML=result.candidates.map((c,i)=>`<button data-candidate="${c.id}" class="placement-candidate ${candidate?.id===c.id?'chosen':''}" aria-pressed="${candidate?.id===c.id}"><span class="candidate-rank">${i+1}</span><div><strong>${esc(c.label)}</strong><small>${c.boards[0].rotation}° · ${c.boards.length}장 ${c.metrics.estimated_mm===bestLength?'· 짧은 안':''} ${c.metrics.readability_penalty===bestRead?'· 정돈된 안':''}</small></div><div><b>${(c.metrics.estimated_mm/1000).toFixed(2)} m</b><small>가독성 벌점 ${c.metrics.readability_penalty} · 보드 간 ${c.metrics.interboard}</small></div></button>`).join('');
  }
  function selectCandidate(c){candidate=c;selectedChip=null;renderCandidates();renderMetrics();renderMap();fit();renderInspector();renderBoardEditor();}
  function renderMetrics(){
    if(!candidate)return;
    const c=candidate;
    $('placement-metrics').innerHTML=`<span>칩 간 예상 <b>${(c.metrics.estimated_mm/1000).toFixed(2)} m</b></span><span>경로 후보 합 <b>${(c.routed_mm/1000).toFixed(2)} m</b></span><span>보드 간 <b>${c.metrics.interboard}</b></span><span>교차 지점 <b>${c.crossings}</b></span><span>가독성 벌점 <b>${c.metrics.readability_penalty}</b></span>`;
    $('placement-route-status').textContent=c.routing_diagnostics.length?`미해결 경로 ${c.routing_diagnostics.length}개: ${c.routing_diagnostics.join(' / ')}`:`${c.wires.length}개 신호 점퍼 경로 후보 · 칩 몸체 회피 확인 · 전원/외부 배선 제외`;
    $('placement-route-status').classList.toggle('error',!!c.routing_diagnostics.length);
    $('placement-cluster-note').textContent=c.cluster?`B1·B2: 153 4개씩 → B3·B4: 283 1개씩 → B5: 157 2개. 가산기 몸체 사이 ${c.cluster.adder_body_gap_mm.toFixed(2)} mm · 출력 MUX 사이 ${c.cluster.output_body_gap_mm.toFixed(2)} mm (모델 치수).`:'칩을 선택해 위치를 편집하거나 고정할 수 있습니다.';
    $('placement-fit-cluster').disabled=!c.cluster;
    $('placement-export').disabled=false;$('placement-csv').disabled=false;
  }
  function transform(b){const [x,y,r]=[b.x,b.y,b.rotation];return r===90?`translate(${x+165} ${y}) rotate(90)`:r===180?`translate(${x+55} ${y+165}) rotate(180)`:r===270?`translate(${x} ${y+55}) rotate(270)`:`translate(${x} ${y})`;}
  function boardDrawing(b){
    const p=result.profile;let s=`<g transform="${transform(b)}"><rect class="bb-body" width="55" height="165" rx="2"/><rect class="bb-trench" x="25.4" y="1" width="4.2" height="163"/><text class="bb-name" x="27.5" y="-3" text-anchor="middle">B${b.id+1} · 830</text>`;
    for(let row=1;row<=63;row++)for(const [col,x] of Object.entries(p.columns))s+=`<circle class="bb-hole" cx="${x}" cy="${p.row_origin_mm+(row-1)*p.pitch_mm}" r=".48"/>`;
    for(let rail=0;rail<4;rail++){
      const x=p.rail_x_mm[rail],color=rail%2===0?'#cc6452':'#5281a7';
      s+=`<path stroke="${color}" stroke-width=".4" fill="none" d="M${x-1} 8 V${result.settings.rail_split?80:158}${result.settings.rail_split?` M${x-1} 86 V158`:''}"/>`;
      for(const y of p.rail_y_mm)s+=`<circle class="bb-hole" cx="${x}" cy="${y}" r=".48"/>`;
    }
    for(let row=1;row<=63;row++)if(row===1||row%5===0)s+=`<text class="bb-row" x="10.5" y="${p.row_origin_mm+(row-1)*p.pitch_mm+.7}" text-anchor="end">${row}</text>`;
    for(const [col,x] of Object.entries(p.columns))s+=`<text class="bb-row" x="${x}" y="2" text-anchor="middle">${col}</text>`;
    for(const pos of candidate.placements.filter(c=>c.board===b.id)){
      const y=p.row_origin_mm+(pos.row-1)*p.pitch_mm-1.27,center=y+10.16,locked=locks.some(l=>l.id===pos.id);
      s+=`<g class="bb-chip ${pos.id===selectedChip?'selected':''}" data-place-chip="${esc(pos.id)}" role="button" tabindex="0" aria-label="${esc(short(pos.id))}, B${b.id+1}, ${pos.row}행"><title>${esc(pos.id)} · B${b.id+1} · ${pos.row}–${pos.row+7}행 · ${pos.rotation}°${locked?' · 고정':''}</title><rect x="24.325" y="${y}" width="6.35" height="20.32" rx=".7"/><path class="bb-notch" d="M26 ${pos.rotation===0?y:y+20.32} a1.5 1.5 0 0 ${pos.rotation===0?0:1} 3 0"/><text transform="translate(27.5 ${center}) rotate(90)" text-anchor="middle">${esc(short(pos.id))}${locked?' ●':''}</text></g>`;
    }
    return s+'</g>';
  }
  function renderMap(){
    if(!candidate)return;
    let s=candidate.boards.map(boardDrawing).join('');
    const all=$('placement-all-wires').checked;
    for(const wire of candidate.wires){
      const selected=wire.net===selectedNet;if(!all&&!selected)continue;
      s+=`<g data-place-net="${esc(wire.net)}" class="bb-wire ${selected?'selected':''} ${wire.kind}" role="button" tabindex="0" aria-label="${esc(wire.net)} ${esc(wire.from.hole)}에서 ${esc(wire.to.hole)}"><title>${esc(wire.net)} · ${esc(wire.from.hole)} → ${esc(wire.to.hole)} · ${wire.length_mm} mm</title><polyline points="${wire.path.map(p=>p.join(',')).join(' ')}"/><polyline class="bb-wire-hit" points="${wire.path.map(p=>p.join(',')).join(' ')}"/></g>`;
      if(selected)for(const endpoint of [wire.from,wire.to]){
        const pin=candidate.contacts.find(p=>p.component===endpoint.component&&p.pin===endpoint.pin);
        s+=`<line class="bb-strip" x1="${pin.xy[0]}" y1="${pin.xy[1]}" x2="${endpoint.xy[0]}" y2="${endpoint.xy[1]}"/><circle class="bb-end" cx="${endpoint.xy[0]}" cy="${endpoint.xy[1]}" r="1.05"/><text class="bb-end-label" x="${endpoint.xy[0]+1.5}" y="${endpoint.xy[1]-1.5}">${esc(endpoint.hole)}</text>`;
      }
    }
    $('placement-scene').innerHTML=s;
    if(camera)updateCamera();
  }
  function bounds(){
    const a=candidate.boards.map(b=>[b.x,b.y,b.x+(b.rotation%180?165:55),b.y+(b.rotation%180?55:165)]);
    return {x:Math.min(...a.map(r=>r[0]))-8,y:Math.min(...a.map(r=>r[1]))-10,w:Math.max(...a.map(r=>r[2]))-Math.min(...a.map(r=>r[0]))+16,h:Math.max(...a.map(r=>r[3]))-Math.min(...a.map(r=>r[1]))+18};
  }
  function fit(){if(!candidate)return;camera=bounds();updateCamera();}
  function updateCamera(){$('placement-map').setAttribute('viewBox',`${camera.x} ${camera.y} ${camera.w} ${camera.h}`);}
  function zoom(f){if(!camera)return;const w=Math.max(20,Math.min(10000,camera.w*f)),ratio=w/camera.w;camera={x:camera.x+(camera.w-w)/2,y:camera.y+(camera.h-camera.h*ratio)/2,w,h:camera.h*ratio};updateCamera();}
  function renderInspector(){
    if(!candidate)return;
    $('placement-chip-picker').innerHTML='<option value="">칩 선택</option>'+candidate.placements.map(p=>`<option value="${esc(p.id)}">${short(p.id)} · B${p.board+1} · ${p.row}행</option>`).join('');
    $('placement-chip-picker').value=selectedChip||'';
    const p=candidate.placements.find(p=>p.id===selectedChip);
    $('placement-chip-form').hidden=!p;
    $('placement-selected-chip').textContent=p?`${short(p.id)} 위치 편집`:'칩을 눌러 위치 고정';
    if(p){$('placement-chip-board').innerHTML=candidate.boards.map(b=>`<option value="${b.id}">B${b.id+1}</option>`).join('');$('placement-chip-board').value=String(p.board);$('placement-chip-row').value=p.row;$('placement-chip-rotation').value=String(p.rotation);$('placement-chip-lock').checked=locks.some(l=>l.id===p.id);}
    const options=circuit.nets.filter(n=>n.endpoints.length).map(n=>`<option value="${esc(n.id)}">${esc(n.id)}</option>`).join('');
    $('placement-net').innerHTML=options;$('placement-net').value=selectedNet;
    renderWireTable();lockSummary();
  }
  function renderWireTable(){
    if(!candidate)return;
    const wires=candidate.wires.filter(w=>w.net===selectedNet),n=circuit.nets.find(n=>n.id===selectedNet);
    $('placement-net').value=selectedNet;
    $('placement-wire-list').innerHTML=wires.map(w=>`<div class="placement-wire-row"><b>${esc(w.from.hole)} → ${esc(w.to.hole)}</b><span>${esc(short(w.from.component))} ${w.from.number}번 ${esc(w.from.pin)} → ${esc(short(w.to.component))} ${w.to.number}번 ${esc(w.to.pin)}</span><small>${w.length_mm.toFixed(1)} mm · 핀 옆의 같은 접점 묶음에 꽂기</small></div>`).join('')||`<p class="placement-note">${n?.kind==='power'?'전원/Enable 배선은 이 탐색의 비용·경로에 포함하지 않습니다. 칩 배선도 탭에서 접속 핀을 확인하세요.':n?.endpoints.length?'외부 연결이 필요하거나 칩 간 점퍼가 없는 넷입니다.':'선택한 넷이 없습니다.'}</p>`;
  }
  function renderBoardEditor(){if(!candidate)return;$('placement-board-fields').innerHTML=candidate.boards.map(b=>`<div class="board-edit-row" data-board-edit="${b.id}"><b>B${b.id+1}</b><label>X mm<input data-axis="x" type="number" value="${b.x}" step="1"></label><label>Y mm<input data-axis="y" type="number" value="${b.y}" step="1"></label><label>회전<select data-axis="rotation">${[0,90,180,270].map(r=>`<option ${r===b.rotation?'selected':''}>${r}</option>`).join('')}</select></label></div>`).join('');}
  async function apply(boards,placements,settings,label){
    if(busy)return;const gen=++generation;
    try{setBusy(true);status('직접 배치 검증 중…');const data=await api('/api/placement/evaluate',{boards,placements,settings});if(gen!==generation)return;
      writeSettings(settings);result={...result,...data,settings,candidates:[data.candidate]};dirty=false;selectCandidate(data.candidate);status(label);
    }catch(error){if(gen===generation)status(`배치 적용 실패: ${error.message} 이전 결과를 유지합니다.`,true);}finally{setBusy(false);}
  }
  function download(name,text,type){const url=URL.createObjectURL(new Blob([text],{type}));const a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
  function init(c,netCallback){circuit=c;onNet=netCallback;$('placement-search').disabled=false;}
  function open(){if(circuit&&!result&&!busy)run();}
  function selectNet(net){selectedNet=net;if(candidate){renderMap();renderWireTable();}}
  $('placement-search').addEventListener('click',run);
  $('placement-settings').addEventListener('input',invalidate);
  $('place-topology').addEventListener('change',()=>{
    if($('place-topology').value==='compact221'){$('place-board_count').value='5';$('place-grouping').value='compact221';}
    else if($('place-topology').value!=='custom'&&$('place-grouping').value==='compact221')$('place-grouping').value='stages';
    invalidate();
  });
  $('place-grouping').addEventListener('change',()=>{
    if($('place-grouping').value==='compact221'){$('place-board_count').value='5';if($('place-topology').value!=='custom')$('place-topology').value='compact221';}
    else if($('place-topology').value==='compact221'&&candidate){customBoards=structuredClone(candidate.boards);$('place-topology').value='custom';}
    invalidate();
  });
  $('placement-candidates').addEventListener('click',e=>{const el=e.target.closest('[data-candidate]');if(el)selectCandidate(result.candidates.find(c=>c.id===el.dataset.candidate));});
  $('placement-net').addEventListener('change',e=>{selectedNet=e.target.value;onNet(selectedNet);renderMap();renderWireTable();});
  $('placement-all-wires').addEventListener('change',renderMap);
  function chooseTarget(t){const chip=t.closest('[data-place-chip]'),net=t.closest('[data-place-net]');if(chip){selectedChip=chip.dataset.placeChip;renderMap();renderInspector();}else if(net){selectedNet=net.dataset.placeNet;onNet(selectedNet);renderMap();renderWireTable();}}
  $('placement-map').addEventListener('keydown',e=>{if(['Enter',' '].includes(e.key)){e.preventDefault();chooseTarget(e.target);}});
  $('placement-map').addEventListener('pointerdown',e=>{if(e.button!==0||!camera)return;drag={x:e.clientX,y:e.clientY,camera:{...camera},target:e.target,moved:false};$('placement-map').setPointerCapture(e.pointerId);});
  $('placement-map').addEventListener('pointermove',e=>{if(!drag)return;const dx=e.clientX-drag.x,dy=e.clientY-drag.y;if(Math.abs(dx)+Math.abs(dy)>4)drag.moved=true;if(!drag.moved)return;const rect=$('placement-map').getBoundingClientRect(),scale=Math.min(rect.width/drag.camera.w,rect.height/drag.camera.h);camera={...drag.camera,x:drag.camera.x-dx/scale,y:drag.camera.y-dy/scale};updateCamera();});
  $('placement-map').addEventListener('pointerup',e=>{if(drag&&!drag.moved)chooseTarget(drag.target);drag=null;if($('placement-map').hasPointerCapture(e.pointerId))$('placement-map').releasePointerCapture(e.pointerId);});
  $('placement-map').addEventListener('pointercancel',()=>{drag=null;});
  $('placement-map').addEventListener('wheel',e=>{e.preventDefault();zoom(e.deltaY>0?1.15:.87);},{passive:false});
  $('placement-chip-picker').addEventListener('change',e=>{selectedChip=e.target.value;renderMap();renderInspector();});
  $('placement-fit-chip').addEventListener('click',()=>{if(!candidate||!selectedChip)return;const i=candidate.placements.findIndex(p=>p.id===selectedChip),r=candidate.chip_rects[i];camera={x:r[0]-15,y:r[1]-12,w:r[2]-r[0]+30,h:r[3]-r[1]+24};updateCamera();});
  $('placement-fit-cluster').addEventListener('click',()=>{if(!candidate?.cluster)return;const r=candidate.cluster.bounds;camera={x:r[0]-15,y:r[1]-15,w:r[2]-r[0]+30,h:r[3]-r[1]+30};updateCamera();});
  $('placement-fit').addEventListener('click',fit);$('placement-zoom-in').addEventListener('click',()=>zoom(.8));$('placement-zoom-out').addEventListener('click',()=>zoom(1.25));
  $('placement-apply-chip').addEventListener('click',()=>{
    if(!selectedChip||!candidate)return;
    try{const settings=readSettings(),placements=structuredClone(candidate.placements),p=placements.find(p=>p.id===selectedChip);p.board=Number($('placement-chip-board').value);p.row=Number($('placement-chip-row').value);p.rotation=Number($('placement-chip-rotation').value);
      settings.locks=settings.locks.filter(l=>l.id!==p.id);if($('placement-chip-lock').checked)settings.locks.push({...p});
      apply(candidate.boards,placements,settings,'칩 위치를 적용했습니다. 고정한 칩은 다음 탐색에서도 같은 보드·행을 유지합니다.');
    }catch(e){status(e.message,true);}
  });
  $('placement-unlock').addEventListener('click',()=>{locks=[];lockSummary();invalidate();if(candidate){renderMap();renderInspector();}});
  $('placement-apply-boards').addEventListener('click',()=>{
    if(!candidate)return;
    try{const boards=[...document.querySelectorAll('[data-board-edit]')].map(el=>{const b={id:Number(el.dataset.boardEdit)};for(const k of ['x','y','rotation']){const value=el.querySelector(`[data-axis="${k}"]`).value;if(value.trim()==='')throw new Error('보드 좌표를 입력하세요.');b[k]=Number(value);}return b;});
      const settings={...readSettings(),board_count:boards.length,topology:'custom',custom_boards:boards};apply(boards,candidate.placements,settings,'보드 배열을 적용했습니다. 직접 지정 배열에서 칩 배치를 다시 탐색할 수 있습니다.');
    }catch(e){status(e.message,true);}
  });
  $('placement-export').addEventListener('click',()=>{if(candidate)download(`swiver-${candidate.id}.json`,JSON.stringify({version:result.version,profile:result.profile.id,settings:result.settings,boards:candidate.boards,placements:candidate.placements,metrics:candidate.metrics,limitations:result.limitations},null,2),'application/json');});
  $('placement-csv').addEventListener('click',()=>{if(!candidate)return;const rows=[['net','from_chip','from_pin','from_hole','to_chip','to_pin','to_hole','planar_mm'],...candidate.wires.map(w=>[w.net,w.from.component,w.from.number,w.from.hole,w.to.component,w.to.number,w.to.hole,w.length_mm])];download(`swiver-${candidate.id}-signal-jumpers.csv`,'\ufeff'+rows.map(row=>row.map(v=>'"'+String(v).replaceAll('"','""')+'"').join(',')).join('\r\n'),'text/csv;charset=utf-8');});
  $('placement-import').addEventListener('change',async e=>{
    const file=e.target.files[0];if(!file)return;
    try{if(file.size>500000)throw new Error('배치 파일은 500 KB 이하여야 합니다.');const data=JSON.parse(await file.text());if(data.version!=='bb830-search-v1'||data.profile!=='generic-830-v1')throw new Error('지원하지 않는 배치 파일입니다.');
      if(!result){const r=await fetch('/api/placement/profile');const profile=await r.json();result={...profile,candidates:[]};}
      await apply(data.boards,data.placements,data.settings,'저장한 배치를 검증하고 불러왔습니다.');
    }catch(error){status(`불러오기 실패: ${error.message}`,true);}finally{e.target.value='';}
  });
  writeSettings(defaults);
  return {init,open,selectNet};
})();
