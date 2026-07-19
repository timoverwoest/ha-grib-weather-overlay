"""Abstract interface every GRIB data source (KNMI, and later others) must implement.

Keeping this interface small and provider-agnostic is what lets
``coordinator.py`` and ``config_flow.py`` work with any registered source
without knowing provider-specific details (auth scheme, file layout, grid
projection, ...).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class GribParameter:
    """A single physical quantity that can be extracted from a dataset's GRIB messages.

    KNMI's HARMONIE files use a local GRIB1 parameter table (centre=knmi,
    table2Version=253) that eccodes has no name definitions for, so messages
    can't be matched by shortName -- ``grib_filter`` therefore keys on the
    raw numeric fields (indicatorOfParameter / indicatorOfTypeOfLevel /
    level), which are always present regardless of table definitions.

    Wind (and gusts) are stored as separate u/v component messages rather
    than a single speed field, hence the "vector" kind: grib_filter_u and
    grib_filter_v are combined into a magnitude by grib_decode.py.
    """

    key: str  # stable id, e.g. "wind_10m"
    name: str  # human readable, e.g. "Wind (10m)"
    unit: str
    kind: str = "scalar"  # "scalar" | "vector"
    grib_filter: dict = field(default_factory=dict)  # used when kind == "scalar"
    grib_filter_u: dict | None = None  # used when kind == "vector"
    grib_filter_v: dict | None = None
    scale: float = 1.0  # raw GRIB value -> display unit: value * scale + offset
    offset: float = 0.0
    colormap: str = "turbo"
    value_range: tuple[float, float] | None = None  # fixed scale, or None to auto-scale per frame


@dataclass(frozen=True)
class GribDatasetInfo:
    """Metadata for one dataset offered by a source."""

    key: str  # unique within the source, e.g. "harmonie_arome_cy43_p1"
    name: str  # human readable
    version: str  # provider-side API version, e.g. "1.0"
    description: str
    grid_type: str  # "regular_latlon" | "rotated_latlon"
    bounds: tuple[float, float, float, float]  # (south, west, north, east) in degrees
    output_frequency_hours: float
    forecast_horizon_hours: float
    parameters: tuple[GribParameter, ...]


@dataclass(frozen=True)
class GribFileInfo:
    """One listed file on the provider (a full forecast run, in KNMI's case a .tar)."""

    filename: str
    size: int
    last_modified: str  # ISO-8601 timestamp string


class GribSourceError(Exception):
    """Generic, retryable source error (network, 5xx, ...)."""


class GribSourceAuthError(GribSourceError):
    """Raised on 401/403 so config_flow can surface 'invalid API key'."""


class GribSource(ABC):
    """Base class for a GRIB provider (KNMI Data Platform, and future sources)."""

    key: str
    name: str

    @abstractmethod
    async def async_list_datasets(self) -> list[GribDatasetInfo]:
        """Return the datasets this source offers (static catalog or live lookup)."""

    @abstractmethod
    async def async_list_files(
        self,
        dataset: GribDatasetInfo,
        *,
        max_keys: int = 20,
        order_by: str = "lastModified",
        sorting: str = "desc",
    ) -> list[GribFileInfo]:
        """List available files (forecast runs) for a dataset, most recent first by default."""

    @abstractmethod
    async def async_download_file(
        self, dataset: GribDatasetInfo, filename: str, destination: Path
    ) -> Path:
        """Download one file to ``destination`` and return the path it was written to."""

    # Optional: sources may push new-file notifications (e.g. KNMI's MQTT
    # Notification Service) so the coordinator doesn't have to wait for its
    # next poll. Best-effort by design -- polling remains the source of
    # truth, so a source that can't/doesn't support this just does nothing.
    supports_push_notifications: bool = False

    async def async_start_notifications(
        self, dataset: GribDatasetInfo, on_new_file: Callable[[str], None]
    ) -> None:
        """Start listening for new-file notifications, if the source supports it.

        ``on_new_file`` is called with the new file's name from the event
        loop thread (implementations must marshal any background-thread
        callbacks accordingly, e.g. via ``loop.call_soon_threadsafe``).
        """
        return

    async def async_stop_notifications(self) -> None:
        """Stop listening for new-file notifications. No-op if never started."""
        return
