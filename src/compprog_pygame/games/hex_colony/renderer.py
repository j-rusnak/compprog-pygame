"""Rendering for Hex Colony — draws tiles, buildings, people, and HUD.

Uses procedural pixel-art detail for terrain, buildings, and characters
while keeping the crisp low-resolution aesthetic.

Performance notes
-----------------
* Per-tile detail (tree positions, rock shapes, etc.) is pre-computed once
  and stored in ``_detail_cache`` keyed by ``HexCoord``.  This avoids
  constructing a ``random.Random`` and regenerating positions every frame.
* ``hex_to_pixel`` results are cached in ``_pixel_cache``.
* Zoom is quantised to an LOD band; detail is completely skipped at very
  low zoom and reduced at medium zoom.
* The selection-highlight overlay uses a small, clipped SRCALPHA surface
  instead of a full-screen allocation.
"""

from __future__ import annotations

import math
import random as _random
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

import pygame

from compprog_pygame.games.hex_colony.buildings import Building, BuildingType
from compprog_pygame.games.hex_colony.camera import Camera
from compprog_pygame.games.hex_colony.hex_grid import (
    HexCoord,
    HexTile,
    Terrain,
    hex_corners,
    hex_to_pixel,
)
from compprog_pygame.games.hex_colony.people import Person, Task
from compprog_pygame.games.hex_colony.resources import Inventory, Resource
from compprog_pygame.games.hex_colony.world import World

# ── Colour palette ───────────────────────────────────────────────

BACKGROUND = (9, 12, 25)

# Base + highlight + shadow for each terrain
TERRAIN_COLORS: dict[Terrain, tuple[tuple[int, int, int], tuple[int, int, int], tuple[int, int, int]]] = {
    Terrain.GRASS:         ((76, 140, 60),  (100, 170, 80),  (55, 110, 42)),
    Terrain.FOREST:        ((34, 100, 34),  (50, 125, 50),   (22, 75, 22)),
    Terrain.DENSE_FOREST:  ((18, 70, 22),   (30, 90, 35),    (10, 50, 14)),
    Terrain.STONE_DEPOSIT: ((140, 140, 130),(170, 170, 160),  (105, 105, 95)),
    Terrain.WATER:         ((40, 90, 180),  (65, 120, 210),   (25, 65, 140)),
    Terrain.FIBER_PATCH:   ((120, 160, 60), (150, 190, 85),   (90, 125, 40)),
    Terrain.MOUNTAIN:      ((110, 100, 90), (140, 130, 118),  (80, 72, 62)),
}

BUILDING_COLORS: dict[BuildingType, tuple[int, int, int]] = {
    BuildingType.CAMP: (200, 160, 60),
    BuildingType.WOODCUTTER: (160, 100, 50),
    BuildingType.QUARRY: (170, 170, 160),
    BuildingType.GATHERER: (100, 180, 80),
    BuildingType.STORAGE: (140, 120, 100),
}

PERSON_COLOR = (230, 210, 170)
PERSON_GATHER_COLOR = (180, 220, 120)
PERSON_SKIN = (220, 185, 140)
PERSON_HAIR = (80, 55, 30)
HUD_BG = (16, 24, 45, 220)
HUD_TEXT = (242, 244, 255)
MUTED_TEXT = (140, 150, 175)
HIGHLIGHT_COLOR = (255, 255, 100)
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

# Pre-computed outline colors per terrain (avoids _darken call per tile per frame)
_OUTLINE_COLORS: dict[Terrain, tuple[int, int, int]] = {}


# ── Pre-computed per-tile detail data ────────────────────────────
# Each terrain type produces a list of lightweight draw commands that
# are generated ONCE (deterministically seeded by coord) and replayed
# every frame with only a multiply + offset for the current zoom/pan.

@dataclass(slots=True)
class _GrassTuft:
    ox: float; oy: float; h: float; color: tuple[int, int, int]

@dataclass(slots=True)
class _TreeDetail:
    ox: float; oy: float; radius: float; trunk_h: float
    crown_color: tuple[int, int, int]; style: str  # "tri" or "circle"

@dataclass(slots=True)
class _RockDetail:
    ox: float; oy: float; radius: float
    color: tuple[int, int, int]

