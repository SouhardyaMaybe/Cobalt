#!/usr/bin/env python3
"""Generate the Android string resource the launcher reads Cobalt's config from.

The launcher's parseApkPlugin() does:

    val configRes = metaData.getStringRes("fclPlugin_V2") ?: return
    val configString = context.getString(info, configRes) ?: return
    val config = runCatching { decodeFromString<RendererConfig>(configString) }
        .onFailure { /* logged, then the plugin is skipped */ }.getOrNull() ?: return

So the config must arrive as an Android string resource, and it is JSON inside
XML. That is why this step exists rather than a Kotlin constant:

  A hand-written copy in the APK drifts from the JSON a maintainer actually
  edits, and the drift is invisible. A malformed config is caught by a
  runCatching that logs and skips the plugin, so a stale copy shows up as
  "the launcher never sees my renderer" with nothing on the user's screen.

Generating it keeps one source of truth -- config/cobalt-renderer.json -- and
makes the APK's copy a build product rather than something to remember to
update.

It also validates. A bad config fails here, in CI, with a line number, instead
of on a user's device where the only symptom is a missing renderer.

Usage:  tools/gen-config.py <config.json> <out-dir>
"""

import json
import os
import sys
import xml.dom.minidom
import xml.parsers.expat as expat

# Field names from ZalithLauncher .../plugin/renderer_v2/data/RendererConfig.kt.
# The launcher decodes with kotlinx.serialization and unknown keys are an error
# only if configured to be; missing ones fail the decode outright. Checking
# here means the failure is ours and it has a location.
REQUIRED = [
    "displayName",
    "rendererId",
    "rendererGLPath",
    "rendererEGLPath",
    "dlopenLibPaths",
    "env",
    "minMCVer",
    "maxMCVer",
]

ENV_TYPES = {"NormalEnv", "SelectableEnv", "CustomizableEnv", "ToggleableEnv"}


def validate(cfg, path):
    problems = []

    for key in REQUIRED:
        if key not in cfg:
            problems.append("missing required field: %s" % key)

    unknown = set(cfg) - set(REQUIRED)
    if unknown:
        problems.append("unknown field(s), which the launcher will reject or ignore: %s"
                        % ", ".join(sorted(unknown)))

    # See CobaltConfig.kt for why this specific value. It is not cosmetic and
    # not a preference; two separate launcher mechanisms depend on it.
    if cfg.get("rendererId") != "opengles3":
        problems.append(
            'rendererId is %r, expected "opengles3". A different id can fall '
            "through to br_init() (Birch loader, jumps to address zero) or "
            "disable the ES-compat layer in sdl_hook.c."
            % cfg.get("rendererId")
        )
    if str(cfg.get("rendererId", "")).endswith("_desktopgl"):
        problems.append(
            "rendererId ends in _desktopgl, which requests "
            "eglBindAPI(EGL_OPENGL_API). Android answers EGL_BAD_API (0x300c)."
        )

    # rendererGLPath is dlopen'd verbatim by both the launcher and LWJGL, via
    # -Dorg.lwjgl.opengl.libname. A V2 plugin's nativeLibraryDir is never added to
    # LD_LIBRARY_PATH -- getLibraryPath() includes only the *V1* plugin list -- so
    # a bare filename cannot resolve. This one must be absolute, via "**|".
    gl_path = cfg.get("rendererGLPath", "")
    if not (isinstance(gl_path, str) and (gl_path.startswith("**|") or gl_path.startswith("/"))):
        problems.append(
            "rendererGLPath is %r. LD_LIBRARY_PATH is built from the V1 plugin "
            "list, so a V2 plugin's lib directory is not on it and a bare "
            "filename cannot be dlopen'd. Use the '**|' prefix." % gl_path
        )

    # rendererEGLPath must be a BARE filename -- the opposite of rendererGLPath.
    #
    # setRendererEnv() consumes this one twice, and the two consumers want
    # different things:
    #
    #     envMap["POJAVEXEC_EGL"] = eglName
    #     envMap["SDL_EGL_LIBRARY"] = "$nativeLibPath/$eglName"
    #
    # The second prepends nativeLibPath unconditionally, so an absolute
    # rendererEGLPath yields a doubled path. The first device run showed exactly
    # that:
    #
    #     SDL_EGL_LIBRARY = /data/app/.../lib/arm64//data/app/.../libcobalt.so
    #
    # SDL cannot load a doubled path, falls back to the system EGL, and 26.3 then
    # fails its glGetError address check for precisely that reason.
    #
    # POJAVEXEC_EGL therefore cannot carry the absolute path. The EGL bridge gets
    # one through LIBGL_GLES instead: egl_loader.c reads it first and prefers it
    # over POJAVEXEC_EGL, and Zalith never sets it, so a value from this config
    # survives.
    egl_path = cfg.get("rendererEGLPath", "")
    if not (isinstance(egl_path, str) and "/" not in egl_path):
        problems.append(
            "rendererEGLPath is %r. The launcher builds SDL_EGL_LIBRARY as "
            "'$nativeLibPath/$rendererEGLPath', so an absolute value becomes a "
            "doubled path. Use a bare filename here and put the absolute path in "
            "LIBGL_GLES." % egl_path
        )

    # One library for both roles: the launcher loads it as the EGL implementation
    # and resolves GL through its own eglGetProcAddress, so a separate EGL shim
    # would give one symbol two addresses -- exactly what Minecraft 26.3 refuses
    # to start on. Compared by filename, since the two fields now legitimately
    # differ in form.
    def _basename(v):
        return str(v).replace("**|", "").rsplit("/", 1)[-1]

    if _basename(egl_path) != _basename(gl_path):
        problems.append(
            "rendererGLPath (%r) and rendererEGLPath (%r) name different "
            "libraries. They must be the same one so each GL symbol has exactly "
            "one address." % (gl_path, egl_path)
        )

    for i, entry in enumerate(cfg.get("env", []) or []):
        if not isinstance(entry, dict):
            problems.append("env[%d] is not an object" % i)
            continue
        etype = entry.get("type")
        if etype not in ENV_TYPES:
            problems.append(
                "env[%d] has type %r, not one of %s" % (i, etype, sorted(ENV_TYPES))
            )
        if "key" not in entry:
            problems.append("env[%d] has no key" % i)
        if etype == "CustomizableEnv":
            title = entry.get("title")
            if not title:
                problems.append(
                    "env[%d] (%s) has no title; the launcher shows it unlabelled"
                    % (i, entry.get("key"))
                )
            elif not title.get("key"):
                problems.append("env[%d] (%s) has an empty title key" % (i, entry.get("key")))

    keys = [e.get("key") for e in (cfg.get("env") or []) if isinstance(e, dict)]
    if "SDL_OPENGL_LIBRARY" not in keys:
        problems.append(
            "env has no SDL_OPENGL_LIBRARY. The launcher assigns it the renderer "
            "*id* rather than a path, so SDL falls back to the system GLES and "
            "Minecraft 26.3 then fails its own glGetError address check."
        )
    if "LIBGL_ES" not in keys:
        problems.append(
            "env has no LIBGL_ES. It becomes EGL_CONTEXT_CLIENT_VERSION; unset "
            "defaults to 2 and no 1.13+ Minecraft runs on an ES 2 context."
        )
    if "LIBGL_GLES" not in keys:
        problems.append(
            "env has no LIBGL_GLES. egl_loader.c reads it in preference to "
            "POJAVEXEC_EGL, and it is the only way to hand the EGL bridge an "
            "absolute library path once rendererEGLPath is a bare filename. "
            "Without it the bridge falls back to the system EGL."
        )
    if "SDL_EGL_LIBRARY" in keys:
        problems.append(
            "env sets SDL_EGL_LIBRARY, but the launcher overwrites it afterwards "
            "with '$nativeLibPath/$rendererEGLPath'. Setting it here has no "
            "effect and hides which value is actually in force."
        )

    return problems


