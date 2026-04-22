"""Centralised user-facing text for Hex Colony.

Edit the strings here instead of digging through individual UI files.
Every tooltip, tutorial line, building description, notification,
menu label, overlay entry, and guide page lives in this one module.
"""

from __future__ import annotations

# ═════════════════════════════════════════════════════════════════
#  BUILDING LABELS  (shared by info panel, tier popup, bottom bar)
# ═════════════════════════════════════════════════════════════════

BUILDING_LABELS: dict[str, str] = {
    "CAMP":             "Ship Wreckage",
    "HABITAT":          "Habitat",
    "PATH":             "Path",
    "BRIDGE":           "Bridge",
    "WALL":             "Wall",
    "WOODCUTTER":       "Woodcutter",
    "QUARRY":           "Quarry",
    "GATHERER":         "Gatherer",
    "STORAGE":          "Storage",
    "REFINERY":         "Refinery",
    "MINING_MACHINE":   "Mining Machine",
    "FARM":             "Farm",
    "WELL":             "Well",
    "WORKSHOP":         "Workshop",
    "FORGE":            "Forge",
    "ASSEMBLER":        "Assembler",
    "RESEARCH_CENTER":  "Research Center",
    "CHEMICAL_PLANT":   "Chemical Plant",
    "CONVEYOR":         "Conveyor Belt",
    "SOLAR_ARRAY":      "Solar Array",
    "ROCKET_SILO":      "Rocket Silo",
    "OIL_DRILL":        "Oil Drill",
    "OIL_REFINERY":     "Oil Refinery",
    "PIPE":             "Pipe",
    "FLUID_TANK":       "Fluid Tank",
}

# Short label used in the buildings tab (bottom bar).
# Falls back to BUILDING_LABELS if a key is missing.
BUILDING_SHORT_LABELS: dict[str, str] = {
    "RESEARCH_CENTER": "Research",
    "CHEMICAL_PLANT":  "Chem Plant",
    "CONVEYOR":        "Conveyor",
    "SOLAR_ARRAY":     "Solar Panel",
    "ROCKET_SILO":     "Rocket Silo",
    "OIL_DRILL":       "Drill",
    "OIL_REFINERY":    "Oil Refinery",
    "PIPE":            "Pipe",
    "FLUID_TANK":      "Tank",
}


# ═════════════════════════════════════════════════════════════════
#  BUILDING DESCRIPTIONS  (tooltip under each card in the build menu)
# ═════════════════════════════════════════════════════════════════

BUILDING_DESCRIPTIONS: dict[str, str] = {
    "HABITAT":          "Houses 6 colonists. Population grows when a Habitat has free space and on-site Food.",
    "PATH":             "Connects buildings into a network so workers and haulers can reach them. Place anywhere except water.",
    "BRIDGE":           "Acts as a Path over water tiles. Required to reach islands or cross rivers.",
    "WOODCUTTER":       "Place adjacent to forest tiles to harvest Wood. Workers walk to nearby trees and bring logs back.",
    "QUARRY":           "Place adjacent to mountain or stone tiles to harvest Stone. Also harvests Iron & Copper from neighbouring veins.",
    "GATHERER":         "Place on / next to grass and fiber patches to harvest Fiber and Food.",
    "STORAGE":          "Buffers up to 100 of one resource type. Click to choose which resource to stockpile.",
    "REFINERY":         "Crafting station: turns Stone into Bricks and (with research) Stone+Iron into Concrete.",
    "MINING_MACHINE":   "Deep-mines an adjacent ore vein. Burns Charcoal or Petroleum as fuel \u2014 keep it supplied.",
    "FARM":             "Grows Food on any tile. Output multiplied by adjacent Wells.",
    "WELL":             "Place adjacent to one or more Farms to boost their Food output. Must be on or next to water.",
    "WALL":             "Decorative / defensive barrier. Blocks pathfinding but doesn't connect to your network.",
    "WORKSHOP":         "Crafting station: planks, rope, copper wire, and most placeable buildings. Click and pick a recipe.",
    "FORGE":            "Crafting station: smelts ore into Iron / Copper Bars and (with research) Steel Bars, Glass and Charcoal.",
    "ASSEMBLER":        "Crafting station: machines Gears, Silicon, Circuits and assembles late-game items like the Rocket Silo.",
    "RESEARCH_CENTER":  "Spend resources over time to unlock new buildings and recipes. Open Tech Tree from its info panel or via the Help button.",
    "CHEMICAL_PLANT":   "Crafting station: synthesises Plastic, Rocket Fuel and Rubber from Charcoal, Glass and Petroleum.",
    "CONVEYOR":         "Acts as a Path; colonists walking on it move at 2x speed. Great for long supply lines.",
    "SOLAR_ARRAY":      "Passive: every adjacent crafting station (Workshop / Forge / Assembler / Refinery / Chemical Plant) crafts +25% faster.",
    "ROCKET_SILO":      "End-game goal. Feed it Rocket Parts assembled at the Assembler to launch off-world and win.",
    "OIL_DRILL":        "Must be placed directly on an Oil Deposit tile. Pumps Crude Oil automatically with no fuel. Connect to refinery via Pipes.",
    "OIL_REFINERY":     "Crafting station: turns Crude Oil into Petroleum (a powerful fuel) and Lubricant (used in Robotic Arms).",
    "PIPE":             "Carries fluids (Oil, Petroleum, Lubricant, Rocket Fuel) between buildings. Workers can't carry fluids \u2014 only pipes can.",
    "FLUID_TANK":       "Buffers one fluid type. Connect to producers and consumers via Pipes; click to select which fluid.",
}


