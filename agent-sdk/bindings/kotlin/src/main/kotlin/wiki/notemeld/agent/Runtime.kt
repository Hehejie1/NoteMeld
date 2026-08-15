package wiki.notemeld.agent

const val SDK_VERSION: String = "0.1.0"
const val SCHEMA_VERSION: String = "1"

/** Android/JNI translation over the shared C ABI; events remain JSON v1. */
class Runtime(
    configJson: String,
    private val driver: (String) -> String,
    private val onEvent: (String) -> Unit = {}
) : AutoCloseable {
    private var handle: Long = 0L

    init {
        require(nativeSdkVersion() == SDK_VERSION)
        require(nativeSchemaVersion() == SCHEMA_VERSION)
        val created = nativeNew(configJson)
        require(created != 0L) { "native runtime creation failed" }
        try {
            require(nativeSetCallbacks(created, this) == 0) { "callback registration failed" }
            handle = created
        } catch (error: Throwable) {
            nativeFree(created)
            throw error
        }
    }

    fun submitTurn(requestJson: String): ULong = nativeSubmit(handle, requestJson).toULong()
    fun cancel(turnToken: ULong): Int = nativeCancel(handle, turnToken.toLong())
    fun wait(turnToken: ULong, timeoutMs: ULong = 30_000u): Int =
        nativeWait(handle, turnToken.toLong(), timeoutMs.toLong())
    fun steer(turnToken: ULong, steerJson: String): Int =
        nativeSteer(handle, turnToken.toLong(), steerJson)

    @Suppress("unused")
    private fun receiveEvent(eventJson: String): Int =
        try { onEvent(eventJson); 0 } catch (_: Throwable) { -9 }

    @Suppress("unused")
    private fun receiveDriver(requestJson: String): String = try { driver(requestJson) } catch (_: Throwable) {
        """{"schema_version":"1","ok":false,"error":{"code":"sdk_internal_error","message":"host driver failed"}}"""
    }

    override fun close() {
        if (handle != 0L) { nativeFree(handle); handle = 0L }
    }

    companion object {
        init { System.loadLibrary("notemeld_agent_jni") }
        @JvmStatic private external fun nativeSdkVersion(): String
        @JvmStatic private external fun nativeSchemaVersion(): String
        @JvmStatic private external fun nativeNew(configJson: String): Long
        @JvmStatic private external fun nativeSetCallbacks(handle: Long, runtime: Runtime): Int
        @JvmStatic private external fun nativeSubmit(handle: Long, requestJson: String): Long
        @JvmStatic private external fun nativeCancel(handle: Long, turnToken: Long): Int
        @JvmStatic private external fun nativeWait(handle: Long, turnToken: Long, timeoutMs: Long): Int
        @JvmStatic private external fun nativeSteer(handle: Long, turnToken: Long, steerJson: String): Int
        @JvmStatic private external fun nativeFree(handle: Long)
    }
}
