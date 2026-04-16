"""UI framework for Hex Colony.

Architecture
------------
The UI is built from **panels** managed by a central ``UIManager``.

* ``Panel`` — abstract base for any rectangular screen-space element.
  Every panel implements ``draw()``, optionally ``handle_event()``, and
  ``layout()`` (called when the window resizes).

* ``UIManager`` — owns all panels, dispatches events top-to-bottom
  (front-to-back), calls ``layout()`` on resize, and draws back-to-front.

Adding a new panel
~~~~~~~~~~~~~~~~~~
1.  Subclass ``Panel``.
2.  Override ``layout(sw, sh)`` to set ``self.rect``.
3.  Override ``draw(surface, world)`` to render content.
4.  Optionally override ``handle_event(event) -> bool`` (return True to
    consume the event so panels beneath don't see it).
5.  Register the panel with ``ui_manager.add_panel(my_panel)``.

Adding a new tab to the bottom bar
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
1.  Subclass ``TabContent``.
2.  Override ``draw_content(surface, rect, world)`` to render content
    inside the tab's content area.
3.  Optionally override ``handle_event(event, rect) -> bool``.
4.  Add an entry in ``_create_default_tabs()`` inside ``BottomBar``, or
    call ``bottom_bar.add_tab("Label", my_content_instance)`` at runtime.

Colour constants shared across all panels live here so the look stays
consistent.  Import them instead of defining duplicates.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import pygame

if TYPE_CHECKING:
    from compprog_pygame.games.hex_colony.world import World

from compprog_pygame.games.hex_colony.resources import Resource


# ── Shared colour palette ────────────────────────────────────────

UI_BG = (16, 24, 45, 220)
UI_BG_OPAQUE = (16, 24, 45)
UI_TEXT = (242, 244, 255)
UI_MUTED = (140, 150, 175)
UI_ACCENT = (200, 160, 60)
UI_BORDER = (60, 70, 100)
UI_TAB_ACTIVE = (35, 50, 85, 240)
UI_TAB_HOVER = (30, 42, 72, 200)
UI_TAB_INACTIVE = (16, 24, 45, 200)

# ── Resource display constants (shared across all panels) ────────

RESOURCE_ICONS: dict[Resource, str] = {
    Resource.WOOD: "\u25b2",   # ▲
    Resource.FIBER: "\u2022",  # •
    Resource.STONE: "\u25a0",  # ■
    Resource.FOOD: "\u2665",   # ♥
    Resource.IRON: "\u25c6",   # ◆
    Resource.COPPER: "\u25c8", # ◈
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
    """Abstract UI panel drawn in screen space.

    Subclasses must set ``self.rect`` in ``layout()`` and render into
    the given surface in ``draw()``.
    """

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
        """Process an input event.  Return True to consume it."""
        return False


# ── UIManager ────────────────────────────────────────────────────

class UIManager:
    """Owns all UI panels and orchestrates layout, drawing, and events.

    Panels are drawn back-to-front (index 0 first) and receive events
    front-to-back (last panel first) so overlapping panels work correctly.
    """

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
        """Dispatch *event* front-to-back; stop at the first consumer."""
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
        """Return True if *pos* is inside any visible panel."""
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


# ── Helpers ──────────────────────────────────────────────────────

def draw_panel_bg(
    surface: pygame.Surface,
    rect: pygame.Rect,
    *,
    accent_edge: str = "top",
) -> None:
    """Draw a semi-transparent panel background with optional accent line."""
    bg = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
    bg.fill(UI_BG)
    surface.blit(bg, rect.topleft)
    pygame.draw.rect(surface, UI_BORDER, rect, width=2, border_radius=4)
    if accent_edge == "top":
        pygame.draw.line(surface, UI_ACCENT, rect.topleft, rect.topright, 2)
    elif accent_edge == "bottom":
        pygame.draw.line(
            surface, UI_ACCENT, rect.bottomleft, rect.bottomright, 2,
        )
