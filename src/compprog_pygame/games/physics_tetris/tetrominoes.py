"""Tetromino shape definitions.

Each shape is a list of (col, row) offsets relative to the piece origin,
measured in cell units.  Colours are RGB tuples.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import pygame


@dataclass(frozen=True, slots=True)
class TetrominoDef:
    name: str
    cells: tuple[tuple[int, int], ...]  # (col, row) offsets
    color: tuple[int, int, int]


# Classic 7 tetrominoes
SHAPES: tuple[TetrominoDef, ...] = (
    TetrominoDef("I", ((0, 0), (1, 0), (2, 0), (3, 0)), (0, 240, 240)),
    TetrominoDef("O", ((0, 0), (1, 0), (0, 1), (1, 1)), (240, 240, 0)),
    TetrominoDef("T", ((0, 0), (1, 0), (2, 0), (1, 1)), (160, 0, 240)),
    TetrominoDef("S", ((1, 0), (2, 0), (0, 1), (1, 1)), (0, 240, 0)),
    TetrominoDef("Z", ((0, 0), (1, 0), (1, 1), (2, 1)), (240, 0, 0)),
    TetrominoDef("J", ((0, 0), (1, 0), (2, 0), (0, 1)), (0, 0, 240)),
    TetrominoDef("L", ((0, 0), (1, 0), (2, 0), (2, 1)), (240, 160, 0)),
)

# Spawn weights – S and Z appear half as often as the other pieces.
SHAPE_WEIGHTS: tuple[int, ...] = tuple(
    1 if s.name in ("S", "Z") else 2 for s in SHAPES
)
