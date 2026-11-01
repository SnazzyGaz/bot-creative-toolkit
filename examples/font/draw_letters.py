# hand-drawn-style capitals: each stroke is a wobbly brush line, so tracing gives an organic outline
import math, random
from PIL import Image, ImageDraw
random.seed(7)
import os; os.makedirs("png", exist_ok=True); os.makedirs("svg", exist_ok=True)
S = 400  # canvas; letters sit between y=60 (top) and y=340 (baseline)
T, B = 60, 340
L = {  # strokes as point lists in a 0..1 box (x right, y down)
 "B": [[(0.2,0),(0.2,1)], [(0.2,0),(0.6,0),(0.75,0.1),(0.75,0.35),(0.6,0.47),(0.2,0.47)], [(0.2,0.47),(0.65,0.47),(0.82,0.6),(0.82,0.85),(0.65,1),(0.2,1)]],
 "O": [[(0.5+0.36*math.cos(t/24*2*math.pi), 0.5+0.5*math.sin(t/24*2*math.pi)) for t in range(26)]],
 "T": [[(0.05,0.02),(0.95,0)], [(0.5,0),(0.52,1)]],
 "S": [[(0.8,0.12),(0.62,0),(0.35,0),(0.18,0.12),(0.2,0.33),(0.45,0.47),(0.72,0.58),(0.84,0.78),(0.7,0.97),(0.4,1),(0.15,0.88)]],
 "R": [[(0.2,0),(0.2,1)], [(0.2,0),(0.6,0),(0.78,0.12),(0.78,0.38),(0.6,0.5),(0.2,0.5)], [(0.45,0.5),(0.85,1)]],
 "exclam": [[(0.5,0),(0.5,0.68)], [(0.5,0.92),(0.5,0.96)]],
 "Y": [[(0.1,0),(0.5,0.5)], [(0.9,0),(0.5,0.5),(0.5,1)]],
 "E": [[(0.25,0),(0.25,1)], [(0.25,0),(0.8,0)], [(0.25,0.5),(0.7,0.5)], [(0.25,1),(0.82,1)]],
}
def wob(pts, n=14, amp=5):
    out = []
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        for k in range(n):
            t = k / n
            out.append((x0 + (x1 - x0) * t, y0 + (y1 - y0) * t))
    out.append(pts[-1])
    return [(60 + x * 280 + random.uniform(-amp, amp) * 0.4, T + y * (B - T) + random.uniform(-amp, amp) * 0.4) for x, y in out]
for name, strokes in L.items():
    im = Image.new("L", (S, S), 255); d = ImageDraw.Draw(im)
    for st in strokes:
        pts = wob(st)
        for i, (p, q) in enumerate(zip(pts, pts[1:])):
            w = 44 + 12 * math.sin(i / 5.0)  # brush pressure
            d.line([p, q], fill=0, width=int(w)); d.ellipse([q[0]-w/2, q[1]-w/2, q[0]+w/2, q[1]+w/2], fill=0)
        for p in (pts[0], pts[-1]):
            d.ellipse([p[0]-24, p[1]-24, p[0]+24, p[1]+24], fill=0)
    im.save(f"png/{name}.png")
print("ok", list(L))
