"""Insert / newline / remove text line operators."""
import bpy
from bpy.types import Operator

from ..core.serialize import save_runtime_data_immediate
from ..core.sync import sync_content_to_lines


class TTAG_OT_Insert_Top_Line(Operator):
    bl_idname = "ttag.insert_top_line"
    bl_label = "顶部插入行"
    bl_description = "在当前激活标签的文本最上方插入一个新行"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        scene = context.scene
        items = scene.ttag_runtime_items
        idx = scene.ttag_active_item_index
        if not (0 <= idx < len(items)):
            return {'CANCELLED'}
        item = items[idx]
        new_line = item.text_lines.add()
        # Move new line to top (index 0)
        last_idx = len(item.text_lines) - 1
        if last_idx > 0:
            item.text_lines.move(last_idx, 0)
        save_runtime_data_immediate(scene)
        return {'FINISHED'}


class TTAG_OT_Insert_Newline(Operator):
    bl_idname = "ttag.insert_newline"
    bl_label = "插入换行"
    bl_description = "在当前激活标签的文本末尾插入一个新行"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        scene = context.scene
        items = scene.ttag_runtime_items
        idx = scene.ttag_active_item_index
        if not (0 <= idx < len(items)):
            return {'CANCELLED'}
        item = items[idx]
        item.text_lines.add()
        save_runtime_data_immediate(scene)
        return {'FINISHED'}


class TTAG_OT_Remove_Text_Line(Operator):
    bl_idname = "ttag.remove_text_line"
    bl_label = "删除该行"
    bl_description = "删除当前激活标签中选定的行"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        scene = context.scene
        items = scene.ttag_runtime_items
        idx = scene.ttag_active_item_index
        if not (0 <= idx < len(items)):
            return {'CANCELLED'}
        item = items[idx]
        if len(item.text_lines) > 1:
            # Remove the last line for simplicity (UI may refine)
            item.text_lines.remove(len(item.text_lines) - 1)
            save_runtime_data_immediate(scene)
        return {'FINISHED'}
