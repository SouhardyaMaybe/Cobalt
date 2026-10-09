# Cobalt Wrapper — state of the build

What exists, what was verified, and what is still untested on hardware.

## Verified

`v0.1.0` is green end to end and published. Every claim below was checked
against the built artifact, not inferred from a passing build.

- Renderer builds for arm64-v8a, armeabi-v7a and x86_64.
- 4937 symbols exported per ABI; all **256** GL names Minecraft resolves across
  1.13.2 → 26.3 are among them (checked on the released `.so`, not on a log).
- `glGetError` exported exactly once — Minecraft 26.3 compares its address
  across `dlsym`, `eglGetProcAddress` and `SDL_GL_GetProcAddress` and refuses to
  start if they disagree.
- No exported symbol contains "MobileGlues". User-visible strings read Cobalt:
  `GL_VERSION` → `" Cobalt "`, `GL_SHADING_LANGUAGE_VERSION` → `" Cobalt with
  glslang and SPIRV-Cross"`, extensions → `GL_CB_*`, log prefix → `Cobalt`.
- APK is signed (`META-INF/CERT.RSA`), carries all three ABIs, and its
  `resources.arsc` contains the renderer config the launcher reads.

## Cross-check against a renderer that works

`ref/towo-builds/` holds three arm64 builds of a MobileGlues fork that were run
on this device. They are the only working reference available, so they were used
to check two decisions rather than reasoning alone.

**Static libc++ is right.** All three link only `libandroid`, `liblog`, `libm`,
`libdl`, `libc` -- no `libc++_shared`. Upstream's history agrees: `CMakeLists.txt`
has only ever set `c++_static`, never `c++_shared`. Our first build overrode
that and could not `dlopen` on device.

**The ARB/EXT additions are real, and larger than upstream's.** TOWO exports
`glDebugMessageCallbackARB` (the one pair modern versions need, which
`NATIVE_FUNCTION_HEAD` covers) but not `glActiveTextureARB` or
`glGenBuffersARB`. All 30 names in `src/arb_ext.cpp` are absent from every TOWO
build and from upstream's sources, so none can collide at link time.

### The 256-name target is an over-count, and TOWO proves it

TOWO runs Minecraft on this device while lacking 9 of the 256, including all of
these for 26.3:

    glGetInteger      glGetFloat      glGetInteger64    glGetProgrami
    glGetShaderi      glGetTexLevelParameteri
    glGetQueryObjecti glGetQueryObjectui64               glClipControl

None of these are real GL or GLES functions -- `glGetProgrami` and
`glGetShaderi` have never existed, `glGetInteger` has no `v` form in ES, and
`glClipControl` is GL 3.2 core, absent from ES. They are strings in LWJGL's
constant pool that the extraction in `research-mcgl/` matched.

So: a renderer that demonstrably works does not export them, and Minecraft runs.
The extraction is a string scan, not symbol resolution, and it over-approximates.

Cobalt exports all 256 anyway. That is deliberate and costs a few hundred bytes
-- an unnecessary symbol is harmless, a missing one is a startup crash -- but the
figure should be read as "no known gaps", not as "256 are required".

## Not yet verified

**Nothing has run on a device.** Every check above is static. The first thing to
do after installing is confirm the plugin appears in the launcher's renderer
list, then that a Minecraft version starts.

Logs land in the plugin's own `nativeLibraryDir/cobalt` (inside the app sandbox,
no permission needed). `latest.log` is the one to read.

## Minecraft 26.3: the shader translation failure

26.3 was the one version that would not start. Everything up to the shader
compile was correct — EGL context, `dlopen`, SDL window, and 26.3's own
`glGetError` address gate — and every core/terrain fragment shader failed with:

    ERROR: 0:224: '_uniform' : undeclared identifier
    ERROR: 0:224: '_instance_00_00' : Syntax error

