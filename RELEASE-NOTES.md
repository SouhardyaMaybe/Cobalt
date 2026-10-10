Cobalt Wrapper v0.4.0

Minecraft 26.3 works. Everything after this is cleanup.

The shader bug is fixed and confirmed on device -- no compile errors, no failed
pipelines, world renders, multiplayer connects. That was v0.3.2.

What is in this release is the three things your log showed that were real, plus the
guards that stop them coming back. None of them changed how anything renders.

1. The renderer was running on default settings

Your log said:

    Failed to load config. Use default config.
    [Cobalt] Setting: maxGlslCacheSize            = 0

No config file was shipped, so the renderer fell back to defaults. It does that
quietly: config_get_int() answers -1 for a key it cannot read, and the settings code
reads -1 as "the config did not say" rather than as an error. The visible cost was a
disabled shader cache -- and with it the negative cache, so a shader that fails to
compile is retried on every resource reload, and Minecraft reloads resources every time
you change dimension.

The settings now ship with the plugin and are installed on first launch. Everything is
at the value it was already using, apart from the cache, which is now on.

2. The plugin said it was 0.1.0

You noticed this. It was hardcoded at 0.1.0 in build.gradle.kts and never changed for
six releases, so v0.3.2's App info screen said 0.1.0. Nothing caught it because the
build did exactly what it was told -- there was just nothing asking for the right
answer.

VERSION is now the single source. CI reads the version back out of the built APK and
fails if it disagrees, so this cannot recur silently.

3. A comment explaining what the remaining log lines are

Not every warning is ours. `Couldn't leave fullscreen`, `Failed to set window icon`,
the udev and /proc warnings and the "unexpected shutdown ... resetting fullscreen mode"
note from the previous crashed run come from Zalith, SDL or the Android sandbox.
`Can't ping mcpvp.net` is DNS.

One is worth keeping: `Not Detected GL_EXT_multi_draw_indirect!` is a true statement
about your Adreno 613, and the multi-draw order in the log is the renderer filtering
itself down to what the device can actually do -- `unroll` for arrays is that working
correctly, since unroll is the one backend every device has. Silencing that message
would only hide why the order is what it is.

The version check needed its own parser

Reading the APK's version meant `aapt`, which cannot read this APK: resolving the
manifest's `@android:drawable/ic_menu_rotate` needs the framework resource table, and
without it aapt fails with "attribute value reference does not exist" -- which reads
like a broken manifest and cost a build.

tools/apk-version.py reads the binary manifest directly instead. It is tested against
a real one, kept in tools/apk-fixtures/, because that is what found the bug: the parser
handled UTF-8 string pools and every real APK uses UTF-16, where it dropped the first
character of every string. Reintroducing that bug fails 8 assertions.

The pattern across this project, which is why these are worth reading

Every one of the failures above produced a green build or, worse, a check that passed
without checking anything:

- a missing GLAPI compiles, links, and is then garbage-collected
- a missing extern "C" means every dlsym misses it
- comm(1) reported 29 missing symbols when all were exported
- a shader pass corrupted every 26.3 shader and no audit could see it
- a JSON file the renderer could not read looked identical to no file
- a config staged into jniLibs was silently dropped by AGP
- a version parser that could not read an APK reported no version and exited 0
- a test suite built its fixtures the way the code read them, so a wrong assumption
  was confirmed by both sides

So CI now runs four host-side suites before the build, and every claim in a release
note is checked against the built artifact rather than against the inputs. Where a
check could have passed vacuously it is verified that it fails when the defect is
put back.

Uninstall v0.3.2 first: each build signs with a new key, so Android will not upgrade
over it.