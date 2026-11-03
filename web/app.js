const $=(s)=>document.querySelector(s);
const esc=(s)=>String(s??'').replace(/&/g,'&amp;').replace(/</g,'&lt;');
const attr=(s)=>esc(s).replace(/"/g,'&quot;');
function inlineMd(s){return esc(s).replace(/\*\*(.+?)\*\*/g,'<strong>$1</strong>');}
function mdToHtml(text){
  const lines=String(text||'').replace(/<!--[\s\S]*?-->/g,'').split(/\r?\n/);
  let html='', inList=false;
  const closeList=()=>{ if(inList){ html+='</ul>'; inList=false; } };
  for(const raw of lines){
    const line=raw.trim();
    if(!line){ closeList(); html+='<div style="height:8px"></div>'; continue; }
    if(line.startsWith('### ')){ closeList(); html+='<h3>'+inlineMd(line.slice(4))+'</h3>'; continue; }
    if(line.startsWith('## ')){ closeList(); html+='<h2>'+inlineMd(line.slice(3))+'</h2>'; continue; }
    if(line.startsWith('# ')){ closeList(); html+='<h2>'+inlineMd(line.slice(2))+'</h2>'; continue; }
    if(line.startsWith('> ')){ closeList(); html+='<blockquote>'+inlineMd(line.slice(2))+'</blockquote>'; continue; }
    if(line.startsWith('- ')){ if(!inList){ html+='<ul>'; inList=true; } html+='<li>'+inlineMd(line.slice(2))+'</li>'; continue; }
    closeList(); html+='<p>'+inlineMd(line)+'</p>';
  }
  closeList();
  return '<div class="md">'+html+'</div>';
}
const CATS={
  overview:{subs:[['overview','概览']]},
  inner:{subs:[['memory','记忆'],['persona','人格'],['guests','群友'],['notebook','小本子'],['mood','心情 · 关系'],['proactive','主动']]},
  media:{subs:[['stickers','表情包'],['lexicon','梗 · 黑话']]},
  logs:{subs:[['logs','日志']]},
  bili:{subs:[['interests','兴趣'],['bili','B站']]}
};
let curCat='overview', curSub='overview';
function renderSubs(){
  const box=$('#subtabs'); const subs=CATS[curCat].subs;
  if(subs.length<2){ box.innerHTML=''; box.style.display='none'; return; }
  box.style.display='flex';
  box.innerHTML=subs.map(([id,label])=>`<div class="tab${id===curSub?' on':''}" data-sub="${id}">${label}</div>`).join('');
  box.querySelectorAll('.tab').forEach(el=>el.onclick=()=>showTab(curCat, el.dataset.sub));
}
function showTab(cat, sub){
  curCat=cat; curSub=sub;
  document.querySelectorAll('.tab[data-cat]').forEach(x=>x.classList.toggle('on', x.dataset.cat===cat));
  document.querySelectorAll('main section').forEach(s=>s.hidden=true);
  const target=$('#'+sub); if(target) target.hidden=false;
  renderSubs(); load();
}
document.querySelectorAll('.tab[data-cat]').forEach(el=>el.onclick=()=>showTab(el.dataset.cat, CATS[el.dataset.cat].subs[0][0]));
showTab('overview','overview');
async function j(u){const r=await fetch(u);return await r.json();}
function badge(ok,on='在线',off='离线'){return `<span class="badge ${ok?'ok':'bad'}">${ok?on:off}</span>`}
let logName='bridge';
let memTab='long';
let memTier='';
function renderMem(){
  const q=(document.getElementById('memq')?.value||'').trim().toLowerCase();
  const items=(window.__memItems||[]).filter(it=>{
    if(memTier && it.type!==memTier) return false;
    if(q && !String(it.content||'').toLowerCase().includes(q)) return false;
    return true;
  });
  let h='';
  for(const it of items){
    const t=it.time?new Date(it.time*1000).toLocaleString('zh-CN',{hour12:false}):'';
    h+=`<div style="margin:8px 0;border-bottom:1px solid #1e252e;padding-bottom:8px"><span class="badge ok">${esc(it.type)}</span> <span class="mut">${esc(t)}</span><div style="margin-top:3px">${esc(it.content)}</div></div>`;
  }
  const box=document.getElementById('memlist'); if(box) box.innerHTML=h||'<div class="mut">没有匹配的记忆</div>';
}
let lexFilter='all';
function renderLex(){
  const items=(window.__lexEntries||[]).filter(it=>lexFilter==='all'||it.category===lexFilter);
  let h='';
  for(const it of items){
    const tag=it.category==='group'?`群黑话 · ${esc(it.scope)}`:'网络梗';
    h+=`<div style="margin:8px 0;border-bottom:1px solid #1e252e;padding-bottom:8px"><span class="badge ok">${tag}</span> <b>${esc(it.term)}</b> <span class="mut">×${it.count||1}</span> <button style="float:right" onclick="lexDel('${encodeURIComponent(it.category)}','${encodeURIComponent(it.term)}')">删</button><div>${esc(it.meaning||'')}</div></div>`;
  }
  const box=document.getElementById('lexlist'); if(box) box.innerHTML=h||'<div class="mut">还没有词条</div>';
}
async function editCore(){
  window.__coreLock=true;
  const preview=document.getElementById('corePreview');
  const wrap=document.getElementById('coreEditWrap');
  if(preview) preview.hidden=true;
  if(wrap) wrap.hidden=false;
  document.getElementById('coreText')?.focus();
}
function cancelCore(){
  window.__coreLock=false;
  const preview=document.getElementById('corePreview');
  const wrap=document.getElementById('coreEditWrap');
  if(wrap) wrap.hidden=true;
  if(preview) preview.hidden=false;
  load();
}
async function saveCore(){
  const text=document.getElementById('coreText')?.value||'';
  const msg=document.getElementById('coreMsg');
  if(msg) msg.textContent='保存中…';
  const r=await fetch('/api/persona/save',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({constitution:text})});
  const data=await r.json();
  if(!data.ok){ if(msg) msg.textContent=data.error||'保存失败'; return; }
  window.__coreLock=false;
  alert('核心设定已保存');
  load();
}
const PERSONA_FIELDS={
  self_model:{preview:'selfPreview',wrap:'selfEditWrap',text:'selfText',msg:'selfMsg'},
  user_profile:{preview:'profilePreview',wrap:'profileEditWrap',text:'profileText',msg:'profileMsg'}
};
function editPersonaField(field){
  const f=PERSONA_FIELDS[field]; if(!f) return;
  window.__coreLock=true;
  const preview=document.getElementById(f.preview);
  const wrap=document.getElementById(f.wrap);
  if(preview) preview.hidden=true;
  if(wrap) wrap.hidden=false;
  document.getElementById(f.text)?.focus();
}
function cancelPersonaField(field){
  const f=PERSONA_FIELDS[field]; if(!f) return;
  window.__coreLock=false;
  const preview=document.getElementById(f.preview);
  const wrap=document.getElementById(f.wrap);
  if(wrap) wrap.hidden=true;
  if(preview) preview.hidden=false;
  load();
}
async function savePersonaField(field){
  const f=PERSONA_FIELDS[field]; if(!f) return;
  const text=document.getElementById(f.text)?.value||'';
  const msg=document.getElementById(f.msg);
  if(msg) msg.textContent='保存中…';
  const r=await fetch('/api/persona/field',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({field,text})});
  const data=await r.json();
  if(!data.ok){ if(msg) msg.textContent=data.error||'保存失败'; return; }
  window.__coreLock=false;
  alert(data.field==='self_model'?'自我认知已保存':'用户画像已保存');
  load();
}
async function lexAdd(){
  const term=document.getElementById('lexTerm')?.value||'';
  const meaning=document.getElementById('lexMeaning')?.value||'';
  const category=document.getElementById('lexCat')?.value||'network';
  if(!term.trim()) return alert('先填词');
  const r=await fetch('/api/lexicon/add',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({term,meaning,category})});
  const data=await r.json(); if(!data.ok) alert(data.error||'失败'); load();
}
async function lexDel(category,term){
  category=decodeURIComponent(category); term=decodeURIComponent(term);
  if(!confirm('删掉「'+term+'」？')) return;
  await fetch('/api/lexicon/delete',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({category,term})});
  load();
}
async function load(){
  const s=await j('/api/status');
  $('#clock').textContent=s.time;
  $('#alive').innerHTML=s.bridge.alive?`桥 ${badge(true)} <span class="mut">${s.bridge.age}s 前心跳</span>`:`桥 ${badge(false)}`;
  $('#quick').textContent = `心情 ${s.mood ?? '?'} · 记忆 ${s.memory_count} 条 · 收藏表情 ${s.stickers_user} 张 · B站 ${s.bili_logged_in?'已登录':'未登录'}`;
  if(!$('#overview').hidden){
    let h='<div class="card"><div class="k">服务端口</div><div class="grid" style="margin-top:8px">';
    for(const [k,v] of Object.entries(s.ports)) h+=`<div><div class="k">${k}</div><div class="v">${badge(v)}</div></div>`;
    h+='</div></div>';
    h+=`<div class="card"><div class="k">她现在的状态</div><div class="grid" style="margin-top:8px">
      <div><div class="k">记忆</div><div class="v">${s.memory_count} 条</div></div>
      <div><div class="k">心情值</div><div class="v">${s.mood ?? '—'} / 100</div></div>
      <div><div class="k">亲密度</div><div class="v">${(s.intimacy??0).toFixed(1)} · ${esc(s.stage||'')}</div></div>
      <div><div class="k">主动唤醒</div><div class="v">${s.proactive?'<span class="badge ok">开</span>':'<span class="badge bad">关</span>'}</div></div>
    </div><div class="mut" style="margin-top:8px">${esc(s.activity||'')}</div></div>`;
    h+='<div class="card"><div class="k">操作</div><button onclick="restartBridge()">重启桥接</button> <span class="mut" style="margin-left:8px">重启后约 6 秒恢复</span></div>';
    $('#overview').innerHTML=h;
  }
  if(!$('#mood').hidden){
    const m=await j('/api/mood');
    let h=`<div class="card"><div class="k">现在的心情</div><div class="v" style="font-size:26px">${m.mood ?? '—'} <span class="mut" style="font-size:13px">/100</span> ${m.mood>=70?'😊':m.mood>=40?'🙂':'😔'}</div>
      <div class="bar" style="margin:10px 0"><i style="width:${m.mood ?? 0}%"></i></div>
      <div class="k">亲密度 ${(m.intimacy??0).toFixed(1)} · ${esc(m.stage||'')} · 唤醒 ${Math.round((m.arousal??0)*100)}% · 情绪值 ${Math.round((m.valence??0)*100)}</div></div>`;
    h+=`<div class="card"><div class="k">情绪维度</div><div id="dims"></div></div>`;
    h+=`<div class="card"><div class="k">她正在做什么</div><div>${esc(m.activity||'—')}</div></div>`;
    h+=`<div class="card"><div class="k">最近一次情绪的由头</div><div>${esc(m.emotion_label||'—')}${m.reason?('：'+esc(m.reason)):''}</div></div>`;
    h+=`<div class="card"><div class="k">情绪时间线（最近 ${m.timeline.length} 条）</div><div id="tl"></div></div>`;
    $('#mood').innerHTML=h;
    const dims=m.dims||{}; let dh='';
    for(const [k,v] of Object.entries(dims)) dh+=`<div class="dim"><span class="name">${k}</span><div class="bar"><i style="width:${Math.max(0,Math.min(100,v))}%"></i></div><span class="mut">${v}</span></div>`;
    $('#dims').innerHTML=dh||'<span class="mut">还没有数据</span>';
    let tl='';
    for(const t of m.timeline){
      const time=t.at?new Date(t.at*1000).toLocaleString('zh-CN',{hour12:false}):'';
      tl+=`<div style="margin:8px 0;border-bottom:1px solid #1e252e;padding-bottom:6px"><span class="mut">${time}</span> <span class="badge ok">${esc(t.mood)}</span> ${t.source?`<span class="mut">${esc(t.source)}</span>`:''}<div>${esc(t.reason||'')}</div></div>`;
    }
    $('#tl').innerHTML=tl||'<span class="mut">还没有记录</span>';
  }
  if(!$('#memory').hidden){
    const m=await j('/api/memory');
    let h=`<div class="card"><div class="k">记忆 · ${m.count} 条</div>
      <div style="margin:10px 0"><input id="memq" placeholder="搜内容…" style="background:#0b0f13;border:1px solid #232a33;color:#e6edf3;border-radius:8px;padding:7px 10px;width:260px" oninput="renderMem()">
      <button onclick="memTier='' ;renderMem()">全部</button> <button onclick="memTier='L1' ;renderMem()">L1 事实</button> <button onclick="memTier='L2' ;renderMem()">L2 画像</button> <button onclick="memTier='L3' ;renderMem()">L3 事件</button> <button onclick="memTier='L4' ;renderMem()">L4 规矩</button></div>
      <div id="memlist"></div></div>`;
    $('#memory').innerHTML=h;
    window.__memItems=m.items||[];
    renderMem();
  }
  if(!$('#persona').hidden && !window.__coreLock){
    const p=await j('/api/persona');
    const st=await j('/api/style');
    let h=`<div class="card"><div class="k">人格 · ${esc(p.identity||'大肥鱼')}</div>
      <div class="grid" style="margin-top:8px">
        <div><div class="k">身份</div><div class="v">${esc(p.identity||'—')}</div></div>
        <div><div class="k">自我形象</div><div class="v">${esc(p.self_image||'—')}</div></div>
        <div><div class="k">字数</div><div class="v">核心设定 ${(p.chars||{}).constitution||0} · 自我认知 ${(p.chars||{}).self_model||0}</div></div>
      </div></div>`;
    if(st.proposal && st.proposal.style){
      h+=`<div class="card" style="border-color:#d29922"><div class="k">风格提议（待确认）</div>
        <div class="mut" style="margin:6px 0">${esc(st.proposal.reason||'')}</div>
        <div class="section-title">现在</div>${mdToHtml(st.current||'')}
        <div class="section-title">提议</div>${mdToHtml(st.proposal.style||'')}
        <button onclick="applyStyle()">应用</button> <button onclick="dismissStyle()">忽略</button></div>`;
    }
    h+=`<div class="card"><div class="k">核心设定 <button style="float:right" onclick="editCore()">编辑</button></div>
      <div id="corePreview">${p.constitution?mdToHtml(p.constitution):'<div class="mut">（空）</div>'}</div>
      <div id="coreEditWrap" hidden>
        <textarea id="coreText" onfocus="window.__coreLock=true" oninput="window.__coreLock=true" style="width:100%;height:340px;background:#0b0f13;border:1px solid #232a33;color:#e6edf3;border-radius:8px;padding:10px;font-family:ui-monospace,Consolas,monospace;font-size:13px;line-height:1.6">${esc(p.constitution||'')}</textarea>
        <div style="margin-top:8px"><button onclick="saveCore()">保存</button> <button onclick="cancelCore()">取消</button> <span id="coreMsg" class="mut"></span></div>
        <div class="mut" style="margin-top:6px">“非常重要的事”也可以在这里直接改；保存后会同步到 important.md。</div>
      </div></div>`;
    h+=`<div class="card"><div class="k">自我认知（会随相处变化）<button style="float:right" onclick="editPersonaField('self_model')">编辑</button></div>
      <div id="selfPreview">${p.self_model?mdToHtml(p.self_model):'<div class="mut">（空）</div>'}</div>
      <div id="selfEditWrap" hidden>
        <textarea id="selfText" style="width:100%;height:280px;background:#0b0f13;border:1px solid #232a33;color:#e6edf3;border-radius:8px;padding:10px;font-family:ui-monospace,Consolas,monospace;font-size:13px;line-height:1.6">${esc(p.self_model||'')}</textarea>
        <div style="margin-top:8px"><button onclick="savePersonaField('self_model')">保存</button> <button onclick="cancelPersonaField('self_model')">取消</button> <span id="selfMsg" class="mut"></span></div>
        <div class="mut" style="margin-top:6px">只会改自我认知，不会动核心设定和身份。</div>
      </div></div>`;
    h+=`<div class="card"><div class="k">用户画像<button style="float:right" onclick="editPersonaField('user_profile')">编辑</button></div>
      <div id="profilePreview">${p.user_profile?mdToHtml(p.user_profile):'<div class="mut">（还没形成）</div>'}</div>
      <div id="profileEditWrap" hidden>
        <textarea id="profileText" style="width:100%;height:280px;background:#0b0f13;border:1px solid #232a33;color:#e6edf3;border-radius:8px;padding:10px;font-family:ui-monospace,Consolas,monospace;font-size:13px;line-height:1.6">${esc(p.user_profile||'')}</textarea>
        <div style="margin-top:8px"><button onclick="savePersonaField('user_profile')">保存</button> <button onclick="cancelPersonaField('user_profile')">取消</button> <span id="profileMsg" class="mut"></span></div>
        <div class="mut" style="margin-top:6px">只改「我眼中的主人」，不会动核心设定。</div>
      </div></div>`;
    $('#persona').innerHTML=h;
  }
  if(!$('#guests').hidden){
    const g=await j('/api/guests');
    let h=`<div class="card"><div class="k">群友 · ${g.profiles.length} 人</div><div class="mut" style="margin-top:4px">按亲密度/消息数排序</div></div>`;
    if(!g.profiles.length) h+='<div class="card"><div class="mut">还没有群友记录</div></div>';
    for(const p of g.profiles){
      h+=`<div class="card"><div class="grid"><div><div class="k">称呼</div><div class="v">${esc(p.name||'（没名字）')}</div></div>
        <div><div class="k">QQ</div><div class="v">${esc(p.user_id)}</div></div>
        <div><div class="k">消息</div><div class="v">${p.msg_count}</div></div>
        <div><div class="k">亲密度</div><div class="v">${p.affinity.toFixed(1)}</div></div></div>
        ${p.profile?`<div class="mut" style="margin-top:8px">${esc(p.profile)}</div>`:''}</div>`;
    }
    $('#guests').innerHTML=h;
  }
  if(!$('#notebook').hidden){
    const n=await j('/api/notebook');
    let h=`<div class="card"><div class="k">她的便签（${n.notes.length}）</div>`;
    if(!n.notes.length) h+='<div class="mut">还没有便签</div>';
    for(const note of n.notes) h+=`<div style="margin:8px 0;border-bottom:1px solid #1e252e;padding-bottom:6px"><span class="mut">${esc(note.date||'')}</span> ${esc(note.text||'')}</div>`;
    h+='</div>';
    h+=`<div class="card"><div class="k">任务（${n.tasks.length}）</div>`;
    if(!n.tasks.length) h+='<div class="mut">没有待办</div>';
    for(const t of n.tasks) h+=`<div style="margin:6px 0"><span class="tag">${t.done?'完成':'进行中'}</span> ${esc(t.text||'')}</div>`;
    h+='</div>';
    h+=`<div class="card"><div class="k">日记（${n.diary.length}）</div>`;
    if(!n.diary.length) h+='<div class="mut">今天还没写</div>';
    for(const d of n.diary) h+=`<div style="margin:8px 0"><span class="mut">${esc(d.date||'')}</span> ${esc(d.text||'')}</div>`;
    h+='</div>';
    $('#notebook').innerHTML=h;
  }
  if(!$('#proactive').hidden){
    const p=await j('/api/proactive');
    let h=`<div class="card"><div class="k">主动唤醒 · ${p.enabled?'<span class="badge ok">开</span>':'<span class="badge bad">关</span>'}</div>
      <div class="grid" style="margin-top:10px">
        <div><div class="k">时间窗</div><div class="v">${p.startHour ?? 8}:00 – ${p.endHour ?? 23}:00</div></div>
        <div><div class="k">间隔</div><div class="v">${p.minGapMinutes ?? 30} – ${p.maxGapMinutes ?? 180} 分钟</div></div>
        <div><div class="k">静默比例</div><div class="v">${p.silentRatio ?? 40}%</div></div>
        <div><div class="k">允许发言</div><div class="v">${p.talkEnabled?'是':'否'}</div></div>
      </div>
      <div style="margin-top:12px">
        <button onclick="setProactive({enabled:true,talkEnabled:true})">开</button>
        <button onclick="setProactive({enabled:false})">关</button>
        <button onclick="setProactive({startHour:8,endHour:24})">8–24 点</button>
        <button onclick="setProactive({startHour:8,endHour:23})">8–23 点</button>
      </div>
      <div class="mut" style="margin-top:8px">到点由记忆服务写唤醒事件，桥接生成一句话；静默事件不发。</div></div>`;
    $('#proactive').innerHTML=h;
  }
  if(!$('#stickers').hidden){
    const st=await j('/api/stickers');
    const items=st.items||st.user_items||[];
    let h='<div class="card"><div class="k">分类统计</div><div style="margin-top:8px">';
    for(const [k,v] of Object.entries(st.categories)) h+=`<span class="tag">${esc(k)} ${v.user}/${v.total}</span> `;
    h+='</div></div>';
    h+=`<div class="card"><div class="k">表情库（${items.length} 张）</div>${st.hidden_images?`<div class="mut" style="margin:4px 0">另有 ${st.hidden_images} 张旧图片没有表情标识，已隐藏；重新发一次可收成表情。</div>`:''}<div class="items" style="margin-top:8px">`;
    for(let i=0;i<items.length;i++){
      const it=items[i], id=`st_tags_${i}`;
      h+=`<div class="item"><img class="thumb" src="/api/sticker?file=${encodeURIComponent(it.file)}">
        <div><b>${esc(it.name||'')}</b> <span class="mut">${esc(it.category||'')}${it.usage_count?` · 发过 ${it.usage_count} 次`:''}</span></div>
        <div class="mut" style="margin:3px 0">${esc(it.caption||'')}</div>
        <div style="display:flex;gap:6px;align-items:center;flex-wrap:wrap;margin-top:4px">
          <input id="${id}" value="${attr((it.tags||[]).join(', '))}" placeholder="标签，用逗号分隔" style="background:#0b0f13;border:1px solid #232a33;color:#e6edf3;border-radius:7px;padding:5px 8px;width:260px">
          <button onclick='stickerSaveTags(${JSON.stringify(it.file)}, ${JSON.stringify(id)})'>保存标签</button>
          <button onclick='stickerDelete(${JSON.stringify(it.file)})'>删除</button>
        </div></div>`;
    }
    h+='</div></div>';
    $('#stickers').innerHTML=h;
  }
  if(!$('#lexicon').hidden){
    const lx=await j('/api/lexicon');
    window.__lexEntries=lx.entries||[];
    let h=`<div class="card"><div class="k">梗 · 黑话 · ${window.__lexEntries.length} 条</div>
      <div style="margin:10px 0">
        <input id="lexTerm" placeholder="词" style="background:#0b0f13;border:1px solid #232a33;color:#e6edf3;border-radius:8px;padding:7px 10px;width:150px">
        <input id="lexMeaning" placeholder="意思" style="background:#0b0f13;border:1px solid #232a33;color:#e6edf3;border-radius:8px;padding:7px 10px;width:320px">
        <select id="lexCat" style="background:#0b0f13;border:1px solid #232a33;color:#e6edf3;border-radius:8px;padding:7px 10px"><option value="network">网络梗</option><option value="group">群黑话</option></select>
        <button onclick="lexAdd()">添加</button>
      </div>
      <div style="margin:8px 0"><button onclick="lexFilter='all';renderLex()">全部</button> <button onclick="lexFilter='group';renderLex()">群黑话</button> <button onclick="lexFilter='network';renderLex()">网络梗</button></div>
      <div id="lexlist"></div></div>`;
    $('#lexicon').innerHTML=h;
    renderLex();
  }
  if(!$('#logs').hidden){
    const data=await j('/api/logs?name='+logName);
    let h=`<div class="card"><div class="k">日志</div>
      <div style="margin:8px 0"><button onclick="setLog('bridge')">桥接</button> <button onclick="setLog('selfwake')">主动开口</button> <button onclick="setLog('bili')">B站值班</button> <button onclick="setLog('dsh')">DSH 错误</button></div>
      <pre id="logbox">${esc(data.text)}</pre></div>`;
    $('#logs').innerHTML=h;
  }
  if(!$('#interests').hidden){
    const it=await j('/api/interests');
    const s=it.state||{};
    let h=`<div class="card"><div class="k">自主刷 B 站</div><div class="v">今天 ${s.rounds||0} 轮 · 分享 ${s.shares||0} 次${s.last_run?(' · 上次 '+new Date(s.last_run*1000).toLocaleString('zh-CN',{hour12:false})):''}</div></div>`;
    h+=`<div class="card"><div class="k">兴趣清单（${it.interests.length}）</div>`;
    for(const i of it.interests) h+=`<div style="margin:6px 0"><span class="tag">${esc(i.topic)}</span> <span class="mut">权重 ${i.weight}${i.evidence?(' · '+esc(i.evidence)):''}</span></div>`;
    h+='</div>';
    $('#interests').innerHTML=h;
  }
  if(!$('#bili').hidden){
    const f=await j('/api/bili/feed'); const qr=await j('/api/bili/qr/status');
    const b=f.login;
    let h=`<div class="card"><div class="k">B 站</div><div class="v">${badge(b.logged_in,'已登录','未登录')} <span class="mut">${b.uid?('UID '+b.uid):''}</span></div>`;
    h+=`<div class="mut" style="margin-top:6px">看过的 ${f.seen.length} 条 · 自主刷笔记 ${f.notes.length} 轮</div></div>`;
    h+=`<div class="card"><div class="k">看过的视频</div>`;
    for(const v of f.seen){
      const mark = v.status==='挑了' ? '<span class="badge ok">挑了</span>' : '<span class="badge warn">跳过</span>';
      h+=`<div class="video-row">${mark} <a href="${v.url}" target="_blank">${esc(v.title)}</a><div class="video-meta">${esc(v.date)}${v.up?(' · '+esc(v.up)):''}</div></div>`;
    }
    if(!f.seen.length) h+='<div class="mut">还没有记录</div>';
    h+='</div>';
    h+=`<div class="section-title">刷到并记下的</div>`;
    for(const n of f.notes){
      const parts = n.head.split(' · ');
      const when = parts[0] || '';
      const topic = parts.slice(1).join(' · ') || n.head;
      h+=`<div class="note"><div class="note-title">${esc(topic)}</div><div class="note-sub">${esc(when)} · ${n.videos.length} 个视频</div>`;
      for(const v of n.videos){
        h+=`<div class="video-item"><a href="${v.url}" target="_blank">${esc(v.title)}</a>${v.why?`<div class="why">${esc(v.why)}</div>`:''}</div>`;
      }
      if(n.thought) h+=`<div class="thought">${esc(n.thought)}</div>`;
      h+='</div>';
    }
    if(!f.notes.length) h+='<div class="mut">还没有笔记</div>';
    if(f.interests.length){
      h+=`<div class="card"><div class="k">关注方向</div><div style="margin-top:8px">`;
      for(const i of f.interests) h+=`<span class="tag">${esc(i.topic)} · ${i.weight}</span> `;
      h+='</div></div>';
    }
    const img = qr.qr_ready ? `<img src="/api/bili/qr.png?v=${qr.mtime}" style="width:220px;height:220px;background:#fff;border-radius:10px;padding:6px">` : '<span class="mut">还没有二维码</span>';
    h+=`<div class="card"><details><summary class="k">登录 / 扫码（当前：${esc(qr.state)}）</summary><div style="margin:10px 0">${img}</div><button onclick="startQr()">生成 / 刷新二维码</button></details></div>`;
    $('#bili').innerHTML=h;
  }
}
async function restartBridge(){ await fetch('/api/bridge/restart',{method:'POST'}); setTimeout(load,1500); }
async function setProactive(body){ const r=await fetch('/api/proactive',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}); const j=await r.json(); if(!j.ok&&j.error) alert(j.error); load(); }
async function applyStyle(){ const r=await fetch('/api/style/apply',{method:'POST'}); const j=await r.json(); alert(j.message||j.error||'已处理'); load(); }
async function dismissStyle(){ const r=await fetch('/api/style/dismiss',{method:'POST'}); const j=await r.json(); alert(j.message||'已忽略'); load(); }
async function syncGrowth(){ const r=await fetch('/api/growth/sync',{method:'POST'}); const j=await r.json(); alert(j.output||'已同步'); load(); }
function setLog(n){ logName=n; load(); }
async function startQr(){ await fetch('/api/bili/qr/start',{method:'POST'}); setTimeout(load,1500); }
async function stickerSaveTags(file,id){
  const raw=(document.getElementById(id)?.value||'');
  const tags=raw.split(/[,，、\s]+/).map(x=>x.trim()).filter(Boolean);
  const r=await fetch('/api/stickers/tags',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({file,tags})});
  const j=await r.json();
  if(!j.ok) alert(j.error||'保存失败');
  load();
}
async function stickerDelete(file){
  if(!confirm(`删除这张表情？\n${file}`)) return;
  const r=await fetch('/api/stickers/delete',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({file})});
  const j=await r.json();
  if(!j.ok) alert(j.error||'删除失败');
  load();
}
setInterval(load,10000); load();
