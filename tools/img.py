"""bct img: everyday raster jobs with ImageMagick 7 (`magick`): resize, pad, crop, icon sets, grids, convert, adjust.

  resize IN... (-o OUT | --out-dir DIR) (--fit WxH | --fill WxH | --exact WxH | --width W | --height H)
         [--pad] [--background "#fff"|none] [--shrink-only] [--format png]
        --fit   keep aspect, fit inside the box        --fill  keep aspect, cover the box and crop the overflow
        --exact stretch to the box                     --pad   after --fit, pad to the full box (centred)
  icons IN -o DIR [--sizes 16,32,48,64,128,256,512] [--ico favicon.ico] [--background none] [--name icon]
        square-pads IN (PNG/JPG, or SVG via Inkscape), writes icon-16.png ... and a multi-size .ico (max 256)
  crop IN -o OUT [--box WxH+X+Y] [--trim] [--fuzz 5] [--circle]
        --box cuts a rectangle; --trim removes a flat border (fuzz % tolerance); --circle makes everything
        outside the inscribed circle transparent (round avatars and icons)
  montage IN... -o OUT [--cols 4] [--tile 256 | --native] [--gap 8] [--labels] [--label-color "#ddd"] [--background "#222"]
        --tile scales every image to fit a square cell; --native keeps each image at its own size (labels then show the pixel size)
  convert IN -o OUT [--quality 85] [--strip]          format comes from OUT's extension (png jpg webp tif gif ...)
  adjust IN -o OUT [--brightness 0] [--contrast 0] [--saturation 100] [--hue 100] [--gamma 1.0]
         [--auto-level] [--grayscale] [--sharpen 0]
  info IN...                                          size, format, colourspace, alpha, bytes as JSON
"""
import argparse, json, os, re, shutil, subprocess, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import die, emit


def magick():
    p = shutil.which("magick")
    if not p:
        die("ImageMagick 7 `magick` not found. Run setup.sh")
    return p


def run(cmd, what="magick"):
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        die(f"{what} failed: " + (p.stderr.strip()[-1200:] or f"exit {p.returncode}"), 1)
    return p


def info(paths):
    fmt = '{"file":"%i","format":"%m","width":%w,"height":%h,"colorspace":"%[colorspace]","alpha":"%A","frames":%n}\\n'
    out = []
    for f in paths:
        p = run([magick(), "identify", "-format", fmt, f], "identify")
        first = json.loads(p.stdout.strip().splitlines()[0])
        if len(p.stdout.strip().splitlines()) > 1:   # multi-image files (.ico, .gif): list every size
            first["sizes"] = [[json.loads(l)["width"], json.loads(l)["height"]] for l in p.stdout.strip().splitlines()]
        first["file"] = os.path.abspath(f); first["bytes"] = os.path.getsize(f)
        out.append(first)
    return out


def geom(s):
    if not re.fullmatch(r"\d+x\d+", s or ""):
        die(f"size must look like 800x600, got {s!r}")
    return s


def raster_input(path, tmp, size=1024):
    """SVG goes through Inkscape (better than ImageMagick's built-in SVG reader); others pass through."""
    if path.lower().endswith(".svg") and shutil.which("inkscape"):
        out = os.path.join(tmp, "src.png")
        run(["inkscape", os.path.abspath(path), "--export-type=png", f"--export-filename={out}",
             f"--export-width={size}", "--export-background-opacity=0"], "inkscape")
        return out
    return path


def cmd_resize(a):
    if len(a.inputs) > 1 and not a.out_dir:
        die("several inputs need --out-dir")
    ops = []
    flag = ">" if a.shrink_only else ""
    if a.fit: ops = ["-resize", geom(a.fit) + flag]
    elif a.fill: ops = ["-resize", geom(a.fill) + "^", "-gravity", "center", "-extent", a.fill]
    elif a.exact: ops = ["-resize", geom(a.exact) + "!"]
    elif a.width: ops = ["-resize", f"{a.width}x{flag}"]
    elif a.height: ops = ["-resize", f"x{a.height}{flag}"]
    else: die("give one of --fit --fill --exact --width --height")
    if a.pad:
        box = a.fit or a.exact
        if not box: die("--pad goes with --fit")
        ops += ["-background", a.background, "-gravity", "center", "-extent", box]
    outs = []
    for f in a.inputs:
        if a.out_dir:
            os.makedirs(a.out_dir, exist_ok=True)
            base = os.path.splitext(os.path.basename(f))[0] + "." + (a.format or os.path.splitext(f)[1].lstrip(".") or "png")
            o = os.path.join(a.out_dir, base)
        else:
            o = a.out
        run([magick(), f, "-auto-orient"] + ops + [o])
        outs.append(o)
    emit({"outputs": info(outs)})


def cmd_icons(a):
    sizes = sorted({int(s) for s in a.sizes.split(",")})
    os.makedirs(a.out, exist_ok=True)
    tmp = tempfile.mkdtemp(prefix="bct_icons_")
    src = raster_input(a.input, tmp, max(1024, max(sizes)))
    sq = os.path.join(tmp, "square.png")
    # pad to a square canvas first so nothing is stretched, then resize per size
    run([magick(), src, "-background", a.background, "-gravity", "center",
         "-extent", "%[fx:max(w,h)]x%[fx:max(w,h)]", sq])
    pngs = []
    for s in sizes:
        o = os.path.join(a.out, f"{a.name}-{s}.png")
        run([magick(), sq, "-filter", "Lanczos", "-resize", f"{s}x{s}", "-strip", o]); pngs.append(o)
    res = {"pngs": info(pngs)}
    if a.ico:
        ico_sizes = [s for s in sizes if s <= 256] or [256]
        ico = a.ico if os.path.dirname(a.ico) else os.path.join(a.out, a.ico)
        run([magick(), sq, "-background", a.background, "-define", "icon:auto-resize=" + ",".join(map(str, sorted(ico_sizes, reverse=True))), ico])
        res["ico"] = info([ico])[0]
    shutil.rmtree(tmp, ignore_errors=True)
    emit(res)


