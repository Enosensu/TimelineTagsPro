bl_info = {
    "name": "Timeline Tags Pro V16",
    "author": "Dev_BlenderPy",
    "version": (16, 0),
    "blender": (3, 0, 0),
    "location": "View3D > Sidebar > Tags Pro",
    "description": "最终完善版：支持SRT外部文件导入导出，UI调整，全功能集成",
    "category": "Animation",
}

import bpy
import json
import re
import math
import time
import os
from bpy.props import IntProperty, StringProperty, CollectionProperty, PointerProperty, BoolProperty, FloatVectorProperty
from bpy.types import PropertyGroup, UIList, Operator, Panel
from bpy.app.handlers import persistent
# 引入 ExportHelper 和 ImportHelper
from bpy_extras.io_utils import ImportHelper, ExportHelper

# =========================================================================
# 1. 核心逻辑：数据序列化 (JSON IO)
# =========================================================================

def save_preset_data(preset):
    """将当前预设数据写入文本块"""
    if not preset.storage_file: return
    data_list = []
    # 排序保证顺序
    sorted_items = sorted(preset.items, key=lambda x: x.frame)
    for item in sorted_items:
        entry = {
            "frame": item.frame,
            "summary": item.summary,
            "content": item.content,
            "color": (item.color[0], item.color[1], item.color[2])
        }
        data_list.append(entry)
    preset.storage_file.clear()
    preset.storage_file.write(json.dumps(data_list, indent=2, ensure_ascii=False))

def load_preset_data(preset):
    """从文本块读取数据"""
    if not preset.storage_file: return
    raw_text = preset.storage_file.as_string()
    if not raw_text.strip(): return
    try:
        data_list = json.loads(raw_text)
    except json.JSONDecodeError:
        print("TTAG Error: JSON file corrupted")
        return
    preset.items.clear()
    for entry in data_list:
        item = preset.items.add()
        item.frame = entry.get("frame", 1)
        item.summary = entry.get("summary", "Tag")
        item.content = entry.get("content", "")
        col = entry.get("color", (1.0, 1.0, 1.0))
        item.color = (col[0], col[1], col[2])

def update_preset_name(self, context):
    """预设改名回调"""
    if self.storage_file:
        safe_name = self.name.strip().replace(" ", "_")
        if not safe_name: safe_name = "Unnamed"
        self.storage_file.name = f"TTAG_DB_{safe_name}.json"

# =========================================================================
# 2. 辅助函数 & 同步逻辑
# =========================================================================

def get_active_preset(scene):
    count = len(scene.ttag_presets)
    if count == 0:
        return None
    safe_idx = scene.ttag_active_preset_index
    if safe_idx >= count: safe_idx = count - 1
    if safe_idx < 0: safe_idx = 0
    return scene.ttag_presets[safe_idx]

def validate_preset_index(self, context):
    count = len(self.ttag_presets)
    if count == 0: return
    if self.ttag_active_preset_index >= count:
        self.ttag_active_preset_index = max(0, count - 1)

