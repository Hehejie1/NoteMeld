import { AgentRuntime } from '@notemeld/agent-sdk'

let terminal: string = ''
const runtime = new AgentRuntime('{"schema_version":"1"}', (eventJson: string) => {
  const event = JSON.parse(eventJson) as Record<string, string>
  if (event['type'] === 'turn.succeeded') terminal = 'turn.succeeded'
}, (_requestJson: string) => {
  return '{"schema_version":"1","ok":true,"chunks":[{"type":"content_delta","delta":"harmony hello"}],"completion":{"content":"harmony hello","tool_calls":[],"finish_reason":"stop","usage":{"input_tokens":1,"output_tokens":1,"cache_read_tokens":0,"cache_write_tokens":0}}}'
})
const token = runtime.submitTurn('{"schema_version":"1","request_id":"66666666-6666-4666-8666-666666666666","session_id":"harmony-harness","input":{"text":"hello","attachments":[],"context_refs":[]},"model_override":null,"approval_mode":"interactive"}')
if (runtime.wait(token, 5000n) !== 0 || terminal !== 'turn.succeeded') {
  throw new Error('Harmony harness did not observe turn.succeeded')
}
runtime.close()
