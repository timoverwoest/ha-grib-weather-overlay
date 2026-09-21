"""The card's own report of a browser-side failure: wording, repeats, endpoint."""

from __future__ import annotations

import pytest
from homeassistant.components.persistent_notification import _async_get_or_create_notifications
from homeassistant.setup import async_setup_component

from custom_components.grib_overlay import client_errors
from custom_components.grib_overlay.http import VIEWS, GribOverlayClientErrorView

REPORT = {
    "version": "0.38.0",
    "url": "https://home.example/grib_overlay_static/grib-overlay-card.js?v=0.38.0",
    "loads": 2,
    "navigation": "reload",
    "page": "/lovelace-zeilen/kaarten",
    "user_agent": "Mozilla/5.0 (Macintosh) Vivaldi/8.2",
    "service_worker": "https://home.example/service_worker.js",
    "events": [
        {
            "card": "custom:grib-overlay-card",
            "name": "TypeError",
            "message": "Cannot set property hass of #<GribOverlayCard> which has only a getter",
            "stack": "TypeError: no\n    at HuiCard.update (core.js:1:2)\n" + "    at x\n" * 20,
            "elements": [
                {
                    "tag": "grib-overlay-card",
                    "connected": True,
                    "current": False,
                    "extensible": True,
                    "frozen": False,
                    "prototype_hass": "getter without a setter",
                    "own_hass": "none",
                }
            ],
        }
    ],
}


def test_the_report_reads_as_one_paragraph_naming_what_matters() -> None:
    text = client_errors.format_report(REPORT)
    assert "custom:grib-overlay-card" in text
    assert "TypeError: Cannot set property hass" in text
    assert "navigation: reload" in text
    assert "2 copies of the card file loaded" in text
    assert "/lovelace-zeilen/kaarten" in text
    assert "getter without a setter" in text
    assert "built from another copy of the card file" in text
    assert "Vivaldi/8.2" in text
    # The stack is Home Assistant's own after a few frames; it is not the log's job.
    assert text.count("at x") <= 6


def test_an_element_that_looks_normal_says_so() -> None:
    state = {"tag": "grib-overlay-card", "connected": True, "current": True,
             "extensible": True, "frozen": False, "prototype_hass": "setter", "own_hass": "none"}
    assert "nothing out of the ordinary" in client_errors._describe_element(state)


def test_a_frozen_element_is_called_out() -> None:
    state = {"tag": "grib-overlay-card", "connected": True, "current": True,
             "extensible": False, "frozen": True, "prototype_hass": "setter", "own_hass": "read-only value"}
    described = client_errors._describe_element(state)
    assert "frozen" in described and "read-only value" in described


def test_a_wall_of_text_is_cut_down() -> None:
    text = client_errors.format_report({"events": [{"card": "x" * 500, "message": "y" * 5000}]})
    assert len(text) < 1000


def test_the_same_failure_is_logged_once_until_it_goes_quiet() -> None:
    seen: dict = {}
    assert client_errors.is_new(seen, REPORT, now=0.0)
    assert not client_errors.is_new(seen, REPORT, now=10.0)
    assert not client_errors.is_new(seen, REPORT, now=299.0)
    assert client_errors.is_new(seen, REPORT, now=1000.0)  # gone quiet, then back


def test_a_different_failure_is_its_own_report() -> None:
    seen: dict = {}
    other = {**REPORT, "events": [{**REPORT["events"][0], "message": "something else"}]}
    assert client_errors.is_new(seen, REPORT, now=0.0)
    assert client_errors.is_new(seen, other, now=1.0)


def test_notification_carries_the_message_and_where_to_read_more() -> None:
    dutch = client_errors.notification(REPORT, "nl")
    assert "Cannot set property hass" in dutch
    assert "Logboek" in dutch
    assert "Logs" in client_errors.notification(REPORT, "en")


async def test_the_endpoint_logs_the_report_and_shows_it_as_a_notification(
    hass, hass_client, caplog
) -> None:
    assert await async_setup_component(hass, "http", {})
    assert await async_setup_component(hass, "persistent_notification", {})
    hass.http.register_view(GribOverlayClientErrorView)
    client = await hass_client()

    resp = await client.post("/api/grib_overlay/client_error", json=REPORT)
    assert resp.status == 200
    assert (await resp.json())["logged"] is True
    assert "Cannot set property hass" in caplog.text

    notifications = _async_get_or_create_notifications(hass)
    assert "grib_overlay_client_error" in notifications, (
        "the failure should be visible without opening the log"
    )
    assert "Cannot set property hass" in notifications["grib_overlay_client_error"]["message"]

    # The same card failing on every state change must not fill the log.
    again = await client.post("/api/grib_overlay/client_error", json=REPORT)
    assert (await again.json())["logged"] is False


@pytest.mark.parametrize("body", [{"events": []}, {"nothing": "here"}, []])
async def test_a_report_without_a_failure_in_it_is_refused(hass, hass_client, body) -> None:
    assert await async_setup_component(hass, "http", {})
    hass.http.register_view(GribOverlayClientErrorView)
    client = await hass_client()
    resp = await client.post("/api/grib_overlay/client_error", json=body)
    assert resp.status == 400


def test_the_endpoint_is_registered_and_needs_a_login() -> None:
    assert GribOverlayClientErrorView in VIEWS
    assert GribOverlayClientErrorView.requires_auth is True


def test_a_map_that_stayed_blank_reads_as_itself() -> None:
    """Not a thrown error: no element state, no stack -- just what the card
    could see of itself, which is the whole point of reporting it."""
    report = {
        "navigation": "navigate",
        "page": "/zeilen/kaart",
        "events": [
            {
                "kind": "blank-map",
                "card": "custom:grib-overlay-card",
                "name": "blank map",
                "message": "the map stayed empty after rebuilding it twice "
                "(container 480x320 px, zoom 7, 49 frames loaded)",
                "stack": "irrelevant\n    at somewhere",
            }
        ],
    }
    text = client_errors.format_report(report)
    assert "the map stayed empty after rebuilding it twice" in text
    assert "container 480x320 px" in text
    assert "at somewhere" not in text
