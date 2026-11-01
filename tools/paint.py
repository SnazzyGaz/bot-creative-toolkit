"""bct paint: Krita without its window (export, convert, layer info, Python scripts).

  export IN -o OUT [--timeout 300]
        convert between Krita's formats by extension: .kra .ora .psd .png .jpg .tif .webp ...
        (ORA -> KRA keeps the layers; anything -> PNG flattens). With no Krita, .kra/.ora -> .png still
        works by reading the flattened copy stored inside the file.
  info FILE.kra|FILE.ora        size and layer list, top layer first (name, type, visible, opacity, offset),
                                read straight from the zip (no Krita needed)
  stack A.png B.png ... -o OUT.kra [--names a,b] [--opacity 1,0.5]
        a layered Krita file from PNGs (first = bottom), all placed at 0,0
  script FILE.py [ARGS...] [--timeout 300]
        run your own Python inside Krita. FILE.py defines main(args) and may return a dict;
        `from krita import Krita` works. The result, any print() output and errors come back as JSON.
Krita needs a screen even without a window: with no $DISPLAY this runs it under xvfb-run.
The first run after install takes about 30 s (Krita sets up its resource database); later runs about 2 s.
"""
import argparse, json, os, re, shutil, subprocess, sys, tempfile, time, zipfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import die, emit

RUNNER = r'''
import io, json, sys, traceback, runpy
OUT = %(out)r
def __main__(args):
    buf = io.StringIO(); old = sys.stdout, sys.stderr; sys.stdout = sys.stderr = buf
    res = {"ok": False}
    try:
        sys.argv = [%(script)r] + %(args)r
        g = runpy.run_path(%(script)r, run_name="bct_krita_script")
        if "main" not in g: raise RuntimeError("the script must define main(args)")
        r = g["main"](%(args)r)
        res = {"ok": True, "result": r}
    except BaseException:
        res = {"ok": False, "error": traceback.format_exc()}
    finally:
        sys.stdout, sys.stderr = old
    res["printed"] = buf.getvalue()
    with open(OUT, "w") as f: json.dump(res, f, default=str)
'''


def headless(cmd):
    if os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"): return cmd
    x = shutil.which("xvfb-run")
    if not x: die("Krita needs an X server: install xvfb (setup.sh does) or set $DISPLAY")
    return [x, "-a", "-s", "-screen 0 1280x1024x24"] + cmd


