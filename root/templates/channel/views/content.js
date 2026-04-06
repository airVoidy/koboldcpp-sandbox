// Channel Content Panel — messages render + send

async function sendMessage() {
  const input = document.getElementById('chat-input');
  const msg = input.value.trim();
  if (!msg) return;
  if (!activeChannelName) {
    document.getElementById('new-ch-input').value = 'general';
    await createChannel();
  }
  input.value = '';
  setStatus('Posting...', true);
  try {
    await shellExec(`/post ${msg}`, true, `channel:${activeChannelName}`);
    const state = await fetchState(activeChannelName);
    renderFromState(state);
    setStatus('Ready');
  } catch (e) {
    setStatus('Error: ' + e.message);
  }
}

function renderMessages(items) {
  const el = document.getElementById('chat-thread');
  const msgs = items.filter(i => i.meta?.type === 'message');
  if (!msgs.length) {
    el.innerHTML = '<div class="chat-empty">No messages yet. Say something!</div>';
    return;
  }
  const currentUser = getUsername();
  el.innerHTML = msgs.map(m => {
    const meta = m.meta || {};
    const user = meta.user || 'anon';
    const ts = meta.ts ? new Date(meta.ts).toLocaleTimeString() : '';
    const content = m.data?.content || m.name || '';
    const isSelf = user === currentUser;
    return `<div class="chat-msg${isSelf ? ' self' : ''}">
      <div class="msg-hdr"><span class="msg-user">${esc(user)}</span><span class="msg-ts">${esc(ts)}</span></div>
      <div class="msg-content">${esc(content)}</div>
    </div>`;
  }).join('');
  el.scrollTop = el.scrollHeight;
}
