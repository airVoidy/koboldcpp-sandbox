

    var resultEl = document.getElementById('result');
    var logEl = document.getElementById('log');
    var schemaResultEl = document.getElementById('schemaResult');
    var imageResultEl = document.getElementById('imageResult');
    var imagePreviewEl = document.getElementById('imagePreview');
    var chatTranscriptEl = document.getElementById('chatTranscript');
    var sessionListEl = document.getElementById('sessionList');
    var clientErrorEl = document.getElementById('clientError');
    var imageModalEl = document.getElementById('imageModal');
    var modalImagePromptEl = document.getElementById('modalImagePrompt');
    var modalImagePreviewEl = document.getElementById('modalImagePreview');
    var modalImageResultEl = document.getElementById('modalImageResult');
    var currentSessionId = 'default';

    function byId(id) {
      return document.getElementById(id);
    }

    function showClientError(error) {
      var text = (error && error.message) ? (error.name + ': ' + error.message) : String(error || 'Unknown error');
      if (clientErrorEl) {
        clientErrorEl.textContent = text;
        clientErrorEl.className = '';
      }
      if (window.console && console.error) {
        console.error(error);
      }
    }

    function clearClientError() {
      if (clientErrorEl) {
        clientErrorEl.textContent = '';
        clientErrorEl.className = 'hidden';
      }
    }

    function requestJson(method, url, body, onSuccess) {
      clearClientError();
      var xhr = new XMLHttpRequest();
      xhr.open(method, url, true);
      xhr.setRequestHeader('Content-Type', 'application/json');
      xhr.onreadystatechange = function () {
        if (xhr.readyState !== 4) {
          return;
        }
        if (xhr.status < 200 || xhr.status >= 300) {
          showClientError(new Error('HTTP ' + xhr.status + ' for ' + url));
          return;
        }
        try {
          onSuccess(xhr.responseText ? JSON.parse(xhr.responseText) : {});
        } catch (error) {
          showClientError(error);
        }
      };
      xhr.send(body ? JSON.stringify(body) : null);
    }

    function escapeHtml(text) {
      return String(text || '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;');
    }

    function showTab(tabId) {
      var panels = document.querySelectorAll('.tab-panel');
      var buttons = document.querySelectorAll('.tab-button');
      var i;
      for (i = 0; i < panels.length; i += 1) {
        panels[i].className = panels[i].className.replace(/\s*active\b/g, '');
        if (panels[i].id === tabId) {
          panels[i].className += ' active';
        }
      }
      for (i = 0; i < buttons.length; i += 1) {
        buttons[i].className = buttons[i].className.replace(/\s*active\b/g, '');
        if (buttons[i].getAttribute('data-tab') === tabId) {
          buttons[i].className += ' active';
        }
      }
    }

    function renderMessageContent(text) {
      var container = document.createElement('div');
      container.className = 'bubble-body';
      var source = String(text || '');
      var regex = /```([\w+-]*)\n?([\s\S]*?)```/g;
      var lastIndex = 0;
      var match;
      while ((match = regex.exec(source)) !== null) {
        appendProse(container, source.slice(lastIndex, match.index));
        appendCode(container, match[1], match[2]);
        lastIndex = regex.lastIndex;
      }
      appendProse(container, source.slice(lastIndex));
      if (!container.firstChild) {
        appendProse(container, source);
      }
      return container;
    }

    function appendProse(container, text) {
      var trimmed = String(text || '');
      if (!trimmed.replace(/\s+/g, '')) {
        return;
      }
      var blocks = trimmed.split(/\n{2,}/);
      var i;
      for (i = 0; i < blocks.length; i += 1) {
        if (!blocks[i].replace(/\s+/g, '')) {
          continue;
        }
        var p = document.createElement('p');
        p.textContent = blocks[i].replace(/^\s+|\s+$/g, '');
        container.appendChild(p);
      }
    }

    function appendCode(container, lang, code) {
      var card = document.createElement('div');
      card.className = 'code-card';
      var head = document.createElement('div');
      head.className = 'code-head';
      var label = document.createElement('span');
      label.textContent = lang || 'code';
      var btn = document.createElement('button');
      btn.className = 'secondary code-imagegen-button';
      btn.setAttribute('type', 'button');
      btn.setAttribute('data-prompt', String(code || '').replace(/^\s+|\s+$/g, ''));
      btn.textContent = 'Image Gen';
      var pre = document.createElement('pre');
      var codeEl = document.createElement('code');
      codeEl.textContent = String(code || '').replace(/^\s+|\s+$/g, '');
      pre.appendChild(codeEl);
      head.appendChild(label);
      head.appendChild(btn);
      card.appendChild(head);
      card.appendChild(pre);
      container.appendChild(card);
    }

    function renderTranscript(entries) {
      chatTranscriptEl.innerHTML = '';
      var hasChats = false;
      var i;
      for (i = 0; i < entries.length; i += 1) {
        if (entries[i].kind !== 'chat') {
          continue;
        }
        hasChats = true;
        renderBubble((entries[i].request && entries[i].request.nickname) || 'User', 'prompt', (entries[i].request && entries[i].request.message) || '', 'user');
        renderBubble('Assistant', 'response', entries[i].response_text || '', 'assistant');
      }
      if (!hasChats) {
        var empty = document.createElement('div');
        empty.className = 'muted';
        empty.textContent = 'Conversation is empty.';
        chatTranscriptEl.appendChild(empty);
      }
      chatTranscriptEl.scrollTop = chatTranscriptEl.scrollHeight;
    }

    function renderBubble(title, meta, content, kind) {
      var bubble = document.createElement('div');
      bubble.className = kind === 'user' ? 'bubble user' : 'bubble';
      var head = document.createElement('div');
      head.className = 'bubble-head';
      head.innerHTML = '<strong>' + escapeHtml(title) + '</strong><span>' + escapeHtml(meta) + '</span>';
      bubble.appendChild(head);
      bubble.appendChild(renderMessageContent(content));
      chatTranscriptEl.appendChild(bubble);
    }

    function renderSessions(items) {
      sessionListEl.innerHTML = '';
      var i;
      for (i = 0; i < items.length; i += 1) {
        var item = items[i];
        var node = document.createElement('div');
        node.className = 'session-item' + (item.id === currentSessionId ? ' active' : '');
        node.setAttribute('data-session-id', item.id);
        node.innerHTML = '<div class="session-title">' + escapeHtml(item.title || item.id) + '</div><div class="muted">' + (item.message_count || 0) + ' messages</div>';
        sessionListEl.appendChild(node);
      }
    }

    function refreshSessions() {
      requestJson('GET', '/api/chat/sessions', null, function (payload) {
        renderSessions(payload.sessions || []);
      });
    }

    function refreshLog() {
      requestJson('GET', '/api/chat/log?session_id=' + encodeURIComponent(currentSessionId), null, function (payload) {
        var entries = payload.entries || [];
        var i;
        logEl.innerHTML = '';
        renderTranscript(entries);
        for (i = entries.length - 1; i >= 0; i -= 1) {
          var entry = entries[i];
          var node = document.createElement('div');
          node.className = 'entry';
          var promptText = entry.composed_prompt || ((entry.request && entry.request.prompt) || '');
          node.innerHTML = '<div><strong>' + escapeHtml(entry.kind || 'chat') + '</strong></div>' +
            '<div style="margin-top:8px"><strong>Request</strong></div>' +
            '<pre>' + escapeHtml(JSON.stringify(entry.request, null, 2)) + '</pre>' +
            '<div style="margin-top:8px"><strong>Prompt</strong></div>' +
            '<pre>' + escapeHtml(promptText) + '</pre>' +
            '<div style="margin-top:8px"><strong>Response</strong></div>' +
            '<pre>' + escapeHtml(entry.response_text || '') + '</pre>';
          if (entry.preview_image) {
            var img = document.createElement('img');
            img.src = 'data:image/png;base64,' + entry.preview_image;
            img.alt = 'preview';
            img.style.marginTop = '8px';
            img.style.maxWidth = '100%';
            img.style.border = '1px solid #d8cdbf';
            img.style.borderRadius = '12px';
            node.appendChild(img);
          }
          logEl.appendChild(node);
        }
        if (!entries.length) {
          logEl.innerHTML = '<div class="muted">Log is empty.</div>';
        }
        refreshSessions();
      });
    }

    function sendChat() {
      requestJson('POST', '/api/chat', {
        session_id: currentSessionId,
        nickname: byId('nickname').value || null,
        user_context: byId('userContext').value || null,
        system_prompt: byId('systemPrompt').value || null,
        message: byId('message').value,
        model: byId('model').value || null
      }, function (payload) {
        resultEl.textContent = payload.response_text || JSON.stringify(payload, null, 2);
        byId('message').value = '';
        showTab('chatTab');
        refreshLog();
      });
    }

    function resetChat() {
      requestJson('POST', '/api/chat/reset?session_id=' + encodeURIComponent(currentSessionId), null, function () {
        resultEl.textContent = 'No requests yet.';
        chatTranscriptEl.innerHTML = '<div class="muted">Conversation is empty.</div>';
        logEl.innerHTML = '<div class="muted">Log is empty.</div>';
        refreshSessions();
      });
    }

    function generateImage(target) {
      requestJson('POST', '/api/imagegen', {
        session_id: currentSessionId,
        prompt: target === 'modal' ? modalImagePromptEl.value : byId('imagePrompt').value,
        negative_prompt: byId('imageNegative').value || null,
        width: Number(byId('imageWidth').value || 768),
        height: Number(byId('imageHeight').value || 768),
        steps: Number(byId('imageSteps').value || 20),
        cfg_scale: Number(byId('imageCfg').value || 7),
        sampler_name: byId('imageSampler').value || null
      }, function (payload) {
        var image = payload.preview_image;
        if (target === 'modal') {
          modalImageResultEl.textContent = JSON.stringify(payload, null, 2);
          modalImagePreviewEl.src = image ? 'data:image/png;base64,' + image : '';
        } else {
          imageResultEl.textContent = JSON.stringify(payload, null, 2);
          imagePreviewEl.src = image ? 'data:image/png;base64,' + image : '';
          showTab('imageTab');
        }
        refreshLog();
      });
    }

    function loadSamplers() {
      requestJson('GET', '/api/imagegen/samplers', null, function (payload) {
        imageResultEl.textContent = JSON.stringify(payload, null, 2);
        if (payload.samplers && payload.samplers.length && !byId('imageSampler').value) {
          byId('imageSampler').value = payload.samplers[0];
        }
      });
    }

    function runExample() {
      var model = byId('model').value || '';
      var suffix = model ? '?model=' + encodeURIComponent(model) : '';
      requestJson('POST', '/api/logic/example' + suffix, null, function (payload) {
        resultEl.textContent = JSON.stringify(payload, null, 2);
        showTab('logicTab');
      });
    }

    function loadExampleRaw(callback) {
      requestJson('GET', '/api/logic/example/raw', null, callback);
    }

    function runStructured() {
      requestJson('POST', '/api/logic/parse-structured', {
        analysis_text: byId('message').value,
        model: byId('model').value || null
      }, function (payload) {
        schemaResultEl.textContent = JSON.stringify(payload, null, 2);
        showTab('logicTab');
      });
    }

    function convertStructured() {
      requestJson('POST', '/api/logic/parse-structured', {
        analysis_text: byId('linearSchema').value,
        model: byId('model').value || null
      }, function (payload) {
        schemaResultEl.textContent = JSON.stringify(payload, null, 2);
        showTab('logicTab');
      });
    }

    function loadExampleToMessage() {
      loadExampleRaw(function (payload) {
        byId('message').value = payload.reasoning_excerpt || payload.reasoning_text || payload.source_text;
        showTab('chatTab');
      });
    }

    function loadExampleToSchema() {
      loadExampleRaw(function (payload) {
        byId('linearSchema').value = payload.reasoning_excerpt || payload.reasoning_text;
        showTab('logicTab');
      });
    }

    function useSchemaAsMessage() {
      byId('message').value = byId('linearSchema').value;
      showTab('chatTab');
    }

    function copyManifestToMessage() {
      var text = schemaResultEl.textContent || resultEl.textContent || '';
      if (text && text !== 'No schema requests yet.' && text !== 'No requests yet.') {
        byId('message').value = text;
      }
      showTab('chatTab');
    }

    function useMessageAsImagePrompt() {
      byId('imagePrompt').value = byId('message').value;
      showTab('imageTab');
    }

    function openImageModal(promptText) {
      modalImagePromptEl.value = promptText || byId('message').value || '';
      modalImagePreviewEl.src = '';
      modalImageResultEl.textContent = 'No image generated yet.';
      imageModalEl.className = imageModalEl.className.replace(/\s*active\b/g, '') + ' active';
    }

    function closeImageModal() {
      imageModalEl.className = imageModalEl.className.replace(/\s*active\b/g, '');
    }

    function setAiryPreset() {
      byId('nickname').value = 'Airy';
      byId('userContext').value = '\u041f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u0442\u0435\u043b\u044c \u0437\u043e\u0432\u0435\u0442 \u0430\u0441\u0441\u0438\u0441\u0442\u0435\u043d\u0442\u043a\u0443 Airy, \u0436\u0435\u043d\u0441\u043a\u043e\u0433\u043e \u0440\u043e\u0434\u0430. \u041b\u044e\u0431\u0438\u0442 \u043a\u0440\u0430\u0442\u043a\u043e\u0441\u0442\u044c.';
      byId('systemPrompt').value = 'Be concise. Use a calm, direct tone.';
    }

    function setAnalystPreset() {
      byId('nickname').value = 'Analyst';
      byId('userContext').value = '\u041d\u0443\u0436\u043d\u044b \u0444\u043e\u0440\u043c\u0430\u043b\u044c\u043d\u044b\u0435 \u043e\u0433\u0440\u0430\u043d\u0438\u0447\u0435\u043d\u0438\u044f \u0438 \u043c\u0438\u043d\u0438\u043c\u0443\u043c \u0441\u043b\u043e\u0432.';
      byId('systemPrompt').value = 'Focus on constraints, explicit formulas, and clean structure.';
    }

    function clearPrompts() {
      byId('nickname').value = '';
      byId('userContext').value = '';
      byId('systemPrompt').value = '';
    }

    function createSession() {
      requestJson('POST', '/api/chat/sessions', { title: '' }, function (payload) {
        currentSessionId = payload.session.id;
        resultEl.textContent = 'No requests yet.';
        refreshLog();
        showTab('chatTab');
      });
    }

    function switchSession(sessionId) {
      currentSessionId = sessionId;
      resultEl.textContent = 'No requests yet.';
      refreshLog();
      showTab('chatTab');
    }

    function bindEvents() {
      var tabButtons = document.querySelectorAll('.tab-button');
      var i;
      for (i = 0; i < tabButtons.length; i += 1) {
        tabButtons[i].onclick = function () { showTab(this.getAttribute('data-tab')); };
      }
      byId('sendChat').onclick = sendChat;
      byId('runExample').onclick = runExample;
      byId('runStructured').onclick = runStructured;
      byId('refreshLog').onclick = refreshLog;
      byId('presetAiry').onclick = setAiryPreset;
      byId('presetAnalyst').onclick = setAnalystPreset;
      byId('clearPrompts').onclick = clearPrompts;
      byId('resetChat').onclick = resetChat;
      byId('newSession').onclick = createSession;
      byId('convertStructured').onclick = convertStructured;
      byId('useSchemaAsMessage').onclick = useSchemaAsMessage;
      byId('loadExampleMessage').onclick = loadExampleToMessage;
      byId('loadExampleSchema').onclick = loadExampleToSchema;
      byId('copyManifestToMessage').onclick = copyManifestToMessage;
      byId('generateImage').onclick = function () { generateImage('panel'); };
      byId('loadSamplers').onclick = loadSamplers;
      byId('useMessageAsImagePrompt').onclick = useMessageAsImagePrompt;
      byId('closeImageModal').onclick = closeImageModal;
      byId('modalGenerateImage').onclick = function () { generateImage('modal'); };
      byId('modalUseNegativeDefault').onclick = function () {
        byId('imageNegative').value = 'blurry, distorted, extra limbs, low quality';
      };
      byId('message').onkeydown = function (event) {
        event = event || window.event;
        if (event.keyCode === 13 && !event.shiftKey) {
          if (event.preventDefault) { event.preventDefault(); }
          sendChat();
          return false;
        }
      };
      document.onclick = function (event) {
        event = event || window.event;
        var target = event.target || event.srcElement;
        while (target) {
          if (target.className && String(target.className).indexOf('code-imagegen-button') >= 0) {
            openImageModal(target.getAttribute('data-prompt') || '');
            return;
          }
          if (target.className && String(target.className).indexOf('session-item') >= 0) {
            switchSession(target.getAttribute('data-session-id'));
            return;
          }
          if (target === imageModalEl) {
            closeImageModal();
            return;
          }
          target = target.parentNode;
        }
      };
      window.onerror = function (msg) {
        showClientError(msg);
      };
    }

    bindEvents();
    refreshLog();

  