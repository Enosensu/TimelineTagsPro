"""Clipboard copy / paste operators."""
import bpy
from bpy.types import Operator

from ..core.serialize import save_runtime_data_immediate
from ..core.sync import sync_content_to_lines


class TTAG_OT_Copy_Clipboard(Operator):
    bl_idname = "ttag.copy_clipboard"
    bl_label = "复制内容"
    bl_description = "将当前激活标签的内容复制到系统剪贴板"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        scene = context.scene
        items = scene.ttag_runtime_items
        idx = scene.ttag_active_item_index
        if not (0 <= idx < len(items)):
            return {'CANCELLED'}
        item = items[idx]
        from ..core.sync import sync_lines_to_content
        sync_lines_to_content(item)
        context.window_manager.clipboard = item.content
        return {'FINISHED'}


class TTAG_OT_Paste_Clipboard(Operator):
    bl_idname = "ttag.paste_clipboard"
    bl_label = "粘贴内容"
    bl_description = "将系统剪贴板的内容粘贴到当前激活标签"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        scene = context.scene
        items = scene.ttag_runtime_items
        idx = scene.ttag_active_item_index
        if not (0 <= idx < len(items)):
            return {'CANCELLED'}
        item = items[idx]
        item.content = context.window_manager.clipboard
        sync_content_to_lines(item)
        save_runtime_data_immediate(scene)
        return {'FINISHED'}
