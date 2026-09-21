package com.notemeld.mobile

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotEquals
import org.junit.Test

class MobileStringsTest {
    @Test
    fun homeAndSessionVocabularyIsCompleteForAllSelectableLanguages() {
        val keys = listOf(
            "homeSlogan",
            "placeholder",
            "continuePlaceholder",
            "documentProcessing",
            "presentation",
            "workbench",
            "more",
            "tools",
            "permission",
            "permissionGranted",
            "permissionTitle",
            "sessionSettings",
            "permissionDefault",
            "permissionDefaultDescription",
            "permissionFull",
            "permissionFullDescription",
            "model",
            "aiDisclaimer",
            "localAgent",
            "cloudAgent",
            "remoteAgent",
            "statusOfflineReadonly",
            "statusRunning",
            "statusCompleted",
            "statusNeedsAttention",
            "statusReady",
        )

        listOf("简体中文", "繁體中文", "English").forEach { language ->
            keys.forEach { key -> assertNotEquals("$language must translate $key", key, mobileText(language, key)) }
        }
    }

    @Test
    fun explicitLanguagesDoNotDependOnTheDeviceLocale() {
        assertEquals("Documents", mobileText("English", "documentProcessing"))
        assertEquals("文件處理", mobileText("繁體中文", "documentProcessing"))
        assertEquals("文档处理", mobileText("简体中文", "documentProcessing"))
    }

    @Test
    fun modelConfigVocabularyIsCompleteForAllSelectableLanguages() {
        val keys = listOf(
            "provider",
            "providers",
            "localModels",
            "cloudModels",
            "pairedModels",
            "protocol",
            "baseUrl",
            "apiKey",
            "apiKeyHint",
            "contextWindow",
            "selectVendor",
            "bedrockUnsupported",
            "fetchModels",
            "testConnection",
            "testUntested",
            "testOk",
            "testFailed",
            "setDefault",
            "defaultBadge",
            "enableModel",
            "disableModel",
            "editModel",
            "deleteProvider",
            "shareConfig",
            "shareLinkCopied",
            "saveConfig",
            "cancel",
            "confirm",
            "modelSelection",
            "noProviders",
            "noLocalModels",
            "discoverFailed",
            "discovering",
            "savingConfig",
            "configImported",
            "confirmDeleteProvider",
            "scannerIntro",
            "scannerAlign",
            "scannerDenied",
            "scannerNotSupported",
            "scannerPairing",
            "scannerPairOk",
            "scannerPairFail",
            "scannerShareOk",
            "scannerCameraFail",
            "allowCamera",
        )
        listOf("简体中文", "繁體中文", "English").forEach { language ->
            keys.forEach { key -> assertNotEquals("$language must translate $key", key, mobileText(language, key)) }
        }
    }
}
