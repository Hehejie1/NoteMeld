import CloudClient, { CloudSession } from './cloud'

export interface CloudSessionState {
  session: CloudSession | null
  events: unknown[]
  lastSequence: number
  loading: boolean
  error: Error | null
}

/** UI-facing projection; CloudClient remains the only transport authority. */
export class CloudSessionController {
  private state: CloudSessionState = { session: null, events: [], lastSequence: 0, loading: false, error: null }
  private listeners = new Set<(state: CloudSessionState) => void>()
  constructor(private readonly client: CloudClient) {}
  getState() { return this.state }
  subscribe(listener: (state: CloudSessionState) => void) { this.listeners.add(listener); return () => this.listeners.delete(listener) }
  private update(changes: Partial<CloudSessionState>) { this.state = { ...this.state, ...changes }; for (const listener of this.listeners) listener(this.state) }

  async open(sessionId: string) {
    this.update({ loading: true, error: null })
    try {
      const snapshot = await this.client.snapshot(sessionId) as { session: CloudSession; events?: Array<{ sequence: number }> }
      const events = snapshot.events ?? []
      this.update({ session: snapshot.session, events, lastSequence: events.reduce((max, event) => Math.max(max, event.sequence), 0), loading: false })
      return this.state
    } catch (error) {
      const normalized = error instanceof Error ? error : new Error(String(error))
      this.update({ loading: false, error: normalized }); throw normalized
    }
  }

  async refreshEvents() {
    if (!this.state.session) throw new Error('session is not open')
    const incoming = await this.client.events(this.state.session.id, this.state.lastSequence) as Array<{ sequence: number }>
    const fresh = incoming.filter(event => Number.isInteger(event.sequence) && event.sequence > this.state.lastSequence)
      .sort((left, right) => left.sequence - right.sequence)
    if (fresh.length) this.update({ events: [...this.state.events, ...fresh], lastSequence: fresh[fresh.length - 1].sequence })
    return fresh
  }

  async send(input: string, requestId: string) {
    if (!this.state.session) throw new Error('session is not open')
    return this.client.sendCommand(this.state.session.id, requestId, input)
  }

  async recover(commandId: string, mode: 'resume' | 'abandon') {
    if (!this.state.session) throw new Error('session is not open')
    return this.client.recoverCommand(this.state.session.id, commandId, mode)
  }
}
