import { AgentRuntime, AgentRuntimeError } from '@notemeld/agent-sdk'

export async function runNativeSmoke(): Promise<void> {
  const runtime = new AgentRuntime('{"schema_version":"1"}', (_eventJson: string) => {}, (_requestJson: string) => {
    return '{"schema_version":"1","ok":true,"chunks":[{"type":"content_delta","delta":"harmony hello"}],"completion":{"content":"harmony hello","tool_calls":[],"finish_reason":"stop","usage":{"input_tokens":1,"output_tokens":1,"cache_read_tokens":0,"cache_write_tokens":0}}}'
  })
  const token = runtime.submitTurn('{"schema_version":"1","request_id":"66666666-6666-4666-8666-666666666666","session_id":"harmony-harness","input":{"text":"hello","attachments":[],"context_refs":[]},"model_override":null,"approval_mode":"interactive"}')
  if (token === 0n || await runtime.waitForTerminal() !== 'turn.succeeded') {
    throw new Error('Harmony harness did not observe turn.succeeded')
  }
  let unsupported = false
  try { runtime.steer(token, '{"text":"later"}') }
  catch (error) { unsupported = error instanceof AgentRuntimeError && error.status === -6 }
  if (!unsupported) throw new Error('steer must be unsupported')
  await runtime.close()
}
