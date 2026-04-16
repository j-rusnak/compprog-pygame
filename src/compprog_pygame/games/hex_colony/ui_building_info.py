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
    BUILDING_COSTS,
    BUILDING_HOUSING,
    BuildingType,
)
from compprog_pygame.games.hex_colony.resources import Resource
from compprog_pygame.games.hex_colony import params
from compprog_pygame.games.hex_colony.ui import (
    Panel,
    RESOURCE_COLORS,
    RESOURCE_ICONS,
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

_BUILDING_LABEL: dict[BuildingType, str] = {
    BuildingType.CAMP: "Camp",
    BuildingType.HOUSE: "House",
    BuildingType.PATH: "Path",
    BuildingType.WOODCUTTER: "Woodcutter",
    BuildingType.QUARRY: "Quarry",
    BuildingType.GATHERER: "Gatherer",
    BuildingType.STORAGE: "Storage",
    BuildingType.WORKSHOP: "Workshop",
}

# Buildings that can be crafted in a workshop
WORKSHOP_CRAFTABLE: list[BuildingType] = [
    BuildingType.HABITAT,
    BuildingType.PATH,
    BuildingType.BRIDGE,
    BuildingType.WALL,
    BuildingType.WOODCUTTER,
    BuildingType.QUARRY,
    BuildingType.GATHERER,
    BuildingType.STORAGE,
    BuildingType.REFINERY,
    BuildingType.FARM,
    BuildingType.WELL,
    BuildingType.WORKSHOP,
]


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
        self._recipe_rects: list[tuple[pygame.Rect, BuildingType]] = []

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
                icon = RESOURCE_ICONS[res]
                val = int(world.inventory[res])
                lines.append((f"  {icon} {res.name.capitalize()}: {val}", RESOURCE_COLORS[res], self._font))

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
                    icon = RESOURCE_ICONS[res]
                    lines.append((f"  {icon} {res.name.capitalize()}: {int(amount)}", RESOURCE_COLORS[res], self._font))

        # Workshop recipe & progress
        workshop_lines_start = -1
        if b.type == BuildingType.WORKSHOP:
            lines.append(("", UI_TEXT, self._small))  # spacer
            if b.recipe is not None:
                recipe_name = b.recipe.name.replace("_", " ").title()
                lines.append((f"Crafting: {recipe_name}", UI_ACCENT, self._font))
                pct = int(b.craft_progress / params.WORKSHOP_CRAFT_TIME * 100)
                lines.append((f"Progress: {pct}%", UI_TEXT, self._font))
                # Show resource cost for the recipe
                cost = BUILDING_COSTS[b.recipe]
                for res, amount in cost.costs.items():
                    icon = RESOURCE_ICONS[res]
                    has = world.inventory[res] >= amount
                    col = RESOURCE_COLORS[res] if has else (200, 60, 60)
                    lines.append((f"  {icon} {amount}", col, self._small))
            else:
                lines.append(("Select recipe:", UI_MUTED, self._font))
            workshop_lines_start = len(lines)

        # Compute panel height
        panel_h = _PADDING * 2
        for text, _, font in lines:
            if text == "":
                panel_h += 6  # spacer
            else:
                panel_h += _LINE_H

        # Extra height for workshop recipe buttons
        recipe_btn_h = 0
        if b.type == BuildingType.WORKSHOP:
            recipe_btn_h = len(WORKSHOP_CRAFTABLE) * (_LINE_H + 2) + 4
            panel_h += recipe_btn_h

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

        # Render workshop recipe buttons
        self._recipe_rects = []
        if b.type == BuildingType.WORKSHOP and workshop_lines_start >= 0:
            for craft_type in WORKSHOP_CRAFTABLE:
                btn_rect = pygame.Rect(x + _PADDING, cy, _PANEL_W - _PADDING * 2, _LINE_H)
                is_selected = b.recipe == craft_type
                bg_col = UI_ACCENT if is_selected else UI_BG
                pygame.draw.rect(surface, bg_col, btn_rect, border_radius=3)
                pygame.draw.rect(surface, UI_BORDER, btn_rect, width=1, border_radius=3)
                label = craft_type.name.replace("_", " ").title()
                text_surf = self._small.render(label, True, UI_TEXT)
                surface.blit(text_surf, (btn_rect.x + 6, btn_rect.y + 3))
                self._recipe_rects.append((btn_rect, craft_type))
                cy += _LINE_H + 2

    def handle_event(self, event: pygame.event.Event) -> bool:
        if self.building is None:
            return False
        # Consume clicks inside the panel so they don't select world hexes
        if hasattr(event, "pos") and self.rect.collidepoint(event.pos):
            # Handle workshop recipe selection
            if (event.type == pygame.MOUSEBUTTONDOWN and event.button == 1
                    and self.building.type == BuildingType.WORKSHOP):
                for btn_rect, craft_type in self._recipe_rects:
                    if btn_rect.collidepoint(event.pos):
                        if self.building.recipe == craft_type:
                            self.building.recipe = None
                            self.building.craft_progress = 0.0
                        else:
                            self.building.recipe = craft_type
                            self.building.craft_progress = 0.0
                        return True
            return True
        return False
