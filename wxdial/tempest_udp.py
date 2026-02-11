# wxdial/tempest_udp.py
import time
from wxdial.tempest_event import WxEvent
from wxdial.tempest_decode import TempestUdpDecoder

class WxFlowUdp:
    """
    UDP receiver that decodes packets into WxEvent objects.

    API:
      - connect()
      - disconnect()
      - poll() -> list[WxEvent]
    """

    def __init__(
        self,
        pool,
        *,
        listen_port=50222,
        decoder=None,
        buffer_size=1024,
        max_packets_per_poll=8,
        altitude_m=0.0
    ):
        self._pool = pool
        self._listen_port = int(listen_port)
        self._decoder = decoder or TempestUdpDecoder(altitude_m=altitude_m)
        self._buffer = bytearray(int(buffer_size))
        self._max_packets = int(max_packets_per_poll)

        self._sock = None

    def connect(self):
        if self._sock:
            return
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

    def poll(self):
            if not self._sock:
                return []

            events = []
            packets = 0

            while packets < self._max_packets:
                try:
                    nbytes, addr = self._sock.recvfrom_into(self._buffer)
                except OSError:
                    break

                if not nbytes:
                    break

                data = self._buffer[:nbytes]

                try:
                    decoded = self._decoder.decode(data, addr)
                except Exception:
                    decoded = None

                if decoded is None:
                    packets += 1
                    continue

                mtype, payload = decoded
                events.append(WxEvent(mtype, payload, ts=time.monotonic()))
                packets += 1

            return events
