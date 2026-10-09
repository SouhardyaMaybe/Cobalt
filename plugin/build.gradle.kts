// Cobalt Wrapper -- the launcher-facing plugin.
//
// This module is a shell. It carries no rendering code: the renderer is
// libcobalt.so, built from ref/mobileglues and staged into jniLibs by
// build-android.sh before this module runs. The plugin exists only to tell the
// launcher where that library is and how to configure it.
plugins {
    id("com.android.application") version "8.5.2"
}

// The version is read from the repository's VERSION file rather than written here,
// because a version stated in two places is a version that is wrong in one of them.
// It was hardcoded at 0.1.0 and stayed there for six releases: the APK's own
// "App info" screen said 0.1.0 for v0.3.2, and nothing in CI could see it, because
// the build genuinely produced the artifact it was asked for.
//
// Reading the file is also what keeps the plugin's version from drifting away from
// the git tag, which is the name the release is published under. tools/check-env.py
// asserts the two agree.
val cobaltVersion: String = rootProject.file("VERSION")
    .readText()
    .trim()
    .removePrefix("v")

require(Regex("""^\d+\.\d+\.\d+([-+.][0-9A-Za-z.+-]+)?$""").matches(cobaltVersion)) {
    "VERSION contains '$cobaltVersion', which is not a version"
}

android {
    namespace = "me.shadow.cobalt"
    compileSdk = 34

    defaultConfig {
        applicationId = "me.shadow.cobalt"
        minSdk = 21
        targetSdk = 34
        // Monotonic with the version, so the two cannot disagree about ordering.
        // Build-time versionCode -- the default -- would leave it at 1 forever, and
        // Android then refuses to install over an existing build as a downgrade.
        // Since each CI run signs with a fresh key an install always needs an
        // uninstall first anyway, but that is a property of the key, not a licence
        // for the version to stop moving.
        versionCode = cobaltVersion.split("-").first().split("+").first()
            .split(".").map { it.toInt() }
            .let { (major, minor, patch) -> major * 10000 + minor * 100 + patch }
        versionName = cobaltVersion

        // The renderer .so is staged into jniLibs by build-android.sh, not by
        // Gradle, so a missing renderer still produces an APK -- and the
        // launcher then lists a plugin it cannot load. The renderer build is the
        // step that must fail; see the ABI audit in the workflow.
        ndk {
            abiFilters += listOf("arm64-v8a", "armeabi-v7a", "x86_64")
        }
    }

    signingConfigs {
        // A debug-signed release, deliberately.
        //
        // An unsigned APK cannot be installed, and the launcher discovers
        // renderer plugins by querying installed packages -- so an unsigned
        // artifact is not a degraded build, it is an untestable one. There is
        // no release key for this project and no user to hold one.
        //
        // The consequence is stated rather than hidden: Android will refuse to
        // update an existing install signed with a different key, and this key
        // is generated per build, so every CI run produces a different
        // signature. Reinstalling means uninstalling first. A real release key
        // belongs in a secret store, not in a repository, and that is a
        // decision to make when there is a distribution to protect.
        create("release") {
            storeFile = file(System.getProperty("cobalt.storeFile") ?: "cobalt-debug.jks")
            storePassword = System.getProperty("cobalt.storePassword") ?: "cobalt"
            keyAlias = System.getProperty("cobalt.keyAlias") ?: "cobalt"
            keyPassword = System.getProperty("cobalt.keyPassword") ?: "cobalt"
        }
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            signingConfig = signingConfigs.getByName("release")
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    sourceSets {
        getByName("main") {
            // Deliberately outside build/. AGP owns build/generated/res as its
            // own output, so a generator writing there collides with
            // mergeResources and the build fails with an undeclared-task-
            // dependency error rather than anything mentioning the generator.
            res.srcDir("generated/res")
        }
    }
}

dependencies {
    implementation("com.google.code.gson:gson:2.11.0")
}