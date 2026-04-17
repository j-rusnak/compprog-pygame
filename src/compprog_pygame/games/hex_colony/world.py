"""World generation for Hex Colony.

Creates the initial hex map with terrain and resources, places the starting
camp, and spawns the initial population.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

from compprog_pygame.games.hex_colony.buildings import Building, BuildingManager, BuildingType, BUILDING_MAX_WORKERS
from compprog_pygame.games.hex_colony.hex_grid import HexCoord, HexGrid
from compprog_pygame.games.hex_colony.people import PopulationManager, Task
from compprog_pygame.games.hex_colony.procgen import generate_terrain
from compprog_pygame.games.hex_colony.resources import BuildingInventory, Inventory, Resource
from compprog_pygame.games.hex_colony.settings import HexColonySettings
from compprog_pygame.games.hex_colony import params


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

    @property
    def name(self) -> str:
        return f"Network {self.id}"

    def contains(self, b: Building) -> bool:
        return id(b) in self._bids


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
        self._housing_dirty: bool = True  # needs recalc on first frame
        # Per-building-network worker priority lists.  ``networks`` is
        # rebuilt each frame; each Network keeps its own tier list so
        # the player can edit them independently in the UI.
        self.networks: list[Network] = []
        self._next_network_id: int = 1
        # Buildings we've already notified the player are unreachable
        # (no path from any populated house).  Tracked by ``id(b)`` so
        # the warning pushes exactly once per newly-stranded building.
        self._unreachable_notified: set[int] = set()
        # Optional NotificationManager plugged in by game.py for
        # one-time toasts like "No workers can reach X".
        self.notifications: object | None = None

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

    # ── Generation ───────────────────────────────────────────────

    @classmethod
    def generate(cls, settings: HexColonySettings, seed: str = "default") -> World:
        world = cls(settings)
        world.seed = seed
        world.grid = generate_terrain(seed, settings)
        world._place_starting_camp()
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
        camp.storage_capacity = sum(
            v * m for v in (s.start_wood, s.start_fiber, s.start_stone, s.start_food)
        ) + params.START_IRON + params.START_COPPER

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

        # Recompute connected housing only when buildings/population changed
        if self._housing_dirty:
            self._update_housing()
            self._housing_dirty = False

        # Keep networks and worker-priority lists in sync with placed
        # buildings, assign targets, and dispatch commuters.  The
        # building.workers count is rebuilt from people actually present
        # at the end so production naturally gates on arrival.
        self._rebuild_networks()
        self._assign_workers()
        self._dispatch_commuters()

        # Farm & Refinery production
        self._update_production(dt)

        # Workshop crafting
        self._update_workshops(dt)

        # Move people
        self.population.update(dt, self, self.settings.hex_size)

        # Finally, recount present workers (must be AFTER movement so
        # newly-arrived commuters are credited this frame).
        self._recount_present_workers()
        self._check_unreachable_buildings()

    def mark_housing_dirty(self) -> None:
        """Flag that housing assignments need recalculation."""
        self._housing_dirty = True

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
            ))

        # Stable display order: by id ascending.
        new_networks.sort(key=lambda n: n.id)
        self.networks = new_networks

    # ── Worker assignment & dispatch ─────────────────────────────

    def _network_of_building(self, b: Building) -> Network | None:
        for n in self.networks:
            if n.contains(b):
                return n
        return None

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

        for net in self.networks:
            people = by_network.get(net.id, [])
            # Available = people in this network who aren't "homeless
            # overflow" at the camp.  Homeless people still belong to
            # network 1 (where the camp is) and can be assigned.
            available = len(people)
            if camp is not None and net.contains(camp):
                homeless = max(0, camp.residents - camp.housing_capacity)
                available = max(0, available - homeless)

            # Compute per-building target slot counts via the tiered
            # round-robin algorithm.
            target_slots: dict[int, int] = {
                id(b): 0
                for tier in net.priority for b in tier
            }
            remaining = available
            for tier in net.priority:
                if remaining <= 0:
                    break
                while remaining > 0:
                    placed_any = False
                    for b in tier:
                        if target_slots[id(b)] < b.max_workers:
                            target_slots[id(b)] += 1
                            remaining -= 1
                            placed_any = True
                            if remaining <= 0:
                                break
                    if not placed_any:
                        break

            # Reconcile targets with people.  First pass: respect
            # existing assignments that still have an open slot.
            remaining_slots = dict(target_slots)
            unassigned: list = []
            b_by_id: dict[int, Building] = {
                id(b): b for tier in net.priority for b in tier
            }
            for p in people:
                tgt = p.workplace_target
                if tgt is not None and id(tgt) in remaining_slots \
                        and remaining_slots[id(tgt)] > 0:
                    remaining_slots[id(tgt)] -= 1
                else:
                    p.workplace_target = None
                    unassigned.append(p)
            # Fill remaining slots with unassigned people, preserving
            # priority order (tiers top→bottom, cards left→right).
            ui = 0
            for tier in net.priority:
                for b in tier:
                    while remaining_slots.get(id(b), 0) > 0 and ui < len(unassigned):
                        unassigned[ui].workplace_target = b
                        remaining_slots[id(b)] -= 1
                        ui += 1

    def _dispatch_commuters(self) -> None:
        """Give each person a COMMUTE path when their target differs
        from their current workplace.  Workers that lost their target
        go idle; new assignments trigger path recomputation."""
        for p in self.population.people:
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

    def _check_unreachable_buildings(self) -> None:
        """Push a one-time notification for every worker-building that
        is in a network with no housed population."""
        if self.notifications is None:
            return
        # Networks with at least one populated home (camp or house).
        populated_net_ids: set[int] = set()
        for p in self.population.people:
            if p.home is None:
                continue
            net = self._network_of_building(p.home)
            if net is not None:
                populated_net_ids.add(net.id)

        current_unreachable: set[int] = set()
        for net in self.networks:
            if net.id in populated_net_ids:
                continue
            for b in net.buildings:
                if BUILDING_MAX_WORKERS.get(b.type, 0) <= 0:
                    continue
                bid = id(b)
                current_unreachable.add(bid)
                if bid in self._unreachable_notified:
                    continue
                label = b.type.name.replace("_", " ").title()
                self.notifications.push(
                    f"No workers can reach {label}", (230, 100, 100),
                )
                self._unreachable_notified.add(bid)
        # Forget buildings that became reachable again (or were deleted)
        # so a future disconnection re-notifies.
        self._unreachable_notified &= current_unreachable

    def unreachable_buildings(self) -> set[int]:
        """Return ``id(b)`` for every worker-building in a network with
        no populated house.  Used by the renderer to draw a red "!"
        marker above the affected buildings."""
        populated_net_ids: set[int] = set()
        for p in self.population.people:
            if p.home is None:
                continue
            net = self._network_of_building(p.home)
            if net is not None:
                populated_net_ids.add(net.id)
        result: set[int] = set()
        for net in self.networks:
            if net.id in populated_net_ids:
                continue
            for b in net.buildings:
                if BUILDING_MAX_WORKERS.get(b.type, 0) <= 0:
                    continue
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

        # Assign non-relocating people
        for person in self.population.people:
            if person.task == Task.RELOCATE and person.path:
                continue  # already counted above

            old_home = person.home
            placed = False
            # Try to keep them in their current home if it's connected and has space
            if old_home is not None and old_home != camp:
                if (old_home in connected_houses
                        and old_home.residents < old_home.housing_capacity):
                    old_home.residents += 1
                    placed = True
            if not placed:
                # Find a connected house with space
                for house in connected_houses:
                    if house.residents < house.housing_capacity:
                        person.home = house
                        house.residents += 1
                        placed = True
                        break
            if not placed:
                # Assign to camp (may be over capacity = homeless)
                person.home = camp
                camp.residents += 1

            # Trigger relocation animation if home changed
            if person.home != old_home and old_home is not None:
                path = self._find_building_path(
                    person.hex_pos, person.home.coord,
                )
                if path:
                    person.task = Task.RELOCATE
                    person.path = path
                else:
                    # No building path — snap to new home
                    person.hex_pos = person.home.coord
                    person.snap_to_hex(self.settings.hex_size)

    def _find_building_path(
        self, start: HexCoord, end: HexCoord,
    ) -> list[HexCoord]:
        """BFS shortest path from *start* to *end* through building hexes.

        The start hex does not need a building (the person may be at a
        cleared tile).  All intermediate and destination hexes must have
        a building.
        """
        if start == end:
            return []
        visited: set[HexCoord] = {start}
        queue: deque[tuple[HexCoord, list[HexCoord]]] = deque([(start, [])])
        while queue:
            current, path = queue.popleft()
            for nb in current.neighbors():
                if nb in visited:
                    continue
                visited.add(nb)
                if self.buildings.at(nb) is None:
                    continue
                new_path = path + [nb]
                if nb == end:
                    return new_path
                queue.append((nb, new_path))
        return []

    # ── Production update (Farms, Refineries, Wells) ─────────────

    def _update_production(self, dt: float) -> None:
        """Per-frame resource production from farms and refineries."""
        # Pre-compute well locations for farm bonus
        well_coords: set[HexCoord] = set()
        for b in self.buildings.by_type(BuildingType.WELL):
            well_coords.add(b.coord)

        # Farm: produces food per worker, boosted by adjacent wells
        for farm in self.buildings.by_type(BuildingType.FARM):
            if farm.workers <= 0:
                continue
            bonus = 1.0
            for nb in farm.coord.neighbors():
                if nb in well_coords:
                    bonus += params.WELL_FARM_BONUS
                    break  # only one well bonus
            amount = params.FARM_FOOD_RATE * farm.workers * bonus * dt
            self.inventory.add(Resource.FOOD, amount)

        # Refinery: produces from adjacent iron/copper veins
        for refinery in self.buildings.by_type(BuildingType.REFINERY):
            if refinery.workers <= 0:
                continue
            amount = params.REFINERY_RATE * refinery.workers * dt
            # Check adjacent ore tiles and produce
            for nb in refinery.coord.neighbors():
                tile = self.grid.get(nb)
                if tile is None:
                    continue
                from compprog_pygame.games.hex_colony.hex_grid import Terrain
                if tile.terrain == Terrain.IRON_VEIN:
                    self.inventory.add(Resource.IRON, amount)
                elif tile.terrain == Terrain.COPPER_VEIN:
                    self.inventory.add(Resource.COPPER, amount)

        # Mining machine: automated miner.  Requires fuel (CHARCOAL
        # for now; other fuels will be added later).  Produces
        # iron/copper from adjacent veins while fuel is available.
        from compprog_pygame.games.hex_colony.hex_grid import Terrain
        for mm in self.buildings.by_type(BuildingType.MINING_MACHINE):
            # Needs at least one adjacent ore tile to do useful work.
            adjacent_ores: list[Resource] = []
            for nb in mm.coord.neighbors():
                tile = self.grid.get(nb)
                if tile is None:
                    continue
                if tile.terrain == Terrain.IRON_VEIN:
                    adjacent_ores.append(Resource.IRON)
                elif tile.terrain == Terrain.COPPER_VEIN:
                    adjacent_ores.append(Resource.COPPER)
            if not adjacent_ores:
                mm.active = False
                continue

            # Try each accepted fuel in priority order; stop at the
            # first one the stockpile has enough of.
            fuel_needed = params.MINING_MACHINE_FUEL_RATE * dt
            fuel_res: Resource | None = None
            for fuel_name in params.MINING_MACHINE_FUELS:
                candidate = Resource[fuel_name]
                if self.inventory[candidate] >= fuel_needed:
                    fuel_res = candidate
                    break
            if fuel_res is None:
                mm.active = False
                continue

            self.inventory.spend(fuel_res, fuel_needed)
            mm.active = True
            amount = params.MINING_MACHINE_RATE * dt
            for ore in adjacent_ores:
                self.inventory.add(ore, amount)

    # ── Crafting stations (Workshop / Forge / Refinery) ──────────

    def _update_workshops(self, dt: float) -> None:
        """Advance crafting at every Workshop, Forge, and Refinery.

        A station's ``recipe`` may be either:
          * a ``BuildingType`` — crafts a placeable building (Workshop only).
          * a ``Resource``     — crafts an intermediate material using
            :data:`MATERIAL_RECIPES`.  The output is added to the world
            inventory; inputs are consumed from it.
        """
        from compprog_pygame.games.hex_colony.buildings import BUILDING_COSTS
        from compprog_pygame.games.hex_colony.resources import (
            MATERIAL_RECIPES, Resource,
        )

        station_types = (
            BuildingType.WORKSHOP,
            BuildingType.FORGE,
            BuildingType.REFINERY,
            BuildingType.ASSEMBLER,
        )
        for stype in station_types:
            for station in self.buildings.by_type(stype):
                if station.recipe is None or station.workers <= 0:
                    continue

                if isinstance(station.recipe, BuildingType):
                    # Building recipe — Workshop only.
                    if stype is not BuildingType.WORKSHOP:
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
        cost = building_costs[station.recipe]
        can_afford = all(
            self.inventory[res] >= amount
            for res, amount in cost.costs.items()
        )
        if not can_afford:
            return
        station.craft_progress += dt * station.workers
        if station.craft_progress >= params.WORKSHOP_CRAFT_TIME:
            for res, amount in cost.costs.items():
                self.inventory.spend(res, amount)
            self.building_inventory.add(station.recipe)
            station.craft_progress = 0.0

    def _tick_material_recipe(self, station, recipe, dt: float) -> None:
        can_afford = all(
            self.inventory[res] >= amount
            for res, amount in recipe.inputs.items()
        )
        if not can_afford:
            return
        station.craft_progress += dt * station.workers
        if station.craft_progress >= recipe.time:
            for res, amount in recipe.inputs.items():
                self.inventory.spend(res, amount)
            self.inventory.add(recipe.output, recipe.output_amount)
            station.craft_progress = 0.0
