Cobalt Wrapper v0.1.0

A GL-to-GLES renderer for Minecraft: Java Edition on Android. Installs into
ZalithLauncher2 as a renderer plugin; there is no app to launch.

Supports Minecraft 1.13.2 through 26.3. The renderer exports all 256 GL symbols
those versions resolve, on arm64-v8a, armeabi-v7a and x86_64, and the build
fails if that set changes in either direction.

Install the APK, then pick "Cobalt Wrapper" in the launcher's renderer list. If
it is not in the list, the launcher cannot see the package — open the plugin's
activity to see what it actually installed.

Signed with a generated debug key, so installing over a previous build requires
uninstalling first: Android refuses to replace an install signed with a
different key.

Logs, config and shader cache are written to the plugin's own nativeLibraryDir,
inside the app sandbox. `latest.log` is the one to read.