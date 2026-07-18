"""Sort by frame and rename-by-frame operators."""
import bpy
from bpy.types import Operator

from ..core.serialize import save_runtime_data_immediate


class TTAG_OT_Sort_By_Frame(Operator):
    bl_idname = "ttag.sort_by_frame"
    bl_label = "按帧排序"
    bl_description = "根据标签帧号从小到大重新排序列表"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        scene = context.scene
        items = scene.ttag_runtime_items
        n = len(items)
        if n == 0:
            return {'CANCELLED'}

        scene.ttag_lock_sync = True
        try:
            # Bubble-sort the CollectionProperty in place by frame.
            for i in range(n):
                for j in range(0, n - i - 1):
                    if items[j].frame > items[j + 1].frame:
                        items.move(j, j + 1)
                        # After move(j, j+1), the element originally at j
                        # is now at j+1; swap is complete.
            save_runtime_data_immediate(scene)
        finally:
            scene.ttag_lock_sync = False

        return {'FINISHED'}


class TTAG_OT_Rename_By_Frame(Operator):
    bl_idname = "ttag.rename_by_frame"
    bl_label = "按帧号重命名"
    bl_description = "根据当前插件所在的帧数重新生成名称(F_xxx)，并同步修改对应时间轴标记的名称"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        scene = context.scene
        items = scene.ttag_runtime_items
        if len(items) == 0:
            return {'CANCELLED'}

        used_names = set()
        scene.ttag_lock_sync = True
        try:
            for item in items:
                old_name = item.summary if item.summary else f"F_{item.frame}"
                marker = scene.timeline_markers.get(old_name)

                base_name = f"F_{item.frame}"
                unique_name = base_name
                counter = 1
                while unique_name in used_names:
                    unique_name = f"{base_name}_{counter}"
                    counter += 1

                item.summary = unique_name

                if marker:
                    marker.name = unique_name

                used_names.add(unique_name)

            save_runtime_data_immediate(scene)
            self.report({'INFO'}, "已根据实际帧数重新规范所有标签及对应时间轴标记的名称")
        finally:
            scene.ttag_lock_sync = False

        return {'FINISHED'}
