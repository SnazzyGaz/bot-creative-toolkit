# Changelog

## 0.3.0 (2026-11-01)

- `setup.sh` installs Krita, G'MIC, FontForge and SoX (already on PATH, then apt, then portable: the Krita 6 and
  FontForge AppImages, the official G'MIC `.deb` for the Debian/Ubuntu release with any missing libraries fetched by
  `tools/deb_fill.py`, and SoX from conda-forge via micromamba). It also installs Xvfb for Krita. `--check` covers
  them; `--no-art` skips all four and `--no-krita` skips only Krita.
- New `bct fx` (G'MIC): 21 named styles (`painting`, `watercolor`, `cartoon`, `sketch`, `halftone`, `glow`, ...),
  `strip` for a labelled side-by-side comparison, `gui` to run any of G'MIC's ~430 GUI filters by menu name with
  its defaults (`gui-info`, `list --all/--search`), and `run` for raw pipelines. Each result reports how much the
  picture changed. The `painting` style works around a colour bug in G'MIC 4.0.7's own painting filter.
- New `bct paint` (Krita, no window): `export` between `.kra .ora .psd .png ...` keeping layers, `info` (layer list
  read from the file), `stack` (layered `.kra` from PNGs) and `script` (your Python inside Krita via kritarunner,
  with its return value and print output as JSON). Runs under Xvfb when there's no display; `.kra` → `.png` works
  without Krita.
- New `bct font` (FontForge): `build` a font from SVG letters (common scale, baseline, side bearings, space glyph,
  correct line metrics), `specimen` PNG with missing-character report, `convert` (TTF/OTF/WOFF/WOFF2/SFD), `info`.
- New `bct audio` (SoX): `tone`, `noise`, `synth` (note names, chords, rests, bpm), `trim`, `fade`, `norm`,
  `concat`, `mix`, `fx`, `wave` and `spectrogram` pictures, and `probe` (length, peak/RMS dBFS, silent, clipped).
- AGENTS.md: sections on G'MIC, Krita, FontForge and SoX with their gotchas. `selftest.sh` now has 89 checks,
  including FFT pitch, exact tune length, glyph shapes rendered with Pillow, and Krita output matched pixel-for-pixel
  against the `bct layers` render.

## 0.2.1 (2026-11-01)

- Docs only: README "Examples" section with a rocket turntable GIF, a Northwind icon set and the parametric phone
  stand (OpenSCAD picture, contact sheet and turntable), with the commands that made them.

## 0.2.0 (2026-11-01)

- `setup.sh` installs FFmpeg, ImageMagick 7 and OpenSCAD (already on PATH, then apt, then a static FFmpeg build, the
  ImageMagick AppImage and the newest OpenSCAD snapshot). `--check` covers them; `--no-extra` skips them.
- New `bct video`: `encode` (frames to MP4/GIF/WebM, two-pass palette GIFs), `turntable` (360° Blender orbit of a
  model, encoded to MP4 and GIF), `trim` (exact frame counts), `sheet` (contact sheet of a video's frames), `probe`.
- New `bct img`: `resize` (fit, fill, exact, pad), `crop` (box, trim, circle), `icons` (16–512 px PNGs and `.ico`),
  `montage`, `convert`, `adjust`, `info`.
- New `bct scad`: `render` (STL/3MF/OFF with `-D`/`-S` parameters, PNG of the part, Blender sheet, measured bounding
  box), `png`, `params`.
- `bct look` reads mesh files (`.stl .obj .ply .glb .gltf`) with `--import-scale`, and has `--orbit N` for turntable
  frames and `--margin` for framing.
- New examples: `examples/phone_stand.scad`, `examples/rocket.py`.
- AGENTS.md: sections on video, batch images and OpenSCAD, with the common FFmpeg, ImageMagick and OpenSCAD
  mistakes. `selftest.sh` now has 55 checks and inspects the real outputs (ffprobe frame counts and durations,
  icon sizes, STL bounding boxes, blank-image checks).

## 0.1.2 (2026-11-01)

- Docs only: rewrote README.md with quick starts, the with/without-toolkit test results and comparison images
  (`docs/images/`), self-test coverage, and platform limits.

## 0.1.1 (2026-11-01)

- `bct layers`: any layer can take `"center": "x" | "y" | "both"` to centre it on the canvas.
- `bct layers`: image layers take `"radius"` for rounded corners.
- `bct vector export`: new `--text-to-path` flag turns text into outlines; exporting to `.svg` now writes plain SVG.
- `bct vector trace --colors`: fixed dark seams between colours. The lightest colour is now the background and the
  other colours are stacked light to dark, each covering its own area plus every darker one, so traced edges overlap
  instead of leaving gaps. On a test image this halved the error (mean abs diff 26.2 to 15.5).

## 0.1.0 (2026-11-01)

- First release: `setup.sh`, `selftest.sh`, `bct look`, `bct layers`, `bct vector`, `bct gimp`.