`patches/0004` fixes it. The cause is in `process_uniform_declarations`, which
matched the bare substring `uniform` rather than the keyword:

    if (glslCode.compare(scan_pos, 7, "uniform") == 0) {

26.3 is the only version that ships RenderPearl, which flattens uniforms into
interface blocks and names them `_uniform_00_00` / `_uniform_instance_00_00`.
Every shader is full of identifiers that *start* with `uniform`, so the pass
fired inside them, consumed the enclosing condition and every statement up to
the next `;`, and rewrote the lot as a uniform declaration:

    if (_uniform_instance_00_00.UseRgss == 1)
    {
        highp vec2 param = _interface_variable_03;
        highp vec2 param_1 = ...;

became

    if (_uniform _instance_00_00 ;

— the dangling `_` being what the driver reported as an undeclared identifier.
The rewritten text also references `_uniform_00_02`, which by then is never
declared, so it could not have compiled even if the brace had survived.

Two defects, both fixed:

1. **No token boundary on the keyword.** `is_uniform_keyword()` now requires a
   non-identifier character on both sides.
2. **A block's end was found at its first `;`,** which is inside the body. The
   pass therefore deleted the body of any block containing an initialiser and
   left unbalanced braces. Unreachable for valid GLSL from older versions, which
   is why 1.13 → 26.2 were unaffected; found by an invariant in the new test
   rather than by a failing shader.

### Reproducing this without a device

The translation passes are plain `std::string` code; only the file around them
needs glslang and SPIRV-Cross. `tools/test-glsl.sh` lifts the functions out of
the shipped source and compiles them on the host, so the fix is testable in
seconds rather than only on a phone. Two fixtures are taken from the on-device
log of the failing shaders, and the suite asserts each comes back byte-identical.

The test is deliberately not vacuous: linked against pristine upstream it fails
9 assertions, naming the 26.3 corruption, `myuniform`, `uniforms`, and the brace
imbalance.

Note for anyone extending it: `#include "passes.inc"` resolves next to the test
source before any `-I` path, so a stale extract in the same directory silently
shadows the one you meant to compile. Run it via `tools/test-glsl.sh`, which
extracts to a fresh temp dir.

## What a working run still says

26.3 runs. The log has no shader errors, no `SHADER DUMP`, no failed pipeline, and
the world renders and a multiplayer server connects. The remaining lines are not all
equal, and treating them as one class is how the last four debugging rounds went
wrong.

**Fixed by shipping the file.** `Failed to load config. Use default config.` came
with `maxGlslCacheSize = 0`. No `config.json` was shipped, `config_refresh()` failed,
and every key took its `-1` fallback — which `init_settings()` reads as "the config
did not say", so the entire config layer degrades silently. The cost was a disabled
shader cache, which also disables the negative cache from `patches/0001`: a shader
that fails to compile is retried on every resource reload, and Minecraft reloads
resources on every dimension change. `plugin/config/cobalt-settings.json` now ships
as `nativeLibraryDir/cobalt/config.json`, per ABI. `tools/test-config.sh` parses it
with the same cJSON the renderer uses, because `config_get_int()` returning `-1` for
an unreadable key is indistinguishable from the key being absent — only something
that reports instead of defaulting can tell.

**Not ours.** `Couldn't leave fullscreen`, `Failed to set window icon`, the udev and
`/proc` warnings, the "unexpected shutdown ... resetting fullscreen mode" note from
the previous crashed run, and `Failed to find a usable hardware address` are Zalith,
SDL and the Android sandbox. `Can't ping mcpvp.net` is DNS.

**Correct, and worth leaving.** `Not Detected GL_EXT_multi_draw_indirect!` is a true
statement about the Adreno 613, and `init_settings_post()` filters the multi-draw
order down to what the device actually resolves — `multidrawOrderArrays = unroll` in
the log is that filter working, with `unroll` always available. Removing the message
would hide the reason the order is what it is.

## The three silent failures

Each produced a green build. Each is now guarded, but the pattern is what
matters — in this project a build succeeding means nothing on its own.

1. **Missing `GLAPI` on a new entry point.** The project compiles C++ with
   `-fvisibility=hidden`, and CMake builds with `-ffunction-sections` +
   `--gc-sections`. A definition lacking
   `GLAPI GLAPIENTRY` (`__attribute__((visibility("default")))`) compiles, links,
   and is then garbage-collected. Locally reproduced: unmarked exports 1 symbol,
   marked exports 30.

2. **Missing `extern "C"`.** The name becomes C++-mangled
   (`_Z18glActiveTextureARBj`) and every `dlsym` lookup misses. Same silence.

3. **A measurement that is wrong rather than the code.** `comm(1)` compares set
   differences only when both sides share a collation; a Python-sorted list
   against a `sort`-sorted one reported 29 missing names when all were exported.

4. **A shader pass that mangles its own input.** `process_uniform_declarations`
   corrupted every 26.3 terrain shader and no build, link or symbol audit could
   see it — the wrong text is still text. It is now a host-side test.

5. **A test that compiled the wrong file.** `#include "passes.inc"` prefers the
   directory of the including file over `-I`, so a stale extract beside the test
   shadowed the patched one and "pristine upstream" comparisons silently ran the
   patched code. Three probes reported a fixed bug as unfixed before this was
   caught. The runner now extracts to a fresh temp directory.

The general lesson, and the reason CI publishes the full symbol list with
`if: always()`: every one of these looked like a defect in the renderer, and two
were defects in the check.

## Build order that must not change

`patches/` → add `src/*.cpp` → `tools/rebrand.py` → configure.

Patches are written against pristine upstream. Anything that rewrites sources
first stops them applying. The CMakeLists insertion is anchored on `gl/mg.cpp`
because that is the spelling present *before* the rebrand; anchoring on
`gl/cobalt.cpp` fails on every run. GNU sed reads `\|` inside `\(...\)` as a
literal, so alternation there matches nothing and fails silently.

## Licensing

The renderer is a MobileGlues derivative, LGPL-2.1. `tools/rebrand.py`
deliberately skips every line containing a copyright or SPDX notice — LGPL-2.1
§5(a) requires the notice to travel with the work. Every identifier, string,
path and filename is renamed; attribution is not. See `NOTICE`.

Third-party licence names were wrong twice before being written down (xxhash is
MIT not BSD-2, ska is Boost-1.0 not BSD-3); each entry in `NOTICE` is now
verified against the licence file it cites.

## Next

Measure before touching the draw path. The bottleneck is CPU state
re-materialisation (MG issue #460: ~250 FPS on OptiFine vs ~100 on Sodium for the
same scene), so the next changes are correctness-optional and speed-only:
sampler-state folding onto bound textures for 1.13+, then DSA, multi-draw and
indirect draw — MC has fallbacks for all three.

Deferred but specified: negative shader caching is done (`patches/0001`).