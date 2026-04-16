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
    OverlayTree,
    build_overlays,
)
from compprog_pygame.games.hex_colony.people import Task
from compprog_pygame.games.hex_colony.world import World

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
)
from compprog_pygame.games.hex_colony.render_buildings import (
    draw_overcrowded,
    draw_camp,
    draw_house,
    draw_woodcutter,
    draw_quarry,
    draw_gatherer,
    draw_storage,
    draw_path,
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
_COLLECTION_BUILDINGS = {BuildingType.WOODCUTTER, BuildingType.QUARRY, BuildingType.GATHERER}

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

        # Tile layer cache (tiles + static overlays, pre-rendered)
        self._tile_layer: pygame.Surface | None = None
        self._tl_zoom: float = -1.0
        self._tl_cam: tuple[float, float] = (0.0, 0.0)
        self._tl_screen: tuple[int, int] = (0, 0)
        self._ripples: list[OverlayRipple] = []
        self._static_overlays: list[OverlayItem] = []
        self._edge_colors: dict[HexCoord, list[tuple[int, int, int]]] = {}
        self._cross_cat: dict[HexCoord, list[int]] = {}  # 0=same category, 2=cross-category: use own colour
        self._dirty_tiles: set[HexCoord] = set()  # tiles needing targeted redraw

        # Alt resource overlay
        self.show_resource_overlay: bool = False

        # Ghost building preview
        self.ghost_building: BuildingType | None = None
        self.ghost_coord: HexCoord | None = None  # snapped hex coord

    @property
    def graphics_quality(self) -> str:
        return self._graphics_quality

    @graphics_quality.setter
    def graphics_quality(self, value: str) -> None:
        if value != self._graphics_quality:
            self._graphics_quality = value
            self._tile_layer = None  # force rebuild

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
        if self._graphics_quality != "low":
            self._draw_ripples(surface, camera, world.settings.hex_size)
        self._draw_buildings(surface, world, camera)
        self._draw_people(surface, world, camera)
        if self.show_resource_overlay:
            self._draw_resource_overlay(surface, world, camera)
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

    def remove_overlays_at(self, coord: HexCoord, hex_size: int) -> None:
        """Remove all overlay items that fall within the given hex tile."""
        cx, cy = hex_to_pixel(coord, hex_size)
        radius = hex_size * 0.85  # slightly smaller than full hex
        r2 = radius * radius
        self._static_overlays = [
            item for item in self._static_overlays
            if (item.wx - cx) ** 2 + (item.wy - cy) ** 2 > r2
        ]
        self._ripples = [
            item for item in self._ripples
            if (item.wx - cx) ** 2 + (item.wy - cy) ** 2 > r2
        ]
        # Mark tile for targeted redraw instead of invalidating entire cache.
        # The building drawn on top will cover stale overlay pixels until the
        # next natural cache rebuild.
        self._dirty_tiles.add(coord)

    def invalidate_tile(self, coord: HexCoord) -> None:
        """Mark a single hex as needing redraw on the tile layer."""
        self._dirty_tiles.add(coord)

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
                base = mountain_tile_color(*mtn_info)
            elif tile.underlying_terrain is not None:
                # Ore veins: show the underlying terrain colour as the base
                base = TERRAIN_BASE_COLOR.get(tile.underlying_terrain, (80, 80, 80))
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
            my_cat = _TERRAIN_CAT.get(
                tile.underlying_terrain if tile.underlying_terrain is not None else tile.terrain, 0
            )
            for nb_coord in coord.neighbors():
                nb_tile = grid.get(nb_coord)
                if nb_tile is None:
                    continue
                nb_cat = _TERRAIN_CAT.get(
                    nb_tile.underlying_terrain if nb_tile.underlying_terrain is not None else nb_tile.terrain, 0
                )
                # Hard category border: only blend within same category
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
            my_cat = _TERRAIN_CAT.get(
                tile.underlying_terrain if tile.underlying_terrain is not None else tile.terrain, 0
            )
            nb_r, nb_g, nb_b = 0, 0, 0
            nb_count = 0
            for nb_coord in coord.neighbors():
                nb_c = first_pass.get(nb_coord)
                if nb_c is None:
                    continue
                # Hard category border in second pass too
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

        # ── Precompute per-edge colours for intra-tile gradients ──
        bc = self._blended_colors
        eb = _EDGE_BLEND
        eb1 = 1.0 - eb
        for tile in grid.tiles():
            coord = tile.coord
            cc = bc[coord]
            my_cat = _TERRAIN_CAT.get(
                tile.underlying_terrain if tile.underlying_terrain is not None else tile.terrain, 0
            )
            edge_cols: list[tuple[int, int, int]] = []
            cross_flags: list[int] = []  # 0=same, 2=cross-cat (own colour)
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

        # Patch any tiles that were individually dirtied (building place/delete)
        if self._dirty_tiles:
            self._patch_dirty_tiles(world, world.settings.hex_size)

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

        lod_high = zoom > 0.45 and self._graphics_quality == "high"
        lod_mid = not lod_high and zoom >= 0.25 and self._graphics_quality != "low"
        lod_low = self._graphics_quality == "low"

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
                sx = (item.wx - cam_x) * zoom + half_cw
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

    # ── Targeted tile patching ───────────────────────────────────

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

            # Re-draw any remaining overlays that overlap this hex
            if (lod_high or lod_mid) and not lod_low:
                patch_r2 = (hex_size * 1.5) ** 2
                iz = max(1, int(zoom))
                for item in self._static_overlays:
                    if (item.wx - wx) ** 2 + (item.wy - wy) ** 2 > patch_r2:
                        continue
                    isx = (item.wx - cam_x) * zoom + half_cw
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
            sx = (item.wx - cam_x) * zoom + half_sw
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

        # First pass: paths (ground-level, drawn beneath other buildings)
        # Also track non-path buildings that need a path disc underneath
        buildings_needing_path: set[HexCoord] = set()
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
            # Compute screen positions of adjacent path or building neighbours
            nb_positions: list[tuple[float, float]] = []
            for nb_coord in building.coord.neighbors():
                nb_building = world.buildings.at(nb_coord)
                if nb_building is not None:
                    nwx, nwy = self._get_pixel(nb_coord, size)
                    nsx = (nwx - cam_x) * zoom + half_sw
                    nsy = (nwy - cam_y) * zoom + half_sh
                    nb_positions.append((nsx, nsy))
                    if nb_building.type != BuildingType.PATH:
                        buildings_needing_path.add(nb_coord)
            draw_path(surface, sx, sy, r, zoom, nb_positions,
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
            # Gather path neighbours for the under-building path disc
            nb_positions_b: list[tuple[float, float]] = []
            for nb_coord in coord.neighbors():
                nb_building = world.buildings.at(nb_coord)
                if nb_building is not None and nb_building.type == BuildingType.PATH:
                    nwx, nwy = self._get_pixel(nb_coord, size)
                    nsx = (nwx - cam_x) * zoom + half_sw
                    nsy = (nwy - cam_y) * zoom + half_sh
                    nb_positions_b.append((nsx, nsy))
            draw_path(surface, sx, sy, r, zoom, nb_positions_b,
                      coord.q, coord.r)

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
                draw_camp(surface, sx, sy, r, zoom)
            elif building.type == BuildingType.HOUSE:
                draw_house(surface, sx, sy, r, zoom)
            elif building.type == BuildingType.WOODCUTTER:
                draw_woodcutter(surface, sx, sy, r, zoom)
            elif building.type == BuildingType.QUARRY:
                draw_quarry(surface, sx, sy, r, zoom)
            elif building.type == BuildingType.GATHERER:
                draw_gatherer(surface, sx, sy, r, zoom)
            elif building.type == BuildingType.STORAGE:
                draw_storage(surface, sx, sy, r, zoom)

            # Overcrowding indicator: red ! above dwelling
            if (building.housing_capacity > 0
                    and building.residents > building.housing_capacity
                    and r >= 3):
                draw_overcrowded(surface, sx, sy, r, zoom)

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
        }
        _BUILDING_OVERLAY: dict[str, tuple[int, int, int, int]] = {
            "resource": (220, 160, 50, 70),
            "path":     (200, 180, 140, 50),
            "storage":  (160, 130, 100, 70),
            "housing":  (100, 160, 220, 70),
        }
        _RESOURCE_BUILDINGS = {BuildingType.WOODCUTTER, BuildingType.QUARRY, BuildingType.GATHERER}
        _HOUSING_BUILDINGS = {BuildingType.CAMP, BuildingType.HOUSE}

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
                    ov = pygame.Surface((w, h), pygame.SRCALPHA)
                    shifted = [(px - min_x, py - min_y) for px, py in corners_screen]
                    pygame.draw.polygon(ov, overlay_col, shifted)
                    surface.blit(ov, (min_x, min_y))

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

        # Draw building at half alpha using a temp surface
        bld_size = r * 4
        bld_surf = pygame.Surface((bld_size, bld_size), pygame.SRCALPHA)
        cx_local = bld_size // 2
        cy_local = bld_size // 2
        # Draw the building shape onto the temp surface
        if btype == BuildingType.CAMP:
            draw_camp(bld_surf, cx_local, cy_local, r, zoom)
        elif btype == BuildingType.HOUSE:
            draw_house(bld_surf, cx_local, cy_local, r, zoom)
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
        bld_surf.set_alpha(140)
        surface.blit(bld_surf, (int(sx) - cx_local, int(sy) - cy_local))

        # Range ring for collection buildings
        if btype in _COLLECTION_BUILDINGS:
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



