package com.notemeld.mobile

import androidx.compose.foundation.background
import androidx.compose.foundation.Image
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.RowScope
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.material3.Button
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.DrawerValue
import androidx.compose.material3.ModalDrawerSheet
import androidx.compose.material3.ModalNavigationDrawer
import androidx.compose.material3.rememberDrawerState
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.Checkbox
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.material3.Slider
import androidx.compose.material3.Switch
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.unit.Density
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalClipboardManager
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.focus.onFocusChanged
import androidx.compose.ui.ExperimentalComposeUiApi
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.testTagsAsResourceId
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.foundation.isSystemInDarkTheme
import com.notemeld.ui.NoteMeldActionButton
import com.notemeld.ui.NoteMeldBadge
import com.notemeld.ui.NoteMeldEmptyState
import com.notemeld.ui.NoteMeldField
import com.notemeld.ui.NoteMeldOfflineState
import com.notemeld.ui.NoteMeldLoadingState
import com.notemeld.ui.NoteMeldErrorState
import com.notemeld.ui.NoteMeldToast
import com.notemeld.ui.NoteMeldSecondaryButton
import com.notemeld.ui.NoteMeldSwitchRow
import com.notemeld.ui.NoteMeldTheme
import com.notemeld.ui.NoteMeldTextButton
import com.notemeld.ui.NoteMeldTokens
import com.notemeld.ui.NoteMeldSegmentedControl
import com.notemeld.ui.NoteMeldBottomSheet
import com.notemeld.ui.NoteMeldChoiceSheet
import kotlinx.coroutines.launch
import kotlinx.coroutines.Dispatchers
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.compose.BackHandler
import androidx.activity.result.contract.ActivityResultContracts
import java.security.MessageDigest

private fun shortDeviceHash(value: String): String = MessageDigest.getInstance("SHA-256").digest(value.toByteArray()).take(6).joinToString("") { "%02x".format(it.toInt() and 0xff) }

@Composable
@OptIn(ExperimentalComposeUiApi::class)
fun MobileSurface(initialState: MobileSurfaceState = MobileSurfaceState(), tasks: List<MobileTask> = emptyList(), reduce: (MobileSurfaceState, MobileSurfaceAction) -> MobileSurfaceState = { state, action -> reduceMobileSurface(state, action) }, onSend: (String, (String, String?) -> Unit) -> Unit = { _, _ -> }, onCancelLocal: () -> Unit = {}, onSteerLocal: (String) -> Unit = {}, onCloudSend: (String, String, String?, (String, String?) -> Unit) -> Unit = { _, _, _, _ -> }, onRemoteSend: (String, RemoteDevice, String, (String, Int?) -> Unit, (String, String?) -> Unit) -> Unit = { _, _, _, _, _ -> }, onCloudLogin: (String, String, String, (String, List<CloudDevice>) -> Unit) -> Unit = { _, _, _, _ -> }, onPairingCodeScanned: (String, (Result<List<CloudModelChoice>>) -> Unit) -> Unit = { _, callback -> callback(Result.failure(IllegalStateException("扫码配对未配置"))) }, onCloudLogout: () -> Unit = {}, onCloudConfigChange: (String, String, Any?) -> Unit = { _, _, _ -> }, onLocalModelSelect: (String?) -> Unit = {}, onLocationChange: (AgentLocation) -> Unit = {}, onAddMemory: (String, (Boolean) -> Unit) -> Unit = { _, callback -> callback(false) }, onDeleteMemory: (Int, String?, (Boolean) -> Unit) -> Unit = { _, _, callback -> callback(false) }, onDeleteTask: (String, (Boolean) -> Unit) -> Unit = { _, callback -> callback(false) }) {
    var state by remember { mutableStateOf(initialState) }
    LaunchedEffect(initialState.connection, initialState.networkAvailable, initialState.memories, initialState.cloudStatus, initialState.cloudSyncRevision, initialState.cloudSyncItemCount, initialState.cloudSyncStatus, initialState.remoteDevices, initialState.selectedRemoteDeviceId) {
        state = state.copy(connection = initialState.connection, networkAvailable = initialState.networkAvailable, memories = initialState.memories, cloudStatus = initialState.cloudStatus, cloudSyncRevision = initialState.cloudSyncRevision, cloudSyncItemCount = initialState.cloudSyncItemCount, cloudSyncStatus = initialState.cloudSyncStatus, remoteDevices = initialState.remoteDevices, selectedRemoteDeviceId = initialState.selectedRemoteDeviceId)
    }
    var selectedAttachments by remember { mutableStateOf(emptyList<MobileAttachment>()) }
    val contentResolver = LocalContext.current.contentResolver
    val localContext = LocalContext.current
    val dispatch: (MobileSurfaceAction) -> Unit = { action ->
        when (action) {
            is MobileSurfaceAction.SelectModel -> onCloudConfigChange("user_preference", "default_model", action.value)
            is MobileSurfaceAction.SelectLocalModel -> onLocalModelSelect(action.id)
            is MobileSurfaceAction.SetTheme -> onCloudConfigChange("user_preference", "theme", action.value)
            is MobileSurfaceAction.SetLanguage -> onCloudConfigChange("user_preference", "language", action.value)
            is MobileSurfaceAction.SetFontSize -> onCloudConfigChange("user_preference", "font_size", action.value)
            is MobileSurfaceAction.SetFollowSystemFont -> onCloudConfigChange("user_preference", "follow_system_font", action.value)
            is MobileSurfaceAction.SetNotifications -> onCloudConfigChange("user_preference", "notifications_enabled", action.value)
            MobileSurfaceAction.ResetFontSettings -> {
                onCloudConfigChange("user_preference", "font_size", 16)
                onCloudConfigChange("user_preference", "follow_system_font", false)
            }
            else -> Unit
        }
        if (action is MobileSurfaceAction.SetLocation) onLocationChange(action.value)
        state = reduce(state, action)
    }
    val startAgentTurn: (String) -> Unit = { rawInput ->
        val input = rawInput.trim()
        if (input.isNotBlank() && canInteractWithAgent(state) && state.permissionGranted && !state.sending) {
            val handleAgentEvent: (String, String?) -> Unit = { content, terminalType ->
                if (content.isNotBlank()) dispatch(MobileSurfaceAction.AppendAssistantContent(content))
                if (terminalType != null) {
                    dispatch(MobileSurfaceAction.RecordAgentTerminal(terminalType))
                    dispatch(MobileSurfaceAction.SetSending(false))
                }
            }
            dispatch(MobileSurfaceAction.OpenTask(null, mobileText(state.language, "newSession")))
            dispatch(MobileSurfaceAction.AddMessage(MobileMessage("user", input)))
            dispatch(MobileSurfaceAction.SetInputText(""))
            dispatch(MobileSurfaceAction.ResetAgentTerminals)
            dispatch(MobileSurfaceAction.SetSending(true))
            when (state.location) {
                AgentLocation.LOCAL -> onSend(input, handleAgentEvent)
                AgentLocation.CLOUD -> onCloudSend(state.cloudUrl, input, state.selectedCloudModelId, handleAgentEvent)
                AgentLocation.REMOTE -> {
                    val selected = state.remoteDevices.firstOrNull { it.id == state.selectedRemoteDeviceId }
                    if (selected == null) {
                        handleAgentEvent("请先在设置中选择在线远程设备。", "turn.failed")
                    } else {
                        dispatch(MobileSurfaceAction.SetRemoteTransport(null))
                        onRemoteSend(state.cloudUrl, selected, input, { transport, cursor -> dispatch(MobileSurfaceAction.SetRemoteTransport(transport, cursor)) }, handleAgentEvent)
                    }
                }
            }
        }
    }
    BackHandler(enabled = state.screen != MobileScreen.HOME || state.drawerOpen || state.sheet != null) {
        when {
            state.drawerOpen || state.sheet != null -> dispatch(MobileSurfaceAction.CloseOverlay)
            state.screen == MobileScreen.SETTINGS -> dispatch(MobileSurfaceAction.CloseSettings)
            state.screen == MobileScreen.MODEL_ADD -> dispatch(MobileSurfaceAction.CloseModelAddPage)
            state.screen == MobileScreen.SESSION -> dispatch(MobileSurfaceAction.Navigate(MobileScreen.HOME))
            else -> dispatch(MobileSurfaceAction.Navigate(MobileScreen.SETTINGS))
        }
    }
    val attachmentPicker = rememberLauncherForActivityResult(ActivityResultContracts.OpenMultipleDocuments()) { uris ->
        selectedAttachments = uris.mapNotNull { uri -> runCatching {
            val bytes = contentResolver.openInputStream(uri)?.use { it.readBytes() } ?: return@runCatching null
            if (bytes.size > 10 * 1024 * 1024) return@runCatching null
            val name = uri.lastPathSegment ?: "附件"
            MobileAttachment(name, android.util.Base64.encodeToString(bytes, android.util.Base64.NO_WRAP), bytes.size, contentResolver.getType(uri) ?: "application/octet-stream")
        }.getOrNull() }
        MobileLocalStore.stageAttachments(localContext, selectedAttachments)
        selectedAttachments.forEach { dispatch(MobileSurfaceAction.AddAttachment(it.name)) }
    }
    val darkTheme = when (state.theme) {
        "dark" -> true
        "light" -> false
        else -> isSystemInDarkTheme()
    }
    val baseDensity = LocalDensity.current
    val effectiveFontScale = if (state.followSystemFont) baseDensity.fontScale else state.fontSize / 16f
    val drawerState = rememberDrawerState(if (state.drawerOpen) DrawerValue.Open else DrawerValue.Closed)
    val drawerScope = rememberCoroutineScope()
    LaunchedEffect(state.drawerOpen) {
        if (state.drawerOpen && drawerState.isClosed) drawerState.open()
        if (!state.drawerOpen && drawerState.isOpen) drawerState.close()
    }
    LaunchedEffect(drawerState.currentValue) {
        if (drawerState.isClosed && state.drawerOpen) dispatch(MobileSurfaceAction.CloseOverlay)
    }
    NoteMeldTheme(darkTheme = darkTheme) {
    CompositionLocalProvider(LocalDensity provides Density(baseDensity.density, effectiveFontScale)) {
    ModalNavigationDrawer(
        drawerState = drawerState,
        gesturesEnabled = true,
        drawerContent = {
            ModalDrawerSheet(
                modifier = Modifier.fillMaxHeight().widthIn(max = 360.dp),
                drawerContainerColor = MaterialTheme.colorScheme.surface,
                drawerShape = RoundedCornerShape(0.dp),
            ) { Drawer(state, dispatch, drawerScope) }
        },
    ) {
    Box(Modifier.fillMaxSize().background(MaterialTheme.colorScheme.background).semantics { testTagsAsResourceId = true }.testTag("notemeld-mobile-root")) {
        Text("", modifier = Modifier.size(1.dp).semantics { contentDescription = "notemeld-build-commit:${BuildConfig.BUILD_COMMIT}" })
        Column(Modifier.fillMaxSize().padding(horizontal = if (state.screen == MobileScreen.COMPONENT_LIBRARY) 0.dp else 20.dp, vertical = if (state.screen == MobileScreen.COMPONENT_LIBRARY) 0.dp else 12.dp).testTag("notemeld-screen-${state.screen.name.lowercase()}"), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            // 组件库页面渲染自带顶栏，故此处隐藏统一 Header。
            if (state.screen != MobileScreen.COMPONENT_LIBRARY) Header(state, dispatch)
            if (state.screen != MobileScreen.COMPONENT_LIBRARY) {
                if (state.connection == ConnectionState.OFFLINE && state.location == AgentLocation.LOCAL) NoteMeldOfflineState("本机服务离线 · 可切换 Cloud 或远程电脑", Modifier.fillMaxWidth().padding(horizontal = 4.dp))
                if (state.connection == ConnectionState.SYNCING) NoteMeldLoadingState("正在同步 Cloud 配置…", Modifier.fillMaxWidth())
                if (state.connection == ConnectionState.ERROR) NoteMeldErrorState("同步失败", "请检查网络或稍后重试。", modifier = Modifier.fillMaxWidth())
            }
            when (state.screen) {
                MobileScreen.HOME -> HomeScreen(state.copy(tasks = tasks), dispatch, startAgentTurn) { attachmentPicker.launch(arrayOf("*/*")) }
                MobileScreen.SESSION -> SessionScreen(state, dispatch, { attachmentPicker.launch(arrayOf("*/*")) }, onSend, onCancelLocal, onSteerLocal, onCloudSend, onRemoteSend, onDeleteTask, onLocalModelSelect)
                MobileScreen.SETTINGS -> SettingsScreen(state, dispatch)
                MobileScreen.MEMORY -> MemoryScreen(state, dispatch, onAddMemory, onDeleteMemory)
                MobileScreen.COMPONENT_LIBRARY -> ComponentLibraryScreen(state, dispatch)
                MobileScreen.FONT_SIZE -> FontScreen(state, dispatch)
                MobileScreen.STORAGE -> StorageScreen(state, dispatch)
                MobileScreen.MODEL_SETTINGS -> ModelSettingsScreen(state, dispatch)
                MobileScreen.MODEL_ADD -> ModelAddPage(state, dispatch)
                MobileScreen.REMOTE_SETTINGS -> RemoteSettingsScreen(state, dispatch)
                MobileScreen.PRODUCTS -> ProductsScreen(state, dispatch)
                MobileScreen.FILE_PREVIEW -> FilePreviewScreen(state, dispatch)
            }
        }
        if (state.sheet != null) Sheet(state, dispatch, onPairingCodeScanned) { share: ModelSharePayload.DecodedShare ->
            // model-add 分享导入：打开独立页面前不携带密钥，用户需自行补 Key
            dispatch(MobileSurfaceAction.CloseOverlay)
            dispatch(MobileSurfaceAction.ShowToast(mobileText(state.language, "configImported")))
            dispatch(MobileSurfaceAction.OpenModelAddPage(null))
        }
        state.toast?.let { NoteMeldToast(it, { dispatch(MobileSurfaceAction.ClearToast) }, Modifier.align(Alignment.TopCenter).padding(top = 12.dp, start = 12.dp, end = 12.dp)) }
    }
    }
    }
    }
}

