// Cobalt - ARB/EXT entry points Minecraft resolves but the renderer lacks.
//
// Added to the build by build-android.sh, which copies this into the renderer's
// gl/ directory. CMakeLists.txt lists it by name, so the two cannot drift
// unnoticed: a source file not in the list compiles cleanly and exports nothing.
//
// Measured, not assumed. The built library exports 4907 names; the union of
// every GL symbol Minecraft 1.13.2 through 26.3 resolves is 256
// (research-mcgl/union_symbols.json). Thirty of the 256 are absent.
//
// Twenty of the thirty are missing a spelling, not a function:
//
//   Upstream emits a name##ARB alias from exactly one place -- the
//   NATIVE_FUNCTION_HEAD macro in gles/loader.h -- so only functions it wraps
//   get one. Everything hand-written has none: glActiveTexture in texture.cpp,
//   the STUB_FUNCTION_ entries in gl_stub.cpp, the state-tracking functions in
//   buffer.cpp, framebuffer.cpp, program.cpp, shader.cpp and drawing.cpp.
//
// That is not cosmetic. LWJGL resolves each name by string and calls through
// whatever pointer comes back, so a name that resolves to null is an
// UnsatisfiedLinkError at class-init, not a silently ignored call. 1.13.2 needs
// 33 suffixed names and cannot start without them.
//
// These are forwarders rather than __attribute__((alias)). An alias gives one
// address, which is what Minecraft 26.3's glGetError check needs, but GCC
// requires the aliased symbol to be visible in the same translation unit -- and
// these twenty are defined across eight files. A forwarder is one file, and
// the extra indirection is one unconditional branch on a call that costs
// microseconds to be worth optimising.
//
// glGetError is deliberately not touched: it is exported exactly once already,
// and 26.3 compares its address across dlsym, eglGetProcAddress and
// SDL_GL_GetProcAddress. Adding a second entry point for it would be the one
// change here that could cause the failure this file exists to fix.

#include "../includes.h"
#include <GL/gl.h>
#include "glcorearb.h"
#include "log.h"
#include "../gles/loader.h"

