"""Game-over overlay for Hex Colony.

Displays when the colony fails (e.g. all colonists die).
Shows final stats and offers Return to Menu / Quit options.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Callable

import pygame

from compprog_pygame.games.hex_colony.ui import (
    Panel,
    UI_ACCENT,
    UI_BORDER,
    UI_MUTED,
    UI_TEXT,
)

if TYPE_CHECKING:
    from compprog_pygame.games.hex_colony.world import World

_OVERLAY_COLOR = (0, 0, 0, 150)
_BUTTON_W = 280
_BUTTON_H = 48
_BUTTON_GAP = 14
_BUTTON_BG = (30, 50, 90)
_BUTTON_HOVER = (50, 75, 130)
_BUTTONS = ["Return to Main Menu", "Quit"]


class GameOverOverlay(Panel):
    """Full-screen overlay shown when the game ends."""

    def __init__(self) -> None:
        super().__init__()
        self.visible = False
        self.active = False  # set by Game when world.game_over is True
        self._title_font = pygame.font.Font(None, 64)
        self._btn_font = pygame.font.Font(None, 34)
        self._info_font = pygame.font.Font(None, 28)
        self._hovered: int = -1

        # Callbacks wired by Game
        self.on_return_to_menu: Callable[[], None] | None = None
        self.on_quit: Callable[[], None] | None = None

    def layout(self, screen_w: int, screen_h: int) -> None:
        self.rect = pygame.Rect(0, 0, screen_w, screen_h)

    def draw(self, surface: pygame.Surface, world: World) -> None:
        # Sync visibility to active flag
        self.visible = self.active
        if not self.active:
            return

        sw, sh = surface.get_size()

        # Dark backdrop
        overlay = pygame.Surface((sw, sh), pygame.SRCALPHA)
        overlay.fill(_OVERLAY_COLOR)
        surface.blit(overlay, (0, 0))

        # Title
        title = self._title_font.render("Colony Lost", True, (220, 50, 50))
        surface.blit(title, ((sw - title.get_width()) // 2, sh // 2 - 120))

        # Stats
        mins, secs = divmod(int(world.time_elapsed), 60)
        info = self._info_font.render(
            f"Survived {mins}:{secs:02d}  |  "
            f"Buildings: {len(world.buildings.buildings)}",
            True, UI_MUTED,
        )
        surface.blit(info, ((sw - info.get_width()) // 2, sh // 2 - 50))

        # Buttons
        bx = (sw - _BUTTON_W) // 2
        by = sh // 2
        for idx, label in enumerate(_BUTTONS):
            rect = pygame.Rect(bx, by, _BUTTON_W, _BUTTON_H)
            hovered = idx == self._hovered
            bg = _BUTTON_HOVER if hovered else _BUTTON_BG
            pygame.draw.rect(surface, bg, rect, border_radius=8)
            border = UI_ACCENT if hovered else UI_BORDER
            pygame.draw.rect(surface, border, rect, width=2, border_radius=8)
            txt = self._btn_font.render(label, True, UI_TEXT)
            surface.blit(txt, (bx + (_BUTTON_W - txt.get_width()) // 2,
                               by + (_BUTTON_H - txt.get_height()) // 2))
            by += _BUTTON_H + _BUTTON_GAP

    def handle_event(self, event: pygame.event.Event) -> bool:
        if not self.active:
            return False

        if event.type == pygame.MOUSEMOTION:
            self._update_hover(event.pos)
            return True

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self._hovered == 0 and self.on_return_to_menu:
                self.on_return_to_menu()
            elif self._hovered == 1 and self.on_quit:
                self.on_quit()
            return True

        # Consume all events while active
        return True

    def _update_hover(self, pos: tuple[int, int]) -> None:
        self._hovered = -1
        sw, sh = pygame.display.get_surface().get_size()
        bx = (sw - _BUTTON_W) // 2
        by = sh // 2
        for idx in range(len(_BUTTONS)):
            if pygame.Rect(bx, by, _BUTTON_W, _BUTTON_H).collidepoint(pos):
                self._hovered = idx
                return
            by += _BUTTON_H + _BUTTON_GAP