@Composable private fun Header(s: MobileSurfaceState, d: (MobileSurfaceAction) -> Unit) {
    Row(Modifier.fillMaxWidth().height(56.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.SpaceBetween) {
        if (s.screen != MobileScreen.HOME && s.screen != MobileScreen.SESSION) {
            androidx.compose.material3.IconButton(onClick = {
                d(when (s.screen) {
                    MobileScreen.SETTINGS -> MobileSurfaceAction.CloseSettings
                    MobileScreen.MODEL_ADD -> MobileSurfaceAction.CloseModelAddPage
                    MobileScreen.FILE_PREVIEW -> MobileSurfaceAction.Navigate(MobileScreen.PRODUCTS)
                    MobileScreen.PRODUCTS -> MobileSurfaceAction.Navigate(MobileScreen.SESSION)
                    else -> MobileSurfaceAction.Navigate(MobileScreen.SETTINGS)
                })
            }, modifier = Modifier.size(48.dp).semantics { contentDescription = "notemeld-back-settings" }) {
                Icon(painterResource(com.notemeld.mobile.R.drawable.ic_back), contentDescription = "返回", tint = MaterialTheme.colorScheme.onBackground)
            }
        } else {
            androidx.compose.material3.IconButton(onClick = { d(MobileSurfaceAction.ToggleDrawer) }, modifier = Modifier.size(40.dp).shadow(8.dp, RoundedCornerShape(12.dp)).background(MaterialTheme.colorScheme.surface, RoundedCornerShape(12.dp)).semantics { contentDescription = "notemeld-open-menu" }) {
                Icon(painterResource(com.notemeld.mobile.R.drawable.ic_menu), contentDescription = null, tint = MaterialTheme.colorScheme.primary)
            }
        }
        Box(Modifier.weight(1f), contentAlignment = Alignment.Center) {
            val title = when (s.screen) {
                MobileScreen.SETTINGS -> mobileText(s.language, "settings")
                MobileScreen.MEMORY -> "记忆库"
                MobileScreen.FONT_SIZE -> "字体大小"
                MobileScreen.STORAGE -> "存储空间"
                MobileScreen.MODEL_SETTINGS -> mobileText(s.language, "modelSettings")
                MobileScreen.MODEL_ADD -> if (s.modelEditProviderId != null) mobileText(s.language, "editModel") else mobileText(s.language, "addModel")
                MobileScreen.REMOTE_SETTINGS -> mobileText(s.language, "remoteSettings")
                MobileScreen.PRODUCTS -> s.activeTaskTitle ?: "全部产物"
                MobileScreen.FILE_PREVIEW -> s.artifacts.firstOrNull { it.id == s.selectedArtifactId }?.name ?: "文件预览"
                else -> if (s.screen == MobileScreen.SESSION) s.activeTaskTitle ?: "NoteMeld" else ""
            }
            if (title.isNotBlank()) {
                if (s.screen == MobileScreen.SESSION) {
                    val location = when (s.location) {
                        AgentLocation.LOCAL -> mobileText(s.language, "localAgent")
                        AgentLocation.CLOUD -> mobileText(s.language, "cloudAgent")
                        AgentLocation.REMOTE -> mobileText(s.language, "remoteAgent")
                    }
                    val status = when {
                        !canInteractWithAgent(s) -> mobileText(s.language, "statusOfflineReadonly")
                        s.sending -> mobileText(s.language, "statusRunning")
                        s.terminalEvents.lastOrNull() == "turn.succeeded" -> mobileText(s.language, "statusCompleted")
                        s.terminalEvents.isNotEmpty() -> mobileText(s.language, "statusNeedsAttention")
                        else -> mobileText(s.language, "statusReady")
                    }
                    Column(horizontalAlignment = Alignment.CenterHorizontally) {
                        Text(title, style = MaterialTheme.typography.titleMedium, color = MaterialTheme.colorScheme.onBackground, maxLines = 1)
                        Text("$location Agent · $status", style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant, modifier = Modifier.semantics { contentDescription = "notemeld-agent-status" })
                    }
                } else {
                    Text(title, style = MaterialTheme.typography.titleLarge, color = MaterialTheme.colorScheme.onBackground)
                }
            }
        }
        if (s.screen == MobileScreen.SESSION) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                androidx.compose.material3.IconButton(onClick = { d(MobileSurfaceAction.OpenNewTask) }, modifier = Modifier.size(44.dp).semantics { contentDescription = "notemeld-new-task" }) {
                    Icon(painterResource(com.notemeld.mobile.R.drawable.ic_plus), contentDescription = null, tint = MaterialTheme.colorScheme.primary, modifier = Modifier.size(22.dp))
                }
                androidx.compose.material3.IconButton(onClick = { d(MobileSurfaceAction.ToggleActionMenu) }, modifier = Modifier.size(44.dp).semantics { contentDescription = "notemeld-session-actions" }) {
                    Icon(painterResource(com.notemeld.mobile.R.drawable.ic_more), contentDescription = null, tint = MaterialTheme.colorScheme.onSurfaceVariant, modifier = Modifier.size(22.dp))
                }
            }
        } else if (s.screen == MobileScreen.MODEL_SETTINGS || s.screen == MobileScreen.REMOTE_SETTINGS) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                androidx.compose.material3.IconButton(onClick = { d(MobileSurfaceAction.OpenSheet("model-scan")) }, modifier = Modifier.size(48.dp).semantics { contentDescription = "notemeld-scan" }) { Icon(painterResource(com.notemeld.mobile.R.drawable.ic_scan), contentDescription = mobileText(s.language, "scan"), tint = MaterialTheme.colorScheme.primary, modifier = Modifier.size(28.dp)) }
                androidx.compose.material3.IconButton(onClick = { if (s.screen == MobileScreen.MODEL_SETTINGS) d(MobileSurfaceAction.OpenModelAddPage(null)) else d(MobileSurfaceAction.ShowToast("请使用扫码或 Cloud 设备同步添加")) }, modifier = Modifier.size(48.dp).semantics { contentDescription = "notemeld-add-configuration" }) { Icon(painterResource(com.notemeld.mobile.R.drawable.ic_plus), contentDescription = mobileText(s.language, "addModel"), tint = MaterialTheme.colorScheme.primary, modifier = Modifier.size(28.dp)) }
            }
        } else if (s.screen == MobileScreen.FONT_SIZE) {
            TextButton(
                onClick = { d(MobileSurfaceAction.ShowToast("字体大小已保存")) },
                modifier = Modifier.width(64.dp).semantics { contentDescription = "notemeld-font-save" },
            ) { Text("确认") }
        } else Spacer(Modifier.width(48.dp))
    }
}

@Composable private fun HomeScreen(s: MobileSurfaceState, d: (MobileSurfaceAction) -> Unit, startAgentTurn: (String) -> Unit, pickAttachment: () -> Unit) {
    Box(Modifier.fillMaxSize().testTag("notemeld-home")) {
        Column(Modifier.fillMaxWidth().verticalScroll(rememberScrollState()).padding(top = 28.dp, bottom = 116.dp), verticalArrangement = Arrangement.spacedBy(18.dp)) {
            Row(Modifier.fillMaxWidth().semantics { contentDescription = "notemeld-home-brand" }, horizontalArrangement = Arrangement.Center, verticalAlignment = Alignment.CenterVertically) {
                Image(painterResource(com.notemeld.mobile.R.drawable.notemeld_brand), contentDescription = "NoteMeld", modifier = Modifier.size(42.dp).clip(RoundedCornerShape(13.dp)))
                Spacer(Modifier.width(10.dp))
                Text(
                    "NoteMeld",
                    style = MaterialTheme.typography.headlineSmall,
                    color = MaterialTheme.colorScheme.onBackground,
                )
            }
            Text(mobileText(s.language, "homeSlogan"), modifier = Modifier.fillMaxWidth(), textAlign = TextAlign.Center, color = MaterialTheme.colorScheme.onSurfaceVariant, style = MaterialTheme.typography.bodyMedium)
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                HomeQuickAction(mobileText(s.language, "documentProcessing"), com.notemeld.mobile.R.drawable.ic_document, "notemeld-quick-document") { d(MobileSurfaceAction.SetInputText(mobileText(s.language, "documentPrompt"))) }
                HomeQuickAction(mobileText(s.language, "presentation"), com.notemeld.mobile.R.drawable.ic_presentation, "notemeld-quick-presentation") { d(MobileSurfaceAction.SetInputText(mobileText(s.language, "presentationPrompt"))) }
                HomeQuickAction(mobileText(s.language, "workbench"), com.notemeld.mobile.R.drawable.ic_work, "notemeld-quick-workbench") { d(MobileSurfaceAction.SetInputText(mobileText(s.language, "workbenchPrompt"))) }
                HomeQuickAction(mobileText(s.language, "more"), com.notemeld.mobile.R.drawable.ic_more, "notemeld-quick-more") { d(MobileSurfaceAction.ToggleActionMenu) }
            }
            if (s.tasks.isNotEmpty()) {
                Text(mobileText(s.language, "recentTasks"), style = MaterialTheme.typography.titleMedium, modifier = Modifier.padding(top = 4.dp))
                s.tasks.take(5).forEach { task ->
                    Row(Modifier.fillMaxWidth().clickable { d(MobileSurfaceAction.OpenTask(task.id, task.title)) }.padding(vertical = 10.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                        Box(Modifier.size(36.dp).background(MaterialTheme.colorScheme.primaryContainer, RoundedCornerShape(11.dp)), contentAlignment = Alignment.Center) { Icon(painterResource(com.notemeld.mobile.R.drawable.ic_document), contentDescription = null, tint = MaterialTheme.colorScheme.primary, modifier = Modifier.size(18.dp)) }
                        Column(Modifier.weight(1f)) { Text(task.title, style = MaterialTheme.typography.bodyMedium); Text(task.status, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant) }
                    }
                }
            }
        }
        HomeComposer(s, d, startAgentTurn, pickAttachment, Modifier.align(Alignment.BottomCenter))
    }
}

@Composable private fun RowScope.HomeQuickAction(label: String, icon: Int, tag: String, onClick: () -> Unit) {
    OutlinedButton(onClick = onClick, modifier = Modifier.weight(1f).height(72.dp).semantics { contentDescription = tag }, contentPadding = androidx.compose.foundation.layout.PaddingValues(horizontal = 2.dp, vertical = 8.dp), shape = RoundedCornerShape(14.dp)) {
        Column(horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(5.dp)) {
            Icon(painterResource(icon), contentDescription = null, tint = MaterialTheme.colorScheme.primary, modifier = Modifier.size(19.dp))
            Text(label, maxLines = 1, style = MaterialTheme.typography.labelSmall)
        }
    }
}

