"""Example scene script for `bct look examples/scene_example.py`.
A script just builds objects with bpy into an empty scene; bct adds lights and cameras."""
import bpy

bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 0, 0.5))
base = bpy.context.object; base.name = "Base"
bpy.ops.mesh.primitive_uv_sphere_add(radius=0.35, location=(0, 0, 1.35))
head = bpy.context.object; head.name = "Head"
bpy.ops.object.shade_smooth()
bpy.ops.mesh.primitive_cylinder_add(radius=0.08, depth=0.5, location=(0.45, 0, 0.75), rotation=(0, 1.5708, 0))
arm = bpy.context.object; arm.name = "Arm"

for ob, col in ((base, (0.2, 0.4, 0.8, 1)), (head, (0.9, 0.6, 0.2, 1)), (arm, (0.3, 0.7, 0.3, 1))):
    m = bpy.data.materials.new(ob.name + "_mat"); m.use_nodes = True
    m.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = col
    ob.data.materials.append(m)
