package com.notemeld.mobile

import android.content.ContentValues
import android.content.Context
import android.database.sqlite.SQLiteDatabase
import android.database.sqlite.SQLiteOpenHelper

/**
 * 安卓端 Provider/Model 两级持久化（schema：notemeld.model-add.v1）。
 *
 * - [ModelDatabase]：[SQLiteOpenHelper]，全新数据库 DATABASE_VERSION=1，
 *   两张表 mobile_model_providers / mobile_models，密钥只存 key_ref 与 has_api_key 非空标记；
 * - [ModelDao]：薄 CRUD 封装，行映射为纯数据类；
 * - DDL/去重/默认派生逻辑抽到 [ModelSchema] 纯 JVM 对象，便于单测。
 *
 * 密钥本体在 Android Keystore（[ModelProviderSecretStore]），任何明文密钥不进入本库。
 */

/** Provider 行；api_key 不落库，仅有 [hasApiKey] 非空标记与 [keyRef] Keystore 别名。 */
data class ProviderRecord(
    val id: String,
    val displayName: String,
    val vendorId: String,
    val protocol: String,
    val baseUrl: String,
    val authType: String,
    val keyRef: String?,
    val hasApiKey: Boolean,
    val createdAt: Long,
    val updatedAt: Long,
)

/** Model 行；默认模型在同一 provider 内唯一。 */
data class ModelRecord(
    val id: String,
    val providerId: String,
    val modelId: String,
    val displayName: String,
    val contextWindow: Int,
    val enabled: Boolean,
    val isDefault: Boolean,
    val supportsStreaming: Boolean,
    val supportsVision: Boolean,
    val supportsTools: Boolean,
    val testStatus: String, // untested | ok | failed
    val createdAt: Long,
    val updatedAt: Long,
)

/** 纯 JVM：DDL 常量与不依赖 android.* 的派生逻辑。 */
object ModelSchema {
    const val DATABASE_NAME = "notemeld-models.db"
    const val DATABASE_VERSION = 2

    const val TABLE_PROVIDERS = "mobile_model_providers"
    const val TABLE_MODELS = "mobile_models"

    const val PROVIDER_CREATE_SQL = """
CREATE TABLE $TABLE_PROVIDERS (
    id TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    vendor_id TEXT NOT NULL DEFAULT 'custom',
    protocol TEXT NOT NULL CHECK (protocol IN ('openai-compatible','anthropic-messages','ollama')),
    base_url TEXT NOT NULL,
    auth_type TEXT NOT NULL DEFAULT 'bearer',
    key_ref TEXT,
    has_api_key INTEGER NOT NULL DEFAULT 0,
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL,
    UNIQUE (display_name)
)
"""

    const val MODEL_CREATE_SQL = """
CREATE TABLE $TABLE_MODELS (
    id TEXT PRIMARY KEY,
    provider_id TEXT NOT NULL REFERENCES $TABLE_PROVIDERS(id) ON DELETE CASCADE,
    model_id TEXT NOT NULL,
    display_name TEXT NOT NULL,
    context_window INTEGER NOT NULL DEFAULT 128000,
    enabled INTEGER NOT NULL DEFAULT 1,
    is_default INTEGER NOT NULL DEFAULT 0,
    supports_streaming INTEGER NOT NULL DEFAULT 1,
    supports_vision INTEGER NOT NULL DEFAULT 0,
    supports_tools INTEGER NOT NULL DEFAULT 0,
    test_status TEXT NOT NULL DEFAULT 'untested' CHECK (test_status IN ('untested','ok','failed')),
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL,
    UNIQUE (provider_id, model_id)
)
"""

    /** 规范化上下文：越界/非正数回退默认值（与 [VendorRegistry] 校验配套）。 */
    fun normalizeContext(value: Int?): Int =
        if (value != null && value in VendorRegistry.CONTEXT_MIN..VendorRegistry.CONTEXT_MAX) value
        else VendorRegistry.DEFAULT_CONTEXT

    /** 计算一个 provider 内重复的 model_id，返回保持入参顺序的去重列表。 */
    fun duplicateModelIds(existing: Collection<String>, incoming: Collection<String>): List<String> {
        val seen = existing.toMutableSet()
        val duplicates = linkedSetOf<String>()
        incoming.forEach { id -> if (!seen.add(id)) duplicates.add(id) }
        return duplicates.toList()
    }
}

