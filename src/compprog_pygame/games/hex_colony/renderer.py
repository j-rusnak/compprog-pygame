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
from functools import lru_cache

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
    OverlayGrassTuft,
    OverlayItem,
    OverlayRipple,
    OverlayRock,
    OverlayTree,
    build_overlays,
)
from compprog_pygame.games.hex_colony.people import Task
from compprog_pygame.games.hex_colony.resources import Resource
from compprog_pygame.games.hex_colony.world import World

# ── Colour palette ───────────────────────────────────────────────

BACKGROUND = (9, 12, 25)

TERRAIN_BASE_COLOR: dict[Terrain, tuple[int, int, int]] = {
    Terrain.GRASS:         (82, 148, 64),
    Terrain.FOREST:        (38, 105, 38),
    Terrain.DENSE_FOREST:  (20, 72, 24),
    Terrain.STONE_DEPOSIT: (142, 142, 132),
    Terrain.WATER:         (38, 85, 175),
    Terrain.FIBER_PATCH:   (115, 155, 58),
    Terrain.MOUNTAIN:      (110, 100, 90),
}

# Blending weight for neighbor influence (0 = no blend, 1 = full average)
_BLEND_STRENGTH = 0.45

# Bank colour tinted toward water-adjacent tiles
_BANK_COLOR = (148, 138, 105)  # sandy/muddy

# Tile-layer cache: pre-render tiles + static overlays to an off-screen
# surface sized at ``_TILE_LAYER_PAD`` \u00d7 the screen dimensions.
_TILE_LAYER_PAD = 2.0
_SQRT3 = 1.7320508075688772

# Intra-tile gradient: how much edge sub-triangles blend toward the neighbor
_EDGE_BLEND = 0.38

# Terrain categories — hard borders between these three groups.
# 0 = grass-type, 1 = water, 2 = rocky
_TERRAIN_CAT: dict[Terrain, int] = {
    Terrain.GRASS: 0,
    Terrain.FOREST: 0,
    Terrain.DENSE_FOREST: 0,
    Terrain.FIBER_PATCH: 0,
    Terrain.WATER: 1,
    Terrain.MOUNTAIN: 2,
    Terrain.STONE_DEPOSIT: 2,
}

BUILDING_COLORS: dict[BuildingType, tuple[int, int, int]] = {
    BuildingType.CAMP: (200, 160, 60),
    BuildingType.HOUSE: (170, 140, 90),
    BuildingType.PATH: (185, 165, 120),
    BuildingType.WOODCUTTER: (160, 100, 50),
    BuildingType.QUARRY: (170, 170, 160),
    BuildingType.GATHERER: (100, 180, 80),
    BuildingType.STORAGE: (140, 120, 100),
}

_PATH_BASE = (185, 165, 120)
_PATH_DARK = (155, 135, 95)
_PATH_LIGHT = (205, 190, 150)

PERSON_COLOR = (230, 210, 170)
PERSON_GATHER_COLOR = (180, 220, 120)
PERSON_SKIN = (220, 185, 140)
PERSON_HAIR = (80, 55, 30)

HUD_BG = (16, 24, 45, 220)
HUD_TEXT = (242, 244, 255)
MUTED_TEXT = (140, 150, 175)
HUD_ACCENT = (200, 160, 60)
HUD_BORDER = (60, 70, 100)

RESOURCE_ICONS: dict[Resource, str] = {
    Resource.WOOD: "\u25b2",
    Resource.FIBER: "\u2022",
    Resource.STONE: "\u25a0",
    Resource.FOOD: "\u2665",
}

RESOURCE_COLORS: dict[Resource, tuple[int, int, int]] = {
    Resource.WOOD: (160, 100, 50),
    Resource.FIBER: (120, 200, 80),
    Resource.STONE: (170, 170, 160),
    Resource.FOOD: (220, 100, 80),
}


# ── Renderer ─────────────────────────────────────────────────────

