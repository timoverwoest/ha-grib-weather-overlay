"""Unit tests for the pure observation parsers + the UTM->WGS84 conversion.

The live KNMI/RWS HTTP calls need a real key/network and are verified on a real
HA instance; here we lock down the response parsing and the geometry, which is
what breaks silently if a provider tweaks its shape.
"""

from __future__ import annotations

from custom_components.grib_overlay.observations import (
    _features_within,
    _iso_seconds,
    _rws_allowed_locations,
    nearest_knmi_location,
    nearest_rws_station,
    parse_knmi_coveragejson,
    parse_rws_waarnemingen,
    provider_for,
    utm31n_to_wgs84,
)


def test_provider_routing() -> None:
    assert provider_for("wind_10m") == "knmi"
    assert provider_for("temperature_2m") == "knmi"
    assert provider_for("wave_height") == "rws"
    assert provider_for("current") == "rws"
    assert provider_for("nonexistent") is None


def test_parse_knmi_coveragejson_zips_value_and_direction() -> None:
    data = {
        "domain": {
            "axes": {
                "t": {"values": ["2026-08-23T10:00:00Z", "2026-08-23T10:10:00Z"]},
                "x": {"values": [4.79]},
                "y": {"values": [52.318]},
            }
        },
        "ranges": {
            "ff": {"values": [5.2, None]},  # second instant missing -> dropped
            "dd": {"values": [210, 220]},
        },
    }
    series = parse_knmi_coveragejson(data, "ff", "dd", scale=1.0)
    assert len(series) == 1
    assert series[0]["valid_time"] == "2026-08-23T10:00:00Z"
    assert series[0]["value"] == 5.2
    assert series[0]["direction"] == 210


def test_parse_knmi_coveragejson_applies_scale() -> None:
    data = {
        "domain": {"axes": {"t": {"values": ["2026-08-23T10:00:00Z"]}}},
        "ranges": {"zm": {"values": [8000]}},  # metres
    }
    series = parse_knmi_coveragejson(data, "zm", None, scale=0.001)  # -> km
    assert series == [{"valid_time": "2026-08-23T10:00:00Z", "value": 8.0}]


def test_parse_knmi_coveragejson_handles_missing_shape() -> None:
    assert parse_knmi_coveragejson({}, "ff", None) == []
    assert parse_knmi_coveragejson({"ranges": {}}, "ff", None) == []


def test_parse_knmi_coveragecollection() -> None:
    # EDR /locations returns a CoverageCollection; descend into coverages[0].
    data = {
        "type": "CoverageCollection",
        "coverages": [
            {
                "domain": {"axes": {"t": {"values": ["2026-08-23T10:00:00Z"]}}},
                "ranges": {"ff": {"values": [7.1]}},
            }
        ],
    }
    assert parse_knmi_coveragejson(data, "ff", None) == [
        {"valid_time": "2026-08-23T10:00:00Z", "value": 7.1}
    ]


def test_nearest_knmi_location_picks_closest_feature() -> None:
    locs = {
        "type": "FeatureCollection",
        "features": [
            {"id": "0-20000-0-06260", "properties": {"name": "De Bilt"}, "geometry": {"type": "Point", "coordinates": [5.18, 52.10]}},
            {"id": "0-20000-0-06269", "properties": {"name": "Lelystad"}, "geometry": {"type": "Point", "coordinates": [5.52, 52.458]}},
        ],
    }
    st = nearest_knmi_location(locs, 52.458, 5.52)  # Lelystad
    assert st is not None
    assert st["id"] == "0-20000-0-06269"
    assert st["name"] == "Lelystad"


def test_features_within_filters_by_radius_and_sorts() -> None:
    geo = {
        "features": [
            {"id": "A", "properties": {"name": "Near"}, "geometry": {"type": "Point", "coordinates": [5.18, 52.10]}},
            {"id": "B", "properties": {"name": "Mid"}, "geometry": {"type": "Point", "coordinates": [5.52, 52.458]}},
            {"id": "C", "properties": {"name": "Far"}, "geometry": {"type": "Point", "coordinates": [6.60, 53.20]}},
        ]
    }
    out = _features_within(geo, 52.10, 5.18, 60.0, "knmi")
    names = [s["name"] for s in out]
    assert names[0] == "Near"  # nearest first
    assert "Far" not in names  # beyond 60 km, dropped
    assert all(s["provider"] == "knmi" for s in out)
    assert all("dist_km" in s for s in out)


