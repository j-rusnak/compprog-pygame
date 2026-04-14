"""Resource bar panel — top-of-screen display of all resources.

Shows an icon and current quantity for each resource, plus population.
The bar auto-sizes to fit the screen width.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pygame

from compprog_pygame.games.hex_colony.resources import Resource
from compprog_pygame.games.hex_colony.ui import (
    Panel,
    UI_ACCENT,
    UI_BG,
    UI_BORDER,
    UI_MUTED,
    UI_TEXT,
    draw_panel_bg,
)

if TYPE_CHECKING:
    from compprog_pygame.games.hex_colony.world import World


# ── Resource display config ──────────────────────────────────────

_RESOURCE_ICONS: dict[Resource, str] = {
    Resource.WOOD: "\u25b2",   # ▲
    Resource.FIBER: "\u2022",  # •
    Resource.STONE: "\u25a0",  # ■
    Resource.FOOD: "\u2665",   # ♥
}

_RESOURCE_COLORS: dict[Resource, tuple[int, int, int]] = {
    Resource.WOOD: (160, 100, 50),
    Resource.FIBER: (120, 200, 80),
    Resource.STONE: (170, 170, 160),
    Resource.FOOD: (220, 100, 80),
}

_PERSON_COLOR = (230, 210, 170)

# Layout constants
_BAR_HEIGHT = 38
_PADDING_X = 14
_ITEM_GAP = 24


class ResourceBar(Panel):
    """Top bar showing resource icons and quantities."""

    def __init__(self) -> None:
        super().__init__()
        self._icon_font = pygame.font.Font(None, 26)
        self._val_font = pygame.font.Font(None, 24)
        self._cache_key: tuple = ()
        self._rendered: list[tuple[pygame.Surface, pygame.Surface]] = []
        self._pop_icon: pygame.Surface | None = None
        self._pop_text: pygame.Surface | None = None

    def layout(self, screen_w: int, screen_h: int) -> None:
        self.rect = pygame.Rect(0, 0, screen_w, _BAR_HEIGHT)

    def draw(self, surface: pygame.Surface, world: World) -> None:
        inv = world.inventory

        # Rebuild text surfaces only when values change
        res_vals = tuple(int(inv[r]) for r in Resource)
        pop = world.population.count
        cache_key = (pop, res_vals)

        if cache_key != self._cache_key:
            self._cache_key = cache_key
            self._rendered = []
            for res in Resource:
                icon_surf = self._icon_font.render(
                    _RESOURCE_ICONS[res], True, _RESOURCE_COLORS[res],
                )
                val_surf = self._val_font.render(
                    f"{int(inv[res])}", True, UI_TEXT,
                )
                self._rendered.append((icon_surf, val_surf))
            self._pop_icon = self._icon_font.render("\u263a", True, _PERSON_COLOR)
            self._pop_text = self._val_font.render(str(pop), True, UI_TEXT)

        # Draw background
        draw_panel_bg(surface, self.rect, accent_edge="bottom")

        # Draw resource items
        x = _PADDING_X
        cy = self.rect.centery

        # Population first
        if self._pop_icon and self._pop_text:
            surface.blit(self._pop_icon, (x, cy - self._pop_icon.get_height() // 2))
            x += self._pop_icon.get_width() + 4
            surface.blit(self._pop_text, (x, cy - self._pop_text.get_height() // 2))
            x += self._pop_text.get_width() + _ITEM_GAP

        # Separator
        pygame.draw.line(surface, UI_BORDER, (x, 6), (x, _BAR_HEIGHT - 6), 1)
        x += _ITEM_GAP // 2

        # Resources
        for icon_surf, val_surf in self._rendered:
            surface.blit(icon_surf, (x, cy - icon_surf.get_height() // 2))
            x += icon_surf.get_width() + 4
            surface.blit(val_surf, (x, cy - val_surf.get_height() // 2))
            x += val_surf.get_width() + _ITEM_GAP
