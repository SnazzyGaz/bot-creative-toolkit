#!/usr/bin/env bash
# End-to-end test of every tool. Prints one line per check and exits non-zero if any check fails.
#   ./selftest.sh            (runs with no DISPLAY, like a headless box)
#   KEEP=1 ./selftest.sh     keep the output folder to look at
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BCT="$HERE/bin/bct"
export PATH="$HOME/.local/bin:$PATH"
unset DISPLAY WAYLAND_DISPLAY
T="$(mktemp -d /tmp/bct-selftest.XXXX)"
PASS=0; FAIL=0; SKIP=0; FAILED=()
START=$(date +%s)
ok()   { PASS=$((PASS+1)); printf 'PASS  %s\n' "$1"; }
bad()  { FAIL=$((FAIL+1)); FAILED+=("$1"); printf 'FAIL  %s\n' "$1"; [ -n "${2:-}" ] && printf '      %s\n' "$2"; }
skip() { SKIP=$((SKIP+1)); printf 'SKIP  %s (%s)\n' "$1" "$2"; }
# check NAME -- command...   (passes if the command exits 0)
check() { local n="$1"; shift; local out; if out="$("$@" 2>&1)"; then ok "$n"; else bad "$n" "$(printf '%s' "$out" | tail -n 4 | tr '\n' ' ')"; fi; }
py() { python3 -c "$1"; }   # small inline assertions

# ---------- 0. tools installed ----------
check "setup: everything installed (setup.sh --check)" "$HERE/setup.sh" --check

# ---------- 1. render-and-look ----------
check "look: .py scene -> 4-view contact sheet" "$BCT" look "$HERE/examples/scene_example.py" -o "$T/sheet.png" \
      --save-blend "$T/scene.blend" --size 200 --samples 8
check "look: sheet is 2x2 tiles and not blank" py "
from PIL import Image, ImageStat
im=Image.open('$T/sheet.png').convert('L'); w,h=im.size
assert w==400 and h>400, im.size
assert ImageStat.Stat(im).stddev[0]>10, 'sheet looks blank'"
check "look: .blend file input, 2 views, workbench engine" "$BCT" look "$T/scene.blend" -o "$T/sheet_blend.png" \
      --views front,top --size 160 --engine workbench --clay
check "look: bad view name is rejected" sh -c "! '$BCT' look '$T/scene.blend' --views sideways >/dev/null 2>&1"
MQA="${MODEL_QA:-$(command -v model-qa || true)}"
if [ -n "$MQA" ]; then
  check "look --qa: model-qa check --look runs" sh -c "'$BCT' look '$T/scene.blend' -o '$T/sheet_qa.png' --size 120 \
      --views front --qa --qa-args '--profile render' > '$T/qa.json'"
  check "look --qa: model-qa wrote a report" py "
import json; r=json.load(open('$T/qa.json'))['model_qa']
assert r.get('exit_code') in (0,1), r; assert r.get('report'), r"
else
  skip "look --qa (model-qa)" "model-qa not installed"
  check "look --qa: skips cleanly without model-qa" py "
import json,subprocess
r=json.loads(subprocess.run(['$BCT','look','$T/scene.blend','-o','$T/sheet_qa.png','--size','96','--views','front','--qa'],capture_output=True,text=True,check=True).stdout)
assert 'skipped' in r['model_qa']"
fi

