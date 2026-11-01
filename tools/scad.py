"""bct scad: OpenSCAD models to STL/3MF/OFF and PNG previews, with parameters, from the command line.

  render MODEL.scad -o OUT.stl [--png preview.png] [--sheet sheet.png] [-D name=value ...] [-S name=text ...]
         [--size 800x600] [--camera "eye_x,y,z,center_x,y,z"] [--colorscheme Tomorrow] [--fast]
         [--backend manifold|cgal] [--ascii]
        -D passes an OpenSCAD expression (numbers, true/false, [1,2,3]); -S passes a string (quoted for you)
        --png    OpenSCAD's own image of the final geometry (faces left by a difference() show in a 2nd colour)
        --fast   use OpenSCAD's quick preview mode for PNGs instead (can z-fight where faces touch)
        --sheet  4-view Blender contact sheet of the STL via `bct look` (mm are converted to metres)
  png MODEL.scad -o OUT.png [same -D/-S/--size/--camera/--colorscheme/--fast]
  params MODEL.scad               the Customizer parameters (name, default, range, caption) as JSON
"""
import argparse, json, os, shutil, struct, subprocess, sys, tempfile, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import die, emit

HERE = os.path.dirname(os.path.abspath(__file__))


def openscad():
    p = shutil.which("openscad") or shutil.which("openscad-nightly")
    if not p:
        die("openscad not found. Run setup.sh")
    return p


_backend_ok = None
def has_manifold():
    global _backend_ok
    if _backend_ok is None:
        h = subprocess.run([openscad(), "--help"], capture_output=True, text=True)
        _backend_ok = "Manifold" in (h.stdout + h.stderr)
    return _backend_ok


def defs(a):
    out = []
    for d in a.D or []:
        if "=" not in d: die(f"-D needs name=value, got {d!r}")
        out += ["-D", d]
    for s in a.S or []:
        if "=" not in s: die(f"-S needs name=text, got {s!r}")
        k, v = s.split("=", 1)
        out += ["-D", f'{k}="' + v.replace("\\", "\\\\").replace('"', '\\"') + '"']
    return out


def run_scad(args, what):
    t = time.time()
    p = subprocess.run([openscad()] + args, capture_output=True, text=True)
    log = p.stderr.splitlines()
    echoes = [l[6:].strip() for l in log if l.startswith("ECHO:")]
    warns = [l.strip() for l in log if l.startswith(("WARNING", "ERROR", "TRACE"))]
    if p.returncode != 0:
        die(f"{what} failed:\n" + "\n".join((warns or log)[-12:]), 1)
    return {"seconds": round(time.time() - t, 2), "echo": echoes, "warnings": warns}


def stl_stats(path):
    """Read an STL (binary or ASCII) ourselves: triangle count and bounding box, independent of OpenSCAD."""
    data = open(path, "rb").read()
    tris = []
    if len(data) >= 84:
        n = struct.unpack("<I", data[80:84])[0]
        if 84 + 50 * n == len(data):
            for i in range(n):
                o = 84 + 50 * i + 12
                tris.append(struct.unpack("<9f", data[o:o + 36]))
    if not tris and data[:5].lower() == b"solid":
        vs = [tuple(map(float, l.split()[1:4])) for l in data.decode("ascii", "replace").splitlines() if l.strip().startswith("vertex")]
        tris = [sum(vs[i:i + 3], ()) for i in range(0, len(vs) - 2, 3)]
    if not tris:
        return {"triangles": 0}
    xs = [t[i] for t in tris for i in (0, 3, 6)]; ys = [t[i] for t in tris for i in (1, 4, 7)]; zs = [t[i] for t in tris for i in (2, 5, 8)]
    lo = [min(xs), min(ys), min(zs)]; hi = [max(xs), max(ys), max(zs)]
    return {"triangles": len(tris), "bbox_min": [round(v, 4) for v in lo], "bbox_max": [round(v, 4) for v in hi],
            "size_mm": [round(h - l, 4) for l, h in zip(lo, hi)]}


