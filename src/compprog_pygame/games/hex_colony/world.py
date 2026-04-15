"""World generation for Hex Colony.

Creates the initial hex map with terrain and resources, places the starting
camp, and spawns the initial population.
"""

from __future__ import annotations

from collections import deque

from compprog_pygame.games.hex_colony.buildings import Building, BuildingManager, BuildingType
from compprog_pygame.games.hex_colony.hex_grid import HexCoord, HexGrid, HexTile, Terrain
from compprog_pygame.games.hex_colony.people import Person, PopulationManager
from compprog_pygame.games.hex_colony.procgen import generate_terrain
from compprog_pygame.games.hex_colony.resources import Inventory, Resource
from compprog_pygame.games.hex_colony.settings import HexColonySettings


class World:
    """Top-level game-state container."""

    def __init__(self, settings: HexColonySettings) -> None:
        self.settings = settings
        self.grid = HexGrid()
        self.buildings = BuildingManager()
        self.population = PopulationManager()
        self.inventory = Inventory()
        self.time_elapsed: float = 0.0

    # ── Generation ───────────────────────────────────────────────

    @classmethod
    def generate(cls, settings: HexColonySettings, seed: str = "default") -> World:
        world = cls(settings)
        world.grid = generate_terrain(seed, settings)
        world._place_starting_camp()
        world._init_resources()
        world._spawn_people()
        return world

    def _place_starting_camp(self) -> None:
        origin = HexCoord(0, 0)
        camp = self.buildings.place(BuildingType.CAMP, origin)
        tile = self.grid[origin]
        tile.building = camp

    def _init_resources(self) -> None:
        s = self.settings
        self.inventory[Resource.WOOD] = s.start_wood
        self.inventory[Resource.FIBER] = s.start_fiber
        self.inventory[Resource.STONE] = s.start_stone
        self.inventory[Resource.FOOD] = s.start_food

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

        # Recompute connected housing and assign homeless
        self._update_housing()

        # Move people
        self.population.update(dt, self, self.settings.hex_size)

    # ── Housing connectivity ─────────────────────────────────────

    def connected_housing(self) -> int:
        """Total housing = camp capacity + capacity of houses reachable
        from the camp via adjacent buildings/paths.

        Every building counts as traversable (acts like a path)."""
        camp = self.buildings.at(HexCoord(0, 0))
        if camp is None:
            return 0

        total = camp.housing_capacity  # 10
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
                # Every building is traversable
                if nb_building.housing_capacity > 0 and nb_building.type != BuildingType.CAMP:
                    total += nb_building.housing_capacity
                queue.append(nb)
        return total

    def _update_housing(self) -> None:
        """Assign every person a home.  Homeless overflow goes to camp."""
        camp = self.buildings.at(HexCoord(0, 0))
        if camp is None:
            return

        total_housing = self.connected_housing()
        total_pop = self.population.count
        homeless_count = max(0, total_pop - total_housing)

        # Reset camp residents count; we'll recount below
        camp.residents = 0

        # Connected houses (BFS, same logic as connected_housing)
        connected_houses: list[Building] = []
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
                    connected_houses.append(nb_building)
                queue.append(nb)

        # Reset all house resident counts
        for house in connected_houses:
            house.residents = 0

        # Assign people to houses: first fill connected houses, overflow to camp
        people_needing_home: list[Person] = list(self.population.people)

        for person in people_needing_home:
            placed = False
            # Try to keep them in their current home if it's connected and has space
            if person.home is not None and person.home != camp:
                if (person.home in connected_houses
                        and person.home.residents < person.home.housing_capacity):
                    person.home.residents += 1
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
