"""Generate polished PNG sprites for the Hex Colony intro cutscene.

Run once to populate ``assets/sprites/cutscene/`` with the artwork the
cutscene module loads at runtime.  Re-running overwrites existing files.

Usage:
    python tools/generate_cutscene_sprites.py
"""

from __future__ import annotations

import math
import os
import random
import sys
from pathlib import Path

# Headless pygame
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "assets" / "sprites" / "cutscene"
OUT_DIR.mkdir(parents=True, exist_ok=True)


# ── Helpers ──────────────────────────────────────────────────────


def _save(surf: pygame.Surface, name: str) -> None:
    path = OUT_DIR / name
    pygame.image.save(surf, str(path))
    print(f"  wrote {path.relative_to(ROOT)}  "
          f"({surf.get_width()}x{surf.get_height()})")


def _lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def _lerp_col(c1, c2, t):
    return (
        int(_lerp(c1[0], c2[0], t)),
        int(_lerp(c1[1], c2[1], t)),
        int(_lerp(c1[2], c2[2], t)),
    )


def _radial_glow(
    radius: int, inner_col, outer_col, inner_alpha=255, outer_alpha=0,
) -> pygame.Surface:
    """Build an additive radial-gradient glow surface (RGBA)."""
    size = radius * 2
    surf = pygame.Surface((size, size), pygame.SRCALPHA)
    cx = cy = radius
    for r in range(radius, 0, -1):
        t = r / radius
        col = _lerp_col(inner_col, outer_col, t)
        a = int(_lerp(inner_alpha, outer_alpha, t))
        if a <= 0:
            continue
        pygame.draw.circle(surf, (*col, a), (cx, cy), r)
    return surf


# ── Space background ────────────────────────────────────────────


