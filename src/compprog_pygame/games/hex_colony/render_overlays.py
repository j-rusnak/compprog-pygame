"""Overlay drawing functions — trees, rocks, ripples, bushes, grass, crystals.

Each function first checks for a matching sprite in the sprite manager.
If a sprite PNG is available it is drawn scaled to the current zoom;
otherwise the original procedural drawing code is used as a fallback.
"""

from __future__ import annotations

import math

import pygame

from compprog_pygame.games.hex_colony.overlay import (
    OverlayBush,
    OverlayCrystal,
    OverlayGrassTuft,
    OverlayRipple,
    OverlayRock,
    OverlayTree,
)
from compprog_pygame.games.hex_colony.render_utils import _darken
from compprog_pygame.games.hex_colony.sprites import sprites


def _try_overlay_sprite(
    surface: pygame.Surface, key: str,
    sx: float, sy: float, z: float, base_w: int, base_h: int,
) -> bool:
    """Attempt to blit an overlay sprite.  Returns True if successful."""
    sheet = sprites.get(key)
    if sheet is None:
        return False
    w = max(1, int(base_w * z))
    h = max(1, int(base_h * z))
    img = sheet.get(w, h)
    surface.blit(img, (int(sx) - w // 2, int(sy) - h // 2))
    return True


def draw_tree(
    surface: pygame.Surface, item: OverlayTree,
    sx: float, sy: float, z: float, iz: int,
) -> None:
    key = f"overlays/tree_{item.style}"
    total_h = item.trunk_h + item.crown_ry * 2
    if _try_overlay_sprite(surface, key, sx, sy - total_h * z * 0.3, z, item.crown_rx * 3, int(total_h * 1.2)):
        return
    if item.style == "canopy":
        crx = max(3, int(item.crown_rx * z))
        cry = max(2, int(item.crown_ry * z))
        th = max(2, int(item.trunk_h * z))
        tw = max(1, int(2 * z))
        # Shadow
        sh_rx, sh_ry = max(2, crx // 2), max(1, cry // 4)
        pygame.draw.ellipse(
            surface, (10, 30, 10),
            (int(sx - sh_rx), int(sy + iz), sh_rx * 2, sh_ry * 2),
        )
        # Trunk
        pygame.draw.line(surface, item.trunk_color,
                         (int(sx), int(sy)), (int(sx), int(sy - th)), tw)
        # Crown
        cy_top = int(sy - th - cry)
        pygame.draw.ellipse(
            surface, item.crown_color,
            (int(sx - crx), cy_top, crx * 2, cry * 2),
        )
        # Highlight
        hl_rx = max(1, crx // 2)
        hl_ry = max(1, int(cry * 0.6))
        pygame.draw.ellipse(
            surface, item.highlight_color,
            (int(sx - crx * 0.6), int(cy_top + cry * 0.15), hl_rx * 2, hl_ry * 2),
        )
    elif item.style == "conifer":
        crx = max(2, int(item.crown_rx * z))
        cry = max(3, int(item.crown_ry * z * 1.3))
        th = max(1, int(item.trunk_h * z))
        pygame.draw.line(surface, item.trunk_color,
                         (int(sx), int(sy)), (int(sx), int(sy - th)), max(1, int(z)))
        top_y = int(sy - th - cry)
        pts = [(int(sx), top_y), (int(sx - crx), int(sy - th)), (int(sx + crx), int(sy - th))]
        pygame.draw.polygon(surface, item.crown_color, pts)
        hl_pts = [
            (int(sx), top_y),
            (int(sx - crx * 0.4), int(sy - th - cry * 0.35)),
            (int(sx), int(sy - th)),
        ]
        pygame.draw.polygon(surface, item.highlight_color, hl_pts)
    else:
        cr = max(2, int(item.crown_rx * z))
        th = max(1, int(item.trunk_h * z))
        pygame.draw.line(surface, item.trunk_color,
                         (int(sx), int(sy)), (int(sx), int(sy - th)), max(1, int(z)))
        head_y = int(sy - th - cr)
        pygame.draw.circle(surface, item.crown_color, (int(sx), head_y), cr)
        hl_r = max(1, cr // 2)
        pygame.draw.circle(surface, item.highlight_color, (int(sx) - iz, head_y - iz), hl_r)


def draw_rock(
    surface: pygame.Surface, item: OverlayRock,
    sx: float, sy: float, z: float, iz: int,
) -> None:
    if _try_overlay_sprite(surface, "overlays/rock", sx, sy, z, item.w * 3, item.h * 3):
        return
    rw = max(2, int(item.w * z))
    rh = max(2, int(item.h * z))
    pts = [
        (int(sx - rw), int(sy + rh // 2)),
        (int(sx - rw // 2), int(sy - rh)),
        (int(sx + rw // 2), int(sy - rh)),
        (int(sx + rw), int(sy + rh // 2)),
    ]
    pygame.draw.polygon(surface, item.color, pts)
    pygame.draw.line(surface, item.highlight_color, pts[1], pts[2], iz)
    pygame.draw.line(surface, _darken(item.color, 0.6), pts[3], pts[0], iz)


def draw_ripple(
    surface: pygame.Surface, item: OverlayRipple,
    sx: float, sy: float, z: float, iz: int, tick: float,
) -> None:
    phase = tick * 1.5
    offset = math.sin(phase + item.phase_offset) * 2 * z
    px = int(sx + offset)
    py = int(sy)
    w = max(2, int(item.w * z))
    # Vary colour slightly per ripple for depth
    bright = 0.85 + 0.15 * math.sin(item.phase_offset)
    col = (int(55 * bright), int(115 * bright), int(215 * bright))
    pygame.draw.line(surface, col, (px - w, py), (px + w, py), iz)
    # Faint highlight above
    if z > 0.5:
        hl = (int(80 * bright), int(145 * bright), int(230 * bright))
        pygame.draw.line(surface, hl, (px - w + iz, py - iz), (px + w - iz, py - iz), max(1, iz - 1))


def draw_bush(
    surface: pygame.Surface, item: OverlayBush,
    sx: float, sy: float, z: float, iz: int,
) -> None:
    if _try_overlay_sprite(surface, "overlays/bush", sx, sy, z, item.radius * 3, item.radius * 3):
        return
    br = max(2, int(item.radius * z))
    # Dark outline for contrast against grass
    pygame.draw.circle(surface, _darken(item.color, 0.7), (int(sx), int(sy)), br + max(1, iz))
    pygame.draw.circle(surface, item.color, (int(sx), int(sy)), br)
    if item.berry_color is not None:
        berry_r = max(1, iz + (1 if br > 4 else 0))
        pygame.draw.circle(surface, item.berry_color, (int(sx) + iz, int(sy) - iz), berry_r)


def draw_grass(
    surface: pygame.Surface, item: OverlayGrassTuft,
    sx: float, sy: float, z: float, iz: int,
) -> None:
    if _try_overlay_sprite(surface, "overlays/grass", sx, sy, z, 8, item.h * 2):
        return
    h = max(1, int(item.h * z))
    px, py = int(sx), int(sy)
    # Two blades at slight angles for a more natural look
    pygame.draw.line(surface, item.color, (px, py), (px + iz, py - h), iz)
    if h > 1:
        darker = _darken(item.color, 0.85)
        pygame.draw.line(surface, darker, (px, py), (px - iz, py - max(1, h - 1)), iz)


def draw_crystal(
    surface: pygame.Surface, item: OverlayCrystal,
    sx: float, sy: float, z: float, iz: int,
) -> None:
    """Draw a faceted crystal shard poking out of the ground."""
    # Pick sprite based on crystal colour (iron vs copper)
    key = "overlays/crystal_iron" if item.color[0] > item.color[2] else "overlays/crystal_copper"
    if _try_overlay_sprite(surface, key, sx, sy, z, item.w * 3, item.h * 2):
        return
    h = max(3, int(item.h * z))
    w = max(2, int(item.w * z))
    # Crystal is a tall narrow polygon — a pointed shard
    sin_a = math.sin(item.angle)
    cos_a = math.cos(item.angle)
    # Tip (top), base-left, base-right, with slight tilt
    tip_x = int(sx + sin_a * h)
    tip_y = int(sy - cos_a * h)
    bl_x = int(sx - w)
    bl_y = int(sy)
    br_x = int(sx + w)
    br_y = int(sy)
    # Main crystal body
    pts = [(tip_x, tip_y), (bl_x, bl_y), (br_x, br_y)]
    pygame.draw.polygon(surface, item.color, pts)
    # Highlight facet on left side
    mid_x = int(sx + sin_a * h * 0.4 - w * 0.3)
    mid_y = int(sy - cos_a * h * 0.4)
    hl_pts = [(tip_x, tip_y), (bl_x, bl_y), (mid_x, mid_y)]
    pygame.draw.polygon(surface, item.highlight_color, hl_pts)
    # Outline
    pygame.draw.polygon(surface, _darken(item.color, 0.6), pts, max(1, iz))
