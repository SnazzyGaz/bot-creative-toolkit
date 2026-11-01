# Toy rocket v3: fixes from the bct look sheet + model-qa report
import bpy, bmesh, math

def mat(name, col, rough=0.4, metal=0.0):
    m = bpy.data.materials.new(name); m.use_nodes = True
    p = m.node_tree.nodes["Principled BSDF"]
    p.inputs["Base Color"].default_value = col; p.inputs["Roughness"].default_value = rough
    p.inputs["Metallic"].default_value = metal
    return m

def smooth(o, angle=40):
    bpy.ops.object.select_all(action="DESELECT"); o.select_set(True); bpy.context.view_layer.objects.active = o
    bpy.ops.object.shade_smooth_by_angle(angle=math.radians(angle))

def bevel(o, w=0.015):
    m = o.modifiers.new("Bevel", "BEVEL"); m.width = w; m.segments = 2; m.limit_method = "ANGLE"

white = mat("White", (0.9, 0.9, 0.88, 1)); red = mat("Red", (0.8, 0.08, 0.05, 1))
glass = mat("Glass", (0.2, 0.5, 0.9, 1), 0.05); grey = mat("Grey", (0.3, 0.3, 0.32, 1), 0.3, 1.0)

# body: a lathe profile (slight taper) so body and nose are one smooth shell
prof = [(0.0, 0.4), (0.42, 0.4), (0.5, 0.7), (0.5, 2.2), (0.46, 2.6), (0.0, 2.6)]
bm = bmesh.new(); seg = 48
rings = []
for r, z in prof:
    rings.append([bm.verts.new((r * math.cos(2 * math.pi * k / seg), r * math.sin(2 * math.pi * k / seg), z)) for k in range(seg)])
for a, b in zip(rings, rings[1:]):
    for k in range(seg):
        bm.faces.new((a[k], a[(k + 1) % seg], b[(k + 1) % seg], b[k]))
bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-5)
bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
me = bpy.data.meshes.new("Body"); bm.to_mesh(me); bm.free()
body = bpy.data.objects.new("Body", me); bpy.context.scene.collection.objects.link(body)
body.data.materials.append(white); smooth(body)

# nose cone sits on the body top (z 2.6), same radius as the shoulder
bpy.ops.mesh.primitive_cone_add(radius1=0.46, radius2=0, depth=0.9, location=(0, 0, 3.05), vertices=48)
nose = bpy.context.object; nose.name = "Nose"; nose.data.materials.append(red); smooth(nose)

# window: glass disc in a grey frame ring, sitting on the surface at the front (-Y)
bpy.ops.mesh.primitive_cylinder_add(radius=0.2, depth=0.06, vertices=32, location=(0, -0.5, 1.75), rotation=(math.radians(90), 0, 0))
frame = bpy.context.object; frame.name = "WindowFrame"; frame.data.materials.append(grey); smooth(frame); bevel(frame, 0.01)
bpy.ops.mesh.primitive_cylinder_add(radius=0.15, depth=0.08, vertices=32, location=(0, -0.5, 1.75), rotation=(math.radians(90), 0, 0))
win = bpy.context.object; win.name = "Window"; win.data.materials.append(glass); smooth(win)

# fins: swept trapezoids built at real size (no object scale), roots buried 2 cm in the body
for i in range(3):
    a = math.radians(90) + i * 2 * math.pi / 3
    root_in, tip = 0.48, 1.0
    pts = [(root_in, 0.35), (root_in, 1.15), (tip, 0.55), (tip, 0.09)]   # tip reaches the ground
    t = 0.035
    v = [(x, -t, z) for x, z in pts] + [(x, t, z) for x, z in pts]
    f = [(0, 1, 2, 3), (7, 6, 5, 4), (0, 4, 5, 1), (1, 5, 6, 2), (2, 6, 7, 3), (3, 7, 4, 0)]
    me = bpy.data.meshes.new(f"Fin{i}"); me.from_pydata(v, [], f)
    bm = bmesh.new(); bm.from_mesh(me); bmesh.ops.recalc_face_normals(bm, faces=bm.faces); bm.to_mesh(me); bm.free()
    fin = bpy.data.objects.new(f"Fin{i}", me); bpy.context.scene.collection.objects.link(fin)
    fin.rotation_euler = (0, 0, a); fin.data.materials.append(red); bevel(fin, 0.01)

# nozzle under the body, top just inside the base
bpy.ops.mesh.primitive_cone_add(radius1=0.36, radius2=0.26, depth=0.32, location=(0, 0, 0.25), vertices=48)
noz = bpy.context.object; noz.name = "Nozzle"; noz.data.materials.append(grey); smooth(noz); bevel(noz, 0.01)
