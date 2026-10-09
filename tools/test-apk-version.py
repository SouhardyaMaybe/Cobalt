#!/usr/bin/env python3
"""Build binary AndroidManifest.xml (AXML) blobs, to test tools/apk-version.py.

The parser has to survive real input, and no APK or runnable aapt is available on this
machine -- the local Android SDK is x86_64 binaries on an arm64 host. So the blobs are
built here from the ResXMLTree layout in the platform's ResourceTypes.h, which is the
same specification the parser reads.

Writes two manifests, differing only in the version, and asserts the parser tells them
apart. A parser that returns the same answer for both is not reading anything.
"""

import struct
import sys
import os
import zipfile

RES_XML_TYPE = 0x0003
RES_STRING_POOL_TYPE = 0x0001
START_ELEMENT = 0x0102
END_ELEMENT = 0x0103
POOL_UTF8_FLAG = 1 << 8
TYPE_STRING = 0x03
TYPE_INT_DEC = 0x10


def string_pool(strings):
    """UTF-8 ResStringPool. Offsets are byte counts."""
    encoded = [s.encode("utf-8") for s in strings]
    blob = b""
    offsets = []
    for e in encoded:
        offsets.append(len(blob))
        # two length prefixes: char count then byte count, each 1-2 bytes
        n = len(e)
        blob += bytes([n & 0x7F]) if n < 0x80 else bytes([0x80 | (n >> 8), n & 0xFF])
        m = len(e)
        blob += bytes([m & 0x7F]) if m < 0x80 else bytes([0x80 | (m >> 8), m & 0xFF])
        blob += e
        blob += b"\x00"

    header_size = 28
    string_count = len(strings)
    total = header_size + 4 * string_count + len(blob)
    # ResStringPool_header: type, headerSize, size, stringCount, styleCount,
    #                       flags, stringsStart, stylesStart  -- 8 fields, two
    # 16-bit followed by six 32-bit.
    out = struct.pack("<HHIIIIII", RES_STRING_POOL_TYPE, header_size, total,
                      string_count, 0, POOL_UTF8_FLAG,
                      header_size + 4 * string_count, 0)
    for o in offsets:
        out += struct.pack("<I", o)
    return out + blob


def res_value(type_code, value):
    """Res_value: size(2) res0(1) dataType(1) data(4) = 8 bytes."""
    return struct.pack("<HBBI", 0x08, 0, type_code, value)


def start_element(name_idx, attrs):
    """attrs: list of (ns_idx, name_idx, typed_value_bytes).

    Struct layouts from ResourceTypes.h. Note attributeStart is measured from the
    start of attrExt, so it stays 20 (the node header is not counted), and
    ResXMLTree_attrExt is 20 bytes including idIndex/classIndex/styleIndex.
    """
    node_header = 8
    ext = struct.pack("<II", 0xFFFFFFFF, name_idx)          # ns, name
    ext += struct.pack("<HHHHHH", 20, 20, len(attrs), 0, 0, 0)  # start,size,count,id,class,style
    # Each attribute is ns(4) name(4) rawValue(4) typedValue(8) = 20 bytes.
    body = ext + b"".join(
        struct.pack("<III", ns, name, 0xFFFFFFFF) + value for ns, name, value in attrs
    )
    # Each attribute is ns(4) name(4) rawValue(4) typedValue(8) = 20 bytes.
    total = node_header + len(body)
    return struct.pack("<HHI", START_ELEMENT, node_header, total) + body


def build_manifest(version_name, version_code):
    # The version string is index 5, so each case puts its own value there rather than
    # reusing a literal -- otherwise every case reports the first one's name and the
    # round trip looks broken when the builder is what is wrong.
    strings = [
        "manifest",           # 0
        "versionCode",        # 1
        "versionName",        # 2
        "application",        # 3
        "label",              # 4
        version_name,         # 5  -- the value under test
    ]
    attrs = [
        (0xFFFFFFFF, 1, res_value(TYPE_INT_DEC, version_code)),
        (0xFFFFFFFF, 2, res_value(TYPE_STRING, 5)),
    ]
    chunks = string_pool(strings)
    chunks += start_element(0, attrs)
    chunks += start_element(3, [(0xFFFFFFFF, 4, res_value(TYPE_STRING, 5))])
    # ResXMLTree_header: type, headerSize, size. The string pool is the first chunk,
    # so its offset from the start of this chunk is the header size -- not 1, which is
    # the pool's own chunk type and a plausible-looking mistake.
    xml_header = struct.pack("<HHI", RES_XML_TYPE, 8, 8 + len(chunks))
    return xml_header + chunks


