package me.shadow.cobalt

import com.google.gson.Gson
import com.google.gson.JsonObject

/**
 * Cobalt Wrapper — renderer configuration for ZalithLauncher2 (V2 contract).
 *
 * This file is the whole integration surface. Everything a launcher needs to
 * route Minecraft's GL calls through Cobalt is here.
 *
 * The values below are not arbitrary. Each one exists because a specific
 * mechanism in the launcher required it, and several of them were found by
 * reading the launcher's source rather than by guessing:
 *
 *  rendererId `opengles3`
 *      pojavInitOpenGL() compares POJAV_RENDERER against a fixed list. Anything
 *      unmatched falls through to br_init(), the Birch loader, which dlopens
 *      libraries this plugin does not ship — a jump to address zero. The prefix
 *      "opengles" selects the GL bridge.
 *
 *      It deliberately does NOT end in "_desktopgl". That suffix makes the
 *      bridge request eglBindAPI(EGL_OPENGL_API), which Android has no
 *      implementation for; the device answered `bind failed: 0x300c`
 *      (EGL_BAD_API) on every attempt. The translation from desktop GL happens
 *      in this layer, so an ES context is what is actually wanted.
 *
 *  rendererGLPath / rendererEGLPath
 *      Both name the same library. The launcher loads it as the EGL
 *      implementation and then resolves GL through its eglGetProcAddress, so a
 *      separate EGL shim would give one symbol two addresses. The library must
 *      exist in nativeLibraryDir or the launcher reports "Failed to load a
 *      library" and no context is ever made.
 *
 *  LIBGL_ES=3
 *      Read by the launcher's GL bridge and becomes
 *      EGL_CONTEXT_CLIENT_VERSION on eglCreateContext. Unset, it defaults to 2,
 *      and no 1.13+ Minecraft can run on an ES 2 context. Note this is NOT
 *      COBALT_ES, which nothing in the launcher reads.
 */
object CobaltConfig {

    private const val RENDERER_ID = "opengles3"
    // One library for both roles, which is what MobileGlues does
    // ("MobileGlues:libmobileglues.so:libmobileglues.so") and what the working
    // 2.0.3-fork build does. The launcher loads it as the EGL implementation
    // and then resolves every GL entry point through *its* eglGetProcAddress,
    // so a second, separate EGL library would only create a second address for
    // the same symbol -- which is the failure being fixed above.
    private const val LIB = "libcobalt.so"

    /**
     * The V2 renderer config, as the launcher's RendererConfig.kt expects it.
     *
     * `env` is where two of the load-bearing values live, and the ordering in
     * the launcher matters:
     *
     *     envMap["SDL_OPENGL_LIBRARY"] = rendererId      // <- just "opengles3"
     *     envMap += renderer.getRendererEnv().value       // <- ours merges here
     *     envMap["SDL_EGL_LIBRARY"] = "$path/$eglName"  // <- correct, set after
     *
     * SDL_GL_LoadLibrary therefore gets "opengles3" — not a path, and not a
     * library — so SDL falls back to the system GLES and resolves glGetError
     * somewhere else entirely. MC 26.3 then fails its own startup gate:
     *
     *     if (GL.getFunctionProvider().getFunctionAddress("glGetError")
     *         != SDLVideo.SDL_GL_GetProcAddress("glGetError"))
     *         throw new BackendCreationException("glGetError mismatch", ...);
     *
     * Because our env is merged after that assignment, naming the library here
     * wins. A bare filename resolves, because the launcher already puts this
     * plugin's nativeLibraryDir on LD_LIBRARY_PATH. This one value is the
     * difference between 26.3 starting and not starting.
     */
    fun rendererConfigJson(): String {
        val env = linkedMapOf(
            "LIBGL_ES" to "3",
            "SDL_OPENGL_LIBRARY" to LIB,
            "SDL_EGL_LIBRARY" to LIB,
            "SDL_VIDEO_DRIVER" to "android",
            "MG_COUNT_LAUNCH" to "1",
            "COBALT_ES" to "3",
            "COBALT_GL" to "32",
            "COBALT_DEBUG" to "0"
        )

        return Gson().toJson(
            mapOf(
                "displayName" to "Cobalt Wrapper",
                "rendererId" to RENDERER_ID,
                "rendererGLPath" to LIB,
                "rendererEGLPath" to LIB,
                "dlopenLibPaths" to emptyList<String>(),
                "minMCVer" to null,
                "maxMCVer" to null,
                "env" to env.map { (k, v) ->
                    mapOf("type" to "NormalEnv", "key" to k, "value" to v)
                }
            )
        )
    }

    /** Shown in the plugin's own activity, so the build is identifiable. */
    fun describe(): JsonObject = JsonObject().apply {
        addProperty("rendererId", RENDERER_ID)
        addProperty("library", LIB)
    }
}