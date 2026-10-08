# towo-builds/ — DNAMobileApplications' 26.3 fixes, recovered from binaries

The source for these fixes is **gone**. `DNAMobileApplications/MobileGlues-plugin-towo`
carries three commits, each a one-line *submodule pointer bump*, and the commits
they point at (`a12aadc6`, `b37a1735`) no longer exist in
`MobileGL-Dev/MobileGlues` — the `pluginindex` branch was deleted or force-pushed.
`git fetch` rejects both as "not our ref", and the object is not recoverable from
any fork in the network.

The **builds** survive, though, as release APKs. Those are what is in this folder:
the arm64 `libmobileglues.so` from each release, plus the 2.0.3 APK.

## What each release claims

| Tag | Date | Claim |
|-----|------|-------|
| `2.0.1-fork` | 2026-08-23 | "Fixed the **invisible blocks** rendering in 26.3 Snapshot 9" · "Fixed black screen rendering with The Broken Script Mod 1.21.1 NeoForge" |
| `2.0.2-fork` | 2026-09-16 | "Fixed performance regression with certain devices for 26.3" |
| `2.0.3-fork` | 2026-09-29 | "Add a **shader compatibility layer**" — issues with 26.3 |

## What the binaries show

`strings` over the three libraries, diffed, shows what was added. These are the
new diagnostic strings, so they are the author's own description of the change:

**Shader compatibility (2.0.3)** — the largest addition:
```
[Shader] Mali renderer detected; dynamic fragment output-array compatibility enabled (%s).
[Shader] Mali fragment output-array workaround rewrote %zu dynamic read(s).
[Shader] Mali fragment output-array workaround rewrote %zu dynamic store(s).
[Shader] Mali dynamic-array fallback found %zu candidate array(s).
[Shader] Mali dynamic-read rewrite rejected; store-only retry succeeded for shader %u.
```
A GLSL rewriter for Mali: dynamic fragment output arrays get rewritten, with a
store-only retry when the read rewrite is rejected. This is a compile-time fix,
which is why it shows up as "invisible blocks" rather than a crash — the shader
fails to build and the block is simply not drawn.

**Clip control / depth range (present by 2.0.3)**:
```
[DroidBridge modern depth] GL_ARB_clip_control exposed to Minecraft 26.2+
[DH26.2 CLIP FIX v2] GL_EXT_clip_control unavailable; applied one-time DH terrain ZERO_TO_ONE shader fallback shader=%u
[DH26.2 DRAW TEST] glMultiDrawArraysIndirect drawcount=%d stride=%d backend=indirect-loop
```
Exposes `GL_ARB_clip_control` / `GL_EXT_clip_control`, with a shader fallback when
the extension is missing. Distant Horizons specific.

**Mali colour / sRGB**:
```
[Color] Mali sRGB state: renderer=%s sRGB_write_control=%d desktopRequested=%d driverEnabled=%d linearWindowFallback=%d
[Color] Mali window-surface request failed (EGL error=0x%x); retrying original attributes.
```
Without `GL_EXT_sRGB_write_control`, forces the window surface colourspace to
LINEAR to match desktop GL's initial `GL_FRAMEBUFFER_SRGB=false`.

**Texture binding hardening**:
```
[MobileGlues] Safe texture binding enabled (MG_SAFE_TEXTURE_BIND=1)
glBindTexture: rejecting invalid bind target %s (0x%X)
glBindTexture: GLES glActiveTexture entry point is unavailable for texture-buffer emulation
```

**Extension exposure**: `GL_ARB_clip_control`, `GL_EXT_clip_control`, plus
`multisample_compatibility`, `clip_cull_distance`, `depth_clamp`,
`sRGB_write_control`, `NV_polygon_mode`, `OES_sample_shading`.

Env switches the build honours: `MG_SAFE_TEXTURE_BIND`, `MG_ANGLE_DIR`,
`MG_MOBILEGLUES_VERSION`, `MG_COUNT_LAUNCH`, `MG_BENCH_*`.

## Relationship to PR #61

Different bugs. PR #61 (applied in `ref/`) is depth-filter completeness:
`GL_NEAREST_MIPMAP_LINEAR` making `D32F` textures filter-incomplete, which breaks
26.x transparency sorting. The TOWO builds do **not** contain that work — no
depth-filter strings appear in any of the three libraries.

So the two are complementary, not alternatives. If 26.3 blocks are invisible on a
Mali device, that is TOWO. If terrain sorts wrongly and clouds render through
blocks, that is #61.

## Caveat

These are compiled binaries, not source. The behaviour is recoverable; the code
is not. Reimplementing from the diagnostic strings is feasible but is a
reimplementation, not a merge, and anything inferred this way should be treated
as a hypothesis to test on device rather than as a known-correct fix.

The 2.0.3 library exports 3,059 `gl*` entry points on arm64.