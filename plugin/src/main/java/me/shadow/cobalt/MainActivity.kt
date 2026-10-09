package me.shadow.cobalt

import android.app.Activity
import android.os.Bundle
import android.widget.TextView

/**
 * The plugin's only activity, and the only reason it exists: the launcher finds
 * renderer plugins with queryIntentActivities(Intent(ACTION_MAIN)), so without
 * an ACTION_MAIN activity this APK is invisible to it. The launcher never
 * launches this activity -- it reads the manifest metadata and the native
 * library beside it.
 *
 * What this does do is fail loudly. Every failure mode in this integration is
 * silent by construction: a plugin whose library failed to stage, or whose
 * config failed to parse, is skipped in silence by the launcher, and the
 * evidence is a log line in an app the user is not looking at. Showing what was
 * installed makes those cases diagnosable without a log dump.
 */
class MainActivity : Activity() {

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        val libDir = applicationInfo.nativeLibraryDir
        // Written before the report is built, so a settings failure is shown here
        // rather than discovered later as the renderer silently using defaults.
        val settingsNotes = StringBuilder()
        val settings = CobaltSettings.install(this, settingsNotes)
        CobaltSettings.describe(this, settings)

        val report = buildString {
            appendLine("Cobalt Wrapper")
            appendLine()
            appendLine(CobaltConfig.describe(resources).toString())
            appendLine()
            appendLine("Libraries in $libDir")
            for (abi in listOf("arm64-v8a", "armeabi-v7a", "x86_64")) {
                val f = java.io.File("$libDir/$abi/${CobaltConfig.LIBRARY}")
                appendLine("  %-12s %s".format(abi, if (f.isFile) "present" else "MISSING"))
            }
            appendLine()
            appendLine("Config and logs")
            appendLine("  ${java.io.File(libDir, "cobalt")}")
            append(settingsNotes)
            appendLine("  %-12s %s".format(
                "config.json",
                if (settings != null) "installed (${settings.length()} bytes)" else "MISSING",
            ))
            appendLine()
            appendLine("A MISSING library means the renderer build did not stage it.")
            appendLine("The launcher will still list this plugin, then fail to load at")
            appendLine("launch. See .github/workflows/build.yml, 'Audit the exported ABI'.")
            appendLine()
            appendLine("A MISSING config.json means the renderer falls back to defaults:")
            appendLine("maxGlslCacheSize becomes 0 and the shader cache is disabled.")
        }

        setContentView(TextView(this).apply { text = report })
    }
}