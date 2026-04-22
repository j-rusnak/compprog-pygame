"""Hexagonal grid coordinate system and utilities.

Uses axial coordinates (q, r) with pointy-top hexagons so the map forms
straight horizontal rows, which reads more naturally in the colony view.
Reference: https://www.redblobgames.com/grids/hexagons/
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum, auto
from typing import Iterator


@dataclass(frozen=True, slots=True)
class HexCoord:
    """Axial hex coordinate."""
    q: int
    r: int

    @property
    def s(self) -> int:
        return -self.q - self.r

    def neighbor(self, direction: int) -> HexCoord:
        """Return the neighbor in one of 6 directions (0=E, going CCW)."""
        dq, dr = HEX_DIRECTIONS[direction % 6]
        return HexCoord(self.q + dq, self.r + dr)

    def neighbors(self) -> list[HexCoord]:
        return [self.neighbor(d) for d in range(6)]

    def distance(self, other: HexCoord) -> int:
        return (abs(self.q - other.q) + abs(self.r - other.r) + abs(self.s - other.s)) // 2

    def __hash__(self) -> int:
        return hash((self.q, self.r))


# Direction offsets for axial hex coordinates (E, NE, NW, W, SW, SE)
HEX_DIRECTIONS: list[tuple[int, int]] = [
    (+1, 0), (+1, -1), (0, -1),
    (-1, 0), (-1, +1), (0, +1),
]


class Terrain(Enum):
    """Terrain types for hex tiles."""
    GRASS = auto()
    FOREST = auto()
    DENSE_FOREST = auto()
    STONE_DEPOSIT = auto()
    WATER = auto()
    FIBER_PATCH = auto()  # berry bushes / flax field
    MOUNTAIN = auto()
    IRON_VEIN = auto()    # iron ore crystals on existing terrain
    COPPER_VEIN = auto()  # copper ore crystals on existing terrain
    OIL_DEPOSIT = auto()  # surface oil pool — only OIL_DRILL can build on it
    WASTELAND = auto()    # corrupted/blighted ground around an awakened ancient tower


@dataclass(slots=True)
class HexTile:
    """Data for a single hex on the map."""
    coord: HexCoord
    terrain: Terrain
    resource_amount: float = 0.0  # harvestable resource remaining
    food_amount: float = 0.0     # harvestable food (fiber/berry patches)
    building: object | None = None  # will hold Building reference
    underlying_terrain: Terrain | None = None  # original terrain under ore veins


class HexGrid:
    """Sparse hex grid backed by a dict."""

    def __init__(self) -> None:
        self._tiles: dict[HexCoord, HexTile] = {}
        self._tile_list_dirty: bool = True
        self._tile_list: list[HexTile] = []

    def __contains__(self, coord: HexCoord) -> bool:
        return coord in self._tiles

    def __getitem__(self, coord: HexCoord) -> HexTile:
        return self._tiles[coord]

    def get(self, coord: HexCoord) -> HexTile | None:
        return self._tiles.get(coord)

    def set_tile(self, tile: HexTile) -> None:
        self._tiles[tile.coord] = tile
        self._tile_list_dirty = True

    def tiles(self) -> list[HexTile]:
        if self._tile_list_dirty:
            self._tile_list = list(self._tiles.values())
            self._tile_list_dirty = False
        return self._tile_list

    def coords(self) -> Iterator[HexCoord]:
        yield from self._tiles.keys()

    def __len__(self) -> int:
        return len(self._tiles)


# ── Pixel conversion (pointy-top hexagons) ───────────────────────

_SQRT3 = math.sqrt(3)
_SQRT3_OVER_3 = _SQRT3 / 3


def hex_to_pixel(coord: HexCoord, size: int) -> tuple[float, float]:
    """Convert axial hex coord to pixel centre (pointy-top)."""
    x = size * _SQRT3 * (coord.q + coord.r / 2)
    y = size * 1.5 * coord.r
    return x, y


def pixel_to_hex(x: float, y: float, size: int) -> HexCoord:
    """Convert pixel position to the nearest axial hex coord (pointy-top)."""
    q = (_SQRT3_OVER_3 * x - 1 / 3 * y) / size
    r = (2 / 3 * y) / size
    return _axial_round(q, r)


def _axial_round(q: float, r: float) -> HexCoord:
    s = -q - r
    rq, rr, rs = round(q), round(r), round(s)
    dq, dr, ds = abs(rq - q), abs(rr - r), abs(rs - s)
    if dq > dr and dq > ds:
        rq = -rr - rs
    elif dr > ds:
        rr = -rq - rs
    return HexCoord(int(rq), int(rr))


# Pre-computed unit corner offsets for pointy-top hex (cos/sin of 30,90,150,210,270,330 deg)
_HEX_CORNER_OFFSETS: list[tuple[float, float]] = [
    (math.cos(math.radians(60 * i + 30)), math.sin(math.radians(60 * i + 30)))
    for i in range(6)
]


def hex_corners(cx: float, cy: float, size: int) -> list[tuple[float, float]]:
    """Return the 6 corner pixel positions for a pointy-top hex centred at (cx, cy)."""
    return [
        (cx + size * dx, cy + size * dy)
        for dx, dy in _HEX_CORNER_OFFSETS
    ]
