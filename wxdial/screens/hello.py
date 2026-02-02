# screens/hello.py

import terminalio
from ..input import DialInput
from .screen import Screen
from adafruit_display_text import label

class GreetingScreen(Screen):
    def __init__(self):
        super().__init__()

        # Create a text label
        text_area = label.Label(
            terminalio.FONT,
            text="Hello, MicroPython!",
            color=0xFFFFFF,  # White text
            anchor_point=(0.5, 0.5),   # center of the label
            anchored_position=(self.cx, self.cy),
        )
        self.append(text_area)
        

    def on_show(self):
        print("GreetingScreen is now shown.")

    def on_hide(self):
        print("GreetingScreen is now hidden.")

    def input(self, event_type, event_value=None):
        if event_type == DialInput.CLICK:
            print("GreetingScreen received a click event.")
            return False
        elif event_type == DialInput.CW:
            print("GreetingScreen received a clockwise rotation.")
            return False
        elif event_type == DialInput.CCW:
            print("GreetingScreen received a counter-clockwise rotation.")
            return False
        elif event_type == DialInput.TAP:
            x, y = event_value
            print(f"TAP at ({x}, {y})")
            return False
        else:
            event_name = DialInput.event_name(event_type)
            # print(event_name, event_value)
            return False
    