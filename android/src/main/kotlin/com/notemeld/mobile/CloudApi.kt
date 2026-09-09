package com.notemeld.mobile

import android.content.Context
import android.util.Base64
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import java.util.UUID
import java.security.KeyStore
import java.security.KeyPair
import java.security.KeyPairGenerator
import java.security.KeyFactory
import java.security.spec.PKCS8EncodedKeySpec
import java.security.spec.X509EncodedKeySpec
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

private class AndroidTokenStore(context: Context) {
    private val prefs = context.getSharedPreferences("notemeld-cloud", Context.MODE_PRIVATE)
    private val alias = "notemeld-cloud-token"
    private fun key(): SecretKey {
        val store = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        (store.getKey(alias, null) as? SecretKey)?.let { return it }
        val generator = KeyGenerator.getInstance("AES", "AndroidKeyStore")
        generator.init(android.security.keystore.KeyGenParameterSpec.Builder(alias, android.security.keystore.KeyProperties.PURPOSE_ENCRYPT or android.security.keystore.KeyProperties.PURPOSE_DECRYPT).setBlockModes(android.security.keystore.KeyProperties.BLOCK_MODE_GCM).setEncryptionPaddings(android.security.keystore.KeyProperties.ENCRYPTION_PADDING_NONE).build())
        return generator.generateKey()
    }
    fun save(value: String) {
        val cipher = Cipher.getInstance("AES/GCM/NoPadding").apply { init(Cipher.ENCRYPT_MODE, key()) }
        val packed = cipher.iv + cipher.doFinal(value.toByteArray(Charsets.UTF_8))
        prefs.edit().putString("token", Base64.encodeToString(packed, Base64.NO_WRAP)).apply()
    }
    fun load(): String? = prefs.getString("token", null)?.let { encoded -> runCatching { val packed = Base64.decode(encoded, Base64.NO_WRAP); Cipher.getInstance("AES/GCM/NoPadding").apply { init(Cipher.DECRYPT_MODE, key(), GCMParameterSpec(128, packed.copyOfRange(0, 12))) }.doFinal(packed.copyOfRange(12, packed.size)).toString(Charsets.UTF_8) }.getOrNull() }
}

data class CloudLoginResult(val username: String, val role: String)
data class CloudDevice(val id: String, val displayName: String, val platform: String, val online: Boolean, val publicKey: String? = null, val lanEndpoints: List<String> = emptyList())

private class AndroidRemoteIdentityStore(context: Context) {
    private val prefs = context.getSharedPreferences("notemeld-remote-identity", Context.MODE_PRIVATE)
    private val alias = "notemeld-remote-identity-key"
    private fun key(): SecretKey {
        val store = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        (store.getKey(alias, null) as? SecretKey)?.let { return it }
        val generator = KeyGenerator.getInstance("AES", "AndroidKeyStore")
        generator.init(android.security.keystore.KeyGenParameterSpec.Builder(alias, android.security.keystore.KeyProperties.PURPOSE_ENCRYPT or android.security.keystore.KeyProperties.PURPOSE_DECRYPT).setBlockModes(android.security.keystore.KeyProperties.BLOCK_MODE_GCM).setEncryptionPaddings(android.security.keystore.KeyProperties.ENCRYPTION_PADDING_NONE).build())
        return generator.generateKey()
    }
    fun loadOrCreate(): KeyPair {
        val stored = prefs.getString("private", null)
        if (stored != null) runCatching {
            val packed = Base64.decode(stored, Base64.NO_WRAP)
            val privateBytes = Cipher.getInstance("AES/GCM/NoPadding").apply { init(Cipher.DECRYPT_MODE, key(), GCMParameterSpec(128, packed.copyOfRange(0, 12))) }.doFinal(packed.copyOfRange(12, packed.size))
            val publicBytes = Base64.decode(prefs.getString("public", ""), Base64.NO_WRAP)
            return KeyPair(KeyFactory.getInstance("Ed25519").generatePublic(X509EncodedKeySpec(publicBytes)), KeyFactory.getInstance("Ed25519").generatePrivate(PKCS8EncodedKeySpec(privateBytes)))
        }
        val pair = KeyPairGenerator.getInstance("Ed25519").generateKeyPair()
        val cipher = Cipher.getInstance("AES/GCM/NoPadding").apply { init(Cipher.ENCRYPT_MODE, key()) }
        prefs.edit().putString("private", Base64.encodeToString(cipher.iv + cipher.doFinal(pair.private.encoded), Base64.NO_WRAP)).putString("public", Base64.encodeToString(pair.public.encoded, Base64.NO_WRAP)).apply()
        return pair
    }
}

