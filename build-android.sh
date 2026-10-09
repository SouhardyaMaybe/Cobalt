#!/usr/bin/env bash
# Build libcobalt.so — the Cobalt Wrapper renderer.
#
# Cobalt is MobileGlues' C++ core with targeted fixes applied in-tree. It is
# built as a single library because that is the contract the launcher expects:
# the plugin names one file for both rendererGLPath and rendererEGLPath, and the
# launcher resolves GL through that library's own eglGetProcAddress. Two
# libraries would give one symbol two addresses, which is exactly the failure
# that blocks Minecraft 26.3's own startup check.
#
# Local builds need ANDROID_NDK_HOME. CI sets it up.

set -euo pipefail

cd "$(dirname "$0")"
ROOT="$PWD"

: "${ANDROID_NDK_HOME:?set ANDROID_NDK_HOME to your NDK root}"
API="${COBALT_API:-26}"
MIN_API="${COBALT_MIN_API:-21}"
OUT="${1:-plugin/src/main/jniLibs}"
SRC="ref/mobileglues/MobileGlues-cpp"
cd "$ROOT"

# The submodules are glslang, SPIRV-Cross and xxhash. All three are required:
# the shader path is glslang -> SPIR-V -> SPIRV-Cross, and dropping any of them
# removes shader translation entirely.
if [ ! -d "$SRC/3rdparty/glslang" ]; then
    echo "error: submodules missing. Run: git submodule update --init --recursive" >&2
    exit 1
fi

BUILD="build-android"

# Cobalt's changes to the renderer live as patches, so the delta against
# upstream stays reviewable as a diff rather than buried in a vendored copy.
# Applied before configure because CMake reads the sources.
echo "==> Applying Cobalt patches"
shopt -s nullglob
for p in "$ROOT"/patches/*.patch; do
    # Absolute path: git -C changes directory before reading the patch file, so
    # a repo-relative one would be looked up inside the submodule, where
    # patches/ does not exist.
    # CI builds three ABIs in one checkout, so the second and third runs find
    # the patches already applied. That is the normal path, not an error, so
    # git's "patch does not apply" is expected there and is redirected rather
    # than left to look like a failure next to the real one below.
    if git -C ref/mobileglues apply --reverse --check -p1 "$p" 2>/dev/null; then
        echo "    $(basename "$p")  (already applied)"
    elif git -C ref/mobileglues apply --check -p1 "$p" 2>/dev/null; then
        git -C ref/mobileglues apply -p1 "$p"
        echo "    $(basename "$p")"
    else
        # Re-run without the redirect, so the context mismatch git would have
        # reported is actually printed. "does not apply" on its own is
        # unactionable; the three lines of context above it are the diagnosis.
        git -C ref/mobileglues apply --check -p1 "$p" || true
        echo "error: $(basename "$p") does not apply to ref/mobileglues" >&2
        echo "       patches are written against pristine upstream MobileGlues" >&2
        echo "       $(git -C ref/mobileglues rev-parse --short HEAD)" >&2
        exit 1
    fi
done

# The rebrand runs after the patches, not before. Patches are written against
# pristine upstream, so anything that rewrites the sources first would make them
# fail to apply. tools/rebrand.py is idempotent, so this ordering costs nothing.
# New source files ship as whole .cpp files rather than patches. A patch adding
# a file is a diff with no pre-image, which git apply handles awkwardly and a
# reviewer cannot read; a file is just the file. They are copied in here, before
# the rebrand, so tools/rebrand.py sees them like any other source.
echo "==> Adding Cobalt sources"
shopt -s nullglob
for f in "$ROOT"/src/*.cpp; do
    b=$(basename "$f")
    cp "$f" "$SRC/gl/$b"
    # CMake compiles only what CMakeLists.txt lists. A source file that is not
    # listed compiles cleanly, exports nothing, and every symbol check still
    # passes -- so the list entry is added here, not left to be remembered.
    #
    # Anchored on gl/mg.cpp, upstream's own spelling, because this step runs
    # before the rebrand and the list has not been renamed yet. An earlier
    # version anchored on gl/cobalt.cpp and failed on every run with "not in
    # CMakeLists.txt after insertion" -- the file was inserted, just not where
    # the anchor was looking. A third attempt used \\(cobalt\|mg\) to cover
    # both spellings; GNU sed reads that as a literal inside the group, so it
    # matched nothing and failed silently instead of loudly.
    if ! grep -q "gl/$b" "$SRC/CMakeLists.txt"; then
        sed -i "0,/^    gl\/mg\.cpp$/s|    gl/mg\.cpp|    gl/$b\\n&|" "$SRC/CMakeLists.txt"
    fi
    grep -q "gl/$b" "$SRC/CMakeLists.txt" || {
        echo "error: gl/$b is not in CMakeLists.txt after insertion" >&2; exit 1; }
    echo "    gl/$b"
done

echo "==> Rebranding to Cobalt"
python3 tools/rebrand.py "$SRC"

# The launcher's config must reach it as an Android string resource, and the
# resource has to exist before Gradle configures. Validating here means a bad
# config fails the build with a reason rather than the launcher silently
# skipping the plugin on a user's device.
echo "==> Generating the launcher config resource"
python3 tools/gen-config.py plugin/config/cobalt-renderer.json plugin/generated/res

echo "==> Configuring ($API, minSdk $MIN_API)"
cmake -B "$BUILD" -S "$SRC" \
    -DCMAKE_TOOLCHAIN_FILE="$ANDROID_NDK_HOME/build/cmake/android.toolchain.cmake" \
    -DANDROID_ABI="$COBALT_ABI" \
    -DANDROID_PLATFORM="android-$API" \
    # c++_static, not c++_shared, and not by preference.
    #
    # A shared-libc++ build puts "NEEDED libc++_shared.so" in the .so and leaves
    # every __ndk1 symbol undefined. That library is in neither the APK nor
    # LD_LIBRARY_PATH -- a plugin's lib directory is not on it -- so dlopen
    # fails on the first C++ symbol it touches:
    #
    #   cannot locate symbol "_ZTVNSt6__ndk119basic_ostringstreamIcE..."
    #
    # which is what the first device run reported. Static libc++ embeds the
    # symbols; it costs a couple of MB per ABI and needs nothing from the host.
    #
    # Upstream's CMakeLists also says c++_static, so this matches it rather than
    # overriding it.
    -DANDROID_STL="c++_static" \
    -DCMAKE_BUILD_TYPE=Release \
    -DPROFILING=OFF

echo "==> Building"
# --verbose so the link command is in the log. Two rounds of chasing a symbol
# problem through guesswork were resolved the moment the real command was
# visible; the linker flags are the whole question and they were hidden.
cmake --build "$BUILD" --config Release -j "$(nproc)" --verbose

echo "==> Staging to $OUT/$COBALT_ABI"
mkdir -p "$ROOT/$OUT/$COBALT_ABI"
# The output name follows CMake's project(), which tools/rebrand.py rewrites to
# "cobalt", so the artifact is already libcobalt.so. Nothing needs renaming
# here -- and nothing should: a rename step is one more place the library name
# and the plugin config can drift apart.
#
# Derived from project() rather than hardcoded, so if the rebrand ever stops
# rewriting it, the error is "no such file" naming the real path instead of a
# copy step that silently ships the wrong name.
SO="$BUILD/lib$(sed -n 's/^project("\(.*\)")$/\1/p' "$SRC/CMakeLists.txt" | head -1).so"
if [ ! -f "$SO" ]; then
    echo "error: expected $SO. CMake's project() name drives the output name;" >&2
    echo "       project() in $SRC/CMakeLists.txt is: $(sed -n 's/^project(.*/&/p' "$SRC/CMakeLists.txt" | head -1)" >&2
    exit 1
