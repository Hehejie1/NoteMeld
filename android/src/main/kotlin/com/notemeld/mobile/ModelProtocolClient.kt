package com.notemeld.mobile

import org.json.JSONArray
import org.json.JSONObject
import java.io.Reader
import java.net.HttpURLConnection
import java.net.URL

/**
 * 模型协议直连客户端（notemeld.model-add.v1）：三协议的「拉取模型列表」与「测试连接」。
 *
 * 安卓端浏览器/前端不经过 NoteMeld 后端，直接对 Provider 出网；密钥只在本进程内存中使用，
 * 不写日志、不落盘。明文 HTTP 仅允许本机/局域网地址（配合 res/xml/network_security_config.xml）。
 *
 * - openai-compatible：GET  {base_url}/models（Bearer）；测试 POST {base_url}/chat/completions
 * - anthropic-messages：无列表端点，返回内置 3 模型；测试 POST {base_url}/v1/messages（x-api-key）
 * - ollama：             GET  {base_url}/api/tags（免 Key），测试同端点
 */
class ModelProtocolClient(
    private val connectTimeoutMs: Int = 8_000,
    private val readTimeoutMs: Int = 12_000,
) {

    data class RemoteModel(
        val id: String,
        val contextWindow: Int,
    )

    class ProtocolException(message: String) : Exception(message)

    /**
     * 拉取模型列表。
     * @throws ProtocolException 中文脱敏错误信息（不含请求细节/密钥）
     */
    fun discover(protocol: String, baseUrl: String, apiKey: String = ""): List<RemoteModel> {
        val normalizedProtocol = normalizeProtocol(protocol)
        val normalizedUrl = requireUrl(baseUrl)
        return when (normalizedProtocol) {
            "ollama" -> parseOllama(httpGet("$normalizedUrl/api/tags"))
            "anthropic-messages" -> VendorRegistry.ANTHROPIC_BUILTIN_MODELS.map {
                RemoteModel(it.id, it.contextWindow ?: VendorRegistry.DEFAULT_CONTEXT)
            }
            else -> parseOpenAiModels(httpGet("$normalizedUrl/models", bearer(apiKey)))
        }
    }

    /**
     * 最小连接测试；网络/状态码/响应结构失败返回 false，参数缺失抛 [ProtocolException]。
     */
    fun testConnection(protocol: String, baseUrl: String, apiKey: String = "", modelId: String = ""): Boolean {
        val normalizedProtocol = normalizeProtocol(protocol)
        val normalizedUrl = requireUrl(baseUrl)
        return when (normalizedProtocol) {
            "ollama" -> runCatching {
                httpGet("$normalizedUrl/api/tags")
                true
            }.getOrDefault(false)
            "anthropic-messages" -> {
                if (apiKey.isBlank()) throw ProtocolException("请填写 API 密钥")
                if (modelId.isBlank()) throw ProtocolException("请选择或填写要测试的模型 ID")
                testAnthropic(normalizedUrl, apiKey, modelId)
            }
            else -> {
                if (apiKey.isBlank()) throw ProtocolException("请填写 API 密钥")
                if (modelId.isBlank()) throw ProtocolException("请选择或填写要测试的模型 ID")
                testOpenAiChat(normalizedUrl, apiKey, modelId)
            }
        }
    }

    private fun parseOpenAiModels(body: String): List<RemoteModel> {
        val data = runCatching { JSONObject(body) }.getOrElse {
            throw ProtocolException("获取模型列表失败")
        }
        val rows: JSONArray = data.optJSONArray("data")
            ?: throw ProtocolException("获取模型列表失败")
        val result = mutableListOf<RemoteModel>()
        for (i in 0 until rows.length()) {
            val id = rows.optJSONObject(i)?.optString("id")?.takeIf { it.isNotBlank() }
            if (id != null) result.add(RemoteModel(id, VendorRegistry.DEFAULT_CONTEXT))
        }
        if (result.isEmpty()) throw ProtocolException("未获取到模型，请检查服务地址或手动添加")
        return result
    }

    private fun parseOllama(body: String): List<RemoteModel> {
        val data = runCatching { JSONObject(body) }.getOrElse {
            throw ProtocolException("Ollama 返回内容不是有效 JSON")
        }
        val rows = data.optJSONArray("models")
            ?: throw ProtocolException("未获取到模型，请先在 Ollama 中拉取模型")
        val result = mutableListOf<RemoteModel>()
        for (i in 0 until rows.length()) {
            val id = rows.optJSONObject(i)?.optString("name")?.takeIf { it.isNotBlank() }
            if (id != null) result.add(RemoteModel(id, VendorRegistry.DEFAULT_CONTEXT))
        }
        if (result.isEmpty()) throw ProtocolException("未获取到模型，请先在 Ollama 中拉取模型")
        return result
    }

    private fun testOpenAiChat(baseUrl: String, apiKey: String, modelId: String): Boolean =
        runCatching {
            val payload = JSONObject()
                .put("model", modelId)
                .put("messages", JSONArray().put(
                    JSONObject().put("role", "user").put("content", "ping"),
                ))
                .put("max_tokens", 1)
                .put("stream", false)
            val body = httpPost("$baseUrl/chat/completions", payload, bearer(apiKey))
            JSONObject(body).optJSONArray("choices") != null
        }.getOrDefault(false)

    private fun testAnthropic(baseUrl: String, apiKey: String, modelId: String): Boolean =
        runCatching {
            val payload = JSONObject()
                .put("model", modelId)
                .put("max_tokens", 1)
                .put("messages", JSONArray().put(
                    JSONObject().put("role", "user").put("content", "ping"),
                ))
            val headers = mapOf(
                "x-api-key" to apiKey,
                "anthropic-version" to ANTHROPIC_VERSION,
            )
            val body = httpPost("$baseUrl/v1/messages", payload, headers)
            val response = JSONObject(body)
            response.opt("content") != null || response.optString("id").isNotBlank()
        }.getOrDefault(false)

    private fun bearer(apiKey: String): Map<String, String> =
        if (apiKey.isBlank()) emptyMap() else mapOf("Authorization" to "Bearer $apiKey")

    private fun normalizeProtocol(protocol: String): String {
        val normalized = (protocol ?: "").trim()
        if (VendorRegistry.getProtocol(normalized) == null) {
            throw ProtocolException("请选择协议类型")
        }
        return normalized
    }

    private fun requireUrl(baseUrl: String): String {
        val normalized = VendorRegistry.trimUrl(baseUrl)
        if (normalized.isBlank()) throw ProtocolException("请填写接口地址")
        if (!VendorRegistry.isValidHttpUrl(normalized)) throw ProtocolException("地址格式不正确")
        if (!VendorRegistry.isLocalUrl(normalized) && !normalized.startsWith("https://", ignoreCase = true)) {
            throw ProtocolException("非本机地址必须使用 HTTPS")
        }
        return normalized
    }

    private fun httpGet(urlText: String, headers: Map<String, String> = emptyMap()): String =
        request("GET", urlText, headers, null)

    private fun httpPost(urlText: String, payload: JSONObject, headers: Map<String, String>): String =
        request("POST", urlText, headers, payload)

    private fun request(
        method: String,
        urlText: String,
        headers: Map<String, String>,
        payload: JSONObject?,
    ): String {
        var connection: HttpURLConnection? = null
        try {
            connection = (URL(urlText).openConnection() as HttpURLConnection).apply {
                connectTimeout = connectTimeoutMs
                readTimeout = readTimeoutMs
                requestMethod = method
                instanceFollowRedirects = false
            }
            connection.setRequestProperty("Accept", "application/json")
            headers.forEach { (key, value) -> connection.setRequestProperty(key, value) }
            if (payload != null) {
                connection.doOutput = true
                connection.setRequestProperty("Content-Type", "application/json")
                connection.outputStream.use {
                    it.write(payload.toString().toByteArray(Charsets.UTF_8))
                }
            }
            val status = connection.responseCode
            if (status !in 200..299) throw ProtocolException("请求失败（HTTP $status）")
            val stream = connection.inputStream
            return stream.bufferedReader().use { readBounded(it, MAX_RESPONSE_CHARS) }
        } catch (error: ProtocolException) {
            throw error
        } catch (error: Exception) {
            throw ProtocolException(networkErrorMessage(urlText))
        } finally {
            connection?.disconnect()
        }
    }

    private fun networkErrorMessage(urlText: String): String =
        if (VendorRegistry.isLocalUrl(urlText)) {
            "无法连接本地服务，请确认服务已启动且地址正确"
        } else {
            "网络请求失败，请检查地址或稍后重试"
        }

    private fun readBounded(reader: Reader, maxChars: Int): String {
        val output = StringBuilder()
        val buffer = CharArray(8 * 1024)
        while (true) {
            val count = reader.read(buffer)
            if (count < 0) break
            if (output.length + count > maxChars) throw ProtocolException("响应内容过大")
            output.append(buffer, 0, count)
        }
        return output.toString()
    }

    companion object {
        private const val ANTHROPIC_VERSION = "2023-06-01"
        private const val MAX_RESPONSE_CHARS = 4 * 1024 * 1024
    }
}
