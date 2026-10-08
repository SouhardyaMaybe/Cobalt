import zipfile, sys, cpool, collections
jar=sys.argv[1]
z=zipfile.ZipFile(jar)
rows=[]
for info in z.infolist():
    if not info.filename.endswith('.class'): continue
    d=z.read(info)
    if b'org/lwjgl/opengl' not in d: continue
    try: cn,refs=cpool.parse_class2(d)
    except Exception: continue
    c=collections.Counter()
    for o,n,ds in refs:
        oo=o.replace('/','.')
        if oo.startswith('org.lwjgl'):
            c[oo.split('.')[-1]+'.'+n]+=1
    rows.append((info.filename[:-6], len(c), sum(c.values())))
rows.sort(key=lambda r:-r[2])
for f,n,t in rows: print(f'{t:5d} refs  {n:4d} distinct  {f}')
