"""Clanker AI — autonomous rival colonies for Hex Colony's Hard mode.

A *clanker* is the AI counterpart to the player.  One clanker is
spawned per AI tribal camp at world-gen time.  Each clanker plays the
game using the **same simulation systems as the player**:

* It owns a :class:`ColonyState` (``world.colonies[faction_id]``) with
  its own inventory, building inventory, tech tree, and tier tracker.
* It places real :class:`Building` objects on the map, tagged with
  its faction id.  Once placed, those buildings produce, consume,
  craft, research, and grow population entirely through the
  faction-aware ``World.update`` path — exactly the same code that
  drives the player's colony.
* The AI's only job is therefore *decision making*: where to expand,
  what to build next, what to research, and what recipes to set on
  its workshops.

Determinism: every random choice is drawn from a per-faction RNG
seeded from ``(world.seed, faction_id)``.
"""

from __future__ import annotations

import hashlib
import random
from collections import deque
from dataclasses import dataclass, field

from compprog_pygame.games.hex_colony.buildings import (
    BUILDING_COSTS,
    BUILDING_HOUSING,
    BUILDING_MAX_WORKERS,
    BuildingType,
)

# Buildings that don't draw from the workforce pool — placing them
# never makes the staffing situation worse.
_NON_WORKER_BTYPES: frozenset[BuildingType] = frozenset({
    BuildingType.PATH, BuildingType.BRIDGE, BuildingType.WALL,
    BuildingType.PIPE, BuildingType.CONVEYOR,
    BuildingType.HABITAT, BuildingType.HOUSE, BuildingType.STORAGE,
})

# We only allow placing a new worker-requiring building if the
# colony has at least this many idle workers to spare beyond its
# current job slots.  Keeps the AI from front-loading every
# workshop in the world before anyone moves in.
_STAFFING_HEADROOM: int = 1
from compprog_pygame.games.hex_colony.colony import ColonyState
from compprog_pygame.games.hex_colony.hex_grid import HexCoord
from compprog_pygame.games.hex_colony.procgen import UNBUILDABLE
from compprog_pygame.games.hex_colony.resources import Resource
from compprog_pygame.games.hex_colony.tech_tree import TECH_NODES
from compprog_pygame.games.hex_colony.world import World


# ── Tunables ─────────────────────────────────────────────────────
# Sim-seconds between successive build attempts per clanker.
_BUILD_INTERVAL: float = 4.0
# Sim-seconds between research-pick attempts.
_RESEARCH_INTERVAL: float = 6.0
# Sim-seconds between workshop-recipe-pick attempts.
_RECIPE_INTERVAL: float = 8.0
# Minimum sim-seconds a recipe must stay set before the AI is allowed
# to change it again.  Prevents thrashing where a station's recipe
# flips every 8 s based on shifting demand and never makes progress.
_RECIPE_STICKY_TIME: float = 60.0
# Sim-seconds between building audits (demolish misplaced buildings).
_AUDIT_INTERVAL: float = 15.0
# Sim-seconds a (btype, target) combo stays blacklisted after the AI
# fails to place there (e.g. across an unbridgeable river).  Without
# this, the planner re-picks the same unreachable hex every build
# tick and spams thousands of identical "no reachable spot worked"
# log lines.  See clanker_monitor logs from 4/21/2026.
_BLOCKED_TARGET_COOLDOWN: float = 240.0
# Hard ceiling on how long a recipe may sit on a station before the
# AI is allowed to re-evaluate, regardless of demand state.  Catches
# the "workshop locked on PLANKS for 7000 s with progress=0" bug
# where output is jammed and the sticky window keeps re-confirming
# the wrong recipe.
_RECIPE_HARD_CEILING: float = 600.0
# Soft ceiling for *materially-impossible* recipes — when a recipe's
# inputs are nowhere in the colony AND the colony has no producer
# for them, clear after this many seconds rather than waiting for
# the hard ceiling.  Was the "FORGE locked on COPPER_BAR for 580 s
# with no copper anywhere" symptom in the 4/21 log.
_RECIPE_IMPOSSIBLE_CEILING: float = 90.0
# Sim-seconds between heartbeat "idle" log entries when _try_build
# finds nothing actionable for a long time (otherwise the player
# sees a clanker fall silent for hours).
_IDLE_HEARTBEAT_INTERVAL: float = 90.0
# After this many seconds idle, the AI starts forcing speculative
# work (e.g. extra HABITAT) to break out of the staffing/pop
# deadlock — "1 HABITAT, pop 11/16, 12 jobs" stalled forever in
# the 4/21 log because no priority condition could trigger.
_IDLE_FORCE_INTERVAL: float = 180.0

# Soft cap on how many non-path buildings a clanker may own.
_MAX_BUILDINGS_PER_CLANKER: int = 80
# Maximum hex distance a clanker will expand from its tribal camp.
# We deliberately keep this very large — the AI can see the whole
# map, just like a player who pans the camera around.  Placement
# scoring still prefers nearby sites so colonies stay coherent.
_MAX_EXPANSION_RADIUS: int = 64
# Maximum entries kept in a clanker's decision log.
_LOG_MAXLEN: int = 60
# Maximum length of a path chain the AI will lay to reach a remote
# resource hex.  Generous so the AI can run out to a distant ore
# vein or fiber patch when the easy spots are already used up.
_MAX_PATH_RUN: int = 24

# Buildings the AI can directly place from its inventory.
_PLACEABLE: tuple[BuildingType, ...] = (
    BuildingType.PATH, BuildingType.BRIDGE,
    BuildingType.HABITAT,
    BuildingType.WOODCUTTER, BuildingType.QUARRY, BuildingType.GATHERER,
    BuildingType.FARM, BuildingType.WELL,
    BuildingType.STORAGE,
    BuildingType.WORKSHOP, BuildingType.FORGE,
    BuildingType.REFINERY, BuildingType.MINING_MACHINE,
    BuildingType.RESEARCH_CENTER,
    BuildingType.CHEMICAL_PLANT, BuildingType.ASSEMBLER,
    BuildingType.OIL_DRILL, BuildingType.OIL_REFINERY,
    BuildingType.SOLAR_ARRAY, BuildingType.ROCKET_SILO,
)

# Lazily-built terrain-affinity map (avoids module-load circularity).
_TERRAIN_FOR: dict[BuildingType, set] = {}


def _terrain_for(btype: BuildingType) -> set | None:
    """Terrains *btype* benefits from being adjacent to."""
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
            BuildingType.FARM: {Terrain.WATER, Terrain.GRASS},
            BuildingType.WELL: {Terrain.WATER},
            BuildingType.MINING_MACHINE: {
                Terrain.IRON_VEIN, Terrain.COPPER_VEIN,
                Terrain.STONE_DEPOSIT, Terrain.MOUNTAIN,
            },
            BuildingType.OIL_DRILL: {Terrain.OIL_DEPOSIT},
        }
    return _TERRAIN_FOR.get(btype)


def _rng_for(world_seed: str, faction_id: str) -> random.Random:
    """Deterministic RNG seeded from world seed + faction id."""
    h = hashlib.sha256(
        f"{world_seed}:{faction_id}".encode("utf-8"),
    ).hexdigest()
    return random.Random(int(h, 16))


_TECH_DEPTH_CACHE: dict[str, int] = {}


def _tech_depth(key: str) -> int:
    """Length of the longest prerequisite chain ending at *key*.

    Memoised across calls.  Roots (no prereqs) return 0.  Used by the
    AI's research scorer to bias toward foundational nodes — players
    naturally do early-tier research first because the deeper nodes
    are visually further out, and we want clankers to feel similar.
    """
    cached = _TECH_DEPTH_CACHE.get(key)
    if cached is not None:
        return cached
    node = TECH_NODES.get(key)
    if node is None or not node.prerequisites:
        _TECH_DEPTH_CACHE[key] = 0
        return 0
    depth = 1 + max(_tech_depth(p) for p in node.prerequisites)
    _TECH_DEPTH_CACHE[key] = depth
    return depth


# ── Goal-chain planner tables ────────────────────────────────────
#
# For each raw resource, what placeable building(s) can produce it,
# and what attribute configuration (if any) must be set on that
# building?  Used by :meth:`Clanker._goal_chain` to back-chain from
# a high-level goal (e.g., "build HABITAT") all the way to "need a
# QUARRY configured for IRON" or "need a MINING_MACHINE near an
# IRON_VEIN", so the AI can reason about missing infrastructure
# rather than only missing materials.
#
# Each producer is ``(building_type, required_output_resource_or_None)``.
# ``None`` means the default/auto output (e.g., QUARRY with no
# ``quarry_output`` mines STONE; GATHERER's default is FOOD when
# ``gatherer_output`` is unset, but we still mark it explicitly).
_RAW_PRODUCERS: dict[
    "Resource",
    tuple[tuple[BuildingType, "Resource | None"], ...],
] = {}


def _build_raw_producers() -> None:
    """Lazily populated on first call to ``_goal_chain`` — done this
    way so the module can stay cheap to import (Resource enum is
    already imported, but we centralise the table construction).
    """
    if _RAW_PRODUCERS:
        return
    _RAW_PRODUCERS.update({
        Resource.WOOD: ((BuildingType.WOODCUTTER, None),),
        Resource.FIBER: ((BuildingType.GATHERER, Resource.FIBER),),
        Resource.STONE: ((BuildingType.QUARRY, None),),
        Resource.FOOD: (
            (BuildingType.FARM, None),
            (BuildingType.GATHERER, Resource.FOOD),
        ),
        Resource.IRON: (
            (BuildingType.MINING_MACHINE, None),
            (BuildingType.QUARRY, Resource.IRON),
        ),
        Resource.COPPER: (
            (BuildingType.MINING_MACHINE, None),
            (BuildingType.QUARRY, Resource.COPPER),
        ),
        Resource.OIL: ((BuildingType.OIL_DRILL, None),),
    })



@dataclass
class _Snapshot:
    """Per-tick cache of this clanker's view of the world.

    Rebuilding is O(N_buildings) but happens at most once per AI
    tick instead of being repeated inside every helper call.  The
    snapshot is invalidated after any mutation by the clanker
    (``_place`` / ``_demolish`` / ``_lay_path_to``).
    """
    my_buildings: list = field(default_factory=list)
    by_type: dict = field(default_factory=dict)
    owned_coords: list = field(default_factory=list)
    owned_coord_set: set = field(default_factory=set)
    camp: object | None = None


