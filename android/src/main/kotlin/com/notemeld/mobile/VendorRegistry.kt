package com.notemeld.mobile

import java.net.URI

/**
 * 安卓端三端统一「添加模型」registry（schema：notemeld.model-add.v1）。
 *
 * 与 desktop/frontend/src/lib/modelVendorRegistry.ts、
 * desktop/backend/app/services/vendor_registry.py 保持 1:1 语义：
 *  - [PROTOCOLS] / [MODEL_VENDORS]：协议枚举与内置厂商预设
 *  - [validateModelConfig]：三端统一即时校验
 *
 * 分享载荷相关逻辑在 [ModelSharePayload]；本文件为纯 JVM 可测，无 Android 依赖。
 */
object VendorRegistry {
    const val SHARE_SCHEMA = "notemeld.model-add.v1"
    const val DEFAULT_CONTEXT = 128000
    const val CONTEXT_MIN = 512
    const val CONTEXT_MAX = 4_000_000

    data class ModelProtocol(
        val id: String,
        val label: String,
        val needsKey: Boolean,
        val modelsPath: String?,
        val testKind: String, // chat | anthropic | ollama
    )

    data class ModelVendor(
        val id: String,
        val name: String,
        val protocol: String,
        val baseUrl: String,
        val icon: String,
        val urlNote: String? = null,
        val unsupported: String? = null,
        val custom: Boolean = false,
    )

    /** 校验/分享用的模型输入；上下文缺省取 [DEFAULT_CONTEXT]。 */
    data class ModelInput(
        val id: String,
        val displayName: String? = null,
        val contextWindow: Int? = null,
    )

    // bedrock、azure 为预留，v1 不支持直连
    val PROTOCOLS: List<ModelProtocol> = listOf(
        ModelProtocol("openai-compatible", "OpenAI 兼容", true, "/models", "chat"),
        ModelProtocol("anthropic-messages", "Anthropic / Claude", true, null, "anthropic"),
        ModelProtocol("ollama", "本地 Ollama", false, "/api/tags", "ollama"),
    )

    // base_url 为空表示官方公开地址待确认，选择后仍需用户补一次，不臆造
    val MODEL_VENDORS: List<ModelVendor> = listOf(
        ModelVendor("deepseek", "DeepSeek", "openai-compatible", "https://api.deepseek.com", "bot"),
        ModelVendor("volcengine-ark", "火山引擎", "openai-compatible", "https://ark.cn-beijing.volces.com/api/v3", "flame"),
        ModelVendor("volcengine-agent-plan", "火山 Agent Plan", "openai-compatible", "https://ark.cn-beijing.volces.com/api/plan/v3", "flame"),
        ModelVendor("volcengine-coding-plan", "火山 Coding Plan", "openai-compatible", "https://ark.cn-beijing.volces.com/api/coding/v3", "flame"),
        ModelVendor("minimax-cn", "MiniMax CN", "openai-compatible", "https://api.minimaxi.com/v1", "audio-lines"),
        ModelVendor("minimax-global", "MiniMax Global", "openai-compatible", "https://api.minimax.io/v1", "audio-lines"),
        ModelVendor("bigmodel", "Bigmodel", "openai-compatible", "https://open.bigmodel.cn/api/paas/v4", "sparkles"),
        ModelVendor("aliyun-bailian", "阿里云", "openai-compatible", "https://dashscope.aliyuncs.com/compatible-mode/v1", "cloud"),
        ModelVendor("xiaomi-mimo", "Xiaomi MIMO", "openai-compatible", "", "smartphone", urlNote = "官方 OpenAI 兼容地址待确认，请按服务商文档填写"),
        ModelVendor("siliconflow", "硅基流动", "openai-compatible", "https://api.siliconflow.cn/v1", "layers"),
        ModelVendor("zai", "Z.ai", "openai-compatible", "https://api.z.ai/api/paas/v4", "sigma"),
        ModelVendor("openrouter", "OpenRouter", "openai-compatible", "https://openrouter.ai/api/v1", "shuffle"),
        ModelVendor("kimi-cn", "Kimi CN", "openai-compatible", "https://api.moonshot.cn/v1", "moon"),
        ModelVendor("kimi-global", "Kimi Global", "openai-compatible", "https://api.moonshot.ai/v1", "moon"),
        ModelVendor("byteplus", "BytePlus", "openai-compatible", "https://ark.mlp.bytepluses.com/api/v3", "zap"),
        ModelVendor("aws-bedrock", "AWS", "bedrock", "", "server", unsupported = "Bedrock 使用 SigV4 签名鉴权，v1 暂不支持直连，请通过 OpenAI 兼容网关接入"),
        ModelVendor("tencent-hunyuan", "腾讯云", "openai-compatible", "https://api.hunyuan.cloud.tencent.com/v1", "message-circle"),
        ModelVendor("moli-fangzhou", "模力方舟", "openai-compatible", "", "compass", urlNote = "官方兼容地址待确认，请按服务商文档填写"),
        ModelVendor("ppio", "PPIO", "openai-compatible", "https://api.ppinfra.com/v1/openai", "radio"),
        ModelVendor("openai", "OpenAI", "openai-compatible", "https://api.openai.com/v1", "globe"),
        ModelVendor("anthropic", "Anthropic / Claude", "anthropic-messages", "https://api.anthropic.com", "brain-circuit"),
        ModelVendor("gemini", "Google Gemini", "openai-compatible", "https://generativelanguage.googleapis.com/v1beta/openai/", "sparkle"),
        ModelVendor("ollama", "本地 Ollama", "ollama", "http://localhost:11434", "hard-drive"),
        ModelVendor("custom", "自定义", "openai-compatible", "", "settings-2", custom = true),
    )

