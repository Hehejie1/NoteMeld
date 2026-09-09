package com.notemeld.mobile

/** Shared page contract for the Android host. Agent execution stays in the SDK/runtime. */
enum class MobileScreen { HOME, SESSION, SETTINGS, MEMORY, FONT_SIZE, STORAGE }
enum class AgentLocation { LOCAL, CLOUD, REMOTE }
enum class ConnectionState { READY, OFFLINE, SYNCING, ERROR }

data class StorageItem(val id: String, val title: String, val description: String, val sizeMb: Double)
data class MobileTask(val id: String, val title: String, val status: String)
data class MobileMessage(val role: String, val content: String)
data class MobileAttachment(val name: String, val contentBase64: String, val size: Int, val type: String)
data class RemoteDevice(val id: String, val displayName: String, val platform: String, val online: Boolean, val publicKey: String? = null, val lanEndpoints: List<String> = emptyList())

data class MobileSurfaceState(
    val screen: MobileScreen = MobileScreen.HOME,
    val drawerOpen: Boolean = false,
    val sheet: String? = null,
    val sending: Boolean = false,
    val permissionGranted: Boolean = false,
    val location: AgentLocation = AgentLocation.LOCAL,
    val connection: ConnectionState = ConnectionState.READY,
    val selectedModel: String = "Auto",
    val theme: String = "system",
    val language: String = "跟随系统",
    val fontSize: Int = 16,
    val followSystemFont: Boolean = false,
    val notificationsEnabled: Boolean = true,
    val memoryDraft: String = "",
    val inputText: String = "",
    val cloudUrl: String = "http://10.0.2.2:8583",
    val cloudUsername: String = "",
    val cloudPassword: String = "",
    val cloudStatus: String = "未连接",
    val remoteDevices: List<RemoteDevice> = emptyList(),
    val selectedRemoteDeviceId: String? = null,
    val showActionMenu: Boolean = false,
    val toast: String? = null,
    val selectedWorkTab: AgentLocation = AgentLocation.LOCAL,
    val attachments: List<String> = emptyList(),
    val tasks: List<MobileTask> = emptyList(),
    val activeTaskId: String? = null,
    val activeTaskTitle: String? = null,
    val messages: List<MobileMessage> = emptyList(),
    val memories: List<String> = emptyList(),
    val storage: List<StorageItem> = emptyList(),
)

sealed interface MobileSurfaceAction {
    data class Navigate(val screen: MobileScreen) : MobileSurfaceAction
    data object ToggleDrawer : MobileSurfaceAction
    data class OpenSheet(val name: String) : MobileSurfaceAction
    data object CloseOverlay : MobileSurfaceAction
    data class SetSending(val value: Boolean) : MobileSurfaceAction
    data class SetPermission(val value: Boolean) : MobileSurfaceAction
    data class SetLocation(val value: AgentLocation) : MobileSurfaceAction
    data class SetConnection(val value: ConnectionState) : MobileSurfaceAction
    data class SelectModel(val value: String) : MobileSurfaceAction
    data class SetTheme(val value: String) : MobileSurfaceAction
    data class SetLanguage(val value: String) : MobileSurfaceAction
    data class SetFontSize(val value: Int) : MobileSurfaceAction
    data class SetFollowSystemFont(val value: Boolean) : MobileSurfaceAction
    data class SetNotifications(val value: Boolean) : MobileSurfaceAction
    data class SetMemoryDraft(val value: String) : MobileSurfaceAction
    data class SetInputText(val value: String) : MobileSurfaceAction
    data object ToggleActionMenu : MobileSurfaceAction
    data class AddAttachment(val name: String) : MobileSurfaceAction
    data object ShowProducts : MobileSurfaceAction
    data object DeleteConversation : MobileSurfaceAction
    data class ShowToast(val value: String) : MobileSurfaceAction
    data class SetWorkTab(val value: AgentLocation) : MobileSurfaceAction
    data object AddMemory : MobileSurfaceAction
    data class SetMemories(val value: List<String>) : MobileSurfaceAction
    data class SetTasks(val value: List<MobileTask>) : MobileSurfaceAction
    data class OpenTask(val id: String?, val title: String) : MobileSurfaceAction
    data class AddMessage(val value: MobileMessage) : MobileSurfaceAction
    data class SetCloudUrl(val value: String) : MobileSurfaceAction
    data class SetCloudUsername(val value: String) : MobileSurfaceAction
    data class SetCloudPassword(val value: String) : MobileSurfaceAction
    data class SetCloudStatus(val value: String) : MobileSurfaceAction
    data class SetRemoteDevices(val value: List<RemoteDevice>) : MobileSurfaceAction
    data class SelectRemoteDevice(val value: String) : MobileSurfaceAction
    data class ClearStorage(val id: String?) : MobileSurfaceAction
}

