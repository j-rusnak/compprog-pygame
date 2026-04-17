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

GATHER_RATE_WOOD: float = 0.1
GATHER_RATE_FIBER: float = 0.08
GATHER_RATE_STONE: float = 0.06
GATHER_RATE_FOOD: float = 0.05
GATHER_RATE_IRON: float = 0.08
GATHER_RATE_COPPER: float = 0.08

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
BUILDING_COST_HABITAT: dict[str, int] = {"IRON": 4, "WOOD": 8, "STONE": 6}
BUILDING_COST_PATH: dict[str, int] = {"STONE": 1, "WOOD": 1}
BUILDING_COST_BRIDGE: dict[str, int] = {"PLANKS": 4}
BUILDING_COST_WOODCUTTER: dict[str, int] = {"WOOD": 10, "STONE": 5}
BUILDING_COST_QUARRY: dict[str, int] = {"WOOD": 15, "FIBER": 5}
BUILDING_COST_GATHERER: dict[str, int] = {"WOOD": 8, "STONE": 3}
BUILDING_COST_STORAGE: dict[str, int] = {"WOOD": 20, "STONE": 10}
BUILDING_COST_REFINERY: dict[str, int] = {"IRON": 8, "STONE": 15, "WOOD": 10}
BUILDING_COST_MINING_MACHINE: dict[str, int] = {"IRON_BAR": 6, "STONE": 20, "WOOD": 10, "GEARS": 2}
BUILDING_COST_FARM: dict[str, int] = {"WOOD": 12, "FIBER": 8, "STONE": 4}
BUILDING_COST_WELL: dict[str, int] = {"STONE": 10, "WOOD": 6}
BUILDING_COST_WALL: dict[str, int] = {"STONE": 8, "WOOD": 4}
BUILDING_COST_WORKSHOP: dict[str, int] = {}
BUILDING_COST_FORGE: dict[str, int] = {"STONE": 20, "WOOD": 10}
BUILDING_COST_ASSEMBLER: dict[str, int] = {"IRON_BAR": 8, "COPPER_BAR": 4, "PLANKS": 6, "BRICKS": 6}
BUILDING_COST_RESEARCH_CENTER: dict[str, int] = {}

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
BUILDING_MAX_WORKERS_RESEARCH_CENTER: int = 0

# Housing capacity (number of people that can live here; 0 = not a dwelling)
BUILDING_HOUSING_CAMP: int = 10
BUILDING_HOUSING_HOUSE: int = 5
BUILDING_HOUSING_HABITAT: int = 6
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

# Storage capacity (max total resources stored; 0 = none)
# Camp capacity is set dynamically at placement time.
BUILDING_STORAGE_CAMP: int = 0
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
BUILDING_STORAGE_RESEARCH_CENTER: int = 0

# ═══════════════════════════════════════════════════════════════════
#  LOGISTICS
# ═══════════════════════════════════════════════════════════════════

