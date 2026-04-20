"""Lightweight frame-time monitor for Hex Colony.

Designed to run at all times during a game session with negligible
overhead.  Each frame the main loop wraps named "sections" with the
``section()`` context manager; at frame end the monitor compares the
total frame duration against a spike threshold and, if exceeded,
hands off a snapshot record to a background daemon thread that
appends a JSON line to the perf log.

Hot-path properties:

* No allocations in the steady state — section timings are kept in
  a fixed-size ``dict`` reused across frames.
* ``time.perf_counter`` only (monotonic, sub-microsecond on Windows).
* The writer thread does all I/O so the main loop never blocks on
  disk.
* If the monitor is disabled, ``section()`` returns a shared no-op
  context manager and ``frame_end()`` is a single comparison + early
  return.

The log file is JSON Lines (one record per spike) so it can be
post-processed by ``jq`` / pandas / a small script.  Format:

    {"t": 12.345, "frame_ms": 78.2, "fps_target": 60,
     "sections": {"sim": 71.4, "render_world": 5.1, ...},
     "worst": "sim"}

Where ``t`` is real-time seconds since the monitor started.
"""

from __future__ import annotations

import json
import os
import queue
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


# ── Configuration ─────────────────────────────────────────────────
# A frame is flagged as a spike if it took longer than
# ``SPIKE_FRAME_MS`` *or* more than ``SPIKE_FACTOR`` × the target
# frame budget (1000 / fps).  Both checks fire so we catch absolute
# stalls (>50 ms) and relative jitter (a 30 ms frame at 144 fps).
SPIKE_FRAME_MS: float = 33.0
SPIKE_FACTOR: float = 1.75

# Maximum queued spike records before we start dropping (so a long
# stall storm cannot pile up unbounded memory).
_QUEUE_MAX: int = 4096

# Disable via env var ``HEX_COLONY_PERF=0``.
_ENABLED_DEFAULT: bool = os.environ.get("HEX_COLONY_PERF", "1") != "0"


def default_log_path() -> Path:
    """Return the default perf-log location.

    Uses the ``HEX_COLONY_PERF_LOG`` env var if set; otherwise drops
    the log next to the working directory so it's easy to find when
    running from source.
    """
    env = os.environ.get("HEX_COLONY_PERF_LOG")
    if env:
        return Path(env)
    return Path.cwd() / "hex_colony_perf.jsonl"


class _NoopSection:
    """Shared no-allocation context manager used when disabled."""

    __slots__ = ()

    def __enter__(self) -> None:
        return None

    def __exit__(self, *_exc: object) -> None:
        return None


_NOOP_SECTION = _NoopSection()


class PerfMonitor:
    """Per-frame instrumentation with background-thread log writer."""

    def __init__(
        self,
        fps_target: int = 60,
        log_path: Path | None = None,
        enabled: bool = _ENABLED_DEFAULT,
    ) -> None:
        self.enabled: bool = enabled
        self.fps_target: int = max(1, fps_target)
        self.log_path: Path = log_path or default_log_path()

        # Per-frame state — reused, never reallocated in the hot path.
        self._sections: dict[str, float] = {}
        self._frame_start: float = 0.0
        self._t0: float = time.perf_counter()
        self._spike_count: int = 0
        self._frame_count: int = 0

        # Stack used so nested sections don't clobber each other.
        # Module-level constant + small list — no per-call allocation
        # beyond the append/pop pair.
        self._stack: list[tuple[str, float]] = []

        # Writer thread + queue.
        self._queue: queue.Queue[dict | None] = queue.Queue(
            maxsize=_QUEUE_MAX,
        )
        self._writer: threading.Thread | None = None
        self._stopped = threading.Event()

    # ── Lifecycle ────────────────────────────────────────────────

    def start(self) -> None:
        if not self.enabled or self._writer is not None:
            return
        self._stopped.clear()
        self._writer = threading.Thread(
            target=self._writer_loop,
            name="HexColonyPerfMonitor",
            daemon=True,
        )
        self._writer.start()

    def stop(self) -> None:
        if self._writer is None:
            return
        self._stopped.set()
        # Sentinel so the writer wakes up and exits promptly.
        try:
            self._queue.put_nowait(None)
        except queue.Full:
            pass
        self._writer.join(timeout=2.0)
        self._writer = None

    # ── Hot-path API ─────────────────────────────────────────────

    def frame_begin(self) -> None:
        if not self.enabled:
            return
        self._sections.clear()
        self._frame_start = time.perf_counter()

    @contextmanager
    def section(self, name: str) -> Iterator[None]:
        """Time the wrapped block and accumulate it under ``name``."""
        if not self.enabled:
            yield
            return
        start = time.perf_counter()
        try:
            yield
        finally:
            dur = time.perf_counter() - start
            # ``+=`` so repeated calls in one frame accumulate.
            self._sections[name] = self._sections.get(name, 0.0) + dur

    def frame_end(self) -> None:
        if not self.enabled:
            return
        frame_dur = time.perf_counter() - self._frame_start
        self._frame_count += 1
        frame_ms = frame_dur * 1000.0
        budget_ms = 1000.0 / self.fps_target
        if frame_ms < SPIKE_FRAME_MS and frame_ms < budget_ms * SPIKE_FACTOR:
            return
        # Snapshot is necessary because we reuse ``_sections`` next
        # frame.  This only happens on spikes (rare), so allocation is
        # acceptable here.
        sections_ms = {k: v * 1000.0 for k, v in self._sections.items()}
        worst = max(sections_ms, key=sections_ms.get) if sections_ms else ""
        record = {
            "t": round(time.perf_counter() - self._t0, 3),
            "frame_ms": round(frame_ms, 2),
            "fps_target": self.fps_target,
            "budget_ms": round(budget_ms, 2),
            "sections": {k: round(v, 2) for k, v in sections_ms.items()},
            "worst": worst,
            "frame_index": self._frame_count,
        }
        self._spike_count += 1
        try:
            self._queue.put_nowait(record)
        except queue.Full:
            # Drop on the floor rather than block the game loop.
            pass

    # ── Stats helpers (cheap; useful for an in-game overlay later) ──

    @property
    def spike_count(self) -> int:
        return self._spike_count

    @property
    def frame_count(self) -> int:
        return self._frame_count

    # ── Background writer ────────────────────────────────────────

    def _writer_loop(self) -> None:
        try:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
        except OSError:
            # Logging is best-effort; if the path is unwritable we
            # still want the queue to drain so the main loop doesn't
            # block on a full queue.
            pass
        try:
            f = open(self.log_path, "a", encoding="utf-8", buffering=1)
        except OSError:
            # Drain silently.
            while not self._stopped.is_set():
                try:
                    item = self._queue.get(timeout=0.5)
                except queue.Empty:
                    continue
                if item is None:
                    break
            return
        try:
            # Session header so logs from separate runs are easy to
            # tell apart when grepping the file.
            try:
                f.write(json.dumps({
                    "session_start": time.time(),
                    "fps_target": self.fps_target,
                    "spike_frame_ms": SPIKE_FRAME_MS,
                    "spike_factor": SPIKE_FACTOR,
                }) + "\n")
            except OSError:
                pass
            while True:
                try:
                    item = self._queue.get(timeout=0.5)
                except queue.Empty:
                    if self._stopped.is_set():
                        break
                    continue
                if item is None:
                    break
                try:
                    f.write(json.dumps(item) + "\n")
                except OSError:
                    pass
        finally:
            try:
                f.close()
            except OSError:
                pass
