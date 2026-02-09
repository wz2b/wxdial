#######

# wxdial/weather/tempest_decode.py
#
# Decode WeatherFlow Tempest UDP JSON messages into topic->value updates
# suitable for WxFlowUdp (DialMQTT-ish cache + dirty tracking).

try:
    import json
except ImportError:
    # CircuitPython has json
    import json  # type: ignore


# --- unit conversions (floats are fine in CircuitPython) ---

_MPS_TO_MPH = 2.23694
_MBAR_TO_INHG = 0.029529983071445
_MM_TO_IN = 1.0 / 25.4
_KM_TO_MI = 0.621371


def decode_tempest_packet(data_bytes, addr, *, pressure_comp_inhg=0.0):
    """
    Main entry point: parse JSON, dispatch by msg["type"].

    Returns: dict {topic: value}

    pressure_comp_inhg: additive correction applied to obs_st pressure
    publish_meta: if True, publishes serial numbers / firmware / rssi into topics too
    use_prefix: topic prefix, e.g. "weather/" or "".
    """
    try:
        text = data_bytes.decode("utf-8")
    except Exception:
        return {}

    try:
        msg = json.loads(text)
    except Exception:
        return {}

    mtype = msg.get("type")
    if not mtype:
        return {}

    if mtype == "rapid_wind":
        return decode_rapid_wind(msg)

    if mtype == "obs_st":
        return decode_obs_st(msg,pressure_comp_inhg=pressure_comp_inhg)

    if mtype == "device_status":
        return decode_device_status(msg)

    if mtype == "hub_status":
        return decode_hub_status(msg)

    if mtype == "evt_strike":
        return decode_evt_strike(msg)

    if mtype == "evt_precip":
        return decode_evt_precip(msg)

    return {}


def decode_rapid_wind(msg, *, publish_meta=False):
    """
    Example:
      {"type":"rapid_wind","ob":[epoch_s, speed_mps, dir_deg],
       "serial_number":"ST-...", "hub_sn":"HB-..."}
    """
    ob = msg.get("ob")
    if not ob or len(ob) < 3:
        return None

    out = {
        "time_epoch": ob[0],
        "wind_speed_mph": ob[1] * _MPS_TO_MPH,
        "wind_dir_deg": ob[2],
    }

    if publish_meta:
        sn = msg.get("serial_number")
        hub = msg.get("hub_sn")
        if sn is not None:
            out["device_serial"] = sn
        if hub is not None:
            out["hub_serial"] = hub

    return out


def pressure_mbar_to_sea_level(mbar, altitude_m):
    if altitude_m <= 0:
        return mbar
    return mbar * (1.0 - 2.25577e-5 * altitude_m) ** -5.25588

def decode_obs_st(msg, *, altitude_m=0.0, publish_meta=False):
    obs = msg.get("obs")
    if not obs:
        return None
    row = obs[-1]
    if not row or len(row) < 18:
        return None

    station_mbar = row[6]
    sea_level_mbar = pressure_mbar_to_sea_level(station_mbar, altitude_m)

    out = {
        # timestamps
        "time_epoch": row[0],

        # wind (m/s -> mph)
        "wind_lull_mph": row[1] * _MPS_TO_MPH,
        "wind_speed_mph": row[2] * _MPS_TO_MPH,
        "wind_gust_mph": row[3] * _MPS_TO_MPH,
        "wind_dir_deg": row[4],
        "wind_sample_interval_s": row[5],

        # pressure (mbar -> inHg) + comp
        
        "pressure_mbar": station_mbar,
        "pressure_inhg": station_mbar * _MBAR_TO_INHG,
        "pressure_sea_level_mbar": sea_level_mbar,
        "pressure_sea_level_inhg": sea_level_mbar * _MBAR_TO_INHG,

        # temperature
        "temp_c": row[7],
        "temp_f": row[7] * 9.0 / 5.0 + 32.0,

        # humidity / light
        "rh": row[8],
        "lux": row[9],
        "uv_index": row[10],
        "light_wm2": row[11],

        # rain (mm -> in)
        "rain_prev_min_mm": row[12],
        "rain_prev_min_in": row[12] * _MM_TO_IN,
        "rain_rate_in_per_hr": row[12] * _MM_TO_IN * 60.0,

        # lightning
        "precip_type": row[13],
        "lightning_strike_avg_distance_mi": row[14] * _KM_TO_MI,
        "lightning_strike_count": row[15],

        # power / reporting
        "battery_v": row[16],
        "report_interval_min": row[17],
    }

    if publish_meta:
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


def decode_device_status(msg, *, publish_meta=False):
    """
    Example:
      {"type":"device_status","timestamp":epoch_s,"uptime":...,"voltage":2.770,
       "firmware_revision":179,"rssi":-66,"hub_rssi":-56,
       "sensor_status":655871,"debug":0,
       "serial_number":"ST-...","hub_sn":"HB-..."}
    """
    out = {}

    ts = msg.get("timestamp")
    if ts is not None:
        out["time_epoch"] = ts

    for k in (
        "uptime",
        "voltage",
        "firmware_revision",
        "rssi",
        "hub_rssi",
        "sensor_status",
        "debug",
    ):
        v = msg.get(k)
        if v is not None:
            out[k] = v

    if publish_meta:
        sn = msg.get("serial_number")
        hub = msg.get("hub_sn")
        if sn is not None:
            out["device_serial"] = sn
        if hub is not None:
            out["hub_serial"] = hub

    return out or None


def decode_hub_status(msg, *, publish_meta=False):
    """
    Example:
      {"type":"hub_status","timestamp":epoch_s,"uptime":...,"rssi":-41,
       "reset_flags":"PIN,SFT,HRDFLT","seq":...,
       "radio_stats":[25,1,0,3,30876],
       "mqtt_stats":[80,2],
       "serial_number":"HB-...",
       "firmware_revision":"194"}
    """
    out = {}

    ts = msg.get("timestamp")
    if ts is not None:
        out["time_epoch"] = ts

    for k in (
        "uptime",
        "rssi",
        "seq",
        "reset_flags",
        "firmware_revision",
    ):
        v = msg.get(k)
        if v is not None:
            out[k] = v

    rs = msg.get("radio_stats")
    if isinstance(rs, list):
        out["radio_stats"] = rs

    ms = msg.get("mqtt_stats")
    if isinstance(ms, list):
        out["mqtt_stats"] = ms

    if publish_meta:
        sn = msg.get("serial_number")
        if sn is not None:
            out["hub_serial"] = sn

    return out or None



def decode_evt_strike(msg):
    """
    Example:
      {"type":"evt_strike","evt":[epoch_s, distance_km, energy], ...}
    """
    evt = msg.get("evt")
    if not evt or len(evt) < 3:
        return None

    out = {
        "time_epoch": evt[0],
        "distance_mi": evt[1] * _KM_TO_MI,
        "energy": evt[2],
    }

    # Optional accumulated count if present
    count = msg.get("count")
    if count is not None:
        out["count"] = count

    return out


def decode_evt_precip(msg):
    """
    Example:
      {"type":"evt_precip","evt":[epoch_s], ...}
    """
    evt = msg.get("evt")
    if not evt or len(evt) < 1:
        return None

    out = {
        "rain_began_epoch": evt[0],
    }

    # Optional accumulated count if present
    count = msg.get("count")
    if count is not None:
        out["count"] = count

    return out

