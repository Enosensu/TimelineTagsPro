"""Reentrancy / read-write guards for the addon.

A thin abstraction over Blender's PropertyGroup boolean flags so that
all "is this region already running?" checks live in one place.
"""


class ReentrancyGuard:
    """Context manager that short-circuits if a named region is already entered.

    Usage::

        with ReentrancyGuard(scene, "saving") as g:
            if g.acquired:
                ... do the save ...

    The guard reads/writes ``scene.ttag_is_<region>`` BoolProperty.
    """

    def __init__(self, scene, region):
        self.scene = scene
        self.region = region
        self.acquired = False
        self._attr = f"ttag_is_{region}"

    def __enter__(self):
        try:
            if getattr(self.scene, self._attr, False):
                # Already inside this region - reentrant call, refuse.
                return self
        except Exception:
            return self
        # Acquire.
        try:
            setattr(self.scene, self._attr, True)
        except Exception:
            pass
        self.acquired = True
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.acquired:
            try:
                setattr(self.scene, self._attr, False)
            except Exception:
                pass
        # Do not suppress exceptions.
        return False
