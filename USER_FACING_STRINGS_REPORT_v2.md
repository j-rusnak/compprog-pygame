# Hex Colony — Exhaustive User-Facing Strings Report (v2)

Every hardcoded user-facing string in `src/compprog_pygame/games/hex_colony/`, organized by file. Each entry lists the exact line number(s), exact string content, and category.

**Categories:** `label`, `button_text`, `header`, `description`, `tooltip`, `notification`, `guide_text`, `hint`, `tab_label`, `other`

---

## params.py

### Tier Data — `TIER_DATA` (lines 389–437)

| Line(s) | String | Category |
|---------|--------|----------|
| 393 | `"Crash Site"` | label |
| 394 | `"Establish basic survival operations"` | description |
| 405 | `"Foothold"` | label |
| 406 | `"Secure basic resource production"` | description |
| 417 | `"Settlement"` | label |
| 418 | `"Begin processing raw materials"` | description |
| 429 | `"Colony"` | label |
| 430 | `"Establish a self-sustaining colony"` | description |

### Tech Tree Data — `TECH_TREE_DATA` (lines 448–510)

| Line(s) | String | Category |
|---------|--------|----------|
| 449 | `"Advanced Logistics"` | label |
| 450 | `"Unlock bridges for crossing water"` | description |
| 457 | `"Agriculture"` | label |
| 458 | `"Cultivate crops for steady food supply"` | description |
| 465 | `"Metallurgy"` | label |
| 466 | `"Smelt raw ore into usable metal"` | description |
| 473 | `"Irrigation"` | label |
| 474 | `"Wells boost adjacent farm output"` | description |
| 481 | `"Fortification"` | label |
| 482 | `"Advanced wall construction techniques"` | description |
| 489 | `"Advanced Smelting"` | label |
| 490 | `"Improved refinery efficiency"` | description |
| 497 | `"Exploration"` | label |
| 498 | `"Reveal more of the surrounding area"` | description |

---

## resources.py

### Resource Enum Names (lines 18–36)

These are used as display text via `res.name.replace("_", " ").title()` throughout the UI:

| Line | Enum Name | Displayed As | Category |
|------|-----------|-------------|----------|
| 18 | `WOOD` | "Wood" | label |
| 19 | `FIBER` | "Fiber" | label |
| 20 | `STONE` | "Stone" | label |
| 21 | `FOOD` | "Food" | label |
| 22 | `IRON` | "Iron" | label |
| 23 | `COPPER` | "Copper" | label |
| 25 | `PLANKS` | "Planks" | label |
| 26 | `IRON_BAR` | "Iron Bar" | label |
| 27 | `COPPER_BAR` | "Copper Bar" | label |
| 28 | `BRICKS` | "Bricks" | label |
| 29 | `COPPER_WIRE` | "Copper Wire" | label |
| 30 | `ROPE` | "Rope" | label |
| 31 | `CHARCOAL` | "Charcoal" | label |
| 32 | `GLASS` | "Glass" | label |
| 33 | `STEEL_BAR` | "Steel Bar" | label |
| 34 | `GEARS` | "Gears" | label |
| 35 | `SILICON` | "Silicon" | label |
| 36 | `CIRCUIT` | "Circuit" | label |

---

## ui.py

### RESOURCE_ICONS (lines 71–88)

Unicode glyphs displayed next to resource names (fallback icons):

| Line | Resource | Glyph | Category |
|------|----------|-------|----------|
| 72 | WOOD | `♣` (U+2663) | other |
| 73 | FIBER | `❀` (U+2740) | other |
| 74 | STONE | `▣` (U+25A3) | other |
| 75 | FOOD | `♥` (U+2665) | other |
| 76 | IRON | `◆` (U+25C6) | other |
| 77 | COPPER | `◇` (U+25C7) | other |
| 78 | PLANKS | `▭` (U+25AD) | other |
| 79 | IRON_BAR | `▬` (U+25AC) | other |
| 80 | COPPER_BAR | `▬` (U+25AC) | other |
| 81 | BRICKS | `▧` (U+25A7) | other |
| 82 | COPPER_WIRE | `ζ` (U+03B6) | other |
| 83 | ROPE | `⚃` (U+2683) | other |
| 84 | CHARCOAL | `▬` (U+25AC) | other |
| 85 | GLASS | `□` (U+25A1) | other |
| 86 | STEEL_BAR | `▬` (U+25AC) | other |
| 87 | GEARS | `⚙` (U+2699) | other |
| 88 | SILICON | `⬢` (U+2B22) | other |
| 89 | CIRCUIT | `▦` (U+25A6) | other |

---

## menu.py

| Line | String | Category |
|------|--------|----------|
| ~201 | `"Hex Colony"` | header |
| ~204 | `"Survive on a re-evolved Earth"` | description |
| ~209 | `"World Seed"` | label |
| ~222 | `"Leave blank for random seed"` | hint |
| ~226 | `"Map Size"` | label |
| ~242 | `"Play"` | button_text |
| ~246 | `"Enter seed  •  ENTER or click Play  •  ESC to go back"` | hint |

---

## game.py

### Tab Labels (lines ~135–154)

| Line | String | Category |
|------|--------|----------|
| ~135 | `"Workers"` | tab_label |
| ~140 | `"Demand"` | tab_label |
| ~145 | `"Supply"` | tab_label |
| ~150 | `"Stats"` | tab_label |
| ~154 | `"Info"` | tab_label |

