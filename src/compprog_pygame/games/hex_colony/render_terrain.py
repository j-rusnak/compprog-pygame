"""Mountain terrain rendering — contours, ridge spurs, and depth-based colouring."""

from __future__ import annotations

from functools import lru_cache

import pygame

from compprog_pygame.games.hex_colony.hex_grid import HexCoord
from compprog_pygame.games.hex_colony.render_utils import _darken, _lighten, _tile_hash

# Direction d (0=E, 1=NE, 2=NW, 3=W, 4=SW, 5=SE) maps to the shared
# hex edge between adjacent corners in the order produced by hex_corners().
# hex_corners() places corner i at angle (60*i + 30)°, so in screen coords
# (y-down): 0=right-bottom, 1=bottom, 2=left-bottom, 3=left-top, 4=top,
# 5=right-top.  Direction d's shared edge uses corners (6-d)%6 and (5-d)%6.
DIR_EDGE = [(5, 0), (4, 5), (3, 4), (2, 3), (1, 2), (0, 1)]


@lru_cache(maxsize=512)
def mountain_tile_color(depth: int, max_depth: int) -> tuple[int, int, int]:
    """Depth-based mountain colour: brown foothills → grey rock → white snow."""
    if max_depth <= 0:
        return (105, 95, 82)
    t = min(1.0, depth / max(1, max_depth))
    # Three-band: 0–0.35 brown rock, 0.35–0.7 grey rock, 0.7–1.0 snow
    if t < 0.35:
        s = t / 0.35
        return (
            int(95 + 25 * s),
            int(85 + 25 * s),
            int(72 + 28 * s),
        )
    elif t < 0.7:
        s = (t - 0.35) / 0.35
        return (
            int(120 + 50 * s),
            int(110 + 55 * s),
            int(100 + 60 * s),
        )
    else:
        s = (t - 0.7) / 0.3
        s = s * s  # ease into snow
        return (
            min(255, int(170 + 70 * s)),
            min(255, int(165 + 75 * s)),
            min(255, int(160 + 80 * s)),
        )


def draw_contours(
    surface: pygame.Surface,
    coord: HexCoord,
    depth: int,
    corners_screen: list[tuple[float, float]],
    base: tuple[int, int, int],
    mountain_depths: dict[HexCoord, tuple[int, int]],
    zoom: float,
) -> None:
    """Draw mountain ridge spurs running downhill with lit/shadow relief."""
    th = _tile_hash(coord.q, coord.r)

    # ~25% of tiles get a ridge spur
    if (th & 0xFF) >= 64:
        return

    cx = sum(p[0] for p in corners_screen) / 6.0
    cy = sum(p[1] for p in corners_screen) / 6.0

    # Gradient vector (downhill direction)
    gx, gy = 0.0, 0.0
    for d, nb_coord in enumerate(coord.neighbors()):
        nb_info = mountain_depths.get(nb_coord)
        if nb_info is None:
            continue
        diff = depth - nb_info[0]
        if diff == 0:
            continue
        c1_idx, c2_idx = DIR_EDGE[d]
        mx = (corners_screen[c1_idx][0] + corners_screen[c2_idx][0]) * 0.5
        my = (corners_screen[c1_idx][1] + corners_screen[c2_idx][1]) * 0.5
        gx += (mx - cx) * diff
        gy += (my - cy) * diff

    glen = (gx * gx + gy * gy) ** 0.5
    if glen < 0.1:
        return

    dx, dy = gx / glen, gy / glen
    nx, ny = -dy, dx  # perpendicular

    hex_r = zoom * 14.0
    length = hex_r * (0.6 + ((th >> 8) & 0xF) / 15.0 * 0.5)
    start_back = hex_r * (0.1 + ((th >> 12) & 0x7) / 7.0 * 0.2)
    half_w = zoom * (1.2 + ((th >> 16) & 0x7) / 7.0 * 1.4)
    tip_w = zoom * 0.3

    lat_off = ((th >> 24) & 0xFF) / 255.0 * 2.0 - 1.0
    lat_shift = lat_off * zoom * 2.5

    rx = cx - dx * start_back + nx * lat_shift
    ry = cy - dy * start_back + ny * lat_shift

    bend = ((th >> 15) & 0xFF) / 255.0 * 2.0 - 1.0
    bend_mag = zoom * 2.0 * bend
    mx = rx + dx * length * 0.5 + nx * bend_mag
    my = ry + dy * length * 0.5 + ny * bend_mag
    tx = rx + dx * length
    ty = ry + dy * length

    mw = (half_w + tip_w) * 0.5

    # Lit half (upper-left when looking downhill)
    lit = [
        (int(rx), int(ry)),
        (int(rx + nx * half_w), int(ry + ny * half_w)),
        (int(mx + nx * mw), int(my + ny * mw)),
        (int(tx + nx * tip_w), int(ty + ny * tip_w)),
        (int(tx), int(ty)),
        (int(mx), int(my)),
    ]
    pygame.draw.polygon(surface, _lighten(base, 1.12), lit)

    # Shadow half
    shd = [
        (int(rx), int(ry)),
        (int(rx - nx * half_w), int(ry - ny * half_w)),
        (int(mx - nx * mw), int(my - ny * mw)),
        (int(tx - nx * tip_w), int(ty - ny * tip_w)),
        (int(tx), int(ty)),
        (int(mx), int(my)),
    ]
    pygame.draw.polygon(surface, _darken(base, 0.72), shd)

    # Spine highlight
    lw = max(1, int(zoom * 0.7))
    pygame.draw.line(surface, _lighten(base, 1.22),
                     (int(rx), int(ry)), (int(mx), int(my)), lw)
    pygame.draw.line(surface, _lighten(base, 1.18),
                     (int(mx), int(my)), (int(tx), int(ty)), lw)
