# Hex Colony — Complete User-Facing Text Strings Report

Every hardcoded user-facing string in the hex_colony codebase, organized by category.
Format: **File** `→` line(s) `→` string(s).

---

## 1. Game Registration / Home Screen

| File | Line | String |
|------|------|--------|
| `games/hex_colony/__init__.py` | 39 | `"Hex Colony"` (game name) |
| `games/hex_colony/__init__.py` | 40 | `"Survive on a re-evolved Earth after your spaceship crash-lands"` (game description) |
| `home_screen.py` | 107 | `"Select a Game"` (title) |
| `home_screen.py` | 140 | `"Click a game to play  •  ESC to quit"` (hint) |

---

## 2. Game Menu (menu.py)

| File | Line | String |
|------|------|--------|
| `menu.py` | ~175 | `"Hex Colony"` (title font render) |
| `menu.py` | ~178 | `"Survive on a re-evolved Earth"` (subtitle) |
| `menu.py` | ~188 | `"World Seed"` (label) |
| `menu.py` | ~215 | `"Leave blank for random seed"` (placeholder hint) |
| `menu.py` | ~219 | `"Map Size"` (slider label) |
| `menu.py` | ~240 | `"Play"` (button) |
| `menu.py` | ~244 | `"Enter seed  •  ENTER or click Play  •  ESC to go back"` (bottom hint) |

---

## 3. Tutorial (ui_tutorial.py)

TUTORIAL_STEPS list (lines 60-186), 10 steps. Each has `id`, `title`, and `lines[]`:

| Step | Title | Lines (summary) |
|------|-------|-----------------|
| 0 | `"Welcome to Hex Colony!"` | 5 lines: intro about crash-landing, building, resources |
| 1 | `"Build a Gatherer"` | 5 lines: click buildings tab, select Gatherer, place near berries |
| 2 | `"Connect with Paths"` | 5 lines: paths connect buildings, workers walk on them |
| 3 | `"Food Production Started!"` | 5 lines: workers automatically gather, logistics deliver |
| 4 | `"Gather More Resources"` | 6 lines: build Woodcutter/Quarry near resources |
| 5 | `"Build a Habitat"` | 5 lines: housing for population, connect to camp |
| 6 | `"Workshop Crafting"` | 6 lines: Workshop converts raw → processed goods |
| 7 | `"Forge — Smelt Ores"` | 5 lines: Forge smelts ores into bars |
| 8 | `"Research New Tech"` | 6 lines: Research Center unlocks new buildings |
| 9 | `"Population Growing!"` | 5 lines: reproduce, advance tiers, experiment |

**All line text is in the `lines` list inside each step dict — needs full extraction from L60-186.**

---

## 4. Game Guide (ui_info_guide.py)

| File | Line | String |
|------|------|--------|
| `ui_info_guide.py` | 167 | `"Game Guide"` (title) |
| `ui_info_guide.py` | 222 | `"Press I or Escape to close"` |

`_PAGES` (lines 33-145) — 6 pages with ~106 total lines of text:

| Page | Title |
|------|-------|
| 0 | `"Getting Started"` |
| 1 | `"Buildings"` |
| 2 | `"Resources & Crafting"` |
| 3 | `"Workers & Logistics"` |
| 4 | `"Research & Tiers"` |
| 5 | `"Controls"` |

Each page has a list of descriptive text lines (see L33-145 for full content).

---

## 5. Help / Controls (ui_help.py)

| File | Line | String |
|------|------|--------|
| `ui_help.py` | 82 | `"Controls"` (panel title) |
| `ui_help.py` | 101 | `"Press H or ESC to close"` |

`_HELP_LINES` (L34-47), 13 key-binding tuples:

| Key | Description |
|-----|-------------|
| `"LMB"` | `"Select / Place building"` |
| `"RMB"` | `"Cancel placement"` |
| `"WASD / Arrows"` | `"Pan camera"` |
| `"Scroll"` | `"Zoom in / out"` |
| `"MMB drag"` | `"Pan camera"` |
| `"B"` | `"Buildings tab"` |
| `"H"` | `"Toggle this help"` |
| `"I"` | `"Game guide"` |
| `"T"` | `"Tech tree"` |
| `"ESC"` | `"Pause / close overlay"` |
| `"1 / 2 / 3"` | `"Simulation speed"` |
| `"Tab"` | `"Toggle stats"` |
| `"Alt"` | `"Hold for resource overlay"` |

---

## 6. Building Labels & Descriptions

### 6a. Building Labels (ui_building_info.py L69-86, `_BUILDING_LABEL`)

