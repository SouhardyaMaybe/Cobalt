// Single-module project. The plugin is a shell around a native library, so
// there is nothing to share between modules and no reason for a multi-module
// layout.
import org.gradle.api.initialization.resolve.RepositoriesMode

pluginManagement {
    repositories {
        // Order matters: gradlePluginPortal() resolves the plugin marker, but
        // AGP itself lives in Google's Maven. With only the portal declared,
        // resolution fails with "could not resolve plugin artifact" -- which
        // reads like a version problem and is not one.
        google()
        gradlePluginPortal()
        mavenCentral()
    }
}

dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        google()
        mavenCentral()
    }
}

rootProject.name = "cobalt-wrapper"