# ═════════════════════════════════════════════════════════════════
#  BUILDING CATEGORIES  (section headers in the build menu)
# ═════════════════════════════════════════════════════════════════

BUILDING_CATEGORY_NAMES: list[str] = [
    "Science",
    "Housing",
    "Resource",
    "Processing",
    "Logistics",
]


# ═════════════════════════════════════════════════════════════════
#  RESOURCE NAMES  (display names derived from enum values)
# ═════════════════════════════════════════════════════════════════

RESOURCE_NAMES: dict[str, str] = {
    "WOOD":        "Wood",
    "FIBER":       "Fiber",
    "STONE":       "Stone",
    "FOOD":        "Food",
    "IRON":        "Iron",
    "COPPER":      "Copper",
    "PLANKS":      "Planks",
    "IRON_BAR":    "Iron Bar",
    "COPPER_BAR":  "Copper Bar",
    "BRICKS":      "Bricks",
    "COPPER_WIRE": "Copper Wire",
    "ROPE":        "Rope",
    "CHARCOAL":    "Charcoal",
    "GLASS":       "Glass",
    "STEEL_BAR":   "Steel Bar",
    "GEARS":       "Gears",
    "SILICON":     "Silicon",
    "CIRCUIT":     "Circuit",
    "CONCRETE":    "Concrete",
    "PLASTIC":     "Plastic",
    "ELECTRONICS": "Electronics",
    "BATTERY":     "Battery",
    "ROCKET_FUEL": "Rocket Fuel",
    "ROCKET_PART": "Rocket Part",
    "OIL":         "Crude Oil",
    "PETROLEUM":   "Petroleum",
    "LUBRICANT":   "Lubricant",
    "RUBBER":      "Rubber",
    "STEEL_PLATE": "Steel Plate",
    "REINFORCED_CONCRETE": "Reinforced Concrete",
    "ADVANCED_CIRCUIT":    "Advanced Circuit",
    "ROBOTIC_ARM": "Robotic Arm",
    "PAPER":       "Paper",
}


def resource_name(key: str) -> str:
    """Look up a human-readable resource name, with a fallback."""
    return RESOURCE_NAMES.get(key, key.replace("_", " ").title())


def building_label(key: str) -> str:
    """Look up a human-readable building name, with a fallback."""
    return BUILDING_LABELS.get(key, key.replace("_", " ").title())


def building_short_label(key: str) -> str:
    """Short label for the bottom-bar buildings tab."""
    return BUILDING_SHORT_LABELS.get(key, building_label(key))


def building_description(key: str) -> str:
    """Tooltip description for a building type."""
    return BUILDING_DESCRIPTIONS.get(key, "")


# ═════════════════════════════════════════════════════════════════
#  NOTIFICATIONS  (push messages that appear at the top of screen)
# ═════════════════════════════════════════════════════════════════

NOTIF_RESEARCH_COMPLETE  = "Research complete: {name}"
NOTIF_GOD_MODE_ON        = "God mode ON"
NOTIF_GOD_MODE_OFF       = "God mode OFF"
NOTIF_REQUIRES_RESEARCH  = "Requires {name} research"
NOTIF_REQUIRES_TIER      = "Requires Tier {level}: {name}"
NOTIF_BUILT              = "Built {name}"
NOTIF_BUILT_PATH         = "Built {count} {label}"  # label = "tile"/"tiles"
NOTIF_NEW_COLONIST       = "A new colonist was born!"
NOTIF_UNREACHABLE        = "No workers can reach {name}"


