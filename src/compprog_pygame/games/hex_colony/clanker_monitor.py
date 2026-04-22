"""Background clanker-AI diagnostics for Hex Colony.

Sister module to :mod:`logistics_monitor` and :mod:`perf_monitor`.
Every ``HEX_COLONY_CLANKER_INTERVAL`` simulation seconds we take a
rich snapshot of every clanker's decision state — building counts,
network-wide stockpile, recipe assignments, tier progress, recent
log entries, staffing, goal chain, and (crucially) any spill of raw
resources into the flat ``colony.inventory`` (which must stay near
zero for AI factions).  The snapshot is handed off to a daemon
writer thread that appends a JSON line to ``hex_colony_clankers.jsonl``.

The snapshot never mutates world state and all allocations happen
on the calling thread — same pattern as the logistics monitor.

JSONL format
------------

Each non-header line is a sample record::

    {
        "t_real": 12.345,
        "t_sim": 36.821,
        "frame_index": 730,
        "clankers": [
            {
                "faction": "PRIMITIVE_0",
                "home": [12, -4],
                "sim_time": 36.821,
                "population": 5,
                "housing_cap": 8,
                "worker_demand": 6,
                "tier": 1,
                "tier_name": "Iron Age",
                "researched": 3,
                "buildings": {"PATH": 18, "HABITAT": 2, ...},
                "network_stock": {"WOOD": 42.0, "PLANKS": 8.0, ...},
                "inventory_spill": {"PLANKS": 3.0},   # SHOULD be empty!
                "building_stockpile": {"PATH": 4, "HABITAT": 1},
                "recipes": [
                    {"type": "WORKSHOP", "coord": [3, -1],
                     "recipe": "PLANKS", "age_s": 12.3,
                     "has_inputs": true, "workers": 2}
                ],
                "active_research": "IRON_SMELTING",
                "goal_demand": {"IRON": 5.0, "PLANKS": 10.0},
                "log_tail": [
                    [35.1, "Wanted FORGE at ..."],
                    [35.4, "Laid 3 path tile(s) to reach (4,-2)."]
                ]
            }
        ]
    }

Toggles:
  HEX_COLONY_CLANKERS=0           disable entirely
  HEX_COLONY_CLANKER_INTERVAL=f   sim-seconds between samples (default 2.0)
  HEX_COLONY_CLANKER_LOG=path     override output path
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
_ENABLED_DEFAULT: bool = os.environ.get("HEX_COLONY_CLANKERS", "1") != "0"
_DEFAULT_INTERVAL_S: float = float(
    os.environ.get("HEX_COLONY_CLANKER_INTERVAL", "2.0"),
)
# How many trailing log lines from each clanker to capture in the
# sample.  Enough context to explain what the AI just decided
# without blowing up the on-disk record.
_LOG_TAIL_N: int = 12


def default_log_path() -> Path:
    env = os.environ.get("HEX_COLONY_CLANKER_LOG")
    if env:
        return Path(env)
    return Path.cwd() / "hex_colony_clankers.jsonl"


class ClankerMonitor:
    """Per-clanker decision diagnostics.

    Usage mirrors :class:`LogisticsMonitor`: call :meth:`start` once,
    :meth:`maybe_sample` from the game loop, and :meth:`stop` on
    shutdown.  Safe to call with no clankers present (Easy mode) —
    the sample simply writes an empty ``clankers`` list.
    """

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
            name="HexColonyClankerMonitor",
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

    def maybe_sample(self, world: "World", manager) -> None:
        if not self.enabled:
            return
        sim_t = float(getattr(world, "time_elapsed", 0.0))
        if sim_t < self._next_sample_sim_t:
            return
        self._next_sample_sim_t = sim_t + self.interval_s
        self._frame_index += 1
        try:
            record = self._snapshot(world, manager, sim_t)
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

    def _snapshot(self, world: "World", manager, sim_t: float) -> dict:
        from compprog_pygame.games.hex_colony.buildings import BuildingType
        from compprog_pygame.games.hex_colony.resources import Resource

        clanker_records: list[dict] = []
        clankers = list(getattr(manager, "clankers", []) or [])

        for c in clankers:
            fid = c.faction_id
            colony = c.colony

            # Aggregate buildings owned by this faction.
            btype_counts: dict[str, int] = {}
            # Per-resource total across every faction-owned building's
            # storage — the "real" picture of what's in the network.
            network_stock: dict[str, float] = {}
            recipes: list[dict] = []
            for b in world.buildings.buildings:
                if getattr(b, "faction", "SURVIVOR") != fid:
                    continue
                btype_counts[b.type.name] = (
                    btype_counts.get(b.type.name, 0) + 1
                )
                for r, amt in b.storage.items():
                    if amt:
                        network_stock[r.name] = (
                            network_stock.get(r.name, 0.0) + float(amt)
                        )
                recipe = getattr(b, "recipe", None)
                if recipe is not None:
                    coord_key = (b.coord.q, b.coord.r)
                    set_at = c._recipe_set_at.get(coord_key)
                    age = (sim_t - set_at) if set_at is not None else None
                    # "has_inputs" reflects whether every ingredient
                    # is obtainable *somewhere* in the colony right
                    # now — either in the building's own input slot
                    # or accessible via logistics.  We call into the
                    # clanker's own predicate if it exists; otherwise
                    # best-effort inspect the recipe.
                    has_inputs = _recipe_has_inputs(world, c, b, recipe)
                    recipes.append({
                        "type": b.type.name,
                        "coord": [b.coord.q, b.coord.r],
                        "recipe": (recipe.name if hasattr(recipe, "name")
                                   else str(recipe)),
                        "age_s": (round(age, 1) if age is not None else None),
                        "has_inputs": has_inputs,
                        "workers": int(getattr(b, "workers", 0)),
                        "progress": round(
                            float(getattr(b, "craft_progress", 0.0)), 2,
                        ),
                    })

            # Flat inventory spill — MUST be empty for clankers.
            # Anything here is a leak (pre-existing state, or a
            # fallback that shouldn't have fired).
            inventory_spill: dict[str, float] = {}
            for r in Resource:
                amt = colony.inventory[r]
                if amt > 0.01:
                    inventory_spill[r.name] = round(float(amt), 2)

            # Building stockpile (placeables the AI has queued).
            building_stockpile: dict[str, int] = {}
            for bt in BuildingType:
                n = colony.building_inventory[bt]
                if n > 0:
                    building_stockpile[bt.name] = int(n)

            # Staffing snapshot — best-effort, via the clanker's own
            # helper if available.
            pop = 0
            cap = 0
            demand = 0
            try:
                pop, cap, demand, _ = c._staffing_state(world)
            except Exception:  # noqa: BLE001
                pass

            # Tier + research.
            tier_tracker = colony.tier_tracker
            try:
                from compprog_pygame.games.hex_colony.tech_tree import (
                    TIERS as _TIERS,
                )
                tier_idx = tier_tracker.current_tier
                tier_name = (_TIERS[tier_idx].name
                             if 0 <= tier_idx < len(_TIERS) else "?")
            except Exception:  # noqa: BLE001
                tier_idx = getattr(tier_tracker, "current_tier", 0)
                tier_name = "?"
            active_research = None
            try:
                active_research = getattr(
                    colony.tech_tree, "current_research", None,
                )
                if active_research is not None:
                    active_research = str(active_research)
            except Exception:  # noqa: BLE001
                pass
            researched = int(getattr(colony.tech_tree,
                                     "researched_count", 0))

            # Goal demand + recent log lines.
            goal_demand = {
                r.name: round(float(v), 2)
                for r, v in getattr(c, "_goal_demand", {}).items()
                if v > 0
            }
            log_tail = [
                [round(float(t), 2), str(m)]
                for (t, m) in list(c.log)[-_LOG_TAIL_N:]
            ]

            clanker_records.append({
                "faction": fid,
                "home": [c.home.q, c.home.r],
                "sim_time": round(sim_t, 2),
                "population": int(pop),
                "housing_cap": int(cap),
                "worker_demand": int(demand),
                "tier": int(tier_idx),
                "tier_name": tier_name,
                "researched": researched,
                "buildings": btype_counts,
                "network_stock": {
                    k: round(v, 1) for k, v in network_stock.items()
                },
                "inventory_spill": inventory_spill,
                "building_stockpile": building_stockpile,
                "recipes": recipes,
                "active_research": active_research,
                "goal_demand": goal_demand,
                "log_tail": log_tail,
                # Diagnostics added 4/21 to chase the
                # "PRIMITIVE_0 idle for 4000s" / "FORGE stuck on
                # COPPER_BAR" symptoms.
                "tick_ms": round(float(getattr(c, "last_tick_ms", 0.0)), 2),
                "idle_streak_s": (
                    round(sim_t - c._idle_streak_start, 1)
                    if getattr(c, "_idle_streak_start", -1.0) >= 0
                    else 0.0
                ),
                "blocked_targets": len(
                    getattr(c, "_blocked_targets", {}) or {},
                ),
                # Comprehensive diagnostics added to answer "is the
                # AI actually making progress?" without tailing 3k log
                # lines.  All four counters are lifetime totals.
                "counters": {
                    "build_attempts": int(
                        getattr(c, "_build_attempts", 0)),
                    "builds_placed": int(
                        getattr(c, "_builds_placed", 0)),
                    "path_tiles_laid": int(
                        getattr(c, "_path_tiles_laid", 0)),
                    "path_extends_ok": int(
                        getattr(c, "_path_extends_ok", 0)),
                    "path_extends_fail": int(
                        getattr(c, "_path_extends_fail", 0)),
                    "research_started": int(
                        getattr(c, "_research_started", 0)),
                    "recipes_set": int(
                        getattr(c, "_recipes_set", 0)),
                    "priorities_set": int(
                        getattr(c, "_priorities_set", 0)),
                },
                # Blacklist breakdown: which building types the AI
                # keeps failing to place (top 6 by count).  Helpful
                # for spotting "QUARRY always unreachable" symptoms.
                "blocked_by_btype": _top_btypes_blocked(c, 6),
                # Which btype families are currently on the
                # "don't retry yet" cooldown, and for how much longer.
                "btype_cooldowns": _btype_cooldowns_remaining(c, sim_t),
                # Path/bridge network footprint — raw size of the AI's
                # reachable road graph.  Cheap proxy for "how much
                # expansion has the AI managed so far".
                "network": {
                    "path_tiles": int(
                        btype_counts.get("PATH", 0)),
                    "bridge_tiles": int(
                        btype_counts.get("BRIDGE", 0)),
                    "path_stock": int(
                        colony.building_inventory.__getitem__(
                            BuildingType.PATH,
                        )),
                    "bridge_stock": int(
                        colony.building_inventory.__getitem__(
                            BuildingType.BRIDGE,
                        )),
                    "owned_buildings": sum(btype_counts.values()),
                },
            })

        return {
            "t_real": round(time.perf_counter() - self._t0_real, 3),
            "t_sim": round(sim_t, 3),
            "frame_index": self._frame_index,
            "clankers": clanker_records,
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


def _recipe_has_inputs(world, clanker, building, recipe) -> bool:
    """Best-effort: does *building* actually have every ingredient
    for its assigned recipe available somewhere in the colony?"""
    from compprog_pygame.games.hex_colony.buildings import BuildingType
    from compprog_pygame.games.hex_colony.resources import (
        MATERIAL_RECIPES, Resource,
    )
    # Building-cost recipe (e.g. WORKSHOP crafting a HABITAT).
    if isinstance(recipe, BuildingType):
        from compprog_pygame.games.hex_colony.buildings import (
            BUILDING_COSTS,
        )
        cost = BUILDING_COSTS.get(recipe)
        if cost is None:
            return True
        for res, amt in cost.costs.items():
            if clanker._stock(world, res) < float(amt):
                return False
        return True
    # Material recipe (Resource output).
    if isinstance(recipe, Resource):
        mrec = MATERIAL_RECIPES.get(recipe)
        if mrec is None:
            return True
        for res, amt in mrec.inputs.items():
            if clanker._stock(world, res) < float(amt):
                return False
        return True
    return True


def _top_btypes_blocked(clanker, limit: int) -> dict[str, int]:
    """Aggregate the clanker's target blacklist by BuildingType
    name and return the *limit* most-populated families."""
    blocked = getattr(clanker, "_blocked_targets", None) or {}
    counts: dict[str, int] = {}
    for key in blocked:
        # Keys are (btype_name, q, r) tuples.
        if isinstance(key, tuple) and key:
            name = key[0]
            if isinstance(name, str):
                counts[name] = counts.get(name, 0) + 1
    if not counts:
        return {}
    top = sorted(counts.items(), key=lambda kv: -kv[1])[:limit]
    return dict(top)


def _btype_cooldowns_remaining(clanker, sim_t: float) -> dict[str, float]:
    """For each btype still on the failure-cooldown, return how much
    sim-time is left before the planner will retry."""
    from compprog_pygame.games.hex_colony.clankers import (
        _BTYPE_FAIL_COOLDOWN,
    )
    cooldowns = getattr(clanker, "_btype_fail_cooldown", None) or {}
    out: dict[str, float] = {}
    for name, t_set in cooldowns.items():
        remaining = _BTYPE_FAIL_COOLDOWN - (sim_t - t_set)
        if remaining > 0:
            out[name] = round(float(remaining), 1)
    return out


__all__ = ["ClankerMonitor", "default_log_path"]
