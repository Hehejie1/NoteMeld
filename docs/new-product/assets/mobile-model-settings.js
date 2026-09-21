/*
 * M07 模型设置（移动端）
 * 三端统一「添加模型」语义，共享资产见 assets/model-vendor-registry.js：
 *  - 添加/编辑模型为独立全屏页面（非底部弹窗）
 *  - 服务商通过底部弹窗（固定高度、上下滚动）选择；选中后名称/地址只读
 *  - 厂商预设自动带出协议与 Base URL
 *  - 模型列表从接口拉取，支持多选；测试连接在顶部 toast 反馈
 *  - 跨端分享：notemeld://model-add，载荷永不包含 API Key
 * 原型为纯内存存储；正式版移动端使用端侧 SQLite + Keystore。
 */
(() => {
  const R = window.ModelVendorRegistry;
  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
  const uid = () => (crypto.randomUUID ? crypto.randomUUID() : `m${Date.now()}${Math.random().toString(16).slice(2)}`);

  // —— 内存数据：Provider / Model 两层 ——
  const ark = R.getVendor('volcengine-ark');
  const ds = R.getVendor('deepseek');
  const providers = [
    { id: uid(), vendorId: 'volcengine-ark', displayName: ark.name, protocol: ark.protocol, baseUrl: ark.baseUrl, authType: 'bearer', apiKey: '' },
    { id: uid(), vendorId: 'deepseek', displayName: ds.name, protocol: ds.protocol, baseUrl: ds.baseUrl, authType: 'bearer', apiKey: '' }
  ];
  const models = [
    { id: uid(), providerId: providers[0].id, modelId: 'doubao-seed-1-6', contextWindow: 256000, enabled: true, isDefault: true, testStatus: 'untested' },
    { id: uid(), providerId: providers[0].id, modelId: 'doubao-seed-1-5-thinking', contextWindow: 256000, enabled: true, isDefault: false, testStatus: 'untested' },
    { id: uid(), providerId: providers[0].id, modelId: 'doubao-seed-1-5-vision', contextWindow: 128000, enabled: true, isDefault: false, testStatus: 'untested' },
    { id: uid(), providerId: providers[1].id, modelId: 'deepseek-chat', contextWindow: 64000, enabled: true, isDefault: false, testStatus: 'untested' }
  ];

  // 独立页面表单状态
  let editingProvider = null;   // 编辑态 Provider；null=新建
  let editingModel = null;
  let selectedVendor = null;    // 当前选中 vendor 对象
  let available = [];           // [{id, contextWindow}]
  let checked = new Set();
  let selectedModelId = null;
  let scanStream = null;
  let scanDetector = null;

  const icon = name => { const node = document.createElement('i'); node.setAttribute('data-lucide', name); return node; };
  const refreshIcons = () => window.lucide?.createIcons({ attrs: { 'stroke-width': 2 } });
  const toast = message => {
    const node = $('[data-model-toast]');
    node.textContent = message; node.hidden = false;
    clearTimeout(node._timer);
    node._timer = setTimeout(() => { node.hidden = true; }, 2600);
  };

  // —— 视图切换 ——
  const showView = name => {
    $$('[data-view]').forEach(v => { v.hidden = v.dataset.view !== name; });
  };
  const closeSheets = () => {
    $$('.mobile-sheet').forEach(s => { s.hidden = true; });
    $('[data-sheet-backdrop]').hidden = true;
  };
  const openSheet = selector => {
    closeSheets();
    $('[data-sheet-backdrop]').hidden = false;
    $(selector).hidden = false;
  };

  // 表单元素
  const fDisplayName = $('[data-display-name]');
  const fBaseUrl = $('[data-base-url]');
  const fApiKey = $('[data-api-key]');
  const fVendorLabel = $('[data-vendor-select-label]');
  const fProtoLine = $('[data-protocol-line]');
  const fFetchStatus = $('[data-fetch-status]');
  const fUrlNote = $('[data-url-note]');

  const currentProtocol = () => selectedVendor && selectedVendor.protocol !== 'bedrock' ? selectedVendor.protocol : 'openai-compatible';
  const effectiveKey = () => {
    const typed = fApiKey.value.trim();
    if (typed) return typed;
    return editingProvider?.apiKey || '';
  };

  // —— 列表渲染：按 Provider 分组 ——
  const render = () => {
    const host = $('[data-model-groups]');
    host.replaceChildren();
    if (!models.length) {
      const empty = document.createElement('div');
      empty.className = 'model-empty';
      empty.textContent = '还没有模型。点击右上角 +，选择服务商或粘贴分享信息添加。';
      host.append(empty);
      refreshIcons();
      return;
    }
    providers.forEach(provider => {
      const items = models.filter(m => m.providerId === provider.id);
      if (!items.length) return;
      const vendor = R.getVendor(provider.vendorId);
      const section = document.createElement('section');
      section.className = 'model-source-group';
      const heading = document.createElement('div');
      heading.className = 'model-source-heading';
      const title = document.createElement('h2');
      title.textContent = provider.displayName;
      const count = document.createElement('span');
      count.textContent = `${R.getProtocol(provider.protocol)?.label || provider.protocol} · ${items.length} 个模型`;
      heading.append(title, count);
      section.append(heading);
      items.forEach(item => {
        const card = document.createElement('article');
        card.className = 'model-card';
        const mark = document.createElement('span');
        mark.className = 'model-card-mark';
        mark.append(icon(vendor?.icon || 'box'));
        const body = document.createElement('div');
        body.className = 'model-card-body';
        const name = document.createElement('strong');
        name.textContent = item.modelId + (item.isDefault ? ' · 默认' : '');
        const meta = document.createElement('small');
        meta.textContent = `${R.trimUrl(provider.baseUrl) || '自定义地址'} · 上下文 ${Number(item.contextWindow).toLocaleString()} tokens${provider.apiKey ? '' : ' · 未填密钥'}`;
        body.append(name, meta);
        const action = document.createElement('button');
        action.type = 'button';
        action.dataset.modelActions = item.id;
        action.setAttribute('aria-label', `更多操作：${item.modelId}`);
        action.append(icon('ellipsis'));
        card.append(mark, body, action);
        section.append(card);
      });
      host.append(section);
    });
    refreshIcons();
  };

  // —— 服务商选择列表（固定高度滚动）——
  const renderVendorPick = () => {
    const host = $('[data-vendor-pick-list]');
    host.replaceChildren();
    R.MODEL_VENDORS.forEach(vendor => {
      const button = document.createElement('button');
      button.type = 'button';
      button.dataset.vendorPickId = vendor.id;
      if (vendor.unsupported) {
        button.classList.add('is-unsupported');
        button.disabled = true;
        button.title = vendor.unsupported;
      }
      button.append(icon(vendor.icon));
      const text = document.createElement('span');
      text.className = 'vendor-pick-name';
      text.textContent = vendor.name;
      const sub = document.createElement('small');
      sub.className = 'vendor-pick-url';
      sub.textContent = vendor.unsupported || R.trimUrl(vendor.baseUrl) || (vendor.custom ? '手动填写' : '地址待确认');
      button.append(text, sub);
      button.append(icon('chevron-right'));
      host.append(button);
    });
    refreshIcons();
  };

  // —— 应用服务商：带出协议/地址，名称与 URL 只读 ——
  const applyVendor = vendor => {
    selectedVendor = vendor;
    fVendorLabel.textContent = vendor.name;
    const proto = vendor.protocol === 'bedrock' ? 'openai-compatible' : vendor.protocol;
    fProtoLine.textContent = `协议 · ${R.getProtocol(proto)?.label || proto}`;

    if (vendor.custom) {
      // 自定义允许编辑名称与地址
      fDisplayName.readOnly = false;
      fBaseUrl.readOnly = false;
      fDisplayName.value = editingProvider?.displayName || '';
      fBaseUrl.value = editingProvider?.baseUrl || '';
    } else {
      fDisplayName.readOnly = true;
      fBaseUrl.readOnly = true;
      fDisplayName.value = vendor.name;
      fBaseUrl.value = vendor.baseUrl || '';
    }

    if (vendor.urlNote) { fUrlNote.textContent = vendor.urlNote; fUrlNote.hidden = false; }
    else { fUrlNote.hidden = true; }

    // Anthropic 内置模型直接列出
    if (proto === 'anthropic-messages') {
      available = R.ANTHROPIC_BUILTIN_MODELS.map(m => ({ ...m }));
      available.forEach(m => checked.add(m.id));
      fFetchStatus.textContent = 'Anthropic 无公开列表接口，已列出常用内置模型，可直接多选。';
    }
    renderOptions();
  };

  // —— 模型多选：复选行（不带每模型上下文输入，保持紧凑）——
  const renderOptions = () => {
    const host = $('[data-model-options]');
    host.replaceChildren();
    if (!available.length) {
      const empty = document.createElement('p');
      empty.className = 'model-options-empty';
      empty.textContent = '暂无模型；填写密钥后点击「拉取模型」。';
      host.append(empty);
      return;
    }
    available.forEach(item => {
      const label = document.createElement('label');
      label.className = 'model-option' + (checked.has(item.id) ? ' is-checked' : '');
      const box = document.createElement('input');
      box.type = 'checkbox';
      box.checked = checked.has(item.id);
      box.addEventListener('change', () => {
        if (box.checked) checked.add(item.id); else checked.delete(item.id);
        label.classList.toggle('is-checked', box.checked);
      });
      const span = document.createElement('span');
      span.className = 'model-option-id';
      span.textContent = item.id;
      label.append(box, span);
      host.append(label);
    });
  };

  // —— 打开新建页 ——
  const openCreatePage = () => {
    editingProvider = null;
    editingModel = null;
    selectedVendor = null;
    fApiKey.value = '';
    fVendorLabel.textContent = '请选择服务商';
    fDisplayName.value = '';
    fBaseUrl.value = '';
    available = [];
    checked = new Set();
    $('[data-form-title]').textContent = '添加模型';
    fFetchStatus.textContent = '先选择服务商，再填写密钥并拉取模型。';
    fUrlNote.hidden = true;
    renderOptions();
    showView('add');
  };

  // —— 打开编辑页 ——
  const openEditPage = modelItem => {
    const provider = providers.find(p => p.id === modelItem.providerId);
    if (!provider) return;
    editingProvider = provider;
    editingModel = modelItem;
    fApiKey.value = '';
    fApiKey.placeholder = provider.apiKey ? '已设置密钥；留空保留' : '填写 API Key';
    available = [{ id: modelItem.modelId, contextWindow: modelItem.contextWindow }];
    checked = new Set([modelItem.modelId]);
    $('[data-form-title]').textContent = '编辑模型';
    fFetchStatus.textContent = '只显示当前模型；重新拉取可加入同服务商其他模型。';
    showView('add');
    const vendor = R.getVendor(provider.vendorId) || R.getVendor('custom');
    applyVendor(vendor);
  };

  // —— 拉取模型 ——
  $('[data-fetch-models]').addEventListener('click', async event => {
    const button = event.currentTarget;
    if (!selectedVendor) { toast('请先选择服务商'); return; }
    const protocol = currentProtocol();
    const baseUrl = R.trimUrl(fBaseUrl.value);

    if (protocol === 'anthropic-messages') {
      const map = new Map(available.map(m => [m.id, m]));
      R.ANTHROPIC_BUILTIN_MODELS.forEach(m => { if (!map.has(m.id)) map.set(m.id, { ...m }); checked.add(m.id); });
      available = [...map.values()].sort((a, b) => a.id.localeCompare(b.id));
      renderOptions();
      fFetchStatus.textContent = '已列出 Anthropic 常用内置模型，可直接多选。';
      return;
    }
    if (!R.isValidHttpUrl(baseUrl)) { fFetchStatus.textContent = '请先填写正确的 Base URL。'; return; }
    if (!R.isLocalUrl(baseUrl) && !/^https:\/\//i.test(baseUrl)) {
      fFetchStatus.textContent = '非本机地址必须使用 HTTPS。'; return;
    }
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 12000);
    button.disabled = true;
    fFetchStatus.textContent = '正在拉取模型列表…';
    try {
      const list = await R.fetchModelList({ protocol, baseUrl, apiKey: effectiveKey(), signal: controller.signal });
      const map = new Map(available.map(m => [m.id, m]));
      list.forEach(m => { if (!map.has(m.id)) map.set(m.id, m); checked.add(m.id); });
      available = [...map.values()].sort((a, b) => a.id.localeCompare(b.id));
      renderOptions();
      fFetchStatus.textContent = `已获取 ${list.length} 个模型，可多选。`;
    } catch (error) {
      fFetchStatus.textContent = error.message === 'empty_list' ? '接口返回空列表。'
        : error.name === 'AbortError' ? '拉取超时，请检查网络与地址。'
        : '拉取失败；请检查 URL、密钥、网络及 CORS 限制。';
    } finally {
      clearTimeout(timer);
      button.disabled = false;
    }
  });

  // —— 测试连接：顶部 toast 反馈 ——
  $('[data-test-model]').addEventListener('click', async event => {
    const button = event.currentTarget;
    if (!selectedVendor) { toast('请先选择服务商'); return; }
    const protocol = currentProtocol();
    const baseUrl = R.trimUrl(fBaseUrl.value);
    const testModel = [...checked][0];

    if (!R.isValidHttpUrl(baseUrl) || (!R.isLocalUrl(baseUrl) && !/^https:\/\//i.test(baseUrl))) {
      toast('请先填写有效的接口地址'); return;
    }
    if (protocol !== 'ollama' && !testModel) { toast('请先拉取并勾选至少一个模型'); return; }

    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 10000);
    button.disabled = true;
    try {
      const result = await R.testConnection({ protocol, baseUrl, apiKey: effectiveKey(), model: testModel, signal: controller.signal });
      toast(result.message || '连接成功');
    } catch (error) {
      toast(error.name === 'AbortError' ? '测试超时，请检查网络和地址' : '连接失败，请检查地址、密钥与模型');
    } finally {
      clearTimeout(timer);
      button.disabled = false;
    }
  });

  // —— 密钥显隐 ——
  $('[data-key-toggle]').addEventListener('click', () => {
    const showing = fApiKey.type === 'text';
    fApiKey.type = showing ? 'password' : 'text';
    $('[data-key-toggle-text]').textContent = showing ? '显示' : '隐藏';
    const old = $('[data-key-toggle]').querySelector('svg, i');
    const node = icon(showing ? 'eye' : 'eye-off');
    if (old) old.replaceWith(node);
    refreshIcons();
  });

  // —— 全选 ——
  $('[data-check-all]').addEventListener('click', event => {
    const allChecked = available.every(m => checked.has(m.id));
    if (allChecked) { checked = new Set(); event.currentTarget.textContent = '全选'; }
    else { available.forEach(m => checked.add(m.id)); event.currentTarget.textContent = '清除'; }
    renderOptions();
  });

  // —— 保存 ——
  const saveCurrent = async () => {
    const displayName = fDisplayName.value.trim();
    const protocol = currentProtocol();
    const baseUrl = R.trimUrl(fBaseUrl.value);
    const typedKey = fApiKey.value.trim();
    const selectedModels = available.filter(m => checked.has(m.id));

    let vendorId = selectedVendor && !selectedVendor.custom ? selectedVendor.id : 'custom';
    const errors = R.validateModelConfig({
      displayName, vendorId, protocol, baseUrl, apiKey: typedKey,
      hasStoredKey: !!(editingProvider?.apiKey),
      models: selectedModels.map(m => ({ id: m.id, contextWindow: m.contextWindow || R.DEFAULT_CONTEXT }))
    });
    if (Object.keys(errors).length) { toast(Object.values(errors)[0]); return; }

    let provider = editingProvider;
    if (!provider) {
      provider = { id: uid(), vendorId, displayName, protocol, baseUrl, authType: protocol === 'ollama' ? 'none' : 'bearer', apiKey: typedKey };
      providers.push(provider);
    } else {
      provider.displayName = displayName;
      provider.protocol = protocol;
      provider.baseUrl = baseUrl;
      provider.vendorId = vendorId;
      if (typedKey) provider.apiKey = typedKey;
      if (protocol === 'ollama') provider.apiKey = '';
    }

    const firstId = selectedModels[0]?.id;
    if (editingModel) {
      editingModel.providerId = provider.id;
      editingModel.modelId = firstId;
      selectedModels.slice(1).forEach(m => {
        if (!models.some(x => x.providerId === provider.id && x.modelId === m.id)) {
          models.push({ id: uid(), providerId: provider.id, modelId: m.id, contextWindow: m.contextWindow || R.DEFAULT_CONTEXT, enabled: true, isDefault: false, testStatus: 'untested' });
        }
      });
    } else {
      selectedModels.forEach((m, i) => {
        models.push({ id: uid(), providerId: provider.id, modelId: m.id, contextWindow: m.contextWindow || R.DEFAULT_CONTEXT, enabled: true, isDefault: i === 0 && !models.some(x => x.providerId === provider.id), testStatus: 'untested' });
      });
    }

    // 保存后测试，回写状态
    let statusOk = false;
    if (firstId) {
      statusOk = await R.testConnection({ protocol, baseUrl, apiKey: provider.apiKey, model: firstId }).then(() => true).catch(() => false);
      const target = models.find(m => m.providerId === provider.id && m.modelId === firstId);
      if (target) target.testStatus = statusOk ? 'ok' : 'failed';
    }

    closeSheets();
    showView('list');
    render();
    toast(firstId ? (statusOk ? '已保存，连接测试通过' : '已保存；连接测试未通过') : '已保存');
  };
  $('[data-add-save]').addEventListener('click', saveCurrent);
  $('[data-add-save-bottom]').addEventListener('click', saveCurrent);

  $('[data-add-back]').addEventListener('click', () => { closeSheets(); showView('list'); });

  // —— 服务商弹窗：打开 + 选择 ——
  $('[data-vendor-select]').addEventListener('click', () => {
    renderVendorPick();
    openSheet('[data-vendor-pick]');
  });
  $('[data-vendor-pick-list]').addEventListener('click', event => {
    const button = event.target.closest('[data-vendor-pick-id]');
    if (!button || button.disabled) return;
    const vendor = R.getVendor(button.dataset.vendorPickId);
    if (!vendor) return;
    closeSheets();
    applyVendor(vendor);
  });

  // —— 添加入口：直接进入独立页面 ——
  $('[data-provider-open]').addEventListener('click', openCreatePage);

  // —— 模型操作菜单 ——
  $('[data-model-groups]').addEventListener('click', event => {
    const button = event.target.closest('[data-model-actions]');
    if (!button) return;
    selectedModelId = button.dataset.modelActions;
    const item = models.find(m => m.id === selectedModelId);
    const provider = item && providers.find(p => p.id === item.providerId);
    $('[data-action-vendor]').textContent = provider?.displayName || '';
    $('[data-action-title]').textContent = item.modelId;
    openSheet('[data-actions-sheet]');
  });
  $('[data-model-edit]').addEventListener('click', () => {
    const item = models.find(m => m.id === selectedModelId);
    if (item) openEditPage(item);
  });
  $('[data-model-delete]').addEventListener('click', () => {
    const item = models.find(m => m.id === selectedModelId);
    if (!item) return;
    closeSheets();
    $('[data-delete-name]').textContent = item.modelId;
    $('[data-delete-modal]').hidden = false;
  });
  $('[data-delete-cancel]').addEventListener('click', () => {
    $('[data-delete-modal]').hidden = true; selectedModelId = null;
  });
  $('[data-delete-confirm]').addEventListener('click', () => {
    const index = models.findIndex(m => m.id === selectedModelId);
    const providerId = models[index]?.providerId;
    if (index >= 0) models.splice(index, 1);
    if (providerId && !models.some(m => m.providerId === providerId)) {
      const pIndex = providers.findIndex(p => p.id === providerId);
      if (pIndex >= 0) providers.splice(pIndex, 1);
    }
    $('[data-delete-modal]').hidden = true;
    selectedModelId = null;
    render();
    toast('模型已删除（仅当前页面）');
  });

  // —— 分享 ——
  $('[data-model-share]').addEventListener('click', () => {
    const item = models.find(m => m.id === selectedModelId);
    const provider = item && providers.find(p => p.id === item.providerId);
    if (!item || !provider) return;
    const payload = R.buildSharePayload({
      vendorId: provider.vendorId, displayName: provider.displayName, protocol: provider.protocol, baseUrl: provider.baseUrl,
      models: [{ id: item.modelId, contextWindow: item.contextWindow }]
    });
    $('[data-share-uri]').value = R.encodeShare(payload);
    openSheet('[data-share-sheet]');
  });
  $('[data-share-copy]').addEventListener('click', async event => {
    const text = $('[data-share-uri]').value;
    try { await navigator.clipboard.writeText(text); toast('分享信息已复制（不含 API 密钥）'); }
    catch { $('[data-share-uri]').select(); document.execCommand('copy'); toast('分享信息已复制（不含 API 密钥）'); }
  });

  // —— 粘贴导入 ——
  $('[data-model-import]')?.addEventListener('click', () => openSheet('[data-import-sheet]'));
  $('[data-import-parse]').addEventListener('click', () => {
    const parsed = R.decodeShare($('[data-import-text]').value);
    if (!parsed) { $('[data-import-status]').textContent = '无法识别：请粘贴完整链接或 JSON。'; return; }
    closeSheets();
    openCreatePage();
    const vendor = R.getVendor(parsed.vendorId) || R.getVendor('custom');
    selectedVendor = vendor;
    fVendorLabel.textContent = vendor.name;
    fDisplayName.value = parsed.displayName;
    fBaseUrl.value = parsed.baseUrl;
    available = parsed.models.map(m => ({ id: m.id, contextWindow: m.contextWindow }));
    checked = new Set(parsed.models.map(m => m.id));
    fProtoLine.textContent = `协议 · ${R.getProtocol(parsed.protocol)?.label || parsed.protocol}`;
    fFetchStatus.textContent = `已识别 ${parsed.models.length} 个模型；请补填密钥。`;
    renderOptions();
    toast('已解析分享信息，请补填密钥');
  });

  // —— 扫一扫 ——
  const stopScan = () => {
    scanStream?.getTracks().forEach(t => t.stop());
    scanStream = null; scanDetector = null;
    const video = $('[data-scan-video]');
    if (video) { video.pause(); video.srcObject = null; video.hidden = true; }
  };
  $('[data-scan-open]').addEventListener('click', () => openSheet('[data-scan-sheet]'));
  $('[data-scan-start]').addEventListener('click', async () => {
    const status = $('[data-scan-status]');
    if (!('BarcodeDetector' in window) || !navigator.mediaDevices?.getUserMedia) {
      status.textContent = '当前浏览器不支持扫描；可改用粘贴导入。'; return;
    }
    try {
      scanDetector = new BarcodeDetector({ formats: ['qr_code'] });
      scanStream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: 'environment' }, audio: false });
      const video = $('[data-scan-video]');
      video.srcObject = scanStream; video.hidden = false; await video.play();
      const tick = async () => {
        if (!scanStream || $('[data-scan-sheet]').hidden) return;
        try {
          const codes = await scanDetector.detect(video);
          if (codes.length) {
            const code = codes[0].rawValue;
            if (/^notemeld:\/\/pair\?code=[A-Za-z0-9_-]+$/.test(code)) {
              stopScan(); status.textContent = '已识别配对码；静态原型未执行凭据交换。'; return;
            }
            const parsed = R.decodeShare(code);
            if (parsed) { stopScan(); applyImportFromScan(parsed); return; }
            status.textContent = '不是受支持的 NoteMeld 二维码。';
          }
        } catch {}
        requestAnimationFrame(tick);
      };
      tick();
    } catch { stopScan(); $('[data-scan-status]').textContent = '无法使用相机，请改用粘贴导入。'; }
  });
  const applyImportFromScan = parsed => {
    openCreatePage();
    const vendor = R.getVendor(parsed.vendorId) || R.getVendor('custom');
    selectedVendor = vendor;
    fVendorLabel.textContent = vendor.name;
    fDisplayName.value = parsed.displayName;
    fBaseUrl.value = parsed.baseUrl;
    available = parsed.models.map(m => ({ id: m.id, contextWindow: m.contextWindow }));
    checked = new Set(parsed.models.map(m => m.id));
    fProtoLine.textContent = `协议 · ${R.getProtocol(parsed.protocol)?.label || parsed.protocol}`;
    renderOptions();
    toast('已扫码导入，请补填密钥');
  };

  $$('[data-sheet-close]').forEach(button => button.addEventListener('click', closeSheets));
  $('[data-sheet-backdrop]').addEventListener('click', closeSheets);
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape') { closeSheets(); $('[data-delete-modal]').hidden = true; }
  });

  render();
})();
