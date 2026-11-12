const $=(s)=>document.querySelector(s);
const DOMINANT_LABEL={importance:'重要',emotion:'情绪',distinctiveness:'独特',self_relevance:'自我',relationship:'关系',none:'无'};
const INSIGHT_KIND_LABEL={me:'关于我',us:'关于我们',none:'想法'};
const insightKindLabel=(kind)=>String(kind||'').split(',').map(x=>INSIGHT_KIND_LABEL[x.trim()]||x.trim()).filter(Boolean).join('、');
function fmtUntil(ts){
  const d=new Date(Number(ts)*1000);
  const now=new Date();
  const hhmm=d.toLocaleTimeString('zh-CN',{hour:'2-digit',minute:'2-digit'});
  const same=(a,b)=>a.getFullYear()===b.getFullYear()&&a.getMonth()===b.getMonth()&&a.getDate()===b.getDate();
  if(same(d,now)) return hhmm;
  const t=new Date(now.getFullYear(),now.getMonth(),now.getDate()+1);
  if(same(d,t)) return '次日 '+hhmm;
  return d.toLocaleDateString('zh-CN',{month:'2-digit',day:'2-digit'})+' '+hhmm;
}
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
  media:{subs:[['stickers','表情包'],['lexicon','词库']]},
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
let memStatus='';
const MEM_TIER_LABEL={L0:'L0 原话',L1:'L1 总结',L2:'L2 判断',L3:'L3 事件',L4:'L4 核心'};
const MEM_STATUS_LABEL={open:'进行中',closed:'已结束',standalone:'片段',dormant:'沉睡',archived:'归档',legacy:'旧数据',hypothesis:'待验证',promoted:'已升 L1',rejected:'已否定',expired:'已过期',superseded:'被替代'};
function memBadgeClass(status){
  if(status==='open') return 'ok';
  if(status==='dormant') return 'warn';
  if(status==='closed') return 'tag';
  return 'tag';
}
function renderMem(){
  const q=(document.getElementById('memq')?.value||'').trim().toLowerCase();
  const items=(window.__memItems||[]).filter(it=>{
    if(memTier && it.type!==memTier) return false;
    if(memStatus && it.status!==memStatus) return false;
    if(!memStatus && it.status==='archived') return false;
    if(q){
      const hay=(String(it.title||'')+' '+String(it.content||'')).toLowerCase();
      if(!hay.includes(q)) return false;
    }
    return true;
  }).sort((a,b)=>Number(b.last_seen||b.time||0)-Number(a.last_seen||a.time||0));
  let h='';
  for(const it of items){
    const ts=Number(it.last_seen||it.time||0);
    const t=ts?new Date(ts*1000).toLocaleString('zh-CN',{hour12:false}):'';
    const status=it.status?`<span class="badge ${memBadgeClass(it.status)}">${esc(MEM_STATUS_LABEL[it.status]||it.status)}</span>`:'';
    const title=it.title?`<b>${esc(it.title)}</b> `:'';
    const stale=it.stale?`<span class="badge warn">已过期</span> `:'';
    const src=it.source_count?`<span class="mut">来源 ${it.source_count} 条</span> `:'';
    const l2=it.type==='L2'?`<div class="mut" style="margin-top:3px">${it.confidence!=null?`置信 ${(Number(it.confidence)*100).toFixed(0)}%`:''}${it.expires_at?` · 过期 ${new Date(Number(it.expires_at)*1000).toLocaleDateString('zh-CN')}`:''}</div>`:'';
    const memo=it.type==='L3'?`<div class="mut" style="margin-top:3px">难忘 ${it.memorability!=null?(Number(it.memorability)*100).toFixed(0)+'%':'—'}${it.dominant&&it.dominant!=='none'?`（${esc(DOMINANT_LABEL[it.dominant]||it.dominant)}）`:''}${it.stability_days?(' · 稳定 '+Math.round(Number(it.stability_days))+' 天'):''}${it.recall_count?(' · 召回 '+it.recall_count+' 次'):''}${it.active_until&&Number(it.active_until)>Date.now()/1000?(' · 活跃至 '+fmtUntil(it.active_until)):''}</div>`:'';
    const ik=insightKindLabel(it.insight_target);
    const insight=it.insight_text?`<div class="mut" style="margin-top:3px">感悟${ik?`（${esc(ik)}）`:''}：${esc(it.insight_text)}</div>`:'';
    const emo=it.emotion_label?`<span class="badge" style="background:#1f6feb;color:#fff">${esc(it.emotion_label)}${it.emotion_valence!=null?` ${Number(it.emotion_valence).toFixed(1)}`:''}</span> `:'';
    const wants=it.want_more?`<div class="mut" style="margin-top:3px">想弄明白${it.want_used?'（已用）':''}：${esc(it.want_more)}</div>`:'';
    const asks=it.ask_him?`<div class="mut" style="margin-top:3px">想问：${esc(it.ask_him)}</div>`:'';
    const id=Number(it.id)||0;
    const editing=window.__memEdit===id;
    const editBtn=it.type==='L3'&&!editing&&id?`<button style="float:right" onclick="editMemText(${id})">改字</button>`:'';
    const content=editing?`<div style="margin-top:6px"><textarea id="memEditText" style="width:100%;height:160px;background:#0b0f13;border:1px solid #232a33;color:#e6edf3;border-radius:8px;padding:10px;font-size:13px;line-height:1.6">${esc(it.content)}</textarea><div style="margin-top:6px"><button onclick="saveMemText(${id})">保存</button> <button onclick="cancelMemText()">取消</button></div></div>`:`<div style="margin-top:3px">${esc(it.content)}</div>`;
    h+=`<div id="mem-${id}" style="margin:8px 0;border-bottom:1px solid #1e252e;padding-bottom:8px"><span class="badge ok">${esc(MEM_TIER_LABEL[it.type]||it.type)}</span> ${emo}${status} ${stale}${title}<span class="mut">${esc(t)}</span>${editBtn}${content}${wants}${asks}${memo}${insight}${l2}<div style="margin-top:3px">${src}</div></div>`;
  }
  const statusRow=document.getElementById('memstatus');
  if(statusRow) statusRow.style.display=memTier==='L3'?'block':'none';
  const box=document.getElementById('memlist'); if(box) box.innerHTML=h||'<div class="mut">没有匹配的记忆</div>';
}
function editMemText(id){
  window.__memEdit=Number(id)||0;
  renderMem();
  setTimeout(()=>{ const el=document.getElementById('memEditText'); if(el){ el.focus(); el.setSelectionRange(el.value.length,el.value.length); } },0);
}
function cancelMemText(){
  window.__memEdit=0;
  renderMem();
}
async function saveMemText(id){
  const el=document.getElementById('memEditText');
  const text=(el?.value||'').trim();
  if(!text){ alert('文字不能为空'); return; }
  try{
    const r=await fetch('/api/memory/update_text',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id,text})});
    const d=await r.json();
    if(!d.ok){ alert(d.error||'保存失败'); return; }
    const item=(window.__memItems||[]).find(x=>Number(x.id)===Number(id));
    if(item) item.content=text;
    window.__memEdit=0;
    renderMem();
  }catch(e){
    alert('保存失败：'+e);
  }
}
async function closeThread(id,btn){
  if(!id){ alert('没有识别到这件事的 id'); return; }
  if(btn){ btn.disabled=true; btn.textContent='结束中…'; }
  try{
    const r=await fetch('/api/threads/close',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id})});
    const d=await r.json();
    if(!d.ok){
      if(btn){ btn.disabled=false; btn.textContent='结束'; }
      alert(d.error||'结束失败');
      return;
    }
    await load();
  }catch(e){
    if(btn){ btn.disabled=false; btn.textContent='结束'; }
    alert('结束失败：'+e);
  }
}

