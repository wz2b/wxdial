# screens/network.py

from ..input import DialInput
from .screen import Screen

import terminalio
from adafruit_display_text import label
import vectorio
import displayio

import wifi_cfg
KNOWN_NETWORKS = wifi_cfg.KNOWN_NETWORKS


def _format_mac(mac_bytes) -> str:
    return ":".join(f"{b:02X}" for b in mac_bytes)


class NetworkScreen(Screen):
    def __init__(self, wifimgr=None):
        super().__init__()
        self.wifimgr = wifimgr

        self._edit_mode = False

        # Background highlight for edit mode
        self._edit_palette = None
        self._edit_bg = None

        # 3 lines
        self._sel_label = None      # "Selected: <ssid>"
        self._conn_label = None     # "Connected" / "Not Connected"
        self._mac_label = None      # "MAC: .."

        self._last_line1 = None
        self._last_line2 = None
        self._last_refresh = 0.0  # monotonic seconds

        # --- selection state for edit mode ---
        self._net_names = list(KNOWN_NETWORKS.keys())
        self._sel_idx = 0
        self._selected_ssid = self._net_names[self._sel_idx] if self._net_names else None

    def _current_ssid(self) -> str | None:
        if self.wifimgr is None:
            return None
        return self.wifimgr.connected_ssid()

    def _is_connected_to(self, ssid: str | None) -> bool:
        if not ssid:
            return False
        cur = self._current_ssid()
        return (cur is not None) and (cur == ssid)

    def on_show(self):
        print("NetworkScreen is now shown.")

        # Default selection: current SSID if known, else first
        cur = self._current_ssid()
        if cur and cur in KNOWN_NETWORKS and self._net_names:
            try:
                self._sel_idx = self._net_names.index(cur)
            except ValueError:
                self._sel_idx = 0
        self._selected_ssid = self._net_names[self._sel_idx] if self._net_names else None

        # --- edit-mode background circle (insert behind everything) ---
        if self._edit_bg is None:
            self._edit_palette = displayio.Palette(1)
            self._edit_palette[0] = 0x001830  # subtle dark blue-ish

            r = max(self.width, self.height) // 2
            self._edit_bg = vectorio.Circle(
                pixel_shader=self._edit_palette,
                radius=r,
                x=self.cx,
                y=self.cy,
                color_index=0,
            )
            self._edit_bg.hidden = True
            self.insert(0, self._edit_bg)

        # Layout: 3 lines centered
        y1 = self.cy - 20
        y2 = self.cy
        y3 = self.cy + 20

        if self._sel_label is None:
            self._sel_label = label.Label(
                terminalio.FONT,
                text="Selected: (none)",
                color=0xFFFFFF,
            )
            self._sel_label.anchor_point = (0.5, 0.5)
            self._sel_label.anchored_position = (self.cx, y1)
            self.append(self._sel_label)

        if self._conn_label is None:
            self._conn_label = label.Label(
                terminalio.FONT,
                text="Not Connected",
                color=0xFFFFFF,
            )
            self._conn_label.anchor_point = (0.5, 0.5)
            self._conn_label.anchored_position = (self.cx, y2)
            self.append(self._conn_label)

        if self._mac_label is None:
            mac = self.wifimgr.mac_address_str() if self.wifimgr else "(no mac)"
            self._mac_label = label.Label(
                terminalio.FONT,
                text=f"MAC: {mac}",
                color=0xFFFFFF,
            )
            self._mac_label.anchor_point = (0.5, 0.5)
            self._mac_label.anchored_position = (self.cx, y3)
            self.append(self._mac_label)

        # Ensure visuals match mode + force a render
        self._set_edit_mode(False)
        self._render_lines(force=True)

    def _set_edit_mode(self, enabled: bool):
        self._edit_mode = enabled

        if self._edit_bg is not None:
            self._edit_bg.hidden = not enabled

        # Dim MAC text while editing (subtle but helpful)
        if self._mac_label is not None:
            self._mac_label.color = 0xAAAAAA if enabled else 0xFFFFFF

        self._render_lines(force=True)

    def _render_lines(self, *, force=False):
        # Line 1: Selected network (always shown, even if not connected)
        if not self._net_names or not self._selected_ssid:
            line1 = "Selected: (none)"
        else:
            line1 = f"Select: {self._selected_ssid}" if self._edit_mode else f"Selected: {self._selected_ssid}"

        # Line 2: Connected/Not Connected (based on selected SSID)
        line2 = "Connected" if self._is_connected_to(self._selected_ssid) else "Not Connected"

        if self._sel_label and (force or line1 != self._last_line1):
            self._sel_label.text = line1
            self._last_line1 = line1

        if self._conn_label and (force or line2 != self._last_line2):
            self._conn_label.text = line2
            self._last_line2 = line2

    def _select_step(self, delta: int):
        if not self._net_names:
            return

        n = len(self._net_names)
        self._sel_idx = (self._sel_idx + delta) % n
        self._selected_ssid = self._net_names[self._sel_idx]
        self._render_lines(force=True)

    def _save(self):
        # Commit selection to wifi manager (non-blocking: manager will attempt connection in its tick)
        if not self._selected_ssid:
            print("NetworkScreen: no SSID selected")
            return

        print(f"NetworkScreen: set desired SSID={self._selected_ssid}")
        if self.wifimgr:
            self.wifimgr.set_network(self._selected_ssid)

    def on_hide(self):
        if self._edit_mode:
            print("NetworkScreen: edit canceled (screen hidden)")
        self._set_edit_mode(False)

    def input(self, event_type, event_value=None):
        if event_type == DialInput.CLICK:
            if self._edit_mode:
                self._save()
                self._set_edit_mode(False)
            else:
                self._set_edit_mode(True)
            return True

        # In edit mode: consume EVERYTHING so the app can't switch screens on you.
        if self._edit_mode:
            if event_type == DialInput.CW:
                self._select_step(+1)
            elif event_type == DialInput.CCW:
                self._select_step(-1)
            return True

        # Not in edit mode: allow normal app navigation
        if event_type in (DialInput.CW, DialInput.CCW):
            return False

        return False

    def tick(self, now):
        if self._edit_mode:
            return

        if (now - self._last_refresh) < 2.0:
            return
        self._last_refresh = now

        self._render_lines(force=False)
