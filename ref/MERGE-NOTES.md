# ref/ — upstream MobileGlues, with selected PRs applied

Base: `MobileGL-Dev/MobileGlues` @ `97558a6` (v2.0.0 line).

## Applied

| PR | Author | What | Why |
|----|--------|------|-----|
| #61 | HEBEI77 | Depth textures stay filter-complete on strict ES hosts | MC 26.x transparency sorting. Mojang's `GlSampler` emits `GL_NEAREST_MIPMAP_LINEAR` (9986); ES 3.0 filter-completeness then rejects the `D32F` layer textures, sampling returns 0.0, and under reversed-Z that is *infinitely far*, so sorting collapses — clouds through terrain. Reported by Gsjsjzhznsz in #57, implemented upstream here. |
| #59 | ALLEN201123 | Null-pointer crash in `glGetString` | `SIGSEGV` on MC 26.3. |
| #50 | ryanmur f | Resolve GL symbols via `RTLD_SELF`, not `RTLD_NEXT` | `RTLD_NEXT` finds the library's own exports and recurses. Scoped to the Apple/glx path, so it is inert on Android, but the reasoning is the rule the Android path has to follow. |

## Deliberately not applied

| PR | Why not |
|----|---------|
| #49 | `GL_DEPTH_COMPONENT32` → `GL_DEPTH_COMPONENT32F` is already in `main` at `texture.cpp:506`. Superseded. |
| #48 | "This is a bit cringe and hardcoded but it gets 26.3-snapshot4 to run." A band-aid against one version. Conflicts with `main`. |
| #3, #9 | From 2025, conflict with `main`, and `main` has since grown the same functionality (`GL_TEXTURE_LOD_BIAS`, `glUnmapBuffer`). |
| #54, #51, #24, #6 | iOS scope. |
| #45, #43, #19, #35, #52, #60, #53 | Already merged into `main`. |

## Not recoverable

`DNAMobileApplications/MobileGlues-plugin-towo` claims two 26.3 fixes
("Fixed 26.3 Snapshot 9", "Fixed a performance regression with 26.3"). Both are
one-line **submodule pointer bumps**, and the commits they point at
(`a12aadc6`, `b37a1735`) no longer exist in `MobileGL-Dev/MobileGlues` — the
`pluginindex` branch was deleted or force-pushed. `git fetch` rejects both as
"not our ref". Only the accompanying version bump to 2.0.3 survives.

`Gsjsjzhznsz/MobileGlues-plugin` — the fork that #57 refers to — contains only
device logs and a GLSL cache (`fcl.log`, `latest.log`, `glsl_cache.tmp`). No
source. The actual fix reached upstream as PR #61.

## Still open upstream, 26.3

- release#474 — Adreno 640: `minecraft:core/terrain` fails to compile under
  Fabric, blocks do not render; with Sodium and ANGLE off, driver crash in
  `glDrawArraysInstanced`. MediaTek/Mali: black on every backend.
- release#471 — transparent blocks in 26.3.
- release#468 / #466 — "26.3 released, MG does not support it".
