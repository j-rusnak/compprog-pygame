# Hex Colony — Architecture & Systems Reference

A complete, top-to-bottom map of how the `hex_colony` game in this
workspace works. This is the single document to read first before
making any change to the game. Every module, system, data table, and
control-flow path is summarised here so a human or an LLM can locate
the right edit point in seconds.

> File paths in this doc are relative to the workspace root
> (`compprog-pygame/`). All `hex_colony` source lives in
> `src/compprog_pygame/games/hex_colony/`.

---

## 1. High-level concept

Hex Colony is a single-player real-time colony / logistics simulation
on a pointy-top axial hex grid. The player crash-lands on a re-evolved
Earth (intro cutscene → menu → game), then:

1. Gathers raw resources (wood, stone, fiber, food, iron, copper, oil…).
2. Crafts intermediates (planks, bars, bricks, gears, plastic, petroleum…).
3. Builds out a colony of dwellings, crafting stations, logistics
   networks, and research centers.
4. Climbs an 8-step **Tier** ladder and a parallel **Tech Tree** until
   they assemble a Rocket Silo and launch off-world to win.

The whole simulation is **deterministic** for a given alphanumeric
seed (terrain, AI tribes, resource-rich tiles).

---

## 2. Repository layout (game-relevant only)

```
src/compprog_pygame/
├── __main__.py            # entry point — runs home_screen
├── home_screen.py         # game-select screen (lists registered games)
├── game_registry.py       # GameSpec registry (each game registers itself)
├── settings.py            # global settings (window size, fps, audio)
└── games/
    └── hex_colony/        # this game
        ├── __init__.py    # registers the game on import
        ├── menu.py        # title / seed / world-size / play
        ├── cutscene.py    # masked load: plays while world generates
        ├── game.py        # top-level Game loop (input + draw + update)
        ├── world.py       # World state, simulation tick, networks, logistics
        ├── settings.py    # HexColonySettings dataclass (per-run config)
        ├── params.py      # *** all gameplay-balance constants ***
        ├── strings.py     # *** all user-facing text ***
        │
        ├── hex_grid.py    # HexCoord, Terrain enum, HexGrid container
        ├── procgen.py     # seed → terrain (noise, lakes, rivers, ore, oil)
        ├── resources.py   # Resource enum, Inventory, MATERIAL_RECIPES
        ├── buildings.py   # BuildingType enum + lookup dicts
        ├── tech_tree.py   # Tier + TechTree state machines
        ├── factions.py    # SURVIVOR / TRIBAL faction tags
        ├── people.py      # colonists (movement, tasks, hunger)
        ├── upgrades.py    # per-building upgrade chains
        ├── blueprints.py  # multi-tile placement patterns
        ├── supply_chain.py# arrow overlay (Alt-key debug view)
        ├── notifications.py # toast queue
        │
        ├── camera.py      # scroll/zoom
        ├── overlay.py     # cross-tile decorative overlays (trees, rocks…)
        ├── render_terrain.py  # tile colour + mountain shading
        ├── render_overlays.py # overlay-item drawers
        ├── render_buildings.py# per-building drawers (sprite or procedural)
        ├── render_utils.py    # shared palettes
        ├── renderer.py        # main draw loop + minimap
        ├── sprites.py         # PNG cache, multi-zoom
        ├── resource_icons.py  # procedural resource icons
        ├── generate_sprites.py# offline: re-emit asset PNGs
        │
        ├── ui.py              # Panel / UIManager framework
        ├── ui_theme.py        # fonts, button primitives
        ├── ui_resource_bar.py # top tier/research strip
        ├── ui_bottom_bar.py   # tabbed bottom bar
        ├── ui_minimap.py
        ├── ui_help.py         # keybindings overlay (?)
        ├── ui_info_guide.py   # multi-page guide (I)
        ├── ui_pause_menu.py   # pause / options / main menu
        ├── ui_tier_popup.py
        ├── ui_tutorial.py     # step-by-step contextual hints
        ├── ui_tile_info.py    # right-side panel (empty tile)
        ├── ui_building_info.py# right-side panel (building selected)
        ├── ui_stats.py        # bottom-bar stats tab
        ├── ui_advanced_stats.py # full-screen graphs popup
        ├── ui_tech_tree.py    # full-screen tech tree popup
        ├── ui_demand_priority.py
        ├── ui_supply_priority.py
        ├── ui_worker_priority.py
        ├── ui_priority_common.py
        └── ui_game_over.py
assets/sprites/                # PNGs auto-loaded by sprites.py
tests/                         # pytest (settings + smoke tests)
tools/build.ps1                # PyInstaller build (CompProgGame.spec)
```

