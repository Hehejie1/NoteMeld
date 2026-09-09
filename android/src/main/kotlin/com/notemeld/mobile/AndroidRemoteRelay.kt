package com.notemeld.mobile

import android.util.Base64
import java.io.BufferedInputStream
import java.io.BufferedOutputStream
import java.net.Socket
import java.net.URI
import java.nio.ByteBuffer
import java.nio.charset.StandardCharsets
import java.security.KeyPair
import java.security.KeyPairGenerator
import java.security.SecureRandom
import java.security.Signature
import javax.crypto.Cipher
import javax.crypto.KeyAgreement
import javax.crypto.Mac
import javax.crypto.spec.GCMParameterSpec
import javax.crypto.spec.SecretKeySpec
import org.json.JSONObject

private fun arB64(value: ByteArray): String = Base64.encodeToString(value, Base64.URL_SAFE or Base64.NO_WRAP or Base64.NO_PADDING)
private fun arDecode(value: String): ByteArray = Base64.decode(value, Base64.URL_SAFE or Base64.NO_WRAP)
private fun arRaw(value: ByteArray): ByteArray = value.takeLast(32).toByteArray()
private fun arJson(values: Map<String, Any?>): String = JSONObject().apply { values.toSortedMap().forEach { (key, value) -> put(key, value) } }.toString()
private fun arHandshakeMessage(session: String, sender: String, recipient: String, publicKey: ByteArray): ByteArray = "notemeld-e2ee-v1\u0000$session\u0000$sender\u0000$recipient\u0000".toByteArray() + publicKey
private fun arTranscript(session: String, first: String, firstKey: ByteArray, second: String, secondKey: ByteArray): ByteArray = "notemeld-e2ee-transcript-v1\u0000$session\u0000$first\u0000$second\u0000".toByteArray() + firstKey + secondKey

private fun arXPublic(raw: ByteArray): java.security.PublicKey = java.security.KeyFactory.getInstance("X25519").generatePublic(java.security.spec.X509EncodedKeySpec(byteArrayOf(0x30, 0x2a, 0x30, 0x05, 0x06, 0x03, 0x2b, 0x65, 0x6e, 0x03, 0x21, 0x00) + raw))
private fun arEdPublic(raw: ByteArray): java.security.PublicKey = java.security.KeyFactory.getInstance("Ed25519").generatePublic(java.security.spec.X509EncodedKeySpec(byteArrayOf(0x30, 0x2a, 0x30, 0x05, 0x06, 0x03, 0x2b, 0x65, 0x70, 0x03, 0x21, 0x00) + raw))
private fun arHkdf(input: ByteArray, info: ByteArray): ByteArray {
    val salt = Mac.getInstance("HmacSHA256").apply { init(SecretKeySpec(ByteArray(32), "HmacSHA256")) }.doFinal(input)
    return Mac.getInstance("HmacSHA256").apply { init(SecretKeySpec(salt, "HmacSHA256")) }.doFinal(info + byteArrayOf(1)).copyOf(32)
}

