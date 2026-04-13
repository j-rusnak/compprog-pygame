"""Buildings for Hex Colony.

Buildings occupy a single hex tile. The camp is the starting structure.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto

from compprog_pygame.games.hex_colony.hex_grid import HexCoord
from compprog_pygame.games.hex_colony.resources import Resource


class BuildingType(Enum):
    CAMP = auto()           # starting base — stores resources, shelters people
    WOODCUTTER = auto()     # harvests wood from adjacent forest hexes
    QUARRY = auto()         # harvests stone from adjacent stone deposits
    GATHERER = auto()       # harvests fiber and food from adjacent patches
    STORAGE = auto()        # extra resource storage capacity


@dataclass(slots=True)
class BuildingCost:
    """Resources required to construct a building."""
    costs: dict[Resource, int]


# What each building costs to place
BUILDING_COSTS: dict[BuildingType, BuildingCost] = {
    BuildingType.CAMP: BuildingCost({}),  # free (starting building)
    BuildingType.WOODCUTTER: BuildingCost({Resource.WOOD: 10, Resource.STONE: 5}),
    BuildingType.QUARRY: BuildingCost({Resource.WOOD: 15, Resource.FIBER: 5}),
    BuildingType.GATHERER: BuildingCost({Resource.WOOD: 8, Resource.STONE: 3}),
    BuildingType.STORAGE: BuildingCost({Resource.WOOD: 20, Resource.STONE: 10}),
}

# Max workers each building supports
BUILDING_MAX_WORKERS: dict[BuildingType, int] = {
    BuildingType.CAMP: 0,
    BuildingType.WOODCUTTER: 2,
    BuildingType.QUARRY: 2,
    BuildingType.GATHERER: 3,
    BuildingType.STORAGE: 0,
}


@dataclass(slots=True)
class Building:
    """A placed building on the map."""
    type: BuildingType
    coord: HexCoord
    workers: int = 0
    built: bool = True  # False while under construction
    build_progress: float = 0.0  # 0..1

    @property
    def max_workers(self) -> int:
        return BUILDING_MAX_WORKERS.get(self.type, 0)


class BuildingManager:
    """Tracks all placed buildings."""

    def __init__(self) -> None:
        self.buildings: list[Building] = []

    def place(self, btype: BuildingType, coord: HexCoord) -> Building:
        b = Building(type=btype, coord=coord)
        self.buildings.append(b)
        return b

    def at(self, coord: HexCoord) -> Building | None:
        for b in self.buildings:
            if b.coord == coord:
                return b
        return None

    def by_type(self, btype: BuildingType) -> list[Building]:
        return [b for b in self.buildings if b.type == btype]
