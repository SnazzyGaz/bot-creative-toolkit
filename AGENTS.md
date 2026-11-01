# Instructions for AI agents

You are doing visual work (3D, layered images, vectors, video, batch images, CAD parts, painting files, artistic
filters, fonts, sound) on a headless Linux box
with `bct`. Follow this file.
It works for any agent that can run shell commands and view images.

## 0. Install once

```bash
git clone https://github.com/SnazzyGaz/bot-creative-toolkit && cd bot-creative-toolkit
./setup.sh          # installs what's missing: Blender, Inkscape, GIMP, potrace, FFmpeg, ImageMagick 7, OpenSCAD,
                    # Krita, G'MIC, FontForge, SoX, Pillow, numpy. Safe to re-run.
./selftest.sh       # must end with "selftest: PASS"
```
`setup.sh` tries apt first (with sudo), then the official portable builds into `~/.local/opt/bct`, linked into
`~/.local/bin`. If `bct` is not found, add `~/.local/bin` to `PATH`. `bct doctor` shows what's installed.
`./setup.sh --no-gimp` skips GIMP (the biggest download); `--no-extra` skips FFmpeg, ImageMagick and OpenSCAD;
`--no-art` skips Krita, G'MIC, FontForge and SoX; `--no-krita` skips only Krita (a 390 MB download, 1.1 GB unpacked). Blender already in `~/blender` or on `PATH` is used as is.

## 1. Why you need it

You can't see a 3D scene or a design until it's a picture, and redoing a whole image to change one part wastes
time and drifts. `bct` gives you one image to look at for 3D work, layered files you can change one piece at a time,
and clean vectors. Every command prints JSON on stdout, so read the paths from it rather than guessing.

## 2. 3D: build, look, fix (cheapest first)

1. **Build** the scene in a `.py` script with `bpy` (it runs in an empty scene; see `examples/scene_example.py`),
   or save a `.blend`. Mesh files work too: `.stl .obj .ply .glb .gltf`. STL from CAD tools is in millimetres, so
   add `--import-scale 0.001` or the header will say your 8 cm part is 80 m.
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

Write a JSON stack (layers bottom to top). Types: `fill` (colour or vertical gradient with `to`), `image` (`radius` rounds its corners), `rect`,
`ellipse`, `line`, `polygon`, `text`. Every layer takes `x`, `y`, `center` (`x`, `y` or `both`, to centre it on the canvas), `opacity`, `blend`
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
bct vector trace art.png -o art.svg --colors 4                           # posterise: lightest colour is the background,
                                                                          # the rest stacked light to dark, one <g> each
