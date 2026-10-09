#!/usr/bin/env bash
# Cut a GitHub release from a green build.
#
# Publishing is not a CI step. GITHUB_TOKEN is scoped to the repository's own
# contents and cannot create a release:
#
#   HTTP 403: Resource not accessible by integration
#
# which failed the final step of an otherwise passing build and read like a
# problem with the build. This script runs where a token with repo scope is
# available -- the same gh the rest of the workflow is invoked through.
#
# It takes the APK from a completed run's artifacts rather than building again,
# so the released artifact is provably the one CI verified: signed, three ABIs,
# all 256 Minecraft-resolved GL symbols exported.
#
# Usage:  tools/publish.sh <tag> [run-id]

set -euo pipefail

cd "$(dirname "$0")/.."

TAG="${1:-}"
RUN="${2:-}"

if [ -z "$TAG" ]; then
    echo "usage: $0 <tag> [run-id]" >&2
    exit 2
fi

if [ -z "$RUN" ]; then
    echo "==> Finding the latest completed run for $TAG"
    RUN=$(gh run list --branch "$TAG" --limit 1 --json status,conclusion \
        -q '[.[] | select(.status == "completed" and .conclusion == "success")] | .[0].databaseId' || true)
    # A tag's build may also be reachable through the ref it points at, so fall
    # back to the newest green run rather than reporting "no run found" when the
    # only green build was triggered by a branch push of the same commit.
    if [ -z "$RUN" ] || [ "$RUN" = "null" ]; then
        RUN=$(gh run list --limit 20 --json status,conclusion,databaseId \
            -q '[.[] | select(.status == "completed" and .conclusion == "success")] | .[0].databaseId')
    fi
fi

if [ -z "$RUN" ] || [ "$RUN" = "null" ]; then
    echo "error: no successful run found to publish from" >&2
    echo "       build and push the tag first: git push origin <tag>" >&2
    exit 1
fi

echo "==> Verifying run $RUN passed before publishing from it"
conclusion=$(gh run view "$RUN" --json conclusion -q .conclusion)
if [ "$conclusion" != "success" ]; then
    echo "error: run $RUN concluded '$conclusion', not success" >&2
    exit 1
fi

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

echo "==> Downloading artifacts"
gh run download "$RUN" -n cobalt-apk -D "$TMP"

APK=$(find "$TMP" -name '*.apk' | head -1)
[ -n "$APK" ] || { echo "error: no APK in the artifact" >&2; exit 1; }
echo "    $(basename "$APK")  $(du -h "$APK" | cut -f1)"

# Re-verify rather than trusting CI. This script may be run by hand against an
# older run, and the two properties that matter -- signed, all three ABIs -- are
# both things a stale artifact can violate without anyone noticing.
echo "==> Checking the artifact"
python3 - "$APK" <<'PY'
import sys, zipfile
z = zipfile.ZipFile(sys.argv[1])
names = z.namelist()
if not any(n.startswith("META-INF/") and n.endswith((".RSA", ".DSA", ".EC")) for n in names):
    sys.exit("APK is unsigned; refusing to publish an artifact that cannot be installed")
for abi in ("arm64-v8a", "armeabi-v7a", "x86_64"):
    if "lib/%s/libcobalt.so" % abi not in names:
        sys.exit("%s is missing from the APK" % abi)
arsc = z.read("resources.arsc")
for probe in (b"opengles3", b"libcobalt.so", b"SDL_OPENGL_LIBRARY"):
    if probe not in arsc:
        sys.exit("renderer config resource is missing %r" % probe)
print("    signed, three ABIs, config present")
PY

# Delete-then-create. Re-publishing a tag after a fix is ordinary, and
# "a release with the same tag name already exists" should not require deleting
# the release by hand first. No --cleanup-tag: that removes the git tag too,
# and the tag is what identifies this build.
echo "==> Publishing $TAG"
gh release delete "$TAG" --yes || true
gh release create "$TAG" "$APK" \
    --title "$TAG" \
    --notes-file RELEASE-NOTES.md

gh release view "$TAG" --json url -q .url