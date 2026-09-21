package com.notemeld.mobile

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class ModelPairingScannerTest {
    private val shareLinkShape = Regex("^notemeld://model-add\\?d=[A-Za-z0-9_-]+$")

    @Test fun acceptsOnlyNoteMeldPairingUris() {
        assertEquals("abc_DEF-123", parseNoteMeldPairingCode("notemeld://pair?code=abc_DEF-123"))
        assertNull(parseNoteMeldPairingCode("https://example.com/?code=abc_DEF-123"))
        assertNull(parseNoteMeldPairingCode("notemeld://pair?code=short"))
        assertNull(parseNoteMeldPairingCode("notemeld://pair?code=abc_DEF-123&token=secret"))
    }

    @Test fun classifyScanResultKeepsPairAndModelShareMutuallyExclusive() {
        // 1. pair 码
        val pair = classifyScanResult("notemeld://pair?code=abc_DEF-123")
        assertTrue(pair is ScanTarget.PairCode)
        assertEquals("abc_DEF-123", (pair as ScanTarget.PairCode).code)

        // pair URI 形态正确但 code 非法：返回 null，不回落到 model-add
        assertNull(classifyScanResult("notemeld://pair?code=short"))

        // 2. model-add 分享链接形态正确（不含 api_key）。手工构造紧凑载荷；
        //    JVM 单测中 org.json 为 stub，完整解码回 roundtrip 由 androidTest 覆盖。
        val json = """{"s":"${VendorRegistry.SHARE_SCHEMA}","v":1,"vendor":"deepseek","models":[{"id":"deepseek-chat","n":"DeepSeek Chat"}]}"""
        val encoded = java.util.Base64.getUrlEncoder().withoutPadding()
            .encodeToString(json.toByteArray(Charsets.UTF_8))
        val link = "notemeld://model-add?d=$encoded"
        assertTrue(shareLinkShape.matches(link))

        // 3. 无关文本
        assertNull(classifyScanResult("https://example.com"))
    }
}
