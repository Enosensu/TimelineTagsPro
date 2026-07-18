"""Main sidebar panel - matches original TimelineTagsPro.py V45.0 layout."""
import bpy
from bpy.types import Panel


class TTAG_PT_Panel(Panel):
    bl_label = "Timeline Tags Pro V46.0"
    bl_idname = "TTAG_PT_main"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Tags Pro"

    def draw(self, context):
        layout = self.layout
        scene = context.scene

        # --- 1. Native Data Block Manager ---
        # 使用 Blender 原生 template_ID 控件（最大化利用内置文本选择器/新建/打开）
        box = layout.box()
        row = box.row(align=True)
        row.template_ID(scene, "ttag_source_text",
                        new="text.new", open="text.open")

        if scene.ttag_source_text:
            row.operator("ttag.reload_from_text", text="", icon='FILE_REFRESH')

        if not scene.ttag_source_text:
            box.label(text="请选择或新建 Text 数据块", icon='INFO')
            return

        layout.separator()

        # --- 2. Global Settings ---
        row = layout.row(align=True)
        row.label(text="标签 (Tags):", icon='TAG')

        sub = row.row(align=True)
        sub.alignment = 'RIGHT'
        sub.prop(scene, "ttag_default_color", text="")
        sub.prop(scene, "ttag_live_sync", text="", icon='TIME', toggle=True)

        # --- 3. Data List ---
        row = layout.row()
        row.template_list("TTAG_UL_List", "",
                          scene, "ttag_runtime_items",
                          scene, "ttag_active_item_index")

        col = row.column(align=True)
        col.operator("ttag.sort_by_frame", text="", icon='SORT_ASC')

        # 按帧重命名按钮
        col.operator("ttag.rename_by_frame", text="", icon='TEXT')

        col.separator()
        col.operator("ttag.list_action", icon='ADD', text="").action = "ADD"
        col.operator("ttag.list_action", icon='REMOVE', text="").action = "REMOVE"
        col.separator()
        col.operator("ttag.list_action", icon='TRIA_UP', text="").action = "UP"
        col.operator("ttag.list_action", icon='TRIA_DOWN', text="").action = "DOWN"

        layout.separator()

        # --- 4. Edit Area ---
        if scene.ttag_active_item_index >= 0 and len(scene.ttag_runtime_items) > 0:
            safe_idx = scene.ttag_active_item_index
            if safe_idx >= len(scene.ttag_runtime_items):
                safe_idx = len(scene.ttag_runtime_items) - 1
            if safe_idx < 0:
                safe_idx = 0

            item = scene.ttag_runtime_items[safe_idx]
            box = layout.box()
            col = box.column(align=True)

            # 标题栏新增行数控制
            row_header = col.row(align=True)
            row_header.label(text="内容编辑 (Content Edit):", icon='TEXT')
            row_header.prop(item, "line_count", text="行数")

            row_tools = col.row(align=True)
            row_tools.scale_y = 1.2
            row_tools.operator("ttag.copy_clipboard", text="复制", icon='COPYDOWN')
            row_tools.operator("ttag.paste_clipboard", text="粘贴", icon='PASTEDOWN')

            # 新增：置顶插入空行按钮
            row_tools.operator("ttag.insert_top_line", text="", icon='ADD')

            col.separator()

            if len(item.text_lines) == 0:
                col.label(text="无文本", icon='ERROR')
            else:
                for idx, line in enumerate(item.text_lines):
                    row_line = col.row(align=True)
                    row_line.prop(line, "body", text="")
                    op_add = row_line.operator("ttag.insert_newline", text="", icon='ADD')
                    op_add.target_index = idx
                    op_del = row_line.operator("ttag.remove_text_line", text="", icon='X')
                    op_del.index = idx

        layout.separator()

        # --- 5. Output Area ---
        box = layout.box()
        box.label(text="输出 (Output):", icon='OUTPUT')

        # Row 1
        row = box.row(align=True)
        row.scale_y = 1.2
        row.operator("ttag.export_srt", icon='TEXT', text="导出 SRT")
        row.operator("ttag.import_srt", icon='IMPORT', text="导入 SRT")

        # Row 2
        row = box.row(align=True)
        sub = row.split(factor=0.60, align=True)
        sub.prop(scene, "ttag_font_path", text="")
        sub_right = sub.row(align=True)
        sub_right.prop(scene, "ttag_line_spacing", text="行距")

        sub_right.prop(scene, "ttag_overwrite", text="", icon='FILE_REFRESH', toggle=True)
        sub_right.prop(scene, "ttag_global_align", text="", expand=True)
        sub_right.prop(scene, "ttag_overwrite_markers", text="", icon='MARKER', toggle=True)

        # Row 3: 烘焙 3D 文字独占一行
        row_bake = box.row(align=True)
        row_bake.scale_y = 1.2
        row_bake.operator("ttag.bake_3d_text", icon='SHADING_BBOX', text="烘焙 3D 文字")

        # Row 4: 时间轴同步
        row_sync = box.row(align=True)
        row_sync.scale_y = 1.2
        row_sync.operator("ttag.bake_timeline_markers", icon='MARKER', text="添加时间轴标签")
        row_sync.operator("ttag.sync_from_timeline", icon='FILE_REFRESH', text="从时间轴同步标签帧")
