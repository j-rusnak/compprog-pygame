"""Shared colour constants, palette definitions, and utility functions for rendering."""

from __future__ import annotations

from functools import lru_cache

from compprog_pygame.games.hex_colony.buildings import BuildingType
from compprog_pygame.games.hex_colony.hex_grid import Terrain

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
    Terrain.IRON_VEIN:     (120, 90, 75),
    Terrain.COPPER_VEIN:   (100, 130, 85),
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
    Terrain.IRON_VEIN: 4,
    Terrain.COPPER_VEIN: 4,
}

# ── Building colours ────────────────────────────────────────────

BUILDING_COLORS: dict[BuildingType, tuple[int, int, int]] = {
    BuildingType.CAMP: (120, 140, 170),   # spaceship hull — blue-grey metallic
    BuildingType.HOUSE: (170, 140, 90),
    BuildingType.HABITAT: (140, 155, 175),  # futuristic pod — blue-grey metal
    BuildingType.PATH: (185, 165, 120),
    BuildingType.BRIDGE: (140, 100, 55),
    BuildingType.WOODCUTTER: (160, 100, 50),
    BuildingType.QUARRY: (170, 170, 160),
    BuildingType.GATHERER: (100, 180, 80),
    BuildingType.STORAGE: (140, 120, 100),
    BuildingType.REFINERY: (90, 80, 100),
    BuildingType.MINING_MACHINE: (95, 95, 110),
    BuildingType.FARM: (100, 70, 40),
    BuildingType.WELL: (140, 135, 125),
    BuildingType.WALL: (160, 155, 145),
    BuildingType.WORKSHOP: (130, 110, 90),
    BuildingType.FORGE: (90, 70, 60),
    BuildingType.ASSEMBLER: (120, 140, 165),
    BuildingType.RESEARCH_CENTER: (70, 100, 150),
}

_PATH_BASE = (185, 165, 120)
_PATH_DARK = (155, 135, 95)
_PATH_LIGHT = (205, 190, 150)

# ── Person colours ───────────────────────────────────────────────

PERSON_COLOR = (230, 210, 170)
PERSON_GATHER_COLOR = (180, 220, 120)
PERSON_SKIN = (220, 185, 140)
PERSON_HAIR = (80, 55, 30)


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
