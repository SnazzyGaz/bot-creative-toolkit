"""bct vector: bitmap to SVG with potrace, simple SVG drawing and editing, PNG export with Inkscape.

  trace IN.png -o OUT.svg [--threshold 0.5] [--despeckle 2] [--smooth 1.0] [--tolerance 0.2]
                          [--invert] [--color "#000"] [--colors N]
        --threshold   0-1, pixels darker than this become shape (1 colour mode)
        --despeckle   drop specks up to this many pixels (potrace -t)
        --smooth      corner smoothing 0 (sharp) to 1.33 (round) (potrace -a)
        --tolerance   curve simplifying, higher = fewer nodes (potrace -O)
        --colors N    posterise to N colours and trace each as its own <g id="color-K"> layer
  new OUT.svg --size 400x300 [--background "#fff"]
  add FILE SHAPE [key=value ...] [--id ID] [--text "Hi"]
        SHAPE: rect circle ellipse line polyline polygon path text  (attrs are plain SVG attributes)
        e.g.  add art.svg rect x=10 y=10 width=80 height=40 fill=#e33 rx=6 --id box
              add art.svg path d="M10 10 L90 90" stroke=#000 stroke-width=3 fill=none
              add art.svg text x=20 y=50 font-size=24 font-family=sans-serif fill=#222 --text "Hello"
  set FILE --id ID key=value ...       change attributes (key=  with no value removes it)
  recolor FILE --from "#000" --to "#c00" [--id ID]   swap a colour in fill/stroke (whole file, or one element)
  recolor FILE --id ID [--fill C] [--stroke C]
  delete FILE --id ID [--id ID2 ...]
  list FILE                             ids, tags and sizes of drawn elements
  export FILE -o OUT.png [--width W | --dpi D] [--background "#fff"]    (Inkscape)
All commands print JSON. Edits change FILE in place.
"""
import argparse, io, json, os, re, shutil, subprocess, sys, tempfile
import xml.etree.ElementTree as ET
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import die, emit

SVG = "http://www.w3.org/2000/svg"
ET.register_namespace("", SVG)
ET.register_namespace("xlink", "http://www.w3.org/1999/xlink")
ET.register_namespace("inkscape", "http://www.inkscape.org/namespaces/inkscape")
ET.register_namespace("sodipodi", "http://sodipodi.sourceforge.net/DTD/sodipodi-0.dtd")
SHAPES = ["rect", "circle", "ellipse", "line", "polyline", "polygon", "path", "text"]
DRAWN = set(SHAPES) | {"g", "image", "use"}


def q(tag):
    return f"{{{SVG}}}{tag}"


def local(tag):
    return tag.split("}")[-1]


def load(path):
    if not os.path.isfile(path):
        die(f"not found: {path}")
    return ET.parse(path)


def save(tree, path):
    tree.write(path, encoding="utf-8", xml_declaration=True)


def by_id(root, i):
    for el in root.iter():
        if el.get("id") == i:
            return el
    die(f"no element with id '{i}'")


def parent_map(root):
    return {c: p for p in root.iter() for c in p}


def next_id(root, tag):
    used = {e.get("id") for e in root.iter()}
    n = 1
    while f"{tag}{n}" in used:
        n += 1
    return f"{tag}{n}"


def norm_color(c):
    c = (c or "").strip().lower()
    if re.fullmatch(r"#[0-9a-f]{3}", c):
        c = "#" + "".join(ch * 2 for ch in c[1:])
    names = {"black": "#000000", "white": "#ffffff", "red": "#ff0000", "blue": "#0000ff", "green": "#008000"}
    return names.get(c, c)


# ---------- trace ----------
def potrace_mask(mask_img, a):
    """mask_img: PIL '1' or 'L' image where black = shape. Returns the potrace SVG root."""
    pot = shutil.which("potrace")
    if not pot:
        die("potrace not found. Run setup.sh (or install potrace).")
    with tempfile.TemporaryDirectory() as td:
        pbm, svg = os.path.join(td, "in.pbm"), os.path.join(td, "out.svg")
        mask_img.convert("1").save(pbm)
        cmd = [pot, pbm, "-s", "-o", svg, "-t", str(a.despeckle), "-a", str(a.smooth), "-O", str(a.tolerance)]
        p = subprocess.run(cmd, capture_output=True, text=True)
        if p.returncode != 0:
            die("potrace failed: " + p.stderr.strip())
        return ET.parse(svg).getroot()


