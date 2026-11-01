"""bct fx: artistic filters with G'MIC, by name.

  apply IN -o OUT --style NAME [--args "a,b,c"] [--width 800]
        NAME is one of the styles in `bct fx list` (painting, watercolor, cartoon, sketch, halftone, glow, ...).
        --args replaces the style's settings (same order as G'MIC's own command); --width resizes first (faster).
  strip IN -o OUT --styles painting,cartoon,sketch [--tile 320] [--cols N] [--no-original] [--work-width 1000]
        the same picture in several styles side by side, labelled: the quickest way to choose one.
        Filters run on the picture at up to --work-width pixels wide (styles depend on scale), then shrink to --tile.
  gui "Filter Name" IN -o OUT [--set 1=8 --set 3=0.5]
        any filter from G'MIC's GUI by its menu name, with the GUI's default settings (needs the filter list that
        setup.sh downloads). --set N=V changes setting N (1-based, in the order `bct fx gui-info` prints).
  gui-info "Filter Name"         the command, settings and defaults of a GUI filter
  list [--all] [--search WORD]   the built-in styles; --all lists every GUI filter by category
  run IN -o OUT -- PIPELINE...   raw G'MIC: `bct fx run in.png -o out.png -- blur 3 sharpen 100`
Every result reports how much the picture changed (mean absolute difference, 0-255) so a no-op shows up.
"""
import argparse, glob, json, os, re, shutil, subprocess, sys, tempfile, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import die, emit

# name: (G'MIC pipeline, what it looks like). Settings checked by eye on photos and paintings.
STYLES = {
    # fx_painting itself turns pale areas green in G'MIC 4.0.7 (its local-normalise step uses the wrong channel number),
    # so this is the same recipe with the channel fixed.
    "painting":   ("fx_normalize_local 10,6,5,20,1,12 fx_normalize_local 10,6,5,20,1,12 fx_normalize_local 10,6,5,20,1,12 fx_smooth_anisotropic 250,0.2,1,2.5,5,0.8,90,2,0,1,1,2,1,16 "
                   "fx_mix_lab 1,0,0,1.5,0,0.5,1.5,0,0.5,0,2,0 fx_segment_watershed 10,1,0 smooth 50,0,1,1,1",
                   "brushy painted look, flattened detail"),
    "oil":        ("fx_brushify 7,0.25,4,64,25,12,0,2,4,0.2,0.5,30,1,1,1,5,0,0.2,1", "thick brush strokes"),
    "watercolor": ("kuwahara 4 smooth 120,0.3,1,2,2 +luminance gradient_norm. blur. 0.7 normalize. 0,110 to_rgb. "
                   "sub[0] [1] remove. cut 0,255 +texturize_paper blend multiply,0.35",
                   "soft washes with darker edges"),
    "cartoon":    ("cartoon 3,200,20,0.25,1.5,8", "flat colours and black outlines"),
    "comic":      ("fx_poster_hope 0,3", "three-tone poster"),
    "sketch":     ("fx_sketchbw 3,45,180,30,1.75,0.02,0.5,0.75,0.1,0.7,3,6,0,1,4,0", "black pencil hatching"),
    "pencil":     ("fx_pencilbw 0.3,60,0,0", "soft grey pencil"),
    "charcoal":   ("fx_charcoal 65,70,170,0,1,0,50,70,255,255,255,0,0,0,0", "smudged charcoal"),
    "ink":        ("fx_ink_wash 0.14,23,0,0.5,0.54,2.25,0,2,6,5,20", "black ink wash"),
    "engrave":    ("fx_engrave 0.5,50,0,8,40,0,0,0,10,1,0,0,0,1", "banknote engraving lines"),
    "halftone":   ("fx_halftone 0,0,0,0,5,8,8,5,0.1", "printed dot pattern"),
    "stencil":    ("fx_stencilbw 10,10,0,0", "black and white stencil"),
    "posterize":  ("fx_posterize 150,30,1,12,0,0,0", "few flat colours"),
    "cubism":     ("cubism 160,30,90,0.7,0", "fractured into angled planes"),
    "stained-glass": ("fx_stained_glass 40,0.1,0,1,1,0,0,0", "cells with dark leading"),
    "mosaic":     ("fx_mosaic 50,0", "square tiles"),
    "pixel":      ("pixelize 8,8", "big pixels"),
    "glow":       ("fx_glow 6,7,0", "soft dreamy glow"),
    "old-photo":  ("old_photo", "faded sepia print"),
    "lomo":       ("fx_lomo 20,1,15,1,1,0,15,100,0", "vignetted toy-camera colour"),
    "pop-art":    ("warhol 2,2,2,40", "four-panel colour print"),
}


