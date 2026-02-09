# wxdial/weather/tempest_topics.py
#
# Canonical topic suffixes for Tempest-derived telemetry.
# Use topic(prefix, SUFFIX) to get a full topic string.

# --- suffix constants (no leading slash) ---

T_WIND_LULL_MPH = "wind_lull_mph"
T_WIND_SPEED_MPH = "wind_speed_mph"
T_WIND_GUST_MPH = "wind_gust_mph"
T_WIND_DIR_DEG = "wind_dir_deg"
T_WIND_SAMPLE_INTERVAL_S = "wind_sample_interval_s"

T_PRESSURE_INHG = "pressure_inhg"
T_TEMP_C = "temp_c"
T_TEMP_F = "temp_f"
T_RH = "rh"
T_LUX = "lux"
T_UV_INDEX = "uv_index"
T_LIGHT_WM2 = "light_wm2"

T_RAIN_PREV_MIN_MM = "rain_prev_min_mm"
T_RAIN_PREV_MIN_IN = "rain_prev_min_in"
T_RAIN_RATE_IN_PER_HR = "rain_rate_in_per_hr"

T_PRECIP_TYPE = "precip_type"
T_LIGHTNING_STRIKE_AVG_DISTANCE_MI = "lightning_strike_avg_distance_mi"
T_LIGHTNING_STRIKE_COUNT = "lightning_strike_count"

T_BATTERY_V = "battery_v"
T_REPORT_INTERVAL_MIN = "report_interval_min"

# Time stamps (separate if you care)
T_OBS_TIME_EPOCH = "obs/time_epoch"
T_DEVICE_TIME_EPOCH = "device/time_epoch"
T_HUB_TIME_EPOCH = "hub/time_epoch"

# Device details
T_DEVICE_UPTIME_S = "device/uptime_s"
T_DEVICE_VOLTAGE_V = "device/voltage_v"
T_DEVICE_FIRMWARE_REV = "device/firmware_revision"
T_DEVICE_RSSI_DBM = "device/rssi_dbm"
T_DEVICE_SENSOR_STATUS = "device/sensor_status"
T_DEVICE_DEBUG = "device/debug"

# Hub details
T_HUB_UPTIME_S = "hub/uptime_s"
T_HUB_RSSI_DBM = "hub/rssi_dbm"
T_HUB_SEQ = "hub/seq"
T_HUB_RESET_FLAGS = "hub/reset_flags"
T_HUB_FIRMWARE_REV = "hub/firmware_revision"
T_HUB_RADIO_STATS = "hub/radio_stats"
T_HUB_MQTT_STATS = "hub/mqtt_stats"

# Optional meta topics
T_DEVICE_SERIAL = "device/serial_number"
T_HUB_SERIAL = "hub/serial_number"


# --- supported suffixes for UDP Tempest decoding ---
# Everything your UDP decoder might ever emit.

SUPPORTED_SUFFIXES = {
    T_WIND_LULL_MPH,
    T_WIND_SPEED_MPH,
    T_WIND_GUST_MPH,
    T_WIND_DIR_DEG,
    T_WIND_SAMPLE_INTERVAL_S,

    T_PRESSURE_INHG,
    T_TEMP_C,
    T_TEMP_F,
    T_RH,
    T_LUX,
    T_UV_INDEX,
    T_LIGHT_WM2,

    T_RAIN_PREV_MIN_MM,
    T_RAIN_PREV_MIN_IN,
    T_RAIN_RATE_IN_PER_HR,

    T_PRECIP_TYPE,
    T_LIGHTNING_STRIKE_AVG_DISTANCE_MI,
    T_LIGHTNING_STRIKE_COUNT,

    T_BATTERY_V,
    T_REPORT_INTERVAL_MIN,

    T_OBS_TIME_EPOCH,
    T_DEVICE_TIME_EPOCH,
    T_HUB_TIME_EPOCH,

    T_DEVICE_UPTIME_S,
    T_DEVICE_VOLTAGE_V,
    T_DEVICE_FIRMWARE_REV,
    T_DEVICE_RSSI_DBM,
    T_DEVICE_SENSOR_STATUS,
    T_DEVICE_DEBUG,

    T_HUB_UPTIME_S,
    T_HUB_RSSI_DBM,
    T_HUB_SEQ,
    T_HUB_RESET_FLAGS,
    T_HUB_FIRMWARE_REV,
    T_HUB_RADIO_STATS,
    T_HUB_MQTT_STATS,

    # Only if you plan to publish_meta=True
    T_DEVICE_SERIAL,
    T_HUB_SERIAL,
}


def topic(prefix: str, suffix: str) -> str:
    """
    Join prefix + suffix safely.
    prefix examples: "weather/", "".
    """
    if not prefix:
        return suffix
    # avoid double slashes if someone passes "weather"
    if prefix.endswith("/"):
        return prefix + suffix
    return prefix + "/" + suffix

