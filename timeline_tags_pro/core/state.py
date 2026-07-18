"""Mutable global state for the debounce timer.

This module isolates the only piece of module-level mutable state
in the addon, so it can be reset cleanly on unregister.
"""

# Global reference to the pending debounce timer function.
# Held as a module attribute so auto_save_debounced / cancel_pending_save_timer
# can coordinate without dangling references.
_TTAG_SAVE_TIMER = None


def set_save_timer(timer_fn):
    """Replace the current pending save timer reference."""
    global _TTAG_SAVE_TIMER
    _TTAG_SAVE_TIMER = timer_fn


def get_save_timer():
    """Return the current pending save timer (or None)."""
    return _TTAG_SAVE_TIMER


def clear_save_timer():
    """Forget the current pending save timer (does not unregister it)."""
    global _TTAG_SAVE_TIMER
    _TTAG_SAVE_TIMER = None