---

## 3. Module-by-module reference

### 3.1 Coordinate / terrain layer

#### `hex_grid.py`
* `HexCoord(q, r)` — axial coordinates. Methods: `neighbors()`,
  `distance(other)`, `+`, `==`, hashable.
* `Terrain` (`Enum`) — `GRASS, FOREST, DENSE_FOREST, MOUNTAIN, WATER,
  STONE_DEPOSIT, FIBER_PATCH, IRON_VEIN, COPPER_VEIN, OIL_DEPOSIT`.
  ⚠️ **When you add a terrain, also update**: `procgen.UNBUILDABLE` if
  it should block buildings, `render_utils.TERRAIN_BASE_COLOR`,
  `render_utils._TERRAIN_CAT`, `overlay.py` (a `_gen_*_tile`
  generator + dispatch in `build_overlays`), and
  `resources.TERRAIN_RESOURCE` if it provides a harvestable resource.
* `HexTile` — owns `terrain`, `underlying_terrain` (set when ore/oil
  is laid on top), `resource_amount` (raw quantity left),
  `food_amount`, `building` back-reference.
* `HexGrid` — dict of `HexCoord → HexTile`. Iterable via `tiles()`.

#### `procgen.py`
Fully deterministic. Public entry: `generate_terrain(seed, settings,
progress_cb=None)` → `(HexGrid, elevation)`. Internally:

1. Carve land/water with layered value noise.
2. Mountains, then forest belts, then fibre/grass clearings.
3. Lakes + rivers (river-like BFS from highlands to lakes).
4. Stone deposits ringing mountains.
5. **Pass 5b** — `_generate_ore_veins()` for IRON_VEIN/COPPER_VEIN
   then `_generate_oil_deposits()` for OIL_DEPOSIT.
6. Clear safe zone around `(0, 0)` (always GRASS, no resources).

`UNBUILDABLE = frozenset({WATER, MOUNTAIN, OIL_DEPOSIT})` — checked
in `game._try_place_building`. Each unbuildable terrain may have
a single building exception (BRIDGE on WATER, OIL_DRILL on OIL_DEPOSIT).

#### `overlay.py`
Pre-computes per-tile decorative items (trees, rocks, ripples,
crystals, oil pools, ruins) **once per world** via
`build_overlays(grid, hex_size, seed)`. Each terrain has a
`_gen_*_tile()` helper. Items are sorted by Y for back-to-front
rendering.

---

### 3.2 Resources / recipes

#### `resources.py`
* `Resource` enum — every material in the game.
* `RAW_RESOURCES` / `PROCESSED_RESOURCES` sets — used by UI grouping
  and starvation tracking.
* `TERRAIN_RESOURCE: dict[Terrain, Resource]` — what a terrain yields
  when harvested (e.g. `OIL_DEPOSIT → OIL`).
* `Inventory` — global colony stockpile (separate from per-building
  storage). `.add()`, `.spend()`, `.get()`, `.cap()`.
* `Recipe` dataclass: `output, output_amount, inputs, time, station`.
* `MATERIAL_RECIPES: dict[Resource, Recipe]` — built at import time
  from `params.MATERIAL_RECIPE_DATA`.