# ═════════════════════════════════════════════════════════════════
#  MENU SCREEN  (hex colony title / seed / play)
# ═════════════════════════════════════════════════════════════════

MENU_TITLE           = "RePioneer"
MENU_SUBTITLE        = "Survive  •  Reclaim  •  Rebuild"
MENU_SEED_LABEL      = "World Seed"
MENU_SEED_PLACEHOLDER = "Leave blank for random seed"
MENU_MAP_SIZE_LABEL  = "Map Size"
MENU_DIFFICULTY_LABEL = "Difficulty"
MENU_DIFFICULTY_EASY = "Isolation"
MENU_DIFFICULTY_HARD = "Evolution"
MENU_DIFFICULTY_EASY_DESC = "Rebuild humanity's old home"
MENU_DIFFICULTY_HARD_DESC = "There's something out there..."
MENU_PLAY_BUTTON     = "Play"
MENU_HINT            = "Enter seed  \u2022  ENTER or click Play  \u2022  ESC to go back"


# ═════════════════════════════════════════════════════════════════
#  PAUSE MENU
# ═════════════════════════════════════════════════════════════════

PAUSE_TITLE          = "Paused"
PAUSE_BUTTONS: list[str] = ["Resume", "Options", "Return to Main Menu", "Quit"]

OPTIONS_TITLE        = "Options"
OPTIONS_GRAPHICS     = "Graphics Quality"
OPTIONS_MUSIC        = "Music Volume"
OPTIONS_SFX          = "Sound Effects"
OPTIONS_BACK         = "Back"

QUALITY_DESCRIPTIONS: dict[str, str] = {
    "high":   "Full gradients, overlays, and contours",
    "medium": "Blended colors, overlays, no triangle gradients",
    "low":    "Flat tile colors and buildings only",
}


# ═════════════════════════════════════════════════════════════════
#  GAME OVER
# ═════════════════════════════════════════════════════════════════

GAME_OVER_TITLE      = "All Survivors Lost"
GAME_OVER_BUTTONS: list[str] = ["Return to Main Menu", "Quit"]
GAME_OVER_STATS      = "Survived {time}   |   Buildings: {buildings}"


# ═════════════════════════════════════════════════════════════════
#  RESOURCE BAR  (top bar indicators)
# ═════════════════════════════════════════════════════════════════

RESOURCE_BAR_DELETE  = "DELETE [X]"
RESOURCE_BAR_SANDBOX = "SANDBOX"
RESOURCE_BAR_MAX_TIER = "(Max Tier)"


# ═════════════════════════════════════════════════════════════════
#  BUILDING INFO PANEL  (right-side panel when a building is clicked)
# ═════════════════════════════════════════════════════════════════

INFO_RESIDENTS       = "Residents: {current}/{cap}"
INFO_RESIDENTS_OVER  = "Residents: ({cap}+{over})/{cap}"
INFO_POPULATION      = "Population: {pop}/{housing}"
INFO_HOMELESS        = "Homeless: {count}"
INFO_WORKERS         = "Workers: {current}/{max}"
INFO_STORAGE         = "Storage: {current}/{cap}"
INFO_OUTPUT          = "Output: {current}/{cap}"
INFO_INPUTS_HEADER   = "Inputs:"
INFO_OUTPUTS_HEADER  = "Outputs:"
INFO_OTHER_HEADER    = "Other:"
INFO_MATERIALS_HEADER = "Materials:"
INFO_SELECT_RECIPE   = "Select recipe:"
INFO_SELECT_RECIPE_DD = "Select recipe..."
INFO_CRAFTING        = "Crafting: {name}"
INFO_CRAFTING_MAT    = "Crafting: {name} \u00d7{amount}"
INFO_PROGRESS        = "Progress: {pct}%"
INFO_GATHERS         = "Gathers: {name}"
INFO_MINING          = "Mining: {name}"
INFO_STORES          = "Stores: {name}"
INFO_STORES_NONE     = "Stores: (none selected)"
INFO_STONE_DEFAULT   = "Stone (default)"
INFO_TIER_FORMAT     = "Tier {level}: {name}"
INFO_NEXT_TIER       = "Next \u2192 Tier {level}: {name}"
INFO_UNLOCKED        = "Unlocked: {names}"
INFO_MAX_TIER        = "(Max tier reached)"
INFO_OPEN_TECH_TREE  = "\u2261 Open Tech Tree"


# ═════════════════════════════════════════════════════════════════
#  HELP OVERLAY  (H key — keybinding reference)
# ═════════════════════════════════════════════════════════════════

