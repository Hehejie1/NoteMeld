(() => {
  const designTokens=document.createElement('link'); designTokens.rel='stylesheet'; designTokens.href='../../design-system/tokens.css'; document.head.append(designTokens);
  const designPrimitives=document.createElement('link'); designPrimitives.rel='stylesheet'; designPrimitives.href='../../design-system/primitives.css'; document.head.append(designPrimitives);
  const designScript=document.createElement('script'); designScript.src='../../design-system/primitives.js'; designScript.dataset.nmDesignSystem='true'; document.head.append(designScript);
  const page = document.body.dataset.page;
  const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
  const list = values => (values || []).map(escapeHtml).join('、') || '待补充';
  const statusLabel = {implemented:'已实现', partial:'部分实现', prototype:'原型演示', needs_backend:'待后端', missing:'待设计'};
  const status = value => `<span class="doc-badge status-${escapeHtml(value)}">${escapeHtml(statusLabel[value] || value || '待补充')}</span>`;

  const showFeature = (feature, defaults) => {
    const modal = document.createElement('dialog');
    modal.className = 'prototype-explain-dialog';
    modal.innerHTML = `<form method="dialog">
      <div class="doc-dialog-kicker">功能说明 · ${escapeHtml(feature?.id || '未登记')}</div>
      <h2>${escapeHtml(feature?.title || '页面交互')}</h2>
      <p>${escapeHtml(feature?.description || '该交互点尚未登记到功能配置，请先补充功能、数据和状态定义。')}</p>
      <div class="doc-dialog-grid">
        <div><strong>实现状态</strong>${status(feature?.status || 'missing')}</div>
        <div><strong>状态流</strong><span>${list(feature?.state)}</span></div>
        <div><strong>接口 / 能力</strong><span>${list(feature?.api)}</span></div>
        <div><strong>数据 / 存储</strong><span>${list(feature?.tables)}</span></div>
        <div><strong>执行动作</strong><span>${escapeHtml(feature?.interaction?.action || defaults?.action || '执行页面交互')}</span></div>
        <div><strong>成功结果</strong><span>${escapeHtml(feature?.interaction?.success || defaults?.success || '显示成功状态')}</span></div>
        <div><strong>失败结果</strong><span>${escapeHtml(feature?.interaction?.failure || defaults?.failure || '显示失败状态')}</span></div>
        <div><strong>预览模式</strong><span>${escapeHtml(feature?.interaction?.preview_behavior || defaults?.preview_behavior || '执行页面交互并反馈结果')}</span></div>
        <div><strong>讲解模式</strong><span>${escapeHtml(feature?.interaction?.explain_behavior || defaults?.explain_behavior || '拦截点击并展示说明')}</span></div>
      </div>
      <button class="doc-dialog-close">知道了</button>
    </form>`;
    document.body.append(modal);
    modal.showModal();
    modal.addEventListener('close', () => modal.remove(), {once:true});
  };

  const renderArchitecture = config => {
    const root = document.querySelector('[data-architecture-body]');
    if (!root) return;
    const layers = config.architecture?.layers || [];
    root.innerHTML = layers.map(layer => `<section class="architecture-section">
      <div class="architecture-heading"><span class="doc-badge">${escapeHtml(layer.id)}</span><div><h2>${escapeHtml(layer.title)}</h2><p>${escapeHtml(layer.description)}</p></div></div>
      <div class="doc-grid">${(layer.components || []).map(component => `<article class="doc-card" data-feature-id="${escapeHtml(component.feature_id || '')}"><span class="doc-badge">${escapeHtml(component.owner || '跨端')}</span><h3>${escapeHtml(component.name)}</h3><p>${escapeHtml(component.responsibility)}</p><p class="doc-meta"><strong>输入：</strong>${escapeHtml(component.input || '—')}<br><strong>输出：</strong>${escapeHtml(component.output || '—')}</p></article>`).join('')}</div>
    </section>`).join('') + (config.architecture?.cloud_control_plane ? `<section class="architecture-section cloud-control-plane"><div class="architecture-heading"><span class="doc-badge">CLOUD</span><div><h2>Cloud 控制面模块</h2><p>${escapeHtml(config.architecture.cloud_control_plane.description)}</p></div></div><div class="doc-grid">${(config.architecture.cloud_control_plane.modules || []).map(module => `<article class="doc-card"><span class="doc-badge">${escapeHtml(module.id)}</span><h3>${escapeHtml(module.title)}</h3><p><strong>接口：</strong>${escapeHtml(module.interface)}</p><p><strong>实现：</strong>${escapeHtml(module.implementation)}</p><p class="doc-meta"><strong>数据：</strong>${list(module.data)}${module.external ? `<br><strong>外部事实源：</strong>${escapeHtml(module.external)}` : ''}</p></article>`).join('')}</div></section>` : '');
  };

  const renderDatabase = config => {
    const body = document.querySelector('[data-schema-body]');
    if (!body) return;
    body.innerHTML = Object.entries(config.database || {}).map(([name, item]) => `<tr>
      <td><code>${escapeHtml(name)}</code><small>${escapeHtml(item.owner || '')}</small></td>
      <td>${escapeHtml(item.purpose)}</td>
      <td>${list(item.pages)}</td>
      <td>${status(item.status || 'existing')}${item.missing ? `<small class="doc-missing">缺少：${list(item.missing)}</small>` : ''}</td>
    </tr>`).join('');
    const details = document.querySelector('[data-database-details]');
    if (details) details.innerHTML = Object.entries(config.database_details || {}).map(([name, item]) => `<article class="doc-card database-detail"><div class="architecture-heading"><code>${escapeHtml(name)}</code><span class="doc-badge">PK · ${escapeHtml(item.primary_key || '待补充')}</span></div><p><strong>字段：</strong>${escapeHtml(item.columns || '待补充')}</p><p><strong>外键：</strong>${list(item.foreign_keys)}</p>${item.external ? `<p class="doc-meta"><strong>外部事实源：</strong>${escapeHtml(item.external)}</p>` : ''}</article>`).join('') || '<p>暂无字段定义。</p>';
  };

  const renderFeatures = config => {
    const body = document.querySelector('[data-feature-table]');
    if (!body) return;
    body.innerHTML = Object.entries(config.features || {}).map(([id, feature]) => `<tr data-feature-id="${escapeHtml(id)}">
      <td><code>${escapeHtml(id)}</code></td><td>${escapeHtml(feature.page)}</td><td>${escapeHtml(feature.title)}</td>
      <td>${escapeHtml(feature.description)}</td><td>${list(feature.api)}</td><td>${list(feature.tables)}</td><td>${status(feature.status)}</td>
    </tr>`).join('');
  };

  const renderDecisionLog = config => {
    document.querySelectorAll('[data-decision-log]').forEach(root => {
      root.innerHTML = (config.decision_log || []).map(item => `<article class="doc-card decision-card"><div class="architecture-heading"><span class="doc-badge status-partial">待确认</span><div><h3>${escapeHtml(item.topic)}</h3><p>${escapeHtml(item.current)}</p></div></div><p><strong>建议：</strong>${escapeHtml(item.recommendation)}</p><p class="doc-meta"><strong>影响：</strong>${escapeHtml(item.impact)}</p></article>`).join('') || '<p>暂无待确认决策。</p>';
    });
  };

  const bindExplainMode = config => {
    const featureMap = config.features || {};
    const bindings = config.bindings || {};
    Object.entries(bindings).forEach(([featureId, selectors]) => {
      if (featureMap[featureId]?.page !== page) return;
      (selectors || []).forEach(selector => document.querySelectorAll(selector).forEach(element => {
        element.dataset.featureId = featureId;
      }));
    });
    document.addEventListener('click', event => {
      if (!document.body.classList.contains('explain-mode') || event.target.closest('dialog')) return;
      const interactive = event.target.closest('a,button,[role="button"]');
      const bound = event.target.closest('[data-feature-id]');
      const target = (interactive?.dataset.featureId ? interactive : bound) || interactive || bound;
      if (!target || target.closest('.prototype-explain-dialog')) return;
      event.preventDefault();
      event.stopPropagation();
      const feature = featureMap[target.dataset.featureId];
      showFeature(feature ? {...feature, id: target.dataset.featureId} : undefined, config.interaction_defaults);
    }, true);
  };

  fetch('../../config/feature-registry.json').then(response => {
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return response.json();
  }).then(config => {
    renderArchitecture(config);
    renderDatabase(config);
    renderFeatures(config);
    renderDecisionLog(config);
    const questions = document.querySelector('[data-open-questions]');
    if (questions) questions.innerHTML = (config.open_questions || []).map(item => `<li>${escapeHtml(item)}</li>`).join('');
    bindExplainMode(config);
    window.addEventListener('message', event => {
      if (event.data?.type !== 'notemeld-prototype-mode') return;
      document.body.classList.toggle('explain-mode', event.data.mode === 'explain');
    });
  }).catch(error => {
    const node = document.querySelector('[data-doc-error]');
    if (node) node.textContent = `配置读取失败：${error.message}`;
  });
})();
