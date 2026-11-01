"""bct layers: build images from a JSON layer stack, so one layer can change without redoing the rest.

Stack file (layers are listed bottom to top):
  {"width": 800, "height": 600, "background": "#ffffff",
   "layers": [
     {"id": "sky",   "type": "fill",    "color": "#87ceeb", "to": "#ffffff"},          # "to" = vertical gradient
     {"id": "photo", "type": "image",   "src": "cat.png", "x": 40, "y": 60, "w": 300},  # w/h scale, keeps aspect if one given
     {"id": "card",  "type": "rect",    "x": 20, "y": 20, "w": 200, "h": 80, "fill": "#0008", "radius": 12,
                                         "stroke": "#fff", "stroke_width": 2},
     {"id": "dot",   "type": "ellipse", "x": 300, "y": 300, "w": 60, "h": 60, "fill": "red"},
     {"id": "zig",   "type": "line",    "points": [[0,0],[50,40],[100,0]], "color": "#000", "width": 4},
     {"id": "tri",   "type": "polygon", "points": [[0,60],[30,0],[60,60]], "x": 500, "y": 50, "fill": "gold"},
     {"id": "title", "type": "text",    "text": "Hello", "x": 30, "y": 30, "size": 48, "color": "#fff",
                                         "font": "DejaVu Sans", "stroke": "#000", "stroke_width": 2, "align": "left"}
   ]}
Every layer also takes: "center" ("x", "y" or "both": centre it on the canvas, ignoring x/y on that axis),
"radius" on image layers (rounded corners), "opacity" 0-1, "blend" (normal multiply screen overlay darken lighten difference add),
"visible" true/false, "rotate" degrees (about the layer's own centre).
Paths in "src" are relative to the stack file. Rendered layers are cached in <stack>.cache/, so after an edit
only the changed layer is drawn again.

Commands (all print JSON):
  new STACK --size 800x600 [--background "#fff"]
  render STACK [-o out.png] [--ora out.ora] [--no-cache]
  list STACK
  add STACK '{"id":..,"type":..}' [--at INDEX]      (INDEX 0 = bottom; default top)
  set STACK ID key=value ...                         (values parsed as JSON when possible: x=10 visible=false)
  replace STACK ID --src new.png | '{"type":..}'     (swap a layer's image, or its whole definition, keeping id)
  move STACK ID --to X Y | --by DX DY
  hide STACK ID / show STACK ID
  reorder STACK ID --to INDEX | --up | --down | --top | --bottom
  remove STACK ID
  from-ora FILE.ora -o STACK [--layers-dir DIR]     (read an OpenRaster file back into a stack)
Add --render (and -o/--ora) to any edit command to re-render straight after.
"""
import argparse, copy, hashlib, io, json, math, os, sys, zipfile
import xml.etree.ElementTree as ET
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import die, emit, load_font, rgba

from PIL import Image, ImageDraw
import numpy as np

BLENDS = ["normal", "multiply", "screen", "overlay", "darken", "lighten", "difference", "add"]
ORA_OP = {"normal": "svg:src-over", "multiply": "svg:multiply", "screen": "svg:screen", "overlay": "svg:overlay",
          "darken": "svg:darken", "lighten": "svg:lighten", "difference": "svg:difference", "add": "svg:plus"}
ORA_OP_BACK = {v: k for k, v in ORA_OP.items()}
TYPES = ["fill", "image", "rect", "ellipse", "line", "polygon", "text"]


# ---------- stack file ----------
def load(path):
    if not os.path.isfile(path):
        die(f"stack not found: {path}")
    s = json.load(open(path))
    s.setdefault("layers", [])
    return s


def save(path, s):
    with open(path, "w") as f:
        json.dump(s, f, indent=1)


def find(s, lid):
    for i, l in enumerate(s["layers"]):
        if l.get("id") == lid:
            return i, l
    die(f"no layer with id '{lid}' (have: {', '.join(str(l.get('id')) for l in s['layers'])})")


def check_layer(l):
    if l.get("type") not in TYPES:
        die(f"layer '{l.get('id')}': type must be one of {', '.join(TYPES)}")
    if l.get("blend", "normal") not in BLENDS:
        die(f"layer '{l.get('id')}': blend must be one of {', '.join(BLENDS)}")


