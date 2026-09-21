package com.notemeld.mobile

import android.content.Context
import android.net.ConnectivityManager
import android.net.Network
import android.os.Bundle
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import kotlinx.coroutines.launch
import kotlinx.coroutines.delay
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.getValue
import androidx.compose.runtime.setValue
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import org.json.JSONObject

class MainActivity : ComponentActivity() {
    override fun onNewIntent(intent: android.content.Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        deepLinkSink[0](intent.dataString)
    }

    private val deepLinkSink = arrayOf<(String?) -> Unit>({})

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        MobileLocalStore.recoverInterruptedLocalTurn(applicationContext)
        setContent {
            var initialState by remember { mutableStateOf(MobileLocalStore.load(applicationContext, restoreNavigation = savedInstanceState != null)) }
            var agentLocation by remember { mutableStateOf(initialState.location) }
            var tasks by remember { mutableStateOf(MobileLocalStore.loadTasks(applicationContext)) }
            var activeLocalToken by remember { mutableStateOf<Long?>(null) }
            var pendingDeepLink by remember { mutableStateOf<String?>(intent?.dataString) }
            val scope = rememberCoroutineScope()
            val localSink = remember { arrayOf<(String, String?) -> Unit>({ _, _ -> }) }
            val connectivity = remember { getSystemService(Context.CONNECTIVITY_SERVICE) as ConnectivityManager }
            val androidDeviceId = "android-${android.provider.Settings.Secure.getString(contentResolver, android.provider.Settings.Secure.ANDROID_ID)}"
            val cloud = remember { CloudApi(this@MainActivity) }
            LaunchedEffect(Unit) {
                val cached = cloud.cachedSyncState()
                initialState = initialState.copy(cloudSyncRevision = cached.revision, cloudSyncItemCount = cached.itemCount, cloudSyncStatus = if (cached.revision > 0L) "已缓存" else "未同步")
            }
            val embeddedLocalAgent = remember { EmbeddedLocalAgent(applicationContext) { event ->
                MobileLocalStore.recordLocalEvent(applicationContext, event)
                val payload = event.optJSONObject("payload")
                val content = if (event.optString("type") == "message.delta") payload?.optString("delta", "") ?: "" else ""
                val terminal = event.optString("type").takeIf { it in setOf("turn.succeeded", "turn.failed", "turn.cancelled", "turn.interrupted") }
                if (content.isNotBlank() || terminal != null) localSink[0](content, terminal)
                if (terminal != null) MobileLocalStore.completeLocalTurn(applicationContext)
            } }
            DisposableEffect(Unit) { onDispose { embeddedLocalAgent.close() } }
            DisposableEffect(connectivity) {
                fun publishNetworkState() {
                    scope.launch { initialState = initialState.copy(networkAvailable = connectivity.activeNetwork != null) }
                }
                val callback = object : ConnectivityManager.NetworkCallback() {
                    override fun onAvailable(network: Network) = publishNetworkState()
                    override fun onLost(network: Network) = publishNetworkState()
                }
                publishNetworkState()
                val registered = runCatching { connectivity.registerDefaultNetworkCallback(callback) }.isSuccess
                if (!registered) initialState = initialState.copy(networkAvailable = false)
                onDispose {
                    if (registered) runCatching { connectivity.unregisterNetworkCallback(callback) }
                }
            }
            LaunchedEffect(Unit) {
                if (cloud.hasAccountToken()) {
                    withContext(Dispatchers.IO) { runCatching { cloud.verifyCapabilities(initialState.cloudUrl); val sync = cloud.syncConfig(initialState.cloudUrl); cloud.registerDevice(initialState.cloudUrl, androidDeviceId); Triple(sync, cloud.listDevices(initialState.cloudUrl, androidDeviceId), cloud.listModels(initialState.cloudUrl)) } }
                        .onSuccess { (sync, devices, models) ->
                            val cloudChoices = models.map { CloudModelChoice(it.id, it.name, it.model, it.isDefault) }
                            initialState = initialState.copy(cloudStatus = "已恢复 Cloud 登录", cloudSyncRevision = sync.revision, cloudSyncItemCount = sync.itemCount, cloudSyncStatus = "已同步", cloudModels = cloudChoices, selectedCloudModelId = cloudChoices.firstOrNull { it.isDefault }?.id ?: initialState.selectedCloudModelId, remoteDevices = devices.map { RemoteDevice(it.id, it.displayName, it.platform, it.online, it.publicKey, it.lanEndpoints) }, selectedRemoteDeviceId = devices.firstOrNull { it.online }?.id ?: devices.firstOrNull()?.id)
                        }
                        .onFailure { initialState = initialState.copy(cloudStatus = "Cloud 会话恢复失败", cloudSyncStatus = "同步失败") }
                }
            }
            LaunchedEffect(agentLocation) {
                while (true) {
                    if (agentLocation == AgentLocation.LOCAL) {
                        initialState = initialState.copy(connection = ConnectionState.READY)
                        tasks = MobileLocalStore.loadTasks(applicationContext)
                        delay(5000)
                        continue
                    }
                    val result = withContext(Dispatchers.IO) { runCatching { MobileApi.loadTasks() to MobileApi.loadMemoryProjection() } }
                    result.onSuccess { (remote, memoryRecords) ->
                        initialState = initialState.copy(connection = ConnectionState.READY, memories = memoryRecords.map { it.content }, memoryIds = memoryRecords.map { it.id })
                        tasks = remote
                        MobileLocalStore.saveTasks(applicationContext, remote)
                        scope.launch(Dispatchers.IO) { MobileApi.recordProjectionCursor(androidDeviceId) }
                    }.onFailure {
                        // LOCAL execution is embedded in this APK; backend projection
                        // availability must not turn the local Agent into read-only mode.
                        initialState = initialState.copy(connection = ConnectionState.READY)
                        tasks = MobileLocalStore.loadTasks(applicationContext)
                    }
                    delay(5000)
                }
            }
            LaunchedEffect(Unit) {
                withContext(Dispatchers.IO) {
                    val dao = ModelDao(applicationContext)
                    val providers = dao.listProviders()
                    val models = dao.listAllModels()
                    val selectedId = embeddedLocalAgent.selectedModelRecord()?.id
                    dao.close()
                    initialState = initialState.copy(
                        localProviders = providers,
                        localModels = models,
                        selectedLocalModelId = selectedId,
                    )
                }
            }
            LaunchedEffect(pendingDeepLink) {
                val link = pendingDeepLink ?: return@LaunchedEffect
                pendingDeepLink = null
                when (classifyScanResult(link)) {
                    is ScanTarget.PairCode -> initialState = initialState.copy(screen = MobileScreen.MODEL_SETTINGS, sheet = "model-scan")
                    is ScanTarget.ModelShare -> initialState = initialState.copy(screen = MobileScreen.MODEL_ADD)
                    null -> initialState = initialState.copy(toast = mobileText(initialState.language, "unsupportedQr"))
                }
            }
            deepLinkSink[0] = { link -> pendingDeepLink = link }
            MobileSurface(
                initialState = initialState,
                reduce = { state, action -> reduceAndPersistMobileSurface(applicationContext, state, action) },
                tasks = tasks,
                onSend = { input, onEvent ->
                    localSink[0] = { content, terminal -> scope.launch { onEvent(content, terminal) } }
                    scope.launch(Dispatchers.IO) { runCatching { val token = embeddedLocalAgent.submit(input); activeLocalToken = token; embeddedLocalAgent.await(token) }.onFailure { error -> MobileLocalStore.completeLocalTurn(applicationContext); scope.launch { onEvent("Agent 请求失败：${error.message ?: "unknown"}", "turn.failed") } }.also { activeLocalToken = null } }
                },
                onCancelLocal = { activeLocalToken?.let(embeddedLocalAgent::cancel) },
                onSteerLocal = { value -> activeLocalToken?.let { embeddedLocalAgent.steer(it, JSONObject().put("text", value)) } },
                onCloudSend = { url, input, modelId, onEvent -> scope.launch(Dispatchers.IO) { runCatching { cloud.streamAgent(url, input, modelId = modelId) { content, terminalType -> scope.launch { onEvent(content, terminalType) } } }.onFailure { error -> scope.launch { onEvent("Cloud Agent 请求失败：${error.message ?: "unknown"}", "turn.failed") } } } },
                onPairingCodeScanned = { code, callback ->
                    scope.launch(Dispatchers.IO) {
                        val result = runCatching {
                            require(initialState.cloudUrl.isNotBlank()) { "请先在设置中配置并登录 Cloud" }
                            val models = cloud.confirmPairing(initialState.cloudUrl, code, androidDeviceId, android.os.Build.MODEL)
                            models.map { CloudModelChoice(it.id, it.name.ifBlank { it.model }, it.model, it.isDefault) }
                        }
                        result.onSuccess { choices -> initialState = initialState.copy(cloudStatus = "设备已配对", pairedModels = choices) }
                        scope.launch { callback(result) }
                    }
                },
                onRemoteSend = { url, device, input, onTransport, onEvent -> scope.launch(Dispatchers.IO) { runCatching { cloud.streamRemoteAgent(url, input, CloudDevice(device.id, device.displayName, device.platform, device.online, device.publicKey, device.lanEndpoints), androidDeviceId, onTransport = { transport, cursor -> scope.launch { onTransport(transport, cursor) } }) { content, terminalType -> scope.launch { onEvent(content, terminalType) } } }.onFailure { error -> scope.launch { onEvent("远程 Agent 请求失败：${error.message ?: "unknown"}", "turn.failed") } } } },
                onLocationChange = { agentLocation = it },
                onCloudLogout = {
                    scope.launch(Dispatchers.IO) {
                        val revoked = cloud.logout(initialState.cloudUrl)
                        scope.launch {
                            initialState = initialState.copy(
                                cloudStatus = if (revoked) "已退出 Cloud" else "已退出 Cloud（服务端撤销待重试）",
                                cloudSyncStatus = "未同步",
                                remoteDevices = emptyList(),
                                selectedRemoteDeviceId = null,
                            )
                        }
                    }
                },
                onCloudConfigChange = { kind, key, value ->
                    if (cloud.hasAccountToken() && initialState.networkAvailable) scope.launch(Dispatchers.IO) {
                        runCatching { cloud.writeConfig(initialState.cloudUrl, kind, key, value) }
                            .onSuccess { sync -> scope.launch { initialState = initialState.copy(cloudSyncRevision = sync.revision, cloudSyncItemCount = sync.itemCount, cloudSyncStatus = "已同步") } }
                            .onFailure { error ->
                                if (error is CloudHttpException && error.statusCode == 409) {
                                    // Do not overwrite a newer Cloud revision. Refresh the
                                    // durable cursor and leave the user's edit visible so
                                    // they can explicitly retry against the new base revision.
                                    runCatching { cloud.syncConfig(initialState.cloudUrl) }
                                        .onSuccess { sync -> scope.launch { initialState = initialState.copy(cloudSyncRevision = sync.revision, cloudSyncItemCount = sync.itemCount, cloudSyncStatus = "版本冲突，已刷新，请重试") } }
                                        .onFailure { scope.launch { initialState = initialState.copy(cloudSyncStatus = "版本冲突，刷新失败，请重试") } }
                                } else {
                                    scope.launch { initialState = initialState.copy(cloudSyncStatus = "同步失败，请刷新后重试") }
                                }
                            }
                    }
                },
                onLocalModelSelect = { modelRecordId -> embeddedLocalAgent.selectModel(modelRecordId) },
                onAddMemory = { content, callback -> scope.launch { val saved = if (agentLocation == AgentLocation.LOCAL) { MobileLocalStore.addMemory(applicationContext, content); true } else withContext(Dispatchers.IO) { MobileApi.createMemory(content) }; callback(saved) } },
                onDeleteMemory = { index, id, callback -> scope.launch { val deleted = if (agentLocation == AgentLocation.LOCAL) MobileLocalStore.deleteMemory(applicationContext, index) else id?.let { withContext(Dispatchers.IO) { MobileApi.deleteMemory(it) } } ?: false; callback(deleted) } },
                onDeleteTask = { id, callback -> scope.launch { val deleted = if (agentLocation == AgentLocation.LOCAL) MobileLocalStore.deleteTask(applicationContext, id) else withContext(Dispatchers.IO) { MobileApi.deleteConversation(id) }; if (deleted) { tasks = tasks.filterNot { it.id == id }; MobileLocalStore.saveTasks(applicationContext, tasks) }; callback(deleted) } },
                onCloudLogin = { url, username, password, result -> scope.launch { val outcome = withContext(Dispatchers.IO) { runCatching { val login = cloud.login(url, username, password); val sync = cloud.syncConfig(url); cloud.registerDevice(url, androidDeviceId); val devices = cloud.listDevices(url, androidDeviceId); val models = cloud.listModels(url); Triple("已连接 Cloud：${login.role}", devices, sync to models) }.getOrElse { Triple("Cloud 连接失败：${it.message ?: "unknown"}", emptyList(), null) } }; outcome.third?.let { (sync, models) -> val cloudChoices = models.map { CloudModelChoice(it.id, it.name, it.model, it.isDefault) }; initialState = initialState.copy(cloudSyncRevision = sync.revision, cloudSyncItemCount = sync.itemCount, cloudSyncStatus = "已同步", cloudModels = cloudChoices, selectedCloudModelId = cloudChoices.firstOrNull { it.isDefault }?.id ?: initialState.selectedCloudModelId) }; result(outcome.first, outcome.second) } },
            )
        }
    }
}