HELP_TITLE = "Controls"
HELP_DISMISS = "Press H or ESC to close"

HELP_BINDINGS: list[tuple[str, str]] = [
    ("WASD / Arrows",  "Pan camera"),
    ("Scroll wheel",   "Zoom in / out"),
    ("Left click",     "Select tile / place building"),
    ("Right click",    "Cancel build / deselect / pan"),
    ("Middle click",   "Pan camera"),
    ("B",              "Cycle build mode"),
    ("X",              "Toggle delete mode"),
    ("H",              "Toggle this help overlay"),
    ("I",              "Toggle game guide"),
    ("1 / 2 / 3 / 5",  "Set game speed (5 = 10x)"),
    ("Tab",            "Toggle sandbox mode"),
    ("Alt (hold)",     "Show resource overlay"),
    ("Escape",         "Pause menu"),
]


# ═════════════════════════════════════════════════════════════════
#  INFO GUIDE OVERLAY  (I key — multi-page game guide)
# ═════════════════════════════════════════════════════════════════

GUIDE_WINDOW_TITLE = "Game Guide"
GUIDE_DISMISS      = "Press I or Escape to close"

# Each entry is (tab_title, list_of_lines).
# Lines starting with "#" render as section headers.
GUIDE_PAGES: list[tuple[str, list[str]]] = [
    ("Getting Started", [
        "# Welcome to RePioneer!",
        "You've crash-landed on an alien world.  Build a thriving",
        "colony by harvesting resources, constructing buildings,",
        "and managing your growing population.",
        "",
        "# First Steps",
        "1. Place Paths to connect your Camp to resource tiles.",
        "2. Build a Woodcutter on a forest tile for Wood.",
        "3. Build a Quarry on a mountain tile for Stone.",
        "4. Build a Gatherer on a plains tile for Fiber.",
        "5. Place a Storage building to stockpile excess goods.",
        "6. Build a Habitat to house more colonists.",
        "",
        "# Tips",
        "\u2022 Buildings must be connected to the Camp by Paths.",
        "\u2022 Workers are assigned automatically (see Workers tab).",
        "\u2022 Hold Alt to see the resource overlay on the map.",
    ]),
    ("Buildings", [
        "# Harvesting Buildings",
        "\u2022 Woodcutter \u2014 harvests Wood from forests.",
        "\u2022 Quarry \u2014 harvests Stone (or ores) from mountains.",
        "\u2022 Gatherer \u2014 harvests Fiber from plains.",
        "\u2022 Farm \u2014 produces Food (requires research).",
        "\u2022 Well \u2014 produces Food from water tiles (requires research).",
        "",
        "# Production Buildings",
        "\u2022 Workshop \u2014 crafts materials and buildings from recipes.",
        "\u2022 Forge \u2014 smelts metals and crafts advanced items.",
        "\u2022 Assembler \u2014 assembles complex components (Tier 2).",
        "\u2022 Refinery \u2014 processes raw ores into metals (requires research).",
        "\u2022 Mining Machine \u2014 deep-mines resources (Tier 2).",
        "",
        "# Infrastructure",
        "\u2022 Path / Bridge \u2014 connects buildings into a network.",
        "\u2022 Wall \u2014 decorative barrier, blocks pathfinding.",
        "\u2022 Storage \u2014 stockpiles resources for the network.",
        "\u2022 Habitat \u2014 houses colonists; more residents = growth.",
        "\u2022 Research Center \u2014 unlocks new technologies.",
    ]),
    ("Resources & Crafting", [
        "# Raw Resources",
        "\u2022 Wood \u2014 from Woodcutters on forest tiles.",
        "\u2022 Stone \u2014 from Quarries on mountain tiles.",
        "\u2022 Fiber \u2014 from Gatherers on plains.",
        "\u2022 Food \u2014 from Farms, Wells, or Gatherers.",
        "",
        "# Crafted Materials",
        "Workshops, Forges, and Assemblers transform raw",
        "resources into processed materials.  Set a recipe on",
        "the building via its info panel (click the building).",
        "",
        "# Logistics",
        "Logistics workers automatically move resources between",
        "buildings in the same network.  They pick up from",
        "suppliers and deliver to consumers based on the",
        "demand and supply priority hierarchies.",
        "",
        "# Building Recipes",
        "Some buildings can craft other buildings as items.",
        "The crafted building appears in your inventory and",
        "can be placed on the map without additional cost.",
    ]),
    ("Workers & Logistics", [
        "# Worker Assignment",
        "Workers are assigned to buildings based on the priority",
        "hierarchy in the Workers tab.  Higher-tier buildings are",
        "staffed first.  Drag cards in the Edit Hierarchy overlay",
        "to re-order priorities.",
        "",
        "# Auto Mode",
        "By default, worker assignment is automatic: all buildings",
        "share one tier, and logistics workers are allocated as",
        "1 per 4 buildings (rounded down, minimum 1).  Toggle Auto",
        "off to customise.",
        "",
        "# Logistics Workers",
        "Logistics workers carry resources between buildings.",
        "Adjust the logistics count with +/- in the Workers tab.",
        "More logistics workers means faster resource delivery.",
        "",
        "# Demand & Supply Priority",
        "The Demand tab controls which buildings receive resources",
        "first.  The Supply tab controls which buildings are drawn",
        "from first.  Both support Auto and Manual modes.",
    ]),
    ("Research & Tiers", [
        "# Research",
        "Build a Research Center and select a technology to",
        "research.  Research consumes resources over time.",
        "Completed research unlocks new buildings and recipes.",
        "",
        "# Tech Tree",
        "Open the tech tree from the Research Center's info",
        "panel to see all available and locked technologies.",
        "Some techs require prerequisites to be researched first.",
        "",
        "# Tiers",
        "The colony progresses through tiers as you meet",
        "requirements (population, buildings, resources, research).",
        "Each tier may unlock new building types.",
        "",
        "Tier 0: Crash Site \u2014 starting buildings.",
        "Tier 1: Foothold \u2014 8 pop, 6 buildings.",
        "Tier 2: Settlement \u2014 15 pop, 100 Food, 1 research.",
        "Tier 3: Colony \u2014 25 pop, 50 Iron, 25 Copper, 3 research.",
    ]),
    ("Controls", [
        "# Camera",
        "\u2022 WASD / Arrow keys \u2014 pan the camera.",
        "\u2022 Scroll wheel \u2014 zoom in / out.",
        "\u2022 Middle click + drag \u2014 pan the camera.",
        "",
        "# Building",
        "\u2022 Left click \u2014 select tile / place building.",
        "\u2022 Right click \u2014 cancel build / deselect.",
        "\u2022 B \u2014 cycle build mode.",
        "\u2022 X \u2014 toggle delete mode.",
        "",
        "# Interface",
        "\u2022 I \u2014 toggle this info guide.",
        "\u2022 H \u2014 toggle quick controls reference.",
        "\u2022 1 / 2 / 3 / 5 \u2014 set game speed (5 = 10x).",
        "\u2022 Tab \u2014 toggle sandbox mode.",
        "\u2022 Alt (hold) \u2014 show resource overlay.",
        "\u2022 Escape \u2014 pause menu.",
        "\u2022 F1 \u2014 toggle god mode.",
    ]),
]


