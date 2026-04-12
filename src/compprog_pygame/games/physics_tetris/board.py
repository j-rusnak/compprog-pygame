"""Physics-backed Tetris board using pymunk.

Manages the Chipmunk2D space, spawning tetrominoes as rigid bodies made of
square cell shapes, the static walls / floor, and row-clear detection.
"""

from __future__ import annotations

import math
import random
import time
from dataclasses import dataclass, field

import pymunk
import pygame

from compprog_pygame.settings import GameSettings
from compprog_pygame.games.physics_tetris.tetrominoes import SHAPES, TetrominoDef

# Collision types
COLLISION_WALL = 1
COLLISION_BLOCK = 2
COLLISION_LINE = 3

# Physics material defaults
BLOCK_FRICTION = 0.6
BLOCK_ELASTICITY = 0.01
BLOCK_MASS_PER_CELL = 1.0
LINE_FRICTION = 0.8  # high friction transfers surface_velocity push effectively
LINE_PUSH_SCALE = 0.5  # scale raw mouse velocity for surface_velocity
LINE_PUSH_CAP = 400.0  # max effective push speed (px/s)
LINE_MAX_SEGMENT_LEN = 24.0  # split long mouse moves for reliable contact
LINE_NORMAL_PUSH = 0.15  # impulse scale for perpendicular push component


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


@dataclass(slots=True)
class LineSegRecord:
    """One segment of a user-drawn line, with a birth timestamp."""
    shape: pymunk.Segment
    point_a: tuple[float, float]
    point_b: tuple[float, float]
    birth: float  # time.monotonic() when created
    in_physics: bool = True  # False when segment spawned overlapping a block
    velocity: tuple[float, float] = (0.0, 0.0)  # stored push velocity


# ------------------------------------------------------------------
# Shared physics setup — used by Board and MenuScreen
# ------------------------------------------------------------------

# Maximum penetration depth (px) tolerated for line↔block contacts.
# Deeper overlaps are ignored so newly-spawned segments that happen to
# land inside a block don't cause explosive correction impulses.
_LINE_MAX_PENETRATION = -10.0


def _line_block_pre_solve(arbiter: pymunk.Arbiter, _space: pymunk.Space, _data: object) -> bool:
    """Handle line↔block contacts: reject deep overlaps, apply push.

    Lines are static segments with ``surface_velocity`` for tangential push
    (friction drags blocks along the surface like a conveyor belt).  This
    handler adds a perpendicular impulse component so strokes drawn across
    a block also push it away from the line surface.
    """
    for pt in arbiter.contact_point_set.points:
        if pt.distance < _LINE_MAX_PENETRATION:
            return False

    # Identify which shape is the line and which is the block.
    sa, sb = arbiter.shapes
    if sa.collision_type == COLLISION_LINE:
        line_shape = sa
        block_body = sb.body
        normal = arbiter.contact_point_set.normal  # from sa → sb
    else:
        line_shape = sb
        block_body = sa.body
        n = arbiter.contact_point_set.normal
        normal = pymunk.Vec2d(-n.x, -n.y)  # flip so it points LINE → BLOCK

    # Apply perpendicular push impulse from stored velocity.
    vel = getattr(line_shape, '_push_velocity', None)
    if vel:
        # Project push velocity onto the contact normal
        dot = vel[0] * normal.x + vel[1] * normal.y
        # Push block in the direction the mouse is moving relative to surface
        if abs(dot) > 5.0:
            imp = dot * LINE_NORMAL_PUSH * block_body.mass
            block_body.apply_impulse_at_world_point(
                (normal.x * imp, normal.y * imp),
                block_body.position,
            )
    return True


