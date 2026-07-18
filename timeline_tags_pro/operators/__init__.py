"""operators - all TTAG_OT_* operators.

Each operator module imports what it needs from `core` and `props`.
"""
from .insert import (
    TTAG_OT_Insert_Top_Line,
    TTAG_OT_Insert_Newline,
    TTAG_OT_Remove_Text_Line,
)
from .clipboard import TTAG_OT_Copy_Clipboard, TTAG_OT_Paste_Clipboard
from .list_action import TTAG_OT_List_Action
from .reload import TTAG_OT_Reload_From_Text
from .sort_rename import TTAG_OT_Sort_By_Frame, TTAG_OT_Rename_By_Frame
from .io_srt import TTAG_OT_Export_SRT, TTAG_OT_Import_SRT
from .bake_3d import TTAG_OT_Bake_3D_Text
from .bake_markers import TTAG_OT_Bake_Timeline_Markers
from .sync_timeline import TTAG_OT_Sync_From_Timeline

# Order: property groups registered separately; operators here are
# independent of each other, so order is not critical.
OPERATORS = [
    TTAG_OT_Insert_Top_Line,
    TTAG_OT_Insert_Newline,
    TTAG_OT_Remove_Text_Line,
    TTAG_OT_Copy_Clipboard,
    TTAG_OT_Paste_Clipboard,
    TTAG_OT_List_Action,
    TTAG_OT_Reload_From_Text,
    TTAG_OT_Sort_By_Frame,
    TTAG_OT_Rename_By_Frame,
    TTAG_OT_Export_SRT,
    TTAG_OT_Import_SRT,
    TTAG_OT_Bake_3D_Text,
    TTAG_OT_Bake_Timeline_Markers,
    TTAG_OT_Sync_From_Timeline,
]

__all__ = ["OPERATORS"]
