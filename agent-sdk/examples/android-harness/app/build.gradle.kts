plugins { id("com.android.application"); kotlin("android") }

android {
    namespace = "wiki.notemeld.agent.harness"
    compileSdk = 35
    defaultConfig { applicationId = "wiki.notemeld.agent.harness"; minSdk = 24; targetSdk = 35 }
}
dependencies { implementation(project(":notemeld-agent-sdk")) }
