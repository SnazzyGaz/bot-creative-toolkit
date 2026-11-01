"""Runs inside Blender (blender -b ... -P look_blender.py -- CONFIG_JSON).
Builds or loads the scene, frames it from each view and writes one PNG per view plus info.json."""
import bpy, json, math, os, sys, time
from mathutils import Vector

cfg = json.loads(sys.argv[sys.argv.index("--") + 1])
out = cfg["outdir"]
os.makedirs(out, exist_ok=True)
GEOM = {"MESH", "CURVE", "SURFACE", "META", "FONT", "CURVES", "POINTCLOUD", "VOLUME"}

# 1. scene: a .blend is already open; a .py script builds into an empty scene
if cfg.get("script"):
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob, do_unlink=True)
    code = open(cfg["script"]).read()
    exec(compile(code, cfg["script"], "exec"), {"__name__": "__main__", "__file__": cfg["script"]})
    if cfg.get("save_blend"):
        bpy.ops.wm.save_as_mainfile(filepath=cfg["save_blend"])

scene = bpy.context.scene
deps = bpy.context.evaluated_depsgraph_get()
objs = [o for o in scene.objects if o.type in GEOM and not o.hide_render and o.visible_get()]
if not objs:
    print("LOOK_ERROR: no visible geometry to render", file=sys.stderr)
    sys.exit(3)

lo = Vector((1e18,) * 3); hi = Vector((-1e18,) * 3); tris = 0
for o in objs:
    ev = o.evaluated_get(deps)
    for c in ev.bound_box:
        w = o.matrix_world @ Vector(c)
        lo = Vector(map(min, lo, w)); hi = Vector(map(max, hi, w))
    if o.type == "MESH":
        try:
            m = ev.to_mesh(); m.calc_loop_triangles(); tris += len(m.loop_triangles); ev.to_mesh_clear()
        except Exception:
            pass
center = (lo + hi) / 2
size = hi - lo
radius = max(size.length / 2, 1e-4)

# 2. lights and world (only added if the scene has none, unless told otherwise)
added = []
has_light = any(o.type == "LIGHT" and not o.hide_render for o in scene.objects)
if cfg.get("lights") == "studio" or (cfg.get("lights") == "auto" and not has_light):
    for name, rot, energy in (("key", (50, 0, -40), 4.0), ("fill", (60, 0, 130), 1.5), ("rim", (-60, 0, 0), 2.0)):
        ld = bpy.data.lights.new("bct_" + name, "SUN"); ld.energy = energy; ld.angle = math.radians(8)
        lo_ = bpy.data.objects.new("bct_" + name, ld); scene.collection.objects.link(lo_)
        lo_.rotation_euler = [math.radians(a) for a in rot]; added.append(lo_)
if scene.world is None:
    scene.world = bpy.data.worlds.new("bct_world")
if cfg.get("lights") != "scene" and not has_light:
    scene.world.use_nodes = True
    bg = scene.world.node_tree.nodes.get("Background")
    if bg:
        g = cfg.get("bg", 0.18)
        bg.inputs[0].default_value = (g, g, g, 1); bg.inputs[1].default_value = 1.0

if cfg.get("clay"):
    mat = bpy.data.materials.new("bct_clay"); mat.diffuse_color = (0.7, 0.7, 0.7, 1)
    mat.use_nodes = True
    p = mat.node_tree.nodes.get("Principled BSDF")
    if p:
        p.inputs["Base Color"].default_value = (0.7, 0.7, 0.7, 1); p.inputs["Roughness"].default_value = 0.6
    bpy.context.view_layer.material_override = mat

# 3. render settings (small and fast by default)
r = scene.render
eng = {"cycles": "CYCLES", "eevee": "BLENDER_EEVEE_NEXT", "workbench": "BLENDER_WORKBENCH"}[cfg["engine"]]
r.engine = eng
r.resolution_x = r.resolution_y = cfg["size"]; r.resolution_percentage = 100
r.film_transparent = False
r.image_settings.file_format = "PNG"; r.image_settings.color_mode = "RGB"
if eng == "CYCLES":
    scene.cycles.device = "CPU"; scene.cycles.samples = cfg["samples"]
    scene.cycles.use_adaptive_sampling = True
    try:
        scene.cycles.use_denoising = True; scene.cycles.denoiser = "OPENIMAGEDENOISE"
    except Exception:
        scene.cycles.use_denoising = False
elif eng == "BLENDER_EEVEE_NEXT":
    scene.eevee.taa_render_samples = cfg["samples"]

# 4. one camera, moved per view
VIEWS = {
    "front": (0, -1, 0), "back": (0, 1, 0), "right": (1, 0, 0), "side": (1, 0, 0), "left": (-1, 0, 0),
    "top": (0, 0, 1), "bottom": (0, 0, -1), "three_quarter": (1, -1, 0.8), "three_quarter_back": (-1, 1, 0.8),
}
cd = bpy.data.cameras.new("bct_cam"); cd.lens = 50; cd.sensor_width = 36
cd.clip_start = radius * 0.01; cd.clip_end = radius * 100
cam = bpy.data.objects.new("bct_cam", cd); scene.collection.objects.link(cam); scene.camera = cam
fov = 2 * math.atan(18 / 50)
dist = radius / math.sin(fov / 2) * cfg.get("margin", 1.08)
if cfg.get("ortho"):
    cd.type = "ORTHO"; cd.ortho_scale = radius * 2 * cfg.get("margin", 1.08)

tiles = []
for v in cfg["views"]:
    d = Vector(VIEWS[v]).normalized()
    cam.location = center + d * dist
    if v in ("top", "bottom"):
        cam.rotation_euler = (0, 0, 0) if v == "top" else (math.pi, 0, 0)
    else:
        cam.rotation_euler = (-d).to_track_quat("-Z", "Y").to_euler()
    r.filepath = os.path.join(out, v + ".png")
    t = time.time()
    bpy.ops.render.render(write_still=True)
    tiles.append({"view": v, "path": r.filepath, "seconds": round(time.time() - t, 2)})

info = {"objects": [o.name for o in objs], "triangles": tris,
        "size_m": [round(x, 4) for x in size], "center": [round(x, 4) for x in center],
        "engine": cfg["engine"], "tiles": tiles}
json.dump(info, open(os.path.join(out, "info.json"), "w"), indent=1)
