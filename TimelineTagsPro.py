bl_info = {
    "name": "Timeline Tags Pro V36.6",
    "author": "Dev_BlenderPy",
    "version": (36, 6),
    "blender": (3, 0, 0),
    "location": "View3D > Sidebar > Tags Pro",
    "description": "修复撤销系统：为所有操作符添加 UNDO 支持，确保 Ctrl+Z 正常工作。",
    "category": "Animation",
}

import bpy
import json
import re
import math
import time
import os
from bpy.props import IntProperty, StringProperty, CollectionProperty, PointerProperty, BoolProperty, FloatVectorProperty, EnumProperty, FloatProperty
from bpy.types import PropertyGroup, UIList, Operator, Panel, Menu
from bpy.app.handlers import persistent
from bpy_extras.io_utils import ImportHelper, ExportHelper

# =========================================================================
# 1. 核心逻辑 (IO & Sync)
# =========================================================================

def sync_lines_to_content(item):
    lines = [line.body for line in item.text_lines]
    item["content"] = "\n".join(lines) 

def sync_content_to_lines(item):
    raw = item.get("content", "")
    item.text_lines.clear()
    if not raw:
        item.text_lines.add()
        return
    lines = raw.split("\n")
    for txt in lines:
        new_line = item.text_lines.add()
        new_line.body = txt

def save_runtime_data(scene):
    """【写】将运行时列表序列化为 JSON 并写入 Text Block"""
    if getattr(scene, "ttag_is_loading", False): return

    text_block = scene.ttag_source_text
    if not text_block: return

    data_list = []
    sorted_items = sorted(scene.ttag_runtime_items, key=lambda x: x.frame)
    
    for item in sorted_items:
        if len(item.text_lines) > 0:
            sync_lines_to_content(item)
            
        entry = {
            "frame": item.frame,
            "summary": item.summary,
            "content": item.content,
            "color": (item.color[0], item.color[1], item.color[2]),
        }
        data_list.append(entry)
    
    text_block.clear()
    text_block.write(json.dumps(data_list, indent=2, ensure_ascii=False))

def repair_invalid_json_text(raw_text):
    """[V36.5] 计数器算法修复反斜杠"""
    result = []
    i = 0
    n = len(raw_text)
    
    while i < n:
        char = raw_text[i]
        if char == '\\':
            start = i
            while i < n and raw_text[i] == '\\':
                i += 1
            bs_count = i - start
            result.append('\\' * bs_count)
            if bs_count % 2 == 1:
                if i < n:
                    next_char = raw_text[i]
                    if next_char in '"\\/bfnrt':
                        pass
                    elif next_char == 'u':
                        is_hex = False
                        if i + 4 < n:
                            try:
                                int(raw_text[i+1:i+5], 16)
                                is_hex = True
                            except ValueError:
                                pass
                        if not is_hex:
                            result.append('\\')
                    else:
                        result.append('\\')
                else:
                    result.append('\\')
        else:
            result.append(char)
            i += 1
    return "".join(result)

