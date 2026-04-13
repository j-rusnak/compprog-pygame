"""World generation for Hex Colony.

Creates the initial hex map with terrain and resources, places the starting
camp, and spawns the initial population.
"""

from __future__ import annotations

import random

from compprog_pygame.games.hex_colony.buildings import Building, BuildingManager, BuildingType
from compprog_pygame.games.hex_colony.hex_grid import HexCoord, HexGrid, HexTile, Terrain
from compprog_pygame.games.hex_colony.people import PopulationManager
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
    def generate(cls, settings: HexColonySettings) -> World:
        world = cls(settings)
        world._generate_terrain()
        world._place_starting_camp()
        world._init_resources()
        world._spawn_people()
        return world

    def _generate_terrain(self) -> None:
        """Fill a hex-shaped map of the configured radius with random terrain."""
        radius = self.settings.world_radius
        for q in range(-radius, radius + 1):
            r1 = max(-radius, -q - radius)
            r2 = min(radius, -q + radius)
            for r in range(r1, r2 + 1):
                coord = HexCoord(q, r)
                terrain = self._pick_terrain(coord)
                amount = 0.0
                if terrain in (Terrain.FOREST, Terrain.DENSE_FOREST):
                    amount = random.uniform(20, 60)
                elif terrain == Terrain.STONE_DEPOSIT:
                    amount = random.uniform(30, 80)
                elif terrain == Terrain.FIBER_PATCH:
                    amount = random.uniform(15, 40)
                self.grid.set_tile(HexTile(coord=coord, terrain=terrain, resource_amount=amount))

    def _pick_terrain(self, coord: HexCoord) -> Terrain:
        """Weighted random terrain, biased toward forest near origin."""
        dist = coord.distance(HexCoord(0, 0))
        # Keep the centre clear-ish for the camp
        if dist <= 1:
            return Terrain.GRASS

        roll = random.random()
        if roll < 0.40:
            return Terrain.FOREST
        if roll < 0.55:
            return Terrain.DENSE_FOREST
        if roll < 0.65:
            return Terrain.STONE_DEPOSIT
        if roll < 0.75:
            return Terrain.FIBER_PATCH
        if roll < 0.82:
            return Terrain.WATER
        return Terrain.GRASS

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
        for _ in range(self.settings.start_population):
            self.population.spawn(origin, self.settings.hex_size)

    # ── Per-frame update ─────────────────────────────────────────

    def update(self, dt: float) -> None:
        """Advance the simulation by *dt* seconds."""
        self.time_elapsed += dt

        # Move people
        self.population.update(dt, self, self.settings.hex_size)

        # Food consumption
        food_needed = self.settings.food_consumption * self.population.count * dt
        self.inventory.spend(Resource.FOOD, food_needed)
