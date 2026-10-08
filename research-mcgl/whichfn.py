import zipfile, sys, cpool, collections
jar, needle = sys.argv[1], sys.argv[2].encode()
z=zipfile.ZipFile(jar)
for n in z.namelist():
    if not n.endswith('.class'): continue
    d=z.read(n)
    if b'org/lwjgl' not in d: continue
    try: cn,refs=cpool.parse_class2(d)
    except Exception: continue
    got=[o.replace('/','.')+'.'+nm for o,nm,ds in refs if o.replace('/','.')+'.'+nm==needle or needle.decode() in o.replace('/','.')+'.'+nm]
    if got: print(n[:-6], '->', sorted(set(got)))
