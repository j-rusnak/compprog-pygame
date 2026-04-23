"""Rendering for Hex Colony — draws tiles, overlays, buildings, people, and HUD.

Performance notes
-----------------
* ``hex_to_pixel`` results are cached in ``_pixel_cache``.
* Cross-tile overlay art is built once per world via ``overlay.build_overlays``.
* Overlay rendering uses zoom thresholds; overlays are completely skipped at
  very low zoom and thinned at medium zoom.
* The selection-highlight overlay uses a small, clipped SRCALPHA surface
  instead of a full-screen allocation.
"""

from __future__ import annotations

import math

import pygame

from compprog_pygame.games.hex_colony.buildings import BuildingType
from compprog_pygame.games.hex_colony.camera import Camera
from compprog_pygame.games.hex_colony.hex_grid import (
    HexCoord,
    Terrain,
    hex_corners,
    hex_to_pixel,
)
from compprog_pygame.games.hex_colony.overlay import (
    OverlayBush,
    OverlayCrystal,
    OverlayGrassTuft,
    OverlayItem,
    OverlayRipple,
    OverlayRock,
    OverlayRuin,
    OverlayTree,
    build_overlays,
)
from compprog_pygame.games.hex_colony.people import Task
from compprog_pygame.games.hex_colony.world import World
from compprog_pygame.games.hex_colony import params

from compprog_pygame.games.hex_colony.render_utils import (
    BACKGROUND,
    TERRAIN_BASE_COLOR,
    _BLEND_STRENGTH,
    _BANK_COLOR,
    _TILE_LAYER_PAD,
    _SQRT3,
    _EDGE_BLEND,
    _TERRAIN_CAT,
    BUILDING_COLORS,
    _PATH_BASE,
    PERSON_COLOR,
    PERSON_GATHER_COLOR,
    PERSON_SKIN,
    PERSON_HAIR,
    _darken,
    _tile_hash,
)
from compprog_pygame.games.hex_colony.render_overlays import (
    draw_tree,
    draw_rock,
    draw_ripple,
    draw_bush,
    draw_grass,
    draw_crystal,
    draw_ruin,
)
from compprog_pygame.games.hex_colony.render_buildings import (
    draw_overcrowded,
    draw_camp,
    draw_habitat,
    draw_house,
    draw_woodcutter,
    draw_quarry,
    draw_gatherer,
    draw_storage,
    draw_path,
    draw_bridge,
    draw_pipe,
    draw_fluid_tank,
    draw_refinery,
    draw_mining_machine,
    draw_farm,
    draw_well,
    draw_wall,
    draw_workshop,
    draw_forge,
    draw_assembler,
    draw_research_center,
    draw_tribal_camp,
    draw_chemical_plant,
    draw_conveyor,
    draw_solar_array,
    draw_rocket_silo,
    draw_oil_drill,
    draw_oil_refinery,
    draw_ancient_tower,
    draw_turret,
    draw_trap,
    draw_enemy,
)
from compprog_pygame.games.hex_colony.render_terrain import (
    DIR_EDGE,
    mountain_tile_color,
    draw_contours,
)
from compprog_pygame.games.hex_colony.sprites import sprites

# Load sprite assets at import time
sprites.load_all()

# Building types that collect resources (show range ring)
_COLLECTION_BUILDINGS = {BuildingType.WOODCUTTER, BuildingType.QUARRY, BuildingType.GATHERER, BuildingType.MINING_MACHINE, BuildingType.OIL_DRILL}

# Sentinel used by per-frame caches to distinguish "not yet looked up"
# from "looked up and found None".
_MISSING_SENTINEL = object()

# Dispatch table for the second-pass non-path/wall building draw.
# A dict lookup is dramatically faster than the long if/elif chain
# this used to be when the renderer iterates hundreds of buildings
# per frame.
_BUILDING_DRAW: dict[BuildingType, callable] = {
    BuildingType.CAMP: draw_camp,
    BuildingType.HOUSE: draw_house,
    BuildingType.HABITAT: draw_habitat,
    BuildingType.WOODCUTTER: draw_woodcutter,
    BuildingType.QUARRY: draw_quarry,
    BuildingType.GATHERER: draw_gatherer,
    BuildingType.STORAGE: draw_storage,
    BuildingType.REFINERY: draw_refinery,
    BuildingType.MINING_MACHINE: draw_mining_machine,
    BuildingType.FORGE: draw_forge,
    BuildingType.ASSEMBLER: draw_assembler,
    BuildingType.FARM: draw_farm,
    BuildingType.WELL: draw_well,
    BuildingType.WORKSHOP: draw_workshop,
    BuildingType.RESEARCH_CENTER: draw_research_center,
    BuildingType.TRIBAL_CAMP: draw_tribal_camp,
    BuildingType.CHEMICAL_PLANT: draw_chemical_plant,
    BuildingType.CONVEYOR: draw_conveyor,
    BuildingType.SOLAR_ARRAY: draw_solar_array,
    BuildingType.ROCKET_SILO: draw_rocket_silo,
    BuildingType.OIL_DRILL: draw_oil_drill,
    BuildingType.OIL_REFINERY: draw_oil_refinery,
    BuildingType.FLUID_TANK: draw_fluid_tank,
    BuildingType.TURRET: draw_turret,
    BuildingType.TRAP: draw_trap,
}