@Composable private fun HomeComposer(
    s: MobileSurfaceState,
    d: (MobileSurfaceAction) -> Unit,
    startAgentTurn: (String) -> Unit,
    pickAttachment: () -> Unit,
    modifier: Modifier = Modifier,
    placeholderKey: String = "placeholder",
    showInlineActionMenu: Boolean = true,
    showDisclaimer: Boolean = true,
    forceExpanded: Boolean = false,
) {
    val enabled = canInteractWithAgent(s)
    val canSend = enabled && s.permissionGranted && !s.sending && s.inputText.isNotBlank()
    var inputFocused by remember { mutableStateOf(false) }
    var showNoModelDialog by remember { mutableStateOf(false) }
    val expanded = forceExpanded || inputFocused || s.inputText.isNotBlank()

    // 汇总当前可用模型（本机 / Cloud+配对）
    val availableModelLabel: String? = if (s.location == AgentLocation.LOCAL) {
        s.localModels.firstOrNull { it.id == s.selectedLocalModelId }?.displayName
            ?: s.localModels.firstOrNull { it.isDefault }?.displayName
            ?: s.localModels.firstOrNull()?.displayName
    } else {
        val cloudChoices = s.cloudModels + s.pairedModels
        cloudChoices.firstOrNull { it.id == s.selectedCloudModelId }?.let { it.name.ifBlank { it.modelId } }
            ?: cloudChoices.firstOrNull { it.isDefault }?.let { it.name.ifBlank { it.modelId } }
            ?: cloudChoices.firstOrNull()?.let { it.name.ifBlank { it.modelId } }
    }
    val hasModel = !availableModelLabel.isNullOrBlank()
    val modelLabel: String = availableModelLabel ?: mobileText(s.language, "noModel")

    Column(modifier.fillMaxWidth().padding(bottom = 4.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
        Surface(
            modifier = Modifier.fillMaxWidth().shadow(12.dp, RoundedCornerShape(20.dp)).semantics { contentDescription = "notemeld-agent-input" },
            shape = RoundedCornerShape(20.dp),
            color = MaterialTheme.colorScheme.surface,
            border = BorderStroke(1.dp, NoteMeldTokens.border),
        ) {
            Column(Modifier.fillMaxWidth().padding(horizontal = 12.dp, vertical = 10.dp)) {
              // 上部：纯输入区（高度 46，输入文本 15sp，下分隔）
              Box(Modifier.fillMaxWidth().height(46.dp)) {
                    BasicTextField(
                        value = s.inputText,
                        onValueChange = { d(MobileSurfaceAction.SetInputText(it)) },
                        enabled = enabled,
                        singleLine = true,
                        textStyle = MaterialTheme.typography.bodyLarge.copy(fontSize = 15.sp, color = MaterialTheme.colorScheme.onSurface),
                        cursorBrush = SolidColor(MaterialTheme.colorScheme.primary),
                        modifier = Modifier.fillMaxWidth().padding(bottom = 8.dp).onFocusChanged { inputFocused = it.isFocused },
                    )
                    if (s.inputText.isBlank()) Text(
                        mobileText(s.language, placeholderKey),
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        style = MaterialTheme.typography.bodyLarge.copy(fontSize = 15.sp),
                        modifier = Modifier.padding(bottom = 8.dp),
                    )
              }
              HorizontalDivider(color = NoteMeldTokens.border)
              // 底部一排：添加文件(34) · 权限 …… 模型 · 发送(44)
              Row(Modifier.fillMaxWidth().height(44.dp), verticalAlignment = Alignment.CenterVertically) {
                androidx.compose.material3.IconButton(onClick = pickAttachment, enabled = enabled && s.permissionGranted, modifier = Modifier.size(34.dp).semantics { contentDescription = "notemeld-agent-add-file" }) {
                    Icon(painterResource(com.notemeld.mobile.R.drawable.ic_plus), contentDescription = "添加附件", tint = MaterialTheme.colorScheme.primary, modifier = Modifier.size(20.dp))
                }

                TextButton(onClick = { d(MobileSurfaceAction.OpenSheet("permission")) }, enabled = enabled, contentPadding = androidx.compose.foundation.layout.PaddingValues(horizontal = 3.dp), modifier = Modifier.height(44.dp).semantics { contentDescription = "notemeld-agent-permission" }) {
                    Icon(painterResource(com.notemeld.mobile.R.drawable.ic_shield), contentDescription = null, tint = MaterialTheme.colorScheme.primary, modifier = Modifier.size(15.dp))
                    Spacer(Modifier.width(3.dp))
                    Text(mobileText(s.language, when (s.permissionMode) { "full" -> "permissionFull"; else -> "permissionDefault" }), maxLines = 1, style = MaterialTheme.typography.labelMedium, fontSize = 12.sp)
                }

                Spacer(Modifier.weight(1f))

                TextButton(onClick = {
                    if (hasModel) d(MobileSurfaceAction.OpenSheet("model")) else showNoModelDialog = true
                }, enabled = enabled, contentPadding = androidx.compose.foundation.layout.PaddingValues(horizontal = 3.dp), modifier = Modifier.height(44.dp).semantics { contentDescription = "notemeld-agent-model" }) {
                    Icon(painterResource(com.notemeld.mobile.R.drawable.ic_sparkles), contentDescription = null, tint = MaterialTheme.colorScheme.primary, modifier = Modifier.size(15.dp))
                    Spacer(Modifier.width(3.dp))
                    Text(modelLabel, maxLines = 1, style = MaterialTheme.typography.labelMedium, fontSize = 12.sp, color = if (hasModel) Color.Unspecified else MaterialTheme.colorScheme.onSurfaceVariant)
                }

                // 发送：44 圆形，内部图标 19
                Box(contentAlignment = Alignment.Center, modifier = Modifier.size(44.dp).semantics { contentDescription = "notemeld-start-chat" }) {
                    Surface(
                        onClick = { startAgentTurn(s.inputText) },
                        enabled = canSend,
                        shape = CircleShape,
                        color = if (canSend) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.surfaceVariant,
                        modifier = Modifier.size(40.dp),
                    ) {
                        Box(contentAlignment = Alignment.Center) {
                            Icon(painterResource(com.notemeld.mobile.R.drawable.ic_send), contentDescription = "发送", tint = if (canSend) MaterialTheme.colorScheme.onPrimary else MaterialTheme.colorScheme.onSurfaceVariant, modifier = Modifier.size(19.dp))
                        }
                    }
                }
              }
            }
        }
        if (showInlineActionMenu && s.showActionMenu) Card(Modifier.fillMaxWidth()) { Row(Modifier.fillMaxWidth().padding(horizontal = 8.dp, vertical = 2.dp), horizontalArrangement = Arrangement.spacedBy(4.dp)) { TextButton(onClick = pickAttachment) { Text(mobileText(s.language, "addFile")) }; TextButton(onClick = { d(MobileSurfaceAction.ShowProducts) }) { Text(mobileText(s.language, "allArtifacts")) } } }
        if (showDisclaimer) Text(mobileText(s.language, "aiDisclaimer"), color = MaterialTheme.colorScheme.onSurfaceVariant, style = MaterialTheme.typography.labelSmall, modifier = Modifier.fillMaxWidth(), textAlign = TextAlign.Center)
    }

    if (showNoModelDialog) {
        NoteMeldAlertDialog(
            onDismissRequest = { showNoModelDialog = false },
            title = mobileText(s.language, "noModelTitle"),
            text = mobileText(s.language, "noModelDesc"),
            confirmLabel = mobileText(s.language, "goSetup"),
            onConfirm = {
                showNoModelDialog = false
                d(MobileSurfaceAction.Navigate(MobileScreen.MODEL_SETTINGS))
            },
            dismissLabel = mobileText(s.language, "cancel"),
        )
    }
}

@Composable private fun ComposerChip(label: String, onClick: () -> Unit, modifier: Modifier, tag: String, icon: Int) {
    OutlinedButton(onClick = onClick, modifier = modifier.height(44.dp).semantics { contentDescription = tag }, contentPadding = androidx.compose.foundation.layout.PaddingValues(horizontal = 4.dp)) { Icon(painterResource(icon), contentDescription = null, modifier = Modifier.size(16.dp)); Spacer(Modifier.width(4.dp)); Text(label, maxLines = 1, style = MaterialTheme.typography.labelMedium) }
}

/** 统一的确认弹窗：标题/正文 + 取消、确认（确认通常用于跳转或提交）。 */
@Composable
private fun NoteMeldAlertDialog(
    onDismissRequest: () -> Unit,
    title: String,
    text: String,
    confirmLabel: String,
    onConfirm: () -> Unit,
    dismissLabel: String,
) {
    AlertDialog(
        onDismissRequest = onDismissRequest,
        title = { Text(title, style = MaterialTheme.typography.titleMedium) },
        text = { Text(text, style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant) },
        confirmButton = {
            TextButton(onClick = onConfirm) { Text(confirmLabel) }
        },
        dismissButton = {
            TextButton(onClick = onDismissRequest) { Text(dismissLabel) }
        },
    )
}

@Composable private fun SessionScreen(s: MobileSurfaceState, d: (MobileSurfaceAction) -> Unit, pickAttachment: () -> Unit, onSend: (String, (String, String?) -> Unit) -> Unit, onCancelLocal: () -> Unit, onSteerLocal: (String) -> Unit, onCloudSend: (String, String, String?, (String, String?) -> Unit) -> Unit, onRemoteSend: (String, RemoteDevice, String, (String, Int?) -> Unit, (String, String?) -> Unit) -> Unit, onDeleteTask: (String, (Boolean) -> Unit) -> Unit, onLocalModelSelect: (String?) -> Unit) {
    val canInteract = canInteractWithAgent(s)
    val handleAgentEvent: (String, String?) -> Unit = { content, terminalType ->
        if (content.isNotBlank()) d(MobileSurfaceAction.AppendAssistantContent(content))
        if (terminalType != null) {
            d(MobileSurfaceAction.RecordAgentTerminal(terminalType))
            d(MobileSurfaceAction.SetSending(false))
        }
    }
    val submit: (String) -> Unit = { rawInput ->
        val input = rawInput.trim()
        if (input.isNotBlank() && canInteract && s.permissionGranted && !s.sending) {
            d(MobileSurfaceAction.AddMessage(MobileMessage("user", input)))
            d(MobileSurfaceAction.SetInputText(""))
            d(MobileSurfaceAction.ResetAgentTerminals)
            d(MobileSurfaceAction.SetSending(true))
            when (s.location) {
                AgentLocation.LOCAL -> onSend(input, handleAgentEvent)
                AgentLocation.CLOUD -> onCloudSend(s.cloudUrl, input, s.selectedCloudModelId, handleAgentEvent)
                AgentLocation.REMOTE -> {
                    val selected = s.remoteDevices.firstOrNull { it.id == s.selectedRemoteDeviceId }
                    if (selected == null) {
                        handleAgentEvent("请先在设置中选择在线远程设备。", "turn.failed")
                    } else {
                        d(MobileSurfaceAction.SetRemoteTransport(null))
                        onRemoteSend(s.cloudUrl, selected, input, { transport, cursor -> d(MobileSurfaceAction.SetRemoteTransport(transport, cursor)) }, handleAgentEvent)
                    }
                }
            }
        }
    }
    Column(Modifier.fillMaxSize().testTag("notemeld-session-detail"), verticalArrangement = Arrangement.spacedBy(8.dp)) {
        if (s.location == AgentLocation.CLOUD && s.cloudUrl.isNotBlank()) Text(s.cloudUrl, color = MaterialTheme.colorScheme.onSurfaceVariant, style = MaterialTheme.typography.labelSmall, modifier = Modifier.fillMaxWidth().semantics { contentDescription = "notemeld-cloud-target" })
        if (s.location == AgentLocation.REMOTE) s.remoteDevices.firstOrNull { it.id == s.selectedRemoteDeviceId }?.let { device -> Text("${device.displayName} · ${shortDeviceHash(device.id)} · ${s.remoteTransport ?: "连接中"}", color = MaterialTheme.colorScheme.onSurfaceVariant, style = MaterialTheme.typography.labelSmall, modifier = Modifier.fillMaxWidth().semantics { contentDescription = "notemeld-remote-host" }) }
        if (s.location == AgentLocation.REMOTE && s.remoteCursor != null) Text("Relay 游标：${s.remoteCursor}", color = MaterialTheme.colorScheme.onSurfaceVariant, style = MaterialTheme.typography.labelSmall, modifier = Modifier.fillMaxWidth().semantics { contentDescription = "notemeld-remote-cursor" })
        if (!canInteract) NoteMeldOfflineState(if (s.location == AgentLocation.LOCAL) "本机模式离线：仅可查看已同步内容" else "网络离线：仅可查看已同步内容", Modifier.semantics { contentDescription = "notemeld-agent-offline-readonly" })
        if (s.terminalEvents.isNotEmpty()) Text("", modifier = Modifier.size(1.dp).semantics { contentDescription = "notemeld-agent-terminal:${s.terminalEvents.last()}:${s.terminalEvents.size}" })
        LazyColumn(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(14.dp), contentPadding = androidx.compose.foundation.layout.PaddingValues(vertical = 8.dp)) {
            item {
                val locationLabel = when (s.location) { AgentLocation.LOCAL -> mobileText(s.language, "localWork"); AgentLocation.CLOUD -> mobileText(s.language, "cloudWork"); AgentLocation.REMOTE -> mobileText(s.language, "remoteComputer") }
                Text(locationLabel, modifier = Modifier.fillMaxWidth(), textAlign = TextAlign.Center, color = MaterialTheme.colorScheme.onSurfaceVariant, style = MaterialTheme.typography.labelSmall)
            }
            if (s.messages.isEmpty()) item { NoteMeldEmptyState("新建会话", "继续告诉 Agent 你要完成什么。", Modifier.fillMaxWidth().padding(top = 36.dp)) }
            items(s.messages) { message -> Bubble(message.content, message.role == "user") }
            if (s.sending) item { Text("✦  NoteMeld Agent · 生成中", color = MaterialTheme.colorScheme.onSurfaceVariant, style = MaterialTheme.typography.labelMedium) }
        }
        if (s.attachments.isNotEmpty()) Text("附件：${s.attachments.joinToString()}", style = MaterialTheme.typography.bodySmall)
        if (s.location == AgentLocation.LOCAL && s.sending) {
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                OutlinedButton(onClick = { onCancelLocal(); d(MobileSurfaceAction.ShowToast("已请求取消本机 Agent")) }, modifier = Modifier.weight(1f)) { Text("取消") }
                OutlinedButton(enabled = s.inputText.isNotBlank(), onClick = { val steer = s.inputText.trim(); d(MobileSurfaceAction.SetInputText("")); onSteerLocal(steer); d(MobileSurfaceAction.ShowToast("已发送调整方向")) }, modifier = Modifier.weight(1f)) { Text("调整方向") }
            }
        }
        if (s.showActionMenu) Card(Modifier.fillMaxWidth()) { Row(Modifier.fillMaxWidth().padding(horizontal = 8.dp, vertical = 2.dp), horizontalArrangement = Arrangement.spacedBy(4.dp)) { TextButton(onClick = { d(MobileSurfaceAction.ShowProducts) }) { Text(mobileText(s.language, "allArtifacts")) }; TextButton(enabled = s.connection != ConnectionState.OFFLINE && s.permissionGranted, onClick = { val id = s.activeTaskId; if (id == null) d(MobileSurfaceAction.ShowToast("新建会话尚未保存，无法删除")) else onDeleteTask(id) { deleted -> if (deleted) { d(MobileSurfaceAction.DeleteConversation); d(MobileSurfaceAction.ShowToast("对话已删除")) } else d(MobileSurfaceAction.ShowToast("删除失败，请检查连接")) } }) { Text("删除对话", color = MaterialTheme.colorScheme.error) } } }
        HomeComposer(s, d, submit, pickAttachment, placeholderKey = "continuePlaceholder", showInlineActionMenu = false, showDisclaimer = false, forceExpanded = true)
    }
}
@Composable private fun Bubble(text: String, user: Boolean) {
    if (user) {
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.End) {
            Surface(color = MaterialTheme.colorScheme.primary, contentColor = MaterialTheme.colorScheme.onPrimary, shape = RoundedCornerShape(17.dp), modifier = Modifier.fillMaxWidth(0.86f).semantics { contentDescription = "notemeld-message-user" }) {
                Text(text, modifier = Modifier.padding(horizontal = 16.dp, vertical = 12.dp), style = MaterialTheme.typography.bodyMedium)
            }
        }
    } else {
        Column(Modifier.fillMaxWidth().semantics { contentDescription = "notemeld-message-assistant" }, verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Text("✦  NoteMeld Agent", color = MaterialTheme.colorScheme.onSurfaceVariant, style = MaterialTheme.typography.labelMedium)
            Text(text, color = MaterialTheme.colorScheme.onBackground, style = MaterialTheme.typography.bodyMedium)
        }
    }
}