def cmd_crop(a):
    ops = []
    if a.box:
        if not re.fullmatch(r"\d+x\d+[+-]\d+[+-]\d+", a.box): die("--box looks like 320x320+36+36")
        ops += ["-crop", a.box, "+repage"]
    if a.trim:
        ops += ["-fuzz", f"{a.fuzz}%", "-trim", "+repage"]
    if a.circle:
        ops += ["-alpha", "set", "(", "+clone", "-alpha", "transparent", "-fill", "white", "-draw",
                "circle %[fx:w/2-0.5],%[fx:h/2-0.5] %[fx:w/2-0.5],0.5", ")",
                "-compose", "DstIn", "-composite"]
    if not ops: die("give --box, --trim and/or --circle")
    run([magick(), a.input] + ops + [a.out])
    emit({"output": info([a.out])[0]})


def cmd_montage(a):
    cmd = [magick(), "montage"]
    if a.labels:
        cmd += ["-label", "%wx%h" if a.native else "%t", "-pointsize", str(14 if a.native else max(12, a.tile // 12)), "-fill", a.label_color]
    cell = f"+{a.gap}+{a.gap}" if a.native else f"{a.tile}x{a.tile}+{a.gap}+{a.gap}"
    cmd += a.inputs + ["-tile", f"{a.cols}x", "-geometry", cell,
                       "-background", a.background, a.out]
    run(cmd, "montage")
    emit({"montage": info([a.out])[0], "inputs": len(a.inputs)})


def cmd_convert(a):
    cmd = [magick(), a.input] + (["-strip"] if a.strip else []) + (["-quality", str(a.quality)] if a.quality else []) + [a.out]
    run(cmd)
    emit({"output": info([a.out])[0], "input_bytes": os.path.getsize(a.input)})


def cmd_adjust(a):
    ops = []
    if a.auto_level: ops += ["-auto-level"]
    if a.gamma != 1.0: ops += ["-gamma", str(a.gamma)]
    if a.brightness or a.contrast: ops += ["-brightness-contrast", f"{a.brightness}x{a.contrast}"]
    if a.saturation != 100 or a.hue != 100: ops += ["-modulate", f"100,{a.saturation},{a.hue}"]
    if a.grayscale: ops += ["-colorspace", "Gray"]
    if a.sharpen: ops += ["-unsharp", f"0x{a.sharpen}"]
    if not ops: die("nothing to do: give at least one adjustment")
    run([magick(), a.input] + ops + [a.out])
    emit({"output": info([a.out])[0], "ops": ops})


def main(argv=None):
    ap = argparse.ArgumentParser(prog="bct img", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("resize"); r.add_argument("inputs", nargs="+"); r.add_argument("-o", "--out"); r.add_argument("--out-dir")
    for k in ("fit", "fill", "exact"): r.add_argument("--" + k)
    r.add_argument("--width", type=int); r.add_argument("--height", type=int); r.add_argument("--pad", action="store_true")
    r.add_argument("--background", default="none"); r.add_argument("--shrink-only", action="store_true"); r.add_argument("--format")
    i = sub.add_parser("icons"); i.add_argument("input"); i.add_argument("-o", "--out", required=True)
    i.add_argument("--sizes", default="16,32,48,64,128,256,512"); i.add_argument("--ico")
    i.add_argument("--background", default="none"); i.add_argument("--name", default="icon")
    k = sub.add_parser("crop"); k.add_argument("input"); k.add_argument("-o", "--out", required=True)
    k.add_argument("--box"); k.add_argument("--trim", action="store_true"); k.add_argument("--fuzz", type=float, default=5)
    k.add_argument("--circle", action="store_true")
    m = sub.add_parser("montage"); m.add_argument("inputs", nargs="+"); m.add_argument("-o", "--out", required=True)
    m.add_argument("--cols", type=int, default=4); m.add_argument("--tile", type=int, default=256)
    m.add_argument("--gap", type=int, default=8); m.add_argument("--labels", action="store_true")
    m.add_argument("--native", action="store_true"); m.add_argument("--label-color", default="#ddd")
    m.add_argument("--background", default="#222")
    c = sub.add_parser("convert"); c.add_argument("input"); c.add_argument("-o", "--out", required=True)
    c.add_argument("--quality", type=int); c.add_argument("--strip", action="store_true")
    d = sub.add_parser("adjust"); d.add_argument("input"); d.add_argument("-o", "--out", required=True)
    d.add_argument("--brightness", type=int, default=0); d.add_argument("--contrast", type=int, default=0)
    d.add_argument("--saturation", type=int, default=100); d.add_argument("--hue", type=int, default=100)
    d.add_argument("--gamma", type=float, default=1.0); d.add_argument("--auto-level", action="store_true")
    d.add_argument("--grayscale", action="store_true"); d.add_argument("--sharpen", type=float, default=0)
    n = sub.add_parser("info"); n.add_argument("inputs", nargs="+")
    a = ap.parse_args(argv)
    for f in getattr(a, "inputs", None) or ([a.input] if hasattr(a, "input") else []):
        if not os.path.isfile(f): die(f"not found: {f}")
    {"resize": cmd_resize, "icons": cmd_icons, "montage": cmd_montage, "crop": cmd_crop, "convert": cmd_convert,
     "adjust": cmd_adjust, "info": lambda a: emit({"images": info(a.inputs)})}[a.cmd](a)


if __name__ == "__main__":
    main()
