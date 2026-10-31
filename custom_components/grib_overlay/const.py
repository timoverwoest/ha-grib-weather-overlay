"""Constants for the grib_overlay integration."""

DOMAIN = "grib_overlay"

CONF_SOURCE = "source"
CONF_API_KEY = "api_key"
CONF_NOTIFICATION_API_KEY = "notification_api_key"
# Optional dedicated KNMI Open Data key for the EDR **observations** collection
# (station downloads). The regular HARMONIE key is often not authorised for that
# dataset (KNMI returns 403); a key with observations access can go here instead.
CONF_OBSERVATIONS_API_KEY = "observations_api_key"
CONF_DATASET = "dataset"
CONF_PARAMETERS = "parameters"
# Optional short alias shown as this entry's compact label in the comparison /
# meteogram views (e.g. "KNMI NL"). Empty -> the card derives a label from the
# source (and disambiguates same-source entries automatically).
CONF_ALIAS = "alias"

# Optional override for where the GRIB working files (the GRIB records being
# decoded, rendered PNG/JSON cache) are kept. Empty -> /var/tmp/grib_overlay,
# which no backup includes, else the system temp dir. Never put this inside
# /config (or /share or /media when those are backed up): this integration's
# file churn both bloats and breaks the backup's tar.
CONF_STORAGE_PATH = "storage_path"
# Not stored: a tick in the options form that gives every source the location
# chosen there, so 18 sources need not be moved one form at a time.
CONF_STORAGE_APPLY_ALL = "storage_apply_all"

CONF_RETAIN_RUNS = "retain_runs"
CONF_FORECAST_HORIZON_HOURS = "forecast_horizon_hours"
CONF_UPDATE_INTERVAL_MINUTES = "update_interval_minutes"
# Take a new run only when the one shown was taken at least this many hours
# ago; 0 takes every run. HARMONIE publishes one every hour (3.4 GB for Europe),
# so 3 here downloads a third of that, with maps at most three hours older.
CONF_MIN_RUN_INTERVAL_HOURS = "min_run_interval_hours"
# Optional per-parameter custom colour scales, entered as text (one parameter per
# line): "<param_key>: <value>:<#hex>, <value>:<#hex>, ...". Values are in the
# parameter's own source unit (m/s, degC, hPa, mm, m). Baked into the PNG at
# render time; an empty/absent entry uses the parameter's built-in colormap.
CONF_COLOR_SCALES = "color_scales"

DEFAULT_RETAIN_RUNS = 2
DEFAULT_FORECAST_HORIZON_HOURS = 24
# The longest reach any dataset has (NOAA GFS). Only a fallback: the options
# flow caps the horizon at the chosen dataset's own forecast_horizon_hours,
# and uses this when the source could not be listed to ask.
MAX_FORECAST_HORIZON_HOURS = 384
DEFAULT_UPDATE_INTERVAL_MINUTES = 30
DEFAULT_MIN_RUN_INTERVAL_HOURS = 0

HTTP_ENTRIES_PATH = "/api/grib_overlay/entries"
HTTP_FRAMES_PATH = "/api/grib_overlay/frames"
HTTP_FRAME_IMAGE_PATH = "/api/grib_overlay/frame"
HTTP_WIND_PATH = "/api/grib_overlay/wind"
HTTP_FIELD_PATH = "/api/grib_overlay/field"
HTTP_POINT_PATH = "/api/grib_overlay/point"
HTTP_POINT_ALL_PATH = "/api/grib_overlay/point_all"
HTTP_STATION_OBS_PATH = "/api/grib_overlay/station_obs"
HTTP_STATIONS_PATH = "/api/grib_overlay/stations"
HTTP_WEATHER_MAPS_PATH = "/api/grib_overlay/weather_maps"
HTTP_CLIENT_ERROR_PATH = "/api/grib_overlay/client_error"

STORAGE_VERSION = 1
