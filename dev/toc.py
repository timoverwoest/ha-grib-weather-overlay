"""Rebuild the two tables of contents in README.md from its own headings.

The README carries the same documentation twice, Dutch then English, and each
half opens with its own contents list. Rather than keeping those lists by hand,
run:

    python3 dev/toc.py

tests/test_readme.py fails when the result would differ from what is committed,
so a new chapter cannot quietly go unlisted.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

TOC_TITLES = {"nl": "Inhoud", "en": "Contents"}
# Chapters whose sub-headings are worth listing as well.
DETAILED = {
    "Bronnen en datasets",
    "Alle instellingen — referentie",
    "Sources and datasets",
    "All settings — reference",
}


def slug(text: str) -> str:
    """GitHub's heading anchor: lowercase, drop punctuation, spaces to hyphens."""
    kept = re.sub(r"[^\w\- ]", "", text.strip().lower(), flags=re.UNICODE)
    return kept.replace(" ", "-")


def headings(lines: list[str], depth: int = 3) -> list[tuple[int, int, str]]:
    """(line index, level, text) for every heading outside a fenced code block.

    ``depth`` bounds the levels returned: the contents list only wants chapters
    and their sections, while anchor checking wants every heading there is.
    """
    found: list[tuple[int, int, str]] = []
    fenced = False
    for i, line in enumerate(lines):
        if line.startswith("```"):
            fenced = not fenced
        elif not fenced and (m := re.match(rf"^(#{{1,{depth}}}) (.+?)\s*$", line)):
            found.append((i, len(m.group(1)), m.group(2)))
    return found


def rebuild(text: str) -> str:
    lines = text.split("\n")
    found = headings(lines)

    # Anchors are unique document-wide: a repeated heading gets -1, -2, ...
    seen: dict[str, int] = {}
    anchors: dict[int, str] = {}
    for i, _, heading in found:
        base = slug(heading)
        n = seen.get(base, 0)
        seen[base] = n + 1
        anchors[i] = base if n == 0 else f"{base}-{n}"

    # The English half starts at the second level-1 heading.
    tops = [i for i, level, _ in found if level == 1]
    halves = [(0, tops[1]), (tops[1], len(lines))] if len(tops) > 1 else [(0, len(lines))]

    edits = []
    for lang, (start, end) in zip(TOC_TITLES, halves):
        entries: list[str] = []
        detail = False
        for i, level, heading in found:
            if not start <= i < end or level == 1 or heading in TOC_TITLES.values():
                continue
            if level == 2:
                detail = heading in DETAILED
                entries.append(f"- [{heading}](#{anchors[i]})")
            elif detail:
                entries.append(f"  - [{heading}](#{anchors[i]})")
        block = [f"## {TOC_TITLES[lang]}", "", *entries, ""]
        at = next(i for i, level, _ in found if start <= i < end and level == 2)
        stop = at
        if lines[at].strip() == f"## {TOC_TITLES[lang]}":  # replace the one already there
            stop = next(i for i, level, _ in found if i > at and level == 2)
        edits.append((at, stop, block))

    # Apply from the bottom up, so the earlier line numbers stay valid.
    for at, stop, block in reversed(edits):
        lines[at:stop] = block
    return "\n".join(lines)


if __name__ == "__main__":
    readme = Path(sys.argv[1] if len(sys.argv) > 1 else "README.md")
    readme.write_text(rebuild(readme.read_text()))
    print("ok")


def anchors(text: str) -> set[str]:
    """Every anchor the rendered README offers, deduplicated the way GitHub does."""
    seen: dict[str, int] = {}
    out = set()
    for _, _, heading in headings(text.split("\n"), depth=6):
        base = slug(heading)
        n = seen.get(base, 0)
        seen[base] = n + 1
        out.add(base if n == 0 else f"{base}-{n}")
    return out