# ═════════════════════════════════════════════════════════════════
#  TUTORIAL  (step-by-step hints for new players)
# ═════════════════════════════════════════════════════════════════

TUTORIAL_DISMISS_BUTTON = "Got it!"

# Each dict: id, title, lines (list[str]).
# Trigger logic stays in ui_tutorial.py — only the text lives here.
TUTORIAL_STEPS: list[dict[str, object]] = [
    {
        "id": "welcome",
        "title": "Welcome to RePioneer!",
        "lines": [
            "You've crash-landed on an abandoned Earth.",
            "Your crew needs Food to survive \u2014 without it",
            "your colonists will starve!",
            "",
            "Let's get started by setting up food production.",
        ],
    },
    {
        "id": "basic_controls",
        "title": "Basic Controls",
        "lines": [
            "Left-click a tile or building to see info",
            "about it in the side panel.",
            "",
            "Hold middle-click (or right-click on empty",
            "space) and drag to pan the camera. Scroll",
            "to zoom. Middle-click also pans menus that",
            "scroll.",
            "",
            "Right-click to cancel build mode or clear",
            "your current selection.",
        ],
    },
    {
        "id": "build_gatherer",
        "title": "Build a Gatherer",
        "lines": [
            "Open the Buildings tab at the bottom of the",
            "screen and select \u201cGatherer\u201d from",
            "the Resource subtab",
            "Place it on a fiber patch tile (light green",
            "with spots) near your crash zone.",
            "Gatherers harvest Food and Fiber.",
        ],
    },
    {
        "id": "connect_paths",
        "title": "Connect with Paths",
        "lines": [
            "Your Gatherer needs a path connection to the",
            "Camp so workers can reach it.",
            "",
            "Select \u201cPath\u201d from Buildings, click near the",
            "Camp, then click near the Gatherer to lay a",
            "route automatically.",
        ],
    },
    {
        "id": "food_producing",
        "title": "Food Production Started!",
        "lines": [
            "Great! Workers are now gathering Food.",
            "Click on the Gatherer to see its info panel.",
            "It defaults to Food \u2014 you can switch to Fiber",
            "later if you need it for crafting.",
            "",
            "Keep an eye on the population in the top bar.",
        ],
    },
    {
        "id": "build_woodcutter",
        "title": "Gather More Resources",
        "lines": [
            "You'll need Wood and Stone to craft buildings",
            "and resources.",
            "Place a Woodcutter on a forest tile and a",
            "Quarry on a mountain tile, then connect them",
            "with Paths.",
        ],
    },
    {
        "id": "build_habitat",
        "title": "Build a Habitat",
        "lines": [
            "Your Camp can only house a few colonists.",
            "Build a Habitat to provide more housing \u2014",
            "colonists will reproduce when they have food",
            "and a home with room.",
            "",
            "More people means more workers!",
        ],
    },
    {
        "id": "tier_goal",
        "title": "Watch Your Tier Goals",
        "lines": [
            "Look at the bar at the top of the screen \u2014",
            "it shows your current tier and progress toward",
            "the next one.",
            "",
            "Use those goals to guide what to build next:",
            "more population, specific buildings, or a",
            "lifetime amount of certain resources.",
        ],
    },
    {
        "id": "workshop_crafting",
        "title": "Workshop Crafting",
        "lines": [
            "Workshops can craft materials and buildings.",
            "",
            "Click on the Workshop, then select a recipe",
            "from the dropdown menu. Workers will craft it",
            "using resources from your global inventory.",
        ],
    },
    {
        "id": "mining_smelting",
        "title": "Mining & Smelting",
        "lines": [
            "Iron and Copper ore tiles can be harvested by a",
            "Quarry placed adjacent to them.",
            "",
            "Once you have raw ore, build a Forge and pick a",
            "smelting recipe to turn it into bars. You'll",
            "need bars to craft advanced buildings.",
        ],
    },
    {
        "id": "research",
        "title": "Research New Tech",
        "lines": [
            "Your Research Center can unlock new buildings",
            "and recipes.",
            "",
            "Click on it and select a technology to research.",
            "Research consumes resources over time. Open the",
            "Tech Tree to see what's available.",
        ],
    },
    {
        "id": "population_growing",
        "title": "Population Growing!",
        "lines": [
            "Your colony is expanding. More colonists means",
            "you can staff more buildings.",
            "",
            "Check the Workers tab to see how workers are",
            "assigned. Logistics workers move resources",
            "between buildings automatically.",
        ],
    },
    {
        "id": "useful_controls",
        "title": "Useful Controls",
        "lines": [
            "Hold Alt to see the resource overlay \u2014 it",
            "highlights which tiles have resources nearby.",
            "",
            "Press I to open the Info Guide with detailed",
            "colony stats and controls reference.",
            "",
            "Press 1 / 2 / 3 / 5 to change the game speed.",
        ],
    },
    # ── Tier 4+ feature tutorials ─────────────────────────────────
    {
        "id": "industrial_intro",
        "title": "Welcome to the Industrial Age",
        "lines": [
            "You've reached the Industrial tier! Open the",
            "Tech Tree to research new advanced unlocks:",
            "",
            "  - Conveyor Belts \u2014 colonists walk 2x faster",
            "  - Basic Chemistry \u2014 unlocks the Chemical Plant",
            "  - Concrete Works \u2014 a stone-and-iron material",
            "    used for end-game buildings.",
        ],
    },
    {
        "id": "conveyor_intro",
        "title": "Conveyor Belts",
        "lines": [
            "Place Conveyor tiles like paths. Anyone walking",
            "onto a Conveyor moves at 2x speed \u2014 great for",
            "long logistics routes between distant outposts.",
            "",
            "Crafted at the Workshop from Iron Bars + Gears.",
        ],
    },
    {
        "id": "chemical_plant_intro",
        "title": "The Chemical Plant",
        "lines": [
            "The Chemical Plant synthesises advanced materials",
            "your Forge can't produce: Plastic, Rocket Fuel,",
            "and other polymers.",
            "",
            "Assign a worker and pick a recipe just like the",
            "Forge or Refinery.",
        ],
    },
    {
        "id": "automation_intro",
        "title": "Automation Tier",
        "lines": [
            "You've unlocked the Automation tier. Research",
            "Solar Panels to build Solar Arrays \u2014 they boost",
            "all adjacent crafting stations by 25%.",
            "",
            "You'll also need Batteries and Microchips to push",
            "into the spacefaring endgame.",
        ],
    },
    {
        "id": "solar_array_intro",
        "title": "Solar Arrays",
        "lines": [
            "Solar Arrays passively boost the speed of every",
            "adjacent Assembler, Forge, Refinery, and Chemical",
            "Plant by 25%.",
            "",
            "Cluster them around your busiest crafting hubs.",
        ],
    },
    {
        "id": "spacefarer_intro",
        "title": "Spacefarer Tier",
        "lines": [
            "The final tier! Research Rocketry to make Rocket",
            "Fuel, then Orbital Assembly to unlock the Rocket",
            "Silo.",
            "",
            "Assemble Rocket Parts to escape this world and",
            "win the game.",
        ],
    },
    {
        "id": "rocket_silo_intro",
        "title": "The Rocket Silo",
        "lines": [
            "Build the Rocket Silo and feed it Rocket Parts to",
            "launch your colony off-world.",
            "",
            "Each Rocket Part needs Steel Bars, Electronics,",
            "and Concrete \u2014 plan your supply chains!",
        ],
    },
    {
        "id": "petrochemical_intro",
        "title": "Petrochemical Tier",
        "lines": [
            "You've entered the Petrochemical tier! Black Oil",
            "Deposits dot the world \u2014 surface pools of crude",
            "oil waiting to be tapped.",
            "",
            "Research Petroleum Engineering to unlock the Oil",
            "Drill and Oil Refinery, then refine Oil into",
            "Petroleum, Lubricant, and Rubber.",
        ],
    },
    {
        "id": "oil_deposit_intro",
        "title": "Oil Deposits",
        "lines": [
            "Those black pools scattered across the map are",
            "Oil Deposits. Buildings can't be placed on them",
            "\u2014 except for the Oil Drill, which sits directly",
            "on top of one and pumps the crude oil out.",
            "",
            "Each deposit holds a finite amount of oil, so",
            "spread your drills across multiple pools.",
        ],
    },
    {
        "id": "oil_drill_intro",
        "title": "The Oil Drill",
        "lines": [
            "Place an Oil Drill directly onto an Oil Deposit",
            "tile. It runs automatically with no fuel and",
            "fills its own storage with Crude Oil.",
            "",
            "Crude Oil is a fluid \u2014 workers cannot carry it.",
            "Connect the drill to a refinery with Pipes.",
        ],
    },
    {
        "id": "pipe_intro",
        "title": "Pipes & Fluid Tanks",
        "lines": [
            "Fluids (Oil, Petroleum, Lubricant, Rocket Fuel)",
            "never travel by worker \u2014 only through Pipes.",
            "",
            "Place Pipes (made from Steel) to connect any",
            "fluid-using buildings: drills, refineries,",
            "chemical plants, mining machines, and silos.",
            "",
            "Fluid Tanks attach to a pipe network and buffer",
            "one fluid of your choice for later use.",
        ],
    },
    {
        "id": "oil_refinery_intro",
        "title": "The Oil Refinery",
        "lines": [
            "The Oil Refinery is a new crafting station that",
            "turns Crude Oil into Petroleum (a high-grade",
            "fuel) and Lubricant (used in Robotic Arms).",
            "",
            "Petroleum can fuel Mining Machines 2.5x as long",
            "as Charcoal, and feeds the Chemical Plant's",
            "Rubber recipe.",
        ],
    },
    {
        "id": "advanced_materials_intro",
        "title": "Advanced Materials",
        "lines": [
            "Late-game tech now unlocks new materials at",
            "every node: Steel Plate, Reinforced Concrete,",
            "Advanced Circuits, and Robotic Arms.",
            "",
            "These feed into Automation and Spacefarer tier",
            "goals \u2014 and the Rocket Silo itself now demands",
            "Reinforced Concrete and Robotic Arms.",
        ],
    },
]


