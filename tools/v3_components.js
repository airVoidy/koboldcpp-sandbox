/**
 * v3_components.js — Rich component library for workflow-v3
 *
 * Registers into the global V3C (must be loaded after the core V3C script).
 * These are optional — without this file, all slots render via schema-view.
 * With this file, slots can use: header, text, tags, status, image, list,
 * badge, button, reactions, actions, thread, table.
 */
(function() {
'use strict';
if (!window.V3C) { console.warn('v3_components.js: V3C not found, skipping'); return; }
const R = V3C.register, _esc = V3C._esc, _truncate = V3C._truncate;
const _statusColors = { done:'green', active:'accent', pending:'text-dim', failed:'red', pass:'green', fail:'red' };

R('header', {
  schema: { icon:{type:'string',default:'#',doc:'Icon'}, title:{type:'string',default:'',doc:'Title'}, status:{type:'string',default:'',doc:'Status'}, time:{type:'string',default:'',doc:'Time'} },
  fieldMap: { icon:'icon', title:'title', status:'status', time:'time' },
  render(p) {
    return `<span class="node-icon">${_esc(p.icon)}</span><span class="node-title">${_esc(p.title)}</span>`
      + (p.time ? `<span class="slot-time">${_esc(p.time)}</span>` : '')
      + (p.status ? `<span class="node-badge ${_esc(p.status)}">${_esc(p.status)}</span>` : '');
  },
  ascii(p, w) { return [` ${p.icon||'#'} ${_truncate(p.title||'',w-12)} ${p.status?'['+p.status+']':''}`]; },
});

R('text', {
  schema: { text:{type:'string',default:'',doc:'Content'}, label:{type:'string',default:'',doc:'Label'} },
  fieldMap: { text:'answer' },
  render(p) {
    const e = p.text ? '' : ' empty';
    return `<div class="node-slot slot-text">`
      + (p.label ? `<div class="slot-label">${_esc(p.label)}</div>` : '')
      + `<textarea readonly class="esc${e}">${_esc(p.text)}</textarea></div>`;
  },
  ascii(p, w) { const l=[]; if(p.label) l.push(`── ${p.label} ──`); const t=String(p.text||'(empty)'); for(let i=0;i<t.length;i+=w-2) l.push(t.slice(i,i+w-2)); return l; },
});

R('tags', {
  schema: { tags:{type:'object',default:{},doc:'Key-value pairs'} },
  fieldMap: { tags:'tags' },
  render(p) {
    const t=p.tags||{}, k=Object.keys(t);
    if (!k.length) return '';
    return `<div class="node-slot slot-tags">${k.map(k=>`<span class="slot-tag">${_esc(k)}: ${_esc(_truncate(String(t[k]),40))}</span>`).join('')}</div>`;
  },
  ascii(p, w) { const t=p.tags||{}, k=Object.keys(t); return k.map(k=>` ${k}: ${_truncate(String(t[k]),w-k.length-4)}`); },
});

R('status', {
  schema: { value:{type:'string',default:'',doc:'Status value'}, label:{type:'string',default:'',doc:'Label'} },
  fieldMap: { value:'status' },
  render(p) {
    const c = _statusColors[String(p.value||'').toLowerCase()] || 'text-dim';
    return `<div class="node-slot" style="font-size:10px;">`
      + (p.label ? `<span style="color:var(--text-dim);">${_esc(p.label)}: </span>` : '')
      + `<span style="color:var(--${c});font-weight:600;">${_esc(p.value)}</span></div>`;
  },
  ascii(p) { return [` ${p.label?p.label+': ':''}${p.value||'-'}`]; },
});

R('image', {
  schema: { src:{type:'string',default:'',doc:'URL'}, label:{type:'string',default:'',doc:'Caption'} },
  fieldMap: { src:'image' },
  render(p) {
    if (!p.src) return '';
    return `<div class="node-slot slot-image">`
      + (p.label ? `<div class="slot-label">${_esc(p.label)}</div>` : '')
      + `<img src="${_esc(p.src)}" style="max-width:100%;border-radius:3px;" /></div>`;
  },
  ascii(p, w) { return p.src ? [` [IMG: ${_truncate(p.src,w-8)}]`] : []; },
});

R('list', {
  schema: { items:{type:'array',default:[],doc:'List items'}, label:{type:'string',default:'',doc:'Header'}, color:{type:'string',default:'',doc:'CSS var'} },
  fieldMap: {},
  render(p) {
    const i=p.items||[]; if (!i.length) return '';
    const cs = p.color ? `color:var(--${p.color})` : '';
    return `<div class="node-slot"><div class="slot-list-hdr" style="${cs}">&#9654; ${_esc(p.label)} <span style="opacity:.5">${i.length}</span></div>`
      + `<div class="slot-list-body open">${i.map(x=>`<div class="slot-list-item" style="${cs}">&#8226; ${_esc(typeof x==='string'?x:x.text||x.title||x.name||JSON.stringify(x))}</div>`).join('')}</div></div>`;
  },
  ascii(p, w) { const i=p.items||[]; if(!i.length) return []; const l=[]; if(p.label) l.push(` ▸ ${p.label} (${i.length})`); for(const x of i.slice(0,8)) l.push(`   • ${_truncate(typeof x==='string'?x:x.text||x.title||'...',w-6)}`); if(i.length>8) l.push(`   ...+${i.length-8}`); return l; },
});

R('badge', {
  schema: { text:{type:'string',default:'',doc:'Text'}, cls:{type:'string',default:'',doc:'CSS class'} },
  fieldMap: {},
  render(p) { return `<span class="node-badge ${_esc(p.cls)}">${_esc(p.text)}</span>`; },
  ascii(p) { return [`[${p.text||''}]`]; },
});

R('button', {
  schema: { label:{type:'string',default:'action',doc:'Label'}, action:{type:'string',default:'',doc:'Action'}, color:{type:'string',default:'',doc:'Color'} },
  fieldMap: {},
  render(p) { return `<button class="btn sm" data-action="${_esc(p.action||p.label)}" style="${p.color?'color:var(--'+p.color+')':''}">${_esc(p.label)}</button>`; },
  ascii(p) { return [`[${p.label||'btn'}]`]; },
});

R('reactions', {
  schema: { items:{type:'array',default:[],doc:'{emoji,worker,status,detail}'} },
  fieldMap: { items:'reactions' },
  render(p) {
    const i=p.items||[]; if (!i.length) return '';
    const ps=i.filter(r=>r.status==='pass').length;
    return `<div class="node-slot slot-reactions">${i.map(r=>`<span class="reaction ${_esc(r.status||'pending')}" title="${_esc(r.detail||'')}"><span class="reaction-emoji">${r.emoji||'\u2753'}</span><span class="reaction-who ${_esc(r.status||'pending')}">${_esc(r.worker||'')}</span></span>`).join('')}<span class="reactions-summary"><span class="count ${ps===i.length?'ok':'bad'}">${ps}/${i.length}</span></span></div>`;
  },
  ascii(p, w) { const i=p.items||[]; if(!i.length) return []; const ps=i.filter(r=>r.status==='pass').length; return [` ${i.map(r=>(r.emoji||'?')+(r.worker?':'+_truncate(r.worker,6):'')).join(' ')} [${ps}/${i.length}]`]; },
});

R('actions', {
  schema: { items:{type:'array',default:[],doc:'{label,action,color} or string'} },
  fieldMap: {},
  render(p) {
    const i=(p.items||[]).map(b=>typeof b==='string'?{label:b}:b);
    return `<div class="node-slot slot-actions">${i.map(b=>`<button class="btn sm" data-action="${_esc(b.action||b.label)}" style="${b.color?'color:var(--'+b.color+')':''}">${_esc(b.label)}</button>`).join('')}</div>`;
  },
  ascii(p) { return [` ${(p.items||[]).map(b=>'['+(typeof b==='string'?b:b.label)+']').join(' ')}`]; },
});

R('thread', {
  schema: { items:{type:'array',default:[],doc:'{name|role,content}'}, label:{type:'string',default:'Thread',doc:'Header'} },
  fieldMap: { items:'thread' },
  render(p) {
    const i=p.items||[]; if (!i.length) return '';
    return `<div class="node-slot slot-thread"><div class="slot-thread-hdr">&#9654; ${_esc(p.label)} <span style="opacity:.5">${i.length}</span></div>`
      + `<div class="slot-thread-body open">${i.map(m=>{const w=m.name||m.role||'system'; return `<div class="tmsg"><span class="tmsg-avatar">${w[0].toUpperCase()}</span><span class="tmsg-who">${_esc(w)}</span><span class="tmsg-text">${_esc(m.content||'')}</span></div>`;}).join('')}</div></div>`;
  },
  ascii(p, w) { const i=p.items||[]; if(!i.length) return []; const l=[` ▸ ${p.label||'Thread'} (${i.length})`]; for(const m of i.slice(0,5)){const w2=m.name||m.role||'sys'; l.push(`   ${w2[0].toUpperCase()}│${_truncate(w2,8)}: ${_truncate(m.content||'',w-16)}`);} if(i.length>5) l.push(`   ...+${i.length-5}`); return l; },
});

R('table', {
  schema: { rows:{type:'array',default:[],doc:'Row arrays'}, headers:{type:'array',default:[],doc:'Column headers'}, label:{type:'string',default:'',doc:'Caption'} },
  fieldMap: {},
  render(p) {
    const r=p.rows||[], h=p.headers||[];
    if (!r.length) return '';
    return `<div class="node-slot slot-table">`
      + (p.label ? `<div class="slot-label">${_esc(p.label)}</div>` : '')
      + `<table class="v3-table">`
      + (h.length ? `<tr>${h.map(c=>`<th>${_esc(c)}</th>`).join('')}</tr>` : '')
      + r.map(row=>`<tr>${(Array.isArray(row)?row:[row]).map(c=>`<td>${_esc(String(c))}</td>`).join('')}</tr>`).join('')
      + `</table></div>`;
  },
  ascii(p, w) { const r=p.rows||[]; if(!r.length) return []; const l=[]; if(p.headers) l.push('  '+p.headers.map(h=>_truncate(String(h),10).padEnd(10)).join(' ').slice(0,w-2)); for(const row of r.slice(0,8)) l.push('  '+(Array.isArray(row)?row:[row]).map(c=>_truncate(String(c),10).padEnd(10)).join(' ').slice(0,w-2)); if(r.length>8) l.push(`  ...+${r.length-8} rows`); return l; },
});

console.log('v3_components.js: registered', V3C.list().filter(n => n !== 'schema').length, 'rich components');
})();