# ---------- 2. layered images ----------
py "
from PIL import Image, ImageDraw
im=Image.new('RGBA',(60,60),(0,0,0,0)); d=ImageDraw.Draw(im); d.ellipse([0,0,59,59],fill=(0,160,0,255)); im.save('$T/green.png')
im=Image.new('RGBA',(60,60),(0,0,255,255)); im.save('$T/blue.png')"
cat > "$T/stack.json" <<J
{"width": 240, "height": 160, "background": "#ffffff", "layers": [
 {"id": "bg",    "type": "fill", "color": "#202040", "to": "#8080c0"},
 {"id": "box",   "type": "rect", "x": 10, "y": 10, "w": 80, "h": 60, "fill": "#ff0000", "radius": 8},
 {"id": "pic",   "type": "image", "src": "green.png", "x": 150, "y": 20},
 {"id": "shade", "type": "rect", "x": 0, "y": 100, "w": 240, "h": 60, "fill": "#808080", "blend": "multiply"},
 {"id": "dot",   "type": "ellipse", "x": 100, "y": 20, "w": 30, "h": 30, "fill": "#ffff00", "opacity": 0.5},
 {"id": "zig",   "type": "line", "points": [[10,140],[60,110],[110,140]], "color": "#ffffff", "width": 3},
 {"id": "tri",   "type": "polygon", "points": [[0,30],[15,0],[30,30]], "x": 200, "y": 110, "fill": "#ffa500"},
 {"id": "title", "type": "text", "text": "Hi", "x": 20, "y": 75, "size": 20, "color": "#ffffff", "rotate": 10}
]}
J
check "layers: render stack (7 types, blend, opacity) to PNG + ORA" "$BCT" layers render "$T/stack.json" -o "$T/stack.png" --ora "$T/stack.ora"
check "layers: pixels are right (rect, image, opacity, multiply)" py "
from PIL import Image
im=Image.open('$T/stack.png').convert('RGB')
r=im.getpixel((50,40)); assert r[0]>240 and r[1]<20, ('box',r)
g=im.getpixel((180,50)); assert g[1]>140 and g[0]<20, ('pic',g)
y=im.getpixel((115,35)); assert 120<y[0]<255 and y[2]<200, ('dot 50%',y)
bg=im.getpixel((5,130)); assert bg[0]<0.6*255, ('multiply',bg)"
check "layers: ORA is valid (mimetype first, stack.xml, 9 layers)" py "
import zipfile,xml.etree.ElementTree as E
z=zipfile.ZipFile('$T/stack.ora'); n=z.namelist(); assert n[0]=='mimetype' and z.read('mimetype')==b'image/openraster'
assert z.getinfo('mimetype').compress_type==0; s=E.fromstring(z.read('stack.xml')); assert len(s.findall('.//layer'))==9
assert 'mergedimage.png' in n"
check "layers: second render redraws nothing (cache)" py "
import json,subprocess
r=json.loads(subprocess.run(['$BCT','layers','render','$T/stack.json','-o','$T/stack2.png'],capture_output=True,text=True,check=True).stdout)
assert r['drawn']==[] and len(r['cached'])==8, r"
check "layers: replace one image -> only that layer redrawn" py "
import json,subprocess
r=json.loads(subprocess.run(['$BCT','layers','replace','$T/stack.json','pic','--src','blue.png','--render','-o','$T/stack3.png'],capture_output=True,text=True,check=True).stdout)['render']
assert r['drawn']==['pic'], r
from PIL import Image; p=Image.open('$T/stack3.png').convert('RGB').getpixel((180,50)); assert p[2]>240 and p[1]<20, p"
check "layers: move, hide, set, reorder, add, remove" sh -c "
'$BCT' layers move '$T/stack.json' box --to 120 90 >/dev/null &&
'$BCT' layers hide '$T/stack.json' dot >/dev/null &&
'$BCT' layers set  '$T/stack.json' title text='\"Bye\"' color='\"#00ffff\"' >/dev/null &&
'$BCT' layers reorder '$T/stack.json' bg --top >/dev/null &&
'$BCT' layers reorder '$T/stack.json' bg --bottom >/dev/null &&
'$BCT' layers add '$T/stack.json' '{\"id\":\"tmp\",\"type\":\"rect\",\"w\":5,\"h\":5,\"fill\":\"#000\"}' --at 1 >/dev/null &&
'$BCT' layers remove '$T/stack.json' tmp >/dev/null &&
'$BCT' layers render '$T/stack.json' -o '$T/stack4.png' --ora '$T/stack4.ora' >/dev/null"
check "layers: edits show up (box moved, dot hidden, order kept)" py "
import json; from PIL import Image
s=json.load(open('$T/stack.json')); ids=[l['id'] for l in s['layers']]
assert ids==['bg','box','pic','shade','dot','zig','tri','title'], ids
im=Image.open('$T/stack4.png').convert('RGB')
assert im.getpixel((160,95))[0]>200 and im.getpixel((160,95))[1]<60, 'box not moved'
assert im.getpixel((50,40))[0]<150, 'old box still there'
assert im.getpixel((115,35))[2]>im.getpixel((115,35))[1], 'dot not hidden'"
check "layers: ORA -> JSON stack -> same picture" sh -c "
'$BCT' layers from-ora '$T/stack4.ora' -o '$T/back.json' >/dev/null &&
'$BCT' layers render '$T/back.json' -o '$T/back.png' >/dev/null && python3 -c \"
from PIL import Image, ImageChops
a=Image.open('$T/stack4.png').convert('RGB'); b=Image.open('$T/back.png').convert('RGB')
d=ImageChops.difference(a,b).getextrema(); assert max(x[1] for x in d)<=3, d\""

