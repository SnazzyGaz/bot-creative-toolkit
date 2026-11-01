"""bct look: render a .blend file or a Python scene script from several angles into one labelled contact sheet.

  bct look MODEL.blend|scene.py|mesh.stl|.obj|.ply|.glb [-o sheet.png] [--views front,right,top,three_quarter] [--size 320]
           [--samples 16] [--engine cycles|eevee|workbench] [--clay] [--ortho] [--lights auto|studio|scene]
           [--save-blend built.blend] [--qa] [--qa-args "--category chair"] [--keep] [--margin 1.08]
           [--import-scale 0.001]   (meshes: e.g. OpenSCAD STL in mm -> metres)
           [--orbit N --frames-dir DIR [--orbit-elev 0.35]]   (turntable frames, no sheet; used by bct video)

Prints JSON: sheet path, tile paths, object names, size in metres, timings, and model-qa results if --qa.
"""
import argparse, json, os, shlex, shutil, subprocess, sys, tempfile, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import die, emit, find_blender, load_font

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_VIEWS = "front,right,top,three_quarter"


def find_model_qa():
    env = os.environ.get("MODEL_QA")
    if env and os.path.isfile(env):
        return env
    return shutil.which("model-qa")


def contact_sheet(tiles, out, title, cols=None):
    from PIL import Image, ImageDraw
    ims = [Image.open(t["path"]).convert("RGB") for t in tiles]
    w, h = ims[0].size
    n = len(ims)
    cols = cols or (2 if n == 4 else min(n, 3))
    rows = (n + cols - 1) // cols
    lab = max(18, w // 14)
    head = lab + 6
    sheet = Image.new("RGB", (cols * w, head + rows * (h + lab)), (24, 24, 24))
    d = ImageDraw.Draw(sheet)
    f = load_font(None, int(lab * 0.7))
    d.text((6, 3), title, fill=(235, 235, 235), font=f)
    for i, (im, t) in enumerate(zip(ims, tiles)):
        x, y = (i % cols) * w, head + (i // cols) * (h + lab)
        d.rectangle([x, y, x + w - 1, y + lab - 1], fill=(45, 45, 45))
        d.text((x + 6, y + 2), t["view"].replace("_", " "), fill=(255, 210, 90), font=f)
        sheet.paste(im, (x, y + lab))
        d.rectangle([x, y, x + w - 1, y + lab + h - 1], outline=(70, 70, 70))
    sheet.save(out)
    return sheet.size


def main(argv=None):
    ap = argparse.ArgumentParser(prog="bct look", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("model")
    ap.add_argument("-o", "--out", default=None, help="contact sheet PNG (default: <model>_sheet.png)")
    ap.add_argument("--views", default=DEFAULT_VIEWS,
                    help="comma list from front,back,right(side),left,top,bottom,three_quarter,three_quarter_back")
    ap.add_argument("--size", type=int, default=320, help="tile size in pixels (default 320)")
    ap.add_argument("--samples", type=int, default=16)
    ap.add_argument("--engine", default="cycles", choices=["cycles", "eevee", "workbench"])
    ap.add_argument("--clay", action="store_true", help="grey clay material on everything")
    ap.add_argument("--ortho", action="store_true", help="orthographic cameras")
    ap.add_argument("--lights", default="auto", choices=["auto", "studio", "scene"],
                    help="auto: add 3 lights only if the scene has none")
    ap.add_argument("--cols", type=int, default=None)
    ap.add_argument("--save-blend", default=None, help="for .py input: also save the built scene here")
    ap.add_argument("--qa", action="store_true", help="also run `model-qa check --look` if model-qa is installed")
    ap.add_argument("--qa-args", default="", help="extra model-qa flags, e.g. \"--category chair --profile render\"")
    ap.add_argument("--keep", action="store_true", help="keep the single-view tiles next to the sheet")
    ap.add_argument("--timeout", type=int, default=600)
    ap.add_argument("--margin", type=float, default=1.08, help="framing: 1.0 = bounding sphere just fits")
    ap.add_argument("--import-scale", type=float, default=1.0, help="scale for imported meshes (0.001: mm to m)")
    ap.add_argument("--orbit", type=int, default=0, help="render N turntable frames instead of the views")
    ap.add_argument("--orbit-elev", type=float, default=0.35)
    ap.add_argument("--frames-dir", default=None, help="with --orbit: where the frames go")
    a = ap.parse_args(argv)

    model = os.path.abspath(a.model)
    if not os.path.isfile(model):
        die(f"not found: {a.model}")
    ext = os.path.splitext(model)[1].lower()
    MESH = (".stl", ".obj", ".ply", ".glb", ".gltf")
    if ext not in (".blend", ".py") + MESH:
        die("model must be a .blend file, a .py script that builds the scene with bpy, or a mesh (" + " ".join(MESH) + ")")
    views = [v.strip() for v in a.views.split(",") if v.strip()]
    known = {"front", "back", "right", "side", "left", "top", "bottom", "three_quarter", "three_quarter_back"}
    bad = [v for v in views if v not in known]
    if bad:
        die(f"unknown view(s): {', '.join(bad)}")
    blender = find_blender()
    if not blender:
        die("Blender not found. Run setup.sh, or set BLENDER=/path/to/blender")

    out = os.path.abspath(a.out or os.path.splitext(model)[0] + "_sheet.png")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    work = (os.path.splitext(out)[0] + "_tiles") if a.keep else tempfile.mkdtemp(prefix="bct_look_")
    if a.orbit:
        if not a.frames_dir:
            die("--orbit needs --frames-dir")
        work = os.path.abspath(a.frames_dir); a.keep = True
    save_blend = a.save_blend
    if ext != ".blend" and a.qa and not save_blend:
        save_blend = os.path.join(work if a.keep else tempfile.mkdtemp(prefix="bct_qa_"), "scene.blend")
    cfg = {"outdir": work, "views": views, "size": a.size, "samples": a.samples, "engine": a.engine,
           "clay": a.clay, "ortho": a.ortho, "lights": a.lights,
           "script": model if ext == ".py" else None,
           "import": model if ext in MESH else None, "import_scale": a.import_scale,
           "margin": a.margin, "orbit": a.orbit, "orbit_elev": a.orbit_elev,
           "save_blend": os.path.abspath(save_blend) if save_blend else None}
    cmd = [blender, "-b", "--factory-startup"] + ([model] if ext == ".blend" else []) + \
          ["--python-exit-code", "1", "-P", os.path.join(HERE, "look_blender.py"), "--", json.dumps(cfg)]
    t0 = time.time()
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=a.timeout)
    except subprocess.TimeoutExpired:
        die(f"Blender timed out after {a.timeout}s (try a smaller --size or fewer --samples)")
    info_path = os.path.join(work, "info.json")
    if p.returncode != 0 or not os.path.isfile(info_path):
        tail = "\n".join((p.stdout + p.stderr).strip().splitlines()[-15:])
        die(f"Blender failed (exit {p.returncode}):\n{tail}")
    info = json.load(open(info_path))
    render_s = round(time.time() - t0, 1)
    if a.orbit:
        emit({"frames_dir": work, "frames": [t["path"] for t in info["tiles"]], "objects": info["objects"],
              "triangles": info["triangles"], "size_m": info["size_m"], "render_seconds": render_s})
        return
    sx, sy, sz = info["size_m"]
    title = f"{os.path.basename(model)}  |  {len(info['objects'])} obj  {info['triangles']} tris  {sx:g} x {sy:g} x {sz:g} m"
    sheet_size = contact_sheet(info["tiles"], out, title, a.cols)
    res = {"sheet": out, "sheet_px": list(sheet_size), "views": views, "objects": info["objects"],
           "triangles": info["triangles"], "size_m": info["size_m"], "engine": a.engine,
           "render_seconds": render_s}
    if a.keep:
        res["tiles"] = [t["path"] for t in info["tiles"]]
    else:
        shutil.rmtree(work, ignore_errors=True)
    if save_blend and (a.save_blend or a.keep):
        res["saved_blend"] = cfg["save_blend"]

    if a.qa:
        mqa = find_model_qa()
        if not mqa:
            res["model_qa"] = {"skipped": "model-qa not installed (pip install it from github.com/SnazzyGaz/model-qa, or set MODEL_QA)"}
        else:
            target = cfg["save_blend"] if ext != ".blend" else model
            qa_out = os.path.splitext(out)[0] + "_qa"
            qcmd = [mqa, "check", target, "--look", "--brief", "-o", qa_out] + shlex.split(a.qa_args)
            try:
                q = subprocess.run(qcmd, capture_output=True, text=True, timeout=a.timeout)
                rep = os.path.join(qa_out, "report.json")
                res["model_qa"] = {"exit_code": q.returncode, "verdict_text": q.stdout.strip()[-3000:],
                                   "outdir": qa_out, "report": rep if os.path.isfile(rep) else None,
                                   "beauty": os.path.join(qa_out, "beauty.png") if os.path.isfile(os.path.join(qa_out, "beauty.png")) else None,
                                   "meaning": {0: "pass/warn", 1: "high-severity issues", 2: "error"}.get(q.returncode, "?")}
            except subprocess.TimeoutExpired:
                res["model_qa"] = {"error": "model-qa timed out"}
    emit(res)


if __name__ == "__main__":
    main()
