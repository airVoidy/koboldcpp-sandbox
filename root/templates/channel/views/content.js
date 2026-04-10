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
    await shellExec(`/cpost ${msg}`, true, 'CMD');
    try {
      await refreshChatContainers();
    } catch {
      const state = await fetchState(activeChannelName);
      renderFromState(state);
    }
    setStatus('Ready');
  } catch (e) {
    setStatus('Error: ' + e.message);
  }
}

async function reactToMessage(msgId, emoji) {
  setStatus('Reacting...', true);
  try {
    await shellExec(`/creact ${msgId} ${emoji}`, true, 'CMD');
    try {
      await refreshChatContainers();
    } catch {
      const state = await fetchState(activeChannelName);
      renderFromState(state);
    }
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
    const msgId = m.name || '';
    const reactions = m.data?.reactions || {};
    const isSelf = user === currentUser;
    const reactionHtml = Object.entries(reactions).map(([emoji, info]) => {
      const users = Array.isArray(info?.users) ? info.users : [];
      const count = typeof info?.count === 'number' ? info.count : users.length;
      const self = users.includes(currentUser) ? ' self' : '';
      return `<span class="msg-reaction${self}">${esc(emoji)} ${esc(String(count))}</span>`;
    }).join('');
    return `<div class="chat-msg${isSelf ? ' self' : ''}">
      <div class="msg-hdr"><span class="msg-user">${esc(user)}</span><span class="msg-ts">${esc(ts)}</span></div>
      <div class="msg-content">${esc(content)}</div>
      ${reactionHtml ? `<div class="msg-reactions">${reactionHtml}</div>` : ''}
      <div class="msg-actions">
        <button class="btn sm" onclick="reactToMessage('${esc(msgId)}','👍')">👍</button>
      </div>
    </div>`;
  }).join('');
  el.scrollTop = el.scrollHeight;
}