* Station name constants: `STATION_WORKSHOP`, `STATION_FORGE`,
  `STATION_REFINERY`, `STATION_ASSEMBLER`, `STATION_CHEMICAL_PLANT`,
  `STATION_OIL_REFINERY`.

> **Adding a recipe** → edit `params.MATERIAL_RECIPE_DATA` only.
> Don't touch `resources.py`.

---

### 3.3 Buildings

#### `buildings.py`
* `BuildingType` enum: `CAMP, HABITAT, PATH, BRIDGE, WALL, WOODCUTTER,
  QUARRY, GATHERER, STORAGE, REFINERY, MINING_MACHINE, FARM, WELL,
  WORKSHOP, FORGE, ASSEMBLER, RESEARCH_CENTER, CHEMICAL_PLANT,
  CONVEYOR, SOLAR_ARRAY, ROCKET_SILO, OIL_DRILL, OIL_REFINERY,
  TRIBAL_CAMP`.
* Lookup dicts — **all sourced from `params.py`** at import time:
  * `BUILDING_COSTS[BuildingType] → BuildingCost(costs={Resource: int})`
  * `BUILDING_MAX_WORKERS[BuildingType] → int`
  * `BUILDING_HOUSING[BuildingType] → int`
  * `BUILDING_STORAGE_CAPACITY[BuildingType] → int`
  * `BUILDING_HARVEST_RESOURCES[BuildingType] → set[Resource]`
* `Building` dataclass (constructed by `world.add_building`):
  * `type, coord, faction, residents, workers, storage,
     storage_capacity, recipe, craft_progress, active, ...`
  * `recipe` is `BuildingType` (a Workshop crafting a placeable),
    `Resource` (a station crafting a material), or `None`.
* `BuildingRegistry` — owned by `World`. `.add()`, `.remove()`,
  `.by_type(t)` (iterator), `.at(coord)`.

> **Adding a building type** → add enum member + 5 dict entries. Then
> add: matching `params.BUILDING_COST_*`, `_MAX_WORKERS_*`,
> `_HOUSING_*`, `_STORAGE_*` constants; a drawer in
> `render_buildings.py` (with `_try_sprite()` fallback); colours in
> `render_utils.BUILDING_COLORS`; dispatch in `renderer.py` (main
> loop + minimap loop); `BUILDABLE` entry in `game.py`; labels +
> description in `strings.py`; usually a tutorial step in
> `strings.TUTORIAL_STEPS` and `ui_tutorial.TUTORIAL_STEPS`.

---

### 3.4 Tech tree & tiers

#### `tech_tree.py`
* `TIERS: list[Tier]` — built from `params.TIER_DATA`. Each tier has
  `name`, `description`, `unlocks_buildings`, `requirements`
  (`population`, `buildings_placed`, `resource_gathered`,
  `research_count`).
* `TIER_BUILDING_REQUIREMENTS: dict[BuildingType, int]` — tier index
  required to *place* each building (separate from tech unlock).
* `TIER_NODES` — alias used by the renderer.
* `TechNode` — built from `params.TECH_TREE_DATA`. Fields: `name,
  description, cost, time, prerequisites, unlocks (list[BuildingType]),
  unlock_resources (list[Resource]), position (col, row)`.
* `TECH_NODES: dict[str, TechNode]` — keyed by node id.
* `TECH_REQUIREMENTS: dict[BuildingType, str]` — building → required
  tech node id.
* `TierTracker` — current tier level, "is X unlocked", advance check
  every tick.
* `TechTree` — owns active research, completed set, consumption per
  resource. `.start_research(node_id)`, `.cancel_research()`,
  `.tick(dt)`, `.is_building_unlocked(t)`.

> **Every tech node must unlock at least one of**: a building
> (`unlocks`) or a resource (`unlock_resources`). Empty unlocks are
> a content-quality bug.

---

### 3.5 World simulation

#### `world.py` (the largest file in the game)

