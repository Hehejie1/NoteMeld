import http from '@ohos.net.http';
import preferences from '@ohos.data.preferences';
import fileIo from '@ohos.file.fs';
import pickerModule from '@ohos.file.picker';
import util from '@ohos.util';
import huks from '@ohos.security.huks';
import { MobileScreen, AgentLocation, ConnectionState, MobileSurfaceState, MobileSurfaceAction, MobileMessage, MobileTask, RemoteDevice, StorageItem, reduceMobileSurface } from '../model/MobileSurfaceState';
import { HarmonyKeyPair, HarmonyRemoteCrypto, PersistedEd25519Key } from '../services/HarmonyRemoteCrypto';
import { HarmonyRemoteTransport } from '../services/HarmonyRemoteTransport';

/** ArkUI host for M01–M06. Agent execution remains in the SDK/runtime host. */
@Entry
@Component
struct MobileSurface {
  @State state: MobileSurfaceState = new MobileSurfaceState();
  private refreshTimer: number = -1;

  aboutToAppear() { this.loadTasks(); this.loadLocalState(); this.refreshTimer = setInterval(() => this.loadTasks(), 5000); }
  aboutToDisappear() { if (this.refreshTimer >= 0) { clearInterval(this.refreshTimer); this.refreshTimer = -1; } }

  private async loadLocalState(): Promise<void> {
    try {
      let store = await preferences.getPreferences(getContext(this), 'notemeld-mobile-state');
      this.state.selectedModel = String(await store.get('selected_model', 'Auto'));
      this.state.language = String(await store.get('language', '跟随系统'));
      this.state.fontSize = Number(await store.get('font_size', 16));
      this.state.followSystemFont = Boolean(await store.get('follow_system_font', false));
      this.state.notificationsEnabled = Boolean(await store.get('notifications_enabled', true));
      this.state.cloudURL = String(await store.get('cloud_url', this.state.cloudURL));
      this.state.cloudUsername = String(await store.get('cloud_username', ''));
      let encodedMemories = String(await store.get('memories', '[]'));
      let decodedMemories = JSON.parse(encodedMemories) as string[];
      this.state.memories = Array.isArray(decodedMemories) ? decodedMemories : [];
      let encodedTasks = String(await store.get('tasks', '[]'));
      let decodedTasks = JSON.parse(encodedTasks) as Array<Record<string, Object>>;
      this.state.tasks = Array.isArray(decodedTasks) ? decodedTasks.map((row: Record<string, Object>) => new MobileTask(String(row['id'] ?? ''), String(row['title'] ?? '未命名会话'), String(row['status'] ?? 'idle'))) : [];
      this.state.storage = await this.storageItems();
    } catch (_) {
      this.state.storage = await this.storageItems();
    }
  }

  private async persistLocalState(): Promise<void> {
    try {
      let store = await preferences.getPreferences(getContext(this), 'notemeld-mobile-state');
      await store.put('selected_model', this.state.selectedModel);
      await store.put('language', this.state.language);
      await store.put('font_size', this.state.fontSize);
      await store.put('follow_system_font', this.state.followSystemFont);
      await store.put('notifications_enabled', this.state.notificationsEnabled);
      await store.put('cloud_url', this.state.cloudURL);
      await store.put('cloud_username', this.state.cloudUsername);
      await store.put('memories', JSON.stringify(this.state.memories));
      let taskRows: Array<Record<string, Object>> = [];
      this.state.tasks.slice(0, 50).forEach((task: MobileTask) => {
        let row: Record<string, Object> = JSON.parse('{}') as Record<string, Object>;
        row['id'] = task.id; row['title'] = task.title; row['status'] = task.status; taskRows.push(row);
      });
      await store.put('tasks', JSON.stringify(taskRows));
      await store.flush();
    } catch (_) {}
  }

  private storageRoots(): StorageRoots {
    let context = getContext(this);
    let roots = new StorageRoots();
    roots.cache = context.cacheDir;
    roots.cloud = `${context.filesDir}/cloud-cache`;
    roots.local = `${context.filesDir}/local`;
    roots.artifacts = `${context.filesDir}/artifacts`;
    return roots;
  }

  private async directorySize(path: string): Promise<number> {
    try {
      let files = await fileIo.listFile(path, { recursion: true });
      let total = 0;
      for (let item of files) {
        try { total += (await fileIo.stat(`${path}${item}`)).size; } catch (_) {}
      }
      return total / (1024 * 1024);
    } catch (_) { return 0; }
  }

