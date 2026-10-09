#!/usr/bin/env python3
"""Reconstruct the environment ZalithLauncher2 will hand the game, from our config.

The launcher does not expose its env construction for inspection, and the one
place it does is where two of our values are silently rewritten. This reproduces
setRendererEnv() from

  ZalithLauncher/.../game/launch/GameLauncher.kt

in the order it appears, so a config can be checked before it is installed
rather than after.

That matters because of how the failure looks. From the first device run:

    SDL_EGL_LIBRARY = /data/app/.../lib/arm64//data/app/.../lib/arm64/libcobalt.so

A doubled path. SDL cannot load it, falls back to the system EGL, and Minecraft
26.3 then fails its own glGetError address comparison -- so the visible symptom
is an unrelated-looking error several steps later, in game code. Nothing in the
launcher's output says the path was malformed.

Usage:  tools/check-env.py [config.json]

Exit code is meaningful: 0 means the env the game will see is well-formed, 1
means at least one value points somewhere that cannot work.
"""

import json
import os
import sys

# Stand-in for the plugin's real nativeLibraryDir. Only its shape matters:
# absolute, and not on LD_LIBRARY_PATH.
FAKE_LIBDIR = "/data/app/~~PLACEHOLDER==/me.shadow.cobalt-XXXX/lib/arm64"

# The plugin directory is deliberately absent, because it is absent in reality.
# getLibraryPath() adds RendererPluginManager.selectedRendererPlugin -- the V1
# plugin list -- and a V2 plugin lives in RendererV2PluginManager's list, so that
# lookup is null and the plugin's own lib directory is never added.
REAL_LD_LIBRARY_PATH = ":".join(
    [
        "/data/user/0/com.movtery.zalithlauncher.v2/files/components/lwjgl/3.4.1/natives/arm64-v8a",
        "/system/lib64",
        "/vendor/lib64",
        "/vendor/lib64/hw",
        "/system_ext/lib64",
        "/data/user/0/com.movtery.zalithlauncher.v2/app_runtime_mod",
        "/data/app/~~PLACEHOLDER==/com.movtery.zalithlauncher.v2-XXXX/lib/arm64",
    ]
)


def resolve_paths(value, libdir):
    """RendererConfig.resolveNativePaths: expands the '**|' prefix."""
    if isinstance(value, str) and value.startswith("**|"):
        return os.path.join(libdir, value[3:])
    return value


def build_env(cfg, libdir=FAKE_LIBDIR):
    """setRendererEnv(), in order. Later writes overwrite earlier ones."""
    env = {}
    renderer_id = cfg["rendererId"]

    # The launcher assigns the renderer *id* here, not a path.
    env["SDL_OPENGL_LIBRARY"] = renderer_id

    if renderer_id.startswith("opengles2"):
        env["LIBGL_ES"] = "2"
        env["LIBGL_MIPMAP"] = "3"
        env["LIBGL_NOERROR"] = "1"
        env["LIBGL_NOINTOVLHACK"] = "1"
        env["LIBGL_NORMALIZE"] = "1"

    # Our env merges here -- which is the only reason SDL_OPENGL_LIBRARY can be
    # corrected at all, and the reason SDL_EGL_LIBRARY cannot.
    for entry in cfg["env"]:
        env[entry["key"]] = resolve_paths(entry.get("value"), libdir)

    egl = resolve_paths(cfg["rendererEGLPath"], libdir)
    if egl is not None:
        env["POJAVEXEC_EGL"] = egl
        # Unconditional prepend. This is the line that doubles an absolute path.
        #
        # String concatenation, not os.path.join: the launcher concatenates, and
        # os.path.join would normalise the doubled path away -- which made this
        # script report "no problems" for the exact config that caused the
        # failure. Reproducing the bug requires reproducing the code that has it.
        env["SDL_EGL_LIBRARY"] = libdir + "/" + egl

    env["POJAV_RENDERER"] = renderer_id
    return env