def load_runtime_data(scene, operator=None, retry_count=0):
    """【读】从 Text Block 读取 JSON"""
    scene.ttag_is_loading = True
    try:
        text_block = scene.ttag_source_text
        if not text_block: 
            scene.ttag_runtime_items.clear()
            return

        raw_text = text_block.as_string()
        if not raw_text.strip(): 
            scene.ttag_runtime_items.clear()
            return 

        data_list = None
        try:
            data_list = json.loads(raw_text)
        except json.JSONDecodeError as e:
            if retry_count == 0:
                print(f"TTAG Info: JSON 解析失败，尝试智能修复... ({str(e)})")
                fixed_text = repair_invalid_json_text(raw_text)
                if fixed_text != raw_text:
                    text_block.clear()
                    text_block.write(fixed_text)
                    if operator:
                        operator.report({'WARNING'}, "检测到复杂转义符错误，已自动修复并重载。")
                    scene.ttag_is_loading = False 
                    load_runtime_data(scene, operator, retry_count=1)
                    return
                else:
                    msg = f"JSON 严重格式错误 (无法自动修复): {str(e)}"
                    if operator: operator.report({'ERROR'}, msg)
                    return
            else:
                msg = f"修复后依然无效: {str(e)}"
                if operator: operator.report({'ERROR'}, msg)
                return

        if not isinstance(data_list, list): 
            msg = "数据格式错误: 根节点必须是列表"
            if operator: operator.report({'ERROR'}, msg)
            return

        scene.ttag_runtime_items.clear()
        for entry in data_list:
            item = scene.ttag_runtime_items.add()
            item.frame = entry.get("frame", 1)
            item.summary = entry.get("summary", "Tag")
            item.content = entry.get("content", "") 
            col = entry.get("color", (1.0, 1.0, 1.0))
            item.color = (col[0], col[1], col[2])
            sync_content_to_lines(item)
        
        if len(scene.ttag_runtime_items) > 0:
            scene.ttag_active_item_index = 0
    finally:
        scene.ttag_is_loading = False

def update_source_text_ptr(self, context):
    load_runtime_data(self, operator=None)

def update_item_data(self, context):
    save_runtime_data(context.scene)

def update_line_body(self, context):
    save_runtime_data(context.scene)

# =========================================================================
# 2. 辅助函数
# =========================================================================

def validate_item_index(self, context):
    count = len(self.ttag_runtime_items)
    if count == 0: return
    if self.ttag_active_item_index >= count:
        self.ttag_active_item_index = max(0, count - 1)

