(() => {
  if (document.body.dataset.page !== 'C03') return;

  const body = document.querySelector('[data-bottom-logs]');
  if (!body) return;

  const token = sessionStorage.getItem('notemeld-cloud-token');
  const sessionId = document.body.dataset.sessionId;

  /* 渲染一条命令 + 结果；prompt 行显示当前工作根（分配文件夹）。 */
  const renderLine = ({ command, stdout, stderr, code, cwd } = {}) => {
    const line = document.createElement('div');
    line.className = 'terminal-line';
    line.dataset.c03Terminal = 'line';
    const loc = cwd || '.';
    line.innerHTML = `
      <div class="t-command">
        <span class="t-prompt-user">hehejie@cloud</span><span class="t-colon">:</span>
        <span class="t-path">${loc}</span><span class="t-colon">$ </span>
        <span class="t-command-text"></span>
      </div>
      ${stdout ? `<pre class="t-stdout"></pre>` : ''}
      ${stderr ? `<pre class="t-stderr"></pre>` : ''}
      ${code && code !== 0 ? `<div class="t-exit">exit=${code}</div>` : ''}`;
    line.querySelector('.t-command-text').textContent = command || '';
    if (stdout) line.querySelector('.t-stdout').textContent = stdout;
    if (stderr) line.querySelector('.t-stderr').textContent = stderr;
    return line;
  };

  const promptLine = () => {
    const wrap = document.createElement('div');
    wrap.className = 'terminal-line t-input-line';
    wrap.dataset.c03Terminal = 'input';
    wrap.innerHTML = `
      <span class="t-prompt-user">hehejie@cloud</span><span class="t-colon">:</span>
      <span class="t-path t-cwd">.</span><span class="t-colon">$ </span>
      <input class="t-input" aria-label="终端命令输入" autocomplete="off" spellcheck="false" />`;
    return wrap;
  };

  let cwd = '.';
  const inputWrap = promptLine();
  const input = inputWrap.querySelector('.t-input');
  const cwdLabel = inputWrap.querySelector('.t-cwd');

  // 初次挂载：根提示 + “仅可访问此目录”说明 + 输入行。
  body.innerHTML = '';
  const note = document.createElement('div');
  note.className = 'terminal-line t-root-note';
  note.dataset.c03Terminal = 'note';
  note.textContent = '工作根目录（仅可访问此目录）：.';
  body.append(note);
  body.append(inputWrap);
  input.focus();

  const scrollEnd = () => { body.scrollTop = body.scrollHeight; };

  const execute = async command => {
    // 用“执行中”行替换输入行，结束后再放回新输入行。
    const running = renderLine({ command, cwd });
    inputWrap.replaceWith(running);

    const finish = result => {
      if (typeof result.cwd === 'string') { cwd = result.cwd; }
      const filled = renderLine({ command, cwd, stdout: result.stdout, stderr: result.stderr, code: result.code });
      running.replaceWith(filled);
      cwdLabel.textContent = cwd;
      body.append(inputWrap);
      input.value = '';
      input.focus();
      scrollEnd();
    };

    try {
      if (token && sessionId) {
        const response = await fetch(
          `/v1/cloud/sessions/${encodeURIComponent(sessionId)}/terminal`,
          {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
            body: JSON.stringify({ command, ...(cwd !== '.' ? { cwd } : {}) }),
          }
        );
        const payload = await response.json();
        if (!response.ok) {
          throw new Error(
            (typeof payload.detail === 'string' && payload.detail) ||
            payload.msg || `HTTP ${response.status}`);
        }
        const d = payload.data;
        finish({ stdout: d.stdout, stderr: d.stderr, code: d.exit_code, cwd: d.cwd });
      } else {
        await demoRun(command, running, finish);
      }
    } catch (error) {
      const filled = renderLine({ command, cwd, stderr: error.message });
      running.replaceWith(filled);
      body.append(inputWrap);
      input.focus();
      scrollEnd();
    }
  };

  /* 静态原型演示：识别几个常见命令给出假输出，越界命令演示被拦截。 */
  const demoRun = async (command, running, finish) => {
    await new Promise(r => setTimeout(r, 250));
    const c = command.trim();
    if (c === 'echo hello-cloud') {
      finish({ stdout: 'hello-cloud', stderr: '', code: 0, cwd });
    } else if (c === 'ls' || c === 'ls -la') {
      finish({ stdout: c === 'ls' ? '新建文件.txt' : 'total 0\ndrwxr-xr-x  .\n-rw-r--r--  新建文件.txt', stderr: '', code: 0, cwd });
    } else if (c.startsWith('cat ../') || c.startsWith('cd /') || c.startsWith('sudo')) {
      const reason = c.startsWith('sudo')
        ? '命令被禁止：sudo'
        : c.startsWith('cd /')
          ? '访问被禁止：只能使用分配文件夹内的相对路径'
          : '访问被拒绝：超出分配文件夹';
      finish({ stdout: '', stderr: reason, code: 1, cwd });
    } else {
      finish({ stdout: '', stderr: '', code: 0, cwd });
    }
  };

  input.addEventListener('keydown', event => {
    if (event.key === 'Enter') {
      const command = input.value.trim();
      if (command) void execute(command);
    }
  });

  // 点击终端体任意位置聚焦输入。
  body.addEventListener('click', event => {
    if (event.target.closest('input')) return;
    input.focus();
  });
})();