# ---------- 3. GIMP ----------
if command -v gimp-console >/dev/null || command -v gimp >/dev/null; then
  check "gimp: opens our ORA and exports a flat PNG that matches" sh -c "
'$BCT' gimp convert '$T/stack4.ora' '$T/gimp_flat.png' >/dev/null && python3 -c \"
from PIL import Image, ImageChops
a=Image.open('$T/stack4.png').convert('RGB'); b=Image.open('$T/gimp_flat.png').convert('RGB')
assert a.size==b.size; d=ImageChops.difference(a,b).convert('L'); h=d.histogram()
close=sum(h[:16])/sum(h); assert close>0.97, close\""
  check "gimp: ORA -> layered PSD" sh -c "'$BCT' gimp convert '$T/stack4.ora' '$T/stack.psd' >/dev/null && head -c4 '$T/stack.psd' | grep -q 8BPS"
else
  bad "gimp: not installed"
fi

# ---------- 4. vectors ----------
py "
from PIL import Image, ImageDraw
im=Image.new('RGB',(200,120),'white'); d=ImageDraw.Draw(im)
d.ellipse([10,10,100,100],fill='black'); d.rectangle([120,20,190,100],fill=(200,30,30)); d.point([(5,115),(6,115)],fill='black')
im.save('$T/logo.png')"
check "vector: trace bitmap -> SVG (threshold, despeckle)" sh -c "'$BCT' vector trace '$T/logo.png' -o '$T/logo.svg' --threshold 0.6 --despeckle 4 --color '#123456' > '$T/trace.json'"
check "vector: trace has paths and the specks are gone" py "
import json; r=json.load(open('$T/trace.json')); assert 1<=r['paths']<=3, r"
check "vector: 3-colour trace makes one group per colour" py "
import json,subprocess
r=json.loads(subprocess.run(['$BCT','vector','trace','$T/logo.png','-o','$T/logo3.svg','--colors','3'],capture_output=True,text=True,check=True).stdout)
assert len(r['groups'])==2, r"
check "vector: new + add rect/circle/text/path + set + recolor + delete" sh -c "
'$BCT' vector new '$T/art.svg' --size 200x100 --background '#ffffff' >/dev/null &&
'$BCT' vector add '$T/art.svg' rect x=10 y=10 width=60 height=60 fill=#000000 --id box >/dev/null &&
'$BCT' vector add '$T/art.svg' circle cx=150 cy=50 r=30 fill=#00ff00 --id dot >/dev/null &&
'$BCT' vector add '$T/art.svg' path d='M80 90 L120 10' stroke=#0000ff stroke-width=4 fill=none --id stroke1 >/dev/null &&
'$BCT' vector add '$T/art.svg' text x=10 y=95 font-size=14 font-family=sans-serif --text 'hello' --id label >/dev/null &&
'$BCT' vector set '$T/art.svg' --id box x=20 >/dev/null &&
'$BCT' vector recolor '$T/art.svg' --from '#000' --to '#ff0000' >/dev/null &&
'$BCT' vector delete '$T/art.svg' --id dot >/dev/null &&
'$BCT' vector list '$T/art.svg' > '$T/list.json'"
check "vector: list shows the edits" py "
import json; e={x['id']:x for x in json.load(open('$T/list.json'))['elements']}
assert 'dot' not in e and e['box']['fill']=='#ff0000' and e['box']['x']=='20' and e['label']['text']=='hello', e"
check "vector: Inkscape export to PNG at a set width" sh -c "'$BCT' vector export '$T/art.svg' -o '$T/art.png' --width 400 > '$T/exp.json'"
check "vector: exported pixels match the SVG (red box, no circle)" py "
from PIL import Image
im=Image.open('$T/art.png').convert('RGB'); assert im.size==(400,200), im.size
p=im.getpixel((100,80)); assert p[0]>200 and p[1]<50, ('box',p)
q=im.getpixel((300,100)); assert min(q)>200, ('dot should be gone',q)"
check "vector: traced SVG exports too" "$BCT" vector export "$T/logo3.svg" -o "$T/logo3.png" --background "#ffffff"

# ---------- 5. video (FFmpeg) ----------
mkdir -p "$T/frames"
py "
from PIL import Image, ImageDraw
for i in range(30):
    im=Image.new('RGB',(161,121),(20,20,40)); d=ImageDraw.Draw(im)
    d.ellipse([10+4*i,40,50+4*i,80],fill=(255,int(8*i),0)); im.save('$T/frames/f_%04d.png'%i)"
