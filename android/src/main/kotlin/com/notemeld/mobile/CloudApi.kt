package com.notemeld.mobile

import android.content.Context
import android.util.Base64
import org.json.JSONArray
import org.json.JSONObject
import org.bouncycastle.jce.provider.BouncyCastleProvider
import java.net.HttpURLConnection
import java.net.URL
import java.util.UUID
import java.security.KeyStore
import java.security.KeyPair
import java.security.KeyPairGenerator
import java.security.KeyFactory
import java.security.MessageDigest
import java.security.Security
import java.security.Signature
import java.security.spec.PKCS8EncodedKeySpec
import java.security.spec.X509EncodedKeySpec
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
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
    fun clear() { prefs.edit().remove("token").apply() }
    fun load(): String? = prefs.getString("token", null)?.let { encoded -> runCatching { val packed = Base64.decode(encoded, Base64.NO_WRAP); Cipher.getInstance("AES/GCM/NoPadding").apply { init(Cipher.DECRYPT_MODE, key(), GCMParameterSpec(128, packed.copyOfRange(0, 12))) }.doFinal(packed.copyOfRange(12, packed.size)).toString(Charsets.UTF_8) }.getOrNull() }
}

data class CloudLoginResult(val username: String, val role: String)
data class CloudDevice(val id: String, val displayName: String, val platform: String, val online: Boolean, val publicKey: String? = null, val lanEndpoints: List<String> = emptyList())
data class CloudModel(val id: String, val name: String, val model: String, val enabled: Boolean, val isDefault: Boolean)
data class PairedModel(val id: String, val name: String, val provider: String, val model: String, val baseUrl: String, val isDefault: Boolean)
data class CloudSyncState(val revision: Long, val itemCount: Int)
class CloudHttpException(val statusCode: Int, val responseBody: String) : IllegalStateException("Cloud 请求失败：$statusCode")
private fun cloudStateHash(value: String): String = MessageDigest.getInstance("SHA-256").digest(value.toByteArray()).joinToString("") { "%02x".format(it.toInt() and 0xff) }

private class AndroidRemoteIdentityStore(context: Context) {
    private val prefs = context.getSharedPreferences("notemeld-remote-identity", Context.MODE_PRIVATE)
    private val alias = "notemeld-remote-identity-key"

    private fun providerName(): String {
        if (Security.getProvider("BC") !is BouncyCastleProvider) {
            Security.removeProvider("BC")
            Security.addProvider(BouncyCastleProvider())
        }
        return "BC"
    }

    fun loadOrCreate(): KeyPair {
        val stored = prefs.getString("private", null)
        if (stored != null) runCatching {
            val packed = Base64.decode(stored, Base64.NO_WRAP)
            val privateBytes = Cipher.getInstance("AES/GCM/NoPadding").apply {
                init(Cipher.DECRYPT_MODE, key(), GCMParameterSpec(128, packed.copyOfRange(0, 12)))
            }.doFinal(packed.copyOfRange(12, packed.size))
            val publicBytes = Base64.decode(prefs.getString("public", ""), Base64.NO_WRAP)
            return KeyPair(
                KeyFactory.getInstance("Ed25519", providerName()).generatePublic(X509EncodedKeySpec(publicBytes)),
                KeyFactory.getInstance("Ed25519", providerName()).generatePrivate(PKCS8EncodedKeySpec(privateBytes)),
            )
        }

        val pair = KeyPairGenerator.getInstance("Ed25519", providerName()).generateKeyPair()
        val cipher = Cipher.getInstance("AES/GCM/NoPadding").apply { init(Cipher.ENCRYPT_MODE, key()) }
        prefs.edit()
            .putString("private", Base64.encodeToString(cipher.iv + cipher.doFinal(pair.private.encoded), Base64.NO_WRAP))
            .putString("public", Base64.encodeToString(pair.public.encoded, Base64.NO_WRAP))
            .apply()
        return pair
    }

