
/* ================================================================
   State
   ================================================================ */
const SB = () => document.getElementById('sandboxUrl').value.replace(/\/+$/,'');
let session = 'default';
let nodes = {};   // id -> node data
let idN = 0;
const feed = document.getElementById('feed');

/* Settings - read from sidebar inputs */
function getSettings() {
  return {
    temperature: parseFloat(document.getElementById('settingTemp').value) || 0.6,
    max_tokens: parseInt(document.getElementById('settingMaxTokens').value) || 2048,
    max_continue: parseInt(document.getElementById('settingMaxContinue').value) || 20,
    verify_max_rounds: parseInt(document.getElementById('settingVerifyRounds').value) || 3,
    no_think: document.getElementById('settingNoThink').checked,
  };
}

/* Workers - multiple validator endpoints */
let workers = [
  {url: 'http://localhost:5001', name: 'local:5001', role: 'generator'},
  {url: 'http://192.168.1.15:5050', name: 'remote:5050', role: 'analyzer'},
];

/* helpers */
function ts() { return new Date().toLocaleTimeString('ru-RU',{hour:'2-digit',minute:'2-digit',second:'2-digit'}); }
function esc(s) { const d=document.createElement('div'); d.textContent=s; return d.innerHTML; }
function gid() { return 'n'+(++idN); }
function setS(c,t) { document.getElementById('dot').className='dot '+c; document.getElementById('stxt').textContent=t; }

/* API */
async function post(p,b) {
  const r=await fetch(SB()+p,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(b)});
  if(!r.ok) throw new Error(r.status+': '+await r.text());
  return r.json();
}
async function get(p) { const r=await fetch(SB()+p); if(!r.ok) throw new Error(''+r.status); return r.json(); }

/* ================================================================
   Node CRUD
   ================================================================ */
function createNode(parentId, opts) {
  const id = gid();
  const nd = {
    id, parentId,
    type: opts.type||'entity',   // root | entity | sub
    title: opts.title||'',
    status: opts.status||'pending',
    tags: opts.tags||{},         // key->value scope constants (collapsible)
    question: opts.question||'',
    questionForm: opts.questionForm||null,
    answer: opts.answer||'',
    answerThink: opts.answerThink||'',  // <think> content, shown collapsed above RESULT
    answerStatus: null,
    showAnswer: opts.showAnswer!==false,
    reactions: [],               // [{worker, emoji, status, detail}]
    children: [],                // child node ids
    thread: [],                  // [{role,name,content,time,status}]
    time: ts(),
    collapsed: false,
    threadOpen: true,
    tagsCollapsed: (opts.type||'entity') === 'root',  // root: tags collapsed, entity: open
    answerOpen: false,
  };
  nodes[id] = nd;
  if (parentId && nodes[parentId]) nodes[parentId].children.push(id);
  renderTree(true);
  return nd;
}

function addThread(nodeId, role, name, content, extra) {
  const nd = nodes[nodeId]; if(!nd) return;
  nd.thread.push({role, name, content, time:ts(), ...(extra||{})});
  nd.threadOpen = true; // keep thread open when new messages arrive
  renderTree();
}

function setAnswer(nodeId, text, status, think) {
  const nd = nodes[nodeId]; if(!nd) return;
  nd.answer = text; nd.answerStatus = status;
  if (think !== undefined) nd.answerThink = think;
  renderTree();
  // Auto-resize answer textareas
  document.querySelectorAll('.answer-ta').forEach(ta => {
    ta.style.height = 'auto';
    ta.style.height = ta.scrollHeight + 'px';
  });
}

function addReaction(nodeId, worker, emoji, status, detail) {
  const nd = nodes[nodeId]; if(!nd) return;
  // Update existing or add new
  const existing = nd.reactions.find(r => r.worker === worker);
  if (existing) { existing.emoji = emoji; existing.status = status; existing.detail = detail||''; }
  else nd.reactions.push({worker, emoji, status, detail:detail||''});
  renderTree();
}

/* LLM fetch with auto-continue on token limit (same pattern as multi_agent_chat.html) */
async function fetchLLMWithContinue(url, messages, opts = {}) {
  const s = getSettings();
  const { temperature = s.temperature, max_tokens = s.max_tokens, noThink = s.no_think, maxContinues = s.max_continue } = opts;
  let result = '';
  const baseMessages = [...messages];

  // No-think: add assistant prefill (same as multi_agent_chat.html)
  if (noThink && (baseMessages.length === 0 || baseMessages[baseMessages.length-1].role !== 'assistant')) {
    baseMessages.push({ role: 'assistant', content: '<think>\n\n</think>\n\n' });
  }

  const lastMsg = baseMessages[baseMessages.length - 1];
  const hasPrefill = lastMsg && lastMsg.role === 'assistant';

  for (let i = 0; i <= maxContinues; i++) {
    let curMessages;
    if (i === 0) {
      curMessages = baseMessages;
    } else if (hasPrefill) {
      // Replace prefill with accumulated result for KV cache match
      curMessages = [...baseMessages.slice(0, -1), { role: 'assistant', content: (noThink ? '<think>\n\n</think>\n\n' : '') + result }];
    } else {
      curMessages = [...baseMessages, { role: 'assistant', content: result }];
    }

    const res = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        messages: curMessages,
        continue_assistant_turn: i > 0 || noThink,
        cache_prompt: false,
        temperature, max_tokens, stream: false,
      }),
    });
    const data = await res.json();
    const chunk = data.choices?.[0]?.message?.content || data.results?.[0]?.text || '';
    const finishReason = data.choices?.[0]?.finish_reason || 'stop';
    result += chunk;
    if (finishReason !== 'length') break;
  }
  // Separate think and answer - return both
  let think = '';
  let answer = result;
  const thinkMatch = result.match(/<think\b[^>]*>([\s\S]*?)<\/think>/i);
  if (thinkMatch) {
    think = thinkMatch[1].trim();
    answer = result.replace(/<think\b[^>]*>[\s\S]*?<\/think>\s*/gi, '').trim();
  } else if (result.includes('<think>')) {
    const idx = result.indexOf('<think>');
    const endIdx = result.lastIndexOf('</think>');
    if (endIdx > idx) {
      think = result.slice(idx + 7, endIdx).trim();
      answer = result.slice(endIdx + 8).trim();
    } else {
      think = result.slice(idx + 7).trim();
      answer = '';
    }
  }
  return { answer, think };
}

async function requestWorkerCheck(nodeId, workerObj) {
  const nd = nodes[nodeId]; if(!nd) return;
  if (!nd.answer) {
    addReaction(nodeId, workerObj.name, '\u26A0\uFE0F', 'pending', 'no text to check');
    return;
  }
  addReaction(nodeId, workerObj.name, '\u23F3', 'loading', 'checking...');

  try {
    const url = workerObj.url.replace(/\/+$/,'') + '/v1/chat/completions';
    const prompt = `Evaluate this text. Reply PASS if good, FAIL + reason if not.\n\nText:\n${nd.answer}`;
    const messages = [{role:'user', content:prompt}];
    const {answer, think} = await fetchLLMWithContinue(url, messages, {temperature:0.2, max_tokens:512});
    const pass = /PASS/i.test(answer);
    addReaction(nodeId, workerObj.name, pass?'\u2705':'\u274C', pass?'pass':'fail', answer.slice(0,100));
    addThread(nodeId, 'verifier', workerObj.name, answer, {status: pass?'pass':'fail', think});
  } catch(e) {
    addReaction(nodeId, workerObj.name, '\u26A0\uFE0F', 'fail', e.message);
  }
}