| BuildingType | Label |
|--------------|-------|
| CAMP | `"Ship Wreckage"` |
| HABITAT | `"Habitat"` |
| WOODCUTTER | `"Woodcutter"` |
| QUARRY | `"Quarry"` |
| GATHERER | `"Gatherer"` |
| STORAGE | `"Storage"` |
| REFINERY | `"Refinery"` |
| MINING_MACHINE | `"Mining Machine"` |
| FARM | `"Farm"` |
| WELL | `"Well"` |
| PATH | `"Path"` |
| BRIDGE | `"Bridge"` |
| WALL | `"Wall"` |
| WORKSHOP | `"Workshop"` |
| FORGE | `"Forge"` |
| ASSEMBLER | `"Assembler"` |
| RESEARCH_CENTER | `"Research Center"` |

### 6b. Building Labels (ui_bottom_bar.py L196-211, `_LABEL`)

Same 16 entries (excludes CAMP) — duplicate of above minus CAMP.

### 6c. Building Labels (ui_tier_popup.py L33-49, `_BUILDING_LABEL`)

Same 17 entries — duplicate of ui_building_info.py's `_BUILDING_LABEL`.

### 6d. Building Short Descriptions (ui_bottom_bar.py L178-193, `_DESC`)

| BuildingType | Description |
|--------------|-------------|
| HABITAT | `"Housing for colonists"` |
| WOODCUTTER | `"Harvests wood from forests"` |
| QUARRY | `"Mines stone from deposits"` |
| GATHERER | `"Gathers food or fiber"` |
| STORAGE | `"Extra resource storage"` |
| REFINERY | `"Smelts ore into bars"` |
| MINING_MACHINE | `"Auto-mines nearby ores"` |
| FARM | `"Grows food on any terrain"` |
| WELL | `"Boosts adjacent farms"` |
| PATH | `"Connects buildings"` |
| BRIDGE | `"Path over water"` |
| WALL | `"Defensive barrier"` |
| WORKSHOP | `"Crafts processed goods"` |
| FORGE | `"Smelts ores into bars"` |
| ASSEMBLER | `"Advanced crafting station"` |
| RESEARCH_CENTER | `"Unlocks new technology"` |

### 6e. Bottom Bar Category Labels (ui_bottom_bar.py L140-145, `_CATEGORIES`)

`["Core", "Housing", "Resource", "Processing", "Logistics"]`

### 6f. Delete Card (ui_bottom_bar.py L312-318)

| String | Context |
|--------|---------|
| `"Delete"` | card name |
| `"Returns to inventory"` | card description |

---

## 7. Building Info Panel (ui_building_info.py)

| File | Line | String | Context |
|------|------|--------|---------|
| `ui_building_info.py` | 384 | `"Both (Food & Fiber)"` | gatherer mode option |
| `ui_building_info.py` | 401 | `"Stone (default)"` | quarry mode option |
| `ui_building_info.py` | 458 | `"≡ Open Tech Tree"` | button |
| `ui_building_info.py` | 500-512 | `"Residents: {n}/{cap}"`, `"Population: {pop}"`, `"Homeless: {n}"` | camp/habitat stats |
| `ui_building_info.py` | 520 | `"Workers: {workers}/{max}"` | worker count |
| `ui_building_info.py` | 535-620 | `"Output:"`, `"Inputs:"`, `"Outputs:"`, `"Other:"` | storage section headers |
| `ui_building_info.py` | 645 | `"(none selected)"` | empty storage label |
| `ui_building_info.py` | 665 | `"Gathers: {label}"` | gatherer info |
| `ui_building_info.py` | 700 | `"Mining: {label}"` | mining machine info |
| `ui_building_info.py` | 730-770 | `"Crafting: {name}"`, `"Progress: {pct}%"`, `"Select recipe:"`, `"Select recipe..."`, `"Materials:"` | crafting info |
| `ui_building_info.py` | 830-845 | `"Tier {cur}: {name}"`, `"Unlocked: {names}"`, `"Next → Tier {cur+1}: {name}"`, `"(Max tier reached)"` | tier display |

**Dynamic name formatting**: `resource.name.replace("_", " ").title()` used for resource labels (L277 tooltip, and throughout).

---

## 8. Terrain Labels & Descriptions (ui_tile_info.py)

### 8a. Terrain Labels (L48-57, `_TERRAIN_LABEL`)

| Terrain | Label |
|---------|-------|
| GRASS | `"Grassland"` |
| FOREST | `"Forest"` |
| DENSE_FOREST | `"Dense Forest"` |
| STONE_DEPOSIT | `"Stone Deposit"` |
| WATER | `"Water"` |
| FIBER_PATCH | `"Fiber Patch"` |
| MOUNTAIN | `"Mountain"` |
| IRON_VEIN | `"Iron Vein"` |
| COPPER_VEIN | `"Copper Vein"` |

