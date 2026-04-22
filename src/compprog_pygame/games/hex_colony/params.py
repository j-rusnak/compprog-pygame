"""Central game-balancing parameters for Hex Colony.

Every tunable constant that affects gameplay balance lives here.
Modify values in this file to rebalance the game without touching logic code.
"""

from __future__ import annotations

# ═══════════════════════════════════════════════════════════════════
#  STARTING CONDITIONS
# ═══════════════════════════════════════════════════════════════════

START_WOOD: int = 0
START_FIBER: int = 0
START_STONE: int = 0
START_FOOD: int = 0
START_IRON: int = 0
START_COPPER: int = 0

START_POPULATION: int = 5

# Camp stores 2× starting resources
CAMP_STORAGE_MULTIPLIER: int = 2

# ═══════════════════════════════════════════════════════════════════
#  RESOURCE GATHERING (units per second per worker)
# ═══════════════════════════════════════════════════════════════════

GATHER_RATE_WOOD: float = 0.2
GATHER_RATE_FIBER: float = 0.2
GATHER_RATE_STONE: float = 0.1
GATHER_RATE_FOOD: float = 0.1
GATHER_RATE_IRON: float = 0.1
GATHER_RATE_COPPER: float = 0.1

# Quarry ore mining rate (per worker per second).  Intended to be
# much slower than the mining machine so the quarry serves as an
# early-game fallback for copper/iron.
QUARRY_ORE_RATE: float = 0.02  # MINING_MACHINE_RATE / 10

# ═══════════════════════════════════════════════════════════════════
#  RESOURCE CONSUMPTION
# ═══════════════════════════════════════════════════════════════════

# Food consumed per person per second
FOOD_CONSUMPTION_PER_PERSON: float = 0.02

# ═══════════════════════════════════════════════════════════════════
#  PEOPLE / MOVEMENT
# ═══════════════════════════════════════════════════════════════════

PERSON_SPEED: float = 60.0  # pixels per second

# ═══════════════════════════════════════════════════════════════════
#  BUILDING COSTS  {BuildingType name: {Resource name: amount}}
#  ── imported as dicts of strings so this file stays free of enum imports
# ═══════════════════════════════════════════════════════════════════

BUILDING_COST_CAMP: dict[str, int] = {}
BUILDING_COST_HOUSE: dict[str, int] = {"WOOD": 12, "FIBER": 4}
BUILDING_COST_HABITAT: dict[str, int] = {"WOOD": 12, "STONE": 10, "FIBER": 4, "IRON_BAR": 2}
BUILDING_COST_PATH: dict[str, int] = {"STONE": 1, "WOOD": 1}
BUILDING_COST_BRIDGE: dict[str, int] = {"PLANKS": 4}
BUILDING_COST_WOODCUTTER: dict[str, int] = {"WOOD": 10, "STONE": 5}
BUILDING_COST_QUARRY: dict[str, int] = {"WOOD": 15, "FIBER": 5}
BUILDING_COST_GATHERER: dict[str, int] = {"WOOD": 8, "STONE": 3}
BUILDING_COST_STORAGE: dict[str, int] = {"WOOD": 20, "STONE": 10}
BUILDING_COST_REFINERY: dict[str, int] = {"STONE": 20, "WOOD": 15, "FIBER": 5}
BUILDING_COST_MINING_MACHINE: dict[str, int] = {"IRON_BAR": 6, "STONE": 20, "WOOD": 10, "GEARS": 2}
BUILDING_COST_FARM: dict[str, int] = {"WOOD": 12, "FIBER": 8, "STONE": 4}
BUILDING_COST_WELL: dict[str, int] = {"STONE": 10, "WOOD": 6}
BUILDING_COST_WALL: dict[str, int] = {"STONE": 8, "WOOD": 4}
BUILDING_COST_WORKSHOP: dict[str, int] = {"WOOD": 25, "STONE": 15, "FIBER": 5}
BUILDING_COST_FORGE: dict[str, int] = {"STONE": 20, "WOOD": 10}
BUILDING_COST_ASSEMBLER: dict[str, int] = {"IRON_BAR": 8, "COPPER_BAR": 4, "PLANKS": 6, "BRICKS": 6}
BUILDING_COST_RESEARCH_CENTER: dict[str, int] = {"PLANKS": 8, "STONE": 15, "FIBER": 6}
BUILDING_COST_TRIBAL_CAMP: dict[str, int] = {}
# ── Tier 4+ industrial buildings ────────────────────────────────
BUILDING_COST_CHEMICAL_PLANT: dict[str, int] = {"BRICKS": 10, "STEEL_BAR": 4, "GLASS": 6, "GEARS": 4}
BUILDING_COST_CONVEYOR: dict[str, int] = {"IRON_BAR": 1, "GEARS": 1}
BUILDING_COST_SOLAR_ARRAY: dict[str, int] = {"GLASS": 6, "SILICON": 4, "STEEL_BAR": 4, "PLASTIC": 4}
BUILDING_COST_ROCKET_SILO: dict[str, int] = {"REINFORCED_CONCRETE": 20, "STEEL_PLATE": 15, "ELECTRONICS": 10, "ROBOTIC_ARM": 4}
# ── Petrochemical chain ────────────────────────────────────
BUILDING_COST_OIL_DRILL: dict[str, int] = {"STEEL_BAR": 6, "GEARS": 4, "PLANKS": 4}
BUILDING_COST_OIL_REFINERY: dict[str, int] = {"BRICKS": 12, "STEEL_BAR": 6, "COPPER_WIRE": 4, "GEARS": 4}
# ── Fluid handling (pipes & tanks) ─────────────────────────
# Pipes are deliberately cheap so the player can lay long runs
# between oil drills, refineries and tanks; they connect adjacent
# fluid-capable buildings into a fluid network.
BUILDING_COST_PIPE: dict[str, int] = {"STEEL_BAR": 1}
# Fluid tanks buffer a single fluid resource and require pipes to
# reach producers/consumers; sized between Storage and Refinery.
BUILDING_COST_FLUID_TANK: dict[str, int] = {"STEEL_BAR": 6, "BRICKS": 4}

# ═══════════════════════════════════════════════════════════════════
#  BUILDING CAPACITY
# ═══════════════════════════════════════════════════════════════════