  private async storageItems(): Promise<StorageItem[]> {
    let roots = this.storageRoots();
    return [
      new StorageItem('cache', '缓存', '接口、预览与附件缓存', await this.directorySize(roots.cache)),
      new StorageItem('cloud', '云端对话数据', '本机保存的云端事件与缓存', await this.directorySize(roots.cloud)),
      new StorageItem('local', '本机对话数据', '仅保存在本机的会话记录', await this.directorySize(roots.local)),
      new StorageItem('artifacts', '下载的产物文件', '沙箱下载的预览与产物', await this.directorySize(roots.artifacts))
    ];
  }

  private async clearStorageFiles(id: string | null): Promise<void> {
    let roots = this.storageRoots();
    let selected: string[] = id === null ? [roots.cache, roots.cloud, roots.local, roots.artifacts] : [id === 'cache' ? roots.cache : id === 'cloud' ? roots.cloud : id === 'local' ? roots.local : roots.artifacts];
    for (let root of selected) {
      if (root === undefined) continue;
      try {
        let files = await fileIo.listFile(root, { recursion: true });
        for (let item of files.reverse()) { try { await fileIo.unlink(`${root}${item}`); } catch (_) {} }
      } catch (_) {}
    }
    this.state.storage = await this.storageItems();
  }

  private async sendAgent(input: string): Promise<void> {
    let request = http.createHttp();
    try {
      let session = await request.request('http://127.0.0.1:8483/api/agent/v1/sessions', { method: http.RequestMethod.POST, header: { 'Content-Type': 'application/json' }, extraData: JSON.stringify({ title: 'NoteMeld Mobile' }) });
      let sessionId = (JSON.parse(session.result as string) as AgentEnvelope).data.id;
      let turn = await request.request(`http://127.0.0.1:8483/api/agent/v1/sessions/${sessionId}/turns`, { method: http.RequestMethod.POST, header: { 'Content-Type': 'application/json' }, extraData: JSON.stringify({ input }) });
      let turnId = (JSON.parse(turn.result as string) as AgentEnvelope).data.turn_id;
      let events = await request.request(`http://127.0.0.1:8483/api/agent/v1/turns/${turnId}/events?after_sequence=-1`, { method: http.RequestMethod.GET, header: { Accept: 'text/event-stream' } });
      let frames = String(events.result as string).split('\n\n');
      frames.forEach((frame: string) => { let line = frame.split('\n').find((value: string) => value.startsWith('data:')); if (line === undefined) return; try { let event = JSON.parse(line.substring(5).trim()) as Record<string, Object>; let payload = event['payload'] as Record<string, Object>; let content = String(payload['content'] ?? ''); if (content.length > 0) this.dispatch({ kind: 'addMessage', value: new MobileMessage('assistant', content) }); } catch (_) {} });
    } catch (error) { this.dispatch({ kind: 'addMessage', value: new MobileMessage('assistant', `Agent 请求失败：${String(error)}`) }); this.state.connection = ConnectionState.Offline; } finally { this.state.sending = false; request.destroy(); }
  }

  private async deleteConversation(): Promise<void> {
    if (this.state.activeTaskId.length === 0) { this.state.sheet = ''; return }
    let request = http.createHttp()
    try {
      let response = await request.request(`http://127.0.0.1:8483/api/conversations/${this.state.activeTaskId}`, { method: http.RequestMethod.DELETE, connectTimeout: 4000, readTimeout: 8000 })
      if (response.responseCode < 200 || response.responseCode > 299) { this.state.connection = ConnectionState.Error; return }
      this.state.tasks = this.state.tasks.filter((item: MobileTask) => item.id !== this.state.activeTaskId)
      this.state.screen = MobileScreen.Home
      this.state.sheet = ''
    } catch (_) { this.state.connection = ConnectionState.Error } finally { request.destroy() }
  }