# ---------- drawing one layer ----------
def draw_layer(l, W, H, base_dir):
    """Returns (RGBA image, x, y) for the layer, before opacity/blend."""
    t = l["type"]
    x, y = int(round(l.get("x", 0))), int(round(l.get("y", 0)))
    if t == "fill":
        c1 = rgba(l.get("color", "#ffffff"))
        if l.get("to"):
            c2 = rgba(l["to"])
            g = np.linspace(0, 1, H)[:, None, None]
            arr = (np.array(c1) * (1 - g) + np.array(c2) * g).astype(np.uint8)
            im = Image.fromarray(np.repeat(arr, W, axis=1), "RGBA")
        else:
            im = Image.new("RGBA", (W, H), c1)
        return im, 0, 0
    if t == "image":
        src = l.get("src")
        if not src:
            die(f"layer '{l.get('id')}': image layer needs src")
        p = src if os.path.isabs(src) else os.path.join(base_dir, src)
        if not os.path.isfile(p):
            die(f"layer '{l.get('id')}': image not found: {p}")
        im = Image.open(p).convert("RGBA")
        w, h = l.get("w"), l.get("h")
        if w or h:
            w = int(w or im.width * h / im.height); h = int(h or im.height * w / im.width)
            im = im.resize((max(1, w), max(1, h)), Image.LANCZOS)
        if l.get("radius"):                                    # rounded corners
            m = Image.new("L", im.size, 0)
            ImageDraw.Draw(m).rounded_rectangle([0, 0, im.width - 1, im.height - 1], radius=int(l["radius"]), fill=255)
            im.putalpha(Image.fromarray(np.minimum(np.asarray(im.getchannel("A")), np.asarray(m))))
        return im, x, y
    if t in ("rect", "ellipse"):
        w, h = int(l.get("w", 100)), int(l.get("h", 100))
        sw = int(l.get("stroke_width", 0) if l.get("stroke") else 0)
        im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        fill = rgba(l["fill"]) if l.get("fill") else None
        outline = rgba(l["stroke"]) if l.get("stroke") else None
        box = [0, 0, w - 1, h - 1]
        if t == "rect" and l.get("radius"):
            d.rounded_rectangle(box, radius=int(l["radius"]), fill=fill, outline=outline, width=sw)
        elif t == "rect":
            d.rectangle(box, fill=fill, outline=outline, width=sw)
        else:
            d.ellipse(box, fill=fill, outline=outline, width=sw)
        return im, x, y
    if t in ("line", "polygon"):
        pts = [tuple(p) for p in l.get("points", [])]
        if len(pts) < 2:
            die(f"layer '{l.get('id')}': needs at least 2 points")
        width = int(l.get("width", l.get("stroke_width", 2)))
        pad = width + 2
        mx, my = min(p[0] for p in pts), min(p[1] for p in pts)
        Mx, My = max(p[0] for p in pts), max(p[1] for p in pts)
        im = Image.new("RGBA", (int(Mx - mx) + 2 * pad + 1, int(My - my) + 2 * pad + 1), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        rel = [(p[0] - mx + pad, p[1] - my + pad) for p in pts]
        if t == "line":
            d.line(rel, fill=rgba(l.get("color", "#000")), width=width, joint="curve")
        else:
            d.polygon(rel, fill=rgba(l["fill"]) if l.get("fill") else None,
                      outline=rgba(l["stroke"]) if l.get("stroke") else None, width=width if l.get("stroke") else 1)
        return im, int(x + mx - pad), int(y + my - pad)
    if t == "text":
        font = load_font(l.get("font"), int(l.get("size", 32)))
        sw = int(l.get("stroke_width", 0))
        text = str(l.get("text", ""))
        probe = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
        kw = dict(font=font, stroke_width=sw, align=l.get("align", "left"), spacing=int(l.get("line_spacing", 4)))
        bb = probe.multiline_textbbox((0, 0), text, **kw)
        im = Image.new("RGBA", (bb[2] - bb[0] + 2, bb[3] - bb[1] + 2), (0, 0, 0, 0))
        ImageDraw.Draw(im).multiline_text((-bb[0] + 1, -bb[1] + 1), text, fill=rgba(l.get("color", "#000")),
                                          stroke_fill=rgba(l.get("stroke", "#000")), **kw)
        return im, x + bb[0], y + bb[1]
    die(f"unknown layer type {t}")


def layer_key(l, base_dir):
    d = {k: v for k, v in l.items() if k not in ("opacity", "blend", "visible", "x", "y", "id", "name")}
    if l["type"] in ("line", "polygon", "text"):   # these use x/y inside the drawing offset only; keep them out too
        pass
    if l["type"] == "image" and l.get("src"):
        p = l["src"] if os.path.isabs(l["src"]) else os.path.join(base_dir, l["src"])
        d["_mtime"] = os.path.getmtime(p) if os.path.exists(p) else 0
    return hashlib.sha1(json.dumps(d, sort_keys=True).encode()).hexdigest()[:16]


def raster(l, W, H, base_dir, cache_dir, stats):
    """Layer pixels (with rotation) + offset, from cache when the layer's look hasn't changed."""
    key = layer_key(l, base_dir) + f"_{W}x{H}"
    cp = os.path.join(cache_dir, key + ".png") if cache_dir else None
    if cp and os.path.isfile(cp) and os.path.isfile(cp + ".json"):
        off = json.load(open(cp + ".json"))
        stats["cached"].append(l["id"])
        im = Image.open(cp); im.load()
    else:
        im, ox, oy = draw_layer(l, W, H, base_dir)
        if l.get("rotate"):
            cx, cy = ox + im.width / 2, oy + im.height / 2
            im = im.rotate(-float(l["rotate"]), resample=Image.BICUBIC, expand=True)
            ox, oy = int(round(cx - im.width / 2)), int(round(cy - im.height / 2))
        off = {"dx": ox - int(round(l.get("x", 0))), "dy": oy - int(round(l.get("y", 0)))}
        stats["drawn"].append(l["id"])
        if cp:
            os.makedirs(cache_dir, exist_ok=True)
            im.save(cp); json.dump(off, open(cp + ".json", "w"))
    return im, int(round(l.get("x", 0))) + off["dx"], int(round(l.get("y", 0))) + off["dy"]


# ---------- compositing ----------
def blend_rgb(b, s, mode):
    if mode == "multiply": return b * s
    if mode == "screen": return 1 - (1 - b) * (1 - s)
    if mode == "overlay": return np.where(b <= 0.5, 2 * b * s, 1 - 2 * (1 - b) * (1 - s))
    if mode == "darken": return np.minimum(b, s)
    if mode == "lighten": return np.maximum(b, s)
    if mode == "difference": return np.abs(b - s)
    if mode == "add": return np.minimum(1, b + s)
    return s


def composite(canvas, im, x, y, opacity, mode):
    """canvas: float32 HxWx4 (straight alpha, 0-1). Places im at x,y with opacity and blend mode."""
    H, W = canvas.shape[:2]
    x0, y0, x1, y1 = max(0, x), max(0, y), min(W, x + im.width), min(H, y + im.height)
    if x0 >= x1 or y0 >= y1:
        return
    src = np.asarray(im, dtype=np.float32)[y0 - y:y1 - y, x0 - x:x1 - x] / 255.0
    dst = canvas[y0:y1, x0:x1]
    sa = src[..., 3:4] * float(opacity); da = dst[..., 3:4]
    sc, dc = src[..., :3], dst[..., :3]
    mixed = blend_rgb(dc, sc, mode)
    sc2 = (1 - da) * sc + da * mixed               # W3C compositing: blend only where there is something below
    oa = sa + da * (1 - sa)
    oc = np.where(oa > 0, (sc2 * sa + dc * da * (1 - sa)) / np.maximum(oa, 1e-6), 0)
    canvas[y0:y1, x0:x1, :3] = oc; canvas[y0:y1, x0:x1, 3:4] = oa


def render(stack_path, out=None, ora=None, use_cache=True):
    s = load(stack_path)
    W, H = int(s["width"]), int(s["height"])
    base = os.path.dirname(os.path.abspath(stack_path))
    cache = (os.path.splitext(stack_path)[0] + ".cache") if use_cache else None
    canvas = np.zeros((H, W, 4), np.float32)
    if s.get("background"):
        canvas[:] = np.array(rgba(s["background"]), np.float32) / 255.0
    stats = {"drawn": [], "cached": [], "hidden": []}
    rasters = []
    for l in s["layers"]:
        check_layer(l)
        if not l.get("visible", True):
            stats["hidden"].append(l["id"])
        im, x, y = raster(l, W, H, base, cache, stats)
        c = l.get("center")                                    # "x", "y" or "both": centre on the canvas
        if c in ("x", "both"): x = (W - im.width) // 2
        if c in ("y", "both"): y = (H - im.height) // 2
        rasters.append((l, im, x, y))
        if l.get("visible", True):
            composite(canvas, im, x, y, l.get("opacity", 1.0), l.get("blend", "normal"))
    flat = Image.fromarray(np.clip(canvas * 255 + 0.5, 0, 255).astype(np.uint8), "RGBA")
    out = out or os.path.splitext(stack_path)[0] + ".png"
    flat.save(out)
    res = {"png": os.path.abspath(out), "size": [W, H], "layers": len(s["layers"]), **stats}
    if ora:
        write_ora(ora, s, rasters, flat)
        res["ora"] = os.path.abspath(ora)
    if cache:   # drop cache files no layer uses any more
        keep = {layer_key(l, base) + f"_{W}x{H}" for l in s["layers"]}
        for f in os.listdir(cache) if os.path.isdir(cache) else []:
            if f.split(".")[0] not in keep:
                os.remove(os.path.join(cache, f))
    return res


# ---------- OpenRaster ----------
def write_ora(path, s, rasters, flat):
    W, H = int(s["width"]), int(s["height"])
    root = ET.Element("image", {"version": "0.0.3", "w": str(W), "h": str(H)})
    st = ET.SubElement(root, "stack")
    files = {}
    if s.get("background"):
        bgim = Image.new("RGBA", (W, H), rgba(s["background"]))
        rasters = [({"id": "_background", "type": "fill", "color": s["background"]}, bgim, 0, 0)] + list(rasters)
    for i, (l, im, x, y) in enumerate(rasters):
        name = f"data/{i:03d}_{l['id']}.png"
        b = io.BytesIO(); im.save(b, "PNG"); files[name] = b.getvalue()
        attrs = {"name": str(l["id"]), "src": name, "x": str(x), "y": str(y),
                 "opacity": f"{float(l.get('opacity', 1.0)):.3f}",
                 "visibility": "visible" if l.get("visible", True) else "hidden",
                 "composite-op": ORA_OP[l.get("blend", "normal")]}
        st.insert(0, ET.Element("layer", attrs))            # ORA lists the top layer first
    with zipfile.ZipFile(path, "w") as z:
        z.writestr(zipfile.ZipInfo("mimetype"), "image/openraster", compress_type=zipfile.ZIP_STORED)
        z.writestr("stack.xml", ET.tostring(root, encoding="utf-8", xml_declaration=True), compress_type=zipfile.ZIP_DEFLATED)
        for n, data in files.items():
            z.writestr(n, data, compress_type=zipfile.ZIP_DEFLATED)
        b = io.BytesIO(); flat.save(b, "PNG"); z.writestr("mergedimage.png", b.getvalue())
        th = flat.copy(); th.thumbnail((256, 256)); b = io.BytesIO(); th.save(b, "PNG")
        z.writestr("Thumbnails/thumbnail.png", b.getvalue())


def from_ora(path, out, layers_dir=None):
    if not zipfile.is_zipfile(path):
        die(f"not an ORA/zip file: {path}")
    z = zipfile.ZipFile(path)
    root = ET.fromstring(z.read("stack.xml"))
    W, H = int(root.get("w")), int(root.get("h"))
    layers_dir = layers_dir or os.path.splitext(out)[0] + "_layers"
    os.makedirs(layers_dir, exist_ok=True)
    rel = os.path.relpath(layers_dir, os.path.dirname(os.path.abspath(out)))
    layers, used = [], set()

    def walk(stack, ox, oy, op, vis):
        for el in stack:                                      # top first
            x = ox + int(float(el.get("x", 0))); y = oy + int(float(el.get("y", 0)))
            o = op * float(el.get("opacity", 1)); v = vis and el.get("visibility", "visible") != "hidden"
            if el.tag == "stack":                             # nested groups are flattened into the list
                walk(el, x, y, o, v)
            elif el.tag == "layer" and el.get("src"):
                name = el.get("name") or os.path.splitext(os.path.basename(el.get("src")))[0]
                lid = "".join(c if c.isalnum() or c in "-_" else "_" for c in name) or "layer"
                while lid in used:
                    lid += "_"
                used.add(lid)
                fn = lid + ".png"
                with open(os.path.join(layers_dir, fn), "wb") as f:
                    f.write(z.read(el.get("src")))
                layers.append({"id": lid, "type": "image", "src": os.path.join(rel, fn), "x": x, "y": y,
                               "opacity": round(o, 3), "visible": v,
                               "blend": ORA_OP_BACK.get(el.get("composite-op", "svg:src-over"), "normal")})
    walk(root.find("stack"), 0, 0, 1.0, True)
    s = {"width": W, "height": H, "background": None, "layers": list(reversed(layers))}
    save(out, s)
    return {"stack": os.path.abspath(out), "size": [W, H], "layers": [l["id"] for l in s["layers"]],
            "layers_dir": os.path.abspath(layers_dir)}


# ---------- CLI ----------
def parse_val(v):
    try:
        return json.loads(v)
    except Exception:
        return v


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(__doc__); return
    cmd, rest = argv[0], argv[1:]
    ap = argparse.ArgumentParser(prog=f"bct layers {cmd}")
    if cmd == "from-ora":
        ap.add_argument("ora"); ap.add_argument("-o", "--out", required=True); ap.add_argument("--layers-dir")
        a = ap.parse_args(rest); emit(from_ora(a.ora, a.out, a.layers_dir)); return
    ap.add_argument("stack")
    if cmd == "new":
        ap.add_argument("--size", default="800x600"); ap.add_argument("--background", default=None)
        a = ap.parse_args(rest)
        w, h = (int(v) for v in a.size.lower().split("x"))
        save(a.stack, {"width": w, "height": h, "background": a.background, "layers": []})
        emit({"stack": os.path.abspath(a.stack), "size": [w, h]}); return
    if cmd in ("set", "replace", "move", "hide", "show", "reorder", "remove"):
        ap.add_argument("id")
    if cmd == "add":
        ap.add_argument("layer", help="layer JSON"); ap.add_argument("--at", type=int)
    if cmd == "set":
        ap.add_argument("pairs", nargs="+", help="key=value")
    if cmd == "replace":
        ap.add_argument("layer", nargs="?", help="new layer JSON"); ap.add_argument("--src")
    if cmd == "move":
        ap.add_argument("--to", nargs=2, type=float); ap.add_argument("--by", nargs=2, type=float)
    if cmd == "reorder":
        g = ap.add_mutually_exclusive_group(required=True)
        g.add_argument("--to", type=int); g.add_argument("--up", action="store_true"); g.add_argument("--down", action="store_true")
        g.add_argument("--top", action="store_true"); g.add_argument("--bottom", action="store_true")
    ap.add_argument("-o", "--out"); ap.add_argument("--ora"); ap.add_argument("--no-cache", action="store_true")
    if cmd != "render":
        ap.add_argument("--render", action="store_true", help="re-render after the edit")
    known = ("render", "list", "add", "set", "replace", "move", "hide", "show", "reorder", "remove")
    if cmd not in known:
        die(f"unknown command '{cmd}' (try: bct layers --help)")
    a = ap.parse_args(rest)

    if cmd == "render":
        emit(render(a.stack, a.out, a.ora, not a.no_cache)); return
    s = load(a.stack)
    if cmd == "list":
        emit({"size": [s["width"], s["height"]], "background": s.get("background"),
              "layers": [{"index": i, "id": l.get("id"), "type": l.get("type"), "x": l.get("x", 0), "y": l.get("y", 0),
                          "opacity": l.get("opacity", 1.0), "blend": l.get("blend", "normal"),
                          "visible": l.get("visible", True)} for i, l in enumerate(s["layers"])]}); return
    res = {"stack": os.path.abspath(a.stack), "edit": cmd}
    if cmd == "add":
        l = json.loads(a.layer)
        l.setdefault("id", f"{l.get('type', 'layer')}{len(s['layers'])}")
        if any(x.get("id") == l["id"] for x in s["layers"]):
            die(f"id '{l['id']}' already used")
        check_layer(l)
        s["layers"].insert(len(s["layers"]) if a.at is None else a.at, l); res["id"] = l["id"]
    else:
        i, l = find(s, a.id); res["id"] = a.id
        if cmd == "set":
            for p in a.pairs:
                if "=" not in p:
                    die(f"expected key=value, got '{p}'")
                k, v = p.split("=", 1)
                if k == "id":
                    die("use replace/remove to change ids")
                l[k] = parse_val(v)
            check_layer(l)
        elif cmd == "replace":
            if a.src:
                if l["type"] != "image":
                    die("--src only works on image layers; pass new layer JSON instead")
                l["src"] = a.src
            elif a.layer:
                new = json.loads(a.layer); new["id"] = a.id; check_layer(new); s["layers"][i] = new
            else:
                die("replace needs --src or new layer JSON")
        elif cmd == "move":
            if a.to:
                l["x"], l["y"] = a.to
            elif a.by:
                l["x"] = l.get("x", 0) + a.by[0]; l["y"] = l.get("y", 0) + a.by[1]
            else:
                die("move needs --to X Y or --by DX DY")
        elif cmd in ("hide", "show"):
            l["visible"] = cmd == "show"
        elif cmd == "reorder":
            s["layers"].pop(i)
            n = len(s["layers"])
            j = a.to if a.to is not None else (i + 1 if a.up else i - 1 if a.down else n if a.top else 0)
            s["layers"].insert(max(0, min(n, j)), l); res["index"] = max(0, min(n, j))
        elif cmd == "remove":
            s["layers"].pop(i)
    save(a.stack, s)
    if a.render:
        res["render"] = render(a.stack, a.out, a.ora, not a.no_cache)
    emit(res)


if __name__ == "__main__":
    main()