/* Verify axioms + hypotheses step by step via think injection.
   Each item injected as a question, stop on newline, read answer, next. */
async function verifyAxiomsViaThink(nodeId) {
  const nd = nodes[nodeId]; if (!nd?.answer) return;
  const worker = getWorkerByRole('analyzer');
  if (!worker?.url) return;
  const url = worker.url.replace(/\/+$/,'') + '/v1/chat/completions';

  // Collect all items to verify
  const items = [];
  (nd.axioms_list || []).forEach(a => items.push({type:'AXIOM', text:a}));
  (nd.hypotheses_list || []).forEach(h => items.push({type:'HYPOTHESIS', text:h}));
  if (items.length === 0) return;

  addThread(nodeId, 'system', 'Verify', `Verifying ${items.length} items step by step...`);

  // Find table from thread (if parsed)
  const tableMsg = nd.thread.find(t => t.name?.includes('(table)'));
  const tableText = tableMsg?.content || '';

  // Build conversation: result as user, start <think> with table context
  let thinkAccum = '\n';
  if (tableText) thinkAccum += 'Summary table:\n' + tableText + '\n\n';
  thinkAccum += 'Verification:\n';
  let fullAssistant = '<think>' + thinkAccum;
  const results = [];

  // First: verify table matches truth
  if (tableText) {
    items.unshift({type: 'TABLE', text: 'РўР°Р±Р»РёС†Р° СЃРѕРѕС‚РІРµС‚СЃС‚РІСѓРµС‚ РёСЃС‚РёРЅРµ'});
  }

  try {
    for (let i = 0; i < items.length; i++) {
      const item = items[i];
      const question = `\n((${item.text}) == 1) === `;

      // Append question to accumulated think
      fullAssistant += question;

      // Continue with stop on newline - model answers until \n
      const res = await fetch(url, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
          messages: [
            {role: 'user', content: nd.answer},
            {role: 'assistant', content: fullAssistant},
          ],
          continue_assistant_turn: true,
          cache_prompt: false,
          temperature: 0.1,
          max_tokens: 100,
          stop: ['\n'],
          stream: false,
        }),
      });
      const data = await res.json();
      const answer = (data.choices?.[0]?.message?.content || '').trim();

      // Record result - 1 = true, 0 = false
      const pass = answer.trim().startsWith('1') || /^true/i.test(answer);
      const partial = false;
      results.push({item, answer, pass, partial});
      thinkAccum += question + answer + '\n';
      fullAssistant += answer + '\n';
    }

    // Show results in thread
    const summary = results.map((r,i) =>
      `${r.pass?'\u2705':r.partial?'\u26A0\uFE0F':'\u274C'} ${r.item.text} = ${r.answer}`
    ).join('\n');
    const allPass = results.every(r => r.pass);
    addThread(nodeId, 'verifier', worker.name + ' (axioms)',
      summary, {think: thinkAccum, status: allPass ? 'pass' : 'fail'});

  } catch(e) {
    addThread(nodeId, 'system', 'Verify', 'Error: ' + e.message);
  }
}

function requestAllWorkersCheck(nodeId) {
  workers.forEach(w => requestWorkerCheck(nodeId, w));
}

/* Pin a thread message -> promote to child node */
function pinThreadMessage(nodeId, threadIdx, pinnerName) {
  const nd = nodes[nodeId]; if(!nd) return;
  const t = nd.thread[threadIdx]; if(!t) return;

  if (!t.pins) t.pins = [];
  if (t.pins.includes(pinnerName)) return;
  t.pins.push(pinnerName);

  const PIN_THRESHOLD = 1;
  if (t.pins.length >= PIN_THRESHOLD && !t.promoted) {
    t.promoted = true;

    // Pin into parent's answer field (make visible)
    nd.showAnswer = true;
    setAnswer(nodeId, t.content, null, t.think || '');

    // If content looks like a markdown table -> parse into entity child nodes
    const hasTable = t.content.includes('|') && t.content.split('\n').filter(l => l.trim().startsWith('|')).length >= 3;
    if (hasTable) {
      parseTableToEntities(nodeId, t.content);
    }

    return;
  }
  renderTree();
}

function updateNode(nodeId, upd) {
  const nd = nodes[nodeId]; if(!nd) return;
  Object.assign(nd, upd);
  renderTree();
}

/* ================================================================
   Render - full tree rebuild (simple & correct)
   ================================================================ */
function renderTree(scrollToBottom) {
  const prevScroll = feed.scrollTop;
  const roots = Object.values(nodes).filter(n => !n.parentId || !nodes[n.parentId]);
  feed.innerHTML = '';
  roots.forEach(n => feed.appendChild(renderNode(n)));
  if (scrollToBottom) {
    feed.scrollTop = feed.scrollHeight;
  } else {
    feed.scrollTop = prevScroll;
  }
  // Auto-resize all answer textareas to fit content
  feed.querySelectorAll('.answer-ta').forEach(ta => {
    ta.style.height = 'auto';
    ta.style.height = ta.scrollHeight + 'px';
  });
}

