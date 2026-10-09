// Cobalt Wrapper -- the launcher-facing plugin.
//
// This module is a shell. It carries no rendering code: the renderer is
// libcobalt.so, built from ref/mobileglues and staged into jniLibs by
// build-android.sh before this module runs. The plugin exists only to tell the
// launcher where that library is and how to configure it.
plugins {
    id("com.android.application") version "8.5.2"
}

android {
    namespace = "me.shadow.cobalt"
    compileSdk = 34

    defaultConfig {
        applicationId = "me.shadow.cobalt"
        minSdk = 21
        targetSdk = 34
        versionCode = 1
        versionName = "0.1.0"

        // The renderer .so is staged into jniLibs by build-android.sh, not by
        // Gradle, so a missing renderer still produces an APK -- and the
        // launcher then lists a plugin it cannot load. The renderer build is the
        // step that must fail; see the ABI audit in the workflow.
        ndk {
            abiFilters += listOf("arm64-v8a", "armeabi-v7a", "x86_64")
        }
    }

    buildTypes {
        release {
            isMinifyEnabled = false
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    sourceSets {
        getByName("main") {
            res.srcDir("build/generated/res")
        }
    }
}

dependencies {
    implementation("com.google.code.gson:gson:2.11.0")
}