    private fun key(): SecretKey {
        val store = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        (store.getKey(alias, null) as? SecretKey)?.let { return it }
        val generator = KeyGenerator.getInstance("AES", "AndroidKeyStore")
        generator.init(android.security.keystore.KeyGenParameterSpec.Builder(alias, android.security.keystore.KeyProperties.PURPOSE_ENCRYPT or android.security.keystore.KeyProperties.PURPOSE_DECRYPT).setBlockModes(android.security.keystore.KeyProperties.BLOCK_MODE_GCM).setEncryptionPaddings(android.security.keystore.KeyProperties.ENCRYPTION_PADDING_NONE).build())
        return generator.generateKey()
    }
}

/**
 * 配对只下发非敏感模型元数据（配对下发禁令：永不包含 api_key/任何凭据）。
 * 元数据按明文 JSON 保存即可；凭据由本端在 Provider CRUD 中自行录入并由 Keystore 保管。
 */
private class AndroidPairedModelStore(context: Context) {
    private val prefs = context.getSharedPreferences("notemeld-paired-models", Context.MODE_PRIVATE)

    fun save(models: List<PairedModel>) {
        val rows = JSONArray()
        models.forEach { model ->
            rows.put(JSONObject()
                .put("id", model.id).put("name", model.name).put("provider", model.provider)
                .put("model", model.model).put("base_url", model.baseUrl)
                .put("is_default", model.isDefault))
        }
        prefs.edit().putString("bundle", rows.toString()).commit()
    }
}

class CloudApi(context: Context) {
    private val appContext = context.applicationContext
    private val tokens = AndroidTokenStore(context.applicationContext)
    private val syncState = context.applicationContext.getSharedPreferences("notemeld-cloud-sync", Context.MODE_PRIVATE)
    private val pairedModels = AndroidPairedModelStore(context.applicationContext)
    // Android Keystore/Ed25519 setup can be slow on a cold emulator. Do not perform
    // it while Compose is constructing the first frame; device registration already
    // runs on the IO dispatcher.
    private val remoteIdentity: KeyPair by lazy(LazyThreadSafetyMode.SYNCHRONIZED) {
        AndroidRemoteIdentityStore(context.applicationContext).loadOrCreate()
    }
    fun hasAccountToken(): Boolean = tokens.load() != null
    fun clearAccountToken() = tokens.clear()
    /** Revokes the bearer at Cloud before removing the local encrypted copy. */
    fun logout(baseUrl: String): Boolean {
        val token = tokens.load() ?: return true
        val revoked = runCatching {
            request(baseUrl, "/v1/auth/revoke", "POST", token, "{}")
            true
        }.getOrDefault(false)
        tokens.clear()
        return revoked
    }
    fun publicKeyBase64(): String = Base64.encodeToString(remoteIdentity.public.encoded.takeLast(32).toByteArray(), Base64.URL_SAFE or Base64.NO_WRAP or Base64.NO_PADDING)
    fun login(baseUrl: String, username: String, password: String): CloudLoginResult {
        val response = request(baseUrl, "/v1/auth/login", "POST", null, JSONObject().put("username", username).put("password", password).toString())
        val data = JSONObject(response).getJSONObject("data")
        val accountState = cloudStateHash("${baseUrl.trimEnd('/')}\u0000$username")
        if (syncState.getString("account_state", null) != accountState) {
            syncState.edit().clear().putString("account_state", accountState).apply()
        }
        tokens.save(data.getString("token"))
        try {
            verifyCapabilities(baseUrl)
        } catch (error: Throwable) {
            tokens.clear()
            throw error
        }
        return CloudLoginResult(username, data.optString("role", "user"))
    }

    /** Rejects incompatible Cloud protocol/runtime combinations before pairing or sync. */
    fun verifyCapabilities(baseUrl: String) {
        val token = tokens.load() ?: throw IllegalStateException("未登录 Cloud")
        val data = JSONObject(request(baseUrl, "/v1/capabilities", "GET", token, null)).getJSONObject("data")
        val protocol = data.optJSONObject("protocol") ?: throw IllegalStateException("Cloud 缺少协议协商信息")
        val current = protocol.optInt("current", -1)
        val minimum = protocol.optInt("min", -1)
        val maximum = protocol.optInt("max", -1)
        if (current !in minimum..maximum || current != 1 || data.optString("protocol_version") != "notemeld.sync.v1") {
            throw IllegalStateException("Cloud 协议版本不兼容，请升级客户端或服务")
        }
        val runtime = data.optJSONObject("runtime") ?: throw IllegalStateException("Cloud 缺少 runtime 协商信息")
        if (runtime.optString("sdk_version") != "0.1.0" || runtime.optInt("abi", -1) != 1 || runtime.optInt("schema", -1) != 1) {
            throw IllegalStateException("Cloud Agent runtime 版本不兼容，请升级客户端或服务")
        }
        val required = data.optJSONArray("required_features") ?: JSONArray()
        val supported = setOf("config_sync_v1", "e2ee_relay_v1", "durable_receipt_v1")
        for (index in 0 until required.length()) if (!supported.contains(required.optString(index))) {
            throw IllegalStateException("Cloud 缺少客户端所需能力")
        }
    }

