# ref/ — upstream MobileGlues, with selected PRs applied

Base: `MobileGL-Dev/MobileGlues` @ `97558a6` (the 2.0.0 line), plus three
community PRs merged on top. Their original commit SHAs are preserved below so
each change can be traced back to its author.

## Applied

| PR | Author | SHAs | What | Why |
|----|--------|------|------|-----|
| #61 | HEBEI77 | `6072625`, `951ffeb` | Depth textures stay filter-complete on strict ES hosts | MC 26.x transparency sorting. Mojang's `GlSampler` emits `GL_NEAREST_MIPMAP_LINEAR` (9986); ES 3.0 filter-completeness then rejects the `D32F` layer textures, sampling returns 0.0, and under reversed-Z that is *infinitely far*, so the sort collapses — clouds through terrain. Reported by Gsjsjzhznsz in issue #57. |
| #59 | ALLEN201123 | — | Null-pointer crash in `glGetString` | `SIGSEGV` on MC 26.3. |
| #50 | ryanmur f | — | Resolve GL symbols via `RTLD_SELF`, not `RTLD_NEXT` | `RTLD_NEXT` finds the library's own exports and recurses. Scoped to the Apple/glx path, so inert on Android — but it is the rule the Android path has to follow. |

## Deliberately not applied

| PR | Why |
|----|-----|
| #49 | `GL_DEPTH_COMPONENT32` → `GL_DEPTH_COMPONENT32F` is already in `main` at `texture.cpp:506`. Superseded. |
| #48 | "a bit cringe and hardcoded but it gets 26.3-snapshot4 to run". A band-aid for one version, and it conflicts with `main`. |
| #3, #9 | 2025-era, conflict with `main`, and `main` has since grown the same functionality. |
| #54, #51, #24, #6 | iOS scope. |
| #45, #43, #19, #35, #52, #60, #53 | Already merged into `main`. |

## 26.3 fixes people cite that are not recoverable

`DNAMobileApplications/MobileGlues-plugin-towo` carries two commits titled
"Fixed 26.3 Snapshot 9" and "Fixed a performance regression with 26.3". Both are
one-line **submodule pointer bumps**. The commits they point at (`a12aadc6`,
`b37a1735`) no longer exist in `MobileGL-Dev/MobileGlues` — the `pluginindex`
branch was deleted or force-pushed — and `git fetch` rejects both as
"not our ref". Only the accompanying version bump to 2.0.3 survives. There is no
code there to merge.

`Gsjsjzhznsz/MobileGlues-plugin`, the fork issue #57 points at, contains only
device logs and a GLSL cache (`fcl.log`, `latest.log`, `glsl_cache.tmp`). No
source. The fix reached upstream as PR #61.

## Still open upstream, 26.3

- **release#474** — Adreno 640: `minecraft:core/terrain` fails to compile under
  Fabric so blocks never render; with Sodium and ANGLE off, a driver crash in
  `glDrawArraysInstanced`. MediaTek/Mali: black on every backend.
- **release#471** — transparent blocks in 26.3.
- **release#468 / #466** — "26.3 released, MG does not support it".
