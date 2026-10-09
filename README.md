# Cobalt Wrapper

A GL-to-GLES renderer for Minecraft: Java Edition, on Android.

Ships as a launcher plugin. There is no app to launch: the APK installs into
ZalithLauncher2, which then offers Cobalt as a renderer for Minecraft.

## Install

1. Download `cobalt-wrapper-release.apk` from the release page.
2. Install it. It is signed with a generated debug key, so if a previous Cobalt
   is installed, uninstall that first — Android refuses to replace an install
   signed with a different key.
3. In the launcher, open the renderer list and select **Cobalt Wrapper**.

The launcher finds renderer plugins by querying installed packages, so if Cobalt
does not appear in that list the APK is not installed under the package the
launcher can see. Open the plugin's own activity to check what it installed.

## What it supports

Minecraft 1.13.2 through 26.3. The renderer exports every GL symbol any of those
versions resolves — 256 names, all three ABIs — and CI fails the build if that
set changes in either direction.

## Reading the logs

The renderer writes its config, log and shader cache into the plugin's own
`nativeLibraryDir/cobalt`. That path is inside the app sandbox, so it needs no
permission and no setup. On an uninstalled-from-the-launcher build it is
`/data/app/~~*/me.shadow.cobalt-*/lib/cobalt/`.

`latest.log` is the one to read. It names the shader it was translating when
something fails, and the negative-cache hits tell you which shaders the ES
driver rejects — those are logged as `GLSL Known-Failure Cache Hit` rather than
retried.

## How it is built

| Path | What it is |
|---|---|
| `ref/mobileglues` | The renderer, a pinned MobileGlues submodule. Not edited. |
| `patches/` | Diffs against that pin. One patch: the shader cache. |
| `src/` | Cobalt's own C++ files, added to the renderer's build at compile time. |
| `tools/rebrand.py` | Rewrites MobileGlues to Cobalt across the whole tree. |
| `tools/gen-config.py` | Generates and validates the launcher's renderer config. |
| `tools/gen-key.sh` | Generates the APK signing key. |
| `build-android.sh` | One ABI, renderer to staged `.so`. |
| `plugin/` | The APK. A shell around the library. |
| `research-mcgl/` | GL symbols Minecraft resolves, per version and unioned. |

Three things are worth knowing if you change this:

**The rebrand runs during the build, not before it.** Patches are written against
pristine upstream, so anything that rewrote the sources first would stop them
applying. `tools/rebrand.py` is idempotent, which is what makes the ordering
safe.

**Licence headers stay.** `tools/rebrand.py` skips any line containing a
copyright or SPDX notice. LGPL-2.1 section 5(a) requires the notice to travel
with the work. Every identifier, string, path and file name is renamed; the
attribution is not, and removing it would not be a rename.

**New entry points need `GLAPI GLAPIENTRY`, and CI will not catch it if you
forget.** The project compiles C++ with `-fvisibility=hidden`, so a symbol
reaches the dynamic table only if marked default-visible. Unmarked definitions
compile, link, and are then garbage-collected by `--gc-sections` — silently.
Symbols marked but without `extern "C"` are C++-mangled and dlsym cannot find
them, also silently. Both happened during development.

## Licence

The renderer is LGPL-2.1. See `LICENSE`.