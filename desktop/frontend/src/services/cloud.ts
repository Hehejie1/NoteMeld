import axios, { AxiosInstance, type AxiosRequestConfig } from 'axios'
import { validateCloudBaseUrl } from './connectionStrategy'

export interface CloudEnvelope<T> {
  code: number
  msg: string
  data: T
}
export interface CloudCapabilities {
  protocol_version: string
  protocol?: { name: string; current: number; min: number; max: number }
  runtime?: { sdk_version: string; abi: number; schema: number }
  required_features?: string[]
  canonical_session_prefix: string
  device_proof_required: boolean
  e2ee_relay_envelope: boolean
  relay_persists_payload: boolean
  relay_backend?: string
  relay_multi_worker?: boolean
  lan_first_candidates?: boolean
  worker_count?: number
  max_request_bytes: number
  relay_max_frame_bytes?: number
  device_token_max_ttl_seconds?: number
  event_page_limit?: number
  max_workspace_bytes: number
  max_workspace_files: number
  features: Record<string, boolean>
}
export interface CloudConfigSyncItem {
  kind: string
  key: string
  value: unknown
  revision?: number
}
export interface CloudConfigSyncDeletion {
  kind: string
  key: string
  revision: number
}
export interface CloudConfigSyncSnapshot {
  workspace_id?: string
  revision: number
  full: boolean
  items: CloudConfigSyncItem[]
  deleted: CloudConfigSyncDeletion[]
  next_cursor?: number | null
  server_time: string
}
export interface CloudConfigSyncChange {
  kind: string
  key: string
  operation: 'set' | 'delete'
  value?: unknown
}
export interface CloudSession {
  id: string
  kind: 'cloud_native' | 'device_remote'
  title?: string
  workspace_id: string
  model_id?: string | null
  status?: string
}
export interface CloudEvent {
  sequence: number
  event_type: string
  payload: unknown
  created_at: number
}
export interface CloudUser {
  id: string
  username: string
  role: 'admin' | 'user'
  disabled: boolean
  created_at: number
}
export interface CloudAccessRequest {
  id: string
  email: string
  display_name: string
  reason: string
  status: 'pending' | 'approved' | 'rejected' | 'expired'
  reviewed_by?: string | null
  reviewed_at?: number | null
  created_at: number
  expires_at?: number | null
}
export interface CloudDevice {
  id: string
  platform: string
  display_name: string
  online: boolean
  public_key?: string | null
  last_seen_at?: number | null
  connectivity?: { lan_endpoints?: string[]; permissions?: CloudDevicePermissions }
}
export interface CloudDevicePermissions {
  workspace_read: boolean
  remote_execute: boolean
  session_read: boolean
  artifact_download: boolean
  approval_required: boolean
}
export interface CloudGrant {
  id: string
  controller_device_id: string
  host_device_id: string
  role: string
  scopes: string[]
  workspace_refs: string[]
  expires_at?: number | null
  revoked_at?: number | null
  created_at: number
}
export interface CloudModel {
  id: string
  name: string
  provider: string
  model: string
  base_url?: string | null
  enabled: boolean
  is_default: boolean
  has_api_key: boolean
  credential_status?: 'not_configured' | 'configured' | 'unavailable' | 'unreadable'
}
// notemeld.model-add.v1 两级目录（Provider → Model）
export type CloudProtocol = 'openai-compatible' | 'anthropic-messages' | 'ollama'
export interface CatalogModel {
  id: string
  organization_id: string | null
  provider_id: string | null
  model_id: string
  display_name: string
  context_window: number
  modalities: string
  enabled: boolean
  is_default: boolean
  test_status: 'unknown' | 'testing' | 'ok' | 'failed'
  created_at: number
  updated_at: number
}
export interface CatalogProvider {
  id: string
  organization_id: string | null
  display_name: string
  vendor_id: string
  protocol: CloudProtocol
  base_url: string
  auth_type: 'bearer' | 'x-api-key' | 'none'
  has_api_key: boolean
  api_key_masked?: string | null
  created_by?: string
  created_at: number
  updated_at: number
  models?: CatalogModel[]
}
export interface CatalogDiscoveredModel {
  id: string
  name: string
  context_window?: number
}
export interface CatalogConnectionResult {
  ok: boolean
  status: 'ok' | 'failed'
  message: string
}
export interface CloudWorkspace {
  id: string
  bytes_used?: number
  quota_bytes?: number
  quota_percent?: number
  file_count?: number
}
export interface CloudAttachment {
  name: string
  size: number
  type: string
  content_base64?: string
}
export interface CloudToken {
  id: string
  audience: string
  device_id?: string | null
  scopes: string[]
  expires_at?: number | null
  revoked_at?: number | null
  created_at: number
}
export interface CloudTokenStore {
  load(): Promise<string | null>
  save(token: string): Promise<void>
  clear(): Promise<void>
}
export interface CloudOrganizationMemory {
  id: string
  organization_id: string
  content: string
  source: string
  created_at: number
  updated_at: number
}
export interface CloudDashboard {
  session_count: number
  running_count: number
  pending_approval_count: number
  failed_count: number
  device_count: number
  storage_total: number
  daily_agent_conversations: number
  total_tokens: number
  recent_activity: Array<Record<string, unknown>>
  workspaces: Array<{ id: string; sessions: number; display_name: string }>
}

