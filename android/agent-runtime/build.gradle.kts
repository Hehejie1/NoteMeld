import java.security.MessageDigest

plugins {
    id("com.android.library")
    id("org.jetbrains.kotlin.android")
}

val sdkTaskRequested = gradle.startParameter.taskNames.any { task ->
    task == "build" || task == "check" || task.contains(":app:") || task.contains(":agent-runtime:")
}
val sdkAar = providers.environmentVariable("NOTEMELD_AGENT_SDK_AAR").orNull?.let(::file)
if (sdkTaskRequested) {
    require(sdkAar != null) { "NOTEMELD_AGENT_SDK_AAR must point to the pinned standalone SDK AAR" }
    require(sdkAar.isFile) { "NOTEMELD_AGENT_SDK_AAR does not exist" }
    val expectedSha256 = providers.environmentVariable("NOTEMELD_AGENT_SDK_AAR_SHA256").orNull
        ?: "e4f8acd6a2217b8fce683c26de2823b4407ebb8b5d9fa58c804c6142cc7fc2c0"
    val actualSha256 = MessageDigest.getInstance("SHA-256").digest(sdkAar.readBytes())
        .joinToString("") { "%02x".format(it) }
    require(actualSha256 == expectedSha256.lowercase()) {
        "NOTEMELD_AGENT_SDK_AAR hash mismatch"
    }
}

android {
    namespace = "com.notemeld.runtime"
    compileSdk = 35
    defaultConfig { minSdk = 26 }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions { jvmTarget = "17" }
}

dependencies {
    // The application packages the same verified AAR; libraries cannot nest a local AAR.
    if (sdkAar != null) compileOnly(files(sdkAar))
}