def trace(a):
    from PIL import Image
    im = Image.open(a.input)
    rgba = im.convert("RGBA")
    flat = Image.new("RGBA", rgba.size, (255, 255, 255, 255)); flat.alpha_composite(rgba)
    W, H = flat.size
    out = ET.Element(q("svg"), {"width": str(W), "height": str(H), "viewBox": f"0 0 {W} {H}", "version": "1.1"})
    layers = []
    if a.colors and a.colors > 1:
        pal_im = flat.convert("RGB").quantize(colors=a.colors, method=Image.Quantize.MEDIANCUT)
        pal = pal_im.getpalette()[:a.colors * 3]
        counts = sorted(pal_im.getcolors(), reverse=True)        # (count, index), most common first
        bg_index = counts[0][1]
        for k, (cnt, idx) in enumerate(counts):
            if idx == bg_index and not a.keep_background:
                continue
            col = "#%02x%02x%02x" % tuple(pal[idx * 3: idx * 3 + 3])
            mask = pal_im.point(lambda v, idx=idx: 0 if v == idx else 255, "L")
            layers.append((f"color-{k}", col, potrace_mask(mask, a)))
        if not a.keep_background:
            out.insert(0, ET.Element(q("rect"), {"id": "background", "width": "100%", "height": "100%",
                                                  "fill": "#%02x%02x%02x" % tuple(pal[bg_index * 3: bg_index * 3 + 3])}))
    else:
        g = flat.convert("L")
        thr = int(a.threshold * 255)
        mask = g.point(lambda v: 255 if (v < thr) == a.invert else 0, "L")
        layers.append(("trace", a.color, potrace_mask(mask, a)))
    npaths = 0
    for gid, col, root in layers:
        grp = ET.SubElement(out, q("g"), {"id": gid, "fill": col, "stroke": "none"})
        for pg in root.iter(q("g")):                 # potrace: one <g transform=...> holding the paths
            if pg.get("transform"):
                grp.set("transform", pg.get("transform"))
            for i, p in enumerate(pg.iter(q("path"))):
                el = ET.SubElement(grp, q("path"), {"id": f"{gid}-p{i}", "d": p.get("d")})
                npaths += 1
            break
    save(ET.ElementTree(out), a.out)
    emit({"svg": os.path.abspath(a.out), "size": [W, H], "groups": [g for g, _, _ in layers],
          "colors": [c for _, c, _ in layers], "paths": npaths, "bytes": os.path.getsize(a.out)})


# ---------- edit ----------
def parse_pairs(pairs):
    d = {}
    for p in pairs:
        if "=" not in p:
            die(f"expected key=value, got '{p}'")
        k, v = p.split("=", 1)
        d[k] = v
    return d


def new(a):
    w, h = a.size.lower().split("x")
    root = ET.Element(q("svg"), {"width": w, "height": h, "viewBox": f"0 0 {w} {h}", "version": "1.1"})
    if a.background:
        ET.SubElement(root, q("rect"), {"id": "background", "width": "100%", "height": "100%", "fill": a.background})
    save(ET.ElementTree(root), a.file)
    emit({"svg": os.path.abspath(a.file), "size": [int(w), int(h)]})


def add(a):
    if a.shape not in SHAPES:
        die(f"shape must be one of {', '.join(SHAPES)}")
    t = load(a.file); root = t.getroot()
    attrs = parse_pairs(a.attrs)
    i = a.id or next_id(root, a.shape)
    if any(e.get("id") == i for e in root.iter()):
        die(f"id '{i}' already used")
    parent = by_id(root, a.into) if a.into else root
    el = ET.SubElement(parent, q(a.shape), {"id": i, **attrs})
    if a.shape == "text":
        el.text = a.text or ""
    save(t, a.file)
    emit({"svg": os.path.abspath(a.file), "added": i, "tag": a.shape})


def set_attrs(a):
    t = load(a.file); el = by_id(t.getroot(), a.id)
    for k, v in parse_pairs(a.attrs).items():
        if v == "":
            el.attrib.pop(k, None)
        else:
            el.set(k, v)
    if a.text is not None:
        el.text = a.text
    save(t, a.file)
    emit({"svg": os.path.abspath(a.file), "changed": a.id, "attrs": dict(el.attrib)})


def recolor(a):
    t = load(a.file); root = t.getroot()
    targets = list(by_id(root, a.id).iter()) if a.id else list(root.iter())
    n = 0
    if a.frm:
        f, to = norm_color(a.frm), a.to
        if not to:
            die("--from needs --to")
        for el in targets:
            for k in ("fill", "stroke", "stop-color"):
                if norm_color(el.get(k)) == f:
                    el.set(k, to); n += 1
            st = el.get("style")
            if st:
                parts = []
                for kv in st.split(";"):
                    if ":" in kv:
                        k, v = kv.split(":", 1)
                        if norm_color(v) == f:
                            v = to; n += 1
                        parts.append(f"{k.strip()}:{v.strip()}")
                el.set("style", ";".join(parts))
    else:
        if not a.id:
            die("recolor needs --from/--to, or --id with --fill/--stroke")
        el = by_id(root, a.id)
        if a.fill: el.set("fill", a.fill); n += 1
        if a.stroke: el.set("stroke", a.stroke); n += 1
    save(t, a.file)
    emit({"svg": os.path.abspath(a.file), "changed": n})


