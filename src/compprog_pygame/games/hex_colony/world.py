"""World generation for Hex Colony.

Creates the initial hex map with terrain and resources, places the starting
camp, and spawns the initial population.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

from compprog_pygame.games.hex_colony.buildings import (
    Building, BuildingManager, BuildingType,
    BUILDING_COSTS, BUILDING_HARVEST_RESOURCES, BUILDING_MAX_WORKERS,
)
from compprog_pygame.games.hex_colony.hex_grid import HexCoord, HexGrid, Terrain
from compprog_pygame.games.hex_colony.people import PopulationManager, Task
from compprog_pygame.games.hex_colony.procgen import generate_terrain, UNBUILDABLE
from compprog_pygame.games.hex_colony.resources import (
    BuildingInventory, FLUID_RESOURCES, Inventory, MATERIAL_RECIPES,
    Resource, TERRAIN_RESOURCE,
)
from compprog_pygame.games.hex_colony.settings import HexColonySettings
from compprog_pygame.games.hex_colony.supply_chain import _hex_range
from compprog_pygame.games.hex_colony.tech_tree import TECH_NODES
from compprog_pygame.games.hex_colony import params
from compprog_pygame.games.hex_colony.strings import (
    building_label,
    NOTIF_NEW_COLONIST,
    NOTIF_UNREACHABLE,
)


# Buildings that can produce, consume, or buffer a fluid resource.
# Fluid networks are formed by BFS over PIPE tiles and these buildings;
# a building only counts as "fluid-capable" if it appears in this set
# (so e.g. Habitats don't accidentally join a pipe network).
FLUID_CAPABLE_BUILDINGS: frozenset[BuildingType] = frozenset({
    BuildingType.OIL_DRILL,        # produces OIL
    BuildingType.OIL_REFINERY,     # consumes OIL, produces PETROLEUM/LUBRICANT
    BuildingType.CHEMICAL_PLANT,   # consumes PETROLEUM, produces ROCKET_FUEL/RUBBER
    BuildingType.FLUID_TANK,       # buffers a single fluid
    BuildingType.ROCKET_SILO,      # consumes ROCKET_FUEL
    BuildingType.MINING_MACHINE,   # can run on PETROLEUM
    BuildingType.RESEARCH_CENTER,  # consumes ROCKET_FUEL for late research
})


# Per-building map of which fluids each producer NATIVELY OUTPUTS.
# Drives :func:`_is_fluid_producer` so the fluid balancer can drain
# producers into sinks first instead of distributing evenly across the
# whole network (which would silently destroy mass when a producer's
# slot is smaller than the actual storage it drew from).
_FLUID_PRODUCER_OUTPUTS: dict[BuildingType, frozenset] = {}


def _is_fluid_producer(b: "Building", fluid) -> bool:
    """Return True if *b* natively produces *fluid* as an output."""
    # Lazy import-time wiring of the producer map (avoids forward refs).
    if not _FLUID_PRODUCER_OUTPUTS:
        from compprog_pygame.games.hex_colony.resources import Resource as _R
        _FLUID_PRODUCER_OUTPUTS[BuildingType.OIL_DRILL] = frozenset({_R.OIL})
        _FLUID_PRODUCER_OUTPUTS[BuildingType.OIL_REFINERY] = frozenset({
            _R.PETROLEUM, _R.LUBRICANT,
        })
        _FLUID_PRODUCER_OUTPUTS[BuildingType.CHEMICAL_PLANT] = frozenset({
            _R.ROCKET_FUEL, _R.LUBRICANT,
        })
    outs = _FLUID_PRODUCER_OUTPUTS.get(b.type)
    if outs is None:
        return False
    return fluid in outs


@dataclass
class Network:
    """A path-connected group of buildings with an independent worker
    priority queue.  Two buildings belong to the same network when
    there's an unbroken chain of adjacent buildings between them (any
    building type counts, matching how housing connectivity works).

    Each network has a stable, monotonically-assigned ``id`` so that its
    priority queue survives across recomputations even as buildings are
    placed or removed.  When two networks merge (e.g. the player bridges
    a gap), the surviving network inherits zipped priority tiers from
    both parents.  When a network splits, the largest fragment keeps
    the id and the smaller ones receive freshly-allocated ids.
    """
    id: int
    buildings: list[Building] = field(default_factory=list)
    priority: list[list[Building]] = field(default_factory=list)
    # Identity-set for fast ``b in network`` checks.  Populated
    # alongside ``buildings`` — callers should not mutate directly.
    _bids: set[int] = field(default_factory=set)
    # Number of workers the player has allocated to the always-present
    # "Logistics" slot for this network.  Survives rebuilds in the same
    # way priority tiers do (persisted across components by id).
    logistics_target: int = 0
    # Per-building delivery-demand tiers.  Higher tiers receive
    # logistics deliveries first; within a tier, demand is split evenly
    # across all member buildings.  When ``demand_auto`` is True the
    # tiers are recomputed automatically on every rebuild (non-storage
    # buildings on tier 0, storage buildings on tier 1).
    demand_priority: list[list[Building]] = field(default_factory=list)
    demand_auto: bool = True
    # Per-building supply tiers: higher tiers are drawn from FIRST
    # when satisfying a demand.  Same auto/manual model as
    # ``demand_priority``: auto puts producers (and other non-storage
    # suppliers) on tier 0, storage on tier 1.
    supply_priority: list[list[Building]] = field(default_factory=list)
    supply_auto: bool = True
    # Worker-priority auto mode: when True, all worker-buildings are
    # placed in a single tier and ``logistics_target`` is automatically
    # computed as ``floor(building_count / 3)``.
    worker_auto: bool = True

    @property
    def name(self) -> str:
        return f"Network {self.id}"

    def contains(self, b: Building) -> bool:
        return id(b) in self._bids


@dataclass
class FluidNetwork:
    """A pipe-connected group of fluid-capable buildings.

    Built by BFS over PIPE tiles plus any
    :data:`FLUID_CAPABLE_BUILDINGS` adjacent to them.  Each tick the
    world balances every fluid type within the network: the total
    surplus held by producers (above their internal recipe needs) is
    redistributed to demanders (consumers + tanks) up to their free
    capacity.  Pipes themselves hold no resources — they're pure
    connectors.
    """
    id: int
    buildings: list[Building] = field(default_factory=list)
    pipes: list[Building] = field(default_factory=list)


class World:
    """Top-level game-state container."""

    def __init__(self, settings: HexColonySettings) -> None:
        self.settings = settings
        self.seed: str = "default"
        self.grid = HexGrid()
        self.buildings = BuildingManager()
        self.population = PopulationManager()
        self.inventory = Inventory()
        self.building_inventory = BuildingInventory()
        self.time_elapsed: float = 0.0
        self.real_time_elapsed: float = 0.0
        # Cumulative resources produced by buildings (harvested/crafted).
        # Separate from ``Inventory.total_produced`` which only counts
        # resources that pass through the global pool.
        self._total_produced: dict[Resource, float] = {r: 0.0 for r in Resource}
        self._housing_dirty: bool = True  # needs recalc on first frame
        # Networks only need rebuilding when buildings are added,
        # removed, or destroyed — population shifts alone don't change
        # the building-graph topology.  Default True so the first frame
        # always builds them.
        self._networks_dirty: bool = True
        # Monotonically increasing counter that ticks every time the
        # building topology changes (placement / deletion).  Used by
        # the UI / renderer to invalidate per-route BFS caches without
        # re-running the search every frame.
        self._topology_version: int = 0
        # Round-robin offset for throttling ``_logistics_find_job`` —
        # only a small slice of idle logistics workers re-scan the
        # network each frame so 50+ haulers don't all run the
        # O(buildings²) supplier/demand scan in the same tick.
        self._logistics_search_cursor: int = 0
        # Tracks the simulation time at which a delivery was last
        # *assigned* to each ``(id(building), resource)`` consumer
        # pair.  Used by ``_logistics_find_job`` to bias scoring
        # toward the longest-starved consumer in the active demand
        # tier so that one popular building does not monopolise the
        # haulers while siblings in the same tier wait indefinitely.
        self._demand_last_served: dict[tuple[int, object], float] = {}
        # Per-update BFS path cache.  Keys are ``(start, end)`` hex
        # coordinate pairs; values are the cached path (a fresh copy
        # is returned to callers so they can mutate it freely).
        # Cleared at the top of every ``update()``.
        self._path_cache: dict[tuple[HexCoord, HexCoord], list[HexCoord]] = {}
        # Per-building-network worker priority lists.  ``networks`` is
        # rebuilt only when ``_networks_dirty`` is set; each Network
        # keeps its own tier list so the player can edit them
        # independently in the UI.
        self.networks: list[Network] = []
        self._next_network_id: int = 1
        # Pipe-based fluid networks (parallel to self.networks).
        # Rebuilt whenever the topology changes.  Fluids never travel
        # through worker logistics — only through these networks.
        self.fluid_networks: list[FluidNetwork] = []
        self._next_fluid_network_id: int = 1
        # Per-frame caches rebuilt by ``_rebuild_networks``.  Used by
        # the hot logistics / housing / unreachable-check loops to
        # avoid repeatedly scanning ``self.buildings.buildings`` (a
        # potentially large list) and ``self.networks`` (a small but
        # non-trivial list).  Both are keyed by ``id(building)``.
        self._bid_to_network: dict[int, Network] = {}
        self._valid_bids: set[int] = set()
        # Set of network ids that contain at least one populated
        # dwelling.  Recomputed each frame in ``update`` so the two
        # callers (``_refresh_unreachable_caches`` and
        # ``unreachable_buildings``) don't each scan the population.
        self._populated_net_ids: set[int] = set()
        # Buildings we've already notified the player are unreachable
        # (no path from any populated house).  Tracked by ``id(b)`` so
        # the warning pushes exactly once per newly-stranded building.
        self._unreachable_notified: set[int] = set()
        # Optional NotificationManager plugged in by game.py for
        # one-time toasts like "No workers can reach X".
        self.notifications: object | None = None
        # Optional TechTree reference plugged in by game.py so the
        # research center can post per-resource demand for whatever
        # research is currently active.
        self.tech_tree: object | None = None
        # Tiles whose terrain just changed because their resource ran
        # out.  The renderer drains this set each frame to clear the
        # static overlay sprites (trees, stones, ore crystals) on top
        # of the depleted hex and refresh the blended-colour cache so
        # the tile blends with neighbouring grass.
        self.pending_depleted_tiles: set[HexCoord] = set()
        # Worker-assignment is one of the heaviest per-frame passes
        # (O(B*P) per network).  We only need to redo it when the
        # population set changes, networks are rebuilt, or the player
        # edits priorities.  Otherwise a low-frequency refresh keeps
        # production targets responsive without paying the cost every
        # frame.
        self._workers_dirty: bool = True
        self._workers_refresh_accum: float = 0.0
        # Throttle for ``_refresh_unreachable_caches`` and the
        # cached ``unreachable_buildings`` / ``starved_producers``
        # queries the renderer asks for every frame.
        self._unreachable_accum: float = 0.0
        self._unreachable_cache: set[int] = set()
        self._starved_cache: set[int] = set()

    @property
    def worker_priority(self) -> list[list[Building]]:
        """Flat view of every network's tier list — convenience used by
        legacy code paths and tests.  Mutating the returned structure
        does not feed back into ``networks``; edit ``Network.priority``
        directly instead."""
        flat: list[list[Building]] = []
        for net in self.networks:
            flat.extend(net.priority)
        return flat

    @property
    def game_over(self) -> bool:
        """The mission is lost when all survivors are dead."""
        return self.population.count == 0 and self.time_elapsed > 0

    def total_produced(self, res: Resource) -> float:
        """Cumulative resources produced by all buildings (harvested/crafted)."""
        return self._total_produced.get(res, 0.0)

    # ── Generation ───────────────────────────────────────────────

    @classmethod
    def generate(
        cls, settings: HexColonySettings, seed: str = "default",
        progress_callback=None,
    ) -> World:
        """Build a fully-populated world.

        *progress_callback*, if provided, is invoked as
        ``cb(fraction, label)`` with ``fraction`` in [0.0, 1.0] as
        terrain generation makes progress.  Safe to call from a
        background thread.
        """
        world = cls(settings)
        world.seed = seed
        world.grid, ai_camp_coords = generate_terrain(
            seed, settings, progress_callback=progress_callback,
        )
        world._place_starting_camp()
        world._place_ai_tribal_camps(ai_camp_coords)
        world._init_resources()
        world._init_building_inventory()
        world._spawn_people()
        return world

    def _place_starting_camp(self) -> None:
        origin = HexCoord(0, 0)
        camp = self.buildings.place(BuildingType.CAMP, origin)
        tile = self.grid[origin]
        tile.building = camp
        # Crashed spaceship stores multiplied starting resources
        s = self.settings
        m = params.CAMP_STORAGE_MULTIPLIER
        camp.storage = {
            Resource.WOOD: float(s.start_wood * m),
            Resource.FIBER: float(s.start_fiber * m),
            Resource.STONE: float(s.start_stone * m),
            Resource.FOOD: float(s.start_food * m),
            Resource.IRON: float(params.START_IRON),
            Resource.COPPER: float(params.START_COPPER),
        }
        camp.storage_capacity = max(
            params.BUILDING_STORAGE_CAMP,
            sum(v * m for v in (s.start_wood, s.start_fiber,
                                s.start_stone, s.start_food))
            + params.START_IRON + params.START_COPPER,
        )

    def _place_ai_tribal_camps(self, coords: list[HexCoord]) -> None:
        """Place a primitive AI tribe camp at each given coordinate.

        Each camp belongs to its own ``"PRIMITIVE_<i>"`` tribe so future
        AI logic can treat them as independent factions.  If the target
        tile is unbuildable (water/mountain), the nearest passable hex
        within a small radius is used as a fallback.
        """
        for i, coord in enumerate(coords):
            target = coord
            tile = self.grid.get(target)
            # Slide off impassable tiles to the nearest valid hex.
            if tile is None or tile.terrain in UNBUILDABLE or tile.building is not None:
                for radius in range(1, 6):
                    found = False
                    for q in range(-radius, radius + 1):
                        for r in range(max(-radius, -q - radius),
                                       min(radius, -q + radius) + 1):
                            cand = HexCoord(coord.q + q, coord.r + r)
                            ct = self.grid.get(cand)
                            if (ct is not None
                                    and ct.terrain not in UNBUILDABLE
                                    and ct.building is None):
                                target = cand
                                tile = ct
                                found = True
                                break
                        if found:
                            break
                    if found:
                        break
            if tile is None:
                continue
            camp = self.buildings.place(BuildingType.TRIBAL_CAMP, target)
            camp.faction = f"PRIMITIVE_{i}"
            tile.building = camp

    def _init_resources(self) -> None:
        s = self.settings
        self.inventory[Resource.WOOD] = s.start_wood
        self.inventory[Resource.FIBER] = s.start_fiber
        self.inventory[Resource.STONE] = s.start_stone
        self.inventory[Resource.FOOD] = s.start_food
        self.inventory[Resource.IRON] = params.START_IRON
        self.inventory[Resource.COPPER] = params.START_COPPER

    def _init_building_inventory(self) -> None:
        """Give the player their starting buildings."""
        for name, count in params.START_BUILDINGS.items():
            btype = BuildingType[name]
            self.building_inventory.add(btype, count)

    def _spawn_people(self) -> None:
        origin = HexCoord(0, 0)
        camp = self.buildings.at(origin)
        for _ in range(self.settings.start_population):
            p = self.population.spawn(origin, self.settings.hex_size)
            # Initial assignment handled by _update_housing in first update
            if camp is not None:
                p.home = camp
                camp.residents += 1

    # ── Per-frame update ─────────────────────────────────────────

    def update(self, dt: float) -> None:
        """Advance the simulation by *dt* seconds."""
        self.time_elapsed += dt
        # Clear the per-update BFS path cache.  Building topology
        # cannot change mid-update, so any path computed during this
        # tick can be safely shared between callers.
        self._path_cache.clear()

        # Recompute connected housing only when buildings/population changed
        if self._housing_dirty:
            self._update_housing()
            self._housing_dirty = False

        # Networks track the building-graph topology.  Only rebuild
        # when buildings have actually been placed/removed — the
        # full BFS+merge pass is expensive once there are many
        # buildings.
        if self._networks_dirty:
            self._rebuild_networks()
            self._rebuild_fluid_networks()
            self._networks_dirty = False
        # ``_populated_net_ids`` depends on people's home assignments
        # (which can shift between rebuilds), so refresh it every
        # frame — this is a cheap O(people) pass.
        self._refresh_populated_net_ids()

        # ``_assign_workers`` is the heaviest per-frame pass.  Run it
        # only when something changed (housing rebuild, network
        # rebuild, player priority edit, population change) or once
        # per ~500 ms to keep effective_worker_demand responsive to
        # stockpile shifts.
        self._workers_refresh_accum += dt
        if self._workers_dirty or self._workers_refresh_accum >= 0.5:
            self._assign_workers()
            self._dispatch_commuters()
            self._workers_dirty = False
            self._workers_refresh_accum = 0.0

        # Farm & Refinery production
        self._update_production(dt)

        # Workshop crafting
        self._update_workshops(dt)

        # Fluid balancing through pipe networks (oil/petroleum/etc.).
        self._update_fluids(dt)

        # Logistics dispatch (runs before population.update so newly
        # assigned paths are walked this same frame).
        self._update_logistics(dt)

        # Move people
        self.population.update(dt, self, self.settings.hex_size)

        # Natural population growth from well-fed, spacious dwellings.
        self._update_population_growth(dt)

        # Finally, recount present workers (must be AFTER movement so
        # newly-arrived commuters are credited this frame).
        self._recount_present_workers()
        # Unreachable / starved checks only need to run at human-
        # noticeable rates (~2 Hz).  The cached id-sets are reused by
        # the renderer every frame.
        self._unreachable_accum += dt
        if self._unreachable_accum >= 0.5:
            self._unreachable_accum = 0.0
            self._refresh_unreachable_caches()

    def mark_housing_dirty(self) -> None:
        """Flag that housing assignments need recalculation.

        Building placements / removals always change both housing
        connectivity and the network graph, so this also flags
        networks for a rebuild on the next ``update()``.
        """
        self._housing_dirty = True
        self._networks_dirty = True
        self._workers_dirty = True
        self._topology_version += 1

    def mark_networks_dirty(self) -> None:
        """Flag that the network/component graph needs rebuilding."""
        self._networks_dirty = True
        self._workers_dirty = True
        self._topology_version += 1

    def mark_population_changed(self) -> None:
        """Flag that people were added or removed.  Triggers a housing
        reassignment and a worker re-allocation but *not* a network
        rebuild — births / deaths don't change the building topology.
        """
        self._housing_dirty = True
        self._workers_dirty = True

    def _refresh_populated_net_ids(self) -> None:
        """Recompute the set of network ids that house at least one
        person.  Cheap O(people) pass run every frame so the dependent
        unreachable-building checks see up-to-date data even when
        ``_rebuild_networks`` was skipped."""
        self._populated_net_ids = {
            net.id
            for p in self.population.people
            if p.home is not None
            and (net := self._bid_to_network.get(id(p.home))) is not None
        }

    # ── Networks ─────────────────────────────────────────────────

    def _compute_components(self) -> list[list[Building]]:
        """Return the list of path-connected building components.

        Two buildings are in the same component when there's a chain of
        adjacent buildings between them — matching the way housing
        connectivity works.  Every placed building appears in exactly
        one component.  Order within a component follows BFS order for
        determinism, not for any gameplay reason.
        """
        all_buildings = list(self.buildings.buildings)
        by_coord: dict[HexCoord, Building] = {
            b.coord: b for b in all_buildings
        }
        visited: set[int] = set()
        components: list[list[Building]] = []
        for seed in all_buildings:
            if id(seed) in visited:
                continue
            comp: list[Building] = []
            queue: deque[Building] = deque([seed])
            visited.add(id(seed))
            while queue:
                cur = queue.popleft()
                comp.append(cur)
                for nb in cur.coord.neighbors():
                    nb_b = by_coord.get(nb)
                    if nb_b is None or id(nb_b) in visited:
                        continue
                    visited.add(id(nb_b))
                    queue.append(nb_b)
            components.append(comp)
        return components

    def _rebuild_networks(self) -> None:
        """Match current components to existing networks by majority of
        member buildings, preserving ids and each network's priority.

        * A component whose buildings are all in the same old network
          keeps that network's id (same network, possibly shrunk).
        * A component that unions multiple old networks inherits the
          id of the old network contributing the most buildings; tier
          lists are zipped (tier-k = concat of parent tier-ks filtered
          to current members).
        * A component with no old-network overlap gets a fresh id.
        * A new buildings (no old network) are appended as singleton
          tiers at the end of their component's priority list.
        """
        components = self._compute_components()
        # Map each building → its old network id (if any).
        old_net_by_bid: dict[int, int] = {}
        old_nets: dict[int, Network] = {n.id: n for n in self.networks}
        for n in self.networks:
            for b in n.buildings:
                old_net_by_bid[id(b)] = n.id

        # Choose a new id for each component: majority of members'
        # old ids; ties broken by smallest id; empty → fresh.  Also
        # ensure no two components share the same new id — if two
        # components both "want" id X, the larger wins and the smaller
        # gets a fresh id (a split).
        claimed: dict[int, tuple[int, int]] = {}  # old_id -> (comp_idx, size)
        picks: list[int | None] = [None] * len(components)
        for ci, comp in enumerate(components):
            counts: dict[int, int] = {}
            for b in comp:
                oid = old_net_by_bid.get(id(b))
                if oid is not None:
                    counts[oid] = counts.get(oid, 0) + 1
            if not counts:
                continue
            # Pick highest count, ties → smallest id.
            best_id = min(counts, key=lambda k: (-counts[k], k))
            prev = claimed.get(best_id)
            size = len(comp)
            if prev is None or size > prev[1]:
                if prev is not None:
                    picks[prev[0]] = None  # evict smaller
                claimed[best_id] = (ci, size)
                picks[ci] = best_id

        # Assign fresh ids to unclaimed components.
        used_ids = set(claimed)
        new_networks: list[Network] = []
        for ci, comp in enumerate(components):
            comp_ids: set[int] = {id(b) for b in comp}
            net_id = picks[ci]
            if net_id is None:
                while self._next_network_id in used_ids:
                    self._next_network_id += 1
                net_id = self._next_network_id
                self._next_network_id += 1
                used_ids.add(net_id)

            # Gather parent networks that contributed buildings.
            parent_ids: list[int] = []
            seen_p: set[int] = set()
            for b in comp:
                oid = old_net_by_bid.get(id(b))
                if oid is not None and oid not in seen_p:
                    seen_p.add(oid)
                    parent_ids.append(oid)
            # Put the surviving parent first so its tiers anchor.
            if net_id in parent_ids:
                parent_ids.remove(net_id)
                parent_ids.insert(0, net_id)

            # Build priority: zip parent tiers by index, then filter to
            # current comp members, preserving left-to-right order.
            tier_lists: list[list[list[Building]]] = [
                old_nets[pid].priority for pid in parent_ids
                if pid in old_nets
            ]
            max_depth = max((len(tl) for tl in tier_lists), default=0)
            new_priority: list[list[Building]] = []
            placed_bids: set[int] = set()
            for k in range(max_depth):
                merged: list[Building] = []
                for tl in tier_lists:
                    if k < len(tl):
                        for b in tl[k]:
                            if id(b) in comp_ids and id(b) not in placed_bids:
                                merged.append(b)
                                placed_bids.add(id(b))
                if merged:
                    new_priority.append(merged)
            # Append buildings new to this network as singleton tiers
            # (in placement order — buildings.buildings is append-only).
            for b in self.buildings.buildings:
                if id(b) not in comp_ids:
                    continue
                if BUILDING_MAX_WORKERS.get(b.type, 0) <= 0:
                    continue
                if id(b) in placed_bids:
                    continue
                new_priority.append([b])
                placed_bids.add(id(b))

            new_networks.append(Network(
                id=net_id,
                buildings=list(comp),
                priority=new_priority,
                _bids=comp_ids,
                logistics_target=max(
                    (old_nets[pid].logistics_target for pid in parent_ids
                     if pid in old_nets),
                    default=0,
                ),
                # Inherit demand_auto from the surviving parent (the
                # first entry in ``parent_ids``).  Brand-new networks
                # default to True so newly-built colonies start with
                # automatic demand routing.
                demand_auto=(
                    old_nets[parent_ids[0]].demand_auto
                    if parent_ids and parent_ids[0] in old_nets
                    else True
                ),
                supply_auto=(
                    old_nets[parent_ids[0]].supply_auto
                    if parent_ids and parent_ids[0] in old_nets
                    else True
                ),
                worker_auto=(
                    old_nets[parent_ids[0]].worker_auto
                    if parent_ids and parent_ids[0] in old_nets
                    else True
                ),
            ))

        # Stable display order: by id ascending.
        new_networks.sort(key=lambda n: n.id)
        self.networks = new_networks
        # Refresh per-frame lookup caches before any priority rebuild
        # runs (the priority refreshers don't need them, but downstream
        # update steps do).
        self._valid_bids = {
            id(b) for b in self.buildings.buildings
        }
        self._bid_to_network = {
            id(b): net for net in self.networks for b in net.buildings
        }
        # Rebuild demand-priority tiers for every network now that the
        # ``buildings`` lists are settled.
        self._refresh_demand_priorities(old_nets)
        self._refresh_supply_priorities(old_nets)
        self._refresh_worker_priorities(old_nets)
        # Recompute populated-network ids from the refreshed map.
        self._populated_net_ids = {
            net.id
            for p in self.population.people
            if p.home is not None
            and (net := self._bid_to_network.get(id(p.home))) is not None
        }
        # Topology-change implies worker assignments need a refresh.
        self._workers_dirty = True

    # ── Fluid networks (parallel to building networks) ───────────

    def _rebuild_fluid_networks(self) -> None:
        """Recompute :attr:`fluid_networks` from current PIPE tiles
        and adjacent fluid-capable buildings.

        BFS connectors are PIPE tiles AND FLUID_TANK tiles — placing
        two tanks side-by-side forms an implicit pipe link between
        them, so players don't need to slot a one-tile pipe to fuse
        adjacent storage.  Other fluid-capable buildings (drill,
        refinery, chemical plant, silo, etc.) join the network of any
        connector that touches them, but do not themselves bridge.
        """
        # Collect all pipes/tanks and a coord→building lookup.
        all_buildings = self.buildings.buildings
        by_coord: dict[HexCoord, Building] = {b.coord: b for b in all_buildings}
        connector_types = (BuildingType.PIPE, BuildingType.FLUID_TANK)
        connectors = [b for b in all_buildings if b.type in connector_types]

        visited_conn: set[int] = set()
        new_networks: list[FluidNetwork] = []
        for seed in connectors:
            if id(seed) in visited_conn:
                continue
            comp_pipes: list[Building] = []
            comp_buildings_set: dict[int, Building] = {}
            queue: deque[Building] = deque([seed])
            visited_conn.add(id(seed))
            # Tanks are both connectors AND members of the network
            # (they hold fluid).  Pipes are pure connectors.
            if seed.type != BuildingType.PIPE:
                comp_buildings_set.setdefault(id(seed), seed)
            while queue:
                node = queue.popleft()
                if node.type == BuildingType.PIPE:
                    comp_pipes.append(node)
                for nb_coord in node.coord.neighbors():
                    nb = by_coord.get(nb_coord)
                    if nb is None:
                        continue
                    if nb.type in connector_types:
                        if id(nb) not in visited_conn:
                            visited_conn.add(id(nb))
                            if nb.type != BuildingType.PIPE:
                                comp_buildings_set.setdefault(id(nb), nb)
                            queue.append(nb)
                    elif nb.type in FLUID_CAPABLE_BUILDINGS:
                        # Join, but do not BFS through buildings.
                        comp_buildings_set.setdefault(id(nb), nb)
            net_id = self._next_fluid_network_id
            self._next_fluid_network_id += 1
            new_networks.append(FluidNetwork(
                id=net_id,
                buildings=list(comp_buildings_set.values()),
                pipes=comp_pipes,
            ))

        self.fluid_networks = new_networks

    def _update_fluids(self, dt: float) -> None:
        """Push fluid from producers toward sinks (consumers + tanks)
        within each pipe network.

        For each (network, fluid):
          1. Identify producers (the building natively *outputs* this
             fluid) and sinks (consumers and tanks).
          2. Drain all producer storage into a shared pool, then fill
             sinks evenly (proportional to their per-fluid capacity).
          3. Any pool remainder flows back into producers, also
             proportionally.  Producer per-fluid capacity is the full
             ``storage_capacity`` so no fluid is destroyed.

        This preserves total mass while giving consumers/tanks
        priority over the producer's own buffer — a drill piped to a
        tank empties into the tank rather than oscillating, and
        oil produced when the tank is full simply backs up in the
        drill (which then halts production via ``_storage_free``).
        """
        if not self.fluid_networks:
            return
        for net in self.fluid_networks:
            if not net.buildings:
                continue
            for fluid in FLUID_RESOURCES:
                producers: list[tuple[Building, float]] = []
                sinks: list[tuple[Building, float]] = []
                pool = 0.0
                for b in net.buildings:
                    cap = self._fluid_capacity_for(b, fluid)
                    if cap <= 0:
                        continue
                    cur = b.storage.get(fluid, 0.0)
                    if cur > cap:
                        cur = cap  # safety clamp
                    if _is_fluid_producer(b, fluid):
                        producers.append((b, cap))
                        pool += cur
                    else:
                        sinks.append((b, cap))
                        pool += cur
                if not producers and not sinks:
                    continue
                # Fill sinks first (proportional to capacity).
                sink_cap = sum(c for _, c in sinks)
                if sinks and sink_cap > 0:
                    take_for_sinks = min(pool, sink_cap)
                    ratio = take_for_sinks / sink_cap
                    for b, cap in sinks:
                        b.storage[fluid] = cap * ratio
                    pool -= take_for_sinks
                else:
                    # No sinks — clear any stale value just in case.
                    for b, _ in sinks:
                        b.storage[fluid] = 0.0
                # Any leftover stays in producers (proportionally).
                prod_cap = sum(c for _, c in producers)
                if producers:
                    if prod_cap > 0 and pool > 0:
                        ratio = min(1.0, pool / prod_cap)
                        for b, cap in producers:
                            b.storage[fluid] = cap * ratio
                    else:
                        for b, _ in producers:
                            b.storage[fluid] = 0.0

    def _fluid_capacity_for(
        self, b: Building, fluid: Resource,
    ) -> float:
        """Per-fluid capacity of *b* (0 if it doesn't handle that fluid).

        Used by :meth:`_update_fluids` to decide which network members
        can receive a given fluid.  Capacity is dedicated per-fluid
        within the building's own ``storage_capacity``: a refinery can
        hold up to ~half its capacity in OIL plus half in PETROLEUM,
        for instance.  Producers get the *full* capacity for their
        output fluid so that drained-into-network values are never
        truncated, which would silently destroy fluid mass.  Pipes
        have no capacity.
        """
        if b.type == BuildingType.PIPE:
            return 0.0
        # Fluid tank: only the player-selected fluid, full capacity.
        if b.type == BuildingType.FLUID_TANK:
            if b.stored_resource == fluid:
                return float(b.storage_capacity)
            return 0.0
        # Storage building: only if configured for this fluid (rare;
        # normally players use FLUID_TANK).
        if b.type == BuildingType.STORAGE:
            if b.stored_resource == fluid:
                return float(b.storage_capacity)
            return 0.0
        # Producer's own output fluid: full capacity (so the drill
        # can buffer crude when the network is full instead of having
        # it silently clipped away).
        if _is_fluid_producer(b, fluid):
            return float(b.storage_capacity)
        # Consumers: each fluid they natively use gets a half-
        # capacity slot.  Numbers chosen to be generous so a refinery
        # can buffer some OIL while still holding its solid output.
        slot = b.storage_capacity * 0.5
        if b.type == BuildingType.OIL_REFINERY and fluid == Resource.OIL:
            return slot
        if b.type == BuildingType.CHEMICAL_PLANT and fluid == Resource.PETROLEUM:
            return slot
        if b.type == BuildingType.MINING_MACHINE and fluid == Resource.PETROLEUM:
            return slot
        if b.type == BuildingType.ROCKET_SILO and fluid == Resource.ROCKET_FUEL:
            return slot
        if b.type == BuildingType.RESEARCH_CENTER and fluid == Resource.ROCKET_FUEL:
            return slot
        return 0.0

    # ── Worker assignment & dispatch ─────────────────────────────

    def _network_of_building(self, b: Building) -> Network | None:
        return self._bid_to_network.get(id(b))

    def _refresh_demand_priorities(
        self, old_nets: dict[int, Network],
    ) -> None:
        """Recompute ``demand_priority`` for every current network.

        For ``demand_auto`` networks: tier 0 = every non-storage
        building, tier 1 = every storage / camp building.  The auto
        layout matches the user's "all consumers equal, storage always
        last" rule from the spec.

        For manual networks: re-use the old per-building tier indexes
        so the player's hand-edited layout survives merges and splits.
        Buildings new to the network slot into tier 0 (highest demand)
        by default — they're more likely to be active producers/users
        than passive overflow storage.
        """
        for net in self.networks:
            members = list(net.buildings)
            if not members:
                net.demand_priority = []
                continue
            if net.demand_auto:
                net.demand_priority = self._auto_demand_tiers(members)
                continue
            # Manual mode: try to recover prior tier index per building.
            old_index: dict[int, int] = {}
            for parent_net in old_nets.values():
                for ti, tier in enumerate(parent_net.demand_priority):
                    for b in tier:
                        # Last-writer wins (largest tier index seen);
                        # acceptable since merges union memberships.
                        old_index[id(b)] = ti
            depth = max(old_index.values(), default=-1) + 1
            tiers: list[list[Building]] = [[] for _ in range(max(depth, 1))]
            for b in members:
                idx = old_index.get(id(b), 0)
                if idx >= len(tiers):
                    tiers.extend([] for _ in range(idx - len(tiers) + 1))
                tiers[idx].append(b)
            net.demand_priority = [t for t in tiers if t]

    def _auto_demand_tiers(
        self, members: list[Building],
    ) -> list[list[Building]]:
        """Default split: non-storage buildings on tier 0, passive
        storage / camp on tier 1.  Roads / bridges (which have no
        demand) and standalone walls are skipped entirely so the UI
        doesn't fill with no-op cards."""
        skip = {BuildingType.PATH, BuildingType.BRIDGE, BuildingType.WALL}
        tier0: list[Building] = []
        tier1: list[Building] = []
        for b in members:
            if b.type in skip:
                continue
            if b.type in (BuildingType.STORAGE, BuildingType.CAMP):
                tier1.append(b)
            else:
                tier0.append(b)
        result: list[list[Building]] = []
        if tier0:
            result.append(tier0)
        if tier1:
            result.append(tier1)
        return result

    def _demand_tier_of(
        self, b: Building, net: Network,
    ) -> int:
        """Return the (0-based) tier index of ``b`` within ``net``'s
        demand-priority list, or a large sentinel when the building
        isn't on the demand schedule at all."""
        for ti, tier in enumerate(net.demand_priority):
            if b in tier:
                return ti
        return 1_000_000

    def _refresh_supply_priorities(
        self, old_nets: dict[int, Network],
    ) -> None:
        """Same model as :meth:`_refresh_demand_priorities` but for
        supply tiers."""
        for net in self.networks:
            members = list(net.buildings)
            if not members:
                net.supply_priority = []
                continue
            if net.supply_auto:
                net.supply_priority = self._auto_supply_tiers(members)
                continue
            old_index: dict[int, int] = {}
            for parent_net in old_nets.values():
                for ti, tier in enumerate(parent_net.supply_priority):
                    for b in tier:
                        old_index[id(b)] = ti
            depth = max(old_index.values(), default=-1) + 1
            tiers: list[list[Building]] = [[] for _ in range(max(depth, 1))]
            for b in members:
                idx = old_index.get(id(b), 0)
                if idx >= len(tiers):
                    tiers.extend([] for _ in range(idx - len(tiers) + 1))
                tiers[idx].append(b)
            net.supply_priority = [t for t in tiers if t]

    def _auto_supply_tiers(
        self, members: list[Building],
    ) -> list[list[Building]]:
        """Default split: storage / camp on tier 0 (drained first so
        the network's buffer is consumed before producers' on-site
        stockpile), all other supply-capable buildings on tier 1.
        Roads / bridges / walls (no supply) and pure dwellings are
        skipped."""
        skip = {BuildingType.PATH, BuildingType.BRIDGE, BuildingType.WALL,
                BuildingType.HOUSE, BuildingType.HABITAT}
        tier0: list[Building] = []
        tier1: list[Building] = []
        for b in members:
            if b.type in skip:
                continue
            if b.type in (BuildingType.STORAGE, BuildingType.CAMP):
                tier0.append(b)
            else:
                tier1.append(b)
        result: list[list[Building]] = []
        if tier0:
            result.append(tier0)
        if tier1:
            result.append(tier1)
        return result

    def _refresh_worker_priorities(
        self, old_nets: dict[int, Network],
    ) -> None:
        """When ``worker_auto`` is enabled on a network, flatten all
        worker-buildings into a single tier and auto-compute
        ``logistics_target`` as 1 per every 4 buildings (rounded
        down, minimum 1).
        """
        for net in self.networks:
            if not net.worker_auto:
                continue
            # Flatten all worker-buildings into one tier.
            flat: list[Building] = []
            for b in net.buildings:
                if BUILDING_MAX_WORKERS.get(b.type, 0) <= 0:
                    continue
                flat.append(b)
            net.priority = [flat] if flat else []
            # Auto logistics: 1 worker per 4 buildings (rounded down,
            # always at least 1 if the network has any countable
            # buildings).  Excludes paths, bridges and walls.
            countable = [
                b for b in net.buildings
                if b.type not in (
                    BuildingType.PATH, BuildingType.BRIDGE,
                    BuildingType.WALL,
                )
            ]
            if countable:
                net.logistics_target = max(1, len(countable) // 4)
            else:
                net.logistics_target = 0

    def _supply_tier_of(
        self, b: Building, net: Network,
    ) -> int:
        for ti, tier in enumerate(net.supply_priority):
            if b in tier:
                return ti
        return 1_000_000

    def _assign_workers(self) -> None:
        """Walk each network's priority list and assign each eligible
        person in that network a ``workplace_target`` building.

        People whose current ``workplace_target`` is still a valid slot
        keep it (minimises commuter churn).  Remaining slots are filled
        from idle / newly-homed people in that network.  People with no
        target have ``workplace_target = None`` and (if already at a
        workplace they've now lost) will drift back to idle.
        """
        # Clear targets for buildings that no longer belong to any
        # network (deleted or zero-worker).
        valid_buildings: set[int] = set()
        for n in self.networks:
            for b in n.buildings:
                valid_buildings.add(id(b))
        for p in self.population.people:
            if (p.workplace_target is not None
                    and id(p.workplace_target) not in valid_buildings):
                p.workplace_target = None
            if p.workplace is not None and id(p.workplace) not in valid_buildings:
                p.workplace = None

        # Group people by the network of their current home.
        by_network: dict[int, list] = {}
        for p in self.population.people:
            if p.home is None:
                continue
            net = self._network_of_building(p.home)
            if net is None:
                continue
            by_network.setdefault(net.id, []).append(p)

        camp_coord = HexCoord(0, 0)
        camp = self.buildings.at(camp_coord)

        # Pre-compute per-network demand caches so the per-building
        # _effective_worker_demand calls are O(1) instead of O(B).
        for net in self.networks:
            self._precompute_network_demand_caches(net)

        for net in self.networks:
            people = by_network.get(net.id, [])
            # Available = people in this network who aren't "homeless
            # overflow" at the camp.  Homeless people still belong to
            # network 1 (where the camp is) and can be assigned.
            available = len(people)
            if camp is not None and net.contains(camp):
                homeless = max(0, camp.residents - camp.housing_capacity)
                available = max(0, available - homeless)

            # ── Compute production slot demand ───────────────────
            # Round-robin tiered fill so higher-tier buildings are
            # always staffed before lower ones.
            target_slots: dict[int, int] = {
                id(b): 0
                for tier in net.priority for b in tier
            }
            b_by_id: dict[int, Building] = {
                id(b): b for tier in net.priority for b in tier
            }
            # Compute a "demand factor" per producer in [min_keep, 1.0].
            # When the network is already swimming in this resource and
            # nothing is consuming it, the building only keeps a token
            # worker — surplus people then promote to logistics or other
            # buildings whose output is actually needed.
            effective_max: dict[int, int] = {}
            for b in b_by_id.values():
                effective_max[id(b)] = self._effective_worker_demand(
                    b, net,
                )
            production_capacity = sum(effective_max.values())
            # Reserve at least ``logistics_target`` people for logistics
            # before staffing production; everyone else first fills
            # production, and any leftover idle workers default to
            # logistics (Task 6: idle → logistics).
            log_min = max(0, min(net.logistics_target, available))
            prod_pool = max(0, available - log_min)
            prod_to_assign = min(prod_pool, production_capacity)
            log_count = available - prod_to_assign

            remaining = prod_to_assign
            for tier in net.priority:
                if remaining <= 0:
                    break
                while remaining > 0:
                    placed_any = False
                    for b in tier:
                        cap = effective_max.get(id(b), b.max_workers)
                        if target_slots[id(b)] < cap:
                            target_slots[id(b)] += 1
                            remaining -= 1
                            placed_any = True
                            if remaining <= 0:
                                break
                    if not placed_any:
                        break

            # ── Decide who goes where ────────────────────────────
            # 1) Try to keep each existing non-logistics worker at
            #    their current target if that slot is still open.
            # 2) Try to keep each existing logistics worker as
            #    logistics if there are still logistics seats free.
            # 3) Fill remaining production slots from the leftover
            #    pool (priority: people whose home is closer; stable
            #    by ``id``).  Promote anyone past production capacity
            #    to logistics.
            remaining_slots = dict(target_slots)
            keep_workers: dict[int, Building] = {}      # person id → bldg
            keep_logistics: set[int] = set()
            leftover: list = []

            # Stable order: existing logistics carrying cargo first
            # (avoid orphaning shipments), then others by id.
            people_sorted = sorted(
                people,
                key=lambda p: (
                    not (p.is_logistics and p.carry_resource is not None),
                    p.id,
                ),
            )

            log_seats = log_count
            for p in people_sorted:
                tgt = p.workplace_target
                if (tgt is not None and id(tgt) in remaining_slots
                        and remaining_slots[id(tgt)] > 0):
                    keep_workers[id(p)] = tgt
                    remaining_slots[id(tgt)] -= 1
                elif p.is_logistics and log_seats > 0:
                    keep_logistics.add(id(p))
                    log_seats -= 1
                else:
                    leftover.append(p)

            # Fill the remaining production slots (in priority order)
            # from the leftover pool.
            li = 0
            for tier in net.priority:
                for b in tier:
                    while (remaining_slots.get(id(b), 0) > 0
                           and li < len(leftover)):
                        keep_workers[id(leftover[li])] = b
                        remaining_slots[id(b)] -= 1
                        li += 1

            # Anyone still unassigned (li.. ) becomes logistics.
            for p in leftover[li:]:
                keep_logistics.add(id(p))

            # ── Apply state changes in one pass ─────────────────
            for p in people:
                want_workplace = keep_workers.get(id(p))
                want_logistics = id(p) in keep_logistics
                if want_workplace is not None:
                    # Production worker.
                    if p.is_logistics:
                        p.is_logistics = False
                        p.logistics_src = None
                        p.logistics_dst = None
                        p.carry_resource = None
                        p.path = []
                        p.task = Task.IDLE
                    if p.workplace_target is not want_workplace:
                        p.workplace_target = want_workplace
                elif want_logistics:
                    if not p.is_logistics:
                        p.is_logistics = True
                        p.workplace = None
                        p.workplace_target = None
                        p.path = []
                        p.task = Task.LOGISTICS_IDLE
                    elif p.task == Task.IDLE:
                        # Stale logistics that lost their state.
                        p.task = Task.LOGISTICS_IDLE
                else:
                    # No slot at all — go idle (rare; only if camp is
                    # over capacity and we deliberately excluded them).
                    if p.is_logistics:
                        p.is_logistics = False
                        p.logistics_src = None
                        p.logistics_dst = None
                        p.carry_resource = None
                    p.workplace_target = None
                    p.workplace = None
                    p.path = []
                    p.task = Task.IDLE

    def _dispatch_commuters(self) -> None:
        """Give each person a COMMUTE path when their target differs
        from their current workplace.  Workers that lost their target
        go idle; new assignments trigger path recomputation."""
        for p in self.population.people:
            if p.is_logistics:
                continue
            tgt = p.workplace_target
            if tgt is None:
                if p.workplace is not None:
                    # Target was cleared — send them back toward home
                    # (they'll linger there until reassigned).
                    p.workplace = None
                if p.task in (Task.COMMUTE, Task.GATHER):
                    if not p.path:
                        p.task = Task.IDLE
                continue
            if p.workplace is tgt and p.hex_pos == tgt.coord:
                # Already there and working.
                if p.task == Task.IDLE or p.task == Task.COMMUTE:
                    p.task = Task.GATHER
                continue
            # Need to travel to target.  Only recompute the path if
            # we're not already commuting, target changed, or path
            # became stale (destination hex differs).
            needs_path = (
                p.task != Task.COMMUTE
                or not p.path
                or (p.path and p.path[-1] != tgt.coord)
            )
            if needs_path:
                path = self._find_building_path(p.hex_pos, tgt.coord)
                if path:
                    p.path = path
                    p.task = Task.COMMUTE
                    # Clear workplace immediately so production stops
                    # at the old workplace the moment they leave.
                    p.workplace = None
                else:
                    # No path — they're stranded.  Stay idle at home.
                    p.task = Task.IDLE
                    p.path = []
                    p.workplace = None

    def _recount_present_workers(self) -> None:
        """Set ``building.workers`` to the number of people currently
        standing at that building's hex with it as their workplace."""
        for b in self.buildings.buildings:
            b.workers = 0
        for p in self.population.people:
            wp = p.workplace
            if wp is None:
                continue
            if p.hex_pos == wp.coord:
                wp.workers += 1

    # ── Supply / demand ──────────────────────────────────────────

    def _building_production_outputs(
        self, b: "Building",
    ) -> set[Resource]:
        """Resources *b* is currently producing (and so supplies)."""
        t = b.type
        if t == BuildingType.WOODCUTTER:
            return {Resource.WOOD}
        if t == BuildingType.QUARRY:
            if b.quarry_output is not None:
                return {b.quarry_output}
            return {Resource.STONE}
        if t == BuildingType.GATHERER:
            if b.gatherer_output is not None:
                return {b.gatherer_output}
            return {Resource.FOOD}
        if t == BuildingType.FARM:
            return {Resource.FOOD}
        if t == BuildingType.MINING_MACHINE:
            return {Resource.IRON, Resource.COPPER}
        if t == BuildingType.OIL_DRILL:
            return {Resource.OIL}
        if t == BuildingType.REFINERY and b.recipe is None:
            return {Resource.IRON, Resource.COPPER}
        if t in (
            BuildingType.WORKSHOP, BuildingType.FORGE,
            BuildingType.REFINERY, BuildingType.ASSEMBLER,
            BuildingType.CHEMICAL_PLANT, BuildingType.OIL_REFINERY,
        ):
            if isinstance(b.recipe, Resource):
                mrec = MATERIAL_RECIPES.get(b.recipe)
                if mrec is not None:
                    return {mrec.output}
        return set()

    def _building_supply(self, b: "Building") -> dict[Resource, float]:
        """Resources currently offered as supply from *b*, with the
        amount currently held in its storage.

        STORAGE buildings only supply their configured resource.  Every
        other building offers any resource it currently holds *except*
        ones it is itself demanding (so logistics workers don't shuttle
        recipe inputs out of a workshop they were just delivered to).

        Fluid resources (oil, petroleum, lubricant, rocket fuel) are
        deliberately excluded — they only move through the parallel
        pipe network and are never carried by workers.
        """
        out: dict[Resource, float] = {}
        # STORAGE: supplies its configured resource (unless it's a
        # fluid; fluids belong to FLUID_TANK + the pipe network).
        if b.type == BuildingType.STORAGE:
            if (b.stored_resource is not None
                    and b.stored_resource not in FLUID_RESOURCES):
                amt = b.storage.get(b.stored_resource, 0.0)
                if amt > 0:
                    out[b.stored_resource] = amt
            return out
        # Fluid tanks never offer their contents to worker logistics.
        if b.type == BuildingType.FLUID_TANK:
            return out
        # Dwellings only consume FOOD — they never supply.  Treating
        # dwellings as suppliers caused workers to ping-pong food
        # between two adjacent houses whenever one was momentarily
        # over the per-house cap.
        if b.housing_capacity > 0:
            return out
        # All other buildings: anything in storage that isn't on their
        # own demand list is fair game as supply, except fluids.
        # Crafting stations additionally never supply any ingredient
        # of their currently selected recipe — even when their input
        # buffer is full — so logistics workers can't shuttle a
        # workshop's own recipe inputs back out of it.
        reserved: set[Resource] = set()
        if b.type in (
            BuildingType.WORKSHOP, BuildingType.FORGE,
            BuildingType.REFINERY, BuildingType.ASSEMBLER,
            BuildingType.CHEMICAL_PLANT, BuildingType.OIL_REFINERY,
        ):
            if isinstance(b.recipe, Resource):
                mrec = MATERIAL_RECIPES.get(b.recipe)
                if mrec is not None:
                    reserved.update(mrec.inputs.keys())
            elif isinstance(b.recipe, BuildingType):
                cost = BUILDING_COSTS.get(b.recipe)
                if cost is not None:
                    reserved.update(cost.costs.keys())
        demanded = set(self._building_demand(b).keys())
        for r, amt in b.storage.items():
            if r in FLUID_RESOURCES:
                continue
            if r in reserved or r in demanded:
                continue
            if amt > 0:
                out[r] = amt
        return out

    def _building_demand(self, b: "Building") -> dict[Resource, float]:
        """Resources *b* wants delivered, with the free space/amount
        it can still accept.

        Fluids are deliberately excluded from the result — they only
        flow through the pipe network and are never carried by
        workers.
        """
        out: dict[Resource, float] = {}
        free = self._storage_free(b)
        if free <= 0:
            return out
        # Fluid tanks never demand from the worker logistics.
        if b.type == BuildingType.FLUID_TANK:
            return out
        # STORAGE: demands its configured resource up to free space.
        if b.type == BuildingType.STORAGE:
            if (b.stored_resource is not None
                    and b.stored_resource not in FLUID_RESOURCES):
                out[b.stored_resource] = free
            return out
        # Dwellings: demand FOOD (capped at 50 worth of food on-site,
        # regardless of total storage capacity — keeps large camps
        # from vacuuming up everything).
        if b.housing_capacity > 0:
            on_site = b.storage.get(Resource.FOOD, 0.0)
            target = 50.0
            need = max(0.0, min(target - on_site, free))
            if need > 0.5:
                out[Resource.FOOD] = need
            return out
        # MINING_MACHINE: demands fuel.
        if b.type == BuildingType.MINING_MACHINE:
            for fuel_name in params.MINING_MACHINE_FUELS:
                fr = Resource[fuel_name]
                have = b.storage.get(fr, 0.0)
                cap_for_fuel = min(free, b.storage_capacity * 0.4)
                need = max(0.0, cap_for_fuel - have)
                if need > 0.5:
                    out[fr] = need
            return out
        # Crafting stations: demand recipe inputs, with each input
        # capped at exactly twice the recipe requirement so a refinery
        # / workshop / forge / assembler reserves a dedicated input
        # slot per ingredient.
        if b.type in (
            BuildingType.WORKSHOP, BuildingType.FORGE,
            BuildingType.REFINERY, BuildingType.ASSEMBLER,
            BuildingType.CHEMICAL_PLANT, BuildingType.OIL_REFINERY,
        ) and isinstance(b.recipe, Resource):
            mrec = MATERIAL_RECIPES.get(b.recipe)
            if mrec is not None:
                # Reserve ~80% of storage for inputs so the output
                # has room to accumulate between worker pickups.
                budget = b.storage_capacity * 0.8
                # Ignore fluid inputs when sizing the per-input cap —
                # they don't occupy worker-deliverable storage.
                solid = {r: a for r, a in mrec.inputs.items()
                         if r not in FLUID_RESOURCES}
                total = sum(solid.values()) or 1.0
                # Default desired buffer is 2x the recipe amount, but
                # scale every input down proportionally if 2x for all
                # inputs would exceed the budget.
                scale = min(2.0, budget / total)
                for res, amt in mrec.inputs.items():
                    if res in FLUID_RESOURCES:
                        continue
                    have = b.storage.get(res, 0.0)
                    target = amt * scale
                    need = max(0.0, target - have)
                    if need > 0.5:
                        out[res] = need
        # Crafting station with a building recipe (placeable
        # building): demand the building cost so logistics will
        # deliver inputs instead of scraping the global inventory.
        # Check BUILDING_RECIPE_STATION so Forge, Assembler, etc.
        # also get deliveries — not just the Workshop.
        if isinstance(b.recipe, BuildingType):
            cost = BUILDING_COSTS.get(b.recipe)
            if cost is not None:
                # Building recipes don't store an output, so the full
                # storage capacity is available for inputs.
                budget = b.storage_capacity
                solid = {r: a for r, a in cost.costs.items()
                         if r not in FLUID_RESOURCES}
                total = sum(solid.values()) or 1.0
                scale = min(2.0, budget / total)
                for res, amt in cost.costs.items():
                    if res in FLUID_RESOURCES:
                        continue
                    have = b.storage.get(res, 0.0)
                    target = amt * scale
                    need = max(0.0, target - have)
                    if need > 0.5:
                        out[res] = need
        # Research center: demands the outstanding cost of the
        # currently-active research, capped per-resource at 2x the
        # remaining requirement so logistics keeps it fed without
        # over-stuffing.  Each RC demands the full remaining amount
        # independently — logistics + the round-robin consumption in
        # TechTree.tick() naturally distribute the load across
        # multiple research centers.
        if b.type == BuildingType.RESEARCH_CENTER:
            tt = self.tech_tree
            if tt is not None and getattr(tt, "current_research", None):
                node = TECH_NODES.get(tt.current_research)
                if node is not None:
                    consumed = getattr(tt, "_consumed", {}) or {}
                    for res, total_amt in node.cost.items():
                        already = consumed.get(res, 0.0)
                        remaining = max(0.0, total_amt - already)
                        if remaining <= 0:
                            continue
                        target = remaining * 2
                        have = b.storage.get(res, 0.0)
                        need = max(0.0, target - have)
                        if need > 0.5:
                            out[res] = need
        # Fluids are never carried by workers — drop any that slipped
        # through (e.g. PETROLEUM as mining-machine fuel, OIL into the
        # refinery, ROCKET_FUEL into the silo / research center).
        for fr in list(out):
            if fr in FLUID_RESOURCES:
                del out[fr]
        return out

    def _is_producer(self, b: "Building") -> bool:
        return b.type in (
            BuildingType.WOODCUTTER, BuildingType.QUARRY,
            BuildingType.GATHERER, BuildingType.FARM,
            BuildingType.MINING_MACHINE, BuildingType.OIL_DRILL,
        ) or (b.type in (
            BuildingType.WORKSHOP, BuildingType.FORGE,
            BuildingType.REFINERY, BuildingType.ASSEMBLER,
            BuildingType.CHEMICAL_PLANT, BuildingType.OIL_REFINERY,
        ) and isinstance(b.recipe, Resource))

    def _is_consumer(self, b: "Building") -> bool:
        if b.type == BuildingType.MINING_MACHINE:
            return True
        if b.type in (
            BuildingType.WORKSHOP, BuildingType.FORGE,
            BuildingType.REFINERY, BuildingType.ASSEMBLER,
            BuildingType.CHEMICAL_PLANT, BuildingType.OIL_REFINERY,
        ) and isinstance(b.recipe, Resource):
            return True
        if b.type == BuildingType.RESEARCH_CENTER:
            tt = self.tech_tree
            if tt is not None and getattr(tt, "current_research", None):
                return True
        if b.housing_capacity > 0:
            return True
        return False

    # ── Adaptive worker demand ──────────────────────────────────

    def _building_output(self, b: "Building") -> "Resource | None":
        """Return the resource this building produces (if any)."""
        bt = b.type
        if bt == BuildingType.WOODCUTTER:
            return Resource.WOOD
        if bt == BuildingType.QUARRY:
            return Resource.STONE
        if bt == BuildingType.GATHERER:
            return Resource.FIBER
        if bt == BuildingType.FARM:
            return Resource.FOOD
        if bt in (
            BuildingType.WORKSHOP, BuildingType.FORGE,
            BuildingType.REFINERY, BuildingType.ASSEMBLER,
            BuildingType.CHEMICAL_PLANT, BuildingType.MINING_MACHINE,
            BuildingType.OIL_REFINERY,
        ):
            r = b.recipe
            return r if isinstance(r, Resource) else None
        if bt == BuildingType.OIL_DRILL:
            return Resource.OIL
        return None

    def _network_resource_buffer(
        self, net: "Network", res: "Resource",
    ) -> tuple[float, float]:
        """Return (total_stock, total_capacity) for ``res`` across all
        buildings in ``net`` plus the global inventory."""
        cached = getattr(net, "_buffer_cache", None)
        if cached is not None:
            entry = cached.get(res)
            if entry is not None:
                return entry
        stock = float(self.inventory[res])
        cap = 0.0
        for b in net.buildings:
            stock += float(b.storage.get(res, 0.0))
            cap += float(b.storage_capacity)
        # Always allow at least one capacity-equivalent worth of buffer
        # so brand-new networks still register pressure correctly.
        cap = max(cap, 1.0)
        return stock, cap

    def _precompute_network_demand_caches(self, net: "Network") -> None:
        """Populate per-network caches used by :meth:`_effective_worker_demand`
        so the inner loop is O(1) per building instead of O(B).  Called
        once at the top of :meth:`_assign_workers` for each network.
        """
        # Sum stock/cap per resource across the network (+ global inv
        # for stock).  Capacity is the same for every resource (each
        # building's full storage), so we sum it once.
        total_cap = 0.0
        per_res_stock: dict[Resource, float] = {}
        consumers_per_res: dict[Resource, int] = {}
        food_consumers = 0
        for b in net.buildings:
            total_cap += float(b.storage_capacity)
            for r, amt in b.storage.items():
                if amt:
                    per_res_stock[r] = per_res_stock.get(r, 0.0) + float(amt)
            recipe = getattr(b, "recipe", None)
            if isinstance(recipe, Resource) and self._is_consumer(b):
                consumers_per_res[recipe] = consumers_per_res.get(recipe, 0) + 1
            if b.housing_capacity > 0:
                food_consumers += 1
        if food_consumers:
            consumers_per_res[Resource.FOOD] = (
                consumers_per_res.get(Resource.FOOD, 0) + food_consumers
            )
        total_cap = max(total_cap, 1.0)
        buffer_cache: dict[Resource, tuple[float, float]] = {}
        # Lazy-fill via _network_resource_buffer fallback for resources
        # not present in storage; pre-seed the common ones from the
        # accumulated stock map.
        inv = self.inventory
        for r in per_res_stock:
            buffer_cache[r] = (per_res_stock[r] + float(inv[r]), total_cap)
        net._buffer_cache = buffer_cache  # type: ignore[attr-defined]
        net._buffer_cap = total_cap  # type: ignore[attr-defined]
        net._consumers_per_res = consumers_per_res  # type: ignore[attr-defined]

    def _effective_worker_demand(
        self, b: "Building", net: "Network",
    ) -> int:
        """Compute how many workers ``b`` actually warrants right now.

        Returns a value in ``[min_keep, b.max_workers]``.  When the
        building's output is already plentiful and nothing in the
        network is consuming it, this drops to a single token worker —
        freeing the rest for logistics or higher-need producers.

        For consumers (workshops, forges, mining machines, …) we leave
        the demand untouched; their throughput is gated by inputs, not
        by oversupply concerns.
        """
        max_w = max(0, int(b.max_workers))
        if max_w <= 1:
            return max_w
        out = self._building_output(b)
        if out is None or self._is_consumer(b):
            return max_w
        # Per-network caches populated by
        # :meth:`_precompute_network_demand_caches` collapse this from
        # O(B) per call to O(1).  Fall back to the on-demand path when
        # the cache hasn't been populated yet (edge cases / tests).
        consumers_map = getattr(net, "_consumers_per_res", None)
        if consumers_map is not None and out in consumers_map:
            consumers_here = consumers_map[out]
            # ``b`` itself counts in that map only if it's also a
            # consumer of its own output — in practice that doesn't
            # happen, but stay defensive.
            recipe = getattr(b, "recipe", None)
            if isinstance(recipe, Resource) and recipe == out and self._is_consumer(b):
                consumers_here -= 1
            if consumers_here > 0:
                return max_w
        else:
            # Fallback path: original O(B) scan.
            consumers_here = 0
            for other in net.buildings:
                if other is b or not self._is_consumer(other):
                    continue
                recipe = getattr(other, "recipe", None)
                if isinstance(recipe, Resource) and recipe == out:
                    consumers_here += 1
                    continue
                if other.housing_capacity > 0 and out == Resource.FOOD:
                    consumers_here += 1
            if consumers_here > 0:
                return max_w
        stock, cap = self._network_resource_buffer(net, out)
        # No internal consumer: scale by stockpile pressure.
        # 0 stock → full crew; ≥cap → single worker.
        ratio = min(1.0, stock / cap) if cap > 0 else 0.0
        # Quadratic falloff so we don't drop to skeleton crew until
        # the stockpile is genuinely full.
        scale = 1.0 - ratio * ratio
        scaled = max(1, int(round(max_w * scale)))
        return min(max_w, scaled)

    # ── Logistics ────────────────────────────────────────────────

    def _update_logistics(self, dt: float) -> None:
        """Advance every logistics worker one step.

        State machine:
            LOGISTICS_IDLE → pick a best (src, dst, res) job and set a
                             path to src (task becomes LOGISTICS_PICKUP).
            LOGISTICS_PICKUP → on arrival at src, transfer up to
                               LOGISTICS_CARRY_CAPACITY units, then set
                               path to dst (task LOGISTICS_DELIVER).
            LOGISTICS_DELIVER → on arrival at dst, deposit cargo, then
                                return to LOGISTICS_IDLE.

        Job-finding (the expensive O(buildings²) scan) is throttled
        to ``params.LOGISTICS_JOBS_PER_FRAME`` idle workers per frame
        AND a hard wall-clock budget of
        ``params.LOGISTICS_FIND_JOB_BUDGET_MS`` milliseconds — when
        50+ haulers all go idle on the same tick this prevents a
        multi-second stall.  Active workers (PICKUP / DELIVER) are
        still ticked unconditionally.
        """
        idle_indices: list[int] = []
        for i, p in enumerate(self.population.people):
            if not p.is_logistics:
                continue
            if p.task == Task.LOGISTICS_IDLE or p.task == Task.IDLE:
                idle_indices.append(i)
            else:
                self._logistics_tick(p)

        if not idle_indices:
            self._logistics_search_cursor = 0
            return

        budget = max(1, params.LOGISTICS_JOBS_PER_FRAME)
        n = len(idle_indices)
        # Wall-clock fence so a single frame's job-finding can never
        # blow out the frame budget regardless of how many idle
        # workers happen to be in scope.  ``perf_counter`` is the
        # cheapest monotonic high-resolution timer on Windows.
        from time import perf_counter
        deadline = perf_counter() + (
            max(0, params.LOGISTICS_FIND_JOB_BUDGET_MS) / 1000.0
        )
        # Process up to `budget` idle workers starting from the
        # round-robin cursor so every worker eventually gets a turn.
        start = self._logistics_search_cursor % n
        processed = 0
        i = start
        while processed < budget and processed < n:
            p = self.population.people[idle_indices[i]]
            self._logistics_tick(p)
            processed += 1
            i = (i + 1) % n
            if perf_counter() >= deadline:
                break
        self._logistics_search_cursor = (start + processed) % n

    def _logistics_tick(self, p) -> None:
        # Arrival is detected by "has logistics state, path empty, and
        # hex_pos matches the expected coord".  Movement is handled
        # later by population.update() — we just set up the next step.
        if p.task == Task.LOGISTICS_IDLE or p.task == Task.IDLE:
            self._logistics_find_job(p)
            return

        if p.task == Task.LOGISTICS_PICKUP:
            src = p.logistics_src
            if src is None or id(src) not in self._valid_bids:
                self._logistics_reset(p)
                return
            if p.path:
                return  # still walking
            if p.hex_pos != src.coord:
                # Path broke — try to replan once.
                path = self._find_building_path(p.hex_pos, src.coord)
                if path:
                    p.path = path
                    return
                self._logistics_reset(p)
                return
            # Pick up.
            res = p.logistics_res
            if res is None:
                self._logistics_reset(p)
                return
            already = p.logistics_amount or 0.0
            free_cap = max(0.0, params.LOGISTICS_CARRY_CAPACITY - already)
            take = min(free_cap, src.storage.get(res, 0.0))
            if take <= 0:
                if already > 0:
                    # Already carrying something — head to destination.
                    dst = p.logistics_dst
                    if dst is not None:
                        path = self._find_building_path(p.hex_pos, dst.coord)
                        if path:
                            p.path = path
                            p.task = Task.LOGISTICS_DELIVER
                            return
                # Supplier's empty; abandon and find something else.
                self._logistics_reset(p)
                return
            src.storage[res] = src.storage.get(res, 0.0) - take
            if src.storage[res] <= 1e-6:
                src.storage.pop(res, None)
            p.logistics_amount = (p.logistics_amount or 0.0) + take
            p.carry_resource = (res, p.logistics_amount)
            # Set path to destination.
            dst = p.logistics_dst
            if dst is None:
                # Shouldn't happen but be defensive.
                self._logistics_reset(p)
                return
            # ── Chained pickup ──────────────────────────────────
            # If we still have free carry capacity, look for another
            # supplier of the same resource that's roughly on the way
            # to the destination.  This keeps a single worker hauling
            # a full load instead of dispatching N workers for N units.
            remaining_cap = params.LOGISTICS_CARRY_CAPACITY - p.logistics_amount
            if remaining_cap > 1e-3:
                next_src = self._find_chained_supplier(
                    p, res, dst, remaining_cap,
                )
                if next_src is not None and next_src is not src:
                    detour_path = self._find_building_path(
                        p.hex_pos, next_src.coord,
                    )
                    if detour_path:
                        p.logistics_src = next_src
                        p.path = detour_path
                        # Stay in PICKUP state — we'll loop back here.
                        return
            path = self._find_building_path(p.hex_pos, dst.coord)
            if not path:
                # Lost path — drop cargo back (best effort).
                self._deposit(src, res, take)
                p.carry_resource = None
                p.logistics_amount = 0.0
                self._logistics_reset(p)
                return
            p.path = path
            p.task = Task.LOGISTICS_DELIVER
            return

        if p.task == Task.LOGISTICS_DELIVER:
            dst = p.logistics_dst
            if dst is None or id(dst) not in self._valid_bids:
                # Destination gone.  Drop cargo at any storage we're
                # on (best effort) or just discard to global inventory.
                if p.logistics_res is not None and p.logistics_amount > 0:
                    self.inventory.add(p.logistics_res, p.logistics_amount)
                p.carry_resource = None
                p.logistics_amount = 0.0
                self._logistics_reset(p)
                return
            if p.path:
                return
            if p.hex_pos != dst.coord:
                path = self._find_building_path(p.hex_pos, dst.coord)
                if path:
                    p.path = path
                    return
                # Drop to inventory as fallback.
                if p.logistics_res is not None and p.logistics_amount > 0:
                    self.inventory.add(p.logistics_res, p.logistics_amount)
                p.carry_resource = None
                p.logistics_amount = 0.0
                self._logistics_reset(p)
                return
            # Deposit.
            res = p.logistics_res
            if res is not None and p.logistics_amount > 0:
                deposited = self._deposit(dst, res, p.logistics_amount)
                leftover = p.logistics_amount - deposited
                if leftover > 0:
                    # Dest full; push leftover to global inventory.
                    self.inventory.add(res, leftover)
            p.carry_resource = None
            p.logistics_amount = 0.0
            self._logistics_reset(p)
            return

    def _logistics_reset(self, p) -> None:
        p.task = Task.LOGISTICS_IDLE
        p.logistics_src = None
        p.logistics_dst = None
        p.logistics_res = None
        p.logistics_amount = 0.0
        p.carry_resource = None
        p.path = []

    def _find_chained_supplier(
        self, p, res: "Resource", dst: "Building", remaining_cap: float,
    ) -> "Building | None":
        """Look for another building in the same network that holds
        ``res`` and is roughly on the way from the worker to ``dst``.

        Returns the most attractive supplier or None.  Detour distance
        from the worker's current position is capped so that chained
        pickups stay efficient — we never want a worker zig-zagging
        across the map to pluck a single unit.
        """
        net = self._network_of_building(dst)
        if net is None:
            return None
        # Hex distance from the worker to the destination acts as the
        # baseline; any candidate must keep total travel within
        # ``baseline + max_detour``.
        baseline = self._hex_distance(p.hex_pos, dst.coord)
        max_detour = max(2, int(baseline * 0.5) + 2)
        best: Building | None = None
        best_score = -1.0
        for cand in net.buildings:
            if cand is p.logistics_src or cand is dst:
                continue
            avail = float(cand.storage.get(res, 0.0))
            if avail <= 1e-3:
                continue
            d_to_cand = self._hex_distance(p.hex_pos, cand.coord)
            d_cand_to_dst = self._hex_distance(cand.coord, dst.coord)
            if d_to_cand + d_cand_to_dst > baseline + max_detour:
                continue
            haul = min(avail, remaining_cap)
            # Higher haul, lower detour ⇒ better.
            detour_pen = max(0, (d_to_cand + d_cand_to_dst) - baseline)
            score = haul - 0.25 * detour_pen
            if score > best_score:
                best_score = score
                best = cand
        return best

    def _hex_distance(self, a: "HexCoord", b: "HexCoord") -> int:
        dq = a.q - b.q
        dr = a.r - b.r
        return (abs(dq) + abs(dr) + abs(dq + dr)) // 2

    def _filter_demands_by_tier(
        self, net: "Network",
        demands: list[tuple],
        supplies: list[tuple],
    ) -> list[tuple]:
        """Restrict the demand pool to the highest-priority tier *per
        resource* that has at least one buyer matching an available
        supplier — but *fall through* to lower tiers as soon as the
        top tier's open need has already been claimed by in-flight
        hauls.  This guarantees every demanding building eventually
        gets served instead of being permanently shadowed by a higher
        tier with permanent overdraw.

        Each entry in ``demands`` is ``(building, resource, need,
        empty_frac)``.  When the network's demand_priority list is
        empty (e.g. a brand-new colony) we return the input unchanged.
        """
        tiers = net.demand_priority
        if not tiers:
            return demands
        supply_res = {s[1] for s in supplies}
        # by_res_tier[resource][tier_index] -> list of demand entries.
        by_res_tier: dict[object, dict[int, list[tuple]]] = {}
        for d in demands:
            if d[1] not in supply_res:
                continue
            ti = self._demand_tier_of(d[0], net)
            by_res_tier.setdefault(d[1], {}).setdefault(ti, []).append(d)
        out: list[tuple] = []
        for r, by_tier in by_res_tier.items():
            sorted_tiers = sorted(by_tier)
            top_ti = sorted_tiers[0]
            top_demands = by_tier[top_ti]
            # Net unmet need in the top tier (after subtracting
            # already-en-route deliveries).  When the top tier's
            # remaining need is zero, lower tiers may participate.
            top_remaining = 0.0
            for db, _r, dneed, _e in top_demands:
                claimed = self._claimed_demand_for(db, r)
                top_remaining += max(0.0, dneed - claimed)
            out.extend(top_demands)
            if top_remaining <= 1e-3:
                # Top tier is fully claimed — let the next tiers join.
                for ti in sorted_tiers[1:]:
                    out.extend(by_tier[ti])
        return out if out else demands

    def _claimed_demand_for(self, b: "Building", res) -> float:
        """Total quantity of *res* already promised to building *b*
        by in-flight hauls.  Mirrors the per-pickup ``claimed_demand``
        accounting in :meth:`_logistics_find_job`."""
        from compprog_pygame.games.hex_colony.people import Task as _T
        carry_cap = params.LOGISTICS_CARRY_CAPACITY
        total = 0.0
        for p in self.population.people:
            if not getattr(p, "is_logistics", False):
                continue
            if p.logistics_dst is not b or p.logistics_res != res:
                continue
            if p.task == _T.LOGISTICS_PICKUP:
                total += carry_cap
            elif p.task == _T.LOGISTICS_DELIVER:
                amt = float(getattr(p, "logistics_amount", 0.0) or 0.0)
                total += amt or carry_cap
        return total

    def _filter_supplies_by_tier(
        self, net: "Network",
        supplies: list[tuple],
        demands: list[tuple],
    ) -> list[tuple]:
        """Restrict the supply pool to the highest-priority tier *per
        resource* whose offerings can satisfy an outstanding demand.

        Per-resource filtering avoids the failure mode where the top
        tier holds a useful resource A but suppresses lower-tier
        suppliers of resource B that consumers also need.  When
        outstanding demand for a resource exceeds what the top tier
        alone can fulfil (after accounting for in-flight hauls),
        lower tiers are folded back in so spare supply is not stranded.
        """
        tiers = net.supply_priority
        if not tiers:
            return supplies
        # Aggregate outstanding demand per-resource (after claims).
        demand_remaining: dict[object, float] = {}
        for db, dres, dneed, _de in demands:
            claimed = self._claimed_demand_for(db, dres)
            demand_remaining[dres] = (
                demand_remaining.get(dres, 0.0) + max(0.0, dneed - claimed)
            )
        by_res_tier: dict[object, dict[int, list[tuple]]] = {}
        for s in supplies:
            if s[1] not in demand_remaining:
                continue
            ti = self._supply_tier_of(s[0], net)
            by_res_tier.setdefault(s[1], {}).setdefault(ti, []).append(s)
        out: list[tuple] = []
        for r, by_tier in by_res_tier.items():
            need = demand_remaining.get(r, 0.0)
            for ti in sorted(by_tier):
                tier_supply = by_tier[ti]
                out.extend(tier_supply)
                # Subtract this tier's offered amount; if demand is
                # met, lower tiers stay out.
                offered = sum(s[2] for s in tier_supply)
                need -= offered
                if need <= 1e-3:
                    break
        return out if out else supplies

    # ── Population growth ────────────────────────────────────────

    def _update_population_growth(self, dt: float) -> None:
        """Every dwelling with empty space accumulates a reproduction
        timer.  Once it reaches POPULATION_REPRO_INTERVAL and the
        dwelling holds at least POPULATION_MIN_FOOD_TO_BIRTH units of
        food, a new person is born: the food is consumed and the new
        person is assigned this dwelling as their home (housing will
        rebalance on the next dirty flag)."""
        birth_interval = params.POPULATION_REPRO_INTERVAL
        food_cost = params.POPULATION_FOOD_PER_BIRTH
        food_min = params.POPULATION_MIN_FOOD_TO_BIRTH
        spawned_any = False
        for b in self.buildings.buildings:
            if b.housing_capacity <= 0:
                continue
            # Skip non-player (AI tribe) dwellings — they reproduce on
            # their own AI logic, not the player's population system.
            if b.faction != "SURVIVOR":
                continue
            # Only tick timer when there's room to grow.
            if b.residents >= b.housing_capacity:
                b.reproduction_timer = 0.0
                continue
            food_here = b.storage.get(Resource.FOOD, 0.0)
            if food_here < food_min:
                # Not enough food — timer stalls until food arrives.
                continue
            b.reproduction_timer += dt
            if b.reproduction_timer >= birth_interval:
                b.reproduction_timer = 0.0
                # Pay the food cost from the building's storage.
                new_food = max(0.0, food_here - food_cost)
                if new_food <= 1e-6:
                    b.storage.pop(Resource.FOOD, None)
                else:
                    b.storage[Resource.FOOD] = new_food
                # Spawn a new person at the dwelling.
                new_person = self.population.spawn(
                    b.coord, self.settings.hex_size,
                )
                new_person.home = b
                b.residents += 1
                spawned_any = True
                if self.notifications is not None:
                    self.notifications.push(
                        NOTIF_NEW_COLONIST, (180, 255, 180),
                    )
        if spawned_any:
            # Births don't change building topology — skip the costly
            # network rebuild and only flag housing + worker reassign.
            self.mark_population_changed()

    def _logistics_find_job(self, p) -> None:
        """Score every (supplier, consumer, resource) pair in *p*'s
        network and pick the best one."""
        if p.home is None:
            return
        net = self._network_of_building(p.home)
        if net is None:
            return
        # Pre-compute supply/demand per building.
        supplies: list[tuple] = []  # (b, res, amount, fill_frac)
        demands: list[tuple] = []   # (b, res, need, empty_frac)
        for b in net.buildings:
            if b.storage_capacity <= 0:
                continue
            sup = self._building_supply(b)
            for r, amt in sup.items():
                cap = max(1.0, b.storage_capacity)
                supplies.append((b, r, amt, amt / cap))
            dem = self._building_demand(b)
            for r, need in dem.items():
                cap = max(1.0, b.storage_capacity)
                demands.append((b, r, need, need / cap))

        if not supplies or not demands:
            return

        # Storage destinations only count as a fallback: if any
        # non-storage demand can be satisfied by some supplier, ignore
        # storage entirely so crafting/research/mining inputs always
        # take priority over filling up a storage building.
        non_storage_demands = [
            d for d in demands if d[0].type != BuildingType.STORAGE
        ]
        non_storage_resources = {d[1] for d in non_storage_demands}
        supply_resources = {s[1] for s in supplies}
        if non_storage_demands and (non_storage_resources & supply_resources):
            demands = non_storage_demands

        # Demand-priority filter: the demand-priority tab lets the
        # player rank consumers into tiers.  We always try to satisfy
        # the highest-occupied tier first; only if no buyer in that
        # tier wants any resource we have do we fall through to the
        # next tier.  Within a tier all buildings share the score so
        # logistics ends up balanced across equal-priority destinations.
        tiered_demands = self._filter_demands_by_tier(net, demands, supplies)
        if tiered_demands:
            demands = tiered_demands

        # Supply-priority filter: drain the highest-priority suppliers
        # first so storage stays as the fallback source it should be.
        tiered_supplies = self._filter_supplies_by_tier(net, supplies, demands)
        if tiered_supplies:
            supplies = tiered_supplies

        # ── Reservation: subtract capacity already claimed by other
        # logistics workers so new workers spread to uncovered needs
        # instead of all piling onto the same highest-scoring route.
        # Workers in PICKUP haven't deducted ``src.storage`` yet, so
        # their pending pickup reserves the supply.  Workers in
        # DELIVER have already physically removed the resource from
        # ``src``; reserving it again would double-count and starve
        # otherwise-viable matches at that supplier.  Destination
        # demand is reserved in BOTH states (the cargo is en-route
        # either way).
        claimed_supply: dict[tuple[int, object], float] = {}  # (id(b), res) → qty
        claimed_demand: dict[tuple[int, object], float] = {}
        carry_cap = params.LOGISTICS_CARRY_CAPACITY
        for other in self.population.people:
            if other is p or not other.is_logistics:
                continue
            if other.logistics_dst is None:
                continue
            res_key = other.logistics_res
            if other.task == Task.LOGISTICS_PICKUP and other.logistics_src is not None:
                sk = (id(other.logistics_src), res_key)
                claimed_supply[sk] = claimed_supply.get(sk, 0.0) + carry_cap
                dk = (id(other.logistics_dst), res_key)
                claimed_demand[dk] = claimed_demand.get(dk, 0.0) + carry_cap
            elif other.task == Task.LOGISTICS_DELIVER:
                # Reserve only the destination — the supply has
                # already been physically consumed at pickup.  Use the
                # carrying amount (more accurate than carry_cap when
                # the worker is hauling a partial load).
                amt = float(other.logistics_amount or 0.0) or float(carry_cap)
                dk = (id(other.logistics_dst), res_key)
                claimed_demand[dk] = claimed_demand.get(dk, 0.0) + amt

        # Collect every viable (sb, db, res) candidate with its score
        # so that if the absolute-best pair turns out to be unreachable
        # from the worker's current hex, we can fall back to the next
        # best instead of giving up for the frame (which used to leave
        # supply/demand pairs unserved indefinitely whenever the top
        # pair had a transient pathing issue).
        candidates: list[tuple[float, "Building", "Building", "Resource"]] = []
        # Fairness term: a consumer that just received a delivery is
        # deprioritised for a few seconds so siblings in the same
        # demand tier can catch up.  The window is short on purpose —
        # within a tier we want the haulers to rotate every dispatch,
        # not just settle on the most-empty building.
        FAIR_FULL_BONUS_AFTER = 4.0
        FAIR_BONUS_WEIGHT = 1.5
        now = self.time_elapsed
        for sb, sres, samt, sfill in supplies:
            # Effective supply after subtracting claimed reservations.
            eff_samt = samt - claimed_supply.get((id(sb), sres), 0.0)
            for db, dres, dneed, dempty in demands:
                if sres != dres or sb is db:
                    continue
                # Effective need after pending deliveries.  We use it
                # for both magnitude AND urgency so a building with
                # workers already en-route stops out-scoring siblings
                # that haven't been dispatched to yet — the previous
                # behaviour kept piling all haulers onto whichever
                # building started the frame most empty.
                claimed = claimed_demand.get((id(db), dres), 0.0)
                eff_dneed = dneed - claimed
                if dneed > 0:
                    eff_dempty = max(0.0, eff_dneed) / dneed * dempty
                else:
                    eff_dempty = 0.0
                # Bonus for storage→consumer (feeding stockpiles back
                # into the production chain).  We deliberately do NOT
                # bonus producer→storage anymore — non-storage demands
                # are filtered above so storage is a true fallback.
                storage_to_consumer = (
                    sb.type == BuildingType.STORAGE and self._is_consumer(db)
                )
                link_bonus = 0.0
                if storage_to_consumer:
                    link_bonus += 0.8
                # Urgency from fill ratios.  ``eff_dempty`` already
                # reflects pending deliveries, so equally-empty
                # tier-mates only diverge once one of them has
                # incoming cargo.
                urgency = sfill * 0.55 + eff_dempty * 0.65
                # Magnitude: what we can actually transport (effective).
                qty = min(
                    carry_cap, eff_samt, eff_dneed,
                )
                if qty <= 0:
                    continue
                magnitude = min(1.0, qty / carry_cap)
                last_served = self._demand_last_served.get(
                    (id(db), dres), -1e9,
                )
                wait = now - last_served
                if wait <= 0:
                    # Just served — penalise so siblings catch up.
                    fairness = -FAIR_BONUS_WEIGHT
                elif wait >= FAIR_FULL_BONUS_AFTER:
                    fairness = 0.0
                else:
                    # Linear ramp from -W (just served) to 0 (cooled
                    # off).  Buildings that haven't been served at
                    # all (last_served = -1e9) land in the ``>=
                    # FAIR_FULL_BONUS_AFTER`` branch above with
                    # fairness = 0, which is the neutral baseline.
                    frac = wait / FAIR_FULL_BONUS_AFTER
                    fairness = -FAIR_BONUS_WEIGHT * (1.0 - frac)
                score = (
                    urgency * 1.0
                    + link_bonus
                    + magnitude * 0.3
                    + fairness
                )
                candidates.append((score, sb, db, sres))

        if not candidates:
            return
        # Try candidates from best score down — the top pair is the
        # natural pick, but if its source isn't reachable from the
        # worker's current hex we fall back to the next-best instead
        # of leaving the worker idle for another round-robin slot.
        candidates.sort(key=lambda c: c[0], reverse=True)
        for _score, best_src, best_dst, best_res in candidates[:8]:
            if best_src.coord == p.hex_pos:
                p.logistics_src = best_src
                p.logistics_dst = best_dst
                p.logistics_res = best_res
                p.path = []
                p.task = Task.LOGISTICS_PICKUP
                self._demand_last_served[(id(best_dst), best_res)] = now
                return
            path = self._find_building_path(p.hex_pos, best_src.coord)
            if not path:
                continue
            p.logistics_src = best_src
            p.logistics_dst = best_dst
            p.logistics_res = best_res
            p.path = path
            p.task = Task.LOGISTICS_PICKUP
            # Record the assignment so siblings in the same demand tier
            # are preferred next time a hauler is dispatched.
            self._demand_last_served[(id(best_dst), best_res)] = now
            return

    def _refresh_unreachable_caches(self) -> None:
        """Recompute the unreachable / starved id-sets and push any
        new \"unreachable\" notifications.  Cheap enough to run every
        ~500 ms; the renderer reads the cached sets every frame."""
        unreachable = self._compute_unreachable_buildings()
        self._unreachable_cache = unreachable
        self._starved_cache = self._compute_starved_producers()
        if self.notifications is not None:
            for bid in unreachable - self._unreachable_notified:
                # Look up the building object for the toast label.
                # The set is small in the common case.
                for net in self.networks:
                    found = False
                    for b in net.buildings:
                        if id(b) == bid:
                            label = building_label(b.type.name)
                            self.notifications.push(
                                NOTIF_UNREACHABLE.format(name=label),
                                (230, 100, 100),
                            )
                            found = True
                            break
                    if found:
                        break
            self._unreachable_notified = (
                self._unreachable_notified | unreachable
            ) & unreachable

    def unreachable_buildings(self) -> set[int]:
        """Return ``id(b)`` for every worker-building in a network with
        no populated house.  Cached — refreshed every ~500 ms."""
        return self._unreachable_cache

    def _compute_unreachable_buildings(self) -> set[int]:
        populated_net_ids = self._populated_net_ids
        result: set[int] = set()
        for net in self.networks:
            if net.id in populated_net_ids:
                continue
            for b in net.buildings:
                if BUILDING_MAX_WORKERS.get(b.type, 0) <= 0:
                    continue
                result.add(id(b))
        return result

    def starved_producers(self) -> set[int]:
        """Return ``id(b)`` for every harvester whose resource patch
        ran dry.  Cached — refreshed every ~500 ms."""
        return self._starved_cache

    def _compute_starved_producers(self) -> set[int]:
        result: set[int] = set()
        for b in self.buildings.buildings:
            if b.workers <= 0:
                continue
            # Crafting refinery (with a recipe) is not a harvester.
            if (b.type == BuildingType.REFINERY
                    and b.recipe is not None):
                continue
            wanted = BUILDING_HARVEST_RESOURCES.get(b.type)
            if not wanted:
                continue
            # Farm produces food without consuming a tile resource —
            # never starves on the map.
            if b.type == BuildingType.FARM:
                continue
            # Gatherer's effective wanted set depends on the player's
            # selection.
            if b.type == BuildingType.GATHERER:
                if b.gatherer_output == Resource.FIBER:
                    wanted = {Resource.FIBER}
                else:
                    wanted = {Resource.FOOD}
            # Quarry's effective wanted set depends on the player's
            # selection (stone by default, or iron/copper ore).
            if b.type == BuildingType.QUARRY:
                if b.quarry_output is None:
                    wanted = {Resource.STONE}
                else:
                    wanted = {b.quarry_output}
            has_tile = False
            for nb in _hex_range(b.coord, params.COLLECTION_RADIUS):
                if nb == b.coord:
                    continue
                tile = self.grid.get(nb)
                if tile is None:
                    continue
                if tile.building is not None:
                    continue
                if Resource.FOOD in wanted and tile.food_amount > 0:
                    has_tile = True
                    break
                tres = TERRAIN_RESOURCE.get(tile.terrain)
                if (tres is not None and tres in wanted
                        and tile.resource_amount > 0):
                    has_tile = True
                    break
            if not has_tile:
                result.add(id(b))
        return result

    # ── Housing connectivity ─────────────────────────────────────

    def _connected_houses(self) -> list[Building]:
        """BFS from camp through all buildings; return non-camp houses."""
        camp = self.buildings.at(HexCoord(0, 0))
        if camp is None:
            return []
        houses: list[Building] = []
        visited: set[HexCoord] = {camp.coord}
        queue: deque[HexCoord] = deque([camp.coord])
        while queue:
            coord = queue.popleft()
            for nb in coord.neighbors():
                if nb in visited:
                    continue
                visited.add(nb)
                nb_building = self.buildings.at(nb)
                if nb_building is None:
                    continue
                if (nb_building.housing_capacity > 0
                        and nb_building.type != BuildingType.CAMP):
                    houses.append(nb_building)
                queue.append(nb)
        return houses

    def connected_housing(self) -> int:
        """Total housing = camp capacity + capacity of houses reachable
        from the camp via adjacent buildings/paths."""
        camp = self.buildings.at(HexCoord(0, 0))
        cap = camp.housing_capacity if camp else 0
        return cap + sum(h.housing_capacity for h in self._connected_houses())

    def _update_housing(self) -> None:
        """Assign every person a home.  Homeless overflow goes to camp.

        People whose home changes get a RELOCATE task with a BFS path
        through connected buildings so they visually walk to their new home.
        """
        camp = self.buildings.at(HexCoord(0, 0))
        if camp is None:
            return

        # Reset camp residents count; we'll recount below
        camp.residents = 0

        # Connected houses via shared BFS
        connected_houses = self._connected_houses()

        # Reset all house resident counts
        for house in connected_houses:
            house.residents = 0

        # People currently relocating: keep their assignment if still valid
        for person in self.population.people:
            if person.task != Task.RELOCATE or not person.path:
                continue
            home = person.home
            if home is None:
                continue
            if home == camp:
                camp.residents += 1
            elif home in connected_houses and home.residents < home.housing_capacity:
                home.residents += 1
            else:
                # Home is no longer valid — cancel relocation
                person.task = Task.IDLE
                person.path = []

        # Assign non-relocating people.  Distribute as evenly as
        # possible across every connected dwelling (camp + houses) by
        # always picking the dwelling with the fewest current residents
        # that still has capacity.  Fall back to keeping the person's
        # existing home only if it's already the most-empty option.
        dwellings: list[Building] = [camp] + list(connected_houses)
        for person in self.population.people:
            if person.task == Task.RELOCATE and person.path:
                continue  # already counted above

            old_home = person.home
            # Pick dwelling with capacity and the fewest residents.
            best: Building | None = None
            best_ratio = 2.0
            for d in dwellings:
                if d.residents >= d.housing_capacity:
                    continue
                ratio = d.residents / max(1, d.housing_capacity)
                if ratio < best_ratio:
                    best_ratio = ratio
                    best = d
            if best is None:
                # No connected dwelling has space — overflow to camp
                # (camp is also allowed to be over its cap = homeless).
                person.home = camp
                camp.residents += 1
                placed_home = camp
            else:
                # If the old home is as empty as the best option, keep
                # them there to avoid churn.
                if (old_home is not None and old_home in dwellings
                        and old_home.residents < old_home.housing_capacity
                        and old_home.residents / max(1, old_home.housing_capacity) <= best_ratio):
                    best = old_home
                person.home = best
                best.residents += 1
                placed_home = best

            # Trigger relocation animation if home changed
            if placed_home != old_home and old_home is not None:
                path = self._find_building_path(
                    person.hex_pos, placed_home.coord,
                )
                if path:
                    person.task = Task.RELOCATE
                    person.path = path
                else:
                    # No building path — snap to new home
                    person.hex_pos = placed_home.coord
                    person.snap_to_hex(self.settings.hex_size)

    def _find_building_path(
        self, start: HexCoord, end: HexCoord,
    ) -> list[HexCoord]:
        """BFS shortest path from *start* to *end* through building hexes.

        The start hex does not need a building (the person may be at a
        cleared tile).  All intermediate and destination hexes must have
        a building.

        Results are memoised in ``_path_cache`` for the duration of the
        current ``update()`` call so multiple commuters / logistics
        workers requesting the same route only pay one BFS.
        """
        if start == end:
            return []
        cache_key = (start, end)
        cached = self._path_cache.get(cache_key)
        if cached is not None:
            # Return a copy so the caller can mutate it freely.
            return list(cached)
        # Parent-pointer BFS — O(V) work, O(V) memory.  The previous
        # implementation appended ``path + [nb]`` per neighbour which
        # was O(L) per expansion and O(L^2) overall, producing visible
        # stalls when many commuters / haulers requested long routes
        # on the same tick.
        buildings_at = self.buildings.at
        visited: set[HexCoord] = {start}
        parent: dict[HexCoord, HexCoord] = {}
        queue: deque[HexCoord] = deque([start])
        found = False
        while queue:
            current = queue.popleft()
            for nb in current.neighbors():
                if nb in visited:
                    continue
                visited.add(nb)
                if buildings_at(nb) is None:
                    continue
                parent[nb] = current
                if nb == end:
                    found = True
                    queue.clear()
                    break
                queue.append(nb)
        if not found:
            self._path_cache[cache_key] = []
            return []
        path: list[HexCoord] = []
        cur = end
        while cur != start:
            path.append(cur)
            cur = parent[cur]
        path.reverse()
        self._path_cache[cache_key] = path
        return list(path)

    def find_path_route(
        self, start: HexCoord, end: HexCoord,
        *, allow_bridges: bool = False, bridge_stock: int = 0,
    ) -> list[tuple[HexCoord, BuildingType]]:
        """BFS shortest path from *start* to *end* over placeable tiles.

        Returns a list of ``(coord, BuildingType.PATH | BRIDGE)`` pairs
        from immediately after *start* up to and including *end* — the
        building type indicates what to place on each tile (PATH for
        land, BRIDGE for water).  Existing PATH/BRIDGE tiles in the
        route are reported with their existing type so callers can skip
        them rather than spending stock.

        Bridges are only considered when ``allow_bridges`` is True
        (i.e. the player has unlocked them).  If the optimal route
        requires more bridges than ``bridge_stock`` allows, the
        function falls back to a land-only route.
        """
        if start == end:
            return []
        if end not in self.grid:
            return []
        _PATH_LIKE = {BuildingType.PATH, BuildingType.BRIDGE, BuildingType.CONVEYOR}

        def passable_land(coord: HexCoord) -> bool:
            tile = self.grid.get(coord)
            if tile is None:
                return False
            if tile.terrain in UNBUILDABLE:
                return False
            b = tile.building
            if b is not None and b.type not in _PATH_LIKE:
                return False
            return True

        def passable_water(coord: HexCoord) -> bool:
            tile = self.grid.get(coord)
            if tile is None:
                return False
            if tile.terrain != Terrain.WATER:
                return False
            b = tile.building
            if b is not None and b.type != BuildingType.BRIDGE:
                return False
            return True

        def step_type(coord: HexCoord) -> BuildingType:
            tile = self.grid.get(coord)
            if tile is not None and tile.building is not None and tile.building.type in _PATH_LIKE:
                return tile.building.type
            if tile is not None and tile.terrain == Terrain.WATER:
                return BuildingType.BRIDGE
            return BuildingType.PATH

        def bfs(allow_water: bool) -> list[HexCoord]:
            visited: set[HexCoord] = {start}
            parent: dict[HexCoord, HexCoord] = {}
            queue: deque[HexCoord] = deque([start])
            found = False
            while queue:
                cur = queue.popleft()
                if cur == end:
                    found = True
                    break
                for nb in cur.neighbors():
                    if nb in visited:
                        continue
                    if passable_land(nb):
                        pass
                    elif allow_water and passable_water(nb):
                        pass
                    else:
                        continue
                    visited.add(nb)
                    parent[nb] = cur
                    queue.append(nb)
            if not found:
                return []
            route: list[HexCoord] = []
            cur = end
            while cur != start:
                route.append(cur)
                cur = parent[cur]
            route.reverse()
            return route

        # Helper to validate end is acceptable for the chosen mode.
        end_is_water = (
            self.grid.get(end) is not None
            and self.grid[end].terrain == Terrain.WATER
        )

        # Try the optimal route first (water allowed if bridges are
        # unlocked).  If the resulting bridge count exceeds the
        # player's stock, fall back to a land-only route.
        bridge_route: list[HexCoord] = []
        if allow_bridges and (passable_land(end) or passable_water(end)):
            bridge_route = bfs(allow_water=True)
            if bridge_route:
                bridges_needed = sum(
                    1 for c in bridge_route if step_type(c) == BuildingType.BRIDGE
                    and (self.grid[c].building is None
                         or self.grid[c].building.type != BuildingType.BRIDGE)
                )
                if bridges_needed <= bridge_stock or bridge_stock < 0:
                    return [(c, step_type(c)) for c in bridge_route]

        # Land-only fallback.
        if end_is_water:
            return []
        if not passable_land(end):
            return []
        land_route = bfs(allow_water=False)
        if not land_route:
            return []
        return [(c, BuildingType.PATH) for c in land_route]

    # ── Production update (Farms, Refineries, Wells) ─────────────

    def _storage_free(self, b: "Building") -> float:
        """Remaining storage capacity on *b* (never negative).

        For crafting stations with reserved input slots (Task 7),
        the input reservations are *added* to the building's nominal
        capacity so output can always grow up to ``storage_capacity``
        and inputs always have their full 2x recipe slot — they don't
        compete for the same pool.
        """
        caps = self._input_caps(b)
        if not caps:
            return max(0.0, b.storage_capacity - b.stored_total)
        # Effective output capacity = nominal capacity.
        # Effective input capacity = sum(caps), tracked per-resource.
        input_held = sum(b.storage.get(r, 0.0) for r in caps)
        output_held = b.stored_total - input_held
        return max(0.0, b.storage_capacity - output_held)

    def _input_caps(self, b: "Building") -> dict[Resource, float]:
        """Per-resource cap for crafting station inputs (2x recipe).

        Returns an empty dict for buildings that don't have per-input
        caps (and so use the regular total ``storage_capacity``).
        Research Centers also use per-input caps for their active
        research's cost (treated as recipe inputs).
        """
        if b.type in (
            BuildingType.WORKSHOP, BuildingType.FORGE,
            BuildingType.REFINERY, BuildingType.ASSEMBLER,
            BuildingType.CHEMICAL_PLANT, BuildingType.OIL_REFINERY,
        ) and isinstance(b.recipe, Resource):
            mrec = MATERIAL_RECIPES.get(b.recipe)
            if mrec is not None:
                return {r: float(amt * 2) for r, amt in mrec.inputs.items()}
        if b.type == BuildingType.RESEARCH_CENTER:
            tt = self.tech_tree
            if tt is not None and getattr(tt, "current_research", None):
                node = TECH_NODES.get(tt.current_research)
                if node is not None:
                    rc_count = max(1, len(
                        self.buildings.by_type(
                            BuildingType.RESEARCH_CENTER,
                        )
                    ))
                    return {
                        r: float(amt * 2 / rc_count)
                        for r, amt in node.cost.items()
                    }
        return {}

    def _deposit(self, b: "Building", res: Resource, amount: float) -> float:
        """Add *amount* of *res* to ``b.storage``, capped to capacity.
        Returns the amount actually deposited.

        For crafting station inputs, each ingredient is capped at
        exactly 2x the recipe requirement so input slots stay
        physically separated from output storage.
        """
        if amount <= 0:
            return 0.0
        # Per-resource cap for inputs.
        caps = self._input_caps(b)
        if res in caps:
            free = max(0.0, caps[res] - b.storage.get(res, 0.0))
        else:
            free = self._storage_free(b)
        dep = min(amount, free)
        if dep > 0:
            b.storage[res] = b.storage.get(res, 0.0) + dep
        return dep

    def _produce(self, b: "Building", res: Resource, amount: float) -> float:
        """Deposit a newly-produced resource and record cumulative production."""
        dep = self._deposit(b, res, amount)
        if dep > 0:
            self._total_produced[res] += dep
        return dep

    def _harvest_from_terrain(
        self, b: "Building", resources: set[Resource], rate_per_worker: float,
        dt: float,
    ) -> None:
        """Adjacent-terrain harvester: pulls from any tile within
        :data:`params.COLLECTION_RADIUS` whose ``TERRAIN_RESOURCE`` is
        in *resources* into the building's storage.  Always retargets
        to whichever in-range tile still has resources, so a depleted
        tile never softlocks the building.

        Also harvests food from fiber/berry patch ``food_amount``.
        """
        if b.workers <= 0:
            return
        free = self._storage_free(b)
        if free <= 0:
            b.active = False
            return
        budget = rate_per_worker * b.workers * dt
        budget = min(budget, free)
        if budget <= 0:
            return
        # Walk every tile in collection range (skipping the building's
        # own hex) and pull from the first one with resource.  This
        # guarantees automatic retargeting: when a tile depletes, the
        # next call lands on a different tile without intervention.
        produced = False
        for nb in _hex_range(b.coord, params.COLLECTION_RADIUS):
            if budget <= 0:
                break
            if nb == b.coord:
                continue
            tile = self.grid.get(nb)
            if tile is None:
                continue
            # A path / wall / bridge or any other building sitting on a
            # resource tile makes that tile uncollectable — the
            # resource is preserved, just sealed off.
            if tile.building is not None:
                continue
            # Try food harvest from food_amount on fiber/berry patches
            if Resource.FOOD in resources and tile.food_amount > 0:
                take = min(budget, tile.food_amount)
                tile.food_amount -= take
                self._produce(b, Resource.FOOD, take)
                budget -= take
                produced = True
                self._maybe_deplete_tile(tile)
                continue
            res = TERRAIN_RESOURCE.get(tile.terrain)
            if res is None or res not in resources:
                continue
            if tile.resource_amount <= 0:
                continue
            take = min(budget, tile.resource_amount)
            tile.resource_amount -= take
            self._produce(b, res, take)
            budget -= take
            produced = True
            self._maybe_deplete_tile(tile)
        b.active = produced

    def _maybe_deplete_tile(self, tile: "HexTile") -> None:
        """Convert a tile to grass once all its resources are exhausted.

        Records the change in :attr:`pending_depleted_tiles` so the
        renderer can strip the now-stale overlay sprites (trees,
        stones, ore crystals) and re-blend the tile colour next frame.
        """
        if tile.terrain == Terrain.GRASS or tile.terrain == Terrain.WATER:
            return
        if tile.resource_amount <= 0 and tile.food_amount <= 0:
            if tile.underlying_terrain is not None:
                tile.terrain = tile.underlying_terrain
                tile.underlying_terrain = None
            else:
                tile.terrain = Terrain.GRASS
            self.pending_depleted_tiles.add(tile.coord)

    def _update_production(self, dt: float) -> None:
        """Per-frame resource production.  All outputs go into the
        building's own ``storage`` (halting when full)."""
        s = self.settings
        # Woodcutter
        for b in self.buildings.by_type(BuildingType.WOODCUTTER):
            self._harvest_from_terrain(
                b, {Resource.WOOD}, s.gather_wood, dt,
            )
        # Quarry: mines stone by default, or iron/copper ore if selected.
        for b in self.buildings.by_type(BuildingType.QUARRY):
            if b.quarry_output is None:
                self._harvest_from_terrain(
                    b, {Resource.STONE}, s.gather_stone, dt,
                )
            else:
                self._harvest_from_terrain(
                    b, {b.quarry_output}, params.QUARRY_ORE_RATE, dt,
                )
        # Gatherer: produce only the user-selected resource (default food)
        for b in self.buildings.by_type(BuildingType.GATHERER):
            if b.gatherer_output == Resource.FIBER:
                self._harvest_from_terrain(
                    b, {Resource.FIBER}, s.gather_fiber, dt,
                )
            else:
                self._harvest_from_terrain(
                    b, {Resource.FOOD}, s.gather_food, dt,
                )

        # Pre-compute well locations for farm bonus
        well_coords: set[HexCoord] = set()
        for b in self.buildings.by_type(BuildingType.WELL):
            well_coords.add(b.coord)

        # Farm: produces food per worker, boosted by adjacent wells.
        for farm in self.buildings.by_type(BuildingType.FARM):
            if farm.workers <= 0:
                continue
            if self._storage_free(farm) <= 0:
                farm.active = False
                continue
            bonus = 1.0
            for nb in farm.coord.neighbors():
                if nb in well_coords:
                    bonus += params.WELL_FARM_BONUS
                    break
            amount = params.FARM_FOOD_RATE * farm.workers * bonus * dt
            self._produce(farm, Resource.FOOD, amount)
            farm.active = True

        # Refinery: if no active recipe, harvests ore from in-range
        # veins into its own storage.  If a recipe is set, it runs as
        # a crafting station (handled by _update_workshops).
        for ref in self.buildings.by_type(BuildingType.REFINERY):
            if ref.recipe is not None:
                continue
            if ref.workers <= 0:
                continue
            if self._storage_free(ref) <= 0:
                ref.active = False
                continue
            rate = params.REFINERY_RATE * ref.workers * dt
            produced = False
            for nb in _hex_range(ref.coord, params.COLLECTION_RADIUS):
                if rate <= 0:
                    break
                if nb == ref.coord:
                    continue
                tile = self.grid.get(nb)
                if tile is None or tile.resource_amount <= 0:
                    continue
                if tile.building is not None:
                    continue
                if tile.terrain == Terrain.IRON_VEIN:
                    take = min(rate, tile.resource_amount,
                               self._storage_free(ref))
                    if take > 0:
                        tile.resource_amount -= take
                        self._produce(ref, Resource.IRON, take)
                        rate -= take
                        produced = True
                        self._maybe_deplete_tile(tile)
                elif tile.terrain == Terrain.COPPER_VEIN:
                    take = min(rate, tile.resource_amount,
                               self._storage_free(ref))
                    if take > 0:
                        tile.resource_amount -= take
                        self._produce(ref, Resource.COPPER, take)
                        rate -= take
                        produced = True
                        self._maybe_deplete_tile(tile)
            ref.active = produced

        # Mining machine: automated miner.  Burns CHARCOAL from its
        # own storage, falling back to the global inventory.  Produces
        # iron/copper from adjacent veins into its storage.
        for mm in self.buildings.by_type(BuildingType.MINING_MACHINE):
            adjacent_ores: list[tuple[HexCoord, Resource]] = []
            for nb in _hex_range(mm.coord, params.COLLECTION_RADIUS):
                if nb == mm.coord:
                    continue
                tile = self.grid.get(nb)
                if tile is None or tile.resource_amount <= 0:
                    continue
                if tile.building is not None:
                    continue
                if tile.terrain == Terrain.IRON_VEIN:
                    adjacent_ores.append((nb, Resource.IRON))
                elif tile.terrain == Terrain.COPPER_VEIN:
                    adjacent_ores.append((nb, Resource.COPPER))
            if not adjacent_ores:
                mm.active = False
                continue
            if self._storage_free(mm) <= 0:
                mm.active = False
                continue

            fuel_res: Resource | None = None
            for fuel_name in params.MINING_MACHINE_ORE_PER_FUEL:
                candidate = Resource[fuel_name]
                # Strict on-site fuel: at least 1 unit of either fuel
                # must be present in the machine's own storage before
                # it begins working.  Logistics is responsible for
                # delivering it; the global inventory is no longer a
                # fallback.
                if mm.storage.get(candidate, 0.0) >= 1.0:
                    fuel_res = candidate
                    break
            if fuel_res is None:
                mm.active = False
                continue
            mm.active = True

            # Discrete fuel burn: one unit of fuel produces a fixed
            # amount of ore.  ``rate`` is the per-tick ore budget; we
            # mine ore until the budget is exhausted, deducting
            # fractional fuel from on-site storage as we go.
            ore_per_unit = params.MINING_MACHINE_ORE_PER_FUEL[fuel_res.name]
            rate = params.MINING_MACHINE_RATE * dt
            ore_mined_this_tick = 0.0
            for nb, ore in adjacent_ores:
                if rate <= 0:
                    break
                if self._storage_free(mm) <= 0:
                    break
                # Cap by remaining fuel (in ore-equivalent units).
                fuel_left = mm.storage.get(fuel_res, 0.0)
                if fuel_left <= 0:
                    break
                ore_budget_from_fuel = fuel_left * ore_per_unit
                tile = self.grid.get(nb)
                if tile is None:
                    continue
                take = min(rate, tile.resource_amount,
                           self._storage_free(mm),
                           ore_budget_from_fuel)
                if take > 0:
                    tile.resource_amount -= take
                    self._produce(mm, ore, take)
                    rate -= take
                    ore_mined_this_tick += take
                    self._maybe_deplete_tile(tile)
            if ore_mined_this_tick > 0:
                fuel_used = ore_mined_this_tick / ore_per_unit
                remaining = mm.storage.get(fuel_res, 0.0) - fuel_used
                if remaining <= 1e-6:
                    mm.storage.pop(fuel_res, None)
                else:
                    mm.storage[fuel_res] = remaining

        # Oil drill: placed *on top of* an OIL_DEPOSIT tile.  No fuel
        # required — extracts OIL into its own storage at a fixed rate
        # until the deposit beneath is depleted (then the tile reverts
        # to its underlying terrain).
        for od in self.buildings.by_type(BuildingType.OIL_DRILL):
            tile = self.grid.get(od.coord)
            if tile is None or tile.terrain != Terrain.OIL_DEPOSIT:
                od.active = False
                continue
            if tile.resource_amount <= 0:
                od.active = False
                continue
            free = self._storage_free(od)
            if free <= 0:
                od.active = False
                continue
            take = min(params.OIL_DRILL_RATE * dt, tile.resource_amount, free)
            if take <= 0:
                od.active = False
                continue
            tile.resource_amount -= take
            self._produce(od, Resource.OIL, take)
            od.active = True
            self._maybe_deplete_tile(tile)

    # ── Crafting stations (Workshop / Forge / Refinery) ──────────

    def _update_workshops(self, dt: float) -> None:
        """Advance crafting at every Workshop, Forge, and Refinery.

        A station's ``recipe`` may be either:
          * a ``BuildingType`` — crafts a placeable building (Workshop only).
          * a ``Resource``     — crafts an intermediate material using
            :data:`MATERIAL_RECIPES`.  The output is added to the world
            inventory; inputs are consumed from it.
        """
        station_types = (
            BuildingType.WORKSHOP,
            BuildingType.FORGE,
            BuildingType.REFINERY,
            BuildingType.ASSEMBLER,
            BuildingType.CHEMICAL_PLANT,
            BuildingType.OIL_REFINERY,
        )
        for stype in station_types:
            for station in self.buildings.by_type(stype):
                if station.recipe is None or station.workers <= 0:
                    continue

                if isinstance(station.recipe, BuildingType):
                    # Building recipe — check params for valid station.
                    expected_station = params.BUILDING_RECIPE_STATION.get(
                        station.recipe.name
                    )
                    if expected_station != stype.name:
                        station.recipe = None
                        station.craft_progress = 0.0
                        continue
                    self._tick_building_recipe(station, dt, BUILDING_COSTS)
                elif isinstance(station.recipe, Resource):
                    recipe = MATERIAL_RECIPES.get(station.recipe)
                    if recipe is None or recipe.station != stype.name:
                        # Stale recipe — clear it.
                        station.recipe = None
                        station.craft_progress = 0.0
                        continue
                    self._tick_material_recipe(station, recipe, dt)

    def _tick_building_recipe(
        self, station, dt: float, building_costs,
    ) -> None:
        # Building recipes consume from the station's local storage
        # first (so logistics deliveries to the workshop are spent
        # there) and fall back to the global inventory.  This matches
        # how material recipes work and lets the demand-priority tab
        # actually feed the workshop.
        cost = building_costs[station.recipe]
        can_afford = all(
            self._station_available(station, res, amount) >= amount
            for res, amount in cost.costs.items()
        )
        if not can_afford:
            return
        station.craft_progress += dt * station.workers
        if station.craft_progress >= params.WORKSHOP_CRAFT_TIME:
            for res, amount in cost.costs.items():
                self._station_consume(station, res, amount)
            self.building_inventory.add(station.recipe)
            station.craft_progress = 0.0

    def _station_available(
        self, station, res: Resource, amount: float,
    ) -> float:
        """How much of *res* the station can draw on, counting its own
        storage first, the global inventory second."""
        return station.storage.get(res, 0.0) + self.inventory[res]

    def _station_consume(
        self, station, res: Resource, amount: float,
    ) -> None:
        """Consume *amount* of *res*, preferring the station's storage."""
        from_local = min(station.storage.get(res, 0.0), amount)
        if from_local > 0:
            station.storage[res] = station.storage.get(res, 0.0) - from_local
            if station.storage[res] <= 1e-6:
                station.storage.pop(res, None)
        rem = amount - from_local
        if rem > 0:
            self.inventory.spend(res, rem)

    def _tick_material_recipe(self, station, recipe, dt: float) -> None:
        # Ensure there's room to deposit the next batch of output.
        free = self._storage_free(station)
        if free < recipe.output_amount:
            # Halt production when output can't fit.
            station.active = False
            return
        # Check inputs (storage + global inventory fallback).
        for res, amount in recipe.inputs.items():
            if self._station_available(station, res, amount) < amount:
                return
        station.craft_progress += dt * station.workers
        station.active = station.workers > 0
        if station.craft_progress >= recipe.time:
            for res, amount in recipe.inputs.items():
                self._station_consume(station, res, amount)
            self._produce(station, recipe.output, recipe.output_amount)
            station.craft_progress = 0.0
