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

# ---------- summary ----------
END=$(date +%s)
echo "----"
echo "selftest: $PASS passed, $FAIL failed, $SKIP skipped in $((END-START))s"
if [ "${KEEP:-0}" = 1 ]; then echo "outputs kept in $T"; else rm -rf "$T"; fi
if [ "$FAIL" -gt 0 ]; then echo "FAILED: ${FAILED[*]}"; exit 1; fi
echo "selftest: PASS"
