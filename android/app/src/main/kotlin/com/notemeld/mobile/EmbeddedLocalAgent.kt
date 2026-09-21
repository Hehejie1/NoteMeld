package com.notemeld.mobile

import android.content.Context
import com.notemeld.runtime.AgentRuntime
import com.notemeld.runtime.ModelDriver
import com.notemeld.runtime.ToolDriver
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.net.HttpURLConnection
import java.net.URL
import java.io.Reader
import java.util.UUID

/** Owns the embedded SDK runtime for LOCAL mode; it never calls the NoteMeld backend. */
class EmbeddedLocalAgent(context: Context, private val onEvent: (JSONObject) -> Unit) : AutoCloseable {
    private val appContext = context.applicationContext
    private val prefs = appContext.getSharedPreferences("notemeld-mobile-state", Context.MODE_PRIVATE)
    private val secretStore = ModelProviderSecretStore(appContext)
    private val dao = ModelDao(appContext)
    private val workspaceRoot = File(appContext.filesDir, "local-workspace")
    private val localTools = JSONArray().apply {
        put(JSONObject().put("name", "workspace.list").put("description", "List files in the local mobile workspace.").put("parameters", JSONObject().put("type", "object").put("properties", JSONObject().put("prefix", JSONObject().put("type", "string"))).put("additionalProperties", false)).put("risk", "read_only").put("safe", true))
        put(JSONObject().put("name", "workspace.read").put("description", "Read a UTF-8 text file from the local mobile workspace.").put("parameters", JSONObject().put("type", "object").put("properties", JSONObject().put("path", JSONObject().put("type", "string"))).put("required", JSONArray().put("path")).put("additionalProperties", false)).put("risk", "read_only").put("safe", true))
    }
    private val runtime = AgentRuntime(
        modelDriver = ModelDriver { request -> model(request) },
        toolDriver = ToolDriver { request ->
            localTool(request)
        },
        onEvent = onEvent,
    )

    fun submit(input: String): Long {
        val persistedMessages = MobileLocalStore.load(appContext).messages
        // The UI persists the user bubble before invoking this callback. The
        // runtime appends the current input itself, so exclude that trailing
        // bubble to avoid sending the current turn twice after a restart.
        val historyMessages = if (persistedMessages.lastOrNull()?.role == "user" && persistedMessages.last().content == input) {
            persistedMessages.dropLast(1)
        } else {
            persistedMessages
        }
        val history = JSONArray().apply {
            historyMessages.takeLast(200).forEach { message ->
                put(JSONObject().put("role", message.role).put("content", message.content))
            }
        }
        val requestId = UUID.randomUUID().toString()
        MobileLocalStore.markLocalTurnPending(appContext, requestId, input)
        val request = JSONObject()
            .put("schema_version", "1")
            .put("request_id", requestId)
            .put("session_id", "android-local")
            .put("input", JSONObject().put("text", input).put("attachments", JSONArray()).put("context_refs", JSONArray()))
            .put("history", history)
            .put("tools", localTools)
            .put("model_override", JSONObject.NULL)
            .put("approval_mode", "interactive")
        return runtime.submit(request)
    }

    fun await(token: Long) = runtime.wait(token)
    fun cancel(token: Long) = runtime.cancel(token)
    fun steer(token: Long, payload: JSONObject) = runtime.steer(token, payload)

    /** 记录 UI 选中的模型（[ModelRecord.id]）；清空选择后回落到默认模型。 */
    fun selectModel(modelRecordId: String?) {
        prefs.edit().apply {
            if (modelRecordId.isNullOrBlank()) remove(KEY_SELECTED_MODEL)
            else putString(KEY_SELECTED_MODEL, modelRecordId)
        }.apply()
    }

    fun selectedModelRecord(): ModelRecord? = resolveModel()

    override fun close() {
        runtime.close()
        dao.close()
    }

    private fun model(request: JSONObject): JSONObject {
        val payload = request.optJSONObject("payload") ?: JSONObject()
        val messages = payload.optJSONArray("messages") ?: JSONArray()
        val tools = payload.optJSONArray("tools") ?: JSONArray()
        val selected = resolveModel()
            ?: return failure("model_not_configured", "本机 Agent 尚未配置模型 Provider")
        val provider = dao.getProvider(selected.providerId)
            ?: return failure("model_unavailable", "本机模型 Provider 不存在")
        val apiKey = secretStore.get(provider.id)?.trim().orEmpty()
        return when (provider.protocol) {
            "ollama" -> ollamaChat(provider, selected, messages, tools)
            "anthropic-messages" -> anthropicChat(provider, selected, messages, tools, apiKey)
            else -> openAiChat(provider, selected, messages, tools, apiKey)
        }
    }