### 8b. Terrain Descriptions (L59-68, `_TERRAIN_DESC`)

| Terrain | Description |
|---------|-------------|
| GRASS | `"Open terrain — good for building"` |
| FOREST | `"Trees — harvestable for wood"` |
| DENSE_FOREST | `"Thick woodland — rich in wood"` |
| STONE_DEPOSIT | `"Rocky outcrop — source of stone"` |
| WATER | `"Deep water — impassable without bridges"` |
| FIBER_PATCH | `"Wild flax — source of plant fiber"` |
| MOUNTAIN | `"Rugged peaks — impassable, may contain ore"` |
| IRON_VEIN | `"Iron-rich rock — mine for iron ore"` |
| COPPER_VEIN | `"Copper deposits — mine for copper ore"` |

### 8c. Other Tile Info Strings (ui_tile_info.py)

| Line | String |
|------|--------|
| ~120 | `"Resource:"` + amount display |
| ~125 | `"Depleted"` |
| ~127 | `"No harvestable resource"` |
| ~130 | `"Food"` (berry patch resource label) |
| ~135 | `"Ancient Ruin"` + `"Remnants of a forgotten civilization"` (flavor text) |
| ~140 | `"Impassable"` / `"Passable"` |
| ~145 | `"Coords: ({q}, {r})"` |

---

## 9. Resource Bar (ui_resource_bar.py)

| Line | String |
|------|--------|
| ~50 | `"{pop}/{housing}"` (population display) |
| ~55 | `"DELETE [X]"` |
| ~60 | `"SANDBOX"` |
| ~65 | `"{speed}x"` (speed multiplier) |
| ~80 | `"Tier {lvl}: {name}"` |
| ~85 | `"(Max Tier)"` |
| ~90 | `"≡ {node.name}: {pct}%"` (active research display) |

---

## 10. Stats Panel (ui_stats.py)

Labels: `"Tier"`, `"Population"`, `"Buildings"`, `"Idle workers"`, `"Research"`, `"Raw stock"`, `"Processed"`, `"Time"`

Button toggle: `"Advanced"` / `"Statistics"`

---

## 11. Advanced Statistics (ui_advanced_stats.py)

| Line | String | Context |
|------|--------|---------|
| ~title | `"Advanced Statistics"` | panel title |
| ~30 | `_WINDOWS`: `"30s"`, `"2m"`, `"5m"`, `"10m"` | time window tabs |
| ~382-392 | Mode labels: `"Stockpile"`, `"Production /s"`, `"Consumption /s"`, `"Total Produced"`, `"Total Consumed"` | mode label map |
| ~440 | `"Time window:"` | section header |
| ~445 | `"Stat:"` | section header |
| ~510 | `"Resources"` | resource list header |
| ~585 | `"Select one or more resources on the left"` | empty graph hint |
| ~450 | Mode buttons: `"Stockpile"`, `"Prod /s"`, `"Cons /s"`, `"Total Prod"`, `"Total Cons"` | button labels |
| ~630 | `"now"` | x-axis label |
| ~632 | `"-{window}"` | x-axis label (formatted) |
| ~725-730 | Summary row: `"Population"`, `"Pop/min"`, `"Prod/s"`, `"Time"`, `"Window"` | aggregate stat labels |

**Dynamic**: Resource names via `res.name.replace("_", " ").title()`, rate labels like `"{net:+.2f}/s"`, `"{cur:.2f}/s"`, `"{tot:.0f}"`.

---

## 12. Tech Tree UI (ui_tech_tree.py)

| Line | String |
|------|--------|
| 86 | `"Technology Tree"` (panel title) |
| 100 | `"Researching: {node.name} ({pct}%)"` |
| 162-168 | Status labels: `"Researched"`, `"In Progress ({pct}%)"`, `"Available"`, `"Locked"` |
| 188 | `"{node.time:.0f}s"` (research time) |
| 195 | `"Unlocks:"` |
| 233 | `"Scroll wheel or middle-drag to pan"` (hint) |
| 288 | `"{name} — Free"` or `"{name} — {cost}"` (unlock tooltips) |

---

## 13. Tech Tree Data (params.py L431-530, `TECH_TREE_DATA`)