class CloudApi(context: Context) {
    private val appContext = context.applicationContext
    private val tokens = AndroidTokenStore(context.applicationContext)
    private val syncState = context.applicationContext.getSharedPreferences("notemeld-cloud-sync", Context.MODE_PRIVATE)
    // Android Keystore/Ed25519 setup can be slow on a cold emulator. Do not perform
    // it while Compose is constructing the first frame; device registration already
    // runs on the IO dispatcher.
    private val remoteIdentity: KeyPair by lazy(LazyThreadSafetyMode.SYNCHRONIZED) {
        AndroidRemoteIdentityStore(context.applicationContext).loadOrCreate()
    }
    fun publicKeyBase64(): String = Base64.encodeToString(remoteIdentity.public.encoded.takeLast(32).toByteArray(), Base64.URL_SAFE or Base64.NO_WRAP or Base64.NO_PADDING)
    fun login(baseUrl: String, username: String, password: String): CloudLoginResult {
        val response = request(baseUrl, "/v1/auth/login", "POST", null, JSONObject().put("username", username).put("password", password).toString())
        val data = JSONObject(response).getJSONObject("data")
        tokens.save(data.getString("token"))
        return CloudLoginResult(username, data.optString("role", "user"))
    }
    fun dashboard(baseUrl: String): String {
        val token = tokens.load() ?: throw IllegalStateException("未登录 Cloud")
        return request(baseUrl, "/v1/cloud/dashboard", "GET", token, null)
    }
    fun registerDevice(baseUrl: String, deviceId: String, platform: String = "android") {
        val token = tokens.load() ?: throw IllegalStateException("未登录 Cloud")
        request(baseUrl, "/v1/devices/register", "POST", token, JSONObject().put("device_id", deviceId).put("platform", platform).put("display_name", "NoteMeld Android").put("public_key", publicKeyBase64()).toString())
        request(baseUrl, "/v1/devices/$deviceId/heartbeat", "POST", token, "{}")
    }

    fun listDevices(baseUrl: String): List<CloudDevice> {
        val token = tokens.load() ?: throw IllegalStateException("未登录 Cloud")
        val rows = JSONObject(request(baseUrl, "/v1/devices", "GET", token, null)).optJSONArray("data") ?: return emptyList()
        return (0 until rows.length()).map { index ->
            val row = rows.getJSONObject(index)
            val connectivity = row.optJSONObject("connectivity")
            val endpoints = connectivity?.optJSONArray("lan_endpoints")?.let { array -> (0 until array.length()).map { array.getString(it) } } ?: emptyList()
            val publicKey = if (row.has("public_key") && !row.isNull("public_key")) row.getString("public_key") else null
            CloudDevice(row.getString("id"), row.optString("display_name", row.getString("id")), row.optString("platform", "unknown"), row.optBoolean("online", false), publicKey, endpoints)
        }
    }

