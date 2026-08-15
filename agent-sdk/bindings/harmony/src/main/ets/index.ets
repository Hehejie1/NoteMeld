import agentNative from 'libnotemeld_agent_napi.so'

export const SDK_VERSION: string = '0.1.0'
export const SCHEMA_VERSION: string = '1'

export type AgentEvent = Record<string, Object>

/** ArkTS only translates JSON and lifecycle calls; event semantics remain Rust v1. */
export class AgentRuntime {
  private handle: bigint
  private terminalPromise: Promise<string> | null = null
  private resolveTerminal: ((type: string) => void) | null = null
  private activeToken: bigint = 0n
  private userEvent: (eventJson: string) => void

  constructor(
    configJson: string,
    onEvent: (eventJson: string) => void,
    onDriverRequest: (requestJson: string) => string
  ) {
    if (agentNative.sdkVersion() !== SDK_VERSION || agentNative.schemaVersion() !== SCHEMA_VERSION) {
      throw new Error('NoteMeld Agent native version mismatch')
    }
    this.userEvent = onEvent
    this.handle = agentNative.runtimeNew(configJson)
    agentNative.setCallbacks(this.handle, (wire: string) => this.receiveEvent(wire), (wire: string) => {
      try {
        const result = onDriverRequest(wire)
        if (typeof result !== 'string') throw new Error('driver result must be JSON string')
        JSON.parse(result)
        return result
      } catch (_) {
        return '{"schema_version":"1","ok":false,"error":{"code":"sdk_internal_error","message":"host driver failed"}}'
      }
    })
  }

  private receiveEvent(eventJson: string): void {
    this.userEvent(eventJson)
    const event = JSON.parse(eventJson) as Record<string, string>
    const type = event['type']
    if (type === 'turn.succeeded' || type === 'turn.failed' || type === 'turn.cancelled' || type === 'turn.interrupted') {
      const resolve = this.resolveTerminal
      this.resolveTerminal = null
      this.activeToken = 0n
      if (resolve !== null) resolve(type)
    }
  }

  submitTurn(requestJson: string): bigint {
    this.terminalPromise = new Promise<string>((resolve) => { this.resolveTerminal = resolve })
    this.activeToken = agentNative.submitTurn(this.handle, requestJson)
    return this.activeToken
  }
  completeDriverCall(callId: bigint, resultJson: string): number {
    return agentNative.completeDriverCall(this.handle, callId, resultJson)
  }
  cancel(turnToken: bigint): number { return agentNative.cancelTurn(this.handle, turnToken) }
  waitForTerminal(): Promise<string> {
    if (this.terminalPromise === null) return Promise.reject(new Error('no submitted turn'))
    return this.terminalPromise
  }
  steer(turnToken: bigint, steerJson: string): number {
    return agentNative.steerTurn(this.handle, turnToken, steerJson)
  }
  async close(): Promise<void> {
    if (this.handle === 0n) return
    if (this.activeToken !== 0n && this.terminalPromise !== null) {
      agentNative.cancelTurn(this.handle, this.activeToken)
      await this.terminalPromise
    }
    agentNative.runtimeFree(this.handle); this.handle = 0n
  }
}