### Notifications (various lines)

| Line | String | Category |
|------|--------|----------|
| ~198 | `f"Research complete: {node.name}"` | notification |
| ~260 | `"God mode ON"` | notification |
| ~260 | `"God mode OFF"` | notification |
| ~358 | `f"Requires {node.name} research"` | notification |
| ~365 | `f"Requires Tier {req_tier}: {tier_info.name}"` | notification |
| ~525 | `f"Built {self.build_mode.name.replace('_', ' ').title()}"` | notification |
| ~636 | `f"Built {placed} {label}"` (label = "tile"/"tiles") | notification |

---

## ui_info_guide.py

### Page Titles (lines 35–143)

| Line | String | Category |
|------|--------|----------|
| 35 | `"Getting Started"` | tab_label |
| 55 | `"Buildings"` | tab_label |
| 77 | `"Resources & Crafting"` | tab_label |
| 100 | `"Workers & Logistics"` | tab_label |
| 122 | `"Research & Tiers"` | tab_label |
| 143 | `"Controls"` | tab_label |

### "Getting Started" Page (lines 37–53)

| Line | String | Category |
|------|--------|----------|
| 37 | `"# Welcome to Hex Colony!"` | header |
| 38 | `"You've crash-landed on an alien world.  Build a thriving"` | guide_text |
| 39 | `"colony by harvesting resources, constructing buildings,"` | guide_text |
| 40 | `"and managing your growing population."` | guide_text |
| 42 | `"# First Steps"` | header |
| 43 | `"1. Place Paths to connect your Camp to resource tiles."` | guide_text |
| 44 | `"2. Build a Woodcutter on a forest tile for Wood."` | guide_text |
| 45 | `"3. Build a Quarry on a mountain tile for Stone."` | guide_text |
| 46 | `"4. Build a Gatherer on a plains tile for Fiber."` | guide_text |
| 47 | `"5. Place a Storage building to stockpile excess goods."` | guide_text |
| 48 | `"6. Build a Habitat to house more colonists."` | guide_text |
| 50 | `"# Tips"` | header |
| 51 | `"• Buildings must be connected to the Camp by Paths."` | guide_text |
| 52 | `"• Workers are assigned automatically (see Workers tab)."` | guide_text |
| 53 | `"• Hold Alt to see the resource overlay on the map."` | guide_text |

### "Buildings" Page (lines 56–75)

| Line | String | Category |
|------|--------|----------|
| 56 | `"# Harvesting Buildings"` | header |
| 57 | `"• Woodcutter — harvests Wood from forests."` | guide_text |
| 58 | `"• Quarry — harvests Stone (or ores) from mountains."` | guide_text |
| 59 | `"• Gatherer — harvests Fiber from plains."` | guide_text |
| 60 | `"• Farm — produces Food (requires research)."` | guide_text |
| 61 | `"• Well — produces Food from water tiles (requires research)."` | guide_text |
| 63 | `"# Production Buildings"` | header |
| 64 | `"• Workshop — crafts materials and buildings from recipes."` | guide_text |
| 65 | `"• Forge — smelts metals and crafts advanced items."` | guide_text |
| 66 | `"• Assembler — assembles complex components (Tier 2)."` | guide_text |
| 67 | `"• Refinery — processes raw ores into metals (requires research)."` | guide_text |
| 68 | `"• Mining Machine — deep-mines resources (Tier 2)."` | guide_text |
| 70 | `"# Infrastructure"` | header |
| 71 | `"• Path / Bridge — connects buildings into a network."` | guide_text |
| 72 | `"• Wall — decorative barrier, blocks pathfinding."` | guide_text |
| 73 | `"• Storage — stockpiles resources for the network."` | guide_text |
| 74 | `"• Habitat — houses colonists; more residents = growth."` | guide_text |
| 75 | `"• Research Center — unlocks new technologies."` | guide_text |

### "Resources & Crafting" Page (lines 78–98)

| Line | String | Category |
|------|--------|----------|
| 78 | `"# Raw Resources"` | header |
| 79 | `"• Wood — from Woodcutters on forest tiles."` | guide_text |
| 80 | `"• Stone — from Quarries on mountain tiles."` | guide_text |
| 81 | `"• Fiber — from Gatherers on plains."` | guide_text |
| 82 | `"• Food — from Farms, Wells, or Gatherers."` | guide_text |
| 84 | `"# Crafted Materials"` | header |
| 85 | `"Workshops, Forges, and Assemblers transform raw"` | guide_text |
| 86 | `"resources into processed materials.  Set a recipe on"` | guide_text |
| 87 | `"the building via its info panel (click the building)."` | guide_text |
| 89 | `"# Logistics"` | header |
| 90 | `"Logistics workers automatically move resources between"` | guide_text |
| 91 | `"buildings in the same network.  They pick up from"` | guide_text |
| 92 | `"suppliers and deliver to consumers based on the"` | guide_text |
| 93 | `"demand and supply priority hierarchies."` | guide_text |
| 95 | `"# Building Recipes"` | header |
| 96 | `"Some buildings can craft other buildings as items."` | guide_text |
| 97 | `"The crafted building appears in your inventory and"` | guide_text |
| 98 | `"can be placed on the map without additional cost."` | guide_text |

### "Workers & Logistics" Page (lines 101–120)