@Composable
private fun SettingsScreen(
    s: MobileSurfaceState,
    d: (MobileSurfaceAction) -> Unit,
) {
    Column(Modifier.fillMaxWidth().verticalScroll(rememberScrollState()).testTag("notemeld-settings"), verticalArrangement = Arrangement.spacedBy(8.dp)) {
        SettingGroup {
            SettingRow("记忆库", "${s.memories.size} 个分类", "notemeld-open-memory") { d(MobileSurfaceAction.Navigate(MobileScreen.MEMORY)) }
            SettingRow("组件库", "Android 组件", "notemeld-open-component-library") { d(MobileSurfaceAction.Navigate(MobileScreen.COMPONENT_LIBRARY)) }
        }
        SettingGroup {
            SettingRow("模型设置", if (s.localModels.isEmpty()) "管理模型" else "${s.localProviders.size} 个 Provider · ${s.localModels.size} 个模型", "notemeld-open-model-settings") { d(MobileSurfaceAction.Navigate(MobileScreen.MODEL_SETTINGS)) }
            SettingRow("远程连接", if (s.remoteDevices.isEmpty()) "云端与设备" else "${s.remoteDevices.size} 台设备", "notemeld-open-remote-settings") { d(MobileSurfaceAction.Navigate(MobileScreen.REMOTE_SETTINGS)) }
        }
        SettingGroup {
            Row(Modifier.fillMaxWidth().height(58.dp).padding(horizontal = 16.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.SpaceBetween) {
                Text("主题")
                NoteMeldSegmentedControl(options = listOf("系统", "浅色", "深色"), selectedIndex = listOf("system", "light", "dark").indexOf(s.theme).coerceAtLeast(0), onSelected = { index -> d(MobileSurfaceAction.SetTheme(listOf("system", "light", "dark")[index])) }, modifier = Modifier.width(180.dp), contentDescriptionPrefix = "主题")
            }
            SettingRow("语言", s.language) { d(MobileSurfaceAction.OpenSheet("language")) }
            SettingRow("字体大小", "${s.fontSize}px", "notemeld-open-font-size") { d(MobileSurfaceAction.Navigate(MobileScreen.FONT_SIZE)) }
            Row(Modifier.fillMaxWidth().height(58.dp).padding(horizontal = 16.dp), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) { Text("消息通知设置"); Switch(checked = s.notificationsEnabled, onCheckedChange = { d(MobileSurfaceAction.SetNotifications(it)) }, modifier = Modifier.semantics { contentDescription = "notemeld-notifications" }) }
        }
        SettingGroup {
            SettingRow("分享日志", "生成 ZIP") { d(MobileSurfaceAction.ShowToast("日志已准备，可交由宿主分享")) }
            SettingRow("清除日志", "谨慎操作") { d(MobileSurfaceAction.ShowToast("请在存储空间中选择要清除的数据")) }
            SettingRow("存储空间", "%.2f MB".format(s.storage.sumOf { it.sizeMb }), "notemeld-open-storage") { d(MobileSurfaceAction.Navigate(MobileScreen.STORAGE)) }
        }
        Text("NoteMeld\n版本 1.4.0 · Build 20260901", color = Color(0xff7d879a), modifier = Modifier.padding(top = 24.dp))
    }
}

@Composable
private fun SettingsScreenWithTheme(s: MobileSurfaceState, d: (MobileSurfaceAction) -> Unit) {
    Column(Modifier.fillMaxWidth()) {
        Card(modifier = Modifier.fillMaxWidth(), shape = RoundedCornerShape(17.dp), border = BorderStroke(1.dp, NoteMeldTokens.border), colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface)) {
            Row(Modifier.fillMaxWidth().height(58.dp).padding(horizontal = 16.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.SpaceBetween) {
                Text("主题")
                NoteMeldSegmentedControl(options = listOf("系统", "浅色", "深色"), selectedIndex = listOf("system", "light", "dark").indexOf(s.theme).coerceAtLeast(0), onSelected = { index -> d(MobileSurfaceAction.SetTheme(listOf("system", "light", "dark")[index])) }, modifier = Modifier.width(180.dp), contentDescriptionPrefix = "主题")
            }
        }
        SettingsScreen(s, d)
    }
}

@Composable
private fun SettingRow(title: String, detail: String, contentDescription: String? = null, onClick: () -> Unit) {
    TextButton(onClick = onClick, modifier = Modifier.fillMaxWidth().height(58.dp).then(if (contentDescription == null) Modifier else Modifier.semantics { this.contentDescription = contentDescription }), contentPadding = androidx.compose.foundation.layout.PaddingValues(horizontal = 16.dp)) {
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) { Text(title); Text(detail, color = MaterialTheme.colorScheme.onSurfaceVariant) }
    }
}

@Composable
private fun SettingGroup(content: @Composable ColumnScope.() -> Unit) {
    Card(modifier = Modifier.fillMaxWidth(), shape = RoundedCornerShape(17.dp), border = BorderStroke(1.dp, NoteMeldTokens.border), colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface), content = content)
}

@Composable
private fun ModelSettingsScreen(s: MobileSurfaceState, d: (MobileSurfaceAction) -> Unit) {
    val context = LocalContext.current
    val clipboard = LocalClipboardManager.current
    val scope = rememberCoroutineScope()
    val dao = remember { ModelDao(context.applicationContext) }
    val secretStore = remember { ModelProviderSecretStore(context.applicationContext) }
    val client = remember { ModelProtocolClient() }
    DisposableEffect(Unit) { onDispose { dao.close() } }

    fun refresh() {
        scope.launch(Dispatchers.IO) {
            val providers = dao.listProviders()
            val models = dao.listAllModels()
            d(MobileSurfaceAction.SetLocalProviders(providers))
            d(MobileSurfaceAction.SetLocalModels(models))
        }
    }
    LaunchedEffect(Unit) { refresh() }

    Column(Modifier.fillMaxWidth().verticalScroll(rememberScrollState()).testTag("notemeld-model-settings"), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Text(mobileText(s.language, "providers") + " · " + mobileText(s.language, "localModels"), color = MaterialTheme.colorScheme.onSurfaceVariant, style = MaterialTheme.typography.bodySmall)
        if (s.localProviders.isEmpty()) NoteMeldEmptyState(mobileText(s.language, "noProviders"), testTag = "notemeld-model-empty")
        s.localProviders.forEach { provider ->
            val models = s.localModels.filter { it.providerId == provider.id }
            SettingGroup {
                Column(Modifier.fillMaxWidth().padding(14.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                        Icon(painterResource(com.notemeld.mobile.R.drawable.ic_work), contentDescription = null, tint = MaterialTheme.colorScheme.primary, modifier = Modifier.size(26.dp))
                        Column(Modifier.weight(1f)) {
                            Text(provider.displayName, style = MaterialTheme.typography.titleMedium)
                            Text("${provider.protocol} · ${provider.baseUrl}", color = MaterialTheme.colorScheme.onSurfaceVariant, style = MaterialTheme.typography.bodySmall, maxLines = 1)
                        }
                    }
                    if (models.isEmpty()) Text(mobileText(s.language, "noLocalModels"), color = MaterialTheme.colorScheme.onSurfaceVariant, style = MaterialTheme.typography.bodySmall)
                    models.forEach { model -> LocalModelRow(s.language, model,
                        onTest = {
                            scope.launch(Dispatchers.IO) {
                                val apiKey = secretStore.get(provider.id)?.trim().orEmpty()
                                val result = runCatching { client.testConnection(provider.protocol, provider.baseUrl, apiKey, model.modelId) }
                                    .getOrElse { error ->
                                        ModelProtocolClient.TestResult(false, (error as? ModelProtocolClient.ProtocolException)?.message ?: "连接失败", -1)
                                    }
                                val now = System.currentTimeMillis()
                                dao.updateModel(model.copy(testStatus = if (result.ok) "ok" else "failed", updatedAt = now))
                                d(MobileSurfaceAction.ShowToast(result.message))
                                refresh()
                            }
                        },
                        onSetDefault = {
                            scope.launch(Dispatchers.IO) { dao.setDefault(model); refresh() }
                        },
                        onToggle = {
                            scope.launch(Dispatchers.IO) {
                                dao.updateModel(model.copy(enabled = !model.enabled, updatedAt = System.currentTimeMillis()))
                                refresh()
                            }
                        },
                    ) }
                    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        NoteMeldSecondaryButton(mobileText(s.language, "editModel"), { d(MobileSurfaceAction.OpenModelAddPage(provider.id)) }, Modifier.weight(1f), testTag = "notemeld-provider-edit-${provider.id}")
                        NoteMeldSecondaryButton(mobileText(s.language, "shareConfig"), {
                            val link = ModelSharePayload.encode(
                                provider.vendorId, provider.displayName, provider.protocol, provider.baseUrl,
                                models.map { VendorRegistry.ModelInput(it.modelId, it.displayName, it.contextWindow) },
                            )
                            clipboard.setText(AnnotatedString(link))
                            d(MobileSurfaceAction.ShowToast(mobileText(s.language, "shareLinkCopied")))
                        }, Modifier.weight(1f), testTag = "notemeld-provider-share-${provider.id}")
                        NoteMeldSecondaryButton(mobileText(s.language, "deleteProvider"), {
                            scope.launch(Dispatchers.IO) {
                                secretStore.clear(provider.id)
                                dao.deleteProvider(provider.id)
                                refresh()
                            }
                        }, Modifier.weight(1f), testTag = "notemeld-provider-delete-${provider.id}")
                    }
                }
            }
        }
    }
}

