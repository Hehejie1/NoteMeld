package com.notemeld.mobile

/** Shared page contract for the Android host. Agent execution stays in the SDK/runtime. */
enum class MobileScreen { HOME, SESSION, SETTINGS, MEMORY, COMPONENT_LIBRARY, FONT_SIZE, STORAGE, MODEL_SETTINGS, MODEL_ADD, REMOTE_SETTINGS, PRODUCTS, FILE_PREVIEW }
enum class AgentLocation { LOCAL, CLOUD, REMOTE }
enum class ConnectionState { READY, OFFLINE, SYNCING, ERROR }

data class StorageItem(val id: String, val title: String, val description: String, val sizeMb: Double)
data class MobileTask(val id: String, val title: String, val status: String)
data class MobileMessage(val role: String, val content: String)
data class MobileMemory(val id: String, val content: String)
data class MobileAttachment(val name: String, val contentBase64: String, val size: Int, val type: String)
data class RemoteDevice(val id: String, val displayName: String, val platform: String, val online: Boolean, val publicKey: String? = null, val lanEndpoints: List<String> = emptyList())
data class MobileArtifact(val id: String, val name: String, val format: String, val content: String? = null, val downloadable: Boolean = true)

/** Cloud/配对下发的非敏感模型目录项（只含 id 与名称，永不含 api_key）。 */
data class CloudModelChoice(val id: String, val name: String, val modelId: String, val isDefault: Boolean = false)

data class MobileSurfaceState(
    val screen: MobileScreen = MobileScreen.HOME,
    val settingsReturnScreen: MobileScreen = MobileScreen.HOME,
    val drawerOpen: Boolean = false,
    val sheet: String? = null,
    val sending: Boolean = false,
    val permissionGranted: Boolean = false,
    val permissionMode: String = "none",
    val location: AgentLocation = AgentLocation.LOCAL,
    val connection: ConnectionState = ConnectionState.READY,
    val networkAvailable: Boolean = true,
    /** 当前工作位置下选中的展示名（仅 UI 投影；权威选择分别在 Cloud 目录与本机 prefs）。 */
    val selectedModel: String = "Auto",
    /** Cloud 模型目录（非敏感元数据，不持久化到 MobileLocalStore）。 */
    val cloudModels: List<CloudModelChoice> = emptyList(),
    val selectedCloudModelId: String? = null,
    /** 配对下发的非敏感模型目录（存于 CloudApi 独立 store，不进 MobileLocalStore）。 */
    val pairedModels: List<CloudModelChoice> = emptyList(),
    /** 本机 Provider/Model 两级配置（SQLite，仅 UI 投影，不进 MobileLocalStore）。 */
    val localProviders: List<ProviderRecord> = emptyList(),
    val localModels: List<ModelRecord> = emptyList(),
    /** 本机选中的 [ModelRecord.id]（权威选择在本机 prefs；仅 UI 投影）。 */
    val selectedLocalModelId: String? = null,
    /** 非空时添加模型页面进入编辑回显模式（仅 UI）。 */
    val modelEditProviderId: String? = null,
    /** 组件库当前选中的组件 id（默认 color）。 */
    val componentLibrarySelection: String = "color",
    val theme: String = "system",
    val language: String = "跟随系统",
    val fontSize: Int = 16,
    val followSystemFont: Boolean = false,
    val notificationsEnabled: Boolean = true,
    val memoryDraft: String = "",
    val inputText: String = "",
    val cloudUrl: String = "",
    val cloudUsername: String = "",
    val cloudPassword: String = "",
    val cloudStatus: String = "未连接",
    val cloudSyncRevision: Long = 0L,
    val cloudSyncItemCount: Int = 0,
    val cloudSyncStatus: String = "未同步",
    val remoteDevices: List<RemoteDevice> = emptyList(),
    val selectedRemoteDeviceId: String? = null,
    val remoteTransport: String? = null,
    val remoteCursor: Int? = null,
    val showActionMenu: Boolean = false,
    val toast: String? = null,
    val selectedWorkTab: AgentLocation = AgentLocation.LOCAL,
    val attachments: List<String> = emptyList(),
    val tasks: List<MobileTask> = emptyList(),
    val activeTaskId: String? = null,
    val activeTaskTitle: String? = null,
    val messages: List<MobileMessage> = emptyList(),
    val terminalEvents: List<String> = emptyList(),
    val memories: List<String> = emptyList(),
    val memoryIds: List<String> = emptyList(),
    val storage: List<StorageItem> = emptyList(),
    val artifacts: List<MobileArtifact> = emptyList(),
    val selectedArtifactId: String? = null,
)

