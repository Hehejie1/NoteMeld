package wiki.notemeld.agent.harness

import wiki.notemeld.agent.Runtime

/** Called by the target instrumentation job after the matching .so is packaged. */
fun runNativeSmoke() {
    var terminal = ""
    val runtime = Runtime("{\"schema_version\":\"1\"}", driver = {
        """{"schema_version":"1","ok":true,"chunks":[{"type":"content_delta","delta":"android hello"}],"completion":{"content":"android hello","tool_calls":[],"finish_reason":"stop","usage":{"input_tokens":1,"output_tokens":1,"cache_read_tokens":0,"cache_write_tokens":0}}}"""
    }, onEvent = { if (it.contains("\"type\":\"turn.succeeded\"")) terminal = "turn.succeeded" })
    val request = """{"schema_version":"1","request_id":"55555555-5555-4555-8555-555555555555","session_id":"android-harness","input":{"text":"hello","attachments":[],"context_refs":[]},"model_override":null,"approval_mode":"interactive"}"""
    val token = runtime.submitTurn(request)
    check(runtime.wait(token, 5_000u) == 0)
    check(terminal == "turn.succeeded")
    runtime.close()
}
