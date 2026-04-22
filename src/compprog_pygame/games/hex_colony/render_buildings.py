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


def draw_tribal_camp(surface: pygame.Surface, sx: float, sy: float, r: int, z: float) -> None:
    """Primitive tribal camp — central fire pit ringed by three small hide tents."""
    if _try_sprite(surface, "buildings/tribal_camp", sx, sy, r, z):
        return
    iz = max(1, int(z))
    hide_col = (140, 100, 60)
    hide_dark = _darken(hide_col, 0.7)
    hide_light = _lighten(hide_col, 1.15)
    earth_col = (95, 70, 45)

    # Earth ring around the camp (a flat trodden-ground disc)
    ring_r = max(3, int(r * 0.95))
    pygame.draw.circle(surface, earth_col, (int(sx), int(sy)), ring_r)
    pygame.draw.circle(surface, _darken(earth_col, 0.7),
                       (int(sx), int(sy)), ring_r, iz)

    # Three small hide tents around the centre (triangle layout)
    tent_r = max(2, int(r * 0.32))
    for i in range(3):
        angle = math.radians(-90 + i * 120)
        tx = sx + math.cos(angle) * r * 0.55
        ty = sy + math.sin(angle) * r * 0.55
        apex_y = ty - tent_r * 1.1
        base_y = ty + tent_r * 0.55
        lx = tx - tent_r * 0.85
        rx = tx + tent_r * 0.85
        # shaded right half
        pygame.draw.polygon(surface, hide_dark,
                            [(tx, apex_y), (tx, base_y), (rx, base_y)])
        # lit left half
        pygame.draw.polygon(surface, hide_light,
                            [(tx, apex_y), (lx, base_y), (tx, base_y)])
        # outline
        pygame.draw.polygon(surface, _darken(hide_col, 0.5),
                            [(tx, apex_y), (lx, base_y), (rx, base_y)], iz)

    # Central fire pit: stone ring with glowing embers
    pit_r = max(2, int(r * 0.22))
    pygame.draw.circle(surface, (90, 85, 80), (int(sx), int(sy)), pit_r)
    pygame.draw.circle(surface, (60, 55, 50), (int(sx), int(sy)), pit_r, iz)
    # Ember glow
    ember_r = max(1, int(pit_r * 0.55))
    pygame.draw.circle(surface, (255, 140, 40), (int(sx), int(sy)), ember_r)
    pygame.draw.circle(surface, (255, 220, 120),
                       (int(sx - iz * 0.5), int(sy - iz * 0.5)),
                       max(1, ember_r - iz))

    # Smoke wisp above fire
    smoke_x = int(sx + iz)
    smoke_top = int(sy - r * 0.85)
    pygame.draw.line(surface, (180, 175, 170),
                     (int(sx), int(sy - pit_r)), (smoke_x, smoke_top), iz)


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


def draw_bridge(
    surface: pygame.Surface,
    sx: float, sy: float,
    r: int, z: float,
    nb_positions: list[tuple[float, float]],
    q: int, rr: int,
) -> None:
    """Wooden bridge — planks over water."""
    isx, isy = int(sx), int(sy)
    iz = max(1, int(z))
    plank_col = (140, 100, 55)
    rail_col = (100, 70, 40)
    band_hw = max(2, int(r * 0.38))

    # Connecting bands to neighbours (same logic as path)
    for nsx, nsy in nb_positions:
        dx = nsx - sx
        dy = nsy - sy
        length = math.hypot(dx, dy)
        if length < 1:
            continue
        px = -dy / length * band_hw
        py = dx / length * band_hw
        mx = sx + dx * 0.5
        my = sy + dy * 0.5
        pts = [
            (sx + px, sy + py), (sx - px, sy - py),
            (mx - px, my - py), (mx + px, my + py),
        ]
        pygame.draw.polygon(surface, plank_col, pts)
        pygame.draw.line(surface, _darken(plank_col, 0.6),
                         (int(pts[0][0]), int(pts[0][1])),
                         (int(pts[3][0]), int(pts[3][1])), iz)
        pygame.draw.line(surface, _darken(plank_col, 0.6),
                         (int(pts[1][0]), int(pts[1][1])),
                         (int(pts[2][0]), int(pts[2][1])), iz)

    # Center platform
    pygame.draw.circle(surface, plank_col, (isx, isy), band_hw + max(1, int(r * 0.08)))

    # Plank lines across
    plank_count = max(2, int(r * 0.3))
    for i in range(plank_count):
        oy = int(-band_hw + i * (2 * band_hw) / max(1, plank_count - 1))
        pygame.draw.line(surface, _darken(plank_col, 0.7),
                         (isx - band_hw, isy + oy), (isx + band_hw, isy + oy), iz)

    # Railing posts
    for sign in (-1, 1):
        px = isx + sign * band_hw
        pygame.draw.line(surface, rail_col, (px, isy - max(2, int(r * 0.2))),
                         (px, isy + max(2, int(r * 0.2))), max(1, int(z * 1.5)))


