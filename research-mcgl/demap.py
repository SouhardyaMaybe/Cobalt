import json, urllib.request, sys, re, pickle, os
def load(ver):
    f=f'cls-{ver}.pkl'
    if os.path.exists(f): return pickle.load(open(f,'rb'))
    d=json.load(open('/tmp/opencode/vm.json'))
    u=[v for v in d['versions'] if v['id']==ver][0]['url']
    j=json.load(urllib.request.urlopen(u,timeout=30))
    txt=urllib.request.urlopen(j['downloads']['client_mappings']['url'],timeout=90).read().decode('utf-8')
    # lines look like:  com.mojang.X.Y -> obf:      (deobf -> obf)
    obf2deobf={}
    for line in txt.splitlines():
        m=re.match(r'^([\w.$]+) -> ([\w.$]+):$', line)
        if m: obf2deobf[m.group(2)]=m.group(1)
    pickle.dump(obf2deobf,open(f,'wb'))
    return obf2deobf
if __name__=='__main__':
    for ver in sys.argv[1:]:
        m=load(ver); print(ver,len(m))
