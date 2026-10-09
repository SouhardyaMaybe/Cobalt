#!/usr/bin/env python3
"""Rename MobileGlues to Cobalt across the renderer source.

The renderer is a MobileGlues fork. A fork that still says "MobileGlues"
everywhere -- in the library name, the log prefix, the GL vendor string, the
config directory, the env vars, the file names -- reads as a repackaged fork
rather than a renderer, and every one of those is something a user or a game
can observe. This rewrites the whole surface to Cobalt.

Two categories are treated differently on purpose:

  Renamed    identifiers, strings and paths Cobalt owns. A user sees these in
             the log, in the config directory, in GL_VERSION, and on disk.

  Kept       the copyright and licence header on each file. LGPL-2.1 section
             5(a) requires the copyright notice and the licence to travel with
             the work. Removing it is not a rename, it is a licence violation,
             and it is the one thing here that would be dishonest rather than
             merely inelegant.

3rdparty/ is never touched: glslang, SPIRV-Cross and xxhash are separate
projects with their own names and licences.

Files and directories are renamed too, not just their contents, because a tree
whose every path says MobileGlues is exactly what a repackaged fork looks
like.

Idempotent. Running it twice is a no-op, so it can sit in the build without a
"have we already run it" flag.

Usage:  tools/rebrand.py <path-to-MobileGlues-cpp>
"""

import os
import re
import sys

# Applied in order, so a rule that matches a prefix of a longer token must come
# before the rule that matches the longer token. The comment on each line says
# what it would break if the order were reversed.
RENAMES = [
    # --- before the generic MOBILEGLUES rules, which would otherwise eat the
    # --- prefix and leave the rest of the token behind.

    # Version macro, then the namespace it belongs to.
    ("MG_MOBILEGLUES_VERSION", "COBALT_VERSION"),
    ("MG_MOBILEGLUES", "COBALT"),

    # Include guard of gl/mg.h, which is renamed to gl/cobalt.h below. Without
    # this the generic rules turn MOBILEGLUES_MG_H into COBALT_CB_H.
    ("MOBILEGLUES_MG_H", "COBALT_H"),

    # Remaining include guards: MOBILEGLUES_INCLUDES_H and friends.
    ("MOBILEGLUES_", "COBALT_"),
    ("MOBILEGLUES", "COBALT"),

    # --- before MG_, which is the general prefix rule further down.

    # The three extension names the renderer advertises. Matched first so the
    # MG_ rule does not shorten them into GL_CB_cobalt and friends.
    ("GL_MG_backend_string_getter_access", "GL_CB_backend_string_getter"),
    ("GL_MG_settings_string_dump", "GL_CB_settings_dump"),
    ("GL_MG_mobileglues", "GL_CB_translation"),
    # The synthetic enums those extensions resolve to. Neither is a real GL
    # token; both are looked up by games only via the names above.
    ("GL_BACKEND_GETTER_MG", "GL_BACKEND_GETTER_CB"),
    ("GL_SETTINGS_MG", "GL_SETTINGS_CB"),

    # --- C++ types and enums that embed the old prefix.

    ("HideMGEnvLevel", "HideCobaltEnvLevel"),
    ("hideMGEnvLevel", "hideCobaltEnvLevel"),
    ("hide_mg_env_level", "hide_cobalt_env_level"),
    ("MGContext", "CobaltContext"),
    ("MGShareGroup", "CobaltShareGroup"),
    ("MGInfoGetter", "CobaltInfoGetter"),

    # Synthetic GL enums the renderer defines for capabilities ES lacks. MGC_ is
    # short and used in dense #define blocks in gl/enable.h; CBC_ keeps it that
    # way without carrying the old name.
    ("MGC_", "CBC_"),

    # The general prefix rule: env var names, cache-directory constants, the
    # few remaining MG_MAX_* limits. MG_ was never an abbreviation anything
    # outside this tree needed to know.
    ("MG_", "CB_"),

    # Include directory holding the synthetic extension enums.
    ("<MG/extensions.h>", "<CB/extensions.h>"),

    # --- user-visible strings and paths.

    # Default config/cache directory. A user's existing /sdcard/MG is left
    # alone; CB_DIR_PATH still overrides it.
    ('"/sdcard/MG', '"/sdcard/Cobalt'),
    # Comment in config/stats.h describing where stats.json is written.
    ("MG/stats.json", "Cobalt/stats.json"),

    ("MobileGlues", "Cobalt"),
    ("mobileglues", "cobalt"),

    ]

