# wxdial/wifi_mgr.py

import time
import wifi
import socketpool

try:
    import wifi_cfg
    KNOWN_NETWORKS = wifi_cfg.KNOWN_NETWORKS
except ImportError:
    KNOWN_NETWORKS = {}


def _decode_ssid(ssid):
    if isinstance(ssid, (bytes, bytearray)):
        return ssid.decode("utf-8", "replace")
    return ssid


class WifiManager:
    """
    Small wifi service with a tick-driven state machine.

    Goals:
      - Mockable status access (no direct wifi usage in screens)
      - Non-spammy reconnect attempts
      - A 'desired' network that UI can set

    Notes:
      - CircuitPython wifi.radio.connect() is blocking.
        We avoid freezing the *whole system repeatedly* by calling it
        only on a backoff schedule.
    """

    # Simple states for observability/debugging
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    ERROR = "error"

    # Perf / UX tunables
    _STATUS_TTL_S = 0.5          # cache ap_info queries (radio can be "expensive")
    _STARTUP_GRACE_S = 2.0       # delay first connect attempt so UI can come up
    _CONNECT_TIMEOUT_S = 5       # best-effort; some ports ignore this

    def __init__(self, *, networks=None, radio=None):
        self._radio = radio if radio is not None else wifi.radio
        self._networks = networks if networks is not None else KNOWN_NETWORKS

        self._desired_ssid = None
        self._state = self.DISCONNECTED
        self._last_error = None

        self._next_attempt_at = 0.0
        self._attempt_backoff_s = 1.0  # grows up to max
        self._max_backoff_s = 30.0

        # Cache connected SSID to avoid hammering wifi.radio.ap_info
        self._cached_connected_ssid = None
        self._cached_at = 0.0

    # ---- status API (mock-friendly) ----

    def connected_ssid(self, now: float | None = None) -> str | None:
        """
        Return SSID string if connected, else None.
        Cached briefly to reduce radio load.
        """
        if now is None:
            now = time.monotonic()

        if (now - self._cached_at) < self._STATUS_TTL_S:
            return self._cached_connected_ssid

        ap = self._radio.ap_info
        if ap is None:
            ssid = None
        else:
            ssid = _decode_ssid(getattr(ap, "ssid", None))
            if not isinstance(ssid, str):
                ssid = None

        self._cached_connected_ssid = ssid
        self._cached_at = now
        return ssid

    def state(self) -> str:
        # Derive CONNECTED from radio if possible (cached)
        if self.connected_ssid():
            return self.CONNECTED
        return self._state

    def last_error(self):
        return self._last_error

    def desired_ssid(self) -> str | None:
        return self._desired_ssid

    # ---- control API ----

    def set_network(self, ssid: str | None):
        """
        Set the desired SSID. Does not block.
        If ssid is None, we simply stop trying (and optionally disconnect).
        """
        self._desired_ssid = ssid
        self._last_error = None

        # Reset backoff so the change reacts quickly
        self._attempt_backoff_s = 1.0
        self._next_attempt_at = time.monotonic()  # attempt soon (but not necessarily immediately)

        # Invalidate cache so screens see updated status faster
        self._cached_at = 0.0

    def startup(self):
        """
        Decide initial desired network.
        Prefer:
          1) already-connected SSID (if any)
          2) first auto_connect=True network
          3) otherwise leave desired None
        """
        now = time.monotonic()

        cur = self.connected_ssid(now)
        if cur:
            self._desired_ssid = cur
            self._state = self.CONNECTED
            self._next_attempt_at = 0.0
            return

        # Find an auto_connect network
        for ssid, cfg in self._networks.items():
            if cfg.get("auto_connect", False):
                self._desired_ssid = ssid
                break

        self._state = self.DISCONNECTED
        # Grace period so the UI can come up before the first blocking connect call
        self._next_attempt_at = now + self._STARTUP_GRACE_S

    def disconnect(self):
        try:
            self._radio.disconnect()
        except Exception:
            pass

        self._state = self.DISCONNECTED
        # Invalidate cache (ap_info may lag briefly otherwise)
        self._cached_connected_ssid = None
        self._cached_at = 0.0

    # ---- main loop hook ----

    def tick(self, now: float):
        """
        Call this frequently (each main loop). It will attempt connection on a schedule.
        """
        # If we're connected, keep state in sync and do nothing
        cur = self.connected_ssid(now)
        if cur:
            self._state = self.CONNECTED
            self._last_error = None

            # If connected to something else than desired, switch
            if self._desired_ssid and self._desired_ssid != cur:
                self.disconnect()
                self._state = self.DISCONNECTED
                self._next_attempt_at = now
            return

        # Not connected
        if not self._desired_ssid:
            self._state = self.DISCONNECTED
            return

        # Wait for the next attempt window (backoff / grace)
        if now < self._next_attempt_at:
            self._state = self.DISCONNECTED
            return

        # Attempt connect (blocking call, so do it sparingly)
        cfg = self._networks.get(self._desired_ssid)
        if not cfg:
            self._last_error = ValueError("Unknown SSID")
            self._state = self.ERROR
            self._schedule_backoff(now)
            return

        password = cfg.get("password", "")

        self._state = self.CONNECTING
        try:
            # Some CP builds support timeout=...; keep it optional
            try:
                self._radio.connect(self._desired_ssid, password, timeout=self._CONNECT_TIMEOUT_S)
            except TypeError:
                self._radio.connect(self._desired_ssid, password)

            # Success
            self._state = self.CONNECTED
            self._last_error = None
            self._attempt_backoff_s = 1.0
            self._next_attempt_at = 0.0

            # Invalidate cache so screens see connected state immediately
            self._cached_at = 0.0

        except Exception as e:
            self._last_error = e
            self._state = self.ERROR
            self._schedule_backoff(now)

            # Invalidate cache; some failures leave ap_info in weird transient states
            self._cached_at = 0.0

    def _schedule_backoff(self, now: float):
        self._next_attempt_at = now + self._attempt_backoff_s
        self._attempt_backoff_s = min(self._attempt_backoff_s * 2.0, self._max_backoff_s)

    # ---- misc helpers ----

    def new_socket_pool(self):
        self._pool = socketpool.SocketPool(self._radio)

    def mac_address(self) -> bytes:
        return self._radio.mac_address

    def mac_address_str(self) -> str:
        mac = self._radio.mac_address
        return ":".join(f"{b:02X}" for b in mac)
