plugins {
    id("com.android.library")
    kotlin("android")
}

group = "wiki.notemeld.agent"
version = "0.1.0"

android {
    namespace = "wiki.notemeld.agent"
    compileSdk = 35
    defaultConfig {
        minSdk = 24
        externalNativeBuild.cmake.arguments += "-DNOTEMELD_AGENT_LIBRARY_DIR=${providers.environmentVariable("NOTEMELD_AGENT_LIBRARY_DIR").orNull ?: ""}"
    }
    externalNativeBuild.cmake.path = file("src/main/cpp/CMakeLists.txt")
    buildFeatures.prefab = true
}