# ═════════════════════════════════════════════════════════════════
#  TIER POPUP  (shown when advancing to a new tier)
# ═════════════════════════════════════════════════════════════════

TIER_POPUP_TITLE     = "Tier {level}: {name}"
TIER_UNLOCKED_HEADER = "Unlocked Buildings:"
TIER_NO_UNLOCKS      = "No new buildings unlocked."
TIER_NEXT_HEADER     = "Next: Tier {level} \u2014 {name}"
TIER_MAX_REACHED     = "Maximum tier reached!"
TIER_DISMISS_HINT    = "Click anywhere or press Escape to continue"
TIER_REQ_POPULATION  = "  \u2022 Population: {amount}"
TIER_REQ_BUILDINGS   = "  \u2022 Buildings: {amount}"
TIER_REQ_RESOURCE    = "  \u2022 {name}: {amount}"
TIER_REQ_RESEARCH    = "  \u2022 Research completed: {amount}"


# ═════════════════════════════════════════════════════════════════
#  COLONY STATS TAB  (Info tab at the bottom bar)
# ═════════════════════════════════════════════════════════════════

STATS_COLONY_AGE     = "Colony age"
STATS_POPULATION     = "Population"
STATS_BUILDINGS      = "Buildings"


# ═════════════════════════════════════════════════════════════════
#  BOTTOM BAR TAB LABELS
# ═════════════════════════════════════════════════════════════════

