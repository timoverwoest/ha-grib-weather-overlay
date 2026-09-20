"""The isobar layer: where its pressure comes from, and why it can be greyed out.

The isobars are drawn from the dataset's own pressure parameter, for the valid
time on screen -- a separate frame from the one being shown, which has to be
paired up. And when a dataset has no pressure in this card at all, the greyed-out
checkbox has to say what to switch on instead of leaving it to guesswork.
"""

from __future__ import annotations

from pathlib import Path

JS = Path("custom_components/grib_overlay/www/grib-overlay-card.js").read_text(encoding="utf-8")
ISOBAR = JS.split("async _updateIsobarOverlay(frame) {", 1)[1].split("\n  }\n", 1)[0]


def test_the_pressure_frame_is_paired_by_nearest_valid_time() -> None:
    # Equality on the timestamp string would drop the layer as soon as a source
    # publishes pressure on its own step.
    assert "pf = nearestFrame(pframes, frame.valid_time, ISOBAR_MAX_OFFSET_MS);" in ISOBAR
    assert "f.valid_time === frame.valid_time" not in ISOBAR
    assert "const ISOBAR_MAX_OFFSET_MS = 90 * 60 * 1000;" in JS
    body = JS.split("function nearestFrame(frames, isoTime, maxOffsetMs) {", 1)[1].split("\n}\n", 1)[0]
    assert "return best && bestGap <= maxOffsetMs ? best : null;" in body


def test_a_dataset_without_pressure_says_why_the_layer_is_off() -> None:
    assert JS.count("isobarsNoPressure:") == 2  # Dutch and English
    avail = JS.split("const hasPressure = !!this._pressureParam();", 1)[1].split("\n  }\n", 1)[0]
    assert 'const tip = hasPressure ? "isobarsTitle" : "isobarsNoPressure";' in avail
    # The tooltip follows a language switch like the rest of the chrome.
    assert 'setAttribute("data-i18n-title", tip)' in avail


def test_isobars_switched_on_without_data_say_so() -> None:
    # Silence was the complaint: the layer was on, the map stayed bare and
    # nothing said why (a run still being processed, a parameter just enabled).
    assert JS.count("isobarsNoData:") == 2  # Dutch and English
    assert 'this._setIsobarNote(gribT("isobarsNoData"));' in ISOBAR
    assert 'this._setIsobarNote("");' in ISOBAR  # ... and it goes away again
    assert "no pressure field for" in ISOBAR  # a console line to go on
    note = JS.split("  _setIsobarNote(text) {", 1)[1].split("\n  }\n", 1)[0]
    # It must not paint over a message that matters more.
    assert "if (!this._els.note.textContent || this._isobarNoteShown)" in note
