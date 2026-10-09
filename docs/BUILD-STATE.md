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

## Not yet verified

**Nothing has run on a device.** Every check above is static. The first thing to
do after installing is confirm the plugin appears in the launcher's renderer
list, then that a Minecraft version starts.

Logs land in the plugin's own `nativeLibraryDir/cobalt` (inside the app sandbox,
no permission needed). `latest.log` is the one to read.

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