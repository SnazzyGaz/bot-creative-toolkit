# bot-creative-toolkit

Headless visual-work tools for AI agents on Linux: Blender, Inkscape, GIMP and potrace, set up with one script,
plus three small helpers that turn them into things a bot can use and check.

- **`bct look`**: render a `.blend` file or a `bpy` scene script from several angles into one labelled
  contact sheet PNG. Optionally runs [model-qa](https://github.com/SnazzyGaz/model-qa) `check --look` on it.
- **`bct layers`**: build images from a JSON layer stack (images, fills, gradients, shapes, text; position, opacity,
  blend mode, visibility, rotation). Outputs PNG and OpenRaster (`.ora`). Edit one layer and only that layer is
  redrawn. Reads `.ora` back into a stack.
- **`bct vector`**: bitmap to clean SVG with potrace (one colour or posterised multi-colour), add/edit/recolour/
  delete SVG elements by id, export PNG/PDF with Inkscape.
- **`bct gimp`**: run GIMP 3 with no window: convert between formats (ORA to PSD, XCF to PNG...) or run your own
  GIMP Python.

## Install

```bash
git clone https://github.com/SnazzyGaz/bot-creative-toolkit
cd bot-creative-toolkit
./setup.sh        # idempotent: skips anything already installed
./selftest.sh     # end-to-end test of every tool, exits non-zero on any failure
```

Needs: x86_64 Linux, `bash`, `curl`, Python 3.9+. No screen or GPU needed. `setup.sh` uses apt with sudo when it
can, and otherwise downloads the official portable builds (Blender 4.2.3 tarball, Inkscape 1.4.2 and GIMP 3.0.6
AppImages, potrace 1.16) into `~/.local/opt/bct` and `~/blender`, linked into `~/.local/bin`.
Options: `--check` (report only), `--no-gimp`, `--portable` (skip apt).

## Quick look

```bash
bct look examples/scene_example.py -o sheet.png
bct layers render my_stack.json -o out.png --ora out.ora
bct vector trace sketch.png -o sketch.svg --despeckle 4 && bct vector export sketch.svg -o sketch_clean.png
bct help
```

Every command prints JSON on stdout (paths, sizes, what changed), so scripts and agents can read the results.

For agents: read [AGENTS.md](AGENTS.md).

## Licence

MIT. Copyright (c) 2026 Garyck Arntzen.
