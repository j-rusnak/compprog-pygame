"""Difficulty-selection screen for Physics Tetris.

This is shown after the player picks Physics Tetris from the home screen.
It has the same animated-blocks background and line drawing as the old
top-level menu, plus Easy / Hard difficulty buttons.
"""

from __future__ import annotations

import math
import random
import time
from dataclasses import dataclass

import pymunk
import pygame

from compprog_pygame.games.physics_tetris.board import (
    BLOCK_ELASTICITY,
    BLOCK_FRICTION,
    BLOCK_MASS_PER_CELL,
    COLLISION_BLOCK,
    COLLISION_LINE,
    COLLISION_WALL,
    LINE_FRICTION,
    LINE_MAX_SEGMENT_LEN,
    LINE_PUSH_CAP,
    LINE_PUSH_SCALE,
    setup_physics_space,
)
from compprog_pygame.games.physics_tetris.tetrominoes import SHAPES, SHAPE_WEIGHTS
from compprog_pygame.settings import DEFAULT_SETTINGS, GameSettings, easy_settings, hard_settings

# Colours
BACKGROUND = (9, 12, 25)
TEXT_COLOR = (242, 244, 255)
MUTED_TEXT = (140, 150, 175)
PANEL_BORDER = (60, 70, 100)
BTN_NORMAL = (40, 55, 90)
BTN_HOVER = (60, 80, 130)
BTN_TEXT = (242, 244, 255)
EASY_COLOR = (60, 200, 120)
HARD_COLOR = (220, 70, 70)
SELECTED_BORDER = (255, 220, 80)

MENU_LINE_LIFETIME = 0.5


@dataclass(slots=True)
class _BgCell:
    local_offset: tuple[float, float]
    color: tuple[int, int, int]


@dataclass(slots=True)
class _BgPiece:
    body: pymunk.Body
    shapes: list[pymunk.Poly]
    cells: list[_BgCell]


@dataclass(slots=True)
class _LineSeg:
    shape: pymunk.Segment
    a: tuple[float, float]
    b: tuple[float, float]
    birth: float
    in_physics: bool = True
    velocity: tuple[float, float] = (0.0, 0.0)


