# wxdial/input.py
from micropython import const
import time
import rotaryio
import keypad
import adafruit_focaltouch

_TOUCH_ERR = object()   # sentinel for I2C glitches


class DialInput:
    """
    Reads rotary encoder + knob button + touchscreen and produces events for screens.

    poll() returns either:
      (event_type, event_value)  or  None

    event_value shapes:
      - CW / CCW:        int delta  (signed)
      - CLICK:           None
      - TOUCH_* / TAP:   (x, y)
    """

    # Input event types
    CW         = const(0)
    CCW        = const(1)
    CLICK      = const(2)

    TOUCH_DOWN = const(3)
    TOUCH_MOVE = const(4)
    TOUCH_UP   = const(5)
    TAP        = const(6)

    # Tunables (tap-friendly)
    _TAP_MIN_S = 0.04          # 40 ms
    _TAP_MAX_S = 2.00         # max press duration to count as a tap
    _MOVE_PX2  = 14 * 14       # movement threshold^2 before drag mode


    def __init__(self, pin_a, pin_b, btn_pin, i2c, touch_irq, *, invert=False):
        # --- encoder ---
        self.encoder = rotaryio.IncrementalEncoder(pin_a, pin_b)
        self.last_pos = self.encoder.position
        self.invert = invert

        # --- knob button ---
        self.keys = keypad.Keys(
            (btn_pin,),
            value_when_pressed=False,  # active-low
            pull=True,
        )

        # --- touch ---
        self.touch = adafruit_focaltouch.Adafruit_FocalTouch(i2c)
        self.touch_irq = touch_irq

        self._touching = False
        self._touch_start_t = 0.0
        self._touch_start_xy = (0, 0)
        self._touch_last_xy = (0, 0)
        self._touch_moved = False

        # ---- debug ----
        self._touch_err_count = 0
        self._touch_err_last_print = 0.0

    def deinit(self):
        self.keys.deinit()
        self.encoder.deinit()
        # adafruit_focaltouch doesn't currently require deinit

    def _read_touch_xy(self):
        """Return (x,y) if touched, None if not touched, or _TOUCH_ERR on I2C error."""
        try:
            if not self.touch.touched:
                return None
            touches = self.touch.touches
            if not touches:
                return None
            t0 = touches[0]
            return (t0["x"], t0["y"])
        except OSError:
            self._touch_err_count += 1
            now = time.monotonic()
            if (now - self._touch_err_last_print) > 2.0:
                print("Touch I2C glitch x", self._touch_err_count)
                self._touch_err_last_print = now
            return _TOUCH_ERR

    def poll(self):
        # --- rotation ---
        pos = self.encoder.position
        if pos != self.last_pos:
            delta = pos - self.last_pos
            self.last_pos = pos
            if self.invert:
                delta = -delta
            return (self.CW, delta) if delta > 0 else (self.CCW, delta)

        # --- button ---
        event = self.keys.events.get()
        if event and event.pressed:
            return (self.CLICK, None)

        # --- touch ---
        # If not currently touching, only read I2C when IRQ indicates activity
        if (not self._touching) and (self.touch_irq is not None):
            if self.touch_irq.value:   # IRQ inactive (pulled high)
                return None

        xy = self._read_touch_xy()
        if xy is _TOUCH_ERR:
            return None  # ignore this frame; don't end the touch

        now = time.monotonic()

        # --- no touch reported ---
        if xy is None:
            if self._touching:
                self._touching = False
                dur = now - self._touch_start_t
                if (
                    (not self._touch_moved)
                    and (self._TAP_MIN_S <= dur <= self._TAP_MAX_S)
                ):
                    return (self.TAP, self._touch_start_xy)
                return (self.TOUCH_UP, self._touch_last_xy)
            return None

        # --- touch reported ---
        x, y = xy

        if not self._touching:
            self._touching = True
            self._touch_start_t = now
            self._touch_start_xy = (x, y)
            self._touch_last_xy = (x, y)
            self._touch_moved = False
            return (self.TOUCH_DOWN, (x, y))

        # --- still touching ---
        lx, ly = self._touch_last_xy
        if x != lx or y != ly:
            sx, sy = self._touch_start_xy
            dx = x - sx
            dy = y - sy

            # Only enter drag mode after exceeding movement threshold
            if not self._touch_moved:
                if (dx * dx + dy * dy) >= self._MOVE_PX2:
                    self._touch_moved = True
                else:
                    # jitter inside tap zone: update position but emit nothing
                    self._touch_last_xy = (x, y)
                    return None

            self._touch_last_xy = (x, y)
            return (self.TOUCH_MOVE, (x, y))

        return None

    @staticmethod
    def event_name(kind):
        if kind == DialInput.CW:
            return "CW"
        if kind == DialInput.CCW:
            return "CCW"
        if kind == DialInput.CLICK:
            return "CLICK"
        if kind == DialInput.TOUCH_DOWN:
            return "TOUCH_DOWN"
        if kind == DialInput.TOUCH_MOVE:
            return "TOUCH_MOVE"
        if kind == DialInput.TOUCH_UP:
            return "TOUCH_UP"
        if kind == DialInput.TAP:
            return "TAP"
        return "UNKNOWN"
