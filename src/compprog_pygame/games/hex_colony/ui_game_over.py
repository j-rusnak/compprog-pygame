"""Game-over overlay for Hex Colony.

Shown when the colony fails. Displays summary stats and buttons for
returning to the main menu or quitting.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Callable

import pygame

from compprog_pygame.games.hex_colony.ui import (
    Fonts,
    Panel,
    UI_BAD,
    UI_MUTED,
    UI_OVERLAY,
    UI_TEXT,
    draw_button,
    draw_titled_panel,
    render_text_clipped,
)
from compprog_pygame.games.hex_colony.strings import (
    GAME_OVER_TITLE,
    GAME_OVER_BUTTONS,
    GAME_OVER_STATS,
)

if TYPE_CHECKING:
    from compprog_pygame.games.hex_colony.world import World


_BUTTON_W = 280
_BUTTON_H = 48
_BUTTON_GAP = 12
_BUTTONS = GAME_OVER_BUTTONS


class GameOverOverlay(Panel):
    """Full-screen overlay shown when the game ends."""

    def __init__(self) -> None:
        super().__init__()
        self.visible = False
        self.active = False
        self._hovered: int = -1
        self._btn_rects: list[pygame.Rect] = []

        self.on_return_to_menu: Callable[[], None] | None = None
        self.on_quit: Callable[[], None] | None = None

    def layout(self, screen_w: int, screen_h: int) -> None:
        self.rect = pygame.Rect(0, 0, screen_w, screen_h)

    def draw(self, surface: pygame.Surface, world: World) -> None:
        self.visible = self.active
        if not self.active:
            return

        sw, sh = surface.get_size()
        overlay = pygame.Surface((sw, sh), pygame.SRCALPHA)
        overlay.fill(UI_OVERLAY)
        surface.blit(overlay, (0, 0))

        pw = _BUTTON_W + 80
        ph = 260 + len(_BUTTONS) * (_BUTTON_H + _BUTTON_GAP)
        pw = min(pw, sw - 40)
        ph = min(ph, sh - 40)
        px = (sw - pw) // 2
        py = (sh - ph) // 2
        panel = pygame.Rect(px, py, pw, ph)
        content_y = draw_titled_panel(
            surface, panel, GAME_OVER_TITLE,
            title_color=UI_BAD, title_font=Fonts.hero(),
        )

        # Stats
        mins, secs = divmod(int(world.real_time_elapsed), 60)
        n_bld = sum(
            1 for b in world.buildings.buildings
            if getattr(b, "faction", "SURVIVOR") == "SURVIVOR"
        )
        info = render_text_clipped(
            Fonts.label(),
            GAME_OVER_STATS.format(time=f"{mins}:{secs:02d}", buildings=n_bld),
            UI_MUTED, pw - 40,
        )
        surface.blit(info, (
            px + (pw - info.get_width()) // 2, content_y + 16,
        ))

        # Buttons
        self._btn_rects = []
        bx = px + (pw - _BUTTON_W) // 2
        by = py + ph - _BUTTON_H * len(_BUTTONS) - _BUTTON_GAP * (len(_BUTTONS) - 1) - 24
        for idx, label in enumerate(_BUTTONS):
            rect = pygame.Rect(bx, by, _BUTTON_W, _BUTTON_H)
            state = "hover" if idx == self._hovered else "normal"
            draw_button(surface, rect, label, state=state)
            self._btn_rects.append(rect)
            by += _BUTTON_H + _BUTTON_GAP

    def handle_event(self, event: pygame.event.Event) -> bool:
        if not self.active:
            return False

        if event.type == pygame.MOUSEMOTION:
            self._hovered = -1
            for i, r in enumerate(self._btn_rects):
                if r.collidepoint(event.pos):
                    self._hovered = i
                    break
            return True

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            for i, r in enumerate(self._btn_rects):
                if r.collidepoint(event.pos):
                    if i == 0 and self.on_return_to_menu:
                        self.on_return_to_menu()
                    elif i == 1 and self.on_quit:
                        self.on_quit()
                    return True
            return True

        return True