class DifficultyMenu:
    """Difficulty selector with animated physics background."""

    def __init__(self, width: int, height: int) -> None:
        self.width = width
        self.height = height

        self.space = setup_physics_space(gravity=765.0)
        self.pieces: list[_BgPiece] = []
        self._wall_shapes: list[pymunk.Segment] = []
        self._line_segments: list[_LineSeg] = []
        self._build_floor()

        self.spawn_timer = 0.0
        self.spawn_interval = 1.5

        self.difficulty: str = "easy"
        self.result: GameSettings | None = None
        self.quit = False

        self._drawing = False
        self._last_mouse: tuple[float, float] | None = None
        self._last_mouse_time: float = 0.0
        self._smooth_vel: tuple[float, float] = (0.0, 0.0)

        self.title_font = pygame.font.Font(None, 80)
        self.btn_font = pygame.font.Font(None, 40)
        self.label_font = pygame.font.Font(None, 30)

    # ------------------------------------------------------------------
    # Floor / walls
    # ------------------------------------------------------------------

    def _build_floor(self) -> None:
        if self._wall_shapes:
            self.space.remove(*self._wall_shapes)
            self._wall_shapes.clear()

        thickness = 20
        w, h = self.width, self.height
        walls = []
        for a, b in [
            ((-thickness, h + thickness), (w + thickness, h + thickness)),
            ((-thickness, -200), (-thickness, h + thickness)),
            ((w + thickness, -200), (w + thickness, h + thickness)),
        ]:
            seg = pymunk.Segment(self.space.static_body, a, b, thickness)
            seg.friction = BLOCK_FRICTION
            seg.elasticity = BLOCK_ELASTICITY
            seg.collision_type = COLLISION_WALL
            walls.append(seg)
        self.space.add(*walls)
        self._wall_shapes = walls

    def resize(self, width: int, height: int) -> None:
        dy = height - self.height
        self.width = width
        self.height = height
        if dy:
            for p in self.pieces:
                bx, by = p.body.position
                p.body.position = (bx, by + dy)
        self._build_floor()

    # ------------------------------------------------------------------
    # Background pieces
    # ------------------------------------------------------------------

    def _spawn_bg_piece(self) -> None:
        tdef = random.choices(SHAPES, weights=SHAPE_WEIGHTS)[0]
        rotation = random.choice([0, math.pi / 2, math.pi, 3 * math.pi / 2])
        cs = 30
        half = cs / 2

        raw = [(cx * cs + half, cy * cs + half) for cx, cy in tdef.cells]
        avg_x = sum(p[0] for p in raw) / len(raw)
        avg_y = sum(p[1] for p in raw) / len(raw)
        centred = [(x - avg_x, y - avg_y) for x, y in raw]

        total_mass = BLOCK_MASS_PER_CELL * len(tdef.cells)
        moment = 0.0
        verts_list: list[list[tuple[float, float]]] = []
        for lx, ly in centred:
            verts = [
                (lx - half, ly - half), (lx + half, ly - half),
                (lx + half, ly + half), (lx - half, ly + half),
            ]
            verts_list.append(verts)
            moment += pymunk.moment_for_poly(BLOCK_MASS_PER_CELL, verts)

        body = pymunk.Body(total_mass, moment)
        body.angle = rotation
        body.position = (random.randint(40, self.width - 40), -cs * 3)

        shapes: list[pymunk.Poly] = []
        cells: list[_BgCell] = []
        dim = tuple(max(c // 3, 20) for c in tdef.color)
        for v, (lx, ly) in zip(verts_list, centred):
            poly = pymunk.Poly(body, v)
            poly.friction = BLOCK_FRICTION
            poly.elasticity = BLOCK_ELASTICITY
            poly.collision_type = COLLISION_BLOCK
            poly.mass = BLOCK_MASS_PER_CELL
            shapes.append(poly)
            cells.append(_BgCell(local_offset=(lx, ly), color=dim))

        self.space.add(body, *shapes)
        self.pieces.append(_BgPiece(body=body, shapes=shapes, cells=cells))

    def _cull_offscreen(self) -> None:
        to_remove: list[_BgPiece] = []
        for p in self.pieces:
            if p.body.position[1] > self.height + 300:
                for s in p.shapes:
                    self.space.remove(s)
                self.space.remove(p.body)
                to_remove.append(p)
        for p in to_remove:
            self.pieces.remove(p)

    # ------------------------------------------------------------------
    # Line drawing
    # ------------------------------------------------------------------

    def add_line_point(
        self,
        prev: tuple[float, float],
        curr: tuple[float, float],
        velocity: tuple[float, float] = (0.0, 0.0),
    ) -> None:
        total_dist = math.hypot(curr[0] - prev[0], curr[1] - prev[1])
        if total_dist < 2.0:
            return

        steps = max(1, math.ceil(total_dist / LINE_MAX_SEGMENT_LEN))

        vx = velocity[0] * LINE_PUSH_SCALE
        vy = velocity[1] * LINE_PUSH_SCALE
        speed = math.hypot(vx, vy)
        if speed > LINE_PUSH_CAP:
            ratio = LINE_PUSH_CAP / speed
            vx, vy = vx * ratio, vy * ratio

        for i in range(steps):
            t0 = i / steps
            t1 = (i + 1) / steps
            a = (prev[0] + (curr[0] - prev[0]) * t0, prev[1] + (curr[1] - prev[1]) * t0)
            b = (prev[0] + (curr[0] - prev[0]) * t1, prev[1] + (curr[1] - prev[1]) * t1)

            seg = pymunk.Segment(self.space.static_body, a, b, 3.0)
            seg.friction = LINE_FRICTION
            seg.elasticity = 0.0
            seg.collision_type = COLLISION_LINE
            seg.surface_velocity = (vx, vy)
            seg._push_velocity = (vx, vy)

            self.space.add(seg)

            rec = _LineSeg(shape=seg, a=a, b=b, birth=time.monotonic(),
                           in_physics=True, velocity=(vx, vy))
            self._line_segments.append(rec)

    def _expire_lines(self) -> None:
        now = time.monotonic()
        cutoff = now - MENU_LINE_LIFETIME
        alive: list[_LineSeg] = []
        for rec in self._line_segments:
            if rec.birth < cutoff:
                self.space.remove(rec.shape)
            else:
                alive.append(rec)
        self._line_segments = alive

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    def run(self, screen: pygame.Surface, clock: pygame.time.Clock) -> GameSettings | None:
        """Returns chosen settings, or None to go back."""
        while not self.result and not self.quit:
            dt = clock.tick(60) / 1000
            dt = min(dt, 0.05)

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.quit = True
                elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                    self.quit = True
                elif event.type == pygame.VIDEORESIZE:
                    screen = pygame.display.get_surface()
                    self.resize(screen.get_width(), screen.get_height())
                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    self._on_click(event.pos)
                    self._drawing = True
                    self._last_mouse = event.pos
                    self._last_mouse_time = time.monotonic()
                elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                    self._drawing = False
                    self._last_mouse = None
                    self._smooth_vel = (0.0, 0.0)
                elif event.type == pygame.MOUSEMOTION:
                    if self._drawing and self._last_mouse is not None:
                        pos = event.pos
                        now = time.monotonic()
                        dt_mouse = max(now - self._last_mouse_time, 0.001)
                        raw_vx = (pos[0] - self._last_mouse[0]) / dt_mouse
                        raw_vy = (pos[1] - self._last_mouse[1]) / dt_mouse
                        alpha = 0.35
                        self._smooth_vel = (
                            self._smooth_vel[0] * (1 - alpha) + raw_vx * alpha,
                            self._smooth_vel[1] * (1 - alpha) + raw_vy * alpha,
                        )
                        self.add_line_point(self._last_mouse, pos, self._smooth_vel)
                        self._last_mouse_time = now
                        self._last_mouse = pos

            self._update(dt)
            self._draw(screen)
            pygame.display.flip()

        return self.result

    def _update(self, dt: float) -> None:
        sub_steps = DEFAULT_SETTINGS.physics_steps
        sub_dt = dt / sub_steps
        for _ in range(sub_steps):
            self.space.step(sub_dt)

        # Decay surface_velocity on line segments
        now = time.monotonic()
        for rec in self._line_segments:
            age = now - rec.birth
            decay = max(0.0, 1.0 - age / MENU_LINE_LIFETIME)
            vx, vy = rec.velocity
            decayed = (vx * decay, vy * decay)
            rec.shape.surface_velocity = decayed
            rec.shape._push_velocity = decayed

        self.spawn_timer += dt
        if self.spawn_timer >= self.spawn_interval:
            self.spawn_timer -= self.spawn_interval
            self._spawn_bg_piece()

        self._expire_lines()
        if len(self.pieces) > 80:
            self._cull_offscreen()

    # ------------------------------------------------------------------
    # Click handling
    # ------------------------------------------------------------------

    def _on_click(self, pos: tuple[int, int]) -> None:
        play_r, easy_r, hard_r = self._button_rects()
        if play_r.collidepoint(pos):
            self.result = easy_settings() if self.difficulty == "easy" else hard_settings()
        elif easy_r.collidepoint(pos):
            self.difficulty = "easy"
        elif hard_r.collidepoint(pos):
            self.difficulty = "hard"

    # ------------------------------------------------------------------
    # Drawing
    # ------------------------------------------------------------------

    def _button_rects(self) -> tuple[pygame.Rect, pygame.Rect, pygame.Rect]:
        cx = self.width // 2
        cy = self.height // 2

        play_rect = pygame.Rect(0, 0, 220, 56)
        play_rect.center = (cx, cy + 20)

        easy_rect = pygame.Rect(0, 0, 150, 48)
        easy_rect.center = (cx - 90, cy + 110)

        hard_rect = pygame.Rect(0, 0, 150, 48)
        hard_rect.center = (cx + 90, cy + 110)

        return play_rect, easy_rect, hard_rect

    def _draw(self, surface: pygame.Surface) -> None:
        surface.fill(BACKGROUND)
        self._draw_bg_pieces(surface)
        self._draw_lines(surface)

        play_r, easy_r, hard_r = self._button_rects()
        cx = self.width // 2
        cy = self.height // 2

        panel_top = cy - 70
        panel_bot = hard_r.bottom + 16
        panel = pygame.Rect(cx - 240, panel_top, 480, panel_bot - panel_top)
        panel_surf = pygame.Surface((panel.w, panel.h), pygame.SRCALPHA)
        panel_surf.fill((16, 24, 45, 200))
        surface.blit(panel_surf, panel.topleft)
        pygame.draw.rect(surface, PANEL_BORDER, panel, width=2, border_radius=14)

        title = self.title_font.render("Physics Tetris", True, TEXT_COLOR)
        surface.blit(title, (cx - title.get_width() // 2, panel_top + 14))

        diff_lbl = self.label_font.render("Difficulty:", True, MUTED_TEXT)
        surface.blit(diff_lbl, (cx - diff_lbl.get_width() // 2, easy_r.top - 28))

        mouse_pos = pygame.mouse.get_pos()

        # Easy
        easy_col = BTN_HOVER if easy_r.collidepoint(mouse_pos) else BTN_NORMAL
        pygame.draw.rect(surface, easy_col, easy_r, border_radius=10)
        border = SELECTED_BORDER if self.difficulty == "easy" else PANEL_BORDER
        pygame.draw.rect(surface, border, easy_r, width=3 if self.difficulty == "easy" else 2, border_radius=10)
        easy_txt = self.btn_font.render("Easy", True, EASY_COLOR)
        surface.blit(easy_txt, (easy_r.centerx - easy_txt.get_width() // 2,
                                easy_r.centery - easy_txt.get_height() // 2))

        # Hard
        hard_col = BTN_HOVER if hard_r.collidepoint(mouse_pos) else BTN_NORMAL
        pygame.draw.rect(surface, hard_col, hard_r, border_radius=10)
        border = SELECTED_BORDER if self.difficulty == "hard" else PANEL_BORDER
        pygame.draw.rect(surface, border, hard_r, width=3 if self.difficulty == "hard" else 2, border_radius=10)
        hard_txt = self.btn_font.render("Hard", True, HARD_COLOR)
        surface.blit(hard_txt, (hard_r.centerx - hard_txt.get_width() // 2,
                                hard_r.centery - hard_txt.get_height() // 2))

        # Play
        play_col = BTN_HOVER if play_r.collidepoint(mouse_pos) else BTN_NORMAL
        pygame.draw.rect(surface, play_col, play_r, border_radius=12)
        pygame.draw.rect(surface, PANEL_BORDER, play_r, width=2, border_radius=12)
        play_txt = self.btn_font.render("Play", True, BTN_TEXT)
        surface.blit(play_txt, (play_r.centerx - play_txt.get_width() // 2,
                                play_r.centery - play_txt.get_height() // 2))

    def _draw_bg_pieces(self, surface: pygame.Surface) -> None:
        for piece in self.pieces:
            body = piece.body
            for cell in piece.cells:
                wx, wy = body.local_to_world(cell.local_offset)
                angle = body.angle
                cos_a, sin_a = math.cos(angle), math.sin(angle)
                half = 15
                corners = []
                for dx, dy in [(-half, -half), (half, -half), (half, half), (-half, half)]:
                    corners.append((wx + cos_a * dx - sin_a * dy,
                                    wy + sin_a * dx + cos_a * dy))
                pygame.draw.polygon(surface, cell.color, corners)
                pygame.draw.polygon(surface, (40, 45, 60), corners, 1)

    def _draw_lines(self, surface: pygame.Surface) -> None:
        now = time.monotonic()
        for rec in self._line_segments:
            age = now - rec.birth
            alpha_frac = max(0.0, 1.0 - age / MENU_LINE_LIFETIME)
            brightness = int(255 * alpha_frac)
            color = (brightness, brightness, brightness)
            width = max(1, int(3.0 * 2 * alpha_frac))
            pygame.draw.line(surface, color, rec.a, rec.b, width)