def test_rws_allowed_locations_maps_grootheid_to_locations() -> None:
    cat = {
        "AquoMetadataLijst": [
            {"AquoMetadata_MessageID": 10, "Grootheid": {"Code": "Hm0"}},
            {"AquoMetadata_MessageID": 11, "Grootheid": {"Code": "WATHTE"}},
        ],
        "AquoMetadataLocatieLijst": [
            {"Locatie_MessageID": 1, "AquoMetaData_MessageID": 11},
            {"Locatie_MessageID": 2, "AquoMetaData_MessageID": 10},
        ],
    }
    allowed = _rws_allowed_locations(cat, "Hm0")
    assert allowed == {2}
    # No coupling info -> None (can't filter)
    assert _rws_allowed_locations({}, "Hm0") is None


def test_iso_seconds_trims_millis_and_offset() -> None:
    assert _iso_seconds("2026-08-23T12:00:00.000Z") == "2026-08-23T12:00:00Z"
    assert _iso_seconds("2026-08-23T12:00:00+00:00") == "2026-08-23T12:00:00Z"
    assert _iso_seconds("2026-08-23T12:00:00Z") == "2026-08-23T12:00:00Z"


def test_parse_rws_waarnemingen_filters_missing_sentinel() -> None:
    data = {
        "Succesvol": True,
        "WaarnemingenLijst": [
            {
                "MetingenLijst": [
                    {
                        "Tijdstip": "2026-08-23T10:00:00.000+00:00",
                        "Meetwaarde": {"Waarde_Numeriek": 1.23},
                    },
                    {
                        "Tijdstip": "2026-08-23T10:10:00.000+00:00",
                        "Meetwaarde": {"Waarde_Numeriek": 999999999.0},  # missing
                    },
                ]
            }
        ],
    }
    series = parse_rws_waarnemingen(data)
    assert series == [{"valid_time": "2026-08-23T10:00:00.000+00:00", "value": 1.23}]


def test_parse_rws_waarnemingen_unsuccessful() -> None:
    assert parse_rws_waarnemingen({"Succesvol": False}) == []
    assert parse_rws_waarnemingen({}) == []


def test_utm31n_central_meridian_is_3E() -> None:
    lat, lon = utm31n_to_wgs84(500000.0, 5764000.0)
    assert abs(lon - 3.0) < 1e-6  # false easting 500000 sits on 3°E
    assert 51.0 < lat < 53.0  # plausible for the southern North Sea


def test_utm31n_offset_is_east_and_plausible() -> None:
    # ~Europlatform (52.0 N, 3.28 E): a small easting offset east of 3°E.
    lat, lon = utm31n_to_wgs84(518900.0, 5763800.0)
    assert 3.1 < lon < 3.5
    assert 51.8 < lat < 52.2


def test_nearest_rws_station_picks_closest_offering_the_grootheid() -> None:
    # Two stations; only the far one offers Hm0 -> it must be chosen despite distance.
    cat = {
        "LocatieLijst": [
            {"Locatie_MessageID": 1, "Code": "NEAR", "Naam": "Near", "X": 500000, "Y": 5764000},
            {"Locatie_MessageID": 2, "Code": "FAR", "Naam": "Far", "X": 600000, "Y": 5900000},
        ],
        "AquoMetadataLijst": [
            {"AquoMetadata_MessageID": 10, "Grootheid": {"Code": "Hm0"}},
            {"AquoMetadata_MessageID": 11, "Grootheid": {"Code": "WATHTE"}},
        ],
        "AquoMetadataLocatieLijst": [
            {"Locatie_MessageID": 1, "AquoMetaData_MessageID": 11},
            {"Locatie_MessageID": 2, "AquoMetaData_MessageID": 10},
        ],
    }
    station = nearest_rws_station(cat, "Hm0", 52.0, 3.0)
    assert station is not None
    assert station["Code"] == "FAR"
    assert "_lat" in station and "_lon" in station