check "video: 30 frames (odd size) -> MP4 at 15 fps" sh -c "'$BCT' video encode '$T/frames' -o '$T/clip.mp4' --fps 15 > '$T/v1.json'"
check "video: ffprobe says h264, 30 frames, 2.0 s, even size, yuv420p" py "
import json; v=json.load(open('$T/v1.json'))
assert v['codec']=='h264' and v['frames']==30 and abs(v['duration']-2.0)<0.05, v
assert v['width']%2==0 and v['height']%2==0 and v['pix_fmt']=='yuv420p', v"
check "video: printf pattern -> GIF keeps all 30 frames" sh -c "'$BCT' video encode '$T/frames/f_%04d.png' -o '$T/clip.gif' --fps 15 --width 120 > '$T/v2.json'"
check "video: GIF is 120 px wide with 30 frames" py "
import json; v=json.load(open('$T/v2.json')); assert v['codec']=='gif' and v['frames']==30 and v['width']==120, v"
check "video: trim 0.5 s + 1.0 s gives exactly 15 frames (MP4 and GIF)" sh -c "
'$BCT' video trim '$T/clip.mp4' -o '$T/cut.mp4' --start 0.5 --duration 1 > '$T/v3.json' &&
'$BCT' video trim '$T/clip.gif' -o '$T/cut.gif' --start 0.5 --end 1.5 > '$T/v4.json'"
check "video: trimmed frame counts and durations" py "
import json
for f in ('v3','v4'):
    v=json.load(open('$T/'+f+'.json')); assert v['frames']==15 and abs(v['duration']-1.0)<0.1, (f,v)  # GIF delays are whole 1/100 s"
check "video: frame contact sheet, 3x2, not blank" sh -c "'$BCT' video sheet '$T/clip.mp4' -o '$T/vsheet.png' --count 6 --cols 3 --width 100 >/dev/null" 
check "video: sheet size and content" py "
from PIL import Image, ImageStat
im=Image.open('$T/vsheet.png'); w,h=im.size; assert w==300 and h>150, im.size
assert ImageStat.Stat(im.convert('L')).stddev[0]>10"
check "video: turntable of a model, 8 frames -> MP4 + GIF" sh -c "'$BCT' video turntable '$T/scene.blend' -o '$T/turn.mp4' \
      --gif '$T/turn.gif' --frames 8 --fps 8 --size 96 --samples 4 > '$T/v5.json'"
check "video: turntable outputs have 8 frames, 1.0 s" py "
import json; v=json.load(open('$T/v5.json'))
assert v['frames_rendered']==8 and v['mp4']['frames']==8 and v['gif']['frames']==8 and abs(v['mp4']['duration']-1.0)<0.05, v"
check "video: turntable frames differ (the camera moves)" py "
import subprocess
from PIL import Image, ImageChops, ImageStat
a=[subprocess.run(['ffmpeg','-v','error','-i','$T/turn.mp4','-vf','select=eq(n\,%d)'%n,'-frames:v','1','-y','$T/tt%d.png'%n]) for n in (0,2)]
d=ImageChops.difference(Image.open('$T/tt0.png').convert('L'),Image.open('$T/tt2.png').convert('L'))
assert ImageStat.Stat(d).mean[0]>1, 'frames identical'"

