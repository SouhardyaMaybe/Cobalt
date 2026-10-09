// Cobalt - dump a failing shader, and only a failing shader.
//
// 26.3's terrain shaders fail with
//
//   ERROR: 0:224: '_uniform' : undeclared identifier
//   ERROR: 0:224: '_instance_00_00' : Syntax error:  syntax error
//
// Neither identifier appears in any of Minecraft's 106 shipped shader files.
// Both come from Mojang's RenderPearl recompiler, which flattens uniforms into
// synthesised globals named "_uniform_%02d_%02d" and "_uniform_instance_%02d_%02d"
// (com/mojang/renderpearl/backend/opengl/GlPipelineRecompiler) and then
// decompiles SPIR-V back to GLSL with SPIRV-Cross. What reaches glShaderSource is
// therefore Mojang-generated text, and something between there and the driver
// separates a declaration from its use. Which something is not determinable by
// reading this source -- three hypotheses were formed and all three were
// disproved by testing.
//
// Hence this. The dump is:
//
//   - on failure only. A successful compile logs nothing, so there is no cost to
//     the common case and no startup penalty.
//   - to logcat as well as the file. The file lives in the plugin's
//     nativeLibraryDir and needs an adb pull; logcat appears in the launcher's
//     own log, which is what gets pasted into a bug report. Three runs produced
//     identical failures and no shader source, because the source was behind a
//     toggle nobody had turned on.
//   - length-capped, and the cap is stated in the log so a truncated dump is
//     visibly truncated rather than quietly incomplete.

#include "../includes.h"
#include <GL/gl.h>
#include "shader.h"
#include "../gles/loader.h"
#include <stdlib.h>

extern "C" {
void write_log(const char *format, ...);
}

// logcat truncates a single entry at 4 KB, silently. Emitting one entry per line
// would therefore lose the tail of every shader with no indication, so each
// section goes out as one capped entry and says what it dropped.
#define COBALT_DUMP_CHARS 3000

// Default on for this path: it fires once per *failing* compile, which during
// startup is about a dozen times, not per frame. CB_LOG_SHADER=0 disables it.
static bool dump_enabled() {
    static int enabled = -1;
    if (enabled < 0) {
        const char *v = getenv("CB_LOG_SHADER");
        enabled = (v != nullptr && v[0] == '0') ? 0 : 1;
    }
    return enabled == 1;
}

// Original source, keyed by shader id.
//
// shaderInfo is a single global holding only the most recent conversion, and
// glShaderSource overwrites it. Minecraft compiles a vertex shader and a
// fragment shader back to back, so by the time the fragment compile fails the
// vertex's source is gone -- and the driver reported only the fragment failing.
// A small ring keeps the last few, which is what makes the dump identify which
// shader it is showing.
#define COBALT_SRC_SLOTS 4
static std::string g_src_original[COBALT_SRC_SLOTS];
static GLuint g_src_id[COBALT_SRC_SLOTS];

static void remember_source(GLuint shader, const char *src) {
    // Hash the id to a slot. Replacement is fine: this is a diagnostic aid, not
    // a correctness structure, and a collision only means an older entry is
    // overwritten.
    unsigned slot = (unsigned)(shader % COBALT_SRC_SLOTS);
    if (g_src_id[slot] != shader) {
        g_src_original[slot].assign(src ? src : "");
        g_src_id[slot] = shader;
    } else if (src) {
        g_src_original[slot].assign(src);
    }
}

static const char *recall_source(GLuint shader) {
    unsigned slot = (unsigned)(shader % COBALT_SRC_SLOTS);
    if (g_src_id[slot] == shader) return g_src_original[slot].c_str();
    return nullptr;
}

