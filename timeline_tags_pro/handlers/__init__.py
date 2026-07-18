"""Handlers - frame_change_post etc."""
import bpy

from .frame_change import ttag_sync_handler

_FRAME_CHANGE_HANDLER_REGISTERED = False


def register_handlers():
    global _FRAME_CHANGE_HANDLER_REGISTERED
    if ttag_sync_handler not in bpy.app.handlers.frame_change_post:
        bpy.app.handlers.frame_change_post.append(ttag_sync_handler)
        _FRAME_CHANGE_HANDLER_REGISTERED = True


def unregister_handlers():
    global _FRAME_CHANGE_HANDLER_REGISTERED
    if ttag_sync_handler in bpy.app.handlers.frame_change_post:
        try:
            bpy.app.handlers.frame_change_post.remove(ttag_sync_handler)
        except Exception:
            pass
    _FRAME_CHANGE_HANDLER_REGISTERED = False