def end_element(name_idx):
    body = struct.pack("<II", 0xFFFFFFFF, name_idx)
    return struct.pack("<HHI", END_ELEMENT, 8, 8 + len(body)) + body


def build_manifest_ordered(version_name, version_code, swapped=False, nested_first=False):
    """A manifest with the attributes in a chosen order, optionally preceded by another
    element. Exercises the two things that make attribute order matter: which
    attribute comes first, and whether an earlier element carries any at all."""
    strings = [
        "manifest",       # 0
        "versionName",    # 1
        "versionCode",    # 2
        "application",    # 3
        "label",          # 4
        version_name,     # 5
    ]
    name_attr = (0xFFFFFFFF, 1, res_value(TYPE_STRING, 5))
    code_attr = (0xFFFFFFFF, 2, res_value(TYPE_INT_DEC, version_code))
    manifest_attrs = [code_attr, name_attr] if swapped else [name_attr, code_attr]

    chunks = string_pool(strings)
    if nested_first:
        # An <application> element with its own attribute, closed before <manifest>'s
        # attributes are reached. Not valid XML nesting, and deliberately so: the parser
        # walks nodes by size and must not depend on document structure.
        chunks += start_element(3, [(0xFFFFFFFF, 4, res_value(TYPE_STRING, 5))])
        chunks += end_element(3)
    chunks += start_element(0, manifest_attrs)
    chunks += end_element(0)

    return struct.pack("<HHI", RES_XML_TYPE, 8, 8 + len(chunks)) + chunks


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, here)
    import importlib.util
    spec = importlib.util.spec_from_file_location("apkversion", os.path.join(here, "apk-version.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    fails = 0

    def check(ok, msg):
        print(("ok    " if ok else "FAIL  ") + msg)
        nonlocal fails
        if not ok:
            fails += 1

    cases = [
        ("0.3.2", 302),
        ("0.1.0", 1),      # the values every release actually shipped
        ("10.20.30", 102030),
        ("1.2.3-rc.1", 10203),
        ("0.0.1", 1),
    ]
    for name, code in cases:
        blob = build_manifest(name, code)
        got = mod.parse(blob)
        check(got.get("versionName") == name,
              "%-12s versionName read back as %r" % (name, got.get("versionName")))
        check(got.get("versionCode") == code,
              "%-12s versionCode read back as %r" % (name, got.get("versionCode")))

    # Distinct inputs must give distinct answers, or the parser is reading nothing.
    a = mod.parse(build_manifest("0.3.2", 302))
    b = mod.parse(build_manifest("0.1.0", 1))
    check(a != b, "two different manifests give two different answers")

    # Attribute order must not matter: a real manifest lists them however the build
    # tools wrote them, and versionCode appearing before versionName is enough to make
    # a parser that assumes an order return nothing.
    reordered = build_manifest_ordered("9.9.9", 99999, swapped=True)
    got = mod.parse(reordered)
    check(got.get("versionName") == "9.9.9", "versionName read when listed second")
    check(got.get("versionCode") == 99999, "versionCode read when listed first")

    # An unrelated element carrying attributes before <manifest>'s own must not be
    # mistaken for it, and must not stop the walk.
    nested = build_manifest_ordered("7.7.7", 707, nested_first=True)
    got = mod.parse(nested)
    check(got.get("versionName") == "7.7.7", "found after an unrelated element")
    check(got.get("versionCode") == 707, "versionCode found after an unrelated element")

    # And through a real zip, the way CI will call it.
    apk = os.path.join("/tmp", "cobalt-parser-test.apk")
    with zipfile.ZipFile(apk, "w") as z:
        z.writestr("AndroidManifest.xml", build_manifest("0.3.2", 302))
        z.writestr("lib/arm64-v8a/libcobalt.so", b"\x7fELF")
    import subprocess
    out = subprocess.run([sys.executable, os.path.join(here, "apk-version.py"), apk],
                         capture_output=True, text=True)
    check(out.returncode == 0 and out.stdout.strip() == "302 0.3.2",
          "end to end through a zip: %r" % out.stdout.strip())
    os.remove(apk)

    print("\n" + ("all tests passed" if fails == 0 else "%d FAILURES" % fails))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())