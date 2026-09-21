(() => {
  const $ = selector => document.querySelector(selector);
  const records = [];
  let editingId = null;
  let deletingId = null;
  let scanType = 'cloud';
  let scanStream = null;
  const icon = name => { const element = document.createElement('i'); element.setAttribute('data-lucide', name); return element; };
  const icons = () => window.lucide?.createIcons({ attrs: { 'stroke-width': 2 } });
  const notify = message => { const node = $('[data-remote-toast]'); node.textContent = message; node.hidden = false; clearTimeout(node._timer); node._timer = setTimeout(() => { node.hidden = true; }, 2600); };
  const stopScan = () => { scanStream?.getTracks().forEach(track => track.stop()); scanStream = null; const video = $('[data-remote-video]'); video.pause(); video.srcObject = null; video.hidden = true; };
  const closeSheets = () => { document.querySelectorAll('.mobile-sheet').forEach(sheet => { sheet.hidden = true; }); $('[data-sheet-backdrop]').hidden = true; stopScan(); };
  const openSheet = selector => { closeSheets(); $('[data-sheet-backdrop]').hidden = false; $(selector).hidden = false; };
  const clouds = () => records.filter(record => record.type === 'cloud');
  const validAddress = (value, type) => {
    try { const url = new URL(value); return !url.username && !url.password && (url.protocol === 'https:' || (type === 'client' && url.protocol === 'wss:') || (url.protocol === 'http:' && ['localhost', '127.0.0.1'].includes(url.hostname))); }
    catch { return false; }
  };
  const card = record => {
    const item = document.createElement('article'); item.className = `remote-card ${record.type}`;
    const mark = document.createElement('span'); mark.className = 'remote-card-mark'; mark.append(icon(record.type === 'cloud' ? 'cloud' : 'monitor-smartphone'));
    const body = document.createElement('div'); body.className = 'remote-card-body';
    const title = document.createElement('strong'); title.textContent = record.name;
    const address = document.createElement('small'); address.textContent = record.address;
    const status = document.createElement('span'); status.className = 'remote-status'; status.textContent = '未验证';
    body.append(title, address, status);
    const actions = document.createElement('span'); actions.className = 'remote-card-actions';
    const edit = document.createElement('button'); edit.type = 'button'; edit.dataset.remoteEdit = record.id; edit.setAttribute('aria-label', `编辑${record.name}`); edit.append(icon('pencil'));
    const remove = document.createElement('button'); remove.type = 'button'; remove.dataset.remoteDelete = record.id; remove.setAttribute('aria-label', `删除${record.name}`); remove.append(icon('trash-2'));
    actions.append(edit, remove); item.append(mark, body, actions); return item;
  };
  const render = () => {
    const host = $('[data-remote-groups]'); host.replaceChildren();
    if (!records.length) { const empty = document.createElement('div'); empty.className = 'remote-empty'; empty.append(icon('cloud-off'), document.createTextNode('还没有远程连接。点击右上角 + 添加云端，或扫描一次性配对码。')); host.append(empty); icons(); return; }
    clouds().forEach(cloud => {
      const clients = records.filter(record => record.type === 'client' && record.cloudId === cloud.id);
      const group = document.createElement('section'); group.className = 'remote-cloud-group';
      const heading = document.createElement('div'); heading.className = 'remote-cloud-heading';
      const title = document.createElement('h2'); title.textContent = cloud.name;
      const count = document.createElement('span'); count.textContent = `${clients.length} 台远程设备`;
      heading.append(title, count); group.append(heading, card(cloud)); clients.forEach(client => group.append(card(client))); host.append(group);
    });
    icons();
  };
  const syncType = () => {
    const form = $('[data-remote-form]'); const client = form.elements.type.value === 'client';
    $('[data-cloud-parent]').hidden = !client;
    const parent = form.elements.cloudId; parent.replaceChildren();
    clouds().forEach(cloud => { const option = document.createElement('option'); option.value = cloud.id; option.textContent = cloud.name; parent.append(option); });
    parent.required = client;
  };
  const showForm = (type = 'cloud', record = null, scanned = null) => {
    const form = $('[data-remote-form]'); form.reset(); editingId = record?.id || null;
    form.elements.type.value = record?.type || type; form.elements.type.disabled = Boolean(record); syncType();
    form.elements.cloudId.value = record?.cloudId || clouds()[0]?.id || '';
    form.elements.name.value = record?.name || scanned?.name || '';
    form.elements.address.value = record?.address || scanned?.address || '';
    form.elements.credential.value = '';
    form.elements.credential.placeholder = record?.credential ? '已设置；留空则保留' : '输入连接凭证';
    $('[data-remote-form-title]').textContent = record ? '编辑连接' : '添加远程连接';
    $('[data-remote-eyebrow]').textContent = record ? record.type === 'cloud' ? '云端连接' : '远程客户端' : scanned ? '已识别一次性配对码' : '新建配置';
    $('[data-remote-error]').hidden = true;
    openSheet('[data-remote-form-sheet]');
  };
  $('[data-remote-add]').addEventListener('click', () => showForm());
  $('[data-remote-form]').elements.type.addEventListener('change', syncType);
  $('[data-remote-form]').addEventListener('submit', event => {
    event.preventDefault(); const form = event.currentTarget; const type = form.elements.type.value;
    const name = form.elements.name.value.trim(); const address = form.elements.address.value.trim(); const cloudId = type === 'client' ? form.elements.cloudId.value : null;
    const error = $('[data-remote-error]');
    if (!name || !validAddress(address, type) || type === 'client' && !clouds().some(cloud => cloud.id === cloudId)) {
      error.textContent = '请填写名称、有效的安全连接地址，并为客户端选择云端。'; error.hidden = false; return;
    }
    const existing = records.find(record => record.id === editingId);
    const credential = form.elements.credential.value.trim() || existing?.credential || '';
    if (existing) Object.assign(existing, { name, address, cloudId, credential });
    else records.push({ id: crypto.randomUUID(), type, name, address, cloudId, credential });
    closeSheets(); render(); notify('配置已保存；连接状态尚未验证。');
  });
  $('[data-remote-groups]').addEventListener('click', event => {
    const edit = event.target.closest('[data-remote-edit]'); const remove = event.target.closest('[data-remote-delete]');
    if (edit) { const record = records.find(item => item.id === edit.dataset.remoteEdit); if (record) showForm(record.type, record); }
    if (remove) {
      const record = records.find(item => item.id === remove.dataset.remoteDelete); if (!record) return;
      deletingId = record.id;
      const children = record.type === 'cloud' ? records.filter(item => item.cloudId === record.id).length : 0;
      $('[data-remote-delete-copy]').textContent = children ? `确定删除「${record.name}」及其下 ${children} 台设备的本页配置吗？` : `确定删除「${record.name}」的本页配置吗？`;
      $('[data-remote-delete-modal]').hidden = false; $('[data-remote-cancel]').focus();
    }
  });
  $('[data-remote-cancel]').addEventListener('click', () => { $('[data-remote-delete-modal]').hidden = true; deletingId = null; });
  $('[data-remote-confirm]').addEventListener('click', () => {
    const index = records.findIndex(record => record.id === deletingId); if (index < 0) return;
    const target = records[index];
    for (let i = records.length - 1; i >= 0; i--) if (records[i].id === deletingId || target.type === 'cloud' && records[i].cloudId === deletingId) records.splice(i, 1);
    $('[data-remote-delete-modal]').hidden = true; deletingId = null; render(); notify('本页配置已删除。');
  });
  $('[data-remote-scan-open]').addEventListener('click', () => openSheet('[data-remote-scan-choice]'));
  $('[data-remote-scan-choice]').addEventListener('click', event => {
    const button = event.target.closest('[data-scan-type]'); if (!button) return;
    scanType = button.dataset.scanType;
    if (scanType === 'client' && !clouds().length) { notify('请先添加云端连接，再关联远程客户端。'); return; }
    $('[data-scan-kind]').textContent = scanType === 'cloud' ? '扫描云端' : '扫描远程客户端';
    $('[data-remote-scan-status]').textContent = '二维码只能包含短时配对码，不能包含长期连接凭证。';
    openSheet('[data-remote-scan-sheet]');
  });
  $('[data-start-remote-scan]').addEventListener('click', async () => {
    const status = $('[data-remote-scan-status]');
    if (!('BarcodeDetector' in window) || !navigator.mediaDevices?.getUserMedia) { status.textContent = '当前浏览器不支持扫码；请使用支持相机和二维码识别的移动设备。'; return; }
    try {
      const detector = new BarcodeDetector({ formats: ['qr_code'] });
      scanStream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: 'environment' }, audio: false });
      const video = $('[data-remote-video]'); video.srcObject = scanStream; video.hidden = false; await video.play(); status.textContent = '请扫描对应类型的一次性配对码。';
      const tick = async () => {
        if (!scanStream || $('[data-remote-scan-sheet]').hidden) return;
        try {
          const found = await detector.detect(video);
          if (found.length) {
            const link = new URL(found[0].rawValue);
            const allowedFields = new Set(['type', 'code', 'name', 'address']);
            if (link.protocol !== 'notemeld:' || link.hostname !== 'pair' || link.searchParams.get('type') !== scanType || !/^[A-Za-z0-9_-]{6,128}$/.test(link.searchParams.get('code') || '') || [...link.searchParams.keys()].some(key => !allowedFields.has(key))) throw new Error('invalid');
            const scanned = { name: link.searchParams.get('name') || '', address: link.searchParams.get('address') || '' };
            stopScan(); showForm(scanType, null, scanned); notify('已识别配对码；请核对地址并完成真实设备认证。'); return;
          }
        } catch { status.textContent = '二维码类型不匹配或内容无效，请重试。'; }
        requestAnimationFrame(tick);
      }; tick();
    } catch { stopScan(); status.textContent = '无法使用相机，请检查设备支持或浏览器权限。'; }
  });
  document.querySelectorAll('[data-sheet-close]').forEach(button => button.addEventListener('click', closeSheets));
  $('[data-sheet-backdrop]').addEventListener('click', closeSheets);
  document.addEventListener('keydown', event => { if (event.key === 'Escape') { closeSheets(); $('[data-remote-delete-modal]').hidden = true; } });
  render();
})();
