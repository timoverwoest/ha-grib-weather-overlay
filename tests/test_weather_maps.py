"""KNMI weather charts: which charts are offered, and what the image view may serve."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from custom_components.grib_overlay import weather_maps
from custom_components.grib_overlay.weather_maps import WeatherMaps, select_charts


def _f(name: str, modified: str = "2026-09-16T19:40:00+00:00") -> dict:
    return {"filename": name, "lastModified": modified, "size": 50000}


def test_offers_recent_analyses_then_the_forecasts_after_them() -> None:
    files = [
        _f("AL_202609151200.gif"), _f("AL_202609151800.gif"), _f("AL_202609160000.gif"),
        _f("AL_202609160600.gif"), _f("AL_202609161200.gif"), _f("AL_202609161800.gif"),
        # Forecasts for times already analysed are stale.
        _f("PL_202609161200.gif"), _f("PL_202609160000.gif"),
        _f("PL_202609170000.gif"), _f("PL_202609171200.gif"), _f("PL_202609181200.gif"),
        _f("readme.txt"),
    ]
    charts = select_charts(files)
    assert [c.name for c in charts] == [
        "AL_202609160000.gif", "AL_202609160600.gif", "AL_202609161200.gif", "AL_202609161800.gif",
        "PL_202609170000.gif", "PL_202609171200.gif", "PL_202609181200.gif",
    ]
    assert [c.kind for c in charts][3:5] == ["analysis", "forecast"]
    assert charts[0].as_dict()["valid_time"] == "2026-09-16T00:00:00+00:00"


def test_a_reissued_forecast_keeps_its_newest_version() -> None:
    charts = select_charts([
        _f("PL_202609170000.gif", "2026-09-16T08:00:00+00:00"),
        _f("PL_202609170000.gif", "2026-09-16T20:15:00+00:00"),
    ])
    assert [(c.name, c.issued) for c in charts] == [("PL_202609170000.gif", "2026-09-16T20:15:00+00:00")]


def test_key_comes_from_a_knmi_entry_only(hass) -> None:
    def coord(source: str, key: str):
        return SimpleNamespace(entry=SimpleNamespace(data={"source": source, "api_key": key}))

    hass.data["grib_overlay"] = {"a": coord("dwd", ""), "b": coord("knmi", "k-123")}
    assert weather_maps.knmi_api_key(hass) == "k-123"
    hass.data["grib_overlay"] = {"a": coord("dwd", "")}
    assert weather_maps.knmi_api_key(hass) is None


async def test_without_a_knmi_entry_the_list_explains_why(hass) -> None:
    hass.data["grib_overlay"] = {}
    with pytest.raises(weather_maps.WeatherMapError, match="no KNMI entry"):
        await WeatherMaps(hass).charts()


async def test_only_listed_charts_are_served(hass, tmp_path, monkeypatch) -> None:
    maps = WeatherMaps(hass)
    maps._dir = tmp_path
    (tmp_path / "AL_202609161800.gif").write_bytes(b"GIF89a")
    (tmp_path / "AL_202609161200.gif").write_bytes(b"GIF89a")
    maps._charts = select_charts([_f("AL_202609161800.gif")])
    assert await maps.image("AL_202609161800.gif") == tmp_path / "AL_202609161800.gif"
    # On disk, but not in the current listing: not served.
    assert await maps.image("AL_202609161200.gif") is None
    # Anything that isn't a chart name never reaches the file system.
    for name in ("../secrets.yaml", "AL_202609161800.png", "index.json"):
        assert await maps.image(name) is None
