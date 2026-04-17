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
}

RESOURCE_COLORS: dict[Resource, tuple[int, int, int]] = {
    Resource.WOOD: (160, 100, 50),
    Resource.FIBER: (120, 200, 80),
    Resource.STONE: (170, 170, 160),
    Resource.FOOD: (220, 100, 80),
    Resource.IRON: (180, 110, 75),
    Resource.COPPER: (80, 180, 120),
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

    def hit_test(self, pos: tuple[int, int]) -> bool:
        for panel in reversed(self._panels):
            if panel.visible and panel.rect.collidepoint(pos):
                return True
        return False


# ── TabContent base class ────────────────────────────────────────

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