# Max workers each building supports (0 = no workers)
BUILDING_MAX_WORKERS_CAMP: int = 0
BUILDING_MAX_WORKERS_HOUSE: int = 0
BUILDING_MAX_WORKERS_HABITAT: int = 0
BUILDING_MAX_WORKERS_PATH: int = 0
BUILDING_MAX_WORKERS_BRIDGE: int = 0
BUILDING_MAX_WORKERS_WOODCUTTER: int = 2
BUILDING_MAX_WORKERS_QUARRY: int = 2
BUILDING_MAX_WORKERS_GATHERER: int = 3
BUILDING_MAX_WORKERS_STORAGE: int = 0
BUILDING_MAX_WORKERS_REFINERY: int = 2
BUILDING_MAX_WORKERS_MINING_MACHINE: int = 0
BUILDING_MAX_WORKERS_FARM: int = 3
BUILDING_MAX_WORKERS_WELL: int = 0
BUILDING_MAX_WORKERS_WALL: int = 0
BUILDING_MAX_WORKERS_WORKSHOP: int = 2
BUILDING_MAX_WORKERS_FORGE: int = 2
BUILDING_MAX_WORKERS_ASSEMBLER: int = 2
BUILDING_MAX_WORKERS_RESEARCH_CENTER: int = 2
BUILDING_MAX_WORKERS_TRIBAL_CAMP: int = 0
BUILDING_MAX_WORKERS_CHEMICAL_PLANT: int = 2
BUILDING_MAX_WORKERS_CONVEYOR: int = 0
BUILDING_MAX_WORKERS_SOLAR_ARRAY: int = 0
BUILDING_MAX_WORKERS_ROCKET_SILO: int = 0
BUILDING_MAX_WORKERS_OIL_DRILL: int = 0
BUILDING_MAX_WORKERS_OIL_REFINERY: int = 2
BUILDING_MAX_WORKERS_PIPE: int = 0
BUILDING_MAX_WORKERS_FLUID_TANK: int = 0

# Housing capacity (number of people that can live here; 0 = not a dwelling)
BUILDING_HOUSING_CAMP: int = 10
BUILDING_HOUSING_HOUSE: int = 5
BUILDING_HOUSING_HABITAT: int = 8
BUILDING_HOUSING_PATH: int = 0
BUILDING_HOUSING_BRIDGE: int = 0
BUILDING_HOUSING_WOODCUTTER: int = 0
BUILDING_HOUSING_QUARRY: int = 0
BUILDING_HOUSING_GATHERER: int = 0
BUILDING_HOUSING_STORAGE: int = 0
BUILDING_HOUSING_REFINERY: int = 0
BUILDING_HOUSING_MINING_MACHINE: int = 0
BUILDING_HOUSING_FARM: int = 0
BUILDING_HOUSING_WELL: int = 0
BUILDING_HOUSING_WALL: int = 0
BUILDING_HOUSING_WORKSHOP: int = 0
BUILDING_HOUSING_FORGE: int = 0
BUILDING_HOUSING_ASSEMBLER: int = 0
BUILDING_HOUSING_RESEARCH_CENTER: int = 0
BUILDING_HOUSING_TRIBAL_CAMP: int = 8
BUILDING_HOUSING_CHEMICAL_PLANT: int = 0
BUILDING_HOUSING_CONVEYOR: int = 0
BUILDING_HOUSING_SOLAR_ARRAY: int = 0
BUILDING_HOUSING_ROCKET_SILO: int = 0
BUILDING_HOUSING_OIL_DRILL: int = 0
BUILDING_HOUSING_OIL_REFINERY: int = 0
BUILDING_HOUSING_PIPE: int = 0
BUILDING_HOUSING_FLUID_TANK: int = 0

# Storage capacity (max total resources stored; 0 = none)
# Camp capacity is set dynamically at placement time.
BUILDING_STORAGE_CAMP: int = 300
BUILDING_STORAGE_HOUSE: int = 50
BUILDING_STORAGE_HABITAT: int = 50
BUILDING_STORAGE_PATH: int = 0
BUILDING_STORAGE_BRIDGE: int = 0
BUILDING_STORAGE_WOODCUTTER: int = 40
BUILDING_STORAGE_QUARRY: int = 40
BUILDING_STORAGE_GATHERER: int = 60
BUILDING_STORAGE_STORAGE: int = 250
BUILDING_STORAGE_REFINERY: int = 40
BUILDING_STORAGE_MINING_MACHINE: int = 60
BUILDING_STORAGE_FARM: int = 60
BUILDING_STORAGE_WELL: int = 0
BUILDING_STORAGE_WALL: int = 0
BUILDING_STORAGE_WORKSHOP: int = 60
BUILDING_STORAGE_FORGE: int = 60
BUILDING_STORAGE_ASSEMBLER: int = 60
BUILDING_STORAGE_RESEARCH_CENTER: int = 80
BUILDING_STORAGE_TRIBAL_CAMP: int = 100
BUILDING_STORAGE_CHEMICAL_PLANT: int = 80
BUILDING_STORAGE_CONVEYOR: int = 0
BUILDING_STORAGE_SOLAR_ARRAY: int = 0
BUILDING_STORAGE_ROCKET_SILO: int = 200
BUILDING_STORAGE_OIL_DRILL: int = 80
BUILDING_STORAGE_OIL_REFINERY: int = 80
BUILDING_STORAGE_PIPE: int = 0
# Fluid tanks hold a single fluid resource; bigger than refinery
# buffers so they're worth building between producers/consumers.
BUILDING_STORAGE_FLUID_TANK: int = 200

# ═══════════════════════════════════════════════════════════════════
#  LOGISTICS
# ═══════════════════════════════════════════════════════════════════

# Items a single logistics worker can carry in one trip.
LOGISTICS_CARRY_CAPACITY: int = 5

# Maximum number of idle logistics workers that may run the
# (expensive) supply/demand search per simulation tick.  The world
# round-robins through the idle pool so every worker still gets
# served promptly while large colonies don't stall.
LOGISTICS_JOBS_PER_FRAME: int = 4

# Hard wall-clock budget (in milliseconds) for per-frame logistics
# job-finding.  Even when ``LOGISTICS_JOBS_PER_FRAME`` would allow
# more, the loop bails out after this many ms so a single tick can
# never blow the frame budget regardless of colony size.  Idle
# workers that didn't get a turn this frame are picked up next
# frame via the round-robin cursor.
LOGISTICS_FIND_JOB_BUDGET_MS: int = 4