TAB_BUILDINGS = "Buildings"
TAB_WORKERS   = "Workers"
TAB_DEMAND    = "Demand"
TAB_SUPPLY    = "Supply"
TAB_STATS     = "Stats"
TAB_INFO      = "Info"

# Hover tooltips for the bottom-bar tabs.  Aimed at first-time players
# — explain *why* each tab exists, not just what it shows.
TAB_TOOLTIPS: dict[str, str] = {
    TAB_BUILDINGS: (
        "Pick a building to place on the map.\n"
        "Cards show stock — empty cards mean you must craft more at "
        "a Workshop or Assembler first."
    ),
    TAB_WORKERS: (
        "Set how aggressively each building competes for workers.\n"
        "Higher priority buildings fill their job slots first when "
        "people are scarce."
    ),
    TAB_DEMAND: (
        "Order which consumers logistics workers serve first.\n"
        "Use this when something keeps running out of inputs even "
        "though you produce it."
    ),
    TAB_SUPPLY: (
        "Order which suppliers logistics workers pull from first.\n"
        "Useful for keeping a key Workshop fed before sending overflow "
        "to Storage."
    ),
    TAB_STATS: (
        "Live colony stats: production, consumption, idle workers, "
        "and storage levels."
    ),
    TAB_INFO: (
        "Colony at a glance: age, population, building count."
    ),
}

