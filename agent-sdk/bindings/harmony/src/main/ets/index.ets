import agentNative from 'libnotemeld_agent_napi.so'

export const SDK_VERSION: string = '0.1.0'
export const SCHEMA_VERSION: string = '1'

export type AgentEvent = Record<string, Object>

/** ArkTS only translates JSON and lifecycle calls; event semantics remain Rust v1. */
export class AgentRuntime {
  private handle: bigint

  constructor(
    configJson: string,
    onEvent: (eventJson: string) => void,
    onDriverRequest: (requestJson: string) => string
  ) {
    if (agentNative.sdkVersion() !== SDK_VERSION || agentNative.schemaVersion() !== SCHEMA_VERSION) {
      throw new Error('NoteMeld Agent native version mismatch')
    }
    this.handle = agentNative.runtimeNew(configJson)
    agentNative.setCallbacks(this.handle, onEvent, onDriverRequest)
  }

  submitTurn(requestJson: string): bigint { return agentNative.submitTurn(this.handle, requestJson) }
  completeDriverCall(callId: bigint, resultJson: string): number {
    return agentNative.completeDriverCall(this.handle, callId, resultJson)
  }
  cancel(turnToken: bigint): number { return agentNative.cancelTurn(this.handle, turnToken) }
  wait(turnToken: bigint, timeoutMs: bigint = 30000n): number {
    return agentNative.waitTurn(this.handle, turnToken, timeoutMs)
  }
  steer(turnToken: bigint, steerJson: string): number {
    return agentNative.steerTurn(this.handle, turnToken, steerJson)
  }
  close(): void { agentNative.runtimeFree(this.handle); this.handle = 0n }
}
