bl_info = {
    "name": "Timeline Tags Pro V14.2",
    "author": "Dev_BlenderPy",
    "version": (14, 2),
    "blender": (3, 0, 0),
    "location": "View3D > Sidebar > Tags Pro",
    "description": "精简UI版：移除直接编辑框，保留内容预览、双向同步与SRT支持。",
    "category": "Animation",
}

import bpy
import json
import re
import math
import time
from bpy.props import IntProperty, StringProperty, CollectionProperty, PointerProperty, BoolProperty, FloatVectorProperty
from bpy.types import PropertyGroup, UIList, Operator, Panel
from bpy.app.handlers import persistent

# =========================================================================
# 1. 核心逻辑：数据序列化 (JSON Serialization)
# =========================================================================

def save_preset_data(preset):
    """将当前预设的所有标签数据写入到唯一的 JSON 文本文件中"""
    if not preset.storage_file:
        return

    data_list = []
    # 按帧号排序保存
    sorted_items = sorted(preset.items, key=lambda x: x.frame)
    
    for item in sorted_items:
        entry = {
            "frame": item.frame,
            "summary": item.summary,
            "content": item.content,
            "color": (item.color[0], item.color[1], item.color[2])
        }
        data_list.append(entry)
    
    # 写入 JSON 到 Blender 文本块
    preset.storage_file.clear()
    preset.storage_file.write(json.dumps(data_list, indent=2, ensure_ascii=False))

def load_preset_data(preset):
    """从 JSON 文本文件中读取数据并重建列表"""
    if not preset.storage_file:
        return

    raw_text = preset.storage_file.as_string()
    if not raw_text.strip():
        return

    try:
        data_list = json.loads(raw_text)
    except json.JSONDecodeError:
        print("TTAG Error: JSON file is corrupted.")
        return

    preset.items.clear()
    
    for entry in data_list:
        item = preset.items.add()
        item.frame = entry.get("frame", 1)
        item.summary = entry.get("summary", "Tag")
        item.content = entry.get("content", "")
        col = entry.get("color", (1.0, 1.0, 1.0))
        item.color = (col[0], col[1], col[2])

# =========================================================================
# 2. 辅助函数 & 同步逻辑
# =========================================================================

def get_active_preset(scene):
    if len(scene.ttag_presets) > 0:
        if scene.ttag_active_preset_index >= len(scene.ttag_presets):
            scene.ttag_active_preset_index = len(scene.ttag_presets) - 1
        if scene.ttag_active_preset_index < 0:
            scene.ttag_active_preset_index = 0
        return scene.ttag_presets[scene.ttag_active_preset_index]
    return None