# Tooltips for the top resource-bar elements.  Each value is a (title,
# body) pair so the renderer can show an emphasised title above an
# explanation.
RESOURCE_BAR_TOOLTIPS: dict[str, tuple[str, str]] = {
    "tier": (
        "Current Tier",
        "Your colony's tech tier.  Each new tier unlocks new buildings "
        "and recipes.  Click the Ship Wreckage to advance once the "
        "requirements shown here are met.",
    ),
    "population": (
        "Population / Housing",
        "Number of colonists living in your buildings versus total "
        "housing capacity.  When pop > housing, growth slows and "
        "colonists become unhappy.",
    ),
    "research": (
        "Active Research",
        "Click to open the Tech Tree.  A Research Center with at "
        "least one assigned worker is required for any progress.",
    ),
    "research_idle": (
        "Tech Tree",
        "Click to choose a research project.  Build a Research "
        "Center, assign a worker, and feed it the required resources.",
    ),
    "help": (
        "Help & Guide",
        "Open the in-game guide: getting started, current tier "
        "goals, every unlocked building, all recipes, the research "
        "list, and key bindings.  (Shortcut: H or I)",
    ),
    "delete": (
        "Delete Mode (X)",
        "Press X or click the red Delete card in the Buildings tab "
        "to toggle.  Click any of your buildings to demolish it; "
        "half of the materials are returned to your inventory.",
    ),
    "sandbox": (
        "Sandbox Mode",
        "Free building, instant research, no resource costs.  Use "
        "this for testing layouts or learning the game.",
    ),
    "speed": (
        "Simulation Speed",
        "Press +/− to step the speed up or down.  Useful for "
        "watching long crafting chains or skipping idle time.",
    ),
}

# Tooltip shown when hovering the Help button on the help overlay
# itself (and used as the description of the Help tab).
HELP_BUTTON_TOOLTIP = (
    "Open the comprehensive guide.  Includes building recipes, "
    "current-tier goals, unlocked research, and key bindings."
)


# ═════════════════════════════════════════════════════════════════
#  HOME SCREEN  (game-select screen)
# ═════════════════════════════════════════════════════════════════

HOME_TITLE           = "RePioneer"
HOME_HINT            = "Press Play to begin  \u2022  ESC to quit"
HOME_NO_GAMES        = "No games registered yet!"
