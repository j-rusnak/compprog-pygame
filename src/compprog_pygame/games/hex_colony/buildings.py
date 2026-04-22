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
    HOUSE = auto()          # primitive hut — used by AI enemies (not player-buildable)
    HABITAT = auto()        # futuristic modular pod — player housing
    PATH = auto()           # dirt path — connects visually to adjacent paths
    BRIDGE = auto()         # wooden bridge — path that can cross water
    WOODCUTTER = auto()     # harvests wood from adjacent forest hexes
    QUARRY = auto()         # harvests stone from adjacent stone deposits
    GATHERER = auto()       # harvests fiber and food from adjacent patches
    STORAGE = auto()        # extra resource storage capacity
    REFINERY = auto()       # processes iron/copper from adjacent ore veins
    MINING_MACHINE = auto()  # fuel-powered auto-miner for adjacent iron/copper veins
    FARM = auto()           # produces food without terrain requirement
    WELL = auto()           # boosts adjacent farm output
    WALL = auto()           # defensive stone wall — connects to adjacent walls
    WORKSHOP = auto()       # crafting workshop — produces buildings and intermediate materials
    FORGE = auto()          # stone blacksmithing forge — smelts raw ore into bars
    ASSEMBLER = auto()      # higher-tier assembler — builds gears, silicon, circuits
    RESEARCH_CENTER = auto() # research center — opens the tech tree
    TRIBAL_CAMP = auto()    # primitive tribal camp — AI tribe centerpiece (not player-buildable)
    # ── Tier 4+ industrial buildings ─────────────────────────
    CHEMICAL_PLANT = auto()  # chemical plant — synthesises plastic, rocket fuel, etc.
    CONVEYOR = auto()        # conveyor belt — workers walk faster on these tiles
    SOLAR_ARRAY = auto()     # solar array — boosts adjacent crafting stations
    ROCKET_SILO = auto()     # rocket silo — assemble & launch the colony rocket
    OIL_DRILL = auto()       # oil drill — placed on OIL_DEPOSIT, auto-extracts OIL
    OIL_REFINERY = auto()    # refines OIL into PETROLEUM and LUBRICANT    # ── Fluid handling (pipe network, parallel to worker logistics) ──
    PIPE = auto()            # connects fluid producers/consumers/tanks
    FLUID_TANK = auto()      # buffers a single fluid resource
    # ── Defensive structures (unlocked after the first awakening wave) ──
    TURRET = auto()          # auto-targets nearest enemy in range and fires
    TRAP = auto()            # one-shot trap detonates when an enemy steps on it

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
    BuildingType.HABITAT: BuildingCost(_costs_from_dict(params.BUILDING_COST_HABITAT)),
    BuildingType.PATH: BuildingCost(_costs_from_dict(params.BUILDING_COST_PATH)),
    BuildingType.BRIDGE: BuildingCost(_costs_from_dict(params.BUILDING_COST_BRIDGE)),
    BuildingType.WOODCUTTER: BuildingCost(_costs_from_dict(params.BUILDING_COST_WOODCUTTER)),
    BuildingType.QUARRY: BuildingCost(_costs_from_dict(params.BUILDING_COST_QUARRY)),
    BuildingType.GATHERER: BuildingCost(_costs_from_dict(params.BUILDING_COST_GATHERER)),
    BuildingType.STORAGE: BuildingCost(_costs_from_dict(params.BUILDING_COST_STORAGE)),
    BuildingType.REFINERY: BuildingCost(_costs_from_dict(params.BUILDING_COST_REFINERY)),
    BuildingType.MINING_MACHINE: BuildingCost(_costs_from_dict(params.BUILDING_COST_MINING_MACHINE)),
    BuildingType.FARM: BuildingCost(_costs_from_dict(params.BUILDING_COST_FARM)),
    BuildingType.WELL: BuildingCost(_costs_from_dict(params.BUILDING_COST_WELL)),
    BuildingType.WALL: BuildingCost(_costs_from_dict(params.BUILDING_COST_WALL)),
    BuildingType.WORKSHOP: BuildingCost(_costs_from_dict(params.BUILDING_COST_WORKSHOP)),
    BuildingType.FORGE: BuildingCost(_costs_from_dict(params.BUILDING_COST_FORGE)),
    BuildingType.ASSEMBLER: BuildingCost(_costs_from_dict(params.BUILDING_COST_ASSEMBLER)),
    BuildingType.RESEARCH_CENTER: BuildingCost(_costs_from_dict(params.BUILDING_COST_RESEARCH_CENTER)),
    BuildingType.TRIBAL_CAMP: BuildingCost(_costs_from_dict(params.BUILDING_COST_TRIBAL_CAMP)),
    BuildingType.CHEMICAL_PLANT: BuildingCost(_costs_from_dict(params.BUILDING_COST_CHEMICAL_PLANT)),
    BuildingType.CONVEYOR: BuildingCost(_costs_from_dict(params.BUILDING_COST_CONVEYOR)),
    BuildingType.SOLAR_ARRAY: BuildingCost(_costs_from_dict(params.BUILDING_COST_SOLAR_ARRAY)),
    BuildingType.ROCKET_SILO: BuildingCost(_costs_from_dict(params.BUILDING_COST_ROCKET_SILO)),
    BuildingType.OIL_DRILL: BuildingCost(_costs_from_dict(params.BUILDING_COST_OIL_DRILL)),
    BuildingType.OIL_REFINERY: BuildingCost(_costs_from_dict(params.BUILDING_COST_OIL_REFINERY)),
    BuildingType.PIPE: BuildingCost(_costs_from_dict(params.BUILDING_COST_PIPE)),
    BuildingType.FLUID_TANK: BuildingCost(_costs_from_dict(params.BUILDING_COST_FLUID_TANK)),
    BuildingType.TURRET: BuildingCost(_costs_from_dict(params.BUILDING_COST_TURRET)),
    BuildingType.TRAP: BuildingCost(_costs_from_dict(params.BUILDING_COST_TRAP)),
}

