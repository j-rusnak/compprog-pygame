"""Supply chain visualization for Hex Colony.

Draws animated lines between production buildings and their resource
sources when the player holds the Alt key overlay or selects a building.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pygame

from compprog_pygame.games.hex_colony.buildings import (
    BUILDING_HARVEST_RESOURCES,
    BuildingType,
)
from compprog_pygame.games.hex_colony.hex_grid import HexCoord, Terrain, hex_to_pixel
from compprog_pygame.games.hex_colony.resources import TERRAIN_RESOURCE, Resource
from compprog_pygame.games.hex_colony.render_utils import BUILDING_COLORS
from compprog_pygame.games.hex_colony.ui import RESOURCE_COLORS

if TYPE_CHECKING:
    from compprog_pygame.games.hex_colony.camera import Camera
    from compprog_pygame.games.hex_colony.world import World
    from compprog_pygame.games.hex_colony import params

# Resource color for supply lines
_LINE_ALPHA = 120
_DASH_LEN = 8
_ANIM_SPEED = 40.0  # pixels per second


def draw_supply_lines(
    surface: pygame.Surface,
    world: World,
    camera: Camera,
    selected_coord: HexCoord | None,
    tick: float,
    hex_size: int,
) -> None:
    """Draw animated resource flow lines from source tiles to production buildings."""
    from compprog_pygame.games.hex_colony import params

    zoom = camera.zoom
    if zoom < 0.3:
        return  # too zoomed out

    cam_x, cam_y = camera.x, camera.y
    sw, sh = surface.get_size()
    half_sw, half_sh = sw * 0.5, sh * 0.5

    # Only draw for selected building or all if overlay is showing
    buildings_to_show = []
    if selected_coord is not None:
        bld = world.buildings.at(selected_coord)
        if bld is not None and bld.type in BUILDING_HARVEST_RESOURCES:
            buildings_to_show.append(bld)
    else:
        return  # only show for selected building to avoid clutter

    offset = (tick * _ANIM_SPEED) % (_DASH_LEN * 2)

    for building in buildings_to_show:
        harvest_resources = BUILDING_HARVEST_RESOURCES.get(building.type, set())
        if not harvest_resources:
            continue

        bwx, bwy = hex_to_pixel(building.coord, hex_size)
        bsx = (bwx - cam_x) * zoom + half_sw
        bsy = (bwy - cam_y) * zoom + half_sh

        # Find source tiles within collection radius
        radius = params.COLLECTION_RADIUS
        for nb in _hex_range(building.coord, radius):
            tile = world.grid.get(nb)
            if tile is None:
                continue
            terrain_res = TERRAIN_RESOURCE.get(tile.terrain)
            if terrain_res is None or terrain_res not in harvest_resources:
                continue

            nwx, nwy = hex_to_pixel(nb, hex_size)
            nsx = (nwx - cam_x) * zoom + half_sw
            nsy = (nwy - cam_y) * zoom + half_sh

            # Clipping
            if (nsx < -50 or nsx > sw + 50 or nsy < -50 or nsy > sh + 50):
                continue

            color = RESOURCE_COLORS.get(terrain_res, (200, 200, 200))
            _draw_dashed_line(surface, color, (int(nsx), int(nsy)),
                              (int(bsx), int(bsy)), max(1, int(zoom * 1.5)),
                              _DASH_LEN, offset)


def _hex_range(center: HexCoord, radius: int):
    """Yield all hex coords within *radius* of *center*."""
    for dq in range(-radius, radius + 1):
        for dr in range(max(-radius, -dq - radius), min(radius, -dq + radius) + 1):
            yield HexCoord(center.q + dq, center.r + dr)


def _draw_dashed_line(
    surface: pygame.Surface,
    color: tuple[int, int, int],
    start: tuple[int, int],
    end: tuple[int, int],
    width: int,
    dash_len: int,
    offset: float,
) -> None:
    """Draw a dashed line with animation offset."""
    import math
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    dist = math.hypot(dx, dy)
    if dist < 1:
        return
    ux, uy = dx / dist, dy / dist

    pos = offset % (dash_len * 2)
    while pos < dist:
        x1 = start[0] + ux * pos
        y1 = start[1] + uy * pos
        end_pos = min(pos + dash_len, dist)
        x2 = start[0] + ux * end_pos
        y2 = start[1] + uy * end_pos
        pygame.draw.line(surface, color, (int(x1), int(y1)), (int(x2), int(y2)), width)
        pos += dash_len * 2
