"""Constants for the grib_overlay integration."""

DOMAIN = "grib_overlay"

CONF_SOURCE = "source"
CONF_API_KEY = "api_key"
CONF_NOTIFICATION_API_KEY = "notification_api_key"
CONF_DATASET = "dataset"
CONF_PARAMETERS = "parameters"

CONF_RETAIN_RUNS = "retain_runs"
CONF_FORECAST_HORIZON_HOURS = "forecast_horizon_hours"
CONF_UPDATE_INTERVAL_MINUTES = "update_interval_minutes"

DEFAULT_RETAIN_RUNS = 2
DEFAULT_FORECAST_HORIZON_HOURS = 24
DEFAULT_UPDATE_INTERVAL_MINUTES = 30

HTTP_ENTRIES_PATH = "/api/grib_overlay/entries"
HTTP_FRAMES_PATH = "/api/grib_overlay/frames"
HTTP_FRAME_IMAGE_PATH = "/api/grib_overlay/frame"
HTTP_WIND_PATH = "/api/grib_overlay/wind"
HTTP_POINT_PATH = "/api/grib_overlay/point"

STORAGE_VERSION = 1