# Max workers each building supports
BUILDING_MAX_WORKERS: dict[BuildingType, int] = {
    BuildingType.CAMP: params.BUILDING_MAX_WORKERS_CAMP,
    BuildingType.HOUSE: params.BUILDING_MAX_WORKERS_HOUSE,
    BuildingType.HABITAT: params.BUILDING_MAX_WORKERS_HABITAT,
    BuildingType.PATH: params.BUILDING_MAX_WORKERS_PATH,
    BuildingType.BRIDGE: params.BUILDING_MAX_WORKERS_BRIDGE,
    BuildingType.WOODCUTTER: params.BUILDING_MAX_WORKERS_WOODCUTTER,
    BuildingType.QUARRY: params.BUILDING_MAX_WORKERS_QUARRY,
    BuildingType.GATHERER: params.BUILDING_MAX_WORKERS_GATHERER,
    BuildingType.STORAGE: params.BUILDING_MAX_WORKERS_STORAGE,
    BuildingType.REFINERY: params.BUILDING_MAX_WORKERS_REFINERY,
    BuildingType.MINING_MACHINE: params.BUILDING_MAX_WORKERS_MINING_MACHINE,
    BuildingType.FARM: params.BUILDING_MAX_WORKERS_FARM,
    BuildingType.WELL: params.BUILDING_MAX_WORKERS_WELL,
    BuildingType.WALL: params.BUILDING_MAX_WORKERS_WALL,
    BuildingType.WORKSHOP: params.BUILDING_MAX_WORKERS_WORKSHOP,
    BuildingType.FORGE: params.BUILDING_MAX_WORKERS_FORGE,
    BuildingType.ASSEMBLER: params.BUILDING_MAX_WORKERS_ASSEMBLER,
    BuildingType.RESEARCH_CENTER: params.BUILDING_MAX_WORKERS_RESEARCH_CENTER,
    BuildingType.TRIBAL_CAMP: params.BUILDING_MAX_WORKERS_TRIBAL_CAMP,
    BuildingType.CHEMICAL_PLANT: params.BUILDING_MAX_WORKERS_CHEMICAL_PLANT,
    BuildingType.CONVEYOR: params.BUILDING_MAX_WORKERS_CONVEYOR,
    BuildingType.SOLAR_ARRAY: params.BUILDING_MAX_WORKERS_SOLAR_ARRAY,
    BuildingType.ROCKET_SILO: params.BUILDING_MAX_WORKERS_ROCKET_SILO,
    BuildingType.OIL_DRILL: params.BUILDING_MAX_WORKERS_OIL_DRILL,
    BuildingType.OIL_REFINERY: params.BUILDING_MAX_WORKERS_OIL_REFINERY,
    BuildingType.PIPE: params.BUILDING_MAX_WORKERS_PIPE,
    BuildingType.FLUID_TANK: params.BUILDING_MAX_WORKERS_FLUID_TANK,
    BuildingType.TURRET: params.BUILDING_MAX_WORKERS_TURRET,
    BuildingType.TRAP: params.BUILDING_MAX_WORKERS_TRAP,
}

