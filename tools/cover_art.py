"""Deterministic, offline library artwork. Standard BMP needs no device decoder dependency."""
from pathlib import Path
import hashlib
import math
import struct

WIDTH, HEIGHT = 480, 192


def artwork(app_id, name):
    seed = hashlib.sha256((app_id + '\n' + name).encode()).digest()
    pixels = bytearray(WIDTH * HEIGHT * 3)
    words = (app_id + ' ' + name).lower()
    music = any(s in words for s in ('beat', 'music', 'drum', 'synth', 'audio'))
    visual = any(s in words for s in ('light', 'orchestra', 'paint', 'color', 'visual', 'art'))
    blocks = any(s in words for s in ('block', 'voxel', 'world', 'craft'))
    panel = any(s in words for s in ('panel', 'counter', 'instrument'))
    bg = (29, 22, 40) if music else (7, 12, 24) if visual else (20, 39, 43) if blocks else (40,17,50) if panel else (32 + seed[0] % 32, 25 + seed[1] % 32, 45 + seed[2] % 32)
    bg = tuple(c + seed[i] % 7 for i, c in enumerate(bg))
    for y in range(HEIGHT):
        for x in range(WIDTH):
            glow = max(0, 1 - ((x-WIDTH*.5)/WIDTH)**2*3 - ((y-HEIGHT*.5)/HEIGHT)**2*2)
            k=(y*WIDTH+x)*3
            pixels[k:k+3]=bytes(min(255, c+int(glow*9)) for c in bg)

    def pixel(x,y,color,alpha=1):
        x,y=int(x),int(y)
        if 0<=x<WIDTH and 0<=y<HEIGHT:
            k=(y*WIDTH+x)*3
            for j in range(3):pixels[k+j]=min(255,int(pixels[k+j]*(1-alpha)+color[j]*alpha))
    def disc(x,y,r,color,alpha=1):
        for yy in range(max(0,int(y-r)),min(HEIGHT,int(y+r)+1)):
            for xx in range(max(0,int(x-r)),min(WIDTH,int(x+r)+1)):
                edge=max(0,min(1,r-math.hypot(xx-x,yy-y)))
                if edge:pixel(xx,yy,color,alpha*edge)
    def line(x0,y0,x1,y1,color,width=1,alpha=1):
        steps=max(1,int(max(abs(x1-x0),abs(y1-y0))))
        for i in range(steps+1):
            t=i/steps;disc(x0+(x1-x0)*t,y0+(y1-y0)*t,width,color,alpha)
    def rect(x,y,w,h,color):
        for yy in range(max(0,y),min(HEIGHT,y+h)):
            for xx in range(max(0,x),min(WIDTH,x+w)):pixel(xx,yy,color)
    def poly(points,color):
        for y in range(max(0,int(min(p[1] for p in points))),min(HEIGHT,int(max(p[1] for p in points))+1)):
            xs=[]
            for i,(x0,y0) in enumerate(points):
                x1,y1=points[(i+1)%len(points)]
                if min(y0,y1)<=y<max(y0,y1):xs.append(x0+(y-y0)/(y1-y0)*(x1-x0))
            xs.sort()
            for a,b in zip(xs[::2],xs[1::2]):
                for x in range(int(a),int(b)+1):pixel(x,y,color)

    if music:
        colors=[(247,130,116),(242,192,103),(153,213,181),(174,161,237)]
        shift = seed[8] % 4
        for row,c in enumerate(colors):
            c = tuple(max(0, min(255, v + seed[10+row*3+j] % 25 - 12)) for j,v in enumerate(c))
            disc(43,45+row*31,10,c)
            for step in range(16):
                active=((step+shift)%16 in ((0,8,11) if row==0 else (4,12) if row==1 else tuple(range(0,16,2)) if row==2 else (7,14)))
                rect(77+step*23,33+row*31,18,23,c if active else (59,45,72))
        for x in range(30,450):
            y=169+math.sin(x*.08)*math.sin(x*.023)*8
            disc(x,y,1.5,(237,166,212),.8)
    elif visual:
        colors=[(93,242,209),(96,159,255),(182,124,255),(255,155,216)]
        for ring in range(3):
            previous=None
            for i in range(721):
                a=i*math.pi/360;radius=49+ring*9+14*math.sin(6*a+ring*.4+seed[8]*.01)
                x=240+math.cos(a)*radius*1.65;y=96+math.sin(a)*radius
                c=colors[(i//180+ring)%4]
                if previous:
                    line(*previous,x,y,c,4,.04);line(*previous,x,y,c,1.5,.85)
                previous=(x,y)
        for i in range(50):
            x=(seed[i%32]*31+i*37)%WIDTH;y=(seed[(i+9)%32]*17+i*29)%HEIGHT
            disc(x,y,1.5,colors[i%4],.35)
    elif blocks:
        disc(405,42,19,(244,191,124),.9)
        def cube(x,y,w,h,top,left,right):
            d=w*.42
            poly([(x,y-h),(x+w,y+d-h),(x,y+2*d-h),(x-w,y+d-h)],top)
            poly([(x-w,y+d-h),(x,y+2*d-h),(x,y+2*d),(x-w,y+d)],left)
            poly([(x,y+2*d-h),(x+w,y+d-h),(x+w,y+d),(x,y+2*d)],right)
        for row,col in sorted(((r,c) for r in range(5) for c in range(7)),key=lambda p:sum(p)):
            x=215+(col-row)*24;y=47+(col+row)*10
            height=14+((col*7+row*3+seed[0])%3)*9
            cube(x,y,24,height,(134,194,145),(63,111,92),(42,77,75))
        for row,col in ((1,2),(2,4),(4,5)):
            x=215+(col-row)*24;y=47+(col+row)*10
            height=14+((col*7+row*3+seed[0])%3)*9
            ground=y+10-height
            cube(x,ground-4,5,25,(190,147,104),(130,91,70),(91,65,57))
            cube(x,ground-25,19,23,(173,215,142),(99,158,118),(63,118,99))
    elif panel:
        # A simple counter and physical controls echo the native starter app.
        rect(37,32,243,127,(57,28,67))
        segments=((8,0,32,5),(40,5,5,34),(40,44,5,34),(8,78,32,5),(3,44,5,34),(3,5,5,34),(8,39,32,5))
        for digit,mask in enumerate((0x3f,0x66,0x5b)):
            for index,(x,y,w,h) in enumerate(segments):
                rect(60+digit*70+x,54+y,w,h,(255,160,215) if mask&(1<<index) else (77,43,82))
        for i,c in enumerate(((255,160,215),(176,155,231),(255,222,246))):
            disc(323+i*47,66,14,c)
            rect(312+i*47,108,22,28+i*9,c)
        line(313,155,432,155,(213,169,205))
    else:
        colors=[(127+seed[3]%100,150+seed[4]%90,155+seed[5]%90),(244,190,126),(166,190,235)]
        for band in range(5):
            previous=None
            for x in range(40,441,2):
                y=96+math.sin(x*.016+band*.55+seed[6])*(32+band*9)
                if previous:line(*previous,x,y,colors[band%3],2,.7)
                previous=(x,y)
        for i in range(7):disc(65+i*57,38+(seed[i]%4)*35,3,colors[i%3])
    return pixels


def write_cover(path, app_id, name):
    path=Path(path)
    if path.exists():
        return False
    rgb=artwork(app_id,name)
    stride=(WIDTH*3+3)&~3
    body=bytearray()
    for y in range(HEIGHT-1,-1,-1):
        row=rgb[y*WIDTH*3:(y+1)*WIDTH*3]
        for x in range(WIDTH):body.extend((row[x*3+2],row[x*3+1],row[x*3]))
        body.extend(b'\0'*(stride-WIDTH*3))
    header=b'BM'+struct.pack('<IHHI',54+len(body),0,0,54)
    header+=struct.pack('<IiiHHIIiiII',40,WIDTH,HEIGHT,1,24,0,len(body),2835,2835,0,0)
    # Exclusive creation preserves author-provided artwork, including in races.
    try:
        with path.open('xb') as f:f.write(header+body)
    except FileExistsError:
        return False
    return True