sealed interface MobileSurfaceAction {
    data class Navigate(val screen: MobileScreen) : MobileSurfaceAction
    data object OpenSettings : MobileSurfaceAction
    /** 组件库选择某个组件模块。 */
    data class SelectComponent(val id: String) : MobileSurfaceAction
    data object CloseSettings : MobileSurfaceAction
    data object ToggleDrawer : MobileSurfaceAction
    data class OpenSheet(val name: String) : MobileSurfaceAction
    data object CloseOverlay : MobileSurfaceAction
    data class SetSending(val value: Boolean) : MobileSurfaceAction
    data class SetPermissionMode(val value: String) : MobileSurfaceAction
    data class SetLocation(val value: AgentLocation) : MobileSurfaceAction
    data class SetConnection(val value: ConnectionState) : MobileSurfaceAction
    data class SetNetworkAvailable(val value: Boolean) : MobileSurfaceAction
    data class SelectModel(val value: String) : MobileSurfaceAction
    data class SetCloudModels(val value: List<CloudModelChoice>) : MobileSurfaceAction
    data class SelectCloudModel(val id: String?) : MobileSurfaceAction
    data class SetPairedModels(val value: List<CloudModelChoice>) : MobileSurfaceAction
    data class SetLocalProviders(val value: List<ProviderRecord>) : MobileSurfaceAction
    data class SetLocalModels(val value: List<ModelRecord>) : MobileSurfaceAction
    /** 选择本机模型（参数为 [ModelRecord.id]）。 */
    data class SelectLocalModel(val id: String?) : MobileSurfaceAction
    /** 打开添加/编辑模型页面；providerId 非空时回显既有配置。 */
    data class OpenModelAddPage(val providerId: String? = null) : MobileSurfaceAction
    /** 返回模型设置页（添加模型页面的返回）。 */
    data object CloseModelAddPage : MobileSurfaceAction
    data class SetTheme(val value: String) : MobileSurfaceAction
    data class SetLanguage(val value: String) : MobileSurfaceAction
    data class SetFontSize(val value: Int) : MobileSurfaceAction
    data class SetFollowSystemFont(val value: Boolean) : MobileSurfaceAction
    data object ResetFontSettings : MobileSurfaceAction
    data class SetNotifications(val value: Boolean) : MobileSurfaceAction
    data class SetMemoryDraft(val value: String) : MobileSurfaceAction
    data class SetInputText(val value: String) : MobileSurfaceAction
    data object ToggleActionMenu : MobileSurfaceAction
    data class AddAttachment(val name: String) : MobileSurfaceAction
    data object ShowProducts : MobileSurfaceAction
    data object DeleteConversation : MobileSurfaceAction
    data class ShowToast(val value: String) : MobileSurfaceAction
    data object ClearToast : MobileSurfaceAction
    data class SetWorkTab(val value: AgentLocation) : MobileSurfaceAction
    data object AddMemory : MobileSurfaceAction
    data class SetMemories(val value: List<String>) : MobileSurfaceAction
    data class DeleteMemory(val index: Int) : MobileSurfaceAction
    data class SetTasks(val value: List<MobileTask>) : MobileSurfaceAction
    data class OpenTask(val id: String?, val title: String) : MobileSurfaceAction
    data object OpenNewTask : MobileSurfaceAction
    data class AddMessage(val value: MobileMessage) : MobileSurfaceAction
    data class AppendAssistantContent(val value: String) : MobileSurfaceAction
    data object ResetAgentTerminals : MobileSurfaceAction
    data class RecordAgentTerminal(val value: String) : MobileSurfaceAction
    data class SetCloudUrl(val value: String) : MobileSurfaceAction
    data class SetCloudUsername(val value: String) : MobileSurfaceAction
    data class SetCloudPassword(val value: String) : MobileSurfaceAction
    data class SetCloudStatus(val value: String) : MobileSurfaceAction
    data class SetCloudSync(val revision: Long, val itemCount: Int, val status: String) : MobileSurfaceAction
    data class SetRemoteDevices(val value: List<RemoteDevice>) : MobileSurfaceAction
    data class SelectRemoteDevice(val value: String) : MobileSurfaceAction
    data class SetRemoteTransport(val value: String?, val cursor: Int? = null) : MobileSurfaceAction
    data class ClearStorage(val id: String?) : MobileSurfaceAction
    data class OpenArtifact(val id: String) : MobileSurfaceAction
    data class SetArtifacts(val value: List<MobileArtifact>) : MobileSurfaceAction
}

