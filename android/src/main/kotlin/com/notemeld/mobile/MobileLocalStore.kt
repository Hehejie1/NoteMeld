package com.notemeld.mobile

import android.content.Context
import org.json.JSONArray
import java.io.File
import android.util.Base64

/** Local mobile projection; server data remains authoritative for sessions. */
object MobileLocalStore {
    private const val PREFS = "notemeld-mobile-state"
    private const val PENDING_LOCAL_TURN = "pendingLocalTurn"
    private const val LOCAL_EVENT_LOG = "localEventLog"
    private const val LOCAL_EVENT_TURN_ID = "localEventTurnId"
    private const val LOCAL_EVENT_CURSOR = "localEventCursor"

    fun load(context: Context, restoreNavigation: Boolean = false): MobileSurfaceState {
        val prefs = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
        val memories = prefs.getString("memories", null)?.let(::decodeStrings) ?: emptyList()
        val memoryIds = prefs.getString("memoryIds", null)?.let(::decodeStrings) ?: emptyList()
        val messages = prefs.getString("messages", null)?.let(::decodeMessages) ?: emptyList()
        val location = runCatching { AgentLocation.valueOf(prefs.getString("location", AgentLocation.LOCAL.name) ?: AgentLocation.LOCAL.name) }.getOrDefault(AgentLocation.LOCAL)
        val screen = if (restoreNavigation) runCatching { MobileScreen.valueOf(prefs.getString("screen", MobileScreen.HOME.name) ?: MobileScreen.HOME.name) }.getOrDefault(MobileScreen.HOME) else MobileScreen.HOME
        val settingsReturnScreen = if (restoreNavigation) runCatching { MobileScreen.valueOf(prefs.getString("settingsReturnScreen", MobileScreen.HOME.name) ?: MobileScreen.HOME.name) }.getOrDefault(MobileScreen.HOME) else MobileScreen.HOME
        // Authorization survives cold starts; accept the mode even if older
        // installs only persisted one of the two keys.
        val permissionMode = prefs.getString("permissionMode", "none") ?: "none"
        val permissionGranted = prefs.getBoolean("permissionGranted", false) ||
            permissionMode == "default" || permissionMode == "full"
        return MobileSurfaceState(
            screen = screen,
            settingsReturnScreen = settingsReturnScreen,
            permissionGranted = permissionGranted,
            permissionMode = permissionMode,
            // 模型配置不再持久化到本 store：本机模型在 SQLite，Cloud/配对目录
            // 在各自独立 store，且任何密钥绝不进入本文件。
            theme = prefs.getString("theme", "system") ?: "system",
            language = prefs.getString("language", "跟随系统") ?: "跟随系统",
            fontSize = prefs.getInt("fontSize", 16),
            followSystemFont = prefs.getBoolean("followSystemFont", false),
            notificationsEnabled = prefs.getBoolean("notificationsEnabled", true),
            // 10.0.2.2 (emulator host loopback) and 127.0.0.1 (real device with
            // adb reverse) are both valid hand-entered endpoints; never drop them.
            cloudUrl = prefs.getString("cloudUrl", "") ?: "",
            cloudUsername = prefs.getString("cloudUsername", "") ?: "",
            location = location,
            selectedWorkTab = location,
            activeTaskId = prefs.getString("activeTaskId", null),
            activeTaskTitle = prefs.getString("activeTaskTitle", null),
            messages = messages,
            terminalEvents = prefs.getString("terminalEvents", null)?.let(::decodeStrings) ?: emptyList(),
            memories = memories,
            memoryIds = memoryIds,
            storage = storage(context),
        )
    }

    fun loadTasks(context: Context): List<MobileTask> {
        val prefs = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
        val raw = prefs.getString("tasks", null) ?: return emptyList()
        return runCatching {
            val rows = JSONArray(raw)
            (0 until rows.length()).mapNotNull { index ->
                val row = rows.optJSONObject(index) ?: return@mapNotNull null
                MobileTask(row.optString("id"), row.optString("title", "未命名会话"), row.optString("status", "idle"))
            }
        }.getOrDefault(emptyList())
    }

    fun save(context: Context, state: MobileSurfaceState) {
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit()
            .putString("screen", state.screen.name)
            .putString("settingsReturnScreen", state.settingsReturnScreen.name)
            .putBoolean("permissionGranted", state.permissionGranted)
            .putString("permissionMode", state.permissionMode)
            // 模型字段（selectedModel/本机 Provider/Cloud 目录/任何密钥）不再写入。
            .putString("theme", state.theme)
            .putString("language", state.language)
            .putInt("fontSize", state.fontSize)
            .putBoolean("followSystemFont", state.followSystemFont)
            .putBoolean("notificationsEnabled", state.notificationsEnabled)
            .putString("cloudUrl", state.cloudUrl)
            .putString("cloudUsername", state.cloudUsername)
            .putString("location", state.location.name)
            .putString("activeTaskId", state.activeTaskId)
            .putString("activeTaskTitle", state.activeTaskTitle)
            .putString("messages", encodeMessages(state.messages.takeLast(200)))
            .putString("terminalEvents", JSONArray(state.terminalEvents.takeLast(50)).toString())
            .putString("memories", JSONArray(state.memories).toString())
            .putString("memoryIds", JSONArray(state.memoryIds).toString())
            .apply()
    }