| Line | String | Category |
|------|--------|----------|
| 101 | `"# Worker Assignment"` | header |
| 102 | `"Workers are assigned to buildings based on the priority"` | guide_text |
| 103 | `"hierarchy in the Workers tab.  Higher-tier buildings are"` | guide_text |
| 104 | `"staffed first.  Drag cards in the Edit Hierarchy overlay"` | guide_text |
| 105 | `"to re-order priorities."` | guide_text |
| 107 | `"# Auto Mode"` | header |
| 108 | `"By default, worker assignment is automatic: all buildings"` | guide_text |
| 109 | `"share one tier, and logistics workers are allocated as"` | guide_text |
| 110 | `"1 per every 3 buildings.  Toggle Auto off to customise."` | guide_text |
| 112 | `"# Logistics Workers"` | header |
| 113 | `"Logistics workers carry resources between buildings."` | guide_text |
| 114 | `"Adjust the logistics count with +/- in the Workers tab."` | guide_text |
| 115 | `"More logistics workers means faster resource delivery."` | guide_text |
| 117 | `"# Demand & Supply Priority"` | header |
| 118 | `"The Demand tab controls which buildings receive resources"` | guide_text |
| 119 | `"first.  The Supply tab controls which buildings are drawn"` | guide_text |
| 120 | `"from first.  Both support Auto and Manual modes."` | guide_text |

### "Research & Tiers" Page (lines 123–141)

| Line | String | Category |
|------|--------|----------|
| 123 | `"# Research"` | header |
| 124 | `"Build a Research Center and select a technology to"` | guide_text |
| 125 | `"research.  Research consumes resources over time."` | guide_text |
| 126 | `"Completed research unlocks new buildings and recipes."` | guide_text |
| 128 | `"# Tech Tree"` | header |
| 129 | `"Open the tech tree from the Research Center's info"` | guide_text |
| 130 | `"panel to see all available and locked technologies."` | guide_text |
| 131 | `"Some techs require prerequisites to be researched first."` | guide_text |
| 133 | `"# Tiers"` | header |
| 134 | `"The colony progresses through tiers as you meet"` | guide_text |
| 135 | `"requirements (population, buildings, resources, research)."` | guide_text |
| 136 | `"Each tier may unlock new building types."` | guide_text |
| 138 | `"Tier 0: Crash Site — starting buildings."` | guide_text |
| 139 | `"Tier 1: Foothold — 8 pop, 6 buildings."` | guide_text |
| 140 | `"Tier 2: Settlement — 15 pop, 100 Food, 1 research."` | guide_text |
| 141 | `"Tier 3: Colony — 25 pop, 50 Iron, 25 Copper, 3 research."` | guide_text |

### "Controls" Page (lines 144–162)

| Line | String | Category |
|------|--------|----------|
| 144 | `"# Camera"` | header |
| 145 | `"• WASD / Arrow keys — pan the camera."` | guide_text |
| 146 | `"• Scroll wheel — zoom in / out."` | guide_text |
| 147 | `"• Middle click + drag — pan the camera."` | guide_text |
| 149 | `"# Building"` | header |
| 150 | `"• Left click — select tile / place building."` | guide_text |
| 151 | `"• Right click — cancel build / deselect."` | guide_text |
| 152 | `"• B — cycle build mode."` | guide_text |
| 153 | `"• X — toggle delete mode."` | guide_text |
| 155 | `"# Interface"` | header |
| 156 | `"• I — toggle this info guide."` | guide_text |
| 157 | `"• H — toggle quick controls reference."` | guide_text |
| 158 | `"• 1 / 2 / 3 — set game speed."` | guide_text |
| 159 | `"• Tab — toggle sandbox mode."` | guide_text |
| 160 | `"• Alt (hold) — show resource overlay."` | guide_text |
| 161 | `"• Escape — pause menu."` | guide_text |
| 162 | `"• F1 — toggle god mode."` | guide_text |

### Other Strings

| Line | String | Category |
|------|--------|----------|
| ~210 | `"Game Guide"` | header |
| ~268 | `"Press I or Escape to close"` | hint |

---

## ui_building_info.py

### _BUILDING_LABEL Dict (lines 69–86)

| Line | Key | String | Category |
|------|-----|--------|----------|
| 70 | CAMP | `"Ship Wreckage"` | label |
| 71 | HABITAT | `"Habitat"` | label |
| 72 | PATH | `"Path"` | label |
| 73 | BRIDGE | `"Bridge"` | label |
| 74 | WALL | `"Wall"` | label |
| 75 | WOODCUTTER | `"Woodcutter"` | label |
| 76 | QUARRY | `"Quarry"` | label |
| 77 | GATHERER | `"Gatherer"` | label |
| 78 | STORAGE | `"Storage"` | label |
| 79 | REFINERY | `"Refinery"` | label |
| 80 | MINING_MACHINE | `"Mining Machine"` | label |
| 81 | FARM | `"Farm"` | label |
| 82 | WELL | `"Well"` | label |
| 83 | WORKSHOP | `"Workshop"` | label |
| 84 | FORGE | `"Forge"` | label |
| 85 | ASSEMBLER | `"Assembler"` | label |
| 86 | RESEARCH_CENTER | `"Research Center"` | label |

### Dynamic Strings in _build_items (lines ~500+)

