"""Resource types and inventory management for Hex Colony."""

from __future__ import annotations

from enum import Enum, auto

from compprog_pygame.games.hex_colony.hex_grid import Terrain


class Resource(Enum):
    """Resource types."""
    WOOD = auto()
    FIBER = auto()
    STONE = auto()
    FOOD = auto()
    IRON = auto()
    COPPER = auto()


# Mapping from terrain to the resource it yields

TERRAIN_RESOURCE: dict[Terrain, Resource] = {
    Terrain.FOREST: Resource.WOOD,
    Terrain.DENSE_FOREST: Resource.WOOD,
    Terrain.STONE_DEPOSIT: Resource.STONE,
    Terrain.FIBER_PATCH: Resource.FIBER,
    Terrain.IRON_VEIN: Resource.IRON,
    Terrain.COPPER_VEIN: Resource.COPPER,
}


class Inventory:
    """Simple resource stockpile."""

    def __init__(self) -> None:
        self._stock: dict[Resource, float] = {r: 0.0 for r in Resource}

    def __getitem__(self, res: Resource) -> float:
        return self._stock[res]

    def __setitem__(self, res: Resource, value: float) -> None:
        self._stock[res] = max(0.0, value)

    def add(self, res: Resource, amount: float) -> None:
        self._stock[res] += amount

    def spend(self, res: Resource, amount: float) -> bool:
        """Try to spend *amount*. Returns True if successful."""
        if self._stock[res] >= amount:
            self._stock[res] -= amount
            return True
        return False

    def items(self):
        return self._stock.items()