def gmic():
    p = shutil.which("gmic")
    if not p: die("gmic not found. Run setup.sh")
    return p


def stdlib_path():
    paths = sorted(glob.glob(os.path.expanduser(os.environ.get("BCT_OPT", "~/.local/opt/bct")) + "/gmic-stdlib/gmic_stdlib_*.gmic"))
    return paths[-1] if paths else None


def run_gmic(args, what="G'MIC"):
    t = time.time()
    args = list(args); move = None
    if "-o" in args:   # G'MIC reads commas in an output name as options, so write elsewhere and move
        k = args.index("-o") + 1
        if "," in args[k]:
            move = args[k]; args[k] = tempfile.mktemp(suffix=os.path.splitext(move)[1] or ".png", prefix="bct_fx_")
    p = subprocess.run([gmic(), "-v", "-1"] + args, capture_output=True, text=True)
    if move and p.returncode == 0: shutil.move(args[k], move)
    if p.returncode != 0:
        err = re.sub(r"\x1b\[[0-9;]*m", "", p.stderr)
        line = next((l for l in err.splitlines() if "***" in l), err.strip()[-600:])
        die(f"{what} failed: {line.strip()}", 1)
    return round(time.time() - t, 2)


def split_pipeline(s):
    """'cmd a,b cmd2' -> ['cmd','a,b','cmd2',',']. If the pipeline ends in a command with no settings, add ','
    so G'MIC uses its defaults instead of reading the next word ('-o') as the setting."""
    toks = s.split()
    if toks and re.fullmatch(r"[a-z_][a-z0-9_]*", toks[-1]) and toks[-1] not in ("done", "fi", "remove", "rm"):
        toks.append(",")
    return toks


def change(a, b):
    """mean absolute difference between two images after fitting b to a's size (0-255)."""
    from PIL import Image, ImageChops, ImageStat
    x = Image.open(a).convert("RGB"); y = Image.open(b).convert("RGB").resize(x.size)
    return round(sum(ImageStat.Stat(ImageChops.difference(x, y)).mean) / 3, 2)


def prep(src, width, tmp):
    if not width: return src
    from PIL import Image
    im = Image.open(src)
    if im.width <= width: return src
    out = os.path.join(tmp, "in.png")
    im.convert("RGBA" if "A" in im.getbands() else "RGB").resize((width, round(im.height * width / im.width)), Image.LANCZOS).save(out)
    return out


def apply_style(src, out, pipeline):
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    secs = run_gmic([src] + split_pipeline(pipeline) + ["-o", out])
    return {"out": os.path.abspath(out), "pipeline": pipeline, "seconds": secs, "change": change(src, out)}


def style_pipeline(name, args=None):
    if name not in STYLES: die(f"unknown style {name!r}. Styles: {', '.join(STYLES)}")
    pipe = STYLES[name][0]
    if args:
        first = pipe.split()[0]
        if len(pipe.split()) > 2: die(f"--args only works on one-command styles; {name} is: {pipe}")
        pipe = f"{first} {args}"
    return pipe


# ---------- GUI filter definitions (#@gui lines of gmic_stdlib.gmic) ----------
def gui_filters():
    path = stdlib_path()
    if not path: die("the G'MIC filter list is not installed; run setup.sh (needed for `gui`, `gui-info`, `list --all`)")
    filters, cat, cur = {}, "", None
    for line in open(path, encoding="utf-8", errors="replace"):
        if not line.startswith("#@gui"):
            if cur and line.startswith("# ") and cur.get("_cont"): cur["_text"] += " " + line[2:].strip()
            continue
        body = line[5:].rstrip("\n")
        m = re.match(r"^\s*<b>(.+?)</b>\s*$", body)
        if m: cat = re.sub("<[^>]+>", "", m.group(1)); cur = None; continue
        m = re.match(r"^ ([^:].*?)\s*:\s*([A-Za-z_][\w]*)\s*,\s*([^\s,]+)", body)
        if m and not body.startswith(" :"):
            if body.rstrip().endswith("_none_") or m.group(1).startswith("_"): cur = None; continue
            name = re.sub("<[^>]+>", "", m.group(1)).strip()
            cur = filters.setdefault(name, {"name": name, "command": m.group(2), "category": cat, "_text": ""})
            continue
        if cur is not None and body.startswith(" :"):
            cur["_text"] += " " + body[2:].strip()
            cur["_cont"] = body.rstrip().endswith("\\")
    return filters


