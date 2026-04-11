"""Physics-backed Tetris board using pymunk.

Manages the Chipmunk2D space, spawning tetrominoes as rigid bodies made of
square cell shapes, the static walls / floor, and row-clear detection.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

import pymunk
import pygame

from compprog_pygame.settings import GameSettings
from compprog_pygame.tetrominoes import SHAPES, TetrominoDef

# Collision types
COLLISION_WALL = 1
COLLISION_BLOCK = 2

# Pymunk works better with some friction / elasticity defaults
BLOCK_FRICTION = 0.25
BLOCK_ELASTICITY = 0.05
BLOCK_MASS_PER_CELL = 1.0


@dataclass(slots=True)
class BlockCell:
    """Visual bookkeeping for a single cell inside a piece."""
    local_offset: tuple[float, float]  # offset from body centre (px)
    color: tuple[int, int, int]


@dataclass(slots=True)
class Piece:
    """A tetromino that lives in the physics world."""
    body: pymunk.Body
    shapes: list[pymunk.Poly]
    cells: list[BlockCell]
    color: tuple[int, int, int]
    settled_time: float = 0.0  # seconds the piece has been nearly still


class Board:
    """The full play-area: static walls, dynamic pieces, row clearing."""

    def __init__(self, settings: GameSettings) -> None:
        self.settings = settings
        cs = settings.cell_size

        # The play area is centred horizontally in the window
        self.play_w = settings.columns * cs
        self.play_h = settings.rows * cs
        self.origin_x = (settings.width - self.play_w) // 2
        self.origin_y = settings.height - self.play_h - 20  # 20 px bottom margin

        # Pymunk space  (y-down to match pygame)
        self.space = pymunk.Space()
        self.space.gravity = (0, settings.gravity)

        self.pieces: list[Piece] = []
        self.settled_pieces: list[Piece] = []
        self._wall_shapes: list[pymunk.Segment] = []

        self._build_walls()

    # ------------------------------------------------------------------
    # Walls
    # ------------------------------------------------------------------

    def _build_walls(self) -> None:
        # Remove old walls if any
        if self._wall_shapes:
            self.space.remove(*self._wall_shapes)
            self._wall_shapes.clear()

        cs = self.settings.cell_size
        ox, oy = self.origin_x, self.origin_y
        pw, ph = self.play_w, self.play_h
        thickness = 20

        walls = [
            # floor – offset down by thickness so inner edge aligns with oy+ph
            pymunk.Segment(self.space.static_body,
                           (ox - thickness, oy + ph + thickness),
                           (ox + pw + thickness, oy + ph + thickness),
                           thickness),
            # left wall – offset left so inner edge aligns with ox
            pymunk.Segment(self.space.static_body,
                           (ox - thickness, oy - 200),
                           (ox - thickness, oy + ph + thickness),
                           thickness),
            # right wall – offset right so inner edge aligns with ox+pw
            pymunk.Segment(self.space.static_body,
                           (ox + pw + thickness, oy - 200),
                           (ox + pw + thickness, oy + ph + thickness),
                           thickness),
        ]
        for w in walls:
            w.friction = BLOCK_FRICTION
            w.elasticity = BLOCK_ELASTICITY
            w.collision_type = COLLISION_WALL
        self.space.add(*walls)
        self._wall_shapes = walls

    def resize(self, new_width: int, new_height: int) -> None:
        """Reposition the play area and rebuild walls for a new window size.

        Pieces keep their physics positions; we shift origins and walls so the
        floor/walls track the visible play area.
        """
        old_ox, old_oy = self.origin_x, self.origin_y

        self.origin_x = (new_width - self.play_w) // 2
        self.origin_y = new_height - self.play_h - 20

        # Shift every body so pieces stay in the same visual grid position
        dx = self.origin_x - old_ox
        dy = self.origin_y - old_oy
        if dx or dy:
            for piece in self.pieces:
                bx, by = piece.body.position
                piece.body.position = (bx + dx, by + dy)

        self._build_walls()

    # ------------------------------------------------------------------
    # Spawning
    # ------------------------------------------------------------------

    def spawn_piece(self) -> Piece:
        """Create a random tetromino at a random column / rotation and add it
        to the physics space."""
        tdef = random.choice(SHAPES)
        rotation = random.choice([0, math.pi / 2, math.pi, 3 * math.pi / 2])
        return self._add_piece(tdef, rotation)

    def _add_piece(self, tdef: TetrominoDef, rotation: float) -> Piece:
        cs = self.settings.cell_size
        half = cs / 2

        # Build cell verts relative to local origin (centre-of-mass will be
        # auto-computed by pymunk from the combined shapes).
        # First compute cell centres relative to (0, 0) then create boxes.
        raw_centres: list[tuple[float, float]] = []
        for cx, cy in tdef.cells:
            raw_centres.append((cx * cs + half, cy * cs + half))

        # Centre the shape around (0, 0)
        avg_x = sum(p[0] for p in raw_centres) / len(raw_centres)
        avg_y = sum(p[1] for p in raw_centres) / len(raw_centres)
        centred = [(x - avg_x, y - avg_y) for x, y in raw_centres]

        # Create body
        total_mass = BLOCK_MASS_PER_CELL * len(tdef.cells)
        moment = 0.0
        poly_verts_list: list[list[tuple[float, float]]] = []
        for lx, ly in centred:
            verts = [
                (lx - half, ly - half),
                (lx + half, ly - half),
                (lx + half, ly + half),
                (lx - half, ly + half),
            ]
            poly_verts_list.append(verts)
            moment += pymunk.moment_for_poly(BLOCK_MASS_PER_CELL, verts)

        body = pymunk.Body(total_mass, moment)
        body.angle = rotation

        # Spawn position: random column, above the visible area
        spawn_x = self.origin_x + random.randint(cs * 2, self.play_w - cs * 2)
        spawn_y = self.origin_y - cs * 2
        body.position = (spawn_x, spawn_y)

        shapes: list[pymunk.Poly] = []
        cells: list[BlockCell] = []
        for verts, (lx, ly) in zip(poly_verts_list, centred):
            poly = pymunk.Poly(body, verts)
            poly.friction = BLOCK_FRICTION
            poly.elasticity = BLOCK_ELASTICITY
            poly.collision_type = COLLISION_BLOCK
            poly.mass = BLOCK_MASS_PER_CELL
            shapes.append(poly)
            cells.append(BlockCell(local_offset=(lx, ly), color=tdef.color))

        self.space.add(body, *shapes)
        piece = Piece(body=body, shapes=shapes, cells=cells, color=tdef.color)
        self.pieces.append(piece)
        return piece

    # ------------------------------------------------------------------
    # Physics step
    # ------------------------------------------------------------------

    def step(self, dt: float) -> None:
        sub = self.settings.physics_steps
        sub_dt = dt / sub
        for _ in range(sub):
            self.space.step(sub_dt)

        # Track settled pieces (low velocity)
        still_threshold = 5.0  # px/s
        for piece in self.pieces:
            speed = piece.body.velocity.length
            if speed < still_threshold and abs(piece.body.angular_velocity) < 0.5:
                piece.settled_time += dt
            else:
                piece.settled_time = 0.0

    # ------------------------------------------------------------------
    # Row clearing
    # ------------------------------------------------------------------

    def clear_full_rows(self) -> int:
        """Detect and remove full rows.  Returns number of rows cleared."""
        cs = self.settings.cell_size
        ox = self.origin_x
        oy = self.origin_y
        cleared = 0

        for row_idx in range(self.settings.rows):
            row_top = oy + row_idx * cs
            row_bot = row_top + cs
            row_mid = row_top + cs / 2

            # Sample occupancy across the row
            filled = 0
            samples = self.settings.columns * 2  # over-sample
            for s in range(samples):
                sx = ox + (s + 0.5) * (self.play_w / samples)
                info = self.space.point_query_nearest((sx, row_mid), 0, pymunk.ShapeFilter())
                if info and info.shape and info.shape.collision_type == COLLISION_BLOCK:
                    filled += 1

            if filled / samples >= self.settings.row_fill_threshold:
                self._remove_row(row_top, row_bot)
                cleared += 1

        return cleared

    def _remove_row(self, y_top: float, y_bot: float) -> None:
        """Remove all block cells whose centres sit inside the given row band."""
        to_remove: list[Piece] = []
        for piece in list(self.pieces):
            body = piece.body
            remaining_shapes: list[pymunk.Poly] = []
            remaining_cells: list[BlockCell] = []
            removed_any = False

            for shape, cell in zip(piece.shapes, piece.cells):
                # World position of this cell centre
                wx, wy = body.local_to_world(cell.local_offset)
                if y_top <= wy <= y_bot:
                    self.space.remove(shape)
                    removed_any = True
                else:
                    remaining_shapes.append(shape)
                    remaining_cells.append(cell)

            if removed_any:
                if not remaining_shapes:
                    # Entire piece removed
                    self.space.remove(body)
                    to_remove.append(piece)
                else:
                    piece.shapes = remaining_shapes
                    piece.cells = remaining_cells

        for p in to_remove:
            self.pieces.remove(p)

    # ------------------------------------------------------------------
    # Drawing helpers
    # ------------------------------------------------------------------

    def draw(self, surface: pygame.Surface) -> None:
        self._draw_grid(surface)
        self._draw_pieces(surface)

    def _draw_grid(self, surface: pygame.Surface) -> None:
        cs = self.settings.cell_size
        ox, oy = self.origin_x, self.origin_y
        grid_color = (30, 36, 52)
        border_color = (60, 70, 100)

        # Background
        pygame.draw.rect(surface, (12, 16, 30),
                         (ox, oy, self.play_w, self.play_h))

        for c in range(self.settings.columns + 1):
            x = ox + c * cs
            pygame.draw.line(surface, grid_color, (x, oy), (x, oy + self.play_h))
        for r in range(self.settings.rows + 1):
            y = oy + r * cs
            pygame.draw.line(surface, grid_color, (ox, y), (ox + self.play_w, y))

        # Border
        pygame.draw.rect(surface, border_color,
                         (ox - 2, oy - 2, self.play_w + 4, self.play_h + 4), 2)

    def _draw_pieces(self, surface: pygame.Surface) -> None:
        cs = self.settings.cell_size
        half = cs / 2
        for piece in self.pieces:
            body = piece.body
            for cell in piece.cells:
                # World position of cell centre
                wx, wy = body.local_to_world(cell.local_offset)
                # Compute rotated square corners
                angle = body.angle
                cos_a = math.cos(angle)
                sin_a = math.sin(angle)
                corners = []
                for dx, dy in [(-half, -half), (half, -half),
                                (half, half), (-half, half)]:
                    rx = cos_a * dx - sin_a * dy
                    ry = sin_a * dx + cos_a * dy
                    corners.append((wx + rx, wy + ry))

                pygame.draw.polygon(surface, cell.color, corners)
                pygame.draw.polygon(surface, (255, 255, 255), corners, 1)
