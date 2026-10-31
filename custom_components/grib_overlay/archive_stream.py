"""Unpack a run archive while it downloads, keeping only what gets decoded.

A KNMI HARMONIE run is one tar holding every lead time with every parameter of
the model: ~0.9 GB for the Netherlands and ~3.4 GB for Europe, every hour.
Written to disk and then extracted, each run cost twice its size in writes --
some 200 GB a day for those two datasets -- for files read once and deleted.

So the archive is read as a stream instead. tarfile walks it member by member
straight off the download; a member past the forecast horizon is dropped, and
of the rest only the GRIB records of the enabled parameters are written to
scratch, where the decoder picks them up as before. Nothing else of the
archive ever reaches the disk.

The download is async and tarfile is blocking, so the two meet in a ChunkPipe:
the event loop feeds it chunks, an executor thread reads it as a file. Its
queue is bounded, so a reader that falls behind slows the download down rather
than piling the archive up in memory.
"""

from __future__ import annotations

from datetime import timedelta
import io
import logging
from pathlib import Path
import queue
import tarfile
import threading

from . import grib1, grib_decode
from .sources.base import GribParameter

_LOGGER = logging.getLogger(__name__)

# How long a blocked feed or read waits before looking whether the other side
# gave up. Only matters when one side stops early; it is not a polling rate.
_WAKE_SECONDS = 0.5


class ChunkPipe(io.RawIOBase):
    """A file to read from in a thread, filled with chunks from the event loop."""

    _END = object()

    def __init__(self, max_chunks: int = 8) -> None:
        """Hold at most ``max_chunks`` chunks (of a megabyte each) in between."""
        super().__init__()
        self._queue: queue.Queue = queue.Queue(max_chunks)
        self._pending = memoryview(b"")
        self._at_end = False
        # Set by whichever side stops first: the reader when the archive ended
        # or failed, the feeding side when the download did.
        self.stopped = threading.Event()

    def readable(self) -> bool:
        """It is read from, never written to as a file."""
        return True

    def readinto(self, buffer) -> int:
        """Blocking: copy the next bytes of the stream into ``buffer``."""
        while not self._pending:
            if self._at_end:
                return 0
            try:
                item = self._queue.get(timeout=_WAKE_SECONDS)
            except queue.Empty:
                if self.stopped.is_set():
                    raise OSError("the download stopped") from None
                continue
            if item is self._END:
                self._at_end = True
                return 0
            self._pending = memoryview(item)
        size = min(len(buffer), len(self._pending))
        buffer[:size] = self._pending[:size]
        self._pending = self._pending[size:]
        return size

    def try_feed(self, chunk: bytes) -> bool:
        """Hand over one chunk if there is room right now; never blocks."""
        try:
            self._queue.put_nowait(chunk)
        except queue.Full:
            return False
        return True

    def feed(self, chunk: bytes) -> bool:
        """Blocking: hand over one chunk. False once the reader has stopped."""
        return self._put(chunk)

    def end(self) -> None:
        """Blocking: tell the reader the stream is complete."""
        self._put(self._END)

    def _put(self, item) -> bool:
        while not self.stopped.is_set():
            try:
                self._queue.put(item, timeout=_WAKE_SECONDS)
            except queue.Full:
                continue
            return True
        return False


def filters_for(parameters: list[GribParameter]) -> list[dict]:
    """Every GRIB filter the enabled parameters decode with (u and v for wind)."""
    return [
        filt
        for parameter in parameters
        for filt in (
            parameter.grib_filter,
            parameter.grib_filter_u,
            parameter.grib_filter_v,
        )
        if filt
    ]


def unpack(
    fileobj,
    raw_dir: Path,
    filters: list[dict] | None = None,
    horizon_hours: float | None = None,
) -> list[Path]:
    """Blocking: walk a tar stream and write what is worth decoding to raw_dir.

    With ``filters`` only the matching GRIB1 records of a member are kept, and
    with ``horizon_hours`` a member beyond it is skipped altogether. Leave both
    out to extract every member whole.
    """
    raw_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    try:
        with tarfile.open(fileobj=fileobj, mode="r|") as tar:
            for member in tar:
                if not member.isfile():
                    continue
                with tar.extractfile(member) as src:
                    kept = _worth_decoding(
                        src.read(), member.name, filters, horizon_hours
                    )
                if not kept:
                    continue
                path = raw_dir / Path(member.name).name
                path.write_bytes(kept)
                paths.append(path)
    finally:
        if isinstance(fileobj, ChunkPipe):
            fileobj.stopped.set()
    return paths


def _worth_decoding(
    buf: bytes, name: str, filters: list[dict] | None, horizon_hours: float | None
) -> bytes:
    """The part of one member the decoder will use; empty when none of it is."""
    if horizon_hours is not None:
        try:
            valid_time, run_time = grib_decode.times_of(buf, name)
        except (grib_decode.GribDecodeError, grib1.Grib1Error) as err:
            _LOGGER.debug("Skipping unreadable member %s: %s", name, err)
            return b""
        if valid_time - run_time > timedelta(hours=horizon_hours):
            return b""
    start = buf.find(b"GRIB")
    if filters is None or start < 0 or buf[start + 7 : start + 8] != b"\x01":
        # Only GRIB1 is cut down by its headers; anything else stays whole.
        return buf
    return grib1.select_records(buf, filters)