TYPES = ("float", "int", "bool", "choice", "color", "point", "text", "value", "file", "folder")


def parse_params(text):
    """settings in order: [(label, type, default_string)] from '#@gui :' text."""
    params, i = [], 0
    pat = re.compile(r"([^=,]*?)\s*=\s*[~_]?\s*([a-z]+)\s*([({\[])")
    while True:
        m = pat.search(text, i)
        if not m: break
        label, typ, op = m.group(1).strip(), m.group(2), m.group(3)
        cl = {"(": ")", "{": "}", "[": "]"}[op]
        j, depth, q = m.end(), 1, False
        while j < len(text) and depth:
            c = text[j]
            if c == '"': q = not q
            elif not q and c == op: depth += 1
            elif not q and c == cl: depth -= 1
            j += 1
        inner = text[m.end():j - 1]
        i = j
        if typ not in TYPES: continue
        args = [a.strip() for a in re.findall(r'(?:"[^"]*"|[^,])+', inner)]
        if typ == "text":   # text(default) or text(multiline,default)
            d = args[-1] if args else '""'
            d = d if d.startswith('"') else f'"{d}"'
            params.append((label, typ, d))
        elif typ == "color":
            params.append((label, typ, ",".join(args) if args else "0,0,0"))
        elif typ == "point":
            params.append((label, typ, ",".join(args[:2]) if args else "50,50"))
        elif typ in ("file", "folder"):
            params.append((label, typ, '""'))
        elif typ == "choice":   # choice(default_index,"a","b") or choice("a","b") (default 0)
            d = args[0] if args and re.fullmatch(r"-?\d+", args[0]) else "0"
            params.append((label, typ, d))
        elif typ == "bool":
            d = (args[0] if args else "0").lower()
            params.append((label, typ, {"true": "1", "false": "0"}.get(d, d)))
        else:
            params.append((label, typ, (args[0] if args else "0").strip('"')))
    return params


def gui_lookup(name):
    fs = gui_filters()
    if name in fs: f = fs[name]
    else:
        low = {k.lower(): v for k, v in fs.items()}
        f = low.get(name.lower())
        if not f:
            close = [k for k in fs if name.lower() in k.lower()][:12]
            die(f"no GUI filter called {name!r}." + (f" Close: {', '.join(close)}" if close else ""))
    return f, parse_params(f["_text"])


# ---------- commands ----------
def cmd_apply(a):
    tmp = tempfile.mkdtemp(prefix="bct_fx_")
    src = prep(a.input, a.width, tmp)
    res = apply_style(src, a.out, style_pipeline(a.style, a.args))
    res["style"] = a.style
    shutil.rmtree(tmp, ignore_errors=True); emit(res)


