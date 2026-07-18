"""Serialization: save/load runtime data to/from Blender Text datablocks.

V46.0 fixes applied here:
- save_runtime_data_immediate: added ttag_is_saving write lock.
- Added cancel_pending_save_timer() for safe text-block switching.
- load_runtime_data: fixed recursive ttag_is_loading flag handling.
"""
import json

import bpy

from .state import get_save_timer, set_save_timer, clear_save_timer
from .sync import sync_lines_to_content, sync_content_to_lines


# =========================================================================
# Save
# =========================================================================
def save_runtime_data_immediate(scene):
    """Save runtime items + settings into the source Text datablock.

    V46.0 fix: added ttag_is_saving write lock. Prevents re-entrant saves
    and avoids text_block.clear()/write() racing with the UI text editor.
    """
    if getattr(scene, "ttag_is_loading", False):
        return
    if getattr(scene, "ttag_is_saving", False):
        return

    text_block = scene.ttag_source_text
    if not text_block:
        return

    scene.ttag_is_saving = True
    try:
        # 1. Serialize tag data
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

        # 2. Serialize global settings
        settings_dict = {
            "overwrite_3d": scene.ttag_overwrite,
            "overwrite_markers": scene.ttag_overwrite_markers,
            "live_sync": scene.ttag_live_sync,
            "default_color": (
                scene.ttag_default_color[0],
                scene.ttag_default_color[1],
                scene.ttag_default_color[2],
            ),
            "global_align": scene.ttag_global_align,
            "font_path": scene.ttag_font_path,
            "line_spacing": scene.ttag_line_spacing,
        }

        final_payload = {
            "version": "V45.0",
            "settings": settings_dict,
            "data": data_list,
        }

        text_block.clear()
        text_block.write(json.dumps(final_payload, indent=2, ensure_ascii=False))
    finally:
        scene.ttag_is_saving = False


def cancel_pending_save_timer():
    """V46.0 fix: cancel any pending debounce save timer.

    Must be called before switching source text blocks, otherwise the
    stale 0.8s timer fires and writes the new block's data back into
    the new block while the user is editing it.
    """
    timer = get_save_timer()
    if timer is not None:
        try:
            if bpy.app.timers.is_registered(timer):
                bpy.app.timers.unregister(timer)
        except Exception:
            pass
        clear_save_timer()


# =========================================================================
# Auto-save (debounced)
# =========================================================================
def auto_save_debounced(scene):
    """Debounced save: 0.8s after the last call.

    Solves the "typing in text fields loses focus" problem.
    """
    # Cancel any previously registered debounce timer.
    cancel_pending_save_timer()

    def _save_task():
        if scene.ttag_source_text:
            save_runtime_data_immediate(scene)
        return None  # one-shot

    set_save_timer(_save_task)
    try:
        bpy.app.timers.register(_save_task, first_interval=0.8)
    except Exception:
        # If registration fails, clear our reference to avoid a dangling pointer.
        clear_save_timer()


# =========================================================================
# Load
# =========================================================================
def repair_invalid_json_text(raw_text):
    """Best-effort repair of malformed JSON text.

    Handles stray backslashes by inserting an escape when the next
    character is not a valid JSON escape target.
    """
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
                                int(raw_text[i + 1:i + 5], 16)
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
    """Deserialize runtime data from the source Text datablock.

    Compatible with both List and Dict payload shapes.

    V46.0 fix: no longer manually resets ttag_is_loading before the
    recursive call. The outer finally block resets it once after all
    recursion unwinds, eliminating residual bad state on exceptions.
    """
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
                    # Recurse with retry_count=1 to prevent infinite recursion.
                    # ttag_is_loading stays True; outer finally resets it.
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

            # Restore settings
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
