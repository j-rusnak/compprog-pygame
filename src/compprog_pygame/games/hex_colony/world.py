"""World generation for Hex Colony.

Creates the initial hex map with terrain and resources, places the starting
camp, and spawns the initial population.
"""

from __future__ import annotations

from collections import deque

from compprog_pygame.games.hex_colony.buildings import Building, BuildingManager, BuildingType
from compprog_pygame.games.hex_colony.hex_grid import HexCoord, HexGrid
from compprog_pygame.games.hex_colony.people import PopulationManager, Task
from compprog_pygame.games.hex_colony.procgen import generate_terrain
from compprog_pygame.games.hex_colony.resources import BuildingInventory, Inventory, Resource
from compprog_pygame.games.hex_colony.settings import HexColonySettings
from compprog_pygame.games.hex_colony import params


class World:
    """Top-level game-state container."""

    def __init__(self, settings: HexColonySettings) -> None:
        self.settings = settings
        self.grid = HexGrid()
        self.buildings = BuildingManager()
        self.population = PopulationManager()
        self.inventory = Inventory()
        self.building_inventory = BuildingInventory()
        self.time_elapsed: float = 0.0
        self._housing_dirty: bool = True  # needs recalc on first frame

    @property
    def game_over(self) -> bool:
        """The mission is lost when all survivors are dead."""
        return self.population.count == 0 and self.time_elapsed > 0

    # ── Generation ───────────────────────────────────────────────

    @classmethod
    def generate(cls, settings: HexColonySettings, seed: str = "default") -> World:
        world = cls(settings)
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

        # Farm & Refinery production
        self._update_production(dt)

        # Workshop crafting
        self._update_workshops(dt)

        # Move people
        self.population.update(dt, self, self.settings.hex_size)

    def mark_housing_dirty(self) -> None:
        """Flag that housing assignments need recalculation."""
        self._housing_dirty = True

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

    # ── Workshop crafting ────────────────────────────────────────

    def _update_workshops(self, dt: float) -> None:
        """Advance workshop crafting; finished items go to building inventory."""
        from compprog_pygame.games.hex_colony.buildings import BUILDING_COSTS

        for ws in self.buildings.by_type(BuildingType.WORKSHOP):
            if ws.recipe is None or ws.workers <= 0:
                continue

            # Check if resources are available for the recipe
            cost = BUILDING_COSTS[ws.recipe]
            can_afford = all(
                self.inventory[res] >= amount
                for res, amount in cost.costs.items()
            )
            if not can_afford:
                continue

            # Advance crafting progress (more workers = faster)
            ws.craft_progress += dt * ws.workers
            if ws.craft_progress >= params.WORKSHOP_CRAFT_TIME:
                # Consume resources
                for res, amount in cost.costs.items():
                    self.inventory.spend(res, amount)
                # Produce the building into inventory
                self.building_inventory.add(ws.recipe)
                ws.craft_progress = 0.0