bct vector new icon.svg --size 256x256
bct vector add icon.svg circle cx=128 cy=128 r=100 fill=#3a7 --id face
bct vector add icon.svg text x=60 y=140 font-size=40 font-family=sans-serif fill=#fff --text "Hi" --id label
bct vector recolor icon.svg --from "#3a7" --to "#e63"      # or: recolor icon.svg --id face --fill "#e63"
bct vector set icon.svg --id face r=90                      # key= with no value removes an attribute
bct vector delete icon.svg --id label
bct vector list icon.svg                                    # ids, tags, sizes, colours
bct vector export icon.svg -o icon.png --width 512 [--background "#fff"]   # Inkscape; .pdf also works, .svg gives plain SVG
bct vector export icon.svg -o icon_final.svg --text-to-path   # plain SVG with text as outlines, for handing over
```
Trace tips: raise `--despeckle` to drop dust, raise `--tolerance` for fewer nodes, `--smooth 0` for sharp corners,
`--invert` for light shapes on dark. Always `export` and look at the PNG; don't judge an SVG from its text.

## 5. GIMP (for what the others don't cover)

`bct gimp convert IN OUT` opens anything GIMP reads (`.xcf .psd .ora .png .jpg ...`) and saves OUT; `.png`/`.jpg`
are flattened, `.psd/.xcf/.ora` keep layers. For anything else, `bct gimp eval "python code"` or
`bct gimp script file.py` runs GIMP 3 Python with `Gimp`, `Gio`, `GLib` imported. Use absolute paths.
GIMP takes a few seconds to start, so batch work into one script.

## 6. Video (FFmpeg): `bct video`

- `bct video encode FRAMES -o out.mp4|out.gif|out.webm --fps 24` turns frames into a video. FRAMES can be a folder,
  a quoted glob (`'shots/*.png'`, sorted by name) or a printf pattern (`f_%04d.png`). MP4 is H.264, `yuv420p`,
  `+faststart`, odd sizes rounded down to even, so it plays everywhere. GIFs use a two-pass palette (good colours,
  small files). `--width` scales, `--crf` sets MP4 quality (18 = near lossless, 23 = default, 28 = small).
- `bct video turntable model -o spin.mp4 --gif spin.gif --frames 48 --fps 24 --size 480` renders a 360° orbit of a
  `.blend`, `bpy` script or mesh with Blender and encodes it. Start small (`--frames 24 --size 320 --samples 8`,
  about 10 s), check it, then do the final one. `--clay` for shape only, `--elev` for camera height.
- `bct video trim IN -o OUT --start 2 --duration 3` (or `--end`). It re-encodes and counts frames exactly;
  `--copy` is instant but cuts on keyframes, so the start can be off by up to a second.
- `bct video sheet IN -o sheet.png --count 9` puts evenly spaced frames on one labelled image. Look at that instead
  of opening a video or every frame.
- `bct video probe IN` gives codec, size, fps, exact frame count and duration as JSON.

FFmpeg tips if you call it yourself:
- Options before `-i` apply to the input, after it to the output. `-framerate 24 -i f_%04d.png` (not `-r`) sets the
  image sequence rate. `-ss` before `-i` seeks fast.
- `-t` can drop the last frame to rounding; use `-frames:v N` when the count matters.
- GIF: `split[a][b];[a]palettegen=stats_mode=diff[p];[b][p]paletteuse=dither=sierra2_4a`. One pass without a
  palette gives banding and big files. GIF frame delays are whole 1/100 s, so 15 fps plays as 14.3 or 16.7.
- H.264 needs even width and height: `scale=trunc(iw/2)*2:trunc(ih/2)*2`. Add `-pix_fmt yuv420p` or some players
  show a black screen.
- Add `-v error` to stop FFmpeg flooding the log.

## 7. Batch images (ImageMagick 7): `bct img`

- `resize IN... -o OUT | --out-dir DIR` with `--fit WxH` (keep aspect, inside the box), `--fill WxH` (cover the
  box, crop the rest), `--exact WxH` (stretch), or `--width/--height`. `--pad` after `--fit` pads to the full box,
  centred, with `--background` (`none` = transparent). `--shrink-only` never enlarges.
- `crop IN -o OUT --box 320x320+40+40 | --trim | --circle`. `--circle` makes the corners transparent.
- `icons IN -o DIR --ico favicon.ico` writes `icon-16.png` … `icon-512.png` and a multi-size `.ico` (16 to 256).
  It pads to a square first, so nothing is stretched. SVG input goes through Inkscape. Use a simple square mark,
  not a wide wordmark: text turns to mush below 48 px. Check the 16 and 32 px sizes.
- `montage IN... -o grid.png --cols 4 --tile 256 --labels` for a grid of pictures (`--native` keeps each one's size).
- `convert IN -o OUT.webp --quality 80 --strip`; the format comes from the extension.
- `adjust IN -o OUT --brightness 10 --contrast 5 --saturation 120 --gamma 1.1 --auto-level --grayscale --sharpen 1`.
- `info IN...` gives size, format, alpha and frame sizes (for `.ico`/`.gif`) as JSON.

ImageMagick tips if you call it yourself:
- Use `magick`, not `convert` (that's IM6 and clashes with a Windows tool). `magick identify`, `magick montage`.
- Settings (`-background`, `-gravity`, `-fill`, `-quality`) go before the operator that uses them.
- Geometry: `800x600` fits inside, `800x600^` fills, `800x600!` stretches, `800x600>` shrinks only, `50%` scales.
  Pad or crop to size with `-gravity center -extent 800x600`. Add `+repage` after `-crop` or `-trim`.
- `mogrify` overwrites files in place; always give it `-path outdir`.
- `-strip` removes metadata (smaller, private). JPEG/WebP `-quality 80-85` is the usual sweet spot.
- If a format is refused with "not authorized", the system `policy.xml` blocks it (often PDF/PS); use Inkscape or
  GIMP for those rather than loosening the policy.

## 8. CAD parts (OpenSCAD): `bct scad`

1. Write a `.scad` file with the sizes as variables at the top, each with a `// [min:max]` comment so they show
   up as parameters (see `examples/phone_stand.scad`). Keep millimetres.