function renderNode(nd) {
  const el = document.createElement('div');
  el.className = 'node' + (nd.status==='done'?' done':'') + (nd.status==='fail'?' fail':'') + (nd.status==='active'?' active':'');
  el.dataset.nid = nd.id;

  const iconCls = nd.type==='root'?'root': nd.status==='done'?'ok': nd.status==='fail'?'err':'entity';
  const iconCh = nd.type==='root'?'T':'#';
  const badgeCls = nd.status||'pending';
  const bodyOpen = !nd.collapsed;

  /* header - tags toggle button pinned here on the right */
  const tagEntries = Object.entries(nd.tags).filter(([k])=>!k.startsWith('_'));
  const tagsCollapsed = nd.tagsCollapsed || false;

  let h = `<div class="node-hdr" data-hdr="${nd.id}">`;
  h += `<span class="node-arrow${bodyOpen?' open':''}">\u25B6</span>`;
  h += `<span class="node-icon ${iconCls}">${iconCh}</span>`;
  h += `<span class="node-title">${esc(nd.title)}</span>`;
  if (nd.children.length) h += `<span class="node-collapse-hint">${nd.children.length} sub</span>`;
  h += `<span class="node-badge ${badgeCls}">${badgeCls}</span>`;
  h += `<span class="node-time">${nd.time}</span>`;
  if (tagEntries.length) h += `<button class="tags-toggle-btn" data-tags-toggle="${nd.id}" title="Toggle scope">${tagsCollapsed?'\u25BC':'\u25B2'}</button>`;
  h += `</div>`;

  /* body */
  h += `<div class="node-body${bodyOpen?' open':''}" data-body="${nd.id}">`;

  /* tags (collapsible - toggle button is in header) */
  if (tagEntries.length) {
    h += `<div class="node-tags-wrap${tagsCollapsed?' collapsed':''}">`;
    h += `<div class="node-tags${tagsCollapsed?' collapsed':''}">`;
    tagEntries.forEach(([k,v]) => {
      const display = Array.isArray(v) ? v.join(', ') : String(v);
      const cls = k.startsWith('used_') ? 'green' : 'accent';
      h += `<span class="tag ${cls}" title="${esc(k)}: ${esc(display)}">${esc(k)}: ${esc(display.length>30 ? display.slice(0,30)+'...' : display)}</span>`;
    });
    h += `</div></div>`;
  }

  /* structured lists (ENTITIES, AXIOMS, HYPOTHESES) */
  if (nd.entities_list?.length || nd.axioms_list?.length || nd.hypotheses_list?.length) {
    h += `<div class="node-lists">`;
    [{name:'ENTITIES', items:nd.entities_list, cls:'entity'},
     {name:'AXIOMS', items:nd.axioms_list, cls:'axiom'},
     {name:'HYPOTHESES', items:nd.hypotheses_list, cls:'hypothesis'}
    ].forEach(list => {
      if (!list.items?.length) return;
      const lOpen = nd['list_'+list.name+'_open'];
      h += `<div class="node-list-section">`;
      h += `<div class="node-list-header" data-list-toggle="${nd.id}:${list.name}"><span class="arrow${lOpen?' open':''}">\u25B6</span> ${list.name} <span class="list-count">${list.items.length}</span></div>`;
      h += `<div class="node-list-body${lOpen?' open':''}">`;
      list.items.forEach(item => {
        h += `<div class="node-list-item ${list.cls}"><span class="li-bullet">\u2022</span>${esc(item)}</div>`;
      });
      h += `</div></div>`;
    });
    h += `</div>`;
  }

  /* question */
  if (nd.question) {
    h += `<div class="node-question">${esc(nd.question)}</div>`;
  }

  /* question form */
  if (nd.questionForm && nd.questionForm.length) {
    h += `<div class="node-form" data-form="${nd.id}">`;
    nd.questionForm.forEach((q,i) => {
      h += `<div class="qf-item">`;
      h += `<label>${esc(q.question)}</label>`;
      if (q.hint) h += `<div class="qf-hint">${esc(q.hint)}</div>`;
      if (q.type==='textarea') h += `<textarea data-field="${esc(q.field)}" placeholder="${esc(q.placeholder||'')}"></textarea>`;
      else h += `<input data-field="${esc(q.field)}" type="text" placeholder="${esc(q.placeholder||'')}" />`;
      h += `</div>`;
    });
    h += `<button class="btn primary" style="margin-top:4px" data-submit="${nd.id}">Submit</button>`;
    h += `</div>`;
  }

  /* think block (collapsed, above RESULT) */
  if (nd.answerThink && nd.showAnswer) {
    h += `<div class="think-block">`;
    h += `<div class="think-toggle" data-think-toggle="${nd.id}"><span class="arrow">\u25B6</span> think (${nd.answerThink.length} chars)</div>`;
    h += `<div class="think-body" data-think-body="${nd.id}">${esc(nd.answerThink)}</div>`;
    h += `</div>`;
  }

  /* answer - code block */
  if (nd.showAnswer) {
    const acls = nd.answerStatus==='pass'?' pass': nd.answerStatus==='fail'?' fail':'';
    const emptyCls = nd.answer ? '' : ' empty';
    h += `<div class="node-answer">`;
    h += `<div class="answer-block${acls}">`;
    const ansOpen = nd.answerOpen !== false; // default open for now, will change
    h += `<div class="answer-lang">`;
    h += `<span>result</span>`;
    h += `<span style="flex:1"></span>`;
    h += `<button class="tags-toggle-btn" data-answer-toggle="${nd.id}">${ansOpen?'\u25B2':'\u25BC'}</button>`;
    h += `</div>`;
    if (ansOpen) {
      h += `<textarea class="answer-ta${emptyCls}" data-ans="${nd.id}" placeholder="(pending...)">${esc(nd.answer)}</textarea>`;
    }
    h += `</div>`;
    h += `</div>`;

    /* reactions bar */
    if (nd.reactions.length) {
      h += `<div class="reactions-bar">`;
      const passed = nd.reactions.filter(r=>r.status==='pass').length;
      const total = nd.reactions.length;
      nd.reactions.forEach(r => {
        const wcls = r.status||'pending';
        h += `<span class="reaction ${wcls}" title="${esc(r.detail||'')}">`;
        h += `<span class="reaction-emoji">${r.emoji||'\u2753'}</span>`;
        h += `<span class="reaction-who ${wcls}">${esc(r.worker)}</span>`;
        h += `</span>`;
      });
      h += `<span class="reactions-summary"><span class="count ${passed===total?'ok':'bad'}">${passed}/${total}</span></span>`;
      h += `</div>`;
    }
  }

  /* thread (before children - thread belongs to THIS node) */
  const tc = nd.thread.length;
  const tOpen = nd.threadOpen;
  h += `<div class="thread-bar" data-thread-toggle="${nd.id}"><span class="arrow${tOpen?' open':''}">\u25B6</span> Thread <span class="thread-cnt">${tc}</span></div>`;
  h += `<div class="thread-wrap${tOpen?' open':''}" data-thread="${nd.id}">`;
  h += `<div class="thread-msgs">`;
  nd.thread.forEach((t, i) => { h += tmsgHTML(t, nd.id, i); });
  h += `</div>`;
  h += `<div class="thread-input"><textarea placeholder="Reply..." data-tinp="${nd.id}" rows="1"></textarea><button class="btn" data-tsend="${nd.id}">Send</button></div>`;
  h += `</div>`;

  /* children (after thread) */
  if (nd.children.length) {
    h += `<div class="node-children" data-children="${nd.id}"></div>`;
  }

  h += `</div>`; // end body

  el.innerHTML = h;

  // Render children recursively
  const childContainer = el.querySelector(`[data-children="${nd.id}"]`);
  if (childContainer) {
    nd.children.forEach(cid => {
      if (nodes[cid]) childContainer.appendChild(renderNode(nodes[cid]));
    });
  }

  // Bind events
  bindNode(el, nd);
  return el;
}

function tmsgHTML(t, nodeId, threadIdx) {
  const r = t.role||'system';
  const ini = (t.name||r)[0].toUpperCase();
  let badge = '';
  if (t.status==='pass') badge='<span class="tmsg-badge pass">PASS</span>';
  if (t.status==='fail') badge='<span class="tmsg-badge fail">FAIL</span>';
  const promoted = t.promoted ? ' promoted' : '';
  const pinCls = t.pinned ? ' pinned' : '';
  const pinCount = t.pins ? t.pins.length : 0;
  const pinLabel = pinCount ? ` ${pinCount}` : '';
  let thinkHtml = '';
  if (t.think) {
    const tid = `tthink-${nodeId}-${threadIdx}`;
    thinkHtml = `<div class="think-block" style="margin:4px 0"><div class="think-toggle" data-think-toggle="${tid}"><span class="arrow">\u25B6</span> think (${t.think.length})</div><div class="think-body" data-think-body="${tid}">${esc(t.think)}</div></div>`;
  }
  return `<div class="tmsg${promoted}"><div class="tmsg-ava ${r}">${ini}</div><div class="tmsg-body"><div class="tmsg-hdr"><span class="tmsg-nick ${r}">${esc(t.name||r)}</span>${badge}<span class="tmsg-time">${t.time||''}</span></div>${thinkHtml}<div class="tmsg-text">${esc(t.content||'')}</div><div class="tmsg-actions"><button class="pin-btn${pinCls}" data-pin="${nodeId}:${threadIdx}" title="Pin to parent">&#x1F4CC;${pinLabel}</button></div></div></div>`;
}

