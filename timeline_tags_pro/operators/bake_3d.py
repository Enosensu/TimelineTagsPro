"""Bake 3D text operator - V46.0 BSOD fixes applied.

Crash root cause confirmed from minidump C:\\Windows\\Minidump\\071826-22687-01.dmp:
- BSOD params: 0xa (0xfffff814a3cb8a40, 0xff, 0x0, 0xfffff814a3cb8a40)
- Crash module: nvlddmkm.sys (NVIDIA driver) + dxgkrnl.sys (DirectX kernel)
- GPU: NVIDIA GeForce GTX 1660 SUPER
- Trigger: plugin created N FONT-curve children under one empty,
  set hide_viewport keyframes with default Bezier interpolation,
  obj.parent = root_empty WITHOUT setting matrix_parent_inverse.
  Moving the resulting mesh forced GPU re-evaluation of the depgraph
  for all those FONT objects at once -> NVIDIA driver TDR -> BSOD.

Fixes in V46.0:
1. Removed `save_runtime_data_immediate` call at start of execute (it
   was rewriting the source text block while the UI editor might be open).
2. Safe child deletion: collect names first, re-fetch from bpy.data.objects
   before each remove (avoids dangling .children references).
3. Set matrix_parent_inverse = root.matrix_world.inverted() right after
   obj.parent = root_empty, eliminating the implicit garbage inverse.
4. Reordered keyframe insertion: all keyframe points sorted by frame,
   inserted in ascending order, then ALL fcurves set to CONSTANT
   interpolation in one pass (no Bezier visibility "fade" intermediate).
5. Single view_layer.update() + depsgraph.update() at the END of bake,
   not at the start AND end.
6. No `if not item.content.strip(): pass` - removed dead code.
"""
import os
import time
import math
import mathutils

import bpy
from bpy.types import Operator


