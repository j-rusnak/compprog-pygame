"""Resource types and inventory management for Hex Colony."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto

from compprog_pygame.games.hex_colony.hex_grid import Terrain


class Resource(Enum):
    """Resource types.

    Raw resources are harvested directly from terrain.  Processed
    (intermediate) resources are crafted at workshops, forges, or
    refineries from raw inputs.
    """
    # ── Raw resources ─────────────────────────────────────────
    WOOD = auto()
    FIBER = auto()
    STONE = auto()
    FOOD = auto()
    IRON = auto()
    COPPER = auto()
    # ── Processed / intermediate resources ────────────────────
    PLANKS = auto()       # crafted from WOOD at workshop
    IRON_BAR = auto()     # smelted from IRON at forge
    COPPER_BAR = auto()   # smelted from COPPER at forge
    BRICKS = auto()       # fired from STONE at refinery
    COPPER_WIRE = auto()  # drawn from COPPER_BAR at workshop
    ROPE = auto()         # twisted from FIBER at workshop
    CHARCOAL = auto()     # baked from WOOD at forge
    GLASS = auto()        # melted from STONE at forge
    STEEL_BAR = auto()    # alloyed from IRON_BAR + CHARCOAL at forge
    GEARS = auto()        # machined from IRON_BAR at assembler
    SILICON = auto()      # refined from GLASS at assembler
    CIRCUIT = auto()      # assembled from COPPER_WIRE + SILICON at assembler


# Resources harvested directly from the map (not produced in a building).
RAW_RESOURCES: frozenset[Resource] = frozenset({
    Resource.WOOD, Resource.FIBER, Resource.STONE,
    Resource.FOOD, Resource.IRON, Resource.COPPER,
})

# Processed resources produced at crafting stations.
PROCESSED_RESOURCES: frozenset[Resource] = frozenset({
    Resource.PLANKS, Resource.IRON_BAR, Resource.COPPER_BAR,
    Resource.BRICKS, Resource.COPPER_WIRE, Resource.ROPE,
    Resource.CHARCOAL, Resource.GLASS, Resource.STEEL_BAR,
    Resource.GEARS, Resource.SILICON, Resource.CIRCUIT,
})


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


class BuildingInventory:
    """Tracks how many pre-crafted buildings the player can place."""

    def __init__(self) -> None:
        self._stock: dict = {}  # BuildingType -> int (lazy to avoid circular import)

    def __getitem__(self, btype) -> int:
        return self._stock.get(btype, 0)

    def __setitem__(self, btype, value: int) -> None:
        self._stock[btype] = max(0, value)

    def add(self, btype, amount: int = 1) -> None:
        self._stock[btype] = self._stock.get(btype, 0) + amount

    def spend(self, btype) -> bool:
        """Consume one building from inventory. Returns True if successful."""
        if self._stock.get(btype, 0) >= 1:
            self._stock[btype] -= 1
            return True
        return False

    def items(self):
        return self._stock.items()


# ── Material (intermediate) recipes ────────────────────────────

# Station identifiers — kept as strings to avoid importing BuildingType
# (which would create a circular import).  Values match the
# BuildingType enum member names exactly.
STATION_WORKSHOP = "WORKSHOP"
STATION_FORGE = "FORGE"
STATION_REFINERY = "REFINERY"
STATION_ASSEMBLER = "ASSEMBLER"


@dataclass(frozen=True, slots=True)
class MaterialRecipe:
    """A recipe that transforms raw/processed resources into an output."""
    output: Resource
    output_amount: int
    inputs: dict[Resource, int]
    time: float        # seconds at 1x speed with 1 worker
    station: str       # STATION_* identifier


# All material recipes in the game.  Keyed by the output resource for
# convenient lookup.  Each crafting station filters this by ``station``.
MATERIAL_RECIPES: dict[Resource, MaterialRecipe] = {
    Resource.PLANKS: MaterialRecipe(
        output=Resource.PLANKS, output_amount=2,
        inputs={Resource.WOOD: 3},
        time=6.0, station=STATION_WORKSHOP,
    ),
    Resource.ROPE: MaterialRecipe(
        output=Resource.ROPE, output_amount=1,
        inputs={Resource.FIBER: 2},
        time=4.0, station=STATION_WORKSHOP,
    ),
    Resource.COPPER_WIRE: MaterialRecipe(
        output=Resource.COPPER_WIRE, output_amount=2,
        inputs={Resource.COPPER_BAR: 1},
        time=6.0, station=STATION_WORKSHOP,
    ),
    Resource.IRON_BAR: MaterialRecipe(
        output=Resource.IRON_BAR, output_amount=1,
        inputs={Resource.IRON: 2},
        time=8.0, station=STATION_FORGE,
    ),
    Resource.COPPER_BAR: MaterialRecipe(
        output=Resource.COPPER_BAR, output_amount=1,
        inputs={Resource.COPPER: 2},
        time=8.0, station=STATION_FORGE,
    ),
    Resource.BRICKS: MaterialRecipe(
        output=Resource.BRICKS, output_amount=2,
        inputs={Resource.STONE: 3},
        time=6.0, station=STATION_REFINERY,
    ),
    Resource.CHARCOAL: MaterialRecipe(
        output=Resource.CHARCOAL, output_amount=1,
        inputs={Resource.WOOD: 2},
        time=6.0, station=STATION_FORGE,
    ),
    Resource.GLASS: MaterialRecipe(
        output=Resource.GLASS, output_amount=1,
        inputs={Resource.STONE: 2},
        time=8.0, station=STATION_FORGE,
    ),
    Resource.STEEL_BAR: MaterialRecipe(
        output=Resource.STEEL_BAR, output_amount=1,
        inputs={Resource.IRON_BAR: 1, Resource.CHARCOAL: 1},
        time=10.0, station=STATION_FORGE,
    ),
    Resource.GEARS: MaterialRecipe(
        output=Resource.GEARS, output_amount=2,
        inputs={Resource.IRON_BAR: 1},
        time=7.0, station=STATION_ASSEMBLER,
    ),
    Resource.SILICON: MaterialRecipe(
        output=Resource.SILICON, output_amount=1,
        inputs={Resource.GLASS: 1},
        time=8.0, station=STATION_ASSEMBLER,
    ),
    Resource.CIRCUIT: MaterialRecipe(
        output=Resource.CIRCUIT, output_amount=1,
        inputs={Resource.COPPER_WIRE: 2, Resource.SILICON: 1},
        time=12.0, station=STATION_ASSEMBLER,
    ),
}


def recipes_for_station(station: str) -> list[MaterialRecipe]:
    """Return all material recipes produced at *station* in definition order."""
    return [r for r in MATERIAL_RECIPES.values() if r.station == station]
