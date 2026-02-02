# screens/hello.py

import terminalio
from ..input import DialInput
from .screen import Screen
from adafruit_display_text import label

class WeatherScreen(Screen):
    def __init__(self):
        super().__init__()

        # Create a text label
        text_area = label.Label(
            terminalio.FONT,
            text="weather",
            color=0xFFFFFF,  # White text
            anchor_point=(0.5, 0.5),   # center of the label
            anchored_position=(self.cx, self.cy),
        )
        self.append(text_area)
        



    def on_show(self):
        pass;

    def on_hide(self):
        pass;

    def input(self, event_type, event_value=None):
        return False

    