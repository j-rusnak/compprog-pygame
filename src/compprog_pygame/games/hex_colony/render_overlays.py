"""Overlay drawing functions — trees, rocks, ripples, bushes, grass."""

from __future__ import annotations

import math

import pygame

from compprog_pygame.games.hex_colony.overlay import (
    OverlayBush,
    OverlayGrassTuft,
    OverlayRipple,
    OverlayRock,
    OverlayTree,
)
from compprog_pygame.games.hex_colony.render_utils import _darken


def draw_tree(
    surface: pygame.Surface, item: OverlayTree,
    sx: float, sy: float, z: float, iz: int,
) -> None:
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
    br = max(2, int(item.radius * z))
    pygame.draw.circle(surface, item.color, (int(sx), int(sy)), br)
    if item.berry_color is not None:
        pygame.draw.circle(surface, item.berry_color, (int(sx) + iz, int(sy) - iz), iz)


def draw_grass(
    surface: pygame.Surface, item: OverlayGrassTuft,
    sx: float, sy: float, z: float, iz: int,
) -> None:
    h = max(1, int(item.h * z))
    px, py = int(sx), int(sy)
    # Two blades at slight angles for a more natural look
    pygame.draw.line(surface, item.color, (px, py), (px + iz, py - h), iz)
    if h > 1:
        darker = _darken(item.color, 0.85)
        pygame.draw.line(surface, darker, (px, py), (px - iz, py - max(1, h - 1)), iz)