`World` is the single source of truth for the run. It owns:
* `grid: HexGrid`
* `inventory: Inventory` (global stockpile)
* `buildings: BuildingRegistry`
* `population: People`
* `tier_tracker, tech_tree`
* `networks: list[Network]` — connected groups of buildings linked by
  paths/bridges/conveyors. Workers and logistics work *within a
  network*. Recomputed lazily when `mark_networks_dirty()` is called.
* `notifications`, `pending_depleted_tiles`, `time` (sim seconds).

##### Update loop (called once per frame from `game.update`)
```python
def update(self, dt):
    if self._networks_dirty: self._rebuild_networks()
    self._refresh_populated_net_ids()
    self._assign_workers()
    self._dispatch_commuters()
    self._update_production(dt)   # gatherers, miners, oil drills
    self._update_workshops(dt)    # crafting stations
    self._update_logistics(dt)    # haulers
    self.population.update(dt, self, hex_size)
    self._update_population_growth(dt)
    self._update_housing()
    self.tech_tree.tick(dt)
    self.tier_tracker.tick(self)
```

##### Production helpers (all in `_update_production`)
* Woodcutter / Quarry / Gatherer / Farm — `_harvest_from_terrain`.
* `MINING_MACHINE` — burns fuel from `params.MINING_MACHINE_FUELS`,
  harvests adjacent ore tiles within `COLLECTION_RADIUS`.
* `OIL_DRILL` — sits **on** an OIL_DEPOSIT tile, no fuel, extracts
  OIL at `params.OIL_DRILL_RATE` straight into its own storage. Tile
  reverts to `underlying_terrain` when depleted.

##### Crafting (`_update_workshops`)
Iterates `station_types = (WORKSHOP, FORGE, REFINERY, ASSEMBLER,
CHEMICAL_PLANT, OIL_REFINERY)`. For each station with a recipe and
≥1 worker, calls `_tick_building_recipe` (placeable buildings) or
`_tick_material_recipe` (materials).

##### Logistics
Hauler people pick a (supplier_building, demander_building) pair.
Supply/demand is computed by `_building_supply()` / `_building_demand()`
which inspect `b.storage` against `b.recipe`/role. Each crafting
station type appears in **multiple tuples** in these helpers — when
adding a new station, audit every `(...CHEMICAL_PLANT, OIL_REFINERY)`
group.

##### Network recomputation
`_compute_components()` does a flood fill over path-connected
buildings; each component becomes a `Network`. Worker/demand
priorities are stored per-network so disconnecting a chunk of the map
preserves its priority lists.

---

### 3.6 People

#### `people.py`
* `Person` dataclass — `coord, current_pos (px), target_coord, role,
  task, home, work, carrying`.
* `People` — list + spatial helpers. `update(dt, world, hex_size)`
  moves everyone toward their `target_coord`, snapping on arrival.
* Roles are dynamic: `worker`, `hauler`, `idle`. Movement speed is
  `2x` on CONVEYOR tiles.
* Hunger is tracked per person; deaths trigger
  `notifications.push("Colonist starved")` and a population decrement.

---

### 3.7 Game loop entry

#### `game.py`
* Module-level constants: `BUILDABLE` (ordered list of placeable
  building types). **Add new buildings here** or they won't appear in
  the build menu.
* `Game.__init__` — wires `world`, `camera`, `renderer`, `tech_tree`,
  `tier_tracker`, every UI panel, sprite manager.
* `Game.handle_event(event)` — dispatches mouse/keyboard. Build
  placement runs through `_try_place_building(coord, silent)`.
* `_try_place_building`:
  1. Reject if `tile.terrain in UNBUILDABLE` **except** the
     special-case exceptions (BRIDGE/WATER, OIL_DRILL/OIL_DEPOSIT).
  2. Tech gate (`tech_tree.is_building_unlocked`).
  3. Tier gate (`tier_tracker.is_building_unlocked`).
  4. Cost check (debit from `world.inventory`).
  5. Special-case overlap rules (paths/bridges/conveyors stack with
     non-blocking buildings).
  6. `world.add_building(...)`.