def draw_pipe(
    surface: pygame.Surface,
    sx: float, sy: float,
    r: int, z: float,
    nb_positions: list[tuple[float, float]],
    q: int, rr: int,
) -> None:
    """Steel pipe segment.  Renders as a metallic band that joins to
    every adjacent pipe / fluid building given in ``nb_positions``,
    matching the visual idiom of :func:`draw_path`."""
    if _try_sprite(surface, "buildings/pipe", sx, sy, r, z):
        return
    isx, isy = int(sx), int(sy)
    iz = max(1, int(z))
    pipe_col = (155, 150, 145)
    pipe_dark = _darken(pipe_col, 0.55)
    pipe_light = _lighten(pipe_col, 1.15)
    band_hw = max(2, int(r * 0.32))

    for nsx, nsy in nb_positions:
        dx = nsx - sx
        dy = nsy - sy
        length = math.hypot(dx, dy)
        if length < 1:
            continue
        px = -dy / length * band_hw
        py = dx / length * band_hw
        mx = sx + dx * 0.5
        my = sy + dy * 0.5
        pts = [
            (sx + px, sy + py), (sx - px, sy - py),
            (mx - px, my - py), (mx + px, my + py),
        ]
        pygame.draw.polygon(surface, pipe_col, pts)
        # Highlight strip down the centre of the pipe.
        pygame.draw.line(
            surface, pipe_light,
            (int(sx), int(sy)), (int(mx), int(my)),
            max(1, int(z)),
        )
        pygame.draw.line(
            surface, pipe_dark,
            (int(pts[0][0]), int(pts[0][1])),
            (int(pts[3][0]), int(pts[3][1])), iz,
        )
        pygame.draw.line(
            surface, pipe_dark,
            (int(pts[1][0]), int(pts[1][1])),
            (int(pts[2][0]), int(pts[2][1])), iz,
        )

    # Centre flange / hub.
    hub_r = band_hw + max(1, int(r * 0.10))
    pygame.draw.circle(surface, pipe_col, (isx, isy), hub_r)
    pygame.draw.circle(surface, pipe_dark, (isx, isy), hub_r, iz)
    pygame.draw.circle(
        surface, pipe_light, (isx, isy),
        max(1, hub_r // 2),
    )


def draw_fluid_tank(
    surface: pygame.Surface, sx: float, sy: float, r: int, z: float,
) -> None:
    """Cylindrical fluid tank with riveted bands."""
    if _try_sprite(surface, "buildings/fluid_tank", sx, sy, r, z):
        return
    iz = max(1, int(z))
    tank_col = (110, 130, 150)
    tank_light = _lighten(tank_col, 1.25)
    tank_dark = _darken(tank_col, 0.55)
    rim_col = (175, 180, 190)

    rect = pygame.Rect(
        int(sx - r * 0.55), int(sy - r * 0.55),
        int(r * 1.10), int(r * 1.10),
    )
    pygame.draw.ellipse(surface, tank_col, rect)
    hl = pygame.Rect(
        rect.x + int(rect.w * 0.1), rect.y + int(rect.h * 0.1),
        max(2, int(rect.w * 0.25)), int(rect.h * 0.8),
    )
    pygame.draw.ellipse(surface, tank_light, hl)
    for frac in (0.30, 0.55, 0.80):
        ly = rect.y + int(rect.h * frac)
        pygame.draw.line(
            surface, tank_dark,
            (rect.x + iz, ly), (rect.right - iz, ly), iz,
        )
    cap = pygame.Rect(
        rect.x + int(rect.w * 0.25), rect.y - max(1, int(z)),
        int(rect.w * 0.5), max(2, int(z * 2)),
    )
    pygame.draw.rect(surface, rim_col, cap, border_radius=2)
    pygame.draw.ellipse(surface, tank_dark, rect, iz)


def draw_refinery(surface: pygame.Surface, sx: float, sy: float, r: int, z: float) -> None:
    if _try_sprite(surface, "buildings/refinery", sx, sy, r, z):
        return
    iz = max(1, int(z))
    base_col = (90, 80, 100)
    # Main structure
    rect = pygame.Rect(int(sx - r * 0.5), int(sy - r * 0.2), int(r * 1.0), int(r * 0.6))
    pygame.draw.rect(surface, base_col, rect)
    pygame.draw.rect(surface, _lighten(base_col, 1.2),
                     pygame.Rect(rect.x, rect.y, rect.w, max(1, int(2 * z))))
    pygame.draw.rect(surface, _darken(base_col, 0.6), rect, iz)
    # Chimney/smokestack
    ch_w = max(2, int(r * 0.15))
    ch_h = max(4, int(r * 0.5))
    ch_x = int(sx + r * 0.2)
    ch_y = int(sy - r * 0.2 - ch_h)
    pygame.draw.rect(surface, (70, 65, 80), (ch_x, ch_y, ch_w, ch_h))
    pygame.draw.rect(surface, (50, 45, 60), (ch_x, ch_y, ch_w, ch_h), iz)
    # Smoke puffs
    for i in range(3):
        smoke_y = ch_y - max(2, int(r * 0.1)) * (i + 1)
        smoke_r = max(1, int(r * 0.08 * (i + 1)))
        pygame.draw.circle(surface, (140, 140, 150, 120), (ch_x + ch_w // 2, smoke_y), smoke_r)
    # Furnace glow
    glow_r = max(2, int(r * 0.12))
    pygame.draw.circle(surface, (220, 120, 40), (int(sx - r * 0.15), int(sy + r * 0.1)), glow_r)


def draw_mining_machine(surface: pygame.Surface, sx: float, sy: float, r: int, z: float) -> None:
    """Mining machine — heavy fuel-powered drilling rig with rotating gear."""
    if _try_sprite(surface, "buildings/mining_machine", sx, sy, r, z):
        return
    isx, isy = int(sx), int(sy)
    iz = max(1, int(z))
    hull_col = (95, 95, 110)
    hull_dark = _darken(hull_col, 0.55)
    hull_light = _lighten(hull_col, 1.2)
    metal_accent = (180, 140, 60)

    # Caterpillar-style base — long low treads across the tile
    tread_w = max(4, int(r * 1.1))
    tread_h = max(2, int(r * 0.22))
    tread_rect = pygame.Rect(
        isx - tread_w // 2, isy + int(r * 0.15), tread_w, tread_h,
    )
    pygame.draw.rect(surface, (40, 40, 48), tread_rect, border_radius=2)
    pygame.draw.rect(surface, hull_dark, tread_rect, iz, border_radius=2)
    # Tread lugs (little tick marks)
    lug_count = max(4, tread_w // max(2, iz * 2))
    for i in range(lug_count):
        lx = tread_rect.x + (i * tread_rect.w) // lug_count + iz
        pygame.draw.line(
            surface, (25, 25, 30),
            (lx, tread_rect.y + 1),
            (lx, tread_rect.bottom - 1), max(1, iz),
        )

    # Main chassis — rectangular hull above the treads
    body_w = max(4, int(r * 0.95))
    body_h = max(3, int(r * 0.55))
    body = pygame.Rect(
        isx - body_w // 2, tread_rect.y - body_h, body_w, body_h,
    )
    pygame.draw.rect(surface, hull_col, body, border_radius=2)
    pygame.draw.rect(surface, hull_light,
                     pygame.Rect(body.x, body.y, body.w, max(1, iz)),
                     border_radius=2)
    pygame.draw.rect(surface, hull_dark, body, iz, border_radius=2)

    # Yellow warning stripe along the lower chassis
    stripe_y = body.bottom - max(1, int(body.h * 0.25))
    pygame.draw.line(
        surface, metal_accent,
        (body.x + iz, stripe_y), (body.right - iz, stripe_y),
        max(1, iz),
    )

    # Angled drill arm — extends forward and down to the ground
    arm_root = (body.x + body.w // 4, body.y + body.h // 2)
    drill_tip = (isx + int(r * 0.55), tread_rect.y + tread_rect.h // 2)
    pygame.draw.line(
        surface, hull_dark, arm_root, drill_tip,
        max(2, int(r * 0.12)),
    )
    pygame.draw.line(
        surface, hull_light, arm_root, drill_tip, max(1, iz),
    )
    # Drill bit — triangular tip with dark shaft outline
    bit_r = max(2, int(r * 0.18))
    bit_pts = [
        (drill_tip[0] - bit_r, drill_tip[1] - bit_r // 2),
        (drill_tip[0] - bit_r, drill_tip[1] + bit_r // 2),
        (drill_tip[0] + bit_r, drill_tip[1]),
    ]
    pygame.draw.polygon(surface, (210, 210, 220), bit_pts)
    pygame.draw.polygon(surface, (30, 30, 35), bit_pts, iz)

    # Rotating cog on top of the chassis (purely cosmetic, static tooth
    # pattern).  Indicates mechanical operation.
    gear_cx = isx - int(body_w * 0.25)
    gear_cy = body.y - max(2, int(r * 0.05))
    gear_r = max(2, int(r * 0.2))
    pygame.draw.circle(surface, hull_dark, (gear_cx, gear_cy), gear_r)
    pygame.draw.circle(surface, metal_accent, (gear_cx, gear_cy), gear_r, iz)
    # Teeth
    import math as _math
    for k in range(6):
        ang = k * _math.pi / 3
        tx = int(gear_cx + _math.cos(ang) * gear_r * 1.3)
        ty = int(gear_cy + _math.sin(ang) * gear_r * 1.3)
        pygame.draw.circle(
            surface, metal_accent, (tx, ty), max(1, gear_r // 3),
        )
    pygame.draw.circle(
        surface, hull_light, (gear_cx, gear_cy), max(1, gear_r // 3),
    )

    # Short exhaust stack on the rear
    st_w = max(2, int(r * 0.12))
    st_h = max(3, int(r * 0.28))
    st_x = body.right - st_w - iz
    st_y = body.y - st_h
    pygame.draw.rect(surface, hull_dark, (st_x, st_y, st_w, st_h))
    pygame.draw.rect(surface, (25, 25, 30), (st_x, st_y, st_w, max(1, iz)))


def draw_farm(surface: pygame.Surface, sx: float, sy: float, r: int, z: float) -> None:
    if _try_sprite(surface, "buildings/farm", sx, sy, r, z):
        return
    iz = max(1, int(z))
    soil_col = (100, 70, 40)
    crop_col = (80, 160, 50)
    # Tilled field
    field_r = max(4, int(r * 0.6))
    pygame.draw.circle(surface, soil_col, (int(sx), int(sy)), field_r)
    pygame.draw.circle(surface, _darken(soil_col, 0.7), (int(sx), int(sy)), field_r, iz)
    # Crop rows
    row_count = max(2, int(r * 0.25))
    for i in range(row_count):
        ry = int(sy - field_r * 0.6 + i * (field_r * 1.2) / max(1, row_count - 1))
        row_w = max(2, int(field_r * 0.7))
        pygame.draw.line(surface, crop_col, (int(sx) - row_w, ry), (int(sx) + row_w, ry), max(1, int(z * 2)))
    # Small hut/barn
    barn_w = max(3, int(r * 0.3))
    barn_h = max(3, int(r * 0.25))
    bx = int(sx + r * 0.35)
    by = int(sy - r * 0.35)
    pygame.draw.rect(surface, (140, 100, 55), (bx, by, barn_w, barn_h))
    pygame.draw.rect(surface, _darken((140, 100, 55), 0.6), (bx, by, barn_w, barn_h), iz)
    # Barn roof
    pygame.draw.polygon(surface, (120, 80, 40),
                        [(bx - iz, by), (bx + barn_w // 2, by - max(2, int(r * 0.15))),
                         (bx + barn_w + iz, by)])


def draw_well(surface: pygame.Surface, sx: float, sy: float, r: int, z: float) -> None:
    if _try_sprite(surface, "buildings/well", sx, sy, r, z):
        return
    iz = max(1, int(z))
    stone_col = (140, 135, 125)
    water_col = (60, 100, 180)
    # Stone ring
    well_r = max(3, int(r * 0.35))
    pygame.draw.circle(surface, stone_col, (int(sx), int(sy)), well_r)
    pygame.draw.circle(surface, _darken(stone_col, 0.6), (int(sx), int(sy)), well_r, max(1, int(z * 1.5)))
    # Water inside
    inner_r = max(2, well_r - max(2, int(r * 0.1)))
    pygame.draw.circle(surface, water_col, (int(sx), int(sy)), inner_r)
    pygame.draw.circle(surface, _lighten(water_col, 1.3), (int(sx), int(sy)), inner_r, iz)
    # Roof support posts
    post_h = max(3, int(r * 0.4))
    for sign in (-1, 1):
        px = int(sx + sign * well_r * 0.8)
        pygame.draw.line(surface, (100, 70, 40), (px, int(sy) - post_h), (px, int(sy)), max(1, int(z * 1.5)))
    # Cross beam
    pygame.draw.line(surface, (100, 70, 40),
                     (int(sx - well_r * 0.8), int(sy) - post_h),
                     (int(sx + well_r * 0.8), int(sy) - post_h), max(1, int(z * 2)))
    # Bucket
    pygame.draw.circle(surface, (120, 90, 50), (int(sx), int(sy) - post_h + iz), max(1, int(r * 0.08)))


def draw_wall(
    surface: pygame.Surface,
    sx: float, sy: float,
    r: int, z: float,
    nb_positions: list[tuple[float, float]],
    q: int, rr: int,
) -> None:
    """Stone wall — connects to adjacent walls like paths."""
    isx, isy = int(sx), int(sy)
    iz = max(1, int(z))
    wall_col = (160, 155, 145)
    wall_dark = _darken(wall_col, 0.6)
    wall_light = _lighten(wall_col, 1.15)
    band_hw = max(2, int(r * 0.28))
    wall_h = max(2, int(r * 0.35))  # wall height (visual)

    # Connecting segments to neighbours
    for nsx, nsy in nb_positions:
        dx = nsx - sx
        dy = nsy - sy
        length = math.hypot(dx, dy)
        if length < 1:
            continue
        px = -dy / length * band_hw
        py = dx / length * band_hw
        mx = sx + dx * 0.5
        my = sy + dy * 0.5
        # Wall top face
        top_pts = [
            (sx + px, sy + py - wall_h),
            (sx - px, sy - py - wall_h),
            (mx - px, my - py - wall_h),
            (mx + px, my + py - wall_h),
        ]
        pygame.draw.polygon(surface, wall_light, top_pts)
        # Wall front face
        front_pts = [
            (sx + px, sy + py - wall_h),
            (mx + px, my + py - wall_h),
            (mx + px, my + py),
            (sx + px, sy + py),
        ]
        pygame.draw.polygon(surface, wall_col, front_pts)
        # Wall back face (darker)
        back_pts = [
            (sx - px, sy - py - wall_h),
            (mx - px, my - py - wall_h),
            (mx - px, my - py),
            (sx - px, sy - py),
        ]
        pygame.draw.polygon(surface, wall_dark, back_pts)
        # Edges
        for pts in (top_pts, front_pts, back_pts):
            pygame.draw.polygon(surface, _darken(wall_col, 0.4), pts, iz)

    # Center tower / post
    tower_r = band_hw + max(1, int(r * 0.08))
    # Tower base
    pygame.draw.circle(surface, wall_col, (isx, isy), tower_r)
    # Tower top (raised)
    pygame.draw.circle(surface, wall_light, (isx, isy - wall_h), tower_r)
    # Tower side (vertical pillars to show height)
    pygame.draw.line(surface, wall_dark, (isx - tower_r, isy),
                     (isx - tower_r, isy - wall_h), iz)
    pygame.draw.line(surface, wall_dark, (isx + tower_r, isy),
                     (isx + tower_r, isy - wall_h), iz)
    pygame.draw.circle(surface, _darken(wall_col, 0.4), (isx, isy - wall_h), tower_r, iz)

    # Battlement notches on top
    notch_count = max(2, int(r * 0.15))
    notch_w = max(1, int(tower_r * 2 / (notch_count * 2)))
    for i in range(notch_count):
        nx = isx - tower_r + i * (tower_r * 2) // notch_count + notch_w
        pygame.draw.rect(surface, _darken(wall_col, 0.5),
                         (nx, isy - wall_h - max(1, int(r * 0.08)),
                          notch_w, max(1, int(r * 0.08))))


def draw_workshop(surface: pygame.Surface, sx: float, sy: float, r: int, z: float) -> None:
    """Workshop — crafting building with anvil/workbench look."""
    if _try_sprite(surface, "buildings/workshop", sx, sy, r, z):
        return
    isx, isy = int(sx), int(sy)
    iz = max(1, int(z))
    base_col = (180, 140, 60)
    dark = _darken(base_col, 0.6)
    light = _lighten(base_col, 1.15)

    # Main building body (rectangle)
    bw = max(4, int(r * 0.9))
    bh = max(3, int(r * 0.6))
    body = pygame.Rect(isx - bw // 2, isy - bh, bw, bh)
    pygame.draw.rect(surface, base_col, body, border_radius=2)
    pygame.draw.rect(surface, dark, body, width=iz, border_radius=2)

    # Roof (triangle)
    roof_pts = [
        (isx - bw // 2 - max(1, int(r * 0.1)), isy - bh),
        (isx + bw // 2 + max(1, int(r * 0.1)), isy - bh),
        (isx, isy - bh - max(3, int(r * 0.5))),
    ]
    pygame.draw.polygon(surface, light, roof_pts)
    pygame.draw.polygon(surface, dark, roof_pts, iz)

    # Anvil symbol (gear/cog)
    gear_r = max(2, int(r * 0.18))
    gear_cx = isx
    gear_cy = isy - bh // 2
    pygame.draw.circle(surface, dark, (gear_cx, gear_cy), gear_r, iz)
    pygame.draw.circle(surface, light, (gear_cx, gear_cy), max(1, gear_r // 2))


def draw_forge(surface: pygame.Surface, sx: float, sy: float, r: int, z: float) -> None:
    """Forge — squat stone blacksmithing forge with a glowing furnace and chimney."""
    if _try_sprite(surface, "buildings/forge", sx, sy, r, z):
        return
    isx, isy = int(sx), int(sy)
    iz = max(1, int(z))
    stone_col = (110, 100, 92)
    stone_dark = _darken(stone_col, 0.65)
    stone_light = _lighten(stone_col, 1.18)
    mortar = _darken(stone_col, 0.45)

    # ── Stone base (wider at bottom, slightly trapezoidal) ──────
    base_w = max(4, int(r * 1.1))
    base_h = max(3, int(r * 0.58))
    top_w = max(4, int(base_w * 0.85))
    base_top = isy - base_h
    base_bottom = isy + max(1, int(r * 0.05))
    base_pts = [
        (isx - base_w // 2, base_bottom),
        (isx + base_w // 2, base_bottom),
        (isx + top_w // 2, base_top),
        (isx - top_w // 2, base_top),
    ]
    pygame.draw.polygon(surface, stone_col, base_pts)
    pygame.draw.polygon(surface, stone_dark, base_pts, iz)
    # Top highlight strip
    pygame.draw.line(
        surface, stone_light,
        (isx - top_w // 2 + iz, base_top),
        (isx + top_w // 2 - iz, base_top), iz,
    )

    # ── Stone block texture (mortar lines) ──────────────────────
    row_h = max(2, base_h // 3)
    for row in range(1, 3):
        y = base_top + row * row_h
        if y >= base_bottom:
            break
        # Interpolate width so the mortar lines follow the trapezoid.
        t = (y - base_top) / max(1, base_h)
        w = int(top_w + (base_w - top_w) * t)
        pygame.draw.line(
            surface, mortar,
            (isx - w // 2 + 1, y), (isx + w // 2 - 1, y), max(1, iz // 2),
        )
        # Staggered vertical joints
        stagger = (row % 2) * (w // 4)
        jx1 = isx - w // 2 + stagger + w // 4
        jx2 = isx + w // 2 - (w // 4 - stagger)
        pygame.draw.line(
            surface, mortar, (jx1, y), (jx1, min(y + row_h, base_bottom)),
            max(1, iz // 2),
        )
        if jx2 != jx1:
            pygame.draw.line(
                surface, mortar,
                (jx2, y), (jx2, min(y + row_h, base_bottom)),
                max(1, iz // 2),
            )

    # ── Furnace opening (glowing arch) ──────────────────────────
    mouth_w = max(3, int(base_w * 0.40))
    mouth_h = max(3, int(base_h * 0.55))
    mouth_rect = pygame.Rect(
        isx - mouth_w // 2, base_bottom - mouth_h - max(1, iz),
        mouth_w, mouth_h,
    )
    pygame.draw.rect(surface, (30, 15, 10), mouth_rect, border_radius=max(1, mouth_h // 3))
    # Inner glow
    glow = pygame.Rect(
        mouth_rect.x + max(1, iz), mouth_rect.y + max(1, iz),
        mouth_rect.w - max(2, iz * 2), mouth_rect.h - max(2, iz * 2),
    )
    if glow.w > 0 and glow.h > 0:
        pygame.draw.rect(surface, (210, 90, 30), glow,
                         border_radius=max(1, glow.h // 3))
        inner = pygame.Rect(
            glow.x + max(1, iz), glow.y + max(1, iz),
            glow.w - max(2, iz * 2), glow.h - max(2, iz * 2),
        )
        if inner.w > 0 and inner.h > 0:
            pygame.draw.rect(surface, (255, 180, 70), inner,
                             border_radius=max(1, inner.h // 3))

    # ── Anvil silhouette to one side ────────────────────────────
    anvil_x = isx + int(base_w * 0.35)
    anvil_y = base_top - max(2, int(r * 0.1))
    anvil_w = max(2, int(r * 0.22))
    anvil_h = max(1, int(r * 0.08))
    pygame.draw.rect(
        surface, (50, 48, 52),
        (anvil_x - anvil_w // 2, anvil_y - anvil_h, anvil_w, anvil_h),
    )
    pygame.draw.rect(
        surface, (35, 33, 38),
        (anvil_x - anvil_w // 4, anvil_y, anvil_w // 2, anvil_h),
    )

    # ── Chimney & smoke ─────────────────────────────────────────
    ch_w = max(2, int(r * 0.22))
    ch_h = max(3, int(r * 0.38))
    ch_x = isx - int(base_w * 0.28) - ch_w // 2
    ch_y = base_top - ch_h
    pygame.draw.rect(surface, stone_dark, (ch_x, ch_y, ch_w, ch_h))
    pygame.draw.rect(surface, stone_col, (ch_x, ch_y, ch_w, max(1, iz)))
    # Smoke puffs
    for i in range(3):
        puff_r = max(1, int(r * 0.09 * (i + 1)))
        py = ch_y - puff_r - max(1, int(r * 0.08)) * i
        pygame.draw.circle(
            surface, (170, 160, 150),
            (ch_x + ch_w // 2, py), puff_r,
        )
    # Ember sparks above chimney
    for dx, dy in ((-1, -2), (2, -3), (-2, -4)):
        spark_x = ch_x + ch_w // 2 + int(dx * max(1, iz))
        spark_y = ch_y + int(dy * max(1, iz))
        pygame.draw.circle(surface, (255, 180, 90), (spark_x, spark_y), max(1, iz))


def draw_assembler(surface: pygame.Surface, sx: float, sy: float, r: int, z: float) -> None:
    """Assembler — futuristic industrial machine with robotic arm and indicator lights."""
    if _try_sprite(surface, "buildings/assembler", sx, sy, r, z):
        return
    isx, isy = int(sx), int(sy)
    iz = max(1, int(z))
    body_col = (120, 140, 165)
    body_dark = _darken(body_col, 0.6)
    body_light = _lighten(body_col, 1.25)
    panel_col = (55, 68, 90)
    glow_col = (80, 200, 255)
    accent = (255, 180, 80)

    # ── Main body (metal box) ────────────────────────────────────
    body_w = max(4, int(r * 1.15))
    body_h = max(4, int(r * 0.70))
    body_top = isy - body_h
    body_bottom = isy + max(1, int(r * 0.05))
    body_rect = pygame.Rect(
        isx - body_w // 2, body_top, body_w, body_h,
    )
    pygame.draw.rect(surface, body_col, body_rect, border_radius=max(1, iz))
    pygame.draw.rect(surface, body_dark, body_rect, iz, border_radius=max(1, iz))
    # Top highlight strip
    pygame.draw.line(
        surface, body_light,
        (body_rect.x + iz + 1, body_top + 1),
        (body_rect.right - iz - 1, body_top + 1), iz,
    )

    # ── Control panel screen ─────────────────────────────────────
    screen_w = max(3, int(body_w * 0.45))
    screen_h = max(2, int(body_h * 0.32))
    screen_x = isx - screen_w // 2
    screen_y = body_top + max(2, int(body_h * 0.15))
    screen_rect = pygame.Rect(screen_x, screen_y, screen_w, screen_h)
    pygame.draw.rect(surface, panel_col, screen_rect, border_radius=max(1, iz // 2))
    pygame.draw.rect(surface, body_dark, screen_rect, max(1, iz // 2),
                     border_radius=max(1, iz // 2))
    # Scan-line glow
    for i in range(2):
        ly = screen_rect.y + max(1, iz) + i * max(2, screen_h // 3)
        if ly < screen_rect.bottom - 1:
            pygame.draw.line(
                surface, glow_col,
                (screen_rect.x + 2, ly),
                (screen_rect.right - 2, ly),
                max(1, iz // 2),
            )

    # ── Indicator LEDs (row of tiny lights) ─────────────────────
    led_y = body_bottom - max(2, int(body_h * 0.18))
    led_r = max(1, iz)
    led_colors = ((90, 240, 120), accent, (240, 90, 90))
    led_spacing = max(3, int(body_w * 0.12))
    led_start_x = isx - led_spacing
    for i, col in enumerate(led_colors):
        lx = led_start_x + i * led_spacing
        pygame.draw.circle(surface, body_dark, (lx, led_y), led_r + 1)
        pygame.draw.circle(surface, col, (lx, led_y), led_r)

    # ── Vent grill on the right side ────────────────────────────
    vent_x = body_rect.right - max(3, int(body_w * 0.16))
    vent_y = body_top + max(2, int(body_h * 0.15))
    vent_w = max(2, int(body_w * 0.10))
    vent_h = max(2, int(body_h * 0.55))
    vent_rect = pygame.Rect(vent_x, vent_y, vent_w, vent_h)
    pygame.draw.rect(surface, body_dark, vent_rect)
    for i in range(3):
        ly = vent_y + max(1, iz) + i * max(2, vent_h // 4)
        if ly < vent_y + vent_h - 1:
            pygame.draw.line(
                surface, panel_col,
                (vent_x + 1, ly), (vent_x + vent_w - 1, ly),
                max(1, iz // 2),
            )

    # ── Robotic arm on top ──────────────────────────────────────
    arm_base_x = isx + int(body_w * 0.18)
    arm_base_y = body_top
    # Shoulder joint
    shoulder_r = max(2, int(r * 0.10))
    pygame.draw.circle(surface, body_dark, (arm_base_x, arm_base_y),
                       shoulder_r)
    pygame.draw.circle(surface, body_light, (arm_base_x, arm_base_y),
                       max(1, shoulder_r - iz))
    # Upper arm segment
    elbow_x = arm_base_x - max(2, int(r * 0.26))
    elbow_y = arm_base_y - max(2, int(r * 0.18))
    pygame.draw.line(
        surface, body_dark,
        (arm_base_x, arm_base_y), (elbow_x, elbow_y),
        max(2, iz * 2),
    )
    pygame.draw.line(
        surface, body_light,
        (arm_base_x, arm_base_y - 1), (elbow_x, elbow_y - 1),
        max(1, iz),
    )
    # Elbow joint
    pygame.draw.circle(surface, body_dark, (elbow_x, elbow_y),
                       max(2, int(r * 0.07)))
    # Forearm + claw
    claw_x = elbow_x - max(2, int(r * 0.12))
    claw_y = elbow_y + max(1, int(r * 0.04))
    pygame.draw.line(
        surface, body_dark,
        (elbow_x, elbow_y), (claw_x, claw_y), max(2, iz * 2),
    )
    # Claw tips (tiny V)
    pygame.draw.line(surface, accent, (claw_x, claw_y),
                     (claw_x - max(1, iz), claw_y + max(1, iz)),
                     max(1, iz))
    pygame.draw.line(surface, accent, (claw_x, claw_y),
                     (claw_x - max(1, iz), claw_y - max(1, iz)),
                     max(1, iz))

    # ── Corner rivets ──────────────────────────────────────────
    for cx_, cy_ in (
        (body_rect.x + max(2, iz), body_top + max(2, iz)),
        (body_rect.right - max(2, iz) - 1, body_top + max(2, iz)),
        (body_rect.x + max(2, iz), body_bottom - max(2, iz) - 1),
        (body_rect.right - max(2, iz) - 1, body_bottom - max(2, iz) - 1),
    ):
        pygame.draw.circle(surface, body_dark, (cx_, cy_), max(1, iz))


def draw_research_center(surface: pygame.Surface, sx: float, sy: float, r: int, z: float) -> None:
    """Research Center — domed building with antenna/satellite dish."""
    if _try_sprite(surface, "buildings/research_center", sx, sy, r, z):
        return
    isx, isy = int(sx), int(sy)
    iz = max(1, int(z))
    base_col = (70, 100, 150)
    dark = _darken(base_col, 0.6)
    light = _lighten(base_col, 1.3)

    # Main dome body (ellipse)
    bw = max(6, int(r * 1.0))
    bh = max(4, int(r * 0.6))
    body = pygame.Rect(isx - bw // 2, isy - bh, bw, bh)
    pygame.draw.ellipse(surface, base_col, body)
    pygame.draw.ellipse(surface, dark, body, iz)

    # Base platform
    plat_w = max(6, int(r * 1.1))
    plat_h = max(2, int(r * 0.15))
    plat = pygame.Rect(isx - plat_w // 2, isy - plat_h, plat_w, plat_h)
    pygame.draw.rect(surface, dark, plat)

    # Antenna / spire
    ant_h = max(4, int(r * 0.7))
    ant_x = isx
    ant_bot = isy - bh
    pygame.draw.line(surface, light, (ant_x, ant_bot), (ant_x, ant_bot - ant_h), max(1, iz))

    # Dish (small arc at top of antenna)
    dish_r = max(2, int(r * 0.2))
    pygame.draw.arc(
        surface, light,
        (ant_x - dish_r, ant_bot - ant_h - dish_r // 2, dish_r * 2, dish_r),
        0.3, 2.8, max(1, iz),
    )

    # Glowing dot at top
    dot_r = max(1, int(r * 0.06))
    pygame.draw.circle(surface, (100, 200, 255), (ant_x, ant_bot - ant_h), dot_r)


# ═══════════════════════════════════════════════════════════════════════
#  Tier 4+ industrial buildings
# ═══════════════════════════════════════════════════════════════════════

def draw_chemical_plant(surface: pygame.Surface, sx: float, sy: float, r: int, z: float) -> None:
    """Chemical Plant — vat + bubbling pipes."""
    if _try_sprite(surface, "buildings/chemical_plant", sx, sy, r, z):
        return
    isx, isy = int(sx), int(sy)
    iz = max(1, int(z))
    base = (90, 130, 110)
    dark = _darken(base, 0.6)
    light = _lighten(base, 1.3)
    glow = (140, 220, 110)
    # Tank body
    tank_w = max(4, int(r * 0.95))
    tank_h = max(4, int(r * 0.85))
    tank_top = isy - tank_h
    tank_rect = pygame.Rect(isx - tank_w // 2, tank_top, tank_w, tank_h)
    pygame.draw.rect(surface, base, tank_rect, border_radius=max(2, iz * 2))
    pygame.draw.rect(surface, dark, tank_rect, iz, border_radius=max(2, iz * 2))
    # Liquid level (bright green)
    liquid_h = max(2, int(tank_h * 0.55))
    liquid_rect = pygame.Rect(
        tank_rect.x + iz, tank_rect.bottom - liquid_h - iz,
        tank_w - iz * 2, liquid_h,
    )
    pygame.draw.rect(surface, glow, liquid_rect)
    # Bubbles
    for i, fx in enumerate((0.25, 0.55, 0.8)):
        bx = liquid_rect.x + int(liquid_rect.w * fx)
        by = liquid_rect.y + max(2, int(liquid_rect.h * (0.3 + 0.15 * (i % 2))))
        pygame.draw.circle(surface, light, (bx, by), max(1, iz))
    # Top pipes
    pipe_y = tank_top - max(2, int(r * 0.18))
    pygame.draw.line(surface, dark,
                     (tank_rect.x + tank_w // 4, pipe_y),
                     (tank_rect.right - tank_w // 4, pipe_y), max(2, iz * 2))
    # Vertical risers
    pygame.draw.line(surface, dark,
                     (tank_rect.x + tank_w // 4, pipe_y),
                     (tank_rect.x + tank_w // 4, tank_top), max(2, iz * 2))
    pygame.draw.line(surface, dark,
                     (tank_rect.right - tank_w // 4, pipe_y),
                     (tank_rect.right - tank_w // 4, tank_top), max(2, iz * 2))
    # Cap valve
    pygame.draw.circle(surface, dark, (isx, pipe_y), max(2, int(r * 0.10)))
    pygame.draw.circle(surface, light, (isx, pipe_y), max(1, int(r * 0.05)))


def draw_conveyor(
    surface: pygame.Surface,
    sx: float,
    sy: float,
    r: int,
    z: float,
    neighbour_dirs: list[int] | None = None,
    q: int = 0,
    rcoord: int = 0,
) -> None:
    """Conveyor belt — flat strip with arrow chevrons (path-like)."""
    if _try_sprite(surface, "buildings/conveyor", sx, sy, r, z):
        return
    isx, isy = int(sx), int(sy)
    iz = max(1, int(z))
    belt = (70, 70, 80)
    edge = (130, 130, 140)
    chevron = (255, 200, 60)
    # Belt strip across the hex
    belt_w = max(4, int(r * 1.6))
    belt_h = max(3, int(r * 0.55))
    belt_rect = pygame.Rect(isx - belt_w // 2, isy - belt_h // 2, belt_w, belt_h)
    pygame.draw.rect(surface, belt, belt_rect, border_radius=max(1, iz))
    # Edge rails
    pygame.draw.line(surface, edge,
                     (belt_rect.x, belt_rect.y),
                     (belt_rect.right, belt_rect.y), max(1, iz))
    pygame.draw.line(surface, edge,
                     (belt_rect.x, belt_rect.bottom),
                     (belt_rect.right, belt_rect.bottom), max(1, iz))
    # Arrow chevrons indicating flow
    chev_count = 3
    spacing = belt_w // (chev_count + 1)
    for i in range(chev_count):
        cx_ = belt_rect.x + spacing * (i + 1)
        cy_ = isy
        size = max(2, int(belt_h * 0.35))
        pygame.draw.lines(surface, chevron, False, [
            (cx_ - size, cy_ - size),
            (cx_ + size, cy_),
            (cx_ - size, cy_ + size),
        ], max(1, iz))


def draw_solar_array(surface: pygame.Surface, sx: float, sy: float, r: int, z: float) -> None:
    """Solar Array — angled panel grid on a stand."""
    if _try_sprite(surface, "buildings/solar_array", sx, sy, r, z):
        return
    isx, isy = int(sx), int(sy)
    iz = max(1, int(z))
    panel = (40, 70, 140)
    panel_light = (90, 130, 220)
    frame = (180, 180, 190)
    stand = (90, 90, 100)
    # Panel quad (trapezoid for tilt)
    pw = max(4, int(r * 1.20))
    ph = max(3, int(r * 0.55))
    top_w = int(pw * 0.78)
    top_y = isy - ph - max(2, int(r * 0.12))
    bot_y = isy - max(2, int(r * 0.05))
    poly = [
        (isx - top_w // 2, top_y),
        (isx + top_w // 2, top_y),
        (isx + pw // 2, bot_y),
        (isx - pw // 2, bot_y),
    ]
    pygame.draw.polygon(surface, panel, poly)
    pygame.draw.polygon(surface, frame, poly, max(1, iz))
    # Grid lines (3 cols �— 2 rows)
    for col in range(1, 3):
        x_top = isx - top_w // 2 + (top_w * col) // 3
        x_bot = isx - pw // 2 + (pw * col) // 3
        pygame.draw.line(surface, frame, (x_top, top_y), (x_bot, bot_y), max(1, iz))
    mid_y = (top_y + bot_y) // 2
    pygame.draw.line(surface, frame,
                     (isx - (top_w + pw) // 4, mid_y),
                     (isx + (top_w + pw) // 4, mid_y), max(1, iz))
    # Highlight on top-left cell
    hl_x = isx - top_w // 2 + max(1, iz)
    hl_y = top_y + max(1, iz)
    pygame.draw.line(surface, panel_light, (hl_x, hl_y),
                     (hl_x + top_w // 4, hl_y), max(1, iz))
    # Stand
    pygame.draw.line(surface, stand, (isx, bot_y),
                     (isx, isy + max(2, int(r * 0.10))), max(2, iz * 2))


def draw_rocket_silo(surface: pygame.Surface, sx: float, sy: float, r: int, z: float) -> None:
    """Rocket Silo — tall white rocket with red fins on a launch pad."""
    if _try_sprite(surface, "buildings/rocket_silo", sx, sy, r, z):
        return
    isx, isy = int(sx), int(sy)
    iz = max(1, int(z))
    body = (235, 235, 240)
    body_dark = _darken(body, 0.7)
    fin = (210, 60, 50)
    pad = (90, 90, 95)
    flame = (255, 180, 60)
    # Launch pad
    pad_w = max(5, int(r * 1.40))
    pad_h = max(2, int(r * 0.18))
    pad_rect = pygame.Rect(isx - pad_w // 2, isy - pad_h // 2, pad_w, pad_h)
    pygame.draw.rect(surface, pad, pad_rect, border_radius=max(1, iz))
    pygame.draw.rect(surface, _darken(pad, 0.7), pad_rect, max(1, iz),
                     border_radius=max(1, iz))
    # Rocket body
    body_w = max(3, int(r * 0.55))
    body_h = max(5, int(r * 1.40))
    body_top = isy - body_h
    body_rect = pygame.Rect(isx - body_w // 2, body_top, body_w, body_h - pad_h // 2)
    pygame.draw.rect(surface, body, body_rect, border_radius=max(1, iz))
    pygame.draw.rect(surface, body_dark, body_rect, max(1, iz),
                     border_radius=max(1, iz))
    # Nose cone (triangle)
    nose_h = max(3, int(r * 0.45))
    pygame.draw.polygon(surface, body, [
        (isx - body_w // 2, body_top),
        (isx + body_w // 2, body_top),
        (isx, body_top - nose_h),
    ])
    pygame.draw.polygon(surface, body_dark, [
        (isx - body_w // 2, body_top),
        (isx + body_w // 2, body_top),
        (isx, body_top - nose_h),
    ], max(1, iz))
    # Window
    pygame.draw.circle(surface, (90, 160, 220), (isx, body_top + body_h // 4),
                       max(2, int(r * 0.10)))
    # Side fins
    fin_h = max(3, int(r * 0.40))
    pygame.draw.polygon(surface, fin, [
        (isx - body_w // 2, body_rect.bottom - fin_h),
        (isx - body_w // 2, body_rect.bottom),
        (isx - body_w // 2 - max(2, int(r * 0.20)), body_rect.bottom),
    ])
    pygame.draw.polygon(surface, fin, [
        (isx + body_w // 2, body_rect.bottom - fin_h),
        (isx + body_w // 2, body_rect.bottom),
        (isx + body_w // 2 + max(2, int(r * 0.20)), body_rect.bottom),
    ])
    # Engine flame hint
    pygame.draw.polygon(surface, flame, [
        (isx - body_w // 3, body_rect.bottom),
        (isx + body_w // 3, body_rect.bottom),
        (isx, body_rect.bottom + max(2, int(r * 0.18))),
    ])


def draw_oil_drill(surface: pygame.Surface, sx: float, sy: float, r: int, z: float) -> None:
    """Oil Drill — small derrick + horse-head pump on top of an oil pool."""
    if _try_sprite(surface, "buildings/oil_drill", sx, sy, r, z):
        return
    isx, isy = int(sx), int(sy)
    iz = max(1, int(z))
    base = (60, 55, 65)
    metal = (140, 140, 150)
    accent = (200, 90, 50)
    # Concrete pad
    pad_w = max(4, int(r * 1.3))
    pad_h = max(2, int(r * 0.30))
    pad_rect = pygame.Rect(isx - pad_w // 2, isy + max(2, int(r * 0.40)) - pad_h // 2, pad_w, pad_h)
    pygame.draw.rect(surface, (130, 130, 125), pad_rect, border_radius=max(1, iz))
    # Derrick legs (X frame)
    leg_h = max(6, int(r * 1.0))
    top_y = pad_rect.y - leg_h
    pygame.draw.line(surface, metal,
                     (pad_rect.x + iz, pad_rect.y),
                     (isx, top_y), max(1, iz))
    pygame.draw.line(surface, metal,
                     (pad_rect.right - iz, pad_rect.y),
                     (isx, top_y), max(1, iz))
    pygame.draw.line(surface, metal,
                     (pad_rect.x + pad_w // 4, pad_rect.y),
                     (isx + pad_w // 6, top_y + leg_h // 3), max(1, iz))
    pygame.draw.line(surface, metal,
                     (pad_rect.right - pad_w // 4, pad_rect.y),
                     (isx - pad_w // 6, top_y + leg_h // 3), max(1, iz))
    # Pivot block at top
    pygame.draw.rect(surface, base,
                     pygame.Rect(isx - max(2, int(r * 0.18)), top_y,
                                 max(4, int(r * 0.36)), max(3, int(r * 0.22))))
    # Horse-head walking beam
    beam_len = max(6, int(r * 1.2))
    beam_thick = max(2, int(r * 0.18))
    beam_y = top_y + beam_thick // 2
    beam_rect = pygame.Rect(isx - beam_len // 2, beam_y, beam_len, beam_thick)
    pygame.draw.rect(surface, accent, beam_rect, border_radius=max(1, iz))
    # Horse head end
    head_r = max(2, int(r * 0.20))
    pygame.draw.circle(surface, accent, (beam_rect.right, beam_rect.centery), head_r)


def draw_oil_refinery(surface: pygame.Surface, sx: float, sy: float, r: int, z: float) -> None:
    """Oil Refinery — twin distillation columns linked by pipes."""
    if _try_sprite(surface, "buildings/oil_refinery", sx, sy, r, z):
        return
    isx, isy = int(sx), int(sy)
    iz = max(1, int(z))
    base = (90, 85, 105)
    dark = _darken(base, 0.65)
    light = _lighten(base, 1.30)
    pipe = (160, 140, 90)
    # Foundation slab
    slab_w = max(6, int(r * 1.5))
    slab_h = max(2, int(r * 0.22))
    slab_rect = pygame.Rect(isx - slab_w // 2, isy + max(2, int(r * 0.35)) - slab_h // 2,
                             slab_w, slab_h)
    pygame.draw.rect(surface, dark, slab_rect, border_radius=max(1, iz))
    # Twin columns
    col_w = max(3, int(r * 0.36))
    col_h = max(8, int(r * 1.1))
    col_top = slab_rect.y - col_h
    left_col = pygame.Rect(isx - int(r * 0.55), col_top, col_w, col_h)
    right_col = pygame.Rect(isx + int(r * 0.55) - col_w, col_top, col_w, col_h)
    for col in (left_col, right_col):
        pygame.draw.rect(surface, base, col, border_radius=max(1, iz))
        pygame.draw.rect(surface, dark, col, iz, border_radius=max(1, iz))
        # bands
        for f in (0.25, 0.55, 0.85):
            by = col.y + int(col.h * f)
            pygame.draw.line(surface, light, (col.x + iz, by),
                             (col.right - iz, by), max(1, iz))
    # Cap domes
    for col in (left_col, right_col):
        pygame.draw.circle(surface, light, (col.centerx, col.y), max(2, col_w // 2))
    # Linking pipe near the top
    link_y = col_top + max(2, int(col_h * 0.18))
    pygame.draw.line(surface, pipe,
                     (left_col.right, link_y), (right_col.x, link_y), max(2, iz * 2))
    # Vent flame on the left column
    flame_y = col_top - max(2, int(r * 0.18))
    pygame.draw.polygon(surface, (240, 160, 60), [
        (left_col.centerx - max(1, iz), flame_y + iz),
        (left_col.centerx + max(1, iz), flame_y + iz),
        (left_col.centerx, flame_y - max(2, iz * 2)),
    ])

# -----------------------------------------------------------------------
#  ANCIENT TECH TOWER  (rises during awakening events)
# -----------------------------------------------------------------------

def draw_ancient_tower(surface, sx, sy, r, z, rise=1.0):
    """Draw an ancient-tech obelisk tower.

    ``rise`` 0..1 controls how far the tower has emerged from the
    ground (used by the awakening cutscene).  At ``rise=0`` only a
    glowing crack is visible; at ``rise=1`` the tower is fully out.
    """
    if _try_sprite(surface, "buildings/ancient_tower", sx, sy, r, z):
        return
    iz = max(1, int(z))
    rise = max(0.0, min(1.0, rise))

    # Base disc — cracked stone pad always visible.
    base_col = (38, 30, 32)
    crack_col = (180, 60, 200)
    pad_r = max(3, int(r * 1.05))
    pygame.draw.circle(surface, base_col, (int(sx), int(sy + r * 0.15)), pad_r)
    # Cracks radiating out (always present).
    for i in range(6):
        ang = i * math.pi / 3.0 + 0.2
        ex = sx + math.cos(ang) * pad_r * 0.95
        ey = sy + r * 0.15 + math.sin(ang) * pad_r * 0.55
        pygame.draw.line(surface, crack_col,
                         (int(sx), int(sy + r * 0.15)),
                         (int(ex), int(ey)), max(1, iz))

    if rise <= 0.02:
        return

    # Tower body — tall hexagonal obelisk that scales from 0 to full
    # height as ``rise`` grows.
    full_h = r * 2.4
    h = full_h * rise
    half_w_top = r * 0.45
    half_w_bot = r * 0.7
    top_y = sy - h + r * 0.15

    body_col = (52, 44, 70)
    body_light = (110, 95, 160)
    body_dark = (24, 18, 36)

    pygame.draw.polygon(surface, body_col, [
        (sx - half_w_bot, sy + r * 0.15),
        (sx - half_w_top, top_y),
        (sx + half_w_top, top_y),
        (sx + half_w_bot, sy + r * 0.15),
    ])
    pygame.draw.line(surface, body_light,
                     (sx, top_y + iz),
                     (sx, sy + r * 0.05), max(1, iz))
    pygame.draw.line(surface, body_dark,
                     (sx + half_w_top, top_y),
                     (sx + half_w_bot, sy + r * 0.15), max(1, iz))

    # Glowing top eye / crystal — brightens with rise.
    eye_y = top_y + r * 0.35
    eye_r = max(2, int(r * 0.3))
    eye_pulse = 0.6 + 0.4 * rise
    eye_col = (
        min(255, int(180 * eye_pulse)),
        min(255, int(80 * eye_pulse)),
        min(255, int(220 * eye_pulse)),
    )
    eye_glow = (220, 130, 255)
    if eye_y < sy + r * 0.1:
        pygame.draw.circle(surface, eye_col, (int(sx), int(eye_y)), eye_r)
        pygame.draw.circle(surface, eye_glow, (int(sx), int(eye_y)), eye_r, max(1, iz))

    # Soft floor glow ring during rise — sells the "emerging" feeling.
    if rise < 1.0:
        glow_a = int(160 * (1.0 - rise))
        if pad_r > 4 and glow_a > 8:
            ring_size = pad_r * 4
            ring = pygame.Surface((ring_size, ring_size), pygame.SRCALPHA)
            pygame.draw.circle(ring, (220, 110, 255, glow_a),
                               (pad_r * 2, pad_r * 2), int(pad_r * 1.6))
            pygame.draw.circle(ring, (0, 0, 0, 0),
                               (pad_r * 2, pad_r * 2), int(pad_r * 0.9))
            surface.blit(ring,
                         (int(sx) - pad_r * 2,
                          int(sy + r * 0.15) - pad_r * 2))


# -- Defense buildings ---------------------------------------------


def draw_turret(surface: pygame.Surface, sx: float, sy: float, r: int, z: float) -> None:
    """Defensive auto-cannon. Stone base, swivel head, barrel."""
    if _try_sprite(surface, "buildings/turret", sx, sy, r, z):
        return
    isx, isy = int(sx), int(sy)
    iz = max(1, int(z))
    base_col = (140, 135, 130)
    metal = (90, 90, 105)
    barrel = (60, 60, 70)
    accent = (200, 80, 60)
    # Stone base ring
    base_r = max(4, int(r * 0.55))
    pygame.draw.circle(surface, base_col, (isx, isy), base_r)
    pygame.draw.circle(surface, _darken(base_col, 0.55), (isx, isy), base_r, max(1, iz))
    # Swivel turret body
    body_r = max(3, int(r * 0.32))
    pygame.draw.circle(surface, metal, (isx, isy - max(2, int(r * 0.1))), body_r)
    pygame.draw.circle(surface, _darken(metal, 0.6), (isx, isy - max(2, int(r * 0.1))), body_r, max(1, iz))
    # Barrel
    barrel_len = max(4, int(r * 0.7))
    barrel_w = max(2, int(r * 0.16))
    pygame.draw.rect(surface, barrel,
                     pygame.Rect(isx, isy - max(2, int(r * 0.1)) - barrel_w // 2,
                                 barrel_len, barrel_w))
    # Red targeting tip
    pygame.draw.circle(surface, accent,
                       (isx + barrel_len, isy - max(2, int(r * 0.1))),
                       max(1, int(r * 0.1)))


def draw_trap(surface: pygame.Surface, sx: float, sy: float, r: int, z: float) -> None:
    """Spike trap � wooden plate with iron spikes; one-shot."""
    if _try_sprite(surface, "buildings/trap", sx, sy, r, z):
        return
    isx, isy = int(sx), int(sy)
    iz = max(1, int(z))
    plate = (110, 80, 50)
    spike = (180, 180, 195)
    spike_dark = (120, 120, 135)
    # Wood plate
    plate_r = max(3, int(r * 0.5))
    pygame.draw.circle(surface, plate, (isx, isy), plate_r)
    pygame.draw.circle(surface, _darken(plate, 0.6), (isx, isy), plate_r, max(1, iz))
    # Spikes (8 around the rim, pointing outward)
    import math as _m
    sp_len = max(2, int(r * 0.28))
    for i in range(8):
        ang = i * (_m.pi / 4) + _m.pi / 8
        bx = isx + int(_m.cos(ang) * plate_r * 0.55)
        by = isy + int(_m.sin(ang) * plate_r * 0.55)
        tx = isx + int(_m.cos(ang) * (plate_r + sp_len))
        ty = isy + int(_m.sin(ang) * (plate_r + sp_len))
        pygame.draw.line(surface, spike_dark, (bx, by), (tx, ty), max(2, iz + 1))
        pygame.draw.line(surface, spike,
                         (bx + iz, by - iz), (tx + iz, ty - iz), max(1, iz))


def draw_enemy(
    surface: pygame.Surface, sx: float, sy: float,
    type_name: str, color: tuple, radius_px: int, z: float,
) -> None:
    """Procedural enemy fallback when no sprite exists.

    Spider-like silhouette: dark body, glowing core, three pairs of
    legs.  Larger `radius_px` for higher-tier enemies.
    """
    if _try_sprite(surface, f"enemies/{type_name.lower()}", sx, sy, max(4, int(radius_px * z)), z):
        return
    isx, isy = int(sx), int(sy)
    iz = max(1, int(z))
    rr = max(3, int(radius_px * z))
    # Body
    body_col = _darken(color, 0.55)
    pygame.draw.circle(surface, body_col, (isx, isy), rr)
    # Core glow
    pygame.draw.circle(surface, color, (isx, isy), max(2, rr // 2))
    # Highlight
    pygame.draw.circle(surface, _lighten(color, 1.4),
                       (isx - rr // 4, isy - rr // 4), max(1, rr // 4))
    # Legs
    import math as _m
    leg_len = int(rr * 1.4)
    for i in range(6):
        ang = i * (_m.pi / 3) + _m.pi / 6
        tx = isx + int(_m.cos(ang) * leg_len)
        ty = isy + int(_m.sin(ang) * leg_len)
        pygame.draw.line(surface, body_col, (isx, isy), (tx, ty), max(1, iz))
