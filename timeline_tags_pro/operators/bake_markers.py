"""Bake timeline markers operator - V46.0 marker name conflict fix."""
import bpy
from bpy.types import Operator

from ..core.serialize import save_runtime_data_immediate


class TTAG_OT_Bake_Timeline_Markers(Operator):
    bl_idname = "ttag.bake_timeline_markers"
    bl_label = "添加时间轴标签"
    bl_description = "生成/更新时间轴标记"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        scene = context.scene
        items = scene.ttag_runtime_items
        if len(items) == 0:
            return {'CANCELLED'}

        save_runtime_data_immediate(scene)

        # Timeline marker handling
        if scene.ttag_overwrite_markers:
            scene.timeline_markers.clear()
            occupied_frames = set()
            occupied_names = set()
        else:
            occupied_frames = {m.frame for m in scene.timeline_markers}
            occupied_names = {m.name for m in scene.timeline_markers}

        sorted_items = sorted(items, key=lambda x: x.frame)
        for item in sorted_items:
            base_name = item.summary if item.summary else f"F_{item.frame}"
            m_frame = item.frame

            if not scene.ttag_overwrite_markers:
                while m_frame in occupied_frames:
                    m_frame += 1

            # V46.0 fix: self-generated unique marker name (.001/.002 rule)
            # instead of relying on Blender's automatic suffix addition.
            unique_name = base_name
            counter = 1
            while unique_name in occupied_names:
                unique_name = f"{base_name}.{counter:03d}"
                counter += 1

            try:
                scene.timeline_markers.new(name=unique_name, frame=m_frame)
                occupied_frames.add(m_frame)
                occupied_names.add(unique_name)
            except Exception as e:
                print(f"Failed to add marker at {m_frame}: {e}")

        self.report({'INFO'}, "时间轴标记已添加")
        return {'FINISHED'}