function bindNode(el, nd) {
  // header click -> collapse/expand body
  const hdr = el.querySelector(`[data-hdr="${nd.id}"]`);
  if (hdr) hdr.addEventListener('click', () => {
    nd.collapsed = !nd.collapsed;
    const body = el.querySelector(`[data-body="${nd.id}"]`);
    const arrow = hdr.querySelector('.node-arrow');
    if (body) body.classList.toggle('open', !nd.collapsed);
    if (arrow) arrow.classList.toggle('open', !nd.collapsed);
  });

  // thread toggle
  const tbar = el.querySelector(`[data-thread-toggle="${nd.id}"]`);
  if (tbar) tbar.addEventListener('click', () => {
    nd.threadOpen = !nd.threadOpen;
    const wrap = el.querySelector(`[data-thread="${nd.id}"]`);
    const arrow = tbar.querySelector('.arrow');
    if (wrap) wrap.classList.toggle('open', nd.threadOpen);
    if (arrow) arrow.classList.toggle('open', nd.threadOpen);
  });

  // list toggles (ENTITIES, AXIOMS, HYPOTHESES)
  el.querySelectorAll('[data-list-toggle]').forEach(toggle => {
    toggle.addEventListener('click', () => {
      const [nid, listName] = toggle.dataset.listToggle.split(':');
      const n = nodes[nid]; if (!n) return;
      n['list_'+listName+'_open'] = !n['list_'+listName+'_open'];
      renderTree();
    });
  });

  // think block toggles (node-level + thread-level)
  el.querySelectorAll('[data-think-toggle]').forEach(toggle => {
    toggle.addEventListener('click', () => {
      const tid = toggle.dataset.thinkToggle;
      const body = el.querySelector(`[data-think-body="${tid}"]`);
      const arrow = toggle.querySelector('.arrow');
      if (body) body.classList.toggle('open');
      if (arrow) arrow.classList.toggle('open');
    });
  });

  // tags collapse toggle
  const tagsBtn = el.querySelector(`[data-tags-toggle="${nd.id}"]`);
  if (tagsBtn) tagsBtn.addEventListener('click', (e) => {
    e.stopPropagation();
    nd.tagsCollapsed = !nd.tagsCollapsed;
    renderTree();
  });

  // pin buttons in thread messages
  el.querySelectorAll(`[data-pin^="${nd.id}:"]`).forEach(btn => {
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      const [nid, idx] = btn.dataset.pin.split(':');
      pinThreadMessage(nid, parseInt(idx), 'You');
    });
  });

  // submit form
  const sbtn = el.querySelector(`[data-submit="${nd.id}"]`);
  if (sbtn) sbtn.addEventListener('click', () => submitForm(nd.id));

  // answer toggle
  const ansToggle = el.querySelector(`[data-answer-toggle="${nd.id}"]`);
  if (ansToggle) ansToggle.addEventListener('click', (e) => {
    e.stopPropagation();
    nd.answerOpen = !(nd.answerOpen !== false);
    renderTree();
  });

  // thread send
  const tsend = el.querySelector(`[data-tsend="${nd.id}"]`);
  if (tsend) tsend.addEventListener('click', () => {
    const ta = el.querySelector(`[data-tinp="${nd.id}"]`);
    if (ta && ta.value.trim()) {
      const text = ta.value.trim();
      ta.value = '';
      // Send through dialog - same as main input
      handleInput(text);
    }
  });
  const tinp = el.querySelector(`[data-tinp="${nd.id}"]`);
  if (tinp) tinp.addEventListener('keydown', e => {
    if (e.key==='Enter' && !e.shiftKey) { e.preventDefault(); tsend?.click(); }
  });
}

/* ================================================================
   Flow
   ================================================================ */
/* Parse a named list from claims text.
   Handles both formats:
     ENTITIES: [a, b, c]
     AXIOMS:
     - item1
     - item2
*/
function parseListFromText(text, listName) {
  const lines = text.split('\n');
  const items = [];
  let inSection = false;

  for (const line of lines) {
    const trimmed = line.trim();

    // Check if this line starts the section
    if (trimmed.toUpperCase().startsWith(listName.toUpperCase() + ':')) {
      inSection = true;
      // Check for inline format: ENTITIES: [a, b, c]
      const afterColon = trimmed.slice(listName.length + 1).trim();
      if (afterColon.startsWith('[')) {
        const inner = afterColon.replace(/^\[|\]$/g, '');
        inner.split(',').forEach(s => { const t = s.trim(); if (t) items.push(t); });
        inSection = false; // inline = done
      }
      continue;
    }

    // Check if we hit another section header -> stop
    if (inSection && /^[A-Z_]+:/.test(trimmed)) {
      inSection = false;
      continue;
    }

    // Collect items (lines starting with -)
    if (inSection && trimmed.startsWith('-')) {
      items.push(trimmed.slice(1).trim());
    }
  }
  return items;
}

let rootNodeId = null;

/* Verify content by ALL workers - returns [{worker, pass, answer}] */

/* Parse markdown table into entity child nodes */
function parseTableToEntities(parentNodeId, tableText) {
  // Parse markdown table: | Header1 | Header2 | ... |
  const lines = tableText.trim().split('\n').filter(l => l.trim().startsWith('|'));
  if (lines.length < 3) return; // need header + separator + at least 1 row

  // Extract headers
  const headers = lines[0].split('|').map(h => h.trim()).filter(h => h && !h.match(/^-+$/));
  // Skip separator line (line 1)
  const dataLines = lines.slice(2);

  dataLines.forEach((line, i) => {
    const cells = line.split('|').map(c => c.trim()).filter(c => c);
    if (cells.length === 0) return;

    const tags = {};
    headers.forEach((h, j) => {
      if (j < cells.length) tags[h] = cells[j];
    });

    const title = cells[0] || `entity-${i+1}`;
    createNode(parentNodeId, {
      type: 'entity',
      title: title,
      tags: tags,
      question: '',
      status: 'pending',
    });
  });

  // Distribute parent's pinned answer to entities
  distributeAnswerToEntities(parentNodeId);
}

