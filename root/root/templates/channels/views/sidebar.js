// Channels Sidebar — render + actions

function renderChannelList(channels) {
  const el = document.getElementById('channel-list');
  if (!channels.length) { el.innerHTML = '<div class="chat-empty" style="font-size:10px">No channels</div>'; return; }
  el.innerHTML = channels.map(ch => {
    const name = ch.meta?.name || ch.name;
    const active = name === activeChannelName ? ' active' : '';
    return `<div class="channel-item${active}" onclick="selectChannel('${esc(name)}')"><span class="ch-hash">#</span> ${esc(name)}</div>`;
  }).join('');
}

async function createChannel() {
  const input = document.getElementById('new-ch-input');
  const name = input.value.trim();
  if (!name) return;
  input.value = '';
  setStatus('Creating channel...', true);
  try {
    const res = await shellExec(`/cmkchannel ${name}`, true, 'CMD');
    activeChannelName = name;
    localStorage.setItem('pchat_channel', name);
    if (!renderFromCommandResult(res)) {
      await refreshChatContainers();
    }
    setStatus('Ready');
  } catch (e) { setStatus('Error: ' + e.message); }
}

async function selectChannel(name) {
  activeChannelName = name;
  localStorage.setItem('pchat_channel', name);
  document.getElementById('channel-label').innerHTML = '# <strong>' + esc(name) + '</strong>';
  setStatus('Loading...', true);
  try {
    const res = await shellExec(`/cselect ${name}`, true, 'CMD');
    if (!renderFromCommandResult(res)) {
      await refreshChatContainers();
    }
    setStatus('Ready');
  } catch (e) { setStatus('Error: ' + e.message); }
}