* Mode switch: `god_mode` bypasses tech/tier/cost gates (debug).

---

### 3.8 Rendering

#### `renderer.py`
Main draw order each frame:
1. Background + tile colours (`render_terrain`).
2. Cross-tile overlays (`render_overlays`, sorted by Y).
3. Buildings (per-type dispatch in a long `if/elif` chain — search
   for `BuildingType.OIL_REFINERY` to see the pattern). Same chain
   exists in two places: the main map render and the **minimap**
   render. Both must be updated when adding a building.
4. People sprites.
5. Selection ring + ghost preview.
6. UI panels (delegated to `UIManager`).

#### `render_buildings.py`
One `draw_*(surface, sx, sy, r, z)` per building. Each starts with
`if _try_sprite(surface, "buildings/<name>", ...): return` so PNGs in
`assets/sprites/buildings/` always win over procedural art. Use
`_darken`/`_lighten` for shading; `iz = max(1, int(z))` for line
widths.

#### `render_utils.py`
* `TERRAIN_BASE_COLOR: dict[Terrain, RGB]`
* `BUILDING_COLORS: dict[BuildingType, RGB]` — used for ghost
  preview, minimap dots, and category icons.
* `_TERRAIN_CAT` — terrain category index used by various UI groups.

#### `resource_icons.py`
* `_PALETTE: dict[Resource, (main, highlight)]` — used by every UI
  that shows a resource icon.
* `get_resource_icon(resource, size=20)` — cached `pygame.Surface`.

---

### 3.9 UI framework

#### `ui.py`
* `Panel` base class: `draw(surface)`, `handle_event(event) → bool`,
  `set_visible()`.
* `UIManager` — owns a list of panels in z-order. Forwards events
  topmost-first; the first panel to return `True` consumes the event.

#### Panel inventory
| Module | Trigger | Purpose |
|---|---|---|
| `ui_resource_bar` | always | Top strip: tier name, requirements, active research |
| `ui_bottom_bar` | always | Tabs: Buildings, Workers, Demand, Supply, Stats, Info |
| `ui_minimap` | always (toggle M) | Bottom-right map view |
| `ui_tile_info` | tile selected (no building) | Right-side terrain/resource info |
| `ui_building_info` | building selected | Right-side building stats + recipe controls + tier-info button |
| `ui_tutorial` | trigger lambdas | Floating contextual hints |
| `ui_tier_popup` | on tier-up | Modal celebration panel |
| `ui_tech_tree` | "Open Tech Tree" button or T key | Full-screen graph |
| `ui_advanced_stats` | "Advanced Statistics" link | Full-screen graphs popup |
| `ui_help` | `?` key | Keybindings reference |
| `ui_info_guide` | `I` key | Multi-page guide |
| `ui_pause_menu` | `Esc` | Pause / options / main menu |
| `ui_game_over` | `world.game_over` true | End-of-run summary |

#### `ui_theme.py`
Centralised fonts (`FONT_TINY/SMALL/BODY/HEADER/TITLE`), button
helpers, text wrapping. **Don't create new fonts in panels** — pull
from here so the look stays uniform and high-DPI scaling works.

---

### 3.10 Strings & tutorials

#### `strings.py`
All user-facing text. Sections (in source order):
* `BUILDING_LABELS`, `BUILDING_SHORT_LABELS`, `BUILDING_DESCRIPTIONS`
* `BUILDING_CATEGORY_NAMES`
* `RESOURCE_NAMES`, `resource_name(key)`
* Notifications, tooltips, tier-popup phrases, stat labels…
* `_TUTORIAL_TEXT` — list of dicts (`id`, `title`, `lines`) used by
  the tutorial system. **Tutorial text and triggers are split**: text
  here, trigger lambdas in `ui_tutorial.TUTORIAL_STEPS`.