    /** 选中项失效时回落到默认启用模型，再退化为第一个启用模型。 */
    private fun resolveModel(): ModelRecord? {
        val enabled = dao.listAllModels().filter { it.enabled }
        if (enabled.isEmpty()) return null
        prefs.getString(KEY_SELECTED_MODEL, null)?.let { savedId ->
            enabled.firstOrNull { it.id == savedId }?.let { return it }
        }
        return enabled.firstOrNull { it.isDefault } ?: enabled.first()
    }

    private fun openAiChat(
        provider: ProviderRecord, model: ModelRecord,
        messages: JSONArray, tools: JSONArray, apiKey: String,
    ): JSONObject {
        val body = JSONObject().put("model", model.modelId).put("messages", messages).put("tools", tools).put("stream", false)
        val connection = openPost(provider.baseUrl.trimEnd('/') + "/chat/completions", buildMap {
            if (apiKey.isNotBlank()) put("Authorization", "Bearer $apiKey")
        }, body)
        return try {
            if (connection.responseCode !in 200..299) return failure("model_unavailable", "本机模型 Provider 请求失败")
            val response = JSONObject(readResponse(connection))
            if (response.optString("model", "") != model.modelId) return failure("model_unavailable", "本机模型 Provider 返回模型不匹配")
            val choices = response.optJSONArray("choices")
            if (choices == null || choices.length() != 1) return failure("model_unavailable", "本机模型 Provider 返回 choices 无效")
            val choice = choices.optJSONObject(0)
                ?: return failure("model_unavailable", "本机模型 Provider 返回缺少 choice")
            val message = choice.optJSONObject("message") ?: JSONObject()
            val finishReason = choice.optString("finish_reason", "")
            val providerCalls = message.optJSONArray("tool_calls") ?: JSONArray()
            validateOpenAiToolCalls(providerCalls, finishReason)?.let { return it }
            val content = message.optString("content", "")
            if (finishReason == "stop" && (content.isBlank() || content.length > MAX_CONTENT_CHARS)) return failure("model_unavailable", "本机模型 Provider 返回内容无效")
            val toolCalls = mapOpenAiToolCalls(providerCalls) ?: return failure("model_unavailable", "本机模型 Provider tool call 无效")
            val usage = response.optJSONObject("usage") ?: JSONObject()
            success(
                content, toolCalls, finishReason,
                usage.optInt("prompt_tokens", 0), usage.optInt("completion_tokens", 0),
            )
        } catch (_: Exception) {
            failure("model_unavailable", "本机模型 Provider 不可用")
        } finally {
            connection.disconnect()
        }
    }

    /** 终态与数量约束；通过时返回 null。 */
    private fun validateOpenAiToolCalls(providerCalls: JSONArray, finishReason: String): JSONObject? {
        if (providerCalls.length() > MAX_TOOL_CALLS) return failure("model_unavailable", "本机模型 Provider 返回 tool call 过多")
        if (providerCalls.length() > 0 && finishReason != "tool_calls") return failure("model_unavailable", "本机模型 Provider tool call 终态无效")
        if (providerCalls.length() == 0 && finishReason != "stop") return failure("model_unavailable", "本机模型 Provider 终态无效")
        return null
    }

    private fun mapOpenAiToolCalls(providerCalls: JSONArray): JSONArray? {
        val toolCalls = JSONArray()
        val seenCallIds = mutableSetOf<String>()
        for (index in 0 until providerCalls.length()) {
            val providerCall = providerCalls.optJSONObject(index) ?: return null
            if (providerCall.optString("type", "") != "function") return null
            val callId = providerCall.optString("id", "")
            if (callId.isBlank() || !seenCallIds.add(callId)) return null
            val function = providerCall.optJSONObject("function") ?: return null
            val toolName = function.optString("name", "")
            if (toolName.isBlank()) return null
            val rawArguments = function.opt("arguments")
            val arguments = when (rawArguments) {
                is JSONObject -> rawArguments
                is String -> runCatching { JSONObject(rawArguments) }.getOrElse { return null }
                else -> return null
            }
            toolCalls.put(JSONObject()
                .put("call_id", callId)
                .put("tool_name", toolName)
                .put("arguments", arguments))
        }
        return toolCalls
    }

