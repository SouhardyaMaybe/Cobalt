#!/usr/bin/env python3
"""Read versionName and versionCode out of an APK's binary AndroidManifest.xml.

Why not aapt. `aapt dump badging` needs the framework resource table to resolve
`@android:drawable/*` in the manifest, so it fails on this APK with

    ERROR getting 'android:icon' attribute: attribute value reference does not exist

unless it is also given -I<platform>/android.jar. That is a whole SDK layout
dependency, a different build-tools version on every runner image, and a failure mode
that reads like a broken manifest rather than a missing flag. `aapt2` has the same
requirement.

So the version is read from the string pool and the manifest's attribute array
directly. Both are fixed layouts documented in the platform's ResourceTypes.h, and the
parser below is 60 lines against them.

The version was hardcoded at 0.1.0 for six releases and no check saw it, because every
check looked at the build inputs and none looked at the artifact. This looks at the
artifact.

Usage:  tools/apk-version.py <apk>
"""

import struct
import sys
import zipfile

# AXML: ResChunk_header { u16 type, u16 headerSize, u32 size }
RES_XML_TYPE = 0x0003
RES_STRING_POOL_TYPE = 0x0001
# Within the string pool
POOL_SORTED_FLAG = 1 << 0
POOL_UTF8_FLAG = 1 << 8

# Inside an XML tree node
START_ELEMENT = 0x0102
END_ELEMENT = 0x0103
# Res_value
TYPE_NULL = 0x00
TYPE_REFERENCE = 0x01
TYPE_STRING = 0x03
TYPE_INT_DEC = 0x10
TYPE_INT_HEX = 0x11
TYPE_INT_BOOLEAN = 0x12


def u16(data, at):
    return struct.unpack_from("<H", data, at)[0]


def u32(data, at):
    return struct.unpack_from("<I", data, at)[0]


def parse_string_pool(data, at):
    """Return (strings, end_offset) for the ResStringPool at `at`."""
    header_size = u16(data, at + 2)
    size = u32(data, at + 4)
    string_count = u32(data, at + 8)
    flags = u32(data, at + 16)
    strings_start = u32(data, at + 20)

    is_utf8 = bool(flags & POOL_UTF8_FLAG)
    offsets = [u32(data, at + header_size + 4 * i) for i in range(string_count)]

    strings = []
    base = at + strings_start
    for off in offsets:
        p = base + off
        if is_utf8:
            # Two length prefixes: the character count, then the byte count. Both are
            # stored as one or two bytes, high bit set meaning "one more follows".
            # Skipping the first and using the second is what the format is for: the
            # byte length is what offsets are measured in.
            while p < len(data) and (data[p] & 0x80):
                p += 1
            p += 1
            n = data[p]
            if n & 0x80:
                n = ((n & 0x7F) << 8) | data[p + 1]
                p += 2
            else:
                p += 1
            strings.append(data[p:p + n].decode("utf-8", "replace"))
        else:
            # UTF-16: a 16-bit character count, then that many UTF-16 code units, then
            # a NUL terminator. The count is read at p and the text starts after it --
            # p must advance past the prefix exactly once, or the first character is
            # dropped and the terminating NUL is kept. Which is what this did: every
            # string came back as "aunchMode" instead of "launchMode", and since the
            # attribute names were mangled the same way, no attribute ever matched and
            # the parser reported no version while exiting successfully.
            n = u16(data, p)
            p += 2
            if n & 0x8000:
                n = ((n & 0x7FFF) << 16) | u16(data, p)
                p += 2
            strings.append(data[p:p + n * 2].decode("utf-16-le", "replace"))

    return strings, at + size


def decode_value(data, at, strings):
    """Return the Python value of the Res_value at `at`.

    Layout: size(2) res0(1) dataType(1) data(4), so the type is the byte at +3.
    """
    value_type = data[at + 3]
    raw = u32(data, at + 4)
    if value_type == TYPE_STRING:
        return strings[raw] if raw < len(strings) else None
    if value_type in (TYPE_INT_DEC, TYPE_INT_HEX):
        return raw
    if value_type == TYPE_INT_BOOLEAN:
        return bool(raw)
    if value_type == TYPE_NULL:
        return None
    if value_type == TYPE_REFERENCE:
        return "@%d" % raw
    return raw


def parse_attributes(data, at, strings):
    """Yield (name, value) for the attribute array of a start-element node.

    Offsets from ResourceTypes.h (frameworks/base/libs/androidfw/include/androidfw):

        ResXMLTree_node       type(2) headerSize(2) size(4)
        ResXMLTree_attrExt    ns(4) name(4) attributeStart(2) attributeSize(2)
                             attributeCount(2) idIndex(2) classIndex(2) styleIndex(2)
        ResXMLTree_attribute  ns(4) name(4) rawValue(4) typedValue(8)

    Three things are easy to get wrong here, and each was:

    - attributeStart is measured from the start of attrExt, which is 8 bytes after
      the node, not from the node itself.
    - ResXMLTree_attrExt is 20 bytes, not 16: idIndex/classIndex/styleIndex follow
      attributeCount and are usually zero, but they occupy the space.
    - typedValue is at offset 12 of an attribute, after rawValue, so its dataType
      byte is at +15.
    """
    ext = at + u16(data, at + 2)  # attrExt begins headerSize bytes after the node
    attribute_start = u16(data, ext + 8)
    attribute_size = u16(data, ext + 10)
    attribute_count = u16(data, ext + 12)

    p = ext + attribute_start
    for _ in range(attribute_count):
        name_idx = u32(data, p + 4)
        value = decode_value(data, p + 12, strings)
        name = strings[name_idx] if name_idx < len(strings) else ""
        yield name, value
        p += attribute_size


def parse(data):
    """Return {'versionName': str, 'versionCode': int} from a binary AXML blob.

    versionName and versionCode are attributes of <manifest>, but the loop does not
    assume that: it collects them from whichever start element carries them. A
    library element could in principle define its own, and taking the first pair in
    document order is the manifest's by construction.
    """
    if u16(data, 0) != RES_XML_TYPE:
        raise ValueError("not a binary AndroidManifest.xml (type 0x%04x)" % u16(data, 0))

    pool_at = u16(data, 2)
    strings, after_pool = parse_string_pool(data, pool_at)

    found = {}
    at = after_pool
    end = u32(data, 4)  # total size of the ResXMLTree chunk
    while at + 8 <= end:
        node_type = u16(data, at)
        node_size = u32(data, at + 4)
        if node_size <= 0:
            break
        if node_type == START_ELEMENT:
            for attr, value in parse_attributes(data, at, strings):
                if attr in ("versionName", "versionCode") and attr not in found:
                    if attr == "versionCode" and not isinstance(value, int):
                        continue
                    if attr == "versionName" and not isinstance(value, str):
                        continue
                    found[attr] = value
            if "versionName" in found and "versionCode" in found:
                return found
        at += node_size

    return found


def main():
    if len(sys.argv) != 2:
        sys.stderr.write(__doc__)
        return 2
    apk = sys.argv[1]
    try:
        with zipfile.ZipFile(apk) as z:
            data = z.read("AndroidManifest.xml")
    except KeyError:
        sys.exit("%s has no AndroidManifest.xml" % apk)

    found = parse(data)
    name = found.get("versionName")
    code = found.get("versionCode")
    if name is None or code is None:
        sys.exit("could not read the version out of %s" % apk)
    print("%s %s" % (code, name))
    return 0


if __name__ == "__main__":
    sys.exit(main())