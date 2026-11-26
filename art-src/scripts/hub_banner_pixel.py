# The Hub's banner (2026-11-25): Kaza's pixel art from the app's Ventures (zones + his six heroes). Run from a folder
# with the app's assets staged; writes hub_banner.jpg (960x240) and hub_banner_1920.png.
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import sys
U='/mnt/user-data/uploads/xifo-app/assets/'
W,H=960,240
def zone(n):
    bg=Image.open(U+'ventures/bg/'+n+'.png').convert('RGBA'); fg=Image.open(U+'ventures/fg/'+n+'.png').convert('RGBA'); bg.alpha_composite(fg); return bg
Y={'ssg':0,'sarutabaruta':40,'uleguerand':40,'gustaberg':40,'ronfaure':60}
def crop(n): y=Y[n]; return zone(n).crop((0,y,960,y+240))
canvas=Image.new('RGBA',(W,H))
# slices: (zone, x_top_start) slanted by 40px
cuts=[('ssg',-40),('sarutabaruta',380),('uleguerand',570),('gustaberg',760)]
slant=50
for i,(n,x0) in enumerate(cuts):
    img=crop(n)
    mask=Image.new('L',(W,H),0); d=ImageDraw.Draw(mask)
    x1=cuts[i+1][1] if i+1<len(cuts) else W+100
    d.polygon([(x0+slant,0),(x1+slant,0),(x1,H),(x0,H)],fill=255)
    canvas.paste(img,(0,0),mask)
# darken left text area with gradient
grad=Image.new('L',(W,1))
for x in range(W):
    a=int(max(0,min(1,(470-x)/220))*170)
    grad.putpixel((x,0),a)
grad=grad.resize((W,H))
dark=Image.new('RGBA',(W,H),(8,12,30,255)); dark.putalpha(grad); canvas.alpha_composite(dark)
# top fade (night sky feel) and bottom ground shade
vg=Image.new('L',(1,H))
for y in range(H): vg.putpixel((0,y), int(max(0,(40-y)/40)*120 + max(0,(y-170)/70)*110))
vg=vg.resize((W,H)); sh=Image.new('RGBA',(W,H),(6,8,20,255)); sh.putalpha(vg); canvas.alpha_composite(sh)
# glowing seams
seam=Image.new('RGBA',(W,H),(0,0,0,0)); sd=ImageDraw.Draw(seam)
for n,x0 in cuts[1:]:
    sd.line([(x0+slant,0),(x0,H)],fill=(255,214,120,255),width=3)
glow=seam.filter(ImageFilter.GaussianBlur(5)); canvas.alpha_composite(glow); canvas.alpha_composite(glow); canvas.alpha_composite(seam)
# heroes
xs=[455,535,615,695,775,855]
for i,x in enumerate(xs):
    sp=Image.open(U+f'ventures/p/k{i+1}.png').convert('RGBA').crop((0,0,128,128))
    bb=sp.getbbox(); sp=sp.crop(bb)
    sp=sp.resize((int(sp.width*1.25),int(sp.height*1.25)),Image.NEAREST)
    foot=226
    shadow=Image.new('RGBA',(W,H),(0,0,0,0)); ImageDraw.Draw(shadow).ellipse([x-26,foot-6,x+26,foot+5],fill=(0,0,0,120))
    canvas.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(2)))
    canvas.alpha_composite(sp,(x-sp.width//2,foot-sp.height))
# text
F='/mnt/user-data/uploads/xifo-app/assets/fonts/'
fb=ImageFont.truetype(F+'PixelifySans-Bold.ttf',84); fr=ImageFont.truetype(F+'PixelifySans-Regular.ttf',20); fs=ImageFont.truetype(F+'PixelifySans-Bold.ttf',17); ft=ImageFont.truetype(F+'PixelifySans-Regular.ttf',11)
d=ImageDraw.Draw(canvas)
GOLD=(255,206,102); 
d.text((36,26),'XI: FOREVER OFFLINE',font=fr,fill=GOLD)
d.text((36+4,52+5),'THE HUB',font=fb,fill=(120,60,10))
d.text((36,52),'THE HUB',font=fb,fill=(255,250,235),stroke_width=3,stroke_fill=(20,14,40))
d.text((38,148),'WHERE WORLDS MEET',font=fr,fill=(220,232,255),stroke_width=2,stroke_fill=(10,10,30))
# badge
txt='BRING YOUR OWN RATES'; tw=d.textlength(txt,font=fs)
bx,by=36,182; d.rounded_rectangle([bx,by,bx+tw+28,by+30],radius=6,fill=(22,26,60),outline=GOLD,width=2)
d.text((bx+14,by+5),txt,font=fs,fill=GOLD)
d.text((W-118,H-15),'pixel art by Kaza',font=ft,fill=(230,230,240),stroke_width=1,stroke_fill=(0,0,0))
# frame
d.rectangle([0,0,W-1,H-1],outline=GOLD,width=2); d.rectangle([4,4,W-5,H-5],outline=(120,90,40),width=1)
out=canvas.convert('RGB'); out.save('/home/claude/hub/hub_banner.png')
big=canvas.resize((1920,480),Image.NEAREST); big.save('/home/claude/hub/hub_banner_1920.png')
out.save('/home/claude/hub/hub_banner.jpg',quality=92)
import os; print(os.path.getsize('/home/claude/hub/hub_banner.jpg'))
