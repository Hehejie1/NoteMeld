package com.notemeld.runtime

import org.json.JSONObject
import wiki.notemeld.agent.Runtime

/**
 * Android adapter around the standalone SDK AAR.
 *
 * This class owns no loop, terminal state machine, retry policy, or replay logic;
 * all of those remain in the Rust runtime exposed by [Runtime].
 */
class AgentRuntime(
    private val modelDriver: ModelDriver,
    private val toolDriver: ToolDriver,
    private val onEvent: (JSONObject) -> Unit = {},
) : AutoCloseable {
    private val sdk = Runtime(
        driver = { request ->
            when (request.optString("kind")) {
                "tool.invoke" -> toolDriver.invoke(request)
                else -> modelDriver.request(request)
            }
        },
        onEvent = onEvent,
    )

    fun submit(request: JSONObject): Long = sdk.submitTurn(request)
    fun wait(token: Long, timeoutMs: Long = 30_000L) = sdk.wait(token, timeoutMs)
    fun cancel(token: Long) = sdk.cancel(token)
    fun steer(token: Long, payload: JSONObject) = sdk.steer(token, payload)
    fun resolveApproval(approvalId: String, decision: String) = sdk.resolveApproval(approvalId, decision)
    val events: List<JSONObject> get() = sdk.events
    override fun close() = sdk.close()
}
