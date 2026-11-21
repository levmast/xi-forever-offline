import sys,struct,re,collections,os
G=os.path.expanduser('~/mnt/PlayOnline/SquareEnix/FINAL FANTASY XI')
id2p={}
def load(vt,ftp,n):
    v=open(vt,'rb').read(); f=open(ftp,'rb').read()
    for i,b in enumerate(v):
        if b==n:
            x=struct.unpack_from('<H',f,2*i)[0]
            id2p[i]=('ROM' if n==1 else f'ROM{n}')+f'/{x>>7}/{x&127}'
load(G+'/VTABLE.DAT',G+'/FTABLE.DAT',1)
for n in range(2,10): load(f'{G}/ROM{n}/VTABLE{n}.DAT',f'{G}/ROM{n}/FTABLE{n}.DAT',n)
p2id={p:i for i,p in id2p.items()}
rows=[]
for m in re.finditer(r"VALUES \((\d+),'([^']*)',(\d+),(\d+),(\d+),(\d+),(\d+),(\d+),(\d+),(\d+),(\d+),(\d+)\)",open(os.path.expanduser('~/mnt/server/sql/item_equipment.sql'),encoding='utf8').read()):
    rows.append(tuple(int(x) if i!=1 else x for i,x in enumerate(m.groups())))
def norm(s): return re.sub(r"[^a-z0-9+]","",s.lower())
def av(race,fn):
    out=[]
    for line in open(f'av/List/PC/{race}/{fn}.csv',encoding='utf8',errors='replace'):
        p=line.strip().split(',',1)
        if len(p)<2 or '/' not in p[0]: continue
        out.append(('ROM/'+p[0].strip(),p[1].strip()))
    return out
RACES=['HumeM','HumeF','ElvaanM','ElvaanF','Tarutaru','Mithra','Galka']
SLOTS={16:'Head',32:'Body',64:'Hands',128:'Legs',256:'Feet'}
def bases():
    B={}
    for slot,fn in SLOTS.items():
        mid=collections.defaultdict(set)
        for r in rows:
            if r[8]==slot and r[5]>0: mid[norm(r[1])].add(r[5])
        for race in RACES:
            c=collections.Counter()
            for path,nm in av(race,fn):
                m=mid.get(norm(nm))
                if m and len(m)==1 and path in p2id and 440<=list(m)[0]<=500: c[p2id[path]-list(m)[0]]+=1
            B[(race,slot)]=c.most_common(3)
    return B
RBASE={'HumeM':0,'HumeF':1,'ElvaanM':2,'ElvaanF':3,'Tarutaru':4,'Mithra':5,'Galka':6}
SIDX={16:0,32:1,64:2,128:3,256:4}
def fid(race,slot,m): return 70927+RBASE[race]*1536+SIDX[slot]*256+m
used=collections.defaultdict(list)
for r in rows:
    if r[8] in SIDX and r[5]>0: used[(r[8],r[5])].append(r[1])
def ranges():
    R={}
    for slot,fn in SLOTS.items():
        mid=collections.defaultdict(set)
        for r in rows:
            if r[8]==slot and r[5]>0: mid[norm(r[1])].add(r[5])
        for race in RACES:
            pts=collections.defaultdict(list)
            for path,nm in av(race,fn):
                m=mid.get(norm(nm))
                if m and len(m)==1 and path in p2id:
                    mm=list(m)[0]; pts[p2id[path]-mm].append(mm)
            R[(race,slot)]=sorted([(min(v),max(v),o,len(v)) for o,v in pts.items() if len(v)>=3])
    return R
def offsets():
    R=ranges(); O={}
    for k,v in R.items():
        for lo,hi,o,n in v:
            band=0 if hi<256 else 1 if lo>=256 and hi<320 else 2 if lo>=320 and hi<576 else 3 if lo>=576 else None
            if band is not None and (k,band) not in O: O[(k,band)]=o
    return O
def band(m): return 0 if m<256 else 1 if m<320 else 2 if m<576 else 3
BANDLEN={0:256,1:64,2:256,3:32}
BANDLO={0:0,1:256,2:320,3:576}
def F(race,slot,m):
    r=RBASE[race]; s=SIDX[slot]; b=band(m)
    if b==1: return 63067+r*448+s*64+m
    if b==2: return 70927+r*1536+s*256+m
    if b==3: return 98211+r*160+s*32+m
    return None
NONE={}
for r in RACES:
    for s,fn in SLOTS.items():
        for path,nm in av(r,fn):
            if nm.lower()=='none': NONE[(r,s)]=p2id.get(path); break
def real(race,slot,m):
    i=F(race,slot,m); return i in id2p and i!=NONE.get((race,slot))
NONEP={k:id2p.get(v) for k,v in NONE.items()}
def real(race,slot,m):
    i=F(race,slot,m); return i in id2p and id2p[i]!=NONEP.get((race,slot))
def grid(ms):
    out={}
    for m in ms:
        row=''
        for s in SLOTS:
            n=sum(real(r,s,m) for r in RACES); u=bool(used.get((s,m)))
            row+=('U' if u else ('#' if n==7 else (str(n) if n else '.')))
        out[m]=row
    return out
PH={}
for r in RACES:
    for s in SLOTS:
        c=collections.Counter(id2p.get(F(r,s,m)) for m in list(range(256,320))+list(range(320,608)))
        PH[(r,s)]=c.most_common(1)[0][0]
def real(race,slot,m):
    i=F(race,slot,m); return i in id2p and id2p[i]!=PH[(race,slot)]
