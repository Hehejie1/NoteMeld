export interface DeviceConnectivity { lan_endpoints?: string[] }
export interface ConnectionCandidate { transport: 'lan' | 'relay'; url: string }

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
  const base = cloudBaseUrl.replace(/\/$/, '')
  const candidates: ConnectionCandidate[] = []
  for (const endpoint of device.lan_endpoints ?? []) {
    const normalized = endpoint.trim()
    if (!normalized) continue
    const host = normalized.includes(':') && normalized.includes('::') && !normalized.startsWith('[')
      ? `[${normalized.slice(0, normalized.lastIndexOf(':'))}]:${normalized.slice(normalized.lastIndexOf(':') + 1)}`
      : normalized
    candidates.push({ transport: 'lan', url: `ws://${host}/v1/relay/connect/${encodeURIComponent(sessionId)}` })
  }
  const relay = new URL(base)
  relay.protocol = relay.protocol === 'https:' ? 'wss:' : 'ws:'
  relay.pathname = `/v1/relay/connect/${encodeURIComponent(sessionId)}`
  relay.search = ''
  candidates.push({ transport: 'relay', url: relay.toString() })
  return candidates
}
