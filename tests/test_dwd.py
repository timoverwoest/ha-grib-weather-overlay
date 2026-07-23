"""Offline tests for the DWD source's run discovery + directory parsing.

The actual downloads are exercised against the live opendata.dwd.de server
during development; here we only unit-test the filename/run parsing with a fake
HTTP session so it runs without network.
"""

from __future__ import annotations

import pytest

from custom_components.grib_overlay.sources.dwd import DwdSource, KNOWN_DATASETS, _BASE


class _FakeResp:
    def __init__(self, text: str, status: int) -> None:
        self._text, self.status = text, status

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def text(self) -> str:
        return self._text


class _FakeSession:
    def __init__(self, pages: dict[str, str]) -> None:
        self._pages = pages

    def get(self, url: str):
        return _FakeResp(self._pages.get(url, ""), 200 if url in self._pages else 404)


def _listing(run: str, steps: range) -> str:
    return "".join(
        f'<a href="EWAM_SWH_{run}_{s:03d}.grib2.bz2">x</a>' for s in steps
    )


@pytest.mark.asyncio
async def test_lists_latest_run() -> None:
    pages = {
        f"{_BASE}/00/swh/": _listing("2026072300", range(0, 4)),
        f"{_BASE}/12/swh/": _listing("2026072312", range(0, 4)),
    }
    src = DwdSource(_FakeSession(pages))
    files = await src.async_list_files(KNOWN_DATASETS[0])
    assert len(files) == 1
    # 12Z run is newer than the same day's 00Z run.
    assert files[0].filename == "2026072312"
    assert files[0].last_modified.startswith("2026-07-23T12:00")


@pytest.mark.asyncio
async def test_horizon_limits_downloaded_steps(monkeypatch, tmp_path) -> None:
    run = "2026072312"
    pages = {
        f"{_BASE}/12/swh/": _listing(run, range(0, 6)),
        f"{_BASE}/00/swh/": "",
    }
    src = DwdSource(_FakeSession(pages))

    grabbed: list[int] = []

    async def _fake_dl(url, dest, loop):
        grabbed.append(int(dest.stem.rsplit("_", 1)[1]))
        dest.write_bytes(b"x")

    monkeypatch.setattr(src, "_download_bunzip", _fake_dl)
    paths = await src.async_download_run(
        KNOWN_DATASETS[0], run, tmp_path, ["wave_height"], horizon_hours=3
    )
    # steps 0..3 only (horizon 3h), not 4/5.
    assert sorted(grabbed) == [0, 1, 2, 3]
    assert len(paths) == 4
