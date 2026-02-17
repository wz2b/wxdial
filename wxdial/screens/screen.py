# screens/screen.py
# SPDX-FileCopyrightText: Copyright (c) 2026 Christopher Piggott
# SPDX-License-Identifier: MIT

#
# Base class for all screens.
#
import displayio
import board
from micropython import const


class Screen(displayio.Group):
    # Cached display geometry (class-level, shared by all screens)
    _width  = None
    _height = None
    _cx     = None
    _cy     = None

    def __init__(self, *, wants_auto_rotate=True):
        super().__init__()
        self.wants_auto_rotate = wants_auto_rotate

        # Initialize geometry once, lazily
        if Screen._width is None:
            d = board.DISPLAY
            Screen._width  = d.width
            Screen._height = d.height
            Screen._cx     = d.width // 2
            Screen._cy     = d.height // 2

    # ---- geometry helpers ----

    @property
    def width(self):
        return Screen._width

    @property
    def height(self):
        return Screen._height

    @property
    def cx(self):
        return Screen._cx

    @property
    def cy(self):
        return Screen._cy

    # ---- lifecycle ----

    def on_show(self):
        """Called when this screen becomes the active screen."""
        pass

    def on_hide(self):
        """Called when this screen is no longer the active screen."""
        pass

    # ---- input / update ----

    def input(self, event_type, event_value=None):
        """
        Sent to the screen to handle input events.

        Return True if handled (consumed), False otherwise.
        """
        return False

    def tick(self, now):
        """
        Called periodically (each main loop) for animations or time-based updates.
        'now' should be time.monotonic() from the app.
        """
        pass

    def refresh(self):
        for child in self:
            if hasattr(child, "refresh"):
                child.refresh()