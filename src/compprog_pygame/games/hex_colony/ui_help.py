"""Help overlay for Hex Colony — shows keybindings and controls."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pygame

from compprog_pygame.games.hex_colony.ui import (
    Fonts,
    Panel,
    UI_ACCENT,
    UI_MUTED,
    UI_OVERLAY,
    UI_TEXT,
    draw_titled_panel,
)
from compprog_pygame.games.hex_colony.strings import (
    HELP_TITLE,
    HELP_DISMISS,
    HELP_BINDINGS,
)

if TYPE_CHECKING:
    from compprog_pygame.games.hex_colony.world import World


_PANEL_W = 440
_LINE_H = 28
_MARGIN_X = 24

_HELP_LINES = HELP_BINDINGS


class HelpOverlay(Panel):
    """Full-screen overlay listing keyboard and mouse controls."""

    def __init__(self) -> None:
        super().__init__()
        self.visible = False

    def toggle(self) -> None:
        self.visible = not self.visible

    def layout(self, screen_w: int, screen_h: int) -> None:
        self.rect = pygame.Rect(0, 0, screen_w, screen_h)

    def draw(self, surface: pygame.Surface, world: World) -> None:
        if not self.visible:
            return
        sw, sh = surface.get_size()

        overlay = pygame.Surface((sw, sh), pygame.SRCALPHA)
        overlay.fill(UI_OVERLAY)
        surface.blit(overlay, (0, 0))

        pw = min(_PANEL_W, sw - 40)
        ph = 100 + len(_HELP_LINES) * _LINE_H + 50
        ph = min(ph, sh - 40)
        px = (sw - pw) // 2
        py = (sh - ph) // 2
        panel = pygame.Rect(px, py, pw, ph)
        content_y = draw_titled_panel(surface, panel, HELP_TITLE)

        # Compute the widest key so the column line aligns.
        key_font = Fonts.label()
        desc_font = Fonts.body()
        max_key_w = max(key_font.size(k)[0] for k, _ in _HELP_LINES)
        divider_x = px + _MARGIN_X + max_key_w + 20
        # Ensure desc column fits inside panel
        if divider_x + 20 > px + pw - _MARGIN_X:
            divider_x = px + pw // 2

        y = content_y
        for key, desc in _HELP_LINES:
            if y + _LINE_H > py + ph - 40:
                break
            key_surf = key_font.render(key, True, UI_ACCENT)
            desc_surf = desc_font.render(desc, True, UI_MUTED)
            surface.blit(key_surf, (px + _MARGIN_X, y))
            surface.blit(desc_surf, (divider_x, y + 2))
            y += _LINE_H

        hint = desc_font.render(HELP_DISMISS, True, UI_MUTED)
        surface.blit(hint, (
            px + (pw - hint.get_width()) // 2,
            py + ph - hint.get_height() - 14,
        ))

    def handle_event(self, event: pygame.event.Event) -> bool:
        if not self.visible:
            return False
        if event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_h, pygame.K_ESCAPE):
                self.visible = False
                return True
        return True
