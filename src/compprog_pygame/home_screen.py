"""Home screen — game selection grid with animated background.

Shows all registered games as clickable cards.  Selecting one launches
that game's own setup / options flow.
"""

from __future__ import annotations

import pygame

from compprog_pygame.game_registry import GameInfo, all_games
from compprog_pygame.games.hex_colony.strings import (
    HOME_TITLE,
    HOME_HINT,
    HOME_NO_GAMES,
)

# Colours
BACKGROUND = (9, 12, 25)
TEXT_COLOR = (242, 244, 255)
MUTED_TEXT = (140, 150, 175)
PANEL_BORDER = (60, 70, 100)
CARD_BG = (16, 24, 45)
CARD_HOVER = (28, 38, 65)
TITLE_COLOR = (242, 244, 255)


class HomeScreen:
    """Full-screen game selector.  Returns the chosen :class:`GameInfo`."""

    def __init__(self, width: int, height: int) -> None:
        self.width = width
        self.height = height
        self.games = all_games()
        self.selected: GameInfo | None = None
        self.quit = False

        # Fonts
        self.title_font = pygame.font.Font(None, 72)
        self.card_title_font = pygame.font.Font(None, 38)
        self.card_desc_font = pygame.font.Font(None, 26)
        self.hint_font = pygame.font.Font(None, 24)

    def resize(self, width: int, height: int) -> None:
        self.width = width
        self.height = height

    # ------------------------------------------------------------------
    # Card layout
    # ------------------------------------------------------------------

    def _card_rects(self) -> list[pygame.Rect]:
        """Compute card rectangles for each game, laid out as a centred grid."""
        card_w, card_h = 280, 140
        pad = 24
        cols = max(1, (self.width - pad) // (card_w + pad))
        rows_needed = (len(self.games) + cols - 1) // cols

        total_w = cols * card_w + (cols - 1) * pad
        total_h = rows_needed * card_h + (rows_needed - 1) * pad
        start_x = (self.width - total_w) // 2
        start_y = (self.height - total_h) // 2 + 50  # offset for title

        rects: list[pygame.Rect] = []
        for idx in range(len(self.games)):
            r = idx // cols
            c = idx % cols
            x = start_x + c * (card_w + pad)
            y = start_y + r * (card_h + pad)
            rects.append(pygame.Rect(x, y, card_w, card_h))
        return rects

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    def run(self, screen: pygame.Surface, clock: pygame.time.Clock) -> GameInfo | None:
        """Run until a game is selected or the user quits."""
        while not self.selected and not self.quit:
            clock.tick(60)

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

            self._draw(screen)
            pygame.display.flip()

        return self.selected

    def _on_click(self, pos: tuple[int, int]) -> None:
        for rect, game in zip(self._card_rects(), self.games):
            if rect.collidepoint(pos):
                self.selected = game
                return

    # ------------------------------------------------------------------
    # Drawing
    # ------------------------------------------------------------------

    def _draw(self, surface: pygame.Surface) -> None:
        surface.fill(BACKGROUND)

        # Title
        title = self.title_font.render(HOME_TITLE, True, TITLE_COLOR)
        surface.blit(title, ((self.width - title.get_width()) // 2, 40))

        mouse_pos = pygame.mouse.get_pos()
        cards = self._card_rects()

        for rect, game in zip(cards, self.games):
            hovered = rect.collidepoint(mouse_pos)
            bg = CARD_HOVER if hovered else CARD_BG

            # Card background
            pygame.draw.rect(surface, bg, rect, border_radius=14)

            # Accent stripe along the left edge
            stripe = pygame.Rect(rect.x, rect.y, 6, rect.h)
            pygame.draw.rect(surface, game.color, stripe,
                             border_top_left_radius=14,
                             border_bottom_left_radius=14)

            # Border
            border_color = game.color if hovered else PANEL_BORDER
            pygame.draw.rect(surface, border_color, rect, width=2, border_radius=14)

            # Game title
            name_surf = self.card_title_font.render(game.name, True, TEXT_COLOR)
            surface.blit(name_surf, (rect.x + 20, rect.y + 24))

            # Description
            desc_surf = self.card_desc_font.render(game.description, True, MUTED_TEXT)
            surface.blit(desc_surf, (rect.x + 20, rect.y + 68))

        # Hint at bottom
        if self.games:
            hint = self.hint_font.render(HOME_HINT, True, MUTED_TEXT)
            surface.blit(hint, ((self.width - hint.get_width()) // 2, self.height - 40))
        else:
            hint = self.hint_font.render(HOME_NO_GAMES, True, MUTED_TEXT)
            surface.blit(hint, ((self.width - hint.get_width()) // 2, self.height // 2))