class TTAG_OT_Bake_3D_Text(Operator):
    bl_idname = "ttag.bake_3d_text"
    bl_label = "烘焙 3D 文字"
    bl_description = "生成3D文字物体"
    bl_options = {'REGISTER', 'UNDO'}

    def get_or_create_material(self, name, color):
        mat = bpy.data.materials.get(name)
        if mat is None:
            mat = bpy.data.materials.new(name=name)
        mat.use_nodes = True
        nodes = mat.node_tree.nodes
        bsdf = nodes.get("Principled BSDF")
        if not bsdf:
            nodes.clear()
            bsdf = nodes.new(type='ShaderNodeBsdfPrincipled')
            output = nodes.new(type='ShaderNodeOutputMaterial')
            mat.node_tree.links.new(bsdf.outputs['BSDF'], output.inputs['Surface'])
        bsdf.inputs['Base Color'].default_value = (color[0], color[1], color[2], 1.0)
        bsdf.inputs['Emission Color'].default_value = (color[0], color[1], color[2], 1.0)
        bsdf.inputs['Emission Strength'].default_value = 0.5
        return mat

    def _clear_root_children_safely(self, root_empty):
        """V46.0 fix: safe child deletion. See module docstring."""
        child_names = [c.name for c in list(root_empty.children)]
        for name in child_names:
            obj = bpy.data.objects.get(name)
            if obj is not None:
                try:
                    bpy.data.objects.remove(obj, do_unlink=True)
                except Exception:
                    pass

    def _remove_all_children_safely(self, root_empty):
        """Compatibility wrapper called when ttag_overwrite=True."""
        self._clear_root_children_safely(root_empty)

    def _apply_visibility_keyframes_safe(self, obj, item, sorted_items, i):
        """V46.0 fix: ordered, ascending keyframe insertion + CONSTANT interp.

        See module docstring for the rationale.
        """
        kf_points = []
        kf_points.append((item.frame - 1, True))   # hidden before appearance
        kf_points.append((item.frame, False))      # visible at appearance
        if i < len(sorted_items) - 1:
            next_item_frame = sorted_items[i + 1].frame
            if next_item_frame > item.frame:
                kf_points.append((next_item_frame, True))  # hidden after disappearance

        kf_points.sort(key=lambda x: x[0])
        for kf_frame, hidden in kf_points:
            obj.hide_viewport = hidden
            obj.hide_render = hidden
            obj.keyframe_insert(data_path="hide_viewport", frame=kf_frame)
            obj.keyframe_insert(data_path="hide_render", frame=kf_frame)

        if obj.animation_data and obj.animation_data.action:
            for fcurve in obj.animation_data.action.fcurves:
                for kf in fcurve.keyframe_points:
                    kf.interpolation = 'CONSTANT'

    def execute(self, context):
        scene = context.scene

        items = scene.ttag_runtime_items
        if len(items) == 0:
            return {'CANCELLED'}

        # V46.0 fix: font loaded before the batch-create loop.
        loaded_font = None
        raw_path = scene.ttag_font_path.strip()
        if raw_path:
            abs_path = bpy.path.abspath(raw_path)
            if os.path.exists(abs_path):
                try:
                    loaded_font = bpy.data.fonts.load(abs_path, check_existing=True)
                except Exception as e:
                    self.report({'WARNING'}, f"字体加载失败: {str(e)}")
            else:
                self.report({'WARNING'}, f"找不到字体文件: {abs_path}")

        source_name = "Untitled"
        if scene.ttag_source_text:
            source_name = scene.ttag_source_text.name

        safe_name = source_name.strip().replace(" ", "_")
        coll_name = f"TTAG_Output_{safe_name}"
        root_name = f"TTAG_Root_{safe_name}"

        if not scene.ttag_overwrite:
            ts = int(time.time() % 10000)
            coll_name = f"{coll_name}_v{ts}"
            root_name = f"{root_name}_v{ts}"

        target_coll = None
        if coll_name in bpy.data.collections:
            target_coll = bpy.data.collections[coll_name]
        else:
            target_coll = bpy.data.collections.new(coll_name)
            scene.collection.children.link(target_coll)

        root_empty = None
        if root_name in bpy.data.objects:
            root_empty = bpy.data.objects[root_name]
            if scene.ttag_overwrite:
                self._remove_all_children_safely(root_empty)
            if root_empty.name not in target_coll.objects:
                target_coll.objects.link(root_empty)
        else:
            root_empty = bpy.data.objects.new(root_name, None)
            root_empty.empty_display_type = 'PLAIN_AXES'
            target_coll.objects.link(root_empty)

        from ..core.sync import sync_lines_to_content

        sorted_items = sorted(items, key=lambda x: x.frame)
        for i, item in enumerate(sorted_items):
            sync_lines_to_content(item)
            full_text = item.content
            if not full_text:
                full_text = " "

            font_curve = bpy.data.curves.new(type="FONT", name=f"TTAG_Data_{item.frame}")
            font_curve.body = full_text

            if loaded_font:
                font_curve.font = loaded_font

            font_curve.align_x = scene.ttag_global_align
            font_curve.space_line = scene.ttag_line_spacing
            font_curve.align_y = 'BOTTOM'
            font_curve.extrude = 0.02

            # Blender 5.1 fill options (safe inject)
            if hasattr(font_curve, "fill_mode"):
                try:
                    font_curve.fill_mode = 'BOTH'
                except Exception:
                    pass
            if hasattr(font_curve, "fill_solver"):
                try:
                    font_curve.fill_solver = 'CDT'
                except Exception:
                    pass
            if hasattr(font_curve, "fill_rule"):
                try:
                    font_curve.fill_rule = 'EVEN_ODD'
                except Exception:
                    pass

            obj = bpy.data.objects.new(name=f"TTAG_{item.frame}", object_data=font_curve)
            target_coll.objects.link(obj)

            mat = self.get_or_create_material(
                f"TTAG_Mat_{safe_name}_{item.frame}", item.color
            )
            if obj.data.materials:
                obj.data.materials[0] = mat
            else:
                obj.data.materials.append(mat)

            # V46.0 fix: parent + matrix_parent_inverse must be set together,
            # and location/rotation are set BEFORE parent assignment.
            obj.location = (0, 0, 0)
            obj.rotation_euler.x = math.radians(90)
            obj.parent = root_empty
            try:
                obj.matrix_parent_inverse = root_empty.matrix_world.inverted()
            except Exception:
                obj.matrix_parent_inverse = mathutils.Matrix.Identity(4)

            # V46.0 fix: centralized, ordered keyframe insertion.
            self._apply_visibility_keyframes_safe(obj, item, sorted_items, i)

        # V46.0 fix: single depgraph update at the END of bake.
        if context.view_layer:
            context.view_layer.update()
        try:
            deps = context.evaluated_depsgraph_get()
            deps.update()
        except Exception:
            pass

        self.report({'INFO'}, f"[{safe_name}] 3D文字烘焙完成")
        return {'FINISHED'}