/** Dependency-free WebSocket + E2EE Relay transport for Android. */
class AndroidRemoteRelay(
    private val cloudUrl: String,
    private val bearer: String,
    private val sessionId: String,
    private val controllerId: String,
    private val hostId: String,
    private val hostPublicKey: ByteArray,
    private val lanEndpoints: List<String> = emptyList(),
    private val identity: KeyPair,
    private val onEvent: (String) -> Unit,
) {
    private val random = SecureRandom()
    private var socket: Socket? = null
    private var input: BufferedInputStream? = null
    private var output: BufferedOutputStream? = null
    private var key: ByteArray? = null
    private var sequence = 1
    private var authorityEpoch = 1
    private var reader: Thread? = null
    private val receiptLock = Object()
    private var pendingFrameId: String? = null
    private var pendingRequestId: String? = null
    private var pendingReceipt: JSONObject? = null

    fun connect() {
        val candidates = lanEndpoints.map { URI("ws://$it/v1/lan/connect/$sessionId") to true } + (webSocketUri(cloudUrl.trimEnd('/') + "/v1/relay/connect/$sessionId?device_id=$controllerId") to false)
        var failure: Throwable? = null
        for ((uri, lan) in candidates) {
            try {
                close()
                openSocket(uri, lan)
                if (lan) authorizeLan()
                completeE2ee(!lan)
                reader = Thread { readLoop() }.also { it.isDaemon = true; it.start() }
                return
            } catch (error: Throwable) {
                failure = error
                close()
            }
        }
        throw failure ?: IllegalStateException("no remote transport candidate")
    }

    private fun openSocket(uri: URI, lan: Boolean) {
        val port = if (uri.port > 0) uri.port else if (uri.scheme == "wss") 443 else 80
        val rawSocket = if (uri.scheme == "wss") javax.net.ssl.SSLSocketFactory.getDefault().createSocket(uri.host, port) else Socket(uri.host, port)
        socket = rawSocket
        input = BufferedInputStream(rawSocket.getInputStream()); output = BufferedOutputStream(rawSocket.getOutputStream())
        val websocketKey = ByteArray(16).also(random::nextBytes)
        val authorization = if (lan) "" else "Authorization: Bearer $bearer\r\n"
        val request = "GET ${uri.rawPath}${if (uri.rawQuery == null) "" else "?${uri.rawQuery}"} HTTP/1.1\r\nHost: ${uri.host}:$port\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Key: ${Base64.encodeToString(websocketKey, Base64.NO_WRAP)}\r\nSec-WebSocket-Version: 13\r\n$authorization\r\n"
        output!!.write(request.toByteArray()); output!!.flush(); readUpgrade()
    }

    private fun authorizeLan() {
        sendText(arJson(mapOf("type" to "hello", "protocol_version" to "notemeld.lan.v1", "controller_device_id" to controllerId)))
        val challenge = JSONObject(String(readFrame() ?: error("LAN challenge missing"), StandardCharsets.UTF_8))
        val proofMessage = "notemeld-lan-auth-v1\u0000$sessionId\u0000$controllerId\u0000$hostId\u0000${challenge.getString("challenge_id")}\u0000${challenge.getString("challenge")}".toByteArray()
        val signature = Signature.getInstance("Ed25519").apply { initSign(identity.private); update(proofMessage) }.sign()
        sendText(arJson(mapOf("type" to "proof", "challenge_id" to challenge.getString("challenge_id"), "challenge" to challenge.getString("challenge"), "signature" to arB64(signature))))
        val authorized = JSONObject(String(readFrame() ?: error("LAN authorization missing"), StandardCharsets.UTF_8))
        check(authorized.optString("type") == "authorized")
        authorityEpoch = authorized.optInt("authority_epoch", 1)
    }

    private fun completeE2ee(relay: Boolean) {
        val ephemeral = KeyPairGenerator.getInstance("X25519").generateKeyPair(); val ephemeralRaw = arRaw(ephemeral.public.encoded)
        val signed = arHandshakeMessage(sessionId, controllerId, hostId, ephemeralRaw)
        val signature = Signature.getInstance("Ed25519").apply { initSign(identity.private); update(signed) }.sign()
        val offer = mapOf("protocol_version" to "notemeld.e2ee.handshake.v1", "session_id" to sessionId, "sender_device_id" to controllerId, "recipient_device_id" to hostId, "ephemeral_public" to arB64(ephemeralRaw), "signature" to arB64(signature))
        val frame = mapOf("authority_epoch" to authorityEpoch, "frame_id" to java.util.UUID.randomUUID().toString(), "frame_type" to "handshake", "nonce" to arB64(ByteArray(12)), "protocol_version" to "notemeld.sync.v1", "recipient_device_id" to hostId, "sender_device_id" to controllerId, "sequence" to 1, "session_id" to sessionId, "ciphertext" to arB64(arJson(offer).toByteArray()))
        sendText(arJson(if (relay) frame else offer))
        val peer = if (relay) waitForHandshake() else JSONObject(String(readFrame() ?: error("LAN E2EE handshake missing"), StandardCharsets.UTF_8))
        val peerRaw = arDecode(peer.getString("ephemeral_public"))
        val verifier = Signature.getInstance("Ed25519").apply { initVerify(arEdPublic(hostPublicKey)); update(arHandshakeMessage(sessionId, hostId, controllerId, peerRaw)) }
        check(verifier.verify(arDecode(peer.getString("signature"))))
        val shared = KeyAgreement.getInstance("X25519").apply { init(ephemeral.private); doPhase(arXPublic(peerRaw), true) }.generateSecret()
        val firstIsController = controllerId < hostId
        key = arHkdf(shared, if (firstIsController) arTranscript(sessionId, controllerId, ephemeralRaw, hostId, peerRaw) else arTranscript(sessionId, hostId, peerRaw, controllerId, ephemeralRaw))
    }

    @Synchronized fun send(inputText: String) {
        val sessionKey = key ?: error("remote transport is not connected")
        val frameId = java.util.UUID.randomUUID().toString(); val requestId = java.util.UUID.randomUUID().toString(); sequence += 1
        val nonce = ByteArray(12).also(random::nextBytes)
        val metadata = mapOf("authority_epoch" to authorityEpoch, "frame_id" to frameId, "frame_type" to "command", "nonce" to arB64(nonce), "protocol_version" to "notemeld.sync.v1", "recipient_device_id" to hostId, "sender_device_id" to controllerId, "sequence" to sequence, "session_id" to sessionId)
        val cipher = Cipher.getInstance("AES/GCM/NoPadding").apply { init(Cipher.ENCRYPT_MODE, SecretKeySpec(sessionKey, "AES"), GCMParameterSpec(128, nonce)); updateAAD(arJson(metadata).toByteArray()) }
        val encrypted = cipher.doFinal(arJson(mapOf("request_id" to requestId, "input" to inputText)).toByteArray())
        synchronized(receiptLock) { pendingFrameId = frameId; pendingRequestId = requestId; pendingReceipt = null }
        sendText(arJson(metadata + mapOf("ciphertext" to arB64(encrypted))))
        synchronized(receiptLock) {
            val deadline = System.currentTimeMillis() + 60_000
            while (pendingReceipt == null && System.currentTimeMillis() < deadline) {
                receiptLock.wait((deadline - System.currentTimeMillis()).coerceAtLeast(1))
            }
            val receipt = pendingReceipt ?: throw IllegalStateException("remote command receipt timeout")
            pendingFrameId = null; pendingRequestId = null; pendingReceipt = null
            if (receipt.optString("status") == "rejected" || receipt.optString("status") == "failed") {
                throw IllegalStateException(receipt.optString("error", "remote command rejected"))
            }
        }
    }

    fun close() {
        runCatching { socket?.close() }; socket = null; reader?.interrupt(); reader = null
        synchronized(receiptLock) { pendingReceipt = JSONObject().put("status", "failed").put("error", "remote transport closed"); receiptLock.notifyAll() }
    }
    private fun readUpgrade() { var line = readLine(); check(line?.contains("101") == true) { "Relay WebSocket upgrade failed" }; while (line?.isNotEmpty() == true) line = readLine() }
    private fun readLine(): String? { val bytes = ArrayList<Byte>(); while (true) { val value = input?.read() ?: return null; if (value == 10) return String(bytes.toByteArray()).trimEnd('\r'); bytes += value.toByte() } }
    private fun sendText(value: String) { sendFrame(value.toByteArray(StandardCharsets.UTF_8)) }
    private fun sendFrame(payload: ByteArray) { val stream = output ?: error("Relay socket is closed"); val mask = ByteArray(4).also(random::nextBytes); val header = ArrayList<Byte>(); header += 0x81.toByte(); when { payload.size < 126 -> header += (0x80 or payload.size).toByte(); payload.size <= 65535 -> { header += 0xfe.toByte(); header += ByteBuffer.allocate(2).putShort(payload.size.toShort()).array().toList() }; else -> error("Relay frame too large") }; header += mask.toList(); val masked = payload.mapIndexed { index, byte -> (byte.toInt() xor mask[index % 4].toInt()).toByte() }; stream.write(header.toByteArray()); stream.write(masked.toByteArray()); stream.flush() }
    private fun waitForHandshake(): JSONObject { while (true) { val payload = readFrame() ?: error("Relay closed during handshake"); val frame = JSONObject(String(payload, StandardCharsets.UTF_8)); if (frame.optString("frame_type") == "handshake") return JSONObject(String(arDecode(frame.getString("ciphertext")), StandardCharsets.UTF_8)); if (frame.optString("type") == "rejected") error(frame.optString("error")) } }
    private fun readFrame(): ByteArray? { val first = input?.read() ?: return null; val second = input?.read() ?: return null; val opcode = first and 0x0f; if (opcode == 8) return null; var length = second and 0x7f; if (length == 126) length = ByteBuffer.wrap(ByteArray(2).also { input!!.read(it) }).short.toInt() and 0xffff; if (length == 127) error("Relay frame is too large"); val mask = if ((second and 0x80) != 0) ByteArray(4).also { input!!.read(it) } else null; val data = ByteArray(length); var offset = 0; while (offset < length) offset += input!!.read(data, offset, length - offset); if (mask != null) data.indices.forEach { data[it] = (data[it].toInt() xor mask[it % 4].toInt()).toByte() }; return data }
    private fun readLoop() {
        while (!Thread.currentThread().isInterrupted) {
            runCatching {
                val value = readFrame() ?: return
                val frame = JSONObject(String(value, StandardCharsets.UTF_8))
                if (frame.optString("frame_type") != "receipt" && frame.optString("frame_type") != "event") return@runCatching
                val payload = decryptPayload(frame)
                if (frame.optString("frame_type") == "receipt") {
                    synchronized(receiptLock) {
                        if (payload.optString("frame_id") == pendingFrameId && payload.optString("request_id") == pendingRequestId) {
                            pendingReceipt = payload; receiptLock.notifyAll()
                        }
                    }
                } else {
                    onEvent(payload.toString())
                }
            }.onFailure { error ->
                synchronized(receiptLock) { pendingReceipt = JSONObject().put("status", "failed").put("error", error.message ?: "remote transport failed"); receiptLock.notifyAll() }
                return
            }
        }
    }
    private fun decryptPayload(frame: JSONObject): JSONObject {
        val sessionKey = key ?: error("remote transport is not connected")
        val nonceText = frame.getString("nonce")
        val nonce = arDecode(nonceText)
        val metadata = linkedMapOf<String, Any?>()
        frame.keys().asSequence().filter { it != "ciphertext" }.forEach { metadata[it] = frame.get(it) }
        val cipher = Cipher.getInstance("AES/GCM/NoPadding").apply {
            init(Cipher.DECRYPT_MODE, SecretKeySpec(sessionKey, "AES"), GCMParameterSpec(128, nonce))
            updateAAD(arJson(metadata).toByteArray(StandardCharsets.UTF_8))
        }
        return JSONObject(String(cipher.doFinal(arDecode(frame.getString("ciphertext"))), StandardCharsets.UTF_8))
    }
    private fun webSocketUri(value: String): URI { val parsed = URI(value); val scheme = when (parsed.scheme.lowercase()) { "https" -> "wss"; "http" -> "ws"; else -> parsed.scheme }; return URI(scheme, parsed.userInfo, parsed.host, parsed.port, parsed.path, parsed.query, parsed.fragment) }
}
