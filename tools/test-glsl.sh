#!/usr/bin/env bash
# Build and run the host-side regression tests for the GLSL translation passes.
#
# These run against ref/mobileglues with Cobalt's patches applied, i.e. the tree that
# actually gets compiled. Point them at the unpatched tree to see upstream behave:
#
#     GLSSL_SRC=ref/mobileglues/MobileGlues-cpp/gl/glsl/glsl_for_es.cpp tools/test-glsl.sh
#
# Deliberately not wired into build-android.sh: that script needs the NDK and builds
# for three ABIs. This one wants a desktop compiler and no submodules, so it can run
# on every push and still be the thing that catches a translation bug before a build
# does. Only the string passes are covered -- anything needing glslang or SPIRV-Cross
# to produce its input is out of reach here.

set -euo pipefail

cd "$(dirname "$0")/.."
ROOT="$PWD"

GLSL_SRC="${GLSSL_SRC:-$ROOT/ref/mobileglues/MobileGlues-cpp/gl/glsl/glsl_for_es.cpp}"
CXX="${CXX:-g++}"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

# Helper before caller: the extracted file has to compile as written.
python3 tools/extract-glsl-fn.py "$GLSL_SRC" \
    is_identifier_char,is_uniform_keyword,process_uniform_declarations \
    "$WORK/passes.inc"

"$CXX" -std=c++17 -O1 -Wall -Wextra -Werror -I"$WORK" \
    -o "$WORK/test-glsl-translation" tools/test-glsl-translation.cpp

"$WORK/test-glsl-translation"