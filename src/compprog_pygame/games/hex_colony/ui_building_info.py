"""Building info popup — shown when a hex with a building is selected.

Displays building-specific information:
* Camp: population, all resource totals, housing capacity.
* House: residents / capacity.
* Production buildings: worker count, resource rates (placeholder).
* Storage: stored amount (placeholder).

The popup anchors to the right side of the screen, vertically centred.
Set ``BuildingInfoPanel.building`` to a ``Building`` to show the popup,
or ``None`` to hide it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pygame

from compprog_pygame.games.hex_colony.buildings import (
    BUILDING_HOUSING,
    BUILDING_STORAGE_CAPACITY,
    BuildingType,
)
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
    from compprog_pygame.games.hex_colony.buildings import Building
    from compprog_pygame.games.hex_colony.world import World


_PANEL_W = 240
_PADDING = 10
_LINE_H = 24

_RES_ICON: dict[Resource, str] = {
    Resource.WOOD: "\u25b2",
    Resource.FIBER: "\u2022",
    Resource.STONE: "\u25a0",
    Resource.FOOD: "\u2665",
}

_RES_COL: dict[Resource, tuple[int, int, int]] = {
    Resource.WOOD: (160, 100, 50),
    Resource.FIBER: (120, 200, 80),
    Resource.STONE: (170, 170, 160),
    Resource.FOOD: (220, 100, 80),
}

_BUILDING_LABEL: dict[BuildingType, str] = {
    BuildingType.CAMP: "Camp",
    BuildingType.HOUSE: "House",
    BuildingType.PATH: "Path",
    BuildingType.WOODCUTTER: "Woodcutter",
    BuildingType.QUARRY: "Quarry",
    BuildingType.GATHERER: "Gatherer",
    BuildingType.STORAGE: "Storage",
}


class BuildingInfoPanel(Panel):
    """Pop-up panel showing details about the selected building."""

    def __init__(self) -> None:
        super().__init__()
        self._title_font = pygame.font.Font(None, 28)
        self._font = pygame.font.Font(None, 22)
        self._small = pygame.font.Font(None, 20)
        self.building: Building | None = None
        self._screen_w = 0
        self._screen_h = 0

    def layout(self, screen_w: int, screen_h: int) -> None:
        self._screen_w = screen_w
        self._screen_h = screen_h
        # Rect is recomputed each draw based on content height
        self.rect = pygame.Rect(screen_w - _PANEL_W - 10, 50, _PANEL_W, 100)

    def draw(self, surface: pygame.Surface, world: World) -> None:
        if self.building is None:
            return

        b = self.building
        lines: list[tuple[str, tuple[int, int, int], pygame.font.Font]] = []

        # Title
        label = _BUILDING_LABEL.get(b.type, b.type.name)
        lines.append((label, UI_ACCENT, self._title_font))

        # Housing info for dwellings
        cap = BUILDING_HOUSING.get(b.type, 0)
        if cap > 0:
            if b.type == BuildingType.CAMP and b.residents > cap:
                res_text = f"Residents: ({cap}+{b.residents - cap})/{cap}"
                lines.append((res_text, (200, 60, 60), self._font))
            else:
                lines.append((f"Residents: {b.residents}/{cap}", UI_TEXT, self._font))

        # Camp-specific: show all resources + total population + housing
        if b.type == BuildingType.CAMP:
            lines.append(("", UI_TEXT, self._small))  # spacer
            total_housing = world.connected_housing()
            pop = world.population.count
            homeless = max(0, pop - total_housing)
            lines.append((f"Population: {pop}/{total_housing}", UI_TEXT, self._font))
            if homeless > 0:
                lines.append((f"Homeless: {homeless}", (200, 60, 60), self._font))
            lines.append(("", UI_TEXT, self._small))  # spacer
            lines.append(("Resources:", UI_MUTED, self._small))
            for res in Resource:
                icon = _RES_ICON[res]
                val = int(world.inventory[res])
                lines.append((f"  {icon} {res.name.capitalize()}: {val}", _RES_COL[res], self._font))

        # Workers for production buildings
        if b.max_workers > 0:
            lines.append((f"Workers: {b.workers}/{b.max_workers}", UI_TEXT, self._font))

        # Storage info
        if b.storage_capacity > 0:
            lines.append(("", UI_TEXT, self._small))  # spacer
            stored = int(b.stored_total)
            lines.append((f"Storage: {stored}/{b.storage_capacity}", UI_TEXT, self._font))
            for res, amount in b.storage.items():
                if amount > 0:
                    icon = _RES_ICON[res]
                    lines.append((f"  {icon} {res.name.capitalize()}: {int(amount)}", _RES_COL[res], self._font))

        # Compute panel height
        panel_h = _PADDING * 2
        for text, _, font in lines:
            if text == "":
                panel_h += 6  # spacer
            else:
                panel_h += _LINE_H

        # Position: right side, vertically centred
        x = self._screen_w - _PANEL_W - 10
        y = max(50, (self._screen_h - panel_h) // 2)
        self.rect = pygame.Rect(x, y, _PANEL_W, panel_h)

        draw_panel_bg(surface, self.rect, accent_edge="top")

        # Render lines
        cy = y + _PADDING
        for text, color, font in lines:
            if text == "":
                cy += 6
                continue
            surf = font.render(text, True, color)
            surface.blit(surf, (x + _PADDING, cy))
            cy += _LINE_H

    def handle_event(self, event: pygame.event.Event) -> bool:
        if self.building is None:
            return False
        # Consume clicks inside the panel so they don't select world hexes
        if hasattr(event, "pos") and self.rect.collidepoint(event.pos):
            return True
        return False
