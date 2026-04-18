"""UI framework for Hex Colony.

Architecture
------------
The UI is built from **panels** managed by a central ``UIManager``.

* ``Panel`` — abstract base for any rectangular screen-space element.
  Every panel implements ``draw()``, optionally ``handle_event()``, and
  ``layout()`` (called when the window resizes).

* ``UIManager`` — owns all panels, dispatches events front-to-back,
  calls ``layout()`` on resize, and draws back-to-front.

Theme and primitives (fonts, colours, buttons, text clipping) live in
``ui_theme``.  Import them from there (this module re-exports them for
backward compatibility).

Adding a new panel
~~~~~~~~~~~~~~~~~~
1.  Subclass ``Panel``.
2.  Override ``layout(sw, sh)`` to set ``self.rect``.
3.  Override ``draw(surface, world)`` to render content.
4.  Optionally override ``handle_event(event) -> bool`` (return True to
    consume the event so panels beneath don't see it).
5.  Register the panel with ``ui_manager.add_panel(my_panel)``.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

import pygame

if TYPE_CHECKING:
    from compprog_pygame.games.hex_colony.world import World

from compprog_pygame.games.hex_colony.resources import Resource
from compprog_pygame.games.hex_colony.ui_theme import (  # re-export
    Fonts,
    UI_ACCENT,
    UI_BAD,
    UI_BG,
    UI_BG_OPAQUE,
    UI_BG_SOLID,
    UI_BORDER,
    UI_BORDER_LIGHT,
    UI_BTN_ACTIVE,
    UI_BTN_BG,
    UI_BTN_DISABLED,
    UI_BTN_HOVER,
    UI_MUTED,
    UI_OK,
    UI_OVERLAY,
    UI_TAB_ACTIVE,
    UI_TAB_HOVER,
    UI_TAB_INACTIVE,
    UI_TEXT,
    UI_WARN,
    draw_button,
    draw_panel_bg,
    draw_progress_bar,
    draw_titled_panel,
    render_text_clipped,
    wrap_text,
)


# ── Resource display constants (shared across all panels) ────────

RESOURCE_ICONS: dict[Resource, str] = {
    Resource.WOOD: "\u2663",
    Resource.FIBER: "\u2740",
    Resource.STONE: "\u25a3",
    Resource.FOOD: "\u2665",
    Resource.IRON: "\u25c6",
    Resource.COPPER: "\u25c7",
    Resource.PLANKS: "\u25ad",
    Resource.IRON_BAR: "\u25ac",
    Resource.COPPER_BAR: "\u25ac",
    Resource.BRICKS: "\u25a7",
    Resource.COPPER_WIRE: "\u03b6",
    Resource.ROPE: "\u2683",
    Resource.CHARCOAL: "\u25ac",
    Resource.GLASS: "\u25a1",
    Resource.STEEL_BAR: "\u25ac",
    Resource.GEARS: "\u2699",
    Resource.SILICON: "\u2b22",
    Resource.CIRCUIT: "\u25a6",
}

RESOURCE_COLORS: dict[Resource, tuple[int, int, int]] = {
    Resource.WOOD: (160, 100, 50),
    Resource.FIBER: (120, 200, 80),
    Resource.STONE: (170, 170, 160),
    Resource.FOOD: (220, 100, 80),
    Resource.IRON: (180, 110, 75),
    Resource.COPPER: (80, 180, 120),
    Resource.PLANKS: (210, 170, 110),
    Resource.IRON_BAR: (170, 180, 200),
    Resource.COPPER_BAR: (225, 150, 90),
    Resource.BRICKS: (200, 120, 90),
    Resource.COPPER_WIRE: (240, 180, 110),
    Resource.ROPE: (200, 170, 120),
    Resource.CHARCOAL: (90, 85, 85),
    Resource.GLASS: (180, 220, 235),
    Resource.STEEL_BAR: (190, 200, 220),
    Resource.GEARS: (170, 175, 195),
    Resource.SILICON: (150, 160, 200),
    Resource.CIRCUIT: (120, 210, 140),
}


# ── Panel base class ─────────────────────────────────────────────

class Panel(ABC):
    """Abstract UI panel drawn in screen space."""

    def __init__(self) -> None:
        self.rect: pygame.Rect = pygame.Rect(0, 0, 0, 0)
        self.visible: bool = True

    @abstractmethod
    def layout(self, screen_w: int, screen_h: int) -> None:
        """Recompute ``self.rect`` for the given screen dimensions."""

    @abstractmethod
    def draw(self, surface: pygame.Surface, world: World) -> None:
        """Render the panel onto *surface*."""

    def handle_event(self, event: pygame.event.Event) -> bool:
        """Process an input event. Return True to consume it."""
        return False


# ── UIManager ────────────────────────────────────────────────────

class UIManager:
    """Owns all UI panels and orchestrates layout, drawing, and events."""

    def __init__(self) -> None:
        self._panels: list[Panel] = []
        self._screen_size: tuple[int, int] = (0, 0)

    def add_panel(self, panel: Panel) -> None:
        self._panels.append(panel)

    def layout(self, screen_w: int, screen_h: int) -> None:
        self._screen_size = (screen_w, screen_h)
        for panel in self._panels:
            panel.layout(screen_w, screen_h)

    def handle_event(self, event: pygame.event.Event) -> bool:
        for panel in reversed(self._panels):
            if not panel.visible:
                continue
            if panel.handle_event(event):
                return True
        return False

    def draw(self, surface: pygame.Surface, world: World) -> None:
        sw, sh = surface.get_size()
        if (sw, sh) != self._screen_size:
            self.layout(sw, sh)
        for panel in self._panels:
            if panel.visible:
                panel.draw(surface, world)
        # Render any tooltip set by panels during draw (drawn last so
        # it always appears on top of other UI elements).
        _draw_pending_tooltip(surface)

    def hit_test(self, pos: tuple[int, int]) -> bool:
        for panel in reversed(self._panels):
            if panel.visible and panel.rect.collidepoint(pos):
                return True
        return False


# ── TabContent base class ────────────────────────────────────────


# ── Tooltip system (set by any panel during draw) ────────────────

_pending_tooltip: str | None = None


def set_tooltip(text: str) -> None:
    """Schedule a tooltip to be drawn at end-of-frame at the cursor."""
    global _pending_tooltip
    _pending_tooltip = text


def _draw_pending_tooltip(surface: pygame.Surface) -> None:
    global _pending_tooltip
    text = _pending_tooltip
    _pending_tooltip = None
    if not text:
        return
    font = Fonts.small()
    pad_x, pad_y = 6, 3
    text_surf = font.render(text, True, UI_TEXT)
    box_w = text_surf.get_width() + pad_x * 2
    box_h = text_surf.get_height() + pad_y * 2
    mx, my = pygame.mouse.get_pos()
    sw, sh = surface.get_size()
    # Place above the cursor with a small gap; flip below if it would
    # clip off the top of the screen.
    bx = mx + 14
    by = my - box_h - 8
    if by < 2:
        by = my + 18
    bx = max(2, min(bx, sw - box_w - 2))
    box = pygame.Rect(bx, by, box_w, box_h)
    bg = pygame.Surface((box_w, box_h), pygame.SRCALPHA)
    bg.fill((20, 24, 28, 235))
    surface.blit(bg, box.topleft)
    pygame.draw.rect(surface, UI_BORDER, box, width=1, border_radius=3)
    surface.blit(text_surf, (bx + pad_x, by + pad_y))


class TabContent(ABC):
    """Content drawn inside a tab of the ``BottomBar``."""

    @abstractmethod
    def draw_content(
        self, surface: pygame.Surface, rect: pygame.Rect, world: World,
    ) -> None:
        """Draw into the content area *rect* on *surface*."""

    def handle_event(
        self, event: pygame.event.Event, rect: pygame.Rect,
    ) -> bool:
        """Handle event within *rect*. Return True to consume."""
        return False