def png_args(a, out):
    w, _, h = a.size.partition("x")
    args = ["-o", out, f"--imgsize={w},{h}", f"--colorscheme={a.colorscheme}"]
    args += [f"--camera={a.camera}"] if a.camera else ["--autocenter", "--viewall"]
    if not a.fast:
        args += ["--render=force"]   # note: a bare --render swallows the next argument
    return args


def cmd_render(a):
    src = os.path.abspath(a.model)
    ext = os.path.splitext(a.out)[1].lower()
    tmp = tempfile.mkdtemp(prefix="bct_scad_")
    summ = os.path.join(tmp, "summary.json")
    args = ["-o", a.out, "--summary", "all", "--summary-file", summ] + defs(a)
    if ext == ".stl":
        args += ["--export-format", "asciistl" if a.ascii else "binstl"]
    backend = a.backend or ("manifold" if has_manifold() else None)
    if backend and has_manifold():
        args += ["--backend", backend]
    r = run_scad(args + [src], "OpenSCAD export")
    res = {"out": os.path.abspath(a.out), "bytes": os.path.getsize(a.out), "backend": backend or "cgal (old OpenSCAD)",
           "seconds": r["seconds"], "echo": r["echo"], "warnings": r["warnings"]}
    if os.path.isfile(summ):
        g = json.load(open(summ)).get("geometry", {})
        res["bbox_mm"] = g.get("bounding_box"); res["facets"] = g.get("facets")
    if ext == ".stl":
        res["stl"] = stl_stats(a.out)
        if not res["stl"].get("triangles"):
            die("the STL is empty: the model produced no 3D geometry (2D only? everything subtracted?)", 1)
    if a.png:
        res["png"] = {"path": os.path.abspath(a.png), **run_scad(png_args(a, a.png) + defs(a) + [src], "OpenSCAD PNG")}
    if a.sheet:
        if ext != ".stl": die("--sheet needs -o something.stl")
        look = [sys.executable, os.path.join(HERE, "look.py"), a.out, "-o", a.sheet, "--import-scale", "0.001",
                "--size", str(a.sheet_size), "--margin", "1.0"]
        p = subprocess.run(look, capture_output=True, text=True)
        if p.returncode != 0: die("bct look on the STL failed:\n" + p.stderr.strip()[-1200:], 1)
        res["sheet"] = json.loads(p.stdout)
    shutil.rmtree(tmp, ignore_errors=True)
    emit(res)


def cmd_png(a):
    r = run_scad(png_args(a, a.out) + defs(a) + [os.path.abspath(a.model)], "OpenSCAD PNG")
    emit({"png": os.path.abspath(a.out), **r})


def cmd_params(a):
    tmp = tempfile.mkdtemp(prefix="bct_scad_"); out = os.path.join(tmp, "p.param")
    run_scad(["-o", out, os.path.abspath(a.model)], "OpenSCAD parameter export")
    d = json.load(open(out)) if os.path.isfile(out) else {}
    shutil.rmtree(tmp, ignore_errors=True)
    emit({"model": os.path.abspath(a.model), "parameters": d.get("parameters", [])})


def main(argv=None):
    ap = argparse.ArgumentParser(prog="bct scad", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("render", "png"):
        p = sub.add_parser(name); p.add_argument("model"); p.add_argument("-o", "--out", required=True)
        p.add_argument("-D", action="append"); p.add_argument("-S", action="append")
        p.add_argument("--size", default="800x600"); p.add_argument("--camera")
        p.add_argument("--colorscheme", default="Tomorrow"); p.add_argument("--fast", action="store_true")
        if name == "render":
            p.add_argument("--png"); p.add_argument("--sheet"); p.add_argument("--sheet-size", type=int, default=320)
            p.add_argument("--backend", choices=["manifold", "cgal"]); p.add_argument("--ascii", action="store_true")
    q = sub.add_parser("params"); q.add_argument("model")
    a = ap.parse_args(argv)
    if not os.path.isfile(a.model): die(f"not found: {a.model}")
    {"render": cmd_render, "png": cmd_png, "params": cmd_params}[a.cmd](a)


if __name__ == "__main__":
    main()
