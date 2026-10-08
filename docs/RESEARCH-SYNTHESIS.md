# Research synthesis — what actually gets compatibility, performance, speed

Sources: five parallel research streams (Android GLES perf model, GL→GLES translator
comparison, shader translation, MobileGlues internals, Minecraft's real GL requirements),
plus primary-source verification against `MobileGL-Dev/MobileGlues @ 97558a6` and the
launchers' own source.

**Measured is marked with a number and a source. Everything else is a claim, and is
labelled as one.** Where the two conflict, the number wins.

---

## 0. The position we start from

MobileGlues 2.0.3-fork (TOWO) runs on the target device. That is the baseline. Every
recommendation below either improves it, replaces part of it, or explains why it is
already fine.

The one-line summary of the research: **MobileGlues is not slow because of Rust-vs-C++.
It is slow because a desktop-GL state vector has to be re-materialised per draw, and
because translation happens per shader without a cache that remembers failures.**

---

## 1. Compatibility

### 1.1 The target is small and now known exactly

Derived from the Mojang client jars themselves (12 versions downloaded, constant pools
parsed, GL-touching classes decompiled, LWJGL Java methods resolved to native symbols).
Artifacts in `research-mcgl/`.

| MC | distinct native `gl*` symbols |
|---|---|
| 1.13.2 | 163 |
| 1.16.5 | 126 |
| 1.17.1 – 1.18.2 | 93 |
| 1.19.4 – 1.21.1 | 99 |
| 1.21.11, 26.1 | 112 |
| 26.3 | 126 |
| **union 1.13.2 – 26.3** | **256** |

`GLxxC` is byte-for-byte identical from LWJGL 3.2.1 through 3.4.3 with **zero signature
changes**. One symbol table covers 1.13 → 26.3. LWJGL-version branching is unnecessary.

### 1.2 Two myths, corrected from primary sources

- **MC has never used immediate mode.** `glBegin`/`glEnd`/`glVertex3f` appear in zero
  versions 1.13.2 → 26.3. Pre-1.17 used *client-side vertex arrays*.
- **1.17.1 is a hard cliff.** Every fixed-function call — matrix stack, lighting, fog,
  texenv, display lists — is zero from 1.17.1 onward and never returns.

So for 1.17+ there is no fixed-function surface to emulate. The `gl_stub.cpp` tier in
MobileGlues (2,411 stubs) is dead weight for modern versions.

### 1.3 The two hard gates for 26.3

Both verified from decompiled bytecode, both currently unfixed upstream:

1. **Address identity.** `GlBackend.loadLibrary()` throws unless
   `GL.getFunctionProvider().getFunctionAddress("glGetError") == SDLVideo.SDL_GL_GetProcAddress("glGetError")`.
   Reproduced identically under MobileGlues, Krypton Wrapper and Amethyst — not
   driver-specific. Alexytomi: *"KW and MG incorrectly bind the wrong egl api… not
   filtered properly."*
2. **SDL must report context ≥ 3.3.** 26.3 switched from GLFW to `org.lwjgl:lwjgl-sdl`.

Neither is a feature problem. Both are symbol-resolution problems.

### 1.4 What MC ships fallbacks for — this is the scope lever

`GlDevice` holds ten optional `USE_GL_*` flags: `ARB_vertex_attrib_binding`, `KHR_debug`,
`EXT_debug_label`, `ARB_debug_output`, `ARB_direct_state_access`, `ARB_buffer_storage`,
`ARB_base_instance`, `ARB_draw_indirect`, `ARB_multi_draw_indirect`,
`ARB_shader_draw_parameters`. **All optional.** MC has `DirectStateAccess$Emulated`,
`VertexArray$Emulated`, `GlTransientMemory$Fallback`, `GlDebugLabel$Ext` for each.

> Implement none of them and you get a correct, slower game. That is the cheapest
> correct scope.

The expensive things everyone builds — `glMultiDrawArrays`, `glClipControl`, DSA — are
precisely the ones deferrable for correctness and payable only in speed.

### 1.5 Must synthesise or shim

| Item | Versions | Why |
|---|---|---|
| `glLogicOp` | **all** | Does not exist in GLES. MC uses it for map/item-frame colouring. |
| `glDrawPixels` | 1.17.1+ | Not in GLES 3.x. |
| `GL_QUADS` topology | all | No quad primitives in GLES. The "GL4ES Fix" mod exists solely to switch rendering to triangles. |
| `glBindSampler` / `glGenSamplers` / `glSamplerParameter*` | 26.3 | GLES 3.2 only. **Not deferrable.** But MC never puts filter state on textures there — folding `glSamplerParameter*` onto the bound texture works. |
| `glGetTexLevelParameteri` | all | MC probes max texture size by allocating and halving on retry. |
| `GL_MULTISAMPLE`, `GL_FRAMEBUFFER_SRGB` enables | 26.3 | Neither exists in GLES; both enabled unconditionally at device creation. |
| `glPolygonMode` | all | GLES only supports POINT/LINE/FILL. |
| `glFoo` **and** `glFooARB`/`glFooEXT` | 1.13 | 1.13 reaches for suffixed forms gated on `GLCapabilities`. LWJGL has 1,306 vendor-suffixed symbols. |
| Fixed-function set + display lists | ≤1.16.5 | Only if pre-1.17 is in scope. |

---

## 2. Performance — where the time actually goes

### 2.1 The number that sets the strategy

GLES costs **4–17 µs of CPU per underlying draw call**; Vulkan 1.6–2.2 µs on the same
devices — GLES is 2–5× more expensive per draw. Arm's budget: **<500 draw calls/frame**
for GLES. A low-power Mali was measured going draw-bound at ~1,200 draws.

### 2.2 The cleanest natural experiment anyone has run on this problem

MobileGlues issue #460 — same device (Galaxy A57, Exynos AMD Xclipse), same world, same
renderer: **OptiFine ≈ 250 FPS, Sodium caps at ≈ 100 FPS.**

OptiFine emits a simpler GL path; Sodium emits modern GL state. The GPU is not the
limit — **translating modern desktop-GL state is.**

### 2.3 Every project independently names the same bottleneck

Not shader math. Not bandwidth. Not draw submission itself. **State-vector
hashing/comparison and pipeline management.**

> *"I suspect that the pipeline-caching is going to be the big hot-spot. There's a lot
> of state to hash, and finally compare once a hit has been found."* — Zink's author

Zink measured **18 FPS vs 100 native** on SPECViewPerf until someone targeted exactly
this, then reached 34. ANGLE ran at 60–70% of native on Android; Samsung's Xclipse team
chose ANGLE-over-Vulkan over shipping a native GL driver. Their top two fixes were
**lock granularity** and **allocation pooling** — both pure CPU state tracking.

The maintainers of MobileGlues agree, in their own commit messages:

> *"Minecraft toggles BLEND/DEPTH_TEST/CULL_FACE thousands of times a frame and most of
> them are repeats."* — `[Perf] (enable): drop redundant enables`

### 2.4 Techniques that worked, across all five projects

1. **Persist binaries, never compile twice** — DXVK state cache, gl4es PSA, ANGLE blob cache
2. **Move compilation off the critical path** — background threads, deliberately rate-limited
3. **Split monolithic pipelines into reusable libraries**
4. **Maximise dynamic state, minimise specialisation constants** → fewer distinct pipelines
5. **Narrow the comparison** — ANGLE's L1 cache compares only bytes the dirty mask says changed
6. **Sort draws so the state-transition graph is a path, not a hub** — ANGLE documents this failure explicitly

### 2.5 Measured gaps in MobileGlues specifically

| Rule | State |
|---|---|
| Batch uploads to frame start; never stall | 7 `glReadPixels` uses, 2 `glFlush`/`glFinish` |
| `glInvalidateFramebuffer` for transient attachments | **1 call total** — Qualcomm measured a forgotten stencil attachment costing **9% of frame time** |
| Sort draws so transitions are a path | **no sorting found** |
| Multidraw backend | expands into `for (primcount)` loops → N underlying draws at 4–17 µs each |
| Shader cache negative caching | **absent** — `put` only fires on success |
| Shader cache key includes `glsl_type` | **absent** — vertex/fragment can collide |
| Caches compiled binaries, not translated source | **source only** |

### 2.6 The multidraw backend is a ranked order, not a mode

Since 2.0.0: `native, multiindirect, multibasevertex, multiarrays, indirect, basevertex,
unroll, compute`. Default resolves to `multiarrays`/`multibasevertex`/`multiindirect`
where supported. **Compute is last and never auto-selected.** The benchmark exists to
let the *device* pick, per entry point — the output is deliberately not aggregated
because the five entry points' absolute times differ by orders of magnitude.

---

## 3. Speed: shader translation

### 3.1 It is not what it looks like

MobileGlues is **glslang → SPIR-V → SPIRV-Cross** with a thin regex pre/post pass — not a
hand-written translator. Measured: glslang ~50 ms/shader, SPIRV-Cross ~4 ms. The front end
dominates.

### 3.2 naga is not a drop-in — this kills the obvious Rust play

naga is genuinely ~30× faster at GLSL→SPIR-V. Its GLSL frontend supports **only
440/450/460**. `#version 120` is rejected at the lexer, before any IR exists. You would
pay glslang's cost anyway *and* add a second translator.

### 3.3 Translation is load-time, not frame-time

Measured 50–70 ms/shader on desktop. On an Android big-core, plausibly 2–4× worse. A
shader pack with hundreds of programs implies tens of seconds of blocking work cold.

But it is paid **once per process at shader-load**, not per frame. So:

> **The cache is the dominant lever, not the translator.** A warm cache turns ~50 ms into
> a SHA-256 and a map lookup. An unwarm cache is ~50 ms no matter which translator you use.

### 3.4 The cache defects, in value order

1. **Negative caching.** Failed translations are never cached. A shader the ES driver
   rejects costs full glslang time on *every* program reload, forever, for something that
   will never succeed. Highest-value single fix identified across all streams.
2. **`glsl_type` in the cache key.** One-line correctness fix.
3. **Layer compiled binaries.** `GL_PROGRAM_BINARY_RETRIEVABLE_HINT` + `glGetProgramBinary`
   over the source cache — ANGLE and Mesa cache compiled artefacts, "where the seconds are".
4. **`precision highp` is forced unconditionally.** `mediump` is the tile-GPU fill-rate win;
   this is a correctness-over-performance choice that should be capability-gated.
5. **Dynamic indexing of sampler/uniform-block/fragment-output arrays.** ES 3.00 makes these
   a hard compile error where desktop GLSL merely leaves it undefined. SPIR-V has no notion
   of that rule, so it is not caught — this is where a hand-written layer earns its keep.
   No evidence MobileGlues handles it.

---

## 4. Optimisation — measured device rules

From Qualcomm and Arm directly. Applies to what a compat layer forwards.

| Rule | Evidence |
|---|---|
| **ASTC sRGB for colour textures** | Linear ASTC decodes to FP16 intermediates; sRGB always 8-bit UNORM. Half the intermediate data free. |
| **ASTC linear + `EXT_texture_compression_astc_decode_mode`** for data maps | Mali: *"significantly improve filtering performance and energy efficiency"* |
| **`GL_TEXTURE_2D_ARRAY`, never `GL_TEXTURE_3D`** | 2× filter cost on Mali; *"expensive"* on Adreno |
| **2× aniso, not trilinear** | Trilinear 2× on Mali; 8× trilinear aniso = **16×** |
| **No `discard`, no FS depth writes mid-frame** | Kills LRZ/Early-Z on Adreno, *"can disable hardware optimizations"* on Mali |
| **One `glBindFramebuffer` per pass, never ping-pong** | Mali: *"the GPU will then go idle"* |
| **`glInvalidateFramebuffer(GL_DRAW_FRAMEBUFFER, GL_ALL_ATTACHMENTS)`** | 9% of frame time in Qualcomm's own demo |
| **Batch VBO updates before the draws using them** | Otherwise the driver keeps multiple full copies |
| **≤500 underlying draw calls/frame** | Arm's budget for GLES |
| **16-bit indices wherever vertex count permits** | Arm: *"lowest precision index data type possible"* |
| **No fullscreen pass last in an FBO** | Defeats Adreno's visibility-stream trimming — 2–5 µs × tile count |
| **Depth D16; `RGB10_A2` over FP16** | Both vendors, hardware fast paths |

**One counter-intuitive result:** on Adreno, **ETC2 stays compressed in L1 while ASTC
does not.** ETC2 can win on cache-resident working sets despite more bytes. Adreno is
also the counter to "trilinear is fine" — 16× aniso is 16× slower.

**Adreno never recompiles shaders** — *"the Adreno drivers never recompile shaders"*.
Mali and others do, and it is legal-but-catastrophic. So runtime shader generation is
free on Adreno and a stall generator elsewhere.

---

## 5. What not to do

- **Do not rewrite the renderer in Rust.** The frame time is the driver and the state
  vector, not the language. MobileGlues already dedups redundant enables, and a from-scratch
  rewrite ships something less battle-tested than the build already on the device.
- **Do not swap glslang for naga.** Its GLSL frontend cannot read desktop GLSL < 440.
- **Do not enable FSR1.** Off by default; the plugin calls it "(Experimental)", warns it
  *"may cause image corruption on some drivers"*, and the source annotates the enum
  `// may be useless`. No measured benefit exists anywhere.
- **Do not use uber-shaders.** Adreno: reduces state changes but *"often increases GPR
  count, which can reduce performance overall."*
- **Do not rely on the ANGLE-on-Adreno combination.** MobileGlues deliberately disables
  ANGLE on Adreno 730/740; users report ANGLE as *"a nightmare for old devices."*
- **Do not chase `PROFILING` in the shipped library.** `set(PROFILING OFF)` — the stock
  `.so` emits zero Perfetto events. Requires `-DPROFILING=ON`.

---

## 6. Measurement plan — do this before optimising

MobileGlues ships the tooling; use it rather than building new.

```bash
# per-entry-point multidraw benchmark, headless, no tapping
adb shell am start -n com.fcl.plugin.mobileglues/.MainActivity \
    --es mg_bench all --es mg_angle borrow
```

It measures µs per draw call per entry point, ranks candidates by median with MAD/RSD,
re-measures noisy functions by doubling the scene, **discards any candidate whose
`g_md_fallback_tick` moved** (it wasn't actually served by the backend being measured),
and gates on all backends hashing the same framebuffer as `unroll` — *"a wrong picture at
any speed is not a candidate."*

Profiling stack, no vendor SDK needed, covers Adreno and Mali:

- **Perfetto** — `gpu.counters`, `gpu.renderstages`, `linux.ftrace`
- **Android GPU Inspector** — per-frame, with render-stage breakdowns

Watch **`% CP Overhead`** on Adreno: must stay under 20%, climbs toward 40% exactly when
draw-call and state counts hurt. Distinguish the two failure modes:

- GPU util < 100% **and** CPU idle **and** bubbles in GPU queue slices → a stall (a bug)
- CPU saturated in your functions at high GPU util → state-tracking cost (the real work)

---

## 7. Recommended order

**Compatibility first, because it is cheap and it gates everything.**

1. Ship the 126-symbol 26.3 set, GLES 3.2 target. Fold `glSamplerParameter*` onto bound
   textures. Synthesise `glLogicOp`, `glDrawPixels`, `GL_QUADS`, `glGetTexLevelParameteri`.
   Export both `glFoo` and `glFooARB`/`EXT`.
2. **Make symbol address identity hold across every lookup path** — `dlsym` on the library,
   `eglGetProcAddress`, and `SDL_GL_GetProcAddress` must all return the same pointer.
   This is the 26.3 gate and it is not a feature.
3. Negative shader caching + `glsl_type` in the key. Two small changes, largest measured
   win in the cache path.
4. Then, and only then, measure with `mg_bench` + AGI before touching the draw path.

**Defer:** DSA, multi-draw, indirect draw, clip_control. MC falls back for all of them.
Each is a speed purchase, not a correctness requirement, and each is device-specific —
which is why the maintainer offers it as a per-device choice rather than a default.

---

## 8. Honest limits of this research

- **No project publishes ms/frame or CPU-µs-per-draw tables.** ANGLE publishes zero
  overhead tables of its own; Mesa none; DXVK publishes intent, not data. The
  measured figures here are point measurements from issue trackers and vendor docs.
- **No A/B decomposition of a GLES compat layer's overhead** into CPU-state vs GPU-stall
  vs shader-compile. That number has to be measured in-house.
- **No published benchmark numbers or leaderboard from MobileGlues itself**, by design.
- **No measured FSR1 benefit** anywhere.
- The `glGetError` address-identity root cause is confirmed from the *check MC performs*
  and the maintainer's statement; the internal mechanism inside MG was not traced.
- Pre-1.13 support is effectively abandoned upstream — the maintainer states MG "likely"
  will not reach 1.12.2.