def cmd_strip(a):
    from PIL import Image, ImageDraw
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from common import load_font
    names = [s.strip() for s in a.styles.split(",") if s.strip()]
    for n in names: style_pipeline(n)
    tmp = tempfile.mkdtemp(prefix="bct_fx_")
    src = prep(a.input, a.work_width, tmp)   # filter at working size, then shrink each result to a tile
    tiles, results = [], []
    if not a.no_original: tiles.append(("original", src))
    for n in names:
        o = os.path.join(tmp, f"{n}.png"); r = apply_style(src, o, style_pipeline(n)); r["style"] = n
        r.pop("out"); results.append(r); tiles.append((n, o))
    cols = a.cols or len(tiles)
    rows = (len(tiles) + cols - 1) // cols
    ims = [(lab, Image.open(p).convert("RGB")) for lab, p in tiles]
    tw = a.tile; th = max(round(im.height * tw / im.width) for _, im in ims)
    lab_h = max(20, tw // 14); font = load_font(size=lab_h - 6)
    sheet = Image.new("RGB", (cols * tw + (cols + 1) * 6, rows * (th + lab_h) + (rows + 1) * 6), (24, 24, 24))
    d = ImageDraw.Draw(sheet)
    for k, (lab, im) in enumerate(ims):
        x = 6 + (k % cols) * (tw + 6); y = 6 + (k // cols) * (th + lab_h + 6)
        im = im.resize((tw, round(im.height * tw / im.width)), Image.LANCZOS)
        sheet.paste(im, (x, y + lab_h)); d.text((x + 4, y + 2), lab, fill=(255, 210, 90), font=font)
    sheet.save(a.out)
    shutil.rmtree(tmp, ignore_errors=True)
    emit({"out": os.path.abspath(a.out), "size": list(sheet.size), "styles": results})


def cmd_gui(a):
    f, params = gui_lookup(a.name)
    vals = [p[2] for p in params]
    for s in a.set or []:
        k, _, v = s.partition("=")
        if not k.isdigit() or not 1 <= int(k) <= len(vals): die(f"--set {s}: setting number must be 1..{len(vals)}")
        vals[int(k) - 1] = v
    tmp = tempfile.mkdtemp(prefix="bct_fx_")
    src = prep(a.input, a.width, tmp)
    pipe = f["command"] + (" " + ",".join(vals) if vals else "")
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    secs = run_gmic([src, f["command"], ",".join(vals) if vals else ",", "-o", a.out], f"G'MIC filter {f['name']!r}")
    shutil.rmtree(tmp, ignore_errors=True)
    emit({"out": os.path.abspath(a.out), "filter": f["name"], "pipeline": pipe, "seconds": secs, "change": change(src, a.out)})


def cmd_gui_info(a):
    f, params = gui_lookup(a.name)
    emit({"filter": f["name"], "category": f["category"], "command": f["command"],
          "settings": [{"n": i + 1, "label": l, "type": t, "default": d} for i, (l, t, d) in enumerate(params)]})


def cmd_list(a):
    if a.all or a.search:
        fs = gui_filters()
        out = {}
        for f in fs.values():
            if a.search and a.search.lower() not in (f["name"] + " " + f["category"]).lower(): continue
            out.setdefault(f["category"], []).append(f["name"])
        emit({"gui_filters": sum(len(v) for v in out.values()), "by_category": out})
    else:
        emit({"styles": {k: v[1] for k, v in STYLES.items()},
              "more": "bct fx list --all (every G'MIC GUI filter), then bct fx gui \"Name\" IN -o OUT"})


def cmd_run(a):
    if not a.pipeline: die("give the G'MIC pipeline after --")
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    secs = run_gmic([a.input] + a.pipeline + ["-o", a.out])
    emit({"out": os.path.abspath(a.out), "pipeline": " ".join(a.pipeline), "seconds": secs, "change": change(a.input, a.out)})


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    pipeline = []
    if "--" in argv:
        k = argv.index("--"); pipeline = argv[k + 1:]; argv = argv[:k]
    ap = argparse.ArgumentParser(prog="bct fx", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("apply"); p.add_argument("input"); p.add_argument("-o", "--out", required=True)
    p.add_argument("--style", required=True); p.add_argument("--args"); p.add_argument("--width", type=int)
    s = sub.add_parser("strip"); s.add_argument("input"); s.add_argument("-o", "--out", required=True)
    s.add_argument("--styles", default="painting,watercolor,cartoon,sketch,halftone,glow")
    s.add_argument("--tile", type=int, default=320); s.add_argument("--work-width", type=int, default=1000); s.add_argument("--cols", type=int); s.add_argument("--no-original", action="store_true")
    g = sub.add_parser("gui"); g.add_argument("name"); g.add_argument("input"); g.add_argument("-o", "--out", required=True)
    g.add_argument("--set", action="append"); g.add_argument("--width", type=int)
    gi = sub.add_parser("gui-info"); gi.add_argument("name")
    l = sub.add_parser("list"); l.add_argument("--all", action="store_true"); l.add_argument("--search")
    r = sub.add_parser("run"); r.add_argument("input"); r.add_argument("-o", "--out", required=True)
    a = ap.parse_args(argv); a.pipeline = pipeline
    if hasattr(a, "input") and not os.path.isfile(a.input): die(f"not found: {a.input}")
    {"apply": cmd_apply, "strip": cmd_strip, "gui": cmd_gui, "gui-info": cmd_gui_info, "list": cmd_list, "run": cmd_run}[a.cmd](a)


if __name__ == "__main__":
    main()
