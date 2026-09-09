package com.notemeld.mobile

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.FilterChip
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.material3.Slider
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.platform.LocalContext
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts

@Composable
fun MobileSurface(initialState: MobileSurfaceState = MobileSurfaceState(), tasks: List<MobileTask> = emptyList(), reduce: (MobileSurfaceState, MobileSurfaceAction) -> MobileSurfaceState = { state, action -> reduceMobileSurface(state, action) }, onSend: (String, (String, Boolean) -> Unit) -> Unit = { _, _ -> }, onCloudSend: (String, String, (String, Boolean) -> Unit) -> Unit = { _, _, _ -> }, onRemoteSend: (String, RemoteDevice, String, (String, Boolean) -> Unit) -> Unit = { _, _, _, _ -> }, onCloudLogin: (String, String, String, (String, List<CloudDevice>) -> Unit) -> Unit = { _, _, _, _ -> }, onAddMemory: (String, (Boolean) -> Unit) -> Unit = { _, callback -> callback(false) }, onDeleteTask: (String, (Boolean) -> Unit) -> Unit = { _, callback -> callback(false) }) {
    var state by remember(initialState) { mutableStateOf(initialState) }
    var selectedAttachments by remember { mutableStateOf(emptyList<MobileAttachment>()) }
    val contentResolver = LocalContext.current.contentResolver
    val localContext = LocalContext.current
    val dispatch: (MobileSurfaceAction) -> Unit = { state = reduce(state, it) }
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
    Box(Modifier.fillMaxSize().background(Color(0xfff7f8fb))) {
        Column(Modifier.fillMaxSize().padding(horizontal = 20.dp, vertical = 12.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Header(state, dispatch)
            if (state.connection == ConnectionState.OFFLINE) Text("离线模式：仅可查看已同步内容", color = MaterialTheme.colorScheme.error)
            when (state.screen) {
                MobileScreen.HOME -> HomeScreen(state.copy(tasks = tasks), dispatch)
                MobileScreen.SESSION -> SessionScreen(state, dispatch, { attachmentPicker.launch(arrayOf("*/*")) }, onSend, onCloudSend, onRemoteSend, onDeleteTask)
                MobileScreen.SETTINGS -> SettingsScreenWithTheme(state, dispatch, onCloudLogin)
                MobileScreen.MEMORY -> MemoryScreen(state, dispatch, onAddMemory)
                MobileScreen.FONT_SIZE -> FontScreen(state, dispatch)
                MobileScreen.STORAGE -> StorageScreen(state, dispatch)
            }
        }
        if (state.drawerOpen) Drawer(state, dispatch)
        if (state.sheet != null) Sheet(state, dispatch)
        state.toast?.let { Text(it, Modifier.align(Alignment.BottomCenter).padding(bottom = 32.dp).background(Color(0xff202533), RoundedCornerShape(20.dp)).padding(horizontal = 18.dp, vertical = 10.dp), color = Color.White) }
    }
}

@Composable private fun Header(s: MobileSurfaceState, d: (MobileSurfaceAction) -> Unit) {
    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.SpaceBetween) {
        TextButton(onClick = { d(MobileSurfaceAction.ToggleDrawer) }) { Text("☰", fontSize = 24.sp) }
        Text("NoteMeld", style = MaterialTheme.typography.titleLarge)
        TextButton(onClick = { d(MobileSurfaceAction.Navigate(MobileScreen.SETTINGS)) }) { Text("设置") }
    }
}

@Composable private fun HomeScreen(s: MobileSurfaceState, d: (MobileSurfaceAction) -> Unit) {
    Column(Modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(18.dp)) {
        Text("让 Agent 把想法变成可交付的成果。", style = MaterialTheme.typography.headlineSmall)
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) { listOf(AgentLocation.LOCAL to "本地工作", AgentLocation.CLOUD to "云端工作", AgentLocation.REMOTE to "远程电脑").forEach { (location, label) -> FilterChip(selected = s.location == location, onClick = { d(MobileSurfaceAction.SetLocation(location)) }, label = { Text(label) }) } }
        Text("快捷操作", style = MaterialTheme.typography.titleMedium)
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) { listOf("文档处理", "做演示", "工作台", "更多").forEach { TextButton(onClick = { d(MobileSurfaceAction.Navigate(MobileScreen.SESSION)) }) { Text(it) } } }
        Text("继续工作", style = MaterialTheme.typography.titleMedium)
        if (s.tasks.isEmpty()) Text("暂无已同步会话", color = Color(0xff7d879a)) else s.tasks.take(6).forEach { task -> Card(onClick = { d(MobileSurfaceAction.OpenTask(task.id, task.title)) }, modifier = Modifier.fillMaxWidth()) { Column(Modifier.padding(16.dp)) { Text(task.title); Text(task.status, style = MaterialTheme.typography.bodySmall, color = Color(0xff7d879a)) } } }
        Button(onClick = { d(MobileSurfaceAction.OpenTask(null, "新建会话")) }, modifier = Modifier.fillMaxWidth()) { Text("新建任务") }
    }
}

