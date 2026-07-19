"""Registry of available GribSource implementations.

Adding a new provider later is: implement GribSource in a new module, import
it here, add it to SOURCE_REGISTRY. config_flow.py and __init__.py never need
to change.
"""

from __future__ import annotations

from .base import GribSource
from .knmi import KnmiSource

SOURCE_REGISTRY: dict[str, type[GribSource]] = {
    KnmiSource.key: KnmiSource,
}


def get_source_class(source_key: str) -> type[GribSource]:
    try:
        return SOURCE_REGISTRY[source_key]
    except KeyError as err:
        raise ValueError(f"Unknown GRIB source '{source_key}'") from err
