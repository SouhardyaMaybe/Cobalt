package me.shadow.cobalt

import android.content.Context
import java.io.File

/**
 * Installs the renderer's own settings file next to libcobalt.so.
 *
 * The renderer reads CB_DIR_PATH/config.json from nativeLibraryDir/cobalt at startup.
 * Until it is there, config_refresh() fails and the renderer falls back to defaults --
 * silently, because config_get_int() answers -1 for a key it cannot read and
 * init_settings() reads -1 as "the config did not say". The device log showed only:
 *
 *     Failed to load config. Use default config.
 *     [Cobalt] Setting: maxGlslCacheSize            = 0
 *
 * and the visible cost was a disabled shader cache, which also disables the negative
 * shader cache: a shader that fails to compile is retried on every resource reload,
 * and Minecraft reloads resources on every dimension change.
 *
 * Why it is not shipped inside the APK under lib/. AGP packs jniLibs by extension --
 * only .so files survive -- so a config.json staged there is dropped without a
 * warning. It goes in assets/ instead, which is packaged verbatim, and is copied out
 * here on first launch. nativeLibraryDir/cobalt is inside the app sandbox and needs
 * no permission.
 *
 * Written on every launch rather than only when missing, so a settings change in a
 * later build reaches an already-installed plugin -- which matters here, because the
 * signing key is generated per build and reinstalling requires an uninstall anyway,
 * but "first launch" would otherwise freeze whatever version arrived first.
 */
object CobaltSettings {

    /** Matches CB_DIR_PATH in plugin/config/cobalt-renderer.json. */
    private const val DIR = "cobalt"
    private const val FILE = "config.json"
    private const val ASSET = "cobalt-settings.json"

    /**
     * Copy the asset to nativeLibraryDir/cobalt/config.json.
     *
     * Returns the file on success, or null with the reason already appended to [report]
     * when it could not be written. Never throws: this runs from onCreate, and a crash
     * here would replace "the renderer uses defaults" with "the plugin app will not
     * open", which is a worse problem for the same underlying cause.
     */
    fun install(context: Context, report: StringBuilder): File? {
        val target = File(context.applicationInfo.nativeLibraryDir, "$DIR/$FILE")
        return try {
            context.assets.open(ASSET).use { input -> copyAtomically(input, target) }
        } catch (e: Exception) {
            report.appendLine("  FAILED to install $FILE: ${e.javaClass.simpleName}: ${e.message}")
            null
        } ?: run {
            report.appendLine("  FAILED to install $FILE (rename failed)")
            null
        }
    }

    /**
     * Write [input] to [target] through a temporary file and a rename, creating the
     * parent directory. Returns the target, or null if the rename did not take.
     *
     * Split out from install() and free of Android types so tools/test-settings-install
     * can run it directly. The rename is the point: an interrupted copy must not be able
     * to leave a truncated config.json behind, because a partial JSON file is the one
     * outcome worse than no file at all -- config_refresh() fails to parse it rather than
     * failing to find it, and the renderer reports neither.
     *
     * Overwrites unconditionally. "Only if missing" would freeze whatever version of the
     * settings arrived first, and the signing key is generated per build so a reinstall
     * already requires an uninstall -- meaning "first launch" would very often be years
     * after the file was written.
     */
    @Throws(java.io.IOException::class)
    fun copyAtomically(input: java.io.InputStream, target: File): File? {
        target.parentFile?.mkdirs()
        val tmp = File(target.parentFile, target.name + ".tmp")
        try {
            tmp.outputStream().use { output -> input.copyTo(output) }
            if (!tmp.renameTo(target)) {
                tmp.delete()
                return null
            }
        } catch (e: Exception) {
            tmp.delete()
            throw e
        }
        return target
    }

    /** Reports what is installed, so a failure here is visible without a log dump. */
    fun describe(context: Context, target: File?) {
        val t = target ?: File(context.applicationInfo.nativeLibraryDir, "$DIR/$FILE")
        if (t.isFile) {
            val bytes = t.length()
            println("Cobalt settings installed: $t ($bytes bytes)")
        } else {
            println("Cobalt settings MISSING: $t")
        }
    }
}