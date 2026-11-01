# bot-creative-toolkit

Headless visual-work tools for AI agents. One setup script installs Blender, Inkscape, GIMP and potrace on a Linux
box with no screen, and a small CLI, `bct`, turns them into things a bot can drive and, more importantly, **check**.

**Who it's for:** any AI agent or bot that can run shell commands and look at an image: Grok bots, Claude Code,
Codex, Cursor agents, or your own scripts. No GPU or display needed.

**What you get:**

| Tool | What it does |
|---|---|
| `bct look` | Renders a `.blend` file or a `bpy` scene script from four angles into one labelled contact sheet. Optionally runs [model-qa](https://github.com/SnazzyGaz/model-qa) on the model. |
| `bct layers` | Builds images from a JSON layer stack (images, fills, gradients, shapes, text; position, centring, opacity, blend mode, rotation, rounded image corners). Edit one layer and only that layer is redrawn. Writes PNG and layered OpenRaster (`.ora`). |
| `bct vector` | Bitmap to SVG with potrace (one colour or several), draw and edit SVG elements by id, export PNG, PDF or plain SVG with Inkscape (optionally with text turned into outlines). |
| `bct gimp` | Runs GIMP 3 with no window: convert formats (ORA to PSD, XCF to PNG and so on) or run your own GIMP Python. |

Every command prints JSON on stdout (paths, sizes, what changed), so an agent can read results instead of guessing.

Contents: [Install](#install) · [Quick start](#quick-start) · [Tested results](#tested-results-with-vs-without-the-toolkit) ·
[Self-test](#self-test) · [Platform support and limits](#platform-support-and-known-limits) · [More](#more)

## Install

```bash
git clone https://github.com/SnazzyGaz/bot-creative-toolkit && cd bot-creative-toolkit && ./setup.sh && ./selftest.sh
```

- Needs x86_64 Linux, `bash`, `curl` and Python 3.9+.
- `setup.sh` is safe to re-run and skips anything already installed. It tries apt (with sudo) first. If that is not
  available it downloads the official portable builds (Blender 4.2.3, Inkscape 1.4.2 and GIMP 3.0.6 AppImages,
  potrace 1.16) into `~/.local/opt/bct` and `~/blender`, linked into `~/.local/bin`.
- Options: `--check` (report only), `--no-gimp` (skip the biggest download), `--portable` (skip apt).
- If `bct` is not found, add `~/.local/bin` to `PATH`. `bct doctor` shows what is installed.

## Quick start

### 3D: build, look, fix

```bash
bct look examples/scene_example.py -o sheet.png              # front, right, top, three-quarter in one image
bct look scene.py -o sheet.png --qa                          # also run model-qa and report issues in the JSON
bct look scene.py -o close.png --views three_quarter --size 640 --clay
bct look scene.py -o sheet.png --save-blend built.blend      # keep the built scene
```

The sheet header shows object count, triangle count and size in metres, which catches unit mistakes straight away.

### Layered images: change one part without redoing the rest

```bash
bct layers new poster.json --size 1080x1350 --background "#fff"
bct layers add poster.json '{"id":"photo","type":"image","src":"cat.png","x":40,"y":60,"w":1000,"radius":24}'
bct layers add poster.json '{"id":"title","type":"text","text":"Lost cat","y":1150,"size":96,"color":"#111","center":"x"}'
bct layers render poster.json -o poster.png --ora poster.ora

bct layers set poster.json title text="Found cat" --render -o poster.png   # only the title is redrawn
```

Other edits: `replace`, `move`, `hide`/`show`, `reorder`, `remove`. `bct layers from-ora file.ora -o stack.json`
reads a layered file back in.

### Vectors

```bash
bct vector trace logo.png -o logo.svg --threshold 0.5 --despeckle 4     # one colour
bct vector trace art.png -o art.svg --colors 6                          # six colours, stacked light to dark
bct vector new icon.svg --size 256x256
bct vector add icon.svg circle cx=128 cy=128 r=100 fill=#3a7 --id face
bct vector recolor icon.svg --id face --fill "#e63"
bct vector export icon.svg -o icon.png --width 512
bct vector export icon.svg -o icon_final.svg --text-to-path             # plain SVG, text as outlines
```

### GIMP

```bash
bct gimp convert poster.ora poster.psd          # keeps layers
bct gimp script my_edit.py                      # GIMP 3 Python, no window
```

## Tested results: with vs without the toolkit

To see whether the toolkit actually helps, four tasks were done twice on the same box on 1 Nov 2026: once
**without** it (plain Python, Pillow, a hand-written SVG and so on) and once **with** it. There was one solid attempt
per side. All numbers below were measured, not estimated. In each image, WITHOUT is on the left and WITH is on the
right.

**Summary:** two clear wins (3D and vectorising) and two ties on the final result, where the toolkit's benefit is the
editing and handover workflow rather than better pixels. The testing also found three missing features and one bug,
which were fixed in 0.1.1 (see [CHANGELOG](CHANGELOG.md)).

| Task | Without | With | Verdict |
|---|---|---|---|
| 3D toy rocket | blind script, one render | `bct look --qa`, two fix rounds | **With wins clearly** |
| Poster, then an edit | Pillow script | `bct layers` stack | Same result; with is easier to edit, about 4× slower |
| Logo | hand-written SVG | `bct vector` | Same result; with is more portable and editable |
| Vectorise The Great Wave | pixel-run rectangles | `bct vector trace` | **With wins** (smooth curves, 2.5 to 4× smaller) |

### 1. 3D object: toy rocket (Blender)

![3D rocket: without vs with](docs/images/compare_3d.png)

| | Without | With |
|---|---|---|
| Script | 34 lines, plus an 11-line render script | 61 lines after two fix rounds |
| Feedback per try | one image, 0.97 s | four-view sheet plus a model-qa report, 8 to 14 s |
| Problems found | none: it was working blind | v1: 6 medium issues (fins with unapplied scale, asymmetry), smeared shading on body/nose, flat-shaded window, no bevels. v2: 3 high (fins inside out) and fins floating 63.6 mm up |
| Final check | not checked (the same model under model-qa: WARN, 0 high / 6 med) | WARN: 0 high, 3 medium (fin bottoms 3.9 mm above the base, from the bevel), 1,878 triangles |

**Verdict:** the single render without the toolkit looked passable, but the model was worse. It had slab fins, a
smear where the body meets the nose and a sunk window, and nothing showed it. With the toolkit, the four views and the
checker caught every problem, and the fix rounds produced a clean rocket with swept, bevelled fins. Most of the value
is in being able to check the work, not in the render itself.

### 2. Image: layered poster, then change the title and colours

![Poster: without vs with](docs/images/compare_poster.png)

| | Without (Pillow) | With (`bct layers`) |
|---|---|---|
| Work | 33-line script | JSON stack of 47 layers, no code |
| First render | 0.145 s | 0.565 s |
| The edit (new title, new background colours) | change the script arguments and redraw everything: 0.145 s | two `bct layers set` commands: 0.583 s, only 2 of 47 layers redrawn, 45 from cache |
| Untouched parts after the edit | rocket and frame unchanged (max pixel diff 0) | rocket and frame unchanged (max pixel diff 0) |
| Output | PNG | PNG plus a layered `.ora` that opens in GIMP and Krita |

**Verdict:** a tie on the result. The two posters match (mean pixel difference 1.23 out of 255). The toolkit makes
edits a one-line command with no code and gives a person a layered file to work with, but for a tiny one-off image
it is about 4× slower than a bare script. The first attempt with the toolkit had an off-centre title and square
image corners because the stack could not centre layers or round corners. Both were added in 0.1.1.

### 3. Logo: "Northwind Pottery"

![Logo: without vs with](docs/images/compare_logo.png)

| | Without | With (`bct vector`) |
|---|---|---|
| Build | hand-written SVG, 689 bytes | `new` plus 5 `add` commands, 795 bytes |
| Turning it into a PNG | headless Chrome, 1.8 s (only works because Chrome happened to be installed) | Inkscape, 1.17 s including the build |
| Edit (recolour, letter spacing) | `sed`, 0.49 s | `recolor` and `set` by id, 0.39 s |
| File to hand over | live text (needs the font) | outlined SVG, 6.8 KB, no `<text>` left |

**Verdict:** a tie on the result. The two renders match (mean pixel difference 0.39 out of 255), and the design
needed the same tweak either way (the name was shrunk to fit). The image shows the without version and the final
recoloured version made with the toolkit. The toolkit did not make a better logo. What it adds is a renderer that
does not depend on a browser, edits by element id, and a font-safe export.

### 4. Vectorise a complex image: The Great Wave off Kanagawa

![The Great Wave: without vs with](docs/images/compare_vector.png)

Source: *The Great Wave off Kanagawa* by Katsushika Hokusai (about 1831), public domain, from
[Wikimedia Commons](https://commons.wikimedia.org/wiki/File:Tsunami_by_hokusai_19th_century.jpg), scaled to 480 × 323.
"Without" writes one `<rect>` per horizontal run of same-colour pixels. "With" uses `bct vector trace`. Every SVG
was turned back into a PNG with Inkscape and compared to the original. MAD is mean absolute pixel difference (lower
is better) and SSIM is structural similarity (higher is better).

| Variant | SVG size | Elements | Points | Fidelity | Time |
|---|---|---|---|---|---|
| Without, one colour | 284 KB | 6,493 rects | 25,968 | matches 100% of the black/white mask; SSIM 0.655 vs greyscale | 72 ms |
| With, one colour | 114 KB | 613 paths | 15,091 | matches 97.0% of the mask; SSIM 0.641 vs greyscale | 105 ms |
| Without, six colours | 3.05 MB | 52,149 rects | 208,596 | MAD 13.1, SSIM 0.824 | 233 ms |
| With, six colours (0.1.0, before the fix) | 721 KB | 4,006 paths | 96,469 | MAD 26.2, SSIM 0.453 | 241 ms |
| With, six colours (0.1.1) | 727 KB | 2,013 paths | 105,453 | MAD 15.5, SSIM 0.749 | 282 ms |

**Verdict:** the toolkit wins. The rectangle SVGs score as perfect copies of the reduced-colour bitmap because they
*are* that bitmap, written out as rectangles. Zoomed in they show staircase edges, and they are 2.5 to 4× bigger.
potrace gives real curves that stay smooth at any size, at a small cost in pixel accuracy. This test also found a bug
in 0.1.0's colour mode: colours were traced separately over the most common colour, so dark seams showed through the
gaps. 0.1.1 uses the lightest colour as the background and stacks the rest light to dark, which halved the error.

### Toolkit gaps found during testing

- Fixed in 0.1.1: centring layers, rounded image corners, `--text-to-path` export, and the multi-colour trace seams.
- Still open: `bct look` frames the subject loosely (it sits small in each tile), and the top view is of little use
  for tall objects.
- Still open: `bct layers` is about 4× slower than a bare Pillow script for tiny one-off images.
- Note: model-qa flags a 3.9 mm gap left by a bevel as "near ground", which is borderline noise.

## Self-test

`./selftest.sh` runs 25 end-to-end checks and exits non-zero if any fail. The last run took about 20 s on a CPU-only
box, not counting first-time downloads.

- **setup (1):** every program is installed (`setup.sh --check`).
- **look (6):** a `.py` scene becomes a 2×2 contact sheet that is not blank; a `.blend` input works with the
  workbench engine; a bad view name is rejected; `--qa` runs model-qa and writes a report (skipped if model-qa is not
  installed).
- **layers (8):**
  - a stack with all 7 layer types, blend modes and opacity renders to PNG and ORA, and the pixels are checked;
  - the ORA file is valid;
  - a second render redraws nothing;
  - replacing one image redraws only that layer;
  - move, hide, set, reorder, add and remove all show up;
  - ORA → JSON → the same picture.
- **gimp (2):** GIMP opens the ORA and exports a matching flat PNG; ORA → layered PSD.
- **vector (8):**
  - a one-colour trace drops the specks;
  - a three-colour trace makes one group per colour;
  - new, add, set, recolor and delete all show up in `list`;
  - Inkscape export comes out at the requested width with the right pixels;
  - traced SVGs export too.

## Platform support and known limits

- **Tested on:** x86_64 Debian-based Linux with no display or GPU, using the portable builds (apt was not available).
  The CLI is Python 3 and bash.
- **Not supported:** ARM Linux, macOS and Windows. The portable downloads are x86_64 Linux builds. On other systems,
  installing Blender, Inkscape, GIMP and potrace yourself may work, but this is untested.
- **Rendering is CPU only.** Cycles at the default small size takes a few seconds per sheet. Eevee is slow without a
  GPU.
- **GIMP is slow to start,** a few seconds per call, so batch work into one script. GIMP is the biggest download;
  skip it with `--no-gimp` if you don't need PSD or XCF.
- **The 3D checks** (`--qa`) need [model-qa](https://github.com/SnazzyGaz/model-qa), installed separately. Without it,
  `bct look` still works and reports the check as skipped.
- **Text** in layers and SVGs uses whatever fonts the box has (DejaVu in the tests). Use `--text-to-path` before
  handing an SVG to someone else.

## More

- [AGENTS.md](AGENTS.md): step-by-step instructions written for AI agents (read this first if you are one).
- [CHANGELOG.md](CHANGELOG.md): what changed in each version.
- `bct help` and `bct <tool> --help` give the full options.

## Licence

MIT. Copyright (c) 2026 Garyck Arntzen. The Great Wave image in `docs/images/compare_vector.png` is in the public
domain.