@Composable private fun SessionScreen(s: MobileSurfaceState, d: (MobileSurfaceAction) -> Unit, pickAttachment: () -> Unit, onSend: (String, (String, Boolean) -> Unit) -> Unit, onCloudSend: (String, String, (String, Boolean) -> Unit) -> Unit, onRemoteSend: (String, RemoteDevice, String, (String, Boolean) -> Unit) -> Unit, onDeleteTask: (String, (Boolean) -> Unit) -> Unit) {
    Column(Modifier.fillMaxSize(), verticalArrangement = Arrangement.spacedBy(10.dp)) {
        Text(s.activeTaskTitle ?: "新建会话", style = MaterialTheme.typography.titleLarge)
        Text("云端 Agent · ${if (s.sending) "生成中" else "运行中"}", color = Color(0xff7d879a))
        if (!s.permissionGranted) TextButton(onClick = { d(MobileSurfaceAction.SetPermission(true)) }) { Text("确认本次 Agent 文件与工具权限") }
        LazyColumn(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(10.dp)) { items(s.messages) { message -> Bubble(message.content, message.role == "user") } }
        if (s.attachments.isNotEmpty()) Text("附件：${s.attachments.joinToString()}", style = MaterialTheme.typography.bodySmall)
        OutlinedTextField(value = s.inputText, onValueChange = { d(MobileSurfaceAction.SetInputText(it)) }, modifier = Modifier.fillMaxWidth(), placeholder = { Text("继续告诉 Agent 你要完成什么…") })
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(6.dp)) { OutlinedButton(onClick = { d(MobileSurfaceAction.ToggleActionMenu) }) { Text("⋯") }; OutlinedButton(onClick = pickAttachment) { Text("添加文件") }; OutlinedButton(onClick = { d(MobileSurfaceAction.ShowProducts) }) { Text("全部产物") }; OutlinedButton(onClick = { d(MobileSurfaceAction.OpenSheet("model")) }) { Text(s.selectedModel) }; Button(enabled = s.connection != ConnectionState.OFFLINE && !s.sending && s.inputText.isNotBlank(), onClick = { val input = s.inputText.trim(); d(MobileSurfaceAction.AddMessage(MobileMessage("user", input))); d(MobileSurfaceAction.SetInputText("")); d(MobileSurfaceAction.SetSending(true)); if (s.location == AgentLocation.LOCAL) onSend(input) { content, terminal -> if (content.isNotBlank()) d(MobileSurfaceAction.AddMessage(MobileMessage("assistant", content))); if (terminal) d(MobileSurfaceAction.SetSending(false)) } else if (s.location == AgentLocation.CLOUD) onCloudSend(s.cloudUrl, input) { content, terminal -> if (content.isNotBlank()) d(MobileSurfaceAction.AddMessage(MobileMessage("assistant", content))); if (terminal) d(MobileSurfaceAction.SetSending(false)) } else { val selected = s.remoteDevices.firstOrNull { it.id == s.selectedRemoteDeviceId }; if (selected == null) { d(MobileSurfaceAction.AddMessage(MobileMessage("assistant", "请先在设置中选择在线远程设备。"))); d(MobileSurfaceAction.SetSending(false)) } else onRemoteSend(s.cloudUrl, selected, input) { content, terminal -> if (content.isNotBlank()) d(MobileSurfaceAction.AddMessage(MobileMessage("assistant", content))); if (terminal) d(MobileSurfaceAction.SetSending(false)) } } }) { Text(if (s.sending) "发送中…" else "发送") } }
        if (s.showActionMenu) Card(Modifier.fillMaxWidth()) { Column(Modifier.padding(8.dp)) { TextButton(onClick = { d(MobileSurfaceAction.ShowProducts) }) { Text("全部产物") }; TextButton(onClick = { val id = s.activeTaskId; if (id == null) d(MobileSurfaceAction.ShowToast("新建会话尚未保存，无法删除")) else onDeleteTask(id) { deleted -> if (deleted) { d(MobileSurfaceAction.DeleteConversation); d(MobileSurfaceAction.ShowToast("对话已删除")) } else d(MobileSurfaceAction.ShowToast("删除失败，请检查连接")) } }) { Text("删除对话") } } }
    }
}
@Composable private fun Bubble(text: String, user: Boolean) { Text(text, Modifier.fillMaxWidth().background(if (user) Color(0xffe8efff) else Color.White, RoundedCornerShape(12.dp)).padding(16.dp), color = Color(0xff202533)) }

