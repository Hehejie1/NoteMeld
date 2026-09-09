export interface DeviceConnectivity { lan_endpoints?: string[] }
export interface ConnectionCandidate { transport: 'lan' | 'relay'; url: string; auth: 'challenge' | 'bearer' }
export function relayWebSocketProtocols(token: string): string[] { if (!token) throw new Error('relay token is required'); return ['notemeld.v1', `bearer.${token}`] }

export function validateCloudBaseUrl(value: string): URL {
  const parsed = new URL(value.trim().replace(/\/$/, ''))
  if (!['http:', 'https:'].includes(parsed.protocol) || parsed.username || parsed.password || parsed.hash || parsed.search) throw new Error('cloud URL must be an http(s) URL without credentials or query parameters')
  const local = ['localhost', '127.0.0.1', '[::1]', '::1'].includes(parsed.hostname)
  if (parsed.protocol === 'http:' && !local) throw new Error('cloud URL must use HTTPS unless it targets localhost')
  return parsed
}

function isPrivateLanEndpoint(endpoint: string): boolean {
  const separator = endpoint.lastIndexOf(':')
  if (separator <= 0) return false
  const host = endpoint.slice(0, separator).replace(/^\[|\]$/g, '').toLowerCase()
  if (host.includes(':') && !endpoint.trim().startsWith('[')) return false
  if (host.includes('%')) return false
  const port = Number(endpoint.slice(separator + 1))
  if (!Number.isInteger(port) || port < 1 || port > 65535) return false
  const ipv4 = host.match(/^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$/)
  if (ipv4) {
    const octets = ipv4.slice(1).map(Number)
    if (octets.some(value => value > 255)) return false
    return octets[0] === 10 || octets[0] === 127 || (octets[0] === 169 && octets[1] === 254) ||
      (octets[0] === 172 && octets[1] >= 16 && octets[1] <= 31) || (octets[0] === 192 && octets[1] === 168)
  }
  if (host === '::1' || host === '::' || host.startsWith('ff')) return host === '::1'
  return /^f[cd][0-9a-f]{2}:/.test(host) || /^fe[89ab][0-9a-f]:/.test(host)
}

export async function connectWithFallback<T>(candidates: ConnectionCandidate[], connect: (candidate: ConnectionCandidate, signal: AbortSignal) => Promise<T>, timeoutMs = 3_000): Promise<{ connection: T; candidate: ConnectionCandidate }> {
  let lastError: unknown = new Error('no connection candidates')
  for (const candidate of candidates) {
    const controller = new AbortController()
    const timer = setTimeout(() => controller.abort(), timeoutMs)
    try {
      const connection = await connect(candidate, controller.signal)
      return { connection, candidate }
    } catch (error) {
      lastError = error
    } finally {
      clearTimeout(timer)
    }
  }
  throw lastError
}

/**
 * Build deterministic connection candidates. Authorization is still performed
 * by the handshake/Relay protocol; these URLs are only routing hints.
 */
export function connectionCandidates(cloudBaseUrl: string, sessionId: string, device: DeviceConnectivity): ConnectionCandidate[] {
  const parsedBase = validateCloudBaseUrl(cloudBaseUrl)
  const base = parsedBase.toString().replace(/\/$/, '')
  const candidates: ConnectionCandidate[] = []
  for (const endpoint of device.lan_endpoints ?? []) {
    const normalized = endpoint.trim()
    if (!normalized) continue
    if (!isPrivateLanEndpoint(normalized)) throw new Error('invalid private LAN endpoint')
    const host = normalized
    candidates.push({ transport: 'lan', auth: 'challenge', url: `ws://${host}/v1/lan/connect/${encodeURIComponent(sessionId)}` })
  }
  const relay = new URL(base)
  relay.protocol = relay.protocol === 'https:' ? 'wss:' : 'ws:'
  relay.pathname = `/v1/relay/connect/${encodeURIComponent(sessionId)}`
  relay.search = ''
  candidates.push({ transport: 'relay', auth: 'bearer', url: relay.toString() })
  return candidates
}

export type LanHandshake = (socket: WebSocket, signal: AbortSignal) => Promise<void>

export function openRelayWebSocket(cloudBaseUrl: string, sessionId: string, device: DeviceConnectivity, token: string, timeoutMs = 3_000, lanHandshake?: LanHandshake): Promise<{ connection: WebSocket; candidate: ConnectionCandidate }> {
  return connectWithFallback(connectionCandidates(cloudBaseUrl, sessionId, device), (candidate, signal) => new Promise<WebSocket>((resolve, reject) => {
    if (candidate.auth === 'challenge' && !lanHandshake) {
      reject(new Error('LAN challenge handler is required'))
      return
    }
    const protocols = candidate.auth === 'bearer' ? relayWebSocketProtocols(token) : ['notemeld.lan.v1']
    const socket = new WebSocket(candidate.url, protocols)
    const abort = () => { socket.close(); reject(new DOMException('relay connection timed out', 'AbortError')) }
    if (signal.aborted) { abort(); return }
    signal.addEventListener('abort', abort, { once: true })
    socket.onopen = () => {
      if (candidate.auth === 'challenge') {
        lanHandshake!(socket, signal).then(() => { signal.removeEventListener('abort', abort); resolve(socket) }).catch(error => { signal.removeEventListener('abort', abort); socket.close(); reject(error) })
        return
      }
      signal.removeEventListener('abort', abort)
      resolve(socket)
    }
    socket.onerror = () => { signal.removeEventListener('abort', abort); socket.close(); reject(new Error('relay connection failed')) }
  }), timeoutMs)
}
