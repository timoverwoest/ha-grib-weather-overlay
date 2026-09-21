"""What the card reports when Home Assistant turns it into a red block.

Home Assistant hands every card a fresh ``hass`` on each state change. When
that assignment throws, it replaces the card with a "configuration error" block
that carries no text at all, and writes the only explanation to the browser
console: the card type and the error. A console is a place nobody is looking --
and on a phone or a tablet there is no console to look at.

So the card watches for that line itself and posts it to
``/api/grib_overlay/client_error``. This module turns such a report into one
readable paragraph for the Home Assistant log and a short notification, and
remembers what it has seen so a card that fails on every state change does not
fill the log with the same paragraph.
"""

from __future__ import annotations

import time

_MESSAGE_MAX = 300
_STACK_LINES = 6
_STACK_LINE_MAX = 200
_EVENTS_MAX = 5
_ELEMENTS_MAX = 6
_REPEAT_SECONDS = 300.0

TITLE = {
    "nl": "GRIB Weather Overlay: de card gaf een fout in de browser",
    "en": "GRIB Weather Overlay: the card failed in the browser",
}
INTRO = {
    "nl": (
        "Home Assistant heeft deze card vervangen door een lege "
        "\"configuratiefout\". Dit is wat de browser erover zei:"
    ),
    "en": (
        "Home Assistant replaced this card with a blank \"configuration "
        "error\". This is what the browser said about it:"
    ),
}
OUTRO = {
    "nl": (
        "Dezelfde tekst staat in het Home Assistant-logboek "
        "(Instellingen → Systeem → Logboek)."
    ),
    "en": (
        "The same text is in the Home Assistant log "
        "(Settings → System → Logs)."
    ),
}


def _text(value: object, limit: int = _MESSAGE_MAX) -> str:
    """One line of at most ``limit`` characters, whatever the browser sent."""
    if value is None:
        return ""
    out = " ".join(str(value).split())
    return out[: limit - 1] + "…" if len(out) > limit else out


def _stack(value: object) -> list[str]:
    """The first few stack frames, trimmed -- the rest is Home Assistant's own."""
    lines = [_text(line, _STACK_LINE_MAX) for line in str(value or "").splitlines()]
    return [line for line in lines if line][:_STACK_LINES]


def _event_lines(event: dict) -> list[str]:
    card = _text(event.get("card"), 80) or "?"
    name = _text(event.get("name"), 60)
    message = _text(event.get("message")) or "(no message)"
    head = f"{card} — {name + ': ' if name and not message.startswith(name) else ''}{message}"
    lines = [head]
    # A blank map is not a thrown error: there is no element state to read
    # and no stack worth printing, only what the card could see of itself.
    if event.get("kind") == "blank-map":
        return lines
    elements = event.get("elements")
    if isinstance(elements, list):
        for element in elements[:_ELEMENTS_MAX]:
            if isinstance(element, dict):
                lines.append("  element " + _describe_element(element))
    lines.extend("  " + line for line in _stack(event.get("stack")))
    return lines


def _describe_element(element: dict) -> str:
    """One element's state at the moment it failed, in words."""
    tag = _text(element.get("tag"), 60) or "?"
    notes = []
    if element.get("connected") is False:
        notes.append("not in the page")
    if element.get("current") is False:
        notes.append("built from another copy of the card file")
    if element.get("frozen"):
        notes.append("frozen")
    elif element.get("extensible") is False:
        notes.append("not extensible")
    proto = _text(element.get("prototype_hass"), 60)
    own = _text(element.get("own_hass"), 60)
    if proto and proto != "setter":
        notes.append(f"hass on the prototype: {proto}")
    if own and own != "none":
        notes.append(f"hass on the element itself: {own}")
    return f"{tag} ({', '.join(notes) if notes else 'nothing out of the ordinary'})"


def _context_lines(report: dict) -> list[str]:
    loads = report.get("loads")
    copies = ""
    if isinstance(loads, (int, float)) and loads > 1:
        copies = f", {int(loads)} copies of the card file loaded"
    lines = [
        "  card "
        + (_text(report.get("version"), 40) or "?")
        + f", page {_text(report.get('page'), 120) or '?'}"
        + f", navigation: {_text(report.get('navigation'), 40) or '?'}"
        + copies
    ]
    agent = _text(report.get("user_agent"), 200)
    if agent:
        lines.append(f"  browser {agent}")
    worker = _text(report.get("service_worker"), 200)
    if worker:
        lines.append(f"  served through service worker {worker}")
    return lines


def events(report: dict) -> list[dict]:
    """The failures in a report -- at most a handful, and only real ones."""
    raw = report.get("events")
    if not isinstance(raw, list):
        return []
    return [event for event in raw if isinstance(event, dict)][:_EVENTS_MAX]


def format_report(report: dict) -> str:
    """The whole report as one paragraph for the log."""
    lines = ["The card reported a failure in the browser:"]
    for event in events(report):
        lines.extend(_event_lines(event))
    lines.extend(_context_lines(report))
    return "\n".join(lines)


def notification(report: dict, lang: str) -> str:
    """The same, shortened for a notification card."""
    lines = [INTRO.get(lang, INTRO["en"]), ""]
    for event in events(report):
        for line in _event_lines(event):
            lines.append("`" + line.strip() + "`" if line.startswith("  ") else "**" + line + "**")
    lines.extend(["", *(line.strip() for line in _context_lines(report)), "", OUTRO.get(lang, OUTRO["en"])])
    return "\n".join(lines)


def fingerprint(report: dict) -> str:
    """What makes two reports "the same failure" -- the card and the message."""
    return "|".join(
        f"{_text(event.get('card'), 80)}→{_text(event.get('message'), 120)}"
        for event in events(report)
    )


def is_new(seen: dict, report: dict, now: float | None = None) -> bool:
    """True the first time a failure shows up, and again after five minutes.

    A card that throws on every state change would otherwise write the same
    paragraph to the log several times a second.
    """
    moment = time.monotonic() if now is None else now
    key = fingerprint(report)
    for old, when in list(seen.items()):
        if moment - when > _REPEAT_SECONDS:
            del seen[old]
    if key in seen:
        return False
    seen[key] = moment
    return True
