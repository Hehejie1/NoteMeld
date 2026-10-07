package com.notemeld.mobile

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class MobileSurfaceStateTest {
    @Test
    fun settingsNavigationKeepsReturnTargetAndReachesM03ToM06() {
        val settings = reduceMobileSurface(
            reduceMobileSurface(MobileSurfaceState(screen = MobileScreen.SESSION), MobileSurfaceAction.OpenSettings),
            MobileSurfaceAction.Navigate(MobileScreen.MEMORY),
        )

        assertEquals(MobileScreen.MEMORY, settings.screen)
        assertEquals(MobileScreen.SESSION, settings.settingsReturnScreen)
        assertEquals(MobileScreen.FONT_SIZE, reduceMobileSurface(settings, MobileSurfaceAction.Navigate(MobileScreen.FONT_SIZE)).screen)
        assertEquals(MobileScreen.STORAGE, reduceMobileSurface(settings, MobileSurfaceAction.Navigate(MobileScreen.STORAGE)).screen)
    }

    @Test
    fun memoryAndFontActionsAreStatefulAndOfflineSafe() {
        val withDraft = reduceMobileSurface(MobileSurfaceState(), MobileSurfaceAction.SetMemoryDraft("  keep this  "))
        val withMemory = reduceMobileSurface(withDraft, MobileSurfaceAction.AddMemory)
        assertEquals(listOf("keep this"), withMemory.memories)
        assertEquals("", withMemory.memoryDraft)

        val offline = withDraft.copy(connection = ConnectionState.OFFLINE)
        assertEquals(offline, reduceMobileSurface(offline, MobileSurfaceAction.AddMemory))

        val font = reduceMobileSurface(
            reduceMobileSurface(withMemory, MobileSurfaceAction.SetFontSize(19)),
            MobileSurfaceAction.SetFollowSystemFont(true),
        )
        assertEquals(19, font.fontSize)
        assertTrue(font.followSystemFont)
        assertEquals(16, reduceMobileSurface(font, MobileSurfaceAction.ResetFontSettings).fontSize)
    }

    @Test
    fun agentInputRespectsLocationAndConnectivity() {
        val localOffline = MobileSurfaceState(connection = ConnectionState.OFFLINE)
        assertEquals(localOffline, reduceMobileSurface(localOffline, MobileSurfaceAction.SetInputText("blocked")))

        val remoteOffline = MobileSurfaceState(location = AgentLocation.REMOTE, networkAvailable = false)
        assertEquals(remoteOffline, reduceMobileSurface(remoteOffline, MobileSurfaceAction.SetInputText("blocked")))

        val remoteReady = reduceMobileSurface(remoteOffline.copy(networkAvailable = true), MobileSurfaceAction.SetInputText("allowed"))
        assertEquals("allowed", remoteReady.inputText)
    }

    @Test
    fun memoryDeleteKeepsIdsAlignedAndRejectsInvalidIndex() {
        val state = MobileSurfaceState(
            memories = listOf("first", "second"),
            memoryIds = listOf("m1", "m2"),
        )
        val deleted = reduceMobileSurface(state, MobileSurfaceAction.DeleteMemory(0))
        assertEquals(listOf("second"), deleted.memories)
        assertEquals(listOf("m2"), deleted.memoryIds)
        assertEquals(deleted, reduceMobileSurface(deleted, MobileSurfaceAction.DeleteMemory(9)))
    }

    @Test
    fun storageClearIsOnlyAppliedByPersistenceBoundary() {
        val state = MobileSurfaceState(storage = listOf(StorageItem("cache", "缓存", "可重建", 1.0)))
        assertEquals(state, reduceMobileSurface(state, MobileSurfaceAction.ClearStorage("cache")))
    }

    @Test
    fun permissionModeGrantsAndRevokesSendAuthorization() {
        val granted = reduceMobileSurface(MobileSurfaceState(), MobileSurfaceAction.SetPermissionMode("default"))
        assertTrue(granted.permissionGranted)
        assertEquals("default", granted.permissionMode)
        assertNull(granted.sheet)

        val fullAccess = reduceMobileSurface(granted, MobileSurfaceAction.SetPermissionMode("full"))
        assertTrue(fullAccess.permissionGranted)
        assertEquals("full", fullAccess.permissionMode)

        val revoked = reduceMobileSurface(fullAccess, MobileSurfaceAction.SetPermissionMode("none"))
        assertFalse(revoked.permissionGranted)
        assertEquals("none", revoked.permissionMode)
    }

    @Test
    fun localAndCloudModelCatalogsAreHeldAsUiProjections() {
        val providers = listOf(ProviderRecord("p1", "DeepSeek", "deepseek", "openai-compatible", "https://api.deepseek.com", "bearer", null, false, 0L, 0L))
        val models = listOf(ModelRecord("m1", "p1", "deepseek-chat", "DeepSeek Chat", 128000, true, true, true, false, false, "untested", 0L, 0L))
        val withLocal = reduceMobileSurface(
            reduceMobileSurface(
                reduceMobileSurface(MobileSurfaceState(), MobileSurfaceAction.SetLocalProviders(providers)),
                MobileSurfaceAction.SetLocalModels(models),
            ),
            MobileSurfaceAction.SelectLocalModel("m1"),
        )
        assertEquals(providers, withLocal.localProviders)
        assertEquals(models, withLocal.localModels)
        assertEquals("m1", withLocal.selectedLocalModelId)
        assertNull(withLocal.sheet)

        val cloudChoices = listOf(CloudModelChoice("c1", "Cloud Model", "cloud-model", true))
        val withCloud = reduceMobileSurface(
            reduceMobileSurface(MobileSurfaceState(), MobileSurfaceAction.SetCloudModels(cloudChoices)),
            MobileSurfaceAction.SelectCloudModel("c1"),
        )
        assertEquals(cloudChoices, withCloud.cloudModels)
        assertEquals("c1", withCloud.selectedCloudModelId)

        val paired = listOf(CloudModelChoice("d1", "Paired Model", "paired-model"))
        assertEquals(paired, reduceMobileSurface(MobileSurfaceState(), MobileSurfaceAction.SetPairedModels(paired)).pairedModels)
        // The reducer must never rewrite or blank a hand-entered Cloud URL.
        assertEquals("http://127.0.0.1:8583", reduceMobileSurface(MobileSurfaceState(), MobileSurfaceAction.SetCloudUrl("http://127.0.0.1:8583")).cloudUrl)
    }

    @Test
    fun newProductM07ToM10RoutesKeepTypedContext() {
        val model = reduceMobileSurface(MobileSurfaceState(), MobileSurfaceAction.Navigate(MobileScreen.MODEL_SETTINGS))
        assertEquals(MobileScreen.MODEL_SETTINGS, model.screen)
        val remote = reduceMobileSurface(model, MobileSurfaceAction.Navigate(MobileScreen.REMOTE_SETTINGS))
        assertEquals(MobileScreen.REMOTE_SETTINGS, remote.screen)
        val artifacts = listOf(MobileArtifact("a1", "报告.md", "Markdown", "# 报告"))
        val products = reduceMobileSurface(remote, MobileSurfaceAction.SetArtifacts(artifacts))
        assertEquals(MobileScreen.REMOTE_SETTINGS, products.screen)
        val preview = reduceMobileSurface(products.copy(screen = MobileScreen.PRODUCTS), MobileSurfaceAction.OpenArtifact("a1"))
        assertEquals(MobileScreen.FILE_PREVIEW, preview.screen)
        assertEquals("a1", preview.selectedArtifactId)
    }
}