def delete(a):
    t = load(a.file); root = t.getroot(); pm = parent_map(root)
    for i in a.id:
        el = by_id(root, i); pm[el].remove(el)
    save(t, a.file)
    emit({"svg": os.path.abspath(a.file), "deleted": a.id})


def list_(a):
    root = load(a.file).getroot()
    items = []
    for el in root.iter():
        tg = local(el.tag)
        if tg in DRAWN:
            d = {"id": el.get("id"), "tag": tg}
            for k in ("x", "y", "width", "height", "cx", "cy", "r", "fill", "stroke"):
                if el.get(k) is not None:
                    d[k] = el.get(k)
            if tg == "text":
                d["text"] = "".join(el.itertext())
            if tg == "path":
                d["d_len"] = len(el.get("d", ""))
            items.append(d)
    emit({"svg": os.path.abspath(a.file), "width": root.get("width"), "height": root.get("height"),
          "viewBox": root.get("viewBox"), "elements": items})


def export(a):
    ink = shutil.which("inkscape")
    if not ink:
        die("inkscape not found. Run setup.sh (or install inkscape).")
    src, out = os.path.abspath(a.file), os.path.abspath(a.out)
    if not os.path.isfile(src):
        die(f"not found: {a.file}")
    ext = os.path.splitext(out)[1].lower().lstrip(".") or "png"
    cmd = [ink, src, f"--export-type={ext}", f"--export-filename={out}"]
    if a.width: cmd.append(f"--export-width={a.width}")
    if a.dpi: cmd.append(f"--export-dpi={a.dpi}")
    if a.background:
        cmd += [f"--export-background={a.background}", "--export-background-opacity=1"]
    if os.path.exists(out):
        os.remove(out)
    env = dict(os.environ); env.pop("DISPLAY", None) if a.no_display else None
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=a.timeout, env=env)
    if not os.path.isfile(out):
        tail = "\n".join(l for l in (p.stdout + p.stderr).splitlines() if "dbind" not in l)[-1500:]
        die(f"inkscape export failed (exit {p.returncode}): {tail}")
    res = {"out": out, "bytes": os.path.getsize(out)}
    if ext == "png":
        from PIL import Image
        res["size"] = list(Image.open(out).size)
    emit(res)


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(__doc__); return
    cmd, rest = argv[0], argv[1:]
    ap = argparse.ArgumentParser(prog=f"bct vector {cmd}")
    if cmd == "trace":
        ap.add_argument("input"); ap.add_argument("-o", "--out", required=True)
        ap.add_argument("--threshold", type=float, default=0.5); ap.add_argument("--despeckle", type=int, default=2)
        ap.add_argument("--smooth", type=float, default=1.0); ap.add_argument("--tolerance", type=float, default=0.2)
        ap.add_argument("--invert", action="store_true"); ap.add_argument("--color", default="#000000")
        ap.add_argument("--colors", type=int, default=0); ap.add_argument("--keep-background", action="store_true")
        return trace(ap.parse_args(rest))
    ap.add_argument("file")
    if cmd == "new":
        ap.add_argument("--size", default="400x300"); ap.add_argument("--background")
        return new(ap.parse_args(rest))
    if cmd == "add":
        ap.add_argument("shape"); ap.add_argument("attrs", nargs="*"); ap.add_argument("--id")
        ap.add_argument("--text"); ap.add_argument("--into", help="id of a <g> to add into")
        return add(ap.parse_args(rest))
    if cmd == "set":
        ap.add_argument("attrs", nargs="*"); ap.add_argument("--id", required=True); ap.add_argument("--text")
        return set_attrs(ap.parse_args(rest))
    if cmd in ("recolor", "recolour"):
        ap.add_argument("--from", dest="frm"); ap.add_argument("--to"); ap.add_argument("--id")
        ap.add_argument("--fill"); ap.add_argument("--stroke")
        return recolor(ap.parse_args(rest))
    if cmd == "delete":
        ap.add_argument("--id", action="append", required=True)
        return delete(ap.parse_args(rest))
    if cmd == "list":
        return list_(ap.parse_args(rest))
    if cmd == "export":
        ap.add_argument("-o", "--out", required=True); ap.add_argument("--width", type=int); ap.add_argument("--dpi", type=int)
        ap.add_argument("--background"); ap.add_argument("--timeout", type=int, default=120)
        ap.add_argument("--no-display", action="store_true", help="unset DISPLAY for the export")
        return export(ap.parse_args(rest))
    die(f"unknown command '{cmd}' (try: bct vector --help)")


if __name__ == "__main__":
    main()
