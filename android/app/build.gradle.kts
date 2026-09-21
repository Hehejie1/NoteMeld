plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("org.jetbrains.kotlin.plugin.compose")
}

import java.security.MessageDigest
import java.util.zip.ZipFile

val appTaskRequested = gradle.startParameter.taskNames.any { task ->
    task == "build" || task == "check" || task.contains(":app:")
}
val sdkAar = providers.environmentVariable("NOTEMELD_AGENT_SDK_AAR").orNull?.let(::file)
if (appTaskRequested) {
    require(sdkAar != null) { "NOTEMELD_AGENT_SDK_AAR must point to the pinned standalone SDK AAR" }
    require(sdkAar.isFile) { "NOTEMELD_AGENT_SDK_AAR does not exist" }
    val pinFile = rootProject.file("sdk-artifact-pin.json")
    require(pinFile.isFile) { "android/sdk-artifact-pin.json is missing" }
    val pin = pinFile.readText()
    fun pinned(name: String): String = Regex("\\\"$name\\\"\\s*:\\s*\\\"([^\\\"]+)\\\"").find(pin)?.groupValues?.get(1)
        ?: error("sdk-artifact-pin.json is missing $name")
    val actualSha256 = MessageDigest.getInstance("SHA-256").digest(sdkAar.readBytes()).joinToString("") { "%02x".format(it) }
    require(actualSha256 == pinned("aar_sha256")) {
        "SDK AAR SHA-256 mismatch: expected ${pinned("aar_sha256")}, got $actualSha256"
    }
    ZipFile(sdkAar).use { archive ->
        val metadata = archive.getInputStream(archive.getEntry("META-INF/notemeld-agent-sdk.json")
            ?: error("SDK AAR metadata is missing" )).bufferedReader().use { it.readText() }
        require(metadata.contains("\"sdk_version\": \"${pinned("sdk_version")}\"")) { "SDK version metadata mismatch" }
        require(metadata.contains("\"schema_version\": \"${pinned("schema_version")}\"")) { "SDK schema metadata mismatch" }
        require(metadata.contains("\"binding_version\": \"${pinned("binding_version")}\"")) { "SDK binding metadata mismatch" }
        require(metadata.contains("\"note_wire_version\": \"${pinned("note_wire_version")}\"")) { "SDK note wire metadata mismatch" }
        val abiContract = archive.getInputStream(archive.getEntry("META-INF/notemeld-agent-abi.json")
            ?: error("SDK ABI contract is missing")).bufferedReader().use { it.readText() }
        require(abiContract.contains("\"sdk_version\": \"${pinned("sdk_version")}\"")) { "SDK ABI version mismatch" }
        require(abiContract.contains("\"schema_version\": \"${pinned("schema_version")}\"")) { "SDK ABI schema mismatch" }
        require(abiContract.contains("\"note_wire_version\": \"${pinned("note_wire_version")}\"")) { "SDK ABI note wire mismatch" }
        listOf("armeabi-v7a", "arm64-v8a", "x86", "x86_64").forEach { abi ->
            require(archive.getEntry("jni/$abi/libnotemeld_agent.so") != null) { "SDK AAR is missing $abi canonical library" }
            require(archive.getEntry("jni/$abi/libnotemeld_agent_jni.so") != null) { "SDK AAR is missing $abi JNI bridge" }
        }
    }
}

val releaseKeystorePath = providers.environmentVariable("NOTEMELD_ANDROID_KEYSTORE_PATH").orNull
val releaseKeystorePassword = providers.environmentVariable("NOTEMELD_ANDROID_KEYSTORE_PASSWORD").orNull
val releaseKeyAlias = providers.environmentVariable("NOTEMELD_ANDROID_KEY_ALIAS").orNull
val releaseKeyPassword = providers.environmentVariable("NOTEMELD_ANDROID_KEY_PASSWORD").orNull
val releaseSigningReady = listOf(releaseKeystorePath, releaseKeystorePassword, releaseKeyAlias, releaseKeyPassword).all { !it.isNullOrBlank() }
val configuredBuildCommit = providers.environmentVariable("NOTEMELD_ANDROID_BUILD_COMMIT").orNull
require(configuredBuildCommit.isNullOrBlank() || Regex("^[0-9a-fA-F]{40}$").matches(configuredBuildCommit)) {
    "NOTEMELD_ANDROID_BUILD_COMMIT must be a full 40-character git commit"
}
val buildCommit = configuredBuildCommit?.lowercase() ?: "development"

android { namespace = "com.notemeld.mobile"; compileSdk = 35
    defaultConfig {
        applicationId = "com.notemeld.mobile"; minSdk = 26; targetSdk = 35
        versionCode = providers.environmentVariable("NOTEMELD_ANDROID_VERSION_CODE").orNull?.toIntOrNull() ?: 1
        versionName = providers.environmentVariable("NOTEMELD_ANDROID_VERSION_NAME").orNull ?: "1.0"
        buildConfigField("String", "BUILD_COMMIT", "\"$buildCommit\"")
        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
    }
    buildFeatures { buildConfig = true }
    compileOptions { sourceCompatibility = JavaVersion.VERSION_17; targetCompatibility = JavaVersion.VERSION_17 }
    kotlinOptions { jvmTarget = "17" }
    sourceSets { getByName("main").java.srcDir("../src/main/kotlin") }
    if (releaseSigningReady) {
        signingConfigs {
            create("release") {
                storeFile = file(requireNotNull(releaseKeystorePath))
                storePassword = releaseKeystorePassword
                keyAlias = releaseKeyAlias
                keyPassword = releaseKeyPassword
            }
        }
        buildTypes.getByName("release").signingConfig = signingConfigs.getByName("release")
    }
}

dependencies {
    if (sdkAar != null) implementation(files(sdkAar))
    implementation(project(":agent-runtime"))
    implementation(project(":ui-core"))
    implementation("org.bouncycastle:bcprov-jdk18on:1.79")
    implementation(platform("androidx.compose:compose-bom:2024.12.01"))
    implementation("androidx.activity:activity-compose:1.10.0")
    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.ui:ui-tooling-preview")
    implementation("androidx.compose.foundation:foundation")
    implementation("androidx.compose.material3:material3")
    implementation("androidx.camera:camera-camera2:1.4.1")
    implementation("androidx.camera:camera-lifecycle:1.4.1")
    implementation("androidx.camera:camera-view:1.4.1")
    implementation("androidx.lifecycle:lifecycle-runtime-compose:2.8.7")
    implementation("com.google.mlkit:barcode-scanning:17.3.0")
    testImplementation("junit:junit:4.13.2")
            debugImplementation("androidx.compose.ui:ui-tooling")
    androidTestImplementation(platform("androidx.compose:compose-bom:2024.12.01"))
    androidTestImplementation("androidx.compose.ui:ui-test-junit4")
    androidTestImplementation("androidx.test:runner:1.6.2")
    androidTestImplementation("androidx.test.ext:junit:1.2.1")
    androidTestImplementation("androidx.test.uiautomator:uiautomator:2.3.0")
    debugImplementation("androidx.compose.ui:ui-test-manifest")
}