# ---------- 6. img (ImageMagick 7) ----------
check "img: fit + pad a 161x121 image into 100x100" sh -c "'$BCT' img resize '$T/frames/f_0000.png' -o '$T/pad.png' --fit 100x100 --pad --background '#ffffff' > '$T/i1.json'"
check "img: padded result is exactly 100x100" py "
import json; o=json.load(open('$T/i1.json'))['outputs'][0]; assert (o['width'],o['height'])==(100,100), o"
check "img: fill crops to the exact box" sh -c "'$BCT' img resize '$T/frames/f_0000.png' -o '$T/fill.png' --fill 64x96 | grep -q '\"width\": 64'"
check "img: icon set 16..512 + .ico" sh -c "'$BCT' img icons '$T/green.png' -o '$T/icons' --ico app.ico > '$T/i2.json'"
check "img: every PNG has its size and the .ico holds 16..256" py "
import json; r=json.load(open('$T/i2.json'))
assert [(p['width'],p['height']) for p in r['pngs']]==[(s,s) for s in (16,32,48,64,128,256,512)], r['pngs']
assert sorted(s[0] for s in r['ico']['sizes'])==[16,32,48,64,128,256], r['ico']"
check "img: icon keeps transparency in the corners" py "
from PIL import Image; im=Image.open('$T/icons/icon-64.png').convert('RGBA'); assert im.getpixel((0,0))[3]==0 and im.getpixel((32,32))[3]==255"
check "img: montage of 6 frames, 3 columns" sh -c "'$BCT' img montage '$T'/frames/f_000[0-5].png -o '$T/grid.png' --cols 3 --tile 50 --gap 5 > '$T/i3.json'"
check "img: montage is 3x2 cells of 60 px" py "
import json; m=json.load(open('$T/i3.json'))['montage']; assert (m['width'],m['height'])==(180,120), m"
check "img: convert PNG -> WebP and JPEG" sh -c "'$BCT' img convert '$T/frames/f_0000.png' -o '$T/f.webp' --quality 80 | grep -q WEBP && '$BCT' img convert '$T/frames/f_0000.png' -o '$T/f.jpg' --strip | grep -q JPEG"
check "img: crop --circle clears the corners" sh -c "'$BCT' img crop '$T/blue.png' -o '$T/round.png' --circle >/dev/null && python3 -c \"
from PIL import Image; im=Image.open('$T/round.png').convert('RGBA'); assert im.getpixel((0,0))[3]==0 and im.getpixel((30,30))[3]==255\""
check "img: adjust saturation 0 gives grey pixels" sh -c "'$BCT' img adjust '$T/frames/f_0010.png' -o '$T/grey.png' --saturation 0 >/dev/null && python3 -c \"
from PIL import Image; p=Image.open('$T/grey.png').convert('RGB').getpixel((90,60)); assert max(p)-min(p)<=3, p\""

# ---------- 7. scad (OpenSCAD) ----------
check "scad: params lists the Customizer variables" sh -c "'$BCT' scad params '$HERE/examples/phone_stand.scad' | grep -q '\"name\": \"angle\"'"
check "scad: phone stand -> STL + PNG with -D width=100" sh -c "'$BCT' scad render '$HERE/examples/phone_stand.scad' -o '$T/stand.stl' \
      -D width=100 -D depth=110 --png '$T/stand.png' --size 320x240 > '$T/s1.json'"
check "scad: STL is valid, non-empty, and its box matches the parameters" py "
import json; r=json.load(open('$T/s1.json')); s=r['stl']
assert s['triangles']>20, s
assert abs(s['size_mm'][0]-100)<0.01 and abs(s['size_mm'][1]-110)<0.01, s
assert abs(r['bbox_mm']['size'][0]-s['size_mm'][0])<0.01, (r['bbox_mm'],s)"
check "scad: preview PNG is the right size and not blank" py "
from PIL import Image, ImageStat
im=Image.open('$T/stand.png').convert('L'); assert im.size==(320,240), im.size
assert ImageStat.Stat(im).stddev[0]>15, 'preview looks blank'"
check "scad: -S string parameter and echo() are reported" sh -c "printf 'name=\"x\";\necho(name);\ncube(5);\n' > '$T/s.scad' &&
      '$BCT' scad render '$T/s.scad' -o '$T/s.stl' -S 'name=hi \"there\"' | grep -q 'hi'"
check "scad: a 2D-only model is refused with a clear error" sh -c "echo 'square(5);' > '$T/flat.scad' && ! '$BCT' scad render '$T/flat.scad' -o '$T/flat.stl' >/dev/null 2>&1"
check "scad: Blender sheet of the STL (mm -> m)" sh -c "'$BCT' scad render '$HERE/examples/phone_stand.scad' -o '$T/stand2.stl' --sheet '$T/stand_sheet.png' --sheet-size 120 > '$T/s2.json'"
check "scad: sheet sees an 8 cm wide object" py "
import json; s=json.load(open('$T/s2.json'))['sheet']; assert abs(s['size_m'][0]-0.08)<0.001, s"

# ---------- 8. fx (G'MIC) ----------
if command -v gmic >/dev/null; then
  py "from PIL import Image; Image.open('$HERE/docs/images/compare_poster.png').convert('RGB').resize((240,160)).save('$T/fx_in.png')"
  for s in painting watercolor cartoon sketch halftone glow; do
    check "fx: $s style runs" sh -c "'$BCT' fx apply '$T/fx_in.png' -o '$T/fx_$s.png' --style $s > '$T/fx_$s.json'"
  done
  check "fx: every style changed the pixels and kept the size" py "