extern "C" {

// glCompileShaderARB, because upstream's NATIVE_FUNCTION_HEAD emitted it and
// replacing the function without it silently drops a name Minecraft resolves.
//
// The GLAPI on this line is not decoration. Verified: an __attribute__((alias))
// does NOT inherit the visibility of its target. Built with
// -fvisibility=hidden and no attribute here:
//
//   $ clang++ -shared -fvisibility=hidden ...
//   $ nm -D --defined-only lib.so | grep -E 'target_a|alias_a'
//   00000000000005e0 T target_a          <- only the target survives
//
// which is exactly upstream's macro, which puts GLAPI on both:
//
//   extern "C" GLAPI GLAPIENTRY type name##ARB(__VA_ARGS__) __attribute__((alias(#name)));
//   extern "C" GLAPI GLAPIENTRY type name(__VA_ARGS__) {
//
// The first version of this file had the alias without it, and the 256-name
// audit reported glCompileShaderARB missing on all three ABIs while every other
// check passed.
GLAPI GLAPIENTRY void glCompileShaderARB(GLuint shader) __attribute__((alias("glCompileShader")));

// Replaces upstream's NATIVE_FUNCTION passthrough, which calls the driver and
// returns without learning anything. A one-line forward has nothing to preserve.
GLAPI GLAPIENTRY void glCompileShader(GLuint shader) {
    GLES.glCompileShader(shader);

    // Only on failure. The success path returns immediately, so this costs one
    // glGetShaderiv per failing compile and nothing per successful one.
    GLint ok = GL_TRUE;
    GLES.glGetShaderiv(shader, GL_COMPILE_STATUS, &ok);
    if (ok || !dump_enabled()) return;

    GLchar driver_log[1024];
    driver_log[0] = '\0';
    GLES.glGetShaderInfoLog(shader, (GLsizei)sizeof(driver_log), nullptr, driver_log);

    // shaderInfo.converted is this layer's output for the most recent
    // glShaderSource, which is the right shader: Minecraft calls
    // glShaderSource then glCompileShader for each stage in turn.
    const char *converted = (shaderInfo.id == shader) ? shaderInfo.converted.c_str() : nullptr;
    const char *original = recall_source(shader);

    __android_log_print(ANDROID_LOG_ERROR, "Cobalt",
                        "=== SHADER COMPILE FAILED id=%u === translated=%s", (unsigned)shader,
                        converted ? "yes" : "NO (translation returned nothing)");
    __android_log_print(ANDROID_LOG_ERROR, "Cobalt", "--- driver info log ---\n%s",
                        driver_log[0] ? driver_log : "(empty)");

    __android_log_print(ANDROID_LOG_ERROR, "Cobalt", "--- ORIGINAL from Minecraft: %d chars, first %d ---%s",
                        original ? (int)strlen(original) : 0, original ? COBALT_DUMP_CHARS : 0,
                        (original && strlen(original) > COBALT_DUMP_CHARS) ? " [TRUNCATED]" : "");
    __android_log_print(ANDROID_LOG_ERROR, "Cobalt", "%s", original ? original : "(not retained)");

    __android_log_print(ANDROID_LOG_ERROR, "Cobalt",
                        "--- TRANSLATED by Cobalt: %d chars, first %d ---%s",
                        converted ? (int)strlen(converted) : 0, converted ? COBALT_DUMP_CHARS : 0,
                        (converted && strlen(converted) > COBALT_DUMP_CHARS) ? " [TRUNCATED]" : "");
    __android_log_print(ANDROID_LOG_ERROR, "Cobalt", "%s", converted ? converted : "(none)");
    __android_log_print(ANDROID_LOG_ERROR, "Cobalt", "=== END SHADER DUMP ===");

    write_log("=== SHADER COMPILE FAILED id=%u translated=%s", (unsigned)shader, converted ? "yes" : "NO");
    write_log("--- driver info log ---\n%s", driver_log[0] ? driver_log : "(empty)");
    write_log("--- ORIGINAL ---\n%s", original ? original : "(not retained)");
    write_log("--- TRANSLATED ---\n%s", converted ? converted : "(none)");
    write_log("=== END SHADER DUMP ===");
}

// Called from glShaderSource so the original is captured before translation
// overwrites shaderInfo.
void cobalt_remember_shader_source(GLuint shader, const char *src) { remember_source(shader, src); }

} // extern "C"