package me.shadow.cobalt

import android.content.res.Resources
import com.google.gson.JsonObject
import com.google.gson.JsonParser

/**
 * Cobalt's launcher-facing configuration.
 *
 * There is one source of truth for this and it is not this file:
 * plugin/config/cobalt-renderer.json. The launcher reads the renderer config
 * from an Android string resource, so it has to be baked into the APK, which
 * makes a hand-written Kotlin constant a second copy waiting to drift. This
 * reads the shipped resource back instead, so the file a maintainer edits and
 * the bytes the launcher parses cannot disagree.
 *
 * Every value in that JSON is traceable to something the launcher does. The
 * notes below are the reasoning, because the obvious choices are wrong:
 *
 *  rendererId `opengles3`
 *      pojavInitOpenGL() compares POJAV_RENDERER against a fixed list, and
 *      anything unmatched falls through to br_init(), the Birch loader, which
 *      dlopens libraries this plugin does not ship. On the device that jump
 *      landed at address zero: SIGSEGV, pc=0x0.
 *
 *      The "opengles" prefix is not cosmetic. jni/sdl_hook.c's
 *      sdlGlesCompatEnabled() reads POJAV_RENDERER first and returns true for
 *      any id starting with "opengles", which is what forces the ES profile on
 *      SDL's window and context creation. An id outside that prefix falls
 *      through to isMobileGluesEgl(), which compares the EGL library's basename
 *      against the literal "libmobileglues.so" -- and this library is named
 *      libcobalt.so, so that test would fail and the ES compat layer would be
 *      off. The id is load-bearing twice over, for two different mechanisms.
 *
 *      It must NOT end in "_desktopgl". That suffix makes the bridge request
 *      eglBindAPI(EGL_OPENGL_API); Android has no implementation for it, and
 *      every attempt on the device answered `bind failed: 0x300c`
 *      (EGL_BAD_API). The desktop-to-ES translation happens inside this
 *      renderer, so an ES context is what is actually wanted.
 *
 *  rendererGLPath / rendererEGLPath, both `**|libcobalt.so`
 *      The `**|` prefix is replaced by the plugin's real nativeLibraryDir when
 *      the launcher parses the config (RendererConfig.resolveNativePaths).
 *
 *      The absolute path is required, not a convenience. The launcher's
 *      LD_LIBRARY_PATH is built by getLibraryPath(), which includes
 *      RendererPluginManager.selectedRendererPlugin -- the *V1* plugin list.
 *      A V2 plugin lives in RendererV2PluginManager's list, so that lookup
 *      returns null and the plugin's lib directory is never added. A bare
 *      filename would therefore fail to dlopen.
 *
 *      Both name the same library on purpose. The launcher loads it as the EGL
 *      implementation and then resolves GL through *that* library's
 *      eglGetProcAddress. Two libraries would give one GL symbol two addresses,
 *      which is the failure Minecraft 26.3 refuses to start on.
 *
 *  SDL_OPENGL_LIBRARY
 *      This is the one value that overrides a launcher default rather than
 *      working around a gap. In setRendererEnv():
 *
 *          envMap["SDL_OPENGL_LIBRARY"] = rendererId   // "opengles3", not a path
 *          ...
 *          envMap += renderer.getRendererEnv().value    // ours merges HERE
 *
 *      SDL_GL_LoadLibrary is handed "opengles3" -- not a path, not a library --
 *      so SDL falls back to the system GLES and resolves glGetError somewhere
 *      else. Minecraft 26.3 then fails its own startup gate:
 *
 *          if (FunctionProvider.getFunctionAddress("glGetError")
 *                  != SDLVideo.SDL_GL_GetProcAddress("glGetError"))
 *              throw new BackendCreationException("glGetError mismatch", ...);
 *
 *      Because our env is merged after that assignment, naming the library here
 *      wins.
 *
 *  LIBGL_ES=3
 *      Read by the launcher's GL bridge and turned into
 *      EGL_CONTEXT_CLIENT_VERSION on eglCreateContext. Unset it defaults to 2,
 *      and no 1.13+ Minecraft runs on an ES 2 context. Note this is LIBGL_ES,
 *      not CB_ES -- nothing in the launcher reads the latter.
 */
object CobaltConfig {

    /** The renderer library. Renamed from libmobileglues.so by tools/rebrand.py. */
    const val LIBRARY = "libcobalt.so"

    /**
     * Where the renderer puts its config, log and shader cache.
     *
     * Deliberately the plugin's own nativeLibraryDir rather than the
     * /sdcard/Cobalt default: the app sandbox means the plugin can always write
     * there, whereas /sdcard needs a runtime permission the plugin cannot
     * request on the launcher's behalf. CB_DIR_PATH overrides the default.
     */
    const val CONFIG_DIR = "**|cobalt"

    /** Read the config the launcher will also read, so there is one copy. */
    fun configJson(res: Resources): String =
        res.getString(R.string.cobalt_renderer_config)

    /** For the plugin's own activity. Shows what is actually installed. */
    fun describe(res: Resources): JsonObject {
        val o = JsonObject()
        try {
            val parsed = JsonParser.parseString(configJson(res)).asJsonObject
            o.add("renderer", parsed)
        } catch (t: Throwable) {
            // A malformed config is a build error, and the launcher's own parse
            // is wrapped in runCatching and skips the plugin silently. Showing
            // the failure here is the only place it becomes visible.
            o.addProperty("error", "config is not valid JSON: ${t.message}")
        }
        return o
    }
}