import json
from PIL import Image
src=Image.open('$T/fx_in.png')
for s in 'painting watercolor cartoon sketch halftone glow'.split():
    r=json.load(open('$T/fx_%s.json'%s)); assert r['change']>5, (s, r['change'])
    assert Image.open('$T/fx_%s.png'%s).size==src.size, s"
  check "fx: sketch is close to grey, cartoon keeps colour" py "
from PIL import Image, ImageStat
sat=lambda f: ImageStat.Stat(Image.open(f).convert('HSV')).mean[1]
assert sat('$T/fx_cartoon.png')>2*sat('$T/fx_sketch.png') or sat('$T/fx_sketch.png')<40, (sat('$T/fx_cartoon.png'),sat('$T/fx_sketch.png'))"
  check "fx: strip of 3 styles + original" sh -c "'$BCT' fx strip '$T/fx_in.png' -o '$T/fx_strip.png' --styles cartoon,glow,halftone --tile 120 > '$T/fx_strip.json'"
  check "fx: strip is 4 tiles wide" py "
from PIL import Image; w,h=Image.open('$T/fx_strip.png').size; assert w==4*120+5*6, (w,h)"
  check "fx: raw pipeline passthrough (blur) changes pixels" sh -c "'$BCT' fx run '$T/fx_in.png' -o '$T/fx_blur.png' -- blur 4 | python3 -c 'import json,sys; assert json.load(sys.stdin)[\"change\"]>1'"
  check "fx: unknown style is rejected" sh -c "! '$BCT' fx apply '$T/fx_in.png' -o '$T/x.png' --style nope >/dev/null 2>&1"
  if "$BCT" fx list --all >/dev/null 2>&1; then
    check "fx: GUI filter by name with its defaults" sh -c "'$BCT' fx gui 'Old Photograph' '$T/fx_in.png' -o '$T/fx_gui.png' | python3 -c 'import json,sys; r=json.load(sys.stdin); assert r[\"change\"]>5 and r[\"pipeline\"].startswith(\"fx_old_photo\"), r'"
    check "fx: GUI filter list has hundreds of filters" sh -c "'$BCT' fx list --all | python3 -c 'import json,sys; assert json.load(sys.stdin)[\"gui_filters\"]>200'"
  else skip "fx gui filters" "G'MIC filter list not downloaded"; fi
else skip "fx (G'MIC)" "gmic not installed"; fi

# ---------- 9. font (FontForge) ----------
if command -v fontforge >/dev/null; then
  mkdir -p "$T/glyphs"
  printf '<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100"><rect x="40" y="0" width="20" height="100"/></svg>' > "$T/glyphs/I.svg"
  printf '<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100"><path d="M10 0 H30 V80 H90 V100 H10 Z"/></svg>' > "$T/glyphs/L.svg"
  printf '<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100"><path fill-rule="evenodd" d="M50 0 A50 50 0 1 0 50.01 0 Z M50 20 A30 30 0 1 1 49.99 20 Z"/></svg>' > "$T/glyphs/O.svg"
  printf '<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100"><rect x="40" y="80" width="20" height="20"/></svg>' > "$T/glyphs/period.svg"
  check "font: build a TTF from 4 SVG glyphs + specimen" sh -c "'$BCT' font build '$T/glyphs' -o '$T/f.ttf' --name 'Bct Test' --specimen '$T/spec.png' --text 'LOIL.' > '$T/font.json'"
  check "font: has exactly I L O . and space, nothing missing" py "
import json; r=json.load(open('$T/font.json'))
assert r['chars']=='.ILO' and r['missing']=='' and not r['blank'] and not r['skipped'], r"
  check "font: glyph shapes are right (I narrow, O wide with a hole, . sits on the baseline)" py "
from PIL import Image, ImageDraw, ImageFont
f=ImageFont.truetype('$T/f.ttf', 200)
def ink(c):
    im=Image.new('L',(400,300),0); ImageDraw.Draw(im).text((50,20),c,font=f,fill=255); return im
wI=ink('I').getbbox(); wO=ink('O').getbbox(); wp=ink('.').getbbox()
assert (wO[2]-wO[0]) > 3*(wI[2]-wI[0]), (wI,wO)
o=ink('O'); cx,cy=(wO[0]+wO[2])//2,(wO[1]+wO[3])//2; assert o.getpixel((cx,cy))==0, 'O has no hole'
assert abs(wp[3]-wI[3])<=2, ('period not on baseline', wp, wI)"
  check "font: convert to WOFF2 and OTF, info reads them back" sh -c "'$BCT' font convert '$T/f.ttf' -o '$T/f.woff2' >/dev/null &&
      '$BCT' font convert '$T/f.ttf' -o '$T/f.otf' >/dev/null &&
      '$BCT' font info '$T/f.woff2' | python3 -c 'import json,sys; r=json.load(sys.stdin); assert r[\"family\"]==\"Bct Test\" and set(\"ILO.\")<=set(r[\"chars\"]), r'"
  check "font: specimen of the WOFF2 renders and reports a missing letter" sh -c "'$BCT' font specimen '$T/f.woff2' -o '$T/spec2.png' --text 'LOX' | python3 -c 'import json,sys; r=json.load(sys.stdin); assert r[\"missing\"]==\"X\" and not r[\"blank\"], r'"
