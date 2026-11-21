exec(open('ft.py').read())
import struct
from PIL import Image, ImageDraw
def chunks(d):
    o=0
    while o+16<=len(d):
        v=struct.unpack_from('<I',d,o+4)[0]; t=v&0x7f; sz=((v>>7)&0x7ffff)*16
        yield o,t,sz
        if sz<=0: break
        o+=sz
def textures(path):
    d=open(G+'/'+path+'.DAT','rb').read(); out=[]
    for o,t,sz in chunks(d):
        if t!=0x20: continue
        flag=d[o+16]; name=d[o+17:o+33]
        bi=struct.unpack_from('<IiiHHIIiiII',d,o+33); w,h=bi[1],abs(bi[2])
        if flag==0xA1:
            fcc=d[o+73:o+77][::-1]; data=d[o+85:o+85+(w*h if fcc!=b'DXT1' else w*h//2)]
            n={b'DXT1':1,b'DXT3':2,b'DXT5':3}.get(fcc)
            try: im=Image.frombytes('RGBA',(w,h),data,'bcn',(n,))
            except Exception as e: continue
        elif flag in (0x91,0x81,0xB1):
            # 8-bit palettized: palette 256*4 then pixels
            pal=d[o+73:o+73+1024]; px=d[o+73+1024:o+73+1024+w*h]
            if len(px)<w*h: continue
            im=Image.frombytes('P',(w,h),px); im.putpalette(bytes(b for i in range(256) for b in (pal[i*4+2],pal[i*4+1],pal[i*4],)))
            im=im.convert('RGBA')
        else: continue
        out.append((name.decode('latin1').strip(),im.transpose(Image.FLIP_TOP_BOTTOM)))
    return out
def sheet(items,fn,cell=160):
    rows=[]
    for label,path in items:
        tx=textures(path) if path else []
        rows.append((label,tx))
    W=cell*7+180; H=cell*len(rows)
    S=Image.new('RGB',(W,H),(40,40,40)); dr=ImageDraw.Draw(S)
    for y,(label,tx) in enumerate(rows):
        dr.text((4,y*cell+4),label,fill=(255,255,0))
        for x,(n,im) in enumerate(tx[:7]):
            t=im.copy(); t.thumbnail((cell-4,cell-14))
            bg=Image.new('RGB',t.size,(128,128,128)); bg.paste(t,(0,0),t)
            S.paste(bg,(180+x*cell,y*cell+12)); dr.text((180+x*cell,y*cell),n[-10:],fill=(200,200,200))
    S.save(fn)
def sheet(items,fn,cell=150):
    rows=[(label,textures(path) if path else []) for label,path in items]
    W=cell*6+110; H=cell*len(rows)
    S=Image.new('RGB',(W,H),(30,30,30)); dr=ImageDraw.Draw(S)
    for y,(label,tx) in enumerate(rows):
        dr.text((4,y*cell+4),label,fill=(255,255,0))
        for x,(n,im) in enumerate(tx[:6]):
            t=im.convert('RGB'); t.thumbnail((cell-4,cell-14))
            S.paste(t,(110+x*cell,y*cell+12)); dr.text((110+x*cell,y*cell),n[-10:],fill=(200,200,200))
    S.save(fn)