fun reduceMobileSurface(state: MobileSurfaceState, action: MobileSurfaceAction): MobileSurfaceState = when (action) {
    is MobileSurfaceAction.Navigate -> state.copy(screen = action.screen, drawerOpen = false, sheet = null)
    MobileSurfaceAction.ToggleDrawer -> state.copy(drawerOpen = !state.drawerOpen, sheet = null)
    is MobileSurfaceAction.OpenSheet -> state.copy(sheet = action.name, drawerOpen = false)
    MobileSurfaceAction.CloseOverlay -> state.copy(drawerOpen = false, sheet = null)
    is MobileSurfaceAction.SetSending -> state.copy(sending = action.value)
    is MobileSurfaceAction.SetPermission -> state.copy(permissionGranted = action.value)
    is MobileSurfaceAction.SetLocation -> state.copy(location = action.value)
    is MobileSurfaceAction.SetConnection -> state.copy(connection = action.value)
    is MobileSurfaceAction.SelectModel -> state.copy(selectedModel = action.value, sheet = null)
    is MobileSurfaceAction.SetTheme -> state.copy(theme = action.value, sheet = null)
    is MobileSurfaceAction.SetLanguage -> state.copy(language = action.value, sheet = null)
    is MobileSurfaceAction.SetFontSize -> state.copy(fontSize = action.value)
    is MobileSurfaceAction.SetFollowSystemFont -> state.copy(followSystemFont = action.value)
    is MobileSurfaceAction.SetNotifications -> state.copy(notificationsEnabled = action.value)
    is MobileSurfaceAction.SetMemoryDraft -> state.copy(memoryDraft = action.value)
    is MobileSurfaceAction.SetInputText -> state.copy(inputText = action.value)
    MobileSurfaceAction.ToggleActionMenu -> state.copy(showActionMenu = !state.showActionMenu)
    is MobileSurfaceAction.AddAttachment -> state.copy(attachments = state.attachments + action.name)
    MobileSurfaceAction.ShowProducts -> state.copy(showActionMenu = false, sheet = "products")
    MobileSurfaceAction.DeleteConversation -> state.copy(showActionMenu = false, screen = MobileScreen.HOME)
    is MobileSurfaceAction.ShowToast -> state.copy(toast = action.value)
    is MobileSurfaceAction.SetWorkTab -> state.copy(selectedWorkTab = action.value)
    MobileSurfaceAction.AddMemory -> if (state.memoryDraft.isBlank()) state else state.copy(
        memories = state.memories + state.memoryDraft.trim(), memoryDraft = ""
    )
    is MobileSurfaceAction.SetMemories -> state.copy(memories = action.value)
    is MobileSurfaceAction.SetTasks -> state.copy(tasks = action.value)
    is MobileSurfaceAction.OpenTask -> state.copy(activeTaskId = action.id, activeTaskTitle = action.title, screen = MobileScreen.SESSION, drawerOpen = false)
    is MobileSurfaceAction.AddMessage -> state.copy(messages = state.messages + action.value)
    is MobileSurfaceAction.SetCloudUrl -> state.copy(cloudUrl = action.value)
    is MobileSurfaceAction.SetCloudUsername -> state.copy(cloudUsername = action.value)
    is MobileSurfaceAction.SetCloudPassword -> state.copy(cloudPassword = action.value)
    is MobileSurfaceAction.SetCloudStatus -> state.copy(cloudStatus = action.value)
    is MobileSurfaceAction.SetRemoteDevices -> state.copy(remoteDevices = action.value, selectedRemoteDeviceId = action.value.firstOrNull { it.online }?.id ?: action.value.firstOrNull()?.id)
    is MobileSurfaceAction.SelectRemoteDevice -> state.copy(selectedRemoteDeviceId = action.value)
    is MobileSurfaceAction.ClearStorage -> state
}

fun reduceAndPersistMobileSurface(context: android.content.Context, state: MobileSurfaceState, action: MobileSurfaceAction): MobileSurfaceState {
    val next = reduceMobileSurface(state, action)
    val persisted = if (action is MobileSurfaceAction.ClearStorage) {
        next.copy(storage = MobileLocalStore.clear(context, action.id))
    } else next
    MobileLocalStore.save(context, persisted)
    return persisted
}
