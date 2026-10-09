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

// The three channels, and why all three.
//
// LOG_V does __android_log_print, printf and write_log. Only printf is visible
// in the launcher's log, and that is the channel this dump needs.
//
// Established from a device log: during "DLOPEN Renderer" the renderer's stdout
// appears in the launcher's output verbatim --
//
//   [Cobalt] Setting: enableAngle                 = false
//   [Cobalt] multidrawOrderElements               = indirect > unroll
//   EGL initialized successfully
//
// The first two are LOG_V, so LOG_V's printf reaches the user. A dump that used
// only __android_log_print and write_log produced nothing in four runs for
// exactly this reason: logcat is not in the launcher's log view, and the file
// needs an adb pull. The dump was working; it was writing to two places nobody
// was looking at.
//
// printf is emitted in chunks because the launcher's log view truncates very
// long lines -- a shader is thousands of characters and would arrive as one
// silently shortened line. 900 characters is comfortably under that and still
// needs few enough chunks to stay readable.
static void emit(const char *tag, const char *text) {
    if (text == nullptr) return;
    printf("[Cobalt] %s: %s\n", tag, text);
    __android_log_print(ANDROID_LOG_ERROR, RENDERERNAME, "%s: %s", tag, text);
    write_log("%s: %s", tag, text);
}

// Emits a labelled source in chunks, stating what was dropped.
static void emit_source(const char *label, const char *src) {
    if (src == nullptr || *src == '\0') {
        emit(label, "(absent)");
        return;
    }
    size_t total = strlen(src);
    size_t off = 0;
    unsigned part = 1;
    while (off < total) {
        size_t n = total - off < 900 ? total - off : 900;
        char chunk[901];
        memcpy(chunk, src + off, n);
        chunk[n] = '\0';
        char label_buf[128];
        snprintf(label_buf, sizeof(label_buf), "%s part %u/%s", label, part,
                 (off + n >= total) ? "last" : "...");
        emit(label_buf, chunk);
        off += n;
        part++;
    }
    char note[192];
    snprintf(note, sizeof(note), "%s: %d chars, emitted in %u part(s)", label, (int)total, part - 1);
    emit("SHADER DUMP SUMMARY", note);
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

    char header[256];
    snprintf(header, sizeof(header), "=== SHADER COMPILE FAILED id=%u translated=%s ===",
             (unsigned)shader, converted ? "yes" : "NO, translation returned nothing");
    emit("SHADER DUMP", header);

    emit("DRIVER INFO LOG", driver_log[0] ? driver_log : "(empty)");
    emit_source("SOURCE AS MINECRAFT SUPPLIED IT", original);
    emit_source("SOURCE AFTER COBALT TRANSLATION", converted);

    emit("SHADER DUMP", "=== END ===");
}

// Called from glShaderSource so the original is captured before translation
// overwrites shaderInfo.
void cobalt_remember_shader_source(GLuint shader, const char *src) { remember_source(shader, src); }

} // extern "C"