  private async sendCloudAgent(input: string): Promise<void> {
    let request = http.createHttp();
    try {
      let store = await preferences.getPreferences(getContext(this), 'notemeld-cloud');
      let base = String(await store.get('cloud_url', this.state.cloudURL)).replace(/\/$/, '');
      let encrypted = String(await store.get('cloud_token', ''));
      if (encrypted.length === 0) throw new Error('未登录 Cloud');
      let token = await HarmonyTokenStore.decrypt(encrypted);
      let syncStore = await preferences.getPreferences(getContext(this), 'notemeld-cloud-sync');
      let sessionID = String(await syncStore.get('session_id', ''));
      if (sessionID.length === 0) {
        let session = JSON.parse(await this.cloudRequest(request, base, '/v1/sessions', token, JSON.stringify({ kind: 'cloud_native', title: 'NoteMeld Harmony' }))) as CloudEnvelope;
        sessionID = session.data.id;
        await syncStore.put('session_id', sessionID);
        await syncStore.put('event_sequence', 0);
        await syncStore.flush();
      }
      let attachments = await this.cloudAttachments();
      await this.cloudRequest(request, base, `/v1/sessions/${sessionID}/commands`, token, JSON.stringify({ request_id: `${Date.now()}`, input, attachments }));
      let after = Number(await syncStore.get('event_sequence', 0));
      for (let count = 0; count < 60; count += 1) {
        await new Promise<void>((resolve: () => void) => setTimeout(resolve, 500));
        let events = JSON.parse(await this.cloudGet(request, base, `/v1/sessions/${sessionID}/events?after=${after}`, token)) as CloudEventsEnvelope;
        let terminal = false;
        events.data.forEach((event: CloudEvent) => {
          after = Math.max(after, event.sequence);
          syncStore.put('event_sequence', after);
          if (event.payload.output.length > 0) this.dispatch({ kind: 'addMessage', value: new MobileMessage('assistant', event.payload.output) });
          terminal = terminal || event.event_type.startsWith('command.') && ['completed', 'failed', 'cancelled'].includes(event.payload.status);
        });
        await syncStore.flush();
        if (terminal) return;
      }
      this.dispatch({ kind: 'addMessage', value: new MobileMessage('assistant', 'Cloud Agent 等待超时') });
    } catch (error) {
      this.dispatch({ kind: 'addMessage', value: new MobileMessage('assistant', `Cloud Agent 请求失败：${String(error)}`) });
      this.state.connection = ConnectionState.Offline;
    } finally { this.state.sending = false; request.destroy(); }
  }

  private async pickAttachments(): Promise<void> {
    try {
      let picker = new pickerModule.DocumentViewPicker(getContext(this));
      let uris = await picker.select({ maxSelectNumber: 16 });
      let root = `${getContext(this).filesDir}/cloud-cache/attachments`;
      try { await fileIo.mkdir(`${getContext(this).filesDir}/cloud-cache`); } catch (_) {}
      try { await fileIo.mkdir(root); } catch (_) {}
      for (let uri of uris) {
        let name = uri.split('/').pop() ?? '附件';
        let destination = `${root}/${name}`;
        try { await fileIo.copyFile(uri, destination); this.dispatch({ kind: 'addAttachment', value: name }); } catch (_) {}
      }
      this.state.storage = await this.storageItems();
    } catch (_) {
      this.dispatch({ kind: 'addMessage', value: new MobileMessage('assistant', '文件选择已取消或当前设备不支持文件访问。') });
    }
  }

  private startAttachmentPicker(): void { this.pickAttachments(); }

  private async cloudAttachments(): Promise<CloudAttachment[]> {
    let result: CloudAttachment[] = [];
    let root = `${getContext(this).filesDir}/cloud-cache/attachments`;
    try {
      let files = await fileIo.listFile(root, { recursion: false });
      for (let name of files.slice(0, 16)) {
        let path = `${root}/${name}`;
        try {
          let info = await fileIo.stat(path);
          if (info.size > 10 * 1024 * 1024) continue;
          let handle = await fileIo.open(path);
          let buffer = new ArrayBuffer(info.size);
          await fileIo.read(handle.fd, buffer);
          await fileIo.close(handle);
          let attachment = new CloudAttachment();
          attachment.name = name;
          attachment.size = info.size;
          attachment.type = 'application/octet-stream';
          attachment.content_base64 = await new util.Base64Helper().encodeToString(new Uint8Array(buffer));
          result.push(attachment);
        } catch (_) {}
      }
    } catch (_) {}
    return result;
  }

  private async loadTasks(): Promise<void> {
    let request = http.createHttp();
    request.request('http://127.0.0.1:8483/api/conversations?limit=20', { method: http.RequestMethod.GET, connectTimeout: 4000, readTimeout: 8000 })
      .then(async (response: http.HttpResponse) => {
        let envelope = JSON.parse(response.result as string) as Record<string, Object>;
        let rows = envelope['data'] as Array<Record<string, Object>>;
        this.state.tasks = rows.map((row: Record<string, Object>) => new MobileTask(String(row['id'] ?? ''), String(row['title'] ?? '未命名会话'), String(row['status'] ?? 'idle')));
        await this.persistLocalState();
        this.state.connection = ConnectionState.Ready;
        this.loadProjection();
        request.destroy();
      }).catch(() => { this.state.connection = ConnectionState.Offline; request.destroy(); });
  }

  private loadProjection(): void {
    let request = http.createHttp();
    request.request('http://127.0.0.1:8483/api/mobile/projection?workspace_id=default', { method: http.RequestMethod.GET, connectTimeout: 4000, readTimeout: 8000 })
      .then((response: http.HttpResponse) => {
        try {
          let envelope = JSON.parse(response.result as string) as Record<string, Object>;
          let data = envelope['data'] as Record<string, Object>;
          let rows = data['memories'] as Array<Record<string, Object>>;
          this.dispatch({ kind: 'setMemories', value: rows.map((row: Record<string, Object>) => String(row['content'] ?? '')).filter((value: string) => value.length > 0) });
          let workspace = data['workspace'] as Record<string, Object>;
          this.recordProjectionCursor(Number(workspace['revision'] ?? 0));
        } catch (_) {}
        request.destroy();
      }).catch(() => { request.destroy(); });
  }

