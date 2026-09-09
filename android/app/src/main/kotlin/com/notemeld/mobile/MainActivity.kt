package com.notemeld.mobile

import android.os.Bundle
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import kotlinx.coroutines.launch
import kotlinx.coroutines.delay
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.material3.MaterialTheme
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.getValue
import androidx.compose.runtime.setValue
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            var initialState by remember { mutableStateOf(MobileLocalStore.load(applicationContext)) }
            var tasks by remember { mutableStateOf(MobileLocalStore.loadTasks(applicationContext)) }
            val scope = rememberCoroutineScope()
            val androidDeviceId = "android-${android.provider.Settings.Secure.getString(contentResolver, android.provider.Settings.Secure.ANDROID_ID)}"
            LaunchedEffect(Unit) {
                while (true) {
                    val result = withContext(Dispatchers.IO) { runCatching { MobileApi.loadTasks() to MobileApi.loadProjection() } }
                    result.onSuccess { (remote, memories) ->
                        initialState = initialState.copy(connection = ConnectionState.READY, memories = memories)
                        tasks = remote
                        MobileLocalStore.saveTasks(applicationContext, remote)
                        scope.launch(Dispatchers.IO) { MobileApi.recordProjectionCursor(androidDeviceId) }
                    }.onFailure {
                        initialState = initialState.copy(connection = ConnectionState.OFFLINE)
                        tasks = MobileLocalStore.loadTasks(applicationContext)
                    }
                    delay(5000)
                }
            }
            val cloud = remember { CloudApi(this@MainActivity) }
            MaterialTheme { MobileSurface(
                initialState = initialState,
                reduce = { state, action -> reduceAndPersistMobileSurface(applicationContext, state, action) },
                tasks = tasks,
                onSend = { input, onEvent -> scope.launch { withContext(Dispatchers.IO) { runCatching { MobileApi.streamAgent(input, onEvent) }.onFailure { onEvent("Agent 请求失败：${it.message ?: "unknown"}", true) } } } },
                onCloudSend = { url, input, onEvent -> scope.launch { withContext(Dispatchers.IO) { runCatching { cloud.streamAgent(url, input, onEvent) }.onFailure { onEvent("Cloud Agent 请求失败：${it.message ?: "unknown"}", true) } } } },
                onRemoteSend = { url, device, input, onEvent -> scope.launch { withContext(Dispatchers.IO) { runCatching { cloud.streamRemoteAgent(url, input, CloudDevice(device.id, device.displayName, device.platform, device.online, device.publicKey, device.lanEndpoints), androidDeviceId, onEvent) }.onFailure { onEvent("远程 Agent 请求失败：${it.message ?: "unknown"}", true) } } } },
                onAddMemory = { content, callback -> scope.launch { val saved = withContext(Dispatchers.IO) { MobileApi.createMemory(content) }; callback(saved) } },
                onDeleteTask = { id, callback -> scope.launch { val deleted = withContext(Dispatchers.IO) { MobileApi.deleteConversation(id) }; if (deleted) { tasks = tasks.filterNot { it.id == id }; MobileLocalStore.saveTasks(applicationContext, tasks) }; callback(deleted) } },
                onCloudLogin = { url, username, password, result -> scope.launch { val outcome = withContext(Dispatchers.IO) { runCatching { val login = cloud.login(url, username, password); cloud.registerDevice(url, androidDeviceId); val devices = cloud.listDevices(url); "已连接 Cloud：${login.role}" to devices }.getOrElse { "Cloud 连接失败：${it.message ?: "unknown"}" to emptyList() } }; result(outcome.first, outcome.second) } },
            ) }
        }
    }
}
