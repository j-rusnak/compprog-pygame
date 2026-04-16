"""Help overlay for Hex Colony — shows keybindings and controls."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pygame

from compprog_pygame.games.hex_colony.ui import (
    Panel,
    UI_ACCENT,
    UI_BG,
    UI_BORDER,
    UI_MUTED,
    UI_TEXT,
)

if TYPE_CHECKING:
    from compprog_pygame.games.hex_colony.world import World

_OVERLAY_COLOR = (0, 0, 0, 120)
_PANEL_W = 400
_LINE_H = 28

_HELP_LINES: list[tuple[str, str]] = [
    ("WASD / Arrows", "Pan camera"),
    ("Scroll wheel", "Zoom in / out"),
    ("Left click", "Select tile / place building"),
    ("Right click", "Cancel build / deselect / pan"),
    ("Middle click", "Pan camera"),
    ("B", "Cycle build mode"),
    ("X", "Toggle delete mode"),
    ("H", "Toggle this help overlay"),
    ("1 / 2 / 3", "Set game speed"),
    ("Tab", "Toggle sandbox mode"),
    ("Alt (hold)", "Show resource overlay"),
    ("Escape", "Pause menu"),
]


class HelpOverlay(Panel):
    """Full-screen overlay listing keyboard and mouse controls."""

    def __init__(self) -> None:
        super().__init__()
        self.visible = False
        self._title_font = pygame.font.Font(None, 40)
        self._key_font = pygame.font.Font(None, 26)
        self._desc_font = pygame.font.Font(None, 24)

    def toggle(self) -> None:
        self.visible = not self.visible

    def layout(self, screen_w: int, screen_h: int) -> None:
        self.rect = pygame.Rect(0, 0, screen_w, screen_h)

    def draw(self, surface: pygame.Surface, world: World) -> None:
        if not self.visible:
            return
        sw, sh = surface.get_size()

        # Dark backdrop
        overlay = pygame.Surface((sw, sh), pygame.SRCALPHA)
        overlay.fill(_OVERLAY_COLOR)
        surface.blit(overlay, (0, 0))

        # Panel
        ph = 80 + len(_HELP_LINES) * _LINE_H + 40
        px = (sw - _PANEL_W) // 2
        py = (sh - ph) // 2
        panel_rect = pygame.Rect(px, py, _PANEL_W, ph)
        bg = pygame.Surface((_PANEL_W, ph), pygame.SRCALPHA)
        bg.fill(UI_BG)
        surface.blit(bg, (px, py))
        pygame.draw.rect(surface, UI_BORDER, panel_rect, width=2, border_radius=8)
        pygame.draw.line(surface, UI_ACCENT, (px, py), (px + _PANEL_W, py), 2)

        # Title
        title = self._title_font.render("Controls", True, UI_TEXT)
        surface.blit(title, (px + (_PANEL_W - title.get_width()) // 2, py + 20))

        # Help lines
        y = py + 70
        for key, desc in _HELP_LINES:
            key_surf = self._key_font.render(key, True, UI_ACCENT)
            desc_surf = self._desc_font.render(desc, True, UI_MUTED)
            surface.blit(key_surf, (px + 20, y))
            surface.blit(desc_surf, (px + 200, y))
            y += _LINE_H

        # Hint
        hint = self._desc_font.render("Press H or ESC to close", True, UI_MUTED)
        surface.blit(hint, (px + (_PANEL_W - hint.get_width()) // 2, y + 10))

    def handle_event(self, event: pygame.event.Event) -> bool:
        if not self.visible:
            return False
        if event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_h, pygame.K_ESCAPE):
                self.visible = False
                return True
        # Consume all events while visible
        return True
