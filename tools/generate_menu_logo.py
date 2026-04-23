"""Generate the Hex Colony menu logo sprite.

Writes ``assets/sprites/ui/menu_logo.png``. Re-run this script to
regenerate the logo from code, or simply replace the PNG with a
hand-painted version of the same dimensions.

Run from the repo root::

    python tools/generate_menu_logo.py
"""

from __future__ import annotations

import math
import os
from pathlib import Path

# Headless pygame for CI / build machines without a display.
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame

REPO_ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = REPO_ROOT / "assets" / "sprites" / "ui"
OUT_PATH = OUT_DIR / "menu_logo.png"

# Logo canvas size. The menu scales this down to fit, so render large
# for a crisp result on hi-dpi displays.
W, H = 720, 360

# Palette (matches the menu's gold-on-navy theme).
NAVY_DARK = (10, 16, 34)
NAVY = (18, 28, 56)
NAVY_HIGH = (40, 60, 100)
GOLD = (220, 176, 70)
GOLD_BRIGHT = (255, 220, 110)
GOLD_DEEP = (160, 110, 30)
WHITE = (245, 248, 255)
SHADOW = (0, 0, 0)


def _hex_points(cx: float, cy: float, size: float, *, pointy: bool = True) -> list[tuple[int, int]]:
    pts = []
    for i in range(6):
        if pointy:
            ang = math.radians(60 * i - 30)
        else:
            ang = math.radians(60 * i)
        pts.append((int(cx + size * math.cos(ang)), int(cy + size * math.sin(ang))))
    return pts


def _draw_emblem(surface: pygame.Surface, center: tuple[int, int], size: int) -> None:
    """Draw a stylised hex emblem (concentric hexes + central rune)."""
    cx, cy = center

    # Soft outer glow
    for i in range(18, 0, -2):
        alpha = max(0, 60 - i * 3)
        glow = pygame.Surface((size * 4, size * 4), pygame.SRCALPHA)
        pygame.draw.polygon(
            glow,
            (*GOLD_BRIGHT, alpha),
            _hex_points(size * 2, size * 2, size + i * 2),
        )
        surface.blit(glow, (cx - size * 2, cy - size * 2))

    # Outer hex shell — gold ring
    pygame.draw.polygon(surface, GOLD_DEEP, _hex_points(cx, cy, size + 8))
    pygame.draw.polygon(surface, GOLD, _hex_points(cx, cy, size + 4))

    # Inner navy face
    pygame.draw.polygon(surface, NAVY, _hex_points(cx, cy, size - 2))
    pygame.draw.polygon(surface, NAVY_HIGH, _hex_points(cx, cy, size - 2), 2)

    # Three petal hexes inside (mini honeycomb)
    inner_r = size // 3
    offset = int(inner_r * 1.6)
    petal_centers = [
        (cx, cy - offset),
        (cx - int(offset * math.cos(math.radians(30))), cy + int(offset * math.sin(math.radians(30)))),
        (cx + int(offset * math.cos(math.radians(30))), cy + int(offset * math.sin(math.radians(30)))),
    ]
    petal_colors = [
        (90, 160, 80),   # green / grass
        (120, 110, 95),  # stone
        (60, 110, 180),  # water
    ]
    for (px, py), col in zip(petal_centers, petal_colors):
        pygame.draw.polygon(surface, col, _hex_points(px, py, inner_r))
        pygame.draw.polygon(surface, GOLD_BRIGHT, _hex_points(px, py, inner_r), 1)

    # Central tiny gold hex
    pygame.draw.polygon(surface, GOLD_BRIGHT, _hex_points(cx, cy, inner_r // 2))
    pygame.draw.polygon(surface, GOLD_DEEP, _hex_points(cx, cy, inner_r // 2), 1)


def _draw_text(
    surface: pygame.Surface,
    text: str,
    font: pygame.font.Font,
    center: tuple[int, int],
    *,
    fill: tuple[int, int, int],
    shadow: tuple[int, int, int] | None = SHADOW,
    outline: tuple[int, int, int] | None = None,
) -> None:
    cx, cy = center
    if outline:
        ow = 3
        out_surf = font.render(text, True, outline)
        for dx in range(-ow, ow + 1):
            for dy in range(-ow, ow + 1):
                if dx == 0 and dy == 0:
                    continue
                surface.blit(
                    out_surf,
                    (cx - out_surf.get_width() // 2 + dx, cy - out_surf.get_height() // 2 + dy),
                )
    if shadow:
        sh = font.render(text, True, shadow)
        sh.set_alpha(180)
        surface.blit(sh, (cx - sh.get_width() // 2 + 4, cy - sh.get_height() // 2 + 5))
    main = font.render(text, True, fill)
    surface.blit(main, (cx - main.get_width() // 2, cy - main.get_height() // 2))


def render_logo() -> pygame.Surface:
    pygame.init()
    surf = pygame.Surface((W, H), pygame.SRCALPHA)

    # Emblem on the left, text on the right.
    emblem_center = (140, H // 2)
    emblem_size = 110
    _draw_emblem(surf, emblem_center, emblem_size)

    # Text block
    title_font = pygame.font.Font(None, 168)
    sub_font = pygame.font.Font(None, 44)

    text_left = 270
    text_right = W - 24
    text_cx = (text_left + text_right) // 2

    _draw_text(
        surf,
        "HEX",
        title_font,
        (text_cx, H // 2 - 56),
        fill=GOLD_BRIGHT,
        outline=NAVY_DARK,
    )
    _draw_text(
        surf,
        "COLONY",
        title_font,
        (text_cx, H // 2 + 56),
        fill=WHITE,
        outline=NAVY_DARK,
    )

    # Subtitle ribbon between the two words
    ribbon_y = H // 2
    rib_left = text_left + 20
    rib_right = text_right - 20
    pygame.draw.line(surf, GOLD, (rib_left, ribbon_y), (rib_right, ribbon_y), 3)
    for x in (rib_left, rib_right):
        pygame.draw.polygon(
            surf,
            GOLD_BRIGHT,
            [(x, ribbon_y - 6), (x + (6 if x == rib_left else -6), ribbon_y),
             (x, ribbon_y + 6)],
        )

    return surf


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    surf = render_logo()
    pygame.image.save(surf, str(OUT_PATH))
    print(f"Wrote {OUT_PATH}  ({W}x{H})")


if __name__ == "__main__":
    main()