  private async recordProjectionCursor(revision: number): Promise<void> {
    let request = http.createHttp();
    try {
      let installID = await this.loadOrCreateInstallID();
      let response = await request.request('http://127.0.0.1:8483/api/mobile/sync-cursor', { method: http.RequestMethod.PUT, header: { 'Content-Type': 'application/json' }, extraData: JSON.stringify({ device_id: `harmony-${installID}`, workspace_id: 'default', session_id: '', snapshot_revision: revision, event_sequence: 0 }), connectTimeout: 4000, readTimeout: 8000 });
      if (response.responseCode < 200 || response.responseCode > 299) { this.state.connection = ConnectionState.Error; }
    } catch (_) {} finally { request.destroy(); }
  }

  private async saveMemory(): Promise<void> {
    let content = this.state.memoryDraft.trim();
    if (content.length === 0) return;
    let request = http.createHttp();
    try {
      let response = await request.request('http://127.0.0.1:8483/api/mobile/memories', { method: http.RequestMethod.POST, header: { 'Content-Type': 'application/json' }, extraData: JSON.stringify({ workspace_id: 'default', content, source: 'harmony' }), connectTimeout: 4000, readTimeout: 8000 });
      if (response.responseCode >= 200 && response.responseCode < 300) { this.dispatch({ kind: 'setMemoryDraft', value: '' }); this.loadProjection(); }
    } catch (_) { this.state.connection = ConnectionState.Error; } finally { request.destroy(); }
  }

  private async loginCloud(): Promise<void> {
    let base = this.state.cloudURL.trim().replace(/\/$/, '');
    if (base.length === 0 || this.state.cloudUsername.trim().length === 0 || this.state.cloudPassword.length === 0) {
      this.state.cloudStatus = '请填写 Cloud 地址、用户名和密码';
      return;
    }
    let request = http.createHttp();
    try {
      let login = await request.request(`${base}/v1/auth/login`, { method: http.RequestMethod.POST, header: { 'Content-Type': 'application/json' }, extraData: JSON.stringify({ username: this.state.cloudUsername, password: this.state.cloudPassword }), connectTimeout: 8000, readTimeout: 12000 });
      if (login.responseCode < 200 || login.responseCode >= 300) throw new Error(`登录失败 (${login.responseCode})`);
      let loginData = JSON.parse(login.result as string) as CloudEnvelope;
      let token = loginData.data.token;
      if (token.length === 0) throw new Error('Cloud 未返回登录凭据');
      let installID = await this.loadOrCreateInstallID();
      let deviceID = `harmony-${installID}`;
      let identity = await this.loadOrCreateRemoteIdentity();
      await this.cloudRequest(request, base, `/v1/devices/register`, token, JSON.stringify({ device_id: deviceID, platform: 'harmony', display_name: 'NoteMeld Harmony', public_key: HarmonyRemoteCrypto.base64(identity.publicKey) }));
      await this.cloudRequest(request, base, `/v1/devices/${deviceID}/heartbeat`, token, '{}');
      let devicesEnvelope = JSON.parse(await this.cloudGet(request, base, '/v1/devices', token)) as Record<string, Object>;
      let deviceRows = (devicesEnvelope['data'] ?? []) as Array<Record<string, Object>>;
      this.dispatch({ kind: 'setRemoteDevices', devices: deviceRows.filter((row: Record<string, Object>) => String(row['id'] ?? '') !== deviceID && String(row['public_key'] ?? '').length > 0).map((row: Record<string, Object>) => { let connectivity = row['connectivity'] as Record<string, Object> | undefined; let endpoints = connectivity === undefined ? [] : (connectivity['lan_endpoints'] as string[] ?? []); return new RemoteDevice(String(row['id'] ?? ''), String(row['display_name'] ?? row['id'] ?? ''), String(row['public_key'] ?? ''), Boolean(row['online']), endpoints); }) });
      let store = await preferences.getPreferences(getContext(this), 'notemeld-cloud');
      await store.put('cloud_url', base);
      await store.put('cloud_username', this.state.cloudUsername);
      await store.put('cloud_token', await HarmonyTokenStore.encrypt(token));
      await store.flush();
      this.state.cloudStatus = '已连接 Cloud · 设备已注册';
    } catch (error) {
      this.state.cloudStatus = `Cloud 连接失败：${String(error)}`;
    } finally {
      request.destroy();
    }
  }