@Composable private fun SettingsScreen(s: MobileSurfaceState, d: (MobileSurfaceAction) -> Unit, onCloudLogin: (String, String, String, (String, List<CloudDevice>) -> Unit) -> Unit) { Column(Modifier.fillMaxWidth().verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(8.dp)) { Text("设置", style = MaterialTheme.typography.headlineSmall); SettingRow("记忆库", "${s.memories.size} 个分类") { d(MobileSurfaceAction.Navigate(MobileScreen.MEMORY)) }; HorizontalDivider(); SettingRow("语言", s.language) { d(MobileSurfaceAction.OpenSheet("language")) }; SettingRow("字体大小", "${s.fontSize}px") { d(MobileSurfaceAction.Navigate(MobileScreen.FONT_SIZE)) }; Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) { Text("消息通知设置"); Switch(s.notificationsEnabled, { d(MobileSurfaceAction.SetNotifications(it)) }) }; HorizontalDivider(); Text("Cloud 连接", style = MaterialTheme.typography.titleMedium); OutlinedTextField(s.cloudUrl, { d(MobileSurfaceAction.SetCloudUrl(it)) }, label = { Text("Cloud 地址") }, singleLine = true, modifier = Modifier.fillMaxWidth()); OutlinedTextField(s.cloudUsername, { d(MobileSurfaceAction.SetCloudUsername(it)) }, label = { Text("用户名") }, singleLine = true, modifier = Modifier.fillMaxWidth()); OutlinedTextField(s.cloudPassword, { d(MobileSurfaceAction.SetCloudPassword(it)) }, label = { Text("密码") }, singleLine = true, visualTransformation = PasswordVisualTransformation(), modifier = Modifier.fillMaxWidth()); Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) { Text(s.cloudStatus); Button(onClick = { onCloudLogin(s.cloudUrl, s.cloudUsername, s.cloudPassword) { result, devices -> d(MobileSurfaceAction.SetCloudStatus(result)); d(MobileSurfaceAction.SetRemoteDevices(devices.map { RemoteDevice(it.id, it.displayName, it.platform, it.online, it.publicKey, it.lanEndpoints) })) } }) { Text("登录并同步") } }; if (s.remoteDevices.isNotEmpty()) { Text("远程电脑", style = MaterialTheme.typography.titleMedium); s.remoteDevices.forEach { device -> FilterChip(selected = s.selectedRemoteDeviceId == device.id, onClick = { d(MobileSurfaceAction.SelectRemoteDevice(device.id)); d(MobileSurfaceAction.SetLocation(AgentLocation.REMOTE)) }, label = { Text("${device.displayName} · ${if (device.online) "在线" else "离线"}") }) } }; SettingRow("分享日志", "生成 ZIP") { d(MobileSurfaceAction.ShowToast("日志已准备，可交由宿主分享")) }; SettingRow("存储空间", "%.2f MB".format(s.storage.sumOf { it.sizeMb })) { d(MobileSurfaceAction.Navigate(MobileScreen.STORAGE)) }; Text("NoteMeld\n版本 1.4.0 · Build 20260901", color = Color(0xff7d879a), modifier = Modifier.padding(top = 24.dp)) } }
@Composable private fun SettingsScreenWithTheme(s: MobileSurfaceState, d: (MobileSurfaceAction) -> Unit, onCloudLogin: (String, String, String, (String, List<CloudDevice>) -> Unit) -> Unit) { Column(Modifier.fillMaxWidth()) { SettingRow("主题", when (s.theme) { "dark" -> "深色"; "light" -> "浅色"; else -> "跟随系统" }) { d(MobileSurfaceAction.OpenSheet("theme")) }; SettingsScreen(s, d, onCloudLogin) } }
@Composable private fun SettingRow(title: String, detail: String, onClick: () -> Unit) { TextButton(onClick = onClick, modifier = Modifier.fillMaxWidth()) { Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) { Text(title); Text(detail, color = Color(0xff7d879a)) } } }

