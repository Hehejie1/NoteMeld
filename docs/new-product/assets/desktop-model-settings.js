/*
 * D09 模型设置（桌面端）
 * 三端统一「添加模型」语义，共享资产见 assets/model-vendor-registry.js：
 *  - 厂商预设自动带出协议与 Base URL；也可手动自定义
 *  - 模型列表默认从 models/list 接口获取，支持多选；每个模型独立上下文窗口
 *  - 编辑回显、密钥显示/隐藏、统一校验、保存后测试闭环
 *  - 跨端分享：notemeld://model-add（二维码占位 + 复制），载荷永不包含 API Key
 * 原型为纯内存存储；正式版写 Desktop SQLite providers/models，密钥存系统 Keychain（见 feature-registry）。
 */
(() => {
  const R = window.ModelVendorRegistry;
  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
  const uid = () => (crypto.randomUUID ? crypto.randomUUID() : `d${Date.now()}${Math.random().toString(16).slice(2)}`);

  // —— 内存数据：Provider / Model 两层 ——
  const ark = R.getVendor('volcengine-ark');
  const ds = R.getVendor('deepseek');
  const providers = [
    { id: uid(), vendorId: 'volcengine-ark', displayName: ark.name, protocol: ark.protocol, baseUrl: ark.baseUrl, authType: 'bearer', apiKey: '', scope: 'local' },
    { id: uid(), vendorId: 'deepseek', displayName: ds.name, protocol: ds.protocol, baseUrl: ds.baseUrl, authType: 'bearer', apiKey: 'sk-demo', scope: 'local' },
    { id: uid(), vendorId: 'ollama', displayName: '本地 Ollama', protocol: 'ollama', baseUrl: 'http://localhost:11434', authType: 'none', apiKey: '', scope: 'local' }
  ];
  const models = [
    { id: uid(), providerId: providers[0].id, modelId: 'doubao-seed-1-6', contextWindow: 256000, enabled: true, isDefault: true, testStatus: 'untested' },
    { id: uid(), providerId: providers[0].id, modelId: 'doubao-seed-1-5-vision', contextWindow: 128000, enabled: true, isDefault: false, testStatus: 'untested' },
    { id: uid(), providerId: providers[1].id, modelId: 'deepseek-chat', contextWindow: 64000, enabled: true, isDefault: false, testStatus: 'ok' },
    { id: uid(), providerId: providers[2].id, modelId: 'llama3.3:70b', contextWindow: 128000, enabled: true, isDefault: false, testStatus: 'untested' }
  ];

  // 表单状态
  let editingProviderId = null;
  let editingModel = null;
  let selectedVendorId = null;
  let available = [];                 // [{id, contextWindow}]
  let checked = new Set();
  let selectedModelId = null;

  const dialog = $('[data-model-dialog]');
  const vendorPanel = $('[data-vendor-panel]');
  const formPanel = $('[data-form-panel]');
  const shareDialog = $('[data-share-dialog]');
  const importDialog = $('[data-import-dialog]');
  const form = $('[data-model-form]');
  const el = name => form.elements[name];
  const currentProtocol = () => el('protocol').value;
  const effectiveKey = () => {
    const typed = el('apiKey').value.trim();
    if (typed) return typed;
    return providers.find(p => p.id === editingProviderId)?.apiKey || '';
  };

  const icon = name => { const node = document.createElement('i'); node.setAttribute('data-lucide', name); return node; };
  const refreshIcons = () => window.lucide?.createIcons({ attrs: { 'stroke-width': 2 } });
  const swapIcon = (container, name) => {
    const old = container.querySelector('svg, i');
    const node = icon(name);
    if (old) old.replaceWith(node); else container.prepend(node);
    refreshIcons();
  };

  // —— Toast ——
  const toastHost = document.createElement('div');
  toastHost.className = 'model-toast-host';
  document.body.append(toastHost);
  const toast = message => {
    const node = document.createElement('div');
    node.className = 'model-toast';
    node.textContent = message;
    toastHost.append(node);
    refreshIcons();
    setTimeout(() => { node.classList.add('show'); }, 10);
    setTimeout(() => { node.classList.remove('show'); setTimeout(() => node.remove(), 250); }, 2600);
  };

  // —— 弹窗面板切换 ——
  const showVendorPanel = () => { vendorPanel.hidden = false; formPanel.hidden = true; };
  const showFormPanel = () => { vendorPanel.hidden = true; formPanel.hidden = false; };
  const openDialog = () => { renderVendorGrid(); showVendorPanel(); dialog.showModal(); };
  const closeDialog = () => dialog.close();

  // —— 列表渲染：按 Provider 分组 ——
  const render = () => {
    const host = $('[data-model-groups]');
    host.replaceChildren();
    if (!models.length) {
      const empty = document.createElement('div');
      empty.className = 'model-empty-desktop';
      empty.textContent = '还没有模型。点击右上角「添加模型」，选择厂商或粘贴分享信息。';
      host.append(empty);
      return;
    }
    providers.forEach(provider => {
      const items = models.filter(m => m.providerId === provider.id);
      if (!items.length) return;
      const vendor = R.getVendor(provider.vendorId);
      const head = document.createElement('div');
      head.className = 'model-group-head';
      head.innerHTML = `<strong>${provider.displayName}</strong><span>${R.getProtocol(provider.protocol)?.label || provider.protocol} · ${R.trimUrl(provider.baseUrl) || '自定义地址'}${provider.apiKey ? '' : ' · 未填密钥'}</span>`;
      host.append(head);
      items.forEach(item => {
        const row = document.createElement('div');
        row.className = 'model-row';
        const mark = document.createElement('span');
        mark.className = 'model-avatar';
        mark.append(icon(vendor?.icon || 'box'));
        const body = document.createElement('div');
        const name = document.createElement('strong');
        name.textContent = item.modelId;
        const meta = document.createElement('small');
        meta.textContent = `上下文 ${Number(item.contextWindow).toLocaleString()} tokens${item.testStatus === 'ok' ? ' · 连接测试通过' : item.testStatus === 'failed' ? ' · 连接测试未通过' : ''}`;
        body.append(name, meta);
        row.append(mark, body);
        if (item.isDefault) {
          const tag = document.createElement('span');
          tag.className = 'tag green';
          tag.textContent = '默认';
          row.append(tag);
        }
        const actions = document.createElement('span');
        actions.className = 'model-row-actions';
        const shareBtn = document.createElement('button');
        shareBtn.type = 'button';
        shareBtn.dataset.modelShare = item.id;
        shareBtn.title = '分享给其他端';
        shareBtn.append(icon('share-2'));
        const editBtn = document.createElement('button');
        editBtn.type = 'button';
        editBtn.dataset.modelEdit = item.id;
        editBtn.textContent = '编辑';
        const delBtn = document.createElement('button');
        delBtn.type = 'button';
        delBtn.className = 'danger-text';
        delBtn.dataset.modelDelete = item.id;
        delBtn.title = '删除';
        delBtn.append(icon('trash-2'));
        actions.append(shareBtn, editBtn, delBtn);
        row.append(actions);
        host.append(row);
      });
    });
    refreshIcons();
  };

  // —— 厂商网格 ——
  const renderVendorGrid = () => {
    const host = $('[data-vendor-grid]');
    host.replaceChildren();
    R.MODEL_VENDORS.forEach(vendor => {
      const button = document.createElement('button');
      button.type = 'button';
      button.dataset.vendorId = vendor.id;
      if (vendor.custom) button.classList.add('wide');
      if (vendor.unsupported) {
        button.classList.add('is-unsupported');
        button.disabled = true;
        button.title = vendor.unsupported;
      }
      const mark = document.createElement('span');
      mark.className = 'vendor-mark';
      mark.append(icon(vendor.icon));
      const text = document.createElement('span');
      text.className = 'vendor-name';
      text.textContent = vendor.name;
      button.append(mark, text);
      if (!vendor.custom) {
        const chevron = icon('chevron-right');
        chevron.classList.add('vendor-chevron');
        button.append(chevron);
      }
      host.append(button);
    });
    refreshIcons();
  };

  // —— 协议联动密钥字段 ——
  const syncProtocolUI = () => {
    const proto = currentProtocol();
    const keyField = $('[data-key-field]');
    keyField.hidden = proto === 'ollama';
    const keyInput = el('apiKey');
    if (proto === 'ollama') {
      keyInput.value = '';
      keyInput.type = 'password';
      $('[data-key-toggle-text]').textContent = '显示';
    }
  };
  el('protocol').addEventListener('change', syncProtocolUI);

  // —— 模型多选区 ——
  const renderOptions = () => {
    const host = $('[data-model-options]');
    host.replaceChildren();
    available.forEach(item => {
      const row = document.createElement('label');
      row.className = 'model-option';
      const box = document.createElement('input');
      box.type = 'checkbox';
      box.checked = checked.has(item.id);
      box.addEventListener('change', () => {
        if (box.checked) checked.add(item.id); else checked.delete(item.id);
        ctxWrap.hidden = !box.checked;
        ctxInput.value = String(item.contextWindow || R.DEFAULT_CONTEXT);
      });
      const span = document.createElement('span');
      span.className = 'model-option-name';
      span.textContent = item.id;
      const ctxWrap = document.createElement('span');
      ctxWrap.className = 'model-context-cell';
      ctxWrap.hidden = !box.checked;
      const ctxLabel = document.createElement('em');
      ctxLabel.textContent = '上下文 tokens';
      const ctxInput = document.createElement('input');
      ctxInput.type = 'number';
      ctxInput.dataset.modelContext = item.id;
      ctxInput.setAttribute('aria-label', `${item.id} 上下文窗口（tokens）`);
      ctxInput.min = String(R.CONTEXT_MIN);
      ctxInput.max = String(R.CONTEXT_MAX);
      ctxInput.value = String(item.contextWindow || R.DEFAULT_CONTEXT);
      ctxInput.addEventListener('input', () => { item.contextWindow = Number(ctxInput.value); });
      ctxWrap.append(ctxLabel, ctxInput);
      row.append(box, span, ctxWrap);
      host.append(row);
    });
  };

  const resetFormStatus = () => {
    const err = $('[data-form-error]');
    err.hidden = true; err.textContent = '';
    const ts = $('[data-test-status]');
    ts.hidden = true; ts.textContent = ''; ts.dataset.result = '';
    const note = $('[data-url-note]');
    note.hidden = true; note.textContent = '';
  };

  const openCreate = vendorId => {
    const vendor = R.getVendor(vendorId);
    if (!vendor || vendor.unsupported) { toast(vendor?.unsupported || '暂不支持该厂商'); return; }
    editingProviderId = null;
    editingModel = null;
    selectedVendorId = vendor.custom ? null : vendor.id;
    form.reset();
    el('protocol').value = vendor.protocol === 'bedrock' ? 'openai-compatible' : vendor.protocol;
    el('baseUrl').value = vendor.baseUrl || '';
    el('displayName').value = vendor.custom ? '' : vendor.name;
    el('apiKey').placeholder = '填写 API Key';
    available = [];
    checked = new Set();
    if (vendor.protocol === 'anthropic-messages') {
      available = R.ANTHROPIC_BUILTIN_MODELS.map(m => ({ ...m }));
      available.forEach(m => checked.add(m.id));
      $('[data-fetch-status]').textContent = 'Anthropic 无公开列表接口，已列出常用内置模型，也可手动添加。';
    } else {
      $('[data-fetch-status]').textContent = vendor.urlNote || '填写 Base URL 与密钥后，从接口获取模型，或手动添加。';
    }
    if (vendor.urlNote) {
      const note = $('[data-url-note]');
      note.textContent = vendor.urlNote; note.hidden = false;
    }
    $('[data-form-title]').textContent = '添加模型';
    $('[data-form-eyebrow]').textContent = '新建配置';
    resetFormStatus();
    syncProtocolUI();
    renderOptions();
    showFormPanel();
  };

  const openEdit = modelItem => {
    const provider = providers.find(p => p.id === modelItem.providerId);
    if (!provider) return;
    editingProviderId = provider.id;
    editingModel = modelItem;
    selectedVendorId = R.getVendor(provider.vendorId) && !R.getVendor(provider.vendorId).custom ? provider.vendorId : null;
    form.reset();
    el('displayName').value = provider.displayName;
    el('protocol').value = provider.protocol;
    el('baseUrl').value = provider.baseUrl;
    el('apiKey').value = '';
    el('apiKey').placeholder = provider.apiKey ? '已设置密钥；留空保留不修改' : '填写 API Key';
    available = [{ id: modelItem.modelId, contextWindow: modelItem.contextWindow }];
    checked = new Set([modelItem.modelId]);
    $('[data-form-title]').textContent = '编辑模型';
    $('[data-form-eyebrow]').textContent = provider.displayName;
    $('[data-fetch-status]').textContent = '只显示当前模型；重新获取列表可加入同服务商的其他模型。';
    resetFormStatus();
    syncProtocolUI();
    renderOptions();
    showFormPanel();
    dialog.showModal();
  };

  // —— 获取模型列表 ——
  $('[data-fetch-models]').addEventListener('click', async event => {
    const button = event.currentTarget;
    const baseUrl = el('baseUrl').value.trim();
    const protocol = currentProtocol();
    const status = $('[data-fetch-status]');
    if (protocol === 'anthropic-messages') {
      const map = new Map(available.map(m => [m.id, m]));
      R.ANTHROPIC_BUILTIN_MODELS.forEach(m => {
        if (!map.has(m.id)) map.set(m.id, { ...m });
        checked.add(m.id);
      });
      available = [...map.values()].sort((a, b) => a.id.localeCompare(b.id));
      renderOptions();
      status.textContent = '已列出 Anthropic 常用内置模型，可直接多选或手动添加。';
      return;
    }
    if (!R.isValidHttpUrl(baseUrl)) { status.textContent = '请先填写正确的 Base URL。'; return; }
    if (!R.isLocalUrl(baseUrl) && !/^https:\/\//i.test(baseUrl)) {
      status.textContent = '非本机地址必须使用 HTTPS（localhost 可用 HTTP）。'; return;
    }
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 12000);
    button.disabled = true;
    status.textContent = '正在获取模型列表…';
    try {
      const list = await R.fetchModelList({ protocol, baseUrl, apiKey: effectiveKey(), signal: controller.signal });
      const map = new Map(available.map(m => [m.id, m]));
      list.forEach(m => { if (!map.has(m.id)) map.set(m.id, m); });
      available = [...map.values()].sort((a, b) => a.id.localeCompare(b.id));
      list.forEach(m => checked.add(m.id));
      renderOptions();
      status.textContent = `已获取 ${list.length} 个模型，可多选；请逐个确认上下文窗口。`;
    } catch (error) {
      status.textContent = error.message === 'empty_list'
        ? '接口返回空列表，可手动填写模型 ID。'
        : error.name === 'AbortError'
          ? '获取超时，请检查网络与服务地址。'
          : '获取失败；请检查 URL、密钥、网络及浏览器跨域（CORS）限制。';
    } finally {
      clearTimeout(timer);
      button.disabled = false;
    }
  });

  // —— 手动添加 ——
  $('[data-manual-add]').addEventListener('click', () => {
    const input = el('manualModel');
    const value = input.value.trim();
    if (!value) { input.focus(); return; }
    if (!available.some(m => m.id === value)) available.push({ id: value, contextWindow: R.DEFAULT_CONTEXT });
    checked.add(value);
    input.value = '';
    renderOptions();
  });

  // —— 密钥显隐 ——
  $('[data-key-toggle]').addEventListener('click', () => {
    const input = el('apiKey');
    const showing = input.type === 'text';
    input.type = showing ? 'password' : 'text';
    $('[data-key-toggle-text]').textContent = showing ? '显示' : '隐藏';
    swapIcon($('[data-key-toggle]'), showing ? 'eye' : 'eye-off');
  });

  // —— 测试连接 ——
  const runTest = async (button, status) => {
    const baseUrl = el('baseUrl').value.trim();
    const protocol = currentProtocol();
    const testModel = [...checked][0];
    status.hidden = false;
    status.dataset.result = '';
    if (!R.isValidHttpUrl(baseUrl) || (!R.isLocalUrl(baseUrl) && !/^https:\/\//i.test(baseUrl))) {
      status.dataset.result = 'error';
      status.textContent = '请先填写有效的接口地址。';
      return false;
    }
    if (!testModel) {
      status.dataset.result = 'error';
      status.textContent = '请先勾选至少一个模型。';
      return false;
    }
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 10000);
    button.disabled = true;
    status.textContent = '正在发送最小请求…';
    try {
      const result = await R.testConnection({ protocol, baseUrl, apiKey: effectiveKey(), model: testModel, signal: controller.signal });
      status.dataset.result = 'ok';
      status.textContent = result.message;
      return true;
    } catch (error) {
      status.dataset.result = 'error';
      status.textContent = error.name === 'AbortError'
        ? '测试超时，请检查网络和服务地址。'
        : '测试失败，请检查地址、密钥、模型与浏览器跨域（CORS）限制。';
      return false;
    } finally {
      clearTimeout(timer);
      button.disabled = false;
    }
  };
  $('[data-test-connection]').addEventListener('click', event =>
    runTest(event.currentTarget, $('[data-test-status]')));

  // —— 提交：统一校验 ——
  form.addEventListener('submit', async event => {
    event.preventDefault();
    const errorBox = $('[data-form-error]');
    const showError = message => { errorBox.textContent = message; errorBox.hidden = false; };

    const displayName = el('displayName').value.trim();
    const protocol = currentProtocol();
    const baseUrl = R.trimUrl(el('baseUrl').value);
    const typedKey = el('apiKey').value.trim();
    const selectedModels = available.filter(m => checked.has(m.id)).map(m => ({ id: m.id, contextWindow: Number(m.contextWindow) }));

    const matchedVendor = R.MODEL_VENDORS.find(v =>
      !v.custom && v.protocol === protocol && v.baseUrl && R.trimUrl(v.baseUrl) === baseUrl);
    const vendorId = selectedVendorId || matchedVendor?.id || 'custom';

    const scopeProvider = editingProviderId
      ? providers.find(p => p.id === editingProviderId)
      : providers.find(p => p.protocol === protocol && R.trimUrl(p.baseUrl) === baseUrl && p.displayName === displayName);
    const existingNames = new Set(
      models
        .filter(m => (scopeProvider && m.providerId === scopeProvider.id) && !(editingModel && m.id === editingModel.id))
        .map(m => m.modelId)
    );
    const duplicateNames = selectedModels.filter(m => existingNames.has(m.id)).map(m => m.id);

    const errors = R.validateModelConfig({
      displayName, vendorId, protocol, baseUrl,
      apiKey: typedKey,
      hasStoredKey: !!(editingProviderId && providers.find(p => p.id === editingProviderId)?.apiKey),
      models: selectedModels,
      duplicateNames
    });
    if (Object.keys(errors).length) { showError(Object.values(errors)[0]); return; }

    let provider = scopeProvider;
    if (!provider) {
      provider = {
        id: uid(), vendorId, displayName, protocol,
        baseUrl, authType: protocol === 'ollama' ? 'none' : 'bearer',
        apiKey: protocol === 'ollama' ? '' : typedKey,
        scope: 'local'
      };
      providers.push(provider);
    } else {
      provider.displayName = displayName;
      provider.protocol = protocol;
      provider.baseUrl = baseUrl;
      provider.vendorId = vendorId;
      if (typedKey) provider.apiKey = typedKey;
      if (protocol === 'ollama') provider.apiKey = '';
    }

    const firstId = selectedModels[0].id;
    if (editingModel) {
      editingModel.providerId = provider.id;
      editingModel.modelId = firstId;
      editingModel.contextWindow = selectedModels[0].contextWindow;
      selectedModels.slice(1).forEach(m => {
        if (!existingNames.has(m.id)) {
          models.push({ id: uid(), providerId: provider.id, modelId: m.id, contextWindow: m.contextWindow, enabled: true, isDefault: false, testStatus: 'untested' });
        }
      });
    } else {
      selectedModels.forEach(m => {
        models.push({ id: uid(), providerId: provider.id, modelId: m.id, contextWindow: m.contextWindow, enabled: true, isDefault: false, testStatus: 'untested' });
      });
    }

    closeDialog();
    render();
    toast(`已保存 ${selectedModels.length} 个模型（仅当前页面）`);
    const statusOk = await R.testConnection({ protocol, baseUrl, apiKey: provider.apiKey, model: firstId })
      .then(r => r.ok).catch(() => false);
    const target = models.find(m => m.providerId === provider.id && m.modelId === firstId);
    if (target) target.testStatus = statusOk ? 'ok' : 'failed';
    render();
    toast(statusOk ? '连接测试通过' : '已保存；连接测试未通过，请检查密钥或网络后在编辑页重试');
  });

  // —— 分享（不含密钥）——
  const openShare = itemId => {
    const item = models.find(m => m.id === itemId);
    const provider = item && providers.find(p => p.id === item.providerId);
    if (!item || !provider) return;
    const payload = R.buildSharePayload({
      vendorId: provider.vendorId,
      displayName: provider.displayName,
      protocol: provider.protocol,
      baseUrl: provider.baseUrl,
      models: [{ id: item.modelId, contextWindow: item.contextWindow }]
    });
    $('[data-share-uri]').value = R.encodeShare(payload);
    $('[data-share-subtitle]').textContent = `${provider.displayName} · ${item.modelId}`;
    shareDialog.showModal();
  };
  $('[data-share-copy]').addEventListener('click', async event => {
    const button = event.currentTarget;
    try {
      await navigator.clipboard.writeText($('[data-share-uri]').value);
    } catch {
      const input = $('[data-share-uri]');
      input.select();
      document.execCommand('copy');
    }
    toast('分享信息已复制（不含 API 密钥）');
    swapIcon(button, 'check');
    setTimeout(() => swapIcon(button, 'copy'), 1600);
  });

  // —— 粘贴导入 ——
  const openImport = () => {
    $('[data-import-text]').value = '';
    const status = $('[data-import-status]');
    status.textContent = '';
    status.hidden = true;
    importDialog.showModal();
  };
  const applyImport = parsed => {
    importDialog.close();
    const vendor = R.getVendor(parsed.vendorId) || R.getVendor('custom');
    editingProviderId = null;
    editingModel = null;
    selectedVendorId = vendor.custom ? null : vendor.id;
    form.reset();
    el('displayName').value = parsed.displayName || vendor.name;
    el('protocol').value = parsed.protocol;
    el('baseUrl').value = parsed.baseUrl || vendor.baseUrl || '';
    el('apiKey').value = '';
    el('apiKey').placeholder = '导入内容不含密钥，请填写 API Key';
    available = parsed.models.map(m => ({ id: m.id, contextWindow: m.contextWindow }));
    checked = new Set(parsed.models.map(m => m.id));
    $('[data-form-title]').textContent = '导入模型';
    $('[data-form-eyebrow]').textContent = '跨端导入';
    $('[data-fetch-status]').textContent = `已识别 ${parsed.models.length} 个模型；请补填 API 密钥后保存。`;
    resetFormStatus();
    syncProtocolUI();
    renderOptions();
    dialog.showModal();
    showFormPanel();
    toast('已解析分享信息，请补填密钥');
  };
  $('[data-import-parse]').addEventListener('click', () => {
    const parsed = R.decodeShare($('[data-import-text]').value);
    const status = $('[data-import-status]');
    if (!parsed) {
      status.hidden = false;
      status.textContent = '无法识别：请粘贴完整的 notemeld://model-add 链接或分享 JSON。';
      return;
    }
    applyImport(parsed);
  });

  // —— 入口与行操作 ——
  $('[data-model-add]').addEventListener('click', openDialog);
  $$('[data-model-import]').forEach(button => button.addEventListener('click', openImport));
  $('[data-vendor-grid]').addEventListener('click', event => {
    const button = event.target.closest('[data-vendor-id]');
    if (button && !button.disabled) openCreate(button.dataset.vendorId);
  });
  $('[data-model-groups]').addEventListener('click', event => {
    const share = event.target.closest('[data-model-share]');
    if (share) { openShare(share.dataset.modelShare); return; }
    const edit = event.target.closest('[data-model-edit]');
    if (edit) {
      const item = models.find(m => m.id === edit.dataset.modelEdit);
      if (item) openEdit(item);
      return;
    }
    const del = event.target.closest('[data-model-delete]');
    if (del) {
      const item = models.find(m => m.id === del.dataset.modelDelete);
      if (!item) return;
      if (!window.confirm(`确定删除模型 ${item.modelId} 的配置吗？此操作不可撤销。`)) return;
      const providerId = item.providerId;
      const index = models.findIndex(m => m.id === item.id);
      if (index >= 0) models.splice(index, 1);
      if (providerId && !models.some(m => m.providerId === providerId)) {
        const pIndex = providers.findIndex(p => p.id === providerId);
        if (pIndex >= 0) providers.splice(pIndex, 1);
      }
      render();
      toast('模型已删除（仅当前页面）');
    }
  });

  // —— 弹窗关闭 / 返回 ——
  $$('[data-dialog-close]').forEach(button => button.addEventListener('click', closeDialog));
  $('[data-share-close]').addEventListener('click', () => shareDialog.close());
  $('[data-import-close]').addEventListener('click', () => importDialog.close());
  $('[data-back-vendor]').addEventListener('click', showVendorPanel);
  dialog.addEventListener('click', event => { if (event.target === dialog) closeDialog(); });
  dialog.addEventListener('close', () => form.reset());

  renderVendorGrid();
  render();
})();
