#!/usr/bin/env python3
"""Lift C++ functions out of a source file by name.

The translation passes in gl/glsl/glsl_for_es.cpp are pure std::string code, but the
file they live in includes glslang and SPIRV-Cross, so it cannot be compiled on its
own. This pulls the named functions' text out verbatim so
tools/test-glsl-translation.cpp can exercise the file that actually ships instead of
a transcription of it.

Names are emitted in the order given, which is the order they have to appear in: a
function may call one listed after it only if the file declares it first, so pass the
helpers before their callers.

Fails loudly rather than returning a partial function: a silently truncated body
would make the regression test pass for the wrong reason.
"""
import sys


def extract(text, name):
    """Return the source of `name`, from its definition to the brace at column 0."""
    at = text.find(name + "(")
    while at >= 0:
        # A definition, not a call or a forward use: the name starts a line of its own
        # and the parameter list is followed by an opening brace.
        line_start = text.rfind("\n", 0, at) + 1
        close = text.find(")", at)
        if text[line_start:at].strip() and close > 0 and text[close + 1:close + 3].strip() == "{":
            break
        at = text.find(name + "(", at + 1)
    if at < 0:
        sys.exit(f"extract-glsl-fn: no definition of {name}()")

    start = text.rfind("\n", 0, at) + 1
    end = text.find("\n}\n", start)
    if end < 0:
        sys.exit(f"extract-glsl-fn: no closing brace for {name}()")
    return text[start:end + 3]


def main():
    if len(sys.argv) != 4:
        sys.exit("usage: extract-glsl-fn.py <source.cpp> <fn,fn,...> <out.inc>")
    src, names, out = sys.argv[1], sys.argv[2].split(","), sys.argv[3]
    with open(src, encoding="utf-8") as fh:
        text = fh.read()
    with open(out, "w", encoding="utf-8") as fh:
        for name in names:
            fh.write("// --- extracted from " + src + " ---\n")
            fh.write(extract(text, name))
            fh.write("\n")


if __name__ == "__main__":
    main()