#### `ui_tutorial.py`
* `_TutorialStep(id, title, lines, trigger, after=None)` —
  `trigger(world, ctx) → bool`; `after` is a step id this one waits
  on. `ctx` contains: `time, current_tier_level, time_in_tier,
  population, building_counts`.
* Helpers: `_research_done(world, node_id)`,
  `_has_building(world, type_name)`.
* `TutorialPanel` polls steps each frame, shows the next eligible one.
* Tutorial state persists per-run only.

---

### 3.11 Auxiliary systems

#### `notifications.py`
`Notifications.push(msg, color=(255,255,255), duration=4.0)`. Toasts
fade in top-right. Used for "Out of stone", "Insufficient research",
"Colonist starved", etc.

#### `supply_chain.py`
Visual debug overlay. Shows arrows from supplier buildings to
demanders for the selected building. Uses
`world._building_supply` / `_building_demand`.

#### `upgrades.py`
Per-building upgrade chains; UI is in `ui_building_info.py`. Edit
upgrades by extending the chain dict — costs/effects mirror
`params.UPGRADE_*` patterns.

#### `blueprints.py`
Multi-tile placement patterns (saved in-memory only). Player records a
selection then stamps it elsewhere.

---

## 4. The two big data files

### 4.1 `params.py` — single source of truth for balance
Sections (in source order):
1. Hex/world sizing
2. Per-building gather rates (`GATHER_WOOD`, `QUARRY_ORE_RATE`, …)
3. **Per-building cost dicts** (`BUILDING_COST_<TYPE>`) and matching
   `BUILDING_MAX_WORKERS_<TYPE>`, `BUILDING_HOUSING_<TYPE>`,
   `BUILDING_STORAGE_<TYPE>` constants
4. Mining-machine + oil-drill rates and fuel tables
5. **`BUILDING_RECIPE_STATION`** — string-keyed dict mapping a
   placeable building name to the station that crafts it
6. **Material recipe dicts** (`RECIPE_<NAME>`) and the aggregator
   `MATERIAL_RECIPE_DATA: dict[str, dict]` (string-keyed by Resource
   name)
7. Population/housing/hunger constants
8. **`TIER_DATA`** — list of dicts (8 entries today)
9. **`TECH_TREE_DATA`** — dict of dicts; every node has `name,
   description, cost, time, prerequisites, unlocks (list[str]),
   unlock_resources (list[str], optional), position (col, row)`
10. Procedural generation parameters (noise scale, ore counts, …)
11. Oil deposit cluster gen parameters
12. Logistics constants (carry cap, walk speed, conveyor multiplier)

> ⚠️ **Never** import from `resources.py` or `buildings.py` here.
> `params.py` uses **string keys** so it can be loaded before those
> registries exist. The string keys are looked up by `_costs_from_dict`
> and similar helpers in `resources.py` / `buildings.py` /
> `tech_tree.py`.

### 4.2 `strings.py` — single source of truth for text
Update text **only** here. UI modules reference these dicts and
fall back to `key.replace("_", " ").title()` so a missing entry
won't crash but will look ugly.

---

## 5. Simulation tick — full call graph

```
Game.update(dt)
└── World.update(dt)
    ├── _rebuild_networks()         # if dirty
    ├── _refresh_populated_net_ids()
    ├── _assign_workers()           # commute targets
    ├── _dispatch_commuters()
    ├── _update_production(dt)
    │   ├── per-type harvest loops (woodcutter/quarry/gatherer/farm/well/refinery)
    │   ├── MINING_MACHINE: fuel + adjacent ore tiles
    │   └── OIL_DRILL: extract OIL from own tile  ← oil chain entry
    ├── _update_workshops(dt)       # crafting stations including OIL_REFINERY
    ├── _update_logistics(dt)       # haulers
    ├── population.update(dt, world, hex_size)
    ├── _update_population_growth(dt)
    ├── _update_housing()
    ├── tech_tree.tick(dt)          # debits inventory, advances research
    └── tier_tracker.tick(self)     # checks tier requirements, fires popup
```