const LEX_KIND={slang:'群黑话',meme:'网络梗',buzzword:'热门词',fandom:'角色/IP',abbreviation:'缩写',emoji:'表情用法',event:'事件'};
const LEX_STATUS={fresh:'新词',hot:'热门',stable:'稳定',archived:'过气'};
function renderLex(){
  const items=(window.__lexEntries||[]).filter(it=>lexFilter==='all'||it.kind===lexFilter);
  let h='';
  for(const it of items){
    const kind=LEX_KIND[it.kind]||it.kind||'词条';
    const scope=it.category==='group'?`群 ${esc(it.scope)}`:'全局';
    const aliases=(it.aliases||[]).length?` <span class="mut">别名：${(it.aliases||[]).map(esc).join('、')}</span>`:'';
    h+=`<div style="margin:8px 0;border-bottom:1px solid #1e252e;padding-bottom:8px"><span class="badge ok">${kind} · ${scope}</span> <b>${esc(it.term)}</b>${aliases} <span class="tag">${LEX_STATUS[it.status]||it.status}</span> <span class="mut">×${it.count||1}</span> <button style="float:right" onclick="lexDel('${encodeURIComponent(it.id||'')}', this)">删</button><div>${esc(it.meaning||'')}</div></div>`;
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
  alert('已保存');
  load();
}
async function lexAdd(){
  const term=document.getElementById('lexTerm')?.value||'';
  const meaning=document.getElementById('lexMeaning')?.value||'';
  const kind=document.getElementById('lexCat')?.value||'meme';
  const aliases=document.getElementById('lexAliases')?.value||'';
  const status=document.getElementById('lexStatus')?.value||'stable';
  if(!term.trim()) return alert('先填词');
  const r=await fetch('/api/lexicon/add',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({term,meaning,kind,aliases,status})});
  const data=await r.json(); if(!data.ok) alert(data.error||'失败'); load();
}
async function lexDel(id,btn){
  id=decodeURIComponent(id);
  if(!id){ alert('没有识别到词条 id'); return; }
  if(btn){ btn.disabled=true; btn.textContent='删除中…'; }
  try{
    const r=await fetch('/api/lexicon/delete',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id})});
    const j=await r.json();
    if(!j.ok){
      if(btn){ btn.disabled=false; btn.textContent='删'; }
      alert(j.error||'删除失败');
      return;
    }
    await load();
  }catch(e){
    if(btn){ btn.disabled=false; btn.textContent='删'; }
    alert('删除失败：'+e);
  }
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
      <div><div class="k">和你的关系</div><div class="v" style="font-size:13px;font-weight:400">${esc(s.relationship||'还没有复盘')}</div></div>
      <div><div class="k">主动唤醒</div><div class="v">${s.proactive?'<span class="badge ok">开</span>':'<span class="badge bad">关</span>'}</div></div>
    </div><div class="mut" style="margin-top:8px">${esc(s.activity||'')}</div></div>`;
    h+='<div class="card"><div class="k">操作</div><button onclick="restartBridge()">重启桥接</button> <span class="mut" style="margin-left:8px">重启后约 6 秒恢复</span></div>';
    $('#overview').innerHTML=h;
  }
  if(!$('#mood').hidden){
    const m=await j('/api/mood');
    const rel=m.relationship||{};
    const relText = rel.summary || '';
    const relBars = `<div style="margin-top:6px">${esc(relText||'还没有复盘。')}</div>
      <div class="mut" style="margin-top:8px">互动 ${Number(rel.interaction_count||0).toFixed(0)} 轮</div>`;
    let h=`<div class="card"><div class="k">现在的心情</div><div class="v" style="font-size:26px">${m.mood ?? '—'} <span class="mut" style="font-size:13px">/100</span> ${m.mood>=70?'😊':m.mood>=40?'🙂':'😔'}</div>
      <div class="bar" style="margin:10px 0"><i style="width:${m.mood ?? 0}%"></i></div>
      <div class="k">情绪值 ${Math.round((m.valence??0)*100)} · 唤醒 ${Math.round((m.arousal??0)*100)}%</div></div>`;
    h+=`<div class="card"><div class="k">和你的关系</div>${relBars}</div>`;
    h+=`<div class="card"><div class="k">她正在做什么</div><div>${esc(m.activity||'—')}</div></div>`;
    h+=`<div class="card"><div class="k">最近一次情绪的由头</div><div>${esc(m.emotion_label||'—')}${m.reason?('：'+esc(m.reason)):''}</div></div>`;
    h+=`<div class="card"><div class="k">情绪时间线（最近 ${m.timeline.length} 条）</div><div id="tl"></div></div>`;
    $('#mood').innerHTML=h;
    let tl='';
    for(const t of m.timeline){
      const time=t.at?new Date(t.at*1000).toLocaleString('zh-CN',{hour12:false}):'';
      tl+=`<div style="margin:8px 0;border-bottom:1px solid #1e252e;padding-bottom:6px"><span class="mut">${time}</span> <span class="badge ok">${esc(t.mood)}</span> ${t.source?`<span class="mut">${esc(t.source)}</span>`:''}<div>${esc(t.reason||'')}</div></div>`;
    }
    $('#tl').innerHTML=tl||'<span class="mut">还没有记录</span>';
  }
  if(!$('#memory').hidden){
    const m=await j('/api/memory');
    const st=m.stats||{};
    const tiers=st.tiers||{};
    const l3=st.l3_status||{};
    const stat=(label,n)=>`<div><div class="k">${label}</div><div class="v">${n||0}</div></div>`;
    let h=`<div class="card"><div class="k">记忆 · ${m.count} 条</div>
      <div class="grid" style="margin-top:8px">${stat('L1 总结',tiers.L1)}${stat('L2 判断',tiers.L2)}${stat('L3 事件',tiers.L3)}${stat('进行中',l3.open)}${stat('已结束',l3.closed)}${stat('片段',l3.standalone)}${stat('沉睡',l3.dormant)}${stat('L4 核心',tiers.L4)}</div>
      <div style="margin:10px 0"><input id="memq" placeholder="搜标题 / 内容…" style="background:#0b0f13;border:1px solid #232a33;color:#e6edf3;border-radius:8px;padding:7px 10px;width:260px" oninput="renderMem()"></div>
      <div style="margin:6px 0">
        <button onclick="memTier='';memStatus='';renderMem()">全部</button>
        <button onclick="memTier='L0';memStatus='';renderMem()">L0 原话</button>
        <button onclick="memTier='L1';memStatus='';renderMem()">L1 总结</button>
        <button onclick="memTier='L2';memStatus='';renderMem()">L2 判断</button>
        <button onclick="memTier='L3';memStatus='';renderMem()">L3 事件</button>
        <button onclick="memTier='L4';memStatus='';renderMem()">L4 核心</button>
      </div>
      <div id="memstatus" style="margin:6px 0;display:${memTier==='L3'?'block':'none'}">
        <button onclick="memTier='L3';memStatus='open';renderMem()">进行中</button>
        <button onclick="memTier='L3';memStatus='closed';renderMem()">已结束</button>
        <button onclick="memTier='L3';memStatus='standalone';renderMem()">片段</button>
        <button onclick="memTier='L3';memStatus='dormant';renderMem()">沉睡</button>
        <button onclick="memTier='L3';memStatus='archived';renderMem()">归档</button>
      </div>
      <div id="memlist"></div></div>`;
    $('#memory').innerHTML=h;
    window.__memItems=m.items||[];
    renderMem();
  }
  if(!$('#persona').hidden && !window.__coreLock){
    const p=await j('/api/persona');
    const st=await j('/api/style');
    let h=`<div class="card"><div class="k">人格设定</div>
      <div class="grid" style="margin-top:8px">
        <div><div class="k">我自己</div><div class="v">${((p.blocks||{}).self||[]).length} 小节</div></div>
        <div><div class="k">我和他</div><div class="v">${((p.blocks||{}).other||[]).length} 小节</div></div>
      </div></div>`;
    if(st.proposal && st.proposal.style){
      h+=`<div class="card" style="border-color:#d29922"><div class="k">风格提议（待确认）</div>
        <div class="mut" style="margin:6px 0">${esc(st.proposal.reason||'')}</div>
        <div class="section-title">现在</div>${mdToHtml(st.current||'')}
        <div class="section-title">提议</div>${mdToHtml(st.proposal.style||'')}
        <button onclick="applyStyle()">应用</button> <button onclick="dismissStyle()">忽略</button></div>`;
    }
    const blk=(p.blocks||{});
    const secHtml=(list)=>(list||[]).map(x=>`<div class="section-title">${esc(x.title)}</div>${x.body?mdToHtml(x.body):'<div class="mut">（空）</div>'}`).join('');
    h+=`<div class="card"><div class="k">我自己 <button style="float:right" onclick="editCore()">编辑</button></div>
      ${secHtml(blk.self)||'<div class="mut">（空）</div>'}
      <div id="coreEditWrap" hidden>
        <textarea id="coreText" onfocus="window.__coreLock=true" oninput="window.__coreLock=true" style="width:100%;height:340px;background:#0b0f13;border:1px solid #232a33;color:#e6edf3;border-radius:8px;padding:10px;font-family:ui-monospace,Consolas,monospace;font-size:13px;line-height:1.6">${esc(p.constitution||'')}</textarea>
        <div style="margin-top:8px"><button onclick="saveCore()">保存</button> <button onclick="cancelCore()">取消</button> <span id="coreMsg" class="mut"></span></div>
        <div class="mut" style="margin-top:6px">「我和他」那几节也在这份文档里，保存会一起写回。</div>
      </div></div>`;
    const otherOf=(t)=>(blk.other||[]).find(x=>x.title===t);
    const rel=p.recent_relationship||{};
    const relWhen=rel.date?rel.date:(rel.updated_at?new Date(Number(rel.updated_at)*1000).toLocaleString('zh-CN',{hour12:false}):"");
    h+=`<div class="card"><div class="k">我和他</div>
      <div class="section-title">我眼中的他 <button style="float:right" onclick="editPersonaField('user_profile')">编辑</button></div>
      <div id="profilePreview">${p.user_profile?mdToHtml(p.user_profile):'<div class="mut">（还没形成）</div>'}</div>
      <div id="profileEditWrap" hidden>
        <textarea id="profileText" style="width:100%;height:280px;background:#0b0f13;border:1px solid #232a33;color:#e6edf3;border-radius:8px;padding:10px;font-family:ui-monospace,Consolas,monospace;font-size:13px;line-height:1.6">${esc(p.user_profile||'')}</textarea>
        <div style="margin-top:8px"><button onclick="savePersonaField('user_profile')">保存</button> <button onclick="cancelPersonaField('user_profile')">取消</button> <span id="profileMsg" class="mut"></span></div>
        <div class="mut" style="margin-top:6px">只改「我眼中的他」，不会动核心设定。</div>
      </div>
      ${secHtml([otherOf('我们怎么对彼此')].filter(Boolean))}
      <div class="section-title">最近的关系 <span class="mut" style="font-weight:400">${esc(relWhen)}</span></div>
      <div>${rel.summary?mdToHtml(rel.summary):'<div class="mut">（还没复盘）</div>'}</div>
      ${secHtml([otherOf('我们之间有什么')].filter(Boolean))}
    </div>`;
    const rv=await j('/api/review');
    if((rv.items||[]).length){
      h+=`<div class="card" style="border-color:#d29922"><div class="k">人格复盘 · ${rv.count} 条待确认</div>`;
      for(const it of rv.items){
        h+=`<div style="margin:8px 0;border-bottom:1px solid #1e252e;padding-bottom:8px">
          <span class="badge ok">${esc(it.target)}</span> <b>${esc(it.op)}</b>
          ${it.from?`<div class="mut">旧：${esc(it.from)}</div>`:''}
          <div>新：${esc(it.text)}</div>
          <div class="mut">${esc(it.reason||'')}</div>
          <div style="margin-top:6px"><button onclick="reviewApply('${encodeURIComponent(it.id)}')">应用</button>
          <button onclick="reviewReject('${encodeURIComponent(it.id)}')">忽略</button></div>
        </div>`;
      }
      h+='</div>';
    }
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
    const threads=Array.isArray(n.open_threads)?n.open_threads:[];
    const statusCn={open:'进行中',closed:'已结束',standalone:'片段',dormant:'沉睡'};
    let h='';
    if(threads.length){
      h+=`<div class="card"><div class="k">还没完的事（${threads.length}）</div>`;
      for(const t of threads.slice(0,8)){
        const ts=Number(t.last_seen_at||0);
        const day=ts?new Date(ts*1000).toLocaleDateString('zh-CN'):'';
        h+=`<div style="margin:8px 0;border-bottom:1px solid #1e252e;padding-bottom:6px"><span class="badge ok">${esc(statusCn[t.status]||t.status||'')}</span> <b>${esc(t.title||'')}</b> <span class="mut">${esc(day)}</span> <button style="float:right" onclick="closeThread(${Number(t.id)||0}, this)">结束</button></div>`;
      }
      h+='</div>';
    }
    h+=`<div class="card"><div class="k">她的便签（${n.notes.length}）</div>`;
    if(!n.notes.length) h+='<div class="mut">还没有便签</div>';
    for(const note of n.notes) h+=`<div style="margin:8px 0;border-bottom:1px solid #1e252e;padding-bottom:6px"><span class="mut">${esc(note.date||'')}</span> ${esc(note.text||'')}</div>`;
    h+='</div>';
    h+=`<div class="card"><div class="k">任务（${n.tasks.length}）</div>`;
    if(!n.tasks.length) h+='<div class="mut">没有待办</div>';
    for(const t of n.tasks) h+=`<div style="margin:6px 0"><span class="tag">${t.done?'完成':'进行中'}</span> ${esc(t.text||'')}</div>`;
    h+='</div>';
    h+=`<div class="card"><div class="k">日记（${n.diary.length}）</div>`;
    if(!n.diary.length) h+='<div class="mut">今天还没写</div>';
    for(const d of n.diary){
      h+=`<div style="margin:10px 0"><span class="mut">${esc(d.date||'')}</span>`;
      if(d.text) h+=`<div style="margin-top:3px">${esc(d.text)}</div>`;
      if(d.changes) h+=`<div class="mut" style="margin-top:4px">最近在变：${esc(d.changes)}</div>`;
      if(d.open_questions) h+=`<div class="mut" style="margin-top:4px">还没想清：${esc(d.open_questions)}</div>`;
      if(d.tasks) h+=`<div class="mut" style="margin-top:4px">正在做：${esc(d.tasks)}</div>`;
      if(d.relationship) h+=`<div class="mut" style="margin-top:4px">那天的关系：${esc(d.relationship)}</div>`;
      h+='</div>';
    }
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
    window.__stickerData=Object.fromEntries(items.map(it=>[it.file,it]));
    let h='<div class="card"><div class="k">分类统计</div><div style="margin-top:8px">';
    for(const [k,v] of Object.entries(st.categories)) h+=`<span class="tag">${esc(k)} ${v.user}/${v.total}</span> `;
    h+='</div></div>';
    h+=`<div class="card"><div class="k">表情库（${items.length} 张）</div>${st.hidden_images?`<div class="mut" style="margin:4px 0">另有 ${st.hidden_images} 张旧图片没有表情标识，已隐藏。</div>`:''}
      <div class="sticker-toolbar">
        <button id="stickerSemanticsBtn" disabled onclick="stickerEditSemanticsSelected()">修改语义</button>
        <button id="stickerDeleteBtn" disabled onclick="stickerArmDelete()">删除</button>
        <span id="stickerSelHint" class="mut">先点一张表情</span>
      </div>
      <div class="items sticker-grid" style="margin-top:10px">`;
    for(let i=0;i<items.length;i++){
      const it=items[i];
      const shown=[it.label, it.caption].filter(Boolean).join(' · ');
      h+=`<div class="item sticker-item" data-file="${attr(it.file)}" data-name="${attr(shown || it.file)}" onclick="stickerSelect(this)">
        <img class="thumb" src="/api/sticker?file=${encodeURIComponent(it.file)}">
        <div class="sticker-label">${esc(it.label || '未命名')}</div>
        <div class="mut" style="font-size:12px">${it.meta_status === 'reviewed' ? '已整理' : '待整理'}</div>
        <div class="sticker-tags">${stickerFacetHtml(it)}</div>
        <button class="sticker-x" hidden onclick="stickerConfirmDelete(event,this)">×</button>
      </div>`;
    }
    h+='</div></div>';
    $('#stickers').innerHTML=h;
  }
  if(!$('#lexicon').hidden){
    const lx=await j('/api/lexicon');
    window.__lexEntries=lx.entries||[];
    let h=`<div class="card"><div class="k">词库 · ${window.__lexEntries.length} 条</div>
      <div style="margin:10px 0">
        <input id="lexTerm" placeholder="词" style="background:#0b0f13;border:1px solid #232a33;color:#e6edf3;border-radius:8px;padding:7px 10px;width:150px">
        <input id="lexMeaning" placeholder="意思" style="background:#0b0f13;border:1px solid #232a33;color:#e6edf3;border-radius:8px;padding:7px 10px;width:320px">
        <input id="lexAliases" placeholder="别名，逗号分隔（可选）" style="background:#0b0f13;border:1px solid #232a33;color:#e6edf3;border-radius:8px;padding:7px 10px;width:190px">
        <select id="lexCat" style="background:#0b0f13;border:1px solid #232a33;color:#e6edf3;border-radius:8px;padding:7px 10px"><option value="meme">网络梗</option><option value="buzzword">热门词</option><option value="fandom">角色/IP</option><option value="abbreviation">缩写</option><option value="slang">群黑话</option></select>
        <select id="lexStatus" style="background:#0b0f13;border:1px solid #232a33;color:#e6edf3;border-radius:8px;padding:7px 10px"><option value="stable">稳定</option><option value="hot">热门</option><option value="fresh">新词</option><option value="archived">过气</option></select>
        <button onclick="lexAdd()">添加</button>
      </div>
      <div style="margin:8px 0"><button onclick="lexFilter='all';renderLex()">全部</button> <button onclick="lexFilter='slang';renderLex()">群黑话</button> <button onclick="lexFilter='meme';renderLex()">网络梗</button> <button onclick="lexFilter='buzzword';renderLex()">热门词</button> <button onclick="lexFilter='fandom';renderLex()">角色/IP</button> <button onclick="lexFilter='abbreviation';renderLex()">缩写</button></div>
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
    if(f.activities && f.activities.length){
      h+=`<div class="card"><div class="k">刷完留下的记录（${f.activities.length}）</div>`;
      for(const a of f.activities){
        const t=Number(a.time||0)?new Date(Number(a.time)*1000).toLocaleString('zh-CN',{hour12:false}):'';
        h+=`<div style="margin:8px 0;border-bottom:1px solid #1e252e;padding-bottom:6px"><span class="mut">${esc(t)}</span> <span class="badge ok">B站</span> ${esc(a.detail||'')}`;
        if(a.summary) h+=`<div class="mut" style="margin-top:3px">讲了什么：${esc(a.summary)}</div>`;
        if(a.thought) h+=`<div class="mut" style="margin-top:3px">想法：${esc(a.thought)}</div>`;
if(a.insight) h+=`<div style="margin-top:3px">感悟：${esc(a.insight)}</div>`;
        if(a.l3_id) h+=`<div class="mut" style="margin-top:3px">已生成 L3 #${a.l3_id}</div>`;
        h+='</div>';
      }
      h+='</div>';
    }
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
async function reviewApply(id){ const r=await fetch('/api/review/apply',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id:decodeURIComponent(id)})}); const j=await r.json(); alert(j.ok?'已应用':(j.error||'应用失败')); load(); }
async function reviewReject(id){ const r=await fetch('/api/review/reject',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id:decodeURIComponent(id)})}); const j=await r.json(); if(!j.ok) alert(j.error||'操作失败'); load(); }
function setLog(n){ logName=n; load(); }
async function startQr(){ await fetch('/api/bili/qr/start',{method:'POST'}); setTimeout(load,1500); }
function stickerFacetHtml(it){
  const groups=[['identity',it.identity],['action',it.action],['expression',it.expression],['generic',it.generic]];
  const parts=[];
  for(const [kind,values] of groups){
    for(const value of (values||[]).slice(0,4)){
      parts.push(`<span class="tag facet-${kind}">${esc(value)}</span>`);
    }
  }
  return parts.length?parts.join(' '):'<span class="mut">未标注</span>';
}
let stickerSelected=null;
function stickerSelect(card){
  document.querySelectorAll('#stickers .sticker-item.selected').forEach(el=>el.classList.remove('selected'));
  document.querySelectorAll('#stickers .sticker-x').forEach(el=>el.hidden=true);
  card.classList.add('selected');
  stickerSelected={file:card.dataset.file,card};
  for(const id of ['stickerSemanticsBtn','stickerDeleteBtn']){
    const el=document.getElementById(id); if(el) el.disabled=false;
  }
  const hint=document.getElementById('stickerSelHint');
  if(hint) hint.textContent=`已选 ${card.dataset.name||card.dataset.file}`;
}
function stickerClearSelection(){
  document.querySelectorAll('#stickers .sticker-item.selected').forEach(el=>el.classList.remove('selected'));
  document.querySelectorAll('#stickers .sticker-x').forEach(el=>el.hidden=true);
  stickerSelected=null;
  for(const id of ['stickerSemanticsBtn','stickerDeleteBtn']){
    const el=document.getElementById(id); if(el) el.disabled=true;
  }
  const hint=document.getElementById('stickerSelHint');
  if(hint) hint.textContent='先点一张表情';
}
function stickerEditSemanticsSelected(){
  if(!stickerSelected){ alert('先点一张表情'); return; }
  const it=(window.__stickerData||{})[stickerSelected.file]||{};
  document.getElementById('stickerSemLabel').value=it.label||'';
  document.getElementById('stickerSemIdentity').value=(it.identity||[]).join(', ');
  document.getElementById('stickerSemAction').value=(it.action||[]).join(', ');
  document.getElementById('stickerSemExpression').value=(it.expression||[]).join(', ');
  document.getElementById('stickerSemGeneric').value=(it.generic||[]).join(', ');
  document.getElementById('stickerSemanticModal').hidden=false;
  setTimeout(()=>document.getElementById('stickerSemLabel').focus(),0);
}
function stickerSemanticClose(){
  document.getElementById('stickerSemanticModal').hidden=true;
}
async function stickerSemanticSave(){
  if(!stickerSelected) return;
  const split=(id)=>document.getElementById(id).value.split(/[,，、\s]+/).map(x=>x.trim()).filter(Boolean);
  const body={
    file:stickerSelected.file,
    label:document.getElementById('stickerSemLabel').value.trim(),
    identity:split('stickerSemIdentity'),
    action:split('stickerSemAction'),
    expression:split('stickerSemExpression'),
    generic:split('stickerSemGeneric'),
  };
  const r=await fetch('/api/stickers/semantics',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  const j=await r.json();
  if(!j.ok){ alert(j.error||'保存失败'); return; }
  stickerSemanticClose();
  stickerClearSelection();
  load();
}
function stickerArmDelete(){
  if(!stickerSelected){ alert('先点一张表情'); return; }
  document.querySelectorAll('#stickers .sticker-x').forEach(el=>el.hidden=true);
  const x=stickerSelected.card.querySelector('.sticker-x');
  if(x) x.hidden=false;
  const hint=document.getElementById('stickerSelHint');
  if(hint) hint.textContent='再点 × 确认删除';
}
async function stickerConfirmDelete(ev,btn){
  if(ev) ev.stopPropagation();
  if(!stickerSelected) return;
  const file=stickerSelected.file;
  const r=await fetch('/api/stickers/delete',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({file})});
  const j=await r.json();
  if(!j.ok){ alert(j.error||'删除失败'); return; }
  stickerClearSelection();
  load();
}
// 表情/词库有输入框，不参与 10 秒轮询，避免把正在输入的内容顶掉
setInterval(()=>{
  if(curSub==='stickers' || curSub==='lexicon') return;
  const el=document.activeElement;
  if(el && ['INPUT','TEXTAREA','SELECT'].includes(el.tagName)) return;
  load();
},10000);
load();