class ModelDatabase(context: Context) :
    SQLiteOpenHelper(context, ModelSchema.DATABASE_NAME, null, ModelSchema.DATABASE_VERSION) {

    override fun onCreate(db: SQLiteDatabase) {
        db.execSQL(ModelSchema.PROVIDER_CREATE_SQL)
        db.execSQL(ModelSchema.MODEL_CREATE_SQL)
    }

    override fun onUpgrade(db: SQLiteDatabase, oldVersion: Int, newVersion: Int) {
        // v1 -> v2：additive，新增三个能力列；禁止销毁既有数据。
        if (oldVersion < 2) {
            db.execSQL("ALTER TABLE ${ModelSchema.TABLE_MODELS} ADD COLUMN supports_streaming INTEGER NOT NULL DEFAULT 1")
            db.execSQL("ALTER TABLE ${ModelSchema.TABLE_MODELS} ADD COLUMN supports_vision INTEGER NOT NULL DEFAULT 0")
            db.execSQL("ALTER TABLE ${ModelSchema.TABLE_MODELS} ADD COLUMN supports_tools INTEGER NOT NULL DEFAULT 0")
        }
    }

    override fun onConfigure(db: SQLiteDatabase) {
        db.setForeignKeyConstraintsEnabled(true)
    }
}

/** 薄 CRUD；调用方负责在 IO 线程使用并 [close]。 */
class ModelDao(context: Context) {
    private val helper = ModelDatabase(context.applicationContext)

    private fun writable() = helper.writableDatabase
    private fun readable() = helper.readableDatabase

    fun createProvider(record: ProviderRecord) {
        val db = writable()
        db.insertWithOnConflict(
            ModelSchema.TABLE_PROVIDERS, null, record.toValues(),
            SQLiteDatabase.CONFLICT_ABORT,
        )
    }

    fun updateProvider(record: ProviderRecord) {
        writable().update(
            ModelSchema.TABLE_PROVIDERS, record.toValues(), "id = ?", arrayOf(record.id),
        )
    }

    fun getProvider(id: String): ProviderRecord? {
        val cursor = readable().query(
            ModelSchema.TABLE_PROVIDERS, null, "id = ?", arrayOf(id), null, null, null,
        )
        return cursor.use { if (it.moveToFirst()) it.toProvider() else null }
    }

    fun listProviders(): List<ProviderRecord> {
        val cursor = readable().query(
            ModelSchema.TABLE_PROVIDERS, null, null, null, null, null, "created_at ASC, id ASC",
        )
        return cursor.use {
            buildList { while (it.moveToNext()) add(it.toProvider()) }
        }
    }

    fun deleteProvider(id: String) {
        writable().delete(ModelSchema.TABLE_PROVIDERS, "id = ?", arrayOf(id))
    }

    /** 全量替换一个 provider 的模型（同事务内删旧插新）。 */
    fun replaceModels(providerId: String, models: List<ModelRecord>) {
        val db = writable()
        db.beginTransaction()
        try {
            db.delete(ModelSchema.TABLE_MODELS, "provider_id = ?", arrayOf(providerId))
            models.forEach { db.insertOrThrow(ModelSchema.TABLE_MODELS, null, it.toValues()) }
            db.setTransactionSuccessful()
        } finally {
            db.endTransaction()
        }
    }

    fun addModel(record: ModelRecord) {
        writable().insertWithOnConflict(
            ModelSchema.TABLE_MODELS, null, record.toValues(), SQLiteDatabase.CONFLICT_ABORT,
        )
    }

    fun updateModel(record: ModelRecord) {
        writable().update(
            ModelSchema.TABLE_MODELS, record.toValues(), "id = ?", arrayOf(record.id),
        )
    }

    fun listModels(providerId: String): List<ModelRecord> {
        val cursor = readable().query(
            ModelSchema.TABLE_MODELS, null, "provider_id = ?", arrayOf(providerId),
            null, null, "created_at ASC, id ASC",
        )
        return cursor.use { buildList { while (it.moveToNext()) add(it.toModel()) } }
    }

