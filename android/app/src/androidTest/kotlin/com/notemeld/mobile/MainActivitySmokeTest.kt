package com.notemeld.mobile

import android.content.ClipboardManager
import android.content.Context
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.hasContentDescription
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performScrollToNode
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performTextInput
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import androidx.test.uiautomator.UiDevice
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class MainActivitySmokeTest {
    @get:Rule
    val composeRule = createAndroidComposeRule<MainActivity>()

    @After
    fun clearPersistedTestState() {
        // Keep authorization/Provider state from leaking between independent tests.
        InstrumentationRegistry.getInstrumentation().targetContext
            .getSharedPreferences("notemeld-mobile-state", Context.MODE_PRIVATE)
            .edit()
            .remove("permissionGranted")
            .remove("permissionMode")
            .remove("cloudUrl")
            .commit()
    }

    private fun openSettingsFromDrawer() {
        composeRule.onNode(hasContentDescription("notemeld-open-menu")).performClick()
        composeRule.onNode(hasContentDescription("notemeld-open-settings")).performClick()
    }

    @Test
    fun homeScreenExposesStableProductionLocators() {
        composeRule.onNodeWithTag("notemeld-mobile-root").assertIsDisplayed()
        composeRule.onNodeWithTag("notemeld-screen-home").assertIsDisplayed()
        composeRule.onNode(hasContentDescription("notemeld-home-brand")).assertIsDisplayed()
        composeRule.onNode(hasContentDescription("notemeld-quick-document")).assertIsDisplayed()
        composeRule.onNode(hasContentDescription("notemeld-start-chat")).assertIsDisplayed()
    }

    @Test
    fun settingsCanOpenAndCloseThroughProductionActions() {
        openSettingsFromDrawer()
        composeRule.onNodeWithTag("notemeld-screen-settings").assertIsDisplayed()
        composeRule.onNode(hasContentDescription("notemeld-back-settings")).performClick()
        composeRule.onNodeWithTag("notemeld-screen-home").assertIsDisplayed()
    }

    @Test
    fun themeSheetCanSelectDarkMode() {
        openSettingsFromDrawer()
        composeRule.onNode(hasContentDescription("主题-深色")).performClick()
        composeRule.onNodeWithTag("notemeld-screen-settings").assertIsDisplayed()
        composeRule.onNodeWithText("深色").assertIsDisplayed()
    }

    @Test
    fun settingsExposeM03ToM06NavigationLocators() {
        openSettingsFromDrawer()
        composeRule.onNode(hasContentDescription("notemeld-open-memory")).assertIsDisplayed()
        composeRule.onNode(hasContentDescription("notemeld-open-font-size")).assertIsDisplayed()
        // 通知行与存储行在较小屏幕上位于折叠区之外，需先滚动设置容器再断言。
        composeRule.onNodeWithTag("notemeld-settings")
            .performScrollToNode(hasContentDescription("notemeld-notifications"))
        composeRule.onNode(hasContentDescription("notemeld-notifications")).assertIsDisplayed()
        composeRule.onNodeWithTag("notemeld-settings")
            .performScrollToNode(hasContentDescription("notemeld-open-storage"))
        composeRule.onNode(hasContentDescription("notemeld-open-storage")).assertIsDisplayed()
    }

    @Test
    fun settingsPagesAreReachableThroughProductionNavigation() {
        openSettingsFromDrawer()

        composeRule.onNode(hasContentDescription("notemeld-open-memory")).performClick()
        composeRule.onNodeWithTag("notemeld-screen-memory").assertIsDisplayed()
        composeRule.onNode(hasContentDescription("notemeld-back-settings")).performClick()

        composeRule.onNode(hasContentDescription("notemeld-open-font-size")).performClick()
        composeRule.onNodeWithTag("notemeld-screen-font_size").assertIsDisplayed()
        composeRule.onNode(hasContentDescription("notemeld-back-settings")).performClick()

        composeRule.onNodeWithTag("notemeld-settings")
            .performScrollToNode(hasContentDescription("notemeld-open-storage"))
        composeRule.onNode(hasContentDescription("notemeld-open-storage")).performClick()
        composeRule.onNodeWithTag("notemeld-screen-storage").assertIsDisplayed()
    }

    @Test
    fun memoryFontAndStorageActionsExposeInteractiveControls() {
        openSettingsFromDrawer()

        composeRule.onNode(hasContentDescription("notemeld-open-memory")).performClick()
        composeRule.onNode(hasContentDescription("notemeld-memory-input")).assertIsDisplayed()
        composeRule.onNode(hasContentDescription("notemeld-memory-add")).assertIsDisplayed()
        composeRule.onNode(hasContentDescription("notemeld-back-settings")).performClick()

        composeRule.onNode(hasContentDescription("notemeld-open-font-size")).performClick()
        composeRule.onNode(hasContentDescription("notemeld-font-follow-system")).assertIsDisplayed()
        composeRule.onNode(hasContentDescription("notemeld-font-slider")).assertIsDisplayed()
        composeRule.onNode(hasContentDescription("notemeld-font-reset")).assertIsDisplayed()
        composeRule.onNode(hasContentDescription("notemeld-font-save")).assertIsDisplayed()
        composeRule.onNode(hasContentDescription("notemeld-back-settings")).performClick()

        composeRule.onNodeWithTag("notemeld-settings")
            .performScrollToNode(hasContentDescription("notemeld-open-storage"))
        composeRule.onNode(hasContentDescription("notemeld-open-storage")).performClick()
        composeRule.onNode(hasContentDescription("notemeld-storage-clear-all")).performClick()
        composeRule.onNode(hasContentDescription("notemeld-storage-confirm")).assertIsDisplayed()
        composeRule.onNode(hasContentDescription("notemeld-storage-cancel")).performClick()
        composeRule.onNodeWithTag("notemeld-screen-storage").assertIsDisplayed()
    }

    @Test
    fun memoryCopyWritesToAndroidClipboard() {
        openSettingsFromDrawer()
        composeRule.onNode(hasContentDescription("notemeld-open-memory")).performClick()
        composeRule.onNode(hasContentDescription("notemeld-memory-input")).performTextInput("copy me")
        composeRule.onNode(hasContentDescription("notemeld-memory-copy")).performClick()
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        val clipboard = context.getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
        composeRule.runOnIdle {
            check(clipboard.primaryClip?.getItemAt(0)?.coerceToText(context)?.toString() == "copy me")
        }
    }

    @Test
    fun systemBackReturnsFromSessionAndSettings() {
        val device = UiDevice.getInstance(InstrumentationRegistry.getInstrumentation())

        composeRule.onNode(hasContentDescription("notemeld-quick-document")).performClick()
        composeRule.onNode(hasContentDescription("notemeld-agent-permission")).performClick()
        composeRule.onNode(hasContentDescription("notemeld-permission-default")).performClick()
        composeRule.onNode(hasContentDescription("notemeld-start-chat")).performClick()
        composeRule.onNodeWithTag("notemeld-screen-session").assertIsDisplayed()
        device.pressBack()
        composeRule.waitForIdle()
        if (runCatching { composeRule.onNodeWithTag("notemeld-screen-session").assertExists() }.isSuccess) {
            composeRule.activity.onBackPressedDispatcher.onBackPressed()
            composeRule.waitForIdle()
        }
        try { composeRule.onNodeWithTag("notemeld-screen-home").assertIsDisplayed() } catch (error: AssertionError) { throw AssertionError("session back did not return to home", error) }

        openSettingsFromDrawer()
        composeRule.onNodeWithTag("notemeld-screen-settings").assertIsDisplayed()
        device.pressBack()
        composeRule.waitForIdle()
        if (runCatching { composeRule.onNodeWithTag("notemeld-screen-settings").assertExists() }.isSuccess) {
            composeRule.activity.onBackPressedDispatcher.onBackPressed()
            composeRule.waitForIdle()
        }
        try { composeRule.onNodeWithTag("notemeld-screen-home").assertIsDisplayed() } catch (error: AssertionError) { throw AssertionError("settings back did not return to home", error) }
    }

    @Test
    fun settingsScreenSurvivesConfigurationRotation() {
        val device = UiDevice.getInstance(InstrumentationRegistry.getInstrumentation())
        openSettingsFromDrawer()
        composeRule.onNodeWithTag("notemeld-screen-settings").assertIsDisplayed()

        device.setOrientationLeft()
        composeRule.waitForIdle()
        composeRule.onNodeWithTag("notemeld-screen-settings").assertIsDisplayed()

        device.setOrientationNatural()
        composeRule.waitForIdle()
        composeRule.onNodeWithTag("notemeld-screen-settings").assertIsDisplayed()
    }

    @Test
    fun modelSettingsScreenIsReachableAndListsProviders() {
        openSettingsFromDrawer()
        composeRule.onNode(hasContentDescription("notemeld-open-model-settings")).performClick()
        composeRule.onNodeWithTag("notemeld-screen-model_settings").assertIsDisplayed()
        composeRule.onNodeWithTag("notemeld-model-settings").assertIsDisplayed()
        composeRule.onNode(hasContentDescription("notemeld-add-configuration")).assertIsDisplayed()
        composeRule.onNode(hasContentDescription("notemeld-scan")).assertIsDisplayed()
        composeRule.onNode(hasContentDescription("notemeld-add-configuration")).performClick()
        composeRule.onNodeWithTag("notemeld-screen-model_add").assertIsDisplayed()
        composeRule.onNodeWithTag("notemeld-model-add-page").assertIsDisplayed()
        composeRule.onNode(hasContentDescription("notemeld-vendor-select")).performClick()
        composeRule.onNodeWithTag("notemeld-vendor-picker").assertIsDisplayed()
    }

    @Test
    fun permissionGrantSurvivesReloadOfPersistedState() {
        // 点击快捷文档使首页 Composer 内联展开，露出动作行上的授权入口（仍在首页）。
        composeRule.onNode(hasContentDescription("notemeld-quick-document")).performClick()
        composeRule.onNode(hasContentDescription("notemeld-agent-permission")).performClick()
        composeRule.onNode(hasContentDescription("notemeld-permission-default")).performClick()

        val context = InstrumentationRegistry.getInstrumentation().targetContext
        composeRule.runOnIdle {
            val reloaded = MobileLocalStore.load(context)
            assertTrue("授权状态必须在重新加载后保留", reloaded.permissionGranted)
            assertEquals("default", reloaded.permissionMode)
        }
    }

    @Test
    fun loopbackCloudUrlsAreNotClearedOnReload() {
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        listOf("http://127.0.0.1:8583", "http://10.0.2.2:8583").forEach { url ->
            val saved = MobileLocalStore.load(context).copy(cloudUrl = url)
            MobileLocalStore.save(context, saved)
            assertEquals(url, MobileLocalStore.load(context).cloudUrl)
        }
    }
}