| Line(s) | String / Template | Category |
|---------|-------------------|----------|
| ~509 | `f"Residents: ({cap}+{b.residents - cap})/{cap}"` | label |
| ~511 | `f"Residents: {b.residents}/{cap}"` | label |
| ~517 | `f"Population: {pop}/{total_housing}"` | label |
| ~519 | `f"Homeless: {homeless}"` | label |
| ~525 | `f"Workers: {b.workers}/{b.max_workers}"` | label |
| ~530 | `f"Output: {int(output_held)}/{b.storage_capacity}"` | label |
| ~535 | `"Inputs:"` | label |
| ~536 | `"Outputs:"` | label |
| ~537 | `"Other:"` | label |
| ~540 | `f"Storage: {int(b.stored_total)}/{b.storage_capacity}"` | label |
| ~545 | `f"Stores: {name}"` or `"(none selected)"` | label |
| ~550 | `f"Gathers: {label}"` | label |
| ~555 | `f"Mining: {label}"` | label |
| ~560 | `"Stone (default)"` | label |
| ~565 | `"Both (Food & Fiber)"` | label |
| ~570 | `f"Crafting: {recipe_name}"` | label |
| ~575 | `f"Progress: {pct}%"` | label |
| ~580 | `"Select recipe:"` | label |
| ~585 | `"Select recipe..."` | label |
| ~590 | `"Materials:"` | label |
| ~425 | `"≡ Open Tech Tree"` | button_text |
| ~430 | `f"Tier {cur}: {info.name}"` | label |
| ~435 | `f"Unlocked: {names}"` | label |
| ~440 | `f"Next → Tier {cur + 1}: {nxt.name}"` | label |
| ~445 | `"(Max tier reached)"` | label |

---

## ui_bottom_bar.py

### Category Tab Labels — `_CATEGORIES` (lines ~141–155)

| Line | String | Category |
|------|--------|----------|
| ~141 | `"Core"` | tab_label |
| ~142 | `"Housing"` | tab_label |
| ~143 | `"Resource"` | tab_label |
| ~144 | `"Processing"` | tab_label |
| ~155 | `"Logistics"` | tab_label |

### Building Descriptions — `_DESC` Dict (lines ~189–204)

| Line | Key | String | Category |
|------|-----|--------|----------|
| ~189 | HABITAT | `"Houses 6 survivors"` | description |
| ~190 | PATH | `"Connects buildings"` | description |
| ~191 | BRIDGE | `"Path over water"` | description |
| ~192 | WOODCUTTER | `"Harvests wood"` | description |
| ~193 | QUARRY | `"Harvests stone"` | description |
| ~194 | GATHERER | `"Gathers fiber & food"` | description |
| ~195 | STORAGE | `"Stores 100 resources"` | description |
| ~196 | REFINERY | `"Processes metals"` | description |
| ~197 | MINING_MACHINE | `"Auto-mines ore (uses fuel)"` | description |
| ~198 | FARM | `"Grows food"` | description |
| ~199 | WELL | `"Boosts nearby farms"` | description |
| ~200 | WALL | `"Defensive wall"` | description |
| ~201 | WORKSHOP | `"Crafts buildings"` | description |
| ~202 | FORGE | `"Smelts metal bars"` | description |
| ~203 | ASSEMBLER | `"Builds advanced parts"` | description |
| ~204 | RESEARCH_CENTER | `"Unlocks tech tree"` | description |

### Building Labels — `_LABEL` Dict (lines ~206–222)

| Line | Key | String | Category |
|------|-----|--------|----------|
| ~207 | HABITAT | `"Habitat"` | label |
| ~208 | PATH | `"Path"` | label |
| ~209 | BRIDGE | `"Bridge"` | label |
| ~210 | WALL | `"Wall"` | label |
| ~211 | WOODCUTTER | `"Woodcutter"` | label |
| ~212 | QUARRY | `"Quarry"` | label |
| ~213 | GATHERER | `"Gatherer"` | label |
| ~214 | STORAGE | `"Storage"` | label |
| ~215 | REFINERY | `"Refinery"` | label |
| ~216 | MINING_MACHINE | `"Mining Machine"` | label |
| ~217 | FARM | `"Farm"` | label |
| ~218 | WELL | `"Well"` | label |
| ~219 | WORKSHOP | `"Workshop"` | label |
| ~220 | FORGE | `"Forge"` | label |
| ~221 | ASSEMBLER | `"Assembler"` | label |
| ~222 | RESEARCH_CENTER | `"Research"` | label |

### Other Strings

| Line | String | Category |
|------|--------|----------|
| ~441 | `"Delete"` | label |
| ~445 | `"Returns to inventory"` | hint |
| ~410 | `"∞"` | label |
| ~415 | `f"x{stock}"` | label |
| ~556 | `"Colony age"` | label |
| ~557 | `"Population"` | label |
| ~558 | `"Buildings"` | label |
| ~591 | `"Buildings"` | tab_label |

---

## ui_resource_bar.py

| Line | String | Category |
|------|--------|----------|
| ~107 | `"−"` (U+2212 minus) | button_text |
| ~115 | `"+"` | button_text |
| ~130 | `f"Tier {lvl}: {tier_name}"` | label |
| ~137 | `"(Max Tier)"` | label |
| ~143 | `"→"` | other |
| ~155 | `"…"` | other |
| ~173 | `"DELETE [X]"` | label |
| ~178 | `"SANDBOX"` | label |
| ~183 | `f"{self.sim_speed:.0f}x"` | label |
| ~191 | `f"≡ {node.name}: {pct}%"` | label |
| (dynamic) | `f"{pop}/{housing}"` | label |