    fun listAllModels(): List<ModelRecord> {
        val cursor = readable().query(
            ModelSchema.TABLE_MODELS, null, null, null, null, null, "created_at ASC, id ASC",
        )
        return cursor.use { buildList { while (it.moveToNext()) add(it.toModel()) } }
    }

    fun getModel(id: String): ModelRecord? {
        val cursor = readable().query(
            ModelSchema.TABLE_MODELS, null, "id = ?", arrayOf(id), null, null, null,
        )
        return cursor.use { if (it.moveToFirst()) it.toModel() else null }
    }

    /** 清除同 provider 内既有默认标记，再设置目标模型。 */
    fun setDefault(model: ModelRecord) {
        val db = writable()
        db.beginTransaction()
        try {
            val now = System.currentTimeMillis()
            val clear = ContentValues().apply {
                put("is_default", 0)
                put("updated_at", now)
            }
            db.update(ModelSchema.TABLE_MODELS, clear, "provider_id = ?", arrayOf(model.providerId))
            val set = ContentValues().apply {
                put("is_default", 1)
                put("updated_at", now)
            }
            db.update(ModelSchema.TABLE_MODELS, set, "id = ?", arrayOf(model.id))
            db.setTransactionSuccessful()
        } finally {
            db.endTransaction()
        }
    }

    fun deleteModel(id: String) {
        writable().delete(ModelSchema.TABLE_MODELS, "id = ?", arrayOf(id))
    }

    fun close() = helper.close()

    private fun ProviderRecord.toValues() = ContentValues().apply {
        put("id", id)
        put("display_name", displayName)
        put("vendor_id", vendorId)
        put("protocol", protocol)
        put("base_url", baseUrl)
        put("auth_type", authType)
        put("key_ref", keyRef)
        put("has_api_key", if (hasApiKey) 1 else 0)
        put("created_at", createdAt)
        put("updated_at", updatedAt)
    }

    private fun ModelRecord.toValues() = ContentValues().apply {
        put("id", id)
        put("provider_id", providerId)
        put("model_id", modelId)
        put("display_name", displayName)
        put("context_window", contextWindow)
        put("enabled", if (enabled) 1 else 0)
        put("is_default", if (isDefault) 1 else 0)
        put("supports_streaming", if (supportsStreaming) 1 else 0)
        put("supports_vision", if (supportsVision) 1 else 0)
        put("supports_tools", if (supportsTools) 1 else 0)
        put("test_status", testStatus)
        put("created_at", createdAt)
        put("updated_at", updatedAt)
    }

    private fun android.database.Cursor.columnIndex(name: String) = getColumnIndexOrThrow(name)

    private fun android.database.Cursor.toProvider() = ProviderRecord(
        id = getString(columnIndex("id")),
        displayName = getString(columnIndex("display_name")),
        vendorId = getString(columnIndex("vendor_id")),
        protocol = getString(columnIndex("protocol")),
        baseUrl = getString(columnIndex("base_url")),
        authType = getString(columnIndex("auth_type")),
        keyRef = getString(columnIndex("key_ref")),
        hasApiKey = getInt(columnIndex("has_api_key")) != 0,
        createdAt = getLong(columnIndex("created_at")),
        updatedAt = getLong(columnIndex("updated_at")),
    )

    private fun android.database.Cursor.toModel() = ModelRecord(
        id = getString(columnIndex("id")),
        providerId = getString(columnIndex("provider_id")),
        modelId = getString(columnIndex("model_id")),
        displayName = getString(columnIndex("display_name")),
        contextWindow = getInt(columnIndex("context_window")),
        enabled = getInt(columnIndex("enabled")) != 0,
        isDefault = getInt(columnIndex("is_default")) != 0,
        supportsStreaming = getInt(columnIndex("supports_streaming")) != 0,
        supportsVision = getInt(columnIndex("supports_vision")) != 0,
        supportsTools = getInt(columnIndex("supports_tools")) != 0,
        testStatus = getString(columnIndex("test_status")),
        createdAt = getLong(columnIndex("created_at")),
        updatedAt = getLong(columnIndex("updated_at")),
    )
}