@dataclass
class Clanker:
    """A single AI rival colony — see module docstring."""
    faction_id: str
    home: HexCoord
    colony: ColonyState
    rng: random.Random
    build_timer: float = 0.0
    research_timer: float = 0.0
    recipe_timer: float = 0.0
    audit_timer: float = 0.0
    _owned_cache: list[HexCoord] = field(default_factory=list)
    _was_staffing_bound: bool = False
    # Per-station sim-time when its recipe was last set/changed by
    # this clanker, keyed by ``(q, r)``.  Used to enforce
    # :data:`_RECIPE_STICKY_TIME` so stations don't oscillate.
    _recipe_set_at: dict[tuple[int, int], float] = field(
        default_factory=dict,
    )
    # Sim-time at which each (btype_name, q, r) combo was last
    # blacklisted by :meth:`_try_build` after exhausting candidates.
    # Entries older than :data:`_BLOCKED_TARGET_COOLDOWN` are pruned
    # lazily.  Keyed by ``(BuildingType.name, q, r)`` so blacklisting
    # a specific target tile doesn't leak into other building types.
    _blocked_targets: dict[tuple[str, int, int], float] = field(
        default_factory=dict,
    )
    # Sim-time of the last "idle / nothing to do" heartbeat log so
    # we don't repeat it every build tick when the AI is stalled.
    _last_idle_log: float = -1e9
    # Sim-time when the AI first started reporting "nothing to
    # place" in an unbroken streak.  Reset whenever a placement
    # actually succeeds.  Used by the idle-rescue logic to force a
    # speculative HABITAT once :data:`_IDLE_FORCE_INTERVAL` passes.
    _idle_streak_start: float = -1.0
    # Per-tick BFS visited cache: {(btype_name): {coord: dist}}.
    # Reset every :meth:`update` because the snapshot is reset.
    # Avoids repeating the multi-source BFS (~1900 hex visits) for
    # every building priority that calls _find_placement.
    _visited_cache: dict[str, dict] = field(default_factory=dict)
    # Per-tick stockpile cache: {Resource: float}.  _stock() walks
    # every owned building's storage; for big colonies this gets
    # called dozens of times per tick from the goal-chain walker.
    _stock_cache: dict = field(default_factory=dict)
    # Per-clanker tick wall-clock so the perf monitor can spot
    # which clanker is the slow one.
    last_tick_ms: float = 0.0
    # Populated by :meth:`_pick_building_to_place` each build tick
    # and consumed by :meth:`_set_recipes` so the recipe scheduler
    # can weight the current goal's dependency chain above ambient
    # top-up demand.  Resets to empty when no goal is active.
    _goal_demand: dict[Resource, float] = field(default_factory=dict)
    # Recent decisions, surfaced via the player's "Possess" panel so
    # the player can see *why* the AI is doing what it does.  Stored
    # as ``(sim_time, message)`` tuples, capped to the most recent
    # ``_LOG_MAXLEN`` entries.
    log: deque[tuple[float, str]] = field(
        default_factory=lambda: deque(maxlen=_LOG_MAXLEN),
    )
    # Per-tick cache of this clanker's view of the world buildings.
    # ``None`` means "rebuild on next access".  Invalidated by
    # ``_place`` / ``_demolish`` / ``_lay_path_to``.
    _snap: _Snapshot | None = None

    # ── Logging ──────────────────────────────────────────────────

    def _log(self, world: World, msg: str) -> None:
        """Record a one-line justification for the player to read.

        Dedupes consecutive identical messages within a 30 s window
        so a stuck loop doesn't drown the log (and the
        ``hex_colony_clankers.jsonl`` monitor) in copies of the same
        line.  Distinct messages always append.
        """
        now = world.time_elapsed
        if self.log:
            last_t, last_msg = self.log[-1]
            if last_msg == msg and (now - last_t) < 30.0:
                return
        self.log.append((now, msg))

    # ── Per-tick snapshot ────────────────────────────────────────

    def _snapshot(self, world: World) -> _Snapshot:
        """Return a cached snapshot of this faction's buildings.

        Rebuilds on first access after invalidation.  All the hot
        decision helpers (``_has_building``, ``_count_building``,
        ``_count_producer_matching``, ``_owned_coords``, etc.) read
        from the snapshot instead of iterating
        ``world.buildings.buildings`` each call — huge win with
        many clankers and many buildings.
        """
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
        camp = world.buildings.at(self.home)
        snap = _Snapshot(
            my_buildings=my,
            by_type=by_type,
            owned_coords=coords,
            owned_coord_set=coord_set,
            camp=camp,
        )
        self._snap = snap
        return snap

    def _invalidate_snapshot(self) -> None:
        self._snap = None

    # ── Top-level update ─────────────────────────────────────────

    def update(self, world: World, dt: float) -> None:
        import time as _time
        _t0 = _time.perf_counter()
        self.build_timer += dt
        self.research_timer += dt
        self.recipe_timer += dt
        self.audit_timer += dt
        # Invalidate the snapshot at the top of each tick so it is
        # rebuilt lazily on first use and reflects the current world
        # state (other clankers / the player may have placed or
        # removed buildings since our last tick).
        self._invalidate_snapshot()
        # Per-tick caches are also stale now.
        if self._visited_cache:
            self._visited_cache.clear()
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
            self._reconfigure_producers(world)
            self._set_recipes(world)
        self.last_tick_ms = (_time.perf_counter() - _t0) * 1000.0

    # ── Helpers ──────────────────────────────────────────────────

    def _owned_coords(self, world: World) -> list[HexCoord]:
        """All coords currently occupied by this faction's buildings."""
        coords = self._snapshot(world).owned_coords
        self._owned_cache = coords
        return coords

    def _is_unlocked(self, btype: BuildingType) -> bool:
        return (
            self.colony.tech_tree.is_building_unlocked(btype)
            and self.colony.tier_tracker.is_building_unlocked(btype)
        )

    def _can_pay_for(self, btype: BuildingType) -> bool:
        """Direct placement requires a stockpiled building of this
        type.  Crafting raw resources into more buildings is the
        WORKSHOP / FORGE's job (handled in :meth:`_set_recipes`)."""
        return self.colony.building_inventory[btype] > 0

    def _has_building(self, world: World, btype: BuildingType) -> bool:
        return bool(self._snapshot(world).by_type.get(btype))

    def _count_building(self, world: World, btype: BuildingType) -> int:
        lst = self._snapshot(world).by_type.get(btype)
        return len(lst) if lst else 0

    def _has_input_supply(
        self, world: World, btype: BuildingType,
    ) -> bool:
        """Does the colony have a realistic source for *btype*'s
        typical inputs?  Used to gate placement of crafting stations
        that otherwise end up with no materials to work on \u2014 e.g.
        FORGEs built before any IRON-mining QUARRY exists just sit
        idle trying to smelt iron bars with zero iron on hand.

        Conservative: WORKSHOP is never gated (it accepts wood/stone
        which any colony has).  For stations that consume specific
        intermediates we require at least one producer of a relevant
        raw material *or* enough pre-existing stock to bootstrap.
        """
        # WORKSHOP / research buildings don't need gating.
        if btype in (
            BuildingType.WORKSHOP, BuildingType.RESEARCH_CENTER,
            BuildingType.STORAGE, BuildingType.HABITAT,
            BuildingType.WELL, BuildingType.FARM,
            BuildingType.GATHERER, BuildingType.WOODCUTTER,
            BuildingType.QUARRY, BuildingType.MINING_MACHINE,
            BuildingType.OIL_DRILL,
        ):
            return True

        def _have_producer(res: Resource) -> bool:
            return (
                self._count_producer_matching(world, res) > 0
                or self._stock(world, res) >= 10.0
            )

        if btype == BuildingType.FORGE:
            # Needs some metal ore \u2014 iron or copper \u2014 available.
            return (
                _have_producer(Resource.IRON)
                or _have_producer(Resource.COPPER)
            )
        if btype in (
            BuildingType.REFINERY, BuildingType.ASSEMBLER,
        ):
            # Refineries and assemblers need metal bars, which in
            # turn need a forge plus metal ore.
            return (
                self._count_building(world, BuildingType.FORGE) > 0
                and (
                    _have_producer(Resource.IRON)
                    or _have_producer(Resource.COPPER)
                )
            )
        if btype in (
            BuildingType.CHEMICAL_PLANT, BuildingType.OIL_REFINERY,
        ):
            return _have_producer(Resource.OIL)
        return True

    def _count_producer_matching(
        self, world: World, res: Resource,
    ) -> int:
        """Count buildings belonging to this faction currently set to
        produce *res* (via quarry_output / gatherer_output / default).
        Mirrors the closure inside :meth:`_goal_chain` but exposed as
        a method so :meth:`_has_input_supply` can reuse it.
        """
        _build_raw_producers()
        snap = self._snapshot(world)
        n = 0
        for btype, required_output in _RAW_PRODUCERS.get(res, ()):
            for b in snap.by_type.get(btype, ()):
                if btype == BuildingType.QUARRY:
                    if getattr(b, "quarry_output", None) == required_output:
                        n += 1
                elif btype == BuildingType.GATHERER:
                    cur = (getattr(b, "gatherer_output", None)
                           or Resource.FOOD)
                    want = required_output or Resource.FOOD
                    if cur == want:
                        n += 1
                else:
                    n += 1
        return n

    def _has_source_for(
        self, world: World, res: Resource,
    ) -> bool:
        """True if the colony can currently source *res*: either a
        producer building matching it exists, or the stockpile is
        non-trivial.  Used by :meth:`_collect_chain_goals` to decide
        whether a recipe / research / mining input is already covered
        by the logistics network or needs a new production chain.
        """
        from compprog_pygame.games.hex_colony.resources import (
            RAW_RESOURCES, MATERIAL_RECIPES,
        )
        if self._stock(world, res) >= 5.0:
            return True
        if res in RAW_RESOURCES:
            return self._count_producer_matching(world, res) > 0
        # Intermediate: a producer is any building currently set to
        # craft this recipe.
        if res not in MATERIAL_RECIPES:
            return False
        for b in self._snapshot(world).my_buildings:
            if getattr(b, "recipe", None) == res:
                return True
        return False

    def _staffing_state(
        self, world: World,
    ) -> tuple[int, int, int, int]:
        """Return ``(my_pop, housing_cap, worker_demand, workers_assigned)``
        for this faction.

        * ``my_pop`` — people belonging to this colony (have a faction
          home building).
        * ``housing_cap`` — total housing capacity of our buildings.
        * ``worker_demand`` — sum of ``BUILDING_MAX_WORKERS`` for every
          worker-requiring building we own (excluding pure infra and
          housing).
        * ``workers_assigned`` — sum of ``b.workers`` for those same
          buildings, i.e. how many job slots are actually filled.
        """
        snap = self._snapshot(world)
        my_buildings_ids = {id(b) for b in snap.my_buildings}
        my_pop = 0
        for p in world.population.people:
            home = p.home
            if home is not None and id(home) in my_buildings_ids:
                my_pop += 1
        housing_cap = 0
        worker_demand = 0
        workers_assigned = 0
        for b in snap.my_buildings:
            housing_cap += BUILDING_HOUSING.get(b.type, 0)
            if b.type in _NON_WORKER_BTYPES:
                continue
            worker_demand += BUILDING_MAX_WORKERS.get(b.type, 0)
            workers_assigned += getattr(b, "workers", 0)
        return my_pop, housing_cap, worker_demand, workers_assigned

    # ── Long-term goal reasoning ─────────────────────────────────

    def _pick_goal_building(
        self, world: World, my_pop: int, my_cap: int,
        worker_demand: int,
    ) -> BuildingType | None:
        """Pick the single highest-priority building the colony
        really wants *right now*, independent of whether we have
        one pre-crafted.

        This is the root of the goal chain.  :meth:`_goal_chain`
        back-chains from this to figure out which stations, raw
        producers, and materials need to exist so the colony can
        actually deliver the goal (rather than giving up the moment
        ``_can_pay_for`` fails and silently doing nothing).
        """
        # Housing pressure mirrors the logic in
        # :meth:`_pick_building_to_place` so the goal chain and the
        # immediate placement priority stay aligned.
        if self._is_unlocked(BuildingType.HABITAT):
            housing_pressure = (
                my_pop >= my_cap - 1
                or (worker_demand > my_pop and my_cap <= my_pop)
            )
            if housing_pressure:
                return BuildingType.HABITAT

        # Need a research centre to make progress through the tree.
        if (self._is_unlocked(BuildingType.RESEARCH_CENTER)
                and not self._has_building(
                    world, BuildingType.RESEARCH_CENTER)):
            return BuildingType.RESEARCH_CENTER

        # Food security.
        if (self._stock(world, Resource.FOOD) < 30
                and self._is_unlocked(BuildingType.FARM)):
            return BuildingType.FARM

        # Missing any basic crafting station is a goal in itself.
        for btype in (
            BuildingType.WORKSHOP, BuildingType.FORGE,
            BuildingType.REFINERY, BuildingType.ASSEMBLER,
        ):
            if (self._is_unlocked(btype)
                    and not self._has_building(world, btype)):
                return btype

        # Otherwise, chase tier goals: the tier-up resource shopping
        # list, expressed as "build whichever producer unlocks the
        # most-short resource."
        try:
            from compprog_pygame.games.hex_colony.tech_tree import (
                TIERS as _TIERS,
            )
        except Exception:
            return BuildingType.HABITAT
        cur = self.colony.tier_tracker.current_tier
        if cur + 1 < len(_TIERS):
            next_tier = _TIERS[cur + 1]
            unlocks_next = list(
                getattr(next_tier, "unlocks_buildings", []) or []
            )
            # If the next tier unlocks a new building we haven't
            # placed yet, and it's already unlocked by tech, aim
            # for that — getting one placed often satisfies the
            # tier requirement directly.
            for btype in unlocks_next:
                if (self._is_unlocked(btype)
                        and not self._has_building(world, btype)):
                    return btype
        # Fallback: more housing never hurts.
        return BuildingType.HABITAT

    def _collect_chain_goals(
        self, world: World, primary: BuildingType | None,
    ) -> list:
        """Build the full goal list fed into :meth:`_goal_chain`.

        Starts with the *primary* building pick (if any) and folds
        in:

        * Any resources the next tier's ``resource_gathered``
          requirement is short on — so the chain builds out the
          production infrastructure for that tier's shopping list,
          not just whatever the AI happens to be placing.
        * Any resource recently unlocked by a tech the AI has
          researched but doesn't yet produce — unlocking
          ``IRON_BAR`` should prompt the chain to stand up a FORGE.

        Deduplicated, order-preserving.
        """
        goals: list = []
        seen: set = set()

        def _add(item) -> None:
            if item is None or item in seen:
                return
            seen.add(item)
            goals.append(item)

        _add(primary)

        # Tier shopping list.
        try:
            from compprog_pygame.games.hex_colony.tech_tree import (
                TIERS as _TIERS,
            )
            cur = self.colony.tier_tracker.current_tier
            if cur + 1 < len(_TIERS):
                req = getattr(
                    _TIERS[cur + 1], "requirements", {}
                ) or {}
                for rname, target in (
                    req.get("resource_gathered", {}) or {}
                ).items():
                    try:
                        res = Resource[rname]
                    except KeyError:
                        continue
                    if self._stock(world, res) < float(target):
                        _add(res)
        except Exception:
            pass

        # Recently-unlocked resources we aren't yet producing.
        try:
            from compprog_pygame.games.hex_colony.tech_tree import (
                RESOURCE_TECH_REQUIREMENTS,
            )
            researched = self.colony.tech_tree.researched
            for res, req_key in RESOURCE_TECH_REQUIREMENTS.items():
                if req_key not in researched:
                    continue
                if self._stock(world, res) >= 10:
                    continue
                _add(res)
        except Exception:
            pass

        # Active recipes whose inputs have no upstream supply.  If
        # the AI has already set a FORGE to IRON_BAR but no quarry
        # is mining iron, the goal chain would otherwise never know
        # IRON matters \u2014 the forge just sits idle.  Treating each
        # recipe output as a chain goal back-propagates the need
        # through ``_goal_chain`` and surfaces the missing raw
        # producer / intermediate station.
        try:
            from compprog_pygame.games.hex_colony.resources import (
                MATERIAL_RECIPES,
            )
            for b in self._snapshot(world).my_buildings:
                rec = getattr(b, "recipe", None)
                if rec is None:
                    continue
                if isinstance(rec, Resource):
                    mrec = MATERIAL_RECIPES.get(rec)
                    if mrec is None:
                        continue
                    inputs = mrec.inputs.keys()
                elif isinstance(rec, BuildingType):
                    cost = BUILDING_COSTS.get(rec)
                    if cost is None:
                        continue
                    inputs = cost.costs.keys()
                else:
                    continue
                # If any input is a resource we can't currently
                # source, fold the recipe output into the chain so
                # the full upstream dependency graph gets built.
                for res in inputs:
                    if not self._has_source_for(world, res):
                        _add(rec)
                        break
        except Exception:
            pass

        # Research centers and other input-consuming non-recipe
        # buildings.  These don't have a ``b.recipe`` attribute but
        # still pull resources through the logistics network:
        #
        # * RESEARCH_CENTER — consumes the currently active tech
        #   node's cost resources.  Without this block the AI will
        #   happily start a research that needs IRON_BAR while
        #   having no forge and no iron quarry, and the research
        #   just stalls forever.
        # * MINING_MACHINE — consumes fuel (charcoal / petroleum /
        #   coal per ``MINING_MACHINE_FUELS``).  If no fuel source
        #   is producible the machine sits idle, so fold the
        #   cheapest available fuel into the chain.
        try:
            from compprog_pygame.games.hex_colony.tech_tree import (
                TECH_NODES,
            )
            tt = getattr(self.colony, "tech_tree", None)
            active = getattr(tt, "current_research", None) if tt else None
            if active:
                node = TECH_NODES.get(active)
                consumed = getattr(tt, "_consumed", {}) or {}
                if node is not None:
                    # Only treat the research as "driving" the chain
                    # if we actually own a research center — otherwise
                    # the primary goal is to build one, not to chase
                    # its inputs.
                    has_rc = self._has_building(
                        world, BuildingType.RESEARCH_CENTER,
                    )
                    if has_rc:
                        for res, total_amt in node.cost.items():
                            remaining = float(total_amt) - float(
                                consumed.get(res, 0.0)
                            )
                            if remaining <= 0:
                                continue
                            if not self._has_source_for(world, res):
                                _add(res)
        except Exception:
            pass

        try:
            from compprog_pygame.games.hex_colony import params as _pm
            mining = self._snapshot(world).by_type.get(
                BuildingType.MINING_MACHINE, ()
            )
            if mining:
                fuels: list[Resource] = []
                for fuel_name in getattr(_pm, "MINING_MACHINE_FUELS", {}):
                    try:
                        fuels.append(Resource[fuel_name])
                    except KeyError:
                        continue
                if fuels and not any(
                    self._has_source_for(world, f) for f in fuels
                ):
                    # None available — add the first fuel (usually
                    # the cheapest / earliest-tier one) as a chain
                    # goal so the planner builds a producer for it.
                    _add(fuels[0])
        except Exception:
            pass

        return goals

    def _goal_chain(
        self,
        world: World,
        goal: "BuildingType | Resource | list[BuildingType | Resource]",
    ) -> tuple[set[BuildingType], set[Resource], dict[Resource, float]]:
        """Back-chain from one or more *goals* through recipes and raw
        producers to surface every piece of missing or capacity-short
        infrastructure.

        Each goal may be either a :class:`BuildingType` (back-chains
        via ``BUILDING_COSTS``) or a :class:`Resource` (back-chains
        directly via ``MATERIAL_RECIPES``), so the planner can handle
        *any* item in the game — building, intermediate material,
        end-game resource like ``ROCKET_PART`` — uniformly.

        Returns ``(missing_stations, missing_raw, demand_boost)``:

        * ``missing_stations`` — crafting stations (WORKSHOP, FORGE,
          REFINERY, ASSEMBLER, CHEMICAL_PLANT, OIL_REFINERY, etc.)
          that the chain requires and of which the colony has either
          **zero** instances, or too few to run all the distinct
          recipes the chain calls for in parallel (capacity-short).
        * ``missing_raw`` — raw resources whose producer is missing
          **or** too thinly spread relative to the demanded volume.
        * ``demand_boost`` — extra resource demand (units) for the
          recipe scheduler's ``needed`` map.

        The walk is depth-limited and cycle-guarded (shared
        ``visited`` set across multiple goals) so mutually recursive
        recipes like WORKSHOP → WOOD → WOODCUTTER-cost → STONE →
        QUARRY-cost → WOOD can't blow up.
        """
        _build_raw_producers()
        from compprog_pygame.games.hex_colony.resources import (
            MATERIAL_RECIPES, RAW_RESOURCES,
        )
        from compprog_pygame.games.hex_colony.params import (
            BUILDING_RECIPE_STATION,
        )

        missing_stations: set[BuildingType] = set()
        missing_raw: set[Resource] = set()
        demand: dict[Resource, float] = {}
        visited: set[tuple[str, str]] = set()
        # Per-tick snapshot — used by the producer-existence /
        # producer-counting closures below in place of full scans
        # over ``world.buildings.buildings``.
        snap = self._snapshot(world)
        # Per-station: which distinct recipes does the chain want
        # this station to run?  A station can only run one recipe at
        # a time, so if the chain touches N recipes on a station and
        # we have fewer than N of that station, we're capacity-short.
        recipe_load: dict[BuildingType, set[str]] = {}
        # Per raw resource: total units demanded from it across the
        # whole chain.  Used to decide whether one producer is
        # enough or we need to scale up.
        raw_volume: dict[Resource, float] = {}

        def _producer_exists(res: Resource) -> bool:
            producers = _RAW_PRODUCERS.get(res, ())
            for btype, required_output in producers:
                for b in snap.by_type.get(btype, ()):
                    if required_output is None:
                        if btype == BuildingType.QUARRY:
                            if getattr(b, "quarry_output", None) is None:
                                return True
                        elif btype == BuildingType.GATHERER:
                            out = getattr(b, "gatherer_output", None)
                            if out is None or out == Resource.FOOD:
                                return True
                        else:
                            return True
                    else:
                        if btype == BuildingType.QUARRY:
                            if (getattr(b, "quarry_output", None)
                                    == required_output):
                                return True
                        elif btype == BuildingType.GATHERER:
                            if (getattr(b, "gatherer_output", None)
                                    == required_output):
                                return True
                        else:
                            return True
            return False

        def _count_producer_matching(res: Resource) -> int:
            """How many of our buildings currently produce *res*?"""
            n = 0
            for btype, required_output in _RAW_PRODUCERS.get(res, ()):
                for b in snap.by_type.get(btype, ()):
                    if btype == BuildingType.QUARRY:
                        if (getattr(b, "quarry_output", None)
                                == required_output):
                            n += 1
                    elif btype == BuildingType.GATHERER:
                        cur = (getattr(b, "gatherer_output", None)
                               or Resource.FOOD)
                        want = required_output or Resource.FOOD
                        if cur == want:
                            n += 1
                    else:
                        n += 1
            return n

        def _walk_building(btype: BuildingType, depth: int) -> None:
            if depth > 8:
                return
            key = ("b", btype.name)
            if key in visited:
                return
            visited.add(key)
            # Station needed to *craft* this building.
            station_name = BUILDING_RECIPE_STATION.get(btype.name)
            if station_name is not None:
                try:
                    station = BuildingType[station_name]
                    recipe_load.setdefault(station, set()).add(btype.name)
                except KeyError:
                    pass
            cost = BUILDING_COSTS.get(btype)
            if cost is None:
                return
            for res, amt in cost.costs.items():
                _walk_resource(res, float(amt), depth + 1)

        def _walk_resource(res: Resource, amount: float, depth: int) -> None:
            if depth > 8 or amount <= 0:
                return
            key = ("r", res.name)
            demand[res] = demand.get(res, 0.0) + amount
            if key in visited:
                # Already walked — just accumulate additional volume
                # so capacity scoring reflects the real total.
                if res in RAW_RESOURCES:
                    raw_volume[res] = raw_volume.get(res, 0.0) + amount
                return
            visited.add(key)
            if res in RAW_RESOURCES:
                raw_volume[res] = raw_volume.get(res, 0.0) + amount
                return
            mrec = MATERIAL_RECIPES.get(res)
            if mrec is None:
                return
            try:
                station = BuildingType[mrec.station]
                recipe_load.setdefault(station, set()).add(res.name)
            except KeyError:
                pass
            per_unit = amount / max(1, mrec.output_amount)
            for in_res, in_amt in mrec.inputs.items():
                _walk_resource(in_res, per_unit * in_amt, depth + 1)

        # Accept single goal or iterable of goals.
        if isinstance(goal, (BuildingType, Resource)):
            goals: list = [goal]
        else:
            goals = list(goal)
        for g in goals:
            if isinstance(g, BuildingType):
                _walk_building(g, 0)
            elif isinstance(g, Resource):
                # Seed demand with a reasonable "try to build up some
                # of this" amount so the chain pulls through.
                _walk_resource(g, 30.0, 0)

        # ── Station capacity scoring ─────────────────────────
        # Need ≥ parallel-recipe-count of each station to actually
        # run every chain recipe concurrently.  If the colony has
        # one WORKSHOP but the chain touches five workshop recipes,
        # flag WORKSHOP as "missing" so the build loop scales up.
        for station, recipes in recipe_load.items():
            have = self._count_building(world, station)
            needed_count = max(1, len(recipes))
            if have < needed_count:
                missing_stations.add(station)

        # ── Raw producer capacity scoring ────────────────────
        # Threshold: one producer comfortably covers ~40 units of
        # total chain demand (rough — WOODCUTTER trickles ~2/s, but
        # we want to bias toward redundancy when demand is huge).
        for res, vol in raw_volume.items():
            have = _count_producer_matching(res)
            needed_count = max(1, int(vol // 40) + 1) if vol > 0 else 1
            if have < needed_count:
                missing_raw.add(res)

        return missing_stations, missing_raw, demand

    # ── Build decision ───────────────────────────────────────────

    def _try_build(self, world: World) -> None:
        owned = self._owned_coords(world)
        # Soft cap — exclude paths / walls / pipes / conveyors.
        non_path_count = 0
        for c in owned:
            b = world.buildings.at(c)
            if b is None:
                continue
            if b.type not in (BuildingType.PATH, BuildingType.BRIDGE,
                              BuildingType.WALL, BuildingType.PIPE,
                              BuildingType.CONVEYOR):
                non_path_count += 1
        if non_path_count >= _MAX_BUILDINGS_PER_CLANKER:
            return

        # Prune expired blacklist entries before consulting it.
        now = world.time_elapsed
        if self._blocked_targets:
            expired = [
                k for k, t in self._blocked_targets.items()
                if (now - t) >= _BLOCKED_TARGET_COOLDOWN
            ]
            for k in expired:
                self._blocked_targets.pop(k, None)

        choice = self._pick_building_to_place(world)
        if choice is None:
            # Heartbeat so the player (and the monitor log) can see
            # that the AI is intentionally idle, not crashed.
            if self._idle_streak_start < 0:
                self._idle_streak_start = now
            if (now - self._last_idle_log) >= _IDLE_HEARTBEAT_INTERVAL:
                pop, cap, demand, _ = self._staffing_state(world)
                streak = now - self._idle_streak_start
                self._log(
                    world,
                    f"Idle ({int(streak)}s) — pop {pop}/{cap}, "
                    f"{demand} job slots, nothing to place this tick.",
                )
                self._last_idle_log = now
            # Idle-rescue: after a long stretch of doing nothing,
            # force a speculative HABITAT to push pop growth past
            # the staffing/single-dwelling deadlock.  HABITAT is
            # safe — it doesn't need workers itself, and a fresh
            # one becomes a new birth site (only HABITATs reproduce;
            # TRIBAL_CAMPs do not), so a colony stuck at 11/16 with
            # one HABITAT actually has only 1 reproduction slot.
            if (now - self._idle_streak_start) >= _IDLE_FORCE_INTERVAL:
                if (self._is_unlocked(BuildingType.HABITAT)
                        and self._can_pay_for(BuildingType.HABITAT)):
                    target = self._find_placement(
                        world, BuildingType.HABITAT,
                    )
                    if target is not None:
                        cand_key = (
                            BuildingType.HABITAT.name, target.q, target.r,
                        )
                        if cand_key not in self._blocked_targets:
                            connected = self._is_path_connected(
                                world, target,
                            )
                            if not connected:
                                connected = self._lay_path_to(
                                    world, target,
                                )
                            if connected and self._place(
                                    world, BuildingType.HABITAT, target):
                                self._log(
                                    world,
                                    "Forcing extra HABITAT — idle "
                                    "rescue, need a new birth site.",
                                )
                                self._idle_streak_start = now
                                self._last_idle_log = now
                                return
                            self._blocked_targets[cand_key] = now
            return
        btype, target, reason = choice
        # A real choice — break the idle streak.
        self._idle_streak_start = -1.0
        # Skip if this exact target was recently blacklisted.
        key = (btype.name, target.q, target.r)
        if key in self._blocked_targets:
            return
        # Every non-path building must touch our PATH/BRIDGE/CAMP
        # network so workers and haulers can reach it.  Being
        # "adjacent to an owned tile" isn't enough — that tile might
        # itself be a stranded building.  If the target isn't
        # already on the network, lay a path chain out to it.  When
        # PATH stock can't cover the run, abort and let the workshop
        # craft more next tick.
        needs_connection = btype not in (
            BuildingType.PATH, BuildingType.BRIDGE,
        )
        # Build a list of candidate placements: the planner's first
        # pick plus alternatives ranked by ``_find_placement_candidates``
        # for the same building type.  This lets the AI fall back to
        # a different resource tile when the first one is blocked
        # (river without bridges, path run too long, etc.) instead of
        # giving up on the whole tier-relevant building.
        targets: list[HexCoord] = [target]
        if needs_connection:
            for alt in self._find_placement_candidates(world, btype, limit=6):
                if alt != target and alt not in targets:
                    targets.append(alt)
        for cand in targets:
            cand_key = (btype.name, cand.q, cand.r)
            if cand_key in self._blocked_targets:
                continue
            if needs_connection and not self._is_path_connected(world, cand):
                if not self._lay_path_to(world, cand):
                    # Path-laying itself failed for this candidate
                    # (no PATH stock, river without bridges, etc.) —
                    # blacklist this specific spot so we move on.
                    self._blocked_targets[cand_key] = now
                    continue
                if not self._is_path_connected(world, cand):
                    self._blocked_targets[cand_key] = now
                    continue
            if self._place(world, btype, cand):
                self._log(world, reason)
                self._last_idle_log = now  # reset heartbeat
                return
            # Place failed at a candidate that *did* path-connect —
            # blacklist so we don't retry next tick.
            self._blocked_targets[cand_key] = now
        # Fell through every candidate — log against the planner's
        # original target so the player can diagnose the stuck state,
        # and blacklist the original pick so the AI tries something
        # else next tick instead of spamming the same plan.
        self._blocked_targets[key] = now
        self._log(
            world,
            f"Wanted {btype.name} at ({target.q},{target.r}) but no "
            f"reachable spot worked (tried {len(targets)} candidate(s)).",
        )

    def _pick_building_to_place(
        self, world: World,
    ) -> tuple[BuildingType, HexCoord, str] | None:
        """Walk priorities and return the first
        (building_type, coord, justification) we can act on."""
        camp = world.buildings.at(self.home)

        def stock(res: Resource) -> float:
            # Delegate to the network-wide _stock so build decisions
            # see every faction-owned building's storage, not just
            # the camp.  This prevents the "I have 0 planks!" bug
            # when planks are actually sitting in a workshop.
            return self._stock(world, res)

        # ── Workforce snapshot ──────────────────────────────────
        my_pop, my_cap, worker_demand, _workers_assigned = (
            self._staffing_state(world)
        )
        # Workers free to staff *new* job slots.  Negative means we
        # already have more job slots than people — adding more would
        # just leave them idle.
        free_workers = my_pop - worker_demand
        # When we're staffing-bound, the only worker-requiring
        # building worth placing is housing (which doesn't need
        # workers itself but lets pop grow to fill the existing
        # jobs).  Pure infra (paths, storage) is always fine.
        can_staff_more = free_workers >= _STAFFING_HEADROOM

        def needs_workers(bt: BuildingType) -> bool:
            return (bt not in _NON_WORKER_BTYPES
                    and BUILDING_MAX_WORKERS.get(bt, 0) > 0)

        # ── Goal-chain planner ───────────────────────────────────
        # Back-chain from the top-level goal (usually HABITAT when
        # population is tight, else a missing crafting station or
        # next-tier unlock) to figure out which infrastructure is
        # missing.  This gives the AI "long-term reasoning": when
        # it wants HABITAT but lacks IRON_BAR, it realises it needs
        # a FORGE; when it lacks IRON, it realises it needs a
        # MINING_MACHINE or an IRON-configured QUARRY; and so on.
        goal_building = self._pick_goal_building(
            world, my_pop, my_cap, worker_demand,
        )
        goal_missing_stations: set[BuildingType] = set()
        goal_missing_raw: set[Resource] = set()
        self._goal_demand: dict[Resource, float] = {}
        goals = self._collect_chain_goals(world, goal_building)
        if goals:
            (goal_missing_stations,
             goal_missing_raw,
             self._goal_demand) = self._goal_chain(world, goals)

        # ── Priority 1: housing ─────────────────────────────────
        # Build housing whenever (a) pop is at/near cap, OR (b) we
        # already have unfilled jobs and need pop to grow into them,
        # OR (c) we're staffing-bound and housing headroom is thin
        # (pushes pop growth so the colony can keep expanding), OR
        # (d) the colony is still small — a starting clanker with
        # 2 pop needs to build habitats aggressively to bootstrap.
        pop_small = my_pop < 8
        low_headroom = (my_cap - my_pop) < 3
        housing_pressure = (
            my_pop >= my_cap - 1
            or (worker_demand > my_pop and my_cap <= my_pop)
            or (not can_staff_more and low_headroom)
            or (pop_small and low_headroom)
        )
        if (housing_pressure
                and self._is_unlocked(BuildingType.HABITAT)
                and self._can_pay_for(BuildingType.HABITAT)):
            target = self._find_placement(world, BuildingType.HABITAT)
            if target is not None:
                if my_pop >= my_cap - 1:
                    why = (
                        f"Building HABITAT \u2014 housing {my_pop}/{my_cap} "
                        "is full, need room to grow."
                    )
                elif pop_small:
                    why = (
                        f"Building HABITAT \u2014 only {my_pop} people so "
                        f"far; need more habitats to attract population."
                    )
                elif not can_staff_more:
                    why = (
                        f"Building HABITAT \u2014 all {worker_demand} "
                        "jobs staffed; growing pop to unblock expansion."
                    )
                else:
                    why = (
                        f"Building HABITAT \u2014 {worker_demand} job slots "
                        f"but only {my_pop} workers; need pop to grow."
                    )
                return (BuildingType.HABITAT, target, why)

        # ── Priority 2: food security ───────────────────────────
        if stock(Resource.FOOD) < 30 and my_pop > 3 and can_staff_more:
            for btype in (BuildingType.FARM, BuildingType.GATHERER):
                if (self._is_unlocked(btype)
                        and self._can_pay_for(btype)):
                    target = self._find_placement(world, btype)
                    if target is not None:
                        return (
                            btype, target,
                            f"Building {btype.name} \u2014 food stock "
                            f"low ({int(stock(Resource.FOOD))}).",
                        )

        # ── Priority 3: basic raw production ────────────────────
        if can_staff_more:
            for res, btype in (
                (Resource.WOOD, BuildingType.WOODCUTTER),
                (Resource.STONE, BuildingType.QUARRY),
                (Resource.FIBER, BuildingType.GATHERER),
            ):
                if (stock(res) < 25
                        and self._is_unlocked(btype)
                        and self._can_pay_for(btype)):
                    target = self._find_placement(world, btype)
                    if target is not None:
                        return (
                            btype, target,
                            f"Building {btype.name} on a "
                            f"{self._terrain_label(btype)} \u2014 "
                            f"{res.name.lower()} stock low "
                            f"({int(stock(res))}).",
                        )

        # ── Priority 4: bring research online ───────────────────
        if (can_staff_more
                and not self._has_building(
                    world, BuildingType.RESEARCH_CENTER)
                and self._is_unlocked(BuildingType.RESEARCH_CENTER)
                and self._can_pay_for(BuildingType.RESEARCH_CENTER)):
            target = self._find_placement(world, BuildingType.RESEARCH_CENTER)
            if target is not None:
                return (
                    BuildingType.RESEARCH_CENTER, target,
                    "Building RESEARCH_CENTER \u2014 need to start "
                    "researching tech to advance.",
                )

        # ── Priority 4.5: goal-chain missing infrastructure ─────
        # If the top-level goal's dependency chain requires a
        # crafting station (FORGE/REFINERY/ASSEMBLER/…) or a raw
        # producer (MINING_MACHINE for IRON, IRON-configured
        # QUARRY, …) that we don't have, place it before generic
        # capacity scaling.  This is the "long-term reasoning"
        # payoff — the AI actively builds what it needs to unblock
        # its chosen goal rather than waiting for defaults to
        # catch up.
        if goal_missing_stations or goal_missing_raw:
            goal_label = (
                goal_building.name if goal_building is not None
                else "current goal"
            )
            chain_picks: list[tuple[BuildingType, str]] = []
            for st in goal_missing_stations:
                have = self._count_building(world, st)
                if have == 0:
                    why = f"chain for {goal_label} needs a {st.name}"
                else:
                    why = (
                        f"chain for {goal_label} needs more {st.name} "
                        f"capacity (have {have})"
                    )
                chain_picks.append((st, why))
            for raw in goal_missing_raw:
                producers = _RAW_PRODUCERS.get(raw, ())
                for btype, _required in producers:
                    chain_picks.append((
                        btype,
                        f"chain for {goal_label} needs "
                        f"{raw.name.lower()} \u2014 placing "
                        f"{btype.name}",
                    ))
            for btype, why in chain_picks:
                if btype == goal_building:
                    # The goal itself is handled by the usual
                    # priorities; don't double up here.
                    continue
                if not self._is_unlocked(btype):
                    continue
                # Goal-chain placements may overshoot worker demand
                # by 1 — pop will catch up via births and the new
                # building unblocks tier progress.  Without this
                # relaxation, a clanker stuck at "11 pop / 12 jobs"
                # never builds the FORGE its goal needs (4/21 log).
                if needs_workers(btype):
                    if free_workers < (_STAFFING_HEADROOM - 1):
                        continue
                if not self._can_pay_for(btype):
                    # Can't place it directly, but the demand boost
                    # will steer workshops to craft one next tick.
                    continue
                if not self._has_input_supply(world, btype):
                    # The chain itself will surface the upstream
                    # producer as "missing_raw"; skip this station
                    # until we have something to feed it.
                    continue
                target = self._find_placement(world, btype)
                if target is None:
                    continue
                return (btype, target, f"Building {btype.name} \u2014 {why}.")

        # ── Priority 5: ensure crafting capacity ────────────────
        if (can_staff_more
                and self._count_building(world, BuildingType.WORKSHOP) < 2
                and self._is_unlocked(BuildingType.WORKSHOP)
                and self._can_pay_for(BuildingType.WORKSHOP)):
            target = self._find_placement(world, BuildingType.WORKSHOP)
            if target is not None:
                return (
                    BuildingType.WORKSHOP, target,
                    "Building WORKSHOP \u2014 need crafting capacity "
                    "for planks and building stockpile.",
                )
        if (can_staff_more
                and self._count_building(world, BuildingType.FORGE) < 1
                and self._is_unlocked(BuildingType.FORGE)
                and self._has_input_supply(world, BuildingType.FORGE)
                and self._can_pay_for(BuildingType.FORGE)):
            target = self._find_placement(world, BuildingType.FORGE)
            if target is not None:
                return (
                    BuildingType.FORGE, target,
                    "Building FORGE \u2014 need metal-tier crafting.",
                )
        # Scale up extra workshops/forges/assemblers once the colony
        # has bandwidth, so late-game material throughput keeps up
        # with downstream demand.
        scale_caps: tuple[tuple[BuildingType, int, str], ...] = (
            (BuildingType.WORKSHOP, max(2, my_pop // 8),
             "more crafting throughput for the growing colony"),
            (BuildingType.FORGE, max(1, my_pop // 12),
             "more metal-bar throughput"),
            (BuildingType.ASSEMBLER, max(1, my_pop // 14),
             "more advanced-recipe throughput"),
            (BuildingType.RESEARCH_CENTER, max(1, my_pop // 18),
             "more research throughput"),
        )
        if can_staff_more:
            for btype, cap, why in scale_caps:
                if not self._is_unlocked(btype):
                    continue
                if not self._can_pay_for(btype):
                    continue
                if not self._has_input_supply(world, btype):
                    continue
                if self._count_building(world, btype) >= cap:
                    continue
                target = self._find_placement(world, btype)
                if target is not None:
                    return (
                        btype, target,
                        f"Building {btype.name} \u2014 {why}.",
                    )

        # ── Priority 6: storage for surplus (no workers needed) ─
        if (any(stock(r) > 80
                for r in (Resource.WOOD, Resource.STONE, Resource.FOOD))
                and self._is_unlocked(BuildingType.STORAGE)
                and self._can_pay_for(BuildingType.STORAGE)):
            target = self._find_placement(world, BuildingType.STORAGE)
            if target is not None:
                return (
                    BuildingType.STORAGE, target,
                    "Building STORAGE \u2014 stockpiles overflowing.",
                )

        # ── Priority 7: tier-driven expansion ───────────────────
        # When a tech / tier just opened up a new building, plant one
        # (or scale by colony size for resource extractors and
        # high-throughput industrial chains).  Skip the placeholder
        # land-only types (PATH/BRIDGE/WALL).  Worker-requiring
        # buildings are gated on having spare staff.
        type_caps: dict[BuildingType, int] = {
            BuildingType.WOODCUTTER: max(2, my_pop // 6),
            BuildingType.QUARRY: max(2, my_pop // 6),
            BuildingType.GATHERER: max(2, my_pop // 8),
            BuildingType.FARM: max(2, my_pop // 6),
            BuildingType.WELL: 2,
            BuildingType.REFINERY: max(1, my_pop // 12),
            BuildingType.MINING_MACHINE: max(1, my_pop // 10),
            BuildingType.OIL_DRILL: max(1, my_pop // 12),
            BuildingType.OIL_REFINERY: max(1, my_pop // 14),
            BuildingType.CHEMICAL_PLANT: max(1, my_pop // 14),
            BuildingType.SOLAR_ARRAY: max(1, my_pop // 10),
            BuildingType.ROCKET_SILO: 1,
        }
        for btype in _PLACEABLE:
            if btype in (BuildingType.PATH, BuildingType.BRIDGE,
                         BuildingType.WALL):
                continue
            if needs_workers(btype) and not can_staff_more:
                continue
            if not (self._is_unlocked(btype)
                    and self._can_pay_for(btype)):
                continue
            if not self._has_input_supply(world, btype):
                continue
            cap = type_caps.get(btype, 1)
            if self._count_building(world, btype) >= cap:
                continue
            target = self._find_placement(world, btype)
            if target is None:
                continue
            return (
                btype, target,
                f"Building {btype.name} \u2014 expanding "
                f"({self._count_building(world, btype) + 1}/{cap}).",
            )

        # Nothing to do this tick.  If we just became staffing-bound,
        # log it once so the player can see why the AI is idle.
        if not can_staff_more and worker_demand > 0:
            if not self._was_staffing_bound:
                self._log(
                    world,
                    f"Holding off on new buildings \u2014 "
                    f"{worker_demand} job slots, only {my_pop} workers.",
                )
            self._was_staffing_bound = True
        else:
            self._was_staffing_bound = False
        return None

    # ── Placement ────────────────────────────────────────────────

    def _is_adjacent_to_owned(
        self, world: World, coord: HexCoord,
    ) -> bool:
        """True iff *coord* is a neighbour of any tile owned by us."""
        owned = self._snapshot(world).owned_coord_set
        for nb in coord.neighbors():
            if nb in owned:
                return True
        return False

    def _is_path_connected(
        self, world: World, coord: HexCoord,
    ) -> bool:
        """True iff *coord* is adjacent to a PATH/BRIDGE/TRIBAL_CAMP
        belonging to this faction.

        Workers and haulers can only reach buildings that touch the
        path network, so we require this before placing any
        non-path structure.  Being next to an isolated faction
        building isn't enough — that building itself might be
        stranded off the network.
        """
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
        """Can we lay a PATH (or BRIDGE, if *allow_bridge*) on
        *coord*, or already have one there?

        With *allow_bridge*, water tiles count as passable since the
        AI can drop a BRIDGE on them — this lets the path-laying BFS
        cross rivers when the colony has bridge stockpile available.
        """
        from compprog_pygame.games.hex_colony.procgen import Terrain
        tile = world.grid.get(coord)
        if tile is None:
            return False
        b = tile.building
        if b is not None:
            # Existing PATH or BRIDGE that's ours — reuse it.
            if (b.type in (BuildingType.PATH, BuildingType.BRIDGE)
                    and getattr(b, "faction", "SURVIVOR") == self.faction_id):
                return True
            # Any other building blocks path-laying.
            return False
        # Water is only passable if we're allowed to bridge it.
        if tile.terrain == Terrain.WATER:
            return allow_bridge
        if tile.terrain in UNBUILDABLE:
            return False
        return True

    def _shortest_path_to(
        self, world: World, target: HexCoord,
    ) -> list[HexCoord] | None:
        """BFS over passable land (and water, when we have BRIDGE
        stockpile) from any of our buildings to a tile adjacent to
        *target*.  Returns the chain of *new* hexes that need a
        PATH/BRIDGE placed on them (excludes already-owned tiles
        and the target itself), in order from nearest-owned outward.

        Returns ``None`` if no route exists within ``_MAX_PATH_RUN``.
        """
        owned = self._snapshot(world).owned_coord_set
        if not owned:
            return None
        # Allow water crossings only if we actually have bridge stock
        # (or workshops likely to craft some) — otherwise the planner
        # would happily route through impassable rivers.
        bridge_stock = self.colony.building_inventory[BuildingType.BRIDGE]
        allow_bridge = bridge_stock > 0
        # BFS frontier: tiles we can step onto that aren't owned yet.
        # Parent map lets us reconstruct the shortest chain.
        visited: set[HexCoord] = set(owned)
        parent: dict[HexCoord, HexCoord] = {}
        queue: deque[HexCoord] = deque()
        for o in owned:
            for nb in o.neighbors():
                if nb in visited:
                    continue
                if not self._is_path_passable(
                    world, nb, allow_bridge=allow_bridge,
                ):
                    # Can't lay a path here, but it might already be
                    # adjacent to target \u2014 only useful if target itself.
                    if nb == target:
                        # No new tiles needed.
                        return []
                    continue
                visited.add(nb)
                parent[nb] = o
                queue.append(nb)
        found: HexCoord | None = None
        while queue:
            cur = queue.popleft()
            # Are we adjacent to the target? then we're done.
            if any(nb == target for nb in cur.neighbors()):
                found = cur
                break
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
                queue.append(nb)
        if found is None:
            return None
        # Walk parents back to an owned tile, collecting only the
        # *new* tiles that need a path placed.
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
        # If the chain crosses more water tiles than we can bridge,
        # bail so we don't half-build an unreachable run.
        if allow_bridge:
            water_steps = sum(
                1 for c in chain
                if self._tile_terrain(world, c).name == "WATER"
            )
            if water_steps > bridge_stock:
                return None
        return chain

    @staticmethod
    def _tile_terrain(world: World, coord: HexCoord):
        tile = world.grid.get(coord)
        if tile is None:
            from compprog_pygame.games.hex_colony.procgen import Terrain
            return Terrain.GRASS
        return tile.terrain

    def _lay_path_to(self, world: World, target: HexCoord) -> bool:
        """Place a chain of PATH (and BRIDGE on water) buildings so
        *target* becomes adjacent to our territory.  Returns True
        on success.

        Aborts (and places nothing) if we don't have enough stock to
        cover the whole route — a workshop will craft more on the
        next ``_set_recipes`` tick.
        """
        chain = self._shortest_path_to(world, target)
        if chain is None:
            return False
        if not chain:
            # Already adjacent — nothing to lay.
            return True
        # Split chain into PATH steps (land) and BRIDGE steps (water).
        from compprog_pygame.games.hex_colony.procgen import Terrain
        path_steps: list[HexCoord] = []
        bridge_steps: list[HexCoord] = []
        for c in chain:
            terr = self._tile_terrain(world, c)
            if terr == Terrain.WATER:
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
        world.mark_networks_dirty()
        self._invalidate_snapshot()
        if bridge_steps:
            self._log(
                world,
                f"Laid {len(path_steps)} path + {len(bridge_steps)} bridge "
                f"tile(s) to reach ({target.q},{target.r}).",
            )
        else:
            self._log(
                world,
                f"Laid {len(path_steps)} path tile(s) to reach "
                f"({target.q},{target.r}).",
            )
        return True

    def _terrain_label(self, btype: BuildingType) -> str:
        """Short human-readable label for the terrain a building wants
        to be near, for use in justification messages."""
        terr = _terrain_for(btype)
        if not terr:
            return "open ground"
        names = sorted(t.name.lower().replace("_", " ") for t in terr)
        return " or ".join(names)

    def _narrow_ore_terrain(
        self, world: World, btype: BuildingType, base: set,
    ) -> set:
        """For QUARRY / MINING_MACHINE, pick the subset of the
        generic ore-terrain set that matches the resource the
        colony most needs right now.

        The generic terrain-affinity map treats stone deposits,
        mountains, iron veins, and copper veins equivalently \u2014
        great for "some ore mining building fits here" but it
        means a colony asking for STONE will happily sit a quarry
        on an IRON_VEIN (since the quarry's default output is
        STONE, that tile then produces nothing).  Priority order:

        1. Goal-chain demand (``self._goal_demand``) if set.
        2. Stockpile shortfall across STONE / IRON / COPPER.
        3. Fall back to the full set if nothing is urgent.
        """
        if btype not in (
            BuildingType.QUARRY, BuildingType.MINING_MACHINE,
        ):
            return base
        from compprog_pygame.games.hex_colony.procgen import Terrain
        stone_set = {Terrain.STONE_DEPOSIT, Terrain.MOUNTAIN}
        iron_set = {Terrain.IRON_VEIN}
        copper_set = {Terrain.COPPER_VEIN}

        # Score each ore by (goal demand) + (stockpile shortfall).
        scores: dict[Resource, float] = {}
        for res in (Resource.STONE, Resource.IRON, Resource.COPPER):
            demand = float(self._goal_demand.get(res, 0.0))
            have = self._stock(world, res)
            # Shortfall vs. a rough "comfortable" target.
            shortfall = max(0.0, 40.0 - have)
            scores[res] = demand * 2.0 + shortfall

        # MINING_MACHINE doesn't produce STONE, only iron/copper.
        if btype == BuildingType.MINING_MACHINE:
            scores[Resource.STONE] = 0.0

        best_res = max(scores, key=lambda r: scores[r])
        if scores[best_res] <= 0:
            return base
        chosen_terrain = {
            Resource.STONE: stone_set,
            Resource.IRON: iron_set,
            Resource.COPPER: copper_set,
        }[best_res] & base
        return chosen_terrain or base

    def _find_placement(
        self, world: World, btype: BuildingType,
    ) -> HexCoord | None:
        """Pick the best buildable hex within our expansion radius.

        For *terrain-affinity* buildings (woodcutters, quarries,
        gatherers, oil drills, etc.) we scan **every** tile inside
        the radius and prefer ones adjacent to the right terrain,
        even if they're a few tiles away from our existing footprint
        \u2014 ``_lay_path_to`` will run a path chain out to the spot.

        For other buildings we restrict placement to tiles directly
        adjacent to our existing territory so they cluster around
        the camp instead of scattering.
        """
        target_terrain = _terrain_for(btype)
        owned = self._snapshot(world).owned_coord_set
        if not owned:
            return None

        if target_terrain is None:
            # Non-resource building \u2014 cluster near owned territory.
            return self._find_adjacent_placement(world, btype)

        # For QUARRY / MINING_MACHINE, the generic terrain set lumps
        # stone, iron, and copper together.  Narrow it to *what the
        # colony actually needs right now* so we don't drop a quarry
        # on an iron vein when we only needed stone (and vice versa).
        target_terrain = self._narrow_ore_terrain(world, btype, target_terrain)

        # Resource building \u2014 hunt for a hex adjacent to the right
        # terrain, anywhere in our radius.  Prefer hexes that are:
        #   * actually next to the target terrain (large bonus)
        #   * close to our existing footprint (cheaper path chain)
        #   * close to the camp (keeps the colony compact)
        #
        # We use a bounded multi-source BFS from owned tiles to
        # enumerate only the candidate hexes within reach (instead
        # of scanning every tile on the map and computing distance
        # to nearest-owned for each one — which is O(tiles \u00d7 owned)
        # and dominated AI tick cost in older versions).
        candidates: list[tuple[float, HexCoord]] = []
        center = self.home
        max_dist = _MAX_PATH_RUN + 1
        # Multi-source BFS gives us dist-from-owned for every reach-
        # able hex in one pass; visited[coord] = nearest_owned dist.
        # Cache per tick — the BFS only depends on owned tiles, not
        # on the building type, so every priority that calls
        # _find_placement in the same tick can share one walk.
        visited = self._visited_cache.get("__placement_bfs")
        if visited is None:
            visited = {c: 0 for c in owned}
            frontier: deque[HexCoord] = deque(owned)
            while frontier:
                cur = frontier.popleft()
                d = visited[cur]
                if d >= max_dist:
                    continue
                for nb in cur.neighbors():
                    if nb in visited:
                        continue
                    if nb.distance(center) > _MAX_EXPANSION_RADIUS:
                        continue
                    visited[nb] = d + 1
                    frontier.append(nb)
            self._visited_cache["__placement_bfs"] = visited
        grid_get = world.grid.get
        target_set = target_terrain  # local alias
        oil_drill = (btype == BuildingType.OIL_DRILL)
        for coord, nearest_owned in visited.items():
            if coord in owned:
                # Tiles already occupied by us — skip; ``tile.building
                # is not None`` would also reject below.
                continue
            tile = grid_get(coord)
            if tile is None or tile.building is not None:
                continue
            if tile.terrain in UNBUILDABLE:
                if not (oil_drill and tile.terrain.name == "OIL_DEPOSIT"):
                    continue
            # Count target-terrain hexes touching this tile.  The
            # tile itself counts double — standing right on a fiber
            # patch / forest / ore vein is the best possible spot.
            terrain_count = 0
            if tile.terrain in target_set:
                terrain_count += 2
            for nb in coord.neighbors():
                nb_tile = grid_get(nb)
                if (nb_tile is not None
                        and nb_tile.terrain in target_set):
                    terrain_count += 1
            if terrain_count == 0:
                continue
            score = (
                100.0
                + 25.0 * terrain_count       # richer site = better
                - 5.0 * nearest_owned        # cheap to reach is good
                - 1.0 * coord.distance(center)
                + self.rng.random() * 0.5    # tie-break jitter
            )
            candidates.append((score, coord))

        if not candidates:
            # No on-terrain spot reachable — give up rather than
            # plopping a gatherer on bare grass.  The build loop will
            # try a different priority next tick.
            return None
        candidates.sort(key=lambda c: c[0], reverse=True)
        # Skip any spot we've recently failed at (e.g. unreachable
        # across a river) so the planner moves on instead of
        # re-picking the same hex every build tick.
        for _score, coord in candidates:
            key = (btype.name, coord.q, coord.r)
            if key in self._blocked_targets:
                continue
            return coord
        return None

    def _find_placement_candidates(
        self, world: World, btype: BuildingType, limit: int = 6,
    ) -> list[HexCoord]:
        """Return up to *limit* ranked placement candidates for
        *btype*, best first.  Used by the build loop so it can fall
        back to alternative resource tiles when its first pick can't
        be reached (e.g. blocked by a river with no bridges, or path
        run too long).
        """
        target_terrain = _terrain_for(btype)
        owned = self._snapshot(world).owned_coord_set
        if not owned:
            return []
        if target_terrain is None:
            best = self._find_adjacent_placement(world, btype)
            return [best] if best is not None else []
        target_terrain = self._narrow_ore_terrain(world, btype, target_terrain)
        candidates: list[tuple[float, HexCoord]] = []
        center = self.home
        max_dist = _MAX_PATH_RUN + 1
        visited: dict[HexCoord, int] = {c: 0 for c in owned}
        frontier: deque[HexCoord] = deque(owned)
        while frontier:
            cur = frontier.popleft()
            d = visited[cur]
            if d >= max_dist:
                continue
            for nb in cur.neighbors():
                if nb in visited:
                    continue
                if nb.distance(center) > _MAX_EXPANSION_RADIUS:
                    continue
                visited[nb] = d + 1
                frontier.append(nb)
        grid_get = world.grid.get
        target_set = target_terrain
        oil_drill = (btype == BuildingType.OIL_DRILL)
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
            if tile.terrain in target_set:
                terrain_count += 2
            for nb in coord.neighbors():
                nb_tile = grid_get(nb)
                if (nb_tile is not None
                        and nb_tile.terrain in target_set):
                    terrain_count += 1
            if terrain_count == 0:
                continue
            score = (
                100.0
                + 25.0 * terrain_count
                - 5.0 * nearest_owned
                - 1.0 * coord.distance(center)
                + self.rng.random() * 0.5
            )
            candidates.append((score, coord))
        if not candidates:
            return []
        candidates.sort(key=lambda c: c[0], reverse=True)
        return [c for _, c in candidates[:limit]]

    def _find_adjacent_placement(
        self, world: World, btype: BuildingType,
    ) -> HexCoord | None:
        """Original BFS-through-paths placement \u2014 used for buildings
        that don't care about terrain (housing, storage, workshops)."""
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
                    if not (btype == BuildingType.BRIDGE
                            and self._is_water(tile.terrain)):
                        continue
                candidates.append(nb)

        if not candidates:
            return None

        def score(coord: HexCoord) -> float:
            dist = coord.distance(self.home)
            return -float(dist) + self.rng.random() * 0.1

        candidates.sort(key=score, reverse=True)
        for coord in candidates:
            key = (btype.name, coord.q, coord.r)
            if key in self._blocked_targets:
                continue
            return coord
        return None

    @staticmethod
    def _is_water(terrain) -> bool:
        from compprog_pygame.games.hex_colony.procgen import Terrain
        return terrain == Terrain.WATER

    def _place(
        self, world: World, btype: BuildingType, coord: HexCoord,
    ) -> bool:
        """Spend a stockpiled building and place it on *coord*."""
        if self.colony.building_inventory[btype] < 1:
            return False
        tile = world.grid.get(coord)
        if tile is None or tile.building is not None:
            return False
        self.colony.building_inventory.spend(btype)
        b = world.buildings.place(btype, coord)
        b.faction = self.faction_id
        tile.building = b
        # Configure freshly-placed building so it actually does
        # something (player UI normally does this; AI must do it
        # manually).
        self._configure_new_building(world, b)
        world.mark_networks_dirty()
        world.mark_housing_dirty()
        self._invalidate_snapshot()
        return True

    # ── Per-building configuration on placement ──────────────────

    def _configure_new_building(self, world: World, b) -> None:
        """Pick a sensible default output / stored-resource for a
        building the AI just placed so it doesn't sit idle.

        * QUARRY — picks IRON / COPPER if those veins are nearby and
          the colony is short on the corresponding ore; defaults to
          STONE otherwise.
        * GATHERER — picks FOOD if food is low, FIBER otherwise.
        * STORAGE — dedicates to whichever resource the colony is
          most flooded with.
        """
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
            # else leave as None (mines stone)
        elif b.type == BuildingType.GATHERER:
            food = self._stock(world, Resource.FOOD)
            fiber = self._stock(world, Resource.FIBER)
            b.gatherer_output = (
                Resource.FOOD if food < fiber + 20 else Resource.FIBER
            )
        elif b.type == BuildingType.STORAGE:
            # Pick the resource we're closest to overflowing on;
            # falls back to WOOD if everything's empty.
            best_res = Resource.WOOD
            best_amt = -1.0
            for r in Resource:
                amt = self._stock(world, r)
                if amt > best_amt:
                    best_amt = amt
                    best_res = r
            b.stored_resource = best_res

    # ── Periodic producer reconfiguration ────────────────────────

    def _reconfigure_producers(self, world: World) -> None:
        """Re-pick ``quarry_output`` / ``gatherer_output`` on existing
        producers when the goal chain asks for a resource no current
        producer is set to.

        Without this, a colony that set all its quarries to STONE
        early on stays stuck on STONE forever — even after building
        a FORGE and researching metallurgy the quarries never switch
        to IRON/COPPER and the forge starves.  Reconfiguring mirrors
        how a player would click a quarry and change its output.
        """
        from compprog_pygame.games.hex_colony.procgen import Terrain
        # Make sure goal demand is fresh even if ``_try_build``
        # hasn't fired yet this tick (build and recipe intervals
        # don't perfectly align).
        if not self._goal_demand:
            my_pop, my_cap, worker_demand, _ = self._staffing_state(world)
            primary = self._pick_goal_building(
                world, my_pop, my_cap, worker_demand,
            )
            goals = self._collect_chain_goals(world, primary)
            if goals:
                _, _, self._goal_demand = self._goal_chain(world, goals)
        if not self._goal_demand:
            return

        # ── Quarries ─────────────────────────────────────────
        snap = self._snapshot(world)
        quarries = snap.by_type.get(BuildingType.QUARRY, ())
        gatherers = snap.by_type.get(BuildingType.GATHERER, ())
        for want in (Resource.IRON, Resource.COPPER):
            if self._goal_demand.get(want, 0.0) <= 0.0:
                continue
            if self._stock(world, want) >= 20:
                continue
            # Already have a quarry set to *want*?
            already = False
            candidate = None
            vein = (Terrain.IRON_VEIN if want == Resource.IRON
                    else Terrain.COPPER_VEIN)
            for b in quarries:
                if getattr(b, "quarry_output", None) == want:
                    already = True
                    break
                # Look for a quarry adjacent to the right vein.
                for nb in b.coord.neighbors():
                    tile = world.grid.get(nb)
                    if tile is not None and tile.terrain == vein:
                        candidate = b
                        break
            if already or candidate is None:
                continue
            candidate.quarry_output = want
            self._log(
                world,
                f"Reassigned QUARRY at "
                f"({candidate.coord.q},{candidate.coord.r}) to mine "
                f"{want.name.lower()} \u2014 chain for current goal "
                f"needs it.",
            )

        # ── Gatherers (FOOD ↔ FIBER) ─────────────────────────
        for want in (Resource.FIBER, Resource.FOOD):
            if self._goal_demand.get(want, 0.0) <= 0.0:
                continue
            if self._stock(world, want) >= 20:
                continue
            already = False
            candidate = None
            for b in gatherers:
                cur = getattr(b, "gatherer_output", None) or Resource.FOOD
                if cur == want:
                    already = True
                    break
                # FIBER needs an adjacent FIBER_PATCH; FOOD can be
                # reassigned anywhere (gatherers wander for FOOD).
                if want == Resource.FIBER:
                    for nb in b.coord.neighbors():
                        tile = world.grid.get(nb)
                        if (tile is not None
                                and tile.terrain == Terrain.FIBER_PATCH):
                            candidate = b
                            break
                else:
                    candidate = b
            if already or candidate is None:
                continue
            candidate.gatherer_output = want
            self._log(
                world,
                f"Reassigned GATHERER at "
                f"({candidate.coord.q},{candidate.coord.r}) to "
                f"{want.name.lower()} \u2014 chain needs it.",
            )

    def _stock(self, world: World, res: Resource) -> float:
        """Total of *res* across the colony's *entire* logistics
        network — every faction-owned building's storage, plus the
        flat ``colony.inventory`` pool (which for clankers should
        stay near-zero, but we count it for safety / parity with
        the player).

        This is the single source of truth the AI uses to decide
        whether it has a resource.  Critically, it sums **every**
        building's storage, not just the camp — otherwise planks
        sitting in a workshop or storage building are invisible
        and the AI keeps queuing more crafts forever.

        Result is cached per AI tick (cleared in :meth:`update`)
        because the goal-chain walker hits this dozens of times.
        """
        cached = self._stock_cache.get(res)
        if cached is not None:
            return cached
        snap = self._snapshot(world)
        total = float(self.colony.inventory[res])
        for b in snap.my_buildings:
            amt = b.storage.get(res, 0.0)
            if amt:
                total += float(amt)
        self._stock_cache[res] = total
        return total

    # ── Demolition / audit ───────────────────────────────────────

    def _demolish(self, world: World, building) -> None:
        """Tear down one of our buildings and refund it to the
        building inventory.  Mirrors the player's demolish path so
        workers/residents are detached cleanly.
        """
        from compprog_pygame.games.hex_colony.people import Task
        coord = building.coord
        tile = world.grid.get(coord)
        if tile is None or tile.building is not building:
            return
        # Detach any people referencing this building.
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
        # Refund the whole stockpiled building back — the AI was
        # the one who placed it, so it's a true do-over.
        self.colony.building_inventory.add(building.type)
        world.buildings.remove(building)
        tile.building = None
        world.mark_networks_dirty()
        world.mark_housing_dirty()
        self._invalidate_snapshot()

    def _audit_buildings(self, world: World) -> None:
        """Look at our resource buildings and demolish ones that are
        stuck — bad placement (no adjacent target terrain) or
        depleted (every nearby resource tile is exhausted).  Snapshot
        the list first so removal during iteration is safe.
        """
        from compprog_pygame.games.hex_colony import params as _p
        from compprog_pygame.games.hex_colony.supply_chain import (
            _hex_range,
        )
        # Buildings that don't consume / deplete the tile resource
        # they sit next to.  Farms grow food on any GRASS/WATER
        # adjacency and wells draw from WATER indefinitely, so the
        # "tile depleted" check below must not apply to them.
        _NON_DEPLETING: frozenset[BuildingType] = frozenset({
            BuildingType.FARM, BuildingType.WELL,
        })
        # Snapshot the list of *our* buildings — cheap via the
        # per-tick cache, and safe against removal during iteration
        # (``_demolish`` mutates the shared list).
        for b in list(self._snapshot(world).my_buildings):
            target_terrain = _terrain_for(b.type)
            if target_terrain is None:
                continue
            tile = world.grid.get(b.coord)
            on_target = (
                tile is not None and tile.terrain in target_terrain
            )
            # Count target-terrain neighbours that are *usable* — i.e.
            # not covered by another building.  A WOODCUTTER plopped
            # in the middle of town may have FOREST tiles touching it
            # on paper, but if every one of them has a house/path on
            # top it's effectively useless.
            count = 0
            for nb in b.coord.neighbors():
                nb_tile = world.grid.get(nb)
                if nb_tile is None:
                    continue
                if nb_tile.terrain not in target_terrain:
                    continue
                # A foreign building on the target tile blocks it.
                # Our own extractor already sitting on the tile
                # doesn't count as blocking here — we handle
                # "on_target" separately above.
                if (nb_tile.building is not None
                        and nb_tile.building is not b):
                    continue
                count += 1
            if count == 0 and not on_target:
                self._log(
                    world,
                    f"Demolishing {b.type.name} at "
                    f"({b.coord.q},{b.coord.r}) — no "
                    f"{self._terrain_label(b.type)} nearby.",
                )
                self._demolish(world, b)
                continue
            # Depletion check — for harvesters whose tiles auto-
            # retarget within COLLECTION_RADIUS.  Demolish only when
            # the building has been fully idle for an audit cycle
            # AND every reachable tile has 0 resource.  Skip this
            # for buildings that don't actually deplete tile
            # resources (FARM, WELL); they can be "inactive" for
            # reasons unrelated to the surrounding tiles (no path,
            # no workers) and we don't want to demolish them.
            if b.type in _NON_DEPLETING:
                continue
            if not getattr(b, "active", False) and b.workers > 0:
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
                        f"({b.coord.q},{b.coord.r}) — local "
                        f"{self._terrain_label(b.type)} depleted.",
                    )
                    self._demolish(world, b)

    # ── Research ─────────────────────────────────────────────────

    def _try_start_research(self, world: World) -> None:
        """If the colony's tech tree is idle, pick a node to research.

        Scoring favours nodes that:
        * Unlock buildings or resources (vs. pure passives).
        * Unlock something we don't already have access to.
        * Are cheap relative to our stockpile (won't stall).
        * Lead toward higher tiers (closer to root → more downstream).
        """
        tt = self.colony.tech_tree
        if tt.current_research is not None:
            return
        # Research requires a working RESEARCH_CENTER, exactly like
        # the player's flow.  Without this gate the AI can pick a
        # node and sink resources into it long before any building
        # is actually capable of delivering the research points.
        if not self._has_building(world, BuildingType.RESEARCH_CENTER):
            return
        candidates = tt.available_techs()
        if not candidates:
            return

        def score(key: str) -> float:
            node = TECH_NODES[key]
            unlocks = list(getattr(node, "unlocks", []) or [])
            unlock_resources = list(
                getattr(node, "unlock_resources", []) or [])
            # Strong bonus for unlocking a building we don't yet own.
            # ``node.unlocks`` is a list of BuildingType enum members
            # (resolved by tech_tree._build_tech_nodes), not strings.
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
            # Prefer foundational nodes: techs with shorter
            # prerequisite chains are scored higher so the AI
            # researches early-tier content before chasing deep
            # branches.  Players generally do the same naturally
            # because the deeper nodes are visually further out.
            depth_penalty = 6.0 * _tech_depth(key)
            # Penalise nodes whose cost we can't currently afford.
            cost = getattr(node, "cost", {}) or {}
            shortfall = 0.0
            for res_key, amt in cost.items():
                # cost keys may be Resource enums already.
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
                - depth_penalty
                - shortfall * 0.05
                - sum(cost.values()) / 200.0
                + self.rng.random() * 0.5
            )

        candidates.sort(key=score, reverse=True)
        choice = candidates[0]
        # Defensive double-check: players can only research a node
        # whose prerequisites are all satisfied.  ``available_techs``
        # already filters for this but re-verify at the start boundary
        # so the AI can never skip ahead if future refactors change
        # the filter's behaviour.
        if not tt.can_research(choice):
            return
        tt.start_research(choice)
        node = TECH_NODES[choice]
        unlocks = list(getattr(node, "unlocks", []) or [])
        unlock_resources = list(getattr(node, "unlock_resources", []) or [])
        what = []
        if unlocks:
            unlock_names = [
                getattr(b, "name", str(b)).replace("_", " ").title() for b in unlocks
            ]
            what.append(f"buildings: {', '.join(unlock_names)}")
        if unlock_resources:
            res_names = [
                getattr(r, "name", str(r)).replace("_", " ").title() for r in unlock_resources
            ]
            what.append(f"materials: {', '.join(res_names)}")
        suffix = f" ({'; '.join(what)})" if what else ""
        self._log(world, f"Researching {node.name}{suffix}.")

    # ── Workshop / Forge recipes ─────────────────────────────────

    def _set_recipes(self, world: World) -> None:
        """Assign a recipe to each idle crafting station owned by this
        clanker, picking valid recipes for that station type.

        Each station can craft either:
          * a :class:`BuildingType` (when ``BUILDING_RECIPE_STATION``
            says it belongs to that station), or
          * a :class:`Resource` material recipe whose ``station``
            field matches.

        Picker is *demand-aware*: it computes the set of resources
        that are bottlenecks for the buildings the colony wants to
        craft (e.g. when HABITAT stockpile is low and we have no
        IRON_BAR, FORGE will be steered toward IRON_BAR).  This lets
        the AI bootstrap its own production chains instead of randomly
        cranking out PLANK and stalling on missing intermediates.
        """
        from compprog_pygame.games.hex_colony.params import (
            BUILDING_RECIPE_STATION,
        )
        from compprog_pygame.games.hex_colony.resources import (
            MATERIAL_RECIPES, recipes_for_station,
        )

        # Buildings whose stockpile we'd like to top up.  Ordered so
        # earlier entries are higher priority.  Keeping this list
        # tight matters: if we flag *every* unlocked building for
        # stockpile we end up cranking hundreds of planks and
        # woodcutters instead of progressing tiers.  The rule is:
        #
        #   * Essentials (PATH, HABITAT, STORAGE) always.
        #   * The current goal building (goal chain's primary).
        #   * The next tier's unlocks_buildings list.
        #   * Crafting stations we're short on capacity for.
        #
        # Ambient top-up of extractors (WOODCUTTER/QUARRY/...) is
        # removed — we only need 1 on-hand; the build loop will
        # craft another when it's actually about to place one.
        wanted_buildings: list[BuildingType] = []
        STOCKPILE_CAP: int = 2

        def _want(bt: BuildingType) -> None:
            if bt in wanted_buildings:
                return
            if not self._is_unlocked(bt):
                return
            if self.colony.building_inventory[bt] >= STOCKPILE_CAP:
                return
            wanted_buildings.append(bt)

        # Essentials.
        for bt in (
            BuildingType.PATH, BuildingType.BRIDGE,
            BuildingType.HABITAT, BuildingType.STORAGE,
        ):
            _want(bt)

        # Tier-oriented goal + next-tier unlocks.
        my_pop, my_cap, worker_demand, _ = self._staffing_state(world)
        primary_goal = self._pick_goal_building(
            world, my_pop, my_cap, worker_demand,
        )
        if primary_goal is not None:
            _want(primary_goal)
        try:
            from compprog_pygame.games.hex_colony.tech_tree import (
                TIERS as _TIERS,
            )
            cur_tier_idx = self.colony.tier_tracker.current_tier
            if cur_tier_idx + 1 < len(_TIERS):
                for bt in (
                    getattr(
                        _TIERS[cur_tier_idx + 1],
                        "unlocks_buildings",
                        [],
                    ) or []
                ):
                    _want(bt)
        except Exception:
            pass

        # Crafting stations we genuinely want more of.
        for bt in (
            BuildingType.WORKSHOP, BuildingType.FORGE,
            BuildingType.REFINERY, BuildingType.ASSEMBLER,
            BuildingType.CHEMICAL_PLANT, BuildingType.OIL_REFINERY,
            BuildingType.RESEARCH_CENTER,
        ):
            # Only queue up a second copy of a station if we've
            # already placed one — stockpiling forges before we
            # even have iron is what leads to plank spam.
            if self._has_building(world, bt):
                _want(bt)
            elif self._has_input_supply(world, bt):
                _want(bt)

        def _material_unlocked(res: Resource) -> bool:
            tt = self.colony.tech_tree
            tier = self.colony.tier_tracker
            try:
                from compprog_pygame.games.hex_colony.tech_tree import (
                    is_resource_available,
                )
                return is_resource_available(res, tt, tier)
            except Exception:
                return True

        # ── Demand resolver ─────────────────────────────────────
        # Walk wanted_buildings → their recipe inputs → recursively
        # to material recipes, accumulating a "needed" count per
        # resource.  A resource is only "needed" if we don't already
        # have plenty of it stockpiled.
        STOCK_TARGET: dict[Resource, float] = {}
        # Tier-up target resources also feed into demand so the AI
        # actually progresses through tiers.
        try:
            from compprog_pygame.games.hex_colony.tech_tree import (
                TIERS as _TIERS,
            )
            cur_tier = self.colony.tier_tracker.current_tier
            if cur_tier + 1 < len(_TIERS):
                next_tier = _TIERS[cur_tier + 1]
                req = getattr(next_tier, "requirements", {}) or {}
                gathered = req.get("resource_gathered", {}) or {}
                for rname, amt in gathered.items():
                    try:
                        STOCK_TARGET[Resource[rname]] = max(
                            STOCK_TARGET.get(Resource[rname], 0.0),
                            float(amt) * 1.5,
                        )
                    except KeyError:
                        pass
        except Exception:
            pass

        # Per-resource minimum we want on hand.
        DEFAULT_TARGET = 30.0
        needed: dict[Resource, float] = {}

        def _add_demand(res: Resource, amount: float, depth: int = 0):
            if depth > 4 or amount <= 0:
                return
            target = max(STOCK_TARGET.get(res, DEFAULT_TARGET), amount)
            have = self._stock(world, res)
            short = max(0.0, target - have)
            if short <= 0:
                return
            needed[res] = needed.get(res, 0.0) + short
            # Recurse into a material recipe if this resource is
            # itself crafted (so the AI also lines up the inputs).
            mrec = MATERIAL_RECIPES.get(res)
            if mrec is None:
                return
            if not _material_unlocked(res):
                return
            for in_res, in_amt in mrec.inputs.items():
                _add_demand(
                    in_res, in_amt * short / max(1, mrec.output_amount),
                    depth + 1,
                )

        for bt in wanted_buildings:
            cost = BUILDING_COSTS.get(bt)
            if cost is None:
                continue
            for res, amt in cost.costs.items():
                _add_demand(res, float(amt))
        # Bake in tier-up demand directly even when no building uses
        # those materials yet (e.g. tier requires GATHERER FOOD count).
        for res, target in STOCK_TARGET.items():
            have = self._stock(world, res)
            if have < target:
                needed[res] = needed.get(res, 0.0) + (target - have)

        # Fold in goal-chain demand (computed by :meth:`_try_build`
        # via :meth:`_goal_chain`).  Weighted up so a station with
        # any goal-relevant output is preferred to one just topping
        # up ambient stockpiles.  This is the recipe side of the
        # long-term reasoning: if HABITAT is the goal, demand for
        # IRON_BAR → IRON → PLANKS all surface here even when those
        # resources weren't previously short.
        for res, amt in self._goal_demand.items():
            have = self._stock(world, res)
            short = max(0.0, amt * 1.5 - have)
            if short > 0:
                needed[res] = needed.get(res, 0.0) + short

        for b in self._snapshot(world).my_buildings:
            coord_key = (b.coord.q, b.coord.r)
            now = world.time_elapsed
            # Re-evaluate an existing recipe only if it's clearly the
            # wrong choice — and only after the recipe has been in
            # place long enough to actually have a chance of running.
            # Without the sticky window the AI thrashes: every cycle
            # the demand resolver computes a slightly different "best"
            # recipe and the station never produces anything.
            if b.recipe is not None:
                set_at = self._recipe_set_at.get(coord_key)
                age = (now - set_at) if set_at is not None else 1e9
                if age < _RECIPE_STICKY_TIME:
                    continue
                # Hard-ceiling escape hatch: a recipe that has been
                # set for 10× the sticky window with the station
                # making no progress is almost certainly jammed
                # (output buffer full, no consumer; or input buffer
                # empty, no producer).  Clear it unconditionally so
                # the picker below can reassign — preventing the
                # "workshop locked on PLANKS for 7000 s with
                # progress=0" bug seen in clanker_monitor logs.
                progress = float(getattr(b, "craft_progress", 0.0))
                if age >= _RECIPE_HARD_CEILING and progress <= 0.0:
                    self._log(
                        world,
                        f"Clearing stale {b.type.name} recipe "
                        f"({getattr(b.recipe, 'name', str(b.recipe))}) "
                        f"— no progress in {int(age)} s.",
                    )
                    b.recipe = None
                    self._recipe_set_at.pop(coord_key, None)
                # Materially-impossible escape hatch: if a Resource
                # recipe's inputs are nowhere in the colony AND we
                # have no producer for at least one of them, clear
                # after :data:`_RECIPE_IMPOSSIBLE_CEILING` instead
                # of waiting for the hard ceiling.  This is the
                # \"FORGE locked on COPPER_BAR with no copper\"
                # case — the recipe will never run, so don't tie up
                # the station for 10 minutes hoping it might.
                elif (isinstance(b.recipe, Resource)
                      and age >= _RECIPE_IMPOSSIBLE_CEILING
                      and progress <= 0.0):
                    mrec = MATERIAL_RECIPES.get(b.recipe)
                    if mrec is not None:
                        impossible = False
                        for in_res in mrec.inputs:
                            if self._stock(world, in_res) > 0.5:
                                continue
                            # Stock is zero — is anyone producing it?
                            producers = _RAW_PRODUCERS.get(in_res, ())
                            has_producer = False
                            for prod_bt, _need in producers:
                                if self._has_building(world, prod_bt):
                                    has_producer = True
                                    break
                            if not has_producer:
                                # Maybe a crafted intermediate?
                                in_mrec = MATERIAL_RECIPES.get(in_res)
                                if in_mrec is not None:
                                    station_name = getattr(
                                        in_mrec, "station", None,
                                    )
                                    if station_name:
                                        try:
                                            station_bt = BuildingType[
                                                station_name
                                            ]
                                            if self._has_building(
                                                    world, station_bt):
                                                has_producer = True
                                        except KeyError:
                                            pass
                            if not has_producer:
                                impossible = True
                                break
                        if impossible:
                            self._log(
                                world,
                                f"Clearing {b.type.name} recipe "
                                f"({b.recipe.name}) — input chain "
                                "unreachable.",
                            )
                            b.recipe = None
                            self._recipe_set_at.pop(coord_key, None)
                if b.recipe is not None and isinstance(b.recipe, BuildingType):
                    # Clear a building-recipe once the colony has
                    # stockpiled plenty of that building — no point
                    # tying up a workshop crafting more HABITATs
                    # when 10 are already sitting in inventory.
                    if (self.colony.building_inventory[b.recipe]
                            >= STOCKPILE_CAP * 2):
                        self._log(
                            world,
                            f"Clearing {b.type.name} recipe "
                            f"({b.recipe.name}) — already have "
                            f"{self.colony.building_inventory[b.recipe]} "
                            "stockpiled.",
                        )
                        b.recipe = None
                        self._recipe_set_at.pop(coord_key, None)
                if b.recipe is not None and isinstance(b.recipe, Resource):
                    out_held = b.storage.get(b.recipe, 0.0)
                    # Only clear when the output is full, no inputs are
                    # waiting, AND the colony already has plenty of
                    # this resource (no current demand).  Otherwise
                    # leave the recipe alone — workers will eventually
                    # pull from storage.
                    out_full = (
                        b.storage_capacity > 0
                        and out_held >= b.storage_capacity * 0.95
                    )
                    if out_full:
                        mrec = MATERIAL_RECIPES.get(b.recipe)
                        in_held = 0.0
                        if mrec is not None:
                            in_held = sum(
                                b.storage.get(r, 0.0) for r in mrec.inputs
                            )
                        no_demand = needed.get(b.recipe, 0.0) <= 0.0
                        if in_held < 0.5 and no_demand:
                            self._log(
                                world,
                                f"Clearing {b.type.name} recipe "
                                f"({b.recipe.name.lower()}) — output "
                                "is full, no inputs arriving, and the "
                                "colony has plenty stockpiled.",
                            )
                            b.recipe = None
                            self._recipe_set_at.pop(coord_key, None)
                if b.recipe is not None:
                    continue
            station_name = b.type.name
            valid_buildings: list[BuildingType] = [
                bt for bt in wanted_buildings
                if BUILDING_RECIPE_STATION.get(bt.name) == station_name
                and bt in BUILDING_COSTS
            ]
            valid_materials: list[Resource] = []
            for mr in recipes_for_station(station_name):
                if not _material_unlocked(mr.output):
                    continue
                have = self._stock(world, mr.output)
                if have >= 200:
                    continue
                valid_materials.append(mr.output)
            if not valid_buildings and not valid_materials:
                continue

            # ── Demand-driven choice ─────────────────────────────
            # 1. If any material recipe outputs a "needed" resource,
            #    prefer the one with highest demand.
            best_mat: Resource | None = None
            best_demand = 0.0
            for r in valid_materials:
                d = needed.get(r, 0.0)
                if d > best_demand:
                    best_demand = d
                    best_mat = r
            # 2. Otherwise, top up a low building stockpile.
            chosen: BuildingType | Resource | None = None
            if best_mat is not None and best_demand > 0:
                chosen = best_mat
            elif valid_buildings:
                # Bias toward buildings whose ALL inputs are now
                # available so the recipe actually completes.
                def _can_build(bt: BuildingType) -> bool:
                    cost = BUILDING_COSTS.get(bt)
                    if cost is None:
                        return False
                    for res, amt in cost.costs.items():
                        if self._stock(world, res) < amt:
                            return False
                    return True
                buildable = [bt for bt in valid_buildings if _can_build(bt)]
                if buildable:
                    pool = buildable
                    self.rng.shuffle(pool)
                    chosen = pool[0]
                else:
                    # None of the wanted building recipes have all
                    # inputs in stock.  Rather than locking the
                    # station onto a recipe it can't finish (e.g.
                    # workshop → HABITAT with no iron bars), see if
                    # this station can craft any of the missing
                    # inputs itself.  Pick the missing material with
                    # the largest shortfall so the chain unblocks
                    # fastest.
                    valid_mat_set = set(valid_materials)
                    shortfalls: dict[Resource, float] = {}
                    for bt in valid_buildings:
                        cost = BUILDING_COSTS.get(bt)
                        if cost is None:
                            continue
                        for res, amt in cost.costs.items():
                            if res not in valid_mat_set:
                                continue
                            if not _material_unlocked(res):
                                continue
                            have = self._stock(world, res)
                            short = max(0.0, float(amt) - have)
                            if short <= 0:
                                continue
                            shortfalls[res] = (
                                shortfalls.get(res, 0.0) + short
                            )
                    if shortfalls:
                        chosen = max(shortfalls.items(),
                                     key=lambda kv: kv[1])[0]
                    # If this station can't craft any of the missing
                    # inputs, leave the recipe unset so logistics
                    # still routes deliveries once upstream producers
                    # come online — better than stalling forever on
                    # an unreachable building recipe.
            elif valid_materials:
                # Falls back to keeping the station busy with
                # *something* unlocked (helps research-tier deliveries).
                pool_m = list(valid_materials)
                self.rng.shuffle(pool_m)
                chosen = pool_m[0]

            if chosen is None:
                continue
            b.recipe = chosen
            self._recipe_set_at[coord_key] = now
            label = (
                chosen.name if isinstance(chosen, BuildingType)
                else f"material {chosen.name.lower()}"
            )
            why = ""
            if isinstance(chosen, Resource) and needed.get(chosen, 0) > 0:
                why = (
                    f" (needed {int(needed[chosen])} units for "
                    "downstream recipes)"
                )
            self._log(
                world,
                f"Set {station_name} recipe to {label}{why}.",
            )


# ═══════════════════════════════════════════════════════════════════
#  Manager
# ═══════════════════════════════════════════════════════════════════

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

    def _locate_camp(self, faction_id: str, fallback: HexCoord) -> HexCoord:
        for b in self.world.buildings.by_type(BuildingType.TRIBAL_CAMP):
            if b.faction == faction_id:
                return b.coord
        return fallback

    def update(self, dt: float) -> None:
        for c in self.clankers:
            c.update(self.world, dt)
