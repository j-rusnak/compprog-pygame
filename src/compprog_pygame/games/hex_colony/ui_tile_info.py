"""Tile info popup — shown when a hex without a building is selected.

Displays tile-specific information:
* Terrain type and description.
* Resource type and remaining amount (if the tile yields a resource).
* Coordinates.
* Passability.

The popup anchors to the right side of the screen, vertically centred.
Set ``TileInfoPanel.tile`` and ``.coord`` to show the popup, or set
``.tile`` to ``None`` to hide it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pygame

from compprog_pygame.games.hex_colony.hex_grid import HexCoord, HexTile, Terrain
from compprog_pygame.games.hex_colony.resources import TERRAIN_RESOURCE
from compprog_pygame.games.hex_colony.ui import (
    Panel,
    RESOURCE_COLORS,
    RESOURCE_ICONS,
    UI_ACCENT,
    UI_MUTED,
    UI_TEXT,
    draw_panel_bg,
)

if TYPE_CHECKING:
    from compprog_pygame.games.hex_colony.world import World


_PANEL_W = 220
_PADDING = 10
_LINE_H = 22

_TERRAIN_LABEL: dict[Terrain, str] = {
    Terrain.GRASS: "Grassland",
    Terrain.FOREST: "Forest",
    Terrain.DENSE_FOREST: "Dense Forest",
    Terrain.STONE_DEPOSIT: "Stone Deposit",
    Terrain.WATER: "Water",
    Terrain.FIBER_PATCH: "Fiber Patch",
    Terrain.MOUNTAIN: "Mountain",
    Terrain.IRON_VEIN: "Iron Vein",
    Terrain.COPPER_VEIN: "Copper Vein",
}

_TERRAIN_DESC: dict[Terrain, str] = {
    Terrain.GRASS: "Open terrain, good for building.",
    Terrain.FOREST: "Trees provide wood.",
    Terrain.DENSE_FOREST: "Thick forest, rich in wood.",
    Terrain.STONE_DEPOSIT: "Rocky outcrop, yields stone.",
    Terrain.WATER: "Impassable body of water.",
    Terrain.FIBER_PATCH: "Wild fibers and berries.",
    Terrain.MOUNTAIN: "Impassable mountain peak.",
    Terrain.IRON_VEIN: "Iron ore deposits.",
    Terrain.COPPER_VEIN: "Copper ore deposits.",
}

_TERRAIN_COLOR: dict[Terrain, tuple[int, int, int]] = {
    Terrain.GRASS: (100, 180, 80),
    Terrain.FOREST: (60, 140, 60),
    Terrain.DENSE_FOREST: (40, 100, 44),
    Terrain.STONE_DEPOSIT: (170, 170, 160),
    Terrain.WATER: (60, 120, 220),
    Terrain.FIBER_PATCH: (130, 180, 60),
    Terrain.MOUNTAIN: (140, 130, 120),
    Terrain.IRON_VEIN: (180, 110, 75),
    Terrain.COPPER_VEIN: (80, 180, 120),
}


class TileInfoPanel(Panel):
    """Pop-up panel showing details about the selected tile."""

    def __init__(self) -> None:
        super().__init__()
        self._title_font = pygame.font.Font(None, 28)
        self._font = pygame.font.Font(None, 22)
        self._small = pygame.font.Font(None, 20)
        self.tile: HexTile | None = None
        self.coord: HexCoord | None = None
        self._screen_w = 0
        self._screen_h = 0

    def layout(self, screen_w: int, screen_h: int) -> None:
        self._screen_w = screen_w
        self._screen_h = screen_h
        self.rect = pygame.Rect(screen_w - _PANEL_W - 10, 50, _PANEL_W, 100)

    def draw(self, surface: pygame.Surface, world: World) -> None:
        if self.tile is None:
            return

        tile = self.tile
        lines: list[tuple[str, tuple[int, int, int], pygame.font.Font]] = []

        # Title — terrain name
        label = _TERRAIN_LABEL.get(tile.terrain, tile.terrain.name)
        color = _TERRAIN_COLOR.get(tile.terrain, UI_ACCENT)
        lines.append((label, color, self._title_font))

        # Description
        desc = _TERRAIN_DESC.get(tile.terrain, "")
        if desc:
            lines.append((desc, UI_MUTED, self._small))

        lines.append(("", UI_TEXT, self._small))  # spacer

        # Resource info
        resource = TERRAIN_RESOURCE.get(tile.terrain)
        if resource is not None:
            icon = RESOURCE_ICONS.get(resource, "?")
            res_color = RESOURCE_COLORS.get(resource, UI_TEXT)
            lines.append(("Resource:", UI_MUTED, self._small))
            lines.append((f"  {icon} {resource.name.capitalize()}", res_color, self._font))
            amount = int(tile.resource_amount)
            if amount > 0:
                lines.append((f"  Remaining: {amount}", UI_TEXT, self._font))
            else:
                lines.append(("  Depleted", (200, 60, 60), self._font))
        else:
            lines.append(("No harvestable resource", UI_MUTED, self._small))

        lines.append(("", UI_TEXT, self._small))  # spacer

        # Passability
        from compprog_pygame.games.hex_colony.procgen import IMPASSABLE
        if tile.terrain in IMPASSABLE:
            lines.append(("Impassable", (200, 60, 60), self._font))
        else:
            lines.append(("Passable", (80, 200, 80), self._font))

        # Coordinates
        if self.coord is not None:
            lines.append((f"Coords: ({self.coord.q}, {self.coord.r})", UI_MUTED, self._small))

        # Compute panel height
        panel_h = _PADDING * 2
        for text, _, font in lines:
            if text == "":
                panel_h += 6
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
        if self.tile is None:
            return False
        if hasattr(event, "pos") and self.rect.collidepoint(event.pos):
            return True
        return False
