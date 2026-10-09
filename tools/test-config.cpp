// Check that the renderer's own config file is one the renderer can actually read.
//
// plugin/config/cobalt-settings.json ships as CB_DIR_PATH/config.json. The
// device log said:
//
//     Failed to load config. Use default config.
//     [Cobalt] Setting: maxGlslCacheSize            = 0
//
// because no such file was shipped, so config_refresh() failed and every key took
// its -1 fallback. That is silent in the worst way: the renderer still starts, and
// the only visible consequence is maxGlslCacheSize = 0, which disables the shader
// cache and with it the negative cache in patches/0001 -- so a shader that fails to
// compile is recompiled on every resource reload, and Minecraft reloads resources on
// every dimension change.
//
// Parsing it with the real cJSON is the point. A JSON file is valid to Python and
// still rejected by the library that reads it, and config_get_int() answers -1 for
// anything that is not a number -- which the renderer interprets as "absent", not as
// an error. So a key that is present but unreadable is indistinguishable from a key
// nobody wrote, and the only way to know is to read it back with the same parser.
//
// Compiled and run by tools/test-config.sh, which links config/cJSON.c from the
// upstream tree so this stays honest about which parser is in use.

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "cJSON.h"

static int failures = 0;

static void check(int ok, const char *msg) {
    printf("%s %s\n", ok ? "ok  " : "FAIL", msg);
    if (!ok) ++failures;
}

static char *read_file(const char *path, long *len) {
    FILE *f = fopen(path, "rb");
    if (!f) {
        fprintf(stderr, "error: cannot open %s\n", path);
        return NULL;
    }
    fseek(f, 0, SEEK_END);
    *len = ftell(f);
    fseek(f, 0, SEEK_SET);
    char *buf = (char *)malloc((size_t)*len + 1);
    if (!buf) {
        fclose(f);
        return NULL;
    }
    if (fread(buf, 1, (size_t)*len, f) != (size_t)*len) {
        fprintf(stderr, "error: short read on %s\n", path);
        fclose(f);
        free(buf);
        return NULL;
    }
    buf[*len] = '\0';
    fclose(f);
    return buf;
}

// config_get_int() returns -1 for a key that is missing, and init_settings() reads
// -1 as "the config did not say". So an unreadable key is invisible: the renderer
// carries on with a default and nothing is logged. These helpers read the file the
// way the renderer does.
static int get_int(cJSON *root, const char *key) {
    cJSON *item = cJSON_GetObjectItem(root, key);
    return (item && cJSON_IsNumber(item)) ? item->valueint : -1;
}

static const char *get_string(cJSON *root, const char *key) {
    cJSON *item = cJSON_GetObjectItem(root, key);
    return (item && cJSON_IsString(item)) ? item->valuestring : NULL;
}

// Every key config/settings.cpp reads. A missing one silently degrades to a default,
// which is exactly the failure this file exists to stop.
static const char *const k_int_keys[] = {
    "enableANGLE", "enableNoError", "enableExtComputeShader", "enableExtTimerQuery",
    "enableExtDirectStateAccess", "maxGlslCacheSize", "angleDepthClearFixMode",
    "customGLVersion", "fsr1Setting", "hideMGEnvLevel",
};

int main(int argc, char **argv) {
    const char *path = argc > 1 ? argv[1] : "plugin/config/cobalt-settings.json";

    long len = 0;
    char *raw = read_file(path, &len);
    if (!raw) return 2;

    cJSON *root = cJSON_Parse(raw);
    if (!root) {
        printf("FAIL  cJSON_Parse rejects the file, at: %.40s\n", cJSON_GetErrorPtr());
        free(raw);
        return 1;
    }
    printf("ok    cJSON_Parse accepts the file (%ld bytes)\n", len);
    if (!cJSON_IsObject(root)) {
        printf("FAIL  top level is not an object\n");
        cJSON_Delete(root);
        free(raw);
        return 1;
    }

    for (unsigned i = 0; i < sizeof k_int_keys / sizeof *k_int_keys; i++) {
        char msg[160];
        snprintf(msg, sizeof msg, "%-26s reads back as an int (%d)", k_int_keys[i],
                 get_int(root, k_int_keys[i]));
        check(get_int(root, k_int_keys[i]) != -1, msg);
    }

    // The file is documented inline with "//"-prefixed keys, which is legal JSON and
    // which cJSON stores as ordinary members. Asserted because a reader that treated
    // them as settings would be reading a comment as configuration.
    check(get_int(root, "//") == -1, "the // key is not readable as a setting");
    check(get_int(root, "//maxGlslCacheSize") == -1, "a //comment key is not readable as a setting");

    // Values, not just presence. These are the settings the device run got wrong or
    // defaulted past, and the comments in the file say why each one is what it is.
    check(get_int(root, "enableNoError") == 0, "enableNoError = 0: driver errors are surfaced");
    check(get_int(root, "enableExtTimerQuery") == 1, "enableExtTimerQuery = 1");
    check(get_int(root, "enableExtDirectStateAccess") == 1,
          "enableExtDirectStateAccess = 1: 26.3 calls glBindVertexBuffer directly");
    check(get_int(root, "maxGlslCacheSize") == 30,
          "maxGlslCacheSize = 30: 0 disables the shader cache and the negative cache");
    check(get_int(root, "customGLVersion") == 40, "customGLVersion = 40, matching the device log");

    // init_settings() clamps out-of-range values, so a value outside the range is
    // silently replaced and the comment describing it becomes a lie.
    int gl = get_int(root, "customGLVersion");
    check(gl == 0 || (gl >= 32 && gl <= 46), "customGLVersion is inside the unclamped range");
    check(get_int(root, "fsr1Setting") == 0, "fsr1Setting = 0, inside the enum");
    check(get_int(root, "hideMGEnvLevel") == 0, "hideMGEnvLevel = 0, inside the enum");
    check(get_int(root, "angleDepthClearFixMode") == 0, "angleDepthClearFixMode = 0, inside the enum");

    // multidrawOrder is read as a string. A non-string gives config_get_string() an
    // empty result, and the order silently reverts to the built-in default.
    const char *md = get_string(root, "multidrawOrder");
    check(md != NULL && *md != '\0', "multidrawOrder is a non-empty string");
    if (md) {
        check(strstr(md, "unroll") != NULL,
              "multidrawOrder lists unroll, the backend every device supports");
        check(strstr(md, "indirect") != NULL,
              "multidrawOrder lists indirect ahead of unroll");
    }

    cJSON_Delete(root);
    free(raw);
    printf("\n%s\n", failures ? "FAILURES" : "all tests passed");
    return failures ? 1 : 0;
}