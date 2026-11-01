# Instructions for AI agents

You are doing visual work (3D, layered images, vectors) on a headless Linux box with `bct`. Follow this file.
It works for any agent that can run shell commands and view images.

## 0. Install once

```bash
git clone https://github.com/SnazzyGaz/bot-creative-toolkit && cd bot-creative-toolkit
./setup.sh          # installs what's missing: Blender, Inkscape, GIMP, potrace, Pillow, numpy. Safe to re-run.
./selftest.sh       # must end with "selftest: PASS"
```
`setup.sh` tries apt first (with sudo), then the official portable builds into `~/.local/opt/bct`, linked into
`~/.local/bin`. If `bct` is not found, add `~/.local/bin` to `PATH`. `bct doctor` shows what's installed.
`./setup.sh --no-gimp` skips GIMP (the biggest download). Blender already in `~/blender` or on `PATH` is used as is.

## 1. Why you need it

You can't see a 3D scene or a design until it's a picture, and redoing a whole image to change one part wastes
time and drifts. `bct` gives you one image to look at for 3D work, layered files you can change one piece at a time,
and clean vectors. Every command prints JSON on stdout, so read the paths from it rather than guessing.

## 2. 3D: build, look, fix (cheapest first)

1. **Build** the scene in a `.py` script with `bpy` (it runs in an empty scene; see `examples/scene_example.py`),
   or save a `.blend`.
2. **Look:** `bct look scene.py -o sheet.png` renders front, right, top and three-quarter views into ONE labelled
   contact sheet (about 2 s at the default 320 px tiles). Open just `sheet.png`. The header shows object count,
   triangles and size in metres, which catches unit mistakes fast.
   - Need a closer look? `--views three_quarter --size 640`. Shape only? `--clay`. Lined up checks? `--ortho`.
   - Your own lights are kept; if the scene has none, 3 lights are added (`--lights studio` forces them).
   - `--save-blend built.blend` keeps the built scene for the next step or for the user.
3. **Check (optional, recommended):** if `model-qa` is installed (github.com/SnazzyGaz/model-qa), add
   `--qa [--qa-args "--category chair --profile render"]`. It runs `model-qa check --look` and puts the exit code,
   verdict text and `report.json` / `beauty.png` paths under `model_qa` in the JSON. Without model-qa it says
   `skipped` and carries on. Set `MODEL_QA=/path/to/model-qa` if it lives in a venv. Follow model-qa's own AGENTS.md
   for what the issues mean.
4. **Fix** in your script, then look again. Stop when the sheet looks right and model-qa has no high/med issues.

Engines: `cycles` (default, CPU, works with no screen), `workbench` (flat, fast), `eevee` (slow without a GPU).

## 3. Layered images: change one part without redoing the rest

Write a JSON stack (layers bottom to top). Types: `fill` (colour or vertical gradient with `to`), `image`, `rect`,
`ellipse`, `line`, `polygon`, `text`. Every layer takes `x`, `y`, `opacity`, `blend`
(`normal multiply screen overlay darken lighten difference add`), `visible`, `rotate`. Full format: `bct layers --help`.

```bash
bct layers new poster.json --size 1080x1350 --background "#fff"
bct layers add poster.json '{"id":"photo","type":"image","src":"cat.png","x":40,"y":60,"w":1000}'
bct layers add poster.json '{"id":"title","type":"text","text":"Lost cat","x":60,"y":1150,"size":96,"color":"#111"}'
bct layers render poster.json -o poster.png --ora poster.ora
```
Then edit one layer by id and re-render: `set ID key=value`, `replace ID --src new.png`, `move ID --to X Y` or
`--by DX DY`, `hide/show ID`, `reorder ID --top|--bottom|--up|--down|--to N`, `remove ID`. Add `--render -o out.png`
to any edit to render straight away. The JSON result lists which layers were `drawn` and which came from the
cache: after a one-layer edit only that layer should be in `drawn`.

- Values in `set` are JSON when they can be: `set title text='"New title"' size=80 visible=false`.
- `.ora` (OpenRaster) opens in GIMP and Krita with layers. `bct layers from-ora file.ora -o stack.json` reads one
  back (layers become image layers in `stack_layers/`).
- Need a PSD? `bct gimp convert poster.ora poster.psd` (keeps layers).

## 4. Vectors

```bash
bct vector trace logo.png -o logo.svg --threshold 0.5 --despeckle 4      # one colour
bct vector trace art.png -o art.svg --colors 4                           # posterise, one <g> per colour
bct vector new icon.svg --size 256x256
bct vector add icon.svg circle cx=128 cy=128 r=100 fill=#3a7 --id face
bct vector add icon.svg text x=60 y=140 font-size=40 font-family=sans-serif fill=#fff --text "Hi" --id label
bct vector recolor icon.svg --from "#3a7" --to "#e63"      # or: recolor icon.svg --id face --fill "#e63"
bct vector set icon.svg --id face r=90                      # key= with no value removes an attribute
bct vector delete icon.svg --id label
bct vector list icon.svg                                    # ids, tags, sizes, colours
bct vector export icon.svg -o icon.png --width 512 [--background "#fff"]   # Inkscape; .pdf also works
```
Trace tips: raise `--despeckle` to drop dust, raise `--tolerance` for fewer nodes, `--smooth 0` for sharp corners,
`--invert` for light shapes on dark. Always `export` and look at the PNG; don't judge an SVG from its text.

## 5. GIMP (for what the others don't cover)

`bct gimp convert IN OUT` opens anything GIMP reads (`.xcf .psd .ora .png .jpg ...`) and saves OUT; `.png`/`.jpg`
are flattened, `.psd/.xcf/.ora` keep layers. For anything else, `bct gimp eval "python code"` or
`bct gimp script file.py` runs GIMP 3 Python with `Gimp`, `Gio`, `GLib` imported. Use absolute paths.
GIMP takes a few seconds to start, so batch work into one script.

## 6. Don't

- Don't render big or with many samples first. Start with the defaults; go bigger only for the final picture.
- Don't open every tile or every file. One contact sheet per round is usually enough.
- Don't rebuild a whole image to change one part. Edit the layer by id.
- Don't trust that an edit worked: render or export, then look.
- Don't print or paste huge SVG path data into chat. Use `bct vector list`.

Exit codes: `0` ok, `1` a check or conversion failed, `2` bad input or a missing program (the message says which).
