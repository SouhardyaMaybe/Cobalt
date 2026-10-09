#!/usr/bin/env bash
# Generate a signing key for the plugin APK, if there is not one already.
#
# The APK has to be signed to be installable, and the launcher finds renderer
# plugins by querying installed packages -- so an unsigned artifact cannot be
# tested at all, which makes this a prerequisite for the build rather than a
# release-time concern.
#
# The key is generated, not committed. A signing key in a repository is a
# published secret; this one is debug-grade and exists so a build produces
# something installable. Every CI run therefore produces a different signature,
# which means reinstalling over an existing install requires uninstalling
# first. That is noted in plugin/build.gradle.kts next to the config that uses
# it, rather than discovered later.

set -euo pipefail

cd "$(dirname "$0")/.."

KEY="plugin/cobalt-debug.jks"
ALIAS="${COBALT_KEY_ALIAS:-cobalt}"
PASS="${COBALT_KEY_PASSWORD:-cobalt}"

if [ -f "$KEY" ]; then
    echo "==> $KEY already exists"
    exit 0
fi

# keytool ships with the JDK that CI has already set up, so there is no extra
# dependency to install.
command -v keytool >/dev/null || {
    echo "error: keytool not found; is a JDK on PATH?" >&2
    exit 1
}

echo "==> Generating $KEY"
keytool -genkeypair \
    -keystore "$KEY" \
    -storepass "$PASS" \
    -keypass "$PASS" \
    -alias "$ALIAS" \
    -keyalg RSA \
    -keysize 2048 \
    -validity 10000 \
    -dname "CN=Cobalt Wrapper, OU=Development, O=Cobalt, L=, ST=, C=" \
    2>&1 | grep -v "^Warning:" || true

# Never let a key reach the repository. .gitignore covers it; this asserts it.
#
# Checked with git check-ignore rather than by grepping .gitignore for the
# filename: the ignore rule is a glob (plugin/*.jks), so a substring match
# reports the key as unignored while git ignores it correctly. Asking git is
# the only version of this question that cannot be wrong.
git check-ignore -q "$KEY" || {
    echo "error: $KEY is not excluded by .gitignore" >&2
    echo "       a committed signing key is a published secret" >&2
    exit 1
}

echo "==> done (alias $ALIAS, password $PASS)"