  private async loadOrCreateInstallID(): Promise<string> {
    let store = await preferences.getPreferences(getContext(this), 'notemeld-device');
    let existing = await store.get('install_id', '') as string;
    if (existing.length > 0) return existing;
    let generated = `${Date.now()}-${Math.floor(Math.random() * 1000000)}`;
    await store.put('install_id', generated);
    await store.flush();
    return generated;
  }

  private async loadOrCreateRemoteIdentity(): Promise<HarmonyKeyPair> {
    let store = await preferences.getPreferences(getContext(this), 'notemeld-device');
    let encrypted = String(await store.get('ed25519_identity', ''));
    if (encrypted.length > 0) {
      let persisted = JSON.parse(await HarmonyTokenStore.decrypt(encrypted)) as PersistedEd25519Key;
      return HarmonyRemoteCrypto.restoreIdentity(persisted);
    }
    let identity = await HarmonyRemoteCrypto.generateIdentity();
    await store.put('ed25519_identity', await HarmonyTokenStore.encrypt(JSON.stringify(HarmonyRemoteCrypto.persistedIdentity(identity))));
    await store.flush();
    return identity;
  }

  private async cloudRequest(request: http.HttpRequest, base: string, path: string, token: string, body: string): Promise<string> {
    let response = await request.request(`${base}${path}`, { method: http.RequestMethod.POST, header: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` }, extraData: body, connectTimeout: 8000, readTimeout: 12000 });
    if (response.responseCode < 200 || response.responseCode >= 300) throw new Error(`Cloud 请求失败 (${response.responseCode})`);
    return String(response.result as string);
  }

  private async sendRemoteAgent(input: string): Promise<void> {
    let request = http.createHttp();
    let transport: HarmonyRemoteTransport | null = null;
    try {
      let store = await preferences.getPreferences(getContext(this), 'notemeld-cloud');
      let base = String(await store.get('cloud_url', this.state.cloudURL)).replace(/\/$/, '');
      let encrypted = String(await store.get('cloud_token', ''));
      if (encrypted.length === 0) throw new Error('未登录 Cloud');
      let token = await HarmonyTokenStore.decrypt(encrypted);
      let target = this.state.remoteDevices.find((item: RemoteDevice) => item.online) ?? this.state.remoteDevices[0];
      if (target === undefined) throw new Error('没有已授权的远程设备');
      let installID = await this.loadOrCreateInstallID();
      let controllerID = `harmony-${installID}`;
      let session = JSON.parse(await this.cloudRequest(request, base, '/v1/sessions', token, JSON.stringify({ kind: 'device_remote', title: 'NoteMeld Harmony Remote' }))) as CloudEnvelope;
      let identity = await this.loadOrCreateRemoteIdentity();
      transport = new HarmonyRemoteTransport(session.data.id, controllerID, { id: target.id, publicKey: HarmonyRemoteTransport.decode(target.publicKey), lanEndpoints: target.lanEndpoints }, base, token, identity);
      await transport.connect();
      let result = await transport.send(input, `${Date.now()}-${Math.floor(Math.random() * 100000)}`);
      this.dispatch({ kind: 'addMessage', value: new MobileMessage('assistant', JSON.stringify(result)) });
    } catch (error) {
      this.dispatch({ kind: 'addMessage', value: new MobileMessage('assistant', `远程 Agent 请求失败：${String(error)}`) });
      this.state.connection = ConnectionState.Error;
    } finally { this.state.sending = false; if (transport !== null) await transport.close(); request.destroy(); }
  }

  private async cloudGet(request: http.HttpRequest, base: string, path: string, token: string): Promise<string> {
    let response = await request.request(`${base}${path}`, { method: http.RequestMethod.GET, header: { Authorization: `Bearer ${token}` }, connectTimeout: 8000, readTimeout: 12000 });
    if (response.responseCode < 200 || response.responseCode >= 300) throw new Error(`Cloud 请求失败 (${response.responseCode})`);
    return String(response.result as string);
  }

  build() {
    Column({ space: 12 }) {
      Row() { Button('☰').onClick(() => this.dispatch({ kind: 'toggleDrawer' })); Text('NoteMeld').fontSize(22).layoutWeight(1); Button('设置').onClick(() => this.dispatch({ kind: 'navigate', screen: MobileScreen.Settings })) }.width('100%')
      if (this.state.connection === ConnectionState.Offline) { Text('离线模式：仅可查看已同步内容').fontColor('#c62828') }
      this.page()
      if (this.state.drawerOpen) { this.drawer() }
      if (this.state.sheet !== '') { this.sheet() }
    }.padding(20).width('100%').height('100%')
  }

  @Builder page() {
    if (this.state.screen === MobileScreen.Home) { this.home() }
    else if (this.state.screen === MobileScreen.Session) { this.session() }
    else if (this.state.screen === MobileScreen.Settings) { this.settings() }
    else if (this.state.screen === MobileScreen.Memory) { this.memory() }
    else if (this.state.screen === MobileScreen.FontSize) { this.font() }
    else { this.storagePage() }
  }

  @Builder home() { Column({ space: 16 }) { Text('让 Agent 把想法变成可交付的成果。').fontSize(24); Row({ space: 6 }) { Button(AgentLocation.Local).onClick(() => this.dispatch({ kind: 'setLocation', value: AgentLocation.Local })); Button(AgentLocation.Cloud).onClick(() => this.dispatch({ kind: 'setLocation', value: AgentLocation.Cloud })); Button(AgentLocation.Remote).onClick(() => this.dispatch({ kind: 'setLocation', value: AgentLocation.Remote })) }; Text('继续工作').fontSize(18); if (this.state.tasks.length === 0) { Text('暂无已同步会话').fontColor('#7d879a'); } else { ForEach(this.state.tasks.slice(0, 6), (item: MobileTask) => { this.task(`${item.title} · ${item.status}`, item.id, item.title); }, (item: MobileTask) => item.id); } Button('新建任务').width('100%').onClick(() => this.dispatch({ kind: 'openTask', id: null, value: '新建会话' })) }.width('100%') }
  @Builder task(label: string, id: string = '', title: string = '新建会话') { Button(label).width('100%').onClick(() => this.dispatch({ kind: 'openTask', id, value: title })) }
  @Builder session() { Column({ space: 12 }) { Text(this.state.activeTaskTitle.length > 0 ? this.state.activeTaskTitle : '新建会话').fontSize(22); Text(`${this.state.location === AgentLocation.Local ? '本地' : this.state.location === AgentLocation.Cloud ? '云端' : '远程'} Agent · ${this.state.sending ? '运行中' : '待命'}`).fontColor('#7d879a'); if (this.state.location === AgentLocation.Remote) { Text(this.state.remoteDevices.length > 0 ? `可用远程设备：${this.state.remoteDevices.length}` : '没有已授权的远程设备').fontSize(12).fontColor('#7d879a'); } this.permissionButton(); Scroll() { Column({ space: 12 }) { ForEach(this.state.messages, (message: MobileMessage) => { Text(message.content).padding(16).backgroundColor(message.role === 'user' ? '#e8efff' : '#f1f3f8'); }) }.width('100%') }.layoutWeight(1); if (this.state.attachments.length > 0) { Text(`附件：${this.state.attachments.join('、')}`).fontSize(12).fontColor('#7d879a'); } TextInput({ placeholder: '继续告诉 Agent 你要完成什么…', text: this.state.inputText }).onChange((value: string) => this.dispatch({ kind: 'setInputText', value })); Row({ space: 8 }) { Button('⋯').onClick(() => this.dispatch({ kind: 'openSheet', name: 'actions' })); Button('添加文件').onClick(() => this.startAttachmentPicker()); Button('全部产物').onClick(() => this.dispatch({ kind: 'openSheet', name: 'products' })); Button(this.state.selectedModel).onClick(() => this.dispatch({ kind: 'openSheet', name: 'model' })); Button(this.state.sending ? '发送中…' : '发送').enabled(this.state.connection !== ConnectionState.Offline && !this.state.sending && this.state.inputText.trim().length > 0).onClick(() => { let input = this.state.inputText.trim(); this.dispatch({ kind: 'addMessage', value: new MobileMessage('user', input) }); this.dispatch({ kind: 'setInputText', value: '' }); this.dispatch({ kind: 'setSending', value: true }); if (this.state.location === AgentLocation.Local) this.sendAgent(input); else if (this.state.location === AgentLocation.Cloud) this.sendCloudAgent(input); else this.sendRemoteAgent(input); }) } }.width('100%').layoutWeight(1) }
  @Builder permissionButton() { Button('确认本次 Agent 文件与工具权限').onClick(() => this.dispatch({ kind: 'setPermission', value: true })) }
  @Builder settings() {
    Scroll() {
      Column({ space: 4 }) {
        Text('设置').fontSize(24)
        this.setting('记忆库', `${this.state.memories.length} 个条目`, MobileScreen.Memory)
        this.setting('语言', this.state.language, null)
        this.setting('字体大小', `${this.state.fontSize}px`, MobileScreen.FontSize)
        Row() {
          Text('消息通知设置').layoutWeight(1)
          Toggle({ type: ToggleType.Switch, isOn: this.state.notificationsEnabled }).onChange((value: boolean) => this.dispatch({ kind: 'setNotifications', value }))
        }.width('100%')
        this.setting('存储空间', `${this.totalStorage().toFixed(2)} MB`, MobileScreen.Storage)
        Text('Cloud 连接').fontSize(20)
        TextInput({ placeholder: 'Cloud 地址', text: this.state.cloudURL }).onChange((value: string) => this.dispatch({ kind: 'setCloudURL', value }))
        TextInput({ placeholder: '用户名', text: this.state.cloudUsername }).onChange((value: string) => this.dispatch({ kind: 'setCloudUsername', value }))
        TextInput({ placeholder: '密码', text: this.state.cloudPassword }).type(InputType.Password).onChange((value: string) => this.dispatch({ kind: 'setCloudPassword', value }))
        Row() {
          Text(this.state.cloudStatus).fontSize(12).layoutWeight(1)
          Button('登录并同步').onClick(() => this.loginCloud())
        }.width('100%')
      }.width('100%')
    }.width('100%').layoutWeight(1)
  }
  @Builder setting(label: string, detail: string, screen: MobileScreen | null) { Button(`${label} · ${detail}`).width('100%').onClick(() => screen === null ? this.dispatch({ kind: 'openSheet', name: 'language' }) : this.dispatch({ kind: 'navigate', screen })) }
  @Builder memory() { Column({ space: 10 }) { Text('记忆库').fontSize(24); ForEach(this.state.memories, (item: string) => { Text(item).width('100%').padding(14).backgroundColor('#f1f3f8') }); TextInput({ placeholder: '告诉 NoteMeld 要记住或忘记什么…', text: this.state.memoryDraft }).onChange((value: string) => this.dispatch({ kind: 'setMemoryDraft', value })); Button('添加我的记忆').onClick(() => this.saveMemory()) }.width('100%') }
  @Builder font() { Column({ space: 16 }) { Text('字体大小').fontSize(24); Text(`NoteMeld Agent\n字号预览：${this.state.fontSize}px`).fontSize(this.state.fontSize); Row() { Text('跟随系统').layoutWeight(1); Toggle({ type: ToggleType.Switch, isOn: this.state.followSystemFont }).onChange((value: boolean) => this.dispatch({ kind: 'setFollowSystemFont', value })) }; Slider({ value: this.state.fontSize, min: 13, max: 19, step: 1 }).onChange((value: number) => this.dispatch({ kind: 'setFontSize', value: Math.round(value) })); Button('确认保存') }.width('100%') }
  @Builder storagePage() { Column({ space: 10 }) { Text('存储空间').fontSize(24); Text(`NoteMeld 占用空间：${this.totalStorage().toFixed(2)} MB`); Button('全部清除').fontColor('#c62828').onClick(() => this.dispatch({ kind: 'clearStorage', id: null })); ForEach(this.state.storage, (item: StorageItem) => { Row() { Column() { Text(item.title); Text(item.detail).fontSize(12).fontColor('#7d879a') }.layoutWeight(1); Text(`${item.sizeMb} MB`); Button('清除').onClick(() => this.dispatch({ kind: 'clearStorage', id: item.id })) }.width('100%').padding(12) }) }.width('100%') }
  @Builder drawer() { Column({ space: 10 }) { Text('任务').fontSize(20); if (this.state.tasks.length === 0) { Text('暂无已同步会话').fontColor('#7d879a'); } else { ForEach(this.state.tasks.slice(0, 8), (item: MobileTask) => { this.task(`${item.title} · ${item.status}`, item.title); }, (item: MobileTask) => item.id); } Button('关闭菜单').onClick(() => this.dispatch({ kind: 'closeOverlay' })) }.width('100%').padding(16).backgroundColor('#ffffff') }
  @Builder sheet() { Column({ space: 8 }) { Text(this.state.sheet === 'model' ? '选择模型' : this.state.sheet === 'products' ? '当前会话产物' : this.state.sheet === 'actions' ? '会话操作' : '选择语言').fontSize(20); if (this.state.sheet === 'model') { ForEach(['Auto', 'Hy4 preview', 'Hy3', 'GLM-5.3', 'Kimi-K3'], (item: string) => { Button(item).width('100%').onClick(() => this.dispatch({ kind: 'selectModel', value: item })) }) } else if (this.state.sheet === 'products') { Text('当前会话暂无可下载产物').fontColor('#7d879a'); Button('关闭').onClick(() => this.dispatch({ kind: 'closeOverlay' })) } else if (this.state.sheet === 'actions') { Button('全部产物').onClick(() => this.dispatch({ kind: 'openSheet', name: 'products' })); Button('删除对话').onClick(() => this.deleteConversation()).enabled(this.state.activeTaskId.length > 0) } else { ForEach(['跟随系统', '简体中文', '繁體中文', 'English'], (item: string) => { Button(item).width('100%').onClick(() => this.dispatch({ kind: 'setLanguage', value: item })) }) } }.width('100%').padding(16).backgroundColor('#ffffff') }

  private totalStorage(): number { return this.state.storage.reduce((total: number, item: StorageItem) => total + item.sizeMb, 0) }
  private dispatch(action: MobileSurfaceAction): void {
    this.state = reduceMobileSurface(this.state, action);
    if (action.kind === 'clearStorage') { this.clearStorageFiles(action.id ?? null); }
    this.persistLocalState();
  }
}

class AgentData { id: string = ''; turn_id: string = '' }
class StorageRoots { cache: string = ''; cloud: string = ''; local: string = ''; artifacts: string = '' }
class AgentEnvelope { data: AgentData = new AgentData() }
class CloudData { token: string = ''; id: string = '' }
class CloudEnvelope { data: CloudData = new CloudData() }
class CloudEventPayload { output: string = ''; status: string = '' }
class CloudEvent { sequence: number = 0; event_type: string = ''; payload: CloudEventPayload = new CloudEventPayload() }
class CloudEventsEnvelope { data: CloudEvent[] = [] }
class CloudAttachment { name: string = ''; size: number = 0; type: string = ''; content_base64: string = '' }

class HarmonyTokenStore {
  private static alias: string = 'notemeld.cloud.token.v1';

  static async encrypt(value: string): Promise<string> {
    await HarmonyTokenStore.ensureKey();
    let nonce = new Uint8Array(12);
    for (let index = 0; index < nonce.length; index += 1) nonce[index] = Math.floor(Math.random() * 256);
    let options: huks.HuksOptions = { properties: HarmonyTokenStore.properties(huks.HuksKeyPurpose.HUKS_KEY_PURPOSE_ENCRYPT, nonce) };
    let handle = await huks.initSession(HarmonyTokenStore.alias, options);
    let update = await huks.updateSession(handle.handle, { inData: new Uint8Array(value.split('').map((item: string) => item.charCodeAt(0))) });
    let finish = await huks.finishSession(handle.handle, {});
    let cipher = HarmonyTokenStore.join(update.outData, finish.outData);
    return JSON.stringify({ nonce: Array.from(nonce), cipher: Array.from(cipher) });
  }

  static async decrypt(serialized: string): Promise<string> {
    await HarmonyTokenStore.ensureKey();
    let parsed = JSON.parse(serialized) as ProtectedToken;
    let nonce = new Uint8Array(parsed.nonce);
    let options: huks.HuksOptions = { properties: HarmonyTokenStore.properties(huks.HuksKeyPurpose.HUKS_KEY_PURPOSE_DECRYPT, nonce) };
    let handle = await huks.initSession(HarmonyTokenStore.alias, options);
    let update = await huks.updateSession(handle.handle, { inData: new Uint8Array(parsed.cipher) });
    let finish = await huks.finishSession(handle.handle, {});
    let plain = HarmonyTokenStore.join(update.outData, finish.outData);
    return String.fromCharCode(...Array.from(plain));
  }

  private static async ensureKey(): Promise<void> {
    let exists = await huks.isKeyExist(HarmonyTokenStore.alias, {});
    if (!exists) {
      await huks.generateKey(HarmonyTokenStore.alias, { properties: [
        { tag: huks.HuksTag.HUKS_TAG_ALGORITHM, value: huks.HuksKeyAlg.HUKS_ALG_AES },
        { tag: huks.HuksTag.HUKS_TAG_PURPOSE, value: huks.HuksKeyPurpose.HUKS_KEY_PURPOSE_ENCRYPT | huks.HuksKeyPurpose.HUKS_KEY_PURPOSE_DECRYPT },
        { tag: huks.HuksTag.HUKS_TAG_KEY_SIZE, value: huks.HuksKeySize.HUKS_AES_KEY_SIZE_256 },
        { tag: huks.HuksTag.HUKS_TAG_BLOCK_MODE, value: huks.HuksCipherMode.HUKS_MODE_GCM },
        { tag: huks.HuksTag.HUKS_TAG_NO_AUTH_REQUIRED, value: true }
      ] });
    }
  }

  private static properties(purpose: huks.HuksKeyPurpose, nonce: Uint8Array): Array<huks.HuksParam> {
    return [
      { tag: huks.HuksTag.HUKS_TAG_ALGORITHM, value: huks.HuksKeyAlg.HUKS_ALG_AES },
      { tag: huks.HuksTag.HUKS_TAG_PURPOSE, value: purpose },
      { tag: huks.HuksTag.HUKS_TAG_BLOCK_MODE, value: huks.HuksCipherMode.HUKS_MODE_GCM },
      { tag: huks.HuksTag.HUKS_TAG_NONCE, value: nonce }
    ];
  }

  private static join(first: Uint8Array | undefined, second: Uint8Array | undefined): Uint8Array {
    let left = first ?? new Uint8Array(0);
    let right = second ?? new Uint8Array(0);
    let result = new Uint8Array(left.length + right.length);
    result.set(left, 0); result.set(right, left.length); return result;
  }
}

class ProtectedToken {
  nonce: Array<number> = []
  cipher: Array<number> = []
}
