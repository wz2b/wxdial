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
    
    Auto-connects to known networks based on availability and priority.
    """

    DISCONNECTED = "disconnected"
    SCANNING = "scanning"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    ERROR = "error"

    _STATUS_TTL_S = 0.5
    _STARTUP_GRACE_S = 2.0
    _CONNECT_TIMEOUT_S = 5
    _SCAN_INTERVAL_S = 10.0  # How often to scan when disconnected

    def __init__(self, *, networks=None, radio=None):
        self._radio = radio if radio is not None else wifi.radio
        self._networks = networks if networks is not None else KNOWN_NETWORKS

        self._desired_ssid = None  # Can still be set manually
        self._state = self.DISCONNECTED
        self._last_error = None

        self._next_attempt_at = 0.0
        self._attempt_backoff_s = 1.0
        self._max_backoff_s = 30.0

        self._cached_connected_ssid = None
        self._cached_at = 0.0
        
        self._last_scan_at = 0.0

    # ---- status API ----

    def connected_ssid(self, now: float | None = None) -> str | None:
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
        Manually set desired SSID (overrides auto-connect).
        Set to None to resume auto-connect behavior.
        """
        self._desired_ssid = ssid
        self._last_error = None
        self._attempt_backoff_s = 1.0
        self._next_attempt_at = time.monotonic()
        self._cached_at = 0.0

    def startup(self):
        """Initialize and check if already connected."""
        now = time.monotonic()

        cur = self.connected_ssid(now)
        if cur and cur in self._networks:
            self._desired_ssid = cur
            self._state = self.CONNECTED
            self._next_attempt_at = 0.0
            return

        self._state = self.DISCONNECTED
        self._next_attempt_at = now + self._STARTUP_GRACE_S

    def disconnect(self):
        try:
            self._radio.disconnect()
        except Exception:
            pass

        self._state = self.DISCONNECTED
        self._cached_connected_ssid = None
        self._cached_at = 0.0

    # ---- scanning ----

    def _scan_for_auto_networks(self) -> str | None:
        """
        Scan for available networks and return the best auto_connect match.
        Priority: explicit priority field > order in dict > signal strength.
        """
        try:
            # Get auto-connect candidates with priority
            candidates = {
                ssid: cfg 
                for ssid, cfg in self._networks.items() 
                if cfg.get("auto_connect", False)
            }
            
            if not candidates:
                return None

            # Scan available networks
            networks = self._radio.start_scanning_networks()
            available = {}
            
            for network in networks:
                ssid = _decode_ssid(network.ssid)
                if ssid in candidates:
                    # Keep strongest signal if duplicate SSID
                    if ssid not in available or network.rssi > available[ssid]["rssi"]:
                        available[ssid] = {
                            "rssi": network.rssi,
                            "priority": candidates[ssid].get("priority", 50)
                        }
            
            self._radio.stop_scanning_networks()
            
            if not available:
                return None
            
            # Sort by priority (lower number = higher priority), then signal strength
            best = sorted(
                available.items(),
                key=lambda x: (x[1]["priority"], -x[1]["rssi"])
            )[0][0]
            
            return best
            
        except Exception as e:
            print(f"Scan error: {e}")
            return None

    # ---- main loop hook ----

    def tick(self, now: float):
        """
        Auto-connect state machine:
        1. If connected, maintain connection
        2. If manual desired_ssid set, try that
        3. Otherwise, scan and auto-connect to best available network
        """
        cur = self.connected_ssid(now)
        
        # Already connected
        if cur:
            self._state = self.CONNECTED
            self._last_error = None

            # If manually set different network, disconnect and reconnect
            if self._desired_ssid and self._desired_ssid != cur:
                self.disconnect()
                self._state = self.DISCONNECTED
                self._next_attempt_at = now
            return

        # Not connected - wait for next attempt window
        if now < self._next_attempt_at:
            return

        # Determine which network to connect to
        target_ssid = None
        
        if self._desired_ssid:
            # Manual override
            target_ssid = self._desired_ssid
        else:
            # Auto-scan mode
            if (now - self._last_scan_at) >= self._SCAN_INTERVAL_S:
                self._state = self.SCANNING
                target_ssid = self._scan_for_auto_networks()
                self._last_scan_at = now
                
                if not target_ssid:
                    # No auto-connect networks found
                    self._state = self.DISCONNECTED
                    self._schedule_backoff(now)
                    return

        if not target_ssid:
            self._state = self.DISCONNECTED
            return

        # Attempt connection
        cfg = self._networks.get(target_ssid)
        if not cfg:
            self._last_error = ValueError(f"Unknown SSID: {target_ssid}")
            self._state = self.ERROR
            self._schedule_backoff(now)
            return

        password = cfg.get("password", "")
        self._state = self.CONNECTING
        
        try:
            try:
                self._radio.connect(target_ssid, password, timeout=self._CONNECT_TIMEOUT_S)
            except TypeError:
                self._radio.connect(target_ssid, password)

            # Success
            self._state = self.CONNECTED
            self._desired_ssid = target_ssid  # Remember what we connected to
            self._last_error = None
            self._attempt_backoff_s = 1.0
            self._next_attempt_at = 0.0
            self._cached_at = 0.0

        except Exception as e:
            self._last_error = e
            self._state = self.ERROR
            self._schedule_backoff(now)
            self._cached_at = 0.0

    def _schedule_backoff(self, now: float):
        self._next_attempt_at = now + self._attempt_backoff_s
        self._attempt_backoff_s = min(self._attempt_backoff_s * 2.0, self._max_backoff_s)

    # ---- misc helpers ----

    def new_socket_pool(self):
        self._pool = socketpool.SocketPool(self._radio)
        return self._pool

    def mac_address(self) -> bytes:
        return self._radio.mac_address

    def mac_address_str(self) -> str:
        mac = self._radio.mac_address
        return ":".join(f"{b:02X}" for b in mac)

    def ip_address(self):
        try:
            return self._radio.ipv4_address
        except Exception:
            return None

    def ip_address_str(self) -> str | None:
        ip = self.ip_address()
        return str(ip) if ip is not None else None