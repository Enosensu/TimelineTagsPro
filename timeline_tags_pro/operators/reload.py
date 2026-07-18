"""Reload-from-text operator."""
import bpy
from bpy.types import Operator

from ..core.serialize import load_runtime_data


class TTAG_OT_Reload_From_Text(Operator):
    bl_idname = "ttag.reload_from_text"
    bl_label = "从文本重新加载"
    bl_description = "丢弃当前列表中的所有未保存修改，从源文本块重新加载数据"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        scene = context.scene
        load_runtime_data(scene, operator=self)
        return {'FINISHED'}