export class CloudClientError extends Error {
  constructor(
    message: string,
    readonly statusCode = 0
  ) {
    super(message)
    this.name = 'CloudClientError'
  }
}

function formatCloudErrorDetail(detail: unknown): string | undefined {
  if (typeof detail === 'string' && detail.trim()) return detail
  if (Array.isArray(detail)) {
    const messages = detail
      .map(item => {
        if (typeof item === 'string') return item
        if (item && typeof item === 'object') {
          const record = item as Record<string, unknown>
          if (typeof record.msg === 'string') return record.msg
          if (typeof record.message === 'string') return record.message
        }
        return undefined
      })
      .filter((item): item is string => Boolean(item))
    if (messages.length) return messages.join('；')
  }
  if (detail && typeof detail === 'object') {
    const record = detail as Record<string, unknown>
    if (typeof record.msg === 'string' && record.msg.trim()) return record.msg
    if (typeof record.message === 'string' && record.message.trim()) return record.message
  }
  return undefined
}

/** Stateless adapter for cloud control-plane APIs; no local Agent state lives here. */
export class CloudClient {
  private readonly http: AxiosInstance
  private token: string | null
  private tokenHydrated = false

  private readonly tokenStore?: CloudTokenStore

  constructor(baseUrl: string, token?: string, deviceId?: string, tokenStore?: CloudTokenStore) {
    this.token = token ?? null
    this.tokenStore = tokenStore
    this.http = axios.create({
      baseURL: validateCloudBaseUrl(baseUrl).toString().replace(/\/$/, ''),
      timeout: 20_000,
    })
    if (deviceId) this.http.defaults.headers.common['X-Device-Id'] = deviceId
  }

  setToken(token: string | null) {
    this.token = token
  }

  /** Read the in-memory token when replacing the client after storage bootstrap. */
  getToken() {
    return this.token
  }

  async persistCurrentToken() {
    await this.persistToken()
  }

  /** Bind the browser/device identity only after the cloud has accepted registration. */
  setDeviceId(deviceId?: string) {
    if (deviceId) this.http.defaults.headers.common['X-Device-Id'] = deviceId
    else delete this.http.defaults.headers.common['X-Device-Id']
  }
  async getAccessToken(): Promise<string | null> {
    await this.hydrateToken()
    return this.token
  }
  async clearToken() {
    this.token = null
    await this.persistToken()
  }
  async hydrateToken() {
    if (!this.tokenHydrated) {
      this.tokenHydrated = true
      if (this.token === null && this.tokenStore) this.token = await this.tokenStore.load()
    }
    return this.token
  }
  private async persistToken() {
    if (!this.tokenStore) return
    if (this.token) await this.tokenStore.save(this.token)
    else await this.tokenStore.clear()
  }

  private async request<T>(
    method: string,
    path: string,
    data?: unknown,
    config?: AxiosRequestConfig
  ): Promise<T> {
    await this.hydrateToken()
    try {
      const response = await this.http.request<CloudEnvelope<T>>({
        method,
        url: path,
        data,
        headers: this.token ? { Authorization: `Bearer ${this.token}` } : undefined,
        ...config,
      })
      if (
        !response.data ||
        typeof response.data !== 'object' ||
        typeof response.data.code !== 'number'
      ) {
        throw new CloudClientError('cloud returned invalid response envelope', response.status)
      }
      if (response.data.code !== 0)
        throw new CloudClientError(response.data.msg || 'cloud request failed', response.status)
      return response.data.data
    } catch (error) {
      if (error instanceof CloudClientError) throw error
      if (axios.isAxiosError(error)) {
        const payload = error.response?.data as
          | (Partial<CloudEnvelope<unknown>> & { detail?: string })
          | undefined
        throw new CloudClientError(
          payload?.msg || formatCloudErrorDetail(payload?.detail) || `云端请求失败（HTTP ${error.response?.status ?? 0}）`,
          error.response?.status ?? 0
        )
      }
      const message = error instanceof Error ? error.message : String(error)
      throw new CloudClientError(
        message && message !== '[object Object]' ? `云端传输失败：${message}` : '云端传输失败'
      )
    }
  }