2. `bct scad render part.scad -o part.stl --png part.png --sheet part_sheet.png -D width=100` writes a binary STL,
   OpenSCAD's own picture and a 4-view Blender sheet. The JSON has the bounding box (from OpenSCAD and re-measured
   from the STL), triangle count, `echo()` output and warnings. Check the size matches what you asked for.
3. Look at the sheet, fix, render again. `bct scad params part.scad` lists the parameters and their ranges.

- `-D name=value` takes an OpenSCAD expression (`-D width=100`, `-D holes=[3,5]`); `-S name=text` takes a string.
  `-D` only overrides variables that the file already sets.
- The PNG is rendered from the final geometry; faces made by a `difference()` cut show in a second colour, which is
  normal. `--fast` uses OpenSCAD's quick preview instead, which can flicker where faces touch.
- Uses the fast Manifold backend when the OpenSCAD build has it (setup installs a recent build; the 2021 release
  in most distros is much slower and has no Manifold).
- An empty STL means no 3D geometry (2D only, or everything subtracted); `bct scad` stops with an error.
- If you call OpenSCAD yourself: `--render=force`, not bare `--render` (it swallows the next argument); `--summary all
  --summary-file -` prints the bounding box as JSON; `--export-format binstl` for binary STL.
- Avoid `minkowski()` on detailed shapes: it's very slow. Make holes 0.01 mm longer than the wall
  (`translate([0,0,-0.01])`) so faces don't coincide.

## 9. Artistic filters (G'MIC): `bct fx`

1. `bct fx strip photo.png -o choices.png --styles painting,watercolor,cartoon,sketch,halftone,glow` puts the
   picture in each style side by side with labels. Look at that one image and pick.
2. `bct fx apply photo.png -o out.png --style cartoon`. The JSON has `change` (mean pixel difference from the input,
   0–255): under about 3 means the filter did almost nothing.
3. `bct fx list` shows the built-in styles. `bct fx list --search glass` and `bct fx gui "Stained Glass" in.png -o
   out.png` reach any of G'MIC's ~430 GUI filters by its menu name, with the GUI's defaults;
   `bct fx gui-info "Stained Glass"` lists the settings, and `--set 1=60` changes setting 1.
4. Anything else: `bct fx run in.png -o out.png -- blur 3 sharpen 100` passes a raw G'MIC pipeline.

- Filters depend on scale: a style tuned for 1000 px looks heavier on 300 px. Filter at the size you'll use.
  `--width 800` shrinks first, which is also faster.
