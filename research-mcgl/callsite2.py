"""javap only the classes that reference org/lwjgl, and map method -> GL entry points."""
import zipfile, subprocess, sys, os, re, tempfile, shutil

def gl_classes(jar, needle=b'org/lwjgl/opengl'):
    z=zipfile.ZipFile(jar)
    return [n[:-6].replace('/','.') for n in z.namelist()
            if n.endswith('.class') and needle in z.read(n)]

def dump(jar, classes):
    z=zipfile.ZipFile(jar); ext=tempfile.mkdtemp()
    names=set(c.replace('.','/')+'.class' for c in classes)
    for n in z.namelist():
        if n in names:
            p=os.path.join(ext,n); os.makedirs(os.path.dirname(p),exist_ok=True)
            open(p,'wb').write(z.read(n))
    res={}
    for t in classes:
        r=subprocess.run(['javap','-p','-c','-classpath',ext,t],
                         capture_output=True,text=True,timeout=120)
        if r.returncode!=0: continue
        cur=None; buf=[]; order=[]
        for line in r.stdout.splitlines():
            st=line.strip()
            if re.match(r'^(public|private|protected|static|final|abstract|\w).*[\w$>\]]\(.*\);\s*$', st) and not st.startswith('//') and '(' in st:
                if cur is not None: res.setdefault(t,[]).append((cur,sorted(set(buf))))
                cur=st; buf=[]
            m=re.search(r'// (?:Method|InterfaceMethod) (org/lwjgl/[\w/]+)\.(\w+)', line)
            if m: buf.append(m.group(1)+'.'+m.group(2))
            if st.startswith('static {') or st.startswith('{'):
                if cur is not None: res.setdefault(t,[]).append((cur,sorted(set(buf)))); cur=None; buf=[]
        if cur is not None: res.setdefault(t,[]).append((cur,sorted(set(buf))))
    shutil.rmtree(ext,ignore_errors=True)
    return res

if __name__=='__main__':
    jar=sys.argv[1]
    cl=gl_classes(jar)
    print('## classes touching org.lwjgl.opengl: %d' % len(cl))
    res=dump(jar,cl)
    for cls in cl:
        if cls not in res: continue
        print('='*96); print(cls)
        for m,c in res[cls]:
            if not c: continue
            print('  '+m)
            print('      -> '+', '.join(sorted(x.replace('org/lwjgl/','') for x in c)))