---

## ui_pause_menu.py

### _PAUSE_LABELS (line 40)

| Line | String | Category |
|------|--------|----------|
| 40 | `"Resume"` | button_text |
| 40 | `"Options"` | button_text |
| 40 | `"Return to Main Menu"` | button_text |
| 40 | `"Quit"` | button_text |

### Other Strings

| Line | String | Category |
|------|--------|----------|
| ~107 | `"Paused"` | header |
| ~120 | `"Options"` | header |
| ~128 | `"Graphics Quality"` | label |
| (dynamic) | `"High"` / `"Medium"` / `"Low"` | button_text |
| ~44 | `"Full gradients, overlays, and contours"` | description |
| ~45 | `"Blended colors, overlays, no triangle gradients"` | description |
| ~46 | `"Flat tile colors and buildings only"` | description |
| ~148 | `"Music Volume"` | label |
| ~148 | `"Sound Effects"` | label |
| ~150 | `"—"` (em dash) | label |
| ~157 | `"Back"` | button_text |

---

## ui_game_over.py

| Line | String | Category |
|------|--------|----------|
| ~74 | `"All Survivors Lost"` | header |
| ~79 | `f"Survived {mins}:{secs:02d}   \|   Buildings: {len(world.buildings.buildings)}"` | label |
| 33 | `"Return to Main Menu"` | button_text |
| 33 | `"Quit"` | button_text |

---

## ui_tier_popup.py

### _BUILDING_LABEL Dict (lines 31–47)

Same 17 building labels as `ui_building_info.py` `_BUILDING_LABEL`.

### Dynamic Strings

| Line | String | Category |
|------|--------|----------|
| ~134 | `f"Tier {cur.level}: {cur.name}"` | header |
| (dynamic) | `cur.description` (from params TIER_DATA) | description |
| ~143 | `"Unlocked Buildings:"` | header |
| ~145 | `f"  • {name}"` | label |
| ~149 | `"No new buildings unlocked."` | label |
| ~155 | `f"Next: Tier {nxt.level} — {nxt.name}"` | header |
| (dynamic) | `nxt.description` | description |
| ~165 | `f"  • Population: {reqs['population']}"` | label |
| ~167 | `f"  • Buildings: {reqs['buildings_placed']}"` | label |
| ~170 | `f"  • {res_name}: {amount}"` | label |
| ~175 | `f"  • Research completed: {reqs['research_count']}"` | label |
| ~181 | `"Maximum tier reached!"` | label |
| ~187 | `"Click anywhere or press Escape to continue"` | hint |

---

## ui_help.py

### _HELP_LINES (lines 27–40)

| Line | Key | Description | Category |
|------|-----|-------------|----------|
| 27 | `"WASD / Arrows"` | `"Pan camera"` | label |
| 28 | `"Scroll wheel"` | `"Zoom in / out"` | label |
| 29 | `"Left click"` | `"Select tile / place building"` | label |
| 30 | `"Right click"` | `"Cancel build / deselect / pan"` | label |
| 31 | `"Middle click"` | `"Pan camera"` | label |
| 32 | `"B"` | `"Cycle build mode"` | label |
| 33 | `"X"` | `"Toggle delete mode"` | label |
| 34 | `"H"` | `"Toggle this help overlay"` | label |
| 35 | `"I"` | `"Toggle game guide"` | label |
| 36 | `"1 / 2 / 3"` | `"Set game speed"` | label |
| 37 | `"Tab"` | `"Toggle sandbox mode"` | label |
| 38 | `"Alt (hold)"` | `"Show resource overlay"` | label |
| 39 | `"Escape"` | `"Pause menu"` | label |

### Other Strings

| Line | String | Category |
|------|--------|----------|
| ~78 | `"Controls"` | header |
| ~94 | `"Press H or ESC to close"` | hint |

---

## ui_tile_info.py

### _TERRAIN_LABEL Dict (lines 47–56)

| Line | Key | String | Category |
|------|-----|--------|----------|
| 47 | GRASS | `"Grassland"` | label |
| 48 | FOREST | `"Forest"` | label |
| 49 | DENSE_FOREST | `"Dense Forest"` | label |
| 50 | STONE_DEPOSIT | `"Stone Deposit"` | label |
| 51 | WATER | `"Water"` | label |
| 52 | FIBER_PATCH | `"Fiber Patch"` | label |
| 53 | MOUNTAIN | `"Mountain"` | label |
| 54 | IRON_VEIN | `"Iron Vein"` | label |
| 55 | COPPER_VEIN | `"Copper Vein"` | label |

### _TERRAIN_DESC Dict (lines 58–67)

| Line | Key | String | Category |
|------|-----|--------|----------|
| 58 | GRASS | `"Open terrain, good for building."` | description |
| 59 | FOREST | `"Trees provide wood."` | description |
| 60 | DENSE_FOREST | `"Thick forest, rich in wood."` | description |
| 61 | STONE_DEPOSIT | `"Rocky outcrop, yields stone."` | description |
| 62 | WATER | `"Impassable body of water."` | description |
| 63 | FIBER_PATCH | `"Wild fibers and berries."` | description |
| 64 | MOUNTAIN | `"Impassable mountain peak."` | description |
| 65 | IRON_VEIN | `"Iron ore deposits."` | description |
| 66 | COPPER_VEIN | `"Copper ore deposits."` | description |