# Housing capacity per building type (0 = not a dwelling)
BUILDING_HOUSING: dict[BuildingType, int] = {
    BuildingType.CAMP: params.BUILDING_HOUSING_CAMP,
    BuildingType.HOUSE: params.BUILDING_HOUSING_HOUSE,
    BuildingType.HABITAT: params.BUILDING_HOUSING_HABITAT,
    BuildingType.PATH: params.BUILDING_HOUSING_PATH,
    BuildingType.BRIDGE: params.BUILDING_HOUSING_BRIDGE,
    BuildingType.WOODCUTTER: params.BUILDING_HOUSING_WOODCUTTER,
    BuildingType.QUARRY: params.BUILDING_HOUSING_QUARRY,
    BuildingType.GATHERER: params.BUILDING_HOUSING_GATHERER,
    BuildingType.STORAGE: params.BUILDING_HOUSING_STORAGE,
    BuildingType.REFINERY: params.BUILDING_HOUSING_REFINERY,
    BuildingType.MINING_MACHINE: params.BUILDING_HOUSING_MINING_MACHINE,
    BuildingType.FARM: params.BUILDING_HOUSING_FARM,
    BuildingType.WELL: params.BUILDING_HOUSING_WELL,
    BuildingType.WALL: params.BUILDING_HOUSING_WALL,
    BuildingType.WORKSHOP: params.BUILDING_HOUSING_WORKSHOP,
    BuildingType.FORGE: params.BUILDING_HOUSING_FORGE,
    BuildingType.ASSEMBLER: params.BUILDING_HOUSING_ASSEMBLER,
    BuildingType.RESEARCH_CENTER: params.BUILDING_HOUSING_RESEARCH_CENTER,
    BuildingType.TRIBAL_CAMP: params.BUILDING_HOUSING_TRIBAL_CAMP,
    BuildingType.CHEMICAL_PLANT: params.BUILDING_HOUSING_CHEMICAL_PLANT,
    BuildingType.CONVEYOR: params.BUILDING_HOUSING_CONVEYOR,
    BuildingType.SOLAR_ARRAY: params.BUILDING_HOUSING_SOLAR_ARRAY,
    BuildingType.ROCKET_SILO: params.BUILDING_HOUSING_ROCKET_SILO,
    BuildingType.OIL_DRILL: params.BUILDING_HOUSING_OIL_DRILL,
    BuildingType.OIL_REFINERY: params.BUILDING_HOUSING_OIL_REFINERY,
    BuildingType.PIPE: params.BUILDING_HOUSING_PIPE,
    BuildingType.FLUID_TANK: params.BUILDING_HOUSING_FLUID_TANK,
    BuildingType.TURRET: params.BUILDING_HOUSING_TURRET,
    BuildingType.TRAP: params.BUILDING_HOUSING_TRAP,
}

# Storage capacity per building type.
# Harvesting buildings store up to their capacity of their resource type.
# Storage building stores up to its capacity (mixed).
# Camp capacity is set at placement time.
BUILDING_STORAGE_CAPACITY: dict[BuildingType, int] = {
    BuildingType.CAMP: params.BUILDING_STORAGE_CAMP,
    BuildingType.HOUSE: params.BUILDING_STORAGE_HOUSE,
    BuildingType.HABITAT: params.BUILDING_STORAGE_HABITAT,
    BuildingType.PATH: params.BUILDING_STORAGE_PATH,
    BuildingType.BRIDGE: params.BUILDING_STORAGE_BRIDGE,
    BuildingType.WOODCUTTER: params.BUILDING_STORAGE_WOODCUTTER,
    BuildingType.QUARRY: params.BUILDING_STORAGE_QUARRY,
    BuildingType.GATHERER: params.BUILDING_STORAGE_GATHERER,
    BuildingType.STORAGE: params.BUILDING_STORAGE_STORAGE,
    BuildingType.REFINERY: params.BUILDING_STORAGE_REFINERY,
    BuildingType.MINING_MACHINE: params.BUILDING_STORAGE_MINING_MACHINE,
    BuildingType.FARM: params.BUILDING_STORAGE_FARM,
    BuildingType.WELL: params.BUILDING_STORAGE_WELL,
    BuildingType.WALL: params.BUILDING_STORAGE_WALL,
    BuildingType.WORKSHOP: params.BUILDING_STORAGE_WORKSHOP,
    BuildingType.FORGE: params.BUILDING_STORAGE_FORGE,
    BuildingType.ASSEMBLER: params.BUILDING_STORAGE_ASSEMBLER,
    BuildingType.RESEARCH_CENTER: params.BUILDING_STORAGE_RESEARCH_CENTER,
    BuildingType.TRIBAL_CAMP: params.BUILDING_STORAGE_TRIBAL_CAMP,
    BuildingType.CHEMICAL_PLANT: params.BUILDING_STORAGE_CHEMICAL_PLANT,
    BuildingType.CONVEYOR: params.BUILDING_STORAGE_CONVEYOR,
    BuildingType.SOLAR_ARRAY: params.BUILDING_STORAGE_SOLAR_ARRAY,
    BuildingType.ROCKET_SILO: params.BUILDING_STORAGE_ROCKET_SILO,
    BuildingType.OIL_DRILL: params.BUILDING_STORAGE_OIL_DRILL,
    BuildingType.OIL_REFINERY: params.BUILDING_STORAGE_OIL_REFINERY,
    BuildingType.PIPE: params.BUILDING_STORAGE_PIPE,
    BuildingType.FLUID_TANK: params.BUILDING_STORAGE_FLUID_TANK,
    BuildingType.TURRET: params.BUILDING_STORAGE_TURRET,
    BuildingType.TRAP: params.BUILDING_STORAGE_TRAP,
}


