# wxdial/widgets/widget.py
# SPDX-FileCopyrightText: Copyright (c) 2026 Christopher Piggott
# SPDX-License-Identifier: MIT

#
# Base class for all widgets.
#
import displayio
from micropython import const


class Widget(displayio.Group):
    """
    Base widget: has a primary numeric value plus optional metadata dict.

    - value: primary numeric value (float/int) or None
    - meta: optional dict for extra fields (direction, displayText, maxGust, etc.)
    - label: optional widget title/caption

    Subclasses typically:
      - build displayio children in __init__
      - override _render() to push state into labels/shapes
      - optionally override format_value()
    """

    # Optional "change flags" if you want them later
    DIRTY_VALUE = const(1)
    DIRTY_LABEL = const(2)
    DIRTY_META  = const(4)
    DIRTY_ALL   = const(7)

    def __init__(self, *, label=None, value=None, meta=None, visible=True):
        super().__init__()
        self._label = label
        self._value = value
        self._meta = meta if meta is not None else {}
        self._dirty = self.DIRTY_ALL
        self.hidden = (not visible)  # displayio.Group supports .hidden

    # ---- properties ----

    @property
    def label(self):
        return self._label

    @label.setter
    def label(self, s):
        if s != self._label:
            self._label = s
            self._dirty |= self.DIRTY_LABEL

    @property
    def value(self):
        return self._value

    @property
    def meta(self):
        # Intentionally return the dict (mutations are allowed),
        # but mutation won't set dirty unless caller calls touch().
        return self._meta

    # ---- updates ----

    def set(self, value=None, meta=None, *, label=None):
        """
        Set one or more fields. Any change marks widget dirty.
        """
        if label is not None and label != self._label:
            self._label = label
            self._dirty |= self.DIRTY_LABEL

        if value != self._value:
            self._value = value
            self._dirty |= self.DIRTY_VALUE

        if meta is not None:
            # Replace meta wholesale (safer + marks dirty)
            self._meta = meta
            self._dirty |= self.DIRTY_META

    def update_meta(self, **kwargs):
        """
        Convenience: update meta keys in-place and mark dirty.
        """
        changed = False
        for k, v in kwargs.items():
            if self._meta.get(k) != v:
                self._meta[k] = v
                changed = True
        if changed:
            self._dirty |= self.DIRTY_META

    def touch(self):
        """
        Mark dirty if caller mutated meta directly (in-place).
        """
        self._dirty |= self.DIRTY_META

    # ---- rendering ----

    def refresh(self, force=False):
        """
        If dirty (or forced), push internal state into display objects.
        Call this from screen.tick() or after set() calls.
        """
        if force:
            self._dirty = self.DIRTY_ALL

        if not self._dirty:
            return False

        self._render(self._dirty)
        self._dirty = 0
        return True

    def tick(self, now):
        pass
    
    def _render(self, dirty_flags):
        """
        Subclasses override this. dirty_flags indicates what changed.
        """
        pass

    # ---- formatting helpers ----

    def format_value(self):
        """
        Subclasses can override. Default formatting for numeric value.
        """
        v = self._value
        if v is None:
            return "--"
        # Keep it simple: ints stay ints, floats get trimmed
        try:
            if int(v) == v:
                return str(int(v))
        except Exception:
            pass
        return "{:.1f}".format(v)