@Composable
private fun LocalModelRow(
    language: String,
    model: ModelRecord,
    onTest: () -> Unit,
    onSetDefault: () -> Unit,
    onToggle: () -> Unit,
) {
    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        Column(Modifier.weight(1f)) {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                Text(model.displayName, style = MaterialTheme.typography.bodyMedium)
                if (model.isDefault) NoteMeldBadge(mobileText(language, "defaultBadge"))
            }
            Text("${model.modelId} · ${model.contextWindow}", color = MaterialTheme.colorScheme.onSurfaceVariant, style = MaterialTheme.typography.bodySmall, maxLines = 1)
            Text(mobileText(language, when (model.testStatus) { "ok" -> "testOk"; "failed" -> "testFailed"; else -> "testUntested" }), color = MaterialTheme.colorScheme.onSurfaceVariant, style = MaterialTheme.typography.labelSmall)
        }
        NoteMeldTextButton(onClick = onTest, modifier = Modifier.semantics { contentDescription = "notemeld-model-test-${model.id}" }) { Text(mobileText(language, "testConnection"), style = MaterialTheme.typography.labelSmall) }
        NoteMeldTextButton(onClick = onSetDefault, enabled = !model.isDefault, modifier = Modifier.semantics { contentDescription = "notemeld-model-default-${model.id}" }) { Text(mobileText(language, "setDefault"), style = MaterialTheme.typography.labelSmall) }
        NoteMeldTextButton(onClick = onToggle, modifier = Modifier.semantics { contentDescription = "notemeld-model-toggle-${model.id}" }) { Text(mobileText(language, if (model.enabled) "disableModel" else "enableModel"), style = MaterialTheme.typography.labelSmall) }
    }
}

@Composable
private fun RemoteSettingsScreen(s: MobileSurfaceState, d: (MobileSurfaceAction) -> Unit) {
    Column(Modifier.fillMaxWidth().verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Text("云端与远程设备 · 连接状态以实际验证为准", color = MaterialTheme.colorScheme.onSurfaceVariant, style = MaterialTheme.typography.bodySmall)
        if (s.remoteDevices.isEmpty()) NoteMeldEmptyState("还没有远程连接", "点击右上角 + 添加云端，或扫描一次性配对码。")
        s.remoteDevices.forEach { device ->
            SettingGroup { Row(Modifier.fillMaxWidth().padding(14.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                Icon(painterResource(com.notemeld.mobile.R.drawable.ic_work), contentDescription = null, tint = MaterialTheme.colorScheme.primary, modifier = Modifier.size(30.dp))
                Column(Modifier.weight(1f)) { Text(device.displayName, style = MaterialTheme.typography.titleMedium); Text("${device.platform} · ${if (device.online) "在线" else "离线，需重新验证"}", color = MaterialTheme.colorScheme.onSurfaceVariant, style = MaterialTheme.typography.bodySmall) }
                Icon(painterResource(com.notemeld.mobile.R.drawable.ic_chevron_right), contentDescription = null, tint = MaterialTheme.colorScheme.onSurfaceVariant)
            } }
        }
    }
}

@Composable
private fun ProductsScreen(s: MobileSurfaceState, d: (MobileSurfaceAction) -> Unit) {
    Column(Modifier.fillMaxWidth().verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(10.dp)) {
        Text("${s.artifacts.size} 个文件", color = MaterialTheme.colorScheme.onSurfaceVariant)
        if (s.artifacts.isEmpty()) NoteMeldEmptyState("当前任务暂无产物", "Agent 返回并保存到本机沙箱的文件会显示在这里。")
        s.artifacts.forEach { artifact ->
            SettingGroup { TextButton(onClick = { d(MobileSurfaceAction.OpenArtifact(artifact.id)) }, modifier = Modifier.fillMaxWidth().padding(4.dp)) {
                Row(Modifier.fillMaxWidth().padding(10.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                    Icon(painterResource(com.notemeld.mobile.R.drawable.ic_document), contentDescription = null, tint = MaterialTheme.colorScheme.primary, modifier = Modifier.size(30.dp))
                    Column(Modifier.weight(1f), horizontalAlignment = Alignment.Start) { Text(artifact.name, color = MaterialTheme.colorScheme.onSurface, style = MaterialTheme.typography.titleMedium); Text(artifact.format, color = MaterialTheme.colorScheme.onSurfaceVariant) }
                    Icon(painterResource(com.notemeld.mobile.R.drawable.ic_chevron_right), contentDescription = null, tint = MaterialTheme.colorScheme.onSurfaceVariant)
                }
            } }
        }
    }
}

@Composable
private fun FilePreviewScreen(s: MobileSurfaceState, d: (MobileSurfaceAction) -> Unit) {
    val artifact = s.artifacts.firstOrNull { it.id == s.selectedArtifactId }
    Column(Modifier.fillMaxWidth().verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        if (artifact == null) NoteMeldEmptyState("文件不存在", "返回文件列表后重新选择一个产物。")
        else {
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.End) { NoteMeldSecondaryButton("原文", { d(MobileSurfaceAction.ShowToast("当前已显示可读预览")) }) }
            SettingGroup { Column(Modifier.fillMaxWidth().padding(18.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) {
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) { Text("预览", style = MaterialTheme.typography.titleMedium); TextButton(onClick = { d(MobileSurfaceAction.ShowToast(if (artifact.downloadable) "文件已准备下载" else "该文件暂不支持下载")) }) { Text("下载") } }
                HorizontalDivider()
                Text(artifact.content ?: "该文件已由 Agent 生成，但当前设备没有可读内容。请下载原文件查看。", style = MaterialTheme.typography.bodyLarge)
            } }
        }
    }
}

@Composable
private fun MemoryScreen(
    s: MobileSurfaceState,
    d: (MobileSurfaceAction) -> Unit,
    onAddMemory: (String, (Boolean) -> Unit) -> Unit,
    onDeleteMemory: (Int, String?, (Boolean) -> Unit) -> Unit,
) {
    val clipboard = LocalClipboardManager.current
    Column(Modifier.fillMaxSize(), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Card(
            modifier = Modifier.fillMaxWidth(),
            shape = RoundedCornerShape(18.dp),
            border = BorderStroke(1.dp, NoteMeldTokens.border),
            colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
        ) {
            Row(Modifier.fillMaxWidth().padding(18.dp), verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(5.dp)) {
                    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        Text("我的记忆", style = MaterialTheme.typography.titleLarge)
                        NoteMeldBadge("${s.memories.size} 条")
                    }
                    Text("仅展示当前已同步到本机的记忆", color = MaterialTheme.colorScheme.onSurfaceVariant, style = MaterialTheme.typography.bodySmall)
                }
                TextButton(
                    onClick = {
                        val value = s.memoryDraft.trim().ifBlank { s.memories.joinToString("\n") }
                        if (value.isBlank()) d(MobileSurfaceAction.ShowToast("暂无可复制的记忆"))
                        else {
                            clipboard.setText(AnnotatedString(value))
                            d(MobileSurfaceAction.ShowToast("记忆已复制"))
                        }
                    },
                    modifier = Modifier.semantics { contentDescription = "notemeld-memory-copy" },
                ) { Text("复制") }
            }
        }

        Card(
            modifier = Modifier.fillMaxWidth().weight(1f),
            shape = RoundedCornerShape(18.dp),
            border = BorderStroke(1.dp, NoteMeldTokens.border),
            colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
        ) {
            if (s.memories.isEmpty()) {
                NoteMeldEmptyState("暂无记忆", "添加一条记忆后，它会出现在这里。", Modifier.fillMaxWidth().padding(18.dp))
            } else {
                LazyColumn(Modifier.fillMaxSize().padding(horizontal = 18.dp), verticalArrangement = Arrangement.spacedBy(0.dp)) {
                    items(s.memories.size) { index ->
                        val memory = s.memories[index]
                        Row(Modifier.fillMaxWidth().padding(vertical = 15.dp), verticalAlignment = Alignment.Top, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                                Text("记忆 ${index + 1}", style = MaterialTheme.typography.titleMedium)
                                Text(memory, color = MaterialTheme.colorScheme.onSurfaceVariant, style = MaterialTheme.typography.bodyMedium)
                            }
                            TextButton(
                                onClick = {
                                    onDeleteMemory(index, s.memoryIds.getOrNull(index)) { deleted ->
                                        if (deleted) d(MobileSurfaceAction.DeleteMemory(index))
                                        else d(MobileSurfaceAction.ShowToast("删除记忆失败，请稍后重试"))
                                    }
                                },
                                modifier = Modifier.semantics { contentDescription = "notemeld-memory-delete-$index" },
                            ) { Text("删除") }
                        }
                        if (index < s.memories.lastIndex) HorizontalDivider(color = NoteMeldTokens.border)
                    }
                }
            }
        }

        Card(
            modifier = Modifier.fillMaxWidth(),
            shape = RoundedCornerShape(18.dp),
            border = BorderStroke(1.dp, NoteMeldTokens.border),
            colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
        ) {
            Column(Modifier.fillMaxWidth().padding(12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                OutlinedTextField(
                    value = s.memoryDraft,
                    onValueChange = { d(MobileSurfaceAction.SetMemoryDraft(it)) },
                    enabled = s.connection != ConnectionState.OFFLINE,
                    modifier = Modifier.fillMaxWidth().semantics { contentDescription = "notemeld-memory-input" },
                    placeholder = { Text("告诉 NoteMeld 要记住什么…") },
                    minLines = 2,
                )
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.End) {
                    Button(
                        enabled = s.memoryDraft.isNotBlank() && s.connection != ConnectionState.OFFLINE,
                        onClick = {
                            val content = s.memoryDraft.trim()
                            onAddMemory(content) { saved ->
                                if (saved) d(MobileSurfaceAction.AddMemory)
                                else d(MobileSurfaceAction.ShowToast("记忆保存失败，请检查连接"))
                            }
                        },
                        modifier = Modifier.semantics { contentDescription = "notemeld-memory-add" },
                    ) { Text("添加记忆") }
                }
            }
        }
    }
}

