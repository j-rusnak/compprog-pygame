"""Procedurally-drawn resource icon sprites.

Every material in the game needs a recognisable icon that reads well at
small sizes in the UI.  Unicode glyphs are unreliable because many
system fonts don't ship the required codepoints, so we draw our own.

Usage:
    >>> icon = get_resource_icon(Resource.IRON_BAR, 20)
    >>> surface.blit(icon, (x, y))

Icons are cached per ``(Resource, size)`` tuple and rendered once.
"""

from __future__ import annotations

import pygame

from compprog_pygame.games.hex_colony.resources import Resource

# ── Palette ──────────────────────────────────────────────────────

_PALETTE: dict[Resource, tuple[tuple[int, int, int], tuple[int, int, int]]] = {
    # (main, highlight)
    Resource.WOOD:        ((140,  90,  45), (205, 150,  95)),
    Resource.FIBER:       (( 90, 160,  60), (170, 215, 110)),
    Resource.STONE:       ((150, 150, 142), (210, 210, 202)),
    Resource.FOOD:        ((190,  60,  55), (240, 130,  95)),
    Resource.IRON:        (( 95, 100, 115), (180, 190, 210)),
    Resource.COPPER:      ((195, 110,  55), (240, 180, 110)),
    Resource.PLANKS:      ((195, 150,  85), (235, 200, 140)),
    Resource.IRON_BAR:    ((140, 145, 165), (215, 225, 240)),
    Resource.COPPER_BAR:  ((210, 130,  70), (245, 195, 125)),
    Resource.BRICKS:      ((175,  80,  55), (225, 135,  95)),
    Resource.COPPER_WIRE: ((220, 150,  80), (250, 210, 130)),
    Resource.ROPE:        ((175, 140,  85), (215, 185, 130)),
    Resource.CHARCOAL:    (( 55,  52,  55), (120, 110, 100)),
    Resource.GLASS:       ((170, 215, 230), (230, 245, 250)),
    Resource.STEEL_BAR:   ((165, 175, 195), (225, 235, 250)),
    Resource.GEARS:       ((130, 135, 150), (200, 205, 220)),
    Resource.SILICON:     (( 70,  75,  95), (150, 160, 200)),
    Resource.CIRCUIT:     (( 40, 100,  65), (130, 210, 150)),
    Resource.CONCRETE:    ((155, 155, 150), (210, 210, 205)),
    Resource.PLASTIC:     ((200, 200, 215), (240, 240, 250)),
    Resource.ELECTRONICS: (( 35,  90,  60), (110, 200, 140)),
    Resource.BATTERY:     ((215, 180,  50), (250, 230, 110)),
    Resource.ROCKET_FUEL: ((185,  80,  45), (240, 140,  80)),
    Resource.ROCKET_PART: ((180, 190, 210), (235, 240, 250)),
}

_DEFAULT = ((180, 180, 180), (230, 230, 230))


# ── Cache ────────────────────────────────────────────────────────

_cache: dict[tuple[Resource, int], pygame.Surface] = {}


def get_resource_icon(resource: Resource, size: int = 20) -> pygame.Surface:
    """Return an icon surface for *resource* at *size* pixels (square).

    The surface has per-pixel alpha so it can be blitted over any
    background.  Surfaces are cached — callers should not mutate them.
    """
    size = max(8, int(size))
    key = (resource, size)
    surf = _cache.get(key)
    if surf is None:
        surf = _render(resource, size)
        _cache[key] = surf
    return surf


def clear_cache() -> None:
    """Drop all cached icon surfaces (useful after changing DPI)."""
    _cache.clear()


# ── Rendering ────────────────────────────────────────────────────

def _render(resource: Resource, size: int) -> pygame.Surface:
    s = pygame.Surface((size, size), pygame.SRCALPHA)
    main, hl = _PALETTE.get(resource, _DEFAULT)
    shadow = _mul(main, 0.55)
    outline = _mul(main, 0.4)

    drawer = _DRAWERS.get(resource)
    if drawer is None:
        _draw_fallback(s, size, main, hl, shadow, outline)
    else:
        drawer(s, size, main, hl, shadow, outline)
    return s


