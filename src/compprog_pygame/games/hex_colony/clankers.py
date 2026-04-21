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
# Sim-seconds between building audits (demolish misplaced buildings).
_AUDIT_INTERVAL: float = 15.0

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
    # Recent decisions, surfaced via the player's "Possess" panel so
    # the player can see *why* the AI is doing what it does.  Stored
    # as ``(sim_time, message)`` tuples, capped to the most recent
    # ``_LOG_MAXLEN`` entries.
    log: deque[tuple[float, str]] = field(
        default_factory=lambda: deque(maxlen=_LOG_MAXLEN),
    )

    # ── Logging ──────────────────────────────────────────────────

    def _log(self, world: World, msg: str) -> None:
        """Record a one-line justification for the player to read."""
        self.log.append((world.time_elapsed, msg))

    # ── Top-level update ─────────────────────────────────────────

    def update(self, world: World, dt: float) -> None:
        self.build_timer += dt
        self.research_timer += dt
        self.recipe_timer += dt
        self.audit_timer += dt
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

    # ── Helpers ──────────────────────────────────────────────────

    def _owned_coords(self, world: World) -> list[HexCoord]:
        """All coords currently occupied by this faction's buildings."""
        coords = [
            b.coord for b in world.buildings.buildings
            if getattr(b, "faction", "SURVIVOR") == self.faction_id
        ]
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
        return any(
            b.type == btype
            and getattr(b, "faction", "SURVIVOR") == self.faction_id
            for b in world.buildings.buildings
        )

    def _count_building(self, world: World, btype: BuildingType) -> int:
        return sum(
            1 for b in world.buildings.buildings
            if b.type == btype
            and getattr(b, "faction", "SURVIVOR") == self.faction_id
        )

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
        my_pop = 0
        for p in world.population.people:
            if (p.home is not None
                    and getattr(p.home, "faction", "SURVIVOR")
                    == self.faction_id):
                my_pop += 1
        housing_cap = 0
        worker_demand = 0
        workers_assigned = 0
        for b in world.buildings.buildings:
            if getattr(b, "faction", "SURVIVOR") != self.faction_id:
                continue
            housing_cap += BUILDING_HOUSING.get(b.type, 0)
            if b.type in _NON_WORKER_BTYPES:
                continue
            worker_demand += BUILDING_MAX_WORKERS.get(b.type, 0)
            workers_assigned += getattr(b, "workers", 0)
        return my_pop, housing_cap, worker_demand, workers_assigned

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

        choice = self._pick_building_to_place(world)
        if choice is None:
            return
        btype, target, reason = choice
        # If the picked target isn't already adjacent to our
        # territory, lay a path chain to it first \u2014 just like a
        # player would.  When PATH stock can't cover the run, abort
        # and let the workshop craft more next tick.
        if not self._is_adjacent_to_owned(world, target):
            if not self._lay_path_to(world, target):
                self._log(
                    world,
                    f"Wanted {btype.name} at ({target.q},{target.r}) "
                    f"but couldn't lay paths to reach it.",
                )
                return
        if self._place(world, btype, target):
            self._log(world, reason)

    def _pick_building_to_place(
        self, world: World,
    ) -> tuple[BuildingType, HexCoord, str] | None:
        """Walk priorities and return the first
        (building_type, coord, justification) we can act on."""
        camp = world.buildings.at(self.home)

        def stock(res: Resource) -> float:
            base = self.colony.inventory[res]
            if camp is not None:
                base += camp.storage.get(res, 0.0)
            return base

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

        # ── Priority 1: housing ─────────────────────────────────
        # Build housing whenever (a) pop is at/near cap, OR (b) we
        # already have unfilled jobs and need pop to grow into them.
        housing_pressure = (
            my_pop >= my_cap - 1
            or (worker_demand > my_pop and my_cap <= my_pop)
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
        for nb in coord.neighbors():
            b = world.buildings.at(nb)
            if (b is not None
                    and getattr(b, "faction", "SURVIVOR")
                    == self.faction_id):
                return True
        return False

    def _is_path_passable(
        self, world: World, coord: HexCoord,
    ) -> bool:
        """Can we lay a PATH on *coord* (or already have one there)?"""
        tile = world.grid.get(coord)
        if tile is None:
            return False
        if tile.terrain in UNBUILDABLE:
            return False
        b = tile.building
        if b is None:
            return True
        # Existing PATH that's ours \u2014 reuse it.
        return (b.type == BuildingType.PATH
                and getattr(b, "faction", "SURVIVOR") == self.faction_id)

    def _shortest_path_to(
        self, world: World, target: HexCoord,
    ) -> list[HexCoord] | None:
        """BFS over passable land from any of our buildings to a tile
        adjacent to *target*.  Returns the chain of *new* hexes that
        need a PATH placed on them (excludes already-owned tiles and
        the target itself), in order from nearest-owned outward.

        Returns ``None`` if no route exists within ``_MAX_PATH_RUN``.
        """
        owned = set(self._owned_coords(world))
        if not owned:
            return None
        # BFS frontier: tiles we can step onto that aren't owned yet.
        # Parent map lets us reconstruct the shortest chain.
        visited: set[HexCoord] = set(owned)
        parent: dict[HexCoord, HexCoord] = {}
        queue: deque[HexCoord] = deque()
        for o in owned:
            for nb in o.neighbors():
                if nb in visited:
                    continue
                if not self._is_path_passable(world, nb):
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
                if not self._is_path_passable(world, nb):
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
        return chain

    def _lay_path_to(self, world: World, target: HexCoord) -> bool:
        """Place a chain of PATH buildings so *target* becomes
        adjacent to our territory.  Returns True on success.

        Aborts (and places nothing) if we don't have enough PATH
        stockpile to cover the whole route \u2014 the workshop will
        craft more on the next ``_set_recipes`` tick.
        """
        chain = self._shortest_path_to(world, target)
        if chain is None:
            return False
        if not chain:
            # Already adjacent \u2014 nothing to lay.
            return True
        if self.colony.building_inventory[BuildingType.PATH] < len(chain):
            return False
        for coord in chain:
            tile = world.grid.get(coord)
            if tile is None or tile.building is not None:
                continue
            self.colony.building_inventory.spend(BuildingType.PATH)
            b = world.buildings.place(BuildingType.PATH, coord)
            b.faction = self.faction_id
            tile.building = b
        world.mark_networks_dirty()
        self._log(
            world,
            f"Laid {len(chain)} path tile(s) to reach "
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
        owned = set(self._owned_coords(world))
        if not owned:
            return None

        if target_terrain is None:
            # Non-resource building \u2014 cluster near owned territory.
            return self._find_adjacent_placement(world, btype)

        # Resource building \u2014 hunt for a hex adjacent to the right
        # terrain, anywhere in our radius.  Prefer hexes that are:
        #   * actually next to the target terrain (large bonus)
        #   * close to our existing footprint (cheaper path chain)
        #   * close to the camp (keeps the colony compact)
        candidates: list[tuple[float, HexCoord]] = []
        center = self.home
        for tile in world.grid.tiles():
            coord = tile.coord
            if coord.distance(center) > _MAX_EXPANSION_RADIUS:
                continue
            if tile.building is not None:
                continue
            if tile.terrain in UNBUILDABLE:
                if not (btype == BuildingType.OIL_DRILL
                        and tile.terrain.name == "OIL_DEPOSIT"):
                    continue
            # Count target-terrain hexes touching this tile.  The
            # tile itself counts double — standing right on a fiber
            # patch / forest / ore vein is the best possible spot.
            terrain_count = 0
            if tile.terrain in target_terrain:
                terrain_count += 2
            for nb in coord.neighbors():
                nb_tile = world.grid.get(nb)
                if (nb_tile is not None
                        and nb_tile.terrain in target_terrain):
                    terrain_count += 1
            if terrain_count == 0:
                continue
            # Distance to nearest owned tile (controls path cost).
            nearest_owned = min(coord.distance(o) for o in owned)
            if nearest_owned > _MAX_PATH_RUN + 1:
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
        return candidates[0][1]

    def _find_adjacent_placement(
        self, world: World, btype: BuildingType,
    ) -> HexCoord | None:
        """Original BFS-through-paths placement \u2014 used for buildings
        that don't care about terrain (housing, storage, workshops)."""
        owned = set(self._owned_coords(world))
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
        return candidates[0]

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
                amt = self.colony.inventory[r]
                if amt > best_amt:
                    best_amt = amt
                    best_res = r
            b.stored_resource = best_res

    def _stock(self, world: World, res: Resource) -> float:
        """Total of *res* across the colony's inventory + camp."""
        camp = world.buildings.at(self.home)
        base = self.colony.inventory[res]
        if camp is not None:
            base += camp.storage.get(res, 0.0)
        return base

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
        for b in list(world.buildings.buildings):
            if getattr(b, "faction", "SURVIVOR") != self.faction_id:
                continue
            target_terrain = _terrain_for(b.type)
            if target_terrain is None:
                continue
            tile = world.grid.get(b.coord)
            on_target = (
                tile is not None and tile.terrain in target_terrain
            )
            count = 0
            for nb in b.coord.neighbors():
                nb_tile = world.grid.get(nb)
                if (nb_tile is not None
                        and nb_tile.terrain in target_terrain):
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
            # AND every reachable tile has 0 resource.
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
        candidates = tt.available_techs()
        if not candidates:
            return

        def score(key: str) -> float:
            node = TECH_NODES[key]
            unlocks = list(getattr(node, "unlocks", []) or [])
            unlock_resources = list(
                getattr(node, "unlock_resources", []) or [])
            # Strong bonus for unlocking a building we don't yet own.
            bld_bonus = 0.0
            for bname in unlocks:
                try:
                    bt = BuildingType[bname]
                except KeyError:
                    continue
                if not self._has_building(world, bt):
                    bld_bonus += 30.0
                else:
                    bld_bonus += 5.0
            res_bonus = 8.0 * len(unlock_resources)
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
                - shortfall * 0.05
                - sum(cost.values()) / 200.0
                + self.rng.random() * 0.5
            )

        candidates.sort(key=score, reverse=True)
        choice = candidates[0]
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
        # earlier entries are higher priority.
        wanted_buildings: list[BuildingType] = []
        for btype in (
            BuildingType.PATH, BuildingType.HABITAT,
            BuildingType.STORAGE, BuildingType.WOODCUTTER,
            BuildingType.QUARRY, BuildingType.GATHERER,
            BuildingType.FARM, BuildingType.WELL,
            BuildingType.WORKSHOP, BuildingType.FORGE,
            BuildingType.RESEARCH_CENTER, BuildingType.REFINERY,
            BuildingType.ASSEMBLER, BuildingType.MINING_MACHINE,
            BuildingType.CHEMICAL_PLANT, BuildingType.OIL_DRILL,
            BuildingType.OIL_REFINERY, BuildingType.SOLAR_ARRAY,
            BuildingType.ROCKET_SILO,
        ):
            if (self._is_unlocked(btype)
                    and self.colony.building_inventory[btype] < 3):
                wanted_buildings.append(btype)

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

        for b in world.buildings.buildings:
            if getattr(b, "faction", "SURVIVOR") != self.faction_id:
                continue
            # Re-evaluate an existing recipe if it's clearly the
            # wrong choice — output bin is full and no inputs are
            # waiting, so the station is just sitting idle.
            if b.recipe is not None:
                if isinstance(b.recipe, Resource):
                    out_held = b.storage.get(b.recipe, 0.0)
                    if (b.storage_capacity > 0
                            and out_held >= b.storage_capacity * 0.95):
                        mrec = MATERIAL_RECIPES.get(b.recipe)
                        in_held = 0.0
                        if mrec is not None:
                            in_held = sum(
                                b.storage.get(r, 0.0) for r in mrec.inputs
                            )
                        if in_held < 0.5:
                            self._log(
                                world,
                                f"Clearing {b.type.name} recipe "
                                f"({b.recipe.name.lower()}) — output "
                                "is full and no inputs arriving.",
                            )
                            b.recipe = None
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
                have = self.colony.inventory[mr.output]
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
                pool = buildable or valid_buildings
                self.rng.shuffle(pool)
                chosen = pool[0]
            elif valid_materials:
                # Falls back to keeping the station busy with
                # *something* unlocked (helps research-tier deliveries).
                pool_m = list(valid_materials)
                self.rng.shuffle(pool_m)
                chosen = pool_m[0]

            if chosen is None:
                continue
            b.recipe = chosen
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
