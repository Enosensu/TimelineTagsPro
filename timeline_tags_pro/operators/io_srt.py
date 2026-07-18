"""SRT (SubRip) import / export operators."""
import bpy
from bpy.types import Operator
from bpy_extras.io_utils import ImportHelper, ExportHelper

from ..core.serialize import save_runtime_data_immediate
from ..core.sync import sync_content_to_lines
from ..props import frame_to_timecode, timecode_to_frame


class TTAG_OT_Export_SRT(Operator, ExportHelper):
    bl_idname = "ttag.export_srt"
    bl_label = "导出 SRT"
    bl_description = "将当前标签列表导出为 SRT 字幕文件"
    bl_options = {'REGISTER', 'UNDO'}

    filename_ext = ".srt"
    filter_glob: bpy.props.StringProperty(default="*.srt", options={'HIDDEN'})

    def execute(self, context):
        scene = context.scene
        items = scene.ttag_runtime_items
        if len(items) == 0:
            self.report({'WARNING'}, "没有标签可以导出")
            return {'CANCELLED'}

        fps = scene.render.fps
        sorted_items = sorted(items, key=lambda x: x.frame)

        srt_lines = []
        for i, item in enumerate(sorted_items, 1):
            from ..core.sync import sync_lines_to_content
            sync_lines_to_content(item)
            start_frame = item.frame
            end_frame = sorted_items[i].frame if i < len(sorted_items) else start_frame + 60
            srt_lines.append(str(i))
            srt_lines.append(
                f"{frame_to_timecode(start_frame, fps)} --> {frame_to_timecode(end_frame, fps)}"
            )
            srt_lines.append(item.content if item.content else item.summary)
            srt_lines.append("")  # blank line between entries

        try:
            with open(self.filepath, 'w', encoding='utf-8') as f:
                f.write("\n".join(srt_lines))
            self.report({'INFO'}, f"SRT 导出成功: {self.filepath}")
        except OSError as e:
            self.report({'ERROR'}, f"文件写入失败: {e}")
            return {'CANCELLED'}

        return {'FINISHED'}


class TTAG_OT_Import_SRT(Operator, ImportHelper):
    bl_idname = "ttag.import_srt"
    bl_label = "导入 SRT"
    bl_description = "从 SRT 字幕文件导入标签到当前列表"
    bl_options = {'REGISTER', 'UNDO'}

    filename_ext = ".srt"
    filter_glob: bpy.props.StringProperty(default="*.srt", options={'HIDDEN'})

    def execute(self, context):
        scene = context.scene
        if not scene.ttag_source_text:
            self.report({'ERROR'}, "请先选择或新建一个 Text 数据块")
            return {'CANCELLED'}

        fps = scene.render.fps

        try:
            with open(self.filepath, 'r', encoding='utf-8') as f:
                content = f.read()
        except OSError as e:
            self.report({'ERROR'}, f"文件读取失败: {e}")
            return {'CANCELLED'}

        # Parse SRT: index, time range, text lines, blank line
        blocks = content.strip().split("\n\n")
        imported_count = 0

        scene.ttag_lock_sync = True
        try:
            for block in blocks:
                lines = block.strip().split("\n")
                if len(lines) < 3:
                    continue
                # Time line is the second line: "HH:MM:SS,mmm --> HH:MM:SS,mmm"
                time_line = lines[1]
                if " --> " not in time_line:
                    continue
                start_tc = time_line.split(" --> ")[0].replace(",", ".")
                try:
                    start_frame = timecode_to_frame(start_tc, fps)
                except Exception:
                    continue
                text_body = "\n".join(lines[2:])

                item = scene.ttag_runtime_items.add()
                item.frame = start_frame
                item.summary = f"F_{start_frame}"
                item.content = text_body
                item.color = scene.ttag_default_color
                sync_content_to_lines(item)
                imported_count += 1

            save_runtime_data_immediate(scene)
        finally:
            scene.ttag_lock_sync = False

        self.report({'INFO'}, f"SRT 导入成功: {imported_count} 条标签")
        return {'FINISHED'}
