"""Buildings for Hex Colony.

Buildings occupy a single hex tile. The camp is the starting structure.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto

from compprog_pygame.games.hex_colony.hex_grid import HexCoord
from compprog_pygame.games.hex_colony.resources import Resource
from compprog_pygame.games.hex_colony import params


class BuildingType(Enum):
    CAMP = auto()           # crashed spaceship — starting base, stores resources, shelters survivors
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


def _costs_from_dict(d: dict[str, int]) -> dict[Resource, int]:
    """Convert a {resource_name: amount} dict from params into {Resource: amount}."""
    return {Resource[k]: v for k, v in d.items()}


# What each building costs to place
BUILDING_COSTS: dict[BuildingType, BuildingCost] = {
    BuildingType.CAMP: BuildingCost(_costs_from_dict(params.BUILDING_COST_CAMP)),
    BuildingType.HOUSE: BuildingCost(_costs_from_dict(params.BUILDING_COST_HOUSE)),
    BuildingType.PATH: BuildingCost(_costs_from_dict(params.BUILDING_COST_PATH)),
    BuildingType.WOODCUTTER: BuildingCost(_costs_from_dict(params.BUILDING_COST_WOODCUTTER)),
    BuildingType.QUARRY: BuildingCost(_costs_from_dict(params.BUILDING_COST_QUARRY)),
    BuildingType.GATHERER: BuildingCost(_costs_from_dict(params.BUILDING_COST_GATHERER)),
    BuildingType.STORAGE: BuildingCost(_costs_from_dict(params.BUILDING_COST_STORAGE)),
}

# Max workers each building supports
BUILDING_MAX_WORKERS: dict[BuildingType, int] = {
    BuildingType.CAMP: params.BUILDING_MAX_WORKERS_CAMP,
    BuildingType.HOUSE: params.BUILDING_MAX_WORKERS_HOUSE,
    BuildingType.PATH: params.BUILDING_MAX_WORKERS_PATH,
    BuildingType.WOODCUTTER: params.BUILDING_MAX_WORKERS_WOODCUTTER,
    BuildingType.QUARRY: params.BUILDING_MAX_WORKERS_QUARRY,
    BuildingType.GATHERER: params.BUILDING_MAX_WORKERS_GATHERER,
    BuildingType.STORAGE: params.BUILDING_MAX_WORKERS_STORAGE,
}

# Housing capacity per building type (0 = not a dwelling)
BUILDING_HOUSING: dict[BuildingType, int] = {
    BuildingType.CAMP: params.BUILDING_HOUSING_CAMP,
    BuildingType.HOUSE: params.BUILDING_HOUSING_HOUSE,
    BuildingType.PATH: params.BUILDING_HOUSING_PATH,
    BuildingType.WOODCUTTER: params.BUILDING_HOUSING_WOODCUTTER,
    BuildingType.QUARRY: params.BUILDING_HOUSING_QUARRY,
    BuildingType.GATHERER: params.BUILDING_HOUSING_GATHERER,
    BuildingType.STORAGE: params.BUILDING_HOUSING_STORAGE,
}

# Storage capacity per building type.
# Harvesting buildings store up to their capacity of their resource type.
# Storage building stores up to its capacity (mixed).
# Camp capacity is set at placement time.
BUILDING_STORAGE_CAPACITY: dict[BuildingType, int] = {
    BuildingType.CAMP: params.BUILDING_STORAGE_CAMP,
    BuildingType.HOUSE: params.BUILDING_STORAGE_HOUSE,
    BuildingType.PATH: params.BUILDING_STORAGE_PATH,
    BuildingType.WOODCUTTER: params.BUILDING_STORAGE_WOODCUTTER,
    BuildingType.QUARRY: params.BUILDING_STORAGE_QUARRY,
    BuildingType.GATHERER: params.BUILDING_STORAGE_GATHERER,
    BuildingType.STORAGE: params.BUILDING_STORAGE_STORAGE,
}


@dataclass(slots=True)
class Building:
    """A placed building on the map."""
    type: BuildingType
    coord: HexCoord
    workers: int = 0
    residents: int = 0  # people living here (for dwellings)
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
        self._by_coord: dict[HexCoord, Building] = {}

    def place(self, btype: BuildingType, coord: HexCoord) -> Building:
        b = Building(
            type=btype,
            coord=coord,
            storage_capacity=BUILDING_STORAGE_CAPACITY.get(btype, 0),
        )
        self.buildings.append(b)
        self._by_coord[coord] = b
        return b

    def at(self, coord: HexCoord) -> Building | None:
        return self._by_coord.get(coord)

    def remove(self, building: Building) -> None:
        """Remove a building from the manager."""
        self.buildings.remove(building)
        self._by_coord.pop(building.coord, None)

    def by_type(self, btype: BuildingType) -> list[Building]:
        return [b for b in self.buildings if b.type == btype]


# Resources each production building can harvest
BUILDING_HARVEST_RESOURCES: dict[BuildingType, set[Resource]] = {
    BuildingType.WOODCUTTER: {Resource.WOOD},
    BuildingType.QUARRY: {Resource.STONE},
    BuildingType.GATHERER: {Resource.FIBER, Resource.FOOD},
}