def run(cmd, timeout):
    t = time.time()
    try:
        p = subprocess.run(headless(cmd), capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        die(f"Krita did not finish in {timeout} s", 1)
    noise = ("Fontconfig", "QStandardPaths", "kf.", "krita.lib", "qt.", "Could not", "libpng warning", "xkbcommon", "QSocketNotifier")
    log = [l for l in (p.stdout + p.stderr).splitlines() if l.strip() and not l.lstrip().startswith(noise)]
    return p.returncode, round(time.time() - t, 2), log[-15:]


def image_stats(path):
    from PIL import Image, ImageStat
    im = Image.open(path).convert("RGBA")
    st = ImageStat.Stat(im)
    cover = sum(im.getchannel("A").histogram()[9:]) / (im.width * im.height)
    rgb_std = round(sum(st.stddev[:3]) / 3, 2)
    return {"size": [im.width, im.height], "opaque_fraction": round(cover, 3), "rgb_std": rgb_std,
            "blank": cover < 0.001 or (rgb_std < 0.5 and st.stddev[3] < 0.5)}


def read_layers(path):
    z = zipfile.ZipFile(path)
    names = z.namelist()
    if "maindoc.xml" in names:   # Krita
        xml = z.read("maindoc.xml").decode("utf-8", "replace")
        img = re.search(r"<IMAGE[^>]*>", xml).group(0)
        attr = lambda tag, k: (re.search(fr'\b{k}="([^"]*)"', tag) or [None, None])[1]
        layers = []
        for tag in re.findall(r"<layer\b[^>]*>", xml):
            layers.append({"name": attr(tag, "name"), "type": attr(tag, "nodetype"),
                           "visible": attr(tag, "visible") != "0", "opacity": round(int(attr(tag, "opacity") or 255) / 255, 3),
                           "x": int(attr(tag, "x") or 0), "y": int(attr(tag, "y") or 0)})
        return {"format": "kra", "size": [int(attr(img, "width")), int(attr(img, "height"))],
                "colorspace": attr(img, "colorspacename"), "layers": layers}
    if "stack.xml" in names:     # OpenRaster
        xml = z.read("stack.xml").decode("utf-8", "replace")
        img = re.search(r"<image[^>]*>", xml).group(0)
        attr = lambda tag, k: (re.search(fr'\b{k}="([^"]*)"', tag) or [None, None])[1]
        layers = [{"name": attr(t, "name"), "type": "paintlayer", "visible": attr(t, "visibility") != "hidden",
                   "opacity": float(attr(t, "opacity") or 1), "x": int(attr(t, "x") or 0), "y": int(attr(t, "y") or 0)}
                  for t in re.findall(r"<layer\b[^>]*>", xml)]
        return {"format": "ora", "size": [int(attr(img, "w")), int(attr(img, "h"))], "layers": layers}
    die(f"{path}: not a .kra or .ora file")


def flat_from_zip(src, out):
    z = zipfile.ZipFile(src)
    if "mergedimage.png" not in z.namelist(): die(f"{src} has no flattened copy inside; install Krita (setup.sh)")
    from PIL import Image
    import io
    Image.open(io.BytesIO(z.read("mergedimage.png"))).save(out)


def krita():
    return shutil.which("krita")


def cmd_export(a):
    src, out = os.path.abspath(a.input), os.path.abspath(a.out)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    if os.path.exists(out): os.remove(out)
    ext_in, ext_out = os.path.splitext(src)[1].lower(), os.path.splitext(out)[1].lower()
    k = krita()
    if not k:
        if ext_in in (".kra", ".ora") and ext_out == ".png":
            flat_from_zip(src, out); res = {"out": out, "via": "flattened copy inside the file (no Krita)"}
        else: die("krita not found. Run setup.sh (or use a .kra/.ora -> .png export, which works without it)")
    else:
        code, secs, log = run([k, "--nosplash", src, "--export", "--export-filename", out], a.timeout)
        if not os.path.exists(out):
            die("Krita did not write the file. " + " | ".join(log[-5:]), 1)
        res = {"out": out, "via": "krita --export", "seconds": secs}
    if ext_out in (".kra", ".ora"):
        info = read_layers(out); res["layers"] = [l["name"] for l in info["layers"]]; res["size"] = info["size"]
    else:
        try: res.update(image_stats(out))
        except Exception: pass
    emit(res)


def cmd_info(a):
    info = read_layers(a.input)
    info["file"] = os.path.abspath(a.input)
    emit(info)


def cmd_stack(a):
    from PIL import Image
    if not a.out.lower().endswith((".kra", ".ora")): die("-o must end in .kra or .ora")
    names = a.names.split(",") if a.names else [os.path.splitext(os.path.basename(p))[0] for p in a.pngs]
    ops = [float(x) for x in a.opacity.split(",")] if a.opacity else [1.0] * len(a.pngs)
    if len(names) != len(a.pngs) or len(ops) != len(a.pngs): die("--names/--opacity need one value per PNG")
    ims = [Image.open(p).convert("RGBA") for p in a.pngs]
    W, H = max(i.width for i in ims), max(i.height for i in ims)
    tmp = tempfile.mkdtemp(prefix="bct_paint_")
    ora = a.out if a.out.lower().endswith(".ora") else os.path.join(tmp, "stack.ora")
    flat = Image.new("RGBA", (W, H))
    with zipfile.ZipFile(ora, "w") as z:
        z.writestr(zipfile.ZipInfo("mimetype"), "image/openraster")
        rows = []
        for k, (im, n, o) in enumerate(zip(ims, names, ops)):
            buf = __import__("io").BytesIO(); im.save(buf, "PNG"); z.writestr(f"data/layer{k}.png", buf.getvalue())
            lay = im.copy(); lay.putalpha(lay.getchannel("A").point(lambda v: int(v * o)))
            flat.alpha_composite(lay)
            n = n.replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;")
            rows.append(f'  <layer name="{n}" src="data/layer{k}.png" x="0" y="0" opacity="{o}" visibility="visible"/>')
        z.writestr("stack.xml", f'<?xml version="1.0" encoding="UTF-8"?>\n<image version="0.0.3" w="{W}" h="{H}">\n <stack>\n'
                   + "\n".join(rows[::-1]) + "\n </stack>\n</image>\n")
        buf = __import__("io").BytesIO(); flat.save(buf, "PNG"); z.writestr("mergedimage.png", buf.getvalue())
        th = flat.copy(); th.thumbnail((256, 256)); buf = __import__("io").BytesIO(); th.save(buf, "PNG")
        z.writestr("Thumbnails/thumbnail.png", buf.getvalue())
    if ora != a.out:
        a.input, a.timeout = ora, a.timeout
        cmd_export(a)
    else:
        emit({"out": os.path.abspath(ora), "layers": names, "size": [W, H]})
    shutil.rmtree(tmp, ignore_errors=True)


def cmd_script(a):
    kr = shutil.which("kritarunner")
    if not kr: die("kritarunner not found (it comes with the Krita AppImage that setup.sh installs)")
    script = os.path.abspath(a.script)
    if not os.path.isfile(script): die(f"not found: {script}")
    tmp = tempfile.mkdtemp(prefix="bct_krita_")
    out = os.path.join(tmp, "result.json")
    with open(os.path.join(tmp, "bct_runner.py"), "w") as f:
        f.write(RUNNER % {"out": out, "script": script, "args": a.args})
    env_pp = os.environ.get("PYTHONPATH")
    os.environ["PYTHONPATH"] = tmp + (":" + env_pp if env_pp else "")
    code, secs, log = run([kr, "-s", "bct_runner"], a.timeout)
    if not os.path.exists(out):
        die("the script did not run inside Krita. " + " | ".join(log[-6:]), 1)
    res = json.load(open(out)); res["seconds"] = secs
    shutil.rmtree(tmp, ignore_errors=True)
    emit(res)
    if not res.get("ok"): sys.exit(1)


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    ap = argparse.ArgumentParser(prog="bct paint", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("export"); e.add_argument("input"); e.add_argument("-o", "--out", required=True)
    e.add_argument("--timeout", type=int, default=300)
    i = sub.add_parser("info"); i.add_argument("input")
    s = sub.add_parser("stack"); s.add_argument("pngs", nargs="+"); s.add_argument("-o", "--out", required=True)
    s.add_argument("--names"); s.add_argument("--opacity"); s.add_argument("--timeout", type=int, default=300)
    sc = sub.add_parser("script"); sc.add_argument("script"); sc.add_argument("args", nargs=argparse.REMAINDER)
    sc.add_argument("--timeout", type=int, default=300)
    a = ap.parse_args(argv)
    if a.cmd == "script":   # --timeout may sit among the script's own args
        if "--timeout" in a.args:
            k = a.args.index("--timeout"); a.timeout = int(a.args[k + 1]); del a.args[k:k + 2]
    if hasattr(a, "input") and not os.path.isfile(a.input): die(f"not found: {a.input}")
    {"export": cmd_export, "info": cmd_info, "stack": cmd_stack, "script": cmd_script}[a.cmd](a)


if __name__ == "__main__":
    main()