def frame_to_timecode(frame, fps):
    total = frame / fps
    h = int(total // 3600)
    m = int((total % 3600) // 60)
    s = int(total % 60)
    ms = int((total - int(total)) * 1000)
    return f"{h:02}:{m:02}:{s:02},{ms:03}"

def timecode_to_frame(timecode, fps):
    try:
        parts = timecode.replace(',', ':').replace('.', ':').split(':') 
        h, m, s, ms = map(int, parts)
        total = h * 3600 + m * 60 + s + (ms / 1000.0)
        return int(total * fps)
    except:
        return 0

def update_item_index(self, context):
    scene = context.scene
    if getattr(scene, "ttag_is_syncing_from_timeline", False): return
    if not getattr(scene, "ttag_live_sync", False): return
    
    active_preset = get_active_preset(scene)
    if self != active_preset: return

    idx = self.active_item_index
    if 0 <= idx < len(self.items):
        scene.frame_current = self.items[idx].frame

@persistent
def ttag_sync_handler(scene):
    if not getattr(scene, "ttag_live_sync", False): return
    preset = get_active_preset(scene)
    if not preset or len(preset.items) == 0: return

    curr = scene.frame_current
    best_idx = -1
    max_frame = -999999

    for i, item in enumerate(preset.items):
        if item.frame <= curr:
            if item.frame > max_frame:
                max_frame = item.frame
                best_idx = i
    
    if not getattr(scene, "ttag_is_syncing_from_timeline", False):
        if best_idx != -1 and preset.active_item_index != best_idx:
            scene.ttag_is_syncing_from_timeline = True 
            preset.active_item_index = best_idx
            scene.ttag_is_syncing_from_timeline = False

# =========================================================================
# 3. 数据结构
# =========================================================================

class TTAG_Item(PropertyGroup):
    frame: IntProperty(name="Frame", default=1, description="标签所在的帧号")
    summary: StringProperty(name="Label", default="Tag", description="标签简略标题")
    content: StringProperty(name="Content", default="", description="详细的字幕内容") 
    color: FloatVectorProperty(name="Color", subtype='COLOR', default=(1.0, 1.0, 1.0), min=0.0, max=1.0, description="标签颜色")

class TTAG_Preset(PropertyGroup):
    name: StringProperty(name="Name", default="New Version", update=update_preset_name, description="版本名称")
    items: CollectionProperty(type=TTAG_Item)
    active_item_index: IntProperty(default=0, update=update_item_index)
    storage_file: PointerProperty(name="DB File", type=bpy.types.Text)

# =========================================================================
# 4. 操作符
# =========================================================================

class TTAG_OT_Preset_Action(Operator):
    bl_idname = "ttag.preset_action"
    bl_label = "Preset Action"
    bl_description = "新建或删除一个字幕版本预设"
    action: StringProperty(default="ADD")

    def execute(self, context):
        scene = context.scene
        if self.action == "ADD":
            new_preset = scene.ttag_presets.add()
            count = len(scene.ttag_presets)
            name = f"Version_{count}"
            new_preset.name = name
            scene.ttag_active_preset_index = count - 1
            fname = f"TTAG_DB_{name}.json"
            if fname not in bpy.data.texts:
                new_preset.storage_file = bpy.data.texts.new(fname)
            else:
                new_preset.storage_file = bpy.data.texts[fname]
                load_preset_data(new_preset)
        elif self.action == "REMOVE":
            if len(scene.ttag_presets) > 0:
                idx = scene.ttag_active_preset_index
                preset_to_remove = scene.ttag_presets[idx]
                file_ref = preset_to_remove.storage_file
                if file_ref:
                    file_name = file_ref.name
                    bpy.data.texts.remove(file_ref, do_unlink=True)
                    self.report({'INFO'}, f"已清除后台文件: {file_name}")
                scene.ttag_presets.remove(idx)
                scene.ttag_active_preset_index = max(0, idx - 1)
        return {'FINISHED'}

class TTAG_OT_Load_From_DB(Operator):
    bl_idname = "ttag.load_from_db"
    bl_label = "从数据库加载"
    bl_description = "如果你手动修改了后台文本文件，点击此按钮刷新列表"
    def execute(self, context):
        preset = get_active_preset(context.scene)
        if preset and preset.storage_file:
            load_preset_data(preset)
            self.report({'INFO'}, "已刷新数据")
        return {'FINISHED'}

class TTAG_OT_Copy_Clipboard(Operator):
    bl_idname = "ttag.copy_clipboard"
    bl_label = "复制"
    bl_description = "将当前选中标签的文本内容复制到系统剪贴板"
    def execute(self, context):
        preset = get_active_preset(context.scene)
        if not preset or len(preset.items) == 0: return {'CANCELLED'}
        item = preset.items[preset.active_item_index]
        context.window_manager.clipboard = item.content
        self.report({'INFO'}, "已复制内容")
        return {'FINISHED'}

class TTAG_OT_Paste_Clipboard(Operator):
    bl_idname = "ttag.paste_clipboard"
    bl_label = "粘贴"
    bl_description = "将剪贴板内容覆盖到当前标签，并自动保存"
    def execute(self, context):
        preset = get_active_preset(context.scene)
        if not preset or len(preset.items) == 0: return {'CANCELLED'}
        content = context.window_manager.clipboard
        if content is None: return {'CANCELLED'}
        item = preset.items[preset.active_item_index]
        item.content = content
        save_preset_data(preset)
        self.report({'INFO'}, "已粘贴并保存")
        return {'FINISHED'}

class TTAG_OT_List_Action(Operator):
    bl_idname = "ttag.list_action"
    bl_label = "List Action"
    bl_description = "列表操作：添加、删除或移动标签"
    action: StringProperty(default="ADD")

    def execute(self, context):
        scene = context.scene
        preset = get_active_preset(scene)
        if not preset: return {'CANCELLED'}
        list_len = len(preset.items)
        idx = preset.active_item_index

        if self.action == "ADD":
            item = preset.items.add()
            item.frame = scene.frame_current
            item.summary = f"F{item.frame}"
            item.color = scene.ttag_default_color
            item.content = "" 
            preset.active_item_index = list_len 
        elif self.action == "REMOVE":
            if list_len > 0:
                preset.items.remove(idx)
                preset.active_item_index = max(0, idx - 1)
        elif self.action == "UP":
            if idx > 0:
                preset.items.move(idx, idx - 1)
                preset.active_item_index -= 1 
        elif self.action == "DOWN":
            if idx < list_len - 1:
                preset.items.move(idx, idx + 1)
                preset.active_item_index += 1 
        save_preset_data(preset)
        return {'FINISHED'}

class TTAG_OT_Save_UI_Changes(Operator):
    bl_idname = "ttag.save_ui"
    bl_label = "Save Changes"
    bl_description = "将列表中的修改（如改名、改色）强制保存到后台数据库文件"
    def execute(self, context):
        preset = get_active_preset(context.scene)
        if preset: 
            save_preset_data(preset)
            self.report({'INFO'}, "数据已保存")
        return {'FINISHED'}

class TTAG_OT_Sort_By_Frame(Operator):
    bl_idname = "ttag.sort_by_frame"
    bl_label = "排序"
    bl_description = "按帧号从小到大重新排列所有标签"
    def execute(self, context):
        preset = get_active_preset(context.scene)
        if not preset: return {'CANCELLED'}
        n = len(preset.items)
        for i in range(n):
            min_idx = i
            for j in range(i + 1, n):
                if preset.items[j].frame < preset.items[min_idx].frame:
                    min_idx = j
            if min_idx != i:
                preset.items.move(min_idx, i)
        save_preset_data(preset)
        return {'FINISHED'}

class TTAG_OT_Export_SRT(Operator, ExportHelper):
    """
    [V16.0] SRT 导出功能：支持文件浏览器选择保存路径
    """
    bl_idname = "ttag.export_srt"
    bl_label = "导出 SRT 文件"
    bl_description = "将当前列表导出为外部 SRT 文件"
    
    # ExportHelper 属性
    filename_ext = ".srt"
    filter_glob: StringProperty(default="*.srt", options={'HIDDEN'})

    def execute(self, context):
        scene = context.scene
        preset = get_active_preset(scene)
        if not preset: return {'CANCELLED'}
        
        fps = scene.render.fps / scene.render.fps_base
        filepath = self.filepath
        
        sorted_items = sorted(preset.items, key=lambda x: x.frame)
        srt_content = ""
        counter = 1
        
        for i, item in enumerate(sorted_items):
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
            self.report({'ERROR'}, f"写入文件失败: {str(e)}")
            return {'CANCELLED'}
            
        return {'FINISHED'}

class TTAG_OT_Import_SRT(Operator, ImportHelper):
    bl_idname = "ttag.import_srt"
    bl_label = "导入 SRT 文件"
    bl_description = "选择一个外部 .srt 文件导入，将自动按帧率转换时间码"
    
    # ImportHelper 属性
    filter_glob: StringProperty(default="*.srt", options={'HIDDEN'})
    filename_ext: StringProperty(default=".srt", options={'HIDDEN'})

    def execute(self, context):
        scene = context.scene
        preset = get_active_preset(scene)
        if not preset: 
            self.report({'ERROR'}, "请先创建一个版本预设")
            return {'CANCELLED'}
        
        filepath = self.filepath
        if not os.path.exists(filepath):
            self.report({'ERROR'}, "文件不存在")
            return {'CANCELLED'}

        try:
            # 尝试使用 utf-8-sig 以兼容带 BOM 的文件
            with open(filepath, 'r', encoding='utf-8-sig') as f:
                raw_text = f.read()
        except Exception as e:
            self.report({'ERROR'}, f"读取文件失败: {str(e)}")
            return {'CANCELLED'}

        fps = scene.render.fps / scene.render.fps_base
        pattern = re.compile(r'(\d+)\s*\n\s*(\d{2}:\d{2}:\d{2}[,:]\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2}[,:]\d{3})\s*\n(.*?)(?=\n\s*\d+\s*\n|\Z)', re.DOTALL)
        matches = pattern.findall(raw_text)
        
        if not matches:
            self.report({'WARNING'}, "未识别到有效的 SRT 内容")
            return {'CANCELLED'}
        
        preset.items.clear()
        for match in matches:
            start_tc = match[1]
            content = match[3].strip()
            frame = timecode_to_frame(start_tc, fps)
            item = preset.items.add()
            item.frame = frame
            item.content = content
            item.summary = f"F{frame}"
            item.color = scene.ttag_default_color
            
        save_preset_data(preset)
        self.report({'INFO'}, f"成功导入 {len(matches)} 条字幕")
        return {'FINISHED'}

class TTAG_OT_Generate_Keyframes(Operator):
    bl_idname = "ttag.generate_keyframes"
    bl_label = "烘焙当前版本"
    bl_description = "将当前版本的所有标签生成为3D物体。不同版本会生成独立的根物体"
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
        preset = get_active_preset(scene)
        if not preset: return {'CANCELLED'}
        save_preset_data(preset) 
        safe_name = preset.name.strip().replace(" ", "_")
        if not safe_name: safe_name = "Unnamed"
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
                for child in list(root_empty.children): bpy.data.objects.remove(child, do_unlink=True)
            if root_empty.name not in target_coll.objects: target_coll.objects.link(root_empty)
        else:
            root_empty = bpy.data.objects.new(root_name, None)
            root_empty.empty_display_type = 'PLAIN_AXES'
            target_coll.objects.link(root_empty)
        
        sorted_items = sorted(preset.items, key=lambda x: x.frame)
        for i, item in enumerate(sorted_items):
            full_text = item.content
            if not full_text: full_text = " "
            font_curve = bpy.data.curves.new(type="FONT", name=f"TTAG_Data_{item.frame}")
            font_curve.body = full_text
            font_curve.align_x = 'CENTER'
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
        self.report({'INFO'}, f"[{preset.name}] 烘焙完成")
        return {'FINISHED'}

# =========================================================================
# 5. UI PANEL
# =========================================================================

class TTAG_UL_List(UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        split = layout.split(factor=0.12)
        split.prop(item, "color", text="", icon_only=True, emboss=True)
        right_area = split.row(align=True)
        # [V16.0 调整] 分割比例 0.5
        sub_split = right_area.split(factor=0.5)
        sub_split.prop(item, "frame", text="", emboss=False)
        sub_split.prop(item, "summary", text="", emboss=False)

class TTAG_PT_Panel(Panel):
    bl_label = "Timeline Tags Pro V16"
    bl_idname = "TTAG_PT_main"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Tags Pro"

    def draw(self, context):
        layout = self.layout
        scene = context.scene

        row = layout.row(align=True)
        row.prop(scene, "ttag_live_sync", text="跟随时间轴", icon='TIME', toggle=True)
        row.operator("ttag.sort_by_frame", text="", icon='SORT_ASC')
        layout.separator()

        box = layout.box()
        row = box.row()
        row.label(text="版本管理 (Presets):", icon='PRESET')
        row = box.row(align=True)
        if len(scene.ttag_presets) == 0:
            row.operator("ttag.preset_action", text="新建版本", icon='ADD').action = "ADD"
        else:
            active_preset = get_active_preset(scene)
            if active_preset:
                row.prop(active_preset, "name", text="")
                row.operator("ttag.load_from_db", text="", icon='FILE_REFRESH')
            row.separator()
            row.operator("ttag.preset_action", text="", icon='ADD').action = "ADD"
            row.operator("ttag.preset_action", text="", icon='TRASH').action = "REMOVE"
            sub = row.row(align=True)
            sub.prop(scene, "ttag_active_preset_index", text="Idx")

        active_preset = get_active_preset(scene)
        if not active_preset: return

        layout.separator()

        row = layout.row(align=True)
        row.label(text="新建颜色:", icon='COLOR')
        sub = row.row()
        sub.scale_x = 0.5 
        sub.prop(scene, "ttag_default_color", text="")
        row.operator("ttag.save_ui", text="保存到数据库", icon='FILE_TICK') 

        row = layout.row()
        row.template_list("TTAG_UL_List", "", active_preset, "items", active_preset, "active_item_index")
        
        col = row.column(align=True)
        col.operator("ttag.list_action", icon='ADD', text="").action = "ADD"
        col.operator("ttag.list_action", icon='REMOVE', text="").action = "REMOVE"
        col.separator()
        col.operator("ttag.list_action", icon='TRIA_UP', text="").action = "UP"
        col.operator("ttag.list_action", icon='TRIA_DOWN', text="").action = "DOWN"

        layout.separator()
        
        # Safe access
        safe_idx = active_preset.active_item_index
        if len(active_preset.items) > 0:
            if safe_idx >= len(active_preset.items): safe_idx = len(active_preset.items) - 1
            if safe_idx < 0: safe_idx = 0
            
            item = active_preset.items[safe_idx]
            box = layout.box()
            col = box.column(align=True)
            row_io = col.row(align=True)
            row_io.scale_y = 1.4
            
            op_copy = row_io.operator("ttag.copy_clipboard", icon='COPYDOWN', text="复制")
            op_paste = row_io.operator("ttag.paste_clipboard", icon='PASTEDOWN', text="粘贴")
            col.separator()
            
            sub = col.box()
            header = sub.row(align=True)
            header.label(text="[预览]")
            header.prop(scene, "ttag_preview_rows", text="行")
            
            lines = item.content.split('\n')
            if not item.content.strip(): sub.label(text="(空)", icon='INFO')
            else:
                limit = scene.ttag_preview_rows
                for i, txt in enumerate(lines[:limit]): sub.label(text=txt)
                if len(lines) > limit: sub.label(text="...")

        layout.separator()
        
        box = layout.box()
        box.label(text="输出:", icon='OUTPUT')
        row = box.row(align=True)
        row.operator("ttag.export_srt", icon='TEXT', text="导出 SRT")
        row.operator("ttag.import_srt", icon='IMPORT', text="导入 SRT")
        
        row = box.row()
        row.prop(scene, "ttag_overwrite", text="覆盖旧烘焙")
        box.operator("ttag.generate_keyframes", icon='SHADING_BBOX', text=f"烘焙: {active_preset.name}")

# =========================================================================
# 6. 注册
# =========================================================================

classes = (
    TTAG_Item, TTAG_Preset,
    TTAG_OT_Preset_Action, TTAG_OT_Load_From_DB, TTAG_OT_Export_SRT, TTAG_OT_Import_SRT,
    TTAG_OT_List_Action, TTAG_OT_Copy_Clipboard, TTAG_OT_Paste_Clipboard, TTAG_OT_Save_UI_Changes,
    TTAG_OT_Sort_By_Frame, TTAG_OT_Generate_Keyframes,
    TTAG_UL_List, TTAG_PT_Panel,
)

def register():
    for cls in classes: bpy.utils.register_class(cls)
    bpy.types.Scene.ttag_presets = CollectionProperty(type=TTAG_Preset)
    
    bpy.types.Scene.ttag_active_preset_index = IntProperty(
        min=0, update=validate_preset_index,
        description="当前激活的预设版本索引"
    )
    
    bpy.types.Scene.ttag_overwrite = BoolProperty(
        name="Overwrite", 
        default=True,
        description="勾选: 更新现有的 Root 物体 (保留位移/动画)\n不勾选: 创建全新的 v1, v2... 物体 (保留历史版本)"
    )
    bpy.types.Scene.ttag_live_sync = BoolProperty(name="Sync", default=True, description="开启: 列表随时间轴自动滚动，点击列表跳转时间轴")
    bpy.types.Scene.ttag_is_syncing_from_timeline = BoolProperty(default=False)
    bpy.types.Scene.ttag_default_color = FloatVectorProperty(name="Default Color", subtype='COLOR', default=(1.0, 1.0, 1.0), min=0.0, max=1.0, description="新建标签的默认颜色")
    bpy.types.Scene.ttag_preview_rows = IntProperty(name="Preview Rows", default=5, min=1, max=50, description="预览框最大显示行数")
    if ttag_sync_handler not in bpy.app.handlers.frame_change_post: bpy.app.handlers.frame_change_post.append(ttag_sync_handler)

def unregister():
    if ttag_sync_handler in bpy.app.handlers.frame_change_post: bpy.app.handlers.frame_change_post.remove(ttag_sync_handler)
    for cls in reversed(classes): bpy.utils.unregister_class(cls)
    del bpy.types.Scene.ttag_presets
    del bpy.types.Scene.ttag_active_preset_index
    del bpy.types.Scene.ttag_overwrite
    del bpy.types.Scene.ttag_live_sync
    del bpy.types.Scene.ttag_is_syncing_from_timeline
    del bpy.types.Scene.ttag_default_color
    del bpy.types.Scene.ttag_preview_rows

if __name__ == "__main__":
    register()