"""Parse Java .class constant pools and collect Methodref/Fieldref targets for a package prefix.

Returns, for each class file:
  - the owning class name
  - the set of (owner_class, member_name, descriptor) for every Fieldref /
    Methodref / InterfaceMethodref in the constant pool.

Constant-pool layout note: a Methodref/Fieldref entry points at a Class entry
and a NameAndType entry; NameAndType in turn points at two Utf8 entries. All
three levels must be resolved, which is what tripped up the first attempt.
"""
import struct
import zipfile
import sys
import collections
import re

FIXED_REF_TAGS = (9, 10, 11, 12)          # Fieldref, Methodref, InterfaceMethodref, NameAndType
OTHER_PAIR_TAGS = (17, 18)                 # Dynamic, InvokeDynamic (2nd u2 is NameAndType)


def parse_class(data):
    if len(data) < 10 or data[0:4] != b'\xca\xfe\xba\xbe':
        return None, []
    off = 8
    count = struct.unpack_from('>H', data, off)[0]
    off += 2
    cp = [None] * count
    i = 1
    while i < count:
        tag = data[off]
        off += 1
        if tag == 1:
            ln = struct.unpack_from('>H', data, off)[0]
            off += 2
            cp[i] = data[off:off + ln].decode('utf-8', 'replace')
            off += ln
        elif tag in (7, 8, 16, 19, 20):
            cp[i] = ('ref', struct.unpack_from('>H', data, off)[0])
            off += 2
        elif tag == 15:
            off += 3
        elif tag in (3, 4):
            off += 4
        elif tag in (5, 6):
            off += 8
            i += 1
        elif tag in FIXED_REF_TAGS or tag in OTHER_PAIR_TAGS:
            cp[i] = ('pair', struct.unpack_from('>H', data, off)[0],
                     struct.unpack_from('>H', data, off + 2)[0])
            off += 4
        else:
            raise ValueError('bad tag %d at cp#%d' % (tag, i))
        i += 1

    def utf(idx):
        if idx is None or idx <= 0 or idx >= count:
            return ''
        v = cp[idx]
        return v if isinstance(v, str) else ''

    def class_name(idx):
        if idx is None or idx <= 0 or idx >= count:
            return ''
        v = cp[idx]
        if isinstance(v, tuple) and v[0] == 'ref':
            return utf(v[1])
        return ''

    def name_and_type(idx):
        """Resolve a NameAndType index -> 'name:descriptor'."""
        if idx is None or idx <= 0 or idx >= count:
            return ''
        v = cp[idx]
        if isinstance(v, tuple) and v[0] == 'pair':
            return utf(v[1]) + ':' + utf(v[2])
        return ''

    off += 2                                    # access_flags
    this_class = class_name(struct.unpack_from('>H', data, off)[0])

    refs = []
    for idx, e in enumerate(cp):
        if not (isinstance(e, tuple) and e[0] == 'pair'):
            continue
        if idx not in _tagset:
            continue                            # skip NameAndType / Dynamic / InvokeDynamic
        owner = class_name(e[1])
        nt = name_and_type(e[2])
        if not owner or not nt:
            continue
        m = re.match(r'^(.*?):(.*)$', nt, re.S)
        if m:
            refs.append((owner, m.group(1), m.group(2)))
    return this_class, refs


def _build_tagset(data):
    """Second pass: remember which cp slots were Fieldref/Methodref/InterfaceMethodref."""
    off = 8
    count = struct.unpack_from('>H', data, off)[0]
    off += 2
    tags = set()
    i = 1
    while i < count:
        tag = data[off]
        off += 1
        if tag == 1:
            ln = struct.unpack_from('>H', data, off)[0]
            off += 2 + ln
        elif tag in (7, 8, 16, 19, 20):
            off += 2
        elif tag == 15:
            off += 3
        elif tag in (3, 4):
            off += 4
        elif tag in (5, 6):
            off += 8
            i += 1
        elif tag in FIXED_REF_TAGS or tag in OTHER_PAIR_TAGS:
            if tag != 12:
                tags.add(i)
            off += 4
        else:
            raise ValueError('bad tag %d' % tag)
        i += 1
    return tags


def parse_class2(data):
    """parse_class, but also filtering NameAndType/Dynamic/InvokeDynamic properly."""
    global _tagset
    _tagset = _build_tagset(data)
    return parse_class(data)


def scan_jar(path, prefixes, want_str=None):
    hits = collections.Counter()
    owners = collections.Counter()
    classes_total = 0
    classes_hit = 0
    with zipfile.ZipFile(path) as z:
        for info in z.infolist():
            if not info.filename.endswith('.class'):
                continue
            classes_total += 1
            data = z.read(info)
            if want_str and want_str.encode() not in data:
                continue
            try:
                cn, refs = parse_class2(data)
            except Exception:
                continue
            got = False
            for owner, name, desc in refs:
                o = owner.replace('/', '.')
                if o.startswith(prefixes):
                    hits['%s.%s%s' % (o, name, desc)] += 1
                    owners[o] += 1
                    got = True
            if got:
                classes_hit += 1
    return hits, owners, classes_total, classes_hit


if __name__ == '__main__':
    jar = sys.argv[1]
    prefixes = tuple(sys.argv[2].split(',')) if len(sys.argv) > 2 else ('org.lwjgl.opengl',)
    h, o, n, nh = scan_jar(jar, prefixes, want_str='org/lwjgl/opengl')
    print('# classes scanned: %d ; classes touching GL: %d' % (n, nh))
    print('# distinct owner classes: %d' % len(o))
    print('## OWNERS')
    for k, v in sorted(o.items(), key=lambda x: -x[1]):
        print('%6d  %s' % (v, k))
    print('## CALLS')
    for k, v in sorted(h.items()):
        print('%6d  %s' % (v, k))