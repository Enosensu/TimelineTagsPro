bl_info = {
    "name": "Timeline Tags Pro V45.0",
    "author": "Dev_BlenderPy",
    "version": (45, 0),
    "blender": (3, 0, 0),
    "location": "View3D > Sidebar > Tags Pro",
    "description": "智能插入版：添加新标签时，自动根据当前帧数将其插入到列表的对应时间顺序位置。",
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

# 全局变量：用于存储防抖计时器
_TTAG_SAVE_TIMER = None

def sync_lines_to_content(item):
    """
    将多行文本合并为字符串。
    完全忠实于用户输入，不自动剔除任何末尾空行。
    """
    lines = [line.body for line in item.text_lines]
    item["content"] = "\n".join(lines) 

def sync_content_to_lines(item):
    """
    将字符串拆分为多行文本。
    完全还原保存的数据（包括空行）。
    """
    raw = item.get("content", "")
    item.text_lines.clear()
    
    if raw:
        # split('\n') 会保留空行，忠实还原
        lines = raw.split("\n")
        for txt in lines:
            new_line = item.text_lines.add()
            new_line.body = txt
    else:
        # 默认给一行，方便输入
        item.text_lines.add()

def save_runtime_data_immediate(scene):
    """
    【立即保存】执行实际的 Text Block 写入操作。
    """
    if getattr(scene, "ttag_is_loading", False): 
        return

    text_block = scene.ttag_source_text
    if not text_block: 
        return

    # 1. 序列化标签数据
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
    
    # 2. 序列化全局设置
    settings_dict = {
        "overwrite_3d": scene.ttag_overwrite,
        "overwrite_markers": scene.ttag_overwrite_markers,
        "live_sync": scene.ttag_live_sync,
        "default_color": (scene.ttag_default_color[0], scene.ttag_default_color[1], scene.ttag_default_color[2]),
        "global_align": scene.ttag_global_align,
        "font_path": scene.ttag_font_path,
        "line_spacing": scene.ttag_line_spacing
    }

    final_payload = {
        "version": "V45.0",
        "settings": settings_dict,
        "data": data_list
    }
    
    text_block.clear()
    text_block.write(json.dumps(final_payload, indent=2, ensure_ascii=False))

def auto_save_debounced(scene):
    """
    【防抖保存】
    用于文本输入、参数调整和行数调整。
    延迟 0.8 秒执行保存，解决打字失焦问题。
    """
    global _TTAG_SAVE_TIMER
    
    if _TTAG_SAVE_TIMER is not None:
        if bpy.app.timers.is_registered(_TTAG_SAVE_TIMER):
            bpy.app.timers.unregister(_TTAG_SAVE_TIMER)
    
    def _save_task():
        if scene.ttag_source_text:
            save_runtime_data_immediate(scene)
        return None 

    _TTAG_SAVE_TIMER = _save_task
    bpy.app.timers.register(_TTAG_SAVE_TIMER, first_interval=0.8)

def repair_invalid_json_text(raw_text):
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
    """【读】反序列化 (兼容 List/Dict)"""
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

        json_data = None
        try:
            json_data = json.loads(raw_text)
        except json.JSONDecodeError as e:
            if retry_count == 0:
                print(f"TTAG Info: JSON Fix... ({str(e)})")
                fixed_text = repair_invalid_json_text(raw_text)
                if fixed_text != raw_text:
                    text_block.clear()
                    text_block.write(fixed_text)
                    if operator: 
                        operator.report({'WARNING'}, "检测到格式错误，已自动修复。")
                    scene.ttag_is_loading = False 
                    load_runtime_data(scene, operator, retry_count=1)
                    return
                else:
                    if operator: 
                        operator.report({'ERROR'}, f"JSON Error: {str(e)}")
                    return
            else:
                if operator: 
                    operator.report({'ERROR'}, f"JSON Error: {str(e)}")
                return

        data_list = []
        if isinstance(json_data, list):
            data_list = json_data
        elif isinstance(json_data, dict):
            data_list = json_data.get("data", [])
            settings = json_data.get("settings", {})
            
            # 恢复设置
            if "overwrite_3d" in settings: 
                scene.ttag_overwrite = settings["overwrite_3d"]
            if "overwrite_markers" in settings: 
                scene.ttag_overwrite_markers = settings["overwrite_markers"]
            if "live_sync" in settings: 
                scene.ttag_live_sync = settings["live_sync"]
            if "default_color" in settings: 
                c = settings["default_color"]
                scene.ttag_default_color = (c[0], c[1], c[2])
            if "global_align" in settings: 
                scene.ttag_global_align = settings["global_align"]
            if "font_path" in settings: 
                scene.ttag_font_path = settings["font_path"]
            if "line_spacing" in settings: 
                scene.ttag_line_spacing = settings["line_spacing"]
        else:
            if operator: 
                operator.report({'ERROR'}, "数据格式错误: 根节点类型未知")
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
    auto_save_debounced(context.scene)

def update_settings(self, context):
    auto_save_debounced(context.scene)

def update_line_body(self, context):
    if getattr(context.scene, "ttag_is_loading", False): 
        return
    auto_save_debounced(context.scene)

# =========================================================================
# 2. 辅助函数
# =========================================================================

def validate_item_index(self, context):
    count = len(self.ttag_runtime_items)
    if count == 0: 
        return
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
    if getattr(scene, "ttag_lock_sync", False): 
        return
    if getattr(scene, "ttag_is_syncing_from_timeline", False): 
        return
    if not getattr(scene, "ttag_live_sync", False): 
        return
    items = scene.ttag_runtime_items
    idx = scene.ttag_active_item_index
    if 0 <= idx < len(items):
        scene.frame_current = items[idx].frame

@persistent
def ttag_sync_handler(scene):
    if not getattr(scene, "ttag_live_sync", False): 
        return
    if getattr(scene, "ttag_lock_sync", False): 
        return
    items = scene.ttag_runtime_items
    if len(items) == 0: 
        return
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

def get_line_count(self):
    return len(self.text_lines)

def set_line_count(self, value):
    current = len(self.text_lines)
    last_content_idx = -1
    for i, line in enumerate(self.text_lines):
        if line.body.strip():
            last_content_idx = i
            
    min_allowed = last_content_idx + 1
    min_allowed = max(1, min_allowed)
    
    target = max(value, min_allowed)
    
    if target > current:
        for _ in range(target - current):
            self.text_lines.add()
    elif target < current:
        for _ in range(current - target):
            self.text_lines.remove(len(self.text_lines) - 1)
            
    try:
        if bpy.context and bpy.context.scene:
            auto_save_debounced(bpy.context.scene)
    except: 
        pass

class TTAG_TextLine(PropertyGroup):
    body: StringProperty(name="Text", default="", update=update_line_body)

class TTAG_Item(PropertyGroup):
    frame: IntProperty(name="Frame", default=1, update=update_item_data)
    summary: StringProperty(name="Label", default="Tag", update=update_item_data)
    content: StringProperty(name="Content", default="") 
    text_lines: CollectionProperty(type=TTAG_TextLine)
    color: FloatVectorProperty(name="Color", subtype='COLOR', default=(1.0, 1.0, 1.0), min=0.0, max=1.0, update=update_item_data)
    
    line_count: IntProperty(
        name="Line Count",
        description="调整行数（不会删除已输入文字的行）",
        default=1,
        min=1,
        get=get_line_count,
        set=set_line_count
    )

# =========================================================================
# 4. 操作符
# =========================================================================

class TTAG_OT_Insert_Top_Line(Operator):
    bl_idname = "ttag.insert_top_line"
    bl_label = "置顶插入空行"
    bl_description = "在当前文本框的最上方添加一行新空行"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        scene = context.scene
        items = scene.ttag_runtime_items
        if len(items) == 0: 
            return {'CANCELLED'}
        
        item = items[scene.ttag_active_item_index]
        
        item.text_lines.add()
        item.text_lines.move(len(item.text_lines) - 1, 0)
        
        sync_lines_to_content(item)
        save_runtime_data_immediate(scene)
        return {'FINISHED'}

class TTAG_OT_Insert_Newline(Operator):
    bl_idname = "ttag.insert_newline"
    bl_label = "插入新行"
    bl_description = "在此行下方插入新文本行"
    bl_options = {'REGISTER', 'UNDO'}
    target_index: IntProperty(default=-1)

    def execute(self, context):
        scene = context.scene
        items = scene.ttag_runtime_items
        if len(items) == 0: 
            return {'CANCELLED'}
        
        item = items[scene.ttag_active_item_index]
        
        insert_pos = 0
        current_len = len(item.text_lines)
        if self.target_index == -1: 
            insert_pos = current_len
        else: 
            insert_pos = self.target_index + 1

        if insert_pos > current_len: 
            insert_pos = current_len
        
        item.text_lines.add()
        new_idx = len(item.text_lines) - 1
        item.text_lines.move(new_idx, insert_pos)
        
        sync_lines_to_content(item)
        save_runtime_data_immediate(scene)
        return {'FINISHED'}

class TTAG_OT_Remove_Text_Line(Operator):
    bl_idname = "ttag.remove_text_line"
    bl_label = "删除行"
    bl_description = "删除此行"
    bl_options = {'REGISTER', 'UNDO'}
    index: IntProperty()

    def execute(self, context):
        scene = context.scene
        items = scene.ttag_runtime_items
        if len(items) == 0: 
            return {'CANCELLED'}
        
        item = items[scene.ttag_active_item_index]
        
        if len(item.text_lines) > 0 and self.index < len(item.text_lines):
            item.text_lines.remove(self.index)
            if len(item.text_lines) == 0:
                item.text_lines.add()
            sync_lines_to_content(item)
            save_runtime_data_immediate(scene)
        return {'FINISHED'}

class TTAG_OT_Copy_Clipboard(Operator):
    bl_idname = "ttag.copy_clipboard"
    bl_label = "复制"
    bl_description = "复制内容"
    
    def execute(self, context):
        scene = context.scene
        items = scene.ttag_runtime_items
        if len(items) == 0: 
            return {'CANCELLED'}
        
        item = items[scene.ttag_active_item_index]
        sync_lines_to_content(item)
        context.window_manager.clipboard = item.content
        self.report({'INFO'}, "已复制")
        return {'FINISHED'}

class TTAG_OT_Paste_Clipboard(Operator):
    bl_idname = "ttag.paste_clipboard"
    bl_label = "粘贴"
    bl_description = "粘贴内容"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        scene = context.scene
        items = scene.ttag_runtime_items
        if len(items) == 0: 
            return {'CANCELLED'}
        
        content = context.window_manager.clipboard
        if content is None: 
            return {'CANCELLED'}
        
        item = items[scene.ttag_active_item_index]
        item.content = content
        sync_content_to_lines(item)
        save_runtime_data_immediate(scene)
        self.report({'INFO'}, "已粘贴")
        return {'FINISHED'}

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
                
                # [V45.0 修改] 1. 先将项目添加到列表末尾
                item = items.add()
                item.frame = new_frame
                
                # 规范化标签命名，并自动防冲突
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
                
                # [V45.0 修改] 2. 智能寻找插入位置（保持列表时间顺序）
                new_index = len(items) - 1 # 默认在最后
                for i in range(len(items) - 1):
                    if items[i].frame > new_frame:
                        new_index = i
                        break
                
                # [V45.0 修改] 3. 移动到对应位置并激活
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

class TTAG_OT_Reload_From_Text(Operator):
    bl_idname = "ttag.reload_from_text"
    bl_label = "重载"
    bl_description = "强制从文本块重新读取数据 (自动修复转义符)"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        load_runtime_data(context.scene, operator=self)
        self.report({'INFO'}, "数据已加载")
        return {'FINISHED'}

class TTAG_OT_Sort_By_Frame(Operator):
    bl_idname = "ttag.sort_by_frame"
    bl_label = "排序"
    bl_description = "按帧号排序"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        scene = context.scene
        if not scene.ttag_source_text: 
            return {'CANCELLED'}
        
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
                # 记录旧名称，用来寻找时间轴上的标记
                old_name = item.summary if item.summary else f"F_{item.frame}"
                marker = scene.timeline_markers.get(old_name)
                
                # 计算新的防冲突名称
                base_name = f"F_{item.frame}"
                unique_name = base_name
                counter = 1
                
                while unique_name in used_names:
                    unique_name = f"{base_name}_{counter}"
                    counter += 1
                    
                # 1. 更改插件内标签名称
                item.summary = unique_name
                
                # 2. 同步更改对应的时间轴标记名称 (仅改名称，不改帧数位置)
                if marker:
                    marker.name = unique_name
                
                used_names.add(unique_name)
                
            save_runtime_data_immediate(scene)
            self.report({'INFO'}, "已根据实际帧数重新规范所有标签及对应时间轴标记的名称")
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
            if not content: 
                continue
            start_time = frame_to_timecode(item.frame, fps)
            end_frame = item.frame + 24
            if i < len(sorted_items) - 1: 
                end_frame = sorted_items[i+1].frame
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
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        scene = context.scene
        if not scene.ttag_source_text:
            self.report({'ERROR'}, "请先选择或新建一个 Text 数据块")
            return {'CANCELLED'}
            
        filepath = self.filepath
        if not os.path.exists(filepath): 
            return {'CANCELLED'}

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
            item.summary = f"F_{frame}"
            item.color = scene.ttag_default_color
            sync_content_to_lines(item) 
            
        save_runtime_data_immediate(scene)
        self.report({'INFO'}, f"导入 {len(matches)} 条")
        return {'FINISHED'}

class TTAG_OT_Bake_3D_Text(Operator):
    bl_idname = "ttag.bake_3d_text"
    bl_label = "烘焙 3D 文字"
    bl_description = "生成3D文字物体"
    bl_options = {'REGISTER', 'UNDO'} 

    def get_or_create_material(self, name, color):
        mat = bpy.data.materials.get(name)
        if mat is None: 
            mat = bpy.data.materials.new(name=name)
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
        if len(items) == 0: 
            return {'CANCELLED'}
            
        save_runtime_data_immediate(scene) 
        
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
        if coll_name in bpy.data.collections: 
            target_coll = bpy.data.collections[coll_name]
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
            
            if root_empty.name not in target_coll.objects: 
                target_coll.objects.link(root_empty)
        else:
            root_empty = bpy.data.objects.new(root_name, None)
            root_empty.empty_display_type = 'PLAIN_AXES'
            target_coll.objects.link(root_empty)
        
        sorted_items = sorted(items, key=lambda x: x.frame)
        for i, item in enumerate(sorted_items):
            sync_lines_to_content(item)
            full_text = item.content
            if not full_text: 
                full_text = " "
            
            font_curve = bpy.data.curves.new(type="FONT", name=f"TTAG_Data_{item.frame}")
            font_curve.body = full_text
            
            if loaded_font:
                font_curve.font = loaded_font
                
            font_curve.align_x = scene.ttag_global_align
            font_curve.space_line = scene.ttag_line_spacing
            font_curve.align_y = 'BOTTOM'
            font_curve.extrude = 0.02
            
            # --- [适配 Blender 5.1 填充选项, 安全注入] ---
            if hasattr(font_curve, "fill_mode"):
                try: 
                    font_curve.fill_mode = 'BOTH'
                except Exception: 
                    pass
                
            if hasattr(font_curve, "fill_solver"):
                try: 
                    font_curve.fill_solver = 'CDT'
                except Exception: 
                    pass
                
            if hasattr(font_curve, "fill_rule"):
                try: 
                    font_curve.fill_rule = 'EVEN_ODD'
                except Exception: 
                    pass
            
            obj = bpy.data.objects.new(name=f"TTAG_{item.frame}", object_data=font_curve)
            target_coll.objects.link(obj)
            
            mat = self.get_or_create_material(f"TTAG_Mat_{safe_name}_{item.frame}", item.color)
            if obj.data.materials: 
                obj.data.materials[0] = mat
            else: 
                obj.data.materials.append(mat)
            
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
                pass 
            
            if obj.animation_data and obj.animation_data.action:
                for fcurve in obj.animation_data.action.fcurves:
                    for kf in fcurve.keyframe_points: 
                        kf.interpolation = 'CONSTANT'
        
        if context.view_layer:
            context.view_layer.update()
            
        self.report({'INFO'}, f"[{safe_name}] 3D文字烘焙完成")
        return {'FINISHED'}

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
        
        # 时间轴标记处理
        if scene.ttag_overwrite_markers:
            scene.timeline_markers.clear()
            occupied_frames = set() 
        else:
            occupied_frames = {m.frame for m in scene.timeline_markers}

        sorted_items = sorted(items, key=lambda x: x.frame)
        for item in sorted_items:
            # --- 时间轴标记生成逻辑 ---
            m_name = item.summary if item.summary else f"F_{item.frame}"
            m_frame = item.frame
            
            if not scene.ttag_overwrite_markers:
                while m_frame in occupied_frames:
                    m_frame += 1
            
            try:
                scene.timeline_markers.new(name=m_name, frame=m_frame)
                occupied_frames.add(m_frame)
            except Exception as e:
                print(f"Failed to add marker at {m_frame}: {e}")

        self.report({'INFO'}, "时间轴标记已添加")
        return {'FINISHED'}

class TTAG_OT_Sync_From_Timeline(Operator):
    bl_idname = "ttag.sync_from_timeline"
    bl_label = "从时间轴同步帧"
    bl_description = "根据时间轴标记(同名)的当前位置，反向更新插件列表中标签的帧数"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        scene = context.scene
        items = scene.ttag_runtime_items
        if len(items) == 0: 
            return {'CANCELLED'}

        # 锁定自动同步，防止修改过程中列表项与时间轴乱跳
        scene.ttag_lock_sync = True
        try:
            updated_count = 0
            for item in items:
                # 使用标签的名称作为匹配标准
                target_name = item.summary if item.summary else f"F_{item.frame}"
                
                # 尝试在 Blender 的时间轴标记中查找同名标记
                marker = scene.timeline_markers.get(target_name)
                
                # 如果找到，且帧数有变，则同步帧数
                if marker and marker.frame != item.frame:
                    item.frame = marker.frame
                    updated_count += 1
                    
            if updated_count > 0:
                # 因为帧数可能发生了改变，重新按帧号对列表进行排序
                n = len(items)
                for i in range(n):
                    min_idx = i
                    for j in range(i + 1, n):
                        if items[j].frame < items[min_idx].frame:
                            min_idx = j
                    if min_idx != i:
                        items.move(min_idx, i)
                        
                # 立即保存修改后的数据
                save_runtime_data_immediate(scene)
                self.report({'INFO'}, f"成功同步了 {updated_count} 个标签的帧数")
            else:
                self.report({'INFO'}, "没有检测到需要同步的改动")
                
        finally:
            # 解除同步锁定
            scene.ttag_lock_sync = False

        return {'FINISHED'}


# =========================================================================
# 5. UI PANEL
# =========================================================================

class TTAG_UL_List(UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        # 1. 整体划分为: 左(12%给颜色) | 右(88%给其他)
        split_main = layout.split(factor=0.12)
        split_main.prop(item, "color", text="", icon_only=True)
        
        # 2. 将刚才的右侧(88%)，再划分为: 左(35%给帧数) | 右(65%给剩余)
        split_right = split_main.split(factor=0.35)
        split_right.prop(item, "frame", text="")
        
        # 3. 将最后的剩余部分(65%)，再划分为: 左(85%给标签名) | 右(15%给纯留白安全区)
        split_summary = split_right.split(factor=0.85)
        split_summary.prop(item, "summary", text="")
        
        # 【收缩逻辑的关键】放入空的 column 防止被拉伸
        split_summary.column()

class TTAG_PT_Panel(Panel):
    bl_label = "Timeline Tags Pro V45.0"
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
        row.label(text="标签 (Tags):", icon='TAG')
        
        sub = row.row(align=True)
        sub.alignment = 'RIGHT'
        sub.prop(scene, "ttag_default_color", text="") 
        sub.prop(scene, "ttag_live_sync", text="", icon='TIME', toggle=True) 

        # --- 3. Data List ---
        row = layout.row()
        row.template_list("TTAG_UL_List", "", scene, "ttag_runtime_items", scene, "ttag_active_item_index")
        
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

# =========================================================================
# 6. 注册
# =========================================================================

classes = (
    TTAG_TextLine,
    TTAG_Item, 
    TTAG_OT_Insert_Top_Line,
    TTAG_OT_Insert_Newline, 
    TTAG_OT_Remove_Text_Line,
    TTAG_OT_Export_SRT, 
    TTAG_OT_Import_SRT,
    TTAG_OT_List_Action, 
    TTAG_OT_Copy_Clipboard, 
    TTAG_OT_Paste_Clipboard, 
    TTAG_OT_Reload_From_Text,
    TTAG_OT_Sort_By_Frame, 
    TTAG_OT_Rename_By_Frame, 
    TTAG_OT_Bake_3D_Text,
    TTAG_OT_Bake_Timeline_Markers,
    TTAG_OT_Sync_From_Timeline, 
    TTAG_UL_List, 
    TTAG_PT_Panel,
)

def register():
    for cls in classes: 
        bpy.utils.register_class(cls)
    
    bpy.types.Scene.ttag_source_text = PointerProperty(
        name="Data Source",
        type=bpy.types.Text,
        description="存储标签数据的文本块",
        update=update_source_text_ptr
    )
    
    bpy.types.Scene.ttag_runtime_items = CollectionProperty(type=TTAG_Item)
    
    bpy.types.Scene.ttag_is_loading = BoolProperty(default=False)
    
    bpy.types.Scene.ttag_active_item_index = IntProperty(
        min=0, 
        update=update_item_index,
        description="当前激活的标签索引"
    )
    
    bpy.types.Scene.ttag_overwrite = BoolProperty(
        name="Overwrite 3D", 
        default=True, 
        description="覆盖: 重新生成3D文字集合",
        update=update_settings
    )
    
    bpy.types.Scene.ttag_overwrite_markers = BoolProperty(
        name="Overwrite Markers", 
        default=True, 
        description="覆盖标记: 勾选则删除现有所有标记后重新生成；不勾选则在空闲位置追加新标记",
        update=update_settings
    )

    bpy.types.Scene.ttag_live_sync = BoolProperty(
        name="Sync", 
        default=True, 
        description="开启: 列表随时间轴自动滚动",
        update=update_settings
    )
    
    bpy.types.Scene.ttag_is_syncing_from_timeline = BoolProperty(default=False)
    
    bpy.types.Scene.ttag_lock_sync = BoolProperty(default=False)
    
    bpy.types.Scene.ttag_default_color = FloatVectorProperty(
        name="Default Color", 
        subtype='COLOR', 
        default=(1.0, 1.0, 1.0), 
        min=0.0, 
        max=1.0,
        update=update_settings
    )
    
    bpy.types.Scene.ttag_global_align = EnumProperty(
        name="Global Align",
        items=[
            ('LEFT', "Left", "左对齐", 'ALIGN_LEFT', 0),
            ('CENTER', "Center", "居中", 'ALIGN_CENTER', 1),
            ('RIGHT', "Right", "右对齐", 'ALIGN_RIGHT', 2),
        ],
        default='CENTER',
        update=update_settings
    )
    
    bpy.types.Scene.ttag_font_path = StringProperty(
        name="烘焙字体", 
        description="烘焙字体文件路径", 
        subtype='FILE_PATH',
        update=update_settings
    )
    
    bpy.types.Scene.ttag_line_spacing = FloatProperty(
        name="行距", 
        default=1.0, 
        description="文字行间距",
        update=update_settings
    )

    if ttag_sync_handler not in bpy.app.handlers.frame_change_post: 
        bpy.app.handlers.frame_change_post.append(ttag_sync_handler)

def unregister():
    if ttag_sync_handler in bpy.app.handlers.frame_change_post: 
        bpy.app.handlers.frame_change_post.remove(ttag_sync_handler)
        
    for cls in reversed(classes): 
        bpy.utils.unregister_class(cls)
        
    del bpy.types.Scene.ttag_source_text
    del bpy.types.Scene.ttag_runtime_items
    del bpy.types.Scene.ttag_is_loading
    del bpy.types.Scene.ttag_active_item_index
    del bpy.types.Scene.ttag_overwrite
    del bpy.types.Scene.ttag_overwrite_markers
    del bpy.types.Scene.ttag_live_sync
    del bpy.types.Scene.ttag_is_syncing_from_timeline
    del bpy.types.Scene.ttag_lock_sync
    del bpy.types.Scene.ttag_default_color
    del bpy.types.Scene.ttag_global_align
    del bpy.types.Scene.ttag_font_path
    del bpy.types.Scene.ttag_line_spacing

if __name__ == "__main__":
    register()