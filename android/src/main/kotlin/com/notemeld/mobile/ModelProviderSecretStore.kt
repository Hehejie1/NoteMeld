package com.notemeld.mobile

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

/**
 * 统一的模型 Provider 密钥保管：每个 Provider 一个 Android Keystore AES/GCM 密钥，
 * 别名规则 `model_provider_<providerId>`；数据库只存 key_ref 与非空标记。
 *
 * - [put]/[get]/[clear]：密文格式 Base64(iv[12] + ciphertext)，与旧实现一致；
 * - [migrateLegacyOnce]：把旧的 LocalProviderSecretStore 单密钥、
 *   AndroidPairedModelStore 中夹带的 api_key（按新禁令本就不该再存在）迁移/清理，
 *   并移除旧 prefs 标量；全程仅执行一次（迁移 flag），先写新别名再清旧存储。
 */
class ModelProviderSecretStore(private val context: Context) {

    fun keyRef(providerId: String): String = alias(providerId)

    fun put(providerId: String, apiKey: String) {
        val cipher = Cipher.getInstance(TRANSFORMATION)
        cipher.init(Cipher.ENCRYPT_MODE, getOrCreateKey(providerId))
        val iv = cipher.iv
        val ciphertext = cipher.doFinal(apiKey.toByteArray(Charsets.UTF_8))
        val packed = ByteArray(iv.size + ciphertext.size)
        System.arraycopy(iv, 0, packed, 0, iv.size)
        System.arraycopy(ciphertext, 0, packed, iv.size, ciphertext.size)
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit()
            .putString(alias(providerId), Base64.encodeToString(packed, Base64.NO_WRAP))
            .apply()
    }

    fun get(providerId: String): String? {
        val raw = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
            .getString(alias(providerId), null) ?: return null
        return runCatching {
            val packed = Base64.decode(raw, Base64.NO_WRAP)
            val iv = packed.copyOfRange(0, GCM_IV_LENGTH)
            val ciphertext = packed.copyOfRange(GCM_IV_LENGTH, packed.size)
            val cipher = Cipher.getInstance(TRANSFORMATION)
            cipher.init(Cipher.DECRYPT_MODE, getOrCreateKey(providerId), GCMParameterSpec(GCM_TAG_LENGTH_BITS, iv))
            String(cipher.doFinal(ciphertext), Charsets.UTF_8)
        }.getOrNull()
    }

    fun clear(providerId: String) {
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit()
            .remove(alias(providerId)).apply()
        runCatching { keyStore.deleteEntry(alias(providerId)) }
    }

    /**
     * 一次性迁移旧凭据：
     * 1. 旧 LocalProviderSecretStore（prefs notemeld-local-provider-secret）存在旧密钥时，
     *    迁到 [LEGACY_PROVIDER_ID] 的新别名；
     * 2. 删除旧 notemeld-paired-models 的加密 bundle（配对下发禁令：配对不再下发任何凭据，
     *    旧缓存整体加密无法局部剥离 api_key，直接删除，元数据由 UI 重新同步）；
     * 3. 无论是否有密钥迁移，都清空旧标量 prefs 键并写迁移 flag。
     *
     * 返回迁移出的 legacy provider 配置（可为 null）。
     */
    fun migrateLegacyOnce(): LegacyProviderMigration? {
        val statePrefs = context.getSharedPreferences(STATE_PREFS, Context.MODE_PRIVATE)
        if (statePrefs.getBoolean(MIGRATION_FLAG, false)) return null

        var legacy: LegacyProviderMigration? = null
        // 1. 旧本地 Provider 密钥（Keystore 别名 notemeld-local-provider-api-key）
        val oldSecretPrefs = context.getSharedPreferences(OLD_SECRET_PREFS, Context.MODE_PRIVATE)
        val oldEncrypted = oldSecretPrefs.getString(OLD_SECRET_KEY, null)
            ?: oldSecretPrefs.getString("localModelApiKey", null)
        val oldApiKey = oldEncrypted?.let { decryptOldKey(it) }
        val baseUrl = statePrefs.getString("localModelBaseUrl", "")?.let(VendorRegistry::trimUrl).orEmpty()
        val modelName = statePrefs.getString("localModelName", null)
        if (!oldApiKey.isNullOrBlank()) {
            put(LEGACY_PROVIDER_ID, oldApiKey)
            legacy = LegacyProviderMigration(
                providerId = LEGACY_PROVIDER_ID,
                baseUrl = baseUrl,
                modelName = modelName,
            )
        }
        oldSecretPrefs.edit().clear().apply()
        runCatching { keyStore.deleteEntry(OLD_KEYSTORE_ALIAS) }

        // 2. 旧 paired bundle 整体加密且按新禁令不得保留任何凭据，直接删除
        dropPairedBundle()

        // 3. 清旧标量（无论是否迁移成功都只做一次）
        statePrefs.edit()
            .remove("localModelBaseUrl")
            .remove("localModelName")
            .remove("availableModels")
            .remove("modelDraftVendor")
            .remove("modelDraftProvider")
            .remove("modelDraftUrl")
            .remove("modelDraftName")
            .remove("modelDraftContext")
            .putBoolean(MIGRATION_FLAG, true)
            .apply()

        return legacy
    }

