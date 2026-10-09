Cobalt Wrapper v0.2.0

Fixes the two bugs reported from the first device run. v0.1.0 built cleanly and
could not be loaded.

libc++: the library could not be dlopen'd

  cannot locate symbol "_ZTVNSt6__ndk119basic_ostringstreamIcE..."

The build passed -DANDROID_STL=c++_shared, which puts "NEEDED libc++_shared.so"
in the .so and leaves 118 __ndk1 symbols undefined. That library is in neither
the APK nor LD_LIBRARY_PATH -- a plugin's lib directory is never added to it,
because the launcher builds that list from its *V1* plugin registry only -- so
the load failed on the first C++ symbol.

Now static, which is what the upstream build has always used. Confirmed against
the three arm64 builds in ref/towo-builds/, which run on this device and link
only libandroid, liblog, libm, libdl and libc. Cobalt's NEEDED list now matches
them exactly.

CI fails on any undefined C++ symbol. A symbol-presence check cannot catch this
class of defect: a library can export all 4937 names correctly and still be
unloadable.

SDL_EGL_LIBRARY was a doubled path

  SDL_EGL_LIBRARY = /data/app/.../lib/arm64//data/app/.../libcobalt.so

The launcher consumes rendererEGLPath twice and its two consumers disagree about
the form: POJAVEXEC_EGL takes it verbatim, while SDL_EGL_LIBRARY has
nativeLibPath prepended unconditionally. An absolute value therefore doubles, SDL
falls back to the system EGL, and Minecraft 26.3 then fails its own glGetError
address comparison.

rendererEGLPath is now a bare filename, and the absolute path the EGL bridge
needs comes from LIBGL_GLES, which egl_loader.c prefers over POJAVEXEC_EGL.
tools/check-env.py reproduces the launcher's environment construction and fails
the build on a doubled path.

Size: 38 MB -> 6.3 MB

Unstripped debug info. Now --strip-unneeded, which preserves the dynamic symbol
table that dlsym resolves through. 6.1 MB per ABI against TOWO's 5.9 MB, for the
same renderer.

Unchanged: all 256 GL names Minecraft resolves are still exported on all three
ABIs.

Note on that figure: the three TOWO builds run Minecraft on this device while
lacking nine of them -- glGetProgrami, glGetShaderi, glGetInteger, glGetFloat,
glGetInteger64, glGetTexLevelParameteri, glGetQueryObjecti,
glGetQueryObjectui64 and glClipControl. None is a real GL or GLES function; they
are LWJGL constant-pool strings the symbol extraction matched. So 256 means "no
known gaps", not "256 required". They are exported anyway, since an unnecessary
symbol costs bytes and a missing one costs a startup crash.