    fun saveTasks(context: Context, tasks: List<MobileTask>) {
        val rows = JSONArray()
        tasks.take(50).forEach { task -> rows.put(org.json.JSONObject().put("id", task.id).put("title", task.title).put("status", task.status)) }
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit().putString("tasks", rows.toString()).apply()
    }

    fun markLocalTurnPending(context: Context, requestId: String, input: String) {
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit()
            .putString(PENDING_LOCAL_TURN, org.json.JSONObject()
                .put("request_id", requestId)
                .put("input", input)
                .put("status", "running")
                .toString())
            // This marker is the crash boundary: apply() may still be queued
            // when Android kills the process immediately after submit.
            .commit()
    }

    fun completeLocalTurn(context: Context) {
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit()
            .remove(PENDING_LOCAL_TURN)
            .commit()
    }

    /** Persist only bounded event metadata; event payloads stay in the UI projection. */
    fun recordLocalEvent(context: Context, event: org.json.JSONObject) {
        val envelope = event.optJSONObject("event") ?: event
        val turnId = event.optString("turn_id", "").ifBlank { envelope.optString("turn_id", "") }
        val sequence = event.optLong("sequence", -1L)
        if (turnId.isBlank() || sequence < 0L) return
        val prefs = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
        val previousTurn = prefs.getString(LOCAL_EVENT_TURN_ID, null)
        val previousSequence = prefs.getLong(LOCAL_EVENT_CURSOR, -1L)
        val pendingTurn = prefs.getString(PENDING_LOCAL_TURN, null)?.let { raw ->
            runCatching { org.json.JSONObject(raw).optString("request_id").takeIf(String::isNotBlank) }.getOrNull()
        }
        // A late callback from an older native turn must never replace the
        // current projection. While a turn is active, only its request id is
        // accepted; while idle, only the last projected turn is accepted.
        if ((pendingTurn != null && pendingTurn != turnId) || (pendingTurn == null && previousTurn != null && previousTurn != turnId)) return
        if (previousTurn == turnId && sequence <= previousSequence) return
        val rows = if (previousTurn == turnId) {
            runCatching { JSONArray(prefs.getString(LOCAL_EVENT_LOG, "[]")) }.getOrDefault(JSONArray())
        } else JSONArray()
        rows.put(org.json.JSONObject()
            .put("turn_id", turnId)
            .put("sequence", sequence)
            .put("type", envelope.optString("type", event.optString("type", "unknown")))
            .put("timestamp", event.optString("timestamp", "")))
        while (rows.length() > 200) rows.remove(0)
        val terminal = envelope.optString("type", event.optString("type", "")) in setOf(
            "turn.succeeded", "turn.failed", "turn.cancelled", "turn.interrupted",
        )
        val editor = prefs.edit()
            .putString(LOCAL_EVENT_TURN_ID, turnId)
            .putLong(LOCAL_EVENT_CURSOR, sequence)
            .putString(LOCAL_EVENT_LOG, rows.toString())
        if (terminal) editor.commit() else editor.apply()
    }

    /**
     * Converts an unknown in-flight local turn into an explicit recovery
     * state. We never replay it: an interrupted tool side effect is unknown.
     */
    fun recoverInterruptedLocalTurn(context: Context): Boolean {
        val prefs = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
        val pending = prefs.getString(PENDING_LOCAL_TURN, null)?.let { raw ->
            runCatching { org.json.JSONObject(raw) }.getOrNull()
        } ?: return false
        val state = load(context)
        val nextEvents = (state.terminalEvents + "turn.interrupted:needs_attention").takeLast(50)
        val pendingInput = pending.optString("input").takeIf(String::isNotBlank)
        val withInput = if (pendingInput != null && state.messages.lastOrNull()?.content != pendingInput) {
            state.messages + MobileMessage("user", pendingInput)
        } else state.messages
        val nextMessages = (withInput + MobileMessage(
            "system",
            "上次本机 Agent 会话在进程回收时中断；未知副作用未自动重放，请确认后重新发送。",
        )).takeLast(200)
        prefs.edit()
            .remove(PENDING_LOCAL_TURN)
            .putString("terminalEvents", JSONArray(nextEvents).toString())
            .putString("messages", encodeMessages(nextMessages))
            .commit()
        return true
    }

