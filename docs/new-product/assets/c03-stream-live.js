(() => {
  if (document.body.dataset.page !== 'C03') return;

  const scrollEl = document.querySelector('[data-session-scroll]');
  const sendBtn = document.querySelector('.cloud-composer .send-button');
  const textarea = document.querySelector('.cloud-composer textarea');
  const modelBtn = document.querySelector('.cloud-composer .model-button');
  if (!scrollEl || !sendBtn || !textarea) return;

  /* ---------- 极简 Markdown（仅覆盖会话常见语法；原型用，非生产解析器） ---------- */
  const esc = value =>
    String(value == null ? '' : value).replace(/[&<>"]/g, c =>
      ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const inline = text =>
    esc(text)
      .replace(/`([^`]+)`/g, '<code>$1</code>')
      .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
      .replace(/(^|[^*])\*([^*]+)\*/g, '$1<em>$2</em>');
  const renderMarkdown = md => {
    const lines = String(md).replace(/\r\n/g, '\n').split('\n');
    const html = [];
    let i = 0;
    let list = null;
    const closeList = () => {
      if (list) { html.push(`</${list}>`); list = null; }
    };
    while (i < lines.length) {
      const line = lines[i];
      let m;
      if ((m = line.match(/^\s*###\s+(.*)$/))) { closeList(); html.push(`<h3>${inline(m[1])}</h3>`); }
      else if ((m = line.match(/^\s*##\s+(.*)$/))) { closeList(); html.push(`<h2>${inline(m[1])}</h2>`); }
      else if ((m = line.match(/^\s*#\s+(.*)$/))) { closeList(); html.push(`<h1>${inline(m[1])}</h1>`); }
      else if ((m = line.match(/^\s*[-*]\s+(.*)$/))) {
        if (list !== 'ul') { closeList(); html.push('<ul>'); list = 'ul'; }
        html.push(`<li>${inline(m[1])}</li>`);
      } else if ((m = line.match(/^\s*\d+\.\s+(.*)$/))) {
        if (list !== 'ol') { closeList(); html.push('<ol>'); list = 'ol'; }
        html.push(`<li>${inline(m[1])}</li>`);
      } else if (line.trim() === '') {
        closeList();
      } else {
        closeList();
        html.push(`<p>${inline(line)}</p>`);
      }
      i += 1;
    }
    closeList();
    return html.join('');
  };

  /* ---------- 思考面板（可折叠；reasoning 数组逐段展示） ---------- */
  const buildReasoning = (reasoning, { streaming } = {}) => {
    const parts = reasoning.filter(part => part && part.trim());
    if (!parts.length && !streaming) return null;
    const wrap = document.createElement('div');
    wrap.className = 'message agent-message';
    wrap.dataset.streamTurn = 'reasoning';
    wrap.innerHTML = `
      <div class="reason-card">
        <button type="button" class="reason-head" aria-expanded="false">
          <i data-icon="chevron-right" class="reason-chev"></i>
          <i data-icon="brain" class="reason-icon"></i>
          <span>思考过程</span>
          <span class="reason-dots" ${streaming ? '' : 'hidden'}></span>
        </button>
        <div class="reason-body" hidden>
          ${parts.map(part => `<div class="reason-part">${esc(part)}</div>`).join('')}
        </div>
      </div>`;
    const head = wrap.querySelector('.reason-head');
    const body = wrap.querySelector('.reason-body');
    const chev = wrap.querySelector('.reason-chev');
    head.addEventListener('click', () => {
      const open = head.getAttribute('aria-expanded') === 'true';
      head.setAttribute('aria-expanded', String(!open));
      body.hidden = open;
      chev.setAttribute('data-icon', open ? 'chevron-right' : 'chevron-down');
      window.lucide?.createIcons({ attrs: { 'stroke-width': 2, 'aria-hidden': 'true' } });
    });
    wrap.update = ({ reasoning: next, streaming: nextStreaming }) => {
      body.innerHTML = next.filter(part => part && part.trim())
        .map(part => `<div class="reason-part">${esc(part)}</div>`).join('');
      wrap.querySelector('.reason-dots').hidden = !nextStreaming;
    };
    return wrap;
  };

  const buildAnswer = () => {
    const wrap = document.createElement('div');
    wrap.className = 'message agent-message';
    wrap.dataset.streamTurn = 'answer';
    wrap.innerHTML = `<div class="agent-card answer-card"><div class="answer-body"></div></div>`;
    const body = wrap.querySelector('.answer-body');
    wrap.set = text => { body.innerHTML = renderMarkdown(text); };
    return wrap;
  };

  /* ---------- 一轮：用户气泡 + 思考 + 正文（占位容器） ---------- */
  const startTurn = userText => {
    const user = document.createElement('div');
    user.className = 'message user-message';
    user.innerHTML = `<div class="message-bubble">${esc(userText)}</div>`;
    const reasoningParts = [];
    let reasoning = buildReasoning([], { streaming: true });
    let answer = buildAnswer();
    const group = document.createElement('div');
    group.className = 'turn-group';
    group.append(user);
    if (reasoning) group.append(reasoning);
    group.append(answer);
    scrollEl.append(group);

    let answerText = '';
    const api = {
      reasoning(part) {
        if (reasoningParts.length === 0) {
          // 首段思考出现，确保 reasoning 卡片已在 answer 之前
          if (!reasoning) { reasoning = buildReasoning([], { streaming: true }); group.insertBefore(reasoning, answer); }
        }
        reasoningParts.push(part);
        reasoning.update({ reasoning: reasoningParts, streaming: answerText === '' });
      },
      delta(text) {
        answerText += text;
        answer.set(answerText);
      },
      error(message) {
        answer.set(`**${message}**`);
        answer.querySelector('.answer-card').classList.add('is-error');
        if (reasoning) reasoning.update({ reasoning: reasoningParts, streaming: false });
      },
      done() {
        if (reasoning) reasoning.update({ reasoning: reasoningParts, streaming: false });
      },
    };
    return api;
  };

  const scrollToEnd = () => { scrollEl.scrollTop = scrollEl.scrollHeight; };

  /* ---------- 真实 /stream（fetch SSE） ---------- */
  const token = sessionStorage.getItem('notemeld-cloud-token');
  const sessionId = document.body.dataset.sessionId;

  const consumeSSE = async (response, api) => {
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const frames = buffer.split('\n\n');
      buffer = frames.pop() || '';
      for (const frame of frames) {
        const line = frame.split('\n').find(l => l.startsWith('data:'));
        if (!line) continue;
        let evt;
        try { evt = JSON.parse(line.slice(5).trim()); } catch { continue; }
        const type = String(evt.type);
        if (type === 'reasoning') api.reasoning(String(evt.text || ''));
        else if (type === 'delta') api.delta(String(evt.text || ''));
        else if (type === 'error') api.error(String(evt.message || '执行失败'));
        else if (type === 'done') api.done();
        scrollToEnd();
      }
    }
  };

  /* ---------- 静态原型演示回退（无登录态时） ---------- */
  const demo = api => new Promise(resolve => {
    const script = [
      ['reason', '用户希望用 Markdown 列出三个学习方法。'],
      ['reason', '我需要给出清晰、可执行的三条建议。'],
      ['delta', '## 三个学习方法\n\n'],
      ['delta', '1. **间隔重复**：按遗忘曲线复习，长期记忆更牢。\n'],
      ['delta', '2. **主动回忆**：合上书自测，而非反复阅读。\n'],
      ['delta', '3. **费曼讲解**：用自己的话讲给别人，找到知识盲区。'],
    ];
    let i = 0;
    const timer = setInterval(() => {
      if (i >= script.length) {
        clearInterval(timer); api.done(); resolve(); return;
      }
      const [kind, text] = script[i];
      if (kind === 'reason') api.reasoning(text); else api.delta(text);
      scrollToEnd();
      i += 1;
    }, 280);
  });

  /* ---------- 发送 ---------- */
  let submitting = false;
  const onSubmit = async event => {
    event.preventDefault();
    const text = textarea.value.trim();
    // 用内部标志防重复；不依赖 sendBtn.disabled——其它脚本的模型可用性
    // 检查在演示态会把按钮误判为禁用。
    if (!text || submitting) return;
    submitting = true;
    const api = startTurn(text);
    textarea.value = '';
    textarea.dispatchEvent(new Event('input', { bubbles: true }));
    scrollToEnd();
    try {
      if (token && sessionId) {
        const modelId = modelBtn?.dataset.modelId;
        const response = await fetch(
          `/v1/cloud/sessions/${encodeURIComponent(sessionId)}/stream`,
          {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
            body: JSON.stringify({
              input: text,
              request_id: crypto.randomUUID(),
              ...(modelId ? { model_id: modelId } : {}),
              authorization_mode: 'default',
            }),
          }
        );
        if (!response.ok || !response.body) {
          const detail = await response.text().catch(() => '');
          throw new Error(detail.slice(0, 120) || `HTTP ${response.status}`);
        }
        await consumeSSE(response, api);
      } else {
        await demo(api);
      }
    } catch (error) {
      api.error(error.message);
    } finally {
      submitting = false;
    }
  };

  // 捕获阶段绑定，避免被其它脚本的按钮处理或 disabled 逻辑拦截。
  sendBtn.addEventListener('click', onSubmit, true);
  const form = document.querySelector('.conversation-composer');
  form?.addEventListener('submit', onSubmit, true);

  window.lucide?.createIcons({ attrs: { 'stroke-width': 2, 'aria-hidden': 'true' } });
})();