# ═══════════════════════════════════════════════════════════════════
#  POPULATION GROWTH
# ═══════════════════════════════════════════════════════════════════

# Seconds between natural births at a dwelling.
POPULATION_REPRO_INTERVAL: float = 120.0
# Food consumed per new person born (paid from the house's storage).
POPULATION_FOOD_PER_BIRTH: float = 25.0
# Minimum food a dwelling must hold before a birth can occur.
POPULATION_MIN_FOOD_TO_BIRTH: float = 25.0

# ═══════════════════════════════════════════════════════════════════
#  BUILDING DELETE REFUND
# ═══════════════════════════════════════════════════════════════════

# Fraction of original cost refunded when deleting (0.0–1.0)
DELETE_REFUND_FRACTION: float = 0.5

# ═══════════════════════════════════════════════════════════════════
#  REFINERY / FARM / WELL
# ═══════════════════════════════════════════════════════════════════

# Refinery: consumes iron/copper ore, produces alloy (counted as same resource)
REFINERY_RATE: float = 0.3  # units per second per worker (faster than raw gathering)

# Mining machine: fuel-powered automated ore miner for iron/copper veins.
# Burns one unit of fuel from its on-site storage to mine a fixed amount
# of ore.  CHARCOAL: 40 ore per unit; PETROLEUM: 100 ore per unit.
# The machine refuses to start until at least one unit of fuel is on
# site (logistics must deliver it — the global inventory is no longer a
# fallback).
MINING_MACHINE_RATE: float = 1.2  # ore per second (machine, not per worker)
# Discrete ore-per-fuel-unit ratios.  Order matters: when both fuels are
# on site the first listed is preferred (charcoal is the early-game
# fuel; petroleum is the late-game upgrade).
MINING_MACHINE_ORE_PER_FUEL: dict[str, float] = {
    "CHARCOAL": 40.0,
    "PETROLEUM": 100.0,
}
# Kept for backwards-compatibility with older code paths that still ask
# for the rate-based fuel data (e.g. tooltip generation).
MINING_MACHINE_FUEL_RATE: float = MINING_MACHINE_RATE / MINING_MACHINE_ORE_PER_FUEL["CHARCOAL"]
MINING_MACHINE_FUELS: dict[str, float] = {
    name: MINING_MACHINE_ORE_PER_FUEL[name] / MINING_MACHINE_ORE_PER_FUEL["CHARCOAL"]
    for name in MINING_MACHINE_ORE_PER_FUEL
}
# Oil drill: placed directly on an OIL_DEPOSIT tile.  No fuel needed —
# extracts crude OIL straight into its own storage at a steady rate.
OIL_DRILL_RATE: float = 0.6  # crude oil per second

# Farm: produces food per second per worker (no terrain requirement)
FARM_FOOD_RATE: float = 0.8

# Well: bonus food multiplier for adjacent farms (1.0 = +100%)
WELL_FARM_BONUS: float = 1.0

# ═══════════════════════════════════════════════════════════════════
#  WORKSHOP CRAFTING
# ═══════════════════════════════════════════════════════════════════

# Time in seconds (at 1x speed) to craft one building
WORKSHOP_CRAFT_TIME: float = 15.0

# ═══════════════════════════════════════════════════════════════════
#  BUILDING RECIPES
#  Defines which crafting station can produce each placeable building.
#  Each entry maps a BuildingType name to the station BuildingType name
#  that crafts it.  Buildings not listed here cannot be crafted (e.g.
#  CAMP, HOUSE).  The crafting cost is the building's own
#  BUILDING_COST_* entry above, consumed from the station's local
#  storage / global inventory during crafting.
#  The craft time for all entries is WORKSHOP_CRAFT_TIME above.
# ═══════════════════════════════════════════════════════════════════

BUILDING_RECIPE_STATION: dict[str, str] = {
    "HABITAT":          "WORKSHOP",
    "PATH":             "WORKSHOP",
    "BRIDGE":           "WORKSHOP",
    "WALL":             "WORKSHOP",
    "WOODCUTTER":       "WORKSHOP",
    "QUARRY":           "WORKSHOP",
    "GATHERER":         "WORKSHOP",
    "STORAGE":          "WORKSHOP",
    "REFINERY":         "ASSEMBLER",
    "FARM":             "WORKSHOP",
    "WELL":             "WORKSHOP",
    "WORKSHOP":         "WORKSHOP",
    "FORGE":            "WORKSHOP",
    "MINING_MACHINE":   "ASSEMBLER",
    "ASSEMBLER":        "FORGE",
    "RESEARCH_CENTER":  "ASSEMBLER",
    # Tier 4+ industrial buildings
    "CHEMICAL_PLANT":   "ASSEMBLER",
    "CONVEYOR":         "WORKSHOP",
    "SOLAR_ARRAY":      "ASSEMBLER",
    "ROCKET_SILO":      "ASSEMBLER",
    "OIL_DRILL":        "ASSEMBLER",
    "OIL_REFINERY":     "ASSEMBLER",
    "PIPE":             "WORKSHOP",
    "FLUID_TANK":       "ASSEMBLER",
}

# ═══════════════════════════════════════════════════════════════════
#  INTERMEDIATE / MATERIAL RECIPES
#  Each recipe transforms raw or processed resources into an output at
#  one of the crafting stations (WORKSHOP, FORGE, REFINERY, ASSEMBLER).
#  Fields:
#    "output_amount" — units of the keyed output produced per craft
#    "inputs"        — {resource_name: amount_consumed_per_craft}
#    "time"          — seconds per craft (at 1x speed, 1 worker)
#    "station"       — BuildingType name that runs the recipe
#  Keeping these as plain str→dict keeps params.py free of enum imports.
# ═══════════════════════════════════════════════════════════════════

RECIPE_STATION_WORKSHOP: str = "WORKSHOP"
RECIPE_STATION_FORGE: str = "FORGE"
RECIPE_STATION_REFINERY: str = "REFINERY"
RECIPE_STATION_ASSEMBLER: str = "ASSEMBLER"
RECIPE_STATION_CHEMICAL_PLANT: str = "CHEMICAL_PLANT"
RECIPE_STATION_OIL_REFINERY: str = "OIL_REFINERY"

