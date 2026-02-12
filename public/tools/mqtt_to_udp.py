#!/usr/bin/env python3
"""
mqtt_to_udp.py

Subscribe to an MQTT topic and forward each message payload verbatim over UDP.

Defaults:
  - MQTT broker: localhost:8883 (TLS)
  - Topic: weather/raw
  - UDP dest port: 50222

TLS behavior:
  - Ignores certificate validity (CERT_NONE + tls_insecure_set(True))

Examples:
  python mqtt_to_udp.py --udp-target 192.168.1.50
  python mqtt_to_udp.py --mqtt-host broker.local --mqtt-port 8883 --udp-target 10.0.0.42
  python mqtt_to_udp.py --mqtt-port 1883 --no-tls --udp-target 192.168.1.50
  python mqtt_to_udp.py --udp-target 192.168.1.50 --udp-bind 192.168.1.10
"""

from __future__ import annotations

import argparse
import socket
import ssl
import sys
import time
from typing import Optional

try:
    import paho.mqtt.client as mqtt
except ImportError:
    print("Missing dependency: paho-mqtt", file=sys.stderr)
    print("Install with:  pip install paho-mqtt", file=sys.stderr)
    raise


def main() -> int:
    ap = argparse.ArgumentParser(description="Forward MQTT messages to UDP.")
    ap.add_argument("--mqtt-host", default="localhost", help="MQTT broker hostname (default: localhost)")
    ap.add_argument("--mqtt-port", type=int, default=8883, help="MQTT broker port (default: 8883)")
    ap.add_argument("--mqtt-username", default=None, help="MQTT username (optional)")
    ap.add_argument("--mqtt-password", default=None, help="MQTT password (optional)")
    ap.add_argument("--topic", default="weather/raw", help="MQTT topic to subscribe to (default: weather/raw)")
    ap.add_argument("--qos", type=int, default=0, choices=[0, 1, 2], help="Subscription QoS (default: 0)")

    ap.add_argument("--udp-target", required=True, help="Destination IP/host to send UDP packets to")
    ap.add_argument("--udp-port", type=int, default=50222, help="Destination UDP port (default: 50222)")
    ap.add_argument("--udp-bind", default=None, help="Optional local source IP to bind UDP socket to (multi-NIC PCs)")

    ap.add_argument("--client-id", default=None, help="Optional MQTT client id (default: auto)")
    ap.add_argument("--keepalive", type=int, default=30, help="MQTT keepalive seconds (default: 30)")
    ap.add_argument("--no-tls", action="store_true", help="Disable TLS (useful if broker is plain MQTT on 1883)")
    ap.add_argument("--verbose", action="store_true", help="Log every forwarded payload (can be noisy)")

    args = ap.parse_args()

    udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        if args.udp_bind:
            udp_sock.bind((args.udp_bind, 0))  # ephemeral source port
    except OSError as e:
        print(f"Failed to bind UDP socket to {args.udp_bind}: {e}", file=sys.stderr)
        return 2

    udp_dest = (args.udp_target, args.udp_port)

    client = mqtt.Client(client_id=args.client_id or "", protocol=mqtt.MQTTv311)

    if args.mqtt_username is not None:
        client.username_pw_set(args.mqtt_username, args.mqtt_password)

    if not args.no_tls:
        # Ignore cert validity completely.
        # tls_insecure_set(True) bypasses hostname check and allows self-signed/untrusted certs.
        client.tls_set(
            ca_certs=None,
            certfile=None,
            keyfile=None,
            cert_reqs=ssl.CERT_NONE,
            tls_version=ssl.PROTOCOL_TLS_CLIENT,
        )
        client.tls_insecure_set(True)

    # --- MQTT callbacks ---

    state = {"connected": False, "subscribed": False, "last_msg_ts": None, "count": 0}

    def on_connect(_client, _userdata, _flags, rc, properties=None):  # paho v2 supports properties
        if rc != 0:
            print(f"MQTT connect failed rc={rc}", file=sys.stderr)
            return
        state["connected"] = True
        state["subscribed"] = False
        print(f"MQTT connected to {args.mqtt_host}:{args.mqtt_port} (tls={'off' if args.no_tls else 'on'})")
        print(f"Subscribing to {args.topic} (qos={args.qos}) ...")
        client.subscribe(args.topic, qos=args.qos)

    def on_disconnect(_client, _userdata, rc, properties=None):
        state["connected"] = False
        state["subscribed"] = False
        if rc != 0:
            print(f"MQTT disconnected unexpectedly rc={rc} (will auto-reconnect)", file=sys.stderr)
        else:
            print("MQTT disconnected.")

    def on_subscribe(_client, _userdata, mid, granted_qos, properties=None):
        state["subscribed"] = True
        print(f"Subscribed. granted_qos={granted_qos}")
        print(f"Forwarding MQTT -> UDP {udp_dest[0]}:{udp_dest[1]}")
        if args.udp_bind:
            print(f"  (UDP source bound to {args.udp_bind})")
        print("Ctrl+C to stop.\n")

    def on_message(_client, _userdata, msg):
        # Forward payload EXACTLY as received (bytes) — no JSON parse, no newline.
        payload = msg.payload  # type: bytes
        try:
            udp_sock.sendto(payload, udp_dest)
        except OSError as e:
            print(f"UDP sendto failed: {e}", file=sys.stderr)
            return

        state["count"] += 1
        state["last_msg_ts"] = time.time()

        if args.verbose:
            # Safe-ish printing: show bytes as UTF-8 if possible, else repr
            try:
                s = payload.decode("utf-8")
            except UnicodeDecodeError:
                s = repr(payload)
            print(f"#{state['count']} {msg.topic} -> {udp_dest[0]}:{udp_dest[1]} len={len(payload)} payload={s}")
        else:
            print(f"#{state['count']} len={len(payload)}")

    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    client.on_subscribe = on_subscribe
    client.on_message = on_message

    # Auto-reconnect tuning
    client.reconnect_delay_set(min_delay=1, max_delay=10)

    # Connect + loop
    try:
        print(f"Connecting MQTT to {args.mqtt_host}:{args.mqtt_port} ...")
        client.connect(args.mqtt_host, args.mqtt_port, keepalive=args.keepalive)
        client.loop_forever(retry_first_connection=True)
        return 0
    except KeyboardInterrupt:
        print("\nStopped.")
        try:
            client.disconnect()
        except Exception:
            pass
        return 0
    finally:
        udp_sock.close()


if __name__ == "__main__":
    raise SystemExit(main())
