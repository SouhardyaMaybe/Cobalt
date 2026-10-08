import json, urllib.request, os, sys
d=json.load(open('/tmp/opencode/vm.json'))
want=sys.argv[1:]
for w in want:
    m=[v for v in d['versions'] if v['id']==w]
    if not m: print('no',w); continue
    j=json.load(urllib.request.urlopen(m[0]['url'],timeout=30))
    dl=j.get('downloads',{}).get('client',{}).get('url')
    if not dl: print('no client dl for',w); continue
    out=f'client-{w}.jar'
    if os.path.exists(out): print('have',out); continue
    urllib.request.urlretrieve(dl,out)
    print(w, os.path.getsize(out)//1024//1024,'MB')