`game.draw()` then runs the renderer on the same `World` snapshot.

---

## 6. Adding new content — workflow

### 6.1 Add a resource
1. `Resource.<NEW>` member in `resources.py`.
2. Add to `RAW_RESOURCES` or `PROCESSED_RESOURCES` set.
3. Palette entry in `resource_icons._PALETTE`.
4. Display name in `strings.RESOURCE_NAMES`.
5. (Recipe) entry in `params.MATERIAL_RECIPE_DATA` + a `RECIPE_<NEW>`
   constant; add to a station that exists.
6. Reference it from a tech node's `unlock_resources` so research
   gates the recipe.

### 6.2 Add a building
1. `BuildingType.<NEW>` enum member.
2. `params.BUILDING_COST_<NEW>`, `_MAX_WORKERS_<NEW>`,
   `_HOUSING_<NEW>`, `_STORAGE_<NEW>`.
3. Wire all four into `buildings.BUILDING_COSTS`,
   `BUILDING_MAX_WORKERS`, `BUILDING_HOUSING`, `BUILDING_STORAGE_CAPACITY`.
4. (If it harvests) `BUILDING_HARVEST_RESOURCES[NEW] = {Resource.X}`.
5. (If it crafts) add to `world._update_workshops`'s `station_types`
   tuple **and** to every station-set tuple in `_building_supply`,
   `_building_demand`, `_building_output`, `_is_producer`,
   `_is_consumer`, `_input_caps` (search for `CHEMICAL_PLANT,
   OIL_REFINERY` to find them all).
6. `render_buildings.draw_<new>()`. Use `_try_sprite` then
   procedural fallback.
7. `render_utils.BUILDING_COLORS[NEW] = (r,g,b)`.
8. `renderer.py` — add `elif building.type == BuildingType.NEW:`
   branches in **two** places (main render + minimap render).
9. `game.BUILDABLE` — append the type.
10. `params.BUILDING_RECIPE_STATION["<NEW>"] = "<STATION>"` so the
    appropriate Workshop/Forge/Assembler can craft it.
11. `strings.BUILDING_LABELS / BUILDING_SHORT_LABELS /
    BUILDING_DESCRIPTIONS`.
12. Add a tech node in `params.TECH_TREE_DATA` with
    `unlocks: ["NEW"]`.
13. Add a tutorial step (text in `strings._TUTORIAL_TEXT`, trigger in
    `ui_tutorial.TUTORIAL_STEPS`).
14. (If special placement) override in `game._try_place_building`
    (e.g. OIL_DRILL must be on OIL_DEPOSIT).

### 6.3 Add a tier
1. New entry in `params.TIER_DATA` (insert at correct index).
2. Bump `current_tier_level` thresholds in
   `ui_tutorial.TUTORIAL_STEPS` for any later tier (insertion
   shifts indices!).
3. (Optional) requirements that reference new resources you've
   already added.

### 6.4 Add a tech node
1. Entry in `params.TECH_TREE_DATA` keyed by `node_id`.
2. Must include `unlocks` (list of building names) **or**
   `unlock_resources` (list of resource names) — otherwise the node
   gives the player nothing and is a content bug.
3. Ensure `prerequisites` reference existing nodes.
4. Tutorial step optional.

### 6.5 Add a tutorial step
1. Text dict in `strings._TUTORIAL_TEXT` with `id`, `title`, `lines`.
2. `_TutorialStep(id=..., trigger=lambda w, ctx: ..., after=...)` in
   `ui_tutorial.TUTORIAL_STEPS`.
3. Trigger context fields available: `time`, `current_tier_level`,
   `time_in_tier`, `population`, `building_counts`. Helpers:
   `_research_done(w, node_id)`, `_has_building(w, type_name)`.

---

## 7. Performance notes

* **Networks** are recomputed only when `mark_networks_dirty()` is
  called (after add/remove of a building or path). Each frame just
  re-derives `_populated_net_ids` (cheap O(people)).
