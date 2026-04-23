"""Background logistics diagnostics for Hex Colony.

Mirror of :mod:`perf_monitor` but for logistics: every N simulation
seconds we snapshot supply, demand, hauler tasks and starved
buildings, then hand the record off to a daemon thread that appends
a JSON line to ``hex_colony_logistics.jsonl``.

The snapshot is intentionally a "cold" pass — it never mutates world
state and never holds anything more than a list of weakref-free
snapshots.  All allocations happen inside :meth:`sample`, never in
the writer thread, so the writer never blocks the sim path.

JSONL format
------------

Each non-header line is a sample record::

    {
        "t_real": 12.345,            # seconds since monitor start (real)
        "t_sim": 36.821,             # seconds of in-game time elapsed
        "frame_index": 730,
        "networks": [
            {
                "id": 4,
                "faction": "SURVIVOR",
                "buildings": 14,
                "haulers": {"idle": 1, "pickup": 2, "deliver": 1},
                "supply": {"WOOD": 23.0, "STONE": 8.5},
                "demand": {"PLANKS": 4.0, "FOOD": 12.0},
                "unmet":  {"PLANKS": 4.0},      # demand with no supplier
                "starved": [
                    {"type": "WORKSHOP", "coord": [3, -2],
                     "missing": {"PLANKS": 4.0}, "starved_for_s": 18.4}
                ],
                "active_jobs": [
                    {"src_type": "WOODCUTTER", "src": [4, -1],
                     "dst_type": "WORKSHOP",   "dst": [3, -2],
                     "res": "WOOD", "qty": 8.0, "task": "PICKUP"}
                ]
            },
            ...
        ]
    }

Toggle via ``HEX_COLONY_LOGISTICS=0`` to disable; default is enabled.
Default sample interval is 2.0 simulation seconds and can be
overridden via ``HEX_COLONY_LOGISTICS_INTERVAL`` (float).
"""

from __future__ import annotations

import json
import os
import queue
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from compprog_pygame.games.hex_colony.world import World


_QUEUE_MAX: int = 2048

_ENABLED_DEFAULT: bool = os.environ.get("HEX_COLONY_LOGISTICS", "1") != "0"

# How often to snapshot, in *simulation* seconds (so 2.0 sim s @ 3x
# speed means a record every ~0.7 real seconds).  Frequent enough to
# diagnose intermittent starvation, sparse enough to keep the log
# compact across long sessions.
_DEFAULT_INTERVAL_S: float = float(
    os.environ.get("HEX_COLONY_LOGISTICS_INTERVAL", "2.0"),
)

# A consumer is flagged "starved" once it has had unmet demand for at
# least this many simulation seconds without any in-flight delivery.
_STARVED_THRESHOLD_S: float = 5.0


def default_log_path() -> Path:
    env = os.environ.get("HEX_COLONY_LOGISTICS_LOG")
    if env:
        return Path(env)
    return Path.cwd() / "hex_colony_logistics.jsonl"