/* Find each entity's section in the answer text by matching entity title */
function distributeAnswerToEntities(parentNodeId) {
  const parent = nodes[parentNodeId]; if (!parent) return;

  const genMsg = parent.thread.find(t => t.name?.includes('(answer)'));
  const fullText = genMsg?.content || '';
  if (!fullText) return;

  const children = parent.children.map(cid => nodes[cid]).filter(n => n?.type === 'entity');
  if (children.length === 0) return;

  // Find start LINE of each entity by its title in the text
  // Match from the line that contains the title, not from the word itself
  const lines = fullText.split('\n');
  const lowerLines = lines.map(l => l.toLowerCase().replace(/[В«В»\*\#]/g, ''));

  const positions = children.map(child => {
    const title = child.title.toLowerCase().replace(/[В«В»\*\#]/g, '').trim();
    let lineIdx = lowerLines.findIndex(l => l.includes(title));
    if (lineIdx < 0) {
      // Partial match: first 2 words
      const words = title.split(/\s+/);
      if (words.length >= 2) lineIdx = lowerLines.findIndex(l => l.includes(words.slice(0,2).join(' ')));
    }
    return { child, lineIdx };
  }).filter(p => p.lineIdx >= 0).sort((a,b) => a.lineIdx - b.lineIdx);

  // Extract from start line to next entity's start line
  const generator = getWorkerByRole('generator');

  // For each entity: find last line via think injection, trim, set answer
  // All trim calls go to parent thread (where table is)
  positions.forEach(async (p, i) => {
    const startLine = p.lineIdx;
    const roughEnd = i + 1 < positions.length ? positions[i+1].lineIdx : lines.length;
    const section = lines.slice(startLine, roughEnd).join('\n').trim();
    if (!section) return;

    // Find end line via think injection - costs 1 token per entity
    if (generator?.url) {
      const url = generator.url.replace(/\/+$/,'') + '/v1/chat/completions';
      const numberedText = lines.map((l,i) => `${i+1}. ${l}`).join('\n');
      const startNum = startLine + 1; // 1-based
      const firstLineText = lines[startLine]?.trim() || p.child.title;
      const thinkQ = `<think>\nР Р°Р·РґРµР»СЋ С‚РµРєСЃС‚ РЅР° Р±Р»РѕРєРё.\nРћРїРёСЃР°РЅРёРµ "${p.child.title}" РЅР°С‡РёРЅР°РµС‚СЃСЏ СЃРѕ СЃС‚СЂРѕРєРё РїРѕРґ РЅРѕРјРµСЂРѕРј "${startNum}" "${firstLineText}" Рё РґР»РёС‚СЃСЏ РґРѕ СЃС‚СЂРѕРєРё РїРѕРґ РЅРѕРјРµСЂРѕРј "line number: `;

      try {
        const res = await fetch(url, {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({
            messages: [
              {role: 'user', content: numberedText},
              {role: 'assistant', content: thinkQ},
            ],
            continue_assistant_turn: true,
            cache_prompt: false,
            temperature: 0.1,
            max_tokens: 10,
            stop: ['\n', '"', ' '],
            stream: false,
          }),
        });
        const data = await res.json();
        const endNum = parseInt((data.choices?.[0]?.message?.content || '').trim());

        addThread(parentNodeId, 'worker', `${generator.name} (trim)`,
          `В«${p.child.title}В» lines ${startNum}-${endNum}`,
          {think: `РћРїРёСЃР°РЅРёРµ "${p.child.title}" РЅР°С‡РёРЅР°РµС‚СЃСЏ СЃРѕ СЃС‚СЂРѕРєРё "${startNum}", РґР»РёС‚СЃСЏ РґРѕ СЃС‚СЂРѕРєРё "line number: ${endNum}"`});

        if (endNum > startLine) {
          // If end line is empty, include it but trim result
          const trimmedSection = lines.slice(startLine, endNum).join('\n').trim();
          if (trimmedSection) {
            setAnswer(p.child.id, trimmedSection, null);
            updateNode(p.child.id, {status: 'done'});
            return;
          }
        }
      } catch(_) {}
    }
    // Fallback
    setAnswer(p.child.id, section, null);
    updateNode(p.child.id, {status: 'done'});
  });
}

/* ================================================================
   Event-driven worker dispatch
   Workers run in parallel. Listeners fire when data arrives.
   ================================================================ */

// Thread message listeners - fire when a new message with matching tag appears
const threadListeners = [];

function onThreadMessage(tag, callback) {
  threadListeners.push({tag, callback});
}

// Override addThread to fire listeners
const _origAddThread = addThread;
addThread = function(nodeId, role, name, content, extra) {
  _origAddThread(nodeId, role, name, content, extra);
  // Fire matching listeners
  const tag = name || '';
  threadListeners.forEach(l => {
    if (tag.includes(l.tag)) {
      try { l.callback(nodeId, {role, name, content, ...(extra||{})}); } catch(_) {}
    }
  });
};

/* Send task to a worker - returns promise, result appears in thread */
function sendToWorker(nodeId, worker, prompt, tag, opts) {
  if (!worker?.url) return Promise.resolve('');
  const url = worker.url.replace(/\/+$/,'') + '/v1/chat/completions';
  return (async () => {
    try {
      const {answer, think} = await fetchLLMWithContinue(
        url, [{role:'user', content:prompt}],
        {temperature: opts?.temperature ?? 0.3, max_tokens: opts?.max_tokens ?? getSettings().max_tokens}
      );
      addThread(nodeId, 'worker', `${worker.name} (${tag})`, answer, {think});
      return answer;
    } catch(e) {
      addThread(nodeId, 'system', tag, 'Error: ' + e.message);
      return '';
    }
  })();
}

let workflowYaml = ''; // loaded on init

async function loadDefaultWorkflow() {
  try {
    const res = await get('/api/workflow/default');
    workflowYaml = res.yaml || '';
  } catch(_) {}
}

async function handleInput(text) {
  setS('busy','Processing...');
  document.getElementById('btnSend').disabled = true;

  try {
    // Create root node
    if (!rootNodeId) {
      const root = createNode(null, {
        type:'root', title: text,
        question: text, showAnswer: false, status: 'active',
      });
      rootNodeId = root.id;
    } else {
      addThread(rootNodeId, 'user', 'You', text);
    }

    if (!workflowYaml) await loadDefaultWorkflow();

    // Build worker URLs map from sidebar
    const workerUrls = {};
    workers.forEach(w => {
      if (w.role && w.url) workerUrls[w.role] = w.url;
    });

    // Execute workflow on server - all steps, all visible
    setS('busy', 'Running workflow...');
    const res = await post('/api/workflow/run', {
      yaml: workflowYaml,
      input: text,
      workers: workerUrls,
      settings: getSettings(),
    });

    // Render all thread messages from server
    if (res.thread) {
      for (const t of res.thread) {
        addThread(rootNodeId, t.role || 'system', t.name || t.role || 'System', t.content || '', {think: t.think || '', tag: t.tag || ''});
      }
    }

    // Update root state
    if (res.state?.root?.answer) {
      nodes[rootNodeId].showAnswer = true;
      setAnswer(rootNodeId, res.state.root.answer);
    }

    // Create entity nodes from state
    if (res.state?.root?.entities) {
      const entityList = res.state.root.entities;
      if (Array.isArray(entityList)) {
        entityList.forEach(e => {
          const title = e._title || e[Object.keys(e)[0]] || 'entity';
          createNode(rootNodeId, {
            type: 'entity', title, tags: e, status: 'pending',
          });
        });
      }
    }

    // Distribute answers to entities from vars
    if (res.vars?.entity_nodes && Array.isArray(res.vars.entity_nodes)) {
      const children = nodes[rootNodeId]?.children?.map(id => nodes[id]).filter(n => n?.type === 'entity') || [];
      res.vars.entity_nodes.forEach((en, i) => {
        if (i < children.length && en.answer) {
          setAnswer(children[i].id, en.answer);
          updateNode(children[i].id, {status: 'done'});
        }
      });
    }

    if (res.status === 'error') {
      addThread(rootNodeId, 'system', 'Error', res.error || 'Unknown error');
    }

    updateNode(rootNodeId, {status: res.status === 'done' ? 'done' : 'active'});

  } catch(e) {
    if (rootNodeId) addThread(rootNodeId, 'system', 'Error', e.message);
    else createNode(null, {type:'root', title:'Error', question:e.message, showAnswer:false, status:'fail'});
  } finally {
    setS('ok','Ready');
    document.getElementById('btnSend').disabled = false;
  }
}

// Load default workflow on startup
loadDefaultWorkflow();

// Worker actions - same prompts as multi_agent_chat.html (no new hardcode)
const WORKER_PROMPTS = {
  claims: (content) => `Ты — логический аналитик. Извлеки все атомарные утверждения/факты из текста.
Верни ТОЛЬКО в формате:
ENTITIES: [сущностт1, сущностт2, ...]
AXIOMS:
- утверждение 1
- утверждение 2
HYPOTHESES:
- гипотеза 1

Требования:
- Используй pos('Имя') для позиционных утверждений.
- AXIOMS = факты, данные как условие.
- HYPOTHESES = выводы, предположения.
- Каждое утверждение атомарное и короткое.
- Не выводи прозу или JSON.
- Отвечай на языке текста.

Текст для анализа:
${content}`,

  table: (content) => `Ты — экстрактор данных. Распарси текст в структурированную таблицу.
Верни markdown-таблицу с подходящими колонками.
Если есть сущности со свойствами: | Сущность | Свойство1 | Свойство2 |
Если список: | # | Элемент | Детали |
Кратко. Только таблица, без комментариев.
Отвечай на языке текста.

Текст:
${content}`,
};

async function workerAction(actionType, nodeId, threadIdx) {
  const nd = nodes[nodeId]; if(!nd) return;
  const t = nd.thread[threadIdx]; if(!t) return;
  const content = t.content;
  const promptFn = WORKER_PROMPTS[actionType];
  if (!promptFn) return;

  // Use analyzer role for extraction actions
  const worker = getWorkerByRole('analyzer');
  if (!worker?.url) { addThread(nodeId, 'system', 'System', 'No worker available'); return; }
  const workerUrl = worker.url;

  addThread(nodeId, 'system', 'System', `Running ${actionType}...`);

  try {
    const prompt = promptFn(content);
    const url = workerUrl.replace(/\/+$/,'') + '/v1/chat/completions';
    const {answer, think} = await fetchLLMWithContinue(url, [{role:'user', content:prompt}], {temperature:0.1, max_tokens:2048});

    // Show result in thread
    addThread(nodeId, 'worker', `Worker (${actionType})`, answer, {think});

    // If claims -> parse entities only
    if (actionType === 'claims' && answer.trim()) {
      try {
        const verifyRes = await post('/api/logic/verify', {raw_schema: answer});
        if (verifyRes.manifest?.entities?.length) {
          addThread(nodeId, 'system', 'Parsed', `Entities: ${verifyRes.manifest.entities.join(', ')}`);
        }
      } catch(e) {
        addThread(nodeId, 'system', 'Verify', 'Verify error: '+e.message);
      }
    }
  } catch(e) {
    addThread(nodeId, 'system', 'Error', `${actionType} failed: ${e.message}`);
  }
}

async function runTask() {
  setS('busy','Running...');

  try {
    // Ensure workers registered before run
    await Promise.all(workers.filter(w => w.status !== 'registered').map(w => probeAndRegisterWorker(w)));

    const res = await post('/api/reactive/task/run?sync=true&session_id='+session, {});

    // Update entity nodes
    for (const [eid, e] of Object.entries(res.entities||{})) {
      const nd = Object.values(nodes).find(n => n.title===eid);
      if (!nd) continue;
      setAnswer(nd.id, e.properties?.text||'', e.properties?.validated?'pass':null, e.properties?._think||'');
      updateNode(nd.id, {status: e.status||'done', tags: e.properties||{}});
      // Dialog -> thread
      if (e.dialog) e.dialog.forEach(d => {
        addThread(nd.id, d.role==='verifier'?'verifier':'worker',
          d.role==='verifier'?'Verifier':'Worker', d.content, {status:d.status});
      });
    }

    // Update root tags with accumulated constraints
    if (rootNodeId && nodes[rootNodeId] && res.entities) {
      const newTags = {...nodes[rootNodeId].tags};
      // Refresh from task state
      try {
        const taskData = await get('/api/reactive/task?session_id='+session);
        if (taskData.global_meta) {
          for (const [k,v] of Object.entries(taskData.global_meta)) {
            if (k.startsWith('used_')) newTags[k] = v;
          }
        }
      } catch(_) {}
      updateNode(rootNodeId, {tags:newTags, status:'done'});
    }
  } catch(e) {
    if (rootNodeId) addThread(rootNodeId,'system','Error',e.message);
  } finally {
    setS('ok','Done');
    }
}

async function exportTask() {
  try {
    const d = await get('/api/reactive/task?session_id='+session);
    const b = new Blob([JSON.stringify(d,null,2)],{type:'application/json'});
    const a = document.createElement('a'); a.href=URL.createObjectURL(b);
    a.download=(d.task_id||'task')+'.json'; a.click();
  } catch(e) { alert(e.message); }
}

/* Events */
async function runWorkflowFromCurrentInput() {
  // Run workflow YAML from editor as-is (input is in let.input)
  const editorYaml = document.getElementById('workflowEditor')?.value;
  if (editorYaml) workflowYaml = editorYaml;
  if (!workflowYaml) return;

  // Extract input from YAML let.input for display
  const inputMatch = workflowYaml.match(/input:\s*[>|]?\s*\n?\s*(.+)/);
  const displayText = inputMatch?.[1]?.trim() || 'workflow';

  if (!rootNodeId) {
    const root = createNode(null, {
      type:'root', title: displayText,
      question: displayText, showAnswer: false, status: 'active',
    });
    rootNodeId = root.id;
  }

  const workerUrls = {};
  workers.forEach(w => { if (w.role && w.url) workerUrls[w.role] = w.url; });

  setS('busy', 'Running workflow...');
  try {
    const res = await post('/api/workflow/run', {
      yaml: workflowYaml, input: '', workers: workerUrls, settings: getSettings(),
    });
    if (res.thread) {
      for (const t of res.thread) {
        addThread(rootNodeId, t.role||'system', t.name||'System', t.content||'', {think:t.think||''});
      }
    }
    if (res.state?.root?.answer) {
      nodes[rootNodeId].showAnswer = true;
      setAnswer(rootNodeId, res.state.root.answer);
    }
    if (res.state?.root?.entities && Array.isArray(res.state.root.entities)) {
      res.state.root.entities.forEach(e => {
        createNode(rootNodeId, {type:'entity', title:e._title||'entity', tags:e, status:'pending'});
      });
    }
    updateNode(rootNodeId, {status: res.status==='done'?'done':'active'});
  } catch(e) {
    addThread(rootNodeId, 'system', 'Error', e.message);
  } finally {
    setS('ok','Ready');
  }
}

function exportWorkflowSnapshot() {
  const snapshot = {
    session,
    workflow_yaml: workflowYaml,
    root_node_id: rootNodeId,
    nodes,
    exported_at: new Date().toISOString(),
  };
  const b = new Blob([JSON.stringify(snapshot, null, 2)], {type:'application/json'});
  const a = document.createElement('a');
  a.href = URL.createObjectURL(b);
  a.download = 'reactive-workflow-snapshot.json';
  a.click();
}

document.getElementById('btnSend').addEventListener('click', () => {
  const t = document.getElementById('inp').value.trim();
  if (t) { document.getElementById('inp').value=''; handleInput(t); }
});
document.getElementById('inp').addEventListener('keydown', e => {
  if (e.key==='Enter' && !e.shiftKey) {
    e.preventDefault();
    document.getElementById('btnSend').click();
  }
});
document.getElementById('inp').addEventListener('input', function() {
  this.style.height='auto'; this.style.height=Math.min(this.scrollHeight,100)+'px';
});
document.getElementById('btnRun').addEventListener('click', runWorkflowFromCurrentInput);
document.getElementById('btnExport').addEventListener('click', exportWorkflowSnapshot);
document.getElementById('btnClear').addEventListener('click', async () => {
  nodes = {}; rootNodeId = null; idN = 0;
  document.getElementById('feed').innerHTML = '';
  document.getElementById('inp').value = '';
  session = 'sess-' + Date.now();
  renderTree();
});

/* Worker management */
// Worker status: 'unknown' | 'reachable' | 'registered'
function renderWorkers() {
  const el = document.getElementById('workerList');
  el.innerHTML = workers.map((w,i) => {
    const dotCls = w.status === 'registered' ? 'ok' : w.status === 'reachable' ? 'busy' : '';
    return `<div style="display:flex;align-items:center;gap:4px;margin-bottom:3px;font-size:11px">
      <span class="dot ${dotCls}" style="width:6px;height:6px"></span>
      <span style="color:var(--text-dim);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:70px" title="${esc(w.url)}">${esc(w.name)}</span>
      <select style="background:var(--bg);border:1px solid var(--border);border-radius:3px;color:var(--text-dim);font-size:9px;padding:0 2px" onchange="workers[${i}].role=this.value">
        <option value="generator"${w.role==='generator'?' selected':''}>generator</option>
        <option value="analyzer"${w.role==='analyzer'?' selected':''}>analyzer</option>
        <option value="verifier"${w.role==='verifier'?' selected':''}>verifier</option>
      </select>
      <button class="btn" style="padding:1px 5px;font-size:9px" onclick="workers.splice(${i},1);renderWorkers()">x</button>
    </div>`;
  }).join('');
}

function getWorkerByRole(role) {
  return workers.find(w => w.role === role && w.status === 'registered') || workers.find(w => w.role === role) || workers[0];
}

async function probeAndRegisterWorker(w) {
  // 1. Check if worker is reachable
  try {
    const r = await fetch(w.url.replace(/\/+$/,'') + '/v1/models', {signal: AbortSignal.timeout(3000)});
    if (!r.ok) { w.status = 'unknown'; renderWorkers(); return; }
    w.status = 'reachable';
    renderWorkers();
  } catch(_) { w.status = 'unknown'; renderWorkers(); return; }

  // 2. Register on sandbox server (as both w.name and small_context_worker for DSL compatibility)
  if (!serverUp) return;
  try {
    const reg = { [w.name]: w.url };
    // First worker also registers as default creative agent
    if (workers.indexOf(w) === 0) reg['small_context_worker'] = w.url;
    await post('/api/behavior/agents', reg);
    w.status = 'registered';
    renderWorkers();
  } catch(_) { /* stay reachable */ }
}

function probeAllWorkers() {
  workers.forEach(w => probeAndRegisterWorker(w));
}

document.getElementById('btnAddWorker').addEventListener('click', () => {
  const inp = document.getElementById('newWorkerUrl');
  const url = inp.value.trim();
  if (!url) return;
  const name = url.replace(/^https?:\/\//,'').replace(/\/+$/,'');
  const w = {url, name, role: 'generator', status: 'unknown'};
  workers.push(w);
  inp.value = '';
  renderWorkers();
  probeAndRegisterWorker(w);
});
renderWorkers();
// Probe workers after server check completes
setTimeout(probeAllWorkers, 3000);
// Re-probe periodically
setInterval(probeAllWorkers, 15000);

/* Resize handle drag */
const resizeHandle = document.getElementById('resizeHandle');
const rightSidebar = document.getElementById('rightSidebar');
let resizing = false;
resizeHandle.addEventListener('mousedown', (e) => {
  resizing = true;
  resizeHandle.classList.add('active');
  e.preventDefault();
});
document.addEventListener('mousemove', (e) => {
  if (!resizing) return;
  const mainRect = document.querySelector('.main').getBoundingClientRect();
  const newWidth = mainRect.right - e.clientX;
  if (newWidth >= 200 && newWidth <= mainRect.width * 0.7) {
    rightSidebar.style.width = newWidth + 'px';
  }
});
document.addEventListener('mouseup', () => {
  resizing = false;
  resizeHandle.classList.remove('active');
});

/* Sidebar toggles */
document.getElementById('btnToggleLeft').addEventListener('click', () => {
  document.querySelector('.sidebar').classList.toggle('collapsed');
});
let savedRightWidth = null;
function toggleRightSidebar() {
  const rs = document.getElementById('rightSidebar');
  if (!rs.classList.contains('collapsed')) {
    // Collapsing — save current width
    savedRightWidth = rs.offsetWidth;
    rs.classList.add('collapsed');
    rs.style.width = '';
  } else {
    // Expanding — restore saved width
    rs.classList.remove('collapsed');
    if (savedRightWidth) rs.style.width = savedRightWidth + 'px';
    document.getElementById('workflowEditor').value = workflowYaml;
  }
}
document.getElementById('btnToggleRight').addEventListener('click', toggleRightSidebar);
document.getElementById('btnWorkflow').addEventListener('click', toggleRightSidebar);
document.getElementById('btnWorkflowSave').addEventListener('click', () => {
  workflowYaml = document.getElementById('workflowEditor').value;
});
document.getElementById('btnWorkflowReset').addEventListener('click', async () => {
  await loadDefaultWorkflow();
  document.getElementById('workflowEditor').value = workflowYaml;
});
// Workflow chat messages
let wfChatMessages = []; // [{role, content}]

function addWfChat(role, content) {
  const chat = document.getElementById('workflowChat');
  const cls = role === 'user' ? 'color:var(--accent)' : 'color:var(--text)';
  const label = role === 'user' ? 'You' : 'Worker';
  // Prepend — newest on top (Docker-style)
  chat.insertAdjacentHTML('afterbegin', `<div style="margin-bottom:8px"><span style="font-weight:600;font-size:11px;${cls}">${esc(label)}</span><div style="white-space:pre-wrap;margin-top:2px">${esc(content)}</div></div>`);
  wfChatMessages.push({role, content});
}

// Apply = instruct mode. Silently updates YAML, no chat log.
document.getElementById('btnWorkflowApplyNL').addEventListener('click', async () => {
  const nlInput = document.getElementById('workflowNL');
  const instruction = nlInput.value.trim();
  if (!instruction) return;

  const editor = document.getElementById('workflowEditor');
  const currentYaml = editor.value;
  const applyRole = document.getElementById('settingYamlApplyRole').value;
  const worker = getWorkerByRole(applyRole);
  if (!worker?.url) return;

  nlInput.value = '';
  nlInput.disabled = true;

  // Load DSL spec for instruct context
  let spec = '';
  try { spec = (await get('/api/workflow/spec')).spec || ''; } catch(_) {}

  // Instruct: spec + current YAML + instruction. Expect YAML back.
  const url = worker.url.replace(/\/+$/,'') + '/v1/chat/completions';
  const prompt = (spec ? spec + '\n\n---\n\n' : '')
    + `Current workflow YAML:\n\`\`\`yaml\n${currentYaml}\n\`\`\`\n\n${instruction}\n\nReturn only the modified YAML. No prose.`;

  try {
    const {answer} = await fetchLLMWithContinue(url, [{role:'user', content:prompt}], {temperature:0.3, max_tokens:4096, noThink:false});
    let yaml = answer.trim();
    if (yaml.startsWith('```')) yaml = yaml.replace(/^```\w*\n?/, '').replace(/\n?```$/, '');
    editor.value = yaml;
    workflowYaml = yaml;
  } catch(e) {
    addWfChat('assistant', 'Apply error: ' + e.message);
  }
  nlInput.disabled = false;
});

// Chat about YAML (Ask button) - discuss, don't modify
document.getElementById('btnWorkflowChatSend').addEventListener('click', async () => {
  const chatInput = document.getElementById('workflowChatInput');
  const question = chatInput.value.trim();
  if (!question) return;

  const editor = document.getElementById('workflowEditor');
  const currentYaml = editor.value;
  const askRole = document.getElementById('settingYamlAskRole').value;
  const askWorker = getWorkerByRole(askRole);
  if (!askWorker?.url) return;

  addWfChat('user', question);
  chatInput.value = '';
  chatInput.disabled = true;

  const url = askWorker.url.replace(/\/+$/,'') + '/v1/chat/completions';
  const messages = [{role:'user', content: `Workflow YAML:\n\`\`\`yaml\n${currentYaml}\n\`\`\`\n\n${question}`}];

  try {
    const {answer} = await fetchLLMWithContinue(url, messages, {temperature:0.3, max_tokens:2048});
    addWfChat('assistant', answer);
  } catch(e) {
    addWfChat('assistant', 'Error: ' + e.message);
  } finally {
    chatInput.disabled = false;
  }
});
document.getElementById('workflowChatInput').addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); document.getElementById('btnWorkflowChatSend').click(); }
});

/* Settings popup */
document.getElementById('btnSettings').addEventListener('click', () => {
  document.getElementById('settingsOverlay').classList.add('open');
});
document.getElementById('btnCloseSettings').addEventListener('click', () => {
  document.getElementById('settingsOverlay').classList.remove('open');
});
document.getElementById('settingsOverlay').addEventListener('click', (e) => {
  if (e.target === e.currentTarget) e.currentTarget.classList.remove('open');
});

/* Server status + start/stop */
const serverDot = document.getElementById('serverDot');
const btnStart = document.getElementById('btnStartServer');
const btnStop = document.getElementById('btnStopServer');
let serverUp = false;

function setServerStatus(status) {
  // status: 'up' | 'down' | 'starting' | 'stopping'
  serverUp = status === 'up';
  serverDot.className = 'dot' + (status==='up'?' ok': status==='starting'||status==='stopping'?' busy':'');
  btnStart.disabled = status === 'up' || status === 'starting';
  btnStop.disabled = status === 'down' || status === 'stopping';
}

async function checkServer() {
  try {
    const r = await fetch(SB() + '/health', {signal: AbortSignal.timeout(2000)});
    if (r.ok) { setServerStatus('up'); return true; }
  } catch(_) {}
  setServerStatus('down');
  return false;
}

btnStart.addEventListener('click', async () => {
  setServerStatus('starting');
  // Show command to run
  const cmd = 'python -c "import uvicorn; from kobold_sandbox.server import create_app; app = create_app(\'.\'); uvicorn.run(app, host=\'0.0.0.0\', port=5002)"';
  try {
    if (typeof require !== 'undefined') {
      require('child_process').exec('start "" "tools/start_sandbox.bat"');
    } else {
      prompt('Run this in terminal (copied to clipboard):', cmd);
      try { await navigator.clipboard.writeText(cmd); } catch(_) {}
    }
  } catch(_) {}
  // Poll until up
  for (let i = 0; i < 20; i++) {
    await new Promise(r => setTimeout(r, 2000));
    if (await checkServer()) return;
  }
  setServerStatus('down');
});

btnStop.addEventListener('click', async () => {
  setServerStatus('stopping');
  try {
    await fetch(SB() + '/shutdown', {method:'POST', signal: AbortSignal.timeout(3000)});
  } catch(_) {}
  await new Promise(r => setTimeout(r, 1000));
  await checkServer();
});

// Periodic health check
checkServer();
setInterval(checkServer, 10000);

// --- Thread message listeners (registered once, fire on matching messages) ---

// Claims -> parse ENTITIES/AXIOMS/HYPOTHESES into node lists
onThreadMessage('(claims)', (nodeId, msg) => {
  if (!msg.content?.trim()) return;
  const nd = nodes[nodeId]; if (!nd) return;
  nd.entities_list = parseListFromText(msg.content, 'ENTITIES');
  nd.axioms_list = parseListFromText(msg.content, 'AXIOMS');
  nd.hypotheses_list = parseListFromText(msg.content, 'HYPOTHESES');
  renderTree();
});

// Answer -> show in RESULT + trigger table
onThreadMessage('(answer)', (nodeId, msg) => {
  if (!msg.content?.trim()) return;
  nodes[nodeId].showAnswer = true;
  setAnswer(nodeId, msg.content, null, msg.think || '');
  // Trigger table parse on analyzer
  const analyzer = getWorkerByRole('analyzer');
  if (analyzer?.url) {
    sendToWorker(nodeId, analyzer, WORKER_PROMPTS.table(msg.content), 'table', {temperature:0.1, max_tokens:2048});
  }
});

// Table → parse into entity child nodes
onThreadMessage('(table)', (nodeId, msg) => {
  if (!msg.content?.trim()) return;
  parseTableToEntities(nodeId, msg.content);
});

setS('ok','Ready');
