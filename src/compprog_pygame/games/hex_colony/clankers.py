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
    BuildingType,
)
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
_MAX_EXPANSION_RADIUS: int = 12
# Maximum entries kept in a clanker's decision log.
_LOG_MAXLEN: int = 60
# Maximum length of a path chain the AI will lay to reach a remote
# resource hex.  Longer than this and we look for a closer site
# instead of spending a huge amount of PATH stockpile in one shot.
_MAX_PATH_RUN: int = 8

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
            BuildingType.WOODCUTTER: {Terrain.FOREST},
            BuildingType.QUARRY: {Terrain.STONE_DEPOSIT, Terrain.MOUNTAIN},
            BuildingType.GATHERER: {Terrain.FIBER_PATCH, Terrain.FOREST},
            BuildingType.FARM: {Terrain.WATER, Terrain.GRASS},
            BuildingType.WELL: {Terrain.WATER},
            BuildingType.MINING_MACHINE: {
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

        # ── Population ──────────────────────────────────────────
        my_pop = sum(
            1 for p in world.population.people
            if p.home is not None
            and getattr(p.home, "faction", "SURVIVOR") == self.faction_id
        )
        my_cap = sum(
            BUILDING_HOUSING.get(b.type, 0)
            for b in world.buildings.buildings
            if getattr(b, "faction", "SURVIVOR") == self.faction_id
        )

        # Priority 1: housing if pop is at/near cap.
        if my_pop >= my_cap - 1 and self._is_unlocked(BuildingType.HABITAT):
            if self._can_pay_for(BuildingType.HABITAT):
                target = self._find_placement(world, BuildingType.HABITAT)
                if target is not None:
                    return (
                        BuildingType.HABITAT, target,
                        f"Building HABITAT \u2014 housing {my_pop}/{my_cap} "
                        "is full, need room to grow.",
                    )

        # Priority 2: food security.
        if stock(Resource.FOOD) < 30 and my_pop > 3:
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

        # Priority 3: basic raw production.
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
                        f"{res.name.lower()} stock low ({int(stock(res))}).",
                    )

        # Priority 4: bring research online.
        if (not self._has_building(world, BuildingType.RESEARCH_CENTER)
                and self._is_unlocked(BuildingType.RESEARCH_CENTER)
                and self._can_pay_for(BuildingType.RESEARCH_CENTER)):
            target = self._find_placement(world, BuildingType.RESEARCH_CENTER)
            if target is not None:
                return (
                    BuildingType.RESEARCH_CENTER, target,
                    "Building RESEARCH_CENTER \u2014 need to start "
                    "researching tech to advance.",
                )

        # Priority 5: ensure crafting capacity.
        if (self._count_building(world, BuildingType.WORKSHOP) < 2
                and self._is_unlocked(BuildingType.WORKSHOP)
                and self._can_pay_for(BuildingType.WORKSHOP)):
            target = self._find_placement(world, BuildingType.WORKSHOP)
            if target is not None:
                return (
                    BuildingType.WORKSHOP, target,
                    "Building WORKSHOP \u2014 need crafting capacity "
                    "for planks and building stockpile.",
                )
        if (not self._has_building(world, BuildingType.FORGE)
                and self._is_unlocked(BuildingType.FORGE)
                and self._can_pay_for(BuildingType.FORGE)):
            target = self._find_placement(world, BuildingType.FORGE)
            if target is not None:
                return (
                    BuildingType.FORGE, target,
                    "Building FORGE \u2014 need metal-tier crafting.",
                )

        # Priority 6: storage for surplus.
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

        # Priority 7: tier-driven expansion \u2014 if we just unlocked
        # something new, plant one to start producing it.  Skip the
        # placeholder land-only types (PATH/BRIDGE/WALL) and the
        # rocket silo (one-shot win condition).
        for btype in _PLACEABLE:
            if btype in (BuildingType.PATH, BuildingType.BRIDGE,
                         BuildingType.WALL, BuildingType.ROCKET_SILO):
                continue
            if (self._is_unlocked(btype)
                    and self._can_pay_for(btype)
                    and not self._has_building(world, btype)):
                target = self._find_placement(world, btype)
                if target is not None:
                    return (
                        btype, target,
                        f"Building {btype.name} \u2014 newly unlocked, "
                        "trying it out.",
                    )

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
        for dq in range(-_MAX_EXPANSION_RADIUS, _MAX_EXPANSION_RADIUS + 1):
            for dr in range(-_MAX_EXPANSION_RADIUS, _MAX_EXPANSION_RADIUS + 1):
                coord = HexCoord(center.q + dq, center.r + dr)
                if coord.distance(center) > _MAX_EXPANSION_RADIUS:
                    continue
                tile = world.grid.get(coord)
                if tile is None or tile.building is not None:
                    continue
                if tile.terrain in UNBUILDABLE:
                    if not (btype == BuildingType.OIL_DRILL
                            and tile.terrain.name == "OIL_DEPOSIT"):
                        continue
                # Count target-terrain hexes touching this tile.
                terrain_count = 0
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
        world.mark_networks_dirty()
        world.mark_housing_dirty()
        return True

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
        """Look at our resource buildings and demolish ones placed
        on bad spots (no adjacent target terrain).  Snapshot the list
        first so removal during iteration is safe.
        """
        for b in list(world.buildings.buildings):
            if getattr(b, "faction", "SURVIVOR") != self.faction_id:
                continue
            target_terrain = _terrain_for(b.type)
            if target_terrain is None:
                continue
            # Count adjacent target-terrain hexes.
            count = 0
            for nb in b.coord.neighbors():
                nb_tile = world.grid.get(nb)
                if (nb_tile is not None
                        and nb_tile.terrain in target_terrain):
                    count += 1
            if count == 0:
                self._log(
                    world,
                    f"Demolishing {b.type.name} at "
                    f"({b.coord.q},{b.coord.r}) — no "
                    f"{self._terrain_label(b.type)} nearby.",
                )
                self._demolish(world, b)

    # ── Research ─────────────────────────────────────────────────

    def _try_start_research(self, world: World) -> None:
        """If the colony's tech tree is idle, pick a node to research."""
        tt = self.colony.tech_tree
        if tt.current_research is not None:
            return
        candidates = tt.available_techs()
        if not candidates:
            return

        def score(key: str) -> float:
            node = TECH_NODES[key]
            unlock_bonus = 10.0 if (
                getattr(node, "unlocks", None)
                or getattr(node, "unlock_resources", None)
            ) else 0.0
            cost_total = sum(node.cost.values()) if node.cost else 0.0
            return unlock_bonus - cost_total / 100.0

        candidates.sort(key=score, reverse=True)
        choice = candidates[0]
        tt.start_research(choice)
        node = TECH_NODES[choice]
        self._log(world, f"Researching {node.name} \u2014 picks up new content.")

    # ── Workshop / Forge recipes ─────────────────────────────────

    def _set_recipes(self, world: World) -> None:
        """Assign a recipe to each idle crafting station owned by this
        clanker, picking valid recipes for that station type.

        Each station can craft either:
          * a :class:`BuildingType` (when ``BUILDING_RECIPE_STATION``
            says it belongs to that station), or
          * a :class:`Resource` material recipe whose ``station``
            field matches.

        Setting a recipe a station can't actually run is a no-op
        (``_tick_building_recipe`` clears it next frame), so we filter
        candidates by station type up-front.  When the colony's
        building stockpile is healthy we keep the workshops crafting
        intermediate materials so feedstock for *future* building
        recipes accumulates \u2014 just like a player would.
        """
        from compprog_pygame.games.hex_colony.params import (
            BUILDING_RECIPE_STATION,
        )
        from compprog_pygame.games.hex_colony.resources import (
            MATERIAL_RECIPES, recipes_for_station,
        )

        # Buildings whose stockpile we'd like to top up.  Keep the list
        # ordered by importance so the rng.choice below biases toward
        # things the AI is genuinely short on.
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

        # Material recipes the AI might want for crafting feedstock.
        # We always consider them so workshops keep busy even when the
        # building stockpile is full.
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

        for b in world.buildings.buildings:
            if getattr(b, "faction", "SURVIVOR") != self.faction_id:
                continue
            # Re-evaluate an existing recipe if it's clearly the
            # wrong choice — output bin is full and no inputs are
            # waiting, so the station is just sitting idle.  Clearing
            # the recipe here lets the picker below try something
            # different (e.g. swap a flooded "PLANK" recipe for a
            # building recipe the colony actually needs).
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
            # Building recipes this station can craft.
            valid_buildings: list[BuildingType] = [
                bt for bt in wanted_buildings
                if BUILDING_RECIPE_STATION.get(bt.name) == station_name
                and bt in BUILDING_COSTS
            ]
            # Material recipes this station can run.  Skip materials
            # we already have a heavy stockpile of — no point
            # cranking out yet more planks if we're drowning in them.
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
            # 60% chance to top up a low building stockpile when one
            # is available; otherwise (or when no building qualifies)
            # craft a material so feedstock keeps flowing.
            choices: list[BuildingType | Resource] = []
            if valid_buildings and (
                not valid_materials or self.rng.random() < 0.6
            ):
                choices = list(valid_buildings)
            else:
                choices = list(valid_materials)
            self.rng.shuffle(choices)
            b.recipe = choices[0]
            label = (
                choices[0].name if isinstance(choices[0], BuildingType)
                else f"material {choices[0].name.lower()}"
            )
            self._log(
                world,
                f"Set {station_name} recipe to {label}.",
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
