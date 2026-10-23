/* Two presentations of the same circuit. No electrical evaluation here. */
"use strict";
window.SwiverViews = (() => {
  const $ = id => document.getElementById(id);
  const esc = v => String(v).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  let circuit, snapshot, selectNet, selectBit, selected = 'net_c_lo', bit = 0, filter = '', chip = '', group = 'all';
  let view = new URLSearchParams(location.search).get('view') === 'cpu' ? 'cpu' : 'assembly';
  const headerTitle = document.querySelector('.header-title').innerHTML;
  const short = id => id.replace('U_ALU_','').replace('157_YBP_','157_');
  const netLabel = id => id.replace(/^net_/,'').replace(/^pwr_/,'').toUpperCase();
  const value = net => snapshot?.signals[net] ?? '—';
  const parts = () => new Map(circuit.components.map(c=>[c.id,c]));
  const pinText = e => {const p=parts().get(e.component); return `${short(p.id)} · ${p.package.pins[e.pin].number}번 ${p.package.pins[e.pin].label}`;};
  const external = n => n.id === 'pwr_vcc' ? '+5 V 전원 레일' : n.id === 'pwr_gnd' ? 'GND 공통 레일' : `외부 입력 · ${netLabel(n.id)}`;
  function endpoints(n) {
    const ps=parts(), output=n.endpoints.find(e=>ps.get(e.component).package.pins[e.pin].direction === 'output');
    const source=output ? pinText(output) : external(n);
    const targets=n.endpoints.filter(e=>e !== output).map(pinText);
    if (!targets.length && output) targets.push(`외부 출력 / 관측 · ${netLabel(n.id)}`);
    return {source,targets,output};
  }
  function mode(next) {
    view=next;
    for (const name of ['assembly','gates','overview','placement','cpu']) {
      $(`view-${name}`).setAttribute('aria-pressed',String(name===view));
      document.querySelector(name==='overview'?'.workspace':`#${name}-view`).hidden=name!==view;
    }
    document.querySelector('.controls').hidden=['assembly','placement','cpu'].includes(view);
    document.querySelector('.observations').hidden=['assembly','placement','cpu'].includes(view);
    document.querySelector('.explanation').hidden=['assembly','placement','cpu'].includes(view);
    document.body.classList.toggle('cpu-mode',view==='cpu');
    document.querySelector('.header-title').innerHTML=view==='cpu'?'CPU 연결도 <span>TWO CPLDs / SHARED 8-BIT BUS</span>':headerTitle;
    const url=new URL(location.href);
    if(view==='cpu') url.searchParams.set('view','cpu'); else url.searchParams.delete('view');
    history.replaceState(null,'',url);
    if(view==='cpu') window.SwiverCpu.open();
    if(view==='overview') $('fit').click();
    if(view==='placement') window.SwiverPlacement.open();
  }
  function init(c,onNet,onBit) {
    circuit=c;selectNet=onNet;selectBit=onBit;
    window.SwiverPlacement.init(c,onNet);
    $('assembly-chip').innerHTML='<option value="">모든 칩</option>'+c.components.map(p=>`<option value="${esc(p.id)}">${short(p.id)} · ${p.part}</option>`).join('');
    $('gate-bit').innerHTML=Array.from({length:8},(_,i)=>`<option value="${i}">비트 ${i}</option>`).join('');
    mode(view); render();
  }
  function update(s) {snapshot=s; renderGates();}
  function select(type,id) {if(type==='net') {window.SwiverPlacement.selectNet(id);selected=id; for(const bus of circuit.buses) {const index=bus.nets.indexOf(id);if(index>=0){bit=index;$('gate-bit').value=String(bit);selectBit(bit);break;}}} render();}
  function matches(n) {
    return n.endpoints.length && (!chip || n.endpoints.some(e=>e.component===chip)) &&
      (group==='all'||(group==='power'?n.kind==='power':group==='control'?n.kind==='control':n.kind==='data')) &&
      (!filter || `${n.id} ${n.endpoints.map(pinText).join(' ')}`.toLowerCase().includes(filter));
  }
  function renderList() {
    const nets=circuit.nets.filter(matches), scroll=$('assembly-nets').scrollTop;
    $('assembly-nets').innerHTML=nets.map(n=>`<button data-wire-net="${esc(n.id)}" class="wire-choice ${n.id===selected?'chosen':''}" aria-pressed="${n.id===selected}"><strong>${netLabel(n.id)}</strong><span>${n.endpoints.length}핀 · ${n.kind==='power'?'전원':n.kind==='control'?'제어':'데이터'}</span></button>`).join('') || '<p>일치하는 연결이 없습니다.</p>';
    $('assembly-nets').scrollTop=scroll;
    $('wire-count').textContent=`${nets.length}개 넷 · 같은 이름은 모두 연결`;
  }
  function renderAssembly() {
    renderList();
    const n=circuit.nets.find(n=>n.id===selected);
    if(!n || !n.endpoints.length) { $('assembly-detail').innerHTML='<p>이 신호는 12칩 외부의 계산·관측 신호입니다. 칩에 연결할 DIP 핀이 없습니다.</p>';return; }
    const ends=endpoints(n), ps=parts(), ids=[...new Set(n.endpoints.map(e=>e.component))];
    const title=`<div class="wire-title"><div><span class="eyebrow">ONE NET AT A TIME</span><h2>${netLabel(n.id)}</h2><code>${esc(n.id)}</code></div><span class="wire-kind">${n.kind==='power'?'공통 전원':n.kind==='control'?'제어 배선':'신호 배선'}</span></div>`;
    const rows=ends.targets.map(t=>`<tr><td>${esc(ends.source)}</td><td class="connection-arrow">⟶</td><td>${esc(t)}</td></tr>`).join('');
    const width=Math.min(ids.length,3)*340+20, height=Math.ceil(ids.length/3)*370+15;
    let svg='', links='';
    for(const [i,id] of ids.entries()) {
      const p=ps.get(id), x=20+(i%3)*340, y=20+Math.floor(i/3)*370;
      svg+=`<text x="${x+160}" y="${y}" text-anchor="middle" class="dip-id">${short(id)} · ${p.part}</text><rect class="dip-body" x="${x+110}" y="${y+32}" width="100" height="280" rx="8"/><path class="dip-notch" d="M${x+146} ${y+32} a14 14 0 0 0 28 0"/><circle cx="${x+122}" cy="${y+46}" r="4" fill="#fff"/><text x="${x+160}" y="${y+332}" text-anchor="middle" class="dip-orientation">윗면 · 홈 ↑ · 왼쪽 위 1번</text>`;
      for(const [pin,meta] of Object.entries(p.package.pins)) {
        const left=meta.number<=8, row=left?meta.number-1:16-meta.number, py=y+65+row*32;
        const px=x+(left?94:226), net=p.pins[pin], active=net===selected;
        if(active) {const lane=x+(left?5:315), rail=y+349;links+=`<path class="dip-wire" d="M${px} ${py} H${lane} V${rail} H8"/><circle class="dip-junction" cx="${px}" cy="${py}" r="4"/>`;}
        svg+=`<g class="dip-pin ${active?'connected':''}" role="button" tabindex="0" data-wire-net="${esc(net)}" aria-label="${esc(short(id))} ${meta.number}번 ${esc(meta.label)}, ${esc(net)}"><title>${esc(pinText({component:id,pin}))} → ${esc(net)}</title><rect x="${px-8}" y="${py-7}" width="16" height="14" rx="2"/><text x="${x+(left?116:204)}" y="${py+4}" text-anchor="${left?'start':'end'}" class="dip-number">${meta.number}</text><text x="${x+(left?79:241)}" y="${py+4}" text-anchor="${left?'end':'start'}" class="dip-function">${esc(meta.label)}</text></g>`;
      }
    }
    if(ids.length>3) links+=`<path class="dip-wire" d="M8 369 V${20+Math.floor((ids.length-1)/3)*370+349}"/>`;
    $('assembly-detail').innerHTML=title+`<p class="wire-instruction">아래 <strong>주황색 핀을 같은 넷으로 연결</strong>합니다. 다른 핀을 누르면 그 핀의 배선으로 이동합니다.</p><div class="connection-table-wrap"><table class="connection-table"><thead><tr><th>출발 / 공통 연결점</th><th></th><th>도착 핀</th></tr></thead><tbody>${rows}</tbody></table></div><div class="dip-scroll"><svg class="dip-diagram ${ids.length===1?'dip-single':'dip-many'}" viewBox="0 0 ${width} ${height}" aria-label="선택 넷의 DIP 핀 연결">${links}${svg}</svg></div><p class="assembly-note">칩은 브레드보드 중앙 홈을 가로질러 배치합니다. 이 그림은 연결 관계이며 빵판 구멍 좌표나 전선 길이는 지정하지 않습니다.</p><div class="pin-sources">핀 배치 출처 ${[...new Set(ids.map(id=>ps.get(id).part))].map(part=>`<a href="${ps.get(ids.find(id=>ps.get(id).part===part)).package.source}" target="_blank" rel="noreferrer">TI ${part} · p.3 ↗</a>`).join('')}</div>`;
  }
  function renderGates() {
    if(!snapshot) return;
    const p=circuit.components.find(p=>p.id===`U_ALU_153_${bit}`), half=bit<4?'LO':'HI', lane=bit%4, mux=bit<4?0:1;
    const n=(prefix)=>`${prefix}${bit}`;
    function wire(net,x1,y1,x2,y2,label) {return `<g data-wire-net="${net}" role="button" tabindex="0"><path class="gate-wire ${net===selected?'chosen':''}" d="M${x1} ${y1} H${(x1+x2)/2} V${y2} H${x2}"/><text x="${x1+8}" y="${y1-8}">${esc(label)} = ${value(net)}</text></g>`;}
    function box(x,y,w,h,name,detail){return `<rect class="gate-box" x="${x}" y="${y}" width="${w}" height="${h}" rx="8"/><text class="gate-title" x="${x+15}" y="${y+25}">${name}</text><text x="${x+15}" y="${y+46}">${detail}</text>`;}
    let svg=box(220,45,170,170,'4:1 MUX · LOGIC',`153_${bit} / 1Y`)+box(220,290,170,170,'4:1 MUX · B_ADD',`153_${bit} / 2Y`)+box(540,275,180,170,'4비트 가산기',`283_${half} · 비트 ${bit<4?'0–3':'4–7'}`)+box(870,115,170,190,'2:1 MUX · 출력',`157_${mux} / ${lane+1}Y`);
    for(let channel=1;channel<=2;channel++) for(let k=0;k<4;k++) {let y=(channel===1?113:358)+k*25, net=p.pins[`${channel}C${k}`];svg+=wire(net,35,y,220,y,`${channel}C${k} · ${netLabel(net)}`);}
    // MUX path emphasis only: address bits and outputs are observed from Python.
    const address = `${value(n('net_b'))}${value(n('net_a'))}`, addresses=['00','01','10','11'];
    for(let channel=1;channel<=2;channel++) for(let k=0;k<4;k++) {
      const py=(channel===1?113:358)+k*25, outY=channel===1?140:385;
      svg+=`<path class="gate-internal ${address===addresses[k]?'enabled':''}" d="M220 ${py} H270 L360 ${outY} H390"/><text x="225" y="${py-4}">C${k}</text>`;
    }
    for(const [level,py] of [['1',200],['0',260]]) svg+=`<path class="gate-internal ${value('net_y_mux_sel')===level?'enabled':''}" d="M870 ${py} H915 L1015 215 H1040"/><text x="875" y="${py-5}">${level==='1'?'B / LOGIC':'A / SUM'}</text>`;
    for(const [prefix,x,y,label] of [['net_a',275,247,'A'],['net_b',315,277,'B']]) {
      const net=n(prefix);
      svg+=`<g data-wire-net="${net}" role="button" tabindex="0"><path class="gate-control" d="M40 ${y} H${x} V215 M${x} ${y} V290"/><circle cx="${x}" cy="${y}" r="3" fill="#547b93"/><text x="45" y="${y-6}">${label}[${bit}] · 주소 ${label} = ${value(net)}</text></g>`;
    }
    svg+=`<g data-wire-net="net_y_mux_sel" role="button" tabindex="0"><path class="gate-control" d="M955 345 V305"/><text x="965" y="338">Y_MUX_SEL = ${value('net_y_mux_sel')}</text></g>`;
    svg+=wire(n('net_y_logic'),390,140,870,200,`LOGIC[${bit}]`)+wire(n('net_b_add'),390,385,540,385,`B_ADD[${bit}]`)+wire(n('net_sum'),720,355,870,260,`SUM[${bit}]`)+wire(n('net_y'),1040,215,1160,215,`Y[${bit}]`)+wire(n('net_a'),410,260,540,320,`A[${bit}]`);
    svg+=`<g data-wire-net="${half==='LO'?'net_cin':'net_c_lo'}" role="button" tabindex="0"><path class="gate-control" d="M590 505 V445"/><text x="400" y="500">${half==='LO'?'외부 CIN':'LO.COUT → C_LO'} = ${value(half==='LO'?'net_cin':'net_c_lo')}</text></g><g data-wire-net="${half==='LO'?'net_c_lo':'net_c_hi'}" role="button" tabindex="0"><path class="gate-control" d="M670 445 V480 H810"/><text x="720" y="470">${half==='LO'?'C_LO → HI.CIN':'C_HI → 외부'} = ${value(half==='LO'?'net_c_lo':'net_c_hi')}</text></g>`;
    svg+=`<text x="235" y="235">B,A = ${value(n('net_b'))}${value(n('net_a'))} · 선택 주소</text><text x="235" y="480">같은 A/B 주소 → 두 MUX</text><text x="555" y="407">CIN ${value(half==='LO'?'net_cin':'net_c_lo')} → COUT ${value(half==='LO'?'net_c_lo':'net_c_hi')}</text><text x="885" y="284">S = ${value('net_y_mux_sel')}</text><text x="40" y="525">주황색: 선택 넷 · 선을 누르면 조립 탭에서도 같은 연결을 볼 수 있습니다.</text>`;
    $('gate-scene').innerHTML=svg;
    $('gate-caption').textContent=`비트 ${bit} · 실제 관측값 · 153의 두 MUX와 283 ${half}, 157 채널 ${lane+1}. 가산기는 캐리 의존성을 포함하는 4비트 기능 블록입니다.`;
  }
  function render(){if(!circuit)return;renderAssembly();renderGates();}
  document.addEventListener('click',e=>{const target=e.target.closest('[data-wire-net]');if(target&&circuit) {selected=target.dataset.wireNet;selectNet(selected);} });
  document.addEventListener('keydown',e=>{if(['Enter',' '].includes(e.key)&&e.target.matches('g[data-wire-net]')) {e.preventDefault();selected=e.target.dataset.wireNet;selectNet(selected);}});
  for(const name of ['assembly','gates','overview','placement','cpu']) $(`view-${name}`).addEventListener('click',()=>mode(name));
  $('assembly-search').addEventListener('input',e=>{filter=e.target.value.toLowerCase();renderList();});
  $('assembly-chip').addEventListener('change',e=>{chip=e.target.value;renderList();});
  $('assembly-group').addEventListener('change',e=>{group=e.target.value;renderList();});
  $('gate-bit').addEventListener('change',e=>{bit=Number(e.target.value);selectBit(bit);renderGates();});
  return {init,update,select};
})();
