"""Diagnostics for a config entry: what this entry is doing, without the keys.

What goes wrong with this integration is almost never visible in a log line on
its own: a run that is a day old, a parameter that decoded to nothing, a cache
that grew past what the disk has, a push channel that never connected. All of
that is state the coordinator already holds, so the download button on the
entry page can hand it over in one go.

Every key is redacted. The three KNMI keys are the most sensitive thing this
integration holds, and a diagnostics file is made to be pasted into a public
issue.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from .const import (
    CONF_API_KEY,
    CONF_DATASET,
    CONF_FORECAST_HORIZON_HOURS,
    CONF_NOTIFICATION_API_KEY,
    CONF_OBSERVATIONS_API_KEY,
    CONF_RETAIN_RUNS,
    CONF_SOURCE,
    CONF_UPDATE_INTERVAL_MINUTES,
    DEFAULT_FORECAST_HORIZON_HOURS,
    DEFAULT_RETAIN_RUNS,
    DEFAULT_UPDATE_INTERVAL_MINUTES,
)
from .coordinator import GribOverlayConfigEntry, enabled_parameter_keys

TO_REDACT = {CONF_API_KEY, CONF_NOTIFICATION_API_KEY, CONF_OBSERVATIONS_API_KEY}


def _disk_usage(storage_dir: Path) -> dict[str, Any]:
    """Blocking: how much this entry's cache holds, per run directory."""
    if not storage_dir.is_dir():
        return {"exists": False}
    runs = {}
    total = 0
    for run_dir in sorted(
        (p for p in storage_dir.iterdir() if p.is_dir()), reverse=True
    ):
        size = sum(f.stat().st_size for f in run_dir.rglob("*") if f.is_file())
        total += size
        runs[run_dir.name] = {
            "bytes": size,
            "files": sum(1 for _ in run_dir.rglob("*")),
        }
    return {"exists": True, "total_bytes": total, "runs": runs}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: GribOverlayConfigEntry
) -> dict[str, Any]:
    """Return everything worth knowing about one entry, with the keys taken out."""
    coordinator = entry.runtime_data
    options = entry.options

    frames = {
        key: {
            "count": len(flist),
            "first_valid_time": flist[0].valid_time.isoformat() if flist else None,
            "last_valid_time": flist[-1].valid_time.isoformat() if flist else None,
            "has_wind_grid": bool(flist and flist[0].wind_path),
            "has_field_grid": bool(flist and flist[0].field_path),
        }
        for key, flist in sorted(coordinator.frames.items())
    }
    disk = await hass.async_add_executor_job(_disk_usage, coordinator.storage_dir)

    return {
        "entry": {
            "source": entry.data.get(CONF_SOURCE),
            "dataset": entry.data.get(CONF_DATASET),
            "title": entry.title,
            "version": entry.version,
            # Redacted copies, so a changed-but-wrong key still shows as set.
            "data": async_redact_data(dict(entry.data), TO_REDACT),
            "options": async_redact_data(dict(options), TO_REDACT),
        },
        "settings": {
            "enabled_parameters": enabled_parameter_keys(entry),
            "forecast_horizon_hours": options.get(
                CONF_FORECAST_HORIZON_HOURS, DEFAULT_FORECAST_HORIZON_HOURS
            ),
            "retain_runs": options.get(CONF_RETAIN_RUNS, DEFAULT_RETAIN_RUNS),
            "update_interval_minutes": options.get(
                CONF_UPDATE_INTERVAL_MINUTES, DEFAULT_UPDATE_INTERVAL_MINUTES
            ),
        },
        "state": {
            "source_name": coordinator.source.name,
            "supports_push": coordinator.source.supports_push_notifications,
            "current_run": coordinator.current_run,
            "last_update_success": coordinator.last_update_success,
            "last_exception": str(coordinator.last_exception)
            if coordinator.last_exception
            else None,
            # A parameter with no frames is the failure mode worth spotting:
            # the card for it never fills and nothing else says why.
            "parameters_without_frames": [
                key
                for key in enabled_parameter_keys(entry)
                if not coordinator.frames.get(key)
            ],
            "frames": frames,
        },
        "storage": {"path": str(coordinator.storage_dir), **disk},
    }