@dataclass(slots=True)
class _WaterRipple:
    ox: float; oy: float; w: float; phase_offset: float

@dataclass(slots=True)
class _BushDetail:
    ox: float; oy: float; radius: float
    bush_color: tuple[int, int, int]
    berry_color: tuple[int, int, int] | None

@dataclass(slots=True)
class _PeakDetail:
    ox: float; oy: float; mh: float; mw: float
    color: tuple[int, int, int]; has_snow: bool


# Type alias for the union
_DetailItem = _GrassTuft | _TreeDetail | _RockDetail | _WaterRipple | _BushDetail | _PeakDetail


def _tile_detail_seed(coord: HexCoord) -> int:
    """Return a deterministic seed for per-tile procedural detail."""
    q = coord.q & 0xFFFFFFFF
    r = coord.r & 0xFFFFFFFF
    seed = 42
    seed ^= q + 0x9E3779B9 + ((seed << 6) & 0xFFFFFFFF) + (seed >> 2)
    seed &= 0xFFFFFFFF
    seed ^= r + 0x9E3779B9 + ((seed << 6) & 0xFFFFFFFF) + (seed >> 2)
    return seed & 0xFFFFFFFF


def _build_tile_detail(coord: HexCoord, terrain: Terrain) -> list[_DetailItem]:
    """Generate detail items once for a tile.  Positions are normalised
    fractions of hex_size, centred on (0, 0)."""
    rng = _random.Random(_tile_detail_seed(coord))
    items: list[_DetailItem] = []

    if terrain == Terrain.GRASS:
        for _ in range(rng.randint(4, 8)):
            items.append(_GrassTuft(
                ox=rng.uniform(-0.5, 0.5), oy=rng.uniform(-0.4, 0.4),
                h=rng.uniform(2, 5),
                color=rng.choice([(90, 160, 70), (70, 130, 50), (100, 175, 85)]),
            ))

    elif terrain == Terrain.FOREST:
        for _ in range(rng.randint(2, 4)):
            items.append(_TreeDetail(
                ox=rng.uniform(-0.45, 0.45), oy=rng.uniform(-0.35, 0.35),
                radius=rng.uniform(3, 6), trunk_h=3.0,
                crown_color=rng.choice([(30, 90, 30), (40, 110, 40), (25, 80, 25)]),
                style="tri",
            ))

    elif terrain == Terrain.DENSE_FOREST:
        for _ in range(rng.randint(3, 6)):
            items.append(_TreeDetail(
                ox=rng.uniform(-0.5, 0.5), oy=rng.uniform(-0.4, 0.4),
                radius=rng.uniform(3, 7), trunk_h=0.0,
                crown_color=rng.choice([(15, 60, 18), (20, 75, 25), (12, 55, 15)]),
                style="circle",
            ))

    elif terrain == Terrain.STONE_DEPOSIT:
        for _ in range(rng.randint(3, 6)):
            items.append(_RockDetail(
                ox=rng.uniform(-0.45, 0.45), oy=rng.uniform(-0.35, 0.35),
                radius=rng.uniform(2, 5),
                color=rng.choice([(155, 155, 145), (130, 130, 120), (160, 158, 150)]),
            ))

    elif terrain == Terrain.WATER:
        for _ in range(rng.randint(2, 4)):
            items.append(_WaterRipple(
                ox=rng.uniform(-0.4, 0.4), oy=rng.uniform(-0.3, 0.3),
                w=rng.uniform(4, 10), phase_offset=rng.uniform(0, 6.28),
            ))

    elif terrain == Terrain.FIBER_PATCH:
        for _ in range(rng.randint(3, 6)):
            berry: tuple[int, int, int] | None = None
            if rng.random() > 0.3:
                berry = rng.choice([(200, 60, 60), (180, 50, 120), (220, 180, 40)])
            items.append(_BushDetail(
                ox=rng.uniform(-0.45, 0.45), oy=rng.uniform(-0.35, 0.35),
                radius=rng.uniform(2, 4),
                bush_color=rng.choice([(100, 150, 50), (130, 170, 65)]),
                berry_color=berry,
            ))

    elif terrain == Terrain.MOUNTAIN:
        for _ in range(rng.randint(2, 4)):
            items.append(_PeakDetail(
                ox=rng.uniform(-0.4, 0.4), oy=rng.uniform(-0.3, 0.3),
                mh=rng.uniform(4, 9), mw=rng.uniform(3, 6),
                color=rng.choice([(120, 110, 100), (100, 90, 80), (130, 120, 108)]),
                has_snow=rng.random() > 0.4,
            ))

    return items