@Composable
private fun FontScreen(s: MobileSurfaceState, d: (MobileSurfaceAction) -> Unit) {
    Column(Modifier.fillMaxSize(), verticalArrangement = Arrangement.spacedBy(14.dp)) {
        Card(
            modifier = Modifier.fillMaxWidth().weight(1f),
            shape = RoundedCornerShape(18.dp),
            border = BorderStroke(1.dp, NoteMeldTokens.border),
            colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
        ) {
            Column(Modifier.fillMaxSize().padding(24.dp), verticalArrangement = Arrangement.spacedBy(24.dp)) {
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.End) {
                    Surface(color = MaterialTheme.colorScheme.surfaceVariant, shape = RoundedCornerShape(14.dp)) {
                        Text("帮我预览一下字号大小", modifier = Modifier.padding(horizontal = 16.dp, vertical = 12.dp), fontSize = s.fontSize.sp)
                    }
                }
                Text("NoteMeld Agent", color = MaterialTheme.colorScheme.primary, style = MaterialTheme.typography.labelLarge)
                Text("你可以拖动下方滑块调整全局字号。合适的字号能让信息阅读更轻松，同时保持清晰的内容层级。", fontSize = s.fontSize.sp, lineHeight = (s.fontSize + 10).sp)
            }
        }
        Card(
            modifier = Modifier.fillMaxWidth(),
            shape = RoundedCornerShape(18.dp),
            border = BorderStroke(1.dp, NoteMeldTokens.border),
            colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
        ) {
            Column(Modifier.fillMaxWidth().padding(18.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                NoteMeldSwitchRow("跟随系统", s.followSystemFont, { d(MobileSurfaceAction.SetFollowSystemFont(it)) }, Modifier.semantics { contentDescription = "notemeld-font-follow-system" })
                Text("开启后字体大小将跟随系统设置", color = MaterialTheme.colorScheme.onSurfaceVariant, style = MaterialTheme.typography.bodySmall)
                HorizontalDivider(color = NoteMeldTokens.border)
                Slider(
                    value = s.fontSize.toFloat(),
                    onValueChange = { d(MobileSurfaceAction.SetFontSize(it.toInt())) },
                    enabled = !s.followSystemFont,
                    valueRange = 13f..19f,
                    steps = 5,
                    modifier = Modifier.semantics { contentDescription = "notemeld-font-slider" },
                )
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
                    Text("A", color = MaterialTheme.colorScheme.onSurfaceVariant)
                    Text(if (s.followSystemFont) "跟随系统" else "${s.fontSize}px", color = MaterialTheme.colorScheme.onSurfaceVariant, style = MaterialTheme.typography.labelLarge)
                    Text("A", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 28.sp)
                }
                TextButton(
                    onClick = {
                        d(MobileSurfaceAction.ResetFontSettings)
                        d(MobileSurfaceAction.ShowToast("已恢复默认字体设置"))
                    },
                    modifier = Modifier.align(Alignment.End).semantics { contentDescription = "notemeld-font-reset" },
                ) { Text("恢复默认") }
            }
        }
    }
}
@Composable private fun StorageScreen(s: MobileSurfaceState, d: (MobileSurfaceAction) -> Unit) {
    var confirmOpen by remember { mutableStateOf(false) }
    var pendingId by remember { mutableStateOf<String?>(null) }
    val pendingTitle = pendingId?.let { id -> s.storage.firstOrNull { it.id == id }?.title } ?: "全部本地数据"
    val totalMb = s.storage.sumOf { it.sizeMb }
    Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(14.dp)) {
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.Bottom) {
            Column(verticalArrangement = Arrangement.spacedBy(5.dp)) {
                Text("NoteMeld 占用空间", color = MaterialTheme.colorScheme.onSurfaceVariant)
                Text("%.2f MB".format(totalMb), style = MaterialTheme.typography.displaySmall)
            }
            TextButton(onClick = { pendingId = null; confirmOpen = true }, modifier = Modifier.semantics { contentDescription = "notemeld-storage-clear-all" }) { Text("全部清除", color = MaterialTheme.colorScheme.error) }
        }
        Box(Modifier.fillMaxWidth().height(7.dp).background(MaterialTheme.colorScheme.surfaceVariant, RoundedCornerShape(8.dp))) {
            if (totalMb > 0.0) Box(Modifier.fillMaxWidth().height(7.dp).background(MaterialTheme.colorScheme.primary, RoundedCornerShape(8.dp)))
        }
        Text("以下数字来自本机实际统计。清理不会删除 Cloud 账号、设备身份或安全凭据。", color = MaterialTheme.colorScheme.onSurfaceVariant, style = MaterialTheme.typography.bodySmall)
        Card(
            modifier = Modifier.fillMaxWidth(),
            shape = RoundedCornerShape(18.dp),
            border = BorderStroke(1.dp, NoteMeldTokens.border),
            colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
        ) {
            if (s.storage.isEmpty()) {
                NoteMeldEmptyState("暂无可清理数据", "缓存、会话和下载文件的实际占用会显示在这里。", Modifier.fillMaxWidth().padding(18.dp))
            }
            s.storage.forEachIndexed { index, item ->
                Column(Modifier.fillMaxWidth().padding(horizontal = 18.dp, vertical = 14.dp), verticalArrangement = Arrangement.spacedBy(9.dp)) {
                    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(12.dp), verticalAlignment = Alignment.CenterVertically) {
                        Box(Modifier.size(38.dp).background(MaterialTheme.colorScheme.primaryContainer, RoundedCornerShape(12.dp)), contentAlignment = Alignment.Center) {
                            Icon(painterResource(com.notemeld.mobile.R.drawable.ic_document), contentDescription = null, tint = MaterialTheme.colorScheme.primary, modifier = Modifier.size(20.dp))
                        }
                        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(3.dp)) {
                            Text(item.title, style = MaterialTheme.typography.titleMedium)
                            Text("%.2f MB".format(item.sizeMb), style = MaterialTheme.typography.titleLarge)
                        }
                        NoteMeldSecondaryButton(label = "清除", onClick = { pendingId = item.id; confirmOpen = true }, contentDescription = "notemeld-storage-clear-${item.id}")
                    }
                    Text(item.description, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    Box(Modifier.fillMaxWidth().height(4.dp).background(MaterialTheme.colorScheme.surfaceVariant, RoundedCornerShape(4.dp))) {
                        if (item.sizeMb > 0.0 && totalMb > 0.0) Box(Modifier.fillMaxWidth((item.sizeMb / totalMb).toFloat().coerceIn(0.02f, 1f)).height(4.dp).background(MaterialTheme.colorScheme.primary, RoundedCornerShape(4.dp)))
                    }
                }
                if (index < s.storage.lastIndex) HorizontalDivider(color = NoteMeldTokens.border)
            }
        }
    }
    if (confirmOpen) {
        AlertDialog(
            onDismissRequest = { confirmOpen = false; pendingId = null },
            title = { Text("确认清除") },
            text = { Text("将清除“$pendingTitle”对应的文件和可重建同步元数据。无法确认已同步的会话数据会保留；不会删除 Cloud 账号、设备身份或安全凭据。") },
            confirmButton = { TextButton(onClick = { val id = pendingId; confirmOpen = false; pendingId = null; d(MobileSurfaceAction.ClearStorage(id)) }, modifier = Modifier.semantics { contentDescription = "notemeld-storage-confirm" }) { Text("确认清除") } },
            dismissButton = { TextButton(onClick = { confirmOpen = false; pendingId = null }, modifier = Modifier.semantics { contentDescription = "notemeld-storage-cancel" }) { Text("取消") } },
        )
    }
}
@Composable private fun Drawer(s: MobileSurfaceState, d: (MobileSurfaceAction) -> Unit, scope: kotlinx.coroutines.CoroutineScope) {
    Column(Modifier.fillMaxSize().padding(horizontal = 24.dp, vertical = 28.dp), verticalArrangement = Arrangement.SpaceBetween) {
        Column(Modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.SpaceBetween) {
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Image(painterResource(com.notemeld.mobile.R.drawable.notemeld_brand), contentDescription = "NoteMeld", modifier = Modifier.size(28.dp).clip(RoundedCornerShape(9.dp)))
                    Text("NoteMeld", style = MaterialTheme.typography.titleMedium)
                }
                NoteMeldTextButton(onClick = { scope.launch { d(MobileSurfaceAction.CloseOverlay) } }, modifier = Modifier.semantics { contentDescription = "notemeld-close-menu" }) { Text("关闭") }
            }
            HorizontalDivider(color = MaterialTheme.colorScheme.outlineVariant)
            NoteMeldSegmentedControl(options = listOf("本地工作", "云端工作", "远程电脑"), selectedIndex = listOf(AgentLocation.LOCAL, AgentLocation.CLOUD, AgentLocation.REMOTE).indexOf(s.selectedWorkTab).coerceAtLeast(0), onSelected = { index -> val location = listOf(AgentLocation.LOCAL, AgentLocation.CLOUD, AgentLocation.REMOTE)[index]; d(MobileSurfaceAction.SetWorkTab(location)); d(MobileSurfaceAction.SetLocation(location)) }, contentDescriptionPrefix = "工作模式")
            Row(Modifier.fillMaxWidth().padding(top = 6.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.SpaceBetween) {
                Text("任务", style = MaterialTheme.typography.titleMedium)
                TextButton(onClick = { d(MobileSurfaceAction.OpenNewTask) }, modifier = Modifier.semantics { contentDescription = "notemeld-new-task" }) { Icon(painterResource(com.notemeld.mobile.R.drawable.ic_plus), contentDescription = null, modifier = Modifier.size(15.dp)); Spacer(Modifier.width(4.dp)); Text(mobileText(s.language, "newTask")) }
            }
            if (s.tasks.isEmpty()) {
                Text(mobileText(s.language, "emptyTasks"), color = MaterialTheme.colorScheme.onSurfaceVariant, modifier = Modifier.padding(vertical = 8.dp))
            } else s.tasks.take(8).forEach { task ->
                TextButton(onClick = { d(MobileSurfaceAction.OpenTask(task.id, task.title)) }, modifier = Modifier.fillMaxWidth()) {
                    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) { Text(task.title, color = MaterialTheme.colorScheme.onSurface); Text(task.status, color = MaterialTheme.colorScheme.onSurfaceVariant) }
                }
            }
        }
        Column(Modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            HorizontalDivider(color = MaterialTheme.colorScheme.outlineVariant)
            Row(Modifier.fillMaxWidth().padding(horizontal = 4.dp), verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp), horizontalAlignment = Alignment.Start) {
                    Text("${android.os.Build.MODEL}", color = MaterialTheme.colorScheme.onSurface, style = MaterialTheme.typography.bodyMedium)
                    Text("NoteMeld Mobile · v${BuildConfig.VERSION_NAME}", color = MaterialTheme.colorScheme.onSurfaceVariant, style = MaterialTheme.typography.bodySmall)
                }
                androidx.compose.material3.IconButton(
                    onClick = { d(MobileSurfaceAction.OpenSettings) },
                    modifier = Modifier.size(40.dp).semantics { contentDescription = "notemeld-open-settings" },
                ) {
                    Icon(painterResource(com.notemeld.mobile.R.drawable.ic_settings), contentDescription = null, tint = MaterialTheme.colorScheme.primary, modifier = Modifier.size(22.dp))
                }
            }
        }
    }
}
@Composable
private fun Sheet(
    s: MobileSurfaceState,
    d: (MobileSurfaceAction) -> Unit,
    onPairingCodeScanned: (String, (Result<List<CloudModelChoice>>) -> Unit) -> Unit,
    onModelShare: (ModelSharePayload.DecodedShare) -> Unit,
) {
    when (s.sheet) {
        "model-scan" -> ModelPairingScannerSheet(
            language = s.language,
            onDismiss = { d(MobileSurfaceAction.CloseOverlay) },
            onPairingCode = { code, scannerCallback ->
                onPairingCodeScanned(code) { result: Result<List<CloudModelChoice>> ->
                    result.onSuccess { models ->
                        d(MobileSurfaceAction.SetPairedModels(models))
                        d(MobileSurfaceAction.CloseOverlay)
                        d(MobileSurfaceAction.ShowToast(mobileText(s.language, "scannerPairOk").format(models.size)))
                    }.onFailure { error -> d(MobileSurfaceAction.ShowToast(error.message ?: mobileText(s.language, "scannerPairFail"))) }
                    scannerCallback(result.map { models -> models.map { it.name.ifBlank { it.modelId } } })
                }
            },
            onModelShare = onModelShare,
        )
        "permission" -> NoteMeldBottomSheet(mobileText(s.language, "permissionTitle"), { d(MobileSurfaceAction.CloseOverlay) }, eyebrow = mobileText(s.language, "sessionSettings"), testTag = "notemeld-permission-sheet") {
            PermissionChoice(
                title = mobileText(s.language, "permissionDefault"),
                description = mobileText(s.language, "permissionDefaultDescription"),
                selected = s.permissionMode == "default",
                testTag = "notemeld-permission-default",
            ) { d(MobileSurfaceAction.SetPermissionMode("default")) }
            PermissionChoice(
                title = mobileText(s.language, "permissionFull"),
                description = mobileText(s.language, "permissionFullDescription"),
                selected = s.permissionMode == "full",
                testTag = "notemeld-permission-full",
            ) { d(MobileSurfaceAction.SetPermissionMode("full")) }
        }
        "model" -> {
            if (s.location == AgentLocation.LOCAL) {
                val enabledModels = s.localModels.filter { it.enabled }
                val options = enabledModels.map { it.displayName }
                val selected = enabledModels.firstOrNull { it.id == s.selectedLocalModelId }?.displayName
                NoteMeldChoiceSheet(mobileText(s.language, "modelSelection"), options.ifEmpty { listOf(mobileText(s.language, "noLocalModels")) }, selected, { label ->
                    if (label != mobileText(s.language, "noLocalModels")) {
                        enabledModels.firstOrNull { it.displayName == label }?.let { d(MobileSurfaceAction.SelectLocalModel(it.id)) }
                    }
                }, { d(MobileSurfaceAction.CloseOverlay) })
            } else {
                val cloudChoices = (s.cloudModels + s.pairedModels).distinctBy { it.id }
                fun CloudModelChoice.label() = name.ifBlank { modelId }
                val options = cloudChoices.map { it.label() }
                val selectedId = s.selectedCloudModelId
                val selectedLabel = cloudChoices.firstOrNull { it.id == selectedId }?.label()
                NoteMeldChoiceSheet(mobileText(s.language, "modelSelection"), options.ifEmpty { listOf(mobileText(s.language, "noModels")) }, selectedLabel, { label ->
                    val pick = cloudChoices.firstOrNull { it.label() == label }
                    if (pick != null) d(MobileSurfaceAction.SelectCloudModel(pick.id))
                }, { d(MobileSurfaceAction.CloseOverlay) })
            }
        }
        "theme" -> NoteMeldChoiceSheet("选择主题", listOf("system", "light", "dark"), s.theme, { d(MobileSurfaceAction.SetTheme(it)) }, { d(MobileSurfaceAction.CloseOverlay) })
        "products" -> NoteMeldBottomSheet("当前会话产物", { d(MobileSurfaceAction.CloseOverlay) }) { Text("当前移动端只展示已由真实 Agent 事件返回并落入沙箱的产物。请从会话的“全部产物”进入文件列表。", color = MaterialTheme.colorScheme.onSurfaceVariant, modifier = Modifier.padding(vertical = 12.dp)) }
        else -> NoteMeldChoiceSheet("选择语言", listOf("跟随系统", "简体中文", "繁體中文", "English"), s.language, { d(MobileSurfaceAction.SetLanguage(it)) }, { d(MobileSurfaceAction.CloseOverlay) })
    }
}