def check(env):
    """Return a list of problems, each one something that cannot work."""
    problems = []

    def is_cobalt(v):
        return isinstance(v, str) and v.endswith("libcobalt.so")

    # A doubled path is the specific bug this exists to catch.
    for key, value in env.items():
        if isinstance(value, str) and value.count("/data/app/") > 1:
            problems.append(
                "%s is a doubled path: %s\n"
                "      the launcher prepends nativeLibPath to rendererEGLPath, so "
                "rendererEGLPath must be a bare filename" % (key, value)
            )

    # Everything that must be able to dlopen the library by absolute path.
    for key in ("SDL_OPENGL_LIBRARY", "SDL_EGL_LIBRARY", "LIBGL_GLES"):
        value = env.get(key)
        if value is None:
            continue
        if not value.startswith("/"):
            problems.append(
                "%s = %r is not absolute, so SDL_GL_LoadLibrary cannot find it"
                % (key, value)
            )
        elif not is_cobalt(value):
            problems.append("%s = %r does not name the renderer" % (key, value))

    # POJAVEXEC_EGL is dlopen'd by name, so a bare name only works if the
    # directory is on the search path. It is not, for a V2 plugin.
    #
    # That is not a defect, because LIBGL_GLES takes precedence:
    #
    #     char* gles = getenv("LIBGL_GLES");
    #     ...
    #     eglName = gles ? gles : (execEgl ? execEgl : "libEGL.so");
    #
    # So the bare POJAVEXEC_EGL is only acceptable while LIBGL_GLES carries the
    # absolute path, and it is a defect when it does not -- egl_loader.c then
    # silently falls back to the system libEGL.so. Checked as a pair, because
    # either half alone is uninformative.
    exec_egl = env.get("POJAVEXEC_EGL", "")
    gles = env.get("LIBGL_GLES")
    if exec_egl and not exec_egl.startswith("/"):
        resolvable = any(
            os.path.join(p, exec_egl) for p in REAL_LD_LIBRARY_PATH.split(":")
        )
        if not resolvable:
            if gles and gles.startswith("/") and gles.endswith(exec_egl):
                print(
                    "note: POJAVEXEC_EGL is a bare name and cannot be dlopen'd "
                    "on its own.\n"
                    "      LIBGL_GLES supplies the absolute path and takes "
                    "precedence in egl_loader.c, so this is covered."
                )
            else:
                problems.append(
                    "POJAVEXEC_EGL = %r cannot be dlopen'd (the plugin's lib "
                    "directory is not on LD_LIBRARY_PATH) and LIBGL_GLES does "
                    "not supply an absolute path (%r).\n"
                    "      egl_loader.c will fall back to the system "
                    "libEGL.so, so SDL and the EGL bridge will resolve GL "
                    "through different libraries." % (exec_egl, gles)
                )

    # 26.3's gate, stated as the launcher will see it.
    if env.get("POJAV_RENDERER", "").endswith("_desktopgl"):
        problems.append(
            "POJAV_RENDERER ends in _desktopgl, which requests "
            "eglBindAPI(EGL_OPENGL_API); Android answers EGL_BAD_API."
        )
    if env.get("LIBGL_ES") != "3":
        problems.append(
            "LIBGL_ES = %r; it becomes EGL_CONTEXT_CLIENT_VERSION and no 1.13+ "
            "Minecraft runs on an ES 2 context" % env.get("LIBGL_ES")
        )

    return problems


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "plugin/config/cobalt-renderer.json"
    with open(path, "r", encoding="utf-8") as fh:
        cfg = json.load(fh)

    env = build_env(cfg)

    print("Environment the game will see")
    print("  LD_LIBRARY_PATH = %s" % REAL_LD_LIBRARY_PATH)
    print()
    for key in sorted(env):
        print("  %-20s = %s" % (key, env[key]))

    problems = check(env)
    print()
    if problems:
        print("%d problem(s):" % len(problems))
        for p in problems:
            print("  - %s" % p)
        return 1
    print("No problems found.")
    return 0


if __name__ == "__main__":
    sys.exit(main())