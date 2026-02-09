import time

class WxFlowUdp:
    """
    DialMQTT-compatible UDP receiver.

    API:
      - connect(): bind UDP socket
      - disconnect(): close socket
      - subscribe(topic): optional gating (exact topics)
      - poll(): read all pending UDP packets; update cache + dirty set
      - get(topic): get last value
      - drain_dirty(): list of topics updated since last drain

    You provide:
      - pool: a socketpool.SocketPool (e.g. wifi_mgr.new_socket_pool())
      - decoder: callable(data: bytes, addr_tuple) -> dict {topic: value}
    """

    def __init__(
        self,
        pool,
        *,
        listen_port=50222,
        decoder=None,
        buffer_size=1024,
        max_packets_per_poll=8,
        only_mark_dirty_on_change=True,
    ):
        self._pool = pool
        self._listen_port = int(listen_port)
        self._decoder = decoder or self._default_decoder
        self._buffer = bytearray(int(buffer_size))
        self._max_packets = int(max_packets_per_poll)
        self._only_on_change = bool(only_mark_dirty_on_change)

        self._sock = None

        self._values = {}    # topic -> last value
        self._dirty = set()  # topics changed since last drain
        self._subs = set()   # subscribed topics (optional gating). empty => accept all.

    # ---- Compatibility-ish API ----

    def connect(self):
        if self._sock:
            return  # already connected

        sock = self._pool.socket(self._pool.AF_INET, self._pool.SOCK_DGRAM)
        sock.setblocking(False)
        sock.bind(("0.0.0.0", self._listen_port))
        self._sock = sock

    def disconnect(self):
        if self._sock:
            try:
                self._sock.close()
            except Exception:
                pass
        self._sock = None

    def subscribe(self, topic):
        # Exact-topic subscribe (optional gating)
        if topic:
            self._subs.add(str(topic))

    def poll(self):
        """
        Read as many UDP packets as are immediately available (up to max_packets_per_poll).
        No sleep here; caller controls cadence.
        """
        if not self._sock:
            # allow poll() to be called before connect() without exploding
            return

        packets = 0

        while packets < self._max_packets:
            try:
                nbytes, addr = self._sock.recvfrom_into(self._buffer)
            except OSError:
                # Non-blocking socket: no data available (EAGAIN) => done for now
                break

            if not nbytes:
                break

            data = self._buffer[:nbytes]

            try:
                updates = self._decoder(data, addr) or {}
            except Exception:
                # If decode fails, just ignore this packet rather than wedging UI
                updates = {}

            if updates:
                self._apply_updates(updates)

            packets += 1

    def get(self, topic, default=None):
        return self._values.get(topic, default)

    def drain_dirty(self):
        if not self._dirty:
            return []
        topics = list(self._dirty)
        self._dirty.clear()
        return topics

    # ---- Internals ----

    def _apply_updates(self, updates):
        # Subscription gating:
        # - if _subs empty => accept all
        # - else only accept subscribed topics
        if self._subs:
            updates = {k: v for (k, v) in updates.items() if k in self._subs}
            if not updates:
                return

        if self._only_on_change:
            for topic, new_val in updates.items():
                old_val = self._values.get(topic, None)
                if old_val != new_val:
                    self._values[topic] = new_val
                    self._dirty.add(topic)
        else:
            for topic, new_val in updates.items():
                self._values[topic] = new_val
                self._dirty.add(topic)

    def _default_decoder(self, data, addr):
        """
        Minimal default:
        - If UTF-8 text, publish it as a single topic.
        - Otherwise publish hex string as a single topic.
        You will almost certainly replace this with a Tempest-specific decoder.
        """
        try:
            text = data.decode("utf-8")
            return {"udp/text": text}
        except Exception:
            hex_str = " ".join("{:02x}".format(b) for b in data)
            return {"udp/hex": hex_str}