def _mul(c: tuple[int, int, int], f: float) -> tuple[int, int, int]:
    return (
        max(0, min(255, int(c[0] * f))),
        max(0, min(255, int(c[1] * f))),
        max(0, min(255, int(c[2] * f))),
    )


def _draw_fallback(
    s: pygame.Surface, size: int,
    main, hl, shadow, outline,
) -> None:
    pygame.draw.rect(s, main, (2, 2, size - 4, size - 4), border_radius=3)
    pygame.draw.rect(s, outline, (2, 2, size - 4, size - 4),
                     width=max(1, size // 16), border_radius=3)
    pygame.draw.line(s, hl, (4, 4), (size - 5, 4), max(1, size // 14))


# Each drawer receives a surface of side *size*.

def _draw_wood(s, size, main, hl, shadow, outline) -> None:
    # End-on log: circle with concentric rings + bark
    cx = cy = size // 2
    r = size // 2 - 2
    pygame.draw.circle(s, shadow, (cx, cy + 1), r)
    pygame.draw.circle(s, main, (cx, cy), r)
    pygame.draw.circle(s, outline, (cx, cy), r, max(1, size // 18))
    # Growth rings
    for i, rr in enumerate((r - size // 6, r - size // 3, max(2, r - size // 2))):
        if rr <= 1:
            break
        col = hl if i % 2 == 0 else _mul(main, 0.75)
        pygame.draw.circle(s, col, (cx, cy), rr, max(1, size // 22))
    # Center pith
    pygame.draw.circle(s, shadow, (cx, cy), max(1, size // 10))


def _draw_fiber(s, size, main, hl, shadow, outline) -> None:
    # Three slim stalks converging at the bottom
    base_x = size // 2
    base_y = size - 3
    for angle, col in ((-0.55, shadow), (0.0, main), (0.55, hl)):
        import math
        tip_x = int(base_x + math.sin(angle) * (size * 0.42))
        tip_y = int(base_y - size * 0.75)
        pygame.draw.line(s, col, (base_x, base_y), (tip_x, tip_y),
                         max(2, size // 9))
        # Leaf nub near the tip
        pygame.draw.circle(s, col, (tip_x, tip_y), max(1, size // 11))
    # Ground tuft
    pygame.draw.ellipse(
        s, shadow,
        (base_x - size // 3, base_y - 2, size * 2 // 3, 4),
    )


def _draw_stone(s, size, main, hl, shadow, outline) -> None:
    # Angular pebble
    pts = [
        (size * 0.18, size * 0.58),
        (size * 0.08, size * 0.38),
        (size * 0.30, size * 0.15),
        (size * 0.70, size * 0.10),
        (size * 0.92, size * 0.40),
        (size * 0.82, size * 0.82),
        (size * 0.42, size * 0.90),
    ]
    pygame.draw.polygon(s, shadow, [(x + 1, y + 2) for x, y in pts])
    pygame.draw.polygon(s, main, pts)
    pygame.draw.polygon(s, outline, pts, max(1, size // 16))
    # Highlight facet
    hl_pts = [
        (size * 0.30, size * 0.20),
        (size * 0.62, size * 0.16),
        (size * 0.55, size * 0.42),
        (size * 0.28, size * 0.40),
    ]
    pygame.draw.polygon(s, hl, hl_pts)


def _draw_food(s, size, main, hl, shadow, outline) -> None:
    # Apple-like fruit with leaf
    cx = size // 2
    cy = size // 2 + 1
    r = int(size * 0.36)
    pygame.draw.circle(s, shadow, (cx + 1, cy + 2), r)
    pygame.draw.circle(s, main, (cx, cy), r)
    pygame.draw.circle(s, outline, (cx, cy), r, max(1, size // 18))
    # Highlight
    pygame.draw.circle(s, hl, (cx - r // 3, cy - r // 3), max(2, r // 3))
    # Stem
    stem_top = (cx + 1, cy - r - max(1, size // 10))
    pygame.draw.line(s, (70, 45, 20), (cx + 1, cy - r),
                     stem_top, max(2, size // 12))
    # Leaf
    leaf_pts = [
        stem_top,
        (stem_top[0] + size // 4, stem_top[1] - 1),
        (stem_top[0] + size // 6, stem_top[1] + size // 8),
    ]
    pygame.draw.polygon(s, (70, 140, 60), leaf_pts)


def _draw_iron(s, size, main, hl, shadow, outline) -> None:
    # Chunky ore nugget
    pts = [
        (size * 0.22, size * 0.72),
        (size * 0.12, size * 0.46),
        (size * 0.26, size * 0.22),
        (size * 0.58, size * 0.16),
        (size * 0.86, size * 0.32),
        (size * 0.82, size * 0.70),
        (size * 0.56, size * 0.90),
        (size * 0.32, size * 0.88),
    ]
    pygame.draw.polygon(s, shadow, [(x + 1, y + 2) for x, y in pts])
    pygame.draw.polygon(s, main, pts)
    pygame.draw.polygon(s, outline, pts, max(1, size // 16))
    # Metallic facets
    pygame.draw.line(s, hl,
                     (size * 0.32, size * 0.28),
                     (size * 0.68, size * 0.24),
                     max(2, size // 12))
    pygame.draw.line(s, hl,
                     (size * 0.28, size * 0.50),
                     (size * 0.46, size * 0.38),
                     max(1, size // 18))


def _draw_copper(s, size, main, hl, shadow, outline) -> None:
    _draw_iron(s, size, main, hl, shadow, outline)
    # Add a green tarnish dot
    pygame.draw.circle(
        s, (100, 170, 120),
        (int(size * 0.60), int(size * 0.60)), max(1, size // 14),
    )


def _draw_planks(s, size, main, hl, shadow, outline) -> None:
    # Two stacked boards
    board_h = max(3, size // 4)
    y1 = size // 2 - board_h - 1
    y2 = size // 2 + 1
    for y in (y1, y2):
        rect = pygame.Rect(2, y, size - 4, board_h)
        pygame.draw.rect(s, shadow, rect.move(1, 1), border_radius=1)
        pygame.draw.rect(s, main, rect, border_radius=1)
        pygame.draw.rect(s, outline, rect, max(1, size // 20),
                         border_radius=1)
        # Grain lines
        for gx in range(5, size - 5, max(3, size // 6)):
            pygame.draw.line(s, hl, (gx, y + 1), (gx, y + board_h - 1),
                             max(1, size // 22))


def _draw_iron_bar(s, size, main, hl, shadow, outline) -> None:
    # Isometric ingot
    bar_w = size - 6
    bar_h = max(4, size // 3)
    top = size // 2 - bar_h // 2
    # Trapezoid (wider at bottom — viewed slightly from above)
    top_inset = max(2, size // 10)
    pts = [
        (3 + top_inset, top),
        (3 + bar_w - top_inset, top),
        (3 + bar_w, top + bar_h),
        (3, top + bar_h),
    ]
    pygame.draw.polygon(s, shadow, [(x + 1, y + 2) for x, y in pts])
    pygame.draw.polygon(s, main, pts)
    pygame.draw.polygon(s, outline, pts, max(1, size // 18))
    # Top highlight band
    top_band = [
        pts[0], pts[1],
        (pts[1][0] - max(1, size // 14), top + max(1, size // 10)),
        (pts[0][0] + max(1, size // 14), top + max(1, size // 10)),
    ]
    pygame.draw.polygon(s, hl, top_band)


def _draw_copper_bar(s, size, main, hl, shadow, outline) -> None:
    _draw_iron_bar(s, size, main, hl, shadow, outline)
    # Extra warm highlight band
    band_y = size // 2 + size // 16
    pygame.draw.line(
        s, (255, 230, 180),
        (5, band_y), (size - 6, band_y), max(1, size // 22),
    )


def _draw_bricks(s, size, main, hl, shadow, outline) -> None:
    # Brick stack 2x2 with staggered rows
    pad = 2
    bw = (size - pad * 2) // 2
    bh = (size - pad * 2) // 2
    mortar = _mul(main, 0.45)
    for row in range(2):
        stagger = bw // 2 if row == 1 else 0
        for col in range(-1, 3):
            bx = pad + col * bw + stagger
            by = pad + row * bh
            rect = pygame.Rect(bx, by, bw - 1, bh - 1)
            clip = rect.clip(pygame.Rect(pad, pad,
                                         size - pad * 2, size - pad * 2))
            if clip.w <= 0 or clip.h <= 0:
                continue
            pygame.draw.rect(s, main, clip)
            pygame.draw.rect(s, outline, clip, max(1, size // 22))
            # Top highlight
            pygame.draw.line(
                s, hl,
                (clip.x + 1, clip.y + 1),
                (clip.right - 2, clip.y + 1),
                max(1, size // 26),
            )
    # Outer frame mortar
    pygame.draw.rect(s, mortar,
                     (pad, pad, size - pad * 2, size - pad * 2),
                     max(1, size // 24))


def _draw_copper_wire(s, size, main, hl, shadow, outline) -> None:
    # Coiled wire spiral
    cx = cy = size // 2
    max_r = size // 2 - 3
    # Base shadow coil
    for rr in range(max_r, 1, -max(2, size // 10)):
        pygame.draw.circle(s, shadow, (cx + 1, cy + 1), rr,
                           max(1, size // 16))
    # Main coil
    for rr in range(max_r, 1, -max(2, size // 10)):
        pygame.draw.circle(s, main, (cx, cy), rr, max(1, size // 16))
    # Inner highlight
    pygame.draw.circle(s, hl, (cx - 1, cy - 1), max(1, size // 10))
    # Protruding ends
    pygame.draw.line(s, main,
                     (cx + max_r - 1, cy),
                     (cx + max_r + 2, cy + 2),
                     max(2, size // 14))


def _draw_rope(s, size, main, hl, shadow, outline) -> None:
    # Coiled rope: series of diagonally-twisted bands forming a ring
    cx = cy = size // 2
    max_r = size // 2 - 3
    pygame.draw.circle(s, shadow, (cx + 1, cy + 2), max_r)
    pygame.draw.circle(s, main, (cx, cy), max_r)
    pygame.draw.circle(s, outline, (cx, cy), max_r, max(1, size // 18))
    # Hole in the middle (darker)
    inner_r = max(2, max_r // 2)
    pygame.draw.circle(s, shadow, (cx, cy), inner_r)
    pygame.draw.circle(s, outline, (cx, cy), inner_r, max(1, size // 22))
    # Twist strokes around the outer band
    import math
    band_mid = (max_r + inner_r) // 2
    for i in range(10):
        a = i * math.tau / 10
        x1 = cx + int(math.cos(a) * (band_mid - 2))
        y1 = cy + int(math.sin(a) * (band_mid - 2))
        x2 = cx + int(math.cos(a + 0.35) * (band_mid + 2))
        y2 = cy + int(math.sin(a + 0.35) * (band_mid + 2))
        pygame.draw.line(s, hl, (x1, y1), (x2, y2), max(1, size // 20))


def _draw_charcoal(s, size, main, hl, shadow, outline) -> None:
    # Chunky black lumps with hint of red glow
    import math
    cx = cy = size // 2
    # Two stacked lumps
    for ox, oy, sc in ((-size * 0.15, size * 0.12, 0.55),
                       (size * 0.10, -size * 0.05, 0.60)):
        pts = []
        rr = size * 0.32 * sc
        nsides = 7
        for i in range(nsides):
            a = i * math.tau / nsides + 0.3
            jitter = 0.8 + 0.25 * ((i * 13) % 5) / 5.0
            pts.append((
                cx + ox + math.cos(a) * rr * jitter,
                cy + oy + math.sin(a) * rr * jitter,
            ))
        pygame.draw.polygon(s, shadow, [(x + 1, y + 1) for x, y in pts])
        pygame.draw.polygon(s, main, pts)
        pygame.draw.polygon(s, outline, pts, max(1, size // 20))
    # Red ember in a crevice
    pygame.draw.circle(s, (230, 90, 40),
                       (cx + size // 10, cy + size // 12), max(1, size // 14))


def _draw_glass(s, size, main, hl, shadow, outline) -> None:
    # Translucent pane with diagonal shine
    pad = max(2, size // 8)
    rect = pygame.Rect(pad, pad, size - pad * 2, size - pad * 2)
    pygame.draw.rect(s, shadow, rect.move(1, 1), border_radius=max(1, size // 10))
    pygame.draw.rect(s, main, rect, border_radius=max(1, size // 10))
    pygame.draw.rect(s, (90, 130, 150), rect, max(1, size // 18),
                     border_radius=max(1, size // 10))
    # Big diagonal highlight bar
    pygame.draw.polygon(s, hl, [
        (rect.x + rect.w * 0.15, rect.y + rect.h * 0.25),
        (rect.x + rect.w * 0.45, rect.y + rect.h * 0.10),
        (rect.x + rect.w * 0.60, rect.y + rect.h * 0.45),
        (rect.x + rect.w * 0.30, rect.y + rect.h * 0.60),
    ])
    # Small secondary highlight
    pygame.draw.line(s, (255, 255, 255),
                     (rect.x + rect.w * 0.70, rect.y + rect.h * 0.25),
                     (rect.x + rect.w * 0.85, rect.y + rect.h * 0.50),
                     max(1, size // 16))


def _draw_steel_bar(s, size, main, hl, shadow, outline) -> None:
    # Ingot like iron_bar but with an extra blue-white sheen
    _draw_iron_bar(s, size, main, hl, shadow, outline)
    # Sharper top shine
    pygame.draw.line(
        s, (245, 250, 255),
        (4, size // 2 - size // 5),
        (size - 5, size // 2 - size // 5),
        max(1, size // 22),
    )
    # Cool blue tint dot to signal "steel"
    pygame.draw.circle(
        s, (120, 170, 220),
        (int(size * 0.30), int(size * 0.62)), max(1, size // 14),
    )


def _draw_gears(s, size, main, hl, shadow, outline) -> None:
    # A single gear with teeth + inner hub
    import math
    cx = cy = size // 2
    outer_r = size // 2 - 2
    inner_r = max(2, outer_r - max(2, size // 7))
    teeth = 8
    # Teeth polygon
    pts = []
    for i in range(teeth * 2):
        a = i * math.pi / teeth - math.pi / 2
        rr = outer_r if (i % 2 == 0) else inner_r
        pts.append((cx + math.cos(a) * rr, cy + math.sin(a) * rr))
    pygame.draw.polygon(s, shadow, [(x + 1, y + 1) for x, y in pts])
    pygame.draw.polygon(s, main, pts)
    pygame.draw.polygon(s, outline, pts, max(1, size // 20))
    # Hub
    hub_r = max(2, inner_r - max(2, size // 6))
    pygame.draw.circle(s, hl, (cx, cy), hub_r)
    pygame.draw.circle(s, outline, (cx, cy), hub_r, max(1, size // 22))
    # Bore hole
    pygame.draw.circle(s, shadow, (cx, cy), max(1, hub_r // 2))


def _draw_silicon(s, size, main, hl, shadow, outline) -> None:
    # Dark bluish crystalline wafer with facets
    import math
    cx = cy = size // 2
    r = size // 2 - 3
    # Hexagonal wafer
    pts = []
    for i in range(6):
        a = i * math.tau / 6 + math.pi / 6
        pts.append((cx + math.cos(a) * r, cy + math.sin(a) * r))
    pygame.draw.polygon(s, shadow, [(x + 1, y + 2) for x, y in pts])
    pygame.draw.polygon(s, main, pts)
    pygame.draw.polygon(s, outline, pts, max(1, size // 18))
    # Crystalline facet lines from center to each vertex
    for px, py in pts:
        pygame.draw.line(s, _mul(main, 0.75), (cx, cy), (px, py),
                         max(1, size // 22))
    # Center shiny facet (diamond)
    d = max(2, r // 2)
    pygame.draw.polygon(s, hl, [
        (cx, cy - d), (cx + d, cy), (cx, cy + d), (cx - d, cy),
    ])
    pygame.draw.polygon(s, outline, [
        (cx, cy - d), (cx + d, cy), (cx, cy + d), (cx - d, cy),
    ], max(1, size // 22))


def _draw_circuit(s, size, main, hl, shadow, outline) -> None:
    # Green circuit board with golden traces + contact pads
    pad = max(2, size // 8)
    rect = pygame.Rect(pad, pad, size - pad * 2, size - pad * 2)
    pygame.draw.rect(s, shadow, rect.move(1, 1), border_radius=max(1, size // 14))
    pygame.draw.rect(s, main, rect, border_radius=max(1, size // 14))
    pygame.draw.rect(s, outline, rect, max(1, size // 20),
                     border_radius=max(1, size // 14))
    # Golden traces
    gold = (230, 195, 80)
    # Vertical + horizontal trace
    mid_x = rect.centerx
    mid_y = rect.centery
    pygame.draw.line(s, gold,
                     (rect.x + 3, mid_y), (rect.right - 3, mid_y),
                     max(1, size // 22))
    pygame.draw.line(s, gold,
                     (mid_x, rect.y + 3), (mid_x, rect.bottom - 3),
                     max(1, size // 22))
    # Right-angle trace
    pygame.draw.line(s, gold,
                     (rect.x + max(3, rect.w // 4),
                      rect.y + max(3, rect.h // 4)),
                     (mid_x, rect.y + max(3, rect.h // 4)),
                     max(1, size // 22))
    # Central IC square
    ic_w = max(3, rect.w // 3)
    ic = pygame.Rect(mid_x - ic_w // 2, mid_y - ic_w // 2, ic_w, ic_w)
    pygame.draw.rect(s, (35, 35, 38), ic)
    pygame.draw.rect(s, hl, ic, max(1, size // 24))
    # Contact pad dots
    for px, py in (
        (rect.x + 4, rect.y + 4),
        (rect.right - 4, rect.y + 4),
        (rect.x + 4, rect.bottom - 4),
        (rect.right - 4, rect.bottom - 4),
    ):
        pygame.draw.circle(s, gold, (px, py), max(1, size // 18))


_DRAWERS = {
    Resource.WOOD: _draw_wood,
    Resource.FIBER: _draw_fiber,
    Resource.STONE: _draw_stone,
    Resource.FOOD: _draw_food,
    Resource.IRON: _draw_iron,
    Resource.COPPER: _draw_copper,
    Resource.PLANKS: _draw_planks,
    Resource.IRON_BAR: _draw_iron_bar,
    Resource.COPPER_BAR: _draw_copper_bar,
    Resource.BRICKS: _draw_bricks,
    Resource.COPPER_WIRE: _draw_copper_wire,
    Resource.ROPE: _draw_rope,
    Resource.CHARCOAL: _draw_charcoal,
    Resource.GLASS: _draw_glass,
    Resource.STEEL_BAR: _draw_steel_bar,
    Resource.GEARS: _draw_gears,
    Resource.SILICON: _draw_silicon,
    Resource.CIRCUIT: _draw_circuit,
}
