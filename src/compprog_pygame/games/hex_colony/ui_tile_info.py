"""Tile info popup — shown when a hex without a building is selected.

Displays terrain name/description, resource info, passability, and
coordinates.  Anchored to the right side of the screen, vertically
centred, with height clamped to fit between the top resource bar and
the bottom bar tab strip.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pygame

from compprog_pygame.games.hex_colony.hex_grid import HexCoord, HexTile, Terrain
from compprog_pygame.games.hex_colony.resources import TERRAIN_RESOURCE
from compprog_pygame.games.hex_colony.ui import (
    Fonts,
    Panel,
    RESOURCE_COLORS,
    RESOURCE_ICONS,
    UI_ACCENT,
    UI_BAD,
    UI_MUTED,
    UI_OK,
    UI_TEXT,
    draw_panel_bg,
    render_text_clipped,
    wrap_text,
)

if TYPE_CHECKING:
    from compprog_pygame.games.hex_colony.world import World


_PANEL_W = 240
_PADDING = 12
_LINE_H = 22
_SPACER_H = 8
_TOP_MARGIN = 48
_BOTTOM_MARGIN = 44

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
        self.tile: HexTile | None = None
        self.coord: HexCoord | None = None
        self._screen_w = 0
        self._screen_h = 0

    def layout(self, screen_w: int, screen_h: int) -> None:
        self._screen_w = screen_w
        self._screen_h = screen_h
        self.rect = pygame.Rect(
            screen_w - _PANEL_W - 10, _TOP_MARGIN, _PANEL_W, 100,
        )

    def draw(self, surface: pygame.Surface, world: World) -> None:
        if self.tile is None:
            return

        tile = self.tile
        inner_w = _PANEL_W - _PADDING * 2
        lines: list[tuple[str, tuple[int, int, int], pygame.font.Font, int]] = []

        def add(text: str, color: tuple[int, int, int],
                font: pygame.font.Font, h: int = _LINE_H) -> None:
            lines.append((text, color, font, h))

        def spacer() -> None:
            lines.append(("", UI_TEXT, Fonts.small(), _SPACER_H))

        label = _TERRAIN_LABEL.get(tile.terrain, tile.terrain.name)
        color = _TERRAIN_COLOR.get(tile.terrain, UI_ACCENT)
        add(label, color, Fonts.title(), 32)

        desc = _TERRAIN_DESC.get(tile.terrain, "")
        if desc:
            for wl in wrap_text(Fonts.small(), desc, inner_w):
                add(wl, UI_MUTED, Fonts.small())
        spacer()

        resource = TERRAIN_RESOURCE.get(tile.terrain)
        if resource is not None:
            icon = RESOURCE_ICONS.get(resource, "?")
            res_color = RESOURCE_COLORS.get(resource, UI_TEXT)
            add("Resource:", UI_MUTED, Fonts.small())
            add(f"  {icon} {resource.name.capitalize()}",
                res_color, Fonts.body())
            amount = int(tile.resource_amount)
            if amount > 0:
                add(f"  Remaining: {amount}", UI_TEXT, Fonts.body())
            else:
                add("  Depleted", UI_BAD, Fonts.body())
        else:
            add("No harvestable resource", UI_MUTED, Fonts.small())
        spacer()

        from compprog_pygame.games.hex_colony.procgen import IMPASSABLE
        if tile.terrain in IMPASSABLE:
            add("Impassable", UI_BAD, Fonts.body())
        else:
            add("Passable", UI_OK, Fonts.body())

        if self.coord is not None:
            add(f"Coords: ({self.coord.q}, {self.coord.r})",
                UI_MUTED, Fonts.small())

        panel_h = _PADDING * 2 + sum(h for _, _, _, h in lines)
        max_h = self._screen_h - _TOP_MARGIN - _BOTTOM_MARGIN
        panel_h = min(panel_h, max(120, max_h))

        x = self._screen_w - _PANEL_W - 10
        y = max(_TOP_MARGIN, (self._screen_h - panel_h) // 2)
        if y + panel_h > self._screen_h - _BOTTOM_MARGIN:
            y = self._screen_h - _BOTTOM_MARGIN - panel_h
        y = max(_TOP_MARGIN, y)

        self.rect = pygame.Rect(x, y, _PANEL_W, panel_h)
        draw_panel_bg(surface, self.rect, accent_edge="top")

        prev_clip = surface.get_clip()
        surface.set_clip(self.rect)
        cy = y + _PADDING
        for text, col, font, h in lines:
            if text:
                surf = render_text_clipped(font, text, col, inner_w)
                surface.blit(surf, (x + _PADDING, cy))
            cy += h
        surface.set_clip(prev_clip)

    def handle_event(self, event: pygame.event.Event) -> bool:
        if self.tile is None:
            return False
        if hasattr(event, "pos") and self.rect.collidepoint(event.pos):
            return True
        return False
