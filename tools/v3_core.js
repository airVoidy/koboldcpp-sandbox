// ══════════════════════════════════════════════════════════
//  V3 CORE — shared between workflow_v3.html and component_builder.html
//  V3C registry, Assembly VM, Skeleton Renderer, Component State
// ══════════════════════════════════════════════════════════
(function(root) {
'use strict';

// ── V3C Component Registry ──────────────────────────────
const _components = {};
const _esc = s => String(s ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
const _statusColors = { done:'green', active:'accent', pending:'text-dim', failed:'red', pass:'green', fail:'red' };
function register(name, def) {
  _components[name] = {
    schema: def.schema||{}, jsonSchema: def.jsonSchema||null, fieldMap: def.fieldMap||{},
    render: def.render||(()=>''), ascii: def.ascii||((p,w)=>['']),
    clientSchema: def.clientSchema||null, assemblySnippet: def.assemblySnippet||null, layout: def.layout||null,
  };
}
function get(name) { return _components[name]||null; }
function list() { return Object.keys(_components); }
function schema(name) { return _components[name]?.schema||{}; }
function _legacyToTemplate(legacy) {
  const tpl = {};
  for (const [k, fd] of Object.entries(legacy)) {
    const t = fd.type || 'string';
    if (t === 'array') tpl[k] = [];
    else if (t === 'object') tpl[k] = {};
    else if (t === 'number') tpl[k] = 'number';
    else if (t === 'boolean') tpl[k] = 'boolean';
    else tpl[k] = 'string';
  }
  return tpl;
}
function template(name) {
  const c = _components[name]; if (!c) return {};
  if (c._template) return c._template;
  c._template = _legacyToTemplate(c.schema);
  return c._template;
}
function jsonSchema(name) { return template(name); }
function resolve(name, rawData, overrides) {
  const comp = _components[name]; if (!comp) return {};
  const props = {}, fmap = { ...comp.fieldMap, ...(overrides||{}) };
  for (const [k, fd] of Object.entries(comp.schema)) {
    const paths = String(fmap[k]||k).split('|').map(s=>s.trim()); let val;
    for (const p of paths) { val = _gp(rawData, p); if (val != null && val !== '') break; }
    if (val == null && 'default' in fd) val = fd.default;
    props[k] = val;
  }
  return props;
}
function _gp(o, p) { if (!o||!p) return; const pp=p.split('.'); let v=o; for (const s of pp) { if (v==null||typeof v!=='object') return; v=v[s]; } return v; }
function render(name, props) { const c=_components[name]; return c ? c.render(props) : `<div>[?${_esc(name)}]</div>`; }
function ascii(name, props, w) { const c=_components[name]; return c ? c.ascii(props, w||40) : [`[?${name}]`]; }
function _pad(s, w) { return (s+' '.repeat(w)).slice(0,w); }
function _truncate(s, m) { s=String(s??''); return s.length>m ? s.slice(0,m-1)+'…' : s; }
function _box(lines, w) { const o=['┌'+'─'.repeat(w-2)+'┐']; for (const l of lines) o.push('│'+_pad(l,w-2)+'│'); o.push('└'+'─'.repeat(w-2)+'┘'); return o; }

// Schema-view: universal JSON renderer
register('schema', { schema: { data:{type:'object',default:{},doc:'Any JSON data'} }, fieldMap:{},
  render(p) {
    function rv(v, depth) {
      if (v == null) return `<span style="color:var(--text-dim);font-style:italic;">(empty)</span>`;
      if (typeof v === 'boolean') return `<span style="color:var(--${v?'green':'red'});">${v}</span>`;
      if (typeof v === 'number') return `<span style="color:var(--accent3);">${v}</span>`;
      if (typeof v === 'string') {
        if (!v) return `<span style="color:var(--text-dim);font-style:italic;">""</span>`;
        const s = v.length > 120 ? _esc(v.slice(0,117)) + '...' : _esc(v);
        return `<span style="color:var(--text);">${s}</span>`;
      }
      if (Array.isArray(v)) {
        if (!v.length) return `<span style="color:var(--text-dim);">[]</span>`;
        if (depth > 2) return `<span style="color:var(--text-dim);">[${v.length}]</span>`;
        return `<div style="padding-left:10px;">${v.map((x,i) => `<div style="margin:1px 0;"><span style="color:var(--text-dim);">${i}:</span> ${rv(x, depth+1)}</div>`).join('')}</div>`;
      }
      if (typeof v === 'object') {
        const keys = Object.keys(v);
        if (!keys.length) return `<span style="color:var(--text-dim);">{}</span>`;
        if (depth > 2) return `<span style="color:var(--text-dim);">{${keys.length}}</span>`;
        return `<div style="padding-left:10px;">${keys.map(k => `<div style="margin:1px 0;"><span style="color:var(--accent2);">${_esc(k)}</span>: ${rv(v[k], depth+1)}</div>`).join('')}</div>`;
      }
      return `<span>${_esc(String(v))}</span>`;
    }
    const keys = Object.keys(p);
    if (!keys.length) return `<div class="node-slot" style="font-size:9px;color:var(--text-dim);padding:4px 6px;">(no data)</div>`;
    return `<div class="node-slot" style="font-size:9px;padding:4px 6px;">${keys.map(k => `<div style="margin:1px 0;"><span style="color:var(--accent2);font-weight:600;">${_esc(k)}</span>: ${rv(p[k], 0)}</div>`).join('')}</div>`;
  },
  ascii(p,w) { const keys=Object.keys(p); return keys.map(k=>` ${k}: ${_truncate(JSON.stringify(p[k]),w-k.length-4)}`); }
});

const V3C = { register, get, list, schema, template, jsonSchema, resolve, render, ascii, _esc, _box, _pad, _truncate, _components, _statusColors };
root.V3C = V3C;

// ── Assembly VM ─────────────────────────────────────────
function asmTokenize(line) {
  const tokens = []; let i = 0;
  while (i < line.length) {
    if (line[i] === ' ' || line[i] === '\t' || line[i] === ',') { i++; continue; }
    if (line[i] === ';') break;
    if (line[i] === '"' || line[i] === "'") {
      const q = line[i]; i++; let s = '';
      while (i < line.length && line[i] !== q) { s += line[i]; i++; }
      if (i < line.length) i++;
      tokens.push(s);
    } else {
      let s = '';
      while (i < line.length && line[i] !== ' ' && line[i] !== '\t' && line[i] !== ',') { s += line[i]; i++; }
      tokens.push(s);
    }
  }
  return tokens;
}

function asmResolve(token, state) {
  if (token === '_') return undefined;
  if (token === 'true') return true;
  if (token === 'false') return false;
  if (token.startsWith('@')) {
    const parts = token.slice(1).split('.');
    let val = state[parts[0]];
    for (let i = 1; i < parts.length; i++) { if (val == null || typeof val !== 'object') return undefined; val = val[parts[i]]; }
    return val;
  }
  if (token.startsWith('+')) { const n = parseInt(token.slice(1)); return isNaN(n) ? token : n; }
  if (token.startsWith('{') || token.startsWith('[')) { try { return JSON.parse(token); } catch(_) {} }
  const n = Number(token); if (!isNaN(n) && token !== '') return n;
  return token;
}

function asmStore(state, ref, value) {
  if (!ref || ref === '_') return;
  const name = ref.startsWith('@') ? ref.slice(1) : ref;
  const parts = name.split('.');
  if (parts.length === 1) { state[parts[0]] = value; return; }
  let obj = state[parts[0]];
  if (obj == null || typeof obj !== 'object') { state[parts[0]] = {}; obj = state[parts[0]]; }
  for (let i = 1; i < parts.length - 1; i++) { if (obj[parts[i]] == null || typeof obj[parts[i]] !== 'object') obj[parts[i]] = {}; obj = obj[parts[i]]; }
  obj[parts[parts.length - 1]] = value;
}

// Builtins for CALL opcode
const _builtins = {
  get(a) { return a[0] != null ? a[0][a[1]] : undefined; },
  set(a) { if (a[0] != null) a[0][a[1]] = a[2]; },
  fmt(a) { let s = String(a[0] || ''); for (let i = 1; i < a.length; i++) s = s.replace(`{${i-1}}`, String(a[i] ?? '')); return s; },
  concat(a) { return String(a[0] ?? '') + String(a[1] ?? ''); },
  len(a) { return Array.isArray(a[0]) ? a[0].length : 0; },
  add(a) { return (+a[0] || 0) + (+a[1] || 0); },
  pluck(a) { return Array.isArray(a[0]) ? a[0].map(i => i != null ? i[a[1]] : undefined).filter(v => v != null) : []; },
  map_fmt(a) { const arr = a[0], tpl = String(a[1] || '{0}'); return Array.isArray(arr) ? arr.map(item => { let s = tpl; if (typeof item === 'object') { for (const [k,v] of Object.entries(item)) s = s.replace(`{${k}}`, String(v??'')); } else { s = s.replace('{0}', String(item??'')); } return s; }) : []; },
  default(a) { return a[0] != null && a[0] !== '' ? a[0] : a[1]; },
  keys(a) { return a[0] != null && typeof a[0] === 'object' ? Object.keys(a[0]) : []; },
  json(a) { try { return JSON.stringify(a[0], null, 2); } catch(_) { return String(a[0]); } },
  slice(a) { return Array.isArray(a[0]) ? a[0].slice(+a[1]||0, a[2]!=null?+a[2]:undefined) : String(a[0]||'').slice(+a[1]||0, a[2]!=null?+a[2]:undefined); },

  // tpl(type, ...args) — render a component inline
  tpl(a) {
    const type = a[0];
    if (type === 'raw') return String(a[1] ?? '');
    const data = {};
    switch (type) {
      case 'header':    data.icon = a[1]; data.title = a[2]; data.status = a[3]; break;
      case 'text':      data.text = a[1]; data.label = a[2]; break;
      case 'tags':      data.tags = a[1]; break;
      case 'list':      data.items = a[1]; data.label = a[2]; data.color = a[3]; break;
      case 'badge':     data.text = a[1]; data.cls = a[2]; break;
      case 'image':     data.src = a[1]; data.label = a[2]; break;
      case 'status':    data.value = a[1]; data.label = a[2]; break;
      case 'button':    data.label = a[1]; data.action = a[2]; data.color = a[3]; break;
      case 'reactions': data.items = a[1]; break;
      case 'actions':   data.items = a[1]; break;
      case 'thread':    data.items = a[1]; data.label = a[2]; break;
      case 'table':     data.rows = a[1]; data.headers = a[2]; break;
    }
    return renderComponent(type, data);
  },

  // card(template_name, node_data) — render through template assemblers
  // NOTE: requires assembleSlots to be defined on root (set by workflow_v3.html)
  card(a) {
    if (!root._assembleSlots) return '[card: no assembler]';
    const tplName = typeof a[0] === 'string' ? a[0] : 'job';
    const rawData = a[1] || {};
    const node = { id: rawData.id || '', data: rawData, children: [] };
    const slots = root._assembleSlots(node, tplName, tplName);
    return slots.map(s => renderComponent(s.type, s.data)).join('');
  },

  append(a) { return String(a[0] ?? '') + String(a[1] ?? ''); },
};

function execAsm(code, extraState) {
  if (!code || !code.trim()) return {};
  const state = { ...extraState };
  const lines = code.split('\n');
  const labels = {};
  for (let i = 0; i < lines.length; i++) { const l = lines[i].trim(); if (l.startsWith(':')) labels[l] = i; }
  let ip = 0; const max = lines.length * 50; let steps = 0;
  while (ip < lines.length && steps < max) {
    steps++;
    const line = lines[ip].trim();
    if (!line || line.startsWith(';') || line.startsWith(':') || line.startsWith('#')) { ip++; continue; }
    const tokens = asmTokenize(line);
    if (!tokens.length) { ip++; continue; }
    const op = tokens[0];
    if (op === 'MOV') { asmStore(state, tokens[1], asmResolve(tokens[2], state)); ip++; }
    else if (op === 'CALL') {
      const dst = tokens[1], fn = tokens[2], args = tokens.slice(3).map(t => asmResolve(t, state));
      const b = _builtins[fn];
      if (b) { const r = b(args); if (dst !== '_') asmStore(state, dst, r); }
      ip++;
    }
    else if (op === 'EACH') {
      const itemRef = tokens[1], list = asmResolve(tokens[2], state), bodyLen = asmResolve(tokens[3], state);
      if (Array.isArray(list) && bodyLen > 0) {
        const bodyCode = lines.slice(ip+1, ip+1+bodyLen).join('\n');
        for (let idx = 0; idx < list.length; idx++) {
          asmStore(state, itemRef, list[idx]);
          state['each_idx'] = idx;
          const sub = execAsm(bodyCode, state);
          Object.assign(state, sub);
        }
      }
      ip += 1 + (bodyLen || 0);
    }
    else if (op === 'CMP') {
      const cmpOp = tokens[2], a = asmResolve(tokens[3], state), b = asmResolve(tokens[4], state);
      let r = false;
      if (cmpOp === 'eq') r = a == b; else if (cmpOp === 'ne') r = a != b;
      else if (cmpOp === 'gt') r = a > b; else if (cmpOp === 'lt') r = a < b;
      asmStore(state, tokens[1], r); ip++;
    }
    else if (op === 'JIF') {
      const cond = asmResolve(tokens[1], state), target = tokens[2];
      if (cond) {
        if (target.startsWith(':') && labels[target] !== undefined) ip = labels[target];
        else ip += (typeof asmResolve(target, state) === 'number' ? asmResolve(target, state) : 1);
      } else { ip++; }
    }
    else { ip++; }
  }
  return state;
}

root.asmTokenize = asmTokenize;
root.asmResolve = asmResolve;
root.asmStore = asmStore;
root.execAsm = execAsm;
root._builtins = _builtins;

// ── Skeleton Renderer ───────────────────────────────────

function _renderSkeletonValue(val) {
  if (val === undefined || val === null) return '<span style="color:var(--text-dim);font-style:italic;">(empty)</span>';
  if (typeof val === 'boolean') return `<span style="color:var(--${val ? 'green' : 'red'});">${val}</span>`;
  if (typeof val === 'number') return `<span style="color:var(--accent3);">${val}</span>`;
  if (typeof val === 'string') return val ? _esc(val.length > 80 ? val.slice(0, 77) + '...' : val) : '<span style="color:var(--text-dim);">""</span>';
  if (Array.isArray(val)) return `<span style="color:var(--text-dim);">[${val.length}]</span>`;
  if (typeof val === 'object') return `<span style="color:var(--text-dim);">{${Object.keys(val).join(', ')}}</span>`;
  return _esc(String(val));
}

function _renderSkeletonCell(field, val, js) {
  // Array → repeat block
  if (Array.isArray(val)) {
    const itemSchema = js?.properties?.[field]?.items?.properties || {};
    const itemFields = Object.keys(itemSchema);
    let h = `<td data-field="${_esc(field)}" style="padding:0;">`;
    h += `<div class="skel-label" style="padding:2px 6px;">${_esc(field)} [${val.length}]</div>`;
    if (val.length === 0) {
      h += `<div class="skel-value" style="padding:2px 6px;color:var(--text-dim);font-style:italic;">(empty array)</div>`;
    } else {
      h += `<table class="skel-table" style="margin:0;">`;
      for (let i = 0; i < val.length; i++) {
        const item = val[i];
        h += `<tr>`;
        if (typeof item === 'object' && item !== null) {
          const fields = itemFields.length ? itemFields : Object.keys(item);
          for (const k of fields) {
            h += `<td><div class="skel-label">${_esc(k)}</div><div class="skel-value">${_renderSkeletonValue(item[k])}</div></td>`;
          }
        } else {
          h += `<td><div class="skel-label">[${i}]</div><div class="skel-value">${_renderSkeletonValue(item)}</div></td>`;
        }
        h += `</tr>`;
      }
      h += `</table>`;
    }
    h += `</td>`;
    return h;
  }
  // Object → nested key-value
  if (typeof val === 'object' && val !== null) {
    let h = `<td data-field="${_esc(field)}">`;
    h += `<div class="skel-label">${_esc(field)}</div>`;
    h += `<div class="skel-value">`;
    for (const [k, v] of Object.entries(val)) {
      h += `<div><span style="color:var(--accent2);font-size:8px;">${_esc(k)}:</span> ${_renderSkeletonValue(v)}</div>`;
    }
    h += `</div></td>`;
    return h;
  }
  // Primitive
  return `<td data-field="${_esc(field)}"><div class="skel-label">${_esc(field)}</div><div class="skel-value">${_renderSkeletonValue(val)}</div></td>`;
}

function renderSkeletonFromLayout(layout, data, schema) {
  if (!layout || !layout.rows) return '';
  let html = '<table class="skel-table">';
  for (const row of layout.rows) {
    const cells = row.cells.filter(f => data[f] !== undefined);
    if (!cells.length) continue;
    html += '<tr>';
    for (const field of cells) {
      html += _renderSkeletonCell(field, data[field], schema);
    }
    html += '</tr>';
  }
  html += '</table>';
  return `<div class="node-slot">${html}</div>`;
}

function renderComponent(type, data, style, viewName) {
  const comp = V3C.get(type) || V3C.get('schema');
  if (!comp) return `<div class="node-slot">[no renderer]</div>`;
  const vn = viewName || (type + '/default');
  const view = _clientViews[vn];
  if (view && view.assembly && view.layout) {
    const state = execAsm(view.assembly, { server: data || {} });
    const clientData = {};
    for (const [k, v] of Object.entries(state)) {
      if (k !== 'server' && k !== 'each_idx' && !k.startsWith('_')) clientData[k] = v;
    }
    return renderSkeletonFromLayout(view.layout, clientData, view.clientTemplate);
  }
  return comp.render(data || {}, style);
}

root.renderSkeletonFromLayout = renderSkeletonFromLayout;
root.renderComponent = renderComponent;
root._renderSkeletonValue = _renderSkeletonValue;
root._renderSkeletonCell = _renderSkeletonCell;

// ── Sample Data Generation ──────────────────────────────

function _genSample(name, tplVal, depth) {
  if (tplVal === 'string' || tplVal === '') return name + '.sample';
  if (tplVal === 'number') return 42;
  if (tplVal === 'boolean') return true;
  if (Array.isArray(tplVal)) {
    const items = [];
    const itemTpl = tplVal[0];
    for (let i = 0; i < 3; i++) {
      if (itemTpl && typeof itemTpl === 'object' && depth < 2) {
        const o = {};
        for (const [k, v] of Object.entries(itemTpl)) {
          const base = _genSample(k, v, depth + 1);
          o[k] = typeof base === 'string' ? `${base}_${i + 1}` : base;
        }
        items.push(o);
      } else {
        items.push(`${name}.item_${i + 1}`);
      }
    }
    return items;
  }
  if (typeof tplVal === 'object' && tplVal !== null) {
    if (depth >= 2) return { key: name + '.sample' };
    const o = {};
    for (const [k, v] of Object.entries(tplVal)) o[k] = _genSample(k, v, depth + 1);
    return o;
  }
  return name + '.sample';
}

function _generateSampleJson(compName) {
  const tpl = V3C.template(compName);
  const sample = {};
  for (const [k, v] of Object.entries(tpl)) {
    sample[k] = _genSample(k, v, 0);
  }
  return JSON.stringify(sample, null, 2);
}

root._genSample = _genSample;
root._generateSampleJson = _generateSampleJson;

// ── Custom Components & Client Views (shared state) ─────

const _customComponents = {};
const _clientViews = {};

function _registerCustomComponent(name, tpl) {
  if (tpl && tpl.type === 'object' && tpl.properties) {
    const converted = {};
    for (const [k, p] of Object.entries(tpl.properties)) {
      if (p.type === 'array') converted[k] = p.items?.properties ? [Object.fromEntries(Object.entries(p.items.properties).map(([sk,sv]) => [sk, sv.type || 'string']))] : [];
      else if (p.type === 'object') converted[k] = {};
      else converted[k] = p.type || 'string';
    }
    tpl = converted;
  }
  const existing = _customComponents[name] || {};
  _customComponents[name] = { ...existing, template: tpl };
  const legacy = {};
  for (const [k, v] of Object.entries(tpl)) {
    if (typeof v === 'string') legacy[k] = { type: v || 'string' };
    else if (Array.isArray(v)) legacy[k] = { type: 'array' };
    else if (typeof v === 'object') legacy[k] = { type: 'object' };
    else legacy[k] = { type: 'string' };
  }
  const schemaRenderer = V3C.get('schema');
  V3C.register(name, {
    schema: legacy,
    render(props) { return schemaRenderer.render(props); },
    ascii(props, w) { return schemaRenderer.ascii(props, w); },
  });
}

function _saveCustomComponents() {
  localStorage.setItem('v3_custom_components', JSON.stringify(_customComponents));
}

function _saveClientViews() {
  localStorage.setItem('v3_client_views', JSON.stringify(_clientViews));
}

// Load from localStorage
try {
  const cc = JSON.parse(localStorage.getItem('v3_custom_components'));
  if (cc) for (const [name, def] of Object.entries(cc)) {
    const tpl = def.template || def.jsonSchema || (def.fields ? Object.fromEntries(Object.entries(def.fields).map(([k,v]) => [k, v.type||'string'])) : { data: 'string' });
    _registerCustomComponent(name, tpl);
    if (def.assemblySnippet || def.clientSchema || def.layout) {
      _clientViews[name + '/default'] = {
        component: name,
        clientTemplate: def.clientSchema || def.clientTemplate || null,
        assembly: def.assemblySnippet || '',
        layout: def.layout || null,
      };
    }
  }
} catch(_) {}

try {
  const cv = JSON.parse(localStorage.getItem('v3_client_views'));
  if (cv) Object.assign(_clientViews, cv);
} catch(_) {}

root._customComponents = _customComponents;
root._clientViews = _clientViews;
root._registerCustomComponent = _registerCustomComponent;
root._saveCustomComponents = _saveCustomComponents;
root._saveClientViews = _saveClientViews;

// ── Card Templates (shared state) ───────────────────────

const _cardTemplates = {};

function _saveCardTemplates() {
  localStorage.setItem('v3_card_templates', JSON.stringify(_cardTemplates));
}

// Load from localStorage
try {
  const ct = JSON.parse(localStorage.getItem('v3_card_templates'));
  if (ct) Object.assign(_cardTemplates, ct);
} catch(_) {}

// Assemble card: run assembly per slot, return [{type, id, data, clientSchema, warnings, html}]
function assembleCard(cardName, serverData) {
  const card = _cardTemplates[cardName];
  if (!card || !card.slots) return [];
  const typeCounts = {};
  return card.slots.map(slotDef => {
    const n = (typeCounts[slotDef.type] = (typeCounts[slotDef.type] || 0) + 1);
    const id = slotDef.type + '.' + n;
    let data = {};
    let asmError = null;
    try {
      if (slotDef.asm) {
        const state = execAsm(slotDef.asm, { n: serverData });
        for (const [k, v] of Object.entries(state)) {
          if (k !== 'n' && k !== 'each_idx' && !k.startsWith('_')) data[k] = v;
        }
      }
    } catch(e) { asmError = e.message; }
    const comp = slotDef.component || slotDef.type;
    // Client schema: auto-derive from assembly output, or use contract if set
    const contract = slotDef.schema || null; // optional declared contract
    const autoSchema = {};
    for (const [k, v] of Object.entries(data)) {
      if (Array.isArray(v)) autoSchema[k] = 'array';
      else if (v != null && typeof v === 'object') autoSchema[k] = 'object';
      else if (typeof v === 'number') autoSchema[k] = 'number';
      else if (typeof v === 'boolean') autoSchema[k] = 'boolean';
      else autoSchema[k] = 'string';
    }
    const clientSchema = contract || autoSchema;
    // Validate: warn on missing fields if contract is set
    const warnings = [];
    if (contract) {
      for (const field of Object.keys(contract)) {
        if (data[field] === undefined) warnings.push(`missing: ${field}`);
      }
    }
    if (asmError) warnings.push(`asm error: ${asmError}`);
    const html = renderComponent(comp, data);
    return { type: slotDef.type, component: comp, id, data, clientSchema, warnings, html };
  });
}

// Render full card to HTML
function renderCard(cardName, serverData) {
  const slots = assembleCard(cardName, serverData);
  if (!slots.length) return '<div class="node-slot" style="color:var(--text-dim);">(empty card)</div>';
  return slots.map(s => s.html).join('');
}

root._cardTemplates = _cardTemplates;
root._saveCardTemplates = _saveCardTemplates;
root.assembleCard = assembleCard;
root.renderCard = renderCard;

})(window);