    private fun anthropicChat(
        provider: ProviderRecord, model: ModelRecord,
        messages: JSONArray, tools: JSONArray, apiKey: String,
    ): JSONObject {
        if (apiKey.isBlank()) return failure("model_unavailable", "该 Provider 需要 API 密钥，请先在模型设置中填写")
        val connection = openPost(
            provider.baseUrl.trimEnd('/') + "/v1/messages",
            mapOf("x-api-key" to apiKey, "anthropic-version" to ANTHROPIC_VERSION),
            anthropicBody(model, messages, tools),
        )
        return try {
            if (connection.responseCode !in 200..299) return failure("model_unavailable", "本机模型 Provider 请求失败")
            val response = JSONObject(readResponse(connection))
            if (response.optString("id", "").isBlank()) return failure("model_unavailable", "本机模型 Provider 响应无效")
            val stopReason = response.optString("stop_reason", "")
            if (stopReason !in ALLOWED_ANTHROPIC_STOP_REASONS) return failure("model_unavailable", "本机模型 Provider 终态无效")
            val blocks = response.optJSONArray("content")
                ?: return failure("model_unavailable", "本机模型 Provider 返回 content 无效")
            if (blocks.length() > MAX_TOOL_CALLS * 2) return failure("model_unavailable", "本机模型 Provider 返回内容块过多")
            val text = StringBuilder()
            val toolCalls = JSONArray()
            val seenCallIds = mutableSetOf<String>()
            for (index in 0 until blocks.length()) {
                val block = blocks.optJSONObject(index) ?: continue
                when (block.optString("type")) {
                    "text" -> text.append(block.optString("text"))
                    "tool_use" -> {
                        val callId = block.optString("id", "")
                        if (callId.isBlank() || !seenCallIds.add(callId)) return failure("model_unavailable", "本机模型 Provider tool call ID 无效")
                        val toolName = block.optString("name", "")
                        if (toolName.isBlank()) return failure("model_unavailable", "本机模型 Provider tool name 无效")
                        val input = block.optJSONObject("input")
                            ?: runCatching { JSONObject(block.optString("input", "{}")) }.getOrElse { return failure("model_unavailable", "本机模型 Provider tool arguments 无效") }
                        toolCalls.put(JSONObject()
                            .put("call_id", callId)
                            .put("tool_name", toolName)
                            .put("arguments", input))
                    }
                }
            }
            if (toolCalls.length() > MAX_TOOL_CALLS) return failure("model_unavailable", "本机模型 Provider 返回 tool call 过多")
            val content = text.toString()
            val finishReason = if (stopReason == "tool_use" || toolCalls.length() > 0) "tool_calls" else "stop"
            if (finishReason == "tool_calls" && toolCalls.length() == 0) return failure("model_unavailable", "本机模型 Provider tool call 无效")
            if (finishReason == "stop" && (content.isBlank() || content.length > MAX_CONTENT_CHARS)) return failure("model_unavailable", "本机模型 Provider 返回内容无效")
            val usage = response.optJSONObject("usage") ?: JSONObject()
            success(
                content, toolCalls, finishReason,
                usage.optInt("input_tokens", 0), usage.optInt("output_tokens", 0),
            )
        } catch (_: Exception) {
            failure("model_unavailable", "本机模型 Provider 不可用")
        } finally {
            connection.disconnect()
        }
    }

    /** OpenAI 形态 messages/tools → Anthropic Messages 请求体。 */
    private fun anthropicBody(model: ModelRecord, messages: JSONArray, tools: JSONArray): JSONObject {
        val systemParts = StringBuilder()
        val out = JSONArray()
        var index = 0
        while (index < messages.length()) {
            val msg = messages.optJSONObject(index)
            if (msg == null) { index++; continue }
            when (msg.optString("role")) {
                "system" -> {
                    systemParts.append(msg.optString("content")).append('\n'); index++
                }
                "tool" -> {
                    // Anthropic 要求一个 user 轮次承载所有 tool_result 块
                    val blocks = JSONArray()
                    while (index < messages.length() && messages.optJSONObject(index)?.optString("role") == "tool") {
                        val toolMsg = messages.optJSONObject(index)
                        blocks.put(JSONObject()
                            .put("type", "tool_result")
                            .put("tool_call_id", toolMsg?.optString("tool_call_id") ?: "")
                            .put("content", toolMsg?.optString("content") ?: ""))
                        index++
                    }
                    out.put(JSONObject().put("role", "user").put("content", blocks))
                }
                "assistant" -> {
                    val calls = msg.optJSONArray("tool_calls")
                    if (calls != null && calls.length() > 0) {
                        val blocks = JSONArray()
                        msg.optString("content").takeIf { it.isNotBlank() }?.let {
                            blocks.put(JSONObject().put("type", "text").put("text", it))
                        }
                        for (callIndex in 0 until calls.length()) {
                            val call = calls.optJSONObject(callIndex)
                            val function = call?.optJSONObject("function")
                            val rawArguments = function?.opt("arguments")
                            val input = when (rawArguments) {
                                is JSONObject -> rawArguments
                                is String -> runCatching { JSONObject(rawArguments) }.getOrDefault(JSONObject())
                                else -> JSONObject()
                            }
                            blocks.put(JSONObject()
                                .put("type", "tool_use")
                                .put("id", call?.optString("id")?.takeIf { it.isNotBlank() } ?: "call_$callIndex")
                                .put("name", function?.optString("name") ?: "")
                                .put("input", input))
                        }
                        out.put(JSONObject().put("role", "assistant").put("content", blocks))
                    } else {
                        out.put(JSONObject().put("role", "assistant").put("content", msg.optString("content")))
                    }
                    index++
                }
                else -> {
                    out.put(JSONObject().put("role", "user").put("content", msg.optString("content")))
                    index++
                }
            }
        }
        val body = JSONObject()
            .put("model", model.modelId)
            .put("messages", out)
            .put("max_tokens", ANTHROPIC_MAX_TOKENS)
        if (systemParts.isNotBlank()) body.put("system", systemParts.trim().toString())
        if (tools.length() > 0) body.put("tools", translateAnthropicTools(tools))
        return body
    }

