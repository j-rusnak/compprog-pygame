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
    # ── Tier 4+ industrial chain ──────────────────────────────
    CONCRETE = auto()     # cast at refinery from STONE + IRON_BAR
    PLASTIC = auto()      # synthesised at chemical plant from CHARCOAL
    ELECTRONICS = auto()  # assembled from CIRCUIT + PLASTIC
    BATTERY = auto()      # assembled from COPPER_BAR + IRON_BAR + PLASTIC
    ROCKET_FUEL = auto()  # mixed at chemical plant from CHARCOAL + PLASTIC
    ROCKET_PART = auto()  # assembled from STEEL_BAR + ELECTRONICS + CONCRETE
    # ── Petrochemical chain (oil-based) ────────────────────────
    OIL = auto()          # raw resource pumped from oil deposits
    PETROLEUM = auto()    # refined fuel from oil refinery
    LUBRICANT = auto()    # heavy oil byproduct from oil refinery
    RUBBER = auto()       # synthesised at chemical plant from PETROLEUM
    # ── Late-game advanced materials ─────────────────────────
    STEEL_PLATE = auto()         # rolled at the forge from STEEL_BAR
    REINFORCED_CONCRETE = auto() # cast at the refinery from CONCRETE + STEEL_PLATE
    ADVANCED_CIRCUIT = auto()    # assembled from CIRCUIT + RUBBER
    ROBOTIC_ARM = auto()         # assembled from STEEL_PLATE + ADVANCED_CIRCUIT + LUBRICANT
    PAPER = auto()               # workshop product from WOOD + FIBER (research aid)


# Resources harvested directly from the map (not produced in a building).
RAW_RESOURCES: frozenset[Resource] = frozenset({
    Resource.WOOD, Resource.FIBER, Resource.STONE,
    Resource.FOOD, Resource.IRON, Resource.COPPER,
    Resource.OIL,
})

# Processed resources produced at crafting stations.
PROCESSED_RESOURCES: frozenset[Resource] = frozenset({
    Resource.PLANKS, Resource.IRON_BAR, Resource.COPPER_BAR,
    Resource.BRICKS, Resource.COPPER_WIRE, Resource.ROPE,
    Resource.CHARCOAL, Resource.GLASS, Resource.STEEL_BAR,
    Resource.GEARS, Resource.SILICON, Resource.CIRCUIT,
    Resource.CONCRETE, Resource.PLASTIC, Resource.ELECTRONICS,
    Resource.BATTERY, Resource.ROCKET_FUEL, Resource.ROCKET_PART,
    Resource.PETROLEUM, Resource.LUBRICANT, Resource.RUBBER,
    Resource.STEEL_PLATE, Resource.REINFORCED_CONCRETE,
    Resource.ADVANCED_CIRCUIT, Resource.ROBOTIC_ARM, Resource.PAPER,
})


# Liquid/gaseous resources that cannot be carried by workers.  These
# are moved exclusively through the pipe network: producing buildings
# (Oil Drill, Oil Refinery, Chemical Plant) feed pipe-connected
# consumers (and Fluid Tanks for buffer storage) automatically every
# tick.  Never appears in :func:`World._building_supply` /
# :func:`World._building_demand`, which drive worker logistics.
FLUID_RESOURCES: frozenset[Resource] = frozenset({
    Resource.OIL, Resource.PETROLEUM, Resource.LUBRICANT,
    Resource.ROCKET_FUEL,
})


# Mapping from terrain to the resource it yields

TERRAIN_RESOURCE: dict[Terrain, Resource] = {
    Terrain.FOREST: Resource.WOOD,
    Terrain.DENSE_FOREST: Resource.WOOD,
    Terrain.STONE_DEPOSIT: Resource.STONE,
    Terrain.FIBER_PATCH: Resource.FIBER,
    Terrain.IRON_VEIN: Resource.IRON,
    Terrain.COPPER_VEIN: Resource.COPPER,
    Terrain.OIL_DEPOSIT: Resource.OIL,
}


class Inventory:
    """Simple resource stockpile."""

    def __init__(self) -> None:
        self._stock: dict[Resource, float] = {r: 0.0 for r in Resource}
        # Cumulative amount ever added to this inventory, per resource.
        # Used by tier-progression checks so that consumed resources
        # still count toward "gather X total" requirements.
        self._total_produced: dict[Resource, float] = {
            r: 0.0 for r in Resource
        }

    def __getitem__(self, res: Resource) -> float:
        return self._stock[res]

    def __setitem__(self, res: Resource, value: float) -> None:
        self._stock[res] = max(0.0, value)

    def add(self, res: Resource, amount: float) -> None:
        self._stock[res] += amount
        if amount > 0:
            self._total_produced[res] += amount

    def spend(self, res: Resource, amount: float) -> bool:
        """Try to spend *amount*. Returns True if successful."""
        if self._stock[res] >= amount:
            self._stock[res] -= amount
            return True
        return False

    def total_produced(self, res: Resource) -> float:
        """Cumulative amount ever added to this inventory for *res*."""
        return self._total_produced[res]

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
STATION_CHEMICAL_PLANT = "CHEMICAL_PLANT"
STATION_OIL_REFINERY = "OIL_REFINERY"


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
# Recipe parameters (inputs, times, output amounts, station) live in
# :mod:`compprog_pygame.games.hex_colony.params` as string-keyed dicts
# so params.py stays free of enum imports.
def _build_material_recipes() -> dict[Resource, MaterialRecipe]:
    from compprog_pygame.games.hex_colony import params
    recipes: dict[Resource, MaterialRecipe] = {}
    for out_name, data in params.MATERIAL_RECIPE_DATA.items():
        output = Resource[out_name]
        inputs = {Resource[k]: v for k, v in data["inputs"].items()}
        recipes[output] = MaterialRecipe(
            output=output,
            output_amount=int(data["output_amount"]),
            inputs=inputs,
            time=float(data["time"]),
            station=str(data["station"]),
        )
    return recipes


MATERIAL_RECIPES: dict[Resource, MaterialRecipe] = _build_material_recipes()


def recipes_for_station(station: str) -> list[MaterialRecipe]:
    """Return all material recipes produced at *station* in definition order."""
    return [r for r in MATERIAL_RECIPES.values() if r.station == station]