fun reduceMobileSurface(state: MobileSurfaceState, action: MobileSurfaceAction): MobileSurfaceState = when (action) {
    is MobileSurfaceAction.Navigate -> state.copy(screen = action.screen, drawerOpen = false, sheet = null)
    is MobileSurfaceAction.SelectComponent -> state.copy(componentLibrarySelection = action.id, sheet = null)
    MobileSurfaceAction.OpenSettings -> state.copy(settingsReturnScreen = state.screen, screen = MobileScreen.SETTINGS, drawerOpen = false, sheet = null)
    MobileSurfaceAction.CloseSettings -> state.copy(screen = state.settingsReturnScreen, drawerOpen = false, sheet = null)
    MobileSurfaceAction.ToggleDrawer -> state.copy(drawerOpen = !state.drawerOpen, sheet = null)
    is MobileSurfaceAction.OpenSheet -> state.copy(sheet = action.name, drawerOpen = false)
    MobileSurfaceAction.CloseOverlay -> state.copy(drawerOpen = false, sheet = null)
    is MobileSurfaceAction.SetSending -> state.copy(sending = action.value)
    is MobileSurfaceAction.SetPermissionMode -> state.copy(
        permissionGranted = action.value == "default" || action.value == "full",
        permissionMode = action.value,
        sheet = null,
    )
    is MobileSurfaceAction.SetLocation -> state.copy(location = action.value)
    is MobileSurfaceAction.SetConnection -> state.copy(connection = action.value)
    is MobileSurfaceAction.SetNetworkAvailable -> state.copy(networkAvailable = action.value)
    is MobileSurfaceAction.SelectModel -> state.copy(selectedModel = action.value, sheet = null)
    is MobileSurfaceAction.SetCloudModels -> state.copy(cloudModels = action.value)
    is MobileSurfaceAction.SelectCloudModel -> state.copy(selectedCloudModelId = action.id, sheet = null)
    is MobileSurfaceAction.SetPairedModels -> state.copy(pairedModels = action.value)
    is MobileSurfaceAction.SetLocalProviders -> state.copy(localProviders = action.value)
    is MobileSurfaceAction.SetLocalModels -> state.copy(localModels = action.value)
    is MobileSurfaceAction.SelectLocalModel -> state.copy(selectedLocalModelId = action.id, sheet = null)
    is MobileSurfaceAction.OpenModelAddPage ->
        state.copy(modelEditProviderId = action.providerId, screen = MobileScreen.MODEL_ADD, drawerOpen = false, sheet = null)
    MobileSurfaceAction.CloseModelAddPage ->
        state.copy(screen = MobileScreen.MODEL_SETTINGS, modelEditProviderId = null, sheet = null)
    is MobileSurfaceAction.SetTheme -> state.copy(theme = action.value, sheet = null)
    is MobileSurfaceAction.SetLanguage -> state.copy(language = action.value, sheet = null)
    is MobileSurfaceAction.SetFontSize -> state.copy(fontSize = action.value)
    is MobileSurfaceAction.SetFollowSystemFont -> state.copy(followSystemFont = action.value)
    MobileSurfaceAction.ResetFontSettings -> state.copy(fontSize = 16, followSystemFont = false)
    is MobileSurfaceAction.SetNotifications -> state.copy(notificationsEnabled = action.value)
    is MobileSurfaceAction.SetMemoryDraft -> state.copy(memoryDraft = action.value)
    is MobileSurfaceAction.SetInputText -> if (canInteractWithAgent(state)) state.copy(inputText = action.value) else state
    MobileSurfaceAction.ToggleActionMenu -> state.copy(showActionMenu = !state.showActionMenu)
    is MobileSurfaceAction.AddAttachment -> state.copy(attachments = state.attachments + action.name)
    MobileSurfaceAction.ShowProducts -> state.copy(showActionMenu = false, screen = MobileScreen.PRODUCTS, sheet = null)
    MobileSurfaceAction.DeleteConversation -> state.copy(showActionMenu = false, screen = MobileScreen.HOME)
    is MobileSurfaceAction.ShowToast -> state.copy(toast = action.value)
    MobileSurfaceAction.ClearToast -> state.copy(toast = null)
    is MobileSurfaceAction.SetWorkTab -> state.copy(selectedWorkTab = action.value)
    MobileSurfaceAction.AddMemory -> if (state.connection == ConnectionState.OFFLINE || state.memoryDraft.isBlank()) state else state.copy(
        memories = state.memories + state.memoryDraft.trim(), memoryDraft = ""
    )
    is MobileSurfaceAction.SetMemories -> state.copy(memories = action.value)
    is MobileSurfaceAction.DeleteMemory -> if (action.index !in state.memories.indices) state else state.copy(
        memories = state.memories.filterIndexed { index, _ -> index != action.index },
        memoryIds = state.memoryIds.filterIndexed { index, _ -> index != action.index },
    )
    is MobileSurfaceAction.SetTasks -> state.copy(tasks = action.value)
    is MobileSurfaceAction.OpenTask -> state.copy(activeTaskId = action.id, activeTaskTitle = action.title, screen = MobileScreen.SESSION, drawerOpen = false)
    MobileSurfaceAction.OpenNewTask -> state.copy(activeTaskId = null, activeTaskTitle = null, messages = emptyList(), inputText = "", screen = MobileScreen.HOME, drawerOpen = false, sheet = null)
    is MobileSurfaceAction.AddMessage -> state.copy(messages = state.messages + action.value)
    is MobileSurfaceAction.AppendAssistantContent -> if (action.value.isBlank()) state else {
        val last = state.messages.lastOrNull()
        if (last?.role == "assistant") state.copy(messages = state.messages.dropLast(1) + last.copy(content = last.content + action.value))
        else state.copy(messages = state.messages + MobileMessage("assistant", action.value))
    }
    MobileSurfaceAction.ResetAgentTerminals -> state.copy(terminalEvents = emptyList())
    is MobileSurfaceAction.RecordAgentTerminal -> state.copy(terminalEvents = state.terminalEvents + action.value)
    is MobileSurfaceAction.SetCloudUrl -> state.copy(cloudUrl = action.value)
    is MobileSurfaceAction.SetCloudUsername -> state.copy(cloudUsername = action.value)
    is MobileSurfaceAction.SetCloudPassword -> state.copy(cloudPassword = action.value)
    is MobileSurfaceAction.SetCloudStatus -> state.copy(cloudStatus = action.value)
    is MobileSurfaceAction.SetCloudSync -> state.copy(cloudSyncRevision = action.revision, cloudSyncItemCount = action.itemCount, cloudSyncStatus = action.status)
    is MobileSurfaceAction.SetRemoteDevices -> state.copy(remoteDevices = action.value, selectedRemoteDeviceId = action.value.firstOrNull { it.online }?.id ?: action.value.firstOrNull()?.id)
    is MobileSurfaceAction.SelectRemoteDevice -> state.copy(selectedRemoteDeviceId = action.value)
    is MobileSurfaceAction.SetRemoteTransport -> state.copy(remoteTransport = action.value, remoteCursor = action.cursor)
    is MobileSurfaceAction.ClearStorage -> state
    is MobileSurfaceAction.OpenArtifact -> state.copy(selectedArtifactId = action.id, screen = MobileScreen.FILE_PREVIEW, drawerOpen = false, sheet = null)
    is MobileSurfaceAction.SetArtifacts -> state.copy(artifacts = action.value)
}

fun canInteractWithAgent(state: MobileSurfaceState): Boolean = when (state.location) {
    AgentLocation.LOCAL -> state.connection != ConnectionState.OFFLINE
    AgentLocation.CLOUD, AgentLocation.REMOTE -> state.networkAvailable
}

fun reduceAndPersistMobileSurface(context: android.content.Context, state: MobileSurfaceState, action: MobileSurfaceAction): MobileSurfaceState {
    val next = reduceMobileSurface(state, action)
    val persisted = if (action is MobileSurfaceAction.ClearStorage) {
        val storage = MobileLocalStore.clear(context, action.id)
        next.copy(
            storage = storage,
        )
    } else next
    MobileLocalStore.save(context, persisted)
    return persisted
}
