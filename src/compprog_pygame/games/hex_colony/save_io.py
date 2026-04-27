"""Save / load for Hex Colony.

Snapshots are pickled :class:`World` objects written under
``~/.compprog_pygame/saves/<slug>.sav``.  The format is intentionally
*not* versioned — pickle only round-trips reliably between matching
source revisions, so saves are best treated as session-local.

Public API
----------
* :func:`save_dir` — where save files live (created on first call).
* :func:`save_world(world, name)` — write a snapshot, returns the file path.
* :func:`load_world(path)` — read a snapshot back into a :class:`World`.
* :func:`list_saves()` — newest-first list of ``SaveSlot`` entries.
* :func:`delete_save(path)` — remove a save (unused by UI today).
"""

from __future__ import annotations

import os
import pickle
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from compprog_pygame.games.hex_colony.world import World


_SLUG_RE = re.compile(r"[^A-Za-z0-9_\-]+")


def save_dir() -> Path:
    """Return the directory used to store save files (created on demand)."""
    base = Path.home() / ".compprog_pygame" / "saves"
    base.mkdir(parents=True, exist_ok=True)
    return base


def _slugify(s: str) -> str:
    s = _SLUG_RE.sub("_", s.strip())
    return s[:32] or "save"


@dataclass(slots=True)
class SaveSlot:
    """Metadata for one save file (used by the Load list UI)."""
    path: Path
    seed: str
    timestamp: float           # unix seconds
    pretty_time: str
    population: int
    tier: int
    elapsed_minutes: float


def _slot_from_path(path: Path) -> SaveSlot | None:
    """Best-effort metadata extraction.

    We keep the metadata at the *start* of the pickle stream so the
    list view doesn't have to deserialise the entire (potentially
    large) :class:`World` object just to render a row.
    """
    try:
        with path.open("rb") as f:
            meta = pickle.load(f)
    except Exception:
        return None
    if not isinstance(meta, dict) or meta.get("__hex_colony_save__") != 1:
        return None
    ts = float(meta.get("timestamp", path.stat().st_mtime))
    return SaveSlot(
        path=path,
        seed=str(meta.get("seed", "?")),
        timestamp=ts,
        pretty_time=time.strftime("%Y-%m-%d %H:%M", time.localtime(ts)),
        population=int(meta.get("population", 0)),
        tier=int(meta.get("tier", 0)),
        elapsed_minutes=float(meta.get("elapsed_minutes", 0.0)),
    )


def save_world(world: "World", name: str | None = None) -> Path:
    """Write *world* to a new save file and return its path.

    The save filename is built from ``world.seed`` plus a timestamp
    suffix so concurrent saves never collide.  Caller may pass a
    custom ``name`` to override the filename slug.
    """
    slug = _slugify(name or world.seed or "save")
    ts = time.time()
    fname = f"{slug}_{int(ts)}.sav"
    path = save_dir() / fname

    meta = {
        "__hex_colony_save__": 1,
        "seed": getattr(world, "seed", ""),
        "timestamp": ts,
        "population": int(getattr(world, "player_population_count", 0)),
        "tier": int(getattr(world.tier_tracker, "current_tier", 0)),
        "elapsed_minutes": float(getattr(world, "time_elapsed", 0.0)) / 60.0,
    }
    # Two-payload format: metadata header, then the pickled world.
    # Lets the load-list UI peek at metadata without paying the cost
    # of unpickling the entire world graph.
    tmp = path.with_suffix(".tmp")
    with tmp.open("wb") as f:
        pickle.dump(meta, f, protocol=pickle.HIGHEST_PROTOCOL)
        pickle.dump(world, f, protocol=pickle.HIGHEST_PROTOCOL)
    os.replace(tmp, path)
    return path


def load_world(path: Path) -> "World":
    """Load and return the :class:`World` snapshot stored at *path*.

    Raises ``FileNotFoundError`` / ``pickle.UnpicklingError`` on
    failure; the caller is expected to surface those to the user.
    """
    with path.open("rb") as f:
        _meta = pickle.load(f)
        world = pickle.load(f)
    return world


def list_saves() -> list[SaveSlot]:
    """Return all save slots, newest first."""
    base = save_dir()
    slots: list[SaveSlot] = []
    for p in base.glob("*.sav"):
        slot = _slot_from_path(p)
        if slot is not None:
            slots.append(slot)
    slots.sort(key=lambda s: s.timestamp, reverse=True)
    return slots


def delete_save(path: Path) -> bool:
    try:
        Path(path).unlink()
        return True
    except OSError:
        return False
