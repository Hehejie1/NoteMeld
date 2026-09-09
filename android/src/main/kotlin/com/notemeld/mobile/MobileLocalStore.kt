package com.notemeld.mobile

import android.content.Context
import org.json.JSONArray
import java.io.File
import android.util.Base64

/** Local mobile projection; server data remains authoritative for sessions. */
object MobileLocalStore {
    private const val PREFS = "notemeld-mobile-state"

    fun load(context: Context): MobileSurfaceState {
        val prefs = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
        val memories = prefs.getString("memories", null)?.let(::decodeStrings) ?: emptyList()
        return MobileSurfaceState(
            selectedModel = prefs.getString("selectedModel", "Auto") ?: "Auto",
            theme = prefs.getString("theme", "system") ?: "system",
            language = prefs.getString("language", "跟随系统") ?: "跟随系统",
            fontSize = prefs.getInt("fontSize", 16),
            followSystemFont = prefs.getBoolean("followSystemFont", false),
            notificationsEnabled = prefs.getBoolean("notificationsEnabled", true),
            cloudUrl = prefs.getString("cloudUrl", "http://10.0.2.2:8583") ?: "http://10.0.2.2:8583",
            cloudUsername = prefs.getString("cloudUsername", "") ?: "",
            memories = memories,
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
            .putString("selectedModel", state.selectedModel)
            .putString("theme", state.theme)
            .putString("language", state.language)
            .putInt("fontSize", state.fontSize)
            .putBoolean("followSystemFont", state.followSystemFont)
            .putBoolean("notificationsEnabled", state.notificationsEnabled)
            .putString("cloudUrl", state.cloudUrl)
            .putString("cloudUsername", state.cloudUsername)
            .putString("memories", JSONArray(state.memories).toString())
            .apply()
    }

    fun saveTasks(context: Context, tasks: List<MobileTask>) {
        val rows = JSONArray()
        tasks.take(50).forEach { task -> rows.put(org.json.JSONObject().put("id", task.id).put("title", task.title).put("status", task.status)) }
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit().putString("tasks", rows.toString()).apply()
    }

    fun clear(context: Context, id: String?): List<StorageItem> {
        val roots = storageRoots(context)
        if (id == null) roots.values.forEach(::clearDirectory) else roots[id]?.let(::clearDirectory)
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
            StorageItem("cloud", "云端对话数据", "本机保存的云端事件与缓存", sizeMb(roots.getValue("cloud"))),
            StorageItem("local", "本机对话数据", "仅保存在本机的会话记录", sizeMb(roots.getValue("local"))),
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
}
