#!/usr/bin/env python3
"""
Replay a captured Tempest UDP stream to a fixed target IP on port 50222.

- Sends the JSON payloads exactly as listed (UTF-8 bytes, no trailing newline).
- Preserves the relative timing between packets using the bracketed timestamps.
- Supports looping and speed scaling.

Example:
  python tempest_udp_replay.py --target 192.168.1.50
  python tempest_udp_replay.py --target 192.168.1.50 --loop
  python tempest_udp_replay.py --target 192.168.1.50 --speed 2.0   # 2x faster
"""

from __future__ import annotations

import argparse
import socket
import sys
import time
from dataclasses import dataclass
from typing import List


@dataclass(frozen=True)
class Frame:
    t: float      # seconds (monotonic-ish) from the capture, used only for relative timing
    payload: str  # JSON string


FRAMES: List[Frame] = [
    Frame(142031.06, r'{"serial_number":"ST-00167264","type":"rapid_wind","hub_sn":"HB-00034703","ob":[1770728000,0.90,150]}'),
    Frame(142034.13, r'{"serial_number":"ST-00167264","type":"rapid_wind","hub_sn":"HB-00034703","ob":[1770728003,0.96,150]}'),
    Frame(142037.31, r'{"serial_number":"ST-00167264","type":"rapid_wind","hub_sn":"HB-00034703","ob":[1770728006,1.01,153]}'),
    Frame(142040.25, r'{"serial_number":"HB-00034703","type":"hub_status","firmware_revision":"194","uptime":14497699,"rssi":-42,"timestamp":1770728009,"reset_flags":"PIN,SFT,HRDFLT","seq":1447903,"radio_stats":[25,1,0,3,30876],"mqtt_stats":[80,2]}'),
    Frame(142043.25, r'{"serial_number":"ST-00167264","type":"rapid_wind","hub_sn":"HB-00034703","ob":[1770728012,0.78,159]}'),
    Frame(142049.25, r'{"serial_number":"ST-00167264","type":"rapid_wind","hub_sn":"HB-00034703","ob":[1770728018,0.77,160]}'),
    Frame(142050.31, r'{"serial_number":"HB-00034703","type":"hub_status","firmware_revision":"194","uptime":14497709,"rssi":-42,"timestamp":1770728019,"reset_flags":"PIN,SFT,HRDFLT","seq":1447904,"radio_stats":[25,1,0,3,30876],"mqtt_stats":[80,2]}'),
    Frame(142055.13, r'{"serial_number":"ST-00167264","type":"rapid_wind","hub_sn":"HB-00034703","ob":[1770728024,0.92,179]}'),
    Frame(142061.06, r'{"serial_number":"ST-00167264","type":"rapid_wind","hub_sn":"HB-00034703","ob":[1770728030,0.73,177]}'),
    Frame(142070.06, r'{"serial_number":"ST-00167264","type":"rapid_wind","hub_sn":"HB-00034703","ob":[1770728039,0.48,208]}'),
    Frame(142073.00, r'{"serial_number":"ST-00167264","type":"rapid_wind","hub_sn":"HB-00034703","ob":[1770728042,0.52,195]}'),
    Frame(142075.69, r'{"serial_number":"ST-00167264","type":"rapid_wind","hub_sn":"HB-00034703","ob":[1770728045,0.15,195]}'),
    Frame(142080.31, r'{"serial_number":"HB-00034703","type":"hub_status","firmware_revision":"194","uptime":14497739,"rssi":-41,"timestamp":1770728049,"reset_flags":"PIN,SFT,HRDFLT","seq":1447907,"radio_stats":[25,1,0,3,30876],"mqtt_stats":[80,2]}'),
    Frame(142082.06, r'{"serial_number":"ST-00167264","type":"rapid_wind","hub_sn":"HB-00034703","ob":[1770728051,0.27,250]}'),
    Frame(142085.13, r'{"serial_number":"ST-00167264","type":"rapid_wind","hub_sn":"HB-00034703","ob":[1770728054,0.59,207]}'),
    Frame(142088.19, r'{"serial_number":"ST-00167264","type":"rapid_wind","hub_sn":"HB-00034703","ob":[1770728057,0.49,205]}'),
    Frame(142096.69, r'{"serial_number":"ST-00167264","type":"rapid_wind","hub_sn":"HB-00034703","ob":[1770728066,0.01,205]}'),
    Frame(142102.69, r'{"serial_number":"ST-00167264","type":"rapid_wind","hub_sn":"HB-00034703","ob":[1770728072,0.00,0]}'),
    Frame(142109.06, r'{"serial_number":"ST-00167264","type":"rapid_wind","hub_sn":"HB-00034703","ob":[1770728078,0.55,192]}'),
    Frame(142112.25, r'{"serial_number":"ST-00167264","type":"rapid_wind","hub_sn":"HB-00034703","ob":[1770728081,0.35,303]}'),
    Frame(142114.69, r'{"serial_number":"ST-00167264","type":"rapid_wind","hub_sn":"HB-00034703","ob":[1770728084,0.10,303]}'),
    Frame(142117.69, r'{"serial_number":"ST-00167264","type":"rapid_wind","hub_sn":"HB-00034703","ob":[1770728087,0.03,303]}'),
    Frame(142126.75, r'{"serial_number":"ST-00167264","type":"rapid_wind","hub_sn":"HB-00034703","ob":[1770728096,0.03,213]}'),
    Frame(142129.75, r'{"serial_number":"ST-00167264","type":"rapid_wind","hub_sn":"HB-00034703","ob":[1770728099,0.01,213]}'),
    Frame(142130.25, r'{"serial_number":"HB-00034703","type":"hub_status","firmware_revision":"194","uptime":14497789,"rssi":-42,"timestamp":1770728099,"reset_flags":"PIN,SFT,HRDFLT","seq":1447912,"radio_stats":[25,1,0,3,30876],"mqtt_stats":[80,2]}'),
    Frame(142131.69, r'{"serial_number":"ST-00167264","type":"device_status","hub_sn":"HB-00034703","timestamp":1770728101,"uptime":33348922,"voltage":2.664,"firmware_revision":179,"rssi":-65,"hub_rssi":-55,"sensor_status":655871,"debug":0}'),
    Frame(142132.75, r'{"serial_number":"ST-00167264","type":"rapid_wind","hub_sn":"HB-00034703","ob":[1770728102,0.00,0]}'),
    Frame(142135.69, r'{"serial_number":"ST-00167264","type":"rapid_wind","hub_sn":"HB-00034703","ob":[1770728105,0.00,0]}'),
    Frame(142144.69, r'{"serial_number":"ST-00167264","type":"rapid_wind","hub_sn":"HB-00034703","ob":[1770728114,0.00,0]}'),
    Frame(142150.75, r'{"serial_number":"ST-00167264","type":"rapid_wind","hub_sn":"HB-00034703","ob":[1770728120,0.00,0]}'),
    Frame(142160.38, r'{"serial_number":"HB-00034703","type":"hub_status","firmware_revision":"194","uptime":14497819,"rssi":-42,"timestamp":1770728129,"reset_flags":"PIN,SFT,HRDFLT","seq":1447915,"radio_stats":[25,1,0,3,30876],"mqtt_stats":[80,2]}'),
    Frame(142165.63, r'{"serial_number":"ST-00167264","type":"rapid_wind","hub_sn":"HB-00034703","ob":[1770728135,0.00,0]}'),
    Frame(142171.75, r'{"serial_number":"ST-00167264","type":"rapid_wind","hub_sn":"HB-00034703","ob":[1770728141,0.00,0]}'),
    Frame(142177.69, r'{"serial_number":"ST-00167264","type":"rapid_wind","hub_sn":"HB-00034703","ob":[1770728147,0.00,0]}'),
    Frame(142180.63, r'{"serial_number":"ST-00167264","type":"rapid_wind","hub_sn":"HB-00034703","ob":[1770728150,0.00,0]}'),
    Frame(142183.81, r'{"serial_number":"ST-00167264","type":"rapid_wind","hub_sn":"HB-00034703","ob":[1770728153,0.00,0]}'),
    Frame(142187.19, r'{"serial_number":"ST-00167264","type":"rapid_wind","hub_sn":"HB-00034703","ob":[1770728156,0.16,261]}'),
    Frame(142189.69, r'{"serial_number":"ST-00167264","type":"rapid_wind","hub_sn":"HB-00034703","ob":[1770728159,0.04,261]}'),
    Frame(142191.69, r'{"serial_number":"ST-00167264","type":"device_status","hub_sn":"HB-00034703","timestamp":1770728161,"uptime":33348982,"voltage":2.667,"firmware_revision":179,"rssi":-65,"hub_rssi":-56,"sensor_status":655871,"debug":0}'),
    Frame(142191.88, r'{"serial_number":"ST-00167264","type":"obs_st","hub_sn":"HB-00034703","obs":[[1770728161,0.00,0.01,0.16,262,3,1000.55,-6.70,80.82,4149,0.09,35,0.000000,0,0,0,2.667,1]],"firmware_revision":179}'),
    Frame(142195.69, r'{"serial_number":"ST-00167264","type":"rapid_wind","hub_sn":"HB-00034703","ob":[1770728165,0.00,0]}'),
    Frame(142198.69, r'{"serial_number":"ST-00167264","type":"rapid_wind","hub_sn":"HB-00034703","ob":[1770728168,0.00,0]}'),
    Frame(142204.69, r'{"serial_number":"ST-00167264","type":"rapid_wind","hub_sn":"HB-00034703","ob":[1770728174,0.00,0]}'),
    Frame(142207.81, r'{"serial_number":"ST-00167264","type":"rapid_wind","hub_sn":"HB-00034703","ob":[1770728177,0.00,0]}'),
    Frame(142216.69, r'{"serial_number":"ST-00167264","type":"rapid_wind","hub_sn":"HB-00034703","ob":[1770728186,0.00,0]}'),
    Frame(142222.63, r'{"serial_number":"ST-00167264","type":"rapid_wind","hub_sn":"HB-00034703","ob":[1770728192,0.00,0]}'),
    Frame(142234.69, r'{"serial_number":"ST-00167264","type":"rapid_wind","hub_sn":"HB-00034703","ob":[1770728204,0.00,0]}'),
    Frame(142240.63, r'{"serial_number":"ST-00167264","type":"rapid_wind","hub_sn":"HB-00034703","ob":[1770728210,0.11,194]}'),
    Frame(142247.00, r'{"serial_number":"ST-00167264","type":"rapid_wind","hub_sn":"HB-00034703","ob":[1770728216,0.29,198]}'),
    Frame(142250.06, r'{"serial_number":"ST-00167264","type":"rapid_wind","hub_sn":"HB-00034703","ob":[1770728219,0.18,299]}'),
    Frame(142250.38, r'{"serial_number":"HB-00034703","type":"hub_status","firmware_revision":"194","uptime":14497909,"rssi":-43,"timestamp":1770728219,"reset_flags":"PIN,SFT,HRDFLT","seq":1447924,"radio_stats":[25,1,0,3,30876],"mqtt_stats":[80,2]}'),
    Frame(142251.75, r'{"serial_number":"ST-00167264","type":"device_status","hub_sn":"HB-00034703","timestamp":1770728221,"uptime":33349042,"voltage":2.668,"firmware_revision":179,"rssi":-65,"hub_rssi":-55,"sensor_status":655871,"debug":0}'),
    Frame(142256.00, r'{"serial_number":"ST-00167264","type":"rapid_wind","hub_sn":"HB-00034703","ob":[1770728225,0.61,197]}'),
    Frame(142259.19, r'{"serial_number":"ST-00167264","type":"rapid_wind","hub_sn":"HB-00034703","ob":[1770728228,0.56,199]}'),
    Frame(142260.44, r'{"serial_number":"HB-00034703","type":"hub_status","firmware_revision":"194","uptime":14497919,"rssi":-42,"timestamp":1770728229,"reset_flags":"PIN,SFT,HRDFLT","seq":1447925,"radio_stats":[25,1,0,3,30876],"mqtt_stats":[80,2]}'),
    Frame(142265.25, r'{"serial_number":"ST-00167264","type":"rapid_wind","hub_sn":"HB-00034703","ob":[1770728234,0.13,259]}'),
    Frame(142270.44, r'{"serial_number":"HB-00034703","type":"hub_status","firmware_revision":"194","uptime":14497929,"rssi":-41,"timestamp":1770728239,"reset_flags":"PIN,SFT,HRDFLT","seq":1447926,"radio_stats":[25,1,0,3,30876],"mqtt_stats":[80,2]}'),
    Frame(142270.69, r'{"serial_number":"ST-00167264","type":"rapid_wind","hub_sn":"HB-00034703","ob":[1770728240,0.03,267]}'),
    Frame(142276.63, r'{"serial_number":"ST-00167264","type":"rapid_wind","hub_sn":"HB-00034703","ob":[1770728246,0.00,0]}'),
    Frame(142279.69, r'{"serial_number":"ST-00167264","type":"rapid_wind","hub_sn":"HB-00034703","ob":[1770728249,0.00,0]}'),
    Frame(142280.38, r'{"serial_number":"HB-00034703","type":"hub_status","firmware_revision":"194","uptime":14497939,"rssi":-42,"timestamp":1770728249,"reset_flags":"PIN,SFT,HRDFLT","seq":1447927,"radio_stats":[25,1,0,3,30876],"mqtt_stats":[80,2]}'),
    Frame(142282.63, r'{"serial_number":"ST-00167264","type":"rapid_wind","hub_sn":"HB-00034703","ob":[1770728252,0.00,0]}'),
    Frame(142285.69, r'{"serial_number":"ST-00167264","type":"rapid_wind","hub_sn":"HB-00034703","ob":[1770728255,0.00,0]}'),
    Frame(142289.00, r'{"serial_number":"ST-00167264","type":"rapid_wind","hub_sn":"HB-00034703","ob":[1770728258,0.32,312]}'),
    Frame(142295.06, r'{"serial_number":"ST-00167264","type":"rapid_wind","hub_sn":"HB-00034703","ob":[1770728264,0.17,261]}'),
    Frame(142298.19, r'{"serial_number":"ST-00167264","type":"rapid_wind","hub_sn":"HB-00034703","ob":[1770728267,0.37,274]}'),
    Frame(142304.06, r'{"serial_number":"ST-00167264","type":"rapid_wind","hub_sn":"HB-00034703","ob":[1770728273,0.36,326]}'),
    Frame(142309.69, r'{"serial_number":"ST-00167264","type":"rapid_wind","hub_sn":"HB-00034703","ob":[1770728279,0.10,287]}'),
    Frame(142311.63, r'{"serial_number":"ST-00167264","type":"device_status","hub_sn":"HB-00034703","timestamp":1770728281,"uptime":33349102,"voltage":2.664,"firmware_revision":179,"rssi":-65,"hub_rssi":-55,"sensor_status":655871,"debug":0}'),
    Frame(142312.63, r'{"serial_number":"ST-00167264","type":"rapid_wind","hub_sn":"HB-00034703","ob":[1770728282,0.03,287]}'),
    Frame(142318.69, r'{"serial_number":"ST-00167264","type":"rapid_wind","hub_sn":"HB-00034703","ob":[1770728288,0.00,0]}'),
    Frame(142320.44, r'{"serial_number":"HB-00034703","type":"hub_status","firmware_revision":"194","uptime":14497979,"rssi":-42,"timestamp":1770728289,"reset_flags":"PIN,SFT,HRDFLT","seq":1447931,"radio_stats":[25,1,0,3,30876],"mqtt_stats":[80,2]}'),
    Frame(142321.69, r'{"serial_number":"ST-00167264","type":"rapid_wind","hub_sn":"HB-00034703","ob":[1770728291,0.00,0]}'),
    Frame(142330.50, r'{"serial_number":"HB-00034703","type":"hub_status","firmware_revision":"194","uptime":14497989,"rssi":-41,"timestamp":1770728299,"reset_flags":"PIN,SFT,HRDFLT","seq":1447932,"radio_stats":[25,1,0,3,30876],"mqtt_stats":[80,2]}'),
    Frame(142333.63, r'{"serial_number":"ST-00167264","type":"rapid_wind","hub_sn":"HB-00034703","ob":[1770728302,0.00,0]}'),
    Frame(142337.00, r'{"serial_number":"ST-00167264","type":"rapid_wind","hub_sn":"HB-00034703","ob":[1770728306,0.19,276]}'),
    Frame(142340.00, r'{"serial_number":"ST-00167264","type":"rapid_wind","hub_sn":"HB-00034703","ob":[1770728309,0.41,205]}'),
    Frame(142340.50, r'{"serial_number":"HB-00034703","type":"hub_status","firmware_revision":"194","uptime":14497999,"rssi":-42,"timestamp":1770728309,"reset_flags":"PIN,SFT,HRDFLT","seq":1447933,"radio_stats":[25,1,0,3,30876],"mqtt_stats":[80,2]}'),
    Frame(142342.94, r'{"serial_number":"ST-00167264","type":"rapid_wind","hub_sn":"HB-00034703","ob":[1770728312,0.40,185]}'),
    Frame(142345.63, r'{"serial_number":"ST-00167264","type":"rapid_wind","hub_sn":"HB-00034703","ob":[1770728314,0.11,185]}'),
    Frame(142350.44, r'{"serial_number":"HB-00034703","type":"hub_status","firmware_revision":"194","uptime":14498009,"rssi":-42,"timestamp":1770728319,"reset_flags":"PIN,SFT,HRDFLT","seq":1447934,"radio_stats":[25,1,0,3,30876],"mqtt_stats":[80,2]}'),
]


