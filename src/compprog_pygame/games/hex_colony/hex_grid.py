"""Hexagonal grid coordinate system and utilities.

Uses axial coordinates (q, r) with flat-top hexagons.
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


# Direction offsets for flat-top hexes (E, NE, NW, W, SW, SE)
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


@dataclass(slots=True)
class HexTile:
    """Data for a single hex on the map."""
    coord: HexCoord
    terrain: Terrain
    resource_amount: float = 0.0  # harvestable resource remaining
    building: object | None = None  # will hold Building reference


class HexGrid:
    """Sparse hex grid backed by a dict."""

    def __init__(self) -> None:
        self._tiles: dict[HexCoord, HexTile] = {}

    def __contains__(self, coord: HexCoord) -> bool:
        return coord in self._tiles

    def __getitem__(self, coord: HexCoord) -> HexTile:
        return self._tiles[coord]

    def get(self, coord: HexCoord) -> HexTile | None:
        return self._tiles.get(coord)

    def set_tile(self, tile: HexTile) -> None:
        self._tiles[tile.coord] = tile

    def tiles(self) -> Iterator[HexTile]:
        yield from self._tiles.values()

    def coords(self) -> Iterator[HexCoord]:
        yield from self._tiles.keys()

    def __len__(self) -> int:
        return len(self._tiles)


# ── Pixel conversion (flat-top hexagons) ─────────────────────────

def hex_to_pixel(coord: HexCoord, size: int) -> tuple[float, float]:
    """Convert axial hex coord to pixel centre (flat-top)."""
    x = size * (3 / 2 * coord.q)
    y = size * (math.sqrt(3) / 2 * coord.q + math.sqrt(3) * coord.r)
    return x, y


def pixel_to_hex(x: float, y: float, size: int) -> HexCoord:
    """Convert pixel position to the nearest axial hex coord (flat-top)."""
    q = (2 / 3 * x) / size
    r = (-1 / 3 * x + math.sqrt(3) / 3 * y) / size
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


def hex_corners(cx: float, cy: float, size: int) -> list[tuple[float, float]]:
    """Return the 6 corner pixel positions for a flat-top hex centred at (cx, cy)."""
    corners = []
    for i in range(6):
        angle = math.radians(60 * i)
        corners.append((cx + size * math.cos(angle), cy + size * math.sin(angle)))
    return corners