# Items a single logistics worker can carry in one trip.
LOGISTICS_CARRY_CAPACITY: int = 5
# Worker count scaling factor — the more logistics workers, the more
# the proximity term dominates (so swarms spread across the map).
LOGISTICS_PROXIMITY_WORKER_FACTOR: float = 0.08

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
# Consumes a small amount of CHARCOAL per second while active.  Faster
# than a worker-staffed refinery but stops entirely when out of fuel.
MINING_MACHINE_RATE: float = 1.2  # ore per second (machine, not per worker)
MINING_MACHINE_FUEL_RATE: float = 0.08  # CHARCOAL per second while active
# Acceptable fuel resources (name -> energy multiplier).  Currently only
# CHARCOAL is implemented; additional fuels (coal, oil) will be added
# later and plugged in here.
MINING_MACHINE_FUELS: dict[str, float] = {
    "CHARCOAL": 1.0,
}

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
        "unlocks_buildings": ["BRIDGE", "FARM"],
        "requirements": {
            "population": 8,
            "buildings_placed": 6,
        },
    },
    # ── Tier 2 ───────────────────────────────────────────────────
    {
        "name": "Settlement",
        "description": "Begin processing raw materials",
        "unlocks_buildings": ["REFINERY", "WELL", "ASSEMBLER", "MINING_MACHINE"],
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
        "unlocks_buildings": [],  # future expansion
        "requirements": {
            "population": 25,
            "resource_gathered": {"IRON": 50, "COPPER": 25},
            "research_count": 3,
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
    "advanced_logistics": {
        "name": "Advanced Logistics",
        "description": "Unlock bridges for crossing water",
        "cost": {"WOOD": 15, "STONE": 10},
        "time": 20.0,
        "prerequisites": [],
        "unlocks": ["BRIDGE"],
        "position": (0, 0),
    },
    "agriculture": {
        "name": "Agriculture",
        "description": "Cultivate crops for steady food supply",
        "cost": {"WOOD": 20, "FIBER": 15},
        "time": 30.0,
        "prerequisites": [],
        "unlocks": ["FARM"],
        "position": (1, 0),
    },
    "metallurgy": {
        "name": "Metallurgy",
        "description": "Smelt raw ore into usable metal",
        "cost": {"STONE": 15, "WOOD": 10},
        "time": 35.0,
        "prerequisites": [],
        "unlocks": ["REFINERY"],
        "position": (2, 0),
    },
    "irrigation": {
        "name": "Irrigation",
        "description": "Wells boost adjacent farm output",
        "cost": {"STONE": 20, "IRON": 5},
        "time": 25.0,
        "prerequisites": ["agriculture"],
        "unlocks": ["WELL"],
        "position": (1, 1),
    },
    "fortification": {
        "name": "Fortification",
        "description": "Advanced wall construction techniques",
        "cost": {"STONE": 30, "IRON": 10},
        "time": 40.0,
        "prerequisites": ["metallurgy"],
        "unlocks": [],
        "position": (2, 1),
    },
    "advanced_smelting": {
        "name": "Advanced Smelting",
        "description": "Improved refinery efficiency",
        "cost": {"IRON": 15, "COPPER": 10},
        "time": 45.0,
        "prerequisites": ["metallurgy"],
        "unlocks": [],
        "position": (3, 1),
    },
    "exploration": {
        "name": "Exploration",
        "description": "Reveal more of the surrounding area",
        "cost": {"WOOD": 25, "FIBER": 20},
        "time": 30.0,
        "prerequisites": ["advanced_logistics"],
        "unlocks": [],
        "position": (0, 1),
    },
}

# ═══════════════════════════════════════════════════════════════════
#  RUINS
# ═══════════════════════════════════════════════════════════════════

# Ruins spawn as small clusters of weathered structures.  The map
# generates 1-2 clusters on small maps and up to 3 on large maps.
# Each cluster contains 5-8 ruin pieces placed on nearby tiles.
RUINS_CLUSTERS_MIN: int = 1
RUINS_CLUSTERS_MAX: int = 2
# Map-radius threshold above which an extra cluster may appear.
RUINS_EXTRA_CLUSTER_RADIUS: int = 80
# Pieces per cluster.
RUINS_PIECES_MIN: int = 5
RUINS_PIECES_MAX: int = 8
# Minimum hex distance from camp for any cluster centre.
RUINS_MIN_DISTANCE: int = 8
# Minimum hex distance between two cluster centres.
RUINS_CLUSTER_SEPARATION: int = 10
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

# Number of veins = max(ORE_VEIN_COUNT_MIN, ORE_VEIN_COUNT_BASE + radius // ORE_VEIN_COUNT_RADIUS_DIVISOR)
ORE_IRON_VEIN_COUNT_MIN: int = 3
ORE_IRON_VEIN_COUNT_BASE: int = 2
ORE_IRON_VEIN_COUNT_RADIUS_DIVISOR: int = 15

ORE_COPPER_VEIN_COUNT_MIN: int = 3
ORE_COPPER_VEIN_COUNT_BASE: int = 2
ORE_COPPER_VEIN_COUNT_RADIUS_DIVISOR: int = 15

# Vein size range (number of tiles per vein)
ORE_IRON_VEIN_SIZE_MIN: int = 6
ORE_IRON_VEIN_SIZE_MAX: int = 16

ORE_COPPER_VEIN_SIZE_MIN: int = 5
ORE_COPPER_VEIN_SIZE_MAX: int = 14

# Probability that a neighbor tile is added to the vein during BFS growth
ORE_VEIN_NEIGHBOR_EXPAND_CHANCE: float = 0.65

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
