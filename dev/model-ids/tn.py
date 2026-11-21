exec(open('ft.py').read())
import struct
def chunks(d):
    o=0
    while o+16<=len(d):
        v=struct.unpack_from('<I',d,o+4)[0]; t=v&0x7f; sz=((v>>7)&0x7ffff)*16
        yield o,t,sz,d[o:o+4]
        if sz<=0: break
        o+=sz
def tnames(path):
    d=open(G+'/'+path+'.DAT','rb').read()
    return [d[o+17:o+33].decode('latin1').split()[-1] for o,t,sz,n in chunks(d) if t==0x20], [n.decode('latin1') for o,t,sz,n in chunks(d) if t==42]
