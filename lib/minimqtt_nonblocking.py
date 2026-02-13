# SPDX-FileCopyrightText: 2019-2021 Brent Rubell for Adafruit Industries
# SPDX-FileCopyrightText: 2025 Non-blocking modifications
#
# SPDX-License-Identifier: MIT

"""
`adafruit_minimqtt_nonblocking`
================================================================================

A NON-BLOCKING minimal MQTT Library for CircuitPython.

This version breaks all blocking operations into state machines that can be
called repeatedly without freezing your UI.

Key differences from standard adafruit_minimqtt:
- connect() is now connect_begin() + connect_poll()
- publish() with QoS 1 is now publish() + check via loop()
- All recv operations use non-blocking sockets
- loop() returns immediately if no data available

Limitations:
- TLS handshake still blocks briefly (100-500ms) - unavoidable in CircuitPython
- You must call loop() regularly (every 50-100ms) to process messages

Usage:
    mqtt = MQTT(broker="test.mosquitto.org")
    
    # Non-blocking connect
    mqtt.connect_begin()
    while mqtt.connect_poll() == CONNECT_PENDING:
        # Update your UI, read sensors, etc.
        time.sleep(0.1)
    
    # In main loop
    while True:
        mqtt.loop()  # Returns immediately, processes any waiting messages
        update_display()
        read_sensors()
        time.sleep(0.05)

"""

import errno
import struct
import time
from random import randint

from adafruit_connection_manager import get_connection_manager
from adafruit_ticks import ticks_diff, ticks_ms

try:
    from typing import List, Optional, Tuple, Type, Union
except ImportError:
    pass

try:
    from types import TracebackType
except ImportError:
    pass

from micropython import const

from .matcher import MQTTMatcher

__version__ = "0.0.0+auto.0"
__repo__ = "https://github.com/adafruit/Adafruit_CircuitPython_MiniMQTT.git"

# Client-specific variables
MQTT_MSG_MAX_SZ = const(268435455)
MQTT_MSG_SZ_LIM = const(10000000)
MQTT_TOPIC_LENGTH_LIMIT = const(65535)
MQTT_TCP_PORT = const(1883)
MQTT_TLS_PORT = const(8883)

# MQTT Commands
MQTT_PINGREQ = b"\xc0\0"
MQTT_PINGRESP = const(0xD0)
MQTT_PUBLISH = const(0x30)
MQTT_SUB = const(0x82)
MQTT_SUBACK = const(0x90)
MQTT_UNSUB = const(0xA2)
MQTT_UNSUBACK = const(0xB0)
MQTT_DISCONNECT = b"\xe0\0"

MQTT_PKT_TYPE_MASK = const(0xF0)

CONNACK_ERROR_INCORRECT_PROTOCOL = const(0x01)
CONNACK_ERROR_ID_REJECTED = const(0x02)
CONNACK_ERROR_SERVER_UNAVAILABLE = const(0x03)
CONNACK_ERROR_INCORECT_USERNAME_PASSWORD = const(0x04)
CONNACK_ERROR_UNAUTHORIZED = const(0x05)

CONNACK_ERRORS = {
    CONNACK_ERROR_INCORRECT_PROTOCOL: "Connection Refused - Incorrect Protocol Version",
    CONNACK_ERROR_ID_REJECTED: "Connection Refused - ID Rejected",
    CONNACK_ERROR_SERVER_UNAVAILABLE: "Connection Refused - Server unavailable",
    CONNACK_ERROR_INCORECT_USERNAME_PASSWORD: "Connection Refused - Incorrect username/password",
    CONNACK_ERROR_UNAUTHORIZED: "Connection Refused - Unauthorized",
}

# Connection state constants
CONNECT_IDLE = const(0)
CONNECT_PENDING = const(1)
CONNECT_CONNECTED = const(2)
CONNECT_FAILED = const(3)


class MMQTTException(Exception):
    """MiniMQTT Exception class."""
    def __init__(self, error, code=None):
        super().__init__(error, code)
        self.code = code


class MMQTTStateError(MMQTTException):
    """MiniMQTT invalid state error."""


class NullLogger:
    """Fake logger class that does not do anything"""
    def nothing(self, msg: str, *args) -> None:
        """no action"""

    def __init__(self) -> None:
        for log_level in ["debug", "info", "warning", "error", "critical"]:
            setattr(NullLogger, log_level, self.nothing)


