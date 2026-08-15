pluginManagement {
    repositories { google(); mavenCentral(); gradlePluginPortal() }
    plugins {
        id("com.android.library") version "8.7.3"
        kotlin("android") version "2.0.21"
    }
}
rootProject.name = "notemeld-agent-sdk"