def setup_physics_space(gravity: float = 765.0) -> pymunk.Space:
    """Create a pymunk Space with consistent physics settings.

    A *pre_solve* handler on LINE↔BLOCK contacts prevents explosive
    impulses when a drawn segment happens to overlap a block deeply.
    Shallow contacts are processed normally so kinematic line bodies
    can push blocks proportionally to the mouse velocity.
    """
    space = pymunk.Space()
    space.gravity = (0, gravity)
    space.collision_slop = 1.0
    space.damping = 0.97  # gentle global velocity damping
    space.on_collision(
        collision_type_a=COLLISION_LINE,
        collision_type_b=COLLISION_BLOCK,
        pre_solve=_line_block_pre_solve,
    )
    return space


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

        # Pymunk space — shared helper keeps menu & game in sync
        self.space = setup_physics_space(gravity=settings.gravity)

        self.pieces: list[Piece] = []
        self.settled_pieces: list[Piece] = []
        self._wall_shapes: list[pymunk.Segment] = []
        self._line_segments: list[LineSegRecord] = []

        # Next-piece preview
        self.next_shape: TetrominoDef = random.choice(SHAPES)
        self.next_rotation: float = random.choice(
            [0, math.pi / 2, math.pi, 3 * math.pi / 2]
        )

        self._build_walls()

    # ------------------------------------------------------------------
    # User-drawn lines
    # ------------------------------------------------------------------

    def add_line_point(
        self,
        prev: tuple[float, float],
        curr: tuple[float, float],
        velocity: tuple[float, float] = (0.0, 0.0),
    ) -> None:
        """Add a collideable segment between two screen-space points.

        *velocity* is the mouse velocity in px/s.  The segment is a static
        shape with ``surface_velocity`` set so pymunk's friction solver
        pushes touching blocks tangentially (like a conveyor belt).  A
        perpendicular impulse is applied in the ``pre_solve`` callback for
        cross-stroke pushes.  The pre_solve handler rejects deeply overlapping
        contacts to prevent explosive forces.
        """
        total_dist = math.hypot(curr[0] - prev[0], curr[1] - prev[1])
        if total_dist < 2.0:
            return  # skip near-duplicate points

        # Break long cursor jumps into short segments so fast movement still
        # creates reliable contacts along the stroke path.
        steps = max(1, math.ceil(total_dist / LINE_MAX_SEGMENT_LEN))

        # Scale and cap the push velocity
        vx = velocity[0] * LINE_PUSH_SCALE
        vy = velocity[1] * LINE_PUSH_SCALE
        speed = math.hypot(vx, vy)
        if speed > LINE_PUSH_CAP:
            ratio = LINE_PUSH_CAP / speed
            vx, vy = vx * ratio, vy * ratio

        for i in range(steps):
            t0 = i / steps
            t1 = (i + 1) / steps
            a = (
                prev[0] + (curr[0] - prev[0]) * t0,
                prev[1] + (curr[1] - prev[1]) * t0,
            )
            b = (
                prev[0] + (curr[0] - prev[0]) * t1,
                prev[1] + (curr[1] - prev[1]) * t1,
            )

            seg = pymunk.Segment(
                self.space.static_body, a, b,
                self.settings.line_thickness,
            )
            seg.friction = LINE_FRICTION
            seg.elasticity = 0.0
            seg.collision_type = COLLISION_LINE
            seg.surface_velocity = (vx, vy)
            seg._push_velocity = (vx, vy)  # read by pre_solve for normal impulse

            # Always add to physics — the pre_solve handler rejects
            # contacts that are too deeply overlapping, so explosive
            # impulses from segments spawned inside a block are prevented.
            self.space.add(seg)

            rec = LineSegRecord(
                shape=seg, point_a=a, point_b=b,
                birth=time.monotonic(), in_physics=True,
                velocity=(vx, vy),
            )
            self._line_segments.append(rec)

    def expire_lines(self) -> None:
        """Remove line segments older than ``line_lifetime``."""
        now = time.monotonic()
        cutoff = now - self.settings.line_lifetime
        still_alive: list[LineSegRecord] = []
        for rec in self._line_segments:
            if rec.birth < cutoff:
                self.space.remove(rec.shape)
            else:
                still_alive.append(rec)
        self._line_segments = still_alive

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
        """Spawn the queued next piece and pick a new next piece."""
        tdef = self.next_shape
        rotation = self.next_rotation
        self.next_shape = random.choice(SHAPES)
        self.next_rotation = random.choice(
            [0, math.pi / 2, math.pi, 3 * math.pi / 2]
        )
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

        # Spawn position: above the visible area
        if self.settings.random_spawn_x:
            spawn_x = self.origin_x + random.randint(cs * 2, self.play_w - cs * 2)
        else:
            # Cluster near centre
            mid = self.origin_x + self.play_w // 2
            spread = self.play_w // 6
            spawn_x = mid + random.randint(-spread, spread)
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

        # Decay surface_velocity on line segments so push fades over lifetime
        now = time.monotonic()
        lifetime = self.settings.line_lifetime
        for rec in self._line_segments:
            age = now - rec.birth
            decay = max(0.0, 1.0 - age / lifetime)
            vx, vy = rec.velocity
            decayed = (vx * decay, vy * decay)
            rec.shape.surface_velocity = decayed
            rec.shape._push_velocity = decayed

        # Post-step per-body cleanup
        still_threshold = 5.0  # px/s
        for piece in self.pieces:
            body = piece.body
            speed = body.velocity.length

            # Damp angular velocity for slow pieces so they stop wobbling
            if speed < 120.0:
                body.angular_velocity *= 0.96

            # Track settled pieces
            if speed < still_threshold and abs(body.angular_velocity) < 0.5:
                piece.settled_time += dt
            else:
                piece.settled_time = 0.0

    # ------------------------------------------------------------------
    # Row clearing
    # ------------------------------------------------------------------

    def clear_full_rows(self) -> int:
        """Detect and remove full rows.  Returns number of rows cleared.

        A row only clears when *every* column contains a block cell that:
        - has its centre inside that grid cell,
        - belongs to a body whose angle is near axis-aligned (0/90/180/270°),
        - belongs to a body that is nearly at rest.
        """
        cs = self.settings.cell_size
        ox = self.origin_x
        oy = self.origin_y
        cleared = 0

        # Pre-compute world positions + alignment for every cell once.
        # A body is "aligned" if its angle is within ~6° of a 90° multiple
        # and it is nearly still.
        align_tol = math.radians(6)
        speed_tol = 30.0  # px/s
        ang_vel_tol = 0.8  # rad/s

        cell_world: list[tuple[float, float, bool]] = []  # (wx, wy, aligned)
        for piece in self.pieces:
            body = piece.body
            angle_mod = body.angle % (math.pi / 2)
            aligned = (
                (angle_mod < align_tol or angle_mod > math.pi / 2 - align_tol)
                and body.velocity.length < speed_tol
                and abs(body.angular_velocity) < ang_vel_tol
            )
            for cell in piece.cells:
                wx, wy = body.local_to_world(cell.local_offset)
                cell_world.append((wx, wy, aligned))

        for row_idx in range(self.settings.rows):
            row_top = oy + row_idx * cs
            row_bot = row_top + cs

            # Each column must have at least one aligned cell inside it.
            all_filled = True
            for col_idx in range(self.settings.columns):
                col_left = ox + col_idx * cs
                col_right = col_left + cs

                found = False
                for wx, wy, aligned in cell_world:
                    if (
                        aligned
                        and col_left <= wx < col_right
                        and row_top <= wy < row_bot
                    ):
                        found = True
                        break

                if not found:
                    all_filled = False
                    break

            if all_filled:
                self._remove_row(row_top, row_bot)
                cleared += 1

        return cleared

    def check_loss(self) -> bool:
        """Return True if blocks are stacked above the play area.

        Only counts pieces that have been settled (nearly motionless) for
        at least 1.5 seconds AND are within the horizontal play-area
        bounds.  This avoids false positives from freshly-spawned pieces
        falling through the top or blocks flung out of bounds.
        """
        top = self.origin_y
        left = self.origin_x
        right = self.origin_x + self.play_w
        settle_required = 1.5  # seconds of near-stillness
        for piece in self.pieces:
            if piece.settled_time < settle_required:
                continue
            for cell in piece.cells:
                wx, wy = piece.body.local_to_world(cell.local_offset)
                if wy < top and left <= wx <= right:
                    return True
        return False

    def _remove_row(self, y_top: float, y_bot: float) -> None:
        """Remove cells in the row band, then split any piece whose remaining
        cells are no longer contiguous into separate physics bodies."""
        cs = self.settings.cell_size
        new_pieces: list[Piece] = []
        to_remove: list[Piece] = []

        for piece in list(self.pieces):
            body = piece.body
            surviving: list[tuple[pymunk.Poly, BlockCell]] = []
            removed_any = False

            for shape, cell in zip(piece.shapes, piece.cells):
                wx, wy = body.local_to_world(cell.local_offset)
                if y_top <= wy <= y_bot:
                    self.space.remove(shape)
                    removed_any = True
                else:
                    surviving.append((shape, cell))

            if not removed_any:
                continue

            if not surviving:
                self.space.remove(body)
                to_remove.append(piece)
                continue

            # --- split surviving cells into connected groups ---
            groups = self._find_connected_groups(body, [c for _, c in surviving], cs)

            if len(groups) == 1:
                # Still one contiguous piece – just update in place
                piece.shapes = [s for s, _ in surviving]
                piece.cells = [c for _, c in surviving]
            else:
                # Remove the old body + remaining shapes entirely
                for shape, _cell in surviving:
                    self.space.remove(shape)
                self.space.remove(body)
                to_remove.append(piece)

                # Create a fresh body for each connected group
                for group_cells in groups:
                    new_p = self._create_fragment(
                        body, group_cells, piece.color, cs,
                    )
                    new_pieces.append(new_p)

        for p in to_remove:
            self.pieces.remove(p)
        self.pieces.extend(new_pieces)

    # ------------------------------------------------------------------
    # Piece splitting helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _find_connected_groups(
        body: pymunk.Body,
        cells: list[BlockCell],
        cs: float,
    ) -> list[list[BlockCell]]:
        """Partition *cells* into groups of adjacently-connected cells.

        Two cells are neighbours if their world-space centres are within
        ~1.1 × cell_size of each other (diagonal tolerance).
        """
        threshold = cs * 1.2
        world_positions = [body.local_to_world(c.local_offset) for c in cells]
        visited = [False] * len(cells)
        groups: list[list[BlockCell]] = []

        for i in range(len(cells)):
            if visited[i]:
                continue
            group: list[BlockCell] = []
            stack = [i]
            while stack:
                idx = stack.pop()
                if visited[idx]:
                    continue
                visited[idx] = True
                group.append(cells[idx])
                wx, wy = world_positions[idx]
                for j in range(len(cells)):
                    if not visited[j]:
                        ox, oy = world_positions[j]
                        if abs(ox - wx) <= threshold and abs(oy - wy) <= threshold:
                            stack.append(j)
            groups.append(group)
        return groups

    def _create_fragment(
        self,
        old_body: pymunk.Body,
        cells: list[BlockCell],
        color: tuple[int, int, int],
        cs: float,
    ) -> Piece:
        """Build a new physics body from a subset of cells, preserving their
        current world positions and the old body's velocity / rotation."""
        half = cs / 2

        # Compute world centres
        world_centres = [old_body.local_to_world(c.local_offset) for c in cells]
        avg_x = sum(p[0] for p in world_centres) / len(world_centres)
        avg_y = sum(p[1] for p in world_centres) / len(world_centres)

        total_mass = BLOCK_MASS_PER_CELL * len(cells)
        moment = 0.0
        new_local_offsets: list[tuple[float, float]] = []
        poly_verts_list: list[list[tuple[float, float]]] = []

        for wx, wy in world_centres:
            lx = wx - avg_x
            ly = wy - avg_y
            new_local_offsets.append((lx, ly))
            verts = [
                (lx - half, ly - half),
                (lx + half, ly - half),
                (lx + half, ly + half),
                (lx - half, ly + half),
            ]
            poly_verts_list.append(verts)
            moment += pymunk.moment_for_poly(BLOCK_MASS_PER_CELL, verts)

        body = pymunk.Body(total_mass, moment)
        body.position = (avg_x, avg_y)
        body.angle = 0.0  # local offsets already in world orientation
        body.velocity = old_body.velocity
        body.angular_velocity = old_body.angular_velocity

        new_shapes: list[pymunk.Poly] = []
        new_cells: list[BlockCell] = []
        for verts, (lx, ly), orig_cell in zip(poly_verts_list, new_local_offsets, cells):
            poly = pymunk.Poly(body, verts)
            poly.friction = BLOCK_FRICTION
            poly.elasticity = BLOCK_ELASTICITY
            poly.collision_type = COLLISION_BLOCK
            poly.mass = BLOCK_MASS_PER_CELL
            new_shapes.append(poly)
            new_cells.append(BlockCell(local_offset=(lx, ly), color=orig_cell.color))

        self.space.add(body, *new_shapes)
        return Piece(body=body, shapes=new_shapes, cells=new_cells, color=color)

    # ------------------------------------------------------------------
    # Drawing helpers
    # ------------------------------------------------------------------

    def draw(self, surface: pygame.Surface) -> None:
        self._draw_grid(surface)
        self._draw_pieces(surface)
        self._draw_lines(surface)

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

    def _draw_lines(self, surface: pygame.Surface) -> None:
        now = time.monotonic()
        lifetime = self.settings.line_lifetime
        for rec in self._line_segments:
            age = now - rec.birth
            alpha_frac = max(0.0, 1.0 - age / lifetime)
            brightness = int(255 * alpha_frac)
            color = (brightness, brightness, brightness)
            width = max(1, int(self.settings.line_thickness * 2 * alpha_frac))
            pygame.draw.line(surface, color, rec.point_a, rec.point_b, width)