- If you call `gmic` yourself: a command reads the next word as its settings, so `gmic in.png cartoon -o out.png`
  fails (`-o` is taken as cartoon's setting). Write `cartoon , -o out.png` (an empty setting list means defaults)
  or give the settings. Commas in file names break `-o`; `bct fx` works around that for output names only.
- The GUI filters are the `fx_*` commands and need *all* their settings in order; `bct fx gui` fills them in from
  the filter definitions file that `setup.sh` downloads. Choice settings are numbers (0 = first option).
- In G'MIC 4.0.7, `fx_painting` turns pale areas green (a wrong channel number inside it); the `painting` style is
  the same recipe with that fixed. There is no watercolour filter in G'MIC; the `watercolor` style is built from
  Kuwahara smoothing, darkened edges and a paper texture.

## 10. Painting files (Krita): `bct paint`

1. `bct paint export art.ora -o art.kra` turns an OpenRaster file (e.g. from `bct layers render --ora`) into a
   Krita file with the same layers, names, opacity and blend modes. `export art.kra -o art.png` flattens; `.psd`,
   `.jpg`, `.tif`, `.webp` work too. The JSON says whether the PNG is blank.
2. `bct paint info art.kra` lists the layers (top first) without starting Krita.
3. `bct paint stack base.png overlay.png --names base,overlay --opacity 1,0.6 -o art.kra` builds a layered file from
   PNGs.
4. `bct paint script edit.py IN.kra OUT.kra OUT.png` runs your Python inside Krita. The file defines `main(args)`
   and can return a dict, which comes back as `result` with any `print()` output as `printed`. Useful calls:
   `app = Krita.instance()`, `doc = app.openDocument(p)`, `doc.setBatchmode(True)`, `doc.nodeByName("x")`,
   `doc.createNode(name, "paintlayer")`, `node.setPixelData(bytes, x, y, w, h)` (bytes are **BGRA**),
   `app.filter("gaussian blur")` + `.configuration()` / `.apply(node, x, y, w, h)`, `doc.refreshProjection()`,
   `doc.waitForDone()`, `doc.saveAs(p)`, `doc.exportImage(p, InfoObject())`.

- Krita needs an X server even with no window; `bct paint` runs it under `xvfb-run` when `$DISPLAY` is unset.
- The first run after install takes about 30 s (Krita builds its resource database). Later runs take about 2 s.
- Batch mode can't paint brush strokes or use the GUI's tools; scripts can change pixels, layers, filters and
  properties only. Krita's `--export` has no options (quality, size): convert, then use `bct img` for that.
- A `.kra` is a zip: `maindoc.xml` has the layer tree, `mergedimage.png` the flattened picture. With no Krita
  installed, `.kra`/`.ora` → `.png` still works from that copy.
- Ignore "Fontconfig error" lines in Krita's log; they're harmless.

## 11. Fonts (FontForge): `bct font`

1. Draw each letter black on white (big, e.g. 400 px), trace it with `bct vector trace A.png -o glyphs/A.svg`, and
   name the files by character: `A.svg`, `a.svg`, `7.svg`, `uni00E9.svg`, or glyph names like `exclam.svg`,
   `period.svg`, `question.svg`.
2. `bct font build glyphs -o MyFont.ttf --name "My Font" --specimen spec.png --text "HELLO"` builds the font and a
   specimen picture. Look at the specimen. The JSON lists the characters in the font, skipped files, and
   characters of `--text` that are missing.
3. `bct font convert MyFont.ttf -o MyFont.woff2` (also `.otf`, `.woff`, `.sfd`); `bct font info` lists what's in
   a font.

- By default all glyphs are scaled by the same amount so the tallest letter (not g j p q y) is `--cap-height`
  (0.7 em) and sits on the baseline, with `--bearing` units (60) of space each side. Draw letters at a consistent
  size, or use `--no-fit` to keep the SVGs' own size and position.
- There is no kerning: spacing is the same for every pair. Widen `--bearing` for chunky letters.
- If you script FontForge yourself: run `fontforge -lang=py -script /absolute/path.py`; the portable build changes
  folder before running, so relative paths break. Vertical metrics like `hhea_ascent` are offsets unless you set
  `hhea_ascent_add = False` first (otherwise lines come out far too tall).

## 12. Sound (SoX): `bct audio`

1. Make: `bct audio tone beep.wav --freq 880 --dur 0.2`, `bct audio noise hiss.wav --color pink`,
   `bct audio synth tune.ogg --notes "C5/8 E5/8 G5/4 C5+E5+G5/2" --bpm 140 --wave pluck --reverb 25`.
2. Edit: `trim`, `fade`, `norm`, `concat --gap`, `mix --vol`, and `fx` (`--reverb --echo --pitch --tempo --speed
   --lowpass --highpass --bass --treble --gain`, or raw SoX effects after `--`).
3. Check: you can't hear it, so look at it. `bct audio wave x.ogg -o wave.png` (loudness over time, clipping marked
   red) and `bct audio spectrogram x.ogg -o spec.png` (pitch over time: each note is a stack of horizontal lines).
   `bct audio probe x.ogg` gives length, peak and RMS in dBFS, `silent` and `clipped`.

- Every command reports the result's length and peak. Peak at 0 dBFS or `clipped: true` means distortion:
  `norm --db -1`. RMS around -14 to -20 dBFS is a normal loudness for short effects.
- `--pitch` is in cents (1200 = an octave) and keeps the length; `--speed` changes both, like a tape.
- Use `.ogg` or `.flac` for files you keep (small), `.wav` for working files. `-r 32000` is plenty for effects.
- If you call `sox` yourself: options before a file apply to that file; effects go after the output file.

## 13. Don't

- Don't render big or with many samples first. Start with the defaults; go bigger only for the final picture.
- Don't open every tile or every file. One contact sheet per round is usually enough.
- Don't rebuild a whole image to change one part. Edit the layer by id.
- Don't trust that an edit worked: render or export, then look.
- Don't print or paste huge SVG path data into chat. Use `bct vector list`.
- Don't open a video or 48 turntable frames to check them. Use `bct video sheet`.
- Don't try filters one at a time. Use `bct fx strip` and pick from one picture.
- Don't ship a sound you haven't looked at: check the waveform for clipping and the spectrogram for the notes.

Exit codes: `0` ok, `1` a check or conversion failed, `2` bad input or a missing program (the message says which).
