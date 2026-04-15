"""World generation for Hex Colony.

Creates the initial hex map with terrain and resources, places the starting
camp, and spawns the initial population.
"""

from __future__ import annotations

from collections import deque

from compprog_pygame.games.hex_colony.buildings import Building, BuildingManager, BuildingType
from compprog_pygame.games.hex_colony.hex_grid import HexCoord, HexGrid, HexTile, Terrain
from compprog_pygame.games.hex_colony.people import Person, PopulationManager, Task
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
        """Assign every person a home.  Homeless overflow goes to camp.

        People whose home changes get a RELOCATE task with a BFS path
        through connected buildings so they visually walk to their new home.
        """
        camp = self.buildings.at(HexCoord(0, 0))
        if camp is None:
            return

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
