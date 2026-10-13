"""Measure the face features in a front image (reference or render).

    python3 scripts/face_landmarks.py references/02_Morfi_frente.png renders/views/front.png

Finds, by colour and connectivity, the glasses frame (largest very dark part),
its two lens openings, inside each opening the visible eye (everything that is
not celeste skin), the iris and the pupil, the brows (dark parts above the
frame) and the mouth (dark red part below), and prints their boxes relative to
the head (head width = 1, origin at the head's centre column and the frame's
top). One column per image, so the two values per feature say how much each
face parameter has to move.
"""
import sys

import numpy as np
from PIL import Image
from scipy import ndimage as ndi


def measure(path):
    a=np.asarray(Image.open(path).convert('RGB').resize((1145,1374),Image.LANCZOS)).astype(int)
    r,g,b=a[...,0],a[...,1],a[...,2]; lum=a.mean(-1)
    blue=(b>150)&(b-r>70)
    rows=np.nonzero(blue[:687].sum(1)>50)[0]; yw=int(np.argmax(blue[:687].sum(1))); xs=np.nonzero(blue[yw])[0]
    hx0,hx1=xs.min(),xs.max(); cx=(hx0+hx1)/2; hw=hx1-hx0
    dark=(lum<70)&(b>=r)
    reg=np.zeros_like(dark); reg[rows.min():rows.min()+hw, hx0-40:hx1+40]=True
    lab,n=ndi.label(dark&reg); sizes=ndi.sum(dark&reg,lab,range(1,n+1)); fl=np.argmax(sizes)+1
    fm=lab==fl; fy0=np.nonzero(fm.any(1))[0].min()
    holes=ndi.binary_fill_holes(fm)&~fm
    hl,hn=ndi.label(holes); hs=ndi.sum(holes,hl,range(1,hn+1))
    out={'hw':int(hw)}
    def rel(x, y):
        return round(float((x - cx) / hw), 4), round(float((y - fy0) / hw), 4)
    lens=[i+1 for i in np.argsort(hs)[::-1][:2]]
    lens=sorted(lens,key=lambda i: np.nonzero(hl==i)[1].mean())
    celeste=(b-r>70)&(lum>140)
    for k,li in enumerate(lens):
        op=hl==li
        ys,xs=np.nonzero(op); out[f'lens{k}']=(rel(xs.min(),ys.min()),rel(xs.max(),ys.max()))
        eye=op&~celeste
        eye=ndi.binary_opening(eye,iterations=3)
        el,en=ndi.label(eye); es=ndi.sum(eye,el,range(1,en+1)); em=el==(np.argmax(es)+1)
        ys,xs=np.nonzero(em); out[f'eye{k}']=(rel(xs.min(),ys.min()),rel(xs.max(),ys.max()), 'area/hw2', round(float(em.sum() / hw ** 2), 4))
        iris=em&(((lum<150)&(b>r+30))|(lum<45))
        iris=ndi.binary_opening(iris,iterations=2)
        il,inn=ndi.label(iris); isz=ndi.sum(iris,il,range(1,inn+1)); im=il==(np.argmax(isz)+1)
        ys,xs=np.nonzero(im); out[f'iris{k}']=(rel(xs.mean(),ys.mean()), 'r', round(float(np.sqrt(im.sum() / np.pi) / hw), 4))
        pu=em&(lum<40); pl,pn=ndi.label(pu); ps=ndi.sum(pu,pl,range(1,pn+1)); pm=pl==(np.argmax(ps)+1)
        ys,xs=np.nonzero(pm); out[f'pupil{k}']=(rel(xs.mean(),ys.mean()), 'r', round(float(np.sqrt(pm.sum() / np.pi) / hw), 4))
    # brows: dark comps above frame top
    bl,bn=ndi.label(dark&reg&~fm)
    br=[]
    for i,sl in enumerate(ndi.find_objects(bl)):
        m=bl[sl]==i+1
        if m.sum()<500 or sl[0].stop>fy0+5: continue
        ys,xs=np.nonzero(m); br.append((rel(xs.min()+sl[1].start, ys.min()+sl[0].start), rel(xs.max()+sl[1].start, ys.max()+sl[0].start), 'thick', round(float(m.sum() / (xs.max() - xs.min() + 1) / hw), 4)))
    out['brows']=sorted(br)
    mouth=(r>g+25)&(lum<170); mm=np.zeros_like(mouth); fy1=np.nonzero(fm.any(1))[0].max(); mm[fy1-20:fy1+int(hw*0.3), int(cx-hw*0.3):int(cx+hw*0.3)]=True
    ml,mn=ndi.label(mouth&mm); ms=ndi.sum(mouth&mm,ml,range(1,mn+1))
    if mn:
        m=ml==(np.argmax(ms)+1); ys,xs=np.nonzero(m); out['mouth']=(rel(xs.min(),ys.min()),rel(xs.max(),ys.max()))
    return out


def main():
    rs = [measure(p) for p in sys.argv[1:]]
    for k in rs[0]:
        print(f'{k:7s}', ' | '.join(str(r.get(k)) for r in rs))


if __name__ == '__main__':
    main()