    fun addMemory(context: Context, value: String): String {
        val current = load(context).memories
        val id = java.util.UUID.randomUUID().toString()
        val state = load(context)
        save(context, state.copy(memories = (current + value).takeLast(200), memoryIds = (state.memoryIds + id).takeLast(200)))
        return id
    }

    fun deleteMemory(context: Context, index: Int): Boolean {
        val state = load(context)
        if (index !in state.memories.indices) return false
        save(context, state.copy(
            memories = state.memories.filterIndexed { position, _ -> position != index },
            memoryIds = state.memoryIds.filterIndexed { position, _ -> position != index },
        ))
        return true
    }

    fun deleteTask(context: Context, id: String): Boolean {
        val current = loadTasks(context)
        val next = current.filterNot { it.id == id }
        saveTasks(context, next)
        return next.size != current.size
    }

    fun clear(context: Context, id: String?): List<StorageItem> {
        val roots = storageRoots(context)
        val scopes = if (id == null) roots.keys else setOf(id)
        scopes.forEach { scope -> roots[scope]?.let(::clearDirectory) }

        // Session/history projections may contain unsynced data. Without a
        // durable per-record sync marker, preserve them rather than guessing.
        // Cleanup must also never touch the Cloud token or remote identity stores.
        if (id == null || id == "cloud") {
            context.getSharedPreferences("notemeld-cloud-sync", Context.MODE_PRIVATE).edit().clear().apply()
        }
        return storage(context)
    }

    fun stageAttachments(context: Context, attachments: List<MobileAttachment>) {
        val root = File(context.filesDir, "cloud-cache/attachments").also(File::mkdirs)
        root.listFiles()?.forEach { it.delete() }
        attachments.take(16).forEachIndexed { index, item ->
            runCatching { File(root, "%02d-%s".format(index, File(item.name).name)).writeBytes(Base64.decode(item.contentBase64, Base64.NO_WRAP)) }
        }
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit().putString("attachmentNames", JSONArray(attachments.take(16).map { it.name }).toString()).apply()
    }

    fun stagedAttachments(context: Context): List<MobileAttachment> {
        val root = File(context.filesDir, "cloud-cache/attachments")
        val names = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).getString("attachmentNames", null)?.let(::decodeStrings) ?: emptyList()
        return root.listFiles()?.sortedBy { it.name }?.mapIndexedNotNull { index, file ->
            val bytes = runCatching { file.readBytes() }.getOrNull() ?: return@mapIndexedNotNull null
            MobileAttachment(names.getOrNull(index) ?: file.name, Base64.encodeToString(bytes, Base64.NO_WRAP), bytes.size, "application/octet-stream")
        } ?: emptyList()
    }

    fun storage(context: Context): List<StorageItem> {
        val roots = storageRoots(context)
        return listOf(
            StorageItem("cache", "缓存", "接口、预览与附件缓存", sizeMb(roots.getValue("cache"))),
            StorageItem("cloud", "云端缓存文件", "本机保存的 Cloud 事件与附件缓存；未同步会话不会被清理", sizeMb(roots.getValue("cloud"))),
            StorageItem("local", "本机文件", "本机沙箱文件；未同步会话投影不会被清理", sizeMb(roots.getValue("local"))),
            StorageItem("artifacts", "下载的产物文件", "沙箱下载的预览与产物", sizeMb(roots.getValue("artifacts"))),
        )
    }

    private fun storageRoots(context: Context): Map<String, File> = mapOf(
        "cache" to context.cacheDir,
        "cloud" to File(context.filesDir, "cloud-cache").also(File::mkdirs),
        "local" to File(context.filesDir, "local").also(File::mkdirs),
        "artifacts" to File(context.filesDir, "artifacts").also(File::mkdirs),
    )

    private fun sizeMb(root: File): Double = root.walkTopDown().filter(File::isFile).sumOf { it.length() }.toDouble() / (1024.0 * 1024.0)

    private fun clearDirectory(root: File) { if (root.exists()) root.listFiles()?.forEach { it.deleteRecursively() } }

    private fun decodeStrings(raw: String): List<String> = runCatching {
        val values = JSONArray(raw)
        (0 until values.length()).mapNotNull { values.optString(it).takeIf(String::isNotBlank) }
    }.getOrDefault(emptyList())

    private fun encodeMessages(messages: List<MobileMessage>): String = JSONArray().apply {
        messages.forEach { put(org.json.JSONObject().put("role", it.role).put("content", it.content)) }
    }.toString()

    private fun decodeMessages(raw: String): List<MobileMessage> = runCatching {
        val values = JSONArray(raw)
        (0 until values.length()).mapNotNull { index ->
            val value = values.optJSONObject(index) ?: return@mapNotNull null
            val role = value.optString("role").takeIf(String::isNotBlank) ?: return@mapNotNull null
            MobileMessage(role, value.optString("content"))
        }
    }.getOrDefault(emptyList())
}
