from __future__ import annotations

import math
import time

import pygame

from compprog_pygame.board import Board
from compprog_pygame.menu import MenuScreen
from compprog_pygame.settings import DEFAULT_SETTINGS, GameSettings


BACKGROUND = (9, 12, 25)
TEXT_COLOR = (242, 244, 255)
HUD_PANEL = (16, 24, 45)
PANEL_BORDER = (60, 70, 100)
MUTED_TEXT = (140, 150, 175)


class Game:
    def __init__(self, settings: GameSettings) -> None:
        self.settings = settings
        self.screen = pygame.display.get_surface()
        self.clock = pygame.time.Clock()
        self.font = pygame.font.Font(None, 28)
        self.big_font = pygame.font.Font(None, 44)
        self.board = Board(settings)
        self.board.resize(self.screen.get_width(), self.screen.get_height())
        self.score = 0
        self.running = True
        self.spawn_timer = 0.0
        self.row_check_timer = 0.0

        # Mouse drawing state
        self._drawing = False
        self._last_mouse: tuple[float, float] | None = None
        self._last_mouse_time: float = 0.0

        # Spawn the first piece immediately
        self.board.spawn_piece()

    def run(self) -> None:
        while self.running:
            dt = self.clock.tick(self.settings.fps) / 1000
            dt = min(dt, 0.05)  # cap to avoid physics explosions on lag
            self._handle_events()
            self._update(dt)
            self._draw()

    def _handle_events(self) -> None:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                self.running = False
            elif event.type == pygame.VIDEORESIZE:
                self.screen = pygame.display.get_surface()
                self.board.resize(self.screen.get_width(), self.screen.get_height())
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                self._drawing = True
                self._last_mouse = event.pos
                self._last_mouse_time = time.monotonic()
            elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                self._drawing = False
                self._last_mouse = None
            elif event.type == pygame.MOUSEMOTION and self._drawing:
                pos = event.pos
                if self._last_mouse is not None:
                    now = time.monotonic()
                    dt_mouse = max(now - self._last_mouse_time, 0.001)
                    vx = (pos[0] - self._last_mouse[0]) / dt_mouse
                    vy = (pos[1] - self._last_mouse[1]) / dt_mouse
                    self.board.add_line_point(
                        self._last_mouse, pos, (vx, vy),
                    )
                    self._last_mouse_time = now
                self._last_mouse = pos

    def _update(self, dt: float) -> None:
        # Step physics
        self.board.step(dt)

        # Expire old drawn-line segments
        self.board.expire_lines()

        # Spawn new pieces on a timer
        self.spawn_timer += dt
        if self.spawn_timer >= self.settings.spawn_interval:
            self.spawn_timer -= self.settings.spawn_interval
            self.board.spawn_piece()

        # Check for full rows periodically (every ~0.5s to save perf)
        self.row_check_timer += dt
        if self.row_check_timer >= 0.5:
            self.row_check_timer = 0.0
            cleared = self.board.clear_full_rows()
            if cleared:
                self.score += cleared * 100

    def _draw(self) -> None:
        self.screen.fill(BACKGROUND)
        self.board.draw(self.screen)
        self._draw_hud()
        pygame.display.flip()

    def _draw_hud(self) -> None:
        sw = self.screen.get_width()
        sh = self.screen.get_height()
        b = self.board
        pad = 14

        # Available side widths
        left_w = b.origin_x - pad * 2
        right_x = b.origin_x + b.play_w + pad
        right_w = sw - right_x - pad

        # ---- LEFT PANEL: title + instructions ----
        if left_w >= 80:
            panel_x = pad
            panel_top = b.origin_y
            panel_h = b.play_h
            panel = pygame.Rect(panel_x, panel_top, left_w, panel_h)
            pygame.draw.rect(self.screen, HUD_PANEL, panel, border_radius=12)
            pygame.draw.rect(self.screen, PANEL_BORDER, panel, width=2, border_radius=12)

            y = panel.y + pad
            title = self.big_font.render("Physics", True, TEXT_COLOR)
            title2 = self.big_font.render("Tetris", True, TEXT_COLOR)
            self.screen.blit(title, (panel.x + pad, y))
            y += title.get_height() + 2
            self.screen.blit(title2, (panel.x + pad, y))
            y += title2.get_height() + pad * 2

            fade_str = f"{self.settings.line_lifetime:.1f}s"
            for line in ["Click & drag", "to draw guide", "lines that", "redirect the", "falling blocks.", "", "Lines fade", f"after {fade_str}."]:
                txt = self.font.render(line, True, MUTED_TEXT)
                self.screen.blit(txt, (panel.x + pad, y))
                y += txt.get_height() + 3

        # ---- RIGHT PANEL: score + next piece ----
        if right_w >= 80:
            panel = pygame.Rect(right_x, b.origin_y, right_w, b.play_h)
            pygame.draw.rect(self.screen, HUD_PANEL, panel, border_radius=12)
            pygame.draw.rect(self.screen, PANEL_BORDER, panel, width=2, border_radius=12)

            y = panel.y + pad
            score_lbl = self.font.render("SCORE", True, MUTED_TEXT)
            self.screen.blit(score_lbl, (panel.x + pad, y))
            y += score_lbl.get_height() + 4
            score_val = self.big_font.render(str(self.score), True, TEXT_COLOR)
            self.screen.blit(score_val, (panel.x + pad, y))
            y += score_val.get_height() + pad * 2

            next_lbl = self.font.render("NEXT", True, MUTED_TEXT)
            self.screen.blit(next_lbl, (panel.x + pad, y))
            y += next_lbl.get_height() + pad

            # Draw the next piece preview
            self._draw_next_piece(panel.x + pad, y, panel.right - pad)

    def _draw_next_piece(self, x: int, y: int, max_x: int) -> None:
        """Draw the queued next tetromino preview at (x, y)."""
        tdef = self.board.next_shape
        rotation = self.board.next_rotation
        cs = min(self.settings.cell_size, (max_x - x) // 5)  # scale to fit
        half = cs / 2

        # Compute cell centres in local coords
        raw = [(cx * cs + half, cy * cs + half) for cx, cy in tdef.cells]
        avg_x = sum(p[0] for p in raw) / len(raw)
        avg_y = sum(p[1] for p in raw) / len(raw)
        centred = [(px - avg_x, py - avg_y) for px, py in raw]

        # Pivot around the preview centre
        area_w = max_x - x
        cx_off = x + area_w / 2
        cy_off = y + cs * 2

        cos_a = math.cos(rotation)
        sin_a = math.sin(rotation)

        for lx, ly in centred:
            # Rotate
            rx = cos_a * lx - sin_a * ly
            ry = sin_a * lx + cos_a * ly
            wx = cx_off + rx
            wy = cy_off + ry

            corners = []
            for dx, dy in [(-half, -half), (half, -half),
                            (half, half), (-half, half)]:
                crx = cos_a * dx - sin_a * dy
                cry = sin_a * dx + cos_a * dy
                corners.append((wx + crx, wy + cry))

            pygame.draw.polygon(self.screen, tdef.color, corners)
            pygame.draw.polygon(self.screen, (255, 255, 255), corners, 1)


def main() -> None:
    pygame.init()
    try:
        screen = pygame.display.set_mode(
            (DEFAULT_SETTINGS.width, DEFAULT_SETTINGS.height), pygame.RESIZABLE
        )
        pygame.display.set_caption(DEFAULT_SETTINGS.title)
        clock = pygame.time.Clock()

        menu = MenuScreen(screen.get_width(), screen.get_height())
        settings = menu.run(screen, clock)
        if settings is None:
            return

        game = Game(settings)
        game.clock = clock
        game.screen = pygame.display.get_surface()
        game.run()
    finally:
        pygame.quit()