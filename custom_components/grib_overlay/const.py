"""Constants for the grib_overlay integration."""

DOMAIN = "grib_overlay"

CONF_SOURCE = "source"
CONF_API_KEY = "api_key"
CONF_NOTIFICATION_API_KEY = "notification_api_key"
CONF_DATASET = "dataset"
CONF_PARAMETERS = "parameters"
# Optional short alias shown as this entry's compact label in the comparison /
# meteogram views (e.g. "KNMI NL"). Empty -> the card derives a label from the
# source (and disambiguates same-source entries automatically).
CONF_ALIAS = "alias"

CONF_RETAIN_RUNS = "retain_runs"
CONF_FORECAST_HORIZON_HOURS = "forecast_horizon_hours"
CONF_UPDATE_INTERVAL_MINUTES = "update_interval_minutes"
# Optional per-parameter custom colour scales, entered as text (one parameter per
# line): "<param_key>: <value>:<#hex>, <value>:<#hex>, ...". Values are in the
# parameter's own source unit (m/s, degC, hPa, mm, m). Baked into the PNG at
# render time; an empty/absent entry uses the parameter's built-in colormap.
CONF_COLOR_SCALES = "color_scales"

DEFAULT_RETAIN_RUNS = 2
DEFAULT_FORECAST_HORIZON_HOURS = 24
DEFAULT_UPDATE_INTERVAL_MINUTES = 30

HTTP_ENTRIES_PATH = "/api/grib_overlay/entries"
HTTP_FRAMES_PATH = "/api/grib_overlay/frames"
HTTP_FRAME_IMAGE_PATH = "/api/grib_overlay/frame"
HTTP_WIND_PATH = "/api/grib_overlay/wind"
HTTP_FIELD_PATH = "/api/grib_overlay/field"
HTTP_POINT_PATH = "/api/grib_overlay/point"
HTTP_POINT_ALL_PATH = "/api/grib_overlay/point_all"

STORAGE_VERSION = 1