def frame_to_timecode(frame, fps):
    total = frame / fps
    h = int(total // 3600)
    m = int((total % 3600) // 60)
    s = int(total % 60)
    ms = int(round((total - int(total)) * 1000))
    if ms >= 1000:
        ms = 0
        s += 1
        if s >= 60:
            s = 0
            m += 1
            if m >= 60:
                m = 0
                h += 1
    return f"{h:02}:{m:02}:{s:02},{ms:03}"

def timecode_to_frame(timecode, fps):
    try:
        parts = timecode.replace(',', ':').replace('.', ':').split(':') 
        h, m, s, ms = map(int, parts)
        total = h * 3600 + m * 60 + s + (ms / 1000.0)
        return int(round(total * fps))
    except:
        return 0

def update_item_index(self, context):
    scene = context.scene
    if getattr(scene, "ttag_lock_sync", False): return
    if getattr(scene, "ttag_is_syncing_from_timeline", False): return
    if not getattr(scene, "ttag_live_sync", False): return
    
    items = scene.ttag_runtime_items
    idx = scene.ttag_active_item_index
    if 0 <= idx < len(items):
        scene.frame_current = items[idx].frame

@persistent
def ttag_sync_handler(scene):
    if not getattr(scene, "ttag_live_sync", False): return
    if getattr(scene, "ttag_lock_sync", False): return
    
    items = scene.ttag_runtime_items
    if len(items) == 0: return
    
    curr = scene.frame_current
    best_idx = -1
    max_frame = -999999
    
    for i, item in enumerate(items):
        if item.frame <= curr:
            if item.frame > max_frame:
                max_frame = item.frame
                best_idx = i
                
    if not getattr(scene, "ttag_is_syncing_from_timeline", False):
        if best_idx != -1 and scene.ttag_active_item_index != best_idx:
            scene.ttag_is_syncing_from_timeline = True 
            scene.ttag_active_item_index = best_idx
            scene.ttag_is_syncing_from_timeline = False

# =========================================================================
# 3. 数据结构
# =========================================================================

class TTAG_TextLine(PropertyGroup):
    body: StringProperty(name="Text", default="", update=update_line_body, description="单行文本内容")

class TTAG_Item(PropertyGroup):
    frame: IntProperty(name="Frame", default=1, update=update_item_data, description="标签帧号")
    summary: StringProperty(name="Label", default="Tag", update=update_item_data, description="标签标题")
    content: StringProperty(name="Content", default="") 
    text_lines: CollectionProperty(type=TTAG_TextLine)
    color: FloatVectorProperty(name="Color", subtype='COLOR', default=(1.0, 1.0, 1.0), min=0.0, max=1.0, update=update_item_data, description="标签颜色")

# =========================================================================
# 4. 操作符
# =========================================================================

class TTAG_OT_Insert_Newline(Operator):
    bl_idname = "ttag.insert_newline"
    bl_label = "插入新行"
    bl_description = "在此行下方插入新文本行"
    # [V36.6] 添加 UNDO 支持
    bl_options = {'REGISTER', 'UNDO'}
    target_index: IntProperty(default=-1)

    def execute(self, context):
        scene = context.scene
        items = scene.ttag_runtime_items
        if len(items) == 0: return {'CANCELLED'}
        
        item = items[scene.ttag_active_item_index]
        
        insert_pos = 0
        current_len = len(item.text_lines)
        if self.target_index == -1: insert_pos = current_len
        else: insert_pos = self.target_index + 1
        if insert_pos > current_len: insert_pos = current_len
        
        item.text_lines.add()
        new_idx = len(item.text_lines) - 1
        item.text_lines.move(new_idx, insert_pos)
        
        sync_lines_to_content(item)
        save_runtime_data(scene)
        return {'FINISHED'}

class TTAG_OT_Remove_Text_Line(Operator):
    bl_idname = "ttag.remove_text_line"
    bl_label = "删除行"
    bl_description = "删除此行"
    # [V36.6] 添加 UNDO 支持
    bl_options = {'REGISTER', 'UNDO'}
    index: IntProperty()

    def execute(self, context):
        scene = context.scene
        items = scene.ttag_runtime_items
        if len(items) == 0: return {'CANCELLED'}
        
        item = items[scene.ttag_active_item_index]
        
        if len(item.text_lines) > 0 and self.index < len(item.text_lines):
            item.text_lines.remove(self.index)
            if len(item.text_lines) == 0:
                item.text_lines.add()
            sync_lines_to_content(item)
            save_runtime_data(scene)
        return {'FINISHED'}

class TTAG_OT_Copy_Clipboard(Operator):
    bl_idname = "ttag.copy_clipboard"
    bl_label = "复制"
    bl_description = "复制内容"
    # Copy 不需要 Undo，因为它不修改 Blender 数据
    def execute(self, context):
        scene = context.scene
        items = scene.ttag_runtime_items
        if len(items) == 0: return {'CANCELLED'}
        
        item = items[scene.ttag_active_item_index]
        sync_lines_to_content(item)
        context.window_manager.clipboard = item.content
        self.report({'INFO'}, "已复制")
        return {'FINISHED'}

class TTAG_OT_Paste_Clipboard(Operator):
    bl_idname = "ttag.paste_clipboard"
    bl_label = "粘贴"
    bl_description = "粘贴内容"
    # [V36.6] 添加 UNDO 支持
    bl_options = {'REGISTER', 'UNDO'}
    def execute(self, context):
        scene = context.scene
        items = scene.ttag_runtime_items
        if len(items) == 0: return {'CANCELLED'}
        
        content = context.window_manager.clipboard
        if content is None: return {'CANCELLED'}
        
        item = items[scene.ttag_active_item_index]
        item.content = content
        sync_content_to_lines(item)
        save_runtime_data(scene)
        self.report({'INFO'}, "已粘贴")
        return {'FINISHED'}

class TTAG_OT_List_Action(Operator):
    bl_idname = "ttag.list_action"
    bl_label = "List Action"
    bl_description = "列表操作"
    # [V36.6] 添加 UNDO 支持
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
                item = items.add()
                item.frame = scene.frame_current
                item.summary = f"F{item.frame}"
                item.color = scene.ttag_default_color
                item.content = "" 
                sync_content_to_lines(item) 
                scene.ttag_active_item_index = list_len 
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
            save_runtime_data(scene)
        finally:
            scene.ttag_lock_sync = False
        return {'FINISHED'}

class TTAG_OT_Reload_From_Text(Operator):
    bl_idname = "ttag.reload_from_text"
    bl_label = "重载"
    bl_description = "强制从文本块重新读取数据 (自动修复转义符)"
    # [V36.6] 重载也是对数据的大规模修改，支持撤销
    bl_options = {'REGISTER', 'UNDO'}
    def execute(self, context):
        load_runtime_data(context.scene, operator=self)
        if context.scene.ttag_runtime_items:
            self.report({'INFO'}, "数据已加载")
        return {'FINISHED'}

class TTAG_OT_Sort_By_Frame(Operator):
    bl_idname = "ttag.sort_by_frame"
    bl_label = "排序"
    bl_description = "按帧号排序"
    # [V36.6] 添加 UNDO 支持
    bl_options = {'REGISTER', 'UNDO'}
    def execute(self, context):
        scene = context.scene
        if not scene.ttag_source_text: return {'CANCELLED'}
        
        items = scene.ttag_runtime_items
        
        scene.ttag_lock_sync = True 
        try:
            n = len(items)
            for i in range(n):
                min_idx = i
                for j in range(i + 1, n):
                    if items[j].frame < items[min_idx].frame:
                        min_idx = j
                if min_idx != i:
                    items.move(min_idx, i)
            save_runtime_data(scene)
        finally:
            scene.ttag_lock_sync = False
        return {'FINISHED'}

class TTAG_OT_Export_SRT(Operator, ExportHelper):
    bl_idname = "ttag.export_srt"
    bl_label = "导出 SRT 文件"
    bl_description = "导出SRT"
    filename_ext = ".srt"
    filter_glob: StringProperty(default="*.srt", options={'HIDDEN'})

    def execute(self, context):
        scene = context.scene
        items = scene.ttag_runtime_items
        if len(items) == 0: 
            self.report({'WARNING'}, "列表为空")
            return {'CANCELLED'}
            
        fps = scene.render.fps / scene.render.fps_base
        filepath = self.filepath
        
        sorted_items = sorted(items, key=lambda x: x.frame)
        srt_content = ""
        counter = 1
        for i, item in enumerate(sorted_items):
            sync_lines_to_content(item)
            content = item.content.strip()
            if not content: continue
            start_time = frame_to_timecode(item.frame, fps)
            end_frame = item.frame + 24
            if i < len(sorted_items) - 1: end_frame = sorted_items[i+1].frame
            end_time = frame_to_timecode(end_frame, fps)
            srt_content += f"{counter}\n{start_time} --> {end_time}\n{content}\n\n"
            counter += 1
            
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(srt_content)
            self.report({'INFO'}, f"导出成功: {filepath}")
        except Exception as e:
            self.report({'ERROR'}, f"写入失败: {str(e)}")
            return {'CANCELLED'}
        return {'FINISHED'}

class TTAG_OT_Import_SRT(Operator, ImportHelper):
    bl_idname = "ttag.import_srt"
    bl_label = "导入 SRT 文件"
    bl_description = "导入SRT"
    filter_glob: StringProperty(default="*.srt", options={'HIDDEN'})
    filename_ext: StringProperty(default=".srt", options={'HIDDEN'})
    # [V36.6] 导入是大量数据写入，必须支持撤销
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        scene = context.scene
        if not scene.ttag_source_text:
            self.report({'ERROR'}, "请先选择或新建一个 Text 数据块")
            return {'CANCELLED'}
            
        filepath = self.filepath
        if not os.path.exists(filepath): return {'CANCELLED'}

        try:
            with open(filepath, 'r', encoding='utf-8-sig') as f:
                raw_text = f.read()
        except Exception as e:
            self.report({'ERROR'}, f"读取失败: {str(e)}")
            return {'CANCELLED'}

        fps = scene.render.fps / scene.render.fps_base
        pattern = re.compile(r'(\d+)\s*\n\s*(\d{2}:\d{2}:\d{2}[,:]\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2}[,:]\d{3})\s*\n(.*?)(?=\n\s*\d+\s*\n|\Z)', re.DOTALL)
        matches = pattern.findall(raw_text)
        if not matches:
            self.report({'WARNING'}, "无效SRT")
            return {'CANCELLED'}
        
        scene.ttag_runtime_items.clear()
        for match in matches:
            start_tc = match[1]
            content = match[3].strip()
            frame = timecode_to_frame(start_tc, fps)
            item = scene.ttag_runtime_items.add()
            item.frame = frame
            item.content = content
            item.summary = f"F{frame}"
            item.color = scene.ttag_default_color
            sync_content_to_lines(item) 
            
        save_runtime_data(scene)
        self.report({'INFO'}, f"导入 {len(matches)} 条")
        return {'FINISHED'}

class TTAG_OT_Generate_Keyframes(Operator):
    bl_idname = "ttag.generate_keyframes"
    bl_label = "烘焙当前版本"
    bl_description = "生成3D物体"
    bl_options = {'REGISTER', 'UNDO'} 

    def get_or_create_material(self, name, color):
        mat = bpy.data.materials.get(name)
        if mat is None: mat = bpy.data.materials.new(name=name)
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

    def execute(self, context):
        scene = context.scene
        if context.view_layer:
            context.view_layer.update()
            
        items = scene.ttag_runtime_items
        if len(items) == 0: return {'CANCELLED'}
        save_runtime_data(scene) 
        
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
        if coll_name in bpy.data.collections: target_coll = bpy.data.collections[coll_name]
        else:
            target_coll = bpy.data.collections.new(coll_name)
            scene.collection.children.link(target_coll)

        root_empty = None
        if root_name in bpy.data.objects:
            root_empty = bpy.data.objects[root_name]
            if scene.ttag_overwrite:
                children = list(root_empty.children)
                for child in children: 
                    bpy.data.objects.remove(child, do_unlink=True)
            
            if root_empty.name not in target_coll.objects: target_coll.objects.link(root_empty)
        else:
            root_empty = bpy.data.objects.new(root_name, None)
            root_empty.empty_display_type = 'PLAIN_AXES'
            target_coll.objects.link(root_empty)
        
        sorted_items = sorted(items, key=lambda x: x.frame)
        for i, item in enumerate(sorted_items):
            sync_lines_to_content(item)
            full_text = item.content
            if not full_text: full_text = " "
            
            font_curve = bpy.data.curves.new(type="FONT", name=f"TTAG_Data_{item.frame}")
            font_curve.body = full_text
            
            if loaded_font:
                font_curve.font = loaded_font
                
            font_curve.align_x = scene.ttag_global_align
            font_curve.space_line = scene.ttag_line_spacing
            
            font_curve.align_y = 'BOTTOM'
            font_curve.extrude = 0.02
            
            obj = bpy.data.objects.new(name=f"TTAG_{item.frame}", object_data=font_curve)
            target_coll.objects.link(obj)
            
            mat = self.get_or_create_material(f"TTAG_Mat_{safe_name}_{item.frame}", item.color)
            if obj.data.materials: obj.data.materials[0] = mat
            else: obj.data.materials.append(mat)
            
            obj.parent = root_empty
            obj.rotation_euler.x = math.radians(90)
            obj.location = (0, 0, 0)
            
            obj.hide_viewport = True
            obj.hide_render = True
            obj.keyframe_insert(data_path="hide_viewport", frame=item.frame - 1)
            obj.keyframe_insert(data_path="hide_render", frame=item.frame - 1)
            obj.hide_viewport = False
            obj.hide_render = False
            obj.keyframe_insert(data_path="hide_viewport", frame=item.frame)
            obj.keyframe_insert(data_path="hide_render", frame=item.frame)
            
            if i < len(sorted_items) - 1:
                next_item_frame = sorted_items[i+1].frame
                if next_item_frame > item.frame:
                    obj.hide_viewport = True
                    obj.hide_render = True
                    obj.keyframe_insert(data_path="hide_viewport", frame=next_item_frame)
                    obj.keyframe_insert(data_path="hide_render", frame=next_item_frame)
            
            if not item.content.strip():
                obj.hide_viewport = True
                obj.hide_render = True
                obj.keyframe_insert(data_path="hide_viewport", frame=item.frame)
                obj.keyframe_insert(data_path="hide_render", frame=item.frame)
            
            if obj.animation_data and obj.animation_data.action:
                for fcurve in obj.animation_data.action.fcurves:
                    for kf in fcurve.keyframe_points: kf.interpolation = 'CONSTANT'
        
        if context.view_layer:
            context.view_layer.update()
            
        self.report({'INFO'}, f"[{safe_name}] 烘焙完成")
        return {'FINISHED'}

# =========================================================================
# 5. UI PANEL
# =========================================================================

class TTAG_UL_List(UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        split = layout.split(factor=0.12)
        split.prop(item, "color", text="", icon_only=True, emboss=True)
        right_area = split.row(align=True)
        sub_split = right_area.split(factor=0.5)
        sub_split.prop(item, "frame", text="", emboss=False)
        sub_split.prop(item, "summary", text="", emboss=False)

class TTAG_PT_Panel(Panel):
    bl_label = "Timeline Tags Pro V36.6"
    bl_idname = "TTAG_PT_main"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Tags Pro"

    def draw(self, context):
        layout = self.layout
        scene = context.scene

        # --- 1. Native Data Block Manager ---
        box = layout.box()
        row = box.row(align=True)
        row.template_ID(scene, "ttag_source_text", new="text.new", open="text.open")
        
        if scene.ttag_source_text:
            row.operator("ttag.reload_from_text", text="", icon='FILE_REFRESH')

        if not scene.ttag_source_text:
            box.label(text="请选择或新建 Text 数据块", icon='INFO')
            return

        layout.separator()

        # --- 2. Global Settings ---
        row = layout.row(align=True)
        row.label(text="设置 (Settings):", icon='PREFERENCES')
        
        sub = row.row(align=True)
        sub.alignment = 'RIGHT'
        sub.prop(scene, "ttag_default_color", text="") 
        sub.prop(scene, "ttag_live_sync", text="", icon='TIME', toggle=True) 

        # --- 3. Data List ---
        row = layout.row()
        row.template_list("TTAG_UL_List", "", scene, "ttag_runtime_items", scene, "ttag_active_item_index")
        
        col = row.column(align=True)
        col.operator("ttag.sort_by_frame", text="", icon='SORT_ASC')
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
            if safe_idx >= len(scene.ttag_runtime_items): safe_idx = len(scene.ttag_runtime_items) - 1
            if safe_idx < 0: safe_idx = 0
            
            item = scene.ttag_runtime_items[safe_idx]
            box = layout.box()
            col = box.column(align=True)
            
            col.label(text="内容编辑 (Content Edit):", icon='TEXT')
            
            row_tools = col.row(align=True)
            row_tools.scale_y = 1.2
            row_tools.operator("ttag.copy_clipboard", text="复制", icon='COPYDOWN')
            row_tools.operator("ttag.paste_clipboard", text="粘贴", icon='PASTEDOWN')
            
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
        
        # Row 3
        row = box.row()
        row.scale_y = 1.2
        target_name = scene.ttag_source_text.name if scene.ttag_source_text else "None"
        row.operator("ttag.generate_keyframes", icon='SHADING_BBOX', text=f"烘焙: {target_name}")

# =========================================================================
# 6. 注册
# =========================================================================

classes = (
    TTAG_TextLine,
    TTAG_Item, 
    TTAG_OT_Insert_Newline, TTAG_OT_Remove_Text_Line,
    TTAG_OT_Export_SRT, TTAG_OT_Import_SRT,
    TTAG_OT_List_Action, TTAG_OT_Copy_Clipboard, TTAG_OT_Paste_Clipboard, 
    TTAG_OT_Reload_From_Text,
    TTAG_OT_Sort_By_Frame, TTAG_OT_Generate_Keyframes,
    TTAG_UL_List, TTAG_PT_Panel,
)

def register():
    for cls in classes: bpy.utils.register_class(cls)
    
    bpy.types.Scene.ttag_source_text = PointerProperty(
        name="Data Source",
        type=bpy.types.Text,
        description="存储标签数据的文本块",
        update=update_source_text_ptr
    )
    
    bpy.types.Scene.ttag_runtime_items = CollectionProperty(type=TTAG_Item)
    
    bpy.types.Scene.ttag_is_loading = BoolProperty(default=False)
    
    bpy.types.Scene.ttag_active_item_index = IntProperty(
        min=0, update=update_item_index,
        description="当前激活的标签索引"
    )
    
    bpy.types.Scene.ttag_overwrite = BoolProperty(name="Overwrite", default=True, description="勾选: 覆盖旧烘焙")
    bpy.types.Scene.ttag_live_sync = BoolProperty(name="Sync", default=True, description="开启: 列表随时间轴自动滚动")
    bpy.types.Scene.ttag_is_syncing_from_timeline = BoolProperty(default=False)
    bpy.types.Scene.ttag_lock_sync = BoolProperty(default=False)
    bpy.types.Scene.ttag_default_color = FloatVectorProperty(name="Default Color", subtype='COLOR', default=(1.0, 1.0, 1.0), min=0.0, max=1.0)
    
    bpy.types.Scene.ttag_global_align = EnumProperty(
        name="Global Align",
        items=[('LEFT', "Left", "左对齐", 'ALIGN_LEFT', 0), ('CENTER', "Center", "居中", 'ALIGN_CENTER', 1), ('RIGHT', "Right", "右对齐", 'ALIGN_RIGHT', 2)],
        default='CENTER'
    )
    
    bpy.types.Scene.ttag_font_path = StringProperty(name="烘焙字体", description="烘焙字体文件路径", subtype='FILE_PATH')
    bpy.types.Scene.ttag_line_spacing = FloatProperty(name="行距", default=1.0)

    if ttag_sync_handler not in bpy.app.handlers.frame_change_post: bpy.app.handlers.frame_change_post.append(ttag_sync_handler)

def unregister():
    if ttag_sync_handler in bpy.app.handlers.frame_change_post: bpy.app.handlers.frame_change_post.remove(ttag_sync_handler)
    for cls in reversed(classes): bpy.utils.unregister_class(cls)
    del bpy.types.Scene.ttag_source_text
    del bpy.types.Scene.ttag_runtime_items
    del bpy.types.Scene.ttag_is_loading
    del bpy.types.Scene.ttag_active_item_index
    del bpy.types.Scene.ttag_overwrite
    del bpy.types.Scene.ttag_live_sync
    del bpy.types.Scene.ttag_is_syncing_from_timeline
    del bpy.types.Scene.ttag_lock_sync
    del bpy.types.Scene.ttag_default_color
    del bpy.types.Scene.ttag_global_align
    del bpy.types.Scene.ttag_font_path
    del bpy.types.Scene.ttag_line_spacing

if __name__ == "__main__":
    register()