"""Building drawing functions — camp, house, woodcutter, quarry, gatherer, storage, path, overcrowded.

Each function first checks for a matching sprite in the sprite manager.
If a sprite PNG is available it is drawn scaled to the current zoom;
otherwise the original procedural drawing code is used as a fallback.
"""

from __future__ import annotations

import math

import pygame

from compprog_pygame.games.hex_colony.render_utils import (
    _PATH_BASE,
    _PATH_DARK,
    _PATH_LIGHT,
    _darken,
    _lighten,
    _tile_hash,
)
from compprog_pygame.games.hex_colony.sprites import sprites


def _try_sprite(
    surface: pygame.Surface, key: str,
    sx: float, sy: float, r: int, z: float,
) -> bool:
    """Attempt to blit a sprite.  Returns True if successful."""
    sheet = sprites.get(key)
    if sheet is None:
        return False
    # Scale sprite so its width ≈ 2.2 * r (covers the hex footprint)
    target_w = max(4, int(r * 2.8))
    bw, bh = sheet.base_size
    aspect = bh / bw if bw else 1.0
    target_h = max(4, int(target_w * aspect))
    img = sheet.get(target_w, target_h)
    surface.blit(img, (int(sx) - target_w // 2, int(sy) - target_h // 2))
    return True


def draw_overcrowded(surface: pygame.Surface, sx: float, sy: float, r: int, z: float) -> None:
    """Red pulsing exclamation mark above a building to show overcrowding."""
    if _try_sprite(surface, "buildings/overcrowded", sx, sy - r * 0.8, r, z):
        return
    iz = max(1, int(z))
    # Position above the building
    ex = int(sx)
    ey = int(sy - r * 1.3)
    # Red circle background
    bg_r = max(4, int(r * 0.3))
    pygame.draw.circle(surface, (200, 40, 40), (ex, ey), bg_r)
    pygame.draw.circle(surface, (255, 80, 80), (ex, ey), bg_r, iz)
    # White ! inside
    bar_h = max(2, int(bg_r * 0.8))
    bar_w = max(1, iz)
    pygame.draw.line(surface, (255, 255, 255),
                     (ex, ey - bar_h), (ex, ey), bar_w)
    pygame.draw.circle(surface, (255, 255, 255), (ex, ey + max(1, int(bar_h * 0.4))), iz)


def draw_camp(surface: pygame.Surface, sx: float, sy: float, r: int, z: float) -> None:
    """Crashed spaceship — tilted fuselage with broken wing and sparking engine."""
    if _try_sprite(surface, "buildings/camp", sx, sy, r, z):
        return
    iz = max(1, int(z))
    hull_col = (120, 140, 170)
    hull_dark = _darken(hull_col, 0.7)
    hull_light = _lighten(hull_col, 1.2)

    # Fuselage — elongated ellipse tilted slightly
    body_w = max(4, int(r * 1.1))
    body_h = max(3, int(r * 0.55))
    # Draw tilted fuselage as a polygon (wider left=nose, narrower right=tail)
    nose_x = int(sx - r * 0.85)
    nose_y = int(sy + r * 0.1)
    tail_x = int(sx + r * 0.75)
    tail_y = int(sy - r * 0.15)
    top_mid = int(sy - body_h * 0.7)
    bot_mid = int(sy + body_h * 0.5)

    # Main hull shape
    hull_pts = [
        (nose_x, nose_y),
        (int(sx - r * 0.3), top_mid),
        (int(sx + r * 0.2), int(top_mid - r * 0.1)),
        (tail_x, tail_y),
        (int(sx + r * 0.3), bot_mid),
        (int(sx - r * 0.2), int(bot_mid + r * 0.05)),
    ]
    pygame.draw.polygon(surface, hull_col, hull_pts)
    # Upper highlight
    hl_pts = [hull_pts[0], hull_pts[1], hull_pts[2], hull_pts[3]]
    pygame.draw.polygon(surface, hull_light, hl_pts)
    # Outline
    pygame.draw.polygon(surface, hull_dark, hull_pts, iz)

    # Cockpit window — small blue-tinted dome near nose
    cockpit_x = int(sx - r * 0.55)
    cockpit_y = int(sy - r * 0.05)
    cockpit_r = max(2, int(r * 0.18))
    pygame.draw.circle(surface, (80, 140, 200), (cockpit_x, cockpit_y), cockpit_r)
    pygame.draw.circle(surface, (120, 180, 230), (cockpit_x - iz, cockpit_y - iz),
                       max(1, cockpit_r // 2))
    pygame.draw.circle(surface, hull_dark, (cockpit_x, cockpit_y), cockpit_r, iz)

    # Broken wing stub — jagged triangle on upper right
    wing_pts = [
        (int(sx + r * 0.1), int(sy - body_h * 0.6)),
        (int(sx + r * 0.6), int(sy - r * 0.9)),
        (int(sx + r * 0.35), int(sy - r * 0.5)),
        (int(sx + r * 0.55), int(sy - r * 0.65)),
        (int(sx + r * 0.3), int(sy - body_h * 0.4)),
    ]
    pygame.draw.polygon(surface, _darken(hull_col, 0.85), wing_pts)
    pygame.draw.polygon(surface, hull_dark, wing_pts, iz)

    # Engine glow / spark at tail
    spark_x = int(tail_x + r * 0.05)
    spark_y = int(tail_y + r * 0.05)
    spark_r = max(1, int(r * 0.12))
    pygame.draw.circle(surface, (255, 160, 40), (spark_x, spark_y), spark_r + iz)
    pygame.draw.circle(surface, (255, 220, 100), (spark_x, spark_y), spark_r)


def draw_habitat(surface: pygame.Surface, sx: float, sy: float, r: int, z: float) -> None:
    """Futuristic modular habitat pod — cubical with metal panels and glowing window."""
    if _try_sprite(surface, "buildings/habitat", sx, sy, r, z):
        return
    iz = max(1, int(z))

    # --- Main body: boxy pod ---
    body_w = int(r * 1.1)
    body_h = int(r * 0.8)

    hull_col = (140, 155, 175)   # blue-grey metal
    hull_dark = _darken(hull_col, 0.7)
    hull_light = _lighten(hull_col, 1.15)

    # Right face (darker — isometric shading)
    right_pts = [
        (int(sx), int(sy - body_h * 0.55)),
        (int(sx + body_w * 0.5), int(sy - body_h * 0.4)),
        (int(sx + body_w * 0.5), int(sy + body_h * 0.45)),
        (int(sx), int(sy + body_h * 0.3)),
    ]
    pygame.draw.polygon(surface, hull_dark, right_pts)

    # Left face (lighter)
    left_pts = [
        (int(sx), int(sy - body_h * 0.55)),
        (int(sx - body_w * 0.5), int(sy - body_h * 0.4)),
        (int(sx - body_w * 0.5), int(sy + body_h * 0.45)),
        (int(sx), int(sy + body_h * 0.3)),
    ]
    pygame.draw.polygon(surface, hull_col, left_pts)

    # Top face
    top_pts = [
        (int(sx), int(sy - body_h * 0.85)),
        (int(sx + body_w * 0.5), int(sy - body_h * 0.55)),
        (int(sx), int(sy - body_h * 0.4)),
        (int(sx - body_w * 0.5), int(sy - body_h * 0.55)),
    ]
    pygame.draw.polygon(surface, hull_light, top_pts)

    # Outline
    for pts in (right_pts, left_pts, top_pts):
        pygame.draw.polygon(surface, _darken(hull_col, 0.45), pts, iz)

    # Panel seam on left face
    seam_col = _darken(hull_col, 0.55)
    seam_y = int(sy)
    pygame.draw.line(surface, seam_col,
                     (int(sx - body_w * 0.45), seam_y), (int(sx - iz), int(seam_y - body_h * 0.07)), iz)

    # --- Glowing window on right face ---
    win_w = max(2, int(body_w * 0.22))
    win_h = max(2, int(body_h * 0.3))
    win_x = int(sx + body_w * 0.1)
    win_y = int(sy - body_h * 0.15)
    glow = (100, 200, 255)
    glow_dim = (60, 140, 200)
    pygame.draw.rect(surface, glow_dim, (win_x, win_y, win_w, win_h))
    pygame.draw.rect(surface, glow, (win_x + iz, win_y + iz, max(1, win_w - iz * 2), max(1, win_h - iz * 2)))
    pygame.draw.rect(surface, _darken(hull_col, 0.45), (win_x, win_y, win_w, win_h), iz)

    # --- Small antenna on top ---
    ant_x = int(sx + body_w * 0.15)
    ant_base_y = int(sy - body_h * 0.7)
    ant_top_y = ant_base_y - max(2, int(r * 0.3))
    pygame.draw.line(surface, (100, 110, 120), (ant_x, ant_base_y), (ant_x, ant_top_y), iz)
    pygame.draw.circle(surface, (80, 200, 240), (ant_x, ant_top_y), max(1, iz))


def draw_house(surface: pygame.Surface, sx: float, sy: float, r: int, z: float) -> None:
    """Teepee / hut — conical tent with hide covering and smoke hole."""
    if _try_sprite(surface, "buildings/house", sx, sy, r, z):
        return
    iz = max(1, int(z))
    hide_col = (155, 130, 85)
    hide_dark = _darken(hide_col, 0.75)

    # Main cone (wider than camp tent)
    apex_y = sy - r * 0.95
    base_y = sy + r * 0.55
    lx = sx - r * 0.7
    rx = sx + r * 0.7

    # Right half (shaded)
    right_pts = [(sx, apex_y), (sx, base_y), (rx, base_y)]
    pygame.draw.polygon(surface, hide_dark, right_pts)
    # Left half (lit)
    left_pts = [(sx, apex_y), (lx, base_y), (sx, base_y)]
    pygame.draw.polygon(surface, hide_col, left_pts)
    # Outline
    full_pts = [(sx, apex_y), (lx, base_y), (rx, base_y)]
    pygame.draw.polygon(surface, _darken(hide_col, 0.5), full_pts, iz)

    # Support poles poking above
    pole_col = (110, 80, 45)
    for dx in (-0.12, 0.0, 0.12):
        px = int(sx + r * dx)
        pygame.draw.line(surface, pole_col,
                         (px, int(apex_y)), (px, int(apex_y - r * 0.2)), iz)

    # Decorative band around middle
    band_y = int(sy - r * 0.2)
    pygame.draw.line(surface, (180, 80, 50),
                     (int(lx + r * 0.15), band_y), (int(rx - r * 0.15), band_y), max(1, iz))

    # Door opening
    door_w = max(2, int(r * 0.25))
    door_h = max(3, int(r * 0.35))
    door_pts = [
        (sx, base_y - door_h),
        (sx - door_w, base_y),
        (sx + door_w, base_y),
    ]
    pygame.draw.polygon(surface, (50, 35, 18), door_pts)


def draw_woodcutter(surface: pygame.Surface, sx: float, sy: float, r: int, z: float) -> None:
    if _try_sprite(surface, "buildings/woodcutter", sx, sy, r, z):
        return
    iz = max(1, int(z))
    cabin = (140, 90, 45)
    rect = pygame.Rect(int(sx - r * 0.55), int(sy - r * 0.3), int(r * 1.1), int(r * 0.7))
    pygame.draw.rect(surface, cabin, rect)
    pygame.draw.rect(surface, _lighten(cabin, 1.2), pygame.Rect(rect.x, rect.y, rect.w, max(1, int(2 * z))))
    pygame.draw.rect(surface, _darken(cabin, 0.6), rect, iz)
    for i in range(1, 4):
        ly = rect.y + i * rect.h // 4
        pygame.draw.line(surface, _darken(cabin, 0.7), (rect.x, ly), (rect.right, ly), iz)
    roof_col = (100, 60, 30)
    roof_pts = [(sx - r * 0.65, sy - r * 0.3), (sx, sy - r * 0.75), (sx + r * 0.65, sy - r * 0.3)]
    pygame.draw.polygon(surface, roof_col, roof_pts)
    pygame.draw.polygon(surface, _darken(roof_col, 0.7), roof_pts, iz)
    ax, ay = int(sx + r * 0.65), int(sy)
    axe_h = max(2, int(4 * z))
    pygame.draw.line(surface, (120, 90, 50), (ax, ay - axe_h), (ax, ay + max(1, int(3 * z))), iz)
    pygame.draw.polygon(surface, (160, 160, 170),
                        [(ax, ay - axe_h), (ax + max(2, int(3 * z)), ay - max(1, int(2 * z))), (ax, ay - iz)])


def draw_quarry(surface: pygame.Surface, sx: float, sy: float, r: int, z: float) -> None:
    if _try_sprite(surface, "buildings/quarry", sx, sy, r, z):
        return
    iz = max(1, int(z))
    arch_col = (150, 145, 135)
    pw = max(2, int(r * 0.2))
    ph = max(4, int(r * 0.7))
    pygame.draw.rect(surface, arch_col, (int(sx - r * 0.45), int(sy + r * 0.3 - ph), pw, ph))
    pygame.draw.rect(surface, arch_col, (int(sx + r * 0.45 - pw), int(sy + r * 0.3 - ph), pw, ph))
    arch_rect = pygame.Rect(int(sx - r * 0.45), int(sy - r * 0.55), int(r * 0.9), int(r * 0.3))
    pygame.draw.rect(surface, arch_col, arch_rect)
    pygame.draw.rect(surface, _lighten(arch_col, 1.2),
                     pygame.Rect(arch_rect.x, arch_rect.y, arch_rect.w, max(1, int(2 * z))))
    pygame.draw.rect(surface, (30, 25, 20),
                     (int(sx - r * 0.25), int(sy - r * 0.25), int(r * 0.5), int(r * 0.55)))
    px, py = int(sx + r * 0.55), int(sy - r * 0.2)
    pick_h = max(2, int(3 * z))
    pygame.draw.line(surface, (120, 90, 50), (px, py - pick_h), (px, py + pick_h), iz)
    pygame.draw.line(surface, (160, 160, 170),
                     (px - max(1, int(2 * z)), py - pick_h),
                     (px + max(1, int(2 * z)), py - pick_h), max(1, int(z * 1.5)))


def draw_gatherer(surface: pygame.Surface, sx: float, sy: float, r: int, z: float) -> None:
    if _try_sprite(surface, "buildings/gatherer", sx, sy, r, z):
        return
    iz = max(1, int(z))
    hut_col = (85, 150, 65)
    rect = pygame.Rect(int(sx - r * 0.4), int(sy - r * 0.15), int(r * 0.8), int(r * 0.55))
    pygame.draw.rect(surface, hut_col, rect)
    pygame.draw.rect(surface, _lighten(hut_col, 1.2),
                     pygame.Rect(rect.x, rect.y, rect.w, max(1, int(2 * z))))
    pygame.draw.rect(surface, _darken(hut_col, 0.6), rect, iz)
    roof_col = (160, 140, 60)
    roof_pts = [(sx - r * 0.5, sy - r * 0.15), (sx, sy - r * 0.6), (sx + r * 0.5, sy - r * 0.15)]
    pygame.draw.polygon(surface, roof_col, roof_pts)
    pygame.draw.polygon(surface, _darken(roof_col, 0.7), roof_pts, iz)
    bx, by = int(sx + r * 0.5), int(sy + r * 0.15)
    br = max(2, int(3 * z))
    pygame.draw.arc(surface, (140, 110, 60), (bx - br, by - br, br * 2, br * 2), 0, math.pi, iz)
    pygame.draw.circle(surface, (200, 60, 60), (bx, by - iz), iz)


def draw_storage(surface: pygame.Surface, sx: float, sy: float, r: int, z: float) -> None:
    if _try_sprite(surface, "buildings/storage", sx, sy, r, z):
        return
    iz = max(1, int(z))
    ware_col = (130, 110, 85)
    rect = pygame.Rect(int(sx - r * 0.6), int(sy - r * 0.25), int(r * 1.2), int(r * 0.65))
    pygame.draw.rect(surface, ware_col, rect)
    pygame.draw.rect(surface, _lighten(ware_col, 1.2),
                     pygame.Rect(rect.x, rect.y, rect.w, max(1, int(2 * z))))
    pygame.draw.rect(surface, _darken(ware_col, 0.6), rect, iz)
    c2 = max(1, int(2 * z))
    pygame.draw.rect(surface, _darken(ware_col, 0.75),
                     (rect.x - c2, rect.y - c2, rect.w + c2 * 2, max(2, int(4 * z))))
    pygame.draw.line(surface, _darken(ware_col, 0.65), (rect.x, rect.y), (rect.right, rect.bottom), iz)
    pygame.draw.line(surface, _darken(ware_col, 0.65), (rect.right, rect.y), (rect.x, rect.bottom), iz)
    dw = max(2, int(r * 0.3))
    dh = max(3, int(r * 0.35))
    pygame.draw.rect(surface, _darken(ware_col, 0.4),
                     (int(sx - dw // 2), int(sy + r * 0.4 - dh), dw, dh))


def draw_path(
    surface: pygame.Surface,
    sx: float, sy: float,
    r: int, z: float,
    nb_positions: list[tuple[float, float]],
    q: int, rr: int,
) -> None:
    """Draw a dirt path tile.  Isolated → textured circle.  Adjacent paths →
    thick connecting bands that naturally merge into filled areas."""
    isx, isy = int(sx), int(sy)
    iz = max(1, int(z))
    h = _tile_hash(q, rr)

    # Band half-width: roughly 40 % of hex radius so adjacent bands overlap
    band_hw = max(2, int(r * 0.40))

    # Draw connecting bands to each neighbour first (underneath the center disc)
    for nsx, nsy in nb_positions:
        # Direction vector from center to neighbour
        dx = nsx - sx
        dy = nsy - sy
        length = math.hypot(dx, dy)
        if length < 1:
            continue
        # Unit perpendicular (rotated 90°)
        px = -dy / length * band_hw
        py = dx / length * band_hw
        # Quad from center to midpoint between the two hexes
        mx = sx + dx * 0.5
        my = sy + dy * 0.5
        pts = [
            (sx + px, sy + py),
            (sx - px, sy - py),
            (mx - px, my - py),
            (mx + px, my + py),
        ]
        pygame.draw.polygon(surface, _PATH_BASE, pts)
        # Subtle edge darkening
        pygame.draw.line(surface, _PATH_DARK,
                         (int(pts[0][0]), int(pts[0][1])),
                         (int(pts[3][0]), int(pts[3][1])), iz)
        pygame.draw.line(surface, _PATH_DARK,
                         (int(pts[1][0]), int(pts[1][1])),
                         (int(pts[2][0]), int(pts[2][1])), iz)

    # Center disc
    pygame.draw.circle(surface, _PATH_BASE, (isx, isy), band_hw + max(1, int(r * 0.10)))

    # Dirt texture: deterministic speckles
    speck_count = max(3, int(r * 0.6))
    for i in range(speck_count):
        sh2 = _tile_hash(q + i * 7, rr + i * 13)
        ox = ((sh2 & 0xFF) - 128) * band_hw // 160
        oy = (((sh2 >> 8) & 0xFF) - 128) * band_hw // 160
        col = _PATH_DARK if (sh2 >> 16) & 1 else _PATH_LIGHT
        pygame.draw.circle(surface, col, (isx + ox, isy + oy), iz)

    # Edge ring for definition when isolated
    if not nb_positions:
        pygame.draw.circle(surface, _PATH_DARK, (isx, isy),
                           band_hw + max(1, int(r * 0.10)), iz)
