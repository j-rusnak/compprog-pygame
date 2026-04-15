"""Shared colour constants, palette definitions, and utility functions for rendering."""

from __future__ import annotations

from functools import lru_cache

from compprog_pygame.games.hex_colony.buildings import BuildingType
from compprog_pygame.games.hex_colony.hex_grid import Terrain
from compprog_pygame.games.hex_colony.resources import Resource

# ── Colour palette ───────────────────────────────────────────────

BACKGROUND = (9, 12, 25)

TERRAIN_BASE_COLOR: dict[Terrain, tuple[int, int, int]] = {
    Terrain.GRASS:         (82, 148, 64),
    Terrain.FOREST:        (38, 105, 38),
    Terrain.DENSE_FOREST:  (20, 72, 24),
    Terrain.STONE_DEPOSIT: (142, 142, 132),
    Terrain.WATER:         (38, 85, 175),
    Terrain.FIBER_PATCH:   (105, 148, 48),
    Terrain.MOUNTAIN:      (110, 100, 90),
}

# Blending weight for neighbor influence (0 = no blend, 1 = full average)
_BLEND_STRENGTH = 0.45

# Bank colour tinted toward water-adjacent tiles
_BANK_COLOR = (148, 138, 105)  # sandy/muddy

# Tile-layer cache padding multiplier
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
    Terrain.FIBER_PATCH: 3,
    Terrain.WATER: 1,
    Terrain.MOUNTAIN: 2,
    Terrain.STONE_DEPOSIT: 2,
}

# ── Building colours ────────────────────────────────────────────

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

# ── Person colours ───────────────────────────────────────────────

PERSON_COLOR = (230, 210, 170)
PERSON_GATHER_COLOR = (180, 220, 120)
PERSON_SKIN = (220, 185, 140)
PERSON_HAIR = (80, 55, 30)

# ── HUD colours (legacy — kept for _draw_hud) ───────────────────

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


# ── Colour utilities ────────────────────────────────────────────

@lru_cache(maxsize=256)
def _darken(color: tuple[int, int, int], factor: float) -> tuple[int, int, int]:
    return tuple(max(0, int(c * factor)) for c in color)  # type: ignore[return-value]


@lru_cache(maxsize=256)
def _lighten(color: tuple[int, int, int], factor: float) -> tuple[int, int, int]:
    return tuple(min(255, int(c * factor)) for c in color)  # type: ignore[return-value]


@lru_cache(maxsize=4096)
def _tile_hash(q: int, r: int) -> int:
    """Fast deterministic hash for per-tile randomness."""
    h = (q * 0x45D9F3B + r * 0x119DE1F3) & 0xFFFFFFFF
    h ^= h >> 16
    h = (h * 0x45D9F3B) & 0xFFFFFFFF
    return h
