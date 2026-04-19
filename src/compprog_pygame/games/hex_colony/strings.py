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
}

# Short label used in the buildings tab (bottom bar).
# Falls back to BUILDING_LABELS if a key is missing.
BUILDING_SHORT_LABELS: dict[str, str] = {
    "RESEARCH_CENTER": "Research",
}


# ═════════════════════════════════════════════════════════════════
#  BUILDING DESCRIPTIONS  (tooltip under each card in the build menu)
# ═════════════════════════════════════════════════════════════════

BUILDING_DESCRIPTIONS: dict[str, str] = {
    "HABITAT":          "Houses 6 survivors",
    "PATH":             "Connects buildings",
    "BRIDGE":           "Path over water",
    "WOODCUTTER":       "Harvests wood",
    "QUARRY":           "Harvests stone",
    "GATHERER":         "Gathers fiber & food",
    "STORAGE":          "Stores 100 resources",
    "REFINERY":         "Processes metals",
    "MINING_MACHINE":   "Auto-mines ore (uses fuel)",
    "FARM":             "Grows food",
    "WELL":             "Boosts nearby farms",
    "WALL":             "Defensive wall",
    "WORKSHOP":         "Crafts buildings",
    "FORGE":            "Smelts metal bars",
    "ASSEMBLER":        "Builds advanced parts",
    "RESEARCH_CENTER":  "Unlocks tech tree",
}


# ═════════════════════════════════════════════════════════════════
#  BUILDING CATEGORIES  (section headers in the build menu)
# ═════════════════════════════════════════════════════════════════

BUILDING_CATEGORY_NAMES: list[str] = [
    "Core",
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

MENU_TITLE           = "Hex Colony"
MENU_SUBTITLE        = "Survive on a re-evolved Earth"
MENU_SEED_LABEL      = "World Seed"
MENU_SEED_PLACEHOLDER = "Leave blank for random seed"
MENU_MAP_SIZE_LABEL  = "Map Size"
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
    ("1 / 2 / 3",      "Set game speed"),
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
        "# Welcome to Hex Colony!",
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
        "1 per every 3 buildings.  Toggle Auto off to customise.",
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
        "\u2022 1 / 2 / 3 \u2014 set game speed.",
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
        "title": "Welcome to Hex Colony!",
        "lines": [
            "You've crash-landed on an alien world.",
            "Your crew needs Food to survive \u2014 without it",
            "your colonists will starve!",
            "",
            "Let's get started by setting up food production.",
        ],
    },
    {
        "id": "build_gatherer",
        "title": "Build a Gatherer",
        "lines": [
            "Open the Buildings tab at the bottom of the",
            "screen and select \u201cGatherer\u201d.",
            "",
            "Place it on a grass/plains tile near your Camp.",
            "Gatherers harvest Food from surrounding tiles.",
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
            "Keep an eye on the Food counter in the top bar.",
        ],
    },
    {
        "id": "build_woodcutter",
        "title": "Gather More Resources",
        "lines": [
            "You'll need Wood and Stone to build more.",
            "",
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
        "id": "workshop_crafting",
        "title": "Workshop Crafting",
        "lines": [
            "Your Workshop can craft materials and buildings.",
            "",
            "Click on the Workshop, then select a recipe",
            "from the dropdown menu. Workers will craft it",
            "using resources from your global inventory.",
        ],
    },
    {
        "id": "forge_smelting",
        "title": "Forge \u2014 Smelt Ores",
        "lines": [
            "The Forge smelts raw Iron and Copper into bars.",
            "",
            "Click on the Forge and pick a material recipe",
            "to start smelting. You'll need bars to craft",
            "advanced buildings and components.",
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


# ═════════════════════════════════════════════════════════════════
#  HOME SCREEN  (game-select screen)
# ═════════════════════════════════════════════════════════════════

HOME_TITLE           = "Select a Game"
HOME_HINT            = "Click a game to play  \u2022  ESC to quit"
HOME_NO_GAMES        = "No games registered yet!"
