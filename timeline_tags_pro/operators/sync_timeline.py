"""Sync from timeline operator (manual reload driven by current frame)."""
import bpy
from bpy.types import Operator


class TTAG_OT_Sync_From_Timeline(Operator):
    bl_idname = "ttag.sync_from_timeline"
    bl_label = "同步当前帧"
    bl_description = "根据当前时间轴帧数跳转到对应标签"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        scene = context.scene
        items = scene.ttag_runtime_items
        if len(items) == 0:
            return {'CANCELLED'}

        curr = scene.frame_current
        best_idx = -1
        max_frame = -999999
        for i, item in enumerate(items):
            if item.frame <= curr and item.frame > max_frame:
                max_frame = item.frame
                best_idx = i

        if best_idx != -1:
            scene.ttag_active_item_index = best_idx

        return {'FINISHED'}
