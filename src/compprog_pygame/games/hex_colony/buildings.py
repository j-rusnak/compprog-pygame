"""Buildings for Hex Colony.

Buildings occupy a single hex tile. The camp is the starting structure.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto

from compprog_pygame.games.hex_colony.hex_grid import HexCoord
from compprog_pygame.games.hex_colony.resources import Resource


class BuildingType(Enum):
    CAMP = auto()           # starting base — stores resources, shelters people
    HOUSE = auto()          # houses up to 5 people
    PATH = auto()           # dirt path — connects visually to adjacent paths
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
    BuildingType.HOUSE: BuildingCost({Resource.WOOD: 12, Resource.FIBER: 4}),
    BuildingType.PATH: BuildingCost({Resource.STONE: 2}),
    BuildingType.WOODCUTTER: BuildingCost({Resource.WOOD: 10, Resource.STONE: 5}),
    BuildingType.QUARRY: BuildingCost({Resource.WOOD: 15, Resource.FIBER: 5}),
    BuildingType.GATHERER: BuildingCost({Resource.WOOD: 8, Resource.STONE: 3}),
    BuildingType.STORAGE: BuildingCost({Resource.WOOD: 20, Resource.STONE: 10}),
}

# Max workers each building supports
BUILDING_MAX_WORKERS: dict[BuildingType, int] = {
    BuildingType.CAMP: 0,
    BuildingType.HOUSE: 0,
    BuildingType.PATH: 0,
    BuildingType.WOODCUTTER: 2,
    BuildingType.QUARRY: 2,
    BuildingType.GATHERER: 3,
    BuildingType.STORAGE: 0,
}

# Housing capacity per building type (0 = not a dwelling)
BUILDING_HOUSING: dict[BuildingType, int] = {
    BuildingType.CAMP: 10,
    BuildingType.HOUSE: 5,
    BuildingType.PATH: 0,
    BuildingType.WOODCUTTER: 0,
    BuildingType.QUARRY: 0,
    BuildingType.GATHERER: 0,
    BuildingType.STORAGE: 0,
}

# Storage capacity per building type.
# Harvesting buildings store up to 10 of their resource type.
# Storage building stores up to 100 total (mixed).
# Camp capacity is set at placement time (2× starting resources).
BUILDING_STORAGE_CAPACITY: dict[BuildingType, int] = {
    BuildingType.CAMP: 0,        # set dynamically at placement
    BuildingType.HOUSE: 0,
    BuildingType.PATH: 0,
    BuildingType.WOODCUTTER: 10,
    BuildingType.QUARRY: 10,
    BuildingType.GATHERER: 20,   # 10 fiber + 10 food
    BuildingType.STORAGE: 100,
}

# Default starting stock when a building is placed.
# Camp stock is set dynamically (2× starting resources).
BUILDING_DEFAULT_STOCK: dict[BuildingType, dict[Resource, float]] = {
    BuildingType.WOODCUTTER: {Resource.WOOD: 10},
    BuildingType.QUARRY: {Resource.STONE: 10},
    BuildingType.GATHERER: {Resource.FIBER: 10, Resource.FOOD: 10},
}


@dataclass(slots=True)
class Building:
    """A placed building on the map."""
    type: BuildingType
    coord: HexCoord
    workers: int = 0
    residents: int = 0  # people living here (for dwellings)
    built: bool = True  # False while under construction
    build_progress: float = 0.0  # 0..1
    storage: dict[Resource, float] = field(default_factory=dict)
    storage_capacity: int = 0  # max total resources stored

    @property
    def max_workers(self) -> int:
        return BUILDING_MAX_WORKERS.get(self.type, 0)

    @property
    def housing_capacity(self) -> int:
        return BUILDING_HOUSING.get(self.type, 0)

    @property
    def stored_total(self) -> float:
        """Sum of all resources currently stored."""
        return sum(self.storage.values())


class BuildingManager:
    """Tracks all placed buildings."""

    def __init__(self) -> None:
        self.buildings: list[Building] = []

    def place(self, btype: BuildingType, coord: HexCoord) -> Building:
        b = Building(
            type=btype,
            coord=coord,
            storage=dict(BUILDING_DEFAULT_STOCK.get(btype, {})),
            storage_capacity=BUILDING_STORAGE_CAPACITY.get(btype, 0),
        )
        self.buildings.append(b)
        return b

    def at(self, coord: HexCoord) -> Building | None:
        for b in self.buildings:
            if b.coord == coord:
                return b
        return None

    def remove(self, building: Building) -> None:
        """Remove a building from the manager."""
        self.buildings.remove(building)

    def by_type(self, btype: BuildingType) -> list[Building]:
        return [b for b in self.buildings if b.type == btype]