    /** Applies only the non-secret Cloud snapshot and advances the durable cursor. */
    fun syncConfig(baseUrl: String, workspaceId: String = "default"): CloudSyncState {
        val token = tokens.load() ?: throw IllegalStateException("未登录 Cloud")
        val after = syncState.getLong("config_revision_$workspaceId", 0L)
        val response = JSONObject(request(baseUrl, "/v1/config-sync/snapshot?workspace_id=${java.net.URLEncoder.encode(workspaceId, "UTF-8")}&after_revision=$after", "GET", token, null))
        val data = response.getJSONObject("data")
        val revision = data.optLong("revision", after)
        val items = syncState.getString("config_items_$workspaceId", "{}")?.let(::JSONObject) ?: JSONObject()
        val rows = data.optJSONArray("items") ?: JSONArray()
        for (index in 0 until rows.length()) {
            val row = rows.getJSONObject(index)
            items.put("${row.optString("kind")}\u0000${row.optString("key")}", row.opt("value"))
        }
        val deleted = data.optJSONArray("deleted") ?: JSONArray()
        for (index in 0 until deleted.length()) {
            val row = deleted.getJSONObject(index)
            items.remove("${row.optString("kind")}\u0000${row.optString("key")}")
        }
        syncState.edit().putLong("config_revision_$workspaceId", revision).putString("config_items_$workspaceId", items.toString()).apply()
        return CloudSyncState(revision, items.length())
    }

    fun cachedSyncState(workspaceId: String = "default"): CloudSyncState {
        val items = syncState.getString("config_items_$workspaceId", "{}")?.let(::JSONObject) ?: JSONObject()
        return CloudSyncState(syncState.getLong("config_revision_$workspaceId", 0L), items.length())
    }

    /** Writes one non-secret shared preference against the cached revision. */
    fun writeConfig(baseUrl: String, kind: String, key: String, value: Any?, workspaceId: String = "default"): CloudSyncState {
        val token = tokens.load() ?: throw IllegalStateException("未登录 Cloud")
        val cached = cachedSyncState(workspaceId)
        val change = JSONObject().put("kind", kind).put("key", key).put("operation", "set").put("value", value)
        val body = JSONObject().put("workspace_id", workspaceId).put("base_revision", cached.revision).put("idempotency_key", UUID.randomUUID().toString()).put("changes", JSONArray().put(change)).toString()
        val response = JSONObject(request(baseUrl, "/v1/config-sync/changes", "POST", token, body)).getJSONObject("data")
        val revision = response.optLong("revision", cached.revision)
        val items = syncState.getString("config_items_$workspaceId", "{}")?.let(::JSONObject) ?: JSONObject()
        items.put("$kind\u0000$key", value)
        syncState.edit().putLong("config_revision_$workspaceId", revision).putString("config_items_$workspaceId", items.toString()).apply()
        return CloudSyncState(revision, items.length())
    }