// extern "C" is load-bearing, not decoration. These are looked up by dlsym,
// eglGetProcAddress and SDL_GL_GetProcAddress, which match unmangled names by
// string. Compiled as C++ without this, a definition of glActiveTextureARB
// exports as _Z18glActiveTextureARBj and every lookup returns null -- which
// looks exactly like the original bug, and did: the file compiled cleanly,
// CMake reported "Built target cobalt", and the audit found 29 of the 30 names
// still missing.
extern "C" {

// --- Buffers: GL_ARB_vertex_buffer_object, 1999. ------------------------------
void glGenBuffersARB(GLsizei n, GLuint *buffers) { glGenBuffers(n, buffers); }
void glDeleteBuffersARB(GLsizei n, const GLuint *buffers) { glDeleteBuffers(n, buffers); }

// --- Shaders and programs: GL_ARB_shader_objects, 2002. -----------------------
void glShaderSourceARB(GLuint shader, GLsizei count, const GLchar *const *string, const GLint *length) {
    glShaderSource(shader, count, string, length);
}
void glLinkProgramARB(GLuint program) { glLinkProgram(program); }
void glUniform1iARB(GLint location, GLint v0) { glUniform1i(location, v0); }

// --- Texture units. ------------------------------------------------------------
// glActiveTexture is hand-written in texture.cpp and validates the unit against
// MAX_TEXTURE_IMAGE_UNITS, so this is not a no-op: 1.13.2 goes through the ARB
// name on its hot path and skipping the layer would skip the validation.
void glActiveTextureARB(GLenum texture) { glActiveTexture(texture); }

// --- Framebuffers and renderbuffers: GL_EXT_framebuffer_object, 2005. ---------
// GL 3.0 renamed every one of these to the unsuffixed form, so on any device
// that can run 1.17+ the target always exists.
void glBindFramebufferEXT(GLenum target, GLuint framebuffer) { glBindFramebuffer(target, framebuffer); }
void glGenFramebuffersEXT(GLsizei n, GLuint *framebuffers) { glGenFramebuffers(n, framebuffers); }
void glDeleteFramebuffersEXT(GLsizei n, const GLuint *names) { glDeleteFramebuffers(n, names); }
GLenum glCheckFramebufferStatusEXT(GLenum target) { return glCheckFramebufferStatus(target); }
void glFramebufferTexture2DEXT(GLenum target, GLenum attachment, GLenum textarget, GLuint texture, GLint level) {
    glFramebufferTexture2D(target, attachment, textarget, texture, level);
}
void glFramebufferRenderbufferEXT(GLenum target, GLenum attachment, GLenum renderbuffertarget, GLuint renderbuffer) {
    glFramebufferRenderbuffer(target, attachment, renderbuffertarget, renderbuffer);
}
void glBlitFramebufferEXT(GLint srcX0, GLint srcY0, GLint srcX1, GLint srcY1, GLint dstX0, GLint dstY0, GLint dstX1,
                          GLint dstY1, GLbitfield mask, GLenum filter) {
    glBlitFramebuffer(srcX0, srcY0, srcX1, srcY1, dstX0, dstY0, dstX1, dstY1, mask, filter);
}
void glBindRenderbufferEXT(GLenum target, GLuint renderbuffer) { glBindRenderbuffer(target, renderbuffer); }
void glGenRenderbuffersEXT(GLsizei n, GLuint *renderbuffers) { glGenRenderbuffers(n, renderbuffers); }
void glDeleteRenderbuffersEXT(GLsizei n, const GLuint *renderbuffers) {
    glDeleteRenderbuffers(n, renderbuffers);
}
void glRenderbufferStorageEXT(GLenum target, GLenum internalformat, GLsizei width, GLsizei height) {
    glRenderbufferStorage(target, internalformat, width, height);
}
void glBlendFuncSeparateEXT(GLenum sfactorRGB, GLenum dfactorRGB, GLenum sfactorAlpha, GLenum dfactorAlpha) {
    glBlendFuncSeparate(sfactorRGB, dfactorRGB, sfactorAlpha, dfactorAlpha);
}

// --- Names with no modern counterpart in the headers. -------------------------
//
// These are the ones where a forwarder is not a rename. Each existed in an
// older GL or ARB extension, was never carried into ES 3, and so has no
// unsuffixed spelling to alias. They are defined here rather than assumed
// unnecessary: the extraction that produced union_symbols.json reads GL names
// out of LWJGL's constant pools, which is a string scan and not a symbol
// resolution, so these may include entries no version actually calls. Exporting
// a correct forwarder for one that is never called costs a few dozen bytes;
// omitting one that is called is a startup crash.

// glGetProgrami / glGetShaderi were the GL 1.2-era spellings, replaced by
// glGetProgramiv / glGetShaderiv in GL 2.0. Same query, integer result.
void glGetProgrami(GLuint program, GLenum pname, GLint *params) { glGetProgramiv(program, pname, params); }
void glGetShaderi(GLuint shader, GLenum pname, GLint *params) { glGetShaderiv(shader, pname, params); }

// glGetObjectParameteriARB predates the program/shader split. GL never had an
// unsuffixed glGetObjectParameteri, only the iv form, so there is nothing to
// alias.
//
// pname decides which of the two modern queries was meant: LINK_STATUS and
// VALIDATE_STATUS are program-only, COMPILE_STATUS and SHADER_TYPE are
// shader-only. An unrecognised pname is tried on both -- it raises
// GL_INVALID_ENUM on the wrong one, and the value the caller asked for comes
// back from the right one.
void glGetObjectParameteriARB(GLuint obj, GLenum pname, GLint *params) {
    if (pname == GL_LINK_STATUS || pname == GL_VALIDATE_STATUS || pname == GL_INFO_LOG_LENGTH) {
        glGetProgramiv(obj, pname, params);
    } else if (pname == GL_COMPILE_STATUS || pname == GL_SHADER_TYPE || pname == GL_SHADER_SOURCE_LENGTH) {
        glGetShaderiv(obj, pname, params);
    } else {
        glGetProgramiv(obj, pname, params);
        if (glGetError() == GL_INVALID_ENUM) {
            while (glGetError() != GL_NO_ERROR) {
            }
            glGetShaderiv(obj, pname, params);
        }
    }
}

// glGetFramebufferAttachmentParameteri is the GL 3.0 name for the query whose
// unsuffixed form takes a GLint; the EXT form is the 2005 spelling. 1.16.5
// resolves the EXT one, so both are provided.
void glGetFramebufferAttachmentParameteri(GLenum target, GLenum attachment, GLenum pname, GLint *params) {
    glGetFramebufferAttachmentParameteriv(target, attachment, pname, params);
}
void glGetFramebufferAttachmentParameteriEXT(GLenum target, GLenum attachment, GLenum pname, GLint *params) {
    glGetFramebufferAttachmentParameteriv(target, attachment, pname, params);
}

// The glGetQueryObjecti family was removed in GL 3.0 in favour of the _iv and
// _ui64v forms, which the renderer exports. The integer result is the same
// value, only written through a different pointer type.
//
// The 64-bit forms go through GLES rather than the layer's own glGetQueryObjecti64v,
// because that one is a NULL check on GLES.glGetQueryObjecti64vEXT and silently
// returns when the driver lacks it -- which would leave *params untouched and
// hand the caller stack garbage. Querying the driver directly keeps the
// contract: either the driver answers or glGetError reports why it did not.
void glGetQueryObjecti(GLuint id, GLenum pname, GLint *params) {
    GLuint v;
    glGetQueryObjectuiv(id, pname, &v);
    *params = (GLint)v;
}
void glGetQueryObjecti64(GLuint id, GLenum pname, GLint64 *params) {
    if (GLES.glGetQueryObjecti64vEXT) {
        GLES.glGetQueryObjecti64vEXT(id, pname, params);
    }
}
void glGetQueryObjectui64(GLuint id, GLenum pname, GLuint64 *params) {
    if (GLES.glGetQueryObjecti64vEXT) {
        GLint64 v;
        GLES.glGetQueryObjecti64vEXT(id, pname, &v);
        *params = (GLuint64)v;
    }
}

// glGetTexLevelParameteri queries a texture level directly. Removed in GL 3.0,
// and with it the only way to ask about a mipmap without a texture object.
void glGetTexLevelParameteri(GLenum target, GLint level, GLenum pname, GLint *params) {
    glGetTexLevelParameteriv(target, level, pname, params);
}

// glGetInteger and glGetFloat read a current-state value. GLES 3 spells these
// glGetIntegerv and glGetFloatv; the bare names were the desktop-GL forms that
// never existed in ES.
void glGetInteger(GLenum pname, GLint *data) { glGetIntegerv(pname, data); }
void glGetFloat(GLenum pname, GLfloat *data) { glGetFloatv(pname, data); }
void glGetInteger64(GLenum pname, GLint64 *data) { glGetInteger64v(pname, data); }
} // extern "C"
