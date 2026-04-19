# Copilot instructions — `compprog-pygame`

These instructions are auto-loaded by GitHub Copilot in this workspace.
They tell Copilot how this repo is organised and what rules to follow
when editing it. **Read [docs/HEX_COLONY_ARCHITECTURE.md](../docs/HEX_COLONY_ARCHITECTURE.md)
first** — that file is the definitive architectural reference for the
`hex_colony` game.

---

## 1. What this repo is

* Python game launcher (`compprog_pygame`) that hosts multiple games.
* Primary game: **`hex_colony`** — a hex-grid colony / logistics sim
  located at `src/compprog_pygame/games/hex_colony/`. ~50 modules,
  data-driven design, deterministic per-seed.
* Secondary: `physics_tetris` (much smaller, self-contained).
* Engine: `pygame-ce`. Python 3.13+. Build target: PyInstaller exe.

Top-level entry: `python -m compprog_pygame` → home screen → game pick.

---

## 2. Golden rules

1. **Edit data, not logic, for balance changes.** Numbers live in
   `params.py`. Strings live in `strings.py`. Touching `world.py`
   for a balance tweak almost always means you're in the wrong file.
2. **`params.py` uses string keys** for resources/buildings/stations.
   Don't import the `Resource` or `BuildingType` enums into it.
3. **Every tech node must unlock something.** Either `unlocks: [...]`
   (buildings) or `unlock_resources: [...]` (materials) — preferably
   both where it makes sense.
4. **When you add a tier, audit `ui_tutorial.TUTORIAL_STEPS`.** Tier
   index thresholds (`current_tier_level >= N`) shift when a tier is
   inserted in the middle of `TIER_DATA`.
5. **When you add a crafting station, update every station tuple in
   `world.py`.** Search the file for an existing station name (e.g.
   `OIL_REFINERY`) — there are ~6 places that must agree.
6. **The minimap renderer is a parallel draw chain.** When you add a
   building, update both the main and minimap dispatch in
   `renderer.py`.
7. **Don't break determinism.** All randomness in `procgen.py`,
   `overlay.py`, and per-tile decoration must be seeded from the
   world seed (and usually mixed with the tile coord). Never use
   `random.random()` unseeded in the simulation path.
8. **Don't introduce new fonts in panels.** Use `ui_theme` fonts.
9. **No save/load system exists.** Don't add one without a schema
   discussion — the enums it would have to version are huge.

---

## 3. Where to put things

| Change | File |
|---|---|
| Any number that affects gameplay | `params.py` |
| Any user-visible string | `strings.py` |
| New resource | `resources.Resource` + sets, `resource_icons._PALETTE`, `strings.RESOURCE_NAMES`, recipe in `params.MATERIAL_RECIPE_DATA` |
| New building | enum + 5 dicts in `buildings.py`, `params` cost/workers/housing/storage, `render_buildings.draw_*`, `render_utils.BUILDING_COLORS`, two `renderer.py` dispatch sites, `game.BUILDABLE`, `strings` labels, `params.TECH_TREE_DATA` unlock, tutorial step |
| New crafting station | building checklist above **plus** all 6 station tuples in `world.py` (`_update_workshops`, `_building_supply`, `_building_demand`, `_is_producer`, `_is_consumer`, `_building_output`, `_input_caps`) |
| New tier | `params.TIER_DATA` + audit `ui_tutorial.TUTORIAL_STEPS` thresholds |
| New tech node | `params.TECH_TREE_DATA` (must unlock content) |
| New tutorial step | text in `strings._TUTORIAL_TEXT`, trigger in `ui_tutorial.TUTORIAL_STEPS` |
| New keybinding | `Game.handle_event` + `ui_help.py` + `strings` |
| New overlay decoration | `overlay._gen_<terrain>_tile` + dispatch in `build_overlays` |

For the long-form version of these checklists, see
[docs/HEX_COLONY_ARCHITECTURE.md](../docs/HEX_COLONY_ARCHITECTURE.md)
sections 6.1–6.5.

