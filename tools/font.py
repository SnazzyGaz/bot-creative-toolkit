"""bct font: build, inspect and convert fonts with FontForge.

  build SVGDIR -o OUT.ttf|.otf|.woff2|.woff --name "My Font" [--bearing 60] [--cap-height 0.7]
        [--space 0.3] [--em 1000] [--no-fit] [--simplify 2] [--hint] [--specimen PNG]
        one glyph per SVG; the file name says which character it is: A.svg, a.svg, 7.svg, uni00E9.svg,
        exclam.svg, period.svg (standard glyph names). Black shapes become the glyph, e.g. `bct vector trace` output.
        By default every glyph is scaled by the same amount so the tallest non-descender letter is cap-height
        of the em, sat on the baseline (g j p q y drop below it), with --bearing units of space each side.
        --no-fit keeps the SVGs' own size and position instead.
  specimen FONT -o OUT.png [--text "HELLO"] [--sizes 96,48,24] [--bg white] [--fg black]
        a picture of the font: name, the text at several sizes, and every character it has.
        Reports characters of --text the font lacks.
  convert IN -o OUT   (.ttf .otf .woff .woff2 .sfd, any direction) [--name NEW]
  info FONT           family, metrics, glyph count and the characters it covers
"""
import argparse, json, os, shutil, subprocess, sys, tempfile, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import die, emit

HERE = os.path.dirname(os.path.abspath(__file__))


def fontforge(job):
    ff = shutil.which("fontforge")
    if not ff: die("fontforge not found. Run setup.sh")
    tmp = tempfile.mkdtemp(prefix="bct_font_")
    job = dict(job, result=os.path.join(tmp, "result.json"))
    jf = os.path.join(tmp, "job.json"); json.dump(job, open(jf, "w"))
    t = time.time()
    p = subprocess.run([ff, "-quiet", "-lang=py", "-script", os.path.join(HERE, "font_ff.py"), jf],
                       capture_output=True, text=True, timeout=600)
    if not os.path.exists(job["result"]):
        die("FontForge failed: " + (p.stderr.strip().splitlines() or ["no output"])[-1], 1)
    res = json.load(open(job["result"])); shutil.rmtree(tmp, ignore_errors=True)
    if not res.pop("ok"): die("FontForge: " + res.get("error", "failed"), 1)
    res["seconds"] = round(time.time() - t, 2)
    return res


def renderable(path):
    """Pillow reads .ttf/.otf; anything else is converted to a temporary .ttf first."""
    if path.lower().endswith((".ttf", ".otf")): return path, None
    tmp = tempfile.mkdtemp(prefix="bct_font_")
    t = os.path.join(tmp, "f.ttf"); fontforge({"cmd": "convert", "input": os.path.abspath(path), "out": t})
    return t, tmp


def font_chars(path):
    from fontTools.ttLib import TTFont  # optional, fall back to FontForge
    return set(TTFont(path).getBestCmap())


def specimen(font, out, text=None, sizes=(96, 48, 24), bg="white", fg="black"):
    from PIL import Image, ImageDraw, ImageFont
    sys.path.insert(0, HERE); from common import load_font, rgba
    path, tmp = renderable(font)
    try: cmap = font_chars(path)
    except Exception: cmap = {ord(c) for c in fontforge({"cmd": "info", "input": os.path.abspath(path)})["chars"]}
    chars = "".join(chr(c) for c in sorted(cmap) if c > 32 and c != 127 and c < 0x3000)
    text = text or (chars[:26] if len(chars) <= 40 else "The quick brown fox")
    missing = sorted({c for c in text if ord(c) not in cmap and c != " "})
    label = load_font(size=18)
    rows = [("label", os.path.basename(font) + "   " + ", ".join(f"{s}px" for s in sizes), label)]
    for s in sizes: rows.append(("text", text, ImageFont.truetype(path, s)))
    if chars: rows.append(("text", chars, ImageFont.truetype(path, 40)))
    probe = ImageDraw.Draw(Image.new("L", (1, 1)))
    boxes = [probe.textbbox((0, 0), t, font=f) for _, t, f in rows]
    W = min(max(b[2] for b in boxes) + 80, 2400)
    gap = 18
    H = 40 + sum((b[3] - b[1]) + gap for b in boxes)
    im = Image.new("RGB", (W, H), rgba(bg)[:3]); d = ImageDraw.Draw(im)
    y = 20
    for (kind, t, f), bx in zip(rows, boxes):
        d.text((40, y - bx[1]), t, font=f, fill=(120, 120, 120) if kind == "label" else rgba(fg)[:3])
        y += (bx[3] - bx[1]) + gap + (10 if kind == "label" else 0)
    im.save(out)
    from PIL import ImageStat
    ink = ImageStat.Stat(im.convert("L")).stddev[0]
    if tmp: shutil.rmtree(tmp, ignore_errors=True)
    return {"specimen": os.path.abspath(out), "size": list(im.size), "text": text, "missing": "".join(missing),
            "blank": ink < 1}


def main(argv=None):
    ap = argparse.ArgumentParser(prog="bct font", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build"); b.add_argument("svgdir"); b.add_argument("-o", "--out", required=True)
    b.add_argument("--name", default="Bct Display"); b.add_argument("--bearing", type=int, default=60)
    b.add_argument("--cap-height", type=float, default=0.7); b.add_argument("--space", type=float, default=0.3)
    b.add_argument("--em", type=int, default=1000); b.add_argument("--no-fit", action="store_true")
    b.add_argument("--simplify", type=float, default=0); b.add_argument("--hint", action="store_true")
    b.add_argument("--specimen"); b.add_argument("--text")
    s = sub.add_parser("specimen"); s.add_argument("font"); s.add_argument("-o", "--out", required=True)
    s.add_argument("--text"); s.add_argument("--sizes", default="96,48,24"); s.add_argument("--bg", default="white")
    s.add_argument("--fg", default="black")
    c = sub.add_parser("convert"); c.add_argument("input"); c.add_argument("-o", "--out", required=True); c.add_argument("--name")
    i = sub.add_parser("info"); i.add_argument("font")
    a = ap.parse_args(argv)
    if a.cmd == "build":
        if not os.path.isdir(a.svgdir): die(f"not a folder: {a.svgdir}")
        out = os.path.abspath(a.out); os.makedirs(os.path.dirname(out), exist_ok=True)
        res = fontforge({"cmd": "build", "svgdir": os.path.abspath(a.svgdir), "out": out, "name": a.name, "em": a.em,
                         "bearing": a.bearing, "cap_height": a.cap_height, "space": a.space, "fit": not a.no_fit,
                         "simplify": a.simplify, "hint": a.hint})
        if a.specimen: res.update(specimen(out, a.specimen, a.text))
        emit(res)
    elif a.cmd == "specimen":
        if not os.path.isfile(a.font): die(f"not found: {a.font}")
        emit(specimen(a.font, a.out, a.text, [int(x) for x in a.sizes.split(",")], a.bg, a.fg))
    elif a.cmd == "convert":
        if not os.path.isfile(a.input): die(f"not found: {a.input}")
        out = os.path.abspath(a.out); os.makedirs(os.path.dirname(out), exist_ok=True)
        emit(fontforge({"cmd": "convert", "input": os.path.abspath(a.input), "out": out, "name": a.name}))
    else:
        if not os.path.isfile(a.font): die(f"not found: {a.font}")
        emit(fontforge({"cmd": "info", "input": os.path.abspath(a.font)}))


if __name__ == "__main__":
    main()
