"""Minimap panel for Hex Colony.

Shows a small overview of the full map in the bottom-right corner,
with the current camera viewport highlighted.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pygame

from compprog_pygame.games.hex_colony.buildings import BuildingType
from compprog_pygame.games.hex_colony.hex_grid import HexCoord, hex_to_pixel
from compprog_pygame.games.hex_colony.render_utils import (
    BUILDING_COLORS,
    TERRAIN_BASE_COLOR,
)
from compprog_pygame.games.hex_colony.ui import Panel, UI_BG, UI_BORDER

if TYPE_CHECKING:
    from compprog_pygame.games.hex_colony.camera import Camera
    from compprog_pygame.games.hex_colony.world import World

_MAP_SIZE = 160
_MARGIN = 8


class MinimapPanel(Panel):
    """Small overview map in the bottom-right corner."""

    def __init__(self) -> None:
        super().__init__()
        self._minimap_surf: pygame.Surface | None = None
        self._dirty = True
        self._world_bounds: tuple[float, float, float, float] = (0, 0, 1, 1)
        self.camera: Camera | None = None

    def layout(self, screen_w: int, screen_h: int) -> None:
        self.rect = pygame.Rect(
            screen_w - _MAP_SIZE - _MARGIN,
            38 + _MARGIN,  # just under the resource bar (height 38)
            _MAP_SIZE, _MAP_SIZE,
        )
        self._dirty = True

    def invalidate(self) -> None:
        self._dirty = True

    def _rebuild(self, world: World) -> None:
        """Render the minimap texture from world state."""
        size = world.settings.hex_size
        # Compute world bounds
        min_wx = min_wy = float('inf')
        max_wx = max_wy = float('-inf')
        coords = list(world.grid.coords())
        if not coords:
            return
        for coord in coords:
            wx, wy = hex_to_pixel(coord, size)
            min_wx = min(min_wx, wx)
            min_wy = min(min_wy, wy)
            max_wx = max(max_wx, wx)
            max_wy = max(max_wy, wy)

        pad = size * 2
        min_wx -= pad
        min_wy -= pad
        max_wx += pad
        max_wy += pad
        self._world_bounds = (min_wx, min_wy, max_wx, max_wy)

        w_range = max_wx - min_wx
        h_range = max_wy - min_wy
        if w_range < 1 or h_range < 1:
            return

        surf = pygame.Surface((_MAP_SIZE, _MAP_SIZE), pygame.SRCALPHA)
        surf.fill((16, 24, 45, 200))

        scale = min((_MAP_SIZE - 4) / w_range, (_MAP_SIZE - 4) / h_range)

        for coord in coords:
            wx, wy = hex_to_pixel(coord, size)
            mx = int((wx - min_wx) * scale) + 2
            my = int((wy - min_wy) * scale) + 2
            tile = world.grid[coord]
            # Show building color if present, else terrain
            building = world.buildings.at(coord)
            if building is not None:
                color = BUILDING_COLORS.get(building.type, (200, 200, 200))
            else:
                color = TERRAIN_BASE_COLOR.get(tile.terrain, (80, 80, 80))
            r = max(1, int(size * scale * 0.5))
            pygame.draw.circle(surf, color, (mx, my), r)

        self._minimap_surf = surf
        self._dirty = False

    def draw(self, surface: pygame.Surface, world: World) -> None:
        if self._dirty or self._minimap_surf is None:
            self._rebuild(world)
        if self._minimap_surf is None:
            return

        surface.blit(self._minimap_surf, self.rect.topleft)
        pygame.draw.rect(surface, UI_BORDER, self.rect, 1)

        # Draw camera viewport rectangle
        if self.camera is not None:
            min_wx, min_wy, max_wx, max_wy = self._world_bounds
            w_range = max_wx - min_wx
            h_range = max_wy - min_wy
            if w_range < 1 or h_range < 1:
                return
            scale = min((_MAP_SIZE - 4) / w_range, (_MAP_SIZE - 4) / h_range)

            cam = self.camera
            sw, sh = surface.get_size()
            half_vw = sw / (2 * cam.zoom)
            half_vh = sh / (2 * cam.zoom)

            vx1 = int((cam.x - half_vw - min_wx) * scale) + self.rect.x + 2
            vy1 = int((cam.y - half_vh - min_wy) * scale) + self.rect.y + 2
            vx2 = int((cam.x + half_vw - min_wx) * scale) + self.rect.x + 2
            vy2 = int((cam.y + half_vh - min_wy) * scale) + self.rect.y + 2

            vr = pygame.Rect(vx1, vy1, vx2 - vx1, vy2 - vy1)
            vr.clamp_ip(self.rect)
            pygame.draw.rect(surface, (200, 160, 60), vr, 1)

    def handle_event(self, event: pygame.event.Event) -> bool:
        """Click on minimap to pan camera."""
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.rect.collidepoint(event.pos) and self.camera is not None:
                self._pan_to(event.pos)
                return True
        if event.type == pygame.MOUSEMOTION:
            if (pygame.mouse.get_pressed()[0]
                    and self.rect.collidepoint(event.pos)
                    and self.camera is not None):
                self._pan_to(event.pos)
                return True
        return False

    def _pan_to(self, screen_pos: tuple[int, int]) -> None:
        """Move camera to the world position corresponding to a minimap click."""
        min_wx, min_wy, max_wx, max_wy = self._world_bounds
        w_range = max_wx - min_wx
        h_range = max_wy - min_wy
        if w_range < 1 or h_range < 1:
            return
        scale = min((_MAP_SIZE - 4) / w_range, (_MAP_SIZE - 4) / h_range)
        mx = screen_pos[0] - self.rect.x - 2
        my = screen_pos[1] - self.rect.y - 2
        self.camera.x = min_wx + mx / scale
        self.camera.y = min_wy + my / scale
