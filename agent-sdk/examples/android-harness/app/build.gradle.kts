plugins { id("com.android.application"); kotlin("android") }

android {
    namespace = "wiki.notemeld.agent.harness"
    compileSdk = 35
    defaultConfig {
        applicationId = "wiki.notemeld.agent.harness"; minSdk = 24; targetSdk = 35
        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
    }
}
dependencies {
    implementation(project(":notemeld-agent-sdk"))
    androidTestImplementation("androidx.test.ext:junit:1.2.1")
    androidTestImplementation("androidx.test:runner:1.6.2")
}
