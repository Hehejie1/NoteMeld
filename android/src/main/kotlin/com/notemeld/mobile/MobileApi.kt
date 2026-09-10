package com.notemeld.mobile

import android.os.Build
import org.json.JSONArray
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL

/** Small host adapter: native UI reads local NoteMeld conversations, never fabricates task cards. */
object MobileApi {
    /**
     * The emulator exposes the host through 10.0.2.2. A physical device uses
     * loopback so a USB `adb reverse tcp:8483 tcp:8483` or an explicit LAN
     * endpoint can be used without pretending that the device is an emulator.
     */
    fun defaultBaseUrl(): String = if (
        Build.FINGERPRINT.contains("generic", ignoreCase = true) ||
        Build.HARDWARE.contains("goldfish", ignoreCase = true) ||
        Build.HARDWARE.contains("ranchu", ignoreCase = true)
    ) "http://10.0.2.2:8483" else "http://127.0.0.1:8483"

    fun recordProjectionCursor(deviceId: String, baseUrl: String = defaultBaseUrl()): Boolean {
        if (deviceId.isBlank()) return false
        val projection = URL("$baseUrl/api/mobile/projection?workspace_id=default").openConnection() as HttpURLConnection
        return try {
            projection.connectTimeout = 4000
            projection.readTimeout = 8000
            projection.requestMethod = "GET"
            if (projection.responseCode !in 200..299) return false
            val envelope = JSONObject(projection.inputStream.bufferedReader().use { it.readText() })
            val revision = envelope.optJSONObject("data")?.optJSONObject("workspace")?.optInt("revision", 0) ?: 0
            val cursor = URL("$baseUrl/api/mobile/sync-cursor").openConnection() as HttpURLConnection
            try {
                cursor.connectTimeout = 4000
                cursor.readTimeout = 8000
                cursor.requestMethod = "PUT"
                cursor.doOutput = true
                cursor.setRequestProperty("Content-Type", "application/json")
                val body = JSONObject().put("device_id", deviceId).put("workspace_id", "default").put("snapshot_revision", revision).put("event_sequence", 0).toString()
                cursor.outputStream.use { it.write(body.toByteArray(Charsets.UTF_8)) }
                cursor.responseCode in 200..299
            } finally { cursor.disconnect() }
        } catch (_: Exception) { false } finally { projection.disconnect() }
    }

    fun deleteConversation(id: String, baseUrl: String = defaultBaseUrl()): Boolean {
        if (id.isBlank()) return false
        val connection = URL("$baseUrl/api/conversations/${java.net.URLEncoder.encode(id, "UTF-8")}").openConnection() as HttpURLConnection
        return try {
            connection.connectTimeout = 4000
            connection.readTimeout = 8000
            connection.requestMethod = "DELETE"
            connection.responseCode in 200..299
        } catch (_: Exception) { false } finally { connection.disconnect() }
    }

    fun createMemory(content: String, baseUrl: String = defaultBaseUrl()): Boolean {
        if (content.isBlank()) return false
        val connection = URL("$baseUrl/api/mobile/memories").openConnection() as HttpURLConnection
        return try {
            connection.connectTimeout = 4000
            connection.readTimeout = 8000
            connection.requestMethod = "POST"
            connection.doOutput = true
            connection.setRequestProperty("Content-Type", "application/json")
            val body = "{\"workspace_id\":\"default\",\"content\":${JSONObject.quote(content.trim())},\"source\":\"android\"}"
            connection.outputStream.use { it.write(body.toByteArray(Charsets.UTF_8)) }
            connection.responseCode in 200..299 && JSONObject(connection.inputStream.bufferedReader().use { it.readText() }).optInt("code", -1) == 0
        } catch (_: Exception) { false } finally { connection.disconnect() }
    }