### Other Strings

| Line | String | Category |
|------|--------|----------|
| (dynamic) | `"Resource:"` | label |
| (dynamic) | `"  Depleted"` | label |
| (dynamic) | `"No harvestable resource"` | label |
| (dynamic) | `"  Food"` | label |
| (dynamic) | `f"  Remaining: {amount}"` | label |
| (dynamic) | `"Ancient Ruin"` | label |
| (dynamic) | `"A remnant of old Earth. Maybe something can be salvaged..."` | description |
| (dynamic) | `"Impassable"` | label |
| (dynamic) | `"Passable"` | label |
| (dynamic) | `f"Coords: ({self.coord.q}, {self.coord.r})"` | label |

---

## ui_stats.py

### Stats Card Labels (lines ~106–113)

| Line | String | Category |
|------|--------|----------|
| ~106 | `"Tier"` | label |
| ~107 | `"Population"` | label |
| ~108 | `"Buildings"` | label |
| ~109 | `"Idle workers"` | label |
| ~110 | `"Research"` | label |
| ~111 | `"Raw stock"` | label |
| ~112 | `"Processed"` | label |
| ~113 | `"Time"` | label |

### Button Text

| Line | String | Category |
|------|--------|----------|
| ~132 | `"Advanced"` | button_text |
| ~133 | `"Statistics"` | button_text |

---

## ui_tech_tree.py

| Line | String | Category |
|------|--------|----------|
| ~89 | `"Technology Tree"` | header |
| ~100 | `f"Researching: {node.name} ({pct}%)"` | label |
| ~130 | `"Researched"` | label |
| ~132 | `f"In Progress ({pct}%)"` | label |
| ~135 | `"Available"` | label |
| ~140 | `"Locked"` | label |
| ~170 | `f"{node.time:.0f}s"` | label |
| ~177 | `"Unlocks:"` | label |
| ~196 | `"Scroll wheel or middle-drag to pan"` | hint |
| ~364 | `f"{name} — Free"` | tooltip |
| ~364 | `f"{name} — {cost parts}"` | tooltip |

---

## ui_tutorial.py

### Tutorial Steps (lines ~58–192)

#### Step "welcome"

| Line | String | Category |
|------|--------|----------|
| ~60 | `"Welcome to Hex Colony!"` | header |
| ~62 | `"You've crash-landed on an alien world."` | guide_text |
| ~63 | `"Your crew needs Food to survive — without it"` | guide_text |
| ~64 | `"your colonists will starve!"` | guide_text |
| ~66 | `"Let's get started by setting up food production."` | guide_text |

#### Step "build_gatherer"

| Line | String | Category |
|------|--------|----------|
| ~70 | `"Build a Gatherer"` | header |
| ~72 | `"Open the Buildings tab at the bottom of the"` | guide_text |
| ~73 | `"screen and select \u201cGatherer\u201d."` | guide_text |
| ~75 | `"Place it on a grass/plains tile near your Camp."` | guide_text |
| ~76 | `"Gatherers harvest Food from surrounding tiles."` | guide_text |

#### Step "connect_paths"

| Line | String | Category |
|------|--------|----------|
| ~80 | `"Connect with Paths"` | header |
| ~82 | `"Your Gatherer needs a path connection to the"` | guide_text |
| ~83 | `"Camp so workers can reach it."` | guide_text |
| ~85 | `"Select \u201cPath\u201d from Buildings, click near the"` | guide_text |
| ~86 | `"Camp, then click near the Gatherer to lay a"` | guide_text |
| ~87 | `"route automatically."` | guide_text |

#### Step "food_producing"

| Line | String | Category |
|------|--------|----------|
| ~91 | `"Food Production Started!"` | header |
| ~93 | `"Great! Workers are now gathering Food."` | guide_text |
| ~94 | `"Click on the Gatherer to see its info panel."` | guide_text |
| ~95 | `"It defaults to Food — you can switch to Fiber"` | guide_text |
| ~96 | `"later if you need it for crafting."` | guide_text |
| ~98 | `"Keep an eye on the Food counter in the top bar."` | guide_text |

#### Step "build_woodcutter"

| Line | String | Category |
|------|--------|----------|
| ~102 | `"Gather More Resources"` | header |
| ~104 | `"You'll need Wood and Stone to build more."` | guide_text |
| ~106 | `"Place a Woodcutter on a forest tile and a"` | guide_text |
| ~107 | `"Quarry on a mountain tile, then connect them"` | guide_text |
| ~108 | `"with Paths."` | guide_text |

#### Step "build_habitat"

| Line | String | Category |
|------|--------|----------|
| ~112 | `"Build a Habitat"` | header |
| ~114 | `"Your Camp can only house a few colonists."` | guide_text |
| ~115 | `"Build a Habitat to provide more housing —"` | guide_text |
| ~116 | `"colonists will reproduce when they have food"` | guide_text |
| ~117 | `"and a home with room."` | guide_text |
| ~119 | `"More people means more workers!"` | guide_text |

#### Step "workshop_crafting"

| Line | String | Category |
|------|--------|----------|
| ~123 | `"Workshop Crafting"` | header |
| ~125 | `"Your Workshop can craft materials and buildings."` | guide_text |
| ~127 | `"Click on the Workshop, then select a recipe"` | guide_text |
| ~128 | `"from the dropdown menu. Workers will craft it"` | guide_text |
| ~129 | `"using resources from your global inventory."` | guide_text |

