package com.notemeld.mobile

import org.json.JSONArray
import org.json.JSONObject
import java.util.Base64

/**
 * 跨端分享载荷（schema：notemeld.model-add.v1）。
 *
 * 形态：`notemeld://model-add?d=<base64url(JSON)>`，紧凑键压缩（s/v/vendor/name/protocol/url/models[id,n,c]）。
 *
 * 安全红线：
 *  - 编码永不包含 API Key（只接受 [VendorRegistry.ModelInput]，无密钥字段入口）；
 *  - 解码端递归拒绝任何密钥命名字段，并与 `notemeld://pair?code=` 配对码严格区分；
 *  - bedrock/unsupported 厂商、空模型、上下文越界、schema 不符一律返回 null。
 *
 * base64 使用 JDK [java.util.Base64]（minSdk 26 支持），可在无 Robolectric 的 JVM 单测中运行。
 */
object ModelSharePayload {

    data class DecodedModel(
        val id: String,
        val displayName: String,
        val contextWindow: Int,
    )

    data class DecodedShare(
        val vendorId: String,
        val displayName: String,
        val protocol: String,
        val baseUrl: String,
        val models: List<DecodedModel>,
    )

    private val SHARE_LINK_REGEX = Regex("^notemeld://model-add\\?d=([A-Za-z0-9_-]+)$")

    // 解码后禁止出现的密钥相关字段（任何层级，大小写/命名风格均拦截）
    private val SECRET_FIELD_REGEX =
        Regex("^(api[_-]?key|x[_-]?api[_-]?key|authorization|token|credential|secret)$", RegexOption.IGNORE_CASE)

    /** 构建紧凑分享 JSON（不执行 base64）。 */
    fun buildSharePayload(
        vendorId: String?,
        displayName: String,
        protocol: String,
        baseUrl: String,
        models: List<VendorRegistry.ModelInput>,
    ): JSONObject {
        val payload = JSONObject()
            .put("s", VendorRegistry.SHARE_SCHEMA)
            .put("v", 1)
        val vendor = VendorRegistry.getVendor(vendorId)
        if (vendor != null && !vendor.custom && vendor.protocol != "bedrock") {
            // 协议与 base_url 由接收端 registry 解析，保持二维码精简
            payload.put("vendor", vendorId)
        } else {
            payload.put("vendor", "custom")
                .put("name", displayName)
                .put("protocol", protocol)
                .put("url", VendorRegistry.trimUrl(baseUrl))
        }
        val rows = JSONArray()
        models.forEach { model ->
            val item = JSONObject().put("id", model.id)
            val dn = model.displayName
            if (!dn.isNullOrBlank() && dn != model.id) item.put("n", dn)
            val ctx = model.contextWindow
            if (ctx != null && ctx != VendorRegistry.DEFAULT_CONTEXT) item.put("c", ctx)
            rows.put(item)
        }
        payload.put("models", rows)
        return payload
    }

    /** JSON → `notemeld://model-add?d=<base64url>`。 */
    fun encodeShare(payload: JSONObject): String {
        val encoded = Base64.getUrlEncoder().withoutPadding()
            .encodeToString(payload.toString().toByteArray(Charsets.UTF_8))
        return "notemeld://model-add?d=$encoded"
    }

    /** 便捷方法：直接由配置生成分享 URI。 */
    fun encode(
        vendorId: String?,
        displayName: String,
        protocol: String,
        baseUrl: String,
        models: List<VendorRegistry.ModelInput>,
    ): String = encodeShare(buildSharePayload(vendorId, displayName, protocol, baseUrl, models))

    /**
     * 解析分享文本；接受完整 URI 或裸 JSON。非法、配对码、夹带密钥、schema 不符一律返回 null。
     */
    fun decodeShare(rawText: String?): DecodedShare? {
        val raw = (rawText ?: "").trim()
        if (raw.isBlank()) return null
        // 与配对码严格区分，显式拒绝
        if (raw.startsWith("notemeld://pair")) return null

        var jsonText = raw
        val match = SHARE_LINK_REGEX.matchEntire(raw)
        if (match != null) {
            val decoded = runCatching {
                String(Base64.getUrlDecoder().decode(match.groupValues[1]), Charsets.UTF_8)
            }.getOrNull() ?: return null
            jsonText = decoded
        }

        val obj = runCatching { JSONObject(jsonText) }.getOrNull() ?: return null
        if (obj.optString("s") != VendorRegistry.SHARE_SCHEMA) return null
        val modelsArray = obj.optJSONArray("models") ?: return null
        // 安全红线：任何密钥字段都拒绝导入
        if (containsSecretFields(obj)) return null

        val normalizedModels = mutableListOf<DecodedModel>()
        for (i in 0 until modelsArray.length()) {
            val item = modelsArray.optJSONObject(i) ?: return null
            val id = item.optString("id").takeIf { it.isNotBlank() } ?: return null
            val ctx = if (item.has("c")) item.optInt("c", Int.MIN_VALUE) else VendorRegistry.DEFAULT_CONTEXT
            if (ctx == Int.MIN_VALUE || ctx < VendorRegistry.CONTEXT_MIN || ctx > VendorRegistry.CONTEXT_MAX) {
                return null
            }
            normalizedModels.add(
                DecodedModel(
                    id = id,
                    displayName = item.optString("n").takeIf { it.isNotBlank() } ?: id,
                    contextWindow = ctx,
                ),
            )
        }
        if (normalizedModels.isEmpty()) return null

        val vendorId = obj.optString("vendor").takeIf { it.isNotBlank() }
        val vendor = VendorRegistry.getVendor(vendorId)
        if (vendorId != null && vendorId != "custom" && vendor != null && !vendor.custom) {
            // Bedrock 等预留/不支持协议即使伪造为预设厂商载荷也拒绝导入
            if (vendor.protocol == "bedrock" || vendor.unsupported != null) return null
            return DecodedShare(
                vendorId = vendor.id,
                displayName = vendor.name,
                protocol = vendor.protocol,
                baseUrl = vendor.baseUrl,
                models = normalizedModels,
            )
        }

        val protocol = obj.optString("protocol").takeIf { it.isNotBlank() } ?: "openai-compatible"
        if (VendorRegistry.getProtocol(protocol) == null || protocol == "bedrock") return null
        return DecodedShare(
            vendorId = "custom",
            displayName = obj.optString("name"),
            protocol = protocol,
            baseUrl = obj.optString("url"),
            models = normalizedModels,
        )
    }

    private fun containsSecretFields(value: Any?): Boolean = when (value) {
        is JSONObject -> {
            value.keys().asSequence().any { key ->
                SECRET_FIELD_REGEX.matches(key.trim()) || containsSecretFields(value.opt(key))
            }
        }
        is JSONArray -> {
            (0 until value.length()).any { containsSecretFields(value.opt(it)) }
        }
        else -> false
    }
}
