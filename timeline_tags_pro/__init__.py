"""
Timeline Tags Pro - Modular Refactor (V46.0)
=============================================

This package is the modularized successor of the single-file addon
`TimelineTagsPro.py`. It preserves 100% of the original working logic
while splitting it into cohesive modules for easier maintenance and
extension.

Package layout
--------------
    timeline_tags_pro/
    |-- __init__.py            # Addon entry: bl_info, register/unregister
    |-- core/
    |   |-- __init__.py        # re-exports for convenience
    |   |-- state.py           # Global mutable state (debounce timer)
    |   |-- sync.py            # sync_lines_to_content / sync_content_to_lines
    |   |-- serialize.py       # save / load / repair_invalid_json_text
    |   |-- locks.py           # ReentrancyGuard for read/write locks
    +-- operators/
    |   |-- __init__.py        # OPERATORS registry list
    |   |-- insert.py          # Insert_Top_Line / Insert_Newline / Remove_Text_Line
    |   |-- clipboard.py       # Copy_Clipboard / Paste_Clipboard
    |   |-- list_action.py     # List_Action
    |   |-- reload.py          # Reload_From_Text
    |   |-- sort_rename.py     # Sort_By_Frame / Rename_By_Frame
    |   |-- io_srt.py          # Export_SRT / Import_SRT
    |   |-- bake_3d.py         # Bake_3D_Text (with V46.0 BSOD fixes)
    |   |-- bake_markers.py    # Bake_Timeline_Markers
    |   +-- sync_timeline.py   # Sync_From_Timeline
    +-- ui/
    |   |-- __init__.py        # UI_CLASSES registry list
    |   |-- ulist.py           # TTAG_UL_List
    |   +-- panel.py           # TTAG_PT_Panel
    +-- props/
    |   |-- __init__.py        # PROPERTY_GROUPS registry list
    |   +-- groups.py          # TTAG_TextLine / TTAG_Item / update callbacks
    +-- handlers/
        |-- __init__.py
        +-- frame_change.py    # ttag_sync_handler (with V46.0 feedback-loop fix)

Design principles
-----------------
1. **No logic change without explicit note.** Every V46.0 behavioral fix
   carries a comment header so the diff against the original is auditable.
2. **Single source of truth for registries.** Each subpackage exposes a
   list of its classes; the top-level `register()` iterates them.
3. **No circular imports.** `props` <- `core` <- `operators`/`ui`/`handlers`
   (left imports right). `core` is the lowest layer and imports nothing
   from this package.
4. **Original file preserved.** `TimelineTagsPro.py.orig` is the verbatim
   backup; the in-place `TimelineTagsPro.py` carries the same V46.0 fixes
   for users who prefer the single-file form. This package is the
   recommended future form.

Compatibility note
------------------
Blender only loads ONE addon per `bl_idname`. To avoid double-registration
conflicts, use EITHER this package (`timeline_tags_pro`) OR the single
file (`TimelineTagsPro.py`), not both at once. The single-file version is
kept as a fallback for environments that disallow multi-file addons.
"""

bl_info = {
    "name": "Timeline Tags Pro V46.0 (Modular)",
    "author": "Dev_BlenderPy",
    "version": (46, 0, 0),
    "blender": (3, 0, 0),
    "location": "View3D > Sidebar > Tags Pro",
    "description": "时间轴标签 Pro - 模块化重构版，修复 BSOD (IRQL_NOT_LESS_OR_EQUAL in nvlddmkm.sys)",
    "category": "Animation",
    "doc_url": "",
    "tracker_url": "",
}

# =========================================================================
# Top-level imports - kept minimal; submodules import what they need.
# =========================================================================
import bpy

from .props import PROPERTY_GROUPS
from .operators import OPERATORS
from .ui import UI_CLASSES
from .handlers import register_handlers, unregister_handlers


# =========================================================================
# Register / Unregister
# =========================================================================
def register():
    """Register all property groups, operators, UI classes, and handlers."""
    # 1. Property groups first (operators/UI reference them via PointerProperty)
    for cls in PROPERTY_GROUPS:
        bpy.utils.register_class(cls)

    # 2. Operators
    for cls in OPERATORS:
        bpy.utils.register_class(cls)

    # 3. UI classes (panels, lists)
    for cls in UI_CLASSES:
        bpy.utils.register_class(cls)

    # 4. Scene properties (registered on bpy.types.Scene)
    from .props import register_scene_properties
    register_scene_properties()

    # 5. Handlers (frame_change_post etc.)
    register_handlers()


def unregister():
    """Reverse of register(). Order matters to avoid dangling references."""
    # 5. Handlers
    unregister_handlers()

    # 4. Scene properties
    from .props import unregister_scene_properties
    unregister_scene_properties()

    # 3. UI classes
    for cls in reversed(UI_CLASSES):
        bpy.utils.unregister_class(cls)

    # 2. Operators
    for cls in reversed(OPERATORS):
        bpy.utils.unregister_class(cls)

    # 1. Property groups
    for cls in reversed(PROPERTY_GROUPS):
        bpy.utils.unregister_class(cls)