  async login(password: string, username?: string, accountId?: string) {
    const data = await this.request<{ token: string; user_id: string; role: string }>(
      'POST',
      '/v1/auth/login',
      {
        password,
        ...(username ? { username } : {}),
        ...(accountId ? { account_id: accountId } : {}),
      }
    )
    this.token = data.token
    await this.persistToken()
    try {
      await this.verifyCapabilities()
    } catch (error) {
      this.token = null
      await this.persistToken()
      throw error
    }
    return data
  }
  async sendLoginCode(email: string) {
    return this.request<{ email: string; purpose: string; dev_code?: string }>(
      'POST',
      '/v1/auth/code/send',
      { email, purpose: 'login' }
    )
  }
  async sendPasswordResetCode(email: string) {
    return this.request<{ email: string; purpose: string; dev_code?: string }>(
      'POST',
      '/v1/auth/code/send',
      { email, purpose: 'password_reset' }
    )
  }
  resetPassword(email: string, code: string, password: string) {
    return this.request<{ email: string; password_reset: boolean }>(
      'POST',
      '/v1/auth/password/reset',
      { email, code, password }
    )
  }
  async loginWithCode(email: string, code: string) {
    const data = await this.request<{ token: string; user_id: string; role: string }>(
      'POST',
      '/v1/auth/login/code',
      { email, code }
    )
    this.token = data.token
    await this.persistToken()
    try {
      await this.verifyCapabilities()
    } catch (error) {
      this.token = null
      await this.persistToken()
      throw error
    }
    return data
  }
  requestAccess(
    email: string,
    displayName: string,
    password: string,
    confirmPassword: string,
    reason: string
  ) {
    return this.request<{ id: string; email: string; status: string }>(
      'POST',
      '/v1/access-requests',
      { email, display_name: displayName, password, confirm_password: confirmPassword, reason }
    )
  }
  acceptInvitation(token: string, displayName: string, password: string) {
    return this.request<{ user_id: string; username: string; email: string }>(
      'POST',
      `/v1/invitations/${encodeURIComponent(token)}/accept`,
      { display_name: displayName, password }
    )
  }
  async rotateToken() {
    const data = await this.request<{ token: string; jti: string; expires_at?: number | null }>(
      'POST',
      '/v1/auth/rotate'
    )
    this.token = data.token
    await this.persistToken()
    return data
  }
  async revokeCurrentToken() {
    const data = await this.request<Record<string, unknown>>('POST', '/v1/auth/revoke')
    this.token = null
    await this.persistToken()
    return data
  }
  me() {
    return this.request<{
      user_id: string
      username: string
      email?: string | null
      display_name?: string | null
      avatar?: string | null
      role: string
      audience: string
      device_id?: string | null
      scopes: string[]
      expires_at?: number | null
      organization_id?: string | null
      organization_role?: 'owner' | 'admin' | 'member' | null
    }>('GET', '/v1/auth/me')
  }
  updateProfile(changes: { display_name?: string; avatar?: string; password?: string }) {
    return this.request<{
      display_name?: string
      avatar?: string
      password_changed?: boolean
    }>('PUT', '/v1/auth/me', changes)
  }
  listTokens() {
    return this.request<CloudToken[]>('GET', '/v1/auth/tokens')
  }
  createToken(scopes: string[] = ['*'], expiresAt?: number) {
    return this.request<{
      token: string
      jti: string
      scopes: string[]
      expires_at?: number | null
    }>('POST', '/v1/auth/tokens', {
      scopes,
      ...(expiresAt === undefined ? {} : { expires_at: expiresAt }),
    })
  }
  revokeToken(tokenId: string) {
    return this.request<Record<string, unknown>>(
      'POST',
      `/v1/auth/tokens/${encodeURIComponent(tokenId)}/revoke`
    )
  }
  listUsers() {
    return this.request<CloudUser[]>('GET', '/v1/admin/users')
  }
  listAccessRequests(status?: CloudAccessRequest['status']) {
    return this.request<CloudAccessRequest[]>(
      'GET',
      '/v1/admin/access-requests',
      undefined,
      status ? { params: { status } } : undefined
    )
  }
  reviewAccessRequest(requestId: string, status: 'approved' | 'rejected') {
    return this.request<Record<string, unknown>>(
      'POST',
      `/v1/admin/access-requests/${encodeURIComponent(requestId)}/review`,
      { status }
    )
  }
  createUser(username: string, password: string) {
    return this.request<{ id: string; username: string }>('POST', '/v1/admin/users', {
      username,
      password,
    })
  }
  updateUser(
    userId: string,
    changes: { username?: string; password?: string; disabled?: boolean }
  ) {
    return this.request<Record<string, unknown>>(
      'PUT',
      `/v1/admin/users/${encodeURIComponent(userId)}`,
      changes
    )
  }
  deleteUser(userId: string) {
    return this.request<Record<string, unknown>>(
      'DELETE',
      `/v1/admin/users/${encodeURIComponent(userId)}`
    )
  }
  listAudits(limit = 100) {
    return this.request<unknown[]>('GET', '/v1/admin/audits', undefined, { params: { limit } })
  }
  listOrganizationMemories() {
    return this.request<CloudOrganizationMemory[]>('GET', '/v1/admin/organization/memories')
  }
  createOrganizationMemory(content: string, source = 'admin') {
    return this.request<CloudOrganizationMemory>('POST', '/v1/admin/organization/memories', {
      content,
      source,
    })
  }
  deleteOrganizationMemory(memoryId: string) {
    return this.request<Record<string, unknown>>(
      'DELETE',
      `/v1/admin/organization/memories/${encodeURIComponent(memoryId)}`
    )
  }
  capabilities() {
    return this.request<CloudCapabilities>('GET', '/v1/capabilities')
  }
  async verifyCapabilities() {
    const data = await this.capabilities()
    const protocol = data.protocol
    const runtime = data.runtime
    if (
      !protocol ||
      protocol.name !== 'notemeld.sync' ||
      protocol.current !== 1 ||
      protocol.min > 1 ||
      protocol.max < 1
    )
      throw new CloudClientError('cloud protocol is incompatible', 409)
    if (!runtime || runtime.sdk_version !== '0.1.0' || runtime.abi !== 1 || runtime.schema !== 1)
      throw new CloudClientError('cloud Agent runtime is incompatible', 409)
    const supported = new Set(['config_sync_v1', 'e2ee_relay_v1', 'durable_receipt_v1'])
    if ((data.required_features ?? []).some(feature => !supported.has(feature)))
      throw new CloudClientError('cloud requires unsupported capabilities', 409)
    return data
  }
  configSyncSnapshot(workspaceId = 'default', afterRevision = 0) {
    if (!workspaceId || !Number.isSafeInteger(afterRevision) || afterRevision < 0)
      throw new Error('invalid config sync cursor')
    return this.request<CloudConfigSyncSnapshot>('GET', '/v1/config-sync/snapshot', undefined, {
      params: { workspace_id: workspaceId, after_revision: afterRevision },
    })
  }
  configSyncChanges(
    workspaceId: string,
    baseRevision: number,
    idempotencyKey: string,
    changes: CloudConfigSyncChange[]
  ) {
    if (
      !workspaceId ||
      !Number.isSafeInteger(baseRevision) ||
      baseRevision < 0 ||
      !idempotencyKey ||
      !changes.length ||
      changes.some(
        change => !change.kind || !change.key || !['set', 'delete'].includes(change.operation)
      )
    )
      throw new Error('invalid config sync change request')
    return this.request<CloudConfigSyncSnapshot>('POST', '/v1/config-sync/changes', {
      workspace_id: workspaceId,
      base_revision: baseRevision,
      idempotency_key: idempotencyKey,
      changes,
    })
  }
  dashboard() {
    return this.request<CloudDashboard>('GET', '/v1/cloud/dashboard')
  }
  usage(days = 7) {
    return this.request<{
      days: Array<{ date: string; conversations: number; total_tokens: number }>
      total_tokens: number
    }>('GET', '/v1/cloud/usage', undefined, { params: { days } })
  }
  listModels() {
    return this.request<CloudModel[]>('GET', '/v1/models')
  }
  discoverModels(payload: { provider: string; base_url: string; api_key?: string }) {
    return this.request<Array<{ id: string; model: string; name: string }>>(
      'POST',
      '/v1/models/discover',
      payload
    )
  }
  createModel(payload: {
    name: string
    provider: string
    model: string
    base_url?: string
    api_key?: string
    enabled?: boolean
    is_default?: boolean
  }) {
    return this.request<Record<string, unknown>>('POST', '/v1/models', payload)
  }
  updateModel(modelId: string, changes: Record<string, unknown>) {
    return this.request<Record<string, unknown>>(
      'PUT',
      `/v1/models/${encodeURIComponent(modelId)}`,
      changes
    )
  }
  deleteModel(modelId: string) {
    return this.request<Record<string, unknown>>(
      'DELETE',
      `/v1/models/${encodeURIComponent(modelId)}`
    )
  }
  // ---- notemeld.model-add.v1 两级目录 ----
  listCatalogProviders() {
    return this.request<CatalogProvider[]>('GET', '/v1/catalog/providers')
  }
  createCatalogProvider(payload: {
    display_name: string
    vendor_id?: string
    protocol: CloudProtocol
    base_url: string
    auth_type?: 'bearer' | 'x-api-key' | 'none'
    api_key?: string | null
  }) {
    return this.request<CatalogProvider>('POST', '/v1/catalog/providers', payload)
  }
  updateCatalogProvider(
    providerId: string,
    changes: {
      display_name?: string
      vendor_id?: string
      protocol?: CloudProtocol
      base_url?: string
      auth_type?: 'bearer' | 'x-api-key' | 'none'
      api_key?: string | null
    }
  ) {
    return this.request<CatalogProvider>(
      'PATCH',
      `/v1/catalog/providers/${encodeURIComponent(providerId)}`,
      changes
    )
  }
  deleteCatalogProvider(providerId: string) {
    return this.request<{ id: string; deleted: boolean }>(
      'DELETE',
      `/v1/catalog/providers/${encodeURIComponent(providerId)}`
    )
  }
  saveCatalogModelsBatch(
    providerId: string,
    models: Array<{
      model_id: string
      display_name?: string | null
      context_window?: number
      modalities?: string
      enabled?: boolean
      is_default?: boolean
    }>
  ) {
    return this.request<CatalogModel[]>(
      'POST',
      `/v1/catalog/providers/${encodeURIComponent(providerId)}/models/batch`,
      { models }
    )
  }
  updateCatalogModel(
    modelRowId: string,
    changes: {
      display_name?: string
      context_window?: number
      modalities?: string
      enabled?: boolean
      is_default?: boolean
      test_status?: 'unknown' | 'testing' | 'ok' | 'failed'
    }
  ) {
    return this.request<CatalogModel>(
      'PATCH',
      `/v1/catalog/models/${encodeURIComponent(modelRowId)}`,
      changes
    )
  }
  deleteCatalogModel(modelRowId: string) {
    return this.request<{ id: string; deleted: boolean }>(
      'DELETE',
      `/v1/catalog/models/${encodeURIComponent(modelRowId)}`
    )
  }
  setCatalogDefaultModel(modelRowId: string) {
    return this.request<CatalogModel>(
      'POST',
      `/v1/catalog/models/${encodeURIComponent(modelRowId)}/default`
    )
  }
  discoverCatalogModels(payload: {
    protocol: CloudProtocol
    base_url: string
    api_key?: string | null
  }) {
    return this.request<CatalogDiscoveredModel[]>(
      'POST',
      '/v1/catalog/discover',
      payload
    )
  }
  testCatalogConnection(payload: {
    protocol: CloudProtocol
    base_url: string
    api_key?: string | null
    model_id?: string | null
  }) {
    return this.request<CatalogConnectionResult>(
      'POST',
      '/v1/catalog/test-connection',
      payload
    )
  }
  listDevices() {
    return this.request<CloudDevice[]>('GET', '/v1/devices')
  }
  registerDevice(
    deviceId: string,
    platform: string,
    displayName: string,
    publicKey?: string,
    lanEndpoints: string[] = []
  ) {
    return this.request<Record<string, unknown>>('POST', '/v1/devices/register', {
      device_id: deviceId,
      platform,
      display_name: displayName,
      public_key: publicKey,
      lan_endpoints: lanEndpoints,
    })
  }
  revokeDevice(deviceId: string) {
    return this.request<Record<string, unknown>>(
      'DELETE',
      `/v1/devices/${encodeURIComponent(deviceId)}`
    )
  }
  getDevicePermissions(deviceId: string) {
    return this.request<CloudDevicePermissions>('GET', `/v1/devices/${encodeURIComponent(deviceId)}/permissions`)
  }
  updateDevicePermissions(deviceId: string, permissions: CloudDevicePermissions) {
    return this.request<CloudDevicePermissions>('PUT', `/v1/devices/${encodeURIComponent(deviceId)}/permissions`, permissions)
  }
  rotateDeviceKey(deviceId: string, publicKey: string) {
    return this.request<Record<string, unknown>>(
      'POST',
      `/v1/devices/${encodeURIComponent(deviceId)}/rotate-key`,
      { public_key: publicKey }
    )
  }
  heartbeat(deviceId: string, lanEndpoints?: string[]) {
    return this.request<Record<string, unknown>>(
      'POST',
      `/v1/devices/${encodeURIComponent(deviceId)}/heartbeat`,
      lanEndpoints === undefined ? undefined : { lan_endpoints: lanEndpoints }
    )
  }
  requestDeviceChallenge(deviceId: string) {
    return this.request<{ challenge: string; expires_at: number }>(
      'POST',
      `/v1/devices/${encodeURIComponent(deviceId)}/challenge`
    )
  }
  verifyDeviceChallenge(deviceId: string, challenge: string, signature: string) {
    return this.request<Record<string, unknown>>(
      'POST',
      `/v1/devices/${encodeURIComponent(deviceId)}/challenge/verify`,
      { challenge, signature }
    )
  }
  async createDeviceToken(
    deviceId: string,
    scopes?: string[],
    expiresInSeconds = 86_400,
    revokeSourceToken = true,
    adoptToken = true
  ) {
    const data = await this.request<{
      token: string
      jti: string
      device_id: string
      audience: 'device-api'
      scopes: string[]
      expires_at: number
      source_token_revoked: boolean
    }>('POST', `/v1/devices/${encodeURIComponent(deviceId)}/token`, {
      ...(scopes ? { scopes } : {}),
      expires_in_seconds: expiresInSeconds,
      revoke_source_token: revokeSourceToken,
    })
    if (adoptToken) {
      this.token = data.token
      await this.persistToken()
    }
    return data
  }
  startPairing() {
    return this.request<{ code: string; expires_at: number }>('POST', '/v1/pairings/start')
  }
  confirmPairing(
    code: string,
    deviceId: string,
    platform: string,
    displayName: string,
    publicKey?: string
  ) {
    return this.request<Record<string, unknown>>('POST', '/v1/pairings/confirm', {
      code,
      device_id: deviceId,
      platform,
      display_name: displayName,
      public_key: publicKey,
    })
  }
  listGrants() {
    return this.request<CloudGrant[]>('GET', '/v1/grants')
  }
  createGrant(
    controllerDeviceId: string,
    hostDeviceId: string,
    scopes?: string[],
    workspaceRefs?: string[]
  ) {
    return this.request<Record<string, unknown>>('POST', '/v1/grants', {
      controller_device_id: controllerDeviceId,
      host_device_id: hostDeviceId,
      ...(scopes ? { scopes } : {}),
      ...(workspaceRefs ? { workspace_refs: workspaceRefs } : {}),
    })
  }
  revokeGrant(grantId: string) {
    return this.request<Record<string, unknown>>(
      'DELETE',
      `/v1/grants/${encodeURIComponent(grantId)}`
    )
  }
  listShareTokens(sessionId?: string) {
    return this.request<unknown[]>(
      'GET',
      '/v1/share-tokens',
      undefined,
      sessionId === undefined ? undefined : { params: { session_id: sessionId } }
    )
  }
  createShareToken(
    sessionId: string,
    role = 'viewer',
    scopes: string[] = ['event.receive'],
    expiresAt?: number
  ) {
    return this.request<{ token: string; id: string; expires_at?: number | null }>(
      'POST',
      '/v1/share-tokens',
      {
        session_id: sessionId,
        role,
        scopes,
        ...(expiresAt === undefined ? {} : { expires_at: expiresAt }),
      }
    )
  }
  revokeShareToken(tokenId: string) {
    return this.request<Record<string, unknown>>(
      'POST',
      `/v1/share-tokens/${encodeURIComponent(tokenId)}/revoke`
    )
  }
  sharedSnapshot(sessionId: string, shareToken: string, limit = 500) {
    return this.request<Record<string, unknown>>(
      'GET',
      `/v1/shared/${encodeURIComponent(sessionId)}/snapshot`,
      undefined,
      { params: { limit }, headers: { 'X-Share-Token': shareToken } }
    )
  }
  async sharedEvents(
    sessionId: string,
    shareToken: string,
    after = 0,
    limit = 500
  ): Promise<CloudEvent[]> {
    if (!Number.isSafeInteger(after) || after < 0) throw new Error('after must be non-negative')
    const events = await this.request<unknown[]>(
      'GET',
      `/v1/shared/${encodeURIComponent(sessionId)}/events`,
      undefined,
      { params: { after, limit }, headers: { 'X-Share-Token': shareToken } }
    )
    return this.validateEventPage(events, after)
  }
  sharedCommand(sessionId: string, shareToken: string, requestId: string, input: string) {
    return this.request<Record<string, unknown>>(
      'POST',
      `/v1/shared/${encodeURIComponent(sessionId)}/commands`,
      { request_id: requestId, input },
      { headers: { 'X-Share-Token': shareToken } }
    )
  }
  listSessions(archived?: boolean) {
    return this.request<CloudSession[]>(
      'GET',
      '/v1/cloud/sessions',
      undefined,
      archived === undefined ? undefined : { params: { archived } }
    )
  }
  listWorkspaces() {
    return this.request<CloudWorkspace[]>('GET', '/v1/workspaces')
  }
  importSession(snapshot: Record<string, unknown>) {
    return this.request<CloudSession>('POST', '/v1/cloud/sessions/import', snapshot)
  }
  createSession(
    kind: CloudSession['kind'],
    title = 'New session',
    workspaceId = 'default',
    modelId?: string
  ) {
    return this.request<CloudSession>('POST', '/v1/cloud/sessions', {
      kind,
      title,
      workspace_id: workspaceId,
      model_id: modelId,
    })
  }
  sendCommand(
    sessionId: string,
    requestId: string,
    input: string,
    options: {
      attachments?: CloudAttachment[]
      model_id?: string
      authorization_mode?: 'default' | 'full'
    } = {}
  ) {
    return this.request<{ command_id: string; sequence: number; status: string }>(
      'POST',
      `/v1/cloud/sessions/${encodeURIComponent(sessionId)}/commands`,
      {
        request_id: requestId,
        input,
        ...(options.attachments?.length ? { attachments: options.attachments } : {}),
        ...(options.model_id ? { model_id: options.model_id } : {}),
        authorization_mode: options.authorization_mode ?? 'default',
      }
    )
  }
  commandStatus(sessionId: string, commandId: string) {
    return this.request<Record<string, unknown>>(
      'GET',
      `/v1/cloud/sessions/${encodeURIComponent(sessionId)}/commands/${encodeURIComponent(commandId)}`
    )
  }
  listCommands(sessionId: string, after = 0, limit = 100) {
    if (!Number.isSafeInteger(after) || after < 0) throw new Error('after must be non-negative')
    return this.request<unknown[]>(
      'GET',
      `/v1/cloud/sessions/${encodeURIComponent(sessionId)}/commands`,
      undefined,
      { params: { after, limit } }
    )
  }
  snapshot(sessionId: string, limit = 500) {
    return this.request<Record<string, unknown>>(
      'GET',
      `/v1/cloud/sessions/${encodeURIComponent(sessionId)}/snapshot`,
      undefined,
      { params: { limit } }
    )
  }
  async events(sessionId: string, after = 0, limit = 500): Promise<CloudEvent[]> {
    if (!Number.isSafeInteger(after) || after < 0) throw new Error('after must be non-negative')
    const events = await this.request<unknown[]>(
      'GET',
      `/v1/cloud/sessions/${encodeURIComponent(sessionId)}/events`,
      undefined,
      { params: { after, limit } }
    )
    return this.validateEventPage(events, after)
  }

