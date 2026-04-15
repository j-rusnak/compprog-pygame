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
        self._btn_font = pygame.font.Font(None, 22)
        self._cache_key: tuple = ()
        self._rendered: list[tuple[pygame.Surface, pygame.Surface]] = []
        self._pop_icon: pygame.Surface | None = None
        self._pop_text: pygame.Surface | None = None
        self.sandbox = False
        self.delete_mode = False
        self.sim_speed: float = 1.0
        self._sandbox_surf: pygame.Surface | None = None
        self._delete_surf: pygame.Surface | None = None
        self._on_pop_change: "callable | None" = None
        # Button rects (set during draw)
        self._btn_minus = pygame.Rect(0, 0, 0, 0)
        self._btn_plus = pygame.Rect(0, 0, 0, 0)

    def set_on_pop_change(self, callback) -> None:
        """Register callback(delta) for sandbox population +/- buttons."""
        self._on_pop_change = callback

    def layout(self, screen_w: int, screen_h: int) -> None:
        self.rect = pygame.Rect(0, 0, screen_w, _BAR_HEIGHT)

    def draw(self, surface: pygame.Surface, world: World) -> None:
        inv = world.inventory

        # Rebuild text surfaces only when values change
        res_vals = tuple(round(inv[r], 1) for r in Resource)
        pop = world.population.count
        housing = world.connected_housing()
        cache_key = (pop, housing, res_vals)

        if cache_key != self._cache_key:
            self._cache_key = cache_key
            self._rendered = []
            for res in Resource:
                icon_surf = self._icon_font.render(
                    _RESOURCE_ICONS[res], True, _RESOURCE_COLORS[res],
                )
                val_surf = self._val_font.render(
                    f"{inv[res]:.1f}", True, UI_TEXT,
                )
                self._rendered.append((icon_surf, val_surf))
            self._pop_icon = self._icon_font.render("\u263a", True, _PERSON_COLOR)
            # Show pop/housing, colour red if over capacity
            pop_color = (200, 60, 60) if pop > housing else UI_TEXT
            self._pop_text = self._val_font.render(
                f"{pop}/{housing}", True, pop_color,
            )

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
            x += self._pop_text.get_width() + 4

            # Sandbox +/- buttons
            if self.sandbox:
                btn_sz = 20
                btn_y = cy - btn_sz // 2
                self._btn_minus = pygame.Rect(x, btn_y, btn_sz, btn_sz)
                pygame.draw.rect(surface, UI_BORDER, self._btn_minus, border_radius=3)
                ms = self._btn_font.render("\u2212", True, UI_TEXT)  # −
                surface.blit(ms, (self._btn_minus.x + (btn_sz - ms.get_width()) // 2,
                                  self._btn_minus.y + (btn_sz - ms.get_height()) // 2))
                x += btn_sz + 2
                self._btn_plus = pygame.Rect(x, btn_y, btn_sz, btn_sz)
                pygame.draw.rect(surface, UI_BORDER, self._btn_plus, border_radius=3)
                ps = self._btn_font.render("+", True, UI_TEXT)
                surface.blit(ps, (self._btn_plus.x + (btn_sz - ps.get_width()) // 2,
                                  self._btn_plus.y + (btn_sz - ps.get_height()) // 2))
                x += btn_sz + 4

            x += _ITEM_GAP

        # Separator
        pygame.draw.line(surface, UI_BORDER, (x, 6), (x, _BAR_HEIGHT - 6), 1)
        x += _ITEM_GAP // 2

        # Resources
        for icon_surf, val_surf in self._rendered:
            surface.blit(icon_surf, (x, cy - icon_surf.get_height() // 2))
            x += icon_surf.get_width() + 4
            surface.blit(val_surf, (x, cy - val_surf.get_height() // 2))
            x += val_surf.get_width() + _ITEM_GAP

        # Starvation warning (pulsing when food is at 0)
        if world.starvation_timer > 0:
            import math
            pulse = int(180 + 75 * math.sin(world.time_elapsed * 6))
            warn_col = (pulse, 40, 40)
            secs_left = max(0, 10.0 - world.starvation_timer)
            warn_text = f"\u26a0 STARVING ({secs_left:.0f}s)"
            warn_surf = self._val_font.render(warn_text, True, warn_col)
            surface.blit(warn_surf, (x, cy - warn_surf.get_height() // 2))
            x += warn_surf.get_width() + _ITEM_GAP
        elif inv[Resource.FOOD] < 10:
            warn_surf = self._val_font.render("\u26a0 Food low!", True, (200, 140, 40))
            surface.blit(warn_surf, (x, cy - warn_surf.get_height() // 2))
            x += warn_surf.get_width() + _ITEM_GAP

        # Right-aligned indicators
        rx = self.rect.right - _PADDING_X

        # Speed indicator
        if self.sim_speed > 1.0:
            speed_text = f"{self.sim_speed:.0f}x"
            speed_surf = self._val_font.render(speed_text, True, UI_ACCENT)
            rx -= speed_surf.get_width()
            surface.blit(speed_surf, (rx, cy - speed_surf.get_height() // 2))
            rx -= _ITEM_GAP // 2

        # Sandbox indicator
        if self.sandbox:
            if self._sandbox_surf is None:
                self._sandbox_surf = self._val_font.render(
                    "SANDBOX", True, UI_ACCENT,
                )
            rx -= self._sandbox_surf.get_width()
            surface.blit(self._sandbox_surf, (rx, cy - self._sandbox_surf.get_height() // 2))
            rx -= _ITEM_GAP // 2

        # Delete mode indicator
        if self.delete_mode:
            if self._delete_surf is None:
                self._delete_surf = self._val_font.render(
                    "DELETE [X]", True, (200, 60, 60),
                )
            rx -= self._delete_surf.get_width()
            surface.blit(self._delete_surf, (rx, cy - self._delete_surf.get_height() // 2))

    def handle_event(self, event: pygame.event.Event) -> bool:
        if not self.sandbox:
            return False
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self._btn_minus.collidepoint(event.pos):
                if self._on_pop_change:
                    self._on_pop_change(-1)
                return True
            if self._btn_plus.collidepoint(event.pos):
                if self._on_pop_change:
                    self._on_pop_change(1)
                return True
        return False