    /** Writes a durable tombstone; the next snapshot removes it from the cache. */
    fun deleteConfig(baseUrl: String, kind: String, key: String, workspaceId: String = "default"): CloudSyncState {
        val token = tokens.load() ?: throw IllegalStateException("未登录 Cloud")
        val cached = cachedSyncState(workspaceId)
        val change = JSONObject().put("kind", kind).put("key", key).put("operation", "delete")
        val body = JSONObject().put("workspace_id", workspaceId).put("base_revision", cached.revision)
            .put("idempotency_key", UUID.randomUUID().toString()).put("changes", JSONArray().put(change)).toString()
        val response = JSONObject(request(baseUrl, "/v1/config-sync/changes", "POST", token, body)).getJSONObject("data")
        val revision = response.optLong("revision", cached.revision)
        val items = syncState.getString("config_items_$workspaceId", "{}")?.let(::JSONObject) ?: JSONObject()
        items.remove("$kind\u0000$key")
        syncState.edit().putLong("config_revision_$workspaceId", revision).putString("config_items_$workspaceId", items.toString()).apply()
        return CloudSyncState(revision, items.length())
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

    fun listDevices(baseUrl: String, excludeDeviceId: String? = null): List<CloudDevice> {
        val token = tokens.load() ?: throw IllegalStateException("未登录 Cloud")
        val rows = JSONObject(request(baseUrl, "/v1/devices", "GET", token, null)).optJSONArray("data") ?: return emptyList()
        return (0 until rows.length()).mapNotNull { index ->
            val row = rows.getJSONObject(index)
            val id = row.getString("id")
            val platform = row.optString("platform", "unknown")
            if (id == excludeDeviceId || platform != "desktop") return@mapNotNull null
            val connectivity = row.optJSONObject("connectivity")
            val endpoints = connectivity?.optJSONArray("lan_endpoints")?.let { array -> (0 until array.length()).map { array.getString(it) } } ?: emptyList()
            val publicKey = if (row.has("public_key") && !row.isNull("public_key")) row.getString("public_key") else null
            CloudDevice(id, row.optString("display_name", id), platform, row.optBoolean("online", false), publicKey, endpoints)
        }
    }

    /** Returns only non-secret model metadata; provider endpoints and credentials never enter UI state. */
    fun listModels(baseUrl: String): List<CloudModel> {
        val token = tokens.load() ?: throw IllegalStateException("未登录 Cloud")
        val rows = JSONObject(request(baseUrl, "/v1/models", "GET", token, null)).optJSONArray("data") ?: return emptyList()
        return (0 until rows.length()).mapNotNull { index ->
            val row = rows.optJSONObject(index) ?: return@mapNotNull null
            if (!row.optBoolean("enabled", false)) return@mapNotNull null
            CloudModel(row.optString("id"), row.optString("name", row.optString("model")), row.optString("model"), true, row.optBoolean("is_default", false))
        }.filter { it.id.isNotBlank() && it.model.isNotBlank() }
    }

    /**
     * 消费短期配对码；仅保存非敏感模型元数据（model_id/model/provider/base_url），
     * Cloud 不会下发任何凭据，本端凭 model_id 回传选用模型。
     */
    fun confirmPairing(baseUrl: String, code: String, deviceId: String, displayName: String): List<PairedModel> {
        val token = tokens.load() ?: throw IllegalStateException("请先登录 Cloud")
        verifyCapabilities(baseUrl)
        val body = JSONObject()
            .put("code", code)
            .put("device_id", deviceId)
            .put("platform", "android")
            .put("display_name", displayName)
            .put("public_key", publicKeyBase64())
            .toString()
        val data = JSONObject(request(baseUrl, "/v1/pairings/confirm", "POST", token, body)).getJSONObject("data")
        if (!data.optBoolean("paired", false)) throw IllegalStateException("Cloud 未确认设备配对")
        val rows = data.optJSONArray("models") ?: data.optJSONArray("model_bundle") ?: JSONArray()
        val models = (0 until rows.length()).mapNotNull { index ->
            val row = rows.optJSONObject(index) ?: return@mapNotNull null
            // 权威标识 model_id；旧版本字段 model/name 作兼容兜底
            val modelId = row.optString("model_id").takeIf { it.isNotBlank() } ?: row.optString("model")
            if (modelId.isBlank()) return@mapNotNull null
            PairedModel(
                id = row.optString("id", modelId),
                name = row.optString("name", modelId),
                provider = row.optString("provider", "openai-compatible"),
                model = modelId,
                baseUrl = row.optString("base_url"),
                isDefault = row.optBoolean("is_default", false),
            )
        }
        pairedModels.save(models)
        return models
    }

    fun streamRemoteAgent(baseUrl: String, input: String, host: CloudDevice, deviceId: String, onTransport: (String, Int?) -> Unit = { _, _ -> }, onMessage: (String, String?) -> Unit) {
        val accountToken = tokens.load() ?: throw IllegalStateException("未登录 Cloud")
        registerDevice(baseUrl, deviceId)
        ensureRemoteGrant(baseUrl, accountToken, deviceId, host.id)
        val remoteSessionKey = "remote_session_${cloudStateHash("${baseUrl.trimEnd('/')}\u0000${host.id}").take(24)}"
        val sessionId = syncState.getString(remoteSessionKey, null) ?: run {
            val session = request(baseUrl, "/v1/sessions", "POST", accountToken, JSONObject().put("kind", "device_remote").put("title", "NoteMeld Android Remote").toString())
            JSONObject(session).getJSONObject("data").getString("id").also { syncState.edit().putString(remoteSessionKey, it).apply() }
        }
        val deviceToken = proveDeviceAndIssueToken(baseUrl, accountToken, deviceId)
        val publicKey = host.publicKey?.let { Base64.decode(it, Base64.URL_SAFE or Base64.NO_WRAP) } ?: throw IllegalStateException("远程设备缺少公钥")
        val terminal = CountDownLatch(1)
        val transport = AndroidRemoteRelay(baseUrl, deviceToken, sessionId, deviceId, host.id, publicKey, host.lanEndpoints, remoteIdentity) { message ->
            runCatching {
                val event = JSONObject(message).optJSONObject("event") ?: JSONObject(message)
                val payload = event.optJSONObject("payload") ?: event
                val output = payload.optString("output", payload.optString("delta", ""))
                if (output.isNotBlank()) onMessage(output, null)
                val status = payload.optString("status")
                val type = event.optString("type", event.optString("event_type"))
                if (type == "approval.required") onMessage("危险操作正在等待远程 Host 本机审批；Android 控制端不能代为批准。", null)
                val terminalType = when {
                    type in setOf("turn.succeeded", "turn.failed", "turn.cancelled", "turn.interrupted") -> type
                    status == "completed" -> "turn.succeeded"
                    status == "failed" -> "turn.failed"
                    status == "cancelled" -> "turn.cancelled"
                    status == "interrupted" -> "turn.interrupted"
                    else -> null
                }
                if (terminalType != null) {
                    onMessage("", terminalType)
                    terminal.countDown()
                }
            }
        }
        try {
            transport.connect()
            onTransport(transport.activeTransport ?: throw IllegalStateException("远程传输未就绪"), transport.relayCursorStart)
            transport.send(input)
            if (!terminal.await(60, TimeUnit.SECONDS)) onMessage("远程 Agent 等待超时", "turn.failed")
        } finally {
            transport.close()
        }
    }

    private fun ensureRemoteGrant(baseUrl: String, accountToken: String, controllerId: String, hostId: String) {
        val existing = JSONObject(request(baseUrl, "/v1/grants", "GET", accountToken, null)).optJSONArray("data") ?: JSONArray()
        val now = System.currentTimeMillis() / 1000
        for (index in 0 until existing.length()) {
            val grant = existing.getJSONObject(index)
            val active = (!grant.has("revoked_at") || grant.isNull("revoked_at")) && (!grant.has("expires_at") || grant.isNull("expires_at") || grant.optLong("expires_at") > now)
            val scopes = grant.optJSONArray("scopes")
            if (active && grant.optString("controller_device_id") == controllerId && grant.optString("host_device_id") == hostId && scopes?.let { array -> (0 until array.length()).map { array.optString(it) }.containsAll(listOf("message.send", "event.receive")) } == true) return
        }
        val scopes = JSONArray(listOf("message.send", "event.receive", "context.select", "model.select", "tool.invoke"))
        request(baseUrl, "/v1/grants", "POST", accountToken, JSONObject().put("controller_device_id", controllerId).put("host_device_id", hostId).put("scopes", scopes).toString())
    }

    private fun proveDeviceAndIssueToken(baseUrl: String, accountToken: String, deviceId: String): String {
        val challengeResponse = JSONObject(request(baseUrl, "/v1/devices/$deviceId/challenge", "POST", accountToken, null)).getJSONObject("data")
        val challenge = challengeResponse.getString("challenge")
        val proof = "notemeld-device-proof-v1\u0000$deviceId\u0000$challenge".toByteArray(Charsets.UTF_8)
        val signature = Signature.getInstance("Ed25519").apply { initSign(remoteIdentity.private); update(proof) }.sign()
        request(baseUrl, "/v1/devices/$deviceId/challenge/verify", "POST", accountToken, JSONObject().put("challenge", challenge).put("signature", Base64.encodeToString(signature, Base64.URL_SAFE or Base64.NO_WRAP or Base64.NO_PADDING)).toString())
        val scopes = JSONArray(listOf("device.read", "device.write", "grant.read", "session.read"))
        val response = request(baseUrl, "/v1/devices/$deviceId/token", "POST", accountToken, JSONObject().put("scopes", scopes).put("expires_in_seconds", 86_400).put("revoke_source_token", false).toString())
        return JSONObject(response).getJSONObject("data").getString("token")
    }

    fun streamAgent(baseUrl: String, input: String, attachments: List<MobileAttachment> = emptyList(), modelId: String? = null, onMessage: (String, String?) -> Unit) {
        val token = tokens.load() ?: throw IllegalStateException("未登录 Cloud")
        var sessionId = syncState.getString("session_id", null)
        if (sessionId == null) {
            val createBody = JSONObject().put("kind", "cloud_native").put("title", "NoteMeld Mobile")
            if (!modelId.isNullOrBlank()) createBody.put("model_id", modelId)
            val session = request(baseUrl, "/v1/sessions", "POST", token, createBody.toString())
            sessionId = JSONObject(session).getJSONObject("data").getString("id")
            syncState.edit().putString("session_id", sessionId).putLong("event_sequence", 0L).apply()
        }
        val files = org.json.JSONArray()
        attachments.take(16).forEach { item -> files.put(JSONObject().put("name", item.name).put("size", item.size).put("type", item.type).put("content_base64", item.contentBase64)) }
        val commandBody = JSONObject()
            .put("request_id", UUID.randomUUID().toString())
            .put("input", input)
            .put("attachments", files)
        if (!modelId.isNullOrBlank()) commandBody.put("model_id", modelId)
        request(baseUrl, "/v1/sessions/$sessionId/commands", "POST", token, commandBody.toString())
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
                if (output.isNotBlank()) onMessage(output, null)
                if (event.optString("event_type").startsWith("command.")) {
                    val status = payload?.optString("status", "") ?: ""
                    val terminalType = when (status) {
                        "completed" -> "turn.succeeded"
                        "failed" -> "turn.failed"
                        "cancelled" -> "turn.cancelled"
                        "interrupted" -> "turn.interrupted"
                        else -> null
                    }
                    if (terminalType != null) { onMessage("", terminalType); return }
                }
            }
        }
        onMessage("Cloud Agent 等待超时", "turn.failed")
    }
    fun streamAgent(baseUrl: String, input: String, modelId: String? = null, onMessage: (String, String?) -> Unit) =
        streamAgent(baseUrl, input, MobileLocalStore.stagedAttachments(appContext), modelId, onMessage)
    private fun request(baseUrl: String, path: String, method: String, token: String?, body: String?): String {
        val connection = URL(baseUrl.trimEnd('/') + path).openConnection() as HttpURLConnection
        return try {
            connection.requestMethod = method; connection.connectTimeout = 5000; connection.readTimeout = 10000
            // A local development server can half-close a reused HTTP/1.1
            // socket between sequential Cloud calls. Keep each request
            // isolated so login/device sync is deterministic.
            connection.setRequestProperty("Connection", "close")
            connection.setRequestProperty("Content-Type", "application/json")
            if (token != null) connection.setRequestProperty("Authorization", "Bearer $token")
            if (body != null) { connection.doOutput = true; connection.outputStream.use { it.write(body.toByteArray(Charsets.UTF_8)) } }
            val code = connection.responseCode
            if (code !in 200..299) {
                val errorBody = connection.errorStream?.bufferedReader()?.use { it.readText().take(64 * 1024) } ?: ""
                throw CloudHttpException(code, errorBody)
            }
            connection.inputStream.bufferedReader().use { it.readText() }
        } finally { connection.disconnect() }
    }
}