    fun loadProjection(baseUrl: String = defaultBaseUrl()): List<String> {
        val connection = URL("$baseUrl/api/mobile/projection?workspace_id=default").openConnection() as HttpURLConnection
        return try {
            connection.connectTimeout = 4000
            connection.readTimeout = 8000
            connection.requestMethod = "GET"
            if (connection.responseCode !in 200..299) return emptyList()
            val body = connection.inputStream.bufferedReader().use { it.readText() }
            val data = JSONObject(body).optJSONObject("data") ?: return emptyList()
            val rows = data.optJSONArray("memories") ?: return emptyList()
            buildList { for (index in 0 until rows.length()) rows.optJSONObject(index)?.optString("content")?.takeIf { it.isNotBlank() }?.let(::add) }
        } finally { connection.disconnect() }
    }

    fun loadTasks(baseUrl: String = defaultBaseUrl()): List<MobileTask> {
        val connection = URL("$baseUrl/api/conversations?limit=20").openConnection() as HttpURLConnection
        return try {
            connection.connectTimeout = 4000
            connection.readTimeout = 8000
            connection.requestMethod = "GET"
            if (connection.responseCode !in 200..299) return emptyList()
            val body = connection.inputStream.bufferedReader().use { it.readText() }
            val envelope = JSONObject(body)
            val rows = envelope.optJSONArray("data") ?: JSONArray()
            buildList {
                for (index in 0 until rows.length()) {
                    val row = rows.optJSONObject(index) ?: continue
                    add(MobileTask(row.optString("id"), row.optString("title", "未命名会话"), row.optString("status", "idle")))
                }
            }
        } finally { connection.disconnect() }
    }

    fun streamAgent(input: String, onMessage: (String, Boolean) -> Unit, baseUrl: String = defaultBaseUrl()) {
        val session = postJson("$baseUrl/api/agent/v1/sessions", "{\"title\":\"NoteMeld Mobile\"}")
        val sessionId = JSONObject(session).getJSONObject("data").getString("id")
        val turn = postJson("$baseUrl/api/agent/v1/sessions/$sessionId/turns", "{\"input\":${JSONObject.quote(input)}}")
        val turnId = JSONObject(turn).getJSONObject("data").getString("turn_id")
        val connection = URL("$baseUrl/api/agent/v1/turns/$turnId/events?after_sequence=-1").openConnection() as HttpURLConnection
        try {
            connection.connectTimeout = 4000; connection.readTimeout = 30_000
            connection.setRequestProperty("Accept", "text/event-stream")
            if (connection.responseCode !in 200..299) throw IllegalStateException("agent events: ${connection.responseCode}")
            var eventType = ""
            connection.inputStream.bufferedReader().useLines { lines ->
                var data = StringBuilder()
                lines.forEach { line ->
                    when {
                        line.startsWith("event:") -> eventType = line.substringAfter(':').trim()
                        line.startsWith("data:") -> data.append(line.substringAfter(':').trim())
                        line.isEmpty() && data.isNotEmpty() -> {
                            val event = JSONObject(data.toString())
                            val content = event.optJSONObject("payload")?.optString("content", "") ?: ""
                            if (content.isNotBlank()) onMessage(content, false)
                            if (eventType.startsWith("turn.")) { onMessage("", true); return@forEach }
                            data = StringBuilder(); eventType = ""
                        }
                    }
                }
            }
        } finally { connection.disconnect() }
    }

    private fun postJson(url: String, body: String): String {
        val connection = URL(url).openConnection() as HttpURLConnection
        return try {
            connection.connectTimeout = 4000; connection.readTimeout = 15_000; connection.requestMethod = "POST"; connection.doOutput = true
            connection.setRequestProperty("Content-Type", "application/json")
            connection.outputStream.use { it.write(body.toByteArray(Charsets.UTF_8)) }
            if (connection.responseCode !in 200..299) throw IllegalStateException("agent request: ${connection.responseCode}")
            connection.inputStream.bufferedReader().use { it.readText() }
        } finally { connection.disconnect() }
    }
}