    private fun dropPairedBundle() {
        context.getSharedPreferences(OLD_PAIRED_PREFS, Context.MODE_PRIVATE).edit().clear().apply()
        runCatching { keyStore.deleteEntry(OLD_PAIRED_KEYSTORE_ALIAS) }
    }

    private fun decryptOldKey(encrypted: String): String? = runCatching {
        val packed = Base64.decode(encrypted, Base64.NO_WRAP)
        if (packed.size <= GCM_IV_LENGTH) return@runCatching null
        val iv = packed.copyOfRange(0, GCM_IV_LENGTH)
        val ciphertext = packed.copyOfRange(GCM_IV_LENGTH, packed.size)
        val key = keyStore.getKey(OLD_KEYSTORE_ALIAS, null) as? SecretKey ?: return@runCatching null
        val cipher = Cipher.getInstance(TRANSFORMATION)
        cipher.init(Cipher.DECRYPT_MODE, key, GCMParameterSpec(GCM_TAG_LENGTH_BITS, iv))
        String(cipher.doFinal(ciphertext), Charsets.UTF_8)
    }.getOrNull()

    private fun getOrCreateKey(providerId: String): SecretKey {
        val alias = alias(providerId)
        (keyStore.getEntry(alias, null) as? KeyStore.SecretKeyEntry)?.let { return it.secretKey }
        val generator = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, ANDROID_KEYSTORE)
        generator.init(
            KeyGenParameterSpec.Builder(alias, KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT)
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                .build(),
        )
        return generator.generateKey()
    }

    private fun alias(providerId: String): String = "$ALIAS_PREFIX$providerId"

    private val keyStore: KeyStore by lazy {
        KeyStore.getInstance(ANDROID_KEYSTORE).apply { load(null) }
    }

    data class LegacyProviderMigration(
        val providerId: String,
        val baseUrl: String,
        val modelName: String?,
    )

    companion object {
        private const val ANDROID_KEYSTORE = "AndroidKeyStore"
        private const val TRANSFORMATION = "AES/GCM/NoPadding"
        private const val GCM_IV_LENGTH = 12
        private const val GCM_TAG_LENGTH_BITS = 128
        private const val PREFS = "notemeld-model-provider-secrets"
        private const val ALIAS_PREFIX = "model_provider_"

        const val LEGACY_PROVIDER_ID = "legacy-local"
        private const val STATE_PREFS = "notemeld-mobile-state"
        private const val MIGRATION_FLAG = "modelProviderMigrationV1Done"

        private const val OLD_SECRET_PREFS = "notemeld-local-provider-secret"
        private const val OLD_SECRET_KEY = "notemeld-local-provider-api-key"
        private const val OLD_KEYSTORE_ALIAS = "notemeld-local-provider-api-key"

        private const val OLD_PAIRED_PREFS = "notemeld-paired-models"
        private const val OLD_PAIRED_KEYSTORE_ALIAS = "notemeld-paired-models-key"
    }
}