  private validateEventPage(events: unknown[], after: number): CloudEvent[] {
    if (!Array.isArray(events)) throw new Error('invalid cloud event page')
    let previous = after
    for (const event of events) {
      if (
        !event ||
        typeof event !== 'object' ||
        typeof (event as CloudEvent).sequence !== 'number' ||
        !Number.isSafeInteger((event as CloudEvent).sequence) ||
        (event as CloudEvent).sequence !== previous + 1
      ) {
        throw new Error('event cursor gap; refresh session snapshot')
      }
      previous = (event as CloudEvent).sequence
    }
    return events as CloudEvent[]
  }
  archiveSession(sessionId: string) {
    return this.request<Record<string, unknown>>(
      'POST',
      `/v1/cloud/sessions/${encodeURIComponent(sessionId)}/archive`
    )
  }
  restoreSession(sessionId: string) {
    return this.request<Record<string, unknown>>(
      'POST',
      `/v1/cloud/sessions/${encodeURIComponent(sessionId)}/restore`
    )
  }
  copySession(sessionId: string) {
    return this.request<CloudSession>(
      'POST',
      `/v1/cloud/sessions/${encodeURIComponent(sessionId)}/copy`
    )
  }
  deleteSession(sessionId: string) {
    return this.request<Record<string, unknown>>(
      'DELETE',
      `/v1/cloud/sessions/${encodeURIComponent(sessionId)}`
    )
  }
  renameSession(sessionId: string, title: string) {
    return this.request<{ session_id: string; title: string }>(
      'PATCH',
      `/v1/cloud/sessions/${encodeURIComponent(sessionId)}`,
      { title }
    )
  }
  recoverCommand(sessionId: string, commandId: string, mode: 'resume' | 'abandon') {
    return this.request<Record<string, unknown>>(
      'POST',
      `/v1/cloud/sessions/${encodeURIComponent(sessionId)}/commands/${encodeURIComponent(commandId)}/recover`,
      { mode }
    )
  }
  listWorkspaceFiles(workspaceId: string, prefix = '', limit = 500) {
    return this.request<Record<string, unknown>>(
      'GET',
      `/v1/workspaces/${encodeURIComponent(workspaceId)}/files`,
      undefined,
      { params: { prefix, limit } }
    )
  }
  readWorkspaceFile(workspaceId: string, path: string) {
    return this.request<Record<string, unknown>>(
      'GET',
      `/v1/workspaces/${encodeURIComponent(workspaceId)}/files/${path.split('/').map(encodeURIComponent).join('/')}`
    )
  }
  writeWorkspaceFile(workspaceId: string, path: string, content: string) {
    return this.request<Record<string, unknown>>(
      'PUT',
      `/v1/workspaces/${encodeURIComponent(workspaceId)}/files/${path.split('/').map(encodeURIComponent).join('/')}`,
      { content }
    )
  }
  deleteWorkspaceFile(workspaceId: string, path: string) {
    return this.request<Record<string, unknown>>(
      'DELETE',
      `/v1/workspaces/${encodeURIComponent(workspaceId)}/files/${path.split('/').map(encodeURIComponent).join('/')}`
    )
  }
  workspaceStats(workspaceId: string) {
    return this.request<Record<string, unknown>>(
      'GET',
      `/v1/workspaces/${encodeURIComponent(workspaceId)}/stats`
    )
  }
  workspaceCapacity(workspaceId: string) {
    return this.request<Record<string, unknown>>(
      'GET',
      `/v1/workspaces/${encodeURIComponent(workspaceId)}/capacity`
    )
  }
  createWorkspaceBackup(workspaceId: string) {
    return this.request<Record<string, unknown>>(
      'POST',
      `/v1/workspaces/${encodeURIComponent(workspaceId)}/backups`
    )
  }
  listWorkspaceBackups(workspaceId: string, limit = 100) {
    return this.request<unknown[]>(
      'GET',
      `/v1/workspaces/${encodeURIComponent(workspaceId)}/backups`,
      undefined,
      { params: { limit } }
    )
  }
  restoreWorkspaceBackup(workspaceId: string, backupId: string) {
    return this.request<Record<string, unknown>>(
      'POST',
      `/v1/workspaces/${encodeURIComponent(workspaceId)}/backups/restore`,
      { backup_id: backupId }
    )
  }
  deleteWorkspaceBackup(workspaceId: string, backupId: string) {
    return this.request<Record<string, unknown>>(
      'DELETE',
      `/v1/workspaces/${encodeURIComponent(workspaceId)}/backups/${encodeURIComponent(backupId)}`
    )
  }
  listApprovals(sessionId: string) {
    return this.request<unknown[]>(
      'GET',
      `/v1/cloud/sessions/${encodeURIComponent(sessionId)}/approvals`
    )
  }
  resolveApproval(
    sessionId: string,
    approvalId: string,
    status: 'approved' | 'rejected',
    note?: string
  ) {
    return this.request<Record<string, unknown>>(
      'POST',
      `/v1/cloud/sessions/${encodeURIComponent(sessionId)}/approvals/${encodeURIComponent(approvalId)}/resolve`,
      { status, note }
    )
  }
}

export default CloudClient
