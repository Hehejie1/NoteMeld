import agentNative from 'libnotemeld_agent_napi.so'

export const SDK_VERSION: string = '0.1.0'
export const SCHEMA_VERSION: string = '1'

export type AgentEvent = Record<string, Object>

export class AgentRuntimeError extends Error {
  readonly code: string
  readonly status: number

  constructor(code: string, message: string, status: number = 0) {
    super(message)
    this.code = code
    this.status = status
  }
}

/** ArkTS translates types/lifecycle only; event semantics remain Rust v1. */
export class AgentRuntime {
  private handle: bigint = 0n
  private terminalPromise: Promise<string> | null = null
  private resolveTerminal: ((type: string) => void) | null = null
  private rejectTerminal: ((error: Error) => void) | null = null
  private activeToken: bigint = 0n
  private activeTurnId: string = ''
  private userEvent: (eventJson: string) => void

  constructor(
    configJson: string,
    onEvent: (eventJson: string) => void,
    onDriverRequest: (requestJson: string) => string
  ) {
    if (agentNative.sdkVersion() !== SDK_VERSION || agentNative.schemaVersion() !== SCHEMA_VERSION) {
      throw new AgentRuntimeError('version_mismatch', 'NoteMeld Agent native version mismatch')
    }
    this.userEvent = onEvent
    const created = agentNative.runtimeNew(configJson)
    if (created === 0n) throw new AgentRuntimeError('runtime_unavailable', 'native runtime creation failed')
    this.handle = created
    const callbackStatus = agentNative.setCallbacks(
      this.handle,
      (wire: string) => this.receiveEvent(wire),
      (wire: string) => {
        try {
          const result = onDriverRequest(wire)
          if (typeof result !== 'string') throw new Error('driver result must be JSON string')
          JSON.parse(result)
          return result
        } catch (_) {
          return '{"schema_version":"1","ok":false,"error":{"code":"sdk_internal_error","message":"host driver failed"}}'
        }
      }
    )
    if (callbackStatus !== 0) {
      const freeStatus = agentNative.runtimeFree(this.handle)
      this.handle = 0n
      if (freeStatus !== 0) {
        throw new AgentRuntimeError('runtime_cleanup_failed', 'callback registration and runtime cleanup failed', freeStatus)
      }
      throw new AgentRuntimeError('callback_registration_failed', 'callback registration failed', callbackStatus)
    }
  }

  private receiveEvent(eventJson: string): void {
    try {
      const event = JSON.parse(eventJson) as Record<string, string>
      const type = event['type']
      const matchesActive = this.activeTurnId.length > 0 && event['turn_id'] === this.activeTurnId
      if (matchesActive && (type === 'turn.succeeded' || type === 'turn.failed' ||
          type === 'turn.cancelled' || type === 'turn.interrupted')) {
        const resolve = this.resolveTerminal
        const reject = this.rejectTerminal
        this.resolveTerminal = null
        this.rejectTerminal = null
        this.activeToken = 0n
        this.activeTurnId = ''
        if (type === 'turn.succeeded') {
          if (resolve !== null) resolve(type)
        } else if (reject !== null) {
          reject(new AgentRuntimeError(type, `agent turn terminated: ${type}`))
        }
      }
    } catch (_) {
      // Invalid observer data cannot corrupt the control-plane Promise.
    }
    try { this.userEvent(eventJson) } catch (_) {
      // User observers are isolated from terminal settlement.
    }
  }

  private ensureOpen(): void {
    if (this.handle === 0n) throw new AgentRuntimeError('invalid_handle', 'runtime is closed', -1)
  }

  private checkStatus(status: number, operation: string): void {
    if (status !== 0) throw new AgentRuntimeError(`${operation}_failed`, `${operation} failed`, status)
  }

  submitTurn(requestJson: string): bigint {
    this.ensureOpen()
    if (this.activeToken !== 0n) {
      throw new AgentRuntimeError('agent_runtime_busy', 'one active turn is already running')
    }
    let turnId: string
    try {
      const request = JSON.parse(requestJson) as Record<string, string>
      turnId = request['request_id']
      if (typeof turnId !== 'string' || turnId.length === 0) throw new Error('missing request_id')
    } catch (_) {
      throw new AgentRuntimeError('invalid_input', 'turn request JSON is invalid', -2)
    }
    this.activeTurnId = turnId
    this.terminalPromise = new Promise<string>((resolve, reject) => {
      this.resolveTerminal = resolve
      this.rejectTerminal = reject
    })
    const token = agentNative.submitTurn(this.handle, requestJson)
    if (token === 0n) {
      this.terminalPromise = null
      this.resolveTerminal = null
      this.rejectTerminal = null
      this.activeTurnId = ''
      throw new AgentRuntimeError('submit_failed', 'submit turn failed')
    }
    this.activeToken = this.resolveTerminal === null && this.rejectTerminal === null ? 0n : token
    return token
  }

  completeDriverCall(callId: bigint, resultJson: string): void {
    this.ensureOpen()
    this.checkStatus(agentNative.completeDriverCall(this.handle, callId, resultJson), 'complete_driver_call')
  }

  cancel(turnToken: bigint): void {
    this.ensureOpen()
    this.checkStatus(agentNative.cancelTurn(this.handle, turnToken), 'cancel')
  }

  waitForTerminal(timeoutMs: number = 30000): Promise<string> {
    if (this.terminalPromise === null) {
      return Promise.reject(new AgentRuntimeError('turn_not_found', 'no submitted turn', -7))
    }
    const terminal = this.terminalPromise
    return new Promise<string>((resolve, reject) => {
      const timer = setTimeout(() => reject(
        new AgentRuntimeError('timeout', 'terminal wait timed out', -10)), timeoutMs)
      terminal.then((type: string) => { clearTimeout(timer); resolve(type) })
        .catch((error: Error) => { clearTimeout(timer); reject(error) })
    })
  }

  steer(turnToken: bigint, steerJson: string): void {
    this.ensureOpen()
    this.checkStatus(agentNative.steerTurn(this.handle, turnToken, steerJson), 'steer')
  }

  async close(): Promise<void> {
    if (this.handle === 0n) return
    let freeStatus: number = 0
    try {
      if (this.activeToken !== 0n && this.terminalPromise !== null) {
        const cancelStatus = agentNative.cancelTurn(this.handle, this.activeToken)
        if (cancelStatus !== 0) {
          const reject = this.rejectTerminal
          this.rejectTerminal = null
          this.resolveTerminal = null
          this.activeToken = 0n
          this.activeTurnId = ''
          if (reject !== null) reject(new AgentRuntimeError('cancel_failed', 'cancel failed', cancelStatus))
          try { await this.terminalPromise } catch (_) {
            // Consume the control-plane rejection before releasing native state.
          }
        } else {
          try { await this.waitForTerminal(5000) } catch (_) {
            const pendingReject = this.rejectTerminal
            this.rejectTerminal = null
            this.resolveTerminal = null
            this.activeToken = 0n
            this.activeTurnId = ''
            if (pendingReject !== null) {
              pendingReject(new AgentRuntimeError('timeout', 'terminal wait timed out', -10))
            }
          }
        }
      }
    } finally {
      freeStatus = agentNative.runtimeFree(this.handle)
      this.handle = 0n
      this.activeToken = 0n
      this.activeTurnId = ''
      this.resolveTerminal = null
      this.rejectTerminal = null
      this.terminalPromise = null
    }
    if (freeStatus !== 0) throw new AgentRuntimeError('runtime_cleanup_failed', 'runtime cleanup failed', freeStatus)
  }
}