| Key | Name | Description |
|-----|------|-------------|
| `advanced_logistics` | `"Advanced Logistics"` | `"Unlock bridges for crossing water"` |
| `agriculture` | `"Agriculture"` | `"Cultivate crops for steady food supply"` |
| `metallurgy` | `"Metallurgy"` | `"Smelt raw ore into usable metal"` |
| `irrigation` | `"Irrigation"` | `"Wells boost adjacent farm output"` |
| `fortification` | `"Fortification"` | `"Advanced wall construction techniques"` |
| `advanced_smelting` | `"Advanced Smelting"` | `"Improved refinery efficiency"` |
| `exploration` | `"Exploration"` | `"Reveal more of the surrounding area"` |

---

## 14. Tier Data (params.py L371-420, `TIER_DATA`)

| Tier | Name | Description |
|------|------|-------------|
| 0 | `"Crash Site"` | `"Establish basic survival operations"` |
| 1 | `"Foothold"` | `"Secure basic resource production"` |
| 2 | `"Settlement"` | `"Begin processing raw materials"` |
| 3 | `"Colony"` | `"Establish a self-sustaining colony"` |

---

## 15. Tier Popup (ui_tier_popup.py)

| Line | String |
|------|--------|
| ~65 | `"Tier {level}: {name}"` (title) |
| ~70 | `"Unlocked Buildings:"` |
| ~75 | `"No new buildings unlocked."` |
| ~85 | `"Next: Tier {level} — {name}"` |
| ~95 | `"Maximum tier reached!"` |
| ~100 | `"Click anywhere or press Escape to continue"` |

Tier requirements (from tech_tree.py `check_requirements`): `"Population"`, `"Buildings"`, `"Research"`, and resource names.

---

## 16. Pause Menu (ui_pause_menu.py)

| Line | String |
|------|--------|
| 37 | `_PAUSE_LABELS`: `["Resume", "Options", "Return to Main Menu", "Quit"]` |
| 39-42 | `_QUALITY_DESC`: 3 quality descriptions (Low/Medium/High detail text) |
| 89 | `"Paused"` (title) |
| 109 | `"Options"` (options title) |
| 119 | `"Graphics Quality"` |
| 134 | `"Music Volume"` |
| 137 | `"Sound Effects"` |
| 141 | `"Back"` |

---

## 17. Game Over (ui_game_over.py)

| Line | String |
|------|--------|
| 37 | `_BUTTONS`: `["Return to Main Menu", "Quit"]` |
| 62 | `"All Survivors Lost"` (title) |
| 67 | `"Survived {m}:{s} | Buildings: {n}"` (stats line) |

---

## 18. Notifications (game.py & world.py)

| File | Line | String | Color |
|------|------|--------|-------|
| `game.py` | 234 | `"Research complete: {node.name}"` | green (100,255,100) |
| `game.py` | 339 | `"God mode ON"` / `"God mode OFF"` | gold / gray |
| `game.py` | 471 | `"Requires {node.name} research"` | orange (255,150,80) |
| `game.py` | 481 | `"Requires Tier {req_tier}: {tier_info.name}"` | orange (255,150,80) |
| `game.py` | 521 | `"Built {build_mode.name...title()}"` | default |
| `game.py` | 627 | `"Built {placed} {label}"` (`label` = "tile"/"tiles") | default |
| `world.py` | 1386 | `"A new colonist was born!"` | light green (180,255,180) |
| `world.py` | 1544 | `"No workers can reach {label}"` | red (230,100,100) |

---

## 19. Upgrade Names (upgrades.py)

| BuildingType | Level 0 | Level 1 | Level 2 |
|--------------|---------|---------|---------|
| WOODCUTTER | `"Woodcutter"` | `"Improved Woodcutter"` | `"Advanced Woodcutter"` |
| QUARRY | `"Quarry"` | `"Improved Quarry"` | `"Advanced Quarry"` |
| GATHERER | `"Gatherer"` | `"Improved Gatherer"` | — |
| HABITAT | `"Habitat"` | `"Expanded Habitat"` | — |
| STORAGE | `"Storage"` | `"Large Storage"` | — |
| REFINERY | `"Refinery"` | `"Advanced Refinery"` | — |
| FARM | `"Farm"` | `"Irrigated Farm"` | — |
| WALL | `"Wall"` | `"Reinforced Wall"` | — |

---

## 20. Worker Priority (ui_worker_priority.py)

| Line | String |
|------|--------|
| ~25 | `"Edit Hierarchy"` (button) |
| ~30 | `"Auto"` (button) |
| ~35 | `"No worker buildings placed yet."` (empty state) |
| ~40 | `"Logistics: {active}/{target}"` |
| ~45 | `"Tier {ti+1}"` (tier row label) |
| ~395 | `"Edit Worker Priority"` (overlay title) |
| ~403 | `"Auto mode active — disable Auto to customise."` / `"Drag cards between tiers.  Higher tier = higher priority."` (hint) |
| ~420 | `"Done"` (button) |
| ~460 | `"Logistics"` (row label) |
| ~338 | `"Drop here to create a new tier"` (_EMPTY_ROW_HINT) |