# References to the renamed files, in every form they appear. A plain string
# replacement cannot cover these: the includes are spelled "../mg.h", "../gl/mg.h"
# and "gl/mg.h" depending on the including file's depth, plus a bare "mg.h" from
# inside gl/ itself, and CMakeLists.txt names gl/mg.cpp. Missing one compiles
# nothing and fails with a file-not-found that points at the wrong file.
#
# The lookbehind stops the match at a path boundary, so a hypothetical
# "foo_mg.h" is left alone. 3rdparty is never walked, so no vendored project is
# affected by this or any other rule above.
RENAMED_FILES = re.compile(r"(?<![A-Za-z0-9_.])mg\.(h|cpp)\b")

# Lowercase C-style identifiers. Applied after RENAMES so that the compound
# CamelCase names above are already gone, and word-bounded so that a substring
# ending in "mg_" -- img_, dmsg_ -- is not caught.
LOWERCASE_PREFIX = re.compile(r"\bmg_")
UPPERCASE_PREFIX = re.compile(r"\bMG_")

# Header lines that must survive verbatim. A line containing any of these is
# left alone, which is how the licence header survives a rename that rewrites
# the rest of the file.
KEEP = (
    "Copyright (c)",
    "SPDX-License-Identifier",
    "Licensed under the GNU Lesser General Public License",
    "gnu.org/licenses",
    "MobileGL-Dev",
    "github.com/MobileGL",
)

# Files and directories to rename, as (old relative path, new relative path).
# Applied after the contents are rewritten, so nothing rewrites them back.
# CMakeLists.txt names gl/cobalt.cpp directly and is rewritten by the
# ("gl/mg.cpp", "gl/cobalt.cpp") rule above, so the two cannot drift.
PATH_RENAMES = [
    ("include/MG", "include/CB"),
    ("gl/mg.h", "gl/cobalt.h"),
    ("gl/mg.cpp", "gl/cobalt.cpp"),
]

SKIP_DIRS = {"3rdparty", ".git", "build", ".cxx"}
SOURCE_SUFFIXES = (".cpp", ".h", ".hpp", ".txt", ".cmake", ".in", "")


def rebrand_text(text):
    out = []
    for line in text.splitlines(keepends=True):
        if any(k in line for k in KEEP):
            out.append(line)
            continue
        new = line
        for old, rep in RENAMES:
            new = new.replace(old, rep)
        new = LOWERCASE_PREFIX.sub("cb_", new)
        new = UPPERCASE_PREFIX.sub("CB_", new)
        new = RENAMED_FILES.sub(r"cobalt.\1", new)
        out.append(new)
    return "".join(out)


def rebrand_file(path):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            original = fh.read()
    except (UnicodeDecodeError, OSError):
        return False
    updated = rebrand_text(original)
    if updated != original:
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(updated)
        return True
    return False


def rebrand_paths(root):
    """Rename files and directories, parents first so nesting works."""
    moved = []
    for old_rel, new_rel in PATH_RENAMES:
        src = os.path.join(root, old_rel)
        dst = os.path.join(root, new_rel)
        if not os.path.exists(src):
            continue
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        os.rename(src, dst)
        moved.append((old_rel, new_rel))
    return moved


def main():
    if len(sys.argv) != 2:
        sys.stderr.write(__doc__)
        return 2
    root = sys.argv[1]
    if not os.path.isdir(root):
        sys.stderr.write("error: %s is not a directory\n" % root)
        return 1

    changed = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for name in filenames:
            if name.endswith(SOURCE_SUFFIXES):
                p = os.path.join(dirpath, name)
                if rebrand_file(p):
                    changed.append(os.path.relpath(p, root))

    moved = rebrand_paths(root)

    print("rebranded %d file(s)" % len(changed))
    for old, new in moved:
        print("renamed  %s -> %s" % (old, new))
    return 0


if __name__ == "__main__":
    sys.exit(main())