RECIPE_PLANKS: dict = {
    "output_amount": 2,
    "inputs": {"WOOD": 3},
    "time": 6.0,
    "station": RECIPE_STATION_WORKSHOP,
}
RECIPE_ROPE: dict = {
    "output_amount": 1,
    "inputs": {"FIBER": 2},
    "time": 4.0,
    "station": RECIPE_STATION_WORKSHOP,
}
RECIPE_COPPER_WIRE: dict = {
    "output_amount": 2,
    "inputs": {"COPPER_BAR": 1},
    "time": 6.0,
    "station": RECIPE_STATION_WORKSHOP,
}
RECIPE_IRON_BAR: dict = {
    "output_amount": 1,
    "inputs": {"IRON": 2},
    "time": 8.0,
    "station": RECIPE_STATION_FORGE,
}
RECIPE_COPPER_BAR: dict = {
    "output_amount": 1,
    "inputs": {"COPPER": 2},
    "time": 8.0,
    "station": RECIPE_STATION_FORGE,
}
RECIPE_BRICKS: dict = {
    "output_amount": 2,
    "inputs": {"STONE": 3},
    "time": 6.0,
    "station": RECIPE_STATION_REFINERY,
}
RECIPE_CHARCOAL: dict = {
    "output_amount": 1,
    "inputs": {"WOOD": 2},
    "time": 6.0,
    "station": RECIPE_STATION_FORGE,
}
RECIPE_GLASS: dict = {
    "output_amount": 1,
    "inputs": {"STONE": 2},
    "time": 8.0,
    "station": RECIPE_STATION_FORGE,
}
RECIPE_STEEL_BAR: dict = {
    "output_amount": 1,
    "inputs": {"IRON_BAR": 1, "CHARCOAL": 1},
    "time": 10.0,
    "station": RECIPE_STATION_FORGE,
}
RECIPE_GEARS: dict = {
    "output_amount": 2,
    "inputs": {"IRON_BAR": 1},
    "time": 7.0,
    "station": RECIPE_STATION_ASSEMBLER,
}
RECIPE_SILICON: dict = {
    "output_amount": 1,
    "inputs": {"GLASS": 1},
    "time": 8.0,
    "station": RECIPE_STATION_ASSEMBLER,
}
RECIPE_CIRCUIT: dict = {
    "output_amount": 1,
    "inputs": {"COPPER_WIRE": 2, "SILICON": 1},
    "time": 12.0,
    "station": RECIPE_STATION_ASSEMBLER,
}

# ── Tier 4+ industrial recipes ──────────────────────────────────
RECIPE_CONCRETE: dict = {
    "output_amount": 2,
    "inputs": {"STONE": 3, "IRON_BAR": 1},
    "time": 9.0,
    "station": RECIPE_STATION_REFINERY,
}
RECIPE_PLASTIC: dict = {
    "output_amount": 2,
    "inputs": {"CHARCOAL": 2},
    "time": 10.0,
    "station": RECIPE_STATION_CHEMICAL_PLANT,
}
RECIPE_ELECTRONICS: dict = {
    "output_amount": 1,
    "inputs": {"CIRCUIT": 1, "PLASTIC": 1},
    "time": 14.0,
    "station": RECIPE_STATION_ASSEMBLER,
}
RECIPE_BATTERY: dict = {
    "output_amount": 1,
    "inputs": {"COPPER_BAR": 1, "IRON_BAR": 1, "PLASTIC": 1},
    "time": 12.0,
    "station": RECIPE_STATION_ASSEMBLER,
}
RECIPE_ROCKET_FUEL: dict = {
    "output_amount": 1,
    "inputs": {"CHARCOAL": 2, "PLASTIC": 1},
    "time": 16.0,
    "station": RECIPE_STATION_CHEMICAL_PLANT,
}
RECIPE_ROCKET_PART: dict = {
    "output_amount": 1,
    "inputs": {"STEEL_BAR": 2, "ELECTRONICS": 2, "CONCRETE": 1},
    "time": 25.0,
    "station": RECIPE_STATION_ASSEMBLER,
}

# ── Petrochemical chain ──────────────────────────────────
RECIPE_PETROLEUM: dict = {
    "output_amount": 1,
    "inputs": {"OIL": 2},
    "time": 8.0,
    "station": RECIPE_STATION_OIL_REFINERY,
}
RECIPE_LUBRICANT: dict = {
    "output_amount": 1,
    "inputs": {"OIL": 3},
    "time": 10.0,
    "station": RECIPE_STATION_OIL_REFINERY,
}
RECIPE_RUBBER: dict = {
    "output_amount": 2,
    "inputs": {"PETROLEUM": 2},
    "time": 10.0,
    "station": RECIPE_STATION_CHEMICAL_PLANT,
}

# ── Advanced materials (every late-game tech node unlocks one) ────────
RECIPE_STEEL_PLATE: dict = {
    "output_amount": 1,
    "inputs": {"STEEL_BAR": 2},
    "time": 10.0,
    "station": RECIPE_STATION_FORGE,
}
RECIPE_REINFORCED_CONCRETE: dict = {
    "output_amount": 1,
    "inputs": {"CONCRETE": 2, "STEEL_PLATE": 1},
    "time": 12.0,
    "station": RECIPE_STATION_REFINERY,
}
RECIPE_ADVANCED_CIRCUIT: dict = {
    "output_amount": 1,
    "inputs": {"CIRCUIT": 2, "RUBBER": 1},
    "time": 14.0,
    "station": RECIPE_STATION_ASSEMBLER,
}
RECIPE_ROBOTIC_ARM: dict = {
    "output_amount": 1,
    "inputs": {"STEEL_PLATE": 1, "ADVANCED_CIRCUIT": 1, "LUBRICANT": 1},
    "time": 18.0,
    "station": RECIPE_STATION_ASSEMBLER,
}
RECIPE_PAPER: dict = {
    "output_amount": 2,
    "inputs": {"WOOD": 1, "FIBER": 1},
    "time": 5.0,
    "station": RECIPE_STATION_WORKSHOP,
}

