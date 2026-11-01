# Changelog

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