# Per-building max-health lookup.  Buildings not explicitly listed in
# ``params.BUILDING_MAX_HEALTH`` fall back to the default.
BUILDING_MAX_HEALTH: dict[BuildingType, float] = {
    bt: float(params.BUILDING_MAX_HEALTH.get(
        bt.name, params.BUILDING_DEFAULT_MAX_HEALTH,
    ))
    for bt in BuildingType
}


@dataclass(slots=True)
class Building:
    """A placed building on the map."""
    type: BuildingType
    coord: HexCoord
    faction: str = "SURVIVOR"  # "SURVIVOR" or "PRIMITIVE" — avoids circular import
    workers: int = 0
    residents: int = 0  # people living here (for dwellings)
    storage: dict[Resource, float] = field(default_factory=dict)
    storage_capacity: int = 0  # max total resources stored
    upgrade_level: int = 0  # current upgrade tier (0 = base)
    # A crafting station's active recipe.  For a Workshop this may be
    # either a BuildingType (crafts a placeable building) or a Resource
    # (crafts an intermediate material).  Forge and Refinery only ever
    # hold Resource recipes.  ``None`` means the station is idle.
    recipe: "BuildingType | Resource | None" = None
    craft_progress: float = 0.0  # seconds of crafting work accumulated
    # Generic "running" flag.  Currently used by MINING_MACHINE to
    # indicate whether it has fuel + an adjacent ore vein.  Other
    # building types may repurpose this in the future.
    active: bool = False
    # STORAGE buildings only: which single resource this storage is
    # dedicated to.  ``None`` means the player hasn't picked one yet
    # (the building will neither supply nor demand).
    stored_resource: "Resource | None" = None
    # GATHERER only: which resource to gather.  Defaults to FOOD.
    gatherer_output: "Resource | None" = None
    # QUARRY only: which resource to mine.  ``None`` means stone only
    # (default behaviour).  Can be set to IRON or COPPER to slowly
    # mine ore from adjacent veins at a fraction of the mining-machine
    # rate.
    quarry_output: "Resource | None" = None
    # Dwellings only: seconds accumulated toward the next birth.
    reproduction_timer: float = 0.0
    # Combat health.  ``max_health`` is set at placement time from
    # ``BUILDING_MAX_HEALTH``; ``health`` decreases when enemies
    # attack and the building is removed when it hits 0.
    max_health: float = 0.0
    health: float = 0.0
    # Turrets only: seconds remaining until the next shot may fire.
    weapon_cooldown: float = 0.0

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
        self._by_type: dict[BuildingType, list[Building]] = {}

    def place(self, btype: BuildingType, coord: HexCoord) -> Building:
        b = Building(
            type=btype,
            coord=coord,
            storage_capacity=BUILDING_STORAGE_CAPACITY.get(btype, 0),
        )
        b.max_health = BUILDING_MAX_HEALTH.get(btype, params.BUILDING_DEFAULT_MAX_HEALTH)
        b.health = b.max_health
        self.buildings.append(b)
        self._by_coord[coord] = b
        self._by_type.setdefault(btype, []).append(b)
        return b

    def at(self, coord: HexCoord) -> Building | None:
        return self._by_coord.get(coord)

    def remove(self, building: Building) -> None:
        """Remove a building from the manager."""
        self.buildings.remove(building)
        self._by_coord.pop(building.coord, None)
        type_list = self._by_type.get(building.type)
        if type_list is not None:
            try:
                type_list.remove(building)
            except ValueError:
                pass

    def by_type(self, btype: BuildingType) -> list[Building]:
        return self._by_type.get(btype, [])


# Resources each production building can harvest
BUILDING_HARVEST_RESOURCES: dict[BuildingType, set[Resource]] = {
    BuildingType.WOODCUTTER: {Resource.WOOD},
    BuildingType.QUARRY: {Resource.STONE, Resource.IRON, Resource.COPPER},
    BuildingType.GATHERER: {Resource.FIBER, Resource.FOOD},
    BuildingType.REFINERY: {Resource.IRON, Resource.COPPER},
    BuildingType.MINING_MACHINE: {Resource.IRON, Resource.COPPER},
    BuildingType.FARM: {Resource.FOOD},
    BuildingType.OIL_DRILL: {Resource.OIL},
}