# All material recipes, keyed by output-resource name.  resources.py
# builds the typed MATERIAL_RECIPES registry from this dict.
MATERIAL_RECIPE_DATA: dict[str, dict] = {
    "PLANKS": RECIPE_PLANKS,
    "ROPE": RECIPE_ROPE,
    "COPPER_WIRE": RECIPE_COPPER_WIRE,
    "IRON_BAR": RECIPE_IRON_BAR,
    "COPPER_BAR": RECIPE_COPPER_BAR,
    "BRICKS": RECIPE_BRICKS,
    "CHARCOAL": RECIPE_CHARCOAL,
    "GLASS": RECIPE_GLASS,
    "STEEL_BAR": RECIPE_STEEL_BAR,
    "GEARS": RECIPE_GEARS,
    "SILICON": RECIPE_SILICON,
    "CIRCUIT": RECIPE_CIRCUIT,
    "CONCRETE": RECIPE_CONCRETE,
    "PLASTIC": RECIPE_PLASTIC,
    "ELECTRONICS": RECIPE_ELECTRONICS,
    "BATTERY": RECIPE_BATTERY,
    "ROCKET_FUEL": RECIPE_ROCKET_FUEL,
    "ROCKET_PART": RECIPE_ROCKET_PART,
    # Petrochemical chain
    "PETROLEUM": RECIPE_PETROLEUM,
    "LUBRICANT": RECIPE_LUBRICANT,
    "RUBBER": RECIPE_RUBBER,
    # Late-game advanced materials
    "STEEL_PLATE": RECIPE_STEEL_PLATE,
    "REINFORCED_CONCRETE": RECIPE_REINFORCED_CONCRETE,
    "ADVANCED_CIRCUIT": RECIPE_ADVANCED_CIRCUIT,
    "ROBOTIC_ARM": RECIPE_ROBOTIC_ARM,
    "PAPER": RECIPE_PAPER,
}

# ═══════════════════════════════════════════════════════════════════
#  STARTING BUILDING INVENTORY
#  (buildings the player starts with, placed from the building tab)
# ═══════════════════════════════════════════════════════════════════

START_BUILDINGS: dict[str, int] = {
    "PATH": 40,
    "WALL": 10,
    "BRIDGE": 4,
    "WORKSHOP": 3,
    "FORGE": 1,
    "HABITAT": 3,
    "WOODCUTTER": 2,
    "QUARRY": 2,
    "GATHERER": 2,
    "STORAGE": 2,
    "REFINERY": 1,
    "FARM": 2,
    "WELL": 1,
    "RESEARCH_CENTER": 1,
}

# ═══════════════════════════════════════════════════════════════════
#  TIER PROGRESSION SYSTEM
#  Each tier unlocks new buildings/features.  Requirements use string
#  keys so this file stays free of enum imports.
#  Requirement types:
#    "population"      — min living population
#    "buildings_placed" — total non-path buildings on the map
#    "resource_delivered" — {resource_name: amount} delivered to camp
#    "research_count"   — number of tech nodes researched
#    "production_rate"  — {resource_name: min_per_second} sustained
# ═══════════════════════════════════════════════════════════════════

TIER_DATA: list[dict] = [
    # ── Tier 0 (starting) ────────────────────────────────────────
    {
        "name": "Crash Site",
        "description": "Establish basic survival operations",
        "unlocks_buildings": [
            "PATH", "WALL", "WOODCUTTER", "QUARRY", "GATHERER",
            "STORAGE", "HABITAT", "WORKSHOP", "FORGE", "RESEARCH_CENTER",
        ],
        "requirements": {},  # no requirements — starting tier
    },
    # ── Tier 1 ───────────────────────────────────────────────────
    {
        "name": "Foothold",
        "description": "Secure basic resource production",
        # Bridges and Farms are unlocked via the tech tree instead;
        # tier 1 just gates higher-tier infrastructure.
        "unlocks_buildings": [],
        "requirements": {
            "population": 8,
            "buildings_placed": 6,
        },
    },
    # ── Tier 2 ───────────────────────────────────────────────────
    {
        "name": "Settlement",
        "description": "Begin processing raw materials",
        # Refineries and Wells are unlocked via the tech tree.
        "unlocks_buildings": ["ASSEMBLER", "MINING_MACHINE"],
        "requirements": {
            "population": 15,
            "resource_gathered": {"FOOD": 100},
            "research_count": 1,
        },
    },
    # ── Tier 3 ───────────────────────────────────────────────────
    {
        "name": "Colony",
        "description": "Establish a self-sustaining colony",
        "unlocks_buildings": [],  # tier-4 industrial chain unlocked via tech
        "requirements": {
            "population": 25,
            "resource_gathered": {"IRON": 50, "COPPER": 25},
            "research_count": 3,
        },
    },
    # ── Tier 4 ───────────────────────────────────────────────────
    {
        "name": "Industrial",
        "description": "Build out an advanced production chain",
        # Conveyor & Chemical Plant are unlocked via tech (gated by tier).
        "unlocks_buildings": [],
        "requirements": {
            "population": 35,
            "resource_gathered": {"STEEL_BAR": 10, "GEARS": 15, "BRICKS": 30},
            "research_count": 6,
        },
    },
    # ── Tier 5 ───────────────────────────────────────────────────
    {
        "name": "Petrochemical",
        "description": "Tap surface oil deposits and refine their products",
        # Oil Drill / Oil Refinery are unlocked via the tech tree.
        "unlocks_buildings": [],
        "requirements": {
            "population": 42,
            "resource_gathered": {"OIL": 30, "PETROLEUM": 20, "RUBBER": 8},
            "research_count": 8,
        },
    },
    # ── Tier 6 ───────────────────────────────────────────────────
    {
        "name": "Automation",
        "description": "Power and automate your colony",
        # Solar Array is unlocked via tech (gated by tier).
        "unlocks_buildings": [],
        "requirements": {
            "population": 50,
            "resource_gathered": {
                "PLASTIC": 25, "CIRCUIT": 15, "BATTERY": 5,
                "ADVANCED_CIRCUIT": 6,
            },
            "research_count": 12,
        },
    },
    # ── Tier 7 ───────────────────────────────────────────────────
    {
        "name": "Spacefarer",
        "description": "Reach for the stars and leave this world",
        # Rocket Silo is unlocked via tech (gated by tier).
        "unlocks_buildings": [],
        "requirements": {
            "population": 75,
            "resource_gathered": {
                "ELECTRONICS": 25, "ROCKET_FUEL": 10,
                "REINFORCED_CONCRETE": 8, "ROBOTIC_ARM": 4,
            },
            "research_count": 17,
        },
    },
]

