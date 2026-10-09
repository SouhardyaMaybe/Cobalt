#!/usr/bin/env bash
# Run the settings-install test: the file IO that decides whether the renderer finds
# a usable config.json.
#
# Separate from tools/test-config.sh, which checks that the file's contents are
# readable. This one checks that it gets written.
#
# Deliberately not part of the Gradle build. It needs a Kotlin compiler and
# android.jar, and locating those means digging through the Gradle cache, whose
# contents depend on what else has been built -- so it runs on whatever it finds and
# skips loudly when it finds nothing, rather than failing the build for a reason that
# has nothing to do with the code.
#
# In CI the Gradle build itself is the real check: it compiles these same sources
# against the real Android SDK. This exists so the logic can be exercised without a
# device.

set -euo pipefail

cd "$(dirname "$0")/.."
ROOT="$PWD"

if [ ! -f "$ROOT/plugin/config/cobalt-settings.json" ]; then
    echo "SKIP: plugin/config/cobalt-settings.json not found (run build-android.sh first)"
    exit 0
fi

gradle_cache="${GRADLE_USER_HOME:-$HOME/.gradle}/caches/modules-2"

find_jar() {
    # Newest match wins: the cache holds several versions of each.
    find "$gradle_cache" -name "$1" 2>/dev/null | sort -V | tail -1
}

# The compiler and the stdlib must be the same version. Taking the newest of each
# independently pairs a 2.4.20 compiler with a 2.1.10 stdlib, which the compiler
# rejects after a long startup -- and the resulting message names neither version.
# Read the version out of the compiler's path and match it.
KOTLINC=$(find_jar "kotlin-compiler-embeddable-*.jar")
[ -n "$KOTLINC" ] || {
    echo "SKIP: no Kotlin compiler in the Gradle cache; the Gradle build covers this"
    exit 0
}
KVER=$(basename "$KOTLINC" | sed 's/^kotlin-compiler-embeddable-//; s/\.jar$//')
STDLIB=$(find_jar "kotlin-stdlib-$KVER.jar")
if [ -z "$STDLIB" ]; then
    echo "SKIP: kotlin-compiler-embeddable $KVER but no matching kotlin-stdlib $KVER"
    exit 0
fi

TROVE=$(find_jar "trove4j-*.jar")
COROUTINES=$(find_jar "kotlinx-coroutines-core-jvm-*.jar")
ANNOTATIONS=$(find_jar "annotations-13.0.jar")

# android.jar for the android.content.Context import in CobaltSettings. Stubs only,
# which is why the tested function is free of Android types.
ANDROID_JAR="${ANDROID_JAR:-}"
if [ -z "$ANDROID_JAR" ]; then
    for sdk in "${ANDROID_HOME:-}" "${ANDROID_SDK_ROOT:-}" /opt/android-sdk /usr/lib/android-sdk; do
        [ -n "$sdk" ] || continue
        ANDROID_JAR=$(ls -1 "$sdk"/platforms/android-*/android.jar 2>/dev/null | sort -V | tail -1 || true)
        [ -n "$ANDROID_JAR" ] && break
    done
fi
[ -n "${ANDROID_JAR:-}" ] && [ -f "$ANDROID_JAR" ] || {
    echo "SKIP: no android.jar found; set ANDROID_JAR to run this locally"
    exit 0
}

WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT

echo "compiler: kotlin $KVER"
echo "android:  $(basename "$(dirname "$ANDROID_JAR")")"

java -cp "$KOTLINC:$STDLIB:$TROVE:$COROUTINES:$ANNOTATIONS" \
    org.jetbrains.kotlin.cli.jvm.K2JVMCompiler \
    "$ROOT/plugin/src/main/java/me/shadow/cobalt/CobaltSettings.kt" \
    "$ROOT/tools/test-settings-install.kt" \
    -no-stdlib -no-reflect \
    -cp "$STDLIB:$ANDROID_JAR" \
    -d "$WORK/classes" \
    -nowarn

# Named for the file, not guessed: a wrong name fails with ClassNotFoundException and
# says nothing about the code under test.
MAIN=$(cd "$WORK/classes" && find . -name '*Kt.class' | sed 's|^\./||; s|\.class$||; s|/|.|g')
[ -n "$MAIN" ] || { echo "error: no compiled class found in $WORK/classes" >&2; exit 1; }
java -cp "$WORK/classes:$STDLIB:$ANDROID_JAR" "$MAIN"