class Renderer:
    """Draws the entire game scene."""

    def __init__(self) -> None:
        self.font = pygame.font.Font(None, 22)
        self.selected_hex: HexCoord | None = None
        self._water_tick: float = 0.0
        self._graphics_quality: str = "medium"  # "high", "medium", "low"

        # Caches
        self._pixel_cache: dict[HexCoord, tuple[float, float]] = {}
        self._corner_cache: dict[HexCoord, list[tuple[float, float]]] = {}
        self._overlays: list[OverlayItem] | None = None
        self._mountain_depths: dict[HexCoord, tuple[int, int]] = {}
        self._blended_colors: dict[HexCoord, tuple[int, int, int]] = {}
        # First-pass blend results, kept so we can incrementally
        # recompute the second smoothing pass for a small region of
        # the grid (e.g. when a single tile depletes) without
        # re-running the full O(N) blend over every tile.
        self._first_pass_colors: dict[HexCoord, tuple[int, int, int]] = {}

        # Tile layer cache (tiles + static overlays, pre-rendered)
        self._tile_layer: pygame.Surface | None = None
        self._tl_zoom: float = -1.0
        self._tl_cam: tuple[float, float] = (0.0, 0.0)
        self._tl_screen: tuple[int, int] = (0, 0)
        self._ripples: list[OverlayRipple] = []
        self._static_overlays: list[OverlayItem] = []
        # Set of (q, r) coords that host an OverlayRuin.  Built once
        # from the initial overlay pass so per-placement ruin lookups
        # are O(1) instead of O(static_overlays).
        self._ruin_coords: set[tuple[int, int]] = set()
        self._edge_colors: dict[HexCoord, list[tuple[int, int, int]]] = {}
        self._cross_cat: dict[HexCoord, list[int]] = {}  # 0=same category, 2=cross-category: use own colour
        self._dirty_tiles: set[HexCoord] = set()  # tiles needing targeted redraw
        # Spatial index of overlays by hex coord — built lazily on the
        # first call to ``remove_overlays_at`` so per-tile removal is
        # O(items in that hex) instead of O(total overlays).
        self._overlay_index: dict[tuple[int, int], list] | None = None
        self._removed_overlay_count: int = 0

        # Alt resource overlay
        self.show_resource_overlay: bool = False

        # Ghost building preview
        self.ghost_building: BuildingType | None = None
        self.ghost_coord: HexCoord | None = None  # snapped hex coord
        self.ghost_valid: bool = False  # whether placement is valid

        # Glowing-green chain placement preview for paths
        self.path_preview: list[HexCoord] = []

        # Reusable overlay surface for per-hex alpha blits
        self._hex_overlay: pygame.Surface | None = None
        self._hex_overlay_size: tuple[int, int] = (0, 0)

        # Ghost building surface cache (avoid per-frame allocation)
        self._ghost_cache: pygame.Surface | None = None
        self._ghost_cache_key: tuple | None = None

        # Cached unreachable-marker glyph (font + pre-rendered "!"
        # surfaces).  Re-rendered only when the zoom-bucket font size
        # actually changes, instead of every frame.
        self._unreach_font_size: int = -1
        self._unreach_glyph: pygame.Surface | None = None
        self._unreach_shadow: pygame.Surface | None = None

        # Pre-allocated scratch surface used by the zoom-scale path
        # of ``_blit_tile_layer``.  Without this, ``pygame.transform.scale``
        # allocated a new screen-sized RGB surface (≈8 MB at 1920×1080)
        # every animated zoom frame, which dominated render cost during
        # smooth zoom and added significant GC churn.
        self._scale_scratch: pygame.Surface | None = None

        # Per-(type, zoom-bucket) cache of pre-rendered enemy procedural
        # sprites.  Each enemy used to issue ~10 small draw calls every
        # frame; with the cache we issue a single blit per enemy.  The
        # zoom bucket is quantized to keep the cache compact.
        self._enemy_proc_cache: dict[tuple[str, int], pygame.Surface] = {}

    @property
    def graphics_quality(self) -> str:
        return self._graphics_quality

    @graphics_quality.setter
    def graphics_quality(self, value: str) -> None:
        if value != self._graphics_quality:
            self._graphics_quality = value
            self._tile_layer = None  # force rebuild

    # ── Cache helpers ────────────────────────────────────────────

    def _get_hex_overlay(self, w: int, h: int) -> pygame.Surface:
        """Return a reusable SRCALPHA surface, growing it if needed."""
        if self._hex_overlay is None or w > self._hex_overlay_size[0] or h > self._hex_overlay_size[1]:
            nw = max(w, self._hex_overlay_size[0]) + 16
            nh = max(h, self._hex_overlay_size[1]) + 16
            self._hex_overlay = pygame.Surface((nw, nh), pygame.SRCALPHA)
            self._hex_overlay_size = (nw, nh)
        self._hex_overlay.fill((0, 0, 0, 0), (0, 0, w, h))
        return self._hex_overlay

    def _get_pixel(self, coord: HexCoord, size: int) -> tuple[float, float]:
        cached = self._pixel_cache.get(coord)
        if cached is None:
            cached = hex_to_pixel(coord, size)
            self._pixel_cache[coord] = cached
        return cached

    def _get_corners(self, coord: HexCoord, wx: float, wy: float, size: int) -> list[tuple[float, float]]:
        cached = self._corner_cache.get(coord)
        if cached is None:
            cached = hex_corners(wx, wy, size)
            self._corner_cache[coord] = cached
        return cached

    # ── Public entry point ───────────────────────────────────────

    def draw(
        self,
        surface: pygame.Surface,
        world: World,
        camera: Camera,
        dt: float = 1 / 60,
    ) -> None:
        self._water_tick += dt
        # Expose renderer back to the world so simulation-side helpers
        # (AncientThreat, etc.) can ask the renderer about overlay
        # state — e.g. "is there a ruin on this tile".
        world._renderer_ref = self
        self._ensure_data(world)
        surface.fill(BACKGROUND)
        self._blit_tile_layer(surface, world, camera)
        if self._graphics_quality != "low":
            self._draw_ripples(surface, camera, world.settings.hex_size)
        self._draw_buildings(surface, world, camera)
        self._draw_people(surface, world, camera)
        self._draw_combat(surface, world, camera)
        self._draw_unreachable_markers(surface, world, camera)
        if self.show_resource_overlay:
            self._draw_resource_overlay(surface, world, camera)
        if self.path_preview:
            self._draw_path_preview(surface, camera, world.settings.hex_size)
        if self.ghost_building is not None and self.ghost_coord is not None:
            self._draw_ghost_building(surface, world, camera)
        if self.selected_hex is not None:
            self._draw_hex_highlight(surface, self.selected_hex, camera, world.settings.hex_size)
            # Range ring for selected collection buildings
            building = world.buildings.at(self.selected_hex)
            if building is not None and building.type in _COLLECTION_BUILDINGS:
                self._draw_range_ring(surface, self.selected_hex, camera, world.settings.hex_size)

    # ── Data preparation ─────────────────────────────────────────

    def _ensure_data(self, world: World) -> None:
        """Build overlays, blended colours, and overlay split on first call."""
        if self._overlays is None:
            self._overlays, self._mountain_depths = build_overlays(
                world.grid, world.settings.hex_size,
                seed=abs(hash(getattr(world, "seed", "default"))) & 0xFFFFFFFF,
            )
            self._static_overlays = [
                item for item in self._overlays
                if not isinstance(item, OverlayRipple)
            ]
            self._ripples = [
                item for item in self._overlays
                if isinstance(item, OverlayRipple)
            ]
            # Pre-compute the set of hex coords that host a ruin.
            # ``has_ruin_at`` is hit 7× per building placement by
            # ``AncientThreat.notify_built``; without this set it
            # linear-scanned all ~340k static overlays each call,
            # adding ~700ms of stall per placement.
            self._ruin_coords = {
                item.coord for item in self._static_overlays
                if isinstance(item, OverlayRuin)
            }
        # Drain depleted-tile events from the simulation: strip stale
        # overlays (trees / stones / ore crystals) from the now-grass
        # tile and incrementally re-blend the affected region.  This
        # used to nuke the entire blended-colour cache + tile_layer,
        # which produced multi-second freezes on large worlds whenever
        # any patch dried up.
        depleted = getattr(world, "pending_depleted_tiles", None)
        if depleted:
            depleted_list = list(depleted)
            depleted.clear()
            for coord in depleted_list:
                self.remove_overlays_at(coord, world.settings.hex_size)
            # Only valid if the initial full blend has already run.
            if self._blended_colors:
                affected = self._recompute_blends_around(depleted_list, world)
                # Each affected tile needs to be repainted on the
                # cached tile layer to pick up its new colour.
                self._dirty_tiles.update(affected)
        self._ensure_blended_colors(world)

    def remove_overlays_at(self, coord: HexCoord, hex_size: int) -> None:
        """Remove all overlay items that fall within the given hex tile.

        Uses a lazily-built spatial index keyed by hex coord so removal
        is O(items in this hex) instead of O(total overlay count).  The
        flat ``_static_overlays`` / ``_ripples`` lists are iterated for
        rendering, so removed items are tagged with ``wx = nan`` and
        skipped during draw and during periodic compaction.
        """
        from math import isnan, nan

        # Build the per-coord index lazily.
        self._build_overlay_index_if_needed(hex_size)

        key = (coord.q, coord.r)
        bucket = self._overlay_index.pop(key, None)
        if bucket:
            self._removed_overlay_count += len(bucket)
            for item in bucket:
                # Mark dead — render & blit loops skip nan positions.
                item.wx = nan
            # Periodically compact the flat lists so they don't grow
            # without bound (skip-checks add a tiny per-item cost).
            if self._removed_overlay_count > 256:
                self._static_overlays = [
                    it for it in self._static_overlays if not isnan(it.wx)
                ]
                self._ripples = [
                    it for it in self._ripples if not isnan(it.wx)
                ]
                self._removed_overlay_count = 0

        # Mark tile for targeted redraw instead of invalidating entire cache.
        # The building drawn on top will cover stale overlay pixels until the
        # next natural cache rebuild.
        self._dirty_tiles.add(coord)

    def _build_overlay_index_if_needed(self, hex_size: int) -> None:
        """Populate ``_overlay_index`` from the flat overlay lists.

        Keyed by ``(q, r)`` of the hex each overlay falls on.  Built
        once and then maintained incrementally by ``remove_overlays_at``.
        Used by both depletion removal and per-tile patching so the
        renderer never has to iterate the full ~30k-entry flat list
        per dirty hex.
        """
        if self._overlay_index is not None:
            return
        from math import isnan
        from compprog_pygame.games.hex_colony.hex_grid import pixel_to_hex
        index: dict[tuple[int, int], list] = {}
        for lst in (self._static_overlays, self._ripples):
            for item in lst:
                if isnan(item.wx):
                    continue
                c = pixel_to_hex(item.wx, item.wy, hex_size)
                key = (c.q, c.r)
                bucket = index.get(key)
                if bucket is None:
                    index[key] = [item]
                else:
                    bucket.append(item)
        self._overlay_index = index

    def invalidate_tile(self, coord: HexCoord) -> None:
        """Mark a single hex as needing redraw on the tile layer."""
        self._dirty_tiles.add(coord)

    def regenerate_overlays_at(self, coord: HexCoord, world) -> None:
        """Re-run the per-tile overlay generator for a single hex.

        Used when a building that was sitting on a decorated terrain
        (ore vein, stone deposit, fiber patch, grass, etc.) is
        deleted — the original overlay items were NaN-marked when the
        building was placed, so without this call the pixel art for
        the underlying resource never reappears.  Forest / mountain /
        water tiles aren't restored here because their art is
        cluster-dependent (depth maps / coherent ridges) and buildings
        can't be placed on them in practice.
        """
        from math import isnan
        import random as _random
        from compprog_pygame.games.hex_colony.hex_grid import (
            Terrain, hex_to_pixel,
        )
        from compprog_pygame.games.hex_colony import overlay as _overlay

        tile = world.grid.get(coord)
        if tile is None:
            return
        terrain = tile.terrain
        hex_size = world.settings.hex_size
        wx, wy = hex_to_pixel(coord, hex_size)
        rng = _random.Random(_overlay._tile_seed(coord))

        gen_items: list = []
        if terrain == Terrain.STONE_DEPOSIT:
            gen_items = _overlay._gen_stone_tile(wx, wy, hex_size, 0, rng)
        elif terrain == Terrain.FIBER_PATCH:
            gen_items = _overlay._gen_fiber_tile(wx, wy, hex_size, 0, tile, rng)
        elif terrain == Terrain.GRASS:
            gen_items = _overlay._gen_grass_tile(wx, wy, hex_size, rng)
        elif terrain in (Terrain.IRON_VEIN, Terrain.COPPER_VEIN):
            gen_items = _overlay._gen_ore_tile(
                wx, wy, hex_size, terrain, tile, rng,
            )
        elif terrain == Terrain.OIL_DEPOSIT:
            gen_items = _overlay._gen_oil_tile(wx, wy, hex_size, tile, rng)
        else:
            self._dirty_tiles.add(coord)
            return

        # Ensure the overlay index is up to date so new items are
        # tracked for future removal / compaction.
        self._build_overlay_index_if_needed(hex_size)

        from compprog_pygame.games.hex_colony.overlay import OverlayRipple
        key = (coord.q, coord.r)
        bucket = self._overlay_index.setdefault(key, [])
        # Drop any stale (NaN-marked) items still lingering in the
        # bucket from prior removals.
        bucket[:] = [it for it in bucket if not isnan(it.wx)]
        for _depth_key, item in gen_items:
            if isinstance(item, OverlayRipple):
                self._ripples.append(item)
            else:
                self._static_overlays.append(item)
            bucket.append(item)

        # Re-sort static overlays by wy for correct depth draw order.
        self._static_overlays.sort(
            key=lambda it: (float("inf") if isnan(it.wx) else it.wy),
        )
        self._dirty_tiles.add(coord)

    def has_ruin_at(self, coord: HexCoord) -> bool:
        """True if any OverlayRuin was generated on the given hex."""
        return (coord.q, coord.r) in self._ruin_coords

    # ── Blended tile colours (two-pass smoothing) ────────────────

    def _tile_base_color(
        self, tile, mtn: dict[HexCoord, tuple[int, int]],
    ) -> tuple[int, int, int]:
        """Per-tile base colour (mountain shading or terrain palette)
        with a deterministic per-tile colour jitter."""
        coord = tile.coord
        mtn_info = mtn.get(coord)
        if mtn_info is not None:
            base = mountain_tile_color(*mtn_info)
        elif tile.underlying_terrain is not None:
            base = TERRAIN_BASE_COLOR.get(tile.underlying_terrain, (80, 80, 80))
        else:
            base = TERRAIN_BASE_COLOR.get(tile.terrain, (80, 80, 80))
        th = _tile_hash(coord.q, coord.r)
        var = ((th & 0xFF) - 128) / 128.0 * 6  # ±6 per channel
        return (
            max(0, min(255, int(base[0] + var))),
            max(0, min(255, int(base[1] + var * 0.8))),
            max(0, min(255, int(base[2] + var * 0.6))),
        )

    def _compute_first_pass(self, coord: HexCoord, world: World) -> None:
        """Recompute the first-pass blend for one tile."""
        grid = world.grid
        mtn = self._mountain_depths
        tile = grid.get(coord)
        if tile is None:
            self._first_pass_colors.pop(coord, None)
            return
        base = self._tile_base_color(tile, mtn)
        my_cat = _TERRAIN_CAT.get(
            tile.underlying_terrain if tile.underlying_terrain is not None else tile.terrain, 0
        )
        nb_r = nb_g = nb_b = 0
        nb_count = 0
        is_water_adjacent = False
        for nb_coord in coord.neighbors():
            nb_tile = grid.get(nb_coord)
            if nb_tile is None:
                continue
            nb_cat = _TERRAIN_CAT.get(
                nb_tile.underlying_terrain if nb_tile.underlying_terrain is not None else nb_tile.terrain, 0
            )
            if my_cat != nb_cat:
                if nb_cat == 1 and my_cat != 1:
                    is_water_adjacent = True
                continue
            nb_mtn = mtn.get(nb_coord)
            if nb_mtn is not None:
                nc = mountain_tile_color(*nb_mtn)
            elif nb_tile.underlying_terrain is not None:
                nc = TERRAIN_BASE_COLOR.get(nb_tile.underlying_terrain, (80, 80, 80))
            else:
                nc = TERRAIN_BASE_COLOR.get(nb_tile.terrain, (80, 80, 80))
            nb_r += nc[0]; nb_g += nc[1]; nb_b += nc[2]
            nb_count += 1
        if nb_count > 0:
            avg = (nb_r / nb_count, nb_g / nb_count, nb_b / nb_count)
            s = _BLEND_STRENGTH
            blended = (
                int(base[0] * (1 - s) + avg[0] * s),
                int(base[1] * (1 - s) + avg[1] * s),
                int(base[2] * (1 - s) + avg[2] * s),
            )
        else:
            blended = base
        if is_water_adjacent:
            th = _tile_hash(coord.q, coord.r)
            bk = 0.2 + ((th >> 10) & 0xF) / 15.0 * 0.15  # 0.20–0.35
            blended = (
                int(blended[0] * (1 - bk) + _BANK_COLOR[0] * bk),
                int(blended[1] * (1 - bk) + _BANK_COLOR[1] * bk),
                int(blended[2] * (1 - bk) + _BANK_COLOR[2] * bk),
            )
        self._first_pass_colors[coord] = blended

    def _compute_second_pass(self, coord: HexCoord, world: World) -> None:
        """Recompute the second smoothing pass for one tile."""
        grid = world.grid
        first_pass = self._first_pass_colors
        tile = grid.get(coord)
        if tile is None or coord not in first_pass:
            self._blended_colors.pop(coord, None)
            return
        base = first_pass[coord]
        my_cat = _TERRAIN_CAT.get(
            tile.underlying_terrain if tile.underlying_terrain is not None else tile.terrain, 0
        )
        _SMOOTH2 = 0.30
        nb_r = nb_g = nb_b = 0
        nb_count = 0
        for nb_coord in coord.neighbors():
            nb_c = first_pass.get(nb_coord)
            if nb_c is None:
                continue
            nb_tile = grid.get(nb_coord)
            if nb_tile is not None and _TERRAIN_CAT.get(
                nb_tile.underlying_terrain if nb_tile.underlying_terrain is not None else nb_tile.terrain, 0
            ) != my_cat:
                continue
            nb_r += nb_c[0]; nb_g += nb_c[1]; nb_b += nb_c[2]
            nb_count += 1
        if nb_count > 0:
            avg = (nb_r / nb_count, nb_g / nb_count, nb_b / nb_count)
            self._blended_colors[coord] = (
                int(base[0] * (1 - _SMOOTH2) + avg[0] * _SMOOTH2),
                int(base[1] * (1 - _SMOOTH2) + avg[1] * _SMOOTH2),
                int(base[2] * (1 - _SMOOTH2) + avg[2] * _SMOOTH2),
            )
        else:
            self._blended_colors[coord] = base

    def _compute_edge_colors(self, coord: HexCoord, world: World) -> None:
        """Recompute the per-edge gradient colours for one tile."""
        grid = world.grid
        bc = self._blended_colors
        tile = grid.get(coord)
        cc = bc.get(coord)
        if tile is None or cc is None:
            self._edge_colors.pop(coord, None)
            self._cross_cat.pop(coord, None)
            return
        my_cat = _TERRAIN_CAT.get(
            tile.underlying_terrain if tile.underlying_terrain is not None else tile.terrain, 0
        )
        eb = _EDGE_BLEND
        eb1 = 1.0 - eb
        edge_cols: list[tuple[int, int, int]] = []
        cross_flags: list[int] = []
        for nb_coord in coord.neighbors():
            nc = bc.get(nb_coord)
            if nc is not None:
                nb_tile = grid.get(nb_coord)
                nb_cat = _TERRAIN_CAT.get(
                    (nb_tile.underlying_terrain if nb_tile.underlying_terrain is not None else nb_tile.terrain) if nb_tile else None, my_cat
                )
                if my_cat != nb_cat:
                    edge_cols.append(cc)
                    cross_flags.append(2)
                else:
                    edge_cols.append((
                        int(cc[0] * eb1 + nc[0] * eb),
                        int(cc[1] * eb1 + nc[1] * eb),
                        int(cc[2] * eb1 + nc[2] * eb),
                    ))
                    cross_flags.append(0)
            else:
                edge_cols.append(cc)
                cross_flags.append(0)
        self._edge_colors[coord] = edge_cols
        self._cross_cat[coord] = cross_flags

    def _recompute_blends_around(
        self, coords: set[HexCoord] | list[HexCoord], world: World,
    ) -> set[HexCoord]:
        """Incrementally update blended colours around a small region.

        Used when individual tiles deplete (resource patch ran out and
        the terrain reverted to grass).  Recomputes:
          * first-pass blends for the changed tiles + ring-1 neighbours
            (their first-pass averages used the changed tiles)
          * second-pass blends for the changed tiles + ring-2 neighbours
            (their second-pass averages used the ring-1 first-pass)
          * edge colours for the same ring-2 set

        Returns the set of tiles that need a tile-layer redraw.
        """
        ring1: set[HexCoord] = set()
        for c in coords:
            ring1.add(c)
            for n in c.neighbors():
                ring1.add(n)
        ring2: set[HexCoord] = set()
        for c in ring1:
            ring2.add(c)
            for n in c.neighbors():
                ring2.add(n)
        for c in ring1:
            self._compute_first_pass(c, world)
        for c in ring2:
            self._compute_second_pass(c, world)
            self._compute_edge_colors(c, world)
        return ring2

    def _ensure_blended_colors(self, world: World) -> None:
        """Pre-compute blended tile colours with two-pass smoothing.

        This is the full O(N) initial build; incremental updates after
        tile depletion go through :meth:`_recompute_blends_around`.
        """
        if self._blended_colors:
            return
        grid = world.grid

        # ── First pass: base blending with neighbours ────────────
        for tile in grid.tiles():
            self._compute_first_pass(tile.coord, world)
        # ── Second pass: smooth first-pass colours across neighbours
        for tile in grid.tiles():
            self._compute_second_pass(tile.coord, world)
        # ── Precompute per-edge colours for intra-tile gradients ──
        for tile in grid.tiles():
            self._compute_edge_colors(tile.coord, world)

    # ── Tile-layer cache ─────────────────────────────────────────

    def _blit_tile_layer(
        self, surface: pygame.Surface, world: World, camera: Camera,
    ) -> None:
        """Blit the cached tile+overlay surface; rebuild when stale.

        Uses zoom tolerance so the tile layer is NOT rebuilt for every
        tiny zoom change during smooth-zoom animation.  Between rebuilds
        the cached surface is scaled to approximate the current zoom.
        """
        sw, sh = surface.get_size()
        zoom = camera.zoom
        cam_x, cam_y = camera.x, camera.y

        # Don't rebuild while the camera is mid smooth-zoom animation —
        # that would re-render every frame as zoom drifts toward target,
        # producing the visible "lag" on each scroll.  Instead the
        # cached layer is scaled into place each frame and the rebuild
        # happens once the zoom settles.
        target_zoom = getattr(camera, "_target_zoom", zoom)
        zoom_settling = abs(zoom - target_zoom) > 1e-4

        need_rebuild = (
            self._tile_layer is None
            or self._tl_screen != (sw, sh)
        )

        if not need_rebuild and self._tl_zoom > 0 and not zoom_settling:
            # Only rebuild when zoom changes by more than 15 %
            zoom_ratio = zoom / self._tl_zoom
            if abs(zoom_ratio - 1.0) > 0.15:
                need_rebuild = True

        if not need_rebuild:
            # Check whether the source rect still fits inside the cache
            cw, ch = self._tile_layer.get_size()
            tl_z = self._tl_zoom
            ratio = tl_z / zoom
            src_w = sw * ratio
            src_h = sh * ratio
            src_cx = (cam_x - self._tl_cam[0]) * tl_z + cw * 0.5
            src_cy = (cam_y - self._tl_cam[1]) * tl_z + ch * 0.5
            src_x = src_cx - src_w * 0.5
            src_y = src_cy - src_h * 0.5
            if src_x < 0 or src_y < 0 or src_x + src_w > cw or src_y + src_h > ch:
                need_rebuild = True

        if need_rebuild:
            self._rebuild_tile_layer(world, camera, sw, sh)

        # Patch any tiles that were individually dirtied (building place/delete)
        if self._dirty_tiles:
            self._patch_dirty_tiles(world, world.settings.hex_size)

        # Compute source rect on the cached surface
        cw, ch = self._tile_layer.get_size()
        tl_z = self._tl_zoom
        ratio = tl_z / zoom
        isrc_w = max(1, int(sw * ratio))
        isrc_h = max(1, int(sh * ratio))
        src_cx = (cam_x - self._tl_cam[0]) * tl_z + cw * 0.5
        src_cy = (cam_y - self._tl_cam[1]) * tl_z + ch * 0.5
        isrc_x = int(src_cx - isrc_w * 0.5)
        isrc_y = int(src_cy - isrc_h * 0.5)
        isrc_x = max(0, min(isrc_x, cw - isrc_w))
        isrc_y = max(0, min(isrc_y, ch - isrc_h))

        if isrc_w == sw and isrc_h == sh:
            # Exact zoom match — fast direct blit
            surface.blit(self._tile_layer, (0, 0), (isrc_x, isrc_y, sw, sh))
        else:
            # Zoom mismatch — scale the relevant portion to the screen.
            # Reuse a pre-allocated scratch surface so the per-frame
            # ``transform.scale`` does not allocate a fresh ~screen-sized
            # surface (which dominated zoom-animation cost and triggered
            # frequent GC pauses).
            scratch = self._scale_scratch
            if scratch is None or scratch.get_size() != (sw, sh):
                scratch = pygame.Surface((sw, sh)).convert()
                self._scale_scratch = scratch
            sub = self._tile_layer.subsurface((isrc_x, isrc_y, isrc_w, isrc_h))
            pygame.transform.scale(sub, (sw, sh), scratch)
            surface.blit(scratch, (0, 0))

    def _rebuild_tile_layer(
        self, world: World, camera: Camera, sw: int, sh: int,
    ) -> None:
        """Re-render tiles + static overlays to the cache surface.

        LOD bands based on zoom:
        * zoom > 0.45  — 6 sub-triangle intra-tile gradients + contours + all overlays
        * 0.25–0.45    — flat polygon per tile + contours + stride-2 overlays
        * < 0.25       — flat polygon per tile only (no overlays, no contours)
        """
        zoom = camera.zoom
        cam_x, cam_y = camera.x, camera.y
        size = world.settings.hex_size

        cw = int(sw * _TILE_LAYER_PAD)
        ch = int(sh * _TILE_LAYER_PAD)
        if self._tile_layer is None or self._tile_layer.get_size() != (cw, ch):
            self._tile_layer = pygame.Surface((cw, ch)).convert()
        self._tile_layer.fill(BACKGROUND)

        self._tl_zoom = zoom
        self._tl_cam = (cam_x, cam_y)
        self._tl_screen = (sw, sh)

        half_cw = cw * 0.5
        half_ch = ch * 0.5
        blended = self._blended_colors
        edge_colors = self._edge_colors
        cross_cat = self._cross_cat
        mtn = self._mountain_depths
        grid = world.grid
        cache = self._tile_layer
        draw_poly = pygame.draw.polygon

        lod_high = zoom > 0.45 and self._graphics_quality == "high"
        lod_mid = not lod_high and zoom >= 0.25 and self._graphics_quality != "low"
        lod_low = self._graphics_quality == "low"

        # Frustum bounds in world coords (cache-sized, with one-tile margin).
        # Iterate the sparse tile dict directly — for a radius-80 world
        # this is ~22k tiles vs. the up to 100k+ (q,r) coords the old
        # bounding-rect double loop walked when zoomed out.  Avoids the
        # multi-second freezes that triggered the catastrophic
        # render_world spikes in the perf log.
        margin_world = size * 2
        min_wx = cam_x - half_cw / zoom - margin_world
        max_wx = cam_x + half_cw / zoom + margin_world
        min_wy = cam_y - half_ch / zoom - margin_world
        max_wy = cam_y + half_ch / zoom + margin_world

        for tile in grid.tiles():
            coord = tile.coord
            wx, wy = self._get_pixel(coord, size)
            if wx < min_wx or wx > max_wx or wy < min_wy or wy > max_wy:
                continue

            corners_world = self._get_corners(coord, wx, wy, size)
            corners = [
                ((cx - cam_x) * zoom + half_cw,
                 (cy - cam_y) * zoom + half_ch)
                for cx, cy in corners_world
            ]

            corners_world = self._get_corners(coord, wx, wy, size)
            corners = [
                ((cx - cam_x) * zoom + half_cw,
                 (cy - cam_y) * zoom + half_ch)
                for cx, cy in corners_world
            ]

            base = blended.get(coord, (80, 80, 80))

            if lod_low:
                # Low quality: flat terrain base colour, no blending
                flat = TERRAIN_BASE_COLOR.get(tile.terrain, (80, 80, 80))
                draw_poly(cache, flat, corners)
            elif lod_high:
                # Intra-tile rendering: 6 wedges (center→corner→corner).
                # Same-category: 4-triangle gradient.
                # Cross-category yield: midpoint boundary (smooth line).
                # Cross-category dominate/keep: full wedge own colour.
                ecols = edge_colors.get(coord)
                xcat = cross_cat.get(coord)
                if ecols is not None and xcat is not None:
                    cxs = (corners[0][0] + corners[1][0] + corners[2][0]
                           + corners[3][0] + corners[4][0] + corners[5][0]) / 6.0
                    cys = (corners[0][1] + corners[1][1] + corners[2][1]
                           + corners[3][1] + corners[4][1] + corners[5][1]) / 6.0
                    for d in range(6):
                        i1 = DIR_EDGE[d][0]
                        i2 = DIR_EDGE[d][1]
                        ax, ay = corners[i1]
                        bx, by = corners[i2]
                        xf = xcat[d]
                        if xf == 2:
                            # Cross-category: entire wedge in own colour
                            draw_poly(cache, base,
                                      [(cxs, cys), (ax, ay), (bx, by)])
                        else:
                            # Same category: 4-triangle gradient
                            ec = ecols[d]
                            mca = ((cxs + ax) * 0.5, (cys + ay) * 0.5)
                            mcb = ((cxs + bx) * 0.5, (cys + by) * 0.5)
                            mab = ((ax + bx) * 0.5, (ay + by) * 0.5)
                            mc = ((base[0] + ec[0]) >> 1,
                                  (base[1] + ec[1]) >> 1,
                                  (base[2] + ec[2]) >> 1)
                            draw_poly(cache, base, [(cxs, cys), mca, mcb])
                            draw_poly(cache, ec, [mca, (ax, ay), mab])
                            draw_poly(cache, ec, [mcb, mab, (bx, by)])
                            draw_poly(cache, mc, [mca, mab, mcb])
                else:
                    draw_poly(cache, base, corners)
            else:
                draw_poly(cache, base, corners)

            # Mountain ridge spurs (skip at low quality and very low zoom)
            if (lod_high or lod_mid) and not lod_low:
                mtn_info = mtn.get(coord)
                if mtn_info is not None and mtn_info[0] > 0:
                    draw_contours(
                        cache, coord, mtn_info[0], corners,
                        base, mtn, zoom,
                    )

        # Static overlays (skip on low quality or when zoom < 0.25)
        if (lod_high or lod_mid) and not lod_low:
            margin = size * 16 * zoom
            stride = 1 if lod_high else 2
            for idx in range(0, len(self._static_overlays), stride):
                item = self._static_overlays[idx]
                wx = item.wx
                if wx != wx:  # NaN check — item was removed
                    continue
                sx = (wx - cam_x) * zoom + half_cw
                sy = (item.wy - cam_y) * zoom + half_ch
                if sx < -margin or sx > cw + margin or sy < -margin or sy > ch + margin:
                    continue
                iz = max(1, int(zoom))
                if isinstance(item, OverlayTree):
                    draw_tree(cache, item, sx, sy, zoom, iz)
                elif isinstance(item, OverlayRock):
                    draw_rock(cache, item, sx, sy, zoom, iz)
                elif isinstance(item, OverlayBush):
                    draw_bush(cache, item, sx, sy, zoom, iz)
                elif isinstance(item, OverlayGrassTuft):
                    draw_grass(cache, item, sx, sy, zoom, iz)
                elif isinstance(item, OverlayCrystal):
                    draw_crystal(cache, item, sx, sy, zoom, iz)
                elif isinstance(item, OverlayRuin):
                    draw_ruin(cache, item, sx, sy, zoom, iz)

    def _patch_dirty_tiles(self, world: World, hex_size: int) -> None:
        """Redraw only the dirty tiles on the existing tile layer cache.

        This avoids a full rebuild when a building is placed or deleted,
        preventing the visible "pop" on all surrounding tiles.
        """
        if not self._dirty_tiles or self._tile_layer is None:
            return

        cache = self._tile_layer
        zoom = self._tl_zoom
        cam_x, cam_y = self._tl_cam
        cw, ch = cache.get_size()
        half_cw = cw * 0.5
        half_ch = ch * 0.5
        blended = self._blended_colors
        mtn = self._mountain_depths

        lod_high = zoom > 0.45 and self._graphics_quality == "high"
        lod_mid = not lod_high and zoom >= 0.25 and self._graphics_quality != "low"
        lod_low = self._graphics_quality == "low"

        for coord in self._dirty_tiles:
            tile = world.grid.get(coord)
            if tile is None:
                continue

            wx, wy = self._get_pixel(coord, hex_size)
            corners_world = self._get_corners(coord, wx, wy, hex_size)
            corners = [
                ((cx - cam_x) * zoom + half_cw,
                 (cy - cam_y) * zoom + half_ch)
                for cx, cy in corners_world
            ]
            base = blended.get(coord, (80, 80, 80))

            # Redraw terrain polygon (same LOD logic as _rebuild_tile_layer)
            if lod_low:
                flat = TERRAIN_BASE_COLOR.get(tile.terrain, (80, 80, 80))
                pygame.draw.polygon(cache, flat, corners)
            elif lod_high:
                ecols = self._edge_colors.get(coord)
                xcat = self._cross_cat.get(coord)
                if ecols is not None and xcat is not None:
                    cxs = sum(c[0] for c in corners) / 6.0
                    cys = sum(c[1] for c in corners) / 6.0
                    for d in range(6):
                        i1 = DIR_EDGE[d][0]
                        i2 = DIR_EDGE[d][1]
                        ax, ay = corners[i1]
                        bx, by = corners[i2]
                        xf = xcat[d]
                        if xf == 2:
                            pygame.draw.polygon(cache, base,
                                                [(cxs, cys), (ax, ay), (bx, by)])
                        else:
                            ec = ecols[d]
                            mca = ((cxs + ax) * 0.5, (cys + ay) * 0.5)
                            mcb = ((cxs + bx) * 0.5, (cys + by) * 0.5)
                            mab = ((ax + bx) * 0.5, (ay + by) * 0.5)
                            mc = ((base[0] + ec[0]) >> 1,
                                  (base[1] + ec[1]) >> 1,
                                  (base[2] + ec[2]) >> 1)
                            pygame.draw.polygon(cache, base, [(cxs, cys), mca, mcb])
                            pygame.draw.polygon(cache, ec, [mca, (ax, ay), mab])
                            pygame.draw.polygon(cache, ec, [mcb, mab, (bx, by)])
                            pygame.draw.polygon(cache, mc, [mca, mab, mcb])
                else:
                    pygame.draw.polygon(cache, base, corners)
            else:
                pygame.draw.polygon(cache, base, corners)

            # Mountain contours
            if (lod_high or lod_mid) and not lod_low:
                mtn_info = mtn.get(coord)
                if mtn_info is not None and mtn_info[0] > 0:
                    draw_contours(
                        cache, coord, mtn_info[0], corners,
                        base, mtn, zoom,
                    )

            # Re-draw any remaining overlays that overlap this hex.
            # Uses the per-coord overlay index (own coord + 6
            # neighbours) so this is O(items in 7 hexes) instead of
            # O(total overlay count) per dirty tile.  This was the
            # dominant cost in resource-depletion frame spikes.
            if (lod_high or lod_mid) and not lod_low:
                self._build_overlay_index_if_needed(hex_size)
                patch_r2 = (hex_size * 1.5) ** 2
                iz = max(1, int(zoom))
                index = self._overlay_index
                # Iterate the central tile then its 6 neighbours.
                _candidates: list = []
                _candidates.extend(index.get((coord.q, coord.r), ()))
                for nb in coord.neighbors():
                    _candidates.extend(index.get((nb.q, nb.r), ()))
                for item in _candidates:
                    iwx = item.wx
                    if iwx != iwx:  # NaN — removed
                        continue
                    if (iwx - wx) ** 2 + (item.wy - wy) ** 2 > patch_r2:
                        continue
                    isx = (iwx - cam_x) * zoom + half_cw
                    isy = (item.wy - cam_y) * zoom + half_ch
                    if isinstance(item, OverlayTree):
                        draw_tree(cache, item, isx, isy, zoom, iz)
                    elif isinstance(item, OverlayRock):
                        draw_rock(cache, item, isx, isy, zoom, iz)
                    elif isinstance(item, OverlayBush):
                        draw_bush(cache, item, isx, isy, zoom, iz)
                    elif isinstance(item, OverlayGrassTuft):
                        draw_grass(cache, item, isx, isy, zoom, iz)
                    elif isinstance(item, OverlayCrystal):
                        draw_crystal(cache, item, isx, isy, zoom, iz)
                    elif isinstance(item, OverlayRuin):
                        draw_ruin(cache, item, isx, isy, zoom, iz)

        # Clear after patching so we don't redo these every frame
        self._dirty_tiles.clear()

    # ── Animated overlays (ripples) ──────────────────────────────

    def _draw_ripples(
        self, surface: pygame.Surface, camera: Camera, hex_size: int,
    ) -> None:
        zoom = camera.zoom
        if zoom < 0.2:
            return
        cam_x, cam_y = camera.x, camera.y
        sw, sh = surface.get_size()
        half_sw, half_sh = sw * 0.5, sh * 0.5
        margin = hex_size * 16 * zoom
        tick = self._water_tick
        stride = 1 if zoom > 0.7 else (2 if zoom > 0.4 else 3)
        for idx in range(0, len(self._ripples), stride):
            item = self._ripples[idx]
            wx = item.wx
            if wx != wx:  # NaN — removed
                continue
            sx = (wx - cam_x) * zoom + half_sw
            sy = (item.wy - cam_y) * zoom + half_sh
            if sx < -margin or sx > sw + margin or sy < -margin or sy > sh + margin:
                continue
            iz = max(1, int(zoom))
            draw_ripple(surface, item, sx, sy, zoom, iz, tick)

    # ── Buildings ────────────────────────────────────────────────

    def _draw_buildings(
        self, surface: pygame.Surface, world: World, camera: Camera,
    ) -> None:
        size = world.settings.hex_size
        zoom = camera.zoom
        cam_x, cam_y = camera.x, camera.y
        sw, sh = surface.get_size()
        half_sw, half_sh = sw * 0.5, sh * 0.5
        margin = size * 2 * zoom

        # First pass: paths and bridges (ground-level, drawn beneath other buildings)
        # Also track non-path buildings that need a path disc underneath
        buildings_needing_path: set[HexCoord] = set()
        _PATH_TYPES = {BuildingType.PATH, BuildingType.BRIDGE}
        # Non-path buildings adjacent to other non-path buildings also
        # get an implicit path disc so neighbouring buildings visually
        # connect (workers can step directly between them, so it should
        # not look like they're running on grass).
        _IMPLICIT_PATH_SKIP = {
            BuildingType.PATH, BuildingType.BRIDGE, BuildingType.WALL,
            BuildingType.PIPE,
        }
        for building in world.buildings.buildings:
            if building.type in _IMPLICIT_PATH_SKIP:
                continue
            for nb_coord in building.coord.neighbors():
                nb_building = world.buildings.at(nb_coord)
                if (nb_building is not None
                        and nb_building.type not in _IMPLICIT_PATH_SKIP):
                    buildings_needing_path.add(building.coord)
                    break
        path_buildings = (
            world.buildings.by_type(BuildingType.PATH)
            + world.buildings.by_type(BuildingType.BRIDGE)
        )
        for building in path_buildings:
            wx, wy = self._get_pixel(building.coord, size)
            sx = (wx - cam_x) * zoom + half_sw
            sy = (wy - cam_y) * zoom + half_sh
            if sx < -margin or sx > sw + margin or sy < -margin or sy > sh + margin:
                continue
            r = int(size * 0.75 * zoom)
            if r < 2:
                pygame.draw.circle(surface, _PATH_BASE, (int(sx), int(sy)), max(1, r))
                continue
            # Compute screen positions of adjacent path or building neighbours
            nb_positions: list[tuple[float, float]] = []
            for nb_coord in building.coord.neighbors():
                nb_building = world.buildings.at(nb_coord)
                if nb_building is not None:
                    nwx, nwy = self._get_pixel(nb_coord, size)
                    nsx = (nwx - cam_x) * zoom + half_sw
                    nsy = (nwy - cam_y) * zoom + half_sh
                    nb_positions.append((nsx, nsy))
                    if nb_building.type not in _PATH_TYPES:
                        buildings_needing_path.add(nb_coord)
            if building.type == BuildingType.BRIDGE:
                draw_bridge(surface, sx, sy, r, zoom, nb_positions,
                            building.coord.q, building.coord.r)
            else:
                draw_path(surface, sx, sy, r, zoom, nb_positions,
                          building.coord.q, building.coord.r)

        # Walls pass: walls connect only to other walls
        for building in world.buildings.by_type(BuildingType.WALL):
            wx, wy = self._get_pixel(building.coord, size)
            sx = (wx - cam_x) * zoom + half_sw
            sy = (wy - cam_y) * zoom + half_sh
            if sx < -margin or sx > sw + margin or sy < -margin or sy > sh + margin:
                continue
            r = int(size * 0.75 * zoom)
            if r < 2:
                pygame.draw.circle(surface, (160, 155, 145), (int(sx), int(sy)), max(1, r))
                continue
            nb_positions_w: list[tuple[float, float]] = []
            for nb_coord in building.coord.neighbors():
                nb_building = world.buildings.at(nb_coord)
                if nb_building is not None and nb_building.type == BuildingType.WALL:
                    nwx, nwy = self._get_pixel(nb_coord, size)
                    nsx = (nwx - cam_x) * zoom + half_sw
                    nsy = (nwy - cam_y) * zoom + half_sh
                    nb_positions_w.append((nsx, nsy))
            draw_wall(surface, sx, sy, r, zoom, nb_positions_w,
                      building.coord.q, building.coord.r)

        # Pipes pass: pipes connect to other pipes and to fluid-capable
        # buildings (drills, refineries, chemical plants, tanks, silos).
        from compprog_pygame.games.hex_colony.world import (
            FLUID_CAPABLE_BUILDINGS,
        )
        for building in world.buildings.by_type(BuildingType.PIPE):
            wx, wy = self._get_pixel(building.coord, size)
            sx = (wx - cam_x) * zoom + half_sw
            sy = (wy - cam_y) * zoom + half_sh
            if sx < -margin or sx > sw + margin or sy < -margin or sy > sh + margin:
                continue
            r = int(size * 0.75 * zoom)
            if r < 2:
                pygame.draw.circle(surface, (155, 150, 145), (int(sx), int(sy)), max(1, r))
                continue
            nb_positions_p: list[tuple[float, float]] = []
            for nb_coord in building.coord.neighbors():
                nb_building = world.buildings.at(nb_coord)
                if nb_building is None:
                    continue
                if (nb_building.type == BuildingType.PIPE
                        or nb_building.type in FLUID_CAPABLE_BUILDINGS):
                    nwx, nwy = self._get_pixel(nb_coord, size)
                    nsx = (nwx - cam_x) * zoom + half_sw
                    nsy = (nwy - cam_y) * zoom + half_sh
                    nb_positions_p.append((nsx, nsy))
            draw_pipe(surface, sx, sy, r, zoom, nb_positions_p,
                      building.coord.q, building.coord.r)

        # Draw path discs under non-path buildings adjacent to paths
        for coord in buildings_needing_path:
            bld = world.buildings.at(coord)
            if bld is None:
                continue
            wx, wy = self._get_pixel(coord, size)
            sx = (wx - cam_x) * zoom + half_sw
            sy = (wy - cam_y) * zoom + half_sh
            if sx < -margin or sx > sw + margin or sy < -margin or sy > sh + margin:
                continue
            r = int(size * 0.75 * zoom)
            if r < 2:
                pygame.draw.circle(surface, _PATH_BASE, (int(sx), int(sy)), max(1, r))
                continue
            # Gather neighbours that should anchor the under-building
            # path disc: real paths/bridges and other non-path/wall
            # buildings (so adjacent buildings visually connect).
            nb_positions_b: list[tuple[float, float]] = []
            for nb_coord in coord.neighbors():
                nb_building = world.buildings.at(nb_coord)
                if nb_building is None:
                    continue
                if (nb_building.type in _PATH_TYPES
                        or nb_building.type not in _IMPLICIT_PATH_SKIP):
                    nwx, nwy = self._get_pixel(nb_coord, size)
                    nsx = (nwx - cam_x) * zoom + half_sw
                    nsy = (nwy - cam_y) * zoom + half_sh
                    nb_positions_b.append((nsx, nsy))
            draw_path(surface, sx, sy, r, zoom, nb_positions_b,
                      coord.q, coord.r)

        # Second pass: non-path, non-wall buildings
        _SKIP_SECOND = {
            BuildingType.PATH, BuildingType.BRIDGE, BuildingType.WALL,
            BuildingType.PIPE,
        }
        for building in world.buildings.buildings:
            if building.type in _SKIP_SECOND:
                continue
            wx, wy = self._get_pixel(building.coord, size)
            sx = (wx - cam_x) * zoom + half_sw
            sy = (wy - cam_y) * zoom + half_sh
            if sx < -margin or sx > sw + margin or sy < -margin or sy > sh + margin:
                continue

            r = int(size * 0.75 * zoom)
            color = BUILDING_COLORS.get(building.type, (200, 200, 200))
            if r < 3:
                pygame.draw.circle(surface, color, (int(sx), int(sy)), max(2, r))
                continue

            drawer = _BUILDING_DRAW.get(building.type)
            if drawer is not None:
                drawer(surface, sx, sy, r, zoom)

            # Damage indicator: red HP bar floats above any building
            # whose health is below max.
            if (getattr(building, "max_health", 0.0) > 0
                    and building.health < building.max_health
                    and r >= 3):
                self._draw_hp_bar(surface, sx, sy - r * 1.1,
                                  building.health,
                                  building.max_health, r)

            # Overcrowding indicator: red ! above dwelling
            if (building.housing_capacity > 0
                    and building.residents > building.housing_capacity
                    and r >= 3):
                draw_overcrowded(surface, sx, sy, r, zoom)

        # Ancient tech towers (separate list, not buildings)
        ancient = getattr(world, "ancient", None)
        if ancient is not None:
            for tower in ancient.towers:
                wx, wy = self._get_pixel(tower.coord, size)
                sx = (wx - cam_x) * zoom + half_sw
                sy = (wy - cam_y) * zoom + half_sh
                if sx < -margin or sx > sw + margin or sy < -margin or sy > sh + margin:
                    continue
                r = int(size * 0.75 * zoom)
                draw_ancient_tower(surface, sx, sy, r, zoom, tower.rise_progress)

    # ── People ───────────────────────────────────────────────────

    def _draw_people(
        self, surface: pygame.Surface, world: World, camera: Camera,
    ) -> None:
        zoom = camera.zoom
        cam_x, cam_y = camera.x, camera.y
        sw, sh = surface.get_size()
        half_sw, half_sh = sw * 0.5, sh * 0.5

        for person in world.population.people:
            # Hide people stationed inside a building (idle with a home)
            if person.task == Task.IDLE and person.home is not None:
                continue

            sx = (person.px - cam_x) * zoom + half_sw
            sy = (person.py - cam_y) * zoom + half_sh
            if sx < -20 or sx > sw + 20 or sy < -20 or sy > sh + 20:
                continue

            isx, isy = int(sx), int(sy)
            iz = max(1, int(zoom))

            if zoom < 0.4:
                color = PERSON_GATHER_COLOR if person.task == Task.GATHER else PERSON_COLOR
                pygame.draw.circle(surface, color, (isx, isy), max(1, int(3 * zoom)))
                continue

            # Try sprite first
            person_key = "people/person_gather" if person.task == Task.GATHER else "people/person_idle"
            person_sheet = sprites.get(person_key)
            if person_sheet is not None:
                bw, bh = person_sheet.base_size
                tw = max(2, int(bw * zoom))
                th = max(2, int(bh * zoom))
                img = person_sheet.get(tw, th)
                surface.blit(img, (isx - tw // 2, isy - th + 2))
                continue

            head_r = max(2, int(2.5 * zoom))
            body_h = max(2, int(4 * zoom))
            leg_h = max(1, int(2 * zoom))
            body_w = max(1, iz)

            body_color = PERSON_GATHER_COLOR if person.task == Task.GATHER else PERSON_COLOR
            leg_col = _darken(body_color, 0.6)

            pygame.draw.line(surface, leg_col, (isx - body_w, isy - leg_h), (isx - body_w, isy), iz)
            pygame.draw.line(surface, leg_col, (isx + body_w, isy - leg_h), (isx + body_w, isy), iz)
            pygame.draw.rect(surface, body_color,
                             (isx - body_w - iz, isy - leg_h - body_h,
                              body_w * 2 + iz * 2, body_h))

            head_y = isy - body_h - leg_h - head_r
            pygame.draw.circle(surface, PERSON_SKIN, (isx, head_y), head_r)
            pygame.draw.circle(surface, PERSON_HAIR, (isx, head_y - iz), head_r,
                               draw_top_left=True, draw_top_right=True)

            if person.task == Task.GATHER:
                pygame.draw.circle(surface, (200, 180, 60),
                                   (isx + head_r + iz, isy - leg_h - body_h),
                                   max(1, int(zoom * 1.5)))

            # HP bar over wounded colonists.
            max_h = getattr(person, "max_health", 0.0)
            cur_h = getattr(person, "health", 0.0)
            if max_h > 0 and cur_h < max_h and zoom >= 0.5:
                self._draw_hp_bar(
                    surface, sx, sy - body_h - leg_h - head_r * 2 - 2,
                    cur_h, max_h, max(8, int(8 * zoom)),
                )

    # ── Combat: enemies, projectiles, HP bars ────────────────────

    def _draw_combat(
        self, surface: pygame.Surface, world: World, camera: Camera,
    ) -> None:
        combat = getattr(world, "combat", None)
        if combat is None:
            return
        zoom = camera.zoom
        cam_x, cam_y = camera.x, camera.y
        sw, sh = surface.get_size()
        half_sw, half_sh = sw * 0.5, sh * 0.5

        # Per-type sprite resolution cache.  Avoids the per-enemy
        # f-string allocation and SpriteManager dict lookup that the
        # previous implementation paid for every enemy every frame.
        type_data_lookup = params.ENEMY_TYPE_DATA
        sprite_lookup: dict[str, object] = {}
        hp_bar_min_zoom = 0.4

        # Enemies.
        for enemy in combat.enemies:
            if enemy.dead:
                continue
            data = type_data_lookup.get(enemy.type_name)
            if data is None:
                continue
            sx = (enemy.px - cam_x) * zoom + half_sw
            sy = (enemy.py - cam_y) * zoom + half_sh
            if sx < -40 or sx > sw + 40 or sy < -40 or sy > sh + 40:
                continue

            type_name = enemy.type_name
            sheet = sprite_lookup.get(type_name, _MISSING_SENTINEL)
            if sheet is _MISSING_SENTINEL:
                sheet = sprites.get(f"enemies/{type_name.lower()}")
                sprite_lookup[type_name] = sheet

            radius_px = data["radius_px"]
            if sheet is not None:
                # Sprite blit fast path — inlined version of _try_sprite
                # without the per-call key string and dict lookup.
                r = max(4, int(radius_px * zoom))
                target_w = max(4, int(r * 2.8))
                bw, bh = sheet.base_size
                aspect = (bh / bw) if bw else 1.0
                target_h = max(4, int(target_w * aspect))
                img = sheet.get(target_w, target_h)
                surface.blit(
                    img,
                    (int(sx) - target_w // 2, int(sy) - target_h // 2),
                )
            else:
                draw_enemy(
                    surface, sx, sy,
                    type_name, data["color"], radius_px, zoom,
                )
            # HP bar over wounded enemies only.  Skipping the rect
            # triple draw on full-health enemies is a meaningful win
            # in big raids (3 rects \u00d7 hundreds of enemies / frame).
            if (enemy.max_health > 0 and enemy.health < enemy.max_health
                    and zoom >= hp_bar_min_zoom):
                bar_w = max(14, int(radius_px * 2.4 * zoom))
                self._draw_hp_bar(
                    surface, sx, sy - radius_px * zoom - 6,
                    enemy.health, enemy.max_health, bar_w,
                    fg=(220, 90, 90),
                )

        # Projectiles.
        for proj in combat.projectiles:
            sx1 = (proj.src_px - cam_x) * zoom + half_sw
            sy1 = (proj.src_py - cam_y) * zoom + half_sh
            # Where the bolt currently is.
            t = 0.0
            if proj.distance > 0:
                t = max(0.0, min(1.0, proj.travelled / proj.distance))
            cx = proj.src_px + (proj.dst_px - proj.src_px) * t
            cy = proj.src_py + (proj.dst_py - proj.src_py) * t
            scx = (cx - cam_x) * zoom + half_sw
            scy = (cy - cam_y) * zoom + half_sh
            # Trail
            tail_t = max(0.0, t - 0.18)
            tx = proj.src_px + (proj.dst_px - proj.src_px) * tail_t
            ty = proj.src_py + (proj.dst_py - proj.src_py) * tail_t
            stx = (tx - cam_x) * zoom + half_sw
            sty = (ty - cam_y) * zoom + half_sh
            pygame.draw.line(surface, proj.color,
                             (int(stx), int(sty)), (int(scx), int(scy)),
                             max(1, int(2 * zoom)))
            pygame.draw.circle(surface, proj.color,
                               (int(scx), int(scy)), max(2, int(2 * zoom)))

    def _draw_hp_bar(
        self, surface: pygame.Surface,
        cx: float, cy: float,
        cur: float, full: float, width: int,
        fg: tuple[int, int, int] = (90, 220, 110),
        bg: tuple[int, int, int] = (40, 40, 40),
    ) -> None:
        if full <= 0:
            return
        ratio = max(0.0, min(1.0, cur / full))
        h = max(4, width // 6)
        x = int(cx - width // 2)
        y = int(cy)
        pygame.draw.rect(surface, bg, (x, y, width, h))
        if ratio > 0:
            pygame.draw.rect(surface, fg, (x, y, int(width * ratio), h))
        pygame.draw.rect(surface, (0, 0, 0), (x, y, width, h), 1)

    # ── Selection highlight ──────────────────────────────────────

    def _draw_unreachable_markers(
        self, surface: pygame.Surface, world: World, camera: Camera,
    ) -> None:
        """Draw a red "!" above worker-buildings in networks with no
        populated houses (and therefore no workers that can reach them).
        """
        try:
            ids = world.unreachable_buildings()
        except AttributeError:
            return
        try:
            ids = ids | world.starved_producers()
        except AttributeError:
            pass
        if not ids:
            return
        zoom = camera.zoom
        cam_x, cam_y = camera.x, camera.y
        sw, sh = surface.get_size()
        half_sw, half_sh = sw * 0.5, sh * 0.5
        size = world.settings.hex_size
        font_size = max(20, int(32 * zoom))
        if font_size != self._unreach_font_size or self._unreach_glyph is None:
            font = pygame.font.Font(None, font_size)
            self._unreach_glyph = font.render("!", True, (255, 80, 80))
            self._unreach_shadow = font.render("!", True, (60, 0, 0))
            self._unreach_font_size = font_size
        glyph = self._unreach_glyph
        shadow = self._unreach_shadow
        gw, gh = glyph.get_width(), glyph.get_height()
        sw_g, sh_g = shadow.get_width(), shadow.get_height()
        for b in world.buildings.buildings:
            if id(b) not in ids:
                continue
            wx, wy = self._get_pixel(b.coord, size)
            sx = (wx - cam_x) * zoom + half_sw
            sy = (wy - cam_y) * zoom + half_sh - size * zoom * 1.1
            if sx < -30 or sx > sw + 30 or sy < -30 or sy > sh + 30:
                continue
            # Small circular badge behind the glyph for readability.
            r = max(10, int(14 * zoom))
            pygame.draw.circle(
                surface, (40, 0, 0), (int(sx), int(sy)), r + 1,
            )
            pygame.draw.circle(
                surface, (230, 60, 60), (int(sx), int(sy)), r,
            )
            pygame.draw.circle(
                surface, (140, 0, 0), (int(sx), int(sy)), r, width=2,
            )
            surface.blit(
                shadow,
                (int(sx) - sw_g // 2 + 1, int(sy) - sh_g // 2 + 1),
            )
            surface.blit(
                glyph,
                (int(sx) - gw // 2, int(sy) - gh // 2),
            )

    def _draw_hex_highlight(
        self, surface: pygame.Surface, coord: HexCoord,
        camera: Camera, size: int,
    ) -> None:
        wx, wy = self._get_pixel(coord, size)
        corners_world = self._get_corners(coord, wx, wy, size)
        zoom = camera.zoom
        cam_x, cam_y = camera.x, camera.y
        sw, sh = surface.get_size()
        half_sw, half_sh = sw * 0.5, sh * 0.5
        corners_screen = [
            ((cx - cam_x) * zoom + half_sw, (cy - cam_y) * zoom + half_sh)
            for cx, cy in corners_world
        ]

        pulse = 0.7 + 0.3 * math.sin(pygame.time.get_ticks() / 200)
        glow_color = (int(255 * pulse), int(255 * pulse), int(100 * pulse))
        pygame.draw.polygon(surface, glow_color, corners_screen, width=3)

        xs = [p[0] for p in corners_screen]
        ys = [p[1] for p in corners_screen]
        min_x, max_x = int(min(xs)) - 2, int(max(xs)) + 2
        min_y, max_y = int(min(ys)) - 2, int(max(ys)) + 2
        w = max_x - min_x
        h = max_y - min_y
        if w > 0 and h > 0:
            overlay = self._get_hex_overlay(w, h)
            shifted = [(px - min_x, py - min_y) for px, py in corners_screen]
            pygame.draw.polygon(overlay, (255, 255, 100, 30), shifted)
            surface.blit(overlay, (min_x, min_y), area=(0, 0, w, h))

    # ── Glowing path-placement preview ───────────────────────────

    def _draw_path_preview(
        self, surface: pygame.Surface, camera: Camera, size: int,
    ) -> None:
        """Draw a glowing-green overlay on every coord in path_preview."""
        zoom = camera.zoom
        cam_x, cam_y = camera.x, camera.y
        sw, sh = surface.get_size()
        half_sw, half_sh = sw * 0.5, sh * 0.5
        pulse = 0.5 + 0.5 * math.sin(pygame.time.get_ticks() / 250)
        fill_alpha = int(70 + 50 * pulse)
        edge_alpha = int(200 + 50 * pulse)
        fill_color = (90, 255, 120, fill_alpha)
        edge_color = (160, 255, 170, edge_alpha)
        edge_w = max(1, int(2 * zoom))
        for coord in self.path_preview:
            wx, wy = self._get_pixel(coord, size)
            corners_world = self._get_corners(coord, wx, wy, size)
            corners_screen = [
                ((cx - cam_x) * zoom + half_sw,
                 (cy - cam_y) * zoom + half_sh)
                for cx, cy in corners_world
            ]
            xs = [p[0] for p in corners_screen]
            ys = [p[1] for p in corners_screen]
            min_x, max_x = int(min(xs)) - 2, int(max(xs)) + 2
            min_y, max_y = int(min(ys)) - 2, int(max(ys)) + 2
            w = max_x - min_x
            h = max_y - min_y
            if w <= 0 or h <= 0:
                continue
            if max_x < 0 or max_y < 0 or min_x > sw or min_y > sh:
                continue
            overlay = self._get_hex_overlay(w, h)
            shifted = [(px - min_x, py - min_y) for px, py in corners_screen]
            pygame.draw.polygon(overlay, fill_color, shifted)
            pygame.draw.polygon(overlay, edge_color, shifted, width=edge_w)
            surface.blit(overlay, (min_x, min_y), area=(0, 0, w, h))

    # ── Alt resource overlay ─────────────────────────────────────

    def _draw_resource_overlay(
        self, surface: pygame.Surface, world: World, camera: Camera,
    ) -> None:
        """Colour-code every resource tile and building when Alt is held."""
        zoom = camera.zoom
        cam_x, cam_y = camera.x, camera.y
        sw, sh = surface.get_size()
        half_sw, half_sh = sw * 0.5, sh * 0.5
        size = world.settings.hex_size

        # Terrain overlay colours (semi-transparent per resource)
        _TERRAIN_OVERLAY: dict[Terrain, tuple[int, int, int, int]] = {
            Terrain.FOREST:        (100, 160, 60, 60),
            Terrain.DENSE_FOREST:  (100, 160, 60, 60),
            Terrain.STONE_DEPOSIT: (180, 180, 170, 60),
            Terrain.FIBER_PATCH:   (140, 220, 90, 60),
            Terrain.WATER:         (50, 100, 200, 40),
            Terrain.IRON_VEIN:     (180, 110, 75, 70),
            Terrain.COPPER_VEIN:   (80, 180, 120, 70),
            Terrain.OIL_DEPOSIT:   (0, 0, 0, 150),
        }
        _BUILDING_OVERLAY: dict[str, tuple[int, int, int, int]] = {
            "resource": (220, 160, 50, 70),
            "path":     (200, 180, 140, 50),
            "storage":  (160, 130, 100, 70),
            "housing":  (100, 160, 220, 70),
        }
        _RESOURCE_BUILDINGS = {BuildingType.WOODCUTTER, BuildingType.QUARRY, BuildingType.GATHERER}
        _HOUSING_BUILDINGS = {BuildingType.CAMP, BuildingType.HOUSE, BuildingType.HABITAT}

        # Spatial culling bounds
        half_world_w = (sw * 0.5) / zoom + size * 2
        half_world_h = (sh * 0.5) / zoom + size * 2
        r_lo = int((cam_y - half_world_h) / (1.5 * size)) - 1
        r_hi = int((cam_y + half_world_h) / (1.5 * size)) + 1

        for r in range(r_lo, r_hi + 1):
            q_lo = int((cam_x - half_world_w) / (size * _SQRT3) - r * 0.5) - 1
            q_hi = int((cam_x + half_world_w) / (size * _SQRT3) - r * 0.5) + 1
            for q in range(q_lo, q_hi + 1):
                coord = HexCoord(q, r)
                tile = world.grid.get(coord)
                if tile is None:
                    continue

                # Determine overlay colour
                overlay_col = None
                building = world.buildings.at(coord)
                if building is not None:
                    if building.type in _RESOURCE_BUILDINGS:
                        overlay_col = _BUILDING_OVERLAY["resource"]
                    elif building.type == BuildingType.PATH:
                        overlay_col = _BUILDING_OVERLAY["path"]
                    elif building.type == BuildingType.STORAGE:
                        overlay_col = _BUILDING_OVERLAY["storage"]
                    elif building.type in _HOUSING_BUILDINGS:
                        overlay_col = _BUILDING_OVERLAY["housing"]
                elif tile.terrain in _TERRAIN_OVERLAY:
                    overlay_col = _TERRAIN_OVERLAY[tile.terrain]

                if overlay_col is None:
                    continue

                wx, wy = self._get_pixel(coord, size)
                corners_world = self._get_corners(coord, wx, wy, size)
                corners_screen = [
                    ((cx - cam_x) * zoom + half_sw, (cy - cam_y) * zoom + half_sh)
                    for cx, cy in corners_world
                ]

                xs = [p[0] for p in corners_screen]
                ys = [p[1] for p in corners_screen]
                min_x, max_x = int(min(xs)) - 1, int(max(xs)) + 1
                min_y, max_y = int(min(ys)) - 1, int(max(ys)) + 1
                w = max_x - min_x
                h = max_y - min_y
                if w > 0 and h > 0:
                    ov = self._get_hex_overlay(w, h)
                    shifted = [(px - min_x, py - min_y) for px, py in corners_screen]
                    pygame.draw.polygon(ov, overlay_col, shifted)
                    surface.blit(ov, (min_x, min_y), area=(0, 0, w, h))

                # Building production / storage sprite overlay: draw a
                # large copy of the resource sprite this building is
                # producing (or storing) so the player can read the
                # production chain at a glance.
                if building is not None:
                    icon_res = None
                    if building.type == BuildingType.STORAGE:
                        icon_res = building.stored_resource
                    else:
                        icon_res = world._building_output(building)
                    if icon_res is not None:
                        icon_size = max(8, int(size * zoom * 1.1))
                        from compprog_pygame.games.hex_colony.resource_icons import (
                            get_resource_icon,
                        )
                        icon = get_resource_icon(icon_res, icon_size)
                        if icon is not None:
                            cx = (wx - cam_x) * zoom + half_sw
                            cy = (wy - cam_y) * zoom + half_sh
                            surface.blit(
                                icon,
                                (int(cx - icon.get_width() / 2),
                                 int(cy - icon.get_height() / 2)),
                            )

    # ── Ghost building preview ───────────────────────────────────

    def _draw_ghost_building(
        self, surface: pygame.Surface, world: World, camera: Camera,
    ) -> None:
        """Draw a semi-transparent building at ghost_coord with range ring."""
        coord = self.ghost_coord
        btype = self.ghost_building
        if coord is None or btype is None:
            return

        size = world.settings.hex_size
        zoom = camera.zoom
        cam_x, cam_y = camera.x, camera.y
        sw, sh = surface.get_size()
        half_sw, half_sh = sw * 0.5, sh * 0.5

        wx, wy = self._get_pixel(coord, size)
        sx = (wx - cam_x) * zoom + half_sw
        sy = (wy - cam_y) * zoom + half_sh
        r = int(size * 0.75 * zoom)
        if r < 2:
            return

        # Cache the ghost surface by (type, radius, valid) to avoid
        # creating new SRCALPHA surfaces every frame.
        cache_key = (btype, r, self.ghost_valid)
        if self._ghost_cache_key != cache_key:
            bld_size = r * 4
            bld_surf = pygame.Surface((bld_size, bld_size), pygame.SRCALPHA)
            cx_local = bld_size // 2
            cy_local = bld_size // 2
            if btype == BuildingType.CAMP:
                draw_camp(bld_surf, cx_local, cy_local, r, zoom)
            elif btype == BuildingType.HOUSE:
                draw_house(bld_surf, cx_local, cy_local, r, zoom)
            elif btype == BuildingType.HABITAT:
                draw_habitat(bld_surf, cx_local, cy_local, r, zoom)
            elif btype == BuildingType.WOODCUTTER:
                draw_woodcutter(bld_surf, cx_local, cy_local, r, zoom)
            elif btype == BuildingType.QUARRY:
                draw_quarry(bld_surf, cx_local, cy_local, r, zoom)
            elif btype == BuildingType.GATHERER:
                draw_gatherer(bld_surf, cx_local, cy_local, r, zoom)
            elif btype == BuildingType.STORAGE:
                draw_storage(bld_surf, cx_local, cy_local, r, zoom)
            elif btype == BuildingType.PATH:
                draw_path(bld_surf, cx_local, cy_local, r, zoom, [], coord.q, coord.r)
            elif btype == BuildingType.WORKSHOP:
                draw_workshop(bld_surf, cx_local, cy_local, r, zoom)
            elif btype == BuildingType.FORGE:
                draw_forge(bld_surf, cx_local, cy_local, r, zoom)
            elif btype == BuildingType.ASSEMBLER:
                draw_assembler(bld_surf, cx_local, cy_local, r, zoom)
            elif btype == BuildingType.RESEARCH_CENTER:
                draw_research_center(bld_surf, cx_local, cy_local, r, zoom)
            elif btype == BuildingType.MINING_MACHINE:
                draw_mining_machine(bld_surf, cx_local, cy_local, r, zoom)
            elif btype == BuildingType.FARM:
                draw_farm(bld_surf, cx_local, cy_local, r, zoom)
            elif btype == BuildingType.WELL:
                draw_well(bld_surf, cx_local, cy_local, r, zoom)
            elif btype == BuildingType.WALL:
                draw_wall(bld_surf, cx_local, cy_local, r, zoom, [], coord.q, coord.r)
            elif btype == BuildingType.REFINERY:
                draw_refinery(bld_surf, cx_local, cy_local, r, zoom)
            elif btype == BuildingType.BRIDGE:
                draw_bridge(bld_surf, cx_local, cy_local, r, zoom, [], coord.q, coord.r)
            elif btype == BuildingType.CHEMICAL_PLANT:
                draw_chemical_plant(bld_surf, cx_local, cy_local, r, zoom)
            elif btype == BuildingType.CONVEYOR:
                draw_conveyor(bld_surf, cx_local, cy_local, r, zoom)
            elif btype == BuildingType.SOLAR_ARRAY:
                draw_solar_array(bld_surf, cx_local, cy_local, r, zoom)
            elif btype == BuildingType.ROCKET_SILO:
                draw_rocket_silo(bld_surf, cx_local, cy_local, r, zoom)
            elif btype == BuildingType.OIL_DRILL:
                draw_oil_drill(bld_surf, cx_local, cy_local, r, zoom)
            elif btype == BuildingType.OIL_REFINERY:
                draw_oil_refinery(bld_surf, cx_local, cy_local, r, zoom)
            elif btype == BuildingType.PIPE:
                draw_pipe(bld_surf, cx_local, cy_local, r, zoom, [], coord.q, coord.r)
            elif btype == BuildingType.FLUID_TANK:
                draw_fluid_tank(bld_surf, cx_local, cy_local, r, zoom)
            elif btype == BuildingType.TURRET:
                draw_turret(bld_surf, cx_local, cy_local, r, zoom)
            elif btype == BuildingType.TRAP:
                draw_trap(bld_surf, cx_local, cy_local, r, zoom)

            if not self.ghost_valid:
                red_tint = pygame.Surface((bld_size, bld_size), pygame.SRCALPHA)
                red_tint.fill((255, 60, 60, 100))
                bld_surf.blit(red_tint, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
                red_overlay = pygame.Surface((bld_size, bld_size), pygame.SRCALPHA)
                red_overlay.fill((255, 50, 50, 80))
                bld_surf.blit(red_overlay, (0, 0))

            bld_surf.set_alpha(140 if self.ghost_valid else 100)
            self._ghost_cache = bld_surf
            self._ghost_cache_key = cache_key

        bld_size = r * 4
        cx_local = bld_size // 2
        cy_local = bld_size // 2
        surface.blit(self._ghost_cache, (int(sx) - cx_local, int(sy) - cy_local))

        # Range ring for collection buildings (only when valid)
        if self.ghost_valid and btype in _COLLECTION_BUILDINGS:
            self._draw_range_ring(surface, coord, camera, size)

    # ── Resource collection range ring ───────────────────────────

    def _draw_range_ring(
        self, surface: pygame.Surface, center: HexCoord,
        camera: Camera, size: int,
    ) -> None:
        """Draw a white pulsing outline around all hexes within 2-tile radius."""
        zoom = camera.zoom
        cam_x, cam_y = camera.x, camera.y
        sw, sh = surface.get_size()
        half_sw, half_sh = sw * 0.5, sh * 0.5

        pulse = 0.6 + 0.4 * math.sin(pygame.time.get_ticks() / 250)
        ring_color = (int(255 * pulse), int(255 * pulse), int(255 * pulse))


        # Collect all hex coords within radius 2
        ring_coords: list[HexCoord] = []
        for dq in range(-2, 3):
            for dr in range(-2, 3):
                ds = -dq - dr
                if abs(dq) + abs(dr) + abs(ds) <= 4:  # hex distance <= 2
                    ring_coords.append(HexCoord(center.q + dq, center.r + dr))

        # Find outer edges: edges of ring hexes that don't border another ring hex
        ring_set = set(ring_coords)
        line_w = max(2, int(2 * zoom))
        for coord in ring_coords:
            wx, wy = self._get_pixel(coord, size)
            corners_world = self._get_corners(coord, wx, wy, size)
            corners_screen = [
                ((cx - cam_x) * zoom + half_sw, (cy - cam_y) * zoom + half_sh)
                for cx, cy in corners_world
            ]
            for d in range(6):
                nb = coord.neighbor(d)
                if nb not in ring_set:
                    # This edge is on the boundary — use DIR_EDGE mapping
                    i1, i2 = DIR_EDGE[d]
                    pygame.draw.line(
                        surface, ring_color,
                        (int(corners_screen[i1][0]), int(corners_screen[i1][1])),
                        (int(corners_screen[i2][0]), int(corners_screen[i2][1])),
                        line_w,
                    )