class MQTT:  # noqa: PLR0904
    """NON-BLOCKING MQTT Client for CircuitPython.
    
    All blocking operations have been converted to state machines.
    You MUST call loop() regularly (every 50-100ms) in your main loop.
    """

    def __init__(
        self,
        *,
        broker: str,
        port: Optional[int] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        client_id: Optional[str] = None,
        is_ssl: Optional[bool] = None,
        keep_alive: int = 60,
        recv_timeout: int = 10,
        socket_pool=None,
        ssl_context=None,
        use_binary_mode: bool = False,
        socket_timeout: int = 1,
        connect_retries: int = 5,
        user_data=None,
    ) -> None:
        self._connection_manager = get_connection_manager(socket_pool)
        self._socket_pool = socket_pool
        self._ssl_context = ssl_context
        self._sock = None
        self._backwards_compatible_sock = False
        self._use_binary_mode = use_binary_mode

        if recv_timeout <= socket_timeout:
            raise ValueError("recv_timeout must be strictly greater than socket_timeout")
        self._socket_timeout = socket_timeout
        self._recv_timeout = recv_timeout

        self.keep_alive = keep_alive
        self.user_data = user_data
        self._is_connected = False
        self._msg_size_lim = MQTT_MSG_SZ_LIM
        self._pid = 0
        self._last_msg_sent_timestamp: int = 0
        self.logger = NullLogger()

        self._reconnect_attempt = 0
        self._reconnect_timeout = float(0)
        self._reconnect_maximum_backoff = 32
        if connect_retries <= 0:
            raise ValueError("connect_retries must be positive")
        self._reconnect_attempts_max = connect_retries

        self.broker = broker
        self._username = username
        self._password = password
        if self._password and len(password.encode("utf-8")) > MQTT_TOPIC_LENGTH_LIMIT:
            raise ValueError("Password length is too large.")

        self.port = MQTT_TCP_PORT
        if is_ssl is None:
            is_ssl = False
        self._is_ssl = is_ssl
        if self._is_ssl:
            self.port = MQTT_TLS_PORT
        if port:
            self.port = port

        self.session_id = None

        # define client identifier
        if client_id:
            self.client_id = client_id
        else:
            time_int = int(ticks_ms() / 10) % 1000
            self.client_id = f"cpy{randint(0, time_int)}{randint(0, 99)}"
            if len(self.client_id.encode("utf-8")) > 23 or not self.client_id:
                raise ValueError("MQTT Client ID must be between 1 and 23 bytes")

        # LWT
        self._lw_topic = None
        self._lw_qos = 0
        self._lw_msg = None
        self._lw_retain = False

        # List of subscribed topics
        self._subscribed_topics: List[str] = []
        self._on_message_filtered = MQTTMatcher()

        # Callbacks
        self._on_message = None
        self.on_connect = None
        self.on_disconnect = None
        self.on_publish = None
        self.on_subscribe = None
        self.on_unsubscribe = None

        # Connection state machine
        self._connect_state = CONNECT_IDLE
        self._connect_start_time = 0
        self._connect_recv_buffer = bytearray()
        
        # Pending operations tracking
        self._pending_puback = {}  # pid -> (topic, callback)
        self._pending_suback = {}  # pid -> (topics, callback)
        self._pending_unsuback = {}  # pid -> (topics, callback)
        self._pending_pingresp = False
        self._ping_start_time = 0

        # Receive buffer for partial reads
        self._recv_buffer = bytearray()
        self._recv_expected = 0
        self._recv_state = "idle"  # idle, header, remaining_length, payload

    def __enter__(self):
        return self

    def __exit__(
        self,
        exception_type: Optional[Type[BaseException]],
        exception_value: Optional[BaseException],
        traceback: Optional[TracebackType],
    ) -> None:
        self.deinit()

    def deinit(self) -> None:
        """De-initializes the MQTT client and disconnects from the mqtt broker."""
        self.disconnect()

    @property
    def mqtt_msg(self) -> Tuple[int, int]:
        """Returns maximum MQTT payload and topic size."""
        return self._msg_size_lim, MQTT_TOPIC_LENGTH_LIMIT

    @mqtt_msg.setter
    def mqtt_msg(self, msg_size: int) -> None:
        """Sets the maximum MQTT message payload size."""
        if msg_size < MQTT_MSG_MAX_SZ:
            self._msg_size_lim = msg_size

    def will_set(
        self,
        topic: str,
        msg: Union[str, int, float, bytes],
        retain: bool = False,
        qos: int = 0,
    ) -> None:
        """Sets the last will and testament properties. MUST be called before connect_begin()."""
        self.logger.debug("Setting last will properties")
        if self._is_connected:
            raise MMQTTStateError("Last Will should only be called before connect().")

        self._valid_topic(topic)
        if "+" in topic or "#" in topic:
            raise ValueError("Publish topic can not contain wildcards.")

        if msg is None:
            raise ValueError("Message can not be None.")
        if isinstance(msg, (int, float)):
            msg = str(msg).encode("ascii")
        elif isinstance(msg, str):
            msg = str(msg).encode("utf-8")
        elif isinstance(msg, bytes):
            pass
        else:
            raise ValueError("Invalid message data type.")
        if len(msg) > MQTT_MSG_MAX_SZ:
            raise ValueError(f"Message size larger than {MQTT_MSG_MAX_SZ} bytes.")

        self._valid_qos(qos)

        self._lw_qos = qos
        self._lw_topic = topic
        self._lw_msg = msg
        self._lw_retain = retain
        self.logger.debug("Last will properties successfully set")

    def add_topic_callback(self, mqtt_topic: str, callback_method) -> None:
        """Registers a callback_method for a specific MQTT topic."""
        if mqtt_topic is None or callback_method is None:
            raise ValueError("MQTT topic and callback method must both be defined.")
        self._on_message_filtered[mqtt_topic] = callback_method

    def remove_topic_callback(self, mqtt_topic: str) -> None:
        """Removes a registered callback method."""
        if mqtt_topic is None:
            raise ValueError("MQTT Topic must be defined.")
        try:
            del self._on_message_filtered[mqtt_topic]
        except KeyError:
            raise KeyError("MQTT topic callback not added with add_topic_callback.") from None

    @property
    def on_message(self):
        """Called when a new message has been received on a subscribed topic."""
        return self._on_message

    @on_message.setter
    def on_message(self, method) -> None:
        self._on_message = method

    def _handle_on_message(self, topic: str, message: str):
        matched = False
        if topic is not None:
            for callback in self._on_message_filtered.iter_match(topic):
                callback(self, topic, message)
                matched = True

        if not matched and self.on_message:
            self.on_message(self, topic, message)

    def username_pw_set(self, username: str, password: Optional[str] = None) -> None:
        """Set client's username and an optional password."""
        if self._is_connected:
            raise MMQTTStateError("This method must be called before connect().")
        self._username = username
        if password is not None:
            self._password = password

    def connect_begin(
        self,
        clean_session: bool = True,
        host: Optional[str] = None,
        port: Optional[int] = None,
        keep_alive: Optional[int] = None,
        session_id: Optional[str] = None,
    ) -> None:
        """Begins a non-blocking connection attempt to the MQTT broker.
        
        After calling this, repeatedly call connect_poll() until it returns
        CONNECT_CONNECTED or CONNECT_FAILED.
        
        :param bool clean_session: Establishes a persistent session.
        :param str host: Hostname or IP address of the remote broker.
        :param int port: Network port of the remote broker.
        :param int keep_alive: Maximum period for communication, in seconds.
        :param str session_id: unique session ID for multiple connections
        """
        if host:
            self.broker = host
        if port:
            self.port = port
        if keep_alive:
            self.keep_alive = keep_alive

        self._connect_state = CONNECT_PENDING
        self._connect_start_time = ticks_ms()
        self._connect_recv_buffer = bytearray()
        
        self.logger.debug("Beginning non-blocking MQTT connection...")

        # Get a new socket (this is the only blocking part - TLS handshake)
        # NOTE: The TLS handshake will still block for ~100-500ms
        # This is unavoidable in CircuitPython
        try:
            self._sock = self._connection_manager.get_socket(
                self.broker,
                self.port,
                proto="mqtt:",
                session_id=session_id,
                timeout=self._socket_timeout,
                is_ssl=self._is_ssl,
                ssl_context=self._ssl_context,
            )
            self.session_id = session_id
            self._backwards_compatible_sock = not hasattr(self._sock, "recv_into")
            
            # Make socket non-blocking
            self._sock.setblocking(False)
            
        except Exception as e:
            self.logger.error(f"Failed to get socket: {e}")
            self._connect_state = CONNECT_FAILED
            return

        # Build and send CONNECT packet
        fixed_header = bytearray([0x10])
        var_header = bytearray(b"\x00\x04MQTT\x04\x02\0\0")
        var_header[7] = clean_session << 1

        remaining_length = 12 + len(self.client_id.encode("utf-8"))
        if self._username is not None:
            remaining_length += (
                2 + len(self._username.encode("utf-8")) + 
                2 + len(self._password.encode("utf-8"))
            )
            var_header[7] |= 0xC0
        if self.keep_alive:
            assert self.keep_alive < MQTT_TOPIC_LENGTH_LIMIT
            var_header[8] |= self.keep_alive >> 8
            var_header[9] |= self.keep_alive & 0x00FF
        if self._lw_topic:
            remaining_length += 2 + len(self._lw_topic.encode("utf-8")) + 2 + len(self._lw_msg)
            var_header[7] |= 0x4 | (self._lw_qos & 0x1) << 3 | (self._lw_qos & 0x2) << 3
            var_header[7] |= self._lw_retain << 5

        self._encode_remaining_length(fixed_header, remaining_length)
        
        try:
            self._send_bytes(fixed_header)
            self._send_bytes(var_header)
            self._send_str(self.client_id)
            if self._lw_topic:
                self._send_str(self._lw_topic)
                self._send_str(self._lw_msg)
            if self._username is not None:
                self._send_str(self._username)
                self._send_str(self._password)
            self._last_msg_sent_timestamp = ticks_ms()
            self.logger.debug("CONNECT packet sent, waiting for CONNACK...")
        except Exception as e:
            self.logger.error(f"Failed to send CONNECT: {e}")
            self._close_socket()
            self._connect_state = CONNECT_FAILED

    def connect_poll(self) -> int:
        """Poll the connection state. Call repeatedly after connect_begin().
        
        Returns:
            CONNECT_PENDING: Still connecting, call again
            CONNECT_CONNECTED: Successfully connected
            CONNECT_FAILED: Connection failed
            CONNECT_IDLE: Not attempting to connect
        """
        if self._connect_state != CONNECT_PENDING:
            return self._connect_state

        # Check for timeout
        if ticks_diff(ticks_ms(), self._connect_start_time) / 1000 > self._recv_timeout:
            self.logger.error("Connection timeout")
            self._close_socket()
            self._connect_state = CONNECT_FAILED
            return CONNECT_FAILED

        # Try to read CONNACK (non-blocking)
        try:
            # Read packet type
            if len(self._connect_recv_buffer) < 1:
                chunk = self._try_recv(1)
                if chunk:
                    self._connect_recv_buffer.extend(chunk)
                return CONNECT_PENDING

            # Read remaining length
            if len(self._connect_recv_buffer) < 2:
                chunk = self._try_recv(1)
                if chunk:
                    self._connect_recv_buffer.extend(chunk)
                return CONNECT_PENDING

            # Read the rest (should be 2 bytes for CONNACK)
            if len(self._connect_recv_buffer) < 4:
                needed = 4 - len(self._connect_recv_buffer)
                chunk = self._try_recv(needed)
                if chunk:
                    self._connect_recv_buffer.extend(chunk)
                if len(self._connect_recv_buffer) < 4:
                    return CONNECT_PENDING

            # We have the full CONNACK packet
            op = self._connect_recv_buffer[0]
            if op == 32:  # CONNACK
                rc = self._connect_recv_buffer[1:]
                if rc[2] != 0x00:
                    self.logger.error(f"CONNACK error: {CONNACK_ERRORS.get(rc[2], 'Unknown')}")
                    self._close_socket()
                    self._connect_state = CONNECT_FAILED
                    return CONNECT_FAILED

                self._is_connected = True
                self._connect_state = CONNECT_CONNECTED
                result = rc[0] & 1
                
                if self.on_connect is not None:
                    self.on_connect(self, self.user_data, result, rc[2])
                
                self.logger.debug("Connected successfully!")
                return CONNECT_CONNECTED
            else:
                self.logger.error(f"Unexpected packet type: {op}")
                self._close_socket()
                self._connect_state = CONNECT_FAILED
                return CONNECT_FAILED

        except Exception as e:
            self.logger.error(f"Error during connect poll: {e}")
            self._close_socket()
            self._connect_state = CONNECT_FAILED
            return CONNECT_FAILED

    def connect(self, *args, **kwargs) -> int:
        """BLOCKING compatibility method. Use connect_begin() + connect_poll() instead.
        
        This method exists for backward compatibility but will block your UI!
        """
        self.logger.warning("Using blocking connect() - consider using connect_begin() + connect_poll()")
        self.connect_begin(*args, **kwargs)
        while True:
            state = self.connect_poll()
            if state == CONNECT_CONNECTED:
                return 0
            elif state == CONNECT_FAILED:
                raise MMQTTException("Connection failed")
            time.sleep(0.01)

    def _try_recv(self, size: int) -> Optional[bytearray]:
        """Try to receive data without blocking. Returns None if no data available."""
        try:
            if self._backwards_compatible_sock:
                data = self._sock.recv(size)
                return bytearray(data) if data else None
            else:
                buffer = bytearray(size)
                n = self._sock.recv_into(buffer, size)
                return buffer[:n] if n > 0 else None
        except OSError as e:
            if e.errno in (errno.EAGAIN, errno.EWOULDBLOCK):
                return None
            raise

    def _send_bytes(self, buffer: Union[bytes, bytearray, memoryview]):
        """Send bytes, handling partial sends."""
        bytes_sent: int = 0
        bytes_to_send = len(buffer)
        view = memoryview(buffer)
        while bytes_sent < bytes_to_send:
            try:
                sent_now = self._sock.send(view[bytes_sent:])
                if not isinstance(sent_now, int):
                    return
                bytes_sent += sent_now
            except OSError as exc:
                if exc.errno == errno.EAGAIN:
                    # Would block, but we've already sent some - continue
                    time.sleep(0.001)
                    continue
                raise

    def _close_socket(self):
        if self._sock:
            self.logger.debug("Closing socket")
            self._connection_manager.close_socket(self._sock)
            self._sock = None

    def _encode_remaining_length(self, fixed_header: bytearray, remaining_length: int) -> None:
        """Encode Remaining Length [2.2.3]"""
        if remaining_length > 268_435_455:
            raise MMQTTException("invalid remaining length")

        if remaining_length > 0x7F:
            while remaining_length > 0:
                encoded_byte = remaining_length % 0x80
                remaining_length = remaining_length // 0x80
                if remaining_length > 0:
                    encoded_byte |= 0x80
                fixed_header.append(encoded_byte)
        else:
            fixed_header.append(remaining_length)

    def disconnect(self) -> None:
        """Disconnects the MiniMQTT client from the MQTT broker."""
        if not self.is_connected():
            return
            
        self.logger.debug("Sending DISCONNECT packet to broker")
        try:
            self._send_bytes(MQTT_DISCONNECT)
        except (MemoryError, OSError, RuntimeError) as e:
            self.logger.warning(f"Unable to send DISCONNECT packet: {e}")
        
        self._close_socket()
        self._is_connected = False
        self._subscribed_topics = []
        self._last_msg_sent_timestamp = 0
        self._pending_puback.clear()
        self._pending_suback.clear()
        self._pending_unsuback.clear()
        
        if self.on_disconnect is not None:
            self.on_disconnect(self, self.user_data, 0)

    def ping(self) -> None:
        """Sends a non-blocking PING request. 
        
        The PINGRESP will be handled automatically by loop().
        """
        if not self.is_connected():
            raise MMQTTStateError("MiniMQTT is not connected")
            
        self.logger.debug("Sending PINGREQ")
        self._send_bytes(MQTT_PINGREQ)
        self._last_msg_sent_timestamp = ticks_ms()
        self._pending_pingresp = True
        self._ping_start_time = ticks_ms()

    def publish(
        self,
        topic: str,
        msg: Union[str, int, float, bytes],
        retain: bool = False,
        qos: int = 0,
    ) -> None:
        """Publishes a message to a topic (NON-BLOCKING for QoS 0, 1).
        
        For QoS 0: Returns immediately after sending
        For QoS 1: Sends and tracks PUBACK via loop() - callback fires when PUBACK received
        For QoS 2: Not supported
        """
        if not self.is_connected():
            raise MMQTTStateError("MiniMQTT is not connected")
            
        self._valid_topic(topic)
        if "+" in topic or "#" in topic:
            raise ValueError("Publish topic can not contain wildcards.")

        if msg is None:
            raise ValueError("Message can not be None.")
        if isinstance(msg, (int, float)):
            msg = str(msg).encode("ascii")
        elif isinstance(msg, str):
            msg = str(msg).encode("utf-8")
        elif isinstance(msg, bytes):
            pass
        else:
            raise ValueError("Invalid message data type.")
        if len(msg) > MQTT_MSG_MAX_SZ:
            raise ValueError(f"Message size larger than {MQTT_MSG_MAX_SZ} bytes.")

        self._valid_qos(qos)

        # Build packet
        pub_hdr_fixed = bytearray([MQTT_PUBLISH | retain | qos << 1])
        pub_hdr_var = bytearray(struct.pack(">H", len(topic.encode("utf-8"))))
        pub_hdr_var.extend(topic.encode("utf-8"))

        remaining_length = 2 + len(msg) + len(topic.encode("utf-8"))
        if qos > 0:
            remaining_length += 2
            self._pid = self._pid + 1 if self._pid < 0xFFFF else 1
            pub_hdr_var.append(self._pid >> 8)
            pub_hdr_var.append(self._pid & 0xFF)

        self._encode_remaining_length(pub_hdr_fixed, remaining_length)

        self.logger.debug(f"Sending PUBLISH to {topic} (QoS {qos})")
        self._send_bytes(pub_hdr_fixed)
        self._send_bytes(pub_hdr_var)
        self._send_bytes(msg)
        self._last_msg_sent_timestamp = ticks_ms()

        if qos == 0:
            # QoS 0 - fire callback immediately
            if self.on_publish is not None:
                self.on_publish(self, self.user_data, topic, self._pid)
        elif qos == 1:
            # QoS 1 - track for PUBACK, will be handled in loop()
            self._pending_puback[self._pid] = (topic, self.on_publish)

    def subscribe(
        self,
        topic: Optional[Union[tuple, str, list]],
        qos: int = 0
    ) -> None:
        """Subscribes to a topic (NON-BLOCKING).
        
        SUBACK will be handled automatically by loop().
        """
        if not self.is_connected():
            raise MMQTTStateError("MiniMQTT is not connected")
            
        topics = None
        if isinstance(topic, tuple):
            topic, qos = topic
            self._valid_topic(topic)
            self._valid_qos(qos)
        if isinstance(topic, str):
            self._valid_topic(topic)
            self._valid_qos(qos)
            topics = [(topic, qos)]
        if isinstance(topic, list):
            topics = []
            for t, q in topic:
                self._valid_qos(q)
                self._valid_topic(t)
                topics.append((t, q))

        # Build packet
        self.logger.debug("Sending SUBSCRIBE to broker...")
        fixed_header = bytearray([MQTT_SUB])
        packet_length = 2 + (2 * len(topics)) + (1 * len(topics))
        packet_length += sum(len(topic.encode("utf-8")) for topic, qos in topics)
        self._encode_remaining_length(fixed_header, remaining_length=packet_length)
        
        self._send_bytes(fixed_header)
        self._pid = self._pid + 1 if self._pid < 0xFFFF else 1
        packet_id_bytes = self._pid.to_bytes(2, "big")
        self._send_bytes(packet_id_bytes)
        
        payload = b""
        for t, q in topics:
            topic_size = len(t.encode("utf-8")).to_bytes(2, "big")
            qos_byte = q.to_bytes(1, "big")
            payload += topic_size + t.encode() + qos_byte
        
        self._send_bytes(payload)
        self._last_msg_sent_timestamp = ticks_ms()
        
        # Track for SUBACK
        self._pending_suback[self._pid] = (topics, packet_id_bytes)
        self.logger.debug(f"Subscribed to {[t for t, q in topics]}, waiting for SUBACK...")

    def unsubscribe(self, topic: Optional[Union[str, list]]) -> None:
        """Unsubscribes from a topic (NON-BLOCKING).
        
        UNSUBACK will be handled automatically by loop().
        """
        topics = None
        if isinstance(topic, str):
            self._valid_topic(topic)
            topics = [(topic)]
        if isinstance(topic, list):
            topics = []
            for t in topic:
                self._valid_topic(t)
                topics.append(t)
        
        for t in topics:
            if t not in self._subscribed_topics:
                raise MMQTTStateError("Topic must be subscribed to before attempting unsubscribe.")

        # Build packet
        self.logger.debug("Sending UNSUBSCRIBE to broker...")
        fixed_header = bytearray([MQTT_UNSUB])
        packet_length = 2 + (2 * len(topics))
        packet_length += sum(len(topic.encode("utf-8")) for topic in topics)
        self._encode_remaining_length(fixed_header, remaining_length=packet_length)
        
        self._send_bytes(fixed_header)
        self._pid = self._pid + 1 if self._pid < 0xFFFF else 1
        packet_id_bytes = self._pid.to_bytes(2, "big")
        self._send_bytes(packet_id_bytes)
        
        payload = b""
        for t in topics:
            topic_size = len(t.encode("utf-8")).to_bytes(2, "big")
            payload += topic_size + t.encode()
        
        self._send_bytes(payload)
        self._last_msg_sent_timestamp = ticks_ms()
        
        # Track for UNSUBACK
        self._pending_unsuback[self._pid] = (topics, packet_id_bytes)

    def loop(self) -> Optional[list[int]]:
        """NON-BLOCKING message loop. Call this regularly (every 50-100ms).
        
        Processes:
        - Incoming PUBLISH messages
        - PUBACK for QoS 1 publishes
        - SUBACK for subscriptions
        - UNSUBACK for unsubscriptions
        - PINGRESP for pings
        - Automatic keep-alive pings
        
        Returns list of packet types received or None.
        """
        if not self.is_connected():
            return None

        rcs = []

        # Check if we need to send a keep-alive ping
        if ticks_diff(ticks_ms(), self._last_msg_sent_timestamp) / 1000 >= self.keep_alive:
            self.logger.debug("KeepAlive period elapsed - sending PINGREQ")
            try:
                self.ping()
            except Exception as e:
                self.logger.error(f"Failed to send ping: {e}")

        # Check for pending PINGRESP timeout
        if self._pending_pingresp:
            if ticks_diff(ticks_ms(), self._ping_start_time) / 1000 > self.keep_alive:
                self.logger.error("PINGRESP timeout")
                self.disconnect()
                return None

        # Process any available messages (non-blocking)
        while True:
            rc = self._wait_for_msg_nonblocking()
            if rc is None:
                break
            rcs.append(rc)

        return rcs if rcs else None

    def _wait_for_msg_nonblocking(self) -> Optional[int]:
        """Process one message from the socket without blocking.
        
        Returns packet type or None if no data available.
        """
        # Try to read packet type (1 byte)
        if self._recv_state == "idle":
            data = self._try_recv(1)
            if not data:
                return None
            
            pkt_type = data[0] & MQTT_PKT_TYPE_MASK
            self.logger.debug(f"Got message type: {hex(pkt_type)}")
            
            # Handle simple packets immediately
            if pkt_type == MQTT_PINGRESP:
                # Read remaining byte
                sz_data = self._try_recv(1)
                if not sz_data:
                    # Put back the packet type and wait
                    self._recv_buffer = data
                    self._recv_state = "pingresp_sz"
                    return None
                if sz_data[0] != 0x00:
                    raise MMQTTException(f"Unexpected PINGRESP: {sz_data[0]}")
                self._pending_pingresp = False
                self.logger.debug("Got PINGRESP")
                return pkt_type
            
            # For other packets, we need to read remaining length
            self._recv_buffer = data
            self._recv_state = "remaining_length"
            self._recv_expected = 0
        
        # Handle PINGRESP size byte if we're waiting for it
        if self._recv_state == "pingresp_sz":
            sz_data = self._try_recv(1)
            if not sz_data:
                return None
            if sz_data[0] != 0x00:
                raise MMQTTException(f"Unexpected PINGRESP: {sz_data[0]}")
            self._pending_pingresp = False
            self.logger.debug("Got PINGRESP")
            self._recv_state = "idle"
            self._recv_buffer = bytearray()
            return MQTT_PINGRESP
        
        # Read remaining length (variable length encoding)
        if self._recv_state == "remaining_length":
            remaining_len = self._decode_remaining_length_nonblocking()
            if remaining_len is None:
                return None  # Need more data
            
            self._recv_expected = remaining_len
            self._recv_state = "payload"
        
        # Read payload
        if self._recv_state == "payload":
            needed = self._recv_expected - (len(self._recv_buffer) - 1)  # -1 for packet type
            if needed > 0:
                data = self._try_recv(needed)
                if data:
                    self._recv_buffer.extend(data)
                if len(self._recv_buffer) - 1 < self._recv_expected:
                    return None  # Need more data
            
            # We have the complete packet
            pkt_type = self._recv_buffer[0] & MQTT_PKT_TYPE_MASK
            payload = self._recv_buffer[1:]
            
            # Reset state
            self._recv_state = "idle"
            self._recv_buffer = bytearray()
            self._recv_expected = 0
            
            # Process the packet
            return self._process_packet(pkt_type, payload)
        
        return None

    def _decode_remaining_length_nonblocking(self) -> Optional[int]:
        """Decode remaining length without blocking. Returns None if need more data."""
        n = 0
        sh = 0
        i = 1  # Start after packet type byte
        
        while True:
            if i >= len(self._recv_buffer):
                # Need more data
                data = self._try_recv(1)
                if not data:
                    return None
                self._recv_buffer.extend(data)
            
            b = self._recv_buffer[i]
            n |= (b & 0x7F) << sh
            
            if not b & 0x80:
                # Done
                return n
            
            sh += 7
            i += 1
            
            if sh > 28:
                raise MMQTTException("invalid remaining length encoding")

    def _process_packet(self, pkt_type: int, payload: bytearray) -> int:
        """Process a complete packet."""
        
        if pkt_type == 0x40:  # PUBACK
            if len(payload) < 2:
                raise MMQTTException("Invalid PUBACK")
            rcv_pid = payload[0] << 0x08 | payload[1]
            self.logger.debug(f"Got PUBACK for pid {rcv_pid}")
            
            if rcv_pid in self._pending_puback:
                topic, callback = self._pending_puback.pop(rcv_pid)
                if callback is not None:
                    callback(self, self.user_data, topic, rcv_pid)
            return pkt_type
        
        elif pkt_type == MQTT_SUBACK:
            if len(payload) < 2:
                raise MMQTTException("Invalid SUBACK")
            rcv_pid = payload[0] << 0x08 | payload[1]
            self.logger.debug(f"Got SUBACK for pid {rcv_pid}")
            
            if rcv_pid in self._pending_suback:
                topics, _ = self._pending_suback.pop(rcv_pid)
                return_codes = payload[2:]
                
                for i, (t, q) in enumerate(topics):
                    if return_codes[i] not in [0, 1, 2]:
                        raise MMQTTException(f"SUBACK Failure for topic {t}: {hex(return_codes[i])}")
                    
                    if self.on_subscribe is not None:
                        self.on_subscribe(self, self.user_data, t, q)
                    self._subscribed_topics.append(t)
                    self.logger.debug(f"Subscribed to {t}")
            return pkt_type
        
        elif pkt_type == MQTT_UNSUBACK:
            if len(payload) < 2:
                raise MMQTTException("Invalid UNSUBACK")
            rcv_pid = payload[0] << 0x08 | payload[1]
            self.logger.debug(f"Got UNSUBACK for pid {rcv_pid}")
            
            if rcv_pid in self._pending_unsuback:
                topics, _ = self._pending_unsuback.pop(rcv_pid)
                for t in topics:
                    if self.on_unsubscribe is not None:
                        self.on_unsubscribe(self, self.user_data, t, rcv_pid)
                    self._subscribed_topics.remove(t)
                    self.logger.debug(f"Unsubscribed from {t}")
            return pkt_type
        
        elif pkt_type == MQTT_PUBLISH:
            # Parse PUBLISH packet
            i = 0
            topic_len = (payload[i] << 8) | payload[i + 1]
            i += 2
            
            topic = str(payload[i:i + topic_len], "utf-8")
            i += topic_len
            
            # Check for packet ID (QoS > 0)
            pid = 0
            qos = (self._recv_buffer[0] & 0x06) >> 1
            if qos > 0:
                pid = (payload[i] << 8) | payload[i + 1]
                i += 2
            
            # Get message
            raw_msg = payload[i:]
            msg = raw_msg if self._use_binary_mode else str(raw_msg, "utf-8")
            
            self.logger.debug(f"Received PUBLISH on {topic}: {raw_msg[:50]}")
            self._handle_on_message(topic, msg)
            
            # Send PUBACK if QoS 1
            if qos == 1:
                pkt = bytearray(b"\x40\x02\0\0")
                struct.pack_into("!H", pkt, 2, pid)
                self._send_bytes(pkt)
            
            return pkt_type
        
        else:
            self.logger.warning(f"Unhandled packet type: {hex(pkt_type)}")
            return pkt_type

    def _send_str(self, string: str) -> None:
        """Encodes a string and sends it to a socket."""
        if isinstance(string, str):
            self._send_bytes(struct.pack("!H", len(string.encode("utf-8"))))
            self._send_bytes(str.encode(string, "utf-8"))
        else:
            self._send_bytes(struct.pack("!H", len(string)))
            self._send_bytes(string)

    @staticmethod
    def _valid_topic(topic: str) -> None:
        """Validates if topic provided is proper MQTT topic format."""
        if topic is None:
            raise ValueError("Topic may not be NoneType")
        if not topic:
            raise ValueError("Topic may not be empty.")
        if len(topic.encode("utf-8")) > MQTT_TOPIC_LENGTH_LIMIT:
            raise ValueError(f"Encoded topic length is larger than {MQTT_TOPIC_LENGTH_LIMIT}")

    @staticmethod
    def _valid_qos(qos_level: int) -> None:
        """Validates if the QoS level is supported by this library"""
        if isinstance(qos_level, int):
            if qos_level < 0 or qos_level > 2:
                raise NotImplementedError("QoS must be between 0 and 2.")
        else:
            raise ValueError("QoS must be an integer.")

    def is_connected(self) -> bool:
        """Returns MQTT client session status as True if connected, False if not."""
        return self._is_connected and self._sock is not None

    def enable_logger(self, log_pkg, log_level: int = 20, logger_name: str = "log"):
        """Enables library logging."""
        self.logger = log_pkg.getLogger(logger_name)
        self.logger.setLevel(log_level)
        return self.logger

    def disable_logger(self) -> None:
        """Disables logging."""
        self.logger = NullLogger()