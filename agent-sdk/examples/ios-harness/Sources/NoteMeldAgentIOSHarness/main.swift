import Foundation
import NoteMeldAgentSDK

var terminal: String?
let runtime = try NoteMeldAgentRuntime(driver: { request in
    precondition(request["schema_version"] as? String == "1")
    return [
        "schema_version": "1", "ok": true,
        "result": [
            "chunks": [["type": "content_delta", "delta": "swift hello"]],
            "completion": [
                "content": "swift hello", "tool_calls": [], "finish_reason": "stop",
                "usage": ["input_tokens": 1, "output_tokens": 1,
                          "cache_read_tokens": 0, "cache_write_tokens": 0]
            ]
        ]
    ]
}, onEvent: { event in terminal = event["type"] as? String })
let token = try runtime.submit([
    "schema_version": "1",
    "request_id": "44444444-4444-4444-8444-444444444444",
    "session_id": "swift-harness",
    "input": ["text": "hello", "attachments": [], "context_refs": []],
    "model_override": NSNull(), "approval_mode": "interactive"
])
try runtime.wait(token, timeoutMs: 5_000)
precondition(terminal == "turn.succeeded")
runtime.close()
print("swift harness: turn.succeeded")