def frame_to_timecode(frame, fps):
    total_seconds = frame / fps
    hours = int(total_seconds // 3600)
    minutes = int((total_seconds % 3600) // 60)
    seconds = int(total_seconds % 60)
    milliseconds = int((total_seconds - int(total_seconds)) * 1000)
    return f"{hours:02}:{minutes:02}:{seconds:02},{milliseconds:03}"

def timecode_to_frame(timecode, fps):
    try:
        parts = timecode.replace(',', ':').replace('.', ':').split(':') 
        h = int(parts[0])
        m = int(parts[1])
        s = int(parts[2])
        ms = int(parts[3])
        total_seconds = h * 3600 + m * 60 + s + (ms / 1000.0)
        return int(total_seconds * fps)
    except:
        return 0

def update_preset_name(self, context):
    """当预设名称修改时，自动重命名对应的数据库文件"""
    if self.storage_file:
        safe_name = self.name.strip().replace(" ", "_")
        if not safe_name: safe_name = "Unnamed"
        self.storage_file.name = f"TTAG_DB_{safe_name}.json"

def update_item_index(self, context):
    """[列表点击 -> 跳转时间轴]"""
    scene = context.scene
    if getattr(scene, "ttag_is_syncing_from_timeline", False): return
    if not getattr(scene, "ttag_live_sync", False): return
    
    active_preset = get_active_preset(scene)
    if self != active_preset: return

    idx = self.active_item_index
    if 0 <= idx < len(self.items):
        target_frame = self.items[idx].frame
        scene.frame_current = target_frame

@persistent
def ttag_sync_handler(scene):
    """[时间轴播放 -> 高亮列表]"""
    if not getattr(scene, "ttag_live_sync", False): return
    
    preset = get_active_preset(scene)
    if not preset or len(preset.items) == 0: return

    curr_frame = scene.frame_current
    best_index = -1
    max_frame_found = -999999

    for i, item in enumerate(preset.items):
        if item.frame <= curr_frame:
            if item.frame > max_frame_found:
                max_frame_found = item.frame
                best_index = i
    
    if not getattr(scene, "ttag_is_syncing_from_timeline", False):
        if best_index != -1 and preset.active_item_index != best_index:
            scene.ttag_is_syncing_from_timeline = True 
            preset.active_item_index = best_index
            scene.ttag_is_syncing_from_timeline = False

# =========================================================================
# 3. 数据结构 (Data Structures)
# =========================================================================

class TTAG_Item(PropertyGroup):
    frame: IntProperty(name="Frame", default=1)
    summary: StringProperty(name="Label", default="Tag")
    content: StringProperty(name="Content", default="") 
    color: FloatVectorProperty(
        name="Color", subtype='COLOR', default=(1.0, 1.0, 1.0), min=0.0, max=1.0
    )

class TTAG_Preset(PropertyGroup):
    name: StringProperty(name="Name", default="New Version", update=update_preset_name)
    items: CollectionProperty(type=TTAG_Item)
    active_item_index: IntProperty(default=0, update=update_item_index)
    storage_file: PointerProperty(name="DB File", type=bpy.types.Text)

# =========================================================================
# 4. 操作符 (Operators)
# =========================================================================

class TTAG_OT_Preset_Action(Operator):
    bl_idname = "ttag.preset_action"
    bl_label = "Preset Action"
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
                scene.ttag_presets.remove(scene.ttag_active_preset_index)
                scene.ttag_active_preset_index = max(0, scene.ttag_active_preset_index - 1)
        
        return {'FINISHED'}

class TTAG_OT_Load_From_DB(Operator):
    bl_idname = "ttag.load_from_db"
    bl_label = "从数据库加载"
    bl_description = "重新读取 JSON 文件并刷新列表"
    def execute(self, context):
        preset = get_active_preset(context.scene)
        if preset and preset.storage_file:
            load_preset_data(preset)
            self.report({'INFO'}, "已重新加载")
        return {'FINISHED'}

class TTAG_OT_Copy_Clipboard(Operator):
    bl_idname = "ttag.copy_clipboard"
    bl_label = "复制"
    bl_description = "仅复制当前标签文本"
    def execute(self, context):
        preset = get_active_preset(context.scene)
        if not preset or len(preset.items) == 0: return {'CANCELLED'}
        item = preset.items[preset.active_item_index]
        context.window_manager.clipboard = item.content
        self.report({'INFO'}, "已复制")
        return {'FINISHED'}

class TTAG_OT_Paste_Clipboard(Operator):
    bl_idname = "ttag.paste_clipboard"
    bl_label = "粘贴"
    bl_description = "粘贴文本到当前标签"
    bl_options = {'REGISTER', 'UNDO'}
    def execute(self, context):
        preset = get_active_preset(context.scene)
        if not preset or len(preset.items) == 0: return {'CANCELLED'}
        content = context.window_manager.clipboard
        if content is None: return {'CANCELLED'}
        item = preset.items[preset.active_item_index]
        item.content = content
        save_preset_data(preset)
        self.report({'INFO'}, "已粘贴")
        return {'FINISHED'}

class TTAG_OT_List_Action(Operator):
    bl_idname = "ttag.list_action"
    bl_label = "List Action"
    bl_options = {'REGISTER', 'UNDO'}
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
            item.content = "" # 默认空白
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
    bl_description = "手动将列表数据保存到数据库"
    def execute(self, context):
        preset = get_active_preset(context.scene)
        if preset: 
            save_preset_data(preset)
            self.report({'INFO'}, "已保存")
        return {'FINISHED'}

class TTAG_OT_Sort_By_Frame(Operator):
    bl_idname = "ttag.sort_by_frame"
    bl_label = "排序"
    bl_options = {'REGISTER', 'UNDO'}
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

class TTAG_OT_Export_SRT(Operator):
    bl_idname = "ttag.export_srt"
    bl_label = "导出 SRT"
    bl_description = "导出为SRT字幕文本"
    def execute(self, context):
        scene = context.scene
        preset = get_active_preset(scene)
        if not preset: return {'CANCELLED'}
        fps = scene.render.fps / scene.render.fps_base
        export_name = f"Export_{preset.name}.srt"
        if export_name in bpy.data.texts: bpy.data.texts[export_name].clear()
        else: bpy.data.texts.new(export_name)
        txt_block = bpy.data.texts[export_name]
        
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
        txt_block.write(srt_content)
        for area in context.screen.areas:
            if area.type == 'TEXT_EDITOR':
                area.spaces[0].text = txt_block
        self.report({'INFO'}, f"已导出: {export_name}")
        return {'FINISHED'}

class TTAG_OT_Import_SRT(Operator):
    bl_idname = "ttag.import_srt"
    bl_label = "导入 SRT"
    bl_description = "从文本块导入字幕"
    bl_options = {'REGISTER', 'UNDO'}
    source_text: StringProperty(name="Source Text Block")
    def execute(self, context):
        scene = context.scene
        preset = get_active_preset(scene)
        if not preset: return {'CANCELLED'}
        if self.source_text not in bpy.data.texts: 
            self.report({'ERROR'}, "未找到源文本块")
            return {'CANCELLED'}
        raw_text = bpy.data.texts[self.source_text].as_string()
        fps = scene.render.fps / scene.render.fps_base
        pattern = re.compile(r'(\d+)\s*\n\s*(\d{2}:\d{2}:\d{2}[,:]\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2}[,:]\d{3})\s*\n(.*?)(?=\n\s*\d+\s*\n|\Z)', re.DOTALL)
        matches = pattern.findall(raw_text)
        if not matches:
            self.report({'WARNING'}, "无效的 SRT 格式")
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
        self.report({'INFO'}, f"导入 {len(matches)} 条字幕")
        return {'FINISHED'}
    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)
    def draw(self, context):
        layout = self.layout
        layout.prop_search(self, "source_text", bpy.data, "texts")

class TTAG_OT_Generate_Keyframes(Operator):
    bl_idname = "ttag.generate_keyframes"
    bl_label = "烘焙当前版本"
    bl_description = "生成3D文字"
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
        root_empty = None
        if coll_name in bpy.data.collections:
            target_coll = bpy.data.collections[coll_name]
        else:
            target_coll = bpy.data.collections.new(coll_name)
            scene.collection.children.link(target_coll)

        if root_name in bpy.data.objects:
            root_empty = bpy.data.objects[root_name]
            if scene.ttag_overwrite:
                for child in list(root_empty.children):
                    bpy.data.objects.remove(child, do_unlink=True)
            if root_empty.name not in target_coll.objects:
                target_coll.objects.link(root_empty)
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
# 5. 界面面板 (UI Panel)
# =========================================================================

class TTAG_UL_List(UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        split = layout.split(factor=0.12)
        split.prop(item, "color", text="", icon_only=True, emboss=True)
        right_area = split.row(align=True)
        sub_split = right_area.split(factor=0.33)
        sub_split.prop(item, "frame", text="", emboss=False)
        sub_split.prop(item, "summary", text="", emboss=False)

class TTAG_PT_Panel(Panel):
    bl_label = "Timeline Tags Pro V14.2"
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
            if scene.ttag_active_preset_index < 0: scene.ttag_active_preset_index = 0
            if scene.ttag_active_preset_index >= len(scene.ttag_presets): 
                scene.ttag_active_preset_index = max(0, len(scene.ttag_presets)-1)
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
        
        if active_preset.active_item_index >= 0 and len(active_preset.items) > 0:
            item = active_preset.items[active_preset.active_item_index]
            box = layout.box()
            col = box.column(align=True)
            row_io = col.row(align=True)
            row_io.scale_y = 1.4
            
            op_copy = row_io.operator("ttag.copy_clipboard", icon='COPYDOWN', text="复制内容")
            op_paste = row_io.operator("ttag.paste_clipboard", icon='PASTEDOWN', text="粘贴内容")
            col.separator()
            
            # 移除了文本编辑框，仅保留预览
            sub = col.box()
            header = sub.row(align=True)
            header.label(text="[内容预览]")
            header.prop(scene, "ttag_preview_rows", text="行数")
            
            lines = item.content.split('\n')
            if not item.content.strip(): sub.label(text="(空内容)", icon='INFO')
            else:
                limit = scene.ttag_preview_rows
                for i, txt in enumerate(lines[:limit]): sub.label(text=txt)
                if len(lines) > limit: sub.label(text="...")

        layout.separator()
        
        box = layout.box()
        box.label(text="IO & Bake:", icon='OUTPUT')
        row = box.row(align=True)
        row.operator("ttag.export_srt", icon='TEXT', text="导出 SRT")
        row.operator("ttag.import_srt", icon='IMPORT', text="导入 SRT")
        row = box.row()
        row.prop(scene, "ttag_overwrite", text="覆盖旧烘焙")
        box.operator("ttag.generate_keyframes", icon='SHADING_BBOX', text=f"烘焙: {active_preset.name}")

# =========================================================================
# 6. 注册 (Registration)
# =========================================================================

classes = (
    TTAG_Item, TTAG_Preset,
    TTAG_OT_Preset_Action, 
    TTAG_OT_Load_From_DB, 
    TTAG_OT_Export_SRT, TTAG_OT_Import_SRT,
    TTAG_OT_List_Action, TTAG_OT_Copy_Clipboard, TTAG_OT_Paste_Clipboard, TTAG_OT_Save_UI_Changes,
    TTAG_OT_Sort_By_Frame, TTAG_OT_Generate_Keyframes,
    TTAG_UL_List, TTAG_PT_Panel,
)

def register():
    for cls in classes: bpy.utils.register_class(cls)
    bpy.types.Scene.ttag_presets = CollectionProperty(type=TTAG_Preset)
    bpy.types.Scene.ttag_active_preset_index = IntProperty(min=0) 
    bpy.types.Scene.ttag_overwrite = BoolProperty(name="Overwrite", default=True, description="勾选: 更新现有物体")
    bpy.types.Scene.ttag_live_sync = BoolProperty(name="Sync", default=True)
    bpy.types.Scene.ttag_is_syncing_from_timeline = BoolProperty(default=False)
    bpy.types.Scene.ttag_default_color = FloatVectorProperty(name="Default Color", subtype='COLOR', default=(1.0, 1.0, 1.0), min=0.0, max=1.0)
    bpy.types.Scene.ttag_preview_rows = IntProperty(name="Preview Rows", default=5, min=1, max=50)
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