def to_android_string(text):
    """Escape text for an Android <string> resource body.

    Order matters: the ampersand and angle brackets are escaped first, then
    quotes, then newlines. Android unescapes \\n and \\" back on read, so the
    launcher's JSON decoder sees exactly the original text.
    """
    out = text
    out = out.replace("&", "&amp;")
    out = out.replace("<", "&lt;")
    out = out.replace(">", "&gt;")
    out = out.replace('"', '\\"')
    out = out.replace("\n", "\\n")
    return out


def _android_unescape(text):
    """The inverse of to_android_string, as Android's resource loader does it."""
    return (
        text.replace("\\n", "\n").replace('\\"', '"').replace("\\'", "'")
    )


def _string_body(document):
    """The <string> element's text, as the resource loader would hand it over."""
    node = xml.dom.minidom.parseString(document).getElementsByTagName("string")[0]
    return node.firstChild.data


def main():
    if len(sys.argv) != 3:
        sys.stderr.write(__doc__)
        return 2
    src, out_dir = sys.argv[1], sys.argv[2]

    with open(src, "r", encoding="utf-8") as fh:
        raw = fh.read()

    try:
        cfg = json.loads(raw)
    except json.JSONDecodeError as e:
        sys.stderr.write("error: %s is not valid JSON: %s\n" % (src, e))
        return 1

    problems = validate(cfg, src)
    if problems:
        sys.stderr.write("error: %s\n" % src)
        for p in problems:
            sys.stderr.write("  - %s\n" % p)
        return 1

    rendered = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        "<resources>\n"
        '    <string name="cobalt_renderer_config">%s</string>\n'
        "</resources>\n"
        % to_android_string(raw.strip())
    )
    # Parse what is about to be written. AGP reports a malformed resource as
    # "Error parsing <path>" from ManifestMerger2, which names neither the
    # offending character nor the escaping, so the round trip happens here.
    try:
        xml.dom.minidom.parseString(rendered)
    except expat.ExpatError as e:
        sys.stderr.write(
            "error: generated resource is not well-formed XML: %s\n"
            "       (this is an escaping bug in to_android_string)\n" % e
        )
        return 1

    # And parse it the way the launcher will, rather than only proving the XML
    # is well-formed. Those are different properties: a resource can parse as
    # XML and still decode to something the launcher's RendererConfig rejects,
    # and that is the failure it swallows in a runCatching and reports as
    # "the launcher does not see my renderer".
    try:
        decoded = json.loads(_android_unescape(_string_body(rendered)))
    except ValueError as e:
        sys.stderr.write("error: resource does not decode as JSON: %s\n" % e)
        return 1

    if decoded != cfg:
        sys.stderr.write(
            "error: the resource does not round-trip to the config it was\n"
            "       generated from; escaping has lost or altered data\n"
        )
        return 1

    values = os.path.join(out_dir, "values")
    os.makedirs(values, exist_ok=True)
    target = os.path.join(values, "cobalt_config.xml")
    with open(target, "w", encoding="utf-8") as fh:
        fh.write(rendered)

    print("wrote %s" % target)
    return 0


if __name__ == "__main__":
    sys.exit(main())