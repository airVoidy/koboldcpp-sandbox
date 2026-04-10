// Channel Content Panel - messages render + send

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
    const res = await shellExec(`/cpost ${msg}`, true, 'CMD');
    if (!renderFromCommandResult(res)) {
      await refreshChatContainers();
    }
    setStatus('Ready');
  } catch (e) {
    setStatus('Error: ' + e.message);
  }
}

async function reactToMessage(msgId, emoji) {
  setStatus('Reacting...', true);
  try {
    const res = await shellExec(`/creact ${msgId} ${emoji}`, true, 'CMD');
    if (!renderFromCommandResult(res)) {
      await refreshChatContainers();
    }
    setStatus('Ready');
  } catch (e) {
    setStatus('Error: ' + e.message);
  }
}

async function editMessageAtomic(msgPath, currentText) {
  const nextText = prompt('Edit message', currentText ?? '');
  if (nextText === null) return;
  setStatus('Saving...', true);
  try {
    await atomicPatchValue(`${msgPath}._data.content`, nextText);
    await refreshChatContainers();
    setStatus('Ready');
  } catch (e) {
    setStatus('Error: ' + e.message);
  }
}

async function deleteMessageAtomic(msgPath) {
  setStatus('Deleting...', true);
  try {
    await atomicPatchValue(`${msgPath}._data._deleted`, true);
    await refreshChatContainers();
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
    const msgPath = m.path || '';
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
        <button class="btn sm" onclick="editMessageAtomic('${esc(msgPath)}', ${JSON.stringify(content)})">Edit</button>
        <button class="btn sm" onclick="deleteMessageAtomic('${esc(msgPath)}')">Del</button>
      </div>
    </div>`;
  }).join('');
  el.scrollTop = el.scrollHeight;
}
