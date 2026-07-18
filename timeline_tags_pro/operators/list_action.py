"""List action operator (ADD/REMOVE/UP/DOWN)."""
import bpy
from bpy.types import Operator
from bpy.props import StringProperty

from ..core.serialize import save_runtime_data_immediate
from ..core.sync import sync_content_to_lines


class TTAG_OT_List_Action(Operator):
    bl_idname = "ttag.list_action"
    bl_label = "List Action"
    bl_description = "列表操作"
    bl_options = {'REGISTER', 'UNDO'}
    action: StringProperty(default="ADD")

    def execute(self, context):
        scene = context.scene
        if not scene.ttag_source_text:
            self.report({'ERROR'}, "请先选择或新建一个 Text 数据块")
            return {'CANCELLED'}

        items = scene.ttag_runtime_items
        list_len = len(items)
        idx = scene.ttag_active_item_index

        scene.ttag_lock_sync = True
        try:
            if self.action == "ADD":
                new_frame = scene.frame_current
                item = items.add()
                item.frame = new_frame

                base_name = f"F_{new_frame}"
                existing_names = {it.summary for it in items if it != item}
                unique_name = base_name
                counter = 1
                while unique_name in existing_names:
                    unique_name = f"{base_name}_{counter}"
                    counter += 1

                item.summary = unique_name
                item.color = scene.ttag_default_color
                item.content = ""
                sync_content_to_lines(item)

                new_index = len(items) - 1
                for i in range(len(items) - 1):
                    if items[i].frame > new_frame:
                        new_index = i
                        break

                if new_index < len(items) - 1:
                    items.move(len(items) - 1, new_index)

                scene.ttag_active_item_index = new_index

            elif self.action == "REMOVE":
                if list_len > 0:
                    items.remove(idx)
                    scene.ttag_active_item_index = max(0, idx - 1)
            elif self.action == "UP":
                if idx > 0:
                    items.move(idx, idx - 1)
                    scene.ttag_active_item_index -= 1
            elif self.action == "DOWN":
                if idx < list_len - 1:
                    items.move(idx, idx + 1)
                    scene.ttag_active_item_index += 1

            save_runtime_data_immediate(scene)
        finally:
            scene.ttag_lock_sync = False
        return {'FINISHED'}
