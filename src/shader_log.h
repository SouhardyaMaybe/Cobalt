// Cobalt - shader source logging.
//
// The first successful device run translated Minecraft 26.3's terrain shaders
// into something the ES driver rejected:
//
//   ERROR: 0:224: '_uniform' : undeclared identifier
//   ERROR: 0:224: '_instance_00_00' : Syntax error:  syntax error
//
// Neither identifier exists in desktop GLSL, so the translation is producing
// text that was never in the source. There is no way to tell what from the
// outside, because the source and the converted source are both logged through
// LOG_D, and LOG_D is compiled out:
//
//   gl/log.h:  #define GLOBAL_DEBUG 0
//   #define LOG_D(...)  if (DEBUG || GLOBAL_DEBUG) { ... }
//
// DEBUG is 0 and GLOBAL_DEBUG is 0, so the branch is dead in a release build.
// There is no log file, no printf, no android_log -- the converted shader was
// never written anywhere. latest.log contains none of it.
//
// This adds one logging channel, gated at runtime rather than at compile time.
//
// Runtime, not compile time, because the whole point is to iterate on the
// translation without rebuilding a 6 MB APK per attempt. CB_LOG_SHADER=1 turns
// it on; the plugin exposes that as a user-editable setting so the switch can
// be flipped from the launcher without reinstalling.
//
// Not the existing LOG_D. That is per-call -- every glClear, every glBindTexture
// -- and enabling it would produce hundreds of megabytes and slow startup enough
// to look like a hang. Only the two shader dumps are gated, which is kilobytes.

#include "../includes.h"
#include <stdlib.h>

#ifndef COBALT_SHADER_LOG
#define COBALT_SHADER_LOG 1
#endif

extern "C" {
// Declared in gl/cobalt.h, next to write_log.
void write_log(const char *format, ...);
void write_log_n(const char *format, ...);
}

// Read once. getenv on every shader compile would be wasteful and, more
// importantly, this is meant to be stable for the life of the process: a
// half-logged translation run is harder to read than a consistent one.
static bool shader_log_enabled() {
    static int enabled = -1;
    if (enabled < 0) {
        const char *v = getenv("CB_LOG_SHADER");
        enabled = (v != nullptr && v[0] == '1') ? 1 : 0;
    }
    return enabled == 1;
}

// LOG_SHADERS, not LOG_D: LOG_D is dead in a release build by construction.
//
// write_log_n is the no-trailing-newline variant. Shader sources run to
// hundreds of lines, and write_log appends "\n" after every call -- harmless
// for a one-line message, but it interleaves the source with the next dump's
// header and makes both harder to read. Here the source is written verbatim and
// the separators are explicit.
#define LOG_SHADERS(...)                                                                                               \
    if (COBALT_SHADER_LOG && shader_log_enabled()) {                                                                  \
        printf(__VA_ARGS__);                                                                                          \
        write_log(__VA_ARGS__);                                                                                       \
    }

#define LOG_SHADERS_N(...)                                                                                             \
    if (COBALT_SHADER_LOG && shader_log_enabled()) {                                                                  \
        printf(__VA_ARGS__);                                                                                          \
        write_log_n(__VA_ARGS__);                                                                                     \
    }