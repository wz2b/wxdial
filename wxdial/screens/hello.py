# screens/hello.py
# SPDX-FileCopyrightText: Copyright (c) 2026 Christopher Piggott
# SPDX-License-Identifier: MIT

from wxdial.tempest_event import subscribewx
from ..input import DialInput
from .screen import Screen
from adafruit_display_text import label
from ..widgets.wx_icon import WxIcon
import time
import os

class GreetingScreen(Screen):
    def __init__(self):
        super().__init__()

        self.icon = WxIcon(
            cx=120,
            cy=120,
            t=0.150,
            icon_path="/wxdial/sprites",
            tile_h=120,
            tile_w=120,
        )

        # for the image rotation test
        self.n = 0

        self.append(self.icon)


    def on_show(self):
        print("GreetingScreen is now shown.")

    def on_hide(self):
        # print("GreetingScreen is now hidden.")
        pass

    
    def tick(self, now):
        # Animate current sprite
        self.icon.tick(now)

    @subscribewx()
    def handle_wx_event(self, event):
        if event.type == "custom":
            icon = getattr(event, "wxicon", None)
            if icon is not None:
                try:
                    self.icon.set_code(icon)
                except Exception as e:
                    print(f"!!!! Error setting icon: {e}")






