# wxdial/weather/tempest_decode.py
import json

_MPS_TO_MPH = 2.23694
_MBAR_TO_INHG = 0.029529983071445
_MM_TO_IN = 1.0 / 25.4
_KM_TO_MI = 0.621371


class TempestUdpDecoder:
    def __init__(self, *, altitude_m=0.0, publish_meta=False):
        self.altitude_m = float(altitude_m)
        self.publish_meta = bool(publish_meta)

    def decode(self, data_bytes, addr=None):
        """
        bytes (+ optional addr) -> (mtype, payload_dict) | None
        """
        try:
            text = data_bytes.decode("utf-8")
            msg = json.loads(text)
        except Exception:
            return None

        mtype = msg.get("type")
        if not mtype:
            return None

        if mtype == "rapid_wind":
            payload = self._decode_rapid_wind(msg)
        elif mtype == "obs_st":
            payload = self._decode_obs_st(msg)
        elif mtype == "device_status":
            payload = self._decode_device_status(msg)
        elif mtype == "hub_status":
            payload = self._decode_hub_status(msg)
        elif mtype == "evt_strike":
            payload = self._decode_evt_strike(msg)
        elif mtype == "evt_precip":
            payload = self._decode_evt_precip(msg)
        else:
            return None

        if not payload:
            return None

        # optional: include sender in payload for debugging/routing
        if addr is not None:
            payload["addr"] = addr

        return (mtype, payload)

    def _pressure_mbar_to_sea_level(self, station_mbar, altitude_m):
        if altitude_m <= 0:
            return station_mbar
        return station_mbar * (1.0 - 2.25577e-5 * altitude_m) ** -5.25588

    def _decode_rapid_wind(self, msg):
        ob = msg.get("ob")
        if not ob or len(ob) < 3:
            return None

        out = {
            "time_epoch": ob[0],
            "wind_speed_mph": ob[1] * _MPS_TO_MPH,
            "wind_dir_deg": ob[2],
        }

        if self.publish_meta:
            sn = msg.get("serial_number")
            hub = msg.get("hub_sn")
            if sn is not None:
                out["device_serial"] = sn
            if hub is not None:
                out["hub_serial"] = hub

        return out

    def _decode_obs_st(self, msg):
        obs = msg.get("obs")
        if not obs:
            return None
        row = obs[-1]
        if not row or len(row) < 18:
            return None

        station_mbar = row[6]
        sea_level_mbar = self._pressure_mbar_to_sea_level(station_mbar, self.altitude_m)

        out = {
            "time_epoch": row[0],

            "wind_lull_mph": row[1] * _MPS_TO_MPH,
            "wind_speed_mph": row[2] * _MPS_TO_MPH,
            "wind_gust_mph": row[3] * _MPS_TO_MPH,
            "wind_dir_deg": row[4],
            "wind_sample_interval_s": row[5],

            "pressure_mbar": station_mbar,
            "pressure_inhg": station_mbar * _MBAR_TO_INHG,
            "pressure_sea_level_mbar": sea_level_mbar,
            "pressure_sea_level_inhg": sea_level_mbar * _MBAR_TO_INHG,

            "temp_c": row[7],
            "temp_f": row[7] * 9.0 / 5.0 + 32.0,

            "rh": row[8],
            "lux": row[9],
            "uv_index": row[10],
            "light_wm2": row[11],

            "rain_prev_min_mm": row[12],
            "rain_prev_min_in": row[12] * _MM_TO_IN,
            "rain_rate_in_per_hr": row[12] * _MM_TO_IN * 60.0,

            "precip_type": row[13],
            "lightning_strike_avg_distance_mi": row[14] * _KM_TO_MI,
            "lightning_strike_count": row[15],

            "battery_v": row[16],
            "report_interval_min": row[17],
        }

        if self.publish_meta:
            sn = msg.get("serial_number")
            hub = msg.get("hub_sn")
            fw = msg.get("firmware_revision")
            if sn is not None:
                out["device_serial"] = sn
            if hub is not None:
                out["hub_serial"] = hub
            if fw is not None:
                out["device_firmware_revision"] = fw

        return out

    def _decode_device_status(self, msg):
        out = {}
        ts = msg.get("timestamp")
        if ts is not None:
            out["time_epoch"] = ts

        for k in ("uptime", "voltage", "firmware_revision", "rssi", "hub_rssi", "sensor_status", "debug"):
            v = msg.get(k)
            if v is not None:
                out[k] = v

        if self.publish_meta:
            sn = msg.get("serial_number")
            hub = msg.get("hub_sn")
            if sn is not None:
                out["device_serial"] = sn
            if hub is not None:
                out["hub_serial"] = hub

        return out or None

    def _decode_hub_status(self, msg):
        out = {}
        ts = msg.get("timestamp")
        if ts is not None:
            out["time_epoch"] = ts

        for k in ("uptime", "rssi", "seq", "reset_flags", "firmware_revision"):
            v = msg.get(k)
            if v is not None:
                out[k] = v

        rs = msg.get("radio_stats")
        if isinstance(rs, list):
            out["radio_stats"] = rs

        ms = msg.get("mqtt_stats")
        if isinstance(ms, list):
            out["mqtt_stats"] = ms

        if self.publish_meta:
            sn = msg.get("serial_number")
            if sn is not None:
                out["hub_serial"] = sn

        return out or None

    def _decode_evt_strike(self, msg):
        evt = msg.get("evt")
        if not evt or len(evt) < 3:
            return None

        out = {
            "time_epoch": evt[0],
            "distance_mi": evt[1] * _KM_TO_MI,
            "energy": evt[2],
        }

        count = msg.get("count")
        if count is not None:
            out["count"] = count

        return out

    def _decode_evt_precip(self, msg):
        evt = msg.get("evt")
        if not evt or len(evt) < 1:
            return None

        out = {"rain_began_epoch": evt[0]}

        count = msg.get("count")
        if count is not None:
            out["count"] = count

        return out