# ═══════════════════════════════════════════════════════════════════
#  TECH TREE (RESEARCH CENTER)
#  Each node is a dict with:
#    "name"          — display name
#    "description"   — tooltip text
#    "cost"          — {resource_name: amount} to research
#    "time"          — seconds of research time
#    "prerequisites" — list of tech node keys that must be done first
#    "unlocks"       — list of BuildingType names this tech enables
#    "position"      — (x, y) grid position for visual layout
# ═══════════════════════════════════════════════════════════════════

TECH_TREE_DATA: dict[str, dict] = {
    # ═══════════════════════════════════════════════════════════
    #  EARLY GAME  (tier 1-2)
    # ═══════════════════════════════════════════════════════════
    "advanced_logistics": {
        "name": "Advanced Logistics",
        "description": "Unlock bridges for crossing water and rivers",
        "cost": {"WOOD": 15, "STONE": 10},
        "time": 35.0,
        "prerequisites": [],
        "unlocks": ["BRIDGE"],
        "position": (0, 0),
    },
    "agriculture": {
        "name": "Agriculture",
        "description": "Cultivate crops at Farms for a steady food supply",
        "cost": {"WOOD": 20, "FIBER": 15},
        "time": 45.0,
        "prerequisites": [],
        "unlocks": ["FARM"],
        "position": (3, 0),
    },
    "metallurgy": {
        "name": "Metallurgy",
        "description": "Refinery and Forge: smelt Iron and Copper into bars",
        "cost": {"STONE": 15, "WOOD": 10},
        "time": 50.0,
        "prerequisites": [],
        "unlocks": ["REFINERY"],
        "unlock_resources": ["IRON_BAR", "COPPER_BAR"],
        "position": (5, 0),
    },
    "irrigation": {
        "name": "Irrigation",
        "description": "Wells boost adjacent farm output",
        "cost": {"STONE": 20, "IRON": 5},
        "time": 40.0,
        "prerequisites": ["agriculture"],
        "unlocks": ["WELL"],
        "position": (3, 1),
    },
    "fortification": {
        "name": "Fortification",
        "description": "Roll Steel Plates at the Forge for armoured construction",
        "cost": {"STONE": 30, "IRON": 10},
        "time": 55.0,
        "prerequisites": ["metallurgy"],
        "unlocks": [],
        "unlock_resources": ["STEEL_PLATE"],
        "position": (5, 1),
    },
    "advanced_smelting": {
        "name": "Advanced Smelting",
        "description": "Forge Steel Bars and melt Glass",
        "cost": {"IRON": 15, "COPPER": 10},
        "time": 60.0,
        "prerequisites": ["metallurgy"],
        "unlocks": [],
        "unlock_resources": ["STEEL_BAR", "GLASS"],
        "position": (6, 1),
    },
    "exploration": {
        "name": "Exploration",
        "description": "Mill Paper at the Workshop — needed by future research orders",
        "cost": {"WOOD": 25, "FIBER": 20},
        "time": 45.0,
        "prerequisites": ["advanced_logistics"],
        "unlocks": [],
        "unlock_resources": ["PAPER"],
        "position": (0, 1),
    },
    # ═══════════════════════════════════════════════════════════
    #  MID GAME  (tier 3-4 — industrial chain bootstrapping)
    # ═══════════════════════════════════════════════════════════
    "masonry": {
        "name": "Masonry",
        "description": "Cast Reinforced Concrete at the Refinery (Concrete + Steel Plate)",
        "cost": {"STONE": 40, "BRICKS": 10},
        "time": 70.0,
        "prerequisites": ["fortification"],
        "unlocks": [],
        "unlock_resources": ["REINFORCED_CONCRETE"],
        "position": (5, 2),
    },
    "concrete_works": {
        "name": "Concrete Works",
        "description": "Cast Concrete at the Refinery from Stone + Iron Bars",
        "cost": {"BRICKS": 20, "IRON_BAR": 8},
        "time": 90.0,
        "prerequisites": ["masonry", "advanced_smelting"],
        "unlocks": [],
        "unlock_resources": ["CONCRETE"],
        "position": (5, 3),
    },
    "basic_chemistry": {
        "name": "Basic Chemistry",
        "description": "Build the Chemical Plant for synthesised materials",
        "cost": {"GLASS": 8, "COPPER_BAR": 6, "STEEL_BAR": 2},
        "time": 100.0,
        "prerequisites": ["advanced_smelting"],
        "unlocks": ["CHEMICAL_PLANT"],
        "position": (6, 2),
    },
    "electronics_basics": {
        "name": "Electronics Basics",
        "description": "Workshops draw Copper Wire and machine Gears; Assemblers refine Silicon",
        "cost": {"COPPER_BAR": 8, "GLASS": 4},
        "time": 100.0,
        "prerequisites": ["advanced_smelting"],
        "unlocks": [],
        "unlock_resources": ["COPPER_WIRE", "GEARS", "SILICON"],
        "position": (8, 2),
    },
    "conveyor_belts": {
        "name": "Conveyor Belts",
        "description": "Place Conveyors so workers walk twice as fast",
        "cost": {"IRON_BAR": 10, "GEARS": 8, "PLANKS": 6},
        "time": 80.0,
        "prerequisites": ["advanced_logistics", "metallurgy"],
        "unlocks": ["CONVEYOR"],
        "position": (1, 1),
    },
    # ═══════════════════════════════════════════════════════════
    #  LATE GAME  (tier 5 — chemistry, electronics, power)
    # ═══════════════════════════════════════════════════════════
    "plastics": {
        "name": "Plastics",
        "description": "Synthesise Plastic at the Chemical Plant",
        "cost": {"CHARCOAL": 20, "GLASS": 10},
        "time": 120.0,
        "prerequisites": ["basic_chemistry"],
        "unlocks": [],
        "unlock_resources": ["PLASTIC"],
        "position": (7, 3),
    },
    "petroleum_engineering": {
        "name": "Petroleum Engineering",
        "description": "Drill surface oil deposits, refine them into Petroleum & Lubricant, and lay Pipes & Fluid Tanks to move them",
        "cost": {"STEEL_BAR": 6, "GEARS": 6, "BRICKS": 8},
        "time": 110.0,
        "prerequisites": ["basic_chemistry"],
        "unlocks": ["OIL_DRILL", "OIL_REFINERY", "PIPE", "FLUID_TANK"],
        "unlock_resources": ["OIL", "PETROLEUM", "LUBRICANT"],
        "position": (6, 3),
    },
    "polymers": {
        "name": "Polymers",
        "description": "Synthesise Rubber from Petroleum at the Chemical Plant",
        "cost": {"PLASTIC": 15, "STEEL_BAR": 10},
        "time": 130.0,
        "prerequisites": ["plastics", "petroleum_engineering"],
        "unlocks": [],
        "unlock_resources": ["RUBBER"],
        "position": (6, 4),
    },
    "microchips": {
        "name": "Microchips",
        "description": "Assemble Circuits and Electronics at the Assembler",
        "cost": {"COPPER_WIRE": 8, "PLASTIC": 6},
        "time": 130.0,
        "prerequisites": ["electronics_basics", "plastics"],
        "unlocks": [],
        "unlock_resources": ["CIRCUIT", "ELECTRONICS"],
        "position": (8, 3),
    },
    "energy_storage": {
        "name": "Energy Storage",
        "description": "Craft Batteries at the Assembler",
        "cost": {"COPPER_WIRE": 12, "PLASTIC": 8},
        "time": 120.0,
        "prerequisites": ["microchips"],
        "unlocks": [],
        "unlock_resources": ["BATTERY"],
        "position": (8, 4),
    },
    "solar_panels": {
        "name": "Solar Panels",
        "description": "Solar Arrays boost adjacent crafting +25%",
        "cost": {"SILICON": 10, "PLASTIC": 8, "BATTERY": 4},
        "time": 150.0,
        "prerequisites": ["energy_storage"],
        "unlocks": ["SOLAR_ARRAY"],
        "position": (8, 5),
    },
    "advanced_electronics": {
        "name": "Advanced Electronics",
        "description": "Assemble Advanced Circuits (Circuit + Rubber) for next-gen tech",
        "cost": {"ELECTRONICS": 8, "CIRCUIT": 12},
        "time": 140.0,
        "prerequisites": ["microchips", "polymers"],
        "unlocks": [],
        "unlock_resources": ["ADVANCED_CIRCUIT"],
        "position": (7, 4),
    },
    "automation_logistics": {
        "name": "Automation Logistics",
        "description": "Build Robotic Arms — logistics workers carry +50% per trip",
        "cost": {"GEARS": 16, "ELECTRONICS": 4},
        "time": 130.0,
        "prerequisites": ["conveyor_belts", "advanced_electronics"],
        "unlocks": [],
        "unlock_resources": ["ROBOTIC_ARM"],
        "position": (1, 4),
    },
    # ═══════════════════════════════════════════════════════════
    #  END GAME  (tier 6 — spacefaring)
    # ═══════════════════════════════════════════════════════════
    "rocketry": {
        "name": "Rocketry",
        "description": "Mix Rocket Fuel at the Chemical Plant",
        "cost": {"PLASTIC": 12, "STEEL_BAR": 16, "BATTERY": 5},
        "time": 180.0,
        "prerequisites": ["polymers", "advanced_electronics"],
        "unlocks": [],
        "unlock_resources": ["ROCKET_FUEL"],
        "position": (6, 5),
    },
    "orbital_assembly": {
        "name": "Orbital Assembly",
        "description": "Build the Rocket Silo and assemble Rocket Parts",
        "cost": {"ELECTRONICS": 12, "REINFORCED_CONCRETE": 10, "ROCKET_FUEL": 4},
        "time": 240.0,
        "prerequisites": ["rocketry", "solar_panels", "concrete_works", "automation_logistics"],
        "unlocks": ["ROCKET_SILO"],
        "unlock_resources": ["ROCKET_PART"],
        "position": (7, 6),
    },
}