    // Anthropic 无标准公开模型列表接口，用内置常用目录兜底
    val ANTHROPIC_BUILTIN_MODELS: List<ModelInput> = listOf(
        ModelInput("claude-opus-4-1", contextWindow = 200000),
        ModelInput("claude-sonnet-4-5", contextWindow = 200000),
        ModelInput("claude-3-5-haiku-latest", contextWindow = 200000),
    )

    private val LOCAL_URL_REGEX = Regex("^http://(localhost|127\\.0\\.0\\.1|\\[::1])(:\\d+)?(/|$)", RegexOption.IGNORE_CASE)
    private val TRAILING_SLASH_REGEX = Regex("/+$")

    fun getVendor(vendorId: String?): ModelVendor? {
        if (vendorId.isNullOrBlank()) return null
        return MODEL_VENDORS.firstOrNull { it.id == vendorId }
    }

    fun getProtocol(protocolId: String?): ModelProtocol? {
        if (protocolId.isNullOrBlank()) return null
        return PROTOCOLS.firstOrNull { it.id == protocolId }
    }

    fun trimUrl(url: String?): String = (url ?: "").trim().replace(TRAILING_SLASH_REGEX, "")

    fun isLocalUrl(url: String): Boolean = LOCAL_URL_REGEX.containsMatchIn(url)

    fun isValidHttpUrl(url: String): Boolean = runCatching {
        val parsed = URI(url)
        val scheme = parsed.scheme?.lowercase()
        (scheme == "http" || scheme == "https") && !parsed.host.isNullOrBlank()
    }.getOrDefault(false)

    /**
     * 三端统一即时校验；返回 field -> message，空 Map 表示通过。
     * [hasStoredKey] 表示编辑场景下已留存密钥、本次留空即保留；
     * [duplicateNames] 非空时整体 models 字段报错。
     */
    fun validateModelConfig(
        displayName: String?,
        protocol: String?,
        baseUrl: String?,
        apiKey: String?,
        hasStoredKey: Boolean = false,
        models: List<ModelInput>,
        duplicateNames: List<String> = emptyList(),
    ): Map<String, String> {
        val errors = linkedMapOf<String, String>()
        val name = displayName?.trim().orEmpty()
        val protocolId = protocol?.takeIf { it.isNotBlank() } ?: "openai-compatible"
        val url = trimUrl(baseUrl)
        val key = apiKey?.trim().orEmpty()

        if (name.isBlank()) errors["display_name"] = "请填写名称"
        if (url.isBlank()) {
            errors["base_url"] = "请填写接口地址"
        } else if (!isValidHttpUrl(url)) {
            errors["base_url"] = "地址格式不正确"
        } else if (!isLocalUrl(url) && !url.startsWith("https://", ignoreCase = true)) {
            errors["base_url"] = "非本机地址必须使用 HTTPS"
        }

        val proto = getProtocol(protocolId)
        when {
            proto == null -> errors["protocol"] = "请选择协议类型"
            proto.needsKey && key.isBlank() && !hasStoredKey && protocolId != "ollama" ->
                errors["api_key"] = "请填写 API 密钥"
        }

        if (models.isEmpty()) {
            errors["models"] = "请至少选择或添加一个模型"
        }
        models.forEachIndexed { index, model ->
            val ctx = model.contextWindow
            if (ctx == null || ctx < CONTEXT_MIN || ctx > CONTEXT_MAX) {
                errors["model_context:$index"] =
                    "「${model.id}」上下文需为 $CONTEXT_MIN–$CONTEXT_MAX 的整数"
            }
        }

        if (duplicateNames.isNotEmpty()) {
            errors["models"] = "模型已存在：${duplicateNames.joinToString("、")}，请勿重复添加"
        }
        return errors
    }
}