    private fun translateAnthropicTools(tools: JSONArray): JSONArray {
        val out = JSONArray()
        for (index in 0 until tools.length()) {
            val tool = tools.optJSONObject(index) ?: continue
            val function = tool.optJSONObject("function") ?: continue
            val schema = function.optJSONObject("parameters") ?: JSONObject().put("type", "object")
            out.put(JSONObject()
                .put("name", function.optString("name"))
                .put("description", function.optString("description"))
                .put("input_schema", schema))
        }
        return out
    }

    private fun ollamaChat(
        provider: ProviderRecord, model: ModelRecord,
        messages: JSONArray, tools: JSONArray,
    ): JSONObject {
        val body = JSONObject().put("model", model.modelId).put("messages", messages).put("stream", false)
        if (tools.length() > 0) body.put("tools", tools)
        val connection = openPost(provider.baseUrl.trimEnd('/') + "/api/chat", emptyMap(), body)
        return try {
            if (connection.responseCode !in 200..299) return failure("model_unavailable", "本机模型 Provider 请求失败")
            val response = JSONObject(readResponse(connection))
            val message = response.optJSONObject("message")
                ?: return failure("model_unavailable", "本机模型 Provider 返回缺少 message")
            val providerCalls = message.optJSONArray("tool_calls") ?: JSONArray()
            if (providerCalls.length() > MAX_TOOL_CALLS) return failure("model_unavailable", "本机模型 Provider 返回 tool call 过多")
            val content = message.optString("content", "")
            // Ollama 各版本 done_reason 对 tool call 不一致，按是否存在 tool_calls 判定终态
            val finishReason = if (providerCalls.length() > 0) "tool_calls" else "stop"
            if (finishReason == "stop" && (content.isBlank() || content.length > MAX_CONTENT_CHARS)) return failure("model_unavailable", "本机模型 Provider 返回内容无效")
            val toolCalls = JSONArray()
            for (index in 0 until providerCalls.length()) {
                val call = providerCalls.optJSONObject(index) ?: return failure("model_unavailable", "本机模型 Provider tool call 无效")
                val function = call.optJSONObject("function")
                    ?: return failure("model_unavailable", "本机模型 Provider tool call 缺少 function")
                val toolName = function.optString("name", "")
                if (toolName.isBlank()) return failure("model_unavailable", "本机模型 Provider tool name 无效")
                val arguments = function.optJSONObject("arguments")
                    ?: runCatching { JSONObject(function.optString("arguments", "{}")) }.getOrElse { return failure("model_unavailable", "本机模型 Provider tool arguments 无效") }
                toolCalls.put(JSONObject()
                    .put("call_id", "ollama_call_${index}_${System.nanoTime()}")
                    .put("tool_name", toolName)
                    .put("arguments", arguments))
            }
            success(
                content, toolCalls, finishReason,
                response.optInt("prompt_eval_count", 0), response.optInt("eval_count", 0),
            )
        } catch (_: Exception) {
            failure("model_unavailable", "本机模型 Provider 不可用")
        } finally {
            connection.disconnect()
        }
    }