---

## 4. Tooltips & strings

* New buildings always need three string entries: `BUILDING_LABELS`
  (full), `BUILDING_SHORT_LABELS` (≤ ~10 chars for badges/lists),
  `BUILDING_DESCRIPTIONS` (one or two sentences explaining purpose
  and inputs/outputs).
* New resources need `RESOURCE_NAMES[name] = "Title Case"`.
* When adding a feature that surfaces in a panel, add at least one
  matching tutorial step so players discover it. Use the trigger
  helpers `_research_done(world, node_id)` and
  `_has_building(world, type_name)`.

---

## 5. Performance

* Hot loops (`World.update`, renderer draw) must avoid per-frame
  allocations. Prefer module-level constants for tuples/sets used in
  these paths.
* Use `@lru_cache` or explicit dict caches for any expensive pure
  function called per-tile/per-frame (see `render_utils._pixel_cache`).
* Per-tile randomness must be seeded from `(world.seed, q, r)` so
  results are stable across frames and saves.
* Don't recompute networks every frame; call `world.mark_networks_dirty()`
  only when a building/path is added or removed.
* Sprite loads go through `sprites.py` (cached per zoom). Don't call
  `pygame.image.load` directly.

---

## 6. Bugs to actively prevent

When making a change, double-check the following before declaring done:

1. **Forgot a station tuple in `world.py`** → station produces nothing
   or starves silently.
2. **Forgot the minimap dispatch** in `renderer.py` → building shows
   on map but not on minimap.
3. **Tier insertion** without updating tutorial thresholds → tutorial
   fires at wrong tier.
4. **Tech node with no `unlocks`/`unlock_resources`** → researching it
   does nothing.
5. **Adding a terrain to `UNBUILDABLE`** without an exception → that
   terrain becomes useless.
6. **String key typo** → falls back to `"raw_key".title()`, looks ugly
   but doesn't crash. Always run the game once after string edits.
7. **Importing `Resource`/`BuildingType` into `params.py`** → circular
   import; `params.py` must stay pure data with string keys.
8. **Missing `_try_sprite` early return** in a new building drawer →
   PNGs in `assets/sprites/buildings/` are silently ignored.
9. **Tutorial step `after` referencing an id that doesn't exist** →
   step never fires. IDs must match `strings._TUTORIAL_TEXT`.
10. **Mutating `World` lists during iteration** in production loops —
    use `list(...)` snapshots when removing buildings.

---

## 7. Editing process

1. **Read the relevant section of
   [docs/HEX_COLONY_ARCHITECTURE.md](../docs/HEX_COLONY_ARCHITECTURE.md)**
   before changing anything you're not already familiar with.
2. Make the smallest change that does the job. Don't refactor
   unrelated code, don't add docstrings to untouched functions.
3. Run the smoke test:
   ```powershell
   $env:PYTHONPATH = "src"; python -m pytest tests/ -x
   ```
4. If you changed simulation/world code, also start the game once
   (the `Run Game` task) and verify no exceptions during world gen.
5. Don't bypass safety: never use `git --no-verify`, never
   `git push --force`, never `git reset --hard` without asking.

---

## 8. Style

* Python 3.13+ syntax (PEP 604 unions `int | None`, structural
  pattern matching where clearer, dataclasses freely).
* Type-hint new public functions; existing internals use partial
  hints — match the surrounding file.
* Prefer enum members and dict lookups over string comparisons.
* Keep modules focused; if a module exceeds ~2500 lines (only
  `world.py` does today), prefer adding a sibling module rather than
  growing it further.
* Group related constants into one section in `params.py` with a
  comment header (mirror existing patterns, e.g. the oil chain block).

---

## 9. When in doubt

Check
[docs/HEX_COLONY_ARCHITECTURE.md](../docs/HEX_COLONY_ARCHITECTURE.md)
section 10 ("useful entry points for common tasks") — it's a fast
table of "I want to do X → edit Y".
