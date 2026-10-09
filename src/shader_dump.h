// Cobalt - interface to the shader failure dumper.
//
// The dumper lives in shader_dump.cpp because it replaces glCompileShader, which
// upstream declares in gl/gl_native.cpp. This header exists so glShaderSource can
// hand it the unmodified source without pulling in the whole dumper.

#ifndef COBALT_SHADER_DUMP_H
#define COBALT_SHADER_DUMP_H

#include <GL/gl.h>

#ifdef __cplusplus
extern "C" {
#endif

// Records the source as Minecraft supplied it, before translation overwrites the
// single global shaderInfo.
//
// Called from glShaderSource. Without it the dump can show the wrong shader:
// Minecraft compiles a vertex and a fragment shader back to back, and only the
// fragment fails, so the most recent conversion by the time of the failure is
// not the one that failed.
void cobalt_remember_shader_source(GLuint shader, const char *src);

#ifdef __cplusplus
}
#endif

#endif // COBALT_SHADER_DUMP_H