* **Overlays** are pre-built once per world and stored in
  `renderer._overlay_items`. Adding new overlay tile types must be
  free of per-frame allocation.
* **Sprites** are cached per zoom level in `sprites.py`. Resource
  icons are cached per `(Resource, size)` in `resource_icons`.
* **Pixel cache** — `render_utils.hex_to_pixel` results memoised in
  `_pixel_cache`. Don't bypass it.
* **Per-frame tuples** in `world.py` (e.g. station_types) are
  module-local and constructed once per call — fine; just don't add
  per-tile allocation in hot loops.
* `BuildingRegistry.by_type(t)` returns a generator over a pre-bucketed
  list; safe to call every frame.

---

## 8. Save / persistence

There is currently **no save system**. A run starts from scratch from
the menu (seed → world). All state lives in `World` and is GC'd when
the player returns to the home screen. Don't introduce save logic
without first proposing the schema (would need versioning across the
many enums in `resources.py` / `buildings.py`).

---

## 9. Known invariants & "gotchas"

1. **Every tech node must unlock at least one building or resource.**
   Empty `unlocks` + missing `unlock_resources` = dead-end node.
2. **Tier popup tutorial triggers reference tier indices**, not
   names. Inserting a tier shifts indices — update every later
   `current_tier_level >= N` lambda.
3. **Adding a crafting station type touches ~6 places in `world.py`.**
   Search for an existing station name (`OIL_REFINERY`,
   `CHEMICAL_PLANT`) to find them all.
4. **`params.py` imports nothing from `resources.py`/`buildings.py`.**
   Keep it data-only with string keys.
5. **`Terrain.OIL_DEPOSIT` is in `UNBUILDABLE`** — only `OIL_DRILL`
   has the placement exception. Bridges have a similar carve-out for
   `WATER`.
6. **`Building.recipe`** can be `None`, a `BuildingType` (Workshop
   crafting a placeable), or a `Resource` (station crafting a
   material). Branch carefully.
7. **Logistics demand caps are 2× recipe input.** Don't widen this
   without testing — it controls hauler thrash.
8. **Resource icons are cached** — calling `clear_cache()` is
   required after a DPI/font change.
9. **The minimap renderer** is a parallel draw chain and is the most
   common place where a new building gets forgotten.
10. **Sprite PNGs are optional**. Procedural drawers are the
    authoritative look; PNGs are an override loaded by
    `_try_sprite()`.

---

## 10. Useful entry points for common tasks

| Task | File / function |
|---|---|
| Tweak any number that affects gameplay | `params.py` |
| Change any visible string | `strings.py` |
| Add/edit a tutorial hint | `strings._TUTORIAL_TEXT` + `ui_tutorial.TUTORIAL_STEPS` |
| Recolour a building | `render_utils.BUILDING_COLORS` + drawer in `render_buildings.py` |
| Add a recipe | `params.RECIPE_<NAME>` + register in `MATERIAL_RECIPE_DATA` |
| Make a building auto-run | mirror `OIL_DRILL` in `world._update_production` |
| Add an overlay decoration | `overlay._gen_<terrain>_tile` + dispatch |
| Add a panel | subclass `Panel` in `ui.py`; register in `Game.__init__` |
| Add a key binding | `Game.handle_event` keymap and `ui_help.py` text |
| Update keybindings overlay | `ui_help.py` + `strings` |
| Change build menu order | `BUILDING_CATEGORIES` in `ui_bottom_bar.py` |

---

## 11. Run, test, build

* Run: `Run Game` task (`python -m compprog_pygame`) or
  `& .venv\Scripts\python.exe src\compprog_pygame\__main__.py`.
* Tests: `pytest tests/` (only a few smoke tests exist).
* Build: `Build Executable` task → `tools/build.ps1` → PyInstaller.
* Asset regen: `python -m compprog_pygame.games.hex_colony.generate_sprites`.

---
