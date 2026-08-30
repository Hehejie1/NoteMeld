import axios, { AxiosInstance } from 'axios'
import { validateCloudBaseUrl } from './connectionStrategy'

export interface CloudEnvelope<T> { code: number; msg: string; data: T }
export interface CloudCapabilities { protocol_version: string; canonical_session_prefix: string; device_proof_required: boolean; e2ee_relay_envelope: boolean; relay_persists_payload: boolean; relay_backend?: string; relay_multi_worker?: boolean; lan_first_candidates?: boolean; worker_count?: number; max_request_bytes: number; max_workspace_bytes: number; max_workspace_files: number; features: Record<string, boolean> }
export interface CloudSession { id: string; kind: 'cloud_native' | 'device_remote'; title?: string; workspace_id: string; model_id?: string | null; status?: string }
export interface CloudUser { id: string; username: string; role: 'admin' | 'user'; disabled: boolean; created_at: number }
export interface CloudToken { id: string; audience: string; scopes: string[]; expires_at?: number | null; revoked_at?: number | null; created_at: number }
export interface CloudTokenStore { load(): Promise<string | null>; save(token: string): Promise<void>; clear(): Promise<void> }

/** Stateless adapter for cloud control-plane APIs; no local Agent state lives here. */
export class CloudClient {
  private readonly http: AxiosInstance
  private token: string | null
  private tokenHydrated = false

  private readonly tokenStore?: CloudTokenStore

  constructor(baseUrl: string, token?: string, deviceId?: string, tokenStore?: CloudTokenStore) {
    this.token = token ?? null
    this.tokenStore = tokenStore
    this.http = axios.create({ baseURL: validateCloudBaseUrl(baseUrl).toString().replace(/\/$/, ''), timeout: 20_000 })
    if (deviceId) this.http.defaults.headers.common['X-Device-Id'] = deviceId
  }

  setToken(token: string | null) { this.token = token }
  async hydrateToken() { if (!this.tokenHydrated) { this.tokenHydrated = true; if (this.token === null && this.tokenStore) this.token = await this.tokenStore.load() } return this.token }
  private async persistToken() { if (!this.tokenStore) return; if (this.token) await this.tokenStore.save(this.token); else await this.tokenStore.clear() }

  private async request<T>(method: string, path: string, data?: unknown, config?: Record<string, unknown>): Promise<T> {
    await this.hydrateToken()
    const response = await this.http.request<CloudEnvelope<T>>({ method, url: path, data, headers: this.token ? { Authorization: `Bearer ${this.token}` } : undefined, ...(config as any) })
    if (response.data.code !== 0) throw new Error(response.data.msg || 'cloud request failed')
    return response.data.data
  }

