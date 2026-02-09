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


from .tempest_topics import (
    topic,
    SUPPORTED_SUFFIXES,
    T_WIND_LULL_MPH, T_WIND_SPEED_MPH, T_WIND_GUST_MPH, T_WIND_DIR_DEG, T_WIND_SAMPLE_INTERVAL_S,
    T_PRESSURE_INHG, T_TEMP_C, T_TEMP_F, T_RH, T_LUX, T_UV_INDEX, T_LIGHT_WM2,
    T_RAIN_PREV_MIN_MM, T_RAIN_PREV_MIN_IN, T_RAIN_RATE_IN_PER_HR,
    T_PRECIP_TYPE, T_LIGHTNING_STRIKE_AVG_DISTANCE_MI, T_LIGHTNING_STRIKE_COUNT,
    T_BATTERY_V, T_REPORT_INTERVAL_MIN,
    T_OBS_TIME_EPOCH, T_DEVICE_TIME_EPOCH, T_HUB_TIME_EPOCH,
    T_DEVICE_UPTIME_S, T_DEVICE_VOLTAGE_V, T_DEVICE_FIRMWARE_REV, T_DEVICE_RSSI_DBM,
    T_DEVICE_SENSOR_STATUS, T_DEVICE_DEBUG,
    T_HUB_UPTIME_S, T_HUB_RSSI_DBM, T_HUB_SEQ, T_HUB_RESET_FLAGS, T_HUB_FIRMWARE_REV,
    T_HUB_RADIO_STATS, T_HUB_MQTT_STATS,
    T_DEVICE_SERIAL, T_HUB_SERIAL,
)
# --- unit conversions (floats are fine in CircuitPython) ---

_MPS_TO_MPH = 2.23694
_MBAR_TO_INHG = 0.029529983071445
_MM_TO_IN = 1.0 / 25.4
_KM_TO_MI = 0.621371


def decode_tempest_packet(data_bytes, addr, *,
                          pressure_comp_inhg=0.0,
                          publish_meta=False,
                          use_prefix="weather/"):
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
        return decode_rapid_wind(msg, prefix=use_prefix, publish_meta=publish_meta)

    if mtype == "obs_st":
        return decode_obs_st(msg, prefix=use_prefix,
                             pressure_comp_inhg=pressure_comp_inhg,
                             publish_meta=publish_meta)

    if mtype == "device_status":
        return decode_device_status(msg, prefix=use_prefix, publish_meta=publish_meta)

    if mtype == "hub_status":
        return decode_hub_status(msg, prefix=use_prefix, publish_meta=publish_meta)

    # You mentioned evt_* earlier; easy to add later when you see them on wire
    # if mtype == "evt_strike": ...
    # if mtype == "evt_precip": ...

    return {}


def decode_rapid_wind(msg, *, prefix="weather/", publish_meta=False):
    """
    Example:
      {"type":"rapid_wind","ob":[epoch_s, speed_mps, dir_deg], "serial_number":"ST-...", "hub_sn":"HB-..."}
    """
    ob = msg.get("ob")
    if not ob or len(ob) < 3:
        return {}

    epoch_s = ob[0]
    speed_mps = ob[1]
    direction_deg = ob[2]

    out = {
        prefix + "rapid/time_epoch": epoch_s,
        prefix + "rapid/wind_speed_mph": speed_mps * _MPS_TO_MPH,
        prefix + "rapid/wind_dir_deg": direction_deg,
    }

    if publish_meta:
        sn = msg.get("serial_number")
        hub = msg.get("hub_sn")
        if sn is not None:
            out[prefix + "device/serial_number"] = sn
        if hub is not None:
            out[prefix + "hub/serial_number"] = hub

    return out