#### Step "forge_smelting"

| Line | String | Category |
|------|--------|----------|
| ~133 | `"Forge — Smelt Ores"` | header |
| ~135 | `"The Forge smelts raw Iron and Copper into bars."` | guide_text |
| ~137 | `"Click on the Forge and pick a material recipe"` | guide_text |
| ~138 | `"to start smelting. You'll need bars to craft"` | guide_text |
| ~139 | `"advanced buildings and components."` | guide_text |

#### Step "research"

| Line | String | Category |
|------|--------|----------|
| ~143 | `"Research New Tech"` | header |
| ~145 | `"Your Research Center can unlock new buildings"` | guide_text |
| ~146 | `"and recipes."` | guide_text |
| ~148 | `"Click on it and select a technology to research."` | guide_text |
| ~149 | `"Research consumes resources over time. Open the"` | guide_text |
| ~150 | `"Tech Tree to see what's available."` | guide_text |

#### Step "population_growing"

| Line | String | Category |
|------|--------|----------|
| ~154 | `"Population Growing!"` | header |
| ~156 | `"Your colony is expanding. More colonists means"` | guide_text |
| ~157 | `"you can staff more buildings."` | guide_text |
| ~159 | `"Check the Workers tab to see how workers are"` | guide_text |
| ~160 | `"assigned. Logistics workers move resources"` | guide_text |
| ~161 | `"between buildings automatically."` | guide_text |

### Other Tutorial Strings

| Line | String | Category |
|------|--------|----------|
| ~331 | `"Got it"` | button_text |
| ~337 | `f"{done + 1} / {total}"` | label |

---

## ui_worker_priority.py

| Line | String | Category |
|------|--------|----------|
| ~191 | `"Edit Hierarchy"` | button_text |
| ~215 | `"Auto"` | button_text |
| ~230 | `"No worker buildings placed yet."` | label |
| ~240 | `f"Logistics: {active}/{selected.logistics_target}"` | label |
| ~248 | `f"Tier {ti + 1}"` | label |
| ~321 | `"Drop here to create a new tier"` | hint |
| ~392 | `"Edit Worker Priority"` | header |
| ~397 | `"Auto mode active — disable Auto to customise."` | hint |
| ~399 | `"Drag cards between tiers.  Higher tier = higher priority."` | hint |
| ~414 | `"Done"` | button_text |
| ~455 | `f"Tier {tier_idx + 1}"` | label |
| ~478 | `"Logistics"` | label |
| ~610 | `f"{active}/{net.logistics_target}"` | label |
| ~636 | `"-"` | button_text |
| ~636 | `"+"` | button_text |
| (dynamic) | `n.name` → `f"Network {self.id}"` | tab_label |

---

## ui_advanced_stats.py

### Time Window Labels — `_WINDOWS` (lines ~220–224)

| Line | String | Category |
|------|--------|----------|
| ~221 | `"30s"` | button_text |
| ~222 | `"2m"` | button_text |
| ~223 | `"5m"` | button_text |
| ~224 | `"10m"` | button_text |

### Mode Labels (lines ~390–396)

| Line | String | Category |
|------|--------|----------|
| ~391 | `"Stockpile"` | button_text |
| ~392 | `"Prod /s"` | button_text |
| ~393 | `"Cons /s"` | button_text |
| ~394 | `"Total Prod"` | button_text |
| ~395 | `"Total Cons"` | button_text |

### _mode_label() Return Values (lines ~370–377)

| Line | String | Category |
|------|--------|----------|
| ~371 | `"Stockpile"` | label |
| ~372 | `"Production /s"` | label |
| ~373 | `"Consumption /s"` | label |
| ~374 | `"Total Produced"` | label |
| ~375 | `"Total Consumed"` | label |

### Other Strings

| Line | String | Category |
|------|--------|----------|
| ~400 | `"Advanced Statistics"` | header |
| ~420 | `"Time window:"` | label |
| ~450 | `"Stat:"` | label |
| ~480 | `"Resources"` | header |
| ~530 | `"Select one or more resources on the left"` | hint |
| ~630 | `"now"` | label |
| ~633 | `f"-{_fmt_window_secs(window_s)}"` (e.g. `"-30s"`, `"-2m"`) | label |

### Summary Row Labels (lines ~725–735)

| Line | String | Category |
|------|--------|----------|
| ~728 | `"Population"` | label |
| ~729 | `"Pop/min"` | label |
| ~730 | `"Prod/s"` | label |
| ~731 | `"Time"` | label |
| ~732 | `"Window"` | label |

### Legend Text (dynamic, lines ~660–700)

| Line | Template | Category |
|------|----------|----------|
| ~665 | `f"{res.name.replace('_', ' ').title()}  {net:+.2f}/s"` | label |
| ~671 | `f"{res.name.replace('_', ' ').title()}  {cur:.2f}/s"` | label |
| ~677 | `f"{res.name.replace('_', ' ').title()}  {cur:.2f}/s"` | label |
| ~683 | `f"{res.name.replace('_', ' ').title()}  {tot:.0f}"` | label |
| ~689 | `f"{res.name.replace('_', ' ').title()}  {tot:.0f}"` | label |

---

## ui_demand_priority.py

### PrioritySpec Strings (lines ~35–48)