@Composable private fun MemoryScreen(s: MobileSurfaceState, d: (MobileSurfaceAction) -> Unit, onAddMemory: (String, (Boolean) -> Unit) -> Unit) { Column(Modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(10.dp)) { Text("记忆库", style = MaterialTheme.typography.headlineSmall); Text("我的记忆 · v7", color = Color(0xff7d879a)); s.memories.forEach { memory -> Card(Modifier.fillMaxWidth()) { Text(memory, Modifier.padding(16.dp)) } }; OutlinedTextField(s.memoryDraft, { d(MobileSurfaceAction.SetMemoryDraft(it)) }, modifier = Modifier.fillMaxWidth(), placeholder = { Text("告诉 NoteMeld 要记住或忘记什么…") }); Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) { TextButton(onClick = { d(MobileSurfaceAction.ShowToast("记忆已复制")) }) { Text("复制") }; Button(enabled = s.memoryDraft.isNotBlank() && s.connection != ConnectionState.OFFLINE, onClick = { val content = s.memoryDraft.trim(); onAddMemory(content) { saved -> if (saved) d(MobileSurfaceAction.AddMemory) else d(MobileSurfaceAction.ShowToast("记忆保存失败，请检查连接")) } }) { Text("添加我的记忆") } } } }
@Composable private fun FontScreen(s: MobileSurfaceState, d: (MobileSurfaceAction) -> Unit) { Column(Modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(18.dp)) { Text("字体大小", style = MaterialTheme.typography.headlineSmall); Text("NoteMeld Agent\n你可以拖动下方滑块调整全局字号。", fontSize = s.fontSize.sp); Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) { Text("跟随系统"); Switch(s.followSystemFont, { d(MobileSurfaceAction.SetFollowSystemFont(it)) }) }; Slider(s.fontSize.toFloat(), { d(MobileSurfaceAction.SetFontSize(it.toInt())) }, valueRange = 13f..19f, steps = 5); Button(onClick = { d(MobileSurfaceAction.ShowToast("字体大小已保存")) }, modifier = Modifier.fillMaxWidth()) { Text("确认") } } }
@Composable private fun StorageScreen(s: MobileSurfaceState, d: (MobileSurfaceAction) -> Unit) { val total = s.storage.sumOf { it.sizeMb }; Column(Modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(10.dp)) { Text("存储空间", style = MaterialTheme.typography.headlineSmall); Text("NoteMeld 占用空间"); Text("%.2f MB".format(total), style = MaterialTheme.typography.headlineMedium); Box(Modifier.fillMaxWidth().height(8.dp).background(Color(0xff4b7cf3), RoundedCornerShape(8.dp))); TextButton(onClick = { d(MobileSurfaceAction.ClearStorage(null)) }) { Text("全部清除") }; s.storage.forEach { item -> Card(Modifier.fillMaxWidth()) { Column(Modifier.padding(14.dp)) { Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) { Column(Modifier.weight(1f)) { Text(item.title); Text(item.description, style = MaterialTheme.typography.bodySmall, color = Color(0xff7d879a)) }; TextButton(onClick = { d(MobileSurfaceAction.ClearStorage(item.id)) }) { Text("清除") } }; Box(Modifier.fillMaxWidth().height(4.dp).background(Color(0xffe8efff), RoundedCornerShape(4.dp))) } } } } }
@Composable private fun Drawer(s: MobileSurfaceState, d: (MobileSurfaceAction) -> Unit) { Card(Modifier.fillMaxWidth().padding(top = 64.dp)) { Column(Modifier.padding(18.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) { Text("任务", style = MaterialTheme.typography.titleMedium); if (s.tasks.isEmpty()) Text("暂无已同步会话", color = Color(0xff7d879a)) else s.tasks.take(8).forEach { task -> TextButton(onClick = { d(MobileSurfaceAction.OpenTask(task.id, task.title)) }, modifier = Modifier.fillMaxWidth()) { Text("${task.title} · ${task.status}") } }; TextButton(onClick = { d(MobileSurfaceAction.CloseOverlay) }) { Text("关闭菜单") } } } }
@Composable private fun Sheet(s: MobileSurfaceState, d: (MobileSurfaceAction) -> Unit) { Card(Modifier.fillMaxWidth().padding(top = 240.dp)) { Column(Modifier.padding(18.dp)) { Text(when (s.sheet) { "model" -> "选择模型"; "theme" -> "选择主题"; "products" -> "当前会话产物"; else -> "选择语言" }, style = MaterialTheme.typography.titleMedium); if (s.sheet == "products") { Text("当前移动端只展示已由真实 Agent 事件返回并落入沙箱的产物。当前会话暂无可下载产物。", color = Color(0xff7d879a), modifier = Modifier.padding(vertical = 12.dp)); TextButton(onClick = { d(MobileSurfaceAction.CloseOverlay) }, modifier = Modifier.fillMaxWidth()) { Text("关闭") } } else { val values = when (s.sheet) { "model" -> listOf("Auto", "Hy4 preview", "Hy3", "GLM-5.3", "Kimi-K3"); "theme" -> listOf("system", "light", "dark"); else -> listOf("跟随系统", "简体中文", "繁體中文", "English") }; values.forEach { value -> TextButton(onClick = { when (s.sheet) { "model" -> d(MobileSurfaceAction.SelectModel(value)); "theme" -> d(MobileSurfaceAction.SetTheme(value)); else -> d(MobileSurfaceAction.SetLanguage(value)) } }, modifier = Modifier.fillMaxWidth()) { Text(if (s.sheet == "theme") mapOf("system" to "跟随系统", "light" to "浅色", "dark" to "深色")[value] ?: value else value) } } } } } }
