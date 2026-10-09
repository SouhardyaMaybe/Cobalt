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
    if git -C ref/mobileglues apply --check -p1 "$p"; then
        git -C ref/mobileglues apply -p1 "$p"
        echo "    $(basename "$p")"
    elif git -C ref/mobileglues apply --reverse --check -p1 "$p"; then
        echo "    $(basename "$p")  (already applied)"
    else
        # Not silenced. "does not apply" on its own is unactionable: the useful
        # information is the context mismatch git already printed above it.
        echo "error: $(basename "$p") does not apply to ref/mobileglues" >&2
        echo "       patches are written against pristine upstream MobileGlues" >&2
        echo "       $(git -C ref/mobileglues rev-parse --short HEAD)" >&2
        exit 1
    fi
done

# The rebrand runs after the patches, not before. Patches are written against
# pristine upstream, so anything that rewrites the sources first would make them
# fail to apply. tools/rebrand.py is idempotent, so this ordering costs nothing.
echo "==> Rebranding to Cobalt"
python3 tools/rebrand.py "$SRC"

# The launcher's config must reach it as an Android string resource, and the
# resource has to exist before Gradle configures. Validating here means a bad
# config fails the build with a reason rather than the launcher silently
# skipping the plugin on a user's device.
echo "==> Generating the launcher config resource"
python3 tools/gen-config.py plugin/config/cobalt-renderer.json plugin/build/generated/res

echo "==> Configuring ($API, minSdk $MIN_API)"
cmake -B "$BUILD" -S "$SRC" \
    -DCMAKE_TOOLCHAIN_FILE="$ANDROID_NDK_HOME/build/cmake/android.toolchain.cmake" \
    -DANDROID_ABI="$COBALT_ABI" \
    -DANDROID_PLATFORM="android-$API" \
    -DANDROID_STL="c++_shared" \
    -DCMAKE_BUILD_TYPE=Release \
    -DPROFILING=OFF

echo "==> Building"
cmake --build "$BUILD" --config Release -j "$(nproc)"

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

echo "==> Symbols"
for abi in arm64-v8a armeabi-v7a x86_64; do
    so="$ROOT/$OUT/$abi/libcobalt.so"
    [ -f "$so" ] || { echo "  $abi  MISSING"; exit 1; }
    gl=$(nm -D --defined-only "$so" | grep -cE ' T gl[A-Z]' || true)
    egl=$(nm -D --defined-only "$so" | grep -cE ' T egl' || true)
    # MobileGlues must export the platform GL too, or MG's own internal calls
    # resolve to the system driver and silently bypass all state tracking.
    # -Bsymbolic-functions is what prevents that; see CMakeLists.txt.
    echo "  $abi  gl*=$gl  egl*=$egl  $(du -h "$so" | cut -f1)"
done