# ═══════════════════════════════════════════════════════════════════
#  RUINS
# ═══════════════════════════════════════════════════════════════════

# Ruins spawn as small clusters of weathered structures.  Each
# cluster awakens *one* ancient tower (see AWAKENING_TOWERS_PER_EVENT)
# so the map needs many more clusters than there are tower slots.
# Cluster count scales further on large maps.
RUINS_CLUSTERS_MIN: int = 8
RUINS_CLUSTERS_MAX: int = 14
# Map-radius threshold above which an extra cluster may appear.
RUINS_EXTRA_CLUSTER_RADIUS: int = 40
# Pieces per cluster — kept small now that each cluster only feeds
# one tower; lots of small ruin sites read better than a few large ones.
RUINS_PIECES_MIN: int = 3
RUINS_PIECES_MAX: int = 6
# Minimum hex distance from camp for any cluster centre.
RUINS_MIN_DISTANCE: int = 8
# Minimum hex distance between two cluster centres.
RUINS_CLUSTER_SEPARATION: int = 6
# Radius (in hexes) around the cluster centre in which pieces are placed.
RUINS_CLUSTER_RADIUS: int = 2

# Legacy aliases (kept so older code paths still import cleanly).
RUINS_COUNT_MIN: int = RUINS_CLUSTERS_MIN * RUINS_PIECES_MIN
RUINS_COUNT_MAX: int = RUINS_CLUSTERS_MAX * RUINS_PIECES_MAX

# ═══════════════════════════════════════════════════════════════════
#  RESOURCE AMOUNTS PER TILE (min, max) — set during terrain generation
#  Approximately 5x what a single tile's former capacity was, so a few
#  harvester buildings can sustain a long production chain.
# ═══════════════════════════════════════════════════════════════════

TILE_RESOURCE_FOREST: tuple[float, float] = (100.0, 300.0)
TILE_RESOURCE_DENSE_FOREST: tuple[float, float] = (100.0, 300.0)
TILE_RESOURCE_STONE_DEPOSIT: tuple[float, float] = (150.0, 400.0)
TILE_RESOURCE_FIBER_PATCH: tuple[float, float] = (75.0, 200.0)
TILE_RESOURCE_BERRY_PATCH: tuple[float, float] = (50.0, 150.0)  # Food capacity for berry patches
TILE_RESOURCE_MOUNTAIN: tuple[float, float] = (250.0, 600.0)
TILE_RESOURCE_IRON_VEIN: tuple[float, float] = (200.0, 500.0)
TILE_RESOURCE_COPPER_VEIN: tuple[float, float] = (200.0, 500.0)

