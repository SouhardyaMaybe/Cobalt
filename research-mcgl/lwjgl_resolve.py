import zipfile, struct, re, json, sys

def pool_strings(data):
    off=8; cnt=struct.unpack_from('>H',data,off)[0]; off+=2
    cp=[None]*cnt; i=1; out=[]; sup=None; this=None
    while i<cnt:
        tag=data[off]; off+=1
        if tag==1:
            ln=struct.unpack_from('>H',data,off)[0]; off+=2
            cp[i]=data[off:off+ln].decode('utf-8','replace')
            out.append(cp[i]); off+=ln
        elif tag in (7,8,16,19,20): cp[i]=('ref',struct.unpack_from('>H',data,off)[0]); off+=2
        elif tag==15: off+=3
        elif tag in (3,4): off+=4
        elif tag in (5,6): off+=8; i+=1
        elif tag in (9,10,11,12,17,18):
            cp[i]=('pair',struct.unpack_from('>H',data,off)[0],struct.unpack_from('>H',data,off+2)[0]); off+=4
        else: raise ValueError(tag)
        i+=1
    def utf(k):
        v=cp[k]; return v if isinstance(v,str) else ''
    def cname(idx):
        v=cp[idx]
        return utf(v[1]) if isinstance(v,tuple) and v[0]=='ref' else ''
    off+=2                                   # access_flags
    _this=cname(struct.unpack_from('>H',data,off)[0])
    _sup =cname(struct.unpack_from('>H',data,off+2)[0])
    off+=4
    ifc=struct.unpack_from('>H',data,off)[0]; off+=2+2*ifc
    nf=struct.unpack_from('>H',data,off)[0]; off+=2
    for _ in range(nf):
        off+=6
        n=struct.unpack_from('>H',data,off)[0]; off+=2
        for _ in range(n):
            off+=6+struct.unpack_from('>I',data,off+2)[0]
    return out, _this, _sup

def build(jar):
    z=zipfile.ZipFile(jar)
    syms={}; sup={}
    for n in z.namelist():
        if not n.endswith('.class') or not n.startswith('org/lwjgl/opengl/'): continue
        d=z.read(n)
        ss,this,s=pool_strings(d)
        cls=this.replace('/','.')
        syms[cls]=[x for x in ss if re.fullmatch(r'gl[A-Z]\w*', x)]
        sup[cls]=s.replace('/','.') if s else None
    return syms, sup

def resolve(symbol, mname, syms, sup):
    """walk the chain; find the native symbol for method mname"""
    seen=set(); c=symbol
    while c and c not in seen:
        seen.add(c)
        sl=syms.get(c)
        if sl is None: break
        if mname in sl: return c, mname
        # aliases: glFoo -> glFooARB/EXT etc declared in same class
        cands=[x for x in sl if x==mname or x==mname+'ARB' or x==mname+'EXT']
        if cands: return c, sorted(cands)[0]
        c=sup.get(c)
    return None, None
