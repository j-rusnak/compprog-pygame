"""Clanker AI â€” autonomous rival colonies for Hex Colony's Hard mode.

A *clanker* is the AI counterpart to the player.  One clanker is
spawned per AI tribal camp at world-gen time.  Each clanker plays
the game using the **same simulation systems as the player**: it
owns a :class:`ColonyState`, places real :class:`Building` objects
tagged with its faction id, and lets ``World.update`` drive every
production / consumption / population tick.

The AI's job is purely *decision making*: where to expand, what to
build next, what to research, and what recipes to set on its
crafting stations.  Determinism is preserved by drawing every
random choice from a per-faction RNG seeded from
``(world.seed, faction_id)``.

This module deliberately keeps the planner **simple** â€” a single
prioritised wishlist drives both placement and recipe selection,
so a stuck colony is easy to debug from the
``hex_colony_clankers.jsonl`` monitor logs.
"""

from __future__ import annotations

import hashlib
import random
import time
from collections import deque
from dataclasses import dataclass, field

from compprog_pygame.games.hex_colony.buildings import (
    BUILDING_COSTS,
    BUILDING_HOUSING,
    BUILDING_MAX_WORKERS,
    BuildingType,
)
from compprog_pygame.games.hex_colony.colony import ColonyState
from compprog_pygame.games.hex_colony.hex_grid import HexCoord
from compprog_pygame.games.hex_colony.procgen import UNBUILDABLE
from compprog_pygame.games.hex_colony.resources import Resource
from compprog_pygame.games.hex_colony.tech_tree import TECH_NODES
from compprog_pygame.games.hex_colony.world import World


# â”€â”€ Tunables â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
_BUILD_INTERVAL: float = 4.0          # sim-s between build attempts
_RESEARCH_INTERVAL: float = 6.0       # sim-s between research picks
_RECIPE_INTERVAL: float = 8.0         # sim-s between recipe picks
_AUDIT_INTERVAL: float = 30.0         # sim-s between building audits
_PRIORITY_INTERVAL: float = 20.0      # sim-s between priority rebalance

_RECIPE_STICKY_TIME: float = 60.0     # min sim-s a recipe stays put
_RECIPE_STALE_TIME: float = 240.0     # clear recipe if no progress
_BLOCKED_TARGET_COOLDOWN: float = 120.0  # blacklist a (btype, coord)
_BTYPE_FAIL_COOLDOWN: float = 60.0    # blacklist a whole btype
_IDLE_HEARTBEAT_INTERVAL: float = 60.0  # log "idle" every N sim-s

_MAX_BUILDINGS_PER_CLANKER: int = 80
_MAX_EXPANSION_RADIUS: int = 64
_MAX_PATH_RUN: int = 48
_MAX_PLACEMENT_BFS_VISITS: int = 2000
_LOG_MAXLEN: int = 60

# Buildings that don't draw from the workforce pool.
_NON_WORKER_BTYPES: frozenset[BuildingType] = frozenset({
    BuildingType.PATH, BuildingType.BRIDGE, BuildingType.WALL,
    BuildingType.PIPE, BuildingType.CONVEYOR,
    BuildingType.HABITAT, BuildingType.HOUSE, BuildingType.STORAGE,
})

# Lazily-built terrain-affinity map.  FARM/HOUSE/HABITAT/STORAGE
# etc. are intentionally absent â€” they have no terrain requirement.
_TERRAIN_FOR: dict[BuildingType, set] = {}


def _terrain_for(btype: BuildingType) -> set | None:
    global _TERRAIN_FOR
    if not _TERRAIN_FOR:
        from compprog_pygame.games.hex_colony.procgen import Terrain
        _TERRAIN_FOR = {
            BuildingType.WOODCUTTER: {
                Terrain.FOREST, Terrain.DENSE_FOREST,
            },
            BuildingType.QUARRY: {
                Terrain.STONE_DEPOSIT, Terrain.MOUNTAIN,
                Terrain.IRON_VEIN, Terrain.COPPER_VEIN,
            },
            BuildingType.GATHERER: {Terrain.FIBER_PATCH},
            BuildingType.WELL: {Terrain.WATER},
            BuildingType.MINING_MACHINE: {
                Terrain.IRON_VEIN, Terrain.COPPER_VEIN,
                Terrain.STONE_DEPOSIT, Terrain.MOUNTAIN,
            },
            BuildingType.OIL_DRILL: {Terrain.OIL_DEPOSIT},
        }
    return _TERRAIN_FOR.get(btype)


def _rng_for(world_seed: str, faction_id: str) -> random.Random:
    h = hashlib.sha256(
        f"{world_seed}:{faction_id}".encode("utf-8"),
    ).hexdigest()
    return random.Random(int(h, 16))


# â”€â”€ Worker-priority buckets â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
_HIGH_PRIORITY_WORK_TYPES: frozenset[BuildingType] = frozenset({
    BuildingType.WOODCUTTER, BuildingType.QUARRY,
    BuildingType.GATHERER, BuildingType.FARM, BuildingType.WELL,
    BuildingType.MINING_MACHINE, BuildingType.OIL_DRILL,
    BuildingType.WORKSHOP, BuildingType.FORGE,
    BuildingType.ASSEMBLER, BuildingType.REFINERY,
    BuildingType.CHEMICAL_PLANT, BuildingType.OIL_REFINERY,
})
_LOW_PRIORITY_WORK_TYPES: frozenset[BuildingType] = frozenset({
    BuildingType.RESEARCH_CENTER,
})

# Producer buildings the AI will consider placing for raw resources.
_PRODUCER_FOR: dict[Resource, tuple[BuildingType, ...]] = {
    Resource.WOOD: (BuildingType.WOODCUTTER,),
    Resource.STONE: (BuildingType.QUARRY,),
    Resource.FIBER: (BuildingType.GATHERER,),
    Resource.FOOD: (BuildingType.FARM, BuildingType.GATHERER),
    Resource.IRON: (BuildingType.MINING_MACHINE, BuildingType.QUARRY),
    Resource.COPPER: (BuildingType.MINING_MACHINE, BuildingType.QUARRY),
    Resource.OIL: (BuildingType.OIL_DRILL,),
}


@dataclass
class _Snapshot:
    my_buildings: list = field(default_factory=list)
    by_type: dict = field(default_factory=dict)
    owned_coords: list = field(default_factory=list)
    owned_coord_set: set = field(default_factory=set)
    camp: object | None = None