---

## 21. Demand & Supply Priority (ui_demand_priority.py, ui_supply_priority.py)

| File | String |
|------|--------|
| `ui_demand_priority.py` | `"Edit Resource Demand"` (overlay title) |
| `ui_demand_priority.py` | `"Edit Demand"` (button) |
| `ui_demand_priority.py` | `"No buildings demand resources yet."` |
| `ui_supply_priority.py` | `"Edit Resource Supply"` (overlay title) |
| `ui_supply_priority.py` | `"Edit Supply"` (button) |
| `ui_supply_priority.py` | `"No buildings supply resources yet."` |

---

## 22. Priority Common (ui_priority_common.py)

| Line | String |
|------|--------|
| various | `"Auto"` (button) |
| various | `"Filter: All"` / `"Filter: {resource}"` |
| various | `"Tier {ti+1}"` (row label) |
| various | `"All resources"` (dropdown item) |

---

## 23. Bottom Bar Info Tab (ui_bottom_bar.py)

| Line | String |
|------|--------|
| 570-575 | `"Colony age"`, `"Population"`, `"Buildings"` |
| 590 | `"Buildings"` (default tab name) |

---

## 24. Resource Icons / Names (ui.py & dynamic)

`RESOURCE_ICONS` dict (ui.py L68-85) maps 18 Resources to Unicode symbols:
`♣`, `❀`, `▣`, `♥`, `◆`, `◇`, `▭`, `▬`, `▬`, `▧`, `ζ`, `♃`, `▬`, `□`, `▬`, `⚙`, `⬢`, `▦`

**All resource display names** are generated dynamically via:
```python
resource.name.replace("_", " ").title()
```
Producing: `"Wood"`, `"Fiber"`, `"Stone"`, `"Food"`, `"Iron"`, `"Copper"`, `"Planks"`, `"Iron Bar"`, `"Copper Bar"`, `"Bricks"`, `"Copper Wire"`, `"Rope"`, `"Charcoal"`, `"Glass"`, `"Steel Bar"`, `"Gears"`, `"Silicon"`, `"Circuit"`.

---

## 25. Tooltip Calls

| File | Line | Content |
|------|------|---------|
| `ui_building_info.py` | 277 | Resource name hover (via `set_tooltip(resource.name...)`) |
| `ui_tech_tree.py` | 231 | Resource name on cost icon |
| `ui_tech_tree.py` | 270 | Building unlock tooltip: `"{name} — Free"` or `"{name} — {cost}"` |

---

## 26. Files With NO User-Facing Strings

These files were checked and contain no hardcoded display text:
- `buildings.py` — enum only, labels in UI files
- `resources.py` — enum only, labels derived dynamically
- `settings.py` — config values only
- `overlay.py` — procedural terrain rendering
- `render_overlays.py` — drawing functions only
- `render_terrain.py` — drawing functions only
- `render_buildings.py` — drawing functions only
- `render_utils.py` — color constants only
- `renderer.py` — rendering orchestration
- `camera.py` — viewport math
- `sprites.py` — sprite loading
- `generate_sprites.py` — sprite generation
- `resource_icons.py` — icon rendering
- `notifications.py` — notification framework (no strings)
- `people.py` — person logic
- `supply_chain.py` — logistics logic
- `procgen.py` — map generation
- `hex_grid.py` — coordinate math + Terrain enum
- `factions.py` — faction enum
- `blueprints.py` — save/load logic
- `ui_theme.py` — colors/fonts/drawing primitives
- `ui_minimap.py` — minimap rendering

---

## Summary Statistics

| Category | Approximate String Count |
|----------|------------------------|
| Tutorial steps | ~55 lines of text |
| Game guide pages | ~106 lines of text |
| Help/controls | 13 key-binding pairs |
| Building labels | 17 unique names (×3 duplicate dicts) |
| Building descriptions | 16 short descriptions |
| Terrain labels | 9 |
| Terrain descriptions | 9 |
| Tech tree nodes | 7 (name + description each) |
| Tier data | 4 (name + description each) |
| Upgrade names | 16 |
| Notifications | 8 distinct messages |
| UI labels/buttons/headers | ~80+ across all panels |
| Dynamic resource names | 18 (generated from enum) |
| **Total unique strings** | **~350-400** |