| Line | String | Category |
|------|--------|----------|
| ~38 | `"Edit Resource Demand"` | header |
| ~39 | `"Edit Demand"` | button_text |
| ~40 | `"No buildings demand resources yet."` | label |

---

## ui_supply_priority.py

### PrioritySpec Strings (lines ~35–48)

| Line | String | Category |
|------|--------|----------|
| ~38 | `"Edit Resource Supply"` | header |
| ~39 | `"Edit Supply"` | button_text |
| ~40 | `"No buildings supply resources yet."` | label |

---

## ui_priority_common.py

### Shared Labels/Buttons

| Line | String | Category |
|------|--------|----------|
| ~175 | `"Auto"` | button_text |
| ~245 | `"Filter: All"` | label |
| ~246 | `f"Filter: {self._filter_resource.name.title()}"` | label |
| ~273 | `f"Tier {ti + 1}"` | label |
| ~410 | `"All resources"` | label |
| ~500 | `"Drop here to create a new tier"` | hint |
| ~540 | `"Done"` | button_text |
| ~555 | `"Auto: ON"` | label |
| ~556 | `"Auto: OFF"` | label |
| ~570 | `"Filter: All"` | label |
| ~571 | `f"Filter: {self._filter_resource.name.title()}"` | label |

---

## tech_tree.py

### TierTracker.check_requirements Labels (lines ~327–344)

| Line | String | Category |
|------|--------|----------|
| ~331 | `"Population"` | label |
| ~337 | `"Buildings"` | label |
| ~342 | `res_name.capitalize()` (e.g. `"Food"`, `"Iron"`, `"Copper"`) | label |
| ~344 | `"Research"` | label |

---

## world.py

| Line | String | Category |
|------|--------|----------|
| (dynamic) | `f"Network {self.id}"` (Network.name property) | label |

---

## upgrades.py

### Upgrade Level Names

| Line | Building | String | Category |
|------|----------|--------|----------|
| ~50 | Woodcutter L0 | `"Woodcutter"` | label |
| ~52 | Woodcutter L1 | `"Improved Woodcutter"` | label |
| ~58 | Woodcutter L2 | `"Advanced Woodcutter"` | label |
| ~66 | Quarry L0 | `"Quarry"` | label |
| ~68 | Quarry L1 | `"Improved Quarry"` | label |
| ~74 | Quarry L2 | `"Advanced Quarry"` | label |
| ~82 | Gatherer L0 | `"Gatherer"` | label |
| ~84 | Gatherer L1 | `"Improved Gatherer"` | label |
| ~90 | Habitat L0 | `"Habitat"` | label |
| ~92 | Habitat L1 | `"Expanded Habitat"` | label |
| ~98 | Storage L0 | `"Storage"` | label |
| ~100 | Storage L1 | `"Large Storage"` | label |
| ~106 | Refinery L0 | `"Refinery"` | label |
| ~108 | Refinery L1 | `"Advanced Refinery"` | label |
| ~116 | Farm L0 | `"Farm"` | label |
| ~118 | Farm L1 | `"Irrigated Farm"` | label |
| ~126 | Wall L0 | `"Wall"` | label |
| ~128 | Wall L1 | `"Reinforced Wall"` | label |

---

## Files with NO User-Facing Strings

The following files were checked and contain **no hardcoded user-facing text**:

- **buildings.py** — data structures, enums, cost dicts only
- **camera.py** — camera math only
- **hex_grid.py** — coordinate math only
- **people.py** — people simulation logic only
- **settings.py** — settings dataclass only
- **notifications.py** — notification framework (no hardcoded messages)
- **overlay.py** — terrain overlay rendering only
- **procgen.py** — procedural terrain generation only
- **render_terrain.py** — rendering only
- **render_buildings.py** — rendering only
- **render_overlays.py** — rendering only
- **render_utils.py** — rendering constants/helpers only
- **renderer.py** — rendering orchestration only
- **sprites.py** — sprite loading only
- **generate_sprites.py** — sprite generation only
- **factions.py** — faction enum/data only
- **blueprints.py** — blueprint data only
- **supply_chain.py** — supply chain visualization only (no text rendered)
- **resource_icons.py** — procedural icon drawing only
- **ui_theme.py** — color/font constants, drawing primitives only
- **ui_minimap.py** — minimap rendering only (no text rendered)

---

## Summary

| File | Approx. String Count |
|------|---------------------|
| ui_info_guide.py | ~85 |
| ui_tutorial.py | ~55 |
| ui_building_info.py | ~35 |
| ui_bottom_bar.py | ~40 |
| ui_tile_info.py | ~25 |
| ui_advanced_stats.py | ~30 |
| params.py | ~22 |
| upgrades.py | ~18 |
| resources.py | ~18 |
| ui.py | ~18 |
| ui_worker_priority.py | ~16 |
| ui_help.py | ~15 |
| ui_tier_popup.py | ~15 |
| ui_pause_menu.py | ~14 |
| ui_priority_common.py | ~12 |
| ui_tech_tree.py | ~11 |
| ui_resource_bar.py | ~10 |
| ui_stats.py | ~10 |
| game.py | ~12 |
| menu.py | ~7 |
| ui_game_over.py | ~4 |
| tech_tree.py | ~4 |
| ui_demand_priority.py | ~3 |
| ui_supply_priority.py | ~3 |
| world.py | ~1 |
| **TOTAL** | **~500+** |