fi
install -m 755 "$SO" "$ROOT/$OUT/$COBALT_ABI/libcobalt.so"

# Strip. The build carries -g (upstream puts it in CMAKE_CXX_FLAGS), which leaves
# roughly 48 MB of DWARF per ABI: 54 MB here against 5.9 MB for the stripped
# TOWO builds of the same renderer that run on this device.
#
# Only --strip-unneeded, which removes debug and symbol-table entries but keeps
# the dynamic symbol table. That table is the product -- dlsym resolves glGetError
# and 4900 other names through it -- so this cannot use plain --strip.
strip_tool="$ANDROID_NDK_HOME/toolchains/llvm/prebuilt/linux-x86_64/bin/llvm-strip"
[ -x "$strip_tool" ] || strip_tool=$(command -v llvm-strip || command -v strip)
"$strip_tool" --strip-unneeded "$ROOT/$OUT/$COBALT_ABI/libcobalt.so"

# Reports the ABI that was just built, not all three. CI invokes this once per
# ABI, so asserting the others are present here failed on the first invocation
# with "armeabi-v7a MISSING" -- the ABI had not been attempted yet.
#
# Cross-ABI completeness is checked once, at the end, by the workflow's audit
# step. Splitting it that way keeps each check next to the thing it verifies.
echo "==> Symbols ($COBALT_ABI)"
so="$ROOT/$OUT/$COBALT_ABI/libcobalt.so"
gl=$(nm -D --defined-only "$so" | grep -cE ' T gl[A-Z]' || true)
egl=$(nm -D --defined-only "$so" | grep -cE ' T egl' || true)
# The renderer must export the platform GL symbols too, not just its own
# wrappers. Without -Bsymbolic-functions its internal calls bind to the system
# driver's libGLESv2 instead, so state tracking is bypassed everywhere and the
# translation is silently a no-op.
echo "  gl*=$gl  egl*=$egl  $(du -h "$so" | cut -f1)"
