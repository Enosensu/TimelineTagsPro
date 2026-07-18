"""core - lowest layer, no intra-package imports."""

from .state import (
    _TTAG_SAVE_TIMER,
    set_save_timer,
    get_save_timer,
    clear_save_timer,
)
from .sync import sync_lines_to_content, sync_content_to_lines
from .serialize import (
    save_runtime_data_immediate,
    cancel_pending_save_timer,
    auto_save_debounced,
    repair_invalid_json_text,
    load_runtime_data,
)
from .locks import ReentrancyGuard

__all__ = [
    "_TTAG_SAVE_TIMER",
    "set_save_timer",
    "get_save_timer",
    "clear_save_timer",
    "sync_lines_to_content",
    "sync_content_to_lines",
    "save_runtime_data_immediate",
    "cancel_pending_save_timer",
    "auto_save_debounced",
    "repair_invalid_json_text",
    "load_runtime_data",
    "ReentrancyGuard",
]
