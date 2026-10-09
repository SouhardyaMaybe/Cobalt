#!/usr/bin/env bash
# Check that the shipped renderer config is one the renderer can read.
#
# config/cJSON.c is compiled from the upstream tree rather than a vendored copy, so
# this tests the parser the renderer actually uses. That matters: the device log said
#
#     Failed to load config. Use default config.
#     [Cobalt] Setting: maxGlslCacheSize            = 0
#
# and nothing about that is a parse error the renderer reports. config_get_int()
# answers -1 for a key it cannot read, and init_settings() reads -1 as "the config
# did not say", so a malformed or absent key is indistinguishable from no config at
# all. Python saying the file is valid JSON does not establish that cJSON reads it.
#
# Runs anywhere with a C compiler; no NDK, no submodules beyond config/.

set -euo pipefail

cd "$(dirname "$0")/.."
ROOT="$PWD"

CONFIG="${1:-plugin/config/cobalt-settings.json}"
CJSON_DIR="ref/mobileglues/MobileGlues-cpp/config"
CC="${CC:-cc}"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

for f in cJSON.c cJSON.h; do
    [ -f "$CJSON_DIR/$f" ] || {
        echo "error: $CJSON_DIR/$f not found" >&2
        exit 1
    }
done

# Compiled separately because the two are different languages: the test is C++ and
# cJSON is C, and one -std flag cannot be right for both. Passing both sources to one
# invocation also risks the driver treating a .c as C++ if CC is a C++ compiler.
"$CC" -std=c11 -O1 -c -I"$CJSON_DIR" -o "$WORK/cJSON.o" "$CJSON_DIR/cJSON.c"
"$CC" -std=c++17 -O1 -Wall -Wextra -Werror -Wno-unused-result \
    -I"$CJSON_DIR" -o "$WORK/test-config" tools/test-config.cpp "$WORK/cJSON.o" -lm

"$WORK/test-config" "$CONFIG"