@dataclass
class Clanker:
    """A single AI rival colony â€” see module docstring."""

    faction_id: str
    home: HexCoord
    colony: ColonyState
    rng: random.Random

    # Tick timers.
    build_timer: float = 0.0
    research_timer: float = 0.0
    recipe_timer: float = 0.0
    audit_timer: float = 0.0
    priority_timer: float = 0.0

    # Per-station sim-time when its recipe was last changed.
    _recipe_set_at: dict[tuple[int, int], float] = field(
        default_factory=dict,
    )

    # Blacklists.  Pruned lazily in :meth:`_try_build`.
    _blocked_targets: dict[tuple[str, int, int], float] = field(
        default_factory=dict,
    )
    _btype_fail_cooldown: dict[str, float] = field(
        default_factory=dict,
    )

    # Idle tracking.
    _last_idle_log: float = -1e9
    _idle_streak_start: float = -1.0

    # Per-tick caches (cleared at start of each :meth:`update`).
    _snap: _Snapshot | None = None
    _stock_cache: dict = field(default_factory=dict)
    _placement_bfs: dict | None = None

    # Wall-clock for the perf monitor.
    last_tick_ms: float = 0.0

    # Lifetime counters surfaced by the monitor.
    _build_attempts: int = 0
    _builds_placed: int = 0
    _builds_blacklisted: int = 0
    _path_extends_ok: int = 0
    _path_extends_fail: int = 0
    _path_tiles_laid: int = 0
    _research_started: int = 0
    _recipes_set: int = 0
    _recipes_cleared: int = 0
    _priorities_set: int = 0

    # Kept for the monitor's compatibility (was populated by the old
    # goal-chain planner).  The simplified planner doesn't compute
    # forward demand, so this stays empty.
    _goal_demand: dict[Resource, float] = field(default_factory=dict)

    # Decision log surfaced via the player's "Possess" panel.
    log: deque[tuple[float, str]] = field(
        default_factory=lambda: deque(maxlen=_LOG_MAXLEN),
    )

    # â”€â”€ Logging â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def _log(self, world: World, msg: str) -> None:
        now = world.time_elapsed
        if self.log:
            last_t, last_msg = self.log[-1]
            if last_msg == msg and (now - last_t) < 30.0:
                return
        self.log.append((now, msg))

    # â”€â”€ Per-tick snapshot â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def _snapshot(self, world: World) -> _Snapshot:
        snap = self._snap
        if snap is not None:
            return snap
        fid = self.faction_id
        my: list = []
        by_type: dict = {}
        coords: list = []
        coord_set: set = set()
        for b in world.buildings.buildings:
            if getattr(b, "faction", "SURVIVOR") != fid:
                continue
            my.append(b)
            by_type.setdefault(b.type, []).append(b)
            coords.append(b.coord)
            coord_set.add(b.coord)
        snap = _Snapshot(
            my_buildings=my,
            by_type=by_type,
            owned_coords=coords,
            owned_coord_set=coord_set,
            camp=world.buildings.at(self.home),
        )
        self._snap = snap
        return snap

    def _invalidate_snapshot(self) -> None:
        self._snap = None
        self._placement_bfs = None

    # â”€â”€ Top-level update â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def update(self, world: World, dt: float) -> None:
        _t0 = time.perf_counter()
        self.build_timer += dt
        self.research_timer += dt
        self.recipe_timer += dt
        self.audit_timer += dt
        self.priority_timer += dt

        # Per-tick caches are stale.
        self._invalidate_snapshot()
        if self._stock_cache:
            self._stock_cache.clear()

        if self.audit_timer >= _AUDIT_INTERVAL:
            self.audit_timer = 0.0
            self._audit_buildings(world)
        if self.build_timer >= _BUILD_INTERVAL:
            self.build_timer = 0.0
            self._try_build(world)
        if self.research_timer >= _RESEARCH_INTERVAL:
            self.research_timer = 0.0
            self._try_start_research(world)
        if self.recipe_timer >= _RECIPE_INTERVAL:
            self.recipe_timer = 0.0
            self._set_recipes(world)
        if self.priority_timer >= _PRIORITY_INTERVAL:
            self.priority_timer = 0.0
            self._rebalance_worker_priorities(world)

        self.last_tick_ms = (time.perf_counter() - _t0) * 1000.0

    # â”€â”€ Generic queries â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def _is_unlocked(self, btype: BuildingType) -> bool:
        return (
            self.colony.tech_tree.is_building_unlocked(btype)
            and self.colony.tier_tracker.is_building_unlocked(btype)
        )

    def _can_pay_for(self, btype: BuildingType) -> bool:
        """Direct placement requires a stockpiled blueprint â€”
        crafting raw resources into more blueprints is the
        WORKSHOP / FORGE's job."""
        return self.colony.building_inventory[btype] > 0

    def _has_building(self, world: World, btype: BuildingType) -> bool:
        return bool(self._snapshot(world).by_type.get(btype))

    def _count_building(self, world: World, btype: BuildingType) -> int:
        lst = self._snapshot(world).by_type.get(btype)
        return len(lst) if lst else 0

    def _stock(self, world: World, res: Resource) -> float:
        """Total of *res* across the colony's logistics network."""
        cached = self._stock_cache.get(res)
        if cached is not None:
            return cached
        total = float(self.colony.inventory[res])
        for b in self._snapshot(world).my_buildings:
            amt = b.storage.get(res, 0.0)
            if amt:
                total += float(amt)
        self._stock_cache[res] = total
        return total

    def _staffing_state(
        self, world: World,
    ) -> tuple[int, int, int, int]:
        """Return ``(my_pop, housing_cap, worker_demand, workers_assigned)``."""
        try:
            my_pop = world.faction_population_count(self.faction_id)
        except Exception:
            my_pop = sum(
                1 for p in world.population.people
                if p.home is not None
                and getattr(p.home, "faction", "SURVIVOR")
                == self.faction_id
            )
        housing_cap = 0
        worker_demand = 0
        workers_assigned = 0
        for b in self._snapshot(world).my_buildings:
            housing_cap += BUILDING_HOUSING.get(b.type, 0)
            worker_demand += BUILDING_MAX_WORKERS.get(b.type, 0)
            workers_assigned += getattr(b, "workers", 0)
        return my_pop, housing_cap, worker_demand, workers_assigned

    # â”€â”€ Wishlist (the heart of the planner) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def _wishlist(self, world: World) -> list[BuildingType]:
        """Ordered list of buildings this clanker wants to have, most
        urgent first.  A single source of truth shared by the
        placement loop and the recipe scheduler â€” what we want to
        place is what the workshops should be crafting blueprints for.

        Each entry is *unlocked* and we don't already have all we
        need of it; entries we already have enough of are dropped.
        """
        my_pop, housing_cap, worker_demand, _ = self._staffing_state(world)
        food = self._stock(world, Resource.FOOD)
        wood = self._stock(world, Resource.WOOD)
        stone = self._stock(world, Resource.STONE)

        wl: list[BuildingType] = []

        def want(bt: BuildingType) -> None:
            if bt in wl:
                return
            # Allow locked buildings if we already have a stockpiled
            # blueprint for them â€” they were crafted earlier (or
            # spawned with the colony) and are placeable right now.
            if (not self._is_unlocked(bt)
                    and self.colony.building_inventory[bt] <= 0):
                return
            wl.append(bt)

        # 0. Place anything in the stockpile that fixes a real
        #    shortfall.  Stockpiled blueprints are wasted if we let
        #    them sit â€” surface them ahead of new crafting.
        food_now = self._stock(world, Resource.FOOD)
        for bt in (
            BuildingType.FARM, BuildingType.GATHERER,
            BuildingType.WOODCUTTER, BuildingType.QUARRY,
            BuildingType.HABITAT, BuildingType.HOUSE,
            BuildingType.WELL, BuildingType.STORAGE,
        ):
            if self.colony.building_inventory[bt] > 0:
                # Skip food buildings if we already have surplus.
                if (bt in (BuildingType.FARM, BuildingType.GATHERER)
                        and food_now >= 80.0):
                    continue
                want(bt)

        n_workers = self._count_building(world, BuildingType.WOODCUTTER)
        n_quarries = self._count_building(world, BuildingType.QUARRY)
        n_gatherer = self._count_building(world, BuildingType.GATHERER)
        n_farm = self._count_building(world, BuildingType.FARM)
        n_workshop = self._count_building(world, BuildingType.WORKSHOP)
        n_research = self._count_building(world, BuildingType.RESEARCH_CENTER)
        n_storage = self._count_building(world, BuildingType.STORAGE)
        n_habitat = self._count_building(world, BuildingType.HABITAT)
        food_producers = n_farm + n_gatherer

        # 1. Food crisis â†’ farm first (always available, no terrain
        #    requirement), then gatherer as fallback.
        if food < 25.0 or food_producers == 0:
            if self._is_unlocked(BuildingType.FARM):
                want(BuildingType.FARM)
            want(BuildingType.GATHERER)

        # 2. Housing crisis â†’ grow population.  Population is what
        #    unlocks every other priority, so this comes before
        #    everything except active starvation.
        no_room = my_pop >= int(housing_cap * 0.85)
        understaffed = worker_demand > my_pop + 1
        if (no_room or understaffed) and housing_cap < 64:
            if self._is_unlocked(BuildingType.HABITAT):
                want(BuildingType.HABITAT)
            elif self._is_unlocked(BuildingType.HOUSE):
                want(BuildingType.HOUSE)

        # 3. Bootstrap essentials â€” at least one of each.
        if n_workers == 0:
            want(BuildingType.WOODCUTTER)
        if n_quarries == 0:
            want(BuildingType.QUARRY)
        if n_gatherer == 0:
            want(BuildingType.GATHERER)
        if n_farm == 0 and self._is_unlocked(BuildingType.FARM):
            want(BuildingType.FARM)
        if n_workshop == 0:
            want(BuildingType.WORKSHOP)
        if n_research == 0 and self._is_unlocked(
                BuildingType.RESEARCH_CENTER):
            want(BuildingType.RESEARCH_CENTER)

        # 4. Newly-unlocked progression buildings â€” we want one of
        #    each as soon as it becomes available.
        for bt in (
            BuildingType.FORGE,
            BuildingType.MINING_MACHINE,
            BuildingType.REFINERY,
            BuildingType.ASSEMBLER,
            BuildingType.OIL_DRILL,
            BuildingType.OIL_REFINERY,
            BuildingType.CHEMICAL_PLANT,
            BuildingType.SOLAR_ARRAY,
            BuildingType.ROCKET_SILO,
        ):
            if self._is_unlocked(bt) and self._count_building(world, bt) == 0:
                want(bt)

        # 5. Storage when we're swimming in something.
        big_pile = any(
            self._stock(world, r) > 80.0 for r in (
                Resource.WOOD, Resource.STONE, Resource.FOOD,
                Resource.IRON, Resource.COPPER,
            )
        )
        if big_pile and n_storage < 1 + my_pop // 8:
            want(BuildingType.STORAGE)

        # 6. Scale producers proportionally to population.  One
        #    producer per ~4 colonists is a reasonable steady-state.
        target_extractors = max(1, my_pop // 4)
        if n_workers < target_extractors and wood < 200:
            want(BuildingType.WOODCUTTER)
        if n_quarries < target_extractors and stone < 200:
            want(BuildingType.QUARRY)
        if (n_farm + n_gatherer) < max(2, my_pop // 3) and food < 200:
            if self._is_unlocked(BuildingType.FARM):
                want(BuildingType.FARM)
            else:
                want(BuildingType.GATHERER)

        # 7. Extra HABITAT to keep growth moving even when we're
        #    not maxed out â€” caps growth at the housing limit.
        if (housing_cap < my_pop * 2
                and self._is_unlocked(BuildingType.HABITAT)
                and n_habitat < 12):
            want(BuildingType.HABITAT)

        return wl

    # â”€â”€ Build attempt â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def _try_build(self, world: World) -> None:
        self._build_attempts += 1
        now = world.time_elapsed

        # Soft cap on total non-path buildings.
        non_path = sum(
            1 for b in self._snapshot(world).my_buildings
            if b.type not in (
                BuildingType.PATH, BuildingType.BRIDGE,
                BuildingType.WALL, BuildingType.PIPE,
                BuildingType.CONVEYOR,
            )
        )
        if non_path >= _MAX_BUILDINGS_PER_CLANKER:
            return

        # Prune expired blacklists.
        if self._blocked_targets:
            for k in [k for k, t in self._blocked_targets.items()
                      if (now - t) >= _BLOCKED_TARGET_COOLDOWN]:
                self._blocked_targets.pop(k, None)
        if self._btype_fail_cooldown:
            for k in [k for k, t in self._btype_fail_cooldown.items()
                      if (now - t) >= _BTYPE_FAIL_COOLDOWN]:
                self._btype_fail_cooldown.pop(k, None)

        wl = self._wishlist(world)
        # Pick the first item we can actually pay for and that isn't
        # on the btype cooldown.
        my_pop, _, worker_demand, _ = self._staffing_state(world)
        for btype in wl:
            if self._btype_fail_cooldown.get(btype.name, -1e9) > now - _BTYPE_FAIL_COOLDOWN:
                continue
            if not self._can_pay_for(btype):
                continue
            # Don't pile on more worker-buildings if we have no
            # spare workers â€” except for housing (which fixes the
            # shortage).
            if (btype not in _NON_WORKER_BTYPES
                    and BUILDING_MAX_WORKERS.get(btype, 0) > 0
                    and worker_demand >= my_pop + 2):
                # Allow only essentials when understaffed.
                if self._has_building(world, btype):
                    continue
            target = self._find_placement(world, btype)
            if target is None:
                self._btype_fail_cooldown[btype.name] = now
                continue
            # Path-connect first.
            if not self._is_path_connected(world, target):
                if not self._lay_path_to(world, target):
                    # Try extending toward it for next tick.
                    if self._extend_path_toward(world, target):
                        self._path_extends_ok += 1
                    else:
                        self._path_extends_fail += 1
                    self._blocked_targets[
                        (btype.name, target.q, target.r)
                    ] = now
                    self._builds_blacklisted += 1
                    continue
            if self._place(world, btype, target):
                self._idle_streak_start = -1.0
                self._last_idle_log = now
                self._log(
                    world,
                    f"Placed {btype.name} at "
                    f"({target.q},{target.r}).",
                )
                return
            # Place failed despite passable target â€” blacklist.
            self._blocked_targets[
                (btype.name, target.q, target.r)
            ] = now
            self._builds_blacklisted += 1

        # Nothing actionable this tick.
        if self._idle_streak_start < 0:
            self._idle_streak_start = now
        if (now - self._last_idle_log) >= _IDLE_HEARTBEAT_INTERVAL:
            pop, cap, demand, _ = self._staffing_state(world)
            food = int(self._stock(world, Resource.FOOD))
            self._log(
                world,
                f"Idle ({int(now - self._idle_streak_start)}s) â€” "
                f"pop {pop}/{cap}, {demand} job slots, "
                f"food {food}, want={','.join(b.name for b in wl[:3])}.",
            )
            self._last_idle_log = now

    # â”€â”€ Placement helpers â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def _is_adjacent_to_owned(
        self, world: World, coord: HexCoord,
    ) -> bool:
        owned = self._snapshot(world).owned_coord_set
        for nb in coord.neighbors():
            if nb in owned:
                return True
        return False

    def _is_path_connected(
        self, world: World, coord: HexCoord,
    ) -> bool:
        """True iff *coord* is adjacent to a PATH/BRIDGE/TRIBAL_CAMP
        belonging to this faction."""
        for nb in coord.neighbors():
            b = world.buildings.at(nb)
            if b is None:
                continue
            if getattr(b, "faction", "SURVIVOR") != self.faction_id:
                continue
            if b.type in (BuildingType.PATH, BuildingType.BRIDGE,
                          BuildingType.TRIBAL_CAMP):
                return True
        return False

    def _is_path_passable(
        self, world: World, coord: HexCoord,
        allow_bridge: bool = False,
    ) -> bool:
        from compprog_pygame.games.hex_colony.procgen import Terrain
        tile = world.grid.get(coord)
        if tile is None:
            return False
        b = tile.building
        if b is not None:
            if (b.type in (BuildingType.PATH, BuildingType.BRIDGE)
                    and getattr(b, "faction", "SURVIVOR") == self.faction_id):
                return True
            return False
        if tile.terrain == Terrain.WATER:
            return allow_bridge
        if tile.terrain in UNBUILDABLE:
            return False
        return True

    @staticmethod
    def _tile_terrain(world: World, coord: HexCoord):
        tile = world.grid.get(coord)
        if tile is None:
            from compprog_pygame.games.hex_colony.procgen import Terrain
            return Terrain.GRASS
        return tile.terrain

    def _placement_bfs_walk(
        self, world: World,
    ) -> dict[HexCoord, int]:
        """Multi-source BFS from owned tiles â†’ dict of reachable
        hex â†’ nearest-owned distance.  Cached per-tick because every
        ``_find_placement`` call uses the same map."""
        if self._placement_bfs is not None:
            return self._placement_bfs
        owned = self._snapshot(world).owned_coord_set
        visited: dict[HexCoord, int] = {c: 0 for c in owned}
        if not owned:
            self._placement_bfs = visited
            return visited
        center = self.home
        frontier: deque[HexCoord] = deque(owned)
        while frontier:
            if len(visited) >= _MAX_PLACEMENT_BFS_VISITS:
                break
            cur = frontier.popleft()
            d = visited[cur]
            if d >= _MAX_PATH_RUN + 1:
                continue
            for nb in cur.neighbors():
                if nb in visited:
                    continue
                if nb.distance(center) > _MAX_EXPANSION_RADIUS:
                    continue
                visited[nb] = d + 1
                frontier.append(nb)
        self._placement_bfs = visited
        return visited

    def _find_placement(
        self, world: World, btype: BuildingType,
    ) -> HexCoord | None:
        """Pick the best buildable hex inside our expansion radius.

        For terrain-affinity buildings we score by how many target
        terrain tiles touch the candidate (and how rich they are).
        For housing / workshops / storage we just want a tile near
        existing territory.
        """
        owned = self._snapshot(world).owned_coord_set
        if not owned:
            return None

        target_terrain = _terrain_for(btype)
        if target_terrain is None:
            return self._find_adjacent_placement(world, btype)

        visited = self._placement_bfs_walk(world)
        candidates: list[tuple[float, HexCoord]] = []
        oil_drill = (btype == BuildingType.OIL_DRILL)
        center = self.home
        grid_get = world.grid.get
        for coord, nearest_owned in visited.items():
            if coord in owned:
                continue
            tile = grid_get(coord)
            if tile is None or tile.building is not None:
                continue
            if tile.terrain in UNBUILDABLE:
                if not (oil_drill and tile.terrain.name == "OIL_DEPOSIT"):
                    continue
            terrain_count = 0
            richness = 0.0
            if tile.terrain in target_terrain:
                terrain_count += 2
                richness += 2.0 * (
                    tile.resource_amount + tile.food_amount
                )
            for nb in coord.neighbors():
                nb_tile = grid_get(nb)
                if (nb_tile is not None
                        and nb_tile.terrain in target_terrain):
                    terrain_count += 1
                    richness += (
                        nb_tile.resource_amount + nb_tile.food_amount
                    )
            if terrain_count == 0:
                continue
            score = (
                100.0
                + 0.5 * richness
                + 5.0 * terrain_count
                - 10.0 * nearest_owned
                - 4.0 * coord.distance(center)
                + self.rng.random() * 0.5
            )
            candidates.append((score, coord))

        if not candidates:
            return None
        candidates.sort(key=lambda c: c[0], reverse=True)
        for _score, coord in candidates:
            key = (btype.name, coord.q, coord.r)
            if key in self._blocked_targets:
                continue
            return coord
        return None

    def _find_adjacent_placement(
        self, world: World, btype: BuildingType,
    ) -> HexCoord | None:
        """BFS-through-paths placement for terrain-agnostic
        buildings (housing, storage, workshops, farms)."""
        owned = self._snapshot(world).owned_coord_set
        if not owned:
            return None
        visited: set[HexCoord] = set(owned)
        queue: deque[HexCoord] = deque(owned)
        candidates: list[HexCoord] = []
        while queue:
            c = queue.popleft()
            for nb in c.neighbors():
                if nb in visited:
                    continue
                visited.add(nb)
                if nb.distance(self.home) > _MAX_EXPANSION_RADIUS:
                    continue
                tile = world.grid.get(nb)
                if tile is None:
                    continue
                if tile.building is not None:
                    if (tile.building.type in (BuildingType.PATH,
                                               BuildingType.BRIDGE)
                        and getattr(tile.building, "faction",
                                    "SURVIVOR") == self.faction_id):
                        queue.append(nb)
                    continue
                if tile.terrain in UNBUILDABLE:
                    continue
                candidates.append(nb)

        if not candidates:
            return None
        # Prefer near-home, jitter for tie-break.
        candidates.sort(
            key=lambda c: c.distance(self.home) + self.rng.random() * 0.1,
        )
        for coord in candidates:
            key = (btype.name, coord.q, coord.r)
            if key in self._blocked_targets:
                continue
            return coord
        return None

    # â”€â”€ Path laying â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def _shortest_path_to(
        self, world: World, target: HexCoord,
    ) -> list[HexCoord] | None:
        """BFS over passable land from any owned tile to a tile
        adjacent to *target*.  Returns the list of *new* hexes
        that need a PATH/BRIDGE placed on them, or ``None`` if no
        route exists within ``_MAX_PATH_RUN``."""
        owned = self._snapshot(world).owned_coord_set
        if not owned:
            return None
        bridge_stock = self.colony.building_inventory[BuildingType.BRIDGE]
        allow_bridge = bridge_stock > 0
        visited: set[HexCoord] = set(owned)
        parent: dict[HexCoord, HexCoord] = {}
        depth: dict[HexCoord, int] = {}
        queue: deque[HexCoord] = deque()
        for o in owned:
            for nb in o.neighbors():
                if nb in visited:
                    continue
                if not self._is_path_passable(
                    world, nb, allow_bridge=allow_bridge,
                ):
                    if nb == target:
                        return []
                    continue
                visited.add(nb)
                parent[nb] = o
                depth[nb] = 1
                queue.append(nb)
        found: HexCoord | None = None
        while queue:
            cur = queue.popleft()
            if any(nb == target for nb in cur.neighbors()):
                found = cur
                break
            d = depth[cur]
            if d >= _MAX_PATH_RUN:
                continue
            for nb in cur.neighbors():
                if nb in visited:
                    continue
                if not self._is_path_passable(
                    world, nb, allow_bridge=allow_bridge,
                ):
                    continue
                if nb.distance(self.home) > _MAX_EXPANSION_RADIUS:
                    continue
                visited.add(nb)
                parent[nb] = cur
                depth[nb] = d + 1
                queue.append(nb)
        if found is None:
            return None
        chain: list[HexCoord] = []
        cur = found
        while cur not in owned:
            tile = world.grid.get(cur)
            if tile is not None and tile.building is None:
                chain.append(cur)
            cur = parent[cur]
        chain.reverse()
        if len(chain) > _MAX_PATH_RUN:
            return None
        if allow_bridge:
            from compprog_pygame.games.hex_colony.procgen import Terrain
            water_steps = sum(
                1 for c in chain
                if self._tile_terrain(world, c) == Terrain.WATER
            )
            if water_steps > bridge_stock:
                return None
        return chain

    def _lay_path_to(self, world: World, target: HexCoord) -> bool:
        """Place a chain of PATH/BRIDGE so *target* becomes adjacent
        to our territory.  Aborts if not enough stock."""
        chain = self._shortest_path_to(world, target)
        if chain is None:
            return False
        if not chain:
            return True
        from compprog_pygame.games.hex_colony.procgen import Terrain
        path_steps: list[HexCoord] = []
        bridge_steps: list[HexCoord] = []
        for c in chain:
            if self._tile_terrain(world, c) == Terrain.WATER:
                bridge_steps.append(c)
            else:
                path_steps.append(c)
        if self.colony.building_inventory[BuildingType.PATH] < len(path_steps):
            return False
        if (self.colony.building_inventory[BuildingType.BRIDGE]
                < len(bridge_steps)):
            return False
        for coord in chain:
            tile = world.grid.get(coord)
            if tile is None or tile.building is not None:
                continue
            terr = tile.terrain
            btype = (BuildingType.BRIDGE if terr == Terrain.WATER
                     else BuildingType.PATH)
            self.colony.building_inventory.spend(btype)
            b = world.buildings.place(btype, coord)
            b.faction = self.faction_id
            tile.building = b
            self._path_tiles_laid += 1
        world.mark_networks_dirty()
        self._invalidate_snapshot()
        return True

    def _extend_path_toward(
        self, world: World, target: HexCoord, max_steps: int = 12,
    ) -> bool:
        """Lay a partial PATH/BRIDGE chain that gets us as close to
        *target* as our stockpile allows."""
        owned = self._snapshot(world).owned_coord_set
        if not owned:
            return False
        path_stock = self.colony.building_inventory[BuildingType.PATH]
        bridge_stock = self.colony.building_inventory[BuildingType.BRIDGE]
        if path_stock <= 0 and bridge_stock <= 0:
            return False
        allow_bridge = bridge_stock > 0
        visited: set[HexCoord] = set(owned)
        parent: dict[HexCoord, HexCoord] = {}
        depth: dict[HexCoord, int] = {}
        queue: deque[HexCoord] = deque()
        best_node: HexCoord | None = None
        best_dist: int | None = min(o.distance(target) for o in owned)
        for o in owned:
            for nb in o.neighbors():
                if nb in visited:
                    continue
                if not self._is_path_passable(
                    world, nb, allow_bridge=allow_bridge,
                ):
                    continue
                if nb.distance(self.home) > _MAX_EXPANSION_RADIUS:
                    continue
                visited.add(nb)
                parent[nb] = o
                depth[nb] = 1
                queue.append(nb)
                dd = nb.distance(target)
                if best_dist is None or dd < best_dist:
                    best_dist = dd
                    best_node = nb
        while queue:
            cur = queue.popleft()
            d = depth[cur]
            if d >= _MAX_PATH_RUN:
                continue
            for nb in cur.neighbors():
                if nb in visited:
                    continue
                if not self._is_path_passable(
                    world, nb, allow_bridge=allow_bridge,
                ):
                    continue
                if nb.distance(self.home) > _MAX_EXPANSION_RADIUS:
                    continue
                visited.add(nb)
                parent[nb] = cur
                depth[nb] = d + 1
                queue.append(nb)
                dd = nb.distance(target)
                if best_dist is None or dd < best_dist:
                    best_dist = dd
                    best_node = nb
        if best_node is None or best_node in owned:
            return False
        chain: list[HexCoord] = []
        cur = best_node
        while cur not in owned:
            tile = world.grid.get(cur)
            if tile is not None and tile.building is None:
                chain.append(cur)
            p = parent.get(cur)
            if p is None:
                break
            cur = p
        chain.reverse()
        if not chain:
            return False
        from compprog_pygame.games.hex_colony.procgen import Terrain
        to_lay: list[HexCoord] = []
        path_used = 0
        bridge_used = 0
        for c in chain:
            if len(to_lay) >= max_steps:
                break
            terr = self._tile_terrain(world, c)
            if terr == Terrain.WATER:
                if bridge_used + 1 > bridge_stock:
                    break
                bridge_used += 1
            else:
                if path_used + 1 > path_stock:
                    break
                path_used += 1
            to_lay.append(c)
        # Trim trailing water so we don't end on a dangling bridge.
        while to_lay and self._tile_terrain(world, to_lay[-1]) == Terrain.WATER:
            to_lay.pop()
        if not to_lay:
            return False
        end = to_lay[-1]
        owned_min = min(o.distance(target) for o in owned)
        if end.distance(target) >= owned_min:
            return False
        for coord in to_lay:
            tile = world.grid.get(coord)
            if tile is None or tile.building is not None:
                continue
            terr = tile.terrain
            btype = (BuildingType.BRIDGE if terr == Terrain.WATER
                     else BuildingType.PATH)
            self.colony.building_inventory.spend(btype)
            b = world.buildings.place(btype, coord)
            b.faction = self.faction_id
            tile.building = b
            self._path_tiles_laid += 1
        world.mark_networks_dirty()
        self._invalidate_snapshot()
        return True

    # â”€â”€ Place / configure / demolish â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def _place(
        self, world: World, btype: BuildingType, coord: HexCoord,
    ) -> bool:
        if self.colony.building_inventory[btype] < 1:
            return False
        tile = world.grid.get(coord)
        if tile is None or tile.building is not None:
            return False
        self.colony.building_inventory.spend(btype)
        b = world.buildings.place(btype, coord)
        b.faction = self.faction_id
        tile.building = b
        self._configure_new_building(world, b)
        world.mark_networks_dirty()
        world.mark_housing_dirty()
        self._invalidate_snapshot()
        self._builds_placed += 1
        return True

    def _configure_new_building(self, world: World, b) -> None:
        """Pick a sensible default output for a newly-placed
        producer / storage so it actually does something."""
        from compprog_pygame.games.hex_colony.procgen import Terrain
        if b.type == BuildingType.QUARRY:
            has_iron, has_copper, has_stone = False, False, False
            for nb in b.coord.neighbors():
                tile = world.grid.get(nb)
                if tile is None:
                    continue
                if tile.terrain == Terrain.IRON_VEIN:
                    has_iron = True
                elif tile.terrain == Terrain.COPPER_VEIN:
                    has_copper = True
                elif tile.terrain in (Terrain.STONE_DEPOSIT,
                                      Terrain.MOUNTAIN):
                    has_stone = True
            need_iron = self._stock(world, Resource.IRON) < 25
            need_copper = self._stock(world, Resource.COPPER) < 25
            if has_iron and (need_iron or not has_stone):
                b.quarry_output = Resource.IRON
            elif has_copper and (need_copper or not has_stone):
                b.quarry_output = Resource.COPPER
        elif b.type == BuildingType.GATHERER:
            food = self._stock(world, Resource.FOOD)
            fiber = self._stock(world, Resource.FIBER)
            b.gatherer_output = (
                Resource.FOOD if food < fiber + 20 else Resource.FIBER
            )
        elif b.type == BuildingType.MINING_MACHINE:
            for nb in b.coord.neighbors():
                tile = world.grid.get(nb)
                if tile is None:
                    continue
                if tile.terrain == Terrain.IRON_VEIN:
                    b.quarry_output = Resource.IRON
                    break
                if tile.terrain == Terrain.COPPER_VEIN:
                    b.quarry_output = Resource.COPPER
                    break
        elif b.type == BuildingType.STORAGE:
            best_res = Resource.WOOD
            best_amt = -1.0
            for r in Resource:
                amt = self._stock(world, r)
                if amt > best_amt:
                    best_amt = amt
                    best_res = r
            b.stored_resource = best_res

    def _demolish(self, world: World, building) -> None:
        """Tear down one of our buildings and refund the blueprint."""
        from compprog_pygame.games.hex_colony.people import Task
        coord = building.coord
        btype = building.type
        tile = world.grid.get(coord)
        if tile is None or tile.building is not building:
            return
        for person in world.population.people:
            if person.workplace is building:
                person.workplace = None
                person.carry_resource = None
                person.target_hex = None
                person.task = Task.IDLE
                person.path = []
                building.workers = max(0, building.workers - 1)
            if person.home is building:
                person.home = None
        self.colony.building_inventory.add(building.type)
        world.buildings.remove(building)
        tile.building = None
        world.mark_networks_dirty()
        world.mark_housing_dirty()
        self._invalidate_snapshot()
        # Cooldown so we don't stamp the same coord next tick.
        now = world.time_elapsed
        self._blocked_targets[(btype.name, coord.q, coord.r)] = now

    # â”€â”€ Audit â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def _audit_buildings(self, world: World) -> None:
        """Demolish producers stuck on bad / depleted terrain.

        FARM and WELL are excluded â€” FARM grows food anywhere, WELL
        sits on water indefinitely.
        """
        _NON_DEPLETING: frozenset[BuildingType] = frozenset({
            BuildingType.FARM, BuildingType.WELL,
        })
        for b in list(self._snapshot(world).my_buildings):
            target_terrain = _terrain_for(b.type)
            if target_terrain is None:
                continue  # not a terrain-affinity building
            tile = world.grid.get(b.coord)
            on_target = (
                tile is not None and tile.terrain in target_terrain
            )
            count = 0
            for nb in b.coord.neighbors():
                nb_tile = world.grid.get(nb)
                if nb_tile is None:
                    continue
                if nb_tile.terrain not in target_terrain:
                    continue
                if (nb_tile.building is not None
                        and nb_tile.building is not b):
                    continue
                count += 1
            if count == 0 and not on_target:
                self._log(
                    world,
                    f"Demolishing {b.type.name} at "
                    f"({b.coord.q},{b.coord.r}) â€” no usable "
                    "terrain nearby.",
                )
                self._demolish(world, b)
                continue
            # Depletion check â€” only for actual extractors.
            if b.type in _NON_DEPLETING:
                continue
            if not getattr(b, "active", False) and b.workers > 0:
                from compprog_pygame.games.hex_colony.supply_chain import (
                    _hex_range,
                )
                from compprog_pygame.games.hex_colony import params as _p
                radius = getattr(_p, "COLLECTION_RADIUS", 1)
                any_left = False
                for nb in _hex_range(b.coord, radius):
                    if nb == b.coord:
                        continue
                    nb_tile = world.grid.get(nb)
                    if nb_tile is None:
                        continue
                    if nb_tile.building is not None:
                        continue
                    if nb_tile.terrain not in target_terrain:
                        continue
                    if (nb_tile.resource_amount > 0
                            or nb_tile.food_amount > 0):
                        any_left = True
                        break
                if not any_left:
                    self._log(
                        world,
                        f"Demolishing {b.type.name} at "
                        f"({b.coord.q},{b.coord.r}) â€” local "
                        "resources depleted.",
                    )
                    self._demolish(world, b)

    # â”€â”€ Research â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def _try_start_research(self, world: World) -> None:
        tt = self.colony.tech_tree
        if tt.current_research is not None:
            return
        if not self._has_building(world, BuildingType.RESEARCH_CENTER):
            return
        candidates = tt.available_techs()
        if not candidates:
            return

        def score(key: str) -> float:
            node = TECH_NODES[key]
            unlocks = list(getattr(node, "unlocks", []) or [])
            unlock_resources = list(
                getattr(node, "unlock_resources", []) or []
            )
            bld_bonus = 0.0
            for entry in unlocks:
                if isinstance(entry, BuildingType):
                    bt = entry
                else:
                    try:
                        bt = BuildingType[entry]
                    except KeyError:
                        continue
                if not self._has_building(world, bt):
                    bld_bonus += 30.0
                else:
                    bld_bonus += 5.0
            res_bonus = 8.0 * len(unlock_resources)
            cost = getattr(node, "cost", {}) or {}
            shortfall = 0.0
            for res_key, amt in cost.items():
                try:
                    rname = (
                        res_key.name if hasattr(res_key, "name")
                        else str(res_key)
                    )
                    res = Resource[rname]
                except KeyError:
                    continue
                have = self._stock(world, res)
                if have < amt:
                    shortfall += (amt - have)
            return (
                bld_bonus + res_bonus
                - shortfall * 0.05
                - sum(cost.values()) / 200.0
                + self.rng.random() * 0.5
            )

        candidates.sort(key=score, reverse=True)
        choice = candidates[0]
        if not tt.can_research(choice):
            return
        tt.start_research(choice)
        self._research_started += 1
        node = TECH_NODES[choice]
        self._log(world, f"Researching {node.name}.")

    # â”€â”€ Recipe scheduling â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def _set_recipes(self, world: World) -> None:
        """Assign a recipe to each idle crafting station.

        Strategy: each station crafts whichever wishlist building
        belongs to it (so workshops top up blueprints we want to
        place), or â€” for material recipes â€” whichever output the
        colony is most short on relative to a flat target.
        """
        from compprog_pygame.games.hex_colony.params import (
            BUILDING_RECIPE_STATION,
        )
        from compprog_pygame.games.hex_colony.resources import (
            MATERIAL_RECIPES, recipes_for_station,
        )

        wl = self._wishlist(world)
        # Materials we want a healthy stockpile of.
        STOCK_TARGET = 30.0
        STATION_PROD_CAP = 200.0  # don't craft more than this
        now = world.time_elapsed

        def material_unlocked(res: Resource) -> bool:
            try:
                from compprog_pygame.games.hex_colony.tech_tree import (
                    is_resource_available,
                )
                return is_resource_available(
                    res,
                    self.colony.tech_tree,
                    self.colony.tier_tracker,
                )
            except Exception:
                return True

        for b in self._snapshot(world).my_buildings:
            station_name = b.type.name
            # Skip non-crafting buildings.  Crafting stations are
            # those that appear as a recipe station in
            # BUILDING_RECIPE_STATION values OR in MATERIAL_RECIPES.
            try:
                first_recipe = next(iter(recipes_for_station(station_name)))
            except StopIteration:
                first_recipe = None
            station_buildings = [
                bt for bt, st in BUILDING_RECIPE_STATION.items()
                if st == station_name
            ]
            if first_recipe is None and not station_buildings:
                continue

            coord_key = (b.coord.q, b.coord.r)

            # Re-evaluate existing recipe â€” but enforce sticky window.
            if b.recipe is not None:
                set_at = self._recipe_set_at.get(coord_key)
                age = (now - set_at) if set_at is not None else 1e9
                if age < _RECIPE_STICKY_TIME:
                    continue
                progress = float(getattr(b, "craft_progress", 0.0))
                # Stale recipe with no progress â†’ clear.
                if age >= _RECIPE_STALE_TIME and progress <= 0.0:
                    self._log(
                        world,
                        f"Clearing stale {b.type.name} recipe "
                        f"({getattr(b.recipe, 'name', str(b.recipe))})"
                        f" â€” no progress in {int(age)}s.",
                    )
                    b.recipe = None
                    self._recipe_set_at.pop(coord_key, None)
                    self._recipes_cleared += 1
                # If output is full and we have plenty of the
                # resource, clear so the station can switch.
                elif isinstance(b.recipe, Resource):
                    out_held = b.storage.get(b.recipe, 0.0)
                    out_full = (
                        b.storage_capacity > 0
                        and out_held >= b.storage_capacity * 0.95
                    )
                    if out_full and self._stock(world, b.recipe) >= STOCK_TARGET * 2:
                        b.recipe = None
                        self._recipe_set_at.pop(coord_key, None)
                        self._recipes_cleared += 1
                elif isinstance(b.recipe, BuildingType):
                    if self.colony.building_inventory[b.recipe] >= 4:
                        b.recipe = None
                        self._recipe_set_at.pop(coord_key, None)
                        self._recipes_cleared += 1
                if b.recipe is not None:
                    continue

            # Pick a new recipe.
            chosen: BuildingType | Resource | None = None

            # 1. A wishlist building this station can craft.  Only
            #    pick recipes whose inputs we can fully source right
            #    now â€” a partial pick locks the workshop on an
            #    impossible recipe (e.g. HABITAT needs IRON_BAR at
            #    tier 0) and stalls the colony permanently.
            for bt in wl:
                if BUILDING_RECIPE_STATION.get(bt.name) != station_name:
                    continue
                if bt not in BUILDING_COSTS:
                    continue
                if self.colony.building_inventory[bt] >= 4:
                    continue
                cost = BUILDING_COSTS[bt]
                if all(self._stock(world, r) >= a
                       for r, a in cost.costs.items()):
                    chosen = bt
                    break

            # 2. A material recipe that is short relative to target
            #    AND whose inputs the colony has at least some stock
            #    of (or a producer for).
            if chosen is None:
                best_short = 0.0
                best_mat: Resource | None = None
                for mr in recipes_for_station(station_name):
                    if not material_unlocked(mr.output):
                        continue
                    have = self._stock(world, mr.output)
                    if have >= STATION_PROD_CAP:
                        continue
                    short = max(0.0, STOCK_TARGET - have)
                    if short <= 0:
                        continue
                    # Skip impossible recipes â€” no input stock and
                    # no producer for at least one input.
                    impossible = False
                    for in_res in mr.inputs:
                        if self._stock(world, in_res) >= 0.5:
                            continue
                        producers = _PRODUCER_FOR.get(in_res, ())
                        if any(self._has_building(world, bt)
                               for bt in producers):
                            continue
                        in_mrec = MATERIAL_RECIPES.get(in_res)
                        if in_mrec is not None:
                            try:
                                if self._has_building(
                                    world,
                                    BuildingType[in_mrec.station],
                                ):
                                    continue
                            except (KeyError, AttributeError):
                                pass
                        impossible = True
                        break
                    if impossible:
                        continue
                    if short > best_short:
                        best_short = short
                        best_mat = mr.output
                if best_mat is not None:
                    chosen = best_mat

            if chosen is None:
                continue
            b.recipe = chosen
            self._recipe_set_at[coord_key] = now
            self._recipes_set += 1
            label = (
                chosen.name if isinstance(chosen, BuildingType)
                else f"material {chosen.name.lower()}"
            )
            self._log(
                world,
                f"Set {station_name} recipe to {label}.",
            )

    # â”€â”€ Worker priorities â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def _rebalance_worker_priorities(self, world: World) -> None:
        """Pin each network's worker priority so producers /
        crafting stations get staffed before housing and research.

        Promote RESEARCH_CENTER when we still have tech to research
        and no active research is starving us â€” otherwise it can sit
        idle forever in a staffing-bound colony.
        """
        fid = self.faction_id
        tt = getattr(self.colony, "tech_tree", None)
        food_low = self._stock(world, Resource.FOOD) < 25.0
        farm_unlocked = self._is_unlocked(BuildingType.FARM)
        promote_research = (
            tt is not None
            and getattr(tt, "current_research", None) is not None
            and self._has_building(world, BuildingType.RESEARCH_CENTER)
            and (not food_low or farm_unlocked)
        )
        if promote_research:
            high_set = _HIGH_PRIORITY_WORK_TYPES | {
                BuildingType.RESEARCH_CENTER,
            }
            low_set = _LOW_PRIORITY_WORK_TYPES - {
                BuildingType.RESEARCH_CENTER,
            }
        else:
            high_set = _HIGH_PRIORITY_WORK_TYPES
            low_set = _LOW_PRIORITY_WORK_TYPES

        changed_any = False
        for net in world.networks:
            if net.faction != fid:
                continue
            high: list = []
            mid: list = []
            low: list = []
            countable = 0
            for b in net.buildings:
                if BUILDING_MAX_WORKERS.get(b.type, 0) <= 0:
                    continue
                if b.type in high_set:
                    high.append(b)
                elif b.type in low_set:
                    low.append(b)
                else:
                    mid.append(b)
                if b.type not in (
                    BuildingType.PATH, BuildingType.BRIDGE,
                    BuildingType.WALL,
                ):
                    countable += 1
            if not (high or mid or low):
                continue
            new_tiers: list[list] = []
            if high:
                new_tiers.append(high)
            if mid:
                new_tiers.append(mid)
            if low:
                new_tiers.append(low)
            same = (
                not net.worker_auto
                and len(net.priority) == len(new_tiers)
                and all(
                    {id(b) for b in cur} == {id(b) for b in want}
                    for cur, want in zip(net.priority, new_tiers)
                )
            )
            if same:
                continue
            net.worker_auto = False
            net.priority = new_tiers
            net.logistics_target = (
                max(1, countable // 4) if countable else 0
            )
            changed_any = True
            self._priorities_set += 1
        if changed_any:
            world._workers_dirty = True


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
#  Manager
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

class ClankerManager:
    """Owns every :class:`Clanker` for a Hard-mode world.

    Constructs one ``Clanker`` per coordinate in
    ``world.ai_camp_coords`` and ticks them all every world update.
    Easy-mode worlds simply create an empty manager (zero overhead).
    """

    def __init__(self, world: World) -> None:
        self.world = world
        self.clankers: list[Clanker] = []
        for i, coord in enumerate(world.ai_camp_coords):
            faction_id = f"PRIMITIVE_{i}"
            home = self._locate_camp(faction_id, coord)
            colony = world.colonies.get(faction_id)
            if colony is None:
                continue
            self.clankers.append(Clanker(
                faction_id=faction_id,
                home=home,
                colony=colony,
                rng=_rng_for(world.seed, faction_id),
            ))

    def _locate_camp(
        self, faction_id: str, fallback: HexCoord,
    ) -> HexCoord:
        for b in self.world.buildings.by_type(BuildingType.TRIBAL_CAMP):
            if b.faction == faction_id:
                return b.coord
        return fallback

    def update(self, dt: float) -> None:
        for c in self.clankers:
            c.update(self.world, dt)