    fun streamRemoteAgent(baseUrl: String, input: String, host: CloudDevice, deviceId: String, onMessage: (String, Boolean) -> Unit) {
        val token = tokens.load() ?: throw IllegalStateException("未登录 Cloud")
        val session = request(baseUrl, "/v1/sessions", "POST", token, JSONObject().put("kind", "device_remote").put("title", "NoteMeld Android Remote").toString())
        val sessionId = JSONObject(session).getJSONObject("data").getString("id")
        val publicKey = host.publicKey?.let { Base64.decode(it, Base64.URL_SAFE or Base64.NO_WRAP) } ?: throw IllegalStateException("远程设备缺少公钥")
        val transport = AndroidRemoteRelay(baseUrl, token, sessionId, deviceId, host.id, publicKey, host.lanEndpoints, remoteIdentity) { message ->
            runCatching {
                val event = JSONObject(message).optJSONObject("event") ?: JSONObject(message)
                val payload = event.optJSONObject("payload") ?: event
                val output = payload.optString("output", payload.optString("delta", ""))
                if (output.isNotBlank()) onMessage(output, false)
                val status = payload.optString("status")
                if (status == "completed" || status == "failed" || status == "cancelled") onMessage("", true)
            }
        }
        try { transport.connect(); transport.send(input); Thread.sleep(60_000); onMessage("", true) } finally { transport.close() }
    }

    fun streamAgent(baseUrl: String, input: String, attachments: List<MobileAttachment> = emptyList(), onMessage: (String, Boolean) -> Unit) {
        val token = tokens.load() ?: throw IllegalStateException("未登录 Cloud")
        var sessionId = syncState.getString("session_id", null)
        if (sessionId == null) {
            val session = request(baseUrl, "/v1/sessions", "POST", token, JSONObject().put("kind", "cloud_native").put("title", "NoteMeld Mobile").toString())
            sessionId = JSONObject(session).getJSONObject("data").getString("id")
            syncState.edit().putString("session_id", sessionId).putLong("event_sequence", 0L).apply()
        }
        val files = org.json.JSONArray()
        attachments.take(16).forEach { item -> files.put(JSONObject().put("name", item.name).put("size", item.size).put("type", item.type).put("content_base64", item.contentBase64)) }
        request(baseUrl, "/v1/sessions/$sessionId/commands", "POST", token, JSONObject().put("request_id", UUID.randomUUID().toString()).put("input", input).put("attachments", files).toString())
        var after = syncState.getLong("event_sequence", 0L).toInt()
        repeat(60) {
            Thread.sleep(500)
            val events = JSONObject(request(baseUrl, "/v1/sessions/$sessionId/events?after=$after", "GET", token, null)).optJSONArray("data") ?: return@repeat
            for (index in 0 until events.length()) {
                val event = events.getJSONObject(index)
                after = maxOf(after, event.optInt("sequence", after))
                syncState.edit().putInt("event_sequence", after).apply()
                val payload = event.optJSONObject("payload")
                val output = payload?.optString("output", "") ?: ""
                if (output.isNotBlank()) onMessage(output, false)
                if (event.optString("event_type").startsWith("command.")) {
                    val status = payload?.optString("status", "") ?: ""
                    if (status == "completed" || status == "failed" || status == "cancelled") { onMessage("", true); return }
                }
            }
        }
        onMessage("Cloud Agent 等待超时", true)
    }
    fun streamAgent(baseUrl: String, input: String, onMessage: (String, Boolean) -> Unit) = streamAgent(baseUrl, input, MobileLocalStore.stagedAttachments(appContext), onMessage)
    private fun request(baseUrl: String, path: String, method: String, token: String?, body: String?): String {
        val connection = URL(baseUrl.trimEnd('/') + path).openConnection() as HttpURLConnection
        return try {
            connection.requestMethod = method; connection.connectTimeout = 5000; connection.readTimeout = 10000
            connection.setRequestProperty("Content-Type", "application/json")
            if (token != null) connection.setRequestProperty("Authorization", "Bearer $token")
            if (body != null) { connection.doOutput = true; connection.outputStream.use { it.write(body.toByteArray(Charsets.UTF_8)) } }
            val code = connection.responseCode
            if (code !in 200..299) throw IllegalStateException("Cloud 请求失败：$code")
            connection.inputStream.bufferedReader().use { it.readText() }
        } finally { connection.disconnect() }
    }
}