def run(target_ip: str, target_port: int, speed: float, loop: bool, bind_ip: str | None) -> int:
    if not FRAMES:
        print("No frames to send.", file=sys.stderr)
        return 2

    # Precompute inter-frame delays (seconds), then scale by speed.
    times = [f.t for f in FRAMES]
    base_t0 = times[0]
    rel = [t - base_t0 for t in times]
    delays = [0.0] + [max(0.0, rel[i] - rel[i - 1]) for i in range(1, len(rel))]

    if speed <= 0:
        print("--speed must be > 0", file=sys.stderr)
        return 2
    delays = [d / speed for d in delays]

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # Optional: bind to a specific local IP (useful if your desktop has multiple NICs/VPNs)
        if bind_ip:
            sock.bind((bind_ip, 0))  # ephemeral source port
        target = (target_ip, target_port)

        print(f"Sending {len(FRAMES)} UDP packets to {target_ip}:{target_port}")
        if bind_ip:
            print(f"  (bound source IP {bind_ip})")
        print(f"  speed={speed}x  loop={'on' if loop else 'off'}")
        print("Ctrl+C to stop.\n")

        while True:
            for i, frame in enumerate(FRAMES):
                if delays[i] > 0:
                    time.sleep(delays[i])

                data = frame.payload.encode("utf-8")
                sock.sendto(data, target)

                # helpful local log
                print(f"[{frame.t:0.2f}] -> {target_ip}:{target_port}  len={len(data)}  type={_peek_type(frame.payload)}")

            if not loop:
                break

            # Tiny breather between loops so logs are readable
            time.sleep(0.25)

        return 0
    except KeyboardInterrupt:
        print("\nStopped.")
        return 0
    finally:
        sock.close()


def _peek_type(payload: str) -> str:
    # Cheap 'type' extraction without JSON parsing (keeps payload exactly identical)
    key = '"type":"'
    idx = payload.find(key)
    if idx < 0:
        return "?"
    start = idx + len(key)
    end = payload.find('"', start)
    if end < 0:
        return "?"
    return payload[start:end]


def main() -> int:
    ap = argparse.ArgumentParser(description="Replay captured Tempest UDP JSON frames to a fixed target.")
    ap.add_argument("--target", required=True, help="Target IP address (your M5Dial IP).")
    ap.add_argument("--port", type=int, default=50222, help="Target UDP port (default: 50222).")
    ap.add_argument("--speed", type=float, default=1.0, help="Replay speed multiplier (default: 1.0).")
    ap.add_argument("--loop", action="store_true", help="Loop forever.")
    ap.add_argument("--bind", default=None, help="Optional source IP to bind to (useful on multi-NIC PCs).")
    args = ap.parse_args()

    return run(
        target_ip=args.target,
        target_port=args.port,
        speed=args.speed,
        loop=args.loop,
        bind_ip=args.bind,
    )


if __name__ == "__main__":
    raise SystemExit(main())