else skip "font (FontForge)" "fontforge not installed"; fi

# ---------- 10. audio (SoX) ----------
if command -v sox >/dev/null; then
  check "audio: 440 Hz tone, 0.5 s" sh -c "'$BCT' audio tone '$T/a.wav' --freq 440 --dur 0.5 --vol 0.5 > '$T/a.json'"
  check "audio: tone length, peak and pitch are right" py "
import json, subprocess, numpy as np
r=json.load(open('$T/a.json')); assert abs(r['seconds']-0.5)<0.01 and abs(r['peak']-0.5)<0.02, r
raw=subprocess.run(['sox','$T/a.wav','-t','raw','-e','floating-point','-b','32','-c','1','-'],capture_output=True).stdout
x=np.frombuffer(raw,np.float32); f=np.fft.rfftfreq(len(x),1/r['rate'])[np.argmax(abs(np.fft.rfft(x)))]
assert abs(f-440)<3, f"
  check "audio: synth tune is 2.0 s at 120 bpm (quarter, rest, half)" sh -c "'$BCT' audio synth '$T/s.wav' --notes 'A4/4 R/4 C5+E5/2' --bpm 120 | python3 -c 'import json,sys; r=json.load(sys.stdin); assert abs(r[\"seconds\"]-2.0)<0.02 and not r[\"clipped\"] and abs(r[\"peak_db\"]+3.1)<0.3, r'"
  check "audio: the rest in the tune is silent" sh -c "'$BCT' audio trim '$T/s.wav' -o '$T/rest.wav' --start 0.55 --end 0.95 | python3 -c 'import json,sys; r=json.load(sys.stdin); assert r[\"silent\"] and abs(r[\"seconds\"]-0.4)<0.01, r'"
  check "audio: noise, mix, concat with gap, fade, norm" sh -c "'$BCT' audio noise '$T/n.wav' --dur 0.5 >/dev/null &&
      '$BCT' audio mix '$T/a.wav' '$T/n.wav' -o '$T/m.wav' --vol 1,0.5 >/dev/null &&
      '$BCT' audio concat '$T/a.wav' '$T/m.wav' -o '$T/c.wav' --gap 0.25 | python3 -c 'import json,sys; assert abs(json.load(sys.stdin)[\"seconds\"]-1.25)<0.01' &&
      '$BCT' audio fade '$T/c.wav' -o '$T/cf.wav' --in 0.1 --fade-out 0.3 >/dev/null &&
      '$BCT' audio norm '$T/cf.wav' -o '$T/cn.wav' --db -1 | python3 -c 'import json,sys; assert abs(json.load(sys.stdin)[\"peak_db\"]+1)<0.05'"
  check "audio: fade really starts at silence" py "
import subprocess, numpy as np
raw=subprocess.run(['sox','$T/cf.wav','-t','raw','-e','floating-point','-b','32','-c','1','-'],capture_output=True).stdout
x=np.frombuffer(raw,np.float32); assert abs(x[:40]).max()<0.01 and abs(x[8000:10000]).max()>0.3 and abs(x[23000:32000]).max()<0.001"
  check "audio: effects (pitch up an octave keeps length)" sh -c "'$BCT' audio fx '$T/a.wav' -o '$T/p.wav' --pitch 1200 | python3 -c 'import json,sys; assert abs(json.load(sys.stdin)[\"seconds\"]-0.5)<0.02'"
  check "audio: waveform and spectrogram PNGs, not blank" sh -c "'$BCT' audio wave '$T/c.wav' -o '$T/w.png' --width 600 --height 200 >/dev/null &&
      '$BCT' audio spectrogram '$T/c.wav' -o '$T/sp.png' --width 600 --height 300 >/dev/null && python3 -c \"
from PIL import Image, ImageStat
w=Image.open('$T/w.png'); assert w.size==(600,200), w.size
for f in ('$T/w.png','$T/sp.png'): assert ImageStat.Stat(Image.open(f).convert('L')).stddev[0]>10, f\""
else skip "audio (SoX)" "sox not installed"; fi