class LogisticsMonitor:
    """Per-network supply/demand/hauler diagnostics."""

    def __init__(
        self,
        log_path: Path | None = None,
        enabled: bool = _ENABLED_DEFAULT,
        interval_s: float = _DEFAULT_INTERVAL_S,
    ) -> None:
        self.enabled: bool = enabled
        self.log_path: Path = log_path or default_log_path()
        self.interval_s: float = max(0.25, interval_s)

        self._t0_real: float = time.perf_counter()
        self._next_sample_sim_t: float = 0.0
        self._frame_index: int = 0
        self._sample_count: int = 0

        # First-seen sim-time per (building_id, resource) for unmet
        # demand; cleared on the same sample we emit a starved entry
        # so it doesn't keep firing every tick.  Keyed weakly only
        # logically — the dict is pruned on each sample to drop ids
        # that have disappeared.
        self._unmet_since: dict[tuple[int, str], float] = {}

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
            name="HexColonyLogisticsMonitor",
            daemon=True,
        )
        self._writer.start()

    def stop(self) -> None:
        if self._writer is None:
            return
        self._stopped.set()
        try:
            self._queue.put_nowait(None)
        except queue.Full:
            pass
        self._writer.join(timeout=2.0)
        self._writer = None

    # ── Hot-path API ─────────────────────────────────────────────

    def maybe_sample(self, world: "World") -> None:
        """Emit a sample if at least :attr:`interval_s` simulation
        seconds have passed since the last one.  Cheap when not due
        (a single float compare)."""
        if not self.enabled:
            return
        sim_t = float(getattr(world, "time_elapsed", 0.0))
        if sim_t < self._next_sample_sim_t:
            return
        self._next_sample_sim_t = sim_t + self.interval_s
        self._frame_index += 1
        try:
            record = self._snapshot(world, sim_t)
        except Exception as exc:  # noqa: BLE001 — never crash the sim
            record = {
                "t_real": round(time.perf_counter() - self._t0_real, 3),
                "t_sim": round(sim_t, 3),
                "frame_index": self._frame_index,
                "error": f"{type(exc).__name__}: {exc}",
            }
        try:
            self._queue.put_nowait(record)
            self._sample_count += 1
        except queue.Full:
            pass

    @property
    def sample_count(self) -> int:
        return self._sample_count

    # ── Snapshot ─────────────────────────────────────────────────

    def _snapshot(self, world: "World", sim_t: float) -> dict:
        """Build a self-contained dict describing logistics state."""
        from compprog_pygame.games.hex_colony.buildings import BuildingType
        from compprog_pygame.games.hex_colony.people import Task

        # Map building -> network for quick reverse lookup.
        nets = list(getattr(world, "networks", []) or [])
        bid_to_net: dict[int, "int"] = {}
        for net in nets:
            for b in net.buildings:
                bid_to_net[id(b)] = net.id

        # Bucket haulers by network and gather active jobs.
        haulers_by_net: dict[int, dict[str, int]] = {}
        active_jobs_by_net: dict[int, list[dict]] = {}
        for p in world.population.people:
            if not getattr(p, "is_logistics", False):
                continue
            home = getattr(p, "home", None)
            net_id = bid_to_net.get(id(home)) if home is not None else None
            if net_id is None:
                continue
            buckets = haulers_by_net.setdefault(
                net_id, {"idle": 0, "pickup": 0, "deliver": 0},
            )
            task = getattr(p, "task", None)
            if task == Task.LOGISTICS_PICKUP:
                buckets["pickup"] += 1
            elif task == Task.LOGISTICS_DELIVER:
                buckets["deliver"] += 1
            else:
                buckets["idle"] += 1
            src = getattr(p, "logistics_src", None)
            dst = getattr(p, "logistics_dst", None)
            res = getattr(p, "logistics_res", None)
            if src is not None and dst is not None and res is not None:
                jobs = active_jobs_by_net.setdefault(net_id, [])
                if len(jobs) < 32:  # cap per network so log stays bounded
                    jobs.append({
                        "src_type": src.type.name,
                        "src": [src.coord.q, src.coord.r],
                        "dst_type": dst.type.name,
                        "dst": [dst.coord.q, dst.coord.r],
                        "res": res.name,
                        "qty": round(
                            float(getattr(p, "logistics_amount", 0.0) or 0.0), 2,
                        ),
                        "task": (task.name.replace("LOGISTICS_", "")
                                 if task is not None else "?"),
                    })

        # Per-network supply/demand aggregates.
        seen_keys: set[tuple[int, str]] = set()
        net_records: list[dict] = []
        for net in nets:
            faction = getattr(net, "faction", "SURVIVOR")
            if faction != "SURVIVOR":
                # Skip rival faction networks for now — they generate noise
                # without helping the player diagnose their own colony.
                continue
            supply_totals: dict[str, float] = {}
            demand_totals: dict[str, float] = {}
            unmet: dict[str, float] = {}
            starved: list[dict] = []
            # Per-network supplier resource set so we can flag demand
            # with no possible internal supplier.
            for b in net.buildings:
                if b.storage_capacity <= 0:
                    continue
                try:
                    sup = world._building_supply(b)
                except Exception:  # noqa: BLE001
                    sup = {}
                for r, amt in sup.items():
                    supply_totals[r.name] = (
                        supply_totals.get(r.name, 0.0) + float(amt)
                    )
            for b in net.buildings:
                if b.storage_capacity <= 0:
                    continue
                try:
                    dem = world._building_demand(b)
                except Exception:  # noqa: BLE001
                    dem = {}
                for r, need in dem.items():
                    demand_totals[r.name] = (
                        demand_totals.get(r.name, 0.0) + float(need)
                    )
                    has_supplier = r.name in supply_totals
                    # Track per-(building, resource) starvation timer.
                    key = (id(b), r.name)
                    seen_keys.add(key)
                    first_seen = self._unmet_since.get(key)
                    if first_seen is None:
                        # Only start the clock once nothing is in
                        # flight to satisfy this need.
                        try:
                            claimed = world._claimed_demand_for(b, r)
                        except Exception:  # noqa: BLE001
                            claimed = 0.0
                        if need - claimed > 0.5:
                            self._unmet_since[key] = sim_t
                            first_seen = sim_t
                    if first_seen is not None:
                        starved_for = sim_t - first_seen
                        if (starved_for >= _STARVED_THRESHOLD_S
                                and not has_supplier):
                            starved.append({
                                "type": b.type.name,
                                "coord": [b.coord.q, b.coord.r],
                                "missing": {r.name: round(float(need), 2)},
                                "starved_for_s": round(starved_for, 1),
                            })
                    if not has_supplier:
                        unmet[r.name] = (
                            unmet.get(r.name, 0.0) + float(need)
                        )

            net_records.append({
                "id": net.id,
                "faction": faction,
                "buildings": len(net.buildings),
                "haulers": haulers_by_net.get(net.id, {
                    "idle": 0, "pickup": 0, "deliver": 0,
                }),
                "supply": {k: round(v, 1) for k, v in supply_totals.items()},
                "demand": {k: round(v, 1) for k, v in demand_totals.items()},
                "unmet": {k: round(v, 1) for k, v in unmet.items()},
                "starved": starved,
                "active_jobs": active_jobs_by_net.get(net.id, []),
            })

        # Drop stale (id, res) entries so the dict can't grow forever
        # as buildings are placed and removed across a long session.
        if len(self._unmet_since) > len(seen_keys) * 2:
            for k in list(self._unmet_since):
                if k not in seen_keys:
                    self._unmet_since.pop(k, None)

        return {
            "t_real": round(time.perf_counter() - self._t0_real, 3),
            "t_sim": round(sim_t, 3),
            "frame_index": self._frame_index,
            "networks": net_records,
        }

    # ── Background writer ────────────────────────────────────────

    def _writer_loop(self) -> None:
        try:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass
        try:
            f = open(self.log_path, "a", encoding="utf-8", buffering=1)
        except OSError:
            # Drain silently so the main thread never blocks.
            while not self._stopped.is_set():
                try:
                    item = self._queue.get(timeout=0.5)
                except queue.Empty:
                    continue
                if item is None:
                    break
            return
        try:
            try:
                f.write(json.dumps({
                    "session_start": time.time(),
                    "interval_s": self.interval_s,
                    "starved_threshold_s": _STARVED_THRESHOLD_S,
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


__all__ = ["LogisticsMonitor", "default_log_path"]