class Renderer:
    """Draws the entire game scene with detailed pixel-art style."""

    def __init__(self) -> None:
        self.font = pygame.font.Font(None, 22)
        self.hud_font = pygame.font.Font(None, 28)
        self.hud_title_font = pygame.font.Font(None, 34)
        self.small_font = pygame.font.Font(None, 18)
        self.selected_hex: HexCoord | None = None
        self._water_tick: float = 0.0

        # ── Caches ───────────────────────────────────────────────
        # Pixel position of each hex centre (never changes for a given grid).
        self._pixel_cache: dict[HexCoord, tuple[float, float]] = {}
        # Corner positions in world coords (6 corners per hex, never change).
        self._corner_cache: dict[HexCoord, list[tuple[float, float]]] = {}
        # Pre-computed detail draw-commands per tile.
        self._detail_cache: dict[HexCoord, list[_DetailItem]] = {}
        # Cached HUD panel surface (recreated only when size changes).
        self._hud_panel: pygame.Surface | None = None
        self._hud_panel_size: tuple[int, int] = (0, 0)
        # Cached bottom bar surface.
        self._bar_surf: pygame.Surface | None = None
        self._bar_surf_w: int = 0
        # Cached HUD text surfaces
        self._hud_cache_key: tuple = ()
        self._hud_text_surfs: dict[str, pygame.Surface] = {}

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

    def _get_detail(self, tile: HexTile) -> list[_DetailItem]:
        cached = self._detail_cache.get(tile.coord)
        if cached is None:
            cached = _build_tile_detail(tile.coord, tile.terrain)
            self._detail_cache[tile.coord] = cached
        return cached

    # ── Public draw entry point ──────────────────────────────────

    def draw(
        self,
        surface: pygame.Surface,
        world: World,
        camera: Camera,
        dt: float = 1 / 60,
    ) -> None:
        self._water_tick += dt
        surface.fill(BACKGROUND)
        self._draw_tiles(surface, world, camera)
        self._draw_buildings(surface, world, camera)
        self._draw_people(surface, world, camera)
        if self.selected_hex is not None:
            self._draw_hex_highlight(surface, self.selected_hex, camera, world.settings.hex_size)
        self._draw_hud(surface, world)

    # ── Hex tiles ────────────────────────────────────────────────

    def _draw_tiles(
        self, surface: pygame.Surface, world: World, camera: Camera
    ) -> None:
        size = world.settings.hex_size
        sw, sh = surface.get_size()
        zoom = camera.zoom
        margin = size * 2 * zoom

        # Pre-compute zoom-dependent values once per frame
        bevel_w = max(1, int(2 * zoom))
        draw_bevel = zoom > 0.25
        draw_detail = zoom > 0.35
        draw_outline = zoom > 0.2
        # At medium zoom thin out detail items to save draw calls
        detail_stride = 1 if zoom > 0.7 else 2

        # Ensure outline colors are built
        if not _OUTLINE_COLORS:
            for ter, (_, _, shd) in TERRAIN_COLORS.items():
                _OUTLINE_COLORS[ter] = _darken(shd, 0.7)

        # Inline camera transform constants
        cam_x, cam_y = camera.x, camera.y
        half_sw = sw * 0.5
        half_sh = sh * 0.5

        for tile in world.grid.tiles():
            wx, wy = self._get_pixel(tile.coord, size)

            # Inline world_to_screen (avoid method-call overhead)
            sx = (wx - cam_x) * zoom + half_sw
            sy = (wy - cam_y) * zoom + half_sh

            # Frustum cull
            if sx < -margin or sx > sw + margin or sy < -margin or sy > sh + margin:
                continue

            colors = TERRAIN_COLORS.get(tile.terrain, ((80, 80, 80), (100, 100, 100), (60, 60, 60)))
            base, highlight, shadow = colors

            corners_world = self._get_corners(tile.coord, wx, wy, size)
            # Inline world_to_screen for all 6 corners
            corners_screen = [
                ((cx - cam_x) * zoom + half_sw, (cy - cam_y) * zoom + half_sh)
                for cx, cy in corners_world
            ]

            # Fill base
            pygame.draw.polygon(surface, base, corners_screen)

            # 3D beveled edges (skip at very low zoom where they're invisible)
            if draw_bevel:
                c = corners_screen
                pygame.draw.line(surface, highlight, c[0], c[1], bevel_w)
                pygame.draw.line(surface, highlight, c[1], c[2], bevel_w)
                pygame.draw.line(surface, shadow,    c[2], c[3], bevel_w)
                pygame.draw.line(surface, shadow,    c[3], c[4], bevel_w)
                pygame.draw.line(surface, shadow,    c[4], c[5], bevel_w)
                pygame.draw.line(surface, highlight, c[5], c[0], bevel_w)

            # Terrain detail
            if draw_detail:
                self._draw_terrain_detail_cached(surface, tile, sx, sy, size, zoom, detail_stride)

            # Subtle dark outline (pre-computed color, skip at very low zoom)
            if draw_outline:
                pygame.draw.polygon(surface, _OUTLINE_COLORS.get(tile.terrain, (40, 40, 40)), corners_screen, width=1)

    # ── Terrain detail (from pre-computed cache) ─────────────────

    def _draw_terrain_detail_cached(
        self, surface: pygame.Surface, tile: HexTile,
        sx: float, sy: float, size: int, z: float, stride: int,
    ) -> None:
        items = self._get_detail(tile)
        s = size * z  # scaled radius
        iz = max(1, int(z))
        _draw_line = pygame.draw.line
        _draw_circle = pygame.draw.circle
        _draw_polygon = pygame.draw.polygon

        for idx in range(0, len(items), stride):
            item = items[idx]

            if isinstance(item, _GrassTuft):
                px = int(sx + item.ox * s)
                py = int(sy + item.oy * s)
                h = max(1, int(item.h * z))
                _draw_line(surface, item.color, (px, py), (px + iz, py - h), iz)

            elif isinstance(item, _TreeDetail):
                tx = int(sx + item.ox * s)
                ty = int(sy + item.oy * s)
                tr = max(2, int(item.radius * z))
                if item.style == "tri":
                    trunk_h = max(1, int(item.trunk_h * z))
                    _draw_line(surface, (100, 70, 35), (tx, ty + tr), (tx, ty + tr + trunk_h), iz)
                    pts = [(tx, ty - tr), (tx - tr, ty + tr), (tx + tr, ty + tr)]
                    _draw_polygon(surface, item.crown_color, pts)
                    hl = _lighten(item.crown_color, 1.3)
                    _draw_polygon(surface, hl, [(tx, ty - tr), (tx + tr // 2, ty), (tx - tr // 2, ty)], 0)
                else:  # circle
                    shadow_r = max(1, int(tr * 0.7))
                    iz2 = max(1, int(2 * z))
                    _draw_circle(surface, (10, 40, 12), (tx, ty + tr + iz2), shadow_r)
                    _draw_circle(surface, item.crown_color, (tx, ty), tr)
                    hl = _lighten(item.crown_color, 1.4)
                    _draw_circle(surface, hl, (tx - iz, ty - iz), max(1, tr // 2))

            elif isinstance(item, _RockDetail):
                rx = int(sx + item.ox * s)
                ry = int(sy + item.oy * s)
                rr = max(2, int(item.radius * z))
                pts = [
                    (rx - rr, ry + rr // 2),
                    (rx - rr // 2, ry - rr),
                    (rx + rr // 2, ry - rr),
                    (rx + rr, ry + rr // 2),
                ]
                _draw_polygon(surface, item.color, pts)
                _draw_line(surface, _lighten(item.color, 1.3), pts[1], pts[2], iz)
                _draw_line(surface, _darken(item.color, 0.6), pts[3], pts[0], iz)

            elif isinstance(item, _WaterRipple):
                phase = self._water_tick * 1.5
                offset = math.sin(phase + item.phase_offset) * 2 * z
                px = int(sx + item.ox * s + offset)
                py = int(sy + item.oy * s)
                w = max(2, int(item.w * z))
                _draw_line(surface, (65, 120, 210), (px - w, py), (px + w, py), iz)

            elif isinstance(item, _BushDetail):
                bx = int(sx + item.ox * s)
                by = int(sy + item.oy * s)
                br = max(2, int(item.radius * z))
                _draw_circle(surface, item.bush_color, (bx, by), br)
                if item.berry_color is not None:
                    _draw_circle(surface, item.berry_color, (bx + iz, by - iz), iz)

            elif isinstance(item, _PeakDetail):
                mx = int(sx + item.ox * s)
                my = int(sy + item.oy * s)
                mh = max(3, int(item.mh * z))
                mw = max(2, int(item.mw * z))
                pts = [(mx - mw, my + mh // 2), (mx, my - mh), (mx + mw, my + mh // 2)]
                _draw_polygon(surface, item.color, pts)
                if item.has_snow:
                    c2 = max(1, int(2 * z))
                    cap = [(mx - c2, my - mh + c2), (mx, my - mh), (mx + c2, my - mh + c2)]
                    _draw_polygon(surface, (230, 235, 240), cap)

    # ── Buildings ────────────────────────────────────────────────

    def _draw_buildings(
        self, surface: pygame.Surface, world: World, camera: Camera
    ) -> None:
        size = world.settings.hex_size
        zoom = camera.zoom
        cam_x, cam_y = camera.x, camera.y
        sw, sh = surface.get_size()
        half_sw, half_sh = sw * 0.5, sh * 0.5
        margin = size * 2 * zoom

        for building in world.buildings.buildings:
            wx, wy = self._get_pixel(building.coord, size)
            sx = (wx - cam_x) * zoom + half_sw
            sy = (wy - cam_y) * zoom + half_sh

            if sx < -margin or sx > sw + margin or sy < -margin or sy > sh + margin:
                continue

            r = int(size * 0.5 * zoom)
            color = BUILDING_COLORS.get(building.type, (200, 200, 200))

            if r < 3:
                pygame.draw.circle(surface, color, (int(sx), int(sy)), max(2, r))
                continue

            if building.type == BuildingType.CAMP:
                self._draw_camp(surface, sx, sy, r, zoom)
            elif building.type == BuildingType.WOODCUTTER:
                self._draw_woodcutter(surface, sx, sy, r, zoom)
            elif building.type == BuildingType.QUARRY:
                self._draw_quarry(surface, sx, sy, r, zoom)
            elif building.type == BuildingType.GATHERER:
                self._draw_gatherer(surface, sx, sy, r, zoom)
            elif building.type == BuildingType.STORAGE:
                self._draw_storage(surface, sx, sy, r, zoom)

    def _draw_camp(self, surface: pygame.Surface, sx: float, sy: float, r: int, z: float) -> None:
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

    def _draw_woodcutter(self, surface: pygame.Surface, sx: float, sy: float, r: int, z: float) -> None:
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

    def _draw_quarry(self, surface: pygame.Surface, sx: float, sy: float, r: int, z: float) -> None:
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

    def _draw_gatherer(self, surface: pygame.Surface, sx: float, sy: float, r: int, z: float) -> None:
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

    def _draw_storage(self, surface: pygame.Surface, sx: float, sy: float, r: int, z: float) -> None:
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

    # ── People ───────────────────────────────────────────────────

    def _draw_people(
        self, surface: pygame.Surface, world: World, camera: Camera
    ) -> None:
        zoom = camera.zoom
        cam_x, cam_y = camera.x, camera.y
        sw, sh = surface.get_size()
        half_sw, half_sh = sw * 0.5, sh * 0.5

        for person in world.population.people:
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
        self,
        surface: pygame.Surface,
        coord: HexCoord,
        camera: Camera,
        size: int,
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

        # Small clipped SRCALPHA surface instead of full-screen
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

    # ── HUD overlay ──────────────────────────────────────────────

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

        # Build a cache key from changing data
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


@lru_cache(maxsize=256)
def _darken(color: tuple[int, int, int], factor: float) -> tuple[int, int, int]:
    return tuple(max(0, int(c * factor)) for c in color)  # type: ignore[return-value]


@lru_cache(maxsize=256)
def _lighten(color: tuple[int, int, int], factor: float) -> tuple[int, int, int]:
    return tuple(min(255, int(c * factor)) for c in color)  # type: ignore[return-value]