  async login(password: string, username?: string, accountId?: string) { const data = await this.request<{ token: string; user_id: string; role: string }>('POST', '/v1/auth/login', { password, ...(username ? { username } : {}), ...(accountId ? { account_id: accountId } : {}) }); this.token = data.token; await this.persistToken(); return data }
  async rotateToken() { const data = await this.request<{ token: string; jti: string; expires_at?: number | null }>('POST', '/v1/auth/rotate'); this.token = data.token; await this.persistToken(); return data }
  async revokeCurrentToken() { const data = await this.request<Record<string, unknown>>('POST', '/v1/auth/revoke'); this.token = null; await this.persistToken(); return data }
  listTokens() { return this.request<CloudToken[]>('GET', '/v1/auth/tokens') }
  createToken(scopes: string[] = ['*'], expiresAt?: number) { return this.request<{ token: string; jti: string; scopes: string[]; expires_at?: number | null }>('POST', '/v1/auth/tokens', { scopes, ...(expiresAt === undefined ? {} : { expires_at: expiresAt }) }) }
  revokeToken(tokenId: string) { return this.request<Record<string, unknown>>('POST', `/v1/auth/tokens/${encodeURIComponent(tokenId)}/revoke`) }
  listUsers() { return this.request<CloudUser[]>('GET', '/v1/admin/users') }
  createUser(username: string, password: string) { return this.request<{ id: string; username: string }>('POST', '/v1/admin/users', { username, password }) }
  updateUser(userId: string, changes: { username?: string; password?: string; disabled?: boolean }) { return this.request<Record<string, unknown>>('PUT', `/v1/admin/users/${encodeURIComponent(userId)}`, changes) }
  deleteUser(userId: string) { return this.request<Record<string, unknown>>('DELETE', `/v1/admin/users/${encodeURIComponent(userId)}`) }
  listAudits(limit = 100) { return this.request<unknown[]>('GET', '/v1/admin/audits', undefined, { params: { limit } }) }
  capabilities() { return this.request<CloudCapabilities>('GET', '/v1/capabilities') }
  listDevices() { return this.request<unknown[]>('GET', '/v1/devices') }
  registerDevice(deviceId: string, platform: string, displayName: string, publicKey?: string, lanEndpoints: string[] = []) { return this.request<Record<string, unknown>>('POST', '/v1/devices/register', { device_id: deviceId, platform, display_name: displayName, public_key: publicKey, lan_endpoints: lanEndpoints }) }
  revokeDevice(deviceId: string) { return this.request<Record<string, unknown>>('DELETE', `/v1/devices/${encodeURIComponent(deviceId)}`) }
  rotateDeviceKey(deviceId: string, publicKey: string) { return this.request<Record<string, unknown>>('POST', `/v1/devices/${encodeURIComponent(deviceId)}/rotate-key`, { public_key: publicKey }) }
  heartbeat(deviceId: string, lanEndpoints?: string[]) { return this.request<Record<string, unknown>>('POST', `/v1/devices/${encodeURIComponent(deviceId)}/heartbeat`, lanEndpoints === undefined ? undefined : { lan_endpoints: lanEndpoints }) }
  requestDeviceChallenge(deviceId: string) { return this.request<{ challenge: string; expires_at: number }>('POST', `/v1/devices/${encodeURIComponent(deviceId)}/challenge`) }
  verifyDeviceChallenge(deviceId: string, challenge: string, signature: string) { return this.request<Record<string, unknown>>('POST', `/v1/devices/${encodeURIComponent(deviceId)}/challenge/verify`, { challenge, signature }) }
  startPairing() { return this.request<{ code: string; expires_at: number }>('POST', '/v1/pairings/start') }
  confirmPairing(code: string, deviceId: string, platform: string, displayName: string, publicKey?: string) { return this.request<Record<string, unknown>>('POST', '/v1/pairings/confirm', { code, device_id: deviceId, platform, display_name: displayName, public_key: publicKey }) }
  listGrants() { return this.request<unknown[]>('GET', '/v1/grants') }
  createGrant(controllerDeviceId: string, hostDeviceId: string, scopes?: string[], workspaceRefs?: string[]) { return this.request<Record<string, unknown>>('POST', '/v1/grants', { controller_device_id: controllerDeviceId, host_device_id: hostDeviceId, ...(scopes ? { scopes } : {}), ...(workspaceRefs ? { workspace_refs: workspaceRefs } : {}) }) }
  revokeGrant(grantId: string) { return this.request<Record<string, unknown>>('DELETE', `/v1/grants/${encodeURIComponent(grantId)}`) }
  listSessions(archived?: boolean) { return this.request<CloudSession[]>('GET', '/v1/cloud/sessions', undefined, archived === undefined ? undefined : { params: { archived } }) }
  createSession(kind: CloudSession['kind'], title = 'New session', workspaceId = 'default', modelId?: string) { return this.request<CloudSession>('POST', '/v1/cloud/sessions', { kind, title, workspace_id: workspaceId, model_id: modelId }) }
  sendCommand(sessionId: string, requestId: string, input: string) { return this.request<{ command_id: string; sequence: number; status: string }>('POST', `/v1/cloud/sessions/${encodeURIComponent(sessionId)}/commands`, { request_id: requestId, input }) }
  snapshot(sessionId: string) { return this.request<Record<string, unknown>>('GET', `/v1/cloud/sessions/${encodeURIComponent(sessionId)}/snapshot`) }
  events(sessionId: string, after = 0) { return this.request<unknown[]>('GET', `/v1/cloud/sessions/${encodeURIComponent(sessionId)}/events`, undefined, { params: { after } }) }
  archiveSession(sessionId: string) { return this.request<Record<string, unknown>>('POST', `/v1/cloud/sessions/${encodeURIComponent(sessionId)}/archive`) }
  restoreSession(sessionId: string) { return this.request<Record<string, unknown>>('POST', `/v1/cloud/sessions/${encodeURIComponent(sessionId)}/restore`) }
  copySession(sessionId: string) { return this.request<CloudSession>('POST', `/v1/cloud/sessions/${encodeURIComponent(sessionId)}/copy`) }
  deleteSession(sessionId: string) { return this.request<Record<string, unknown>>('DELETE', `/v1/cloud/sessions/${encodeURIComponent(sessionId)}`) }
  recoverCommand(sessionId: string, commandId: string, mode: 'resume' | 'abandon') { return this.request<Record<string, unknown>>('POST', `/v1/cloud/sessions/${encodeURIComponent(sessionId)}/commands/${encodeURIComponent(commandId)}/recover`, { mode }) }
  listWorkspaceFiles(workspaceId: string, prefix = '') { return this.request<unknown[]>('GET', `/v1/workspaces/${encodeURIComponent(workspaceId)}/files`, undefined, { params: { prefix } }) }
  readWorkspaceFile(workspaceId: string, path: string) { return this.request<Record<string, unknown>>('GET', `/v1/workspaces/${encodeURIComponent(workspaceId)}/files/${path.split('/').map(encodeURIComponent).join('/')}`) }
  writeWorkspaceFile(workspaceId: string, path: string, content: string) { return this.request<Record<string, unknown>>('PUT', `/v1/workspaces/${encodeURIComponent(workspaceId)}/files/${path.split('/').map(encodeURIComponent).join('/')}`, { content }) }
  deleteWorkspaceFile(workspaceId: string, path: string) { return this.request<Record<string, unknown>>('DELETE', `/v1/workspaces/${encodeURIComponent(workspaceId)}/files/${path.split('/').map(encodeURIComponent).join('/')}`) }
  listApprovals(sessionId: string) { return this.request<unknown[]>('GET', `/v1/cloud/sessions/${encodeURIComponent(sessionId)}/approvals`) }
  resolveApproval(sessionId: string, approvalId: string, status: 'approved' | 'rejected', note?: string) { return this.request<Record<string, unknown>>('POST', `/v1/cloud/sessions/${encodeURIComponent(sessionId)}/approvals/${encodeURIComponent(approvalId)}/resolve`, { status, note }) }
}

export default CloudClient