# ═══════════════════════════════════════════════════════════════════
#  ORE VEIN GENERATION
# ═══════════════════════════════════════════════════════════════════

# Number of veins = max(ORE_VEIN_COUNT_MIN, ORE_VEIN_COUNT_BASE
#   + radius // ORE_VEIN_COUNT_RADIUS_DIVISOR)
# Iron and copper are tuned identically so the player gets roughly equal
# stocks of both metals.  Counts are kept small — even distribution
# across the map is enforced by ring-bucketing the seed picker (see
# ``_generate_ore_veins``), so a low count still reaches every ring
# of the map without painting the whole world in ore.
ORE_IRON_VEIN_COUNT_MIN: int = 8
ORE_IRON_VEIN_COUNT_BASE: int = 6
ORE_IRON_VEIN_COUNT_RADIUS_DIVISOR: int = 8

ORE_COPPER_VEIN_COUNT_MIN: int = 8
ORE_COPPER_VEIN_COUNT_BASE: int = 6
ORE_COPPER_VEIN_COUNT_RADIUS_DIVISOR: int = 8

# Vein size range (number of tiles per vein) — equal for iron and copper.
ORE_IRON_VEIN_SIZE_MIN: int = 8
ORE_IRON_VEIN_SIZE_MAX: int = 20

ORE_COPPER_VEIN_SIZE_MIN: int = 8
ORE_COPPER_VEIN_SIZE_MAX: int = 20

# Probability that a neighbor tile is added to the vein during BFS growth
ORE_VEIN_NEIGHBOR_EXPAND_CHANCE: float = 0.72

# ═══════════════════════════════════════════════════════════════════
#  OIL DEPOSIT GENERATION
# ═══════════════════════════════════════════════════════════════════

# Oil deposits spawn as small isolated black-pool clusters scattered
# across the map.  Each cluster is just 2-4 tiles (so an Oil Drill
# claims one specific deposit, Factorio-style).
OIL_DEPOSIT_CLUSTER_COUNT_MIN: int = 4
OIL_DEPOSIT_CLUSTER_COUNT_BASE: int = 3
OIL_DEPOSIT_CLUSTER_COUNT_RADIUS_DIVISOR: int = 18
OIL_DEPOSIT_CLUSTER_SIZE_MIN: int = 2
OIL_DEPOSIT_CLUSTER_SIZE_MAX: int = 4
# Probability that a neighbour tile joins an oil pool during BFS growth.
OIL_DEPOSIT_EXPAND_CHANCE: float = 0.55
# Resource amount (units of OIL) per deposit tile.
TILE_RESOURCE_OIL_DEPOSIT: tuple[float, float] = (300.0, 700.0)
# Minimum hex distance from camp for any oil cluster centre.
OIL_DEPOSIT_MIN_DISTANCE: int = 14

# ═══════════════════════════════════════════════════════════════════
#  TERRAIN GENERATION THRESHOLDS
# ═══════════════════════════════════════════════════════════════════

# Safe-zone radius around the camp (tiles cleared to grass)
SAFE_ZONE_RADIUS: int = 2

# River count
RIVER_COUNT: int = 3

# ═══════════════════════════════════════════════════════════════════
#  DISPLAY / CAMERA
# ═══════════════════════════════════════════════════════════════════

HEX_SIZE: int = 32  # radius in pixels (center to vertex)
FPS: int = 60
DEFAULT_WORLD_RADIUS: int = 80

# Camera zoom bounds
CAMERA_ZOOM_MIN: float = 0.1
CAMERA_ZOOM_MAX: float = 3.0

# ═══════════════════════════════════════════════════════════════════
#  COLLECTION RANGE
# ═══════════════════════════════════════════════════════════════════

# Hex-distance radius for resource-collection buildings
COLLECTION_RADIUS: int = 2


# -------------------------------------------------------------------
#  ANCIENT TECH THREAT  (towers that rise from the ground)
# -------------------------------------------------------------------

# How many awakenings can fire over the course of a game.
AWAKENING_MAX_COUNT: int = 3

# Population thresholds for trigger 1 (>= reaches the next awakening).
AWAKENING_POP_THRESHOLDS: list[int] = [20, 50, 100]

# Disturbance thresholds for trigger 2 (number of unique ruin tiles
# disturbed by the player; ascending per awakening).
AWAKENING_DISTURBANCE_THRESHOLDS: list[int] = [3, 7, 12]

# How many towers spawn per awakening, escalating with index.
AWAKENING_TOWERS_PER_EVENT: list[int] = [3, 6, 9]

# Wasteland radius (in hexes) around each tower.
AWAKENING_TOWER_RADIUS: int = 2

# Sites are kept this many hexes apart so towers spread across the
# map instead of clustering in one corner.
AWAKENING_TOWER_SEPARATION: int = 12

# Minimum / maximum hex distance from the player camp at which a
# tower can spawn.  Keeps the spaceship safe and lets towers reach
# most of the world rather than hugging the camp.
AWAKENING_MIN_CAMP_DISTANCE: int = 8
AWAKENING_MAX_CAMP_DISTANCE: int = 80

# Cutscene timings (real seconds).
AWAKENING_INTRO_TIME: float = 1.4
AWAKENING_PAN_TIME: float = 1.1
AWAKENING_RISE_TIME: float = 1.6
AWAKENING_HOLD_TIME: float = 0.7
AWAKENING_OUTRO_TIME: float = 1.2

# Camera zoom forced during the cutscene.
AWAKENING_ZOOM: float = 1.4

# Letterbox bar height as a fraction of screen height.
AWAKENING_LETTERBOX_FRAC: float = 0.10

# Banner text shown over the cutscene.
AWAKENING_TITLE_TEXT: str = "AWAKENING"
AWAKENING_SUBTITLE_TEXT: str = "Ancient machines stir beneath the soil..."
AWAKENING_SKIP_HINT: str = "Space / click to skip"
