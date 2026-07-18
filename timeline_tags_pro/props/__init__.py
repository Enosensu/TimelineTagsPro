"""props - PropertyGroups and update callbacks.

Depends on: core (for serialize/sync), but import is deferred to avoid
circular imports at module load.
"""
import bpy
from bpy.props import (
    IntProperty,
    StringProperty,
    CollectionProperty,
    PointerProperty,
    BoolProperty,
    FloatVectorProperty,
    EnumProperty,
    FloatProperty,
)
from bpy.types import PropertyGroup


# =========================================================================
# Update callbacks (defined here so PropertyGroups can reference them)
# =========================================================================
def update_source_text_ptr(self, context):
    """Called when user picks a different source Text datablock.

    V46.0 fix: cancel any pending debounce save before loading, to
    avoid a stale 0.8s timer firing into the new datablock.
    """
    from ..core.serialize import cancel_pending_save_timer, load_runtime_data
    cancel_pending_save_timer()
    load_runtime_data(self, operator=None)


def update_item_data(self, context):
    from ..core.serialize import auto_save_debounced
    auto_save_debounced(context.scene)


def update_settings(self, context):
    from ..core.serialize import auto_save_debounced
    auto_save_debounced(context.scene)


def update_line_body(self, context):
    if getattr(context.scene, "ttag_is_loading", False):
        return
    from ..core.serialize import auto_save_debounced
    auto_save_debounced(context.scene)


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
    ms = int((total - int(total)) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"


def timecode_to_frame(timecode, fps):
    try:
        h, m, s = timecode.split(":")
        total_seconds = int(h) * 3600 + int(m) * 60 + float(s)
        return int(round(total_seconds * fps))
    except Exception:
        return 1


def update_item_index(self, context):
    """Live-sync: changing the active item moves the timeline cursor.

    V46.0 fix: ttag_is_syncing_from_timeline is now a stable guard set
    by ttag_sync_handler for the duration of its execution, so the
    frame -> index -> frame feedback loop is broken.
    """
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


# =========================================================================
# line_count get/set
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
            from ..core.serialize import auto_save_debounced
            auto_save_debounced(bpy.context.scene)
    except Exception:
        pass


# =========================================================================
# PropertyGroups
# =========================================================================
class TTAG_TextLine(PropertyGroup):
    body: StringProperty(name="Body", default="", update=update_line_body)


class TTAG_Item(PropertyGroup):
    frame: IntProperty(name="Frame", default=1, update=update_item_data)
    summary: StringProperty(name="Label", default="Tag", update=update_item_data)
    content: StringProperty(name="Content", default="")
    text_lines: CollectionProperty(type=TTAG_TextLine)
    color: FloatVectorProperty(
        name="Color",
        subtype='COLOR',
        default=(1.0, 1.0, 1.0),
        min=0.0,
        max=1.0,
        update=update_item_data,
    )

    line_count: IntProperty(
        name="Line Count",
        description="调整行数（不会删除已输入文字的行）",
        default=1,
        min=1,
        get=get_line_count,
        set=set_line_count,
    )


# Order matters: TTAG_TextLine must be registered before TTAG_Item
# (CollectionProperty(type=TTAG_TextLine) requires TTAG_TextLine to exist).
PROPERTY_GROUPS = [
    TTAG_TextLine,
    TTAG_Item,
]


# =========================================================================
# Scene-level properties
# =========================================================================
def register_scene_properties():
    Scene = bpy.types.Scene
    Scene.ttag_source_text = PointerProperty(
        name="Data Source",
        type=bpy.types.Text,
        description="存储标签数据的文本块",
        update=update_source_text_ptr,
    )
    Scene.ttag_runtime_items = CollectionProperty(type=TTAG_Item)
    Scene.ttag_is_loading = BoolProperty(default=False)
    Scene.ttag_is_saving = BoolProperty(default=False)  # V46.0 write lock
    Scene.ttag_active_item_index = IntProperty(
        min=0,
        update=update_item_index,
        description="当前激活的标签索引",
    )
    Scene.ttag_overwrite = BoolProperty(
        name="Overwrite 3D",
        default=True,
        description="覆盖: 重新生成3D文字集合",
        update=update_settings,
    )
    Scene.ttag_overwrite_markers = BoolProperty(
        name="Overwrite Markers",
        default=True,
        description="覆盖标记: 勾选则删除现有所有标记后重新生成；不勾选则在空闲位置追加新标记",
        update=update_settings,
    )
    Scene.ttag_live_sync = BoolProperty(
        name="Sync",
        default=True,
        description="开启: 列表随时间轴自动滚动",
        update=update_settings,
    )
    Scene.ttag_is_syncing_from_timeline = BoolProperty(default=False)
    Scene.ttag_lock_sync = BoolProperty(default=False)
    Scene.ttag_default_color = FloatVectorProperty(
        name="Default Color",
        subtype='COLOR',
        default=(1.0, 1.0, 1.0),
        min=0.0,
        max=1.0,
        update=update_settings,
    )
    Scene.ttag_global_align = EnumProperty(
        name="Global Align",
        items=[
            ('LEFT', "Left", "左对齐", 'ALIGN_LEFT', 0),
            ('CENTER', "Center", "居中", 'ALIGN_CENTER', 1),
            ('RIGHT', "Right", "右对齐", 'ALIGN_RIGHT', 2),
        ],
        default='CENTER',
        update=update_settings,
    )
    Scene.ttag_font_path = StringProperty(
        name="烘焙字体",
        description="烘焙字体文件路径",
        subtype='FILE_PATH',
        update=update_settings,
    )
    Scene.ttag_line_spacing = FloatProperty(
        name="行距",
        default=1.0,
        description="文字行间距",
        update=update_settings,
    )


def unregister_scene_properties():
    Scene = bpy.types.Scene
    for attr in (
        "ttag_source_text", "ttag_runtime_items", "ttag_is_loading",
        "ttag_is_saving", "ttag_active_item_index", "ttag_overwrite",
        "ttag_overwrite_markers", "ttag_live_sync",
        "ttag_is_syncing_from_timeline", "ttag_lock_sync",
        "ttag_default_color", "ttag_global_align", "ttag_font_path",
        "ttag_line_spacing",
    ):
        try:
            delattr(Scene, attr)
        except AttributeError:
            pass