@Composable
private fun PermissionChoice(title: String, description: String, selected: Boolean, testTag: String, onClick: () -> Unit) {
    Surface(
        onClick = onClick,
        modifier = Modifier.fillMaxWidth().semantics { contentDescription = testTag },
        shape = RoundedCornerShape(16.dp),
        color = if (selected) MaterialTheme.colorScheme.primaryContainer else MaterialTheme.colorScheme.surface,
        border = BorderStroke(1.dp, if (selected) MaterialTheme.colorScheme.primary else NoteMeldTokens.border),
    ) {
        Row(Modifier.fillMaxWidth().padding(16.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            Text(if (selected) "✓" else "◇", color = if (selected) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.onSurfaceVariant, style = MaterialTheme.typography.titleLarge)
            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                Text(title, style = MaterialTheme.typography.titleMedium)
                Text(description, color = MaterialTheme.colorScheme.onSurfaceVariant, style = MaterialTheme.typography.bodySmall)
            }
        }
    }
}

/** 添加/编辑页面内的候选模型行。 */
private data class CandidateModel(
    val id: String,
    val selected: Boolean,
)

/**
 * 添加/编辑模型：独立全屏页面（非底部弹窗）。
 * - 服务商经底部弹窗（固定高度、滚动）选择；预设厂商名称/地址只读，自定义可编辑；
 * - 拉取模型后在固定高度列表里多选；测试连接结果以顶部 toast 反馈。
 */
@Composable
private fun ModelAddPage(s: MobileSurfaceState, d: (MobileSurfaceAction) -> Unit) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val dao = remember { ModelDao(context.applicationContext) }
    val secretStore = remember { ModelProviderSecretStore(context.applicationContext) }
    val client = remember { ModelProtocolClient() }
    DisposableEffect(Unit) { onDispose { dao.close() } }

    val editingId = s.modelEditProviderId
    val editing = editingId?.let { runCatching { dao.getProvider(it) }.getOrNull() }

    var vendorId: String? by remember { mutableStateOf(editing?.vendorId) }
    var customName by remember { mutableStateOf(if (editing?.vendorId == "custom") editing.displayName else "") }
    var customUrl by remember { mutableStateOf(if (editing?.vendorId == "custom") editing.baseUrl else "") }
    var apiKey by remember { mutableStateOf("") }
    var candidates: List<CandidateModel> by remember {
        mutableStateOf(
            editingId?.let { id -> dao.listModels(id).map { CandidateModel(it.modelId, true) } }
                ?: emptyList(),
        )
    }
    var vendorPickerOpen by remember { mutableStateOf(false) }
    var busy by remember { mutableStateOf(false) }
    var statusText by remember { mutableStateOf<String?>(null) }

    val vendor = VendorRegistry.getVendor(vendorId)
    val isCustom = vendor?.custom == true
    val protocol = vendor?.protocol?.takeIf { it != "bedrock" } ?: "openai-compatible"
    val needsKey = VendorRegistry.getProtocol(protocol)?.needsKey ?: true
    val effectiveName = if (isCustom) customName.trim() else vendor?.name.orEmpty()
    val effectiveUrl = VendorRegistry.trimUrl(if (isCustom) customUrl else vendor?.baseUrl.orEmpty())

    fun effectiveKey(): String {
        val typed: String = apiKey.trim()
        if (typed.isNotBlank()) return typed
        return editingId?.let { id -> secretStore.get(id)?.trim().orEmpty() } ?: ""
    }

    Column(Modifier.fillMaxSize().testTag("notemeld-model-add-page")) {
        Column(
            Modifier.fillMaxWidth().verticalScroll(rememberScrollState())
                .padding(horizontal = 4.dp).weight(1f),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            // 服务商 select
            Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                Text(mobileText(s.language, "provider"), style = MaterialTheme.typography.labelMedium)
                Surface(
                    onClick = { vendorPickerOpen = true },
                    modifier = Modifier.fillMaxWidth().semantics { contentDescription = "notemeld-vendor-select" },
                    shape = RoundedCornerShape(12.dp),
                    color = MaterialTheme.colorScheme.surface,
                    border = BorderStroke(1.dp, NoteMeldTokens.border),
                ) {
                    Row(Modifier.fillMaxWidth().padding(horizontal = 14.dp, vertical = 13.dp), verticalAlignment = Alignment.CenterVertically) {
                        Text(vendor?.name ?: mobileText(s.language, "selectVendor"), Modifier.weight(1f), style = MaterialTheme.typography.bodyMedium, color = if (vendor == null) NoteMeldTokens.mutedText else MaterialTheme.colorScheme.onSurface)
                        Icon(painterResource(com.notemeld.mobile.R.drawable.ic_chevron_right), contentDescription = null, tint = NoteMeldTokens.mutedText, modifier = Modifier.size(18.dp))
                    }
                }
            }

            // 配置名称
            Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                Text(mobileText(s.language, "provider"), style = MaterialTheme.typography.labelMedium)
                NoteMeldField(
                    effectiveName, {}, mobileText(s.language, "provider"),
                    enabled = isCustom,
                    testTag = "notemeld-model-provider",
                )
            }

            // Base URL
            Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                Text(mobileText(s.language, "baseUrl"), style = MaterialTheme.typography.labelMedium)
                NoteMeldField(
                    effectiveUrl, {}, mobileText(s.language, "baseUrl"),
                    enabled = isCustom,
                    testTag = "notemeld-model-url",
                )
            }
            Text(mobileText(s.language, "protocol") + " · $protocol", color = MaterialTheme.colorScheme.onSurfaceVariant, style = MaterialTheme.typography.bodySmall)

            // API 密钥
            if (needsKey) {
                Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    Text(mobileText(s.language, "apiKey"), style = MaterialTheme.typography.labelMedium)
                    NoteMeldField(
                        apiKey, { apiKey = it }, mobileText(s.language, "apiKey"),
                        visualTransformation = PasswordVisualTransformation(),
                        placeholder = if (editing?.hasApiKey == true) mobileText(s.language, "apiKeyHint") else null,
                        testTag = "notemeld-model-api-key",
                    )
                }
            }

            // 拉取 / 测试
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                NoteMeldSecondaryButton(mobileText(s.language, "fetchModels"), {
                    if (vendor == null) { d(MobileSurfaceAction.ShowToast(mobileText(s.language, "selectVendor"))); return@NoteMeldSecondaryButton }
                    busy = true
                    statusText = mobileText(s.language, "discovering")
                    scope.launch(Dispatchers.IO) {
                        val result = runCatching { client.discover(protocol, effectiveUrl, effectiveKey()) }
                        result.onSuccess { remote ->
                            val existingIds = candidates.map { it.id }.toSet()
                            candidates = candidates + remote.filter { it.id !in existingIds }.map { CandidateModel(it.id, true) }
                            statusText = null
                        }.onFailure { error -> statusText = error.message ?: mobileText(s.language, "discoverFailed") }
                        busy = false
                    }
                }, Modifier.weight(1f), enabled = !busy, testTag = "notemeld-model-fetch")
                NoteMeldSecondaryButton(mobileText(s.language, "testConnection"), {
                    if (vendor == null) { d(MobileSurfaceAction.ShowToast(mobileText(s.language, "selectVendor"))); return@NoteMeldSecondaryButton }
                    val testModel = candidates.firstOrNull { it.selected }?.id ?: ""
                    if (needsKey) {
                        if (effectiveUrl.isBlank()) { d(MobileSurfaceAction.ShowToast(mobileText(s.language, "baseUrl"))); return@NoteMeldSecondaryButton }
                        if (testModel.isBlank()) { d(MobileSurfaceAction.ShowToast(mobileText(s.language, "modelSelection"))); return@NoteMeldSecondaryButton }
                    }
                    busy = true
                    scope.launch(Dispatchers.IO) {
                        val result = runCatching { client.testConnection(protocol, effectiveUrl, effectiveKey(), testModel) }
                            .getOrElse { error ->
                                ModelProtocolClient.TestResult(false, (error as? ModelProtocolClient.ProtocolException)?.message ?: mobileText(s.language, "testFailed"), -1)
                            }
                        d(MobileSurfaceAction.ShowToast(result.message))
                        busy = false
                    }
                }, Modifier.weight(1f), enabled = !busy, testTag = "notemeld-model-test")
            }

            // 模型多选（固定高度滚动）
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
                Text(mobileText(s.language, "modelSelection"), style = MaterialTheme.typography.labelMedium)
                NoteMeldTextButton(onClick = {
                    val allSelected = candidates.isNotEmpty() && candidates.all { it.selected }
                    candidates = candidates.map { it.copy(selected = !allSelected) }
                }) { Text(if (candidates.isNotEmpty() && candidates.all { it.selected }) mobileText(s.language, "cancel") else mobileText(s.language, "confirm"), style = MaterialTheme.typography.labelSmall) }
            }
            Surface(
                Modifier.fillMaxWidth().heightIn(max = 260.dp),
                shape = RoundedCornerShape(12.dp),
                color = MaterialTheme.colorScheme.surface,
                border = BorderStroke(1.dp, NoteMeldTokens.border),
            ) {
                if (candidates.isEmpty()) {
                    Text(mobileText(s.language, "noLocalModels"), Modifier.padding(16.dp), color = NoteMeldTokens.mutedText, style = MaterialTheme.typography.bodySmall)
                } else {
                    Column(Modifier.verticalScroll(rememberScrollState())) {
                        candidates.forEachIndexed { index, model ->
                            Row(
                                Modifier.fillMaxWidth()
                                    .clickable {
                                        candidates = candidates.toMutableList().also { it[index] = model.copy(selected = !model.selected) }
                                    }
                                    .padding(horizontal = 14.dp, vertical = 12.dp),
                                verticalAlignment = Alignment.CenterVertically,
                                horizontalArrangement = Arrangement.spacedBy(10.dp),
                            ) {
                                Checkbox(checked = model.selected, onCheckedChange = { checked ->
                                    candidates = candidates.toMutableList().also { it[index] = model.copy(selected = checked) }
                                })
                                Text(model.id, style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurface)
                            }
                        }
                    }
                }
            }
            statusText?.let { Text(it, color = MaterialTheme.colorScheme.onSurfaceVariant, style = MaterialTheme.typography.bodySmall) }
        }

        // 底部保存
        NoteMeldActionButton(
            onClick = {
                val picked = candidates.filter { it.selected }
                val keyProvided = apiKey.trim().isNotBlank()
                val inputs = picked.map { VendorRegistry.ModelInput(it.id, null, VendorRegistry.DEFAULT_CONTEXT) }
                val errors = VendorRegistry.validateModelConfig(
                    effectiveName, protocol, effectiveUrl, apiKey,
                    hasStoredKey = editing?.hasApiKey == true || keyProvided,
                    models = inputs,
                    duplicateNames = if (editing == null) ModelSchema.duplicateModelIds(emptyList(), dao.listAllModels().map { it.modelId }) else emptyList(),
                )
                if (errors.isNotEmpty()) { d(MobileSurfaceAction.ShowToast(errors.values.first())); return@NoteMeldActionButton }
                scope.launch(Dispatchers.IO) {
                    val now = System.currentTimeMillis()
                    val providerId = editing?.id ?: java.util.UUID.randomUUID().toString()
                    val keyRef = if (keyProvided) {
                        secretStore.put(providerId, apiKey.trim())
                        secretStore.keyRef(providerId)
                    } else editing?.keyRef
                    val record = ProviderRecord(
                        id = providerId,
                        displayName = effectiveName,
                        vendorId = vendorId ?: "custom",
                        protocol = protocol,
                        baseUrl = effectiveUrl,
                        authType = if (needsKey) "bearer" else "none",
                        keyRef = keyRef,
                        hasApiKey = keyRef != null,
                        createdAt = editing?.createdAt ?: now,
                        updatedAt = now,
                    )
                    if (editing == null) dao.createProvider(record) else dao.updateProvider(record)
                    val modelRows = picked.map { m ->
                        ModelRecord(
                            id = java.util.UUID.randomUUID().toString(),
                            providerId = providerId,
                            modelId = m.id,
                            displayName = m.id,
                            contextWindow = VendorRegistry.DEFAULT_CONTEXT,
                            enabled = true,
                            isDefault = false,
                            testStatus = "untested",
                            createdAt = now,
                            updatedAt = now,
                        )
                    }
                    dao.replaceModels(providerId, modelRows)
                    d(MobileSurfaceAction.SetLocalProviders(dao.listProviders()))
                    d(MobileSurfaceAction.SetLocalModels(dao.listAllModels()))
                    d(MobileSurfaceAction.CloseModelAddPage)
                }
            },
            enabled = vendor != null && !busy,
            modifier = Modifier.fillMaxWidth().padding(horizontal = 4.dp, vertical = 10.dp).semantics { contentDescription = "notemeld-model-save" },
        ) { Text(mobileText(s.language, "saveConfig")) }
    }

    // 服务商选择底部弹窗：固定高度滚动
    if (vendorPickerOpen) {
        NoteMeldBottomSheet(
            title = mobileText(s.language, "selectVendor"),
            onDismiss = { vendorPickerOpen = false },
            eyebrow = mobileText(s.language, "modelSettings"),
            testTag = "notemeld-vendor-picker",
        ) {
            Column(
                Modifier.fillMaxWidth().heightIn(max = 320.dp).verticalScroll(rememberScrollState()),
                verticalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                VendorRegistry.MODEL_VENDORS.forEach { option ->
                    val unsupported = option.unsupported
                    Surface(
                        onClick = {
                            if (unsupported == null) {
                                vendorId = option.id
                                vendorPickerOpen = false
                            }
                        },
                        enabled = unsupported == null,
                        modifier = Modifier.fillMaxWidth().semantics { contentDescription = "notemeld-vendor-${option.id}" },
                        shape = RoundedCornerShape(12.dp),
                        color = if (option.id == vendorId) MaterialTheme.colorScheme.primaryContainer else MaterialTheme.colorScheme.surfaceVariant,
                        border = BorderStroke(1.dp, NoteMeldTokens.border),
                    ) {
                        Row(Modifier.fillMaxWidth().padding(horizontal = 14.dp, vertical = 13.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                            Column(Modifier.weight(1f)) {
                                Text(option.name, style = MaterialTheme.typography.bodyMedium, color = if (unsupported != null) NoteMeldTokens.mutedText else MaterialTheme.colorScheme.onSurface)
                                Text(unsupported ?: VendorRegistry.trimUrl(option.baseUrl).ifBlank { if (option.custom) "手动填写" else "地址待确认" }, style = MaterialTheme.typography.bodySmall, color = NoteMeldTokens.mutedText)
                            }
                        }
                    }
                }
            }
        }
    }
}

/** 组件库模块定义：按 label 分组，androidImpl 描述该组件在 Android 的实现。 */
private data class ComponentLibItem(val id: String, val name: String, val androidImpl: String)
private data class ComponentLibGroup(val label: String, val items: List<ComponentLibItem>)

private val componentLibraryGroups: List<ComponentLibGroup> = listOf(
    ComponentLibGroup("基础设计", listOf(
        ComponentLibItem("color", "Color 颜色", "语义色板由 NoteMeldTheme 提供：lightColorScheme/darkColorScheme（primary、surface、error 等），Compose Color 随主题切换。"),
        ComponentLibItem("spacing", "Spacing 间距", "NoteMeldTokens：spacingXs/Sm/Md/Lg（4/8/12/20 dp），统一 spacedBy 与 padding。"),
        ComponentLibItem("radius", "Radius 圆角", "Material shapes：7/9/12/14 dp；RoundedCornerShape。"),
        ComponentLibItem("typography", "Typography 字体规范", "MaterialTheme.typography：body/title/label 统一字号行高。"),
        ComponentLibItem("iconography", "Iconography 图标", "Compose Icon + painterResource 矢量资源，tint 跟随主题。"),
        ComponentLibItem("layout", "Layout 布局", "Column/Row/Box + weight、Arrangement；ModalBottomSheet 统一弹窗。"),
        ComponentLibItem("motion", "Motion 动画", "animateColorAsState、AnimatedVisibility 与 BottomSheet 内建过渡。"),
    )),
    ComponentLibGroup("通用", listOf(
        ComponentLibItem("button", "Button 按钮", "NoteMeldActionButton/PrimaryButton：Material Button，containerColor=primary。"),
        ComponentLibItem("icon-button", "Icon Button 图标按钮", "NoteMeldIconButton：48 dp 点击目标，强制 contentDescription。"),
    )),
    ComponentLibGroup("数据录入", listOf(
        ComponentLibItem("autocomplete", "AutoComplete 自动完成", "ExposedDropdownMenuBox + OutlinedTextField，过滤候选项。"),
        ComponentLibItem("checkbox", "Checkbox 多选框", "Material Checkbox；模型多选列表即此组件。"),
        ComponentLibItem("date-picker", "DatePicker 日期选择", "DatePickerDialog / Material DatePicker。"),
        ComponentLibItem("input", "Input 输入框", "NoteMeldField = OutlinedTextField，label/placeholder 统一。"),
        ComponentLibItem("input-number", "InputNumber 数字输入", "KeyboardType.Number 的 OutlinedTextField + 校验。"),
        ComponentLibItem("mentions", "Mentions 提及", "BasicTextField + @ 触发候选弹层。"),
        ComponentLibItem("radio", "Radio 单选框", "Material RadioButton；弹窗单选列表。"),
        ComponentLibItem("rate", "Rate 评分", "Row 内可点 Icon + 状态。"),
        ComponentLibItem("select", "Select 选择器", "Surface 点击 + ModalBottomSheet（固定高度滚动）。"),
    )),
)

/**
 * 组件库页面（不含设计价值观）：
 * 顶栏返回/标题/菜单；点菜单出底部弹窗按 label 分类选择，内容区展示该模块的 Android 实现；
 * 深/浅色由 NoteMeldTheme 自动同步外部设置。
 */
@Composable
private fun ComponentLibraryScreen(s: MobileSurfaceState, d: (MobileSurfaceAction) -> Unit) {
    var moduleSheetOpen by remember { mutableStateOf(false) }
    val currentItem = componentLibraryGroups
        .flatMap { it.items }
        .firstOrNull { it.id == s.componentLibrarySelection }
        ?: componentLibraryGroups.first().items.first()
    val currentGroup = componentLibraryGroups.first { g -> g.items.any { it.id == currentItem.id } }

    Column(Modifier.fillMaxSize().testTag("notemeld-component-library")) {
        // 组件库自带顶栏：返回 / 组件库 / 菜单
        Row(Modifier.fillMaxWidth().height(56.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.SpaceBetween) {
            androidx.compose.material3.IconButton(onClick = { d(MobileSurfaceAction.Navigate(MobileScreen.SETTINGS)) }, modifier = Modifier.size(48.dp).semantics { contentDescription = "notemeld-back-settings" }) {
                Icon(painterResource(com.notemeld.mobile.R.drawable.ic_back), contentDescription = "返回", tint = MaterialTheme.colorScheme.onBackground)
            }
            Text("组件库", style = MaterialTheme.typography.titleLarge, color = MaterialTheme.colorScheme.onBackground)
            androidx.compose.material3.IconButton(onClick = { moduleSheetOpen = true }, modifier = Modifier.size(48.dp).semantics { contentDescription = "notemeld-component-menu" }) {
                Icon(painterResource(com.notemeld.mobile.R.drawable.ic_more), contentDescription = "选择模块", tint = MaterialTheme.colorScheme.onBackground)
            }
        }
        Column(
            Modifier.fillMaxWidth().verticalScroll(rememberScrollState())
                .padding(horizontal = 4.dp).weight(1f),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Column(Modifier.padding(top = 8.dp, start = 4.dp)) {
                Text(currentGroup.label, color = MaterialTheme.colorScheme.primary, style = MaterialTheme.typography.labelSmall)
                Text(currentItem.name, style = MaterialTheme.typography.headlineSmall, color = MaterialTheme.colorScheme.onBackground)
            }
            Surface(
                Modifier.fillMaxWidth(),
                shape = RoundedCornerShape(16.dp),
                color = MaterialTheme.colorScheme.surface,
                border = BorderStroke(1.dp, NoteMeldTokens.border),
            ) {
                Column(Modifier.padding(18.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                    Text("Android 端实现", style = MaterialTheme.typography.titleMedium, color = MaterialTheme.colorScheme.onSurface)
                    Text(currentItem.androidImpl, style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
            }
        }

        if (moduleSheetOpen) {
            NoteMeldBottomSheet(
                title = "选择模块",
                onDismiss = { moduleSheetOpen = false },
                eyebrow = "组件库",
                testTag = "notemeld-component-module-sheet",
            ) {
                Column(
                    Modifier.fillMaxWidth().heightIn(max = 360.dp).verticalScroll(rememberScrollState()),
                    verticalArrangement = Arrangement.spacedBy(8.dp),
                ) {
                    componentLibraryGroups.forEach { group ->
                        Text(group.label, Modifier.padding(start = 4.dp, top = 6.dp), color = MaterialTheme.colorScheme.onSurfaceVariant, style = MaterialTheme.typography.labelSmall)
                        group.items.forEach { item ->
                            Surface(
                                onClick = {
                                    d(MobileSurfaceAction.SelectComponent(item.id))
                                    moduleSheetOpen = false
                                },
                                modifier = Modifier.fillMaxWidth(),
                                shape = RoundedCornerShape(11.dp),
                                color = if (item.id == currentItem.id) MaterialTheme.colorScheme.primaryContainer else MaterialTheme.colorScheme.surfaceVariant,
                                border = BorderStroke(1.dp, NoteMeldTokens.border),
                            ) {
                                Text(item.name, Modifier.fillMaxWidth().padding(horizontal = 14.dp, vertical = 13.dp), style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurface)
                            }
                        }
                    }
                }
            }
        }
    }
}
