import axios, { AxiosInstance } from 'axios'

export interface CloudEnvelope<T> { code: number; msg: string; data: T }
export interface CloudCapabilities { protocol_version: string; canonical_session_prefix: string; device_proof_required: boolean; e2ee_relay_envelope: boolean; relay_persists_payload: boolean; max_request_bytes: number; max_workspace_bytes: number; max_workspace_files: number; features: Record<string, boolean> }
export interface CloudSession { id: string; kind: 'cloud_native' | 'device_remote'; title?: string; workspace_id: string; model_id?: string | null; status?: string }

/** Stateless adapter for cloud control-plane APIs; no local Agent state lives here. */
export class CloudClient {
  private readonly http: AxiosInstance
  private token: string | null

  constructor(baseUrl: string, token?: string, deviceId?: string) {
    this.token = token ?? null
    this.http = axios.create({ baseURL: baseUrl.replace(/\/$/, ''), timeout: 20_000 })
    if (deviceId) this.http.defaults.headers.common['X-Device-Id'] = deviceId
  }

  setToken(token: string | null) { this.token = token }

  private async request<T>(method: string, path: string, data?: unknown, config?: Record<string, unknown>): Promise<T> {
    const response = await this.http.request<CloudEnvelope<T>>({ method, url: path, data, headers: this.token ? { Authorization: `Bearer ${this.token}` } : undefined, ...(config as any) })
    if (response.data.code !== 0) throw new Error(response.data.msg || 'cloud request failed')
    return response.data.data
  }

  login(password: string, username?: string, accountId?: string) { return this.request<{ token: string; user_id: string; role: string }>('POST', '/v1/auth/login', { password, ...(username ? { username } : {}), ...(accountId ? { account_id: accountId } : {}) }) }
  capabilities() { return this.request<CloudCapabilities>('GET', '/v1/capabilities') }
  listDevices() { return this.request<unknown[]>('GET', '/v1/devices') }
  registerDevice(deviceId: string, platform: string, displayName: string, publicKey?: string) { return this.request<Record<string, unknown>>('POST', '/v1/devices/register', { device_id: deviceId, platform, display_name: displayName, public_key: publicKey }) }
  revokeDevice(deviceId: string) { return this.request<Record<string, unknown>>('DELETE', `/v1/devices/${encodeURIComponent(deviceId)}`) }
  listGrants() { return this.request<unknown[]>('GET', '/v1/grants') }
  createGrant(controllerDeviceId: string, hostDeviceId: string, scopes?: string[], workspaceRefs?: string[]) { return this.request<Record<string, unknown>>('POST', '/v1/grants', { controller_device_id: controllerDeviceId, host_device_id: hostDeviceId, ...(scopes ? { scopes } : {}), ...(workspaceRefs ? { workspace_refs: workspaceRefs } : {}) }) }
  revokeGrant(grantId: string) { return this.request<Record<string, unknown>>('DELETE', `/v1/grants/${encodeURIComponent(grantId)}`) }
  listSessions() { return this.request<CloudSession[]>('GET', '/v1/cloud/sessions') }
  createSession(kind: CloudSession['kind'], title = 'New session', workspaceId = 'default', modelId?: string) { return this.request<CloudSession>('POST', '/v1/cloud/sessions', { kind, title, workspace_id: workspaceId, model_id: modelId }) }
  sendCommand(sessionId: string, requestId: string, input: string) { return this.request<{ command_id: string; sequence: number; status: string }>('POST', `/v1/cloud/sessions/${encodeURIComponent(sessionId)}/commands`, { request_id: requestId, input }) }
  snapshot(sessionId: string) { return this.request<Record<string, unknown>>('GET', `/v1/cloud/sessions/${encodeURIComponent(sessionId)}/snapshot`) }
  events(sessionId: string, after = 0) { return this.request<unknown[]>('GET', `/v1/cloud/sessions/${encodeURIComponent(sessionId)}/events`, undefined, { params: { after } }) }
  archiveSession(sessionId: string) { return this.request<Record<string, unknown>>('POST', `/v1/cloud/sessions/${encodeURIComponent(sessionId)}/archive`) }
  restoreSession(sessionId: string) { return this.request<Record<string, unknown>>('POST', `/v1/cloud/sessions/${encodeURIComponent(sessionId)}/restore`) }
  copySession(sessionId: string) { return this.request<CloudSession>('POST', `/v1/cloud/sessions/${encodeURIComponent(sessionId)}/copy`) }
  recoverCommand(sessionId: string, commandId: string, mode: 'resume' | 'abandon') { return this.request<Record<string, unknown>>('POST', `/v1/cloud/sessions/${encodeURIComponent(sessionId)}/commands/${encodeURIComponent(commandId)}/recover`, { mode }) }
  listWorkspaceFiles(workspaceId: string, prefix = '') { return this.request<unknown[]>('GET', `/v1/workspaces/${encodeURIComponent(workspaceId)}/files`, undefined, { params: { prefix } }) }
  readWorkspaceFile(workspaceId: string, path: string) { return this.request<Record<string, unknown>>('GET', `/v1/workspaces/${encodeURIComponent(workspaceId)}/files/${path.split('/').map(encodeURIComponent).join('/')}`) }
  writeWorkspaceFile(workspaceId: string, path: string, content: string) { return this.request<Record<string, unknown>>('PUT', `/v1/workspaces/${encodeURIComponent(workspaceId)}/files/${path.split('/').map(encodeURIComponent).join('/')}`, { content }) }
  deleteWorkspaceFile(workspaceId: string, path: string) { return this.request<Record<string, unknown>>('DELETE', `/v1/workspaces/${encodeURIComponent(workspaceId)}/files/${path.split('/').map(encodeURIComponent).join('/')}`) }
  listApprovals(sessionId: string) { return this.request<unknown[]>('GET', `/v1/cloud/sessions/${encodeURIComponent(sessionId)}/approvals`) }
  resolveApproval(sessionId: string, approvalId: string, status: 'approved' | 'rejected', note?: string) { return this.request<Record<string, unknown>>('POST', `/v1/cloud/sessions/${encodeURIComponent(sessionId)}/approvals/${encodeURIComponent(approvalId)}/resolve`, { status, note }) }
}

export default CloudClient
