"""frame_change_post handler with V46.0 feedback-loop fix.

V46.0 fix: ttag_is_syncing_from_timeline is now a STABLE guard.
The handler sets it True on entry, False on exit (in finally).
This breaks the "change frame -> change idx -> change frame"
feedback loop that previously caused repeated depgraph evaluation
and eventual GPU driver TDR.

Before this fix, the flag was toggled True/False only around the
single assignment line, so the triggered update_item_index callback
could run while the flag was already cleared.
"""
from bpy.app.handlers import persistent


@persistent
def ttag_sync_handler(scene):
    if not getattr(scene, "ttag_live_sync", False):
        return
    if getattr(scene, "ttag_lock_sync", False):
        return
    if getattr(scene, "ttag_is_syncing_from_timeline", False):
        return

    scene.ttag_is_syncing_from_timeline = True
    try:
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

        if best_idx != -1 and scene.ttag_active_item_index != best_idx:
            scene.ttag_active_item_index = best_idx
    finally:
        scene.ttag_is_syncing_from_timeline = False