# ---------- 11. paint (Krita) ----------
if command -v krita >/dev/null; then
  "$BCT" layers new "$T/k.json" --size 160x100 --background "#ffffff" >/dev/null
  "$BCT" layers add "$T/k.json" '{"id":"red box","type":"rect","x":10,"y":10,"w":60,"h":50,"fill":"#e03020"}' >/dev/null
  "$BCT" layers add "$T/k.json" '{"id":"blue dot","type":"ellipse","x":90,"y":30,"w":50,"h":50,"fill":"#2050e0","opacity":0.7}' >/dev/null
  "$BCT" layers render "$T/k.json" -o "$T/k_flat.png" --ora "$T/k.ora" >/dev/null
  check "paint: ORA -> KRA with Krita (first run can take 30 s)" sh -c "'$BCT' paint export '$T/k.ora' -o '$T/k.kra' > '$T/k1.json'"
  check "paint: KRA keeps the layer names and opacity" sh -c "'$BCT' paint info '$T/k.kra' | python3 -c '
import json,sys; r=json.load(sys.stdin); n={l[\"name\"]:l for l in r[\"layers\"]}
assert \"red box\" in n and \"blue dot\" in n and abs(n[\"blue dot\"][\"opacity\"]-0.7)<0.01 and r[\"size\"]==[160,100], r'"
  check "paint: KRA -> PNG is not blank and matches the layers render" sh -c "'$BCT' paint export '$T/k.kra' -o '$T/k.png' > '$T/k2.json' && python3 -c \"
import json
from PIL import Image, ImageChops, ImageStat
r=json.load(open('$T/k2.json')); assert not r['blank'], r
d=ImageStat.Stat(ImageChops.difference(Image.open('$T/k.png').convert('RGB'),Image.open('$T/k_flat.png').convert('RGB'))).mean
assert max(d)<3, d
assert Image.open('$T/k.png').convert('RGB').getpixel((30,30))[0]>200\""
  check "paint: stack PNGs into a layered KRA" sh -c "'$BCT' paint stack '$T/k_flat.png' '$T/fx_in.png' --names base,top --opacity 1,0.5 -o '$T/st.kra' | python3 -c 'import json,sys; assert json.load(sys.stdin)[\"layers\"]==[\"top\",\"base\"]'"
  if command -v kritarunner >/dev/null; then
    cat > "$T/ks.py" <<'EOF'
from krita import Krita, InfoObject
def main(args):
    app = Krita.instance(); doc = app.openDocument(args[0]); doc.setBatchmode(True)
    n = doc.createNode("green", "paintlayer"); doc.rootNode().addChildNode(n, None)
    n.setPixelData(bytes([0, 200, 0, 255]) * (20 * 20), 0, 0, 20, 20)   # BGRA
    doc.refreshProjection(); doc.waitForDone(); doc.saveAs(args[1]); doc.exportImage(args[2], InfoObject())
    print("done")
    return {"layers": [c.name() for c in doc.rootNode().childNodes()]}
EOF
    check "paint: Python script inside Krita adds a layer" sh -c "'$BCT' paint script '$T/ks.py' '$T/k.kra' '$T/k3.kra' '$T/k3.png' > '$T/k3.json'"
    check "paint: script result, print output and the new pixels" py "
import json
from PIL import Image
r=json.load(open('$T/k3.json')); assert r['ok'] and 'green' in r['result']['layers'] and r['printed'].strip()=='done', r
assert Image.open('$T/k3.png').convert('RGB').getpixel((5,5))==(0,200,0)"
  else skip "paint script" "kritarunner not installed"; fi
else skip "paint (Krita)" "krita not installed"; fi
check "paint: KRA -> PNG without Krita uses the copy inside the file" sh -c "[ -f '$T/k.kra' ] || exit 0; PATH=/usr/bin:/bin python3 '$HERE/tools/paint.py' export '$T/k.kra' -o '$T/k_nok.png' | grep -q 'no Krita'"

# ---------- summary ----------
END=$(date +%s)
echo "----"
echo "selftest: $PASS passed, $FAIL failed, $SKIP skipped in $((END-START))s"
if [ "${KEEP:-0}" = 1 ]; then echo "outputs kept in $T"; else rm -rf "$T"; fi
if [ "$FAIL" -gt 0 ]; then echo "FAILED: ${FAILED[*]}"; exit 1; fi
echo "selftest: PASS"