def decode_obs_st(msg, *, prefix="weather/", pressure_comp_inhg=0.0, publish_meta=False):
    obs = msg.get("obs")
    if not obs:
        return {}
    row = obs[-1]
    if not row or len(row) < 18:
        return {}

    out = {
        topic(prefix, T_OBS_TIME_EPOCH): row[0],

        topic(prefix, T_WIND_LULL_MPH): row[1] * _MPS_TO_MPH,
        topic(prefix, T_WIND_SPEED_MPH): row[2] * _MPS_TO_MPH,
        topic(prefix, T_WIND_GUST_MPH): row[3] * _MPS_TO_MPH,
        topic(prefix, T_WIND_DIR_DEG): row[4],
        topic(prefix, T_WIND_SAMPLE_INTERVAL_S): row[5],

        topic(prefix, T_PRESSURE_INHG): row[6] * _MBAR_TO_INHG + pressure_comp_inhg,

        topic(prefix, T_TEMP_C): row[7],
        topic(prefix, T_TEMP_F): row[7] * 9.0 / 5.0 + 32.0,

        topic(prefix, T_RH): row[8],
        topic(prefix, T_LUX): row[9],
        topic(prefix, T_UV_INDEX): row[10],
        topic(prefix, T_LIGHT_WM2): row[11],

        topic(prefix, T_RAIN_PREV_MIN_MM): row[12],
        topic(prefix, T_RAIN_PREV_MIN_IN): row[12] * _MM_TO_IN,
        topic(prefix, T_RAIN_RATE_IN_PER_HR): row[12] * _MM_TO_IN * 60.0,

        topic(prefix, T_PRECIP_TYPE): row[13],
        topic(prefix, T_LIGHTNING_STRIKE_AVG_DISTANCE_MI): row[14] * _KM_TO_MI,
        topic(prefix, T_LIGHTNING_STRIKE_COUNT): row[15],

        topic(prefix, T_BATTERY_V): row[16],
        topic(prefix, T_REPORT_INTERVAL_MIN): row[17],
    }

    if publish_meta:
        sn = msg.get("serial_number")
        hub = msg.get("hub_sn")
        fw = msg.get("firmware_revision")
        if sn is not None:
            out[topic(prefix, T_DEVICE_SERIAL)] = sn
        if hub is not None:
            out[topic(prefix, T_HUB_SERIAL)] = hub
        if fw is not None:
            out[topic(prefix, T_DEVICE_FIRMWARE_REV)] = fw

    return out


def decode_device_status(msg, *, prefix="weather/", publish_meta=False):
    """
    Example:
      {"type":"device_status","timestamp":epoch_s,"uptime":...,"voltage":2.770,
       "firmware_revision":179,"rssi":-66,"hub_rssi":-56,"sensor_status":655871,"debug":0,
       "serial_number":"ST-...","hub_sn":"HB-..."}
    """
    out = {}

    ts = msg.get("timestamp")
    if ts is not None:
        out[prefix + "device/time_epoch"] = ts

    # These are already in "human" units (volts, dBm, seconds)
    for k_in, k_out in (
        ("uptime", "device/uptime_s"),
        ("voltage", "device/voltage_v"),
        ("firmware_revision", "device/firmware_revision"),
        ("rssi", "device/rssi_dbm"),
        ("hub_rssi", "hub/rssi_dbm"),
        ("sensor_status", "device/sensor_status"),
        ("debug", "device/debug"),
    ):
        v = msg.get(k_in)
        if v is not None:
            out[prefix + k_out] = v

    if publish_meta:
        sn = msg.get("serial_number")
        hub = msg.get("hub_sn")
        if sn is not None:
            out[prefix + "device/serial_number"] = sn
        if hub is not None:
            out[prefix + "hub/serial_number"] = hub

    return out


def decode_hub_status(msg, *, prefix="weather/", publish_meta=False):
    """
    Example:
      {"type":"hub_status","timestamp":epoch_s,"uptime":...,"rssi":-41,
       "reset_flags":"PIN,SFT,HRDFLT","seq":...,
       "radio_stats":[25,1,0,3,30876],"mqtt_stats":[80,2],
       "serial_number":"HB-...","firmware_revision":"194"}
    """
    out = {}

    ts = msg.get("timestamp")
    if ts is not None:
        out[prefix + "hub/time_epoch"] = ts

    for k_in, k_out in (
        ("uptime", "hub/uptime_s"),
        ("rssi", "hub/rssi_dbm"),
        ("seq", "hub/seq"),
        ("reset_flags", "hub/reset_flags"),
        ("firmware_revision", "hub/firmware_revision"),
    ):
        v = msg.get(k_in)
        if v is not None:
            out[prefix + k_out] = v

    # Optional stats arrays (keep raw + maybe also split fields)
    rs = msg.get("radio_stats")
    if isinstance(rs, list):
        out[prefix + "hub/radio_stats"] = rs
        # If you want individual fields, uncomment and name them:
        # if len(rs) >= 5:
        #     out[prefix + "hub/radio/reboots"] = rs[0]
        #     out[prefix + "hub/radio/i2c_errors"] = rs[1]
        #     out[prefix + "hub/radio/whatever2"] = rs[2]
        #     out[prefix + "hub/radio/whatever3"] = rs[3]
        #     out[prefix + "hub/radio/whatever4"] = rs[4]

    ms = msg.get("mqtt_stats")
    if isinstance(ms, list):
        out[prefix + "hub/mqtt_stats"] = ms

    if publish_meta:
        sn = msg.get("serial_number")
        if sn is not None:
            out[prefix + "hub/serial_number"] = sn

    return out



