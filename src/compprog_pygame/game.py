from __future__ import annotations

import pygame

from compprog_pygame.board import Board
from compprog_pygame.settings import DEFAULT_SETTINGS, GameSettings


BACKGROUND = (9, 12, 25)
TEXT_COLOR = (242, 244, 255)
HUD_PANEL = (16, 24, 45)
PANEL_BORDER = (60, 70, 100)


class Game:
    def __init__(self, settings: GameSettings = DEFAULT_SETTINGS) -> None:
        self.settings = settings
        self.screen = pygame.display.set_mode(
            (settings.width, settings.height), pygame.RESIZABLE
        )
        pygame.display.set_caption(settings.title)
        self.clock = pygame.time.Clock()
        self.font = pygame.font.Font(None, 34)
        self.big_font = pygame.font.Font(None, 56)
        self.board = Board(settings)
        self.score = 0
        self.running = True
        self.spawn_timer = 0.0
        self.row_check_timer = 0.0

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

    def _update(self, dt: float) -> None:
        # Step physics
        self.board.step(dt)

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
        title = self.big_font.render("Physics Tetris", True, TEXT_COLOR)
        score_txt = self.font.render(f"Score: {self.score}", True, TEXT_COLOR)
        hint = self.font.render("Blocks fall automatically. Clear rows!", True, TEXT_COLOR)

        panel = pygame.Rect(16, 16, 360, 100)
        pygame.draw.rect(self.screen, HUD_PANEL, panel, border_radius=14)
        pygame.draw.rect(self.screen, PANEL_BORDER, panel, width=2, border_radius=14)

        self.screen.blit(title, (panel.x + 16, panel.y + 12))
        self.screen.blit(score_txt, (panel.x + 16, panel.y + 58))
        self.screen.blit(hint, (panel.x + 120, panel.y + 58))


def main() -> None:
    pygame.init()
    try:
        game = Game()
        game.run()
    finally:
        pygame.quit()