/*
 * C06 模型管理（云端）
 * 三端统一「添加模型」语义，共享资产见 assets/model-vendor-registry.js：
 *  - 厂商预设自动带出协议与 Base URL；也可手动自定义
 *  - 模型列表默认从 models/list 接口获取，支持多选；每个模型独立上下文窗口
 *  - 编辑回显、密钥显示/隐藏（云端加密保存、不回显明文，留空保留不修改）、统一校验、保存后测试闭环
 *  - 跨端分享：notemeld://model-add（二维码占位 + 复制），载荷永不包含 API Key；支持粘贴导入
 *  - 管理员闸门：仅管理员可写，非管理员只读
 * 原型通过 /v1/models 信封接口访问 Cloud 数据库；正式版密钥由 Cloud KMS 加密保存。
 */
(() => {
  if (document.body.dataset.page !== 'C06') return;
  const R = window.ModelVendorRegistry;
  if (!R) return;
  const token = sessionStorage.getItem('notemeld-cloud-token');
  if (!token) return;

  const $ = (sel, root = document) => root.querySelector(sel);

  const api = async (path, options = {}) => {
    const response = await fetch(path, {
      ...options,
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}`, ...(options.headers || {}) }
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || payload.msg || '请求失败');
    return payload.data;
  };

  const escape = value => String(value ?? '').replace(/[&<>"']/g, char => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  }[char]));

  const isAdmin = () => {
    if (new URLSearchParams(location.search).get('role') === 'admin') return true;
    try {
      const user = JSON.parse(sessionStorage.getItem('notemeld-cloud-user') || 'null');
      return user?.role === 'admin';
    } catch { return false; }
  };

  // —— 样式（scoped，复用 cloud 主题变量，明暗自适应）——
  const style = document.createElement('style');
  style.textContent = `
.cm-modal .create-dialog{max-width:780px}
.cm-toast{position:fixed;left:50%;bottom:28px;transform:translate(-50%,12px);opacity:0;transition:opacity .2s,transform .2s;z-index:9999;margin:0;padding:10px 16px;border-radius:10px;background:var(--cloud-text);color:var(--cloud-bg);font-size:13px;box-shadow:var(--cloud-shadow);max-width:80vw}
.cm-toast.show{opacity:1;transform:translate(-50%,0)}
.cm-loading{color:var(--cloud-muted);padding:18px 0}
.cm-toolbar{display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin-bottom:14px}
.cm-readonly-note{color:var(--cloud-warn);font-size:12.5px}
.cm-group{border:1px solid var(--cloud-border);border-radius:14px;margin-bottom:12px;overflow:hidden;background:var(--cloud-surface)}
.cm-group-head{display:flex;justify-content:space-between;gap:12px;align-items:center;padding:12px 16px;background:var(--cloud-surface-2);flex-wrap:wrap}
.cm-group-head small{display:block;color:var(--cloud-muted);margin-top:2px}
.cm-group .c06-option-list{border:none;border-radius:0}
.cm-model-meta{color:var(--cloud-muted)}
.cm-default-tag{display:inline-block;margin-left:6px;padding:1px 8px;border-radius:999px;font-size:11px;background:var(--cloud-accent-soft);color:var(--cloud-accent)}
.cm-vendor-grid{display:grid;grid-template-columns:repeat(2,1fr);gap:10px}
.cm-vendor{display:flex;align-items:center;gap:10px;padding:13px 14px;border:1px solid var(--cloud-border);border-radius:12px;background:var(--cloud-surface);color:var(--cloud-text);cursor:pointer;text-align:left;font-size:14px}
.cm-vendor:hover{border-color:var(--cloud-accent)}
.cm-vendor.wide{grid-column:1/-1}
.cm-vendor:disabled{opacity:.45;cursor:not-allowed}
.cm-vendor .cm-vendor-icon{display:inline-flex;width:30px;height:30px;border-radius:8px;background:var(--cloud-accent-soft);color:var(--cloud-accent);align-items:center;justify-content:center;flex:none}
.cm-vendor .cm-vendor-name{flex:1}
.cm-key-input{display:flex;gap:8px}
.cm-key-input input{flex:1}
.cm-model-options{display:flex;flex-direction:column;gap:8px;margin-top:10px;max-height:260px;overflow:auto;padding-right:4px}
.cm-model-option{display:flex;align-items:center;gap:10px;padding:9px 12px;border:1px solid var(--cloud-border);border-radius:10px;background:var(--cloud-surface)}
.cm-model-option .cm-ctx{margin-left:auto;display:flex;align-items:center;gap:6px;color:var(--cloud-muted);font-size:12.5px}
.cm-model-option .cm-ctx input{width:120px}
.cm-fetch-row{display:flex;gap:10px;flex-wrap:wrap;align-items:center}
.cm-manual{display:flex;gap:8px;flex:1;min-width:240px}
.cm-manual input{flex:1}
.cm-note{font-size:12.5px;color:var(--cloud-muted);margin:6px 0}
.cm-qr{width:152px;height:152px;border:1px dashed var(--cloud-border);border-radius:12px;display:flex;align-items:center;justify-content:center;color:var(--cloud-muted);font-size:12px;text-align:center;margin:0 auto 12px;background:var(--cloud-surface-2)}
.cm-share-row{display:flex;gap:8px}
.cm-share-row input{flex:1}
.cm-fieldset{border:none;padding:0;margin:14px 0 0}
.cm-fieldset legend{font-weight:600;margin-bottom:8px;padding:0}
.cm-readout{display:flex;justify-content:space-between;align-items:center;gap:10px;padding:10px 14px;border-radius:10px;background:var(--cloud-surface-2);margin-bottom:12px}
.cm-readout small{display:block;color:var(--cloud-muted);margin-top:2px}
button.cm-danger{color:var(--cloud-danger)}
[hidden]{display:none!important}`;
  document.head.append(style);

  // —— Toast ——
  const toast = text => {
    const node = document.createElement('p');
    node.className = 'cm-toast';
    node.textContent = text;
    document.body.append(node);
    requestAnimationFrame(() => node.classList.add('show'));
    setTimeout(() => node.remove(), 3200);
  };

  const modal = (title, description, contentHTML) => {
    const node = document.createElement('div');
    node.className = 'modal-backdrop cm-modal';
    node.innerHTML = `<section class="create-dialog" role="dialog" aria-modal="true"><header><div><span class="section-kicker">Cloud settings</span><h2>${escape(title)}</h2><p>${escape(description)}</p></div><button class="icon-button" type="button" data-cm-close aria-label="关闭">×</button></header><div class="c06-dialog-body" data-cm-body>${contentHTML}</div></section>`;
    document.body.append(node);
    const close = () => node.remove();
    node.querySelector('[data-cm-close]').addEventListener('click', close);
    node.addEventListener('click', event => { if (event.target === node) close(); });
    node._cmClose = close;
    return node;
  };

  const icons = () => window.lucide?.createIcons?.({ attrs: { 'stroke-width': 2 } });

  // —— 扁平 /v1/models 记录按 provider+base_url 分组 ——
  const groupKeyOf = item => `${item.provider || 'openai-compatible'}|${R.trimUrl(item.base_url || '')}`;
  const vendorOfGroup = (protocol, baseUrl) =>
    R.MODEL_VENDORS.find(v => !v.custom && v.protocol === protocol && v.baseUrl && R.trimUrl(v.baseUrl) === R.trimUrl(baseUrl)) || null;

  function buildGroups(raw) {
    const map = new Map();
    raw.forEach(item => {
      const key = groupKeyOf(item);
      if (!map.has(key)) map.set(key, []);
      map.get(key).push(item);
    });
    return [...map.entries()].map(([key, items]) => {
      const [protocol, baseUrl] = key.split('|');
      const vendor = vendorOfGroup(protocol, baseUrl);
      return {
        key, protocol, baseUrl, vendor,
        displayName: vendor?.name || items[0]?.name || '自定义配置',
        hasKey: items.some(i => i.has_api_key),
        items
      };
    });
  }

  // —— 面板默认模型摘要 ——
  const refreshDefaultSummary = () => api('/v1/models').then(raw => {
    const def = raw.find(i => i.is_default) || raw.find(i => i.enabled) || null;
    const slot = document.querySelector('[data-default-model]');
    if (slot) slot.textContent = def ? `${def.model} · ${R.getProtocol(def.provider)?.label || def.provider}` : '尚未配置默认模型';
  }).catch(() => {});
  refreshDefaultSummary();

  // —— 模型管理模态 ——
  const openManager = () => {
    const admin = isAdmin();
    const node = modal(
      '模型管理',
      admin
        ? '模型配置属于当前账号，保存在 Cloud 数据库；API Key 加密保存，不回显明文。'
        : '只读模式：仅管理员可新增、编辑或删除云端模型配置；你仍可分享模型到其他端。',
      '<p class="cm-loading">正在读取模型配置…</p>'
    );
    const state = { node, admin, raw: [], editing: null, mode: 'root', vendorId: null, available: [], checked: new Set() };
    node.addEventListener('click', event => delegateClick(state, event));
    refreshRoot(state);
    return state;
  };

  const refreshRoot = async state => {
    const body = state.node.querySelector('[data-cm-body]');
    body.innerHTML = '<p class="cm-loading">正在读取模型配置…</p>';
    try {
      state.raw = await api('/v1/models');
      renderRoot(state);
    } catch (error) {
      body.innerHTML = `<p class="empty-cloud-state">模型加载失败：${escape(error.message)}</p><div class="dialog-actions"><span></span><button class="secondary-button" type="button" data-cm-retry>重试</button></div>`;
    }
  };

  const renderRoot = state => {
    const groups = buildGroups(state.raw);
    const writeActions = (item, compact) => `
      <button class="secondary-button" type="button" data-cm-share="${escape(item.id)}">分享</button>
      ${state.admin ? `
      <button class="secondary-button" type="button" data-cm-edit="${escape(item.id)}">编辑</button>
      <button class="secondary-button" type="button" data-cm-toggle="${escape(item.id)}">${item.enabled ? '停用' : '启用'}</button>
      ${item.is_default ? '' : `<button class="secondary-button" type="button" data-cm-default="${escape(item.id)}">设为默认</button>`}
      <button class="secondary-button cm-danger" type="button" data-cm-delete="${escape(item.id)}">删除</button>`
        : '<button class="secondary-button" type="button" disabled title="仅管理员可修改">只读</button>'}`.replace(/\s+/g, ' ').trim();

    const groupsHTML = groups.length ? groups.map(group => `
      <div class="cm-group">
        <div class="cm-group-head">
          <span><strong>${escape(group.displayName)}</strong><small>${escape(R.getProtocol(group.protocol)?.label || group.protocol)} · ${escape(group.baseUrl || '自定义地址')}${group.hasKey ? ' · 已配置凭证' : ' · 未填密钥'}</small></span>
        </div>
        <div class="c06-option-list">
          ${group.items.map(item => `
            <article class="c06-backup-row">
              <span><strong>${escape(item.model)}</strong><small class="cm-model-meta">${item.enabled ? '已启用' : '已停用'}${item.is_default ? '<span class="cm-default-tag">默认</span>' : ''}</small></span>
              <span>${writeActions(item)}</span>
            </article>`).join('')}
        </div>
      </div>`).join('')
      : '<p class="empty-cloud-state">尚未配置模型。选择厂商或粘贴其他端分享的信息即可添加。</p>';

    state.node.querySelector('[data-cm-body]').innerHTML = `
      <div class="cm-toolbar">
        ${state.admin
          ? '<button class="primary-button" type="button" data-cm-add>+ 添加模型</button><button class="secondary-button" type="button" data-cm-import>粘贴分享信息导入</button>'
          : ''}
        ${state.admin ? '' : '<span class="cm-readonly-note">当前为只读模式，写操作请联系管理员。</span>'}
      </div>
      <div data-cm-groups>${groupsHTML}</div>`;
    state.mode = 'root';
    icons();
  };

  // —— 厂商选择 ——
  const renderVendors = state => {
    const cards = R.MODEL_VENDORS.map(vendor => {
      const disabled = vendor.unsupported ? 'disabled' : '';
      const title = vendor.unsupported ? `title="${escape(vendor.unsupported)}"` : '';
      return `<button type="button" class="cm-vendor ${vendor.custom ? 'wide' : ''}" data-cm-vendor="${vendor.id}" ${disabled} ${title}>
        <span class="cm-vendor-icon"><i data-lucide="${vendor.icon}"></i></span>
        <span class="cm-vendor-name">${escape(vendor.name)}${vendor.urlNote ? `<small class="cm-note" style="margin:2px 0 0">${escape(vendor.urlNote)}</small>` : ''}${vendor.unsupported ? `<small class="cm-note" style="margin:2px 0 0">${escape(vendor.unsupported)}</small>` : ''}</span>
        ${vendor.custom ? '' : '<i data-lucide="chevron-right"></i>'}
      </button>`;
    }).join('');
    state.node.querySelector('[data-cm-body]').innerHTML = `
      <p class="cm-note" style="margin-top:0">选择常用厂商可自动带出协议与 Base URL；选择「自定义」手动填写。</p>
      <div class="cm-vendor-grid">${cards}</div>
      <div class="dialog-actions"><button class="secondary-button" type="button" data-cm-back-root>返回</button><span></span></div>`;
    state.mode = 'vendors';
    icons();
  };

  // —— 表单 ——
  const formViewHTML = state => {
    const f = state.form;
    const protoOptions = R.PROTOCOLS.map(p =>
      `<option value="${p.id}" ${f.protocol === p.id ? 'selected' : ''}>${escape(p.label)}</option>`).join('');
    return `
      <form data-cm-form>
        <div class="cm-readout"><span><strong data-cm-readout-title>${escape(f.title)}</strong><small>${escape(f.eyebrow)}</small></span>
          <button class="secondary-button" type="button" data-cm-back-vendors>重选厂商</button></div>
        <div class="form-grid">
          <label>配置名称<input name="displayName" required placeholder="例如：工作 OpenAI" value="${escape(f.displayName)}"></label>
          <label>协议类型<select name="protocol">${protoOptions}</select></label>
        </div>
        <div class="form-grid">
          <label>Base URL<input name="baseUrl" type="url" required placeholder="https://api.example.com/v1" value="${escape(f.baseUrl)}"></label>
          <label data-cm-key-field>API Key <small class="optional-label">加密保存，不回显明文</small>
            <span class="cm-key-input"><input name="apiKey" type="password" placeholder="${escape(f.keyPlaceholder)}" autocomplete="off">
            <button class="secondary-button" type="button" data-cm-key-toggle>显示</button></span>
          </label>
        </div>
        <p class="cm-note" data-cm-url-note ${f.urlNote ? '' : 'hidden'}>${escape(f.urlNote || '')}</p>
        <fieldset class="cm-fieldset">
          <legend>模型（可多选，逐个确认上下文窗口）</legend>
          <div class="cm-fetch-row">
            <button class="secondary-button" type="button" data-cm-fetch>从接口获取模型</button>
            <button class="secondary-button" type="button" data-cm-test>测试连接</button>
            <span class="cm-manual"><input name="manualModel" placeholder="手动添加模型 ID"><button class="secondary-button" type="button" data-cm-manual-add>添加</button></span>
          </div>
          <p class="cm-note" data-cm-fetch-status>${escape(f.fetchStatus)}</p>
          <div class="cm-model-options" data-cm-options></div>
        </fieldset>
        <label class="switch-row"><span>将第一个模型设为默认</span><input type="checkbox" name="isDefault" ${f.isDefault ? 'checked' : ''}></label>
        <p class="form-message" data-cm-error role="alert" hidden></p>
        <div class="dialog-actions">
          <button class="secondary-button" type="button" data-cm-back-root>取消</button>
          <button class="primary-button" type="submit">${state.editing ? '保存修改' : '保存模型'}</button>
        </div>
      </form>`;
  };

  const renderOptions = state => {
    const host = state.node.querySelector('[data-cm-options]');
    host.replaceChildren();
    state.available.forEach(item => {
      const row = document.createElement('label');
      row.className = 'cm-model-option';
      const box = document.createElement('input');
      box.type = 'checkbox';
      box.checked = state.checked.has(item.id);
      box.addEventListener('change', () => {
        if (box.checked) state.checked.add(item.id); else state.checked.delete(item.id);
        ctxWrap.hidden = !box.checked;
      });
      const name = document.createElement('span');
      name.textContent = item.id;
      const ctxWrap = document.createElement('span');
      ctxWrap.className = 'cm-ctx';
      ctxWrap.hidden = !box.checked;
      const em = document.createElement('em');
      em.textContent = '上下文 tokens';
      const ctxInput = document.createElement('input');
      ctxInput.type = 'number';
      ctxInput.min = String(R.CONTEXT_MIN);
      ctxInput.max = String(R.CONTEXT_MAX);
      ctxInput.value = String(item.contextWindow || R.DEFAULT_CONTEXT);
      ctxInput.addEventListener('input', () => { item.contextWindow = Number(ctxInput.value); });
      ctxWrap.append(em, ctxInput);
      row.append(box, name, ctxWrap);
      host.append(row);
    });
  };

  const syncProtocolUI = state => {
    const proto = state.node.querySelector('[name="protocol"]').value;
    const keyField = state.node.querySelector('[data-cm-key-field]');
    keyField.hidden = proto === 'ollama';
    if (proto === 'ollama') {
      const keyInput = state.node.querySelector('[name="apiKey"]');
      keyInput.value = '';
      keyInput.type = 'password';
      state.node.querySelector('[data-cm-key-toggle]').textContent = '显示';
    }
  };

  const mountForm = state => {
    state.node.querySelector('[data-cm-body]').innerHTML = formViewHTML(state);
    state.mode = 'form';
    renderOptions(state);
    syncProtocolUI(state);
    const form = state.node.querySelector('[data-cm-form]');
    state.node.querySelector('[name="protocol"]').addEventListener('change', () => syncProtocolUI(state));
    form.addEventListener('submit', event => { event.preventDefault(); submitForm(state, form); });
  };

  const openCreate = (state, vendorId) => {
    const vendor = R.getVendor(vendorId);
    if (!vendor || vendor.unsupported) { toast(vendor?.unsupported || '暂不支持该厂商'); return; }
    state.editing = null;
    state.vendorId = vendor.custom ? null : vendor.id;
    state.available = [];
    state.checked = new Set();
    if (vendor.protocol === 'anthropic-messages') {
      state.available = R.ANTHROPIC_BUILTIN_MODELS.map(m => ({ ...m }));
      state.available.forEach(m => state.checked.add(m.id));
    }
    state.form = {
      title: '添加模型', eyebrow: vendor.custom ? '手动自定义' : vendor.name,
      displayName: vendor.custom ? '' : vendor.name,
      protocol: vendor.protocol === 'bedrock' ? 'openai-compatible' : vendor.protocol,
      baseUrl: vendor.baseUrl || '',
      keyPlaceholder: '填写 API Key',
      urlNote: vendor.urlNote || (vendor.protocol === 'anthropic-messages'
        ? 'Anthropic 无公开列表接口，已列出常用内置模型，也可手动添加。' : ''),
      fetchStatus: vendor.protocol === 'anthropic-messages'
        ? '已列出常用内置模型，可直接多选或手动添加。'
        : (vendor.urlNote || '填写 Base URL 与密钥后，从接口获取模型，或手动添加。'),
      isDefault: false
    };
    mountForm(state);
  };

  const openEdit = (state, item) => {
    const vendor = vendorOfGroup(item.provider, item.base_url);
    state.editing = item;
    state.vendorId = vendor?.id || null;
    state.available = [{ id: item.model, contextWindow: R.DEFAULT_CONTEXT }];
    state.checked = new Set([item.model]);
    state.form = {
      title: '编辑模型', eyebrow: vendor?.name || item.name || '自定义配置',
      displayName: vendor?.name || item.name || '自定义配置',
      protocol: item.provider || 'openai-compatible',
      baseUrl: item.base_url || '',
      keyPlaceholder: item.has_api_key ? '已设置密钥；留空保留不修改' : '填写 API Key',
      urlNote: '',
      fetchStatus: '只显示当前模型；重新获取列表可加入同服务商的其他模型。',
      isDefault: !!item.is_default
    };
    mountForm(state);
  };

  const applyImport = (state, parsed) => {
    const vendor = R.getVendor(parsed.vendorId) || R.getVendor('custom');
    state.editing = null;
    state.vendorId = vendor.custom ? null : vendor.id;
    state.available = parsed.models.map(m => ({ id: m.id, contextWindow: m.contextWindow }));
    state.checked = new Set(parsed.models.map(m => m.id));
    state.form = {
      title: '导入模型', eyebrow: '跨端导入',
      displayName: parsed.displayName || vendor.name,
      protocol: parsed.protocol,
      baseUrl: parsed.baseUrl || vendor.baseUrl || '',
      keyPlaceholder: '导入内容不含密钥，请填写 API Key',
      urlNote: '',
      fetchStatus: `已识别 ${parsed.models.length} 个模型；请补填 API 密钥后保存。`,
      isDefault: false
    };
    mountForm(state);
  };

  // —— 表单内操作 ——
  const formValues = state => {
    const get = name => state.node.querySelector(`[name="${name}"]`);
    return {
      displayName: get('displayName').value.trim(),
      protocol: get('protocol').value,
      baseUrl: R.trimUrl(get('baseUrl').value),
      apiKey: get('apiKey').value.trim(),
      isDefault: get('isDefault').checked
    };
  };

  const fetchModels = async state => {
    const v = formValues(state);
    const status = state.node.querySelector('[data-cm-fetch-status]');
    const button = state.node.querySelector('[data-cm-fetch]');
    if (v.protocol === 'anthropic-messages') {
      const map = new Map(state.available.map(m => [m.id, m]));
      R.ANTHROPIC_BUILTIN_MODELS.forEach(m => { if (!map.has(m.id)) map.set(m.id, { ...m }); state.checked.add(m.id); });
      state.available = [...map.values()].sort((a, b) => a.id.localeCompare(b.id));
      renderOptions(state);
      status.textContent = '已列出 Anthropic 常用内置模型，可直接多选或手动添加。';
      return;
    }
    if (!R.isValidHttpUrl(v.baseUrl)) { status.textContent = '请先填写正确的 Base URL。'; return; }
    if (!R.isLocalUrl(v.baseUrl) && !/^https:\/\//i.test(v.baseUrl)) {
      status.textContent = '非本机地址必须使用 HTTPS（localhost 可用 HTTP）。'; return;
    }
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 12000);
    button.disabled = true;
    status.textContent = '正在获取模型列表…';
    try {
      const list = await R.fetchModelList({ protocol: v.protocol, baseUrl: v.baseUrl, apiKey: v.apiKey, signal: controller.signal });
      const map = new Map(state.available.map(m => [m.id, m]));
      list.forEach(m => { if (!map.has(m.id)) map.set(m.id, m); });
      state.available = [...map.values()].sort((a, b) => a.id.localeCompare(b.id));
      list.forEach(m => state.checked.add(m.id));
      renderOptions(state);
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
  };

  const manualAdd = state => {
    const input = state.node.querySelector('[name="manualModel"]');
    const value = input.value.trim();
    if (!value) { input.focus(); return; }
    if (!state.available.some(m => m.id === value)) {
      state.available.push({ id: value, contextWindow: R.DEFAULT_CONTEXT });
    }
    state.checked.add(value);
    input.value = '';
    renderOptions(state);
  };

  const runFormTest = async state => {
    const v = formValues(state);
    const status = state.node.querySelector('[data-cm-fetch-status]');
    const model = [...state.checked][0];
    if (!R.isValidHttpUrl(v.baseUrl) || (!R.isLocalUrl(v.baseUrl) && !/^https:\/\//i.test(v.baseUrl))) {
      status.textContent = '请先填写有效的接口地址。'; return;
    }
    if (!model) { status.textContent = '请先勾选至少一个模型。'; return; }
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 10000);
    status.textContent = '正在发送最小请求…';
    try {
      const result = await R.testConnection({ protocol: v.protocol, baseUrl: v.baseUrl, apiKey: v.apiKey, model, signal: controller.signal });
      status.textContent = result.message;
    } catch (error) {
      status.textContent = error.name === 'AbortError'
        ? '测试超时，请检查网络和服务地址。'
        : '测试失败；编辑已保存密钥的配置时请重新填写密钥后再测（密钥不回显）。';
    } finally {
      clearTimeout(timer);
    }
  };

  const submitForm = async (state, form) => {
    const errorBox = state.node.querySelector('[data-cm-error]');
    const showError = message => { errorBox.textContent = message; errorBox.hidden = false; };
    const v = formValues(state);
    const selected = state.available.filter(m => state.checked.has(m.id))
      .map(m => ({ id: m.id, contextWindow: Number(m.contextWindow) }));

    const matchedVendor = R.MODEL_VENDORS.find(x =>
      !x.custom && x.protocol === v.protocol && x.baseUrl && R.trimUrl(x.baseUrl) === v.baseUrl);
    const vendorId = state.vendorId || matchedVendor?.id || 'custom';

    const sameGroup = state.raw.filter(i =>
      (i.provider || 'openai-compatible') === v.protocol && R.trimUrl(i.base_url || '') === v.baseUrl);
    const existingNames = new Set(
      sameGroup.filter(i => !(state.editing && i.id === state.editing.id)).map(i => i.model));
    const duplicateNames = selected.filter(m => existingNames.has(m.id)).map(m => m.id);

    const errors = R.validateModelConfig({
      displayName: v.displayName, vendorId, protocol: v.protocol, baseUrl: v.baseUrl,
      apiKey: v.apiKey, hasStoredKey: !!(state.editing?.has_api_key),
      models: selected, duplicateNames
    });
    if (Object.keys(errors).length) { showError(Object.values(errors)[0]); return; }

    const submit = form.querySelector('[type="submit"]');
    submit.disabled = true;
    try {
      if (state.editing) {
        const payload = {
          name: v.displayName, provider: v.protocol, model: selected[0].id,
          base_url: v.baseUrl, enabled: true, is_default: v.isDefault
        };
        if (v.apiKey) payload.api_key = v.apiKey;
        await api('/v1/models/' + encodeURIComponent(state.editing.id), { method: 'PUT', body: JSON.stringify(payload) });
        for (const extra of selected.slice(1)) {
          await api('/v1/models', {
            method: 'POST',
            body: JSON.stringify({ name: v.displayName, provider: v.protocol, model: extra.id, base_url: v.baseUrl, ...(v.apiKey ? { api_key: v.apiKey } : {}) })
          });
        }
      } else {
        for (let index = 0; index < selected.length; index += 1) {
          const m = selected[index];
          await api('/v1/models', {
            method: 'POST',
            body: JSON.stringify({
              name: v.displayName, provider: v.protocol, model: m.id, base_url: v.baseUrl,
              ...(v.protocol === 'ollama' ? {} : { api_key: v.apiKey }),
              is_default: v.isDefault && index === 0
            })
          });
        }
      }
      state.editing = null;
      await refreshRoot(state);
      await refreshDefaultSummary();
      toast(`已保存 ${selected.length} 个模型到 Cloud 数据库`);
      // 保存后测试闭环：浏览器直连做最小探测；已存密钥场景由 Cloud 侧凭据代理测试（后续接入）
      if (v.protocol === 'ollama' || v.apiKey) {
        const ok = await R.testConnection({ protocol: v.protocol, baseUrl: v.baseUrl, apiKey: v.apiKey, model: selected[0].id })
          .then(r => r.ok).catch(() => false);
        toast(ok ? '连接测试通过' : '已保存；连接测试未通过，请检查密钥或网络后在编辑页重试');
      } else {
        toast('已保存；Cloud 侧凭据测试接口接入后将自动验证默认模型连通性');
      }
    } catch (error) {
      showError(error.message);
    } finally {
      submit.disabled = false;
    }
  };

  // —— 分享 ——
  const openShare = item => {
    const vendor = vendorOfGroup(item.provider, item.base_url);
    const payload = R.buildSharePayload({
      vendorId: vendor?.id || 'custom',
      displayName: vendor?.name || item.name || '自定义配置',
      protocol: item.provider || 'openai-compatible',
      baseUrl: item.base_url || '',
      models: [{ id: item.model }]
    });
    const uri = R.encodeShare(payload);
    const node = modal('分享模型', `${vendor?.name || '自定义配置'} · ${item.model}`, `
      <div class="cm-qr">二维码占位<br>其他端扫码识别<br>notemeld://model-add</div>
      <p class="cm-note" style="text-align:center">分享内容仅包含厂商、地址与模型信息，<strong>不包含 API 密钥</strong>。</p>
      <div class="cm-share-row"><input type="text" readonly value="${escape(uri)}" data-cm-share-uri><button class="primary-button" type="button" data-cm-share-copy>复制</button></div>`);
    node.querySelector('[data-cm-share-copy]').addEventListener('click', async button_event => {
      const button = button_event.currentTarget;
      try {
        await navigator.clipboard.writeText(uri);
      } catch {
        const input = node.querySelector('[data-cm-share-uri]');
        input.select();
        document.execCommand('copy');
      }
      toast('分享信息已复制（不含 API 密钥）');
      button.textContent = '已复制';
      setTimeout(() => { button.textContent = '复制'; }, 1600);
    });
  };

  // —— 粘贴导入 ——
  const openImport = state => {
    const node = modal('从其他端导入', '粘贴其他端分享的 notemeld://model-add 链接或分享 JSON；导入后需补填 API 密钥。', `
      <label>分享信息<textarea data-cm-import-text rows="5" style="width:100%;font-family:ui-monospace,monospace;font-size:12.5px" placeholder="notemeld://model-add?d=…"></textarea></label>
      <p class="form-message" data-cm-import-error role="alert" hidden></p>
      <div class="dialog-actions"><button class="secondary-button" type="button" data-cm-close>取消</button>
      <button class="primary-button" type="button" data-cm-import-parse>识别并填入</button></div>`);
    node.querySelector('[data-cm-import-parse]').addEventListener('click', () => {
      const text = node.querySelector('[data-cm-import-text]').value;
      const parsed = R.decodeShare(text);
      const errorBox = node.querySelector('[data-cm-import-error]');
      if (!parsed) {
        errorBox.textContent = '无法识别：请粘贴完整的 notemeld://model-add 链接或分享 JSON。';
        errorBox.hidden = false;
        return;
      }
      node._cmClose();
      applyImport(state, parsed);
      toast('已解析分享信息，请补填密钥');
    });
  };

  // —— 事件委托 ——
  const delegateClick = async (state, event) => {
    const find = attr => event.target.closest(`[${attr}]`);

    let button = find('data-cm-retry');
    if (button) { refreshRoot(state); return; }

    button = find('data-cm-share');
    if (button) { openShare(state.raw.find(i => i.id === button.dataset.cmShare)); return; }

    if (state.mode === 'vendors') {
      if (find('data-cm-back-root')) { renderRoot(state); return; }
      const vendorButton = find('data-cm-vendor');
      if (vendorButton && !vendorButton.disabled) openCreate(state, vendorButton.dataset.cmVendor);
      return;
    }

    if (state.mode === 'form') {
      button = find('data-cm-back-vendors');
      if (button) { renderVendors(state); return; }
      button = find('data-cm-back-root');
      if (button) { renderRoot(state); return; }
      button = find('data-cm-key-toggle');
      if (button) {
        const input = state.node.querySelector('[name="apiKey"]');
        const showing = input.type === 'text';
        input.type = showing ? 'password' : 'text';
        button.textContent = showing ? '显示' : '隐藏';
        return;
      }
      button = find('data-cm-fetch');
      if (button) { await fetchModels(state); return; }
      button = find('data-cm-test');
      if (button) { await runFormTest(state); return; }
      button = find('data-cm-manual-add');
      if (button) { manualAdd(state); return; }
      return;
    }

    // root view
    button = find('data-cm-add');
    if (button) { renderVendors(state); return; }
    button = find('data-cm-import');
    if (button) { openImport(state); return; }
    button = find('data-cm-back-vendors');
    if (button) { renderVendors(state); return; }
    button = find('data-cm-edit');
    if (button) {
      if (!state.admin) return;
      openEdit(state, state.raw.find(i => i.id === button.dataset.cmEdit));
      return;
    }
    button = find('data-cm-toggle');
    if (button && state.admin) {
      button.disabled = true;
      const item = state.raw.find(i => i.id === button.dataset.cmToggle);
      try {
        await api('/v1/models/' + encodeURIComponent(item.id), { method: 'PUT', body: JSON.stringify({ enabled: !item.enabled }) });
        await refreshRoot(state);
      } catch (error) { toast(error.message); button.disabled = false; }
      return;
    }
    button = find('data-cm-default');
    if (button && state.admin) {
      button.disabled = true;
      try {
        await api('/v1/models/' + encodeURIComponent(button.dataset.cmDefault), { method: 'PUT', body: JSON.stringify({ is_default: true }) });
        await refreshRoot(state);
        await refreshDefaultSummary();
      } catch (error) { toast(error.message); button.disabled = false; }
      return;
    }
    button = find('data-cm-delete');
    if (button && state.admin) {
      const item = state.raw.find(i => i.id === button.dataset.cmDelete);
      if (!item || !window.confirm(`确认删除模型 ${item.model} 的配置？`)) return;
      button.disabled = true;
      try {
        await api('/v1/models/' + encodeURIComponent(item.id), { method: 'DELETE' });
        await refreshRoot(state);
        await refreshDefaultSummary();
        toast('模型配置已删除');
      } catch (error) { toast(error.message); button.disabled = false; }
    }
  };

  // —— 接管入口（捕获阶段，先于 c06-ui-fixes.js / c06-live.js 生效）——
  document.addEventListener('click', event => {
    const managerButton = event.target.closest('[data-model-manager]');
    if (managerButton) {
      event.preventDefault();
      event.stopImmediatePropagation();
      openManager();
      return;
    }
    const testButton = event.target.closest('[data-model-test]');
    if (testButton) {
      event.preventDefault();
      event.stopImmediatePropagation();
      api('/v1/models').then(raw => {
        const def = raw.find(i => i.is_default) || raw.find(i => i.enabled);
        if (!def) { toast('尚未配置模型，请先添加。'); return; }
        // Cloud 密钥加密保存在服务端、不下发明文；连通性由 Cloud 侧凭据代理测试，接口接入后在此调用
        toast(`默认模型 ${def.model}：Cloud 侧凭据测试接口接入后执行（前端不持有明文密钥）。`);
      }).catch(error => toast(error.message));
    }
  }, true);
})();