class Renderer:
    """Draws the entire game scene."""

    def __init__(self) -> None:
        self.font = pygame.font.Font(None, 22)
        self.hud_font = pygame.font.Font(None, 28)
        self.hud_title_font = pygame.font.Font(None, 34)
        self.small_font = pygame.font.Font(None, 18)
        self.selected_hex: HexCoord | None = None
        self._water_tick: float = 0.0

        # Caches
        self._pixel_cache: dict[HexCoord, tuple[float, float]] = {}
        self._corner_cache: dict[HexCoord, list[tuple[float, float]]] = {}
        self._overlays: list[OverlayItem] | None = None
        self._mountain_depths: dict[HexCoord, tuple[int, int]] = {}
        self._blended_colors: dict[HexCoord, tuple[int, int, int]] = {}
        self._hud_panel: pygame.Surface | None = None
        self._hud_panel_size: tuple[int, int] = (0, 0)
        self._bar_surf: pygame.Surface | None = None
        self._bar_surf_w: int = 0
        self._hud_cache_key: tuple = ()
        self._hud_text_surfs: dict[str, pygame.Surface] = {}

        # Tile layer cache (tiles + static overlays, pre-rendered)
        self._tile_layer: pygame.Surface | None = None
        self._tl_zoom: float = -1.0
        self._tl_cam: tuple[float, float] = (0.0, 0.0)
        self._tl_screen: tuple[int, int] = (0, 0)
        self._ripples: list[OverlayRipple] = []
        self._static_overlays: list[OverlayItem] = []
        self._edge_colors: dict[HexCoord, list[tuple[int, int, int]]] = {}
        self._cross_cat: dict[HexCoord, list[int]] = {}  # 0=same category, 2=cross-category: use own colour

    # ── Cache helpers ────────────────────────────────────────────

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
        self._ensure_data(world)
        surface.fill(BACKGROUND)
        self._blit_tile_layer(surface, world, camera)
        self._draw_ripples(surface, camera, world.settings.hex_size)
        self._draw_buildings(surface, world, camera)
        self._draw_people(surface, world, camera)
        if self.selected_hex is not None:
            self._draw_hex_highlight(surface, self.selected_hex, camera, world.settings.hex_size)

    # ── Data preparation ─────────────────────────────────────────

    def _ensure_data(self, world: World) -> None:
        """Build overlays, blended colours, and overlay split on first call."""
        if self._overlays is None:
            self._overlays, self._mountain_depths = build_overlays(
                world.grid, world.settings.hex_size,
            )
            self._static_overlays = [
                item for item in self._overlays
                if not isinstance(item, OverlayRipple)
            ]
            self._ripples = [
                item for item in self._overlays
                if isinstance(item, OverlayRipple)
            ]
        self._ensure_blended_colors(world)

    # ── Blended tile colours (two-pass smoothing) ────────────────

    def _ensure_blended_colors(self, world: World) -> None:
        """Pre-compute blended tile colours with two-pass smoothing."""
        if self._blended_colors:
            return
        grid = world.grid
        mtn = self._mountain_depths

        # ── First pass: base blending with neighbours ────────────
        first_pass: dict[HexCoord, tuple[int, int, int]] = {}
        for tile in grid.tiles():
            coord = tile.coord
            mtn_info = mtn.get(coord)
            if mtn_info is not None:
                base = _mountain_tile_color(*mtn_info)
            else:
                base = TERRAIN_BASE_COLOR.get(tile.terrain, (80, 80, 80))

            th = _tile_hash(coord.q, coord.r)
            var = ((th & 0xFF) - 128) / 128.0 * 6  # ±6 per channel
            base = (
                max(0, min(255, int(base[0] + var))),
                max(0, min(255, int(base[1] + var * 0.8))),
                max(0, min(255, int(base[2] + var * 0.6))),
            )

            nb_r, nb_g, nb_b = 0, 0, 0
            nb_count = 0
            is_water_adjacent = False
            my_cat = _TERRAIN_CAT[tile.terrain]
            for nb_coord in coord.neighbors():
                nb_tile = grid.get(nb_coord)
                if nb_tile is None:
                    continue
                nb_cat = _TERRAIN_CAT[nb_tile.terrain]
                # Hard category border: only blend within same category
                if my_cat != nb_cat:
                    if nb_cat == 1 and my_cat != 1:
                        is_water_adjacent = True
                    continue
                nb_mtn = mtn.get(nb_coord)
                if nb_mtn is not None:
                    nc = _mountain_tile_color(*nb_mtn)
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
                bk = 0.2 + ((th >> 10) & 0xF) / 15.0 * 0.15  # 0.20–0.35
                blended = (
                    int(blended[0] * (1 - bk) + _BANK_COLOR[0] * bk),
                    int(blended[1] * (1 - bk) + _BANK_COLOR[1] * bk),
                    int(blended[2] * (1 - bk) + _BANK_COLOR[2] * bk),
                )

            first_pass[coord] = blended

        # ── Second pass: smooth first-pass colours across neighbours
        _SMOOTH2 = 0.30
        for tile in grid.tiles():
            coord = tile.coord
            base = first_pass[coord]
            my_cat = _TERRAIN_CAT[tile.terrain]
            nb_r, nb_g, nb_b = 0, 0, 0
            nb_count = 0
            for nb_coord in coord.neighbors():
                nb_c = first_pass.get(nb_coord)
                if nb_c is None:
                    continue
                # Hard category border in second pass too
                nb_tile = grid.get(nb_coord)
                if nb_tile is not None and _TERRAIN_CAT[nb_tile.terrain] != my_cat:
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

        # ── Precompute per-edge colours for intra-tile gradients ──
        bc = self._blended_colors
        eb = _EDGE_BLEND
        eb1 = 1.0 - eb
        for tile in grid.tiles():
            coord = tile.coord
            cc = bc[coord]
            my_cat = _TERRAIN_CAT[tile.terrain]
            edge_cols: list[tuple[int, int, int]] = []
            cross_flags: list[int] = []  # 0=same, 2=cross-cat (own colour)
            for nb_coord in coord.neighbors():
                nc = bc.get(nb_coord)
                if nc is not None:
                    nb_tile = grid.get(nb_coord)
                    nb_cat = _TERRAIN_CAT[nb_tile.terrain] if nb_tile else my_cat
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

    # ── Tile-layer cache ─────────────────────────────────────────

    def _blit_tile_layer(
        self, surface: pygame.Surface, world: World, camera: Camera,
    ) -> None:
        """Blit the cached tile+overlay surface; rebuild when stale."""
        sw, sh = surface.get_size()
        zoom = camera.zoom
        cam_x, cam_y = camera.x, camera.y

        need_rebuild = (
            self._tile_layer is None
            or self._tl_screen != (sw, sh)
            or self._tl_zoom != zoom
        )
        if not need_rebuild:
            dx = abs(cam_x - self._tl_cam[0]) * zoom
            dy = abs(cam_y - self._tl_cam[1]) * zoom
            pad_x = sw * (_TILE_LAYER_PAD - 1) * 0.5
            pad_y = sh * (_TILE_LAYER_PAD - 1) * 0.5
            if dx > pad_x or dy > pad_y:
                need_rebuild = True

        if need_rebuild:
            self._rebuild_tile_layer(world, camera, sw, sh)

        cw, ch = self._tile_layer.get_size()
        src_x = int((cam_x - self._tl_cam[0]) * zoom + cw * 0.5 - sw * 0.5)
        src_y = int((cam_y - self._tl_cam[1]) * zoom + ch * 0.5 - sh * 0.5)
        src_x = max(0, min(src_x, cw - sw))
        src_y = max(0, min(src_y, ch - sh))
        surface.blit(self._tile_layer, (0, 0), (src_x, src_y, sw, sh))

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

        lod_high = zoom > 0.45
        lod_mid = not lod_high and zoom >= 0.25

        # Spatial culling: iterate only hex coords within cache bounds
        half_world_w = half_cw / zoom + size * 2
        half_world_h = half_ch / zoom + size * 2

        r_lo = int((cam_y - half_world_h) / (1.5 * size)) - 1
        r_hi = int((cam_y + half_world_h) / (1.5 * size)) + 1

        for r in range(r_lo, r_hi + 1):
            q_lo = int((cam_x - half_world_w) / (size * _SQRT3) - r * 0.5) - 1
            q_hi = int((cam_x + half_world_w) / (size * _SQRT3) - r * 0.5) + 1
            for q in range(q_lo, q_hi + 1):
                coord = HexCoord(q, r)
                tile = grid.get(coord)
                if tile is None:
                    continue

                wx, wy = self._get_pixel(coord, size)
                corners_world = self._get_corners(coord, wx, wy, size)
                corners = [
                    ((cx - cam_x) * zoom + half_cw,
                     (cy - cam_y) * zoom + half_ch)
                    for cx, cy in corners_world
                ]

                base = blended.get(coord, (80, 80, 80))

                if lod_high:
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
                            i1 = _DIR_EDGE[d][0]
                            i2 = _DIR_EDGE[d][1]
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

                # Mountain ridge spurs (skip at very low zoom)
                if lod_high or lod_mid:
                    mtn_info = mtn.get(coord)
                    if mtn_info is not None and mtn_info[0] > 0:
                        _draw_contours(
                            cache, coord, mtn_info[0], corners,
                            base, mtn, zoom,
                        )

        # Static overlays (skip entirely when zoom < 0.25)
        if lod_high or lod_mid:
            margin = size * 16 * zoom
            stride = 1 if lod_high else 2
            for idx in range(0, len(self._static_overlays), stride):
                item = self._static_overlays[idx]
                sx = (item.wx - cam_x) * zoom + half_cw
                sy = (item.wy - cam_y) * zoom + half_ch
                if sx < -margin or sx > cw + margin or sy < -margin or sy > ch + margin:
                    continue
                iz = max(1, int(zoom))
                if isinstance(item, OverlayTree):
                    _draw_tree(cache, item, sx, sy, zoom, iz)
                elif isinstance(item, OverlayRock):
                    _draw_rock(cache, item, sx, sy, zoom, iz)
                elif isinstance(item, OverlayBush):
                    _draw_bush(cache, item, sx, sy, zoom, iz)
                elif isinstance(item, OverlayGrassTuft):
                    _draw_grass(cache, item, sx, sy, zoom, iz)

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
            sx = (item.wx - cam_x) * zoom + half_sw
            sy = (item.wy - cam_y) * zoom + half_sh
            if sx < -margin or sx > sw + margin or sy < -margin or sy > sh + margin:
                continue
            iz = max(1, int(zoom))
            _draw_ripple(surface, item, sx, sy, zoom, iz, tick)

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

        # First pass: paths (ground-level, drawn beneath other buildings)
        for building in world.buildings.buildings:
            if building.type != BuildingType.PATH:
                continue
            wx, wy = self._get_pixel(building.coord, size)
            sx = (wx - cam_x) * zoom + half_sw
            sy = (wy - cam_y) * zoom + half_sh
            if sx < -margin or sx > sw + margin or sy < -margin or sy > sh + margin:
                continue
            r = int(size * 0.75 * zoom)
            if r < 2:
                pygame.draw.circle(surface, _PATH_BASE, (int(sx), int(sy)), max(1, r))
                continue
            # Compute screen positions of adjacent path neighbours
            nb_positions: list[tuple[float, float]] = []
            for nb_coord in building.coord.neighbors():
                nb_building = world.buildings.at(nb_coord)
                if nb_building is not None and nb_building.type == BuildingType.PATH:
                    nwx, nwy = self._get_pixel(nb_coord, size)
                    nsx = (nwx - cam_x) * zoom + half_sw
                    nsy = (nwy - cam_y) * zoom + half_sh
                    nb_positions.append((nsx, nsy))
            _draw_path(surface, sx, sy, r, zoom, nb_positions,
                       building.coord.q, building.coord.r)

        # Second pass: non-path buildings
        for building in world.buildings.buildings:
            if building.type == BuildingType.PATH:
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

            if building.type == BuildingType.CAMP:
                _draw_camp(surface, sx, sy, r, zoom)
            elif building.type == BuildingType.HOUSE:
                _draw_house(surface, sx, sy, r, zoom)
            elif building.type == BuildingType.WOODCUTTER:
                _draw_woodcutter(surface, sx, sy, r, zoom)
            elif building.type == BuildingType.QUARRY:
                _draw_quarry(surface, sx, sy, r, zoom)
            elif building.type == BuildingType.GATHERER:
                _draw_gatherer(surface, sx, sy, r, zoom)
            elif building.type == BuildingType.STORAGE:
                _draw_storage(surface, sx, sy, r, zoom)

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

    # ── Selection highlight ──────────────────────────────────────

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
            overlay = pygame.Surface((w, h), pygame.SRCALPHA)
            shifted = [(px - min_x, py - min_y) for px, py in corners_screen]
            pygame.draw.polygon(overlay, (255, 255, 100, 30), shifted)
            surface.blit(overlay, (min_x, min_y))

    # ── HUD ──────────────────────────────────────────────────────

    def _draw_hud(self, surface: pygame.Surface, world: World) -> None:
        x, y = 10, 10
        line_h = 28
        inv = world.inventory

        panel_w = 220
        panel_h = line_h * (len(Resource) + 3) + 20
        needed = (panel_w, panel_h)
        if self._hud_panel is None or self._hud_panel_size != needed:
            self._hud_panel = pygame.Surface((panel_w, panel_h), pygame.SRCALPHA)
            self._hud_panel.fill(HUD_BG)
            self._hud_panel_size = needed
        surface.blit(self._hud_panel, (x, y))

        panel_rect = pygame.Rect(x, y, panel_w, panel_h)
        pygame.draw.rect(surface, HUD_BORDER, panel_rect, width=2, border_radius=4)
        pygame.draw.line(surface, HUD_ACCENT, (x, y), (x + panel_w, y), 2)

        res_vals = tuple(int(inv[r]) for r in Resource)
        cache_key = (world.population.count, res_vals)

        if cache_key != self._hud_cache_key:
            self._hud_cache_key = cache_key
            ts = self._hud_text_surfs
            ts["title"] = self.hud_title_font.render("Colony", True, HUD_TEXT)
            ts["pop_icon"] = self.font.render("\u263a", True, PERSON_COLOR)
            ts["pop_text"] = self.font.render(f"Population: {world.population.count}", True, HUD_TEXT)
            for res in Resource:
                ts[f"icon_{res.name}"] = self.font.render(RESOURCE_ICONS[res], True, RESOURCE_COLORS[res])
                ts[f"val_{res.name}"] = self.font.render(
                    f"{res.name.capitalize()}: {inv[res]:.0f}", True, HUD_TEXT
                )

        ts = self._hud_text_surfs
        title = ts["title"]
        surface.blit(title, (x + 10, y + 6))
        ty = y + 6 + title.get_height() + 2
        pygame.draw.line(surface, HUD_ACCENT, (x + 10, ty), (x + panel_w - 10, ty), 1)
        y = ty + 6

        surface.blit(ts["pop_icon"], (x + 10, y))
        surface.blit(ts["pop_text"], (x + 28, y))
        y += line_h

        for res in Resource:
            surface.blit(ts[f"icon_{res.name}"], (x + 10, y))
            surface.blit(ts[f"val_{res.name}"], (x + 28, y))
            y += line_h

        if self.selected_hex is not None:
            tile = world.grid.get(self.selected_hex)
            if tile:
                sw, sh = surface.get_size()
                bar_h = 32
                if self._bar_surf is None or self._bar_surf_w != sw:
                    self._bar_surf = pygame.Surface((sw, bar_h), pygame.SRCALPHA)
                    self._bar_surf.fill((16, 24, 45, 200))
                    self._bar_surf_w = sw
                surface.blit(self._bar_surf, (0, sh - bar_h))
                pygame.draw.line(surface, HUD_ACCENT, (0, sh - bar_h), (sw, sh - bar_h), 1)

                info_parts = [f"Hex ({tile.coord.q},{tile.coord.r})", tile.terrain.name]
                building = world.buildings.at(self.selected_hex)
                if building:
                    info_parts.append(building.type.name)
                info = "  \u2502  ".join(info_parts)
                info_surf = self.font.render(info, True, MUTED_TEXT)
                surface.blit(info_surf, (sw // 2 - info_surf.get_width() // 2, sh - bar_h + 6))


# ── Free-function overlay renderers ─────────────────────────────
# Pulled out of the class so they carry no `self` overhead and can be
# referenced as plain function pointers for clarity.

def _draw_tree(
    surface: pygame.Surface, item: OverlayTree,
    sx: float, sy: float, z: float, iz: int,
) -> None:
    if item.style == "canopy":
        crx = max(3, int(item.crown_rx * z))
        cry = max(2, int(item.crown_ry * z))
        th = max(2, int(item.trunk_h * z))
        tw = max(1, int(2 * z))
        # Shadow
        sh_rx, sh_ry = max(2, crx // 2), max(1, cry // 4)
        pygame.draw.ellipse(
            surface, (10, 30, 10),
            (int(sx - sh_rx), int(sy + iz), sh_rx * 2, sh_ry * 2),
        )
        # Trunk
        pygame.draw.line(surface, item.trunk_color,
                         (int(sx), int(sy)), (int(sx), int(sy - th)), tw)
        # Crown
        cy_top = int(sy - th - cry)
        pygame.draw.ellipse(
            surface, item.crown_color,
            (int(sx - crx), cy_top, crx * 2, cry * 2),
        )
        # Highlight
        hl_rx = max(1, crx // 2)
        hl_ry = max(1, int(cry * 0.6))
        pygame.draw.ellipse(
            surface, item.highlight_color,
            (int(sx - crx * 0.6), int(cy_top + cry * 0.15), hl_rx * 2, hl_ry * 2),
        )
    elif item.style == "conifer":
        crx = max(2, int(item.crown_rx * z))
        cry = max(3, int(item.crown_ry * z * 1.3))
        th = max(1, int(item.trunk_h * z))
        pygame.draw.line(surface, item.trunk_color,
                         (int(sx), int(sy)), (int(sx), int(sy - th)), max(1, int(z)))
        top_y = int(sy - th - cry)
        pts = [(int(sx), top_y), (int(sx - crx), int(sy - th)), (int(sx + crx), int(sy - th))]
        pygame.draw.polygon(surface, item.crown_color, pts)
        hl_pts = [
            (int(sx), top_y),
            (int(sx - crx * 0.4), int(sy - th - cry * 0.35)),
            (int(sx), int(sy - th)),
        ]
        pygame.draw.polygon(surface, item.highlight_color, hl_pts)
    else:
        cr = max(2, int(item.crown_rx * z))
        th = max(1, int(item.trunk_h * z))
        pygame.draw.line(surface, item.trunk_color,
                         (int(sx), int(sy)), (int(sx), int(sy - th)), max(1, int(z)))
        head_y = int(sy - th - cr)
        pygame.draw.circle(surface, item.crown_color, (int(sx), head_y), cr)
        hl_r = max(1, cr // 2)
        pygame.draw.circle(surface, item.highlight_color, (int(sx) - iz, head_y - iz), hl_r)


def _draw_rock(
    surface: pygame.Surface, item: OverlayRock,
    sx: float, sy: float, z: float, iz: int,
) -> None:
    rw = max(2, int(item.w * z))
    rh = max(2, int(item.h * z))
    pts = [
        (int(sx - rw), int(sy + rh // 2)),
        (int(sx - rw // 2), int(sy - rh)),
        (int(sx + rw // 2), int(sy - rh)),
        (int(sx + rw), int(sy + rh // 2)),
    ]
    pygame.draw.polygon(surface, item.color, pts)
    pygame.draw.line(surface, item.highlight_color, pts[1], pts[2], iz)
    pygame.draw.line(surface, _darken(item.color, 0.6), pts[3], pts[0], iz)


def _draw_ripple(
    surface: pygame.Surface, item: OverlayRipple,
    sx: float, sy: float, z: float, iz: int, tick: float,
) -> None:
    phase = tick * 1.5
    offset = math.sin(phase + item.phase_offset) * 2 * z
    px = int(sx + offset)
    py = int(sy)
    w = max(2, int(item.w * z))
    # Vary colour slightly per ripple for depth
    bright = 0.85 + 0.15 * math.sin(item.phase_offset)
    col = (int(55 * bright), int(115 * bright), int(215 * bright))
    pygame.draw.line(surface, col, (px - w, py), (px + w, py), iz)
    # Faint highlight above
    if z > 0.5:
        hl = (int(80 * bright), int(145 * bright), int(230 * bright))
        pygame.draw.line(surface, hl, (px - w + iz, py - iz), (px + w - iz, py - iz), max(1, iz - 1))


def _draw_bush(
    surface: pygame.Surface, item: OverlayBush,
    sx: float, sy: float, z: float, iz: int,
) -> None:
    br = max(2, int(item.radius * z))
    pygame.draw.circle(surface, item.color, (int(sx), int(sy)), br)
    if item.berry_color is not None:
        pygame.draw.circle(surface, item.berry_color, (int(sx) + iz, int(sy) - iz), iz)


def _draw_grass(
    surface: pygame.Surface, item: OverlayGrassTuft,
    sx: float, sy: float, z: float, iz: int,
) -> None:
    h = max(1, int(item.h * z))
    px, py = int(sx), int(sy)
    # Two blades at slight angles for a more natural look
    pygame.draw.line(surface, item.color, (px, py), (px + iz, py - h), iz)
    if h > 1:
        darker = _darken(item.color, 0.85)
        pygame.draw.line(surface, darker, (px, py), (px - iz, py - max(1, h - 1)), iz)


# ── Building renderers ──────────────────────────────────────────

def _draw_camp(surface: pygame.Surface, sx: float, sy: float, r: int, z: float) -> None:
    iz = max(1, int(z))
    tent_col = (180, 150, 80)
    pts = [(sx, sy - r * 0.9), (sx - r * 0.85, sy + r * 0.5), (sx + r * 0.85, sy + r * 0.5)]
    pygame.draw.polygon(surface, tent_col, pts)
    left_pts = [pts[0], pts[1], (sx, sy + r * 0.5)]
    pygame.draw.polygon(surface, _lighten(tent_col, 1.2), left_pts)
    pygame.draw.polygon(surface, _darken(tent_col, 0.6), pts, iz)
    door_w = max(2, int(r * 0.3))
    door_h = max(3, int(r * 0.4))
    pygame.draw.rect(surface, (60, 40, 20),
                     (int(sx - door_w // 2), int(sy + r * 0.5 - door_h), door_w, door_h))
    fire_x, fire_y = int(sx + r * 0.6), int(sy + r * 0.3)
    fr = max(1, int(2 * z))
    pygame.draw.circle(surface, (220, 120, 20), (fire_x, fire_y), fr + iz)
    pygame.draw.circle(surface, (255, 200, 50), (fire_x, fire_y - iz), fr)
    fx, fy = int(sx), int(sy - r * 0.9)
    pole_h = max(2, int(4 * z))
    pygame.draw.line(surface, (120, 80, 40), (fx, fy), (fx, fy - pole_h), iz)
    flag_pts = [(fx, fy - pole_h), (fx + pole_h, fy - max(1, int(2 * z))), (fx, fy - iz)]
    pygame.draw.polygon(surface, (200, 50, 50), flag_pts)


def _draw_house(surface: pygame.Surface, sx: float, sy: float, r: int, z: float) -> None:
    """Teepee / hut — conical tent with hide covering and smoke hole."""
    iz = max(1, int(z))
    hide_col = (155, 130, 85)
    hide_dark = _darken(hide_col, 0.75)

    # Main cone (wider than camp tent)
    apex_y = sy - r * 0.95
    base_y = sy + r * 0.55
    lx = sx - r * 0.7
    rx = sx + r * 0.7

    # Right half (shaded)
    right_pts = [(sx, apex_y), (sx, base_y), (rx, base_y)]
    pygame.draw.polygon(surface, hide_dark, right_pts)
    # Left half (lit)
    left_pts = [(sx, apex_y), (lx, base_y), (sx, base_y)]
    pygame.draw.polygon(surface, hide_col, left_pts)
    # Outline
    full_pts = [(sx, apex_y), (lx, base_y), (rx, base_y)]
    pygame.draw.polygon(surface, _darken(hide_col, 0.5), full_pts, iz)

    # Support poles poking above
    pole_col = (110, 80, 45)
    for dx in (-0.12, 0.0, 0.12):
        px = int(sx + r * dx)
        pygame.draw.line(surface, pole_col,
                         (px, int(apex_y)), (px, int(apex_y - r * 0.2)), iz)

    # Decorative band around middle
    band_y = int(sy - r * 0.2)
    pygame.draw.line(surface, (180, 80, 50),
                     (int(lx + r * 0.15), band_y), (int(rx - r * 0.15), band_y), max(1, iz))

    # Door opening
    door_w = max(2, int(r * 0.25))
    door_h = max(3, int(r * 0.35))
    door_pts = [
        (sx, base_y - door_h),
        (sx - door_w, base_y),
        (sx + door_w, base_y),
    ]
    pygame.draw.polygon(surface, (50, 35, 18), door_pts)


def _draw_woodcutter(surface: pygame.Surface, sx: float, sy: float, r: int, z: float) -> None:
    iz = max(1, int(z))
    cabin = (140, 90, 45)
    rect = pygame.Rect(int(sx - r * 0.55), int(sy - r * 0.3), int(r * 1.1), int(r * 0.7))
    pygame.draw.rect(surface, cabin, rect)
    pygame.draw.rect(surface, _lighten(cabin, 1.2), pygame.Rect(rect.x, rect.y, rect.w, max(1, int(2 * z))))
    pygame.draw.rect(surface, _darken(cabin, 0.6), rect, iz)
    for i in range(1, 4):
        ly = rect.y + i * rect.h // 4
        pygame.draw.line(surface, _darken(cabin, 0.7), (rect.x, ly), (rect.right, ly), iz)
    roof_col = (100, 60, 30)
    roof_pts = [(sx - r * 0.65, sy - r * 0.3), (sx, sy - r * 0.75), (sx + r * 0.65, sy - r * 0.3)]
    pygame.draw.polygon(surface, roof_col, roof_pts)
    pygame.draw.polygon(surface, _darken(roof_col, 0.7), roof_pts, iz)
    ax, ay = int(sx + r * 0.65), int(sy)
    axe_h = max(2, int(4 * z))
    pygame.draw.line(surface, (120, 90, 50), (ax, ay - axe_h), (ax, ay + max(1, int(3 * z))), iz)
    pygame.draw.polygon(surface, (160, 160, 170),
                        [(ax, ay - axe_h), (ax + max(2, int(3 * z)), ay - max(1, int(2 * z))), (ax, ay - iz)])


def _draw_quarry(surface: pygame.Surface, sx: float, sy: float, r: int, z: float) -> None:
    iz = max(1, int(z))
    arch_col = (150, 145, 135)
    pw = max(2, int(r * 0.2))
    ph = max(4, int(r * 0.7))
    pygame.draw.rect(surface, arch_col, (int(sx - r * 0.45), int(sy + r * 0.3 - ph), pw, ph))
    pygame.draw.rect(surface, arch_col, (int(sx + r * 0.45 - pw), int(sy + r * 0.3 - ph), pw, ph))
    arch_rect = pygame.Rect(int(sx - r * 0.45), int(sy - r * 0.55), int(r * 0.9), int(r * 0.3))
    pygame.draw.rect(surface, arch_col, arch_rect)
    pygame.draw.rect(surface, _lighten(arch_col, 1.2),
                     pygame.Rect(arch_rect.x, arch_rect.y, arch_rect.w, max(1, int(2 * z))))
    pygame.draw.rect(surface, (30, 25, 20),
                     (int(sx - r * 0.25), int(sy - r * 0.25), int(r * 0.5), int(r * 0.55)))
    px, py = int(sx + r * 0.55), int(sy - r * 0.2)
    pick_h = max(2, int(3 * z))
    pygame.draw.line(surface, (120, 90, 50), (px, py - pick_h), (px, py + pick_h), iz)
    pygame.draw.line(surface, (160, 160, 170),
                     (px - max(1, int(2 * z)), py - pick_h),
                     (px + max(1, int(2 * z)), py - pick_h), max(1, int(z * 1.5)))


def _draw_gatherer(surface: pygame.Surface, sx: float, sy: float, r: int, z: float) -> None:
    iz = max(1, int(z))
    hut_col = (85, 150, 65)
    rect = pygame.Rect(int(sx - r * 0.4), int(sy - r * 0.15), int(r * 0.8), int(r * 0.55))
    pygame.draw.rect(surface, hut_col, rect)
    pygame.draw.rect(surface, _lighten(hut_col, 1.2),
                     pygame.Rect(rect.x, rect.y, rect.w, max(1, int(2 * z))))
    pygame.draw.rect(surface, _darken(hut_col, 0.6), rect, iz)
    roof_col = (160, 140, 60)
    roof_pts = [(sx - r * 0.5, sy - r * 0.15), (sx, sy - r * 0.6), (sx + r * 0.5, sy - r * 0.15)]
    pygame.draw.polygon(surface, roof_col, roof_pts)
    pygame.draw.polygon(surface, _darken(roof_col, 0.7), roof_pts, iz)
    bx, by = int(sx + r * 0.5), int(sy + r * 0.15)
    br = max(2, int(3 * z))
    pygame.draw.arc(surface, (140, 110, 60), (bx - br, by - br, br * 2, br * 2), 0, math.pi, iz)
    pygame.draw.circle(surface, (200, 60, 60), (bx, by - iz), iz)


def _draw_storage(surface: pygame.Surface, sx: float, sy: float, r: int, z: float) -> None:
    iz = max(1, int(z))
    ware_col = (130, 110, 85)
    rect = pygame.Rect(int(sx - r * 0.6), int(sy - r * 0.25), int(r * 1.2), int(r * 0.65))
    pygame.draw.rect(surface, ware_col, rect)
    pygame.draw.rect(surface, _lighten(ware_col, 1.2),
                     pygame.Rect(rect.x, rect.y, rect.w, max(1, int(2 * z))))
    pygame.draw.rect(surface, _darken(ware_col, 0.6), rect, iz)
    c2 = max(1, int(2 * z))
    pygame.draw.rect(surface, _darken(ware_col, 0.75),
                     (rect.x - c2, rect.y - c2, rect.w + c2 * 2, max(2, int(4 * z))))
    pygame.draw.line(surface, _darken(ware_col, 0.65), (rect.x, rect.y), (rect.right, rect.bottom), iz)
    pygame.draw.line(surface, _darken(ware_col, 0.65), (rect.right, rect.y), (rect.x, rect.bottom), iz)
    dw = max(2, int(r * 0.3))
    dh = max(3, int(r * 0.35))
    pygame.draw.rect(surface, _darken(ware_col, 0.4),
                     (int(sx - dw // 2), int(sy + r * 0.4 - dh), dw, dh))


def _draw_path(
    surface: pygame.Surface,
    sx: float, sy: float,
    r: int, z: float,
    nb_positions: list[tuple[float, float]],
    q: int, rr: int,
) -> None:
    """Draw a dirt path tile.  Isolated → textured circle.  Adjacent paths →
    thick connecting bands that naturally merge into filled areas."""
    isx, isy = int(sx), int(sy)
    iz = max(1, int(z))
    h = _tile_hash(q, rr)

    # Band half-width: roughly 40 % of hex radius so adjacent bands overlap
    band_hw = max(2, int(r * 0.40))

    # Draw connecting bands to each neighbour first (underneath the center disc)
    for nsx, nsy in nb_positions:
        # Direction vector from center to neighbour
        dx = nsx - sx
        dy = nsy - sy
        length = math.hypot(dx, dy)
        if length < 1:
            continue
        # Unit perpendicular (rotated 90°)
        px = -dy / length * band_hw
        py = dx / length * band_hw
        # Quad from center to midpoint between the two hexes
        mx = sx + dx * 0.5
        my = sy + dy * 0.5
        pts = [
            (sx + px, sy + py),
            (sx - px, sy - py),
            (mx - px, my - py),
            (mx + px, my + py),
        ]
        pygame.draw.polygon(surface, _PATH_BASE, pts)
        # Subtle edge darkening
        pygame.draw.line(surface, _PATH_DARK,
                         (int(pts[0][0]), int(pts[0][1])),
                         (int(pts[3][0]), int(pts[3][1])), iz)
        pygame.draw.line(surface, _PATH_DARK,
                         (int(pts[1][0]), int(pts[1][1])),
                         (int(pts[2][0]), int(pts[2][1])), iz)

    # Center disc
    pygame.draw.circle(surface, _PATH_BASE, (isx, isy), band_hw + max(1, int(r * 0.10)))

    # Dirt texture: deterministic speckles
    speck_count = max(3, int(r * 0.6))
    for i in range(speck_count):
        sh2 = _tile_hash(q + i * 7, rr + i * 13)
        ox = ((sh2 & 0xFF) - 128) * band_hw // 160
        oy = (((sh2 >> 8) & 0xFF) - 128) * band_hw // 160
        col = _PATH_DARK if (sh2 >> 16) & 1 else _PATH_LIGHT
        pygame.draw.circle(surface, col, (isx + ox, isy + oy), iz)

    # Edge ring for definition when isolated
    if not nb_positions:
        pygame.draw.circle(surface, _PATH_DARK, (isx, isy),
                           band_hw + max(1, int(r * 0.10)), iz)


# ── Mountain top-down helpers ────────────────────────────────────

# Direction d (0=E, 1=NE, 2=NW, 3=W, 4=SW, 5=SE) maps to the shared
# hex edge between adjacent corners in the order produced by hex_corners().
# hex_corners() places corner i at angle (60*i + 30)°, so in screen coords
# (y-down): 0=right-bottom, 1=bottom, 2=left-bottom, 3=left-top, 4=top,
# 5=right-top.  Direction d's shared edge uses corners (6-d)%6 and (5-d)%6.
_DIR_EDGE = [(5, 0), (4, 5), (3, 4), (2, 3), (1, 2), (0, 1)]


@lru_cache(maxsize=512)
def _mountain_tile_color(depth: int, max_depth: int) -> tuple[int, int, int]:
    """Depth-based mountain colour: brown foothills → grey rock → white snow."""
    if max_depth <= 0:
        return (105, 95, 82)
    t = min(1.0, depth / max(1, max_depth))
    # Three-band: 0–0.35 brown rock, 0.35–0.7 grey rock, 0.7–1.0 snow
    if t < 0.35:
        s = t / 0.35
        return (
            int(95 + 25 * s),
            int(85 + 25 * s),
            int(72 + 28 * s),
        )
    elif t < 0.7:
        s = (t - 0.35) / 0.35
        return (
            int(120 + 50 * s),
            int(110 + 55 * s),
            int(100 + 60 * s),
        )
    else:
        s = (t - 0.7) / 0.3
        s = s * s  # ease into snow
        return (
            min(255, int(170 + 70 * s)),
            min(255, int(165 + 75 * s)),
            min(255, int(160 + 80 * s)),
        )


@lru_cache(maxsize=4096)
def _tile_hash(q: int, r: int) -> int:
    """Fast deterministic hash for per-tile randomness in contours."""
    h = (q * 0x45D9F3B + r * 0x119DE1F3) & 0xFFFFFFFF
    h ^= h >> 16
    h = (h * 0x45D9F3B) & 0xFFFFFFFF
    return h


def _draw_contours(
    surface: pygame.Surface,
    coord: HexCoord,
    depth: int,
    corners_screen: list[tuple[float, float]],
    base: tuple[int, int, int],
    mountain_depths: dict[HexCoord, tuple[int, int]],
    zoom: float,
) -> None:
    """Draw mountain ridge spurs running downhill with lit/shadow relief."""
    th = _tile_hash(coord.q, coord.r)

    # ~25% of tiles get a ridge spur
    if (th & 0xFF) >= 64:
        return

    cx = sum(p[0] for p in corners_screen) / 6.0
    cy = sum(p[1] for p in corners_screen) / 6.0

    # Gradient vector (downhill direction)
    gx, gy = 0.0, 0.0
    for d, nb_coord in enumerate(coord.neighbors()):
        nb_info = mountain_depths.get(nb_coord)
        if nb_info is None:
            continue
        diff = depth - nb_info[0]
        if diff == 0:
            continue
        c1_idx, c2_idx = _DIR_EDGE[d]
        mx = (corners_screen[c1_idx][0] + corners_screen[c2_idx][0]) * 0.5
        my = (corners_screen[c1_idx][1] + corners_screen[c2_idx][1]) * 0.5
        gx += (mx - cx) * diff
        gy += (my - cy) * diff

    glen = (gx * gx + gy * gy) ** 0.5
    if glen < 0.1:
        return

    dx, dy = gx / glen, gy / glen
    nx, ny = -dy, dx  # perpendicular

    hex_r = zoom * 14.0
    length = hex_r * (0.6 + ((th >> 8) & 0xF) / 15.0 * 0.5)
    start_back = hex_r * (0.1 + ((th >> 12) & 0x7) / 7.0 * 0.2)
    half_w = zoom * (1.2 + ((th >> 16) & 0x7) / 7.0 * 1.4)
    tip_w = zoom * 0.3

    lat_off = ((th >> 24) & 0xFF) / 255.0 * 2.0 - 1.0
    lat_shift = lat_off * zoom * 2.5

    rx = cx - dx * start_back + nx * lat_shift
    ry = cy - dy * start_back + ny * lat_shift

    bend = ((th >> 15) & 0xFF) / 255.0 * 2.0 - 1.0
    bend_mag = zoom * 2.0 * bend
    mx = rx + dx * length * 0.5 + nx * bend_mag
    my = ry + dy * length * 0.5 + ny * bend_mag
    tx = rx + dx * length
    ty = ry + dy * length

    mw = (half_w + tip_w) * 0.5

    # Lit half (upper-left when looking downhill)
    lit = [
        (int(rx), int(ry)),
        (int(rx + nx * half_w), int(ry + ny * half_w)),
        (int(mx + nx * mw), int(my + ny * mw)),
        (int(tx + nx * tip_w), int(ty + ny * tip_w)),
        (int(tx), int(ty)),
        (int(mx), int(my)),
    ]
    pygame.draw.polygon(surface, _lighten(base, 1.12), lit)

    # Shadow half
    shd = [
        (int(rx), int(ry)),
        (int(rx - nx * half_w), int(ry - ny * half_w)),
        (int(mx - nx * mw), int(my - ny * mw)),
        (int(tx - nx * tip_w), int(ty - ny * tip_w)),
        (int(tx), int(ty)),
        (int(mx), int(my)),
    ]
    pygame.draw.polygon(surface, _darken(base, 0.72), shd)

    # Spine highlight
    lw = max(1, int(zoom * 0.7))
    pygame.draw.line(surface, _lighten(base, 1.22),
                     (int(rx), int(ry)), (int(mx), int(my)), lw)
    pygame.draw.line(surface, _lighten(base, 1.18),
                     (int(mx), int(my)), (int(tx), int(ty)), lw)


# ── Colour utilities ────────────────────────────────────────────

@lru_cache(maxsize=256)
def _darken(color: tuple[int, int, int], factor: float) -> tuple[int, int, int]:
    return tuple(max(0, int(c * factor)) for c in color)  # type: ignore[return-value]


@lru_cache(maxsize=256)
def _lighten(color: tuple[int, int, int], factor: float) -> tuple[int, int, int]:
    return tuple(min(255, int(c * factor)) for c in color)  # type: ignore[return-value]
