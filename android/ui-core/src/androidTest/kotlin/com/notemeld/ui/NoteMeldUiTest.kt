package com.notemeld.ui

import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.hasTestTag
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.onNodeWithTag
import androidx.test.ext.junit.runners.AndroidJUnit4
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class NoteMeldUiTest {
    @get:Rule
    val composeRule = createComposeRule()

    @Test
    fun emptyAndOfflineStatesExposeStableTags() {
        composeRule.setContent {
            NoteMeldTheme(darkTheme = false) {
                NoteMeldEmptyState("No sessions", "Create one to begin")
                NoteMeldOfflineState()
            }
        }
        composeRule.onNodeWithTag("notemeld-empty-state").assertIsDisplayed()
        composeRule.onNodeWithTag("notemeld-offline-state").assertIsDisplayed()
        composeRule.onNodeWithText("No sessions").assertIsDisplayed()
    }

    @Test
    fun primaryActionUsesProvidedAccessibleTag() {
        composeRule.setContent {
            NoteMeldTheme {
                NoteMeldPrimaryButton(label = "Continue", onClick = {}, testTag = "notemeld-continue")
            }
        }
        composeRule.onNode(hasTestTag("notemeld-continue")).assertIsDisplayed()
    }

    @Test
    fun loadingAndErrorStatesExposeStableTags() {
        composeRule.setContent {
            NoteMeldTheme {
                NoteMeldLoadingState()
                NoteMeldErrorState(description = "Try again")
            }
        }
        composeRule.onNodeWithTag("notemeld-loading-state").assertIsDisplayed()
        composeRule.onNodeWithTag("notemeld-error-state").assertIsDisplayed()
    }

    @Test
    fun sharedChromeAndStatusPrimitivesExposeStableSemantics() {
        composeRule.setContent {
            NoteMeldTheme {
                NoteMeldAppBar(title = "Session", onNavigateBack = {}, navigationContentDescription = "Back")
                NoteMeldBadge("Running")
                NoteMeldSkeleton()
            }
        }
        composeRule.onNodeWithTag("notemeld-app-bar").assertIsDisplayed()
        composeRule.onNodeWithTag("notemeld-badge").assertIsDisplayed()
        composeRule.onNodeWithTag("notemeld-skeleton").assertIsDisplayed()
    }
}