def make_space_bg(w: int = 1920, h: int = 1080) -> pygame.Surface:
    """Cinematic space view: nebula gradient, varied stars, Earth + moon."""
    s = pygame.Surface((w, h), pygame.SRCALPHA)
    rng = random.Random(20240419)

    # Vertical gradient base (deep navy → near-black).
    for y in range(h):
        t = y / h
        col = (
            int(_lerp(8, 4, t)),
            int(_lerp(10, 6, t)),
            int(_lerp(28, 18, t)),
        )
        pygame.draw.line(s, col, (0, y), (w, y))

    # Nebula clouds (large soft alpha-blended blobs).
    nebula_palette = [
        (90, 40, 130), (40, 60, 150), (150, 50, 100),
        (30, 90, 140), (160, 80, 40),
    ]
    for _ in range(22):
        cx = rng.randint(-w // 6, w + w // 6)
        cy = rng.randint(-h // 6, h + h // 6)
        radius = rng.randint(180, 520)
        col = rng.choice(nebula_palette)
        glow = _radial_glow(
            radius, col, col,
            inner_alpha=rng.randint(40, 90), outer_alpha=0,
        )
        s.blit(glow, (cx - radius, cy - radius))

    # Faint diagonal milky-way band.
    band = pygame.Surface((w, h), pygame.SRCALPHA)
    for y in range(h):
        dx = (y - h * 0.45) - (-0.35) * (w * 0.5)
        d = abs(dx) / (h * 0.35)
        a = int(max(0, 40 * (1 - d * d)))
        if a > 0:
            pygame.draw.line(band, (140, 150, 190, a), (0, y), (w, y))
    s.blit(band, (0, 0))

    # Star field with multiple sizes/colours.
    star_colors = [
        (255, 255, 255), (255, 240, 220), (210, 230, 255),
        (255, 220, 180), (220, 200, 255),
    ]
    for _ in range(1400):
        x = rng.randint(0, w - 1)
        y = rng.randint(0, h - 1)
        b = rng.randint(80, 255)
        size = rng.choices([1, 1, 1, 1, 2, 2, 3], k=1)[0]
        col = rng.choice(star_colors)
        col = (min(255, col[0] * b // 255),
               min(255, col[1] * b // 255),
               min(255, col[2] * b // 255))
        if size == 1:
            s.set_at((x, y), (*col, 255))
        else:
            pygame.draw.circle(s, (*col, 255), (x, y), size)

    # Bright featured stars with diffraction spikes.
    for _ in range(22):
        x = rng.randint(40, w - 40)
        y = rng.randint(40, h - 40)
        col = rng.choice(star_colors)
        glow = _radial_glow(14, col, col, inner_alpha=120, outer_alpha=0)
        s.blit(glow, (x - 14, y - 14))
        for dx, dy in ((1, 0), (0, 1)):
            for length in range(1, 14):
                a = int(180 * (1 - length / 14))
                s.set_at(
                    (max(0, min(w - 1, x + dx * length)),
                     max(0, min(h - 1, y + dy * length))),
                    (*col, a),
                )
                s.set_at(
                    (max(0, min(w - 1, x - dx * length)),
                     max(0, min(h - 1, y - dy * length))),
                    (*col, a),
                )
        pygame.draw.circle(s, (255, 255, 255), (x, y), 2)

    # Moon in the upper-left (small, pale).
    mcx, mcy, mr = int(w * 0.18), int(h * 0.22), int(min(w, h) * 0.05)
    s.blit(
        _radial_glow(int(mr * 1.8), (180, 190, 220), (180, 190, 220),
                     inner_alpha=70, outer_alpha=0),
        (mcx - int(mr * 1.8), mcy - int(mr * 1.8)),
    )
    for r in range(mr, 0, -1):
        t = r / mr
        col = _lerp_col((230, 230, 240), (170, 170, 185), t)
        pygame.draw.circle(s, col, (mcx, mcy), r)
    for _ in range(8):
        cr = rng.randint(2, 6)
        ang = rng.uniform(0, math.tau)
        dist = rng.uniform(0, mr - cr - 1)
        cxx = mcx + int(math.cos(ang) * dist)
        cyy = mcy + int(math.sin(ang) * dist)
        pygame.draw.circle(s, (140, 140, 155), (cxx, cyy), cr)
        pygame.draw.circle(s, (210, 210, 220), (cxx - 1, cyy - 1), cr - 1)

    # Earth in the upper-right (the destination).  The cutscene
    # crashes the ship into this point, so keep the position in sync
    # with ``cutscene._EARTH_X_FRAC`` / ``_EARTH_Y_FRAC``.
    ecx, ecy = int(w * 0.80), int(h * 0.30)
    er = int(min(w, h) * 0.24)

    # Atmospheric halo.
    for ring in range(36, 0, -1):
        t = ring / 36
        a = int(120 * (1 - t) ** 1.5)
        col = (90, 160, 230)
        pygame.draw.circle(s, (*col, a), (ecx, ecy), er + ring, 2)

    # Body — radial shading from sunlit edge.
    earth_surf = pygame.Surface((er * 2 + 4, er * 2 + 4), pygame.SRCALPHA)
    eo = er + 2
    for r in range(er, 0, -1):
        t = r / er
        col = _lerp_col((30, 70, 130), (50, 130, 200), 1 - t)
        pygame.draw.circle(earth_surf, col, (eo, eo), r)

    # Continents (free-form blobs with green/tan).
    for _ in range(7):
        ang = rng.uniform(-math.pi, math.pi)
        dist = rng.uniform(0, er * 0.75)
        cxx = eo + int(math.cos(ang) * dist)
        cyy = eo + int(math.sin(ang) * dist)
        rr = rng.randint(er // 8, er // 4)
        col = rng.choice([
            (60, 130, 70), (75, 140, 75), (130, 110, 70), (90, 130, 65),
        ])
        pts = []
        for i in range(14):
            a = i / 14 * math.tau
            pr = rr * (0.7 + 0.5 * rng.random())
            pts.append((cxx + math.cos(a) * pr, cyy + math.sin(a) * pr))
        pygame.draw.polygon(earth_surf, col, pts)

    # Cloud streaks (soft white).
    cloud_layer = pygame.Surface((er * 2 + 4, er * 2 + 4), pygame.SRCALPHA)
    for _ in range(35):
        ang = rng.uniform(-math.pi, math.pi)
        dist = rng.uniform(0, er * 0.85)
        cxx = eo + int(math.cos(ang) * dist)
        cyy = eo + int(math.sin(ang) * dist)
        ww = rng.randint(20, 60)
        hh = rng.randint(4, 10)
        pygame.draw.ellipse(
            cloud_layer, (240, 245, 255, rng.randint(80, 160)),
            (cxx - ww // 2, cyy - hh // 2, ww, hh),
        )
    earth_surf.blit(cloud_layer, (0, 0))

    # Mask to a circle.
    mask = pygame.Surface(earth_surf.get_size(), pygame.SRCALPHA)
    pygame.draw.circle(mask, (255, 255, 255, 255), (eo, eo), er)
    earth_surf.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)

    # Terminator shadow (right side darker — sun coming from upper-left).
    shade = pygame.Surface(earth_surf.get_size(), pygame.SRCALPHA)
    for x in range(earth_surf.get_width()):
        t = x / earth_surf.get_width()
        a = int(max(0, (t - 0.45) * 280))
        if a > 0:
            pygame.draw.line(shade, (0, 0, 30, min(180, a)),
                             (x, 0), (x, earth_surf.get_height()))
    shade.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
    earth_surf.blit(shade, (0, 0))

    # Specular highlight (small spot on the sunlit limb).
    spot_r = int(er * 0.45)
    spot = _radial_glow(spot_r, (255, 255, 240), (255, 255, 240),
                        inner_alpha=110, outer_alpha=0)
    earth_surf.blit(spot, (eo - int(er * 0.55) - spot_r,
                           eo - int(er * 0.55) - spot_r))
    # Re-mask after the highlight.
    mask2 = pygame.Surface(earth_surf.get_size(), pygame.SRCALPHA)
    pygame.draw.circle(mask2, (255, 255, 255, 255), (eo, eo), er)
    earth_surf.blit(mask2, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)

    s.blit(earth_surf, (ecx - eo, ecy - eo))

    return s


# ── Spaceship ────────────────────────────────────────────────────


def _draw_ship_hull(
    s: pygame.Surface, cx: int, cy: int, scale: float = 1.0,
) -> None:
    """Sleek interstellar shuttle facing right."""
    base_dark = (60, 70, 90)
    base = (130, 145, 170)
    base_light = (210, 220, 235)
    hi = (245, 250, 255)
    accent = (210, 80, 60)
    accent_dark = (140, 40, 30)
    cockpit = (60, 130, 200)
    cockpit_hi = (170, 220, 250)
    glow = (255, 220, 120)
    glow_core = (255, 255, 230)

    BW = int(560 * scale)
    BH = int(150 * scale)

    # Ventral fin.
    fin = [
        (cx - BW // 4, cy + BH // 2 - 2),
        (cx - BW // 8, cy + BH),
        (cx + BW // 8, cy + BH),
        (cx + BW // 4, cy + BH // 2 - 2),
    ]
    pygame.draw.polygon(s, base_dark, fin)
    pygame.draw.polygon(s, (40, 50, 65), fin, 2)

    # Lower wing.
    wing_lower = [
        (cx - BW // 6, cy + BH // 6),
        (cx - BW // 2 - 30, cy + BH // 2 + 50),
        (cx - BW // 4, cy + BH // 2 + 60),
        (cx + BW // 6, cy + BH // 2),
    ]
    pygame.draw.polygon(s, base_dark, wing_lower)
    pygame.draw.polygon(s, base, [(x + 2, y - 3) for x, y in wing_lower])
    pygame.draw.polygon(s, (40, 50, 65), wing_lower, 2)

    # Main fuselage.
    body_rect = pygame.Rect(cx - BW // 2, cy - BH // 2, BW, BH)
    pygame.draw.ellipse(s, base_dark, body_rect.inflate(6, 6))
    pygame.draw.ellipse(s, base, body_rect)
    hl = body_rect.copy()
    hl.height = BH // 2 + 4
    hl.y -= 4
    pygame.draw.ellipse(s, base_light, hl)
    hl2 = hl.copy()
    hl2.height = BH // 4
    hl2.y += 2
    hl2.width -= 80
    hl2.x += 40
    pygame.draw.ellipse(s, hi, hl2)

    # Belly shadow.
    bs = body_rect.copy()
    bs.height = BH // 3
    bs.y = body_rect.bottom - bs.height
    bs.width -= 40
    bs.x += 20
    bs_surf = pygame.Surface(bs.size, pygame.SRCALPHA)
    pygame.draw.ellipse(bs_surf, (20, 25, 40, 90), bs_surf.get_rect())
    s.blit(bs_surf, bs.topleft)

    # Panel seams.
    seam_col = (60, 75, 95)
    for i in range(1, 6):
        x = cx - BW // 2 + BW * i // 7
        pygame.draw.line(s, seam_col,
                         (x, cy - BH // 3), (x, cy + BH // 3 - 4), 1)

    # Hull stripe.
    stripe_y = cy + 6
    pygame.draw.line(s, accent,
                     (cx - BW // 2 + 60, stripe_y),
                     (cx + BW // 2 - 80, stripe_y), 4)
    pygame.draw.line(s, accent_dark,
                     (cx - BW // 2 + 60, stripe_y + 3),
                     (cx + BW // 2 - 80, stripe_y + 3), 1)

    # Window strip.
    win_y = cy - 14
    win_h = int(18 * scale)
    win_w = int(22 * scale)
    win_gap = int(12 * scale)
    n_windows = 8
    total_w = n_windows * win_w + (n_windows - 1) * win_gap
    start_x = cx - total_w // 2 - int(40 * scale)
    for i in range(n_windows):
        wx = start_x + i * (win_w + win_gap)
        pygame.draw.rect(s, base_dark,
                         (wx - 1, win_y - 1, win_w + 2, win_h + 2),
                         border_radius=3)
        pygame.draw.rect(s, (110, 200, 240),
                         (wx, win_y, win_w, win_h),
                         border_radius=3)
        pygame.draw.rect(s, (220, 240, 255),
                         (wx + 2, win_y + 2, win_w // 2, win_h // 2),
                         border_radius=2)

    # Cockpit dome on the nose (right side).
    nose_x = cx + BW // 2 - int(60 * scale)
    nose_r = int(48 * scale)
    pygame.draw.circle(s, base_dark, (nose_x + 1, cy - 4), nose_r + 2)
    pygame.draw.circle(s, cockpit, (nose_x, cy - 4), nose_r)
    for r in range(nose_r - 2, 0, -2):
        t = r / nose_r
        col = _lerp_col((40, 80, 150), (180, 220, 250), 1 - t)
        pygame.draw.circle(s, col, (nose_x, cy - 4), r)
    pygame.draw.circle(s, cockpit_hi,
                       (nose_x - nose_r // 3, cy - 4 - nose_r // 3),
                       nose_r // 3)
    pygame.draw.circle(s, (255, 255, 255),
                       (nose_x - nose_r // 2, cy - 4 - nose_r // 2),
                       max(2, nose_r // 8))
    pygame.draw.arc(
        s, base_dark,
        (nose_x - nose_r, cy - 4 - nose_r, nose_r * 2, nose_r * 2),
        math.radians(-30), math.radians(210), 3,
    )

    # Nose tip antenna.
    pygame.draw.line(s, base_dark,
                     (cx + BW // 2 - 8, cy - 6),
                     (cx + BW // 2 + 18, cy - 12), 2)
    pygame.draw.circle(s, accent, (cx + BW // 2 + 18, cy - 12), 3)

    # Upper wing.
    wing_upper = [
        (cx - BW // 6, cy - BH // 6),
        (cx - BW // 2 - 20, cy - BH // 2 - 60),
        (cx - BW // 4, cy - BH // 2 - 70),
        (cx + BW // 6, cy - BH // 6 - 6),
    ]
    pygame.draw.polygon(s, base_dark, wing_upper)
    pygame.draw.polygon(s, base, [(x + 2, y + 3) for x, y in wing_upper])
    pygame.draw.circle(s, accent,
                       (cx - BW // 2 - 18, cy - BH // 2 - 56), 4)
    pygame.draw.line(s, base_dark,
                     (cx - BW // 4, cy - BH // 4 - 18),
                     (cx, cy - BH // 6 - 4), 1)

    # Engine block at the tail.
    eng_w = int(110 * scale)
    eng_h = int(150 * scale)
    eng_x = cx - BW // 2 - eng_w + 50
    eng_rect = pygame.Rect(eng_x, cy - eng_h // 2, eng_w, eng_h)
    pygame.draw.rect(s, base_dark, eng_rect, border_radius=14)
    inner = eng_rect.inflate(-12, -16)
    pygame.draw.rect(s, base, inner, border_radius=12)
    pygame.draw.rect(s, base_light,
                     (inner.x + 4, inner.y + 4,
                      inner.width - 8, inner.height // 3),
                     border_radius=8)
    for oy in (-eng_h // 3, 0, eng_h // 3):
        nx = eng_rect.left - 4
        pygame.draw.circle(s, (30, 30, 40), (nx, cy + oy), int(20 * scale))
        pygame.draw.circle(s, (60, 60, 75),
                           (nx, cy + oy), int(20 * scale), 2)
        gr = int(28 * scale)
        plume = _radial_glow(gr, glow_core, glow,
                             inner_alpha=255, outer_alpha=0)
        s.blit(plume, (nx - gr - 4, cy + oy - gr),
               special_flags=pygame.BLEND_RGBA_ADD)
        pygame.draw.circle(s, glow, (nx - 6, cy + oy), int(10 * scale))
        pygame.draw.circle(s, glow_core, (nx - 8, cy + oy), int(5 * scale))


def make_ship(w: int = 800, h: int = 420) -> pygame.Surface:
    s = pygame.Surface((w, h), pygame.SRCALPHA)
    _draw_ship_hull(s, w // 2, h // 2, scale=1.0)
    return s


def make_ship_damaged(w: int = 800, h: int = 420) -> pygame.Surface:
    s = pygame.Surface((w, h), pygame.SRCALPHA)
    _draw_ship_hull(s, w // 2, h // 2, scale=1.0)
    rng = random.Random(7)
    cx, cy = w // 2, h // 2

    # Soot trails (drawn under the flames).
    for _ in range(80):
        sx = cx + rng.randint(-100, 80)
        sy = cy - 90 - rng.randint(0, 110)
        a = rng.randint(80, 170)
        rr = rng.randint(14, 32)
        pygame.draw.circle(s, (35, 30, 35, a), (sx, sy), rr)

    # Hull breach.
    breach_pts = [
        (cx - 90, cy - 50), (cx - 50, cy - 78), (cx - 10, cy - 60),
        (cx + 30, cy - 80), (cx + 80, cy - 58), (cx + 110, cy - 38),
        (cx + 70, cy - 24), (cx + 30, cy - 32), (cx - 10, cy - 20),
        (cx - 50, cy - 28), (cx - 90, cy - 18),
    ]
    pygame.draw.polygon(s, (15, 12, 12), breach_pts)
    pygame.draw.polygon(s, (140, 60, 30), breach_pts, 3)
    pygame.draw.polygon(s, (255, 140, 60),
                        [(x, y + 2) for x, y in breach_pts[:6]], 2)

    # Layered flames.
    flame_colors = [
        (255, 60, 20, 220), (255, 130, 30, 210),
        (255, 200, 80, 200), (255, 240, 160, 180),
    ]
    for layer_idx, col in enumerate(flame_colors):
        for _ in range(40 - layer_idx * 6):
            fx = cx + rng.randint(-90, 110)
            fy = cy - 50 + rng.randint(-70 - layer_idx * 8, -10)
            rr = rng.randint(8, 20 + layer_idx * 2)
            glow = _radial_glow(rr, col[:3], col[:3],
                                inner_alpha=col[3], outer_alpha=0)
            s.blit(glow, (fx - rr, fy - rr),
                   special_flags=pygame.BLEND_RGBA_ADD)
    for _ in range(30):
        fx = cx + rng.randint(-70, 90)
        fy = cy - 40 + rng.randint(-50, 0)
        pygame.draw.circle(s, (255, 230, 180), (fx, fy),
                           rng.randint(2, 5))

    # Sparks/embers.
    for _ in range(60):
        sx = cx + rng.randint(-100, 100)
        sy = cy - 90 - rng.randint(0, 80)
        col = rng.choice([(255, 230, 140), (255, 180, 80), (255, 100, 40)])
        pygame.draw.circle(s, col, (sx, sy), rng.randint(1, 3))

    # Debris.
    for _ in range(8):
        dx = cx + rng.randint(-80, 90)
        dy = cy - 70 - rng.randint(0, 50)
        sz = rng.randint(3, 7)
        pygame.draw.rect(s, (90, 95, 110), (dx, dy, sz, sz))

    return s


# ── Portraits ────────────────────────────────────────────────────


def _portrait_canvas(w: int, h: int, accent_a, accent_b) -> pygame.Surface:
    s = pygame.Surface((w, h), pygame.SRCALPHA)
    cx, cy = w // 2, h // 2
    R = int(min(w, h) * 0.48)
    for r in range(R, 0, -1):
        t = r / R
        col = _lerp_col(accent_a, accent_b, t)
        a = int(255 * (1 - t * 0.15))
        pygame.draw.circle(s, (*col, a), (cx, cy), r)
    pygame.draw.circle(s, (255, 255, 255, 60), (cx, cy), R, 2)
    return s


def _draw_face(
    s: pygame.Surface, cx: int, cy: int, head_r: int, *,
    skin, skin_shadow, skin_hi, eye_col,
    hair_col, hair_shadow,
    expression: str = "neutral", hair_style: str = "short",
) -> None:
    """Stylised face — shared base for all portraits."""

    # Neck.
    neck = pygame.Rect(cx - int(head_r * 0.32), cy + int(head_r * 0.55),
                       int(head_r * 0.64), int(head_r * 0.6))
    pygame.draw.ellipse(s, skin_shadow, neck.inflate(4, 0))
    pygame.draw.ellipse(s, skin, neck)

    # Head.
    head_rect = pygame.Rect(cx - head_r, cy - int(head_r * 1.05),
                            head_r * 2, int(head_r * 2.05))
    pygame.draw.ellipse(s, skin_shadow, head_rect.inflate(6, 6))
    pygame.draw.ellipse(s, skin, head_rect)
    hl_rect = head_rect.copy()
    hl_rect.width = int(head_rect.width * 0.55)
    hl_rect.x = head_rect.x + int(head_r * 0.1)
    hl_rect.y = head_rect.y + int(head_r * 0.2)
    hl_rect.height = int(head_rect.height * 0.6)
    hl_surf = pygame.Surface(hl_rect.size, pygame.SRCALPHA)
    pygame.draw.ellipse(hl_surf, (*skin_hi, 90), hl_surf.get_rect())
    s.blit(hl_surf, hl_rect.topleft)

    # Hair.
    if hair_style == "short":
        hair_top = pygame.Rect(cx - head_r - 4, cy - int(head_r * 1.25),
                               head_r * 2 + 8, int(head_r * 1.0))
        pygame.draw.ellipse(s, hair_shadow, hair_top.inflate(6, 6))
        pygame.draw.ellipse(s, hair_col, hair_top)
        bang_pts = [
            (cx - head_r + 4, cy - int(head_r * 0.4)),
            (cx - int(head_r * 0.2), cy - int(head_r * 0.95)),
            (cx + int(head_r * 0.6), cy - int(head_r * 0.7)),
            (cx + head_r - 4, cy - int(head_r * 0.3)),
            (cx + int(head_r * 0.4), cy - int(head_r * 0.55)),
            (cx - int(head_r * 0.3), cy - int(head_r * 0.6)),
        ]
        pygame.draw.polygon(s, hair_col, bang_pts)
        pygame.draw.polygon(s, hair_shadow, bang_pts, 2)
    else:
        hair_top = pygame.Rect(cx - head_r - 6, cy - int(head_r * 1.35),
                               head_r * 2 + 12, int(head_r * 1.1))
        pygame.draw.ellipse(s, hair_shadow, hair_top.inflate(6, 6))
        pygame.draw.ellipse(s, hair_col, hair_top)
        sweep_pts = [
            (cx - head_r + 2, cy - int(head_r * 0.6)),
            (cx + int(head_r * 0.1), cy - int(head_r * 1.05)),
            (cx + int(head_r * 0.95), cy - int(head_r * 0.95)),
            (cx + head_r + 4, cy - int(head_r * 0.5)),
            (cx + int(head_r * 0.6), cy - int(head_r * 0.45)),
            (cx + int(head_r * 0.05), cy - int(head_r * 0.55)),
        ]
        pygame.draw.polygon(s, hair_col, sweep_pts)
        pygame.draw.polygon(s, hair_shadow, sweep_pts, 2)

    # Ears.
    ear_y = cy - int(head_r * 0.05)
    pygame.draw.ellipse(s, skin_shadow, (cx - head_r - 4, ear_y - 8, 12, 24))
    pygame.draw.ellipse(s, skin, (cx - head_r - 2, ear_y - 6, 8, 20))
    pygame.draw.ellipse(s, skin_shadow, (cx + head_r - 8, ear_y - 8, 12, 24))
    pygame.draw.ellipse(s, skin, (cx + head_r - 6, ear_y - 6, 8, 20))

    # Eyes.
    eye_y = cy - int(head_r * 0.05)
    eye_dx = int(head_r * 0.38)
    eye_w = int(head_r * 0.32)
    eye_h = int(head_r * 0.22)
    iris_r = int(head_r * 0.10)
    for sign in (-1, 1):
        ex = cx + sign * eye_dx
        pygame.draw.ellipse(
            s, skin_shadow,
            (ex - eye_w // 2 - 2, eye_y - eye_h // 2 - 4,
             eye_w + 4, eye_h + 8),
        )
        pygame.draw.ellipse(
            s, (250, 250, 250),
            (ex - eye_w // 2, eye_y - eye_h // 2, eye_w, eye_h),
        )
        pygame.draw.circle(s, eye_col, (ex, eye_y + 1), iris_r)
        pygame.draw.circle(s, (15, 15, 25), (ex, eye_y + 1),
                           max(2, iris_r // 2))
        pygame.draw.circle(s, (255, 255, 255),
                           (ex - 2, eye_y - 2),
                           max(1, iris_r // 3))
        pygame.draw.arc(
            s, (40, 30, 30),
            (ex - eye_w // 2, eye_y - eye_h // 2 - 1, eye_w, eye_h),
            math.radians(20), math.radians(160), 2,
        )
        brow_y = eye_y - int(head_r * 0.28)
        brow_pts = [
            (ex - int(eye_w * 0.6), brow_y + 3),
            (ex - int(eye_w * 0.2), brow_y - 2),
            (ex + int(eye_w * 0.5), brow_y),
            (ex + int(eye_w * 0.6), brow_y + 3),
        ]
        pygame.draw.lines(s, hair_col, False, brow_pts, 3)

    # Nose.
    nose_top = (cx, eye_y + int(head_r * 0.15))
    nose_bot = (cx - 2, eye_y + int(head_r * 0.55))
    pygame.draw.line(s, skin_shadow, nose_top, nose_bot, 2)
    pygame.draw.circle(s, skin_shadow,
                       (cx + 2, eye_y + int(head_r * 0.55)), 1)

    # Mouth.
    mouth_y = cy + int(head_r * 0.42)
    if expression == "smirk":
        pygame.draw.line(s, (130, 60, 60),
                         (cx - 14, mouth_y), (cx + 16, mouth_y - 2), 3)
        pygame.draw.line(s, (190, 110, 100),
                         (cx - 14, mouth_y + 2), (cx + 16, mouth_y), 1)
    elif expression == "open":
        pygame.draw.ellipse(s, (110, 50, 60),
                            (cx - 14, mouth_y - 4, 28, 14))
        pygame.draw.ellipse(s, (200, 120, 110),
                            (cx - 14, mouth_y - 2, 28, 8))
    else:
        pygame.draw.arc(
            s, (130, 60, 60),
            (cx - 16, mouth_y - 8, 32, 18),
            math.pi, 2 * math.pi, 3,
        )
    pygame.draw.arc(
        s, skin_shadow,
        (cx - int(head_r * 0.4), cy + int(head_r * 0.45),
         int(head_r * 0.8), int(head_r * 0.5)),
        math.radians(200), math.radians(340), 2,
    )


def make_captain(w: int = 360, h: int = 360) -> pygame.Surface:
    """Captain — navy uniform, gold trim, peaked cap."""
    s = _portrait_canvas(w, h, (60, 80, 120), (15, 20, 40))
    cx, cy = w // 2, h // 2 + 8
    head_r = int(min(w, h) * 0.21)

    # Uniform.
    coat = [
        (cx - int(head_r * 2.2), h),
        (cx - int(head_r * 1.6), cy + int(head_r * 0.7)),
        (cx - int(head_r * 0.5), cy + int(head_r * 1.0)),
        (cx + int(head_r * 0.5), cy + int(head_r * 1.0)),
        (cx + int(head_r * 1.6), cy + int(head_r * 0.7)),
        (cx + int(head_r * 2.2), h),
    ]
    pygame.draw.polygon(s, (15, 22, 50), coat)
    pygame.draw.polygon(s, (35, 50, 95),
                        [(x, y - 3) if y < h else (x, y) for x, y in coat])
    lapel_l = [
        (cx - int(head_r * 1.55), cy + int(head_r * 0.75)),
        (cx - int(head_r * 0.1), cy + int(head_r * 1.4)),
        (cx - int(head_r * 0.45), cy + int(head_r * 1.05)),
        (cx - int(head_r * 1.2), cy + int(head_r * 0.65)),
    ]
    lapel_r = [(2 * cx - x, y) for x, y in lapel_l]
    pygame.draw.polygon(s, (10, 14, 30), lapel_l)
    pygame.draw.polygon(s, (10, 14, 30), lapel_r)
    pygame.draw.polygon(s, (210, 175, 60), lapel_l, 2)
    pygame.draw.polygon(s, (210, 175, 60), lapel_r, 2)
    for by in (cy + int(head_r * 1.2), cy + int(head_r * 1.6)):
        pygame.draw.circle(s, (210, 175, 60), (cx, by), 5)
        pygame.draw.circle(s, (255, 230, 130), (cx - 1, by - 1), 2)
    for sign in (-1, 1):
        x = cx + sign * int(head_r * 1.5)
        y = cy + int(head_r * 0.85)
        pygame.draw.rect(s, (180, 145, 50), (x - 18, y - 5, 36, 10),
                         border_radius=3)
        pygame.draw.rect(s, (255, 220, 110), (x - 16, y - 3, 32, 4),
                         border_radius=2)
        for j in range(3):
            pygame.draw.line(s, (90, 60, 20),
                             (x - 12 + j * 8, y + 2),
                             (x - 8 + j * 8, y + 6), 2)

    # Face.
    _draw_face(
        s, cx, cy, head_r,
        skin=(225, 195, 165), skin_shadow=(170, 135, 105),
        skin_hi=(255, 230, 200),
        eye_col=(60, 110, 170),
        hair_col=(50, 35, 25), hair_shadow=(25, 18, 12),
        expression="smirk", hair_style="short",
    )

    # Captain's peaked cap.
    cap_brim_w = int(head_r * 2.4)
    cap_y = cy - int(head_r * 1.2)
    pygame.draw.ellipse(
        s, (15, 22, 50),
        (cx - cap_brim_w // 2, cap_y + int(head_r * 0.05),
         cap_brim_w, int(head_r * 0.45)),
    )
    cap_body = pygame.Rect(
        cx - int(head_r * 1.05), cap_y - int(head_r * 0.5),
        int(head_r * 2.1), int(head_r * 0.65),
    )
    pygame.draw.ellipse(s, (15, 22, 50), cap_body)
    pygame.draw.ellipse(
        s, (50, 65, 105),
        (cap_body.x + 6, cap_body.y + 3,
         cap_body.width - 12, cap_body.height // 2),
    )
    band_y = cap_y + int(head_r * 0.06)
    pygame.draw.rect(s, (180, 145, 50),
                     (cx - cap_brim_w // 2 + 6, band_y, cap_brim_w - 12, 8))
    pygame.draw.line(s, (255, 230, 130),
                     (cx - cap_brim_w // 2 + 6, band_y + 1),
                     (cx + cap_brim_w // 2 - 6, band_y + 1), 2)
    em_y = cap_y - int(head_r * 0.15)
    pygame.draw.circle(s, (210, 175, 60), (cx, em_y), 9)
    pygame.draw.circle(s, (255, 230, 130), (cx, em_y), 9, 2)
    star_pts = []
    for i in range(10):
        a = -math.pi / 2 + i * math.pi / 5
        rr = 8 if i % 2 == 0 else 3
        star_pts.append((cx + math.cos(a) * rr, em_y + math.sin(a) * rr))
    pygame.draw.polygon(s, (90, 60, 20), star_pts)

    return s


def make_scientist(w: int = 360, h: int = 360) -> pygame.Surface:
    """Scientist — white lab coat, glasses, swept hair."""
    s = _portrait_canvas(w, h, (80, 130, 140), (15, 30, 40))
    cx, cy = w // 2, h // 2 + 8
    head_r = int(min(w, h) * 0.21)

    # Teal undershirt.
    under = [
        (cx - int(head_r * 2.2), h),
        (cx - int(head_r * 1.8), cy + int(head_r * 0.7)),
        (cx, cy + int(head_r * 1.4)),
        (cx + int(head_r * 1.8), cy + int(head_r * 0.7)),
        (cx + int(head_r * 2.2), h),
    ]
    pygame.draw.polygon(s, (40, 110, 130), under)
    # Lab coat.
    coat_l = [
        (cx - int(head_r * 2.4), h),
        (cx - int(head_r * 1.8), cy + int(head_r * 0.75)),
        (cx - int(head_r * 0.3), cy + int(head_r * 1.45)),
        (cx - int(head_r * 0.05), h),
    ]
    coat_r = [(2 * cx - x, y) for x, y in coat_l]
    pygame.draw.polygon(s, (240, 245, 250), coat_l)
    pygame.draw.polygon(s, (240, 245, 250), coat_r)
    pygame.draw.polygon(s, (200, 210, 220), coat_l, 2)
    pygame.draw.polygon(s, (200, 210, 220), coat_r, 2)
    shade = pygame.Surface((w, h), pygame.SRCALPHA)
    pygame.draw.polygon(
        shade, (180, 195, 205, 90),
        [(cx - int(head_r * 1.7), cy + int(head_r * 0.95)),
         (cx, cy + int(head_r * 1.5)),
         (cx + int(head_r * 1.7), cy + int(head_r * 0.95)),
         (cx + int(head_r * 1.6), cy + int(head_r * 1.1)),
         (cx, cy + int(head_r * 1.7)),
         (cx - int(head_r * 1.6), cy + int(head_r * 1.1))],
    )
    s.blit(shade, (0, 0))
    pygame.draw.rect(s, (60, 100, 160),
                     (cx - int(head_r * 1.4), cy + int(head_r * 1.55),
                      6, int(head_r * 0.45)))
    pygame.draw.rect(s, (220, 220, 60),
                     (cx - int(head_r * 1.4), cy + int(head_r * 1.55), 6, 6))
    pygame.draw.line(
        s, (200, 210, 220),
        (cx - int(head_r * 1.7), cy + int(head_r * 1.55)),
        (cx - int(head_r * 1.05), cy + int(head_r * 1.55)), 2,
    )
    pygame.draw.line(
        s, (200, 210, 220),
        (cx + int(head_r * 1.05), cy + int(head_r * 1.55)),
        (cx + int(head_r * 1.7), cy + int(head_r * 1.55)), 2,
    )

    # Face.
    _draw_face(
        s, cx, cy, head_r,
        skin=(235, 205, 175), skin_shadow=(180, 145, 115),
        skin_hi=(255, 235, 210),
        eye_col=(80, 140, 95),
        hair_col=(180, 130, 60), hair_shadow=(110, 75, 30),
        expression="neutral", hair_style="swept",
    )

    # Round glasses.
    eye_y = cy - int(head_r * 0.05)
    eye_dx = int(head_r * 0.38)
    glass_r = int(head_r * 0.26)
    for sign in (-1, 1):
        ex = cx + sign * eye_dx
        glass = pygame.Surface((glass_r * 2 + 4, glass_r * 2 + 4),
                               pygame.SRCALPHA)
        pygame.draw.circle(glass, (200, 230, 255, 35),
                           (glass_r + 2, glass_r + 2), glass_r)
        s.blit(glass, (ex - glass_r - 2, eye_y - glass_r - 2))
        pygame.draw.circle(s, (40, 40, 50), (ex, eye_y), glass_r, 3)
        pygame.draw.line(
            s, (255, 255, 255),
            (ex - glass_r // 2, eye_y - glass_r // 2 + 2),
            (ex + glass_r // 4, eye_y - glass_r // 4 + 2), 2,
        )
    pygame.draw.line(
        s, (40, 40, 50),
        (cx - eye_dx + glass_r, eye_y),
        (cx + eye_dx - glass_r, eye_y), 3,
    )

    return s


# ── Click icon ───────────────────────────────────────────────────


def make_click_icon(w: int = 96, h: int = 120) -> pygame.Surface:
    """Polished mouse pointer with drop shadow + click ripple."""
    s = pygame.Surface((w, h), pygame.SRCALPHA)
    body_col = (245, 248, 255)
    body_shadow = (170, 180, 200)
    outline = (40, 45, 60)
    btn_col = (220, 80, 80)
    btn_hi = (255, 160, 160)

    cx = w // 2
    body_top = 26
    body_bot = h - 12
    body_w = 50

    sh = pygame.Surface((w, h), pygame.SRCALPHA)
    pygame.draw.ellipse(
        sh, (0, 0, 0, 90),
        (cx - body_w // 2 + 3, body_top + 6,
         body_w, body_bot - body_top),
    )
    s.blit(sh, (0, 0))

    body = pygame.Rect(cx - body_w // 2, body_top, body_w,
                       body_bot - body_top)
    pygame.draw.rect(s, body_shadow, body.inflate(2, 2), border_radius=22)
    pygame.draw.rect(s, body_col, body, border_radius=22)

    pygame.draw.line(s, (255, 255, 255),
                     (body.left + 6, body.top + 14),
                     (body.left + 6, body.bottom - 18), 2)

    pygame.draw.rect(s, outline, body, 3, border_radius=22)
    mid_y = body.top + (body.height // 2) - 6
    pygame.draw.line(s, outline, (body.left, mid_y),
                     (body.right, mid_y), 2)
    pygame.draw.line(s, outline, (cx, body.top + 4), (cx, mid_y), 2)

    left_btn = pygame.Rect(body.left + 4, body.top + 4,
                           body_w // 2 - 4, mid_y - body.top - 4)
    pygame.draw.rect(s, btn_col, left_btn,
                     border_top_left_radius=18,
                     border_bottom_left_radius=4)
    pygame.draw.rect(s, btn_hi,
                     (left_btn.left + 3, left_btn.top + 3,
                      left_btn.width // 2, 6),
                     border_radius=3)

    pygame.draw.rect(s, (180, 185, 200),
                     (cx - 3, body.top + 8, 6, 12),
                     border_radius=3)
    pygame.draw.rect(s, outline,
                     (cx - 3, body.top + 8, 6, 12), 1, border_radius=3)

    for i, r in enumerate((10, 16, 22)):
        a = 220 - i * 60
        pygame.draw.arc(
            s, (*btn_col, a),
            (cx - r, body_top - r - 4, r * 2, r * 2),
            math.radians(200), math.radians(340), 3,
        )

    return s


# ── Entry point ──────────────────────────────────────────────────


def main() -> int:
    pygame.init()
    pygame.display.set_mode((1, 1))
    print(f"Generating cutscene sprites in {OUT_DIR}")
    _save(make_space_bg(), "space_bg.png")
    _save(make_ship(), "ship.png")
    _save(make_ship_damaged(), "ship_damaged.png")
    _save(make_captain(), "captain.png")
    _save(make_scientist(), "scientist.png")
    _save(make_click_icon(), "click_icon.png")
    print("Done.")
    pygame.quit()
    return 0


if __name__ == "__main__":
    sys.exit(main())