    private fun openPost(url: String, headers: Map<String, String>, body: JSONObject): HttpURLConnection {
        val connection = URL(url).openConnection() as HttpURLConnection
        connection.connectTimeout = CONNECT_TIMEOUT_MS
        connection.readTimeout = READ_TIMEOUT_MS
        connection.requestMethod = "POST"
        connection.doOutput = true
        connection.setRequestProperty("Content-Type", "application/json")
        connection.setRequestProperty("Accept", "application/json")
        headers.forEach { (name, value) -> connection.setRequestProperty(name, value) }
        connection.outputStream.use { it.write(body.toString().toByteArray(Charsets.UTF_8)) }
        return connection
    }

    private fun readResponse(connection: HttpURLConnection): String =
        connection.inputStream.bufferedReader().use { readBounded(it, MAX_RESPONSE_CHARS) }

    private fun success(
        content: String, toolCalls: JSONArray, finishReason: String,
        inputTokens: Int, outputTokens: Int,
    ) = JSONObject().put("ok", true).put("result", JSONObject()
        .put("chunks", if (content.isBlank()) JSONArray() else JSONArray().put(JSONObject().put("type", "content_delta").put("delta", content)))
        .put("completion", JSONObject()
            .put("content", content)
            .put("tool_calls", toolCalls)
            .put("finish_reason", finishReason)
            .put("usage", JSONObject()
                .put("input_tokens", inputTokens)
                .put("output_tokens", outputTokens)
                .put("cache_read_tokens", 0)
                .put("cache_write_tokens", 0))))

    private fun localTool(request: JSONObject): JSONObject {
        val payload = request.optJSONObject("payload") ?: JSONObject()
        val name = payload.optString("tool_name")
        val arguments = payload.optJSONObject("arguments") ?: JSONObject()
        return try {
            val output = when (name) {
                "workspace.list" -> {
                    val prefix = arguments.optString("prefix", "")
                    require(prefix.length <= 1024) { "invalid workspace prefix" }
                    val files = JSONArray()
                    workspaceRoot.mkdirs()
                    workspaceRoot.walkTopDown().filter { it.isFile && it.relativeTo(workspaceRoot).path.startsWith(prefix) }.take(200).forEach { files.put(it.relativeTo(workspaceRoot).path) }
                    JSONObject().put("ok", true).put("files", files).put("truncated", files.length() == 200)
                }
                "workspace.read" -> {
                    val path = arguments.optString("path")
                    require(path.isNotBlank() && path.length <= 1024) { "invalid workspace path" }
                    val file = safeWorkspaceFile(path)
                    require(file.isFile) { "workspace file not found" }
                    require(file.length() <= 100_000) { "workspace file is too large" }
                    val bytes = file.readBytes()
                    JSONObject().put("ok", true).put("path", path).put("content", bytes.toString(Charsets.UTF_8)).put("truncated", false)
                }
                else -> return JSONObject().put("ok", false).put("error", JSONObject().put("code", "unknown_tool").put("message", "本机工具不存在或未授权"))
            }
            JSONObject().put("ok", true).put("result", JSONObject().put("output", output))
        } catch (error: Exception) {
            JSONObject().put("ok", true).put("result", JSONObject().put("output", JSONObject().put("ok", false).put("error", JSONObject().put("code", "tool_failed").put("message", error.message ?: "本机工具执行失败"))))
        }
    }

    private fun safeWorkspaceFile(path: String): File {
        val root = workspaceRoot.canonicalFile
        val file = File(root, path).canonicalFile
        require(file == root || file.path.startsWith(root.path + File.separator)) { "invalid workspace path" }
        return file
    }

    private fun failure(code: String, message: String) = JSONObject()
        .put("ok", false)
        .put("error", JSONObject().put("code", code).put("message", message))

    private fun readBounded(reader: Reader, maxChars: Int): String {
        val output = StringBuilder()
        val buffer = CharArray(8 * 1024)
        while (true) {
            val count = reader.read(buffer)
            if (count < 0) break
            if (output.length + count > maxChars) throw IllegalStateException("Provider response exceeds limit")
            output.append(buffer, 0, count)
        }
        return output.toString()
    }

    companion object {
        private const val CONNECT_TIMEOUT_MS = 8_000
        private const val READ_TIMEOUT_MS = 60_000
        private const val MAX_RESPONSE_CHARS = 4 * 1024 * 1024
        private const val MAX_CONTENT_CHARS = 100_000
        private const val MAX_TOOL_CALLS = 16
        private const val KEY_SELECTED_MODEL = "localSelectedModelId"
        private const val ANTHROPIC_VERSION = "2023-06-01"
        private const val ANTHROPIC_MAX_TOKENS = 8_192
        private val ALLOWED_ANTHROPIC_STOP_REASONS = setOf("end_turn", "tool_use", "max_tokens", "stop_sequence")
    }
}
