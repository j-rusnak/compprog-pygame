"""Menu screen for Hex Colony — title, seed entry, map-size slider, and play button.

The menu is fully animated: a procedural hex-tile field drifts behind a
translucent card that hosts the form. The look mirrors the in-game
terrain palette so the menu feels continuous with the world.
"""

from __future__ import annotations

import math
import random
import string
from dataclasses import dataclass

import pygame

from compprog_pygame.settings import ASSET_DIR
from compprog_pygame.games.hex_colony.settings import Difficulty, HexColonySettings
from compprog_pygame.games.hex_colony.strings import (
    MENU_TITLE,
    MENU_SUBTITLE,
    MENU_SEED_LABEL,
    MENU_SEED_PLACEHOLDER,
    MENU_MAP_SIZE_LABEL,
    MENU_DIFFICULTY_LABEL,
    MENU_DIFFICULTY_EASY,
    MENU_DIFFICULTY_HARD,
    MENU_DIFFICULTY_DESOLATION,
    MENU_DIFFICULTY_EASY_DESC,
    MENU_DIFFICULTY_HARD_DESC,
    MENU_DIFFICULTY_DESOLATION_DESC,
    MENU_PLAY_BUTTON,
    MENU_HINT,
)

# ── Colours ──────────────────────────────────────────────────────

BACKGROUND_TOP = (6, 9, 22)
BACKGROUND_BOT = (14, 22, 44)
TITLE_COLOR = (245, 248, 255)
TITLE_GLOW = (255, 198, 92)
ACCENT = (220, 176, 70)
ACCENT_BRIGHT = (255, 220, 110)
TEXT_COLOR = (242, 244, 255)
MUTED_TEXT = (150, 160, 185)
CARD_BG = (14, 20, 38, 225)
CARD_BORDER = (70, 90, 130)
CARD_BORDER_HI = (110, 140, 190)
INPUT_BG = (10, 16, 32)
INPUT_BORDER = (60, 75, 105)
INPUT_ACTIVE_BORDER = ACCENT_BRIGHT
BUTTON_BG = (30, 50, 90)
BUTTON_HOVER = (55, 82, 140)
BUTTON_ACTIVE = (75, 110, 175)
BUTTON_TEXT = (242, 244, 255)
SLIDER_TRACK = (40, 52, 80)
SLIDER_FILL = ACCENT
SLIDER_KNOB = (255, 228, 120)
SLIDER_KNOB_RING = (255, 255, 255)

# Background hex palette (subtle tints sampled from in-game terrain)
_BG_HEX_COLORS = (
    (28, 44, 60),
    (32, 56, 48),
    (44, 56, 36),
    (24, 38, 70),
    (40, 44, 56),
    (48, 40, 28),
)

MAX_SEED_LEN = 24

_DEFAULTS = HexColonySettings()
MIN_RADIUS = 40
MAX_RADIUS = 120

_SQRT3 = math.sqrt(3.0)

# Path to the swappable menu logo. Drop a new PNG with the same name to
# replace it (any size works — it's scaled down to fit).
LOGO_PATH = ASSET_DIR / "sprites" / "ui" / "menu_logo.png"
LOGO_MAX_W_FRAC = 0.55  # logo width as a fraction of screen width
LOGO_MAX_H = 220


def _size_label(radius: int) -> str:
    """Friendly label for the current map-size value."""
    if radius < 60:
        return "Small"
    if radius < 90:
        return "Medium"
    if radius < 110:
        return "Large"
    return "Huge"


@dataclass
class MenuResult:
    """What the menu hands off to the game."""
    seed: str
    world_radius: int
    difficulty: Difficulty


class HexColonyMenu:
    """Full-screen menu: game title, seed entry box, map-size slider, Play button.

    Returns a :class:`MenuResult` or ``None`` if the player backs out.
    """

    def __init__(self, width: int, height: int) -> None:
        self.width = width
        self.height = height
        self.seed_text = ""
        self.input_active = True
        self.world_radius = _DEFAULTS.world_radius
        self.difficulty = _DEFAULTS.difficulty
        self._dragging_slider = False
        self.result: MenuResult | None = None
        self.quit = False

        # Animation state
        self._t0 = pygame.time.get_ticks()
        self._bg_cache: pygame.Surface | None = None
        self._bg_cache_size: tuple[int, int] = (0, 0)
        self._gradient_cache: pygame.Surface | None = None
        self._gradient_size: tuple[int, int] = (0, 0)
        self._dice_pulse = 0.0  # ticks down after random-seed press
        self._play_pulse = 0.0  # ticks down on hover-in

        # Floating particles (slow drifting motes)
        rng = random.Random(0xC07012)
        self._particles = [
            {
                "x": rng.uniform(0, 1),
                "y": rng.uniform(0, 1),
                "vx": rng.uniform(-0.005, 0.005),
                "vy": rng.uniform(-0.01, -0.002),
                "r": rng.uniform(0.6, 1.8),
                "a": rng.uniform(40, 110),
                "phase": rng.uniform(0, math.tau),
            }
            for _ in range(40)
        ]

        # Pre-generated background hex tints (deterministic so they don't
        # flicker between frames). Map (col, row) → tint colour.
        self._bg_tints: dict[tuple[int, int], tuple[int, int, int]] = {}
        rng2 = random.Random(0xBEEF42)
        for _ in range(220):
            cell = (rng2.randint(-40, 40), rng2.randint(-40, 40))
            self._bg_tints[cell] = rng2.choice(_BG_HEX_COLORS)

        # Fonts
        self.title_font = pygame.font.Font(None, 92)
        self.subtitle_font = pygame.font.Font(None, 28)
        self.label_font = pygame.font.Font(None, 24)
        self.input_font = pygame.font.Font(None, 32)
        self.button_font = pygame.font.Font(None, 36)
        self.hint_font = pygame.font.Font(None, 20)
        self.slider_font = pygame.font.Font(None, 26)
        self.value_font = pygame.font.Font(None, 22)

        # Logo (optional — falls back to text title if file is missing)
        self._logo_base: pygame.Surface | None = None
        try:
            if LOGO_PATH.is_file():
                self._logo_base = pygame.image.load(str(LOGO_PATH)).convert_alpha()
        except (pygame.error, OSError):
            self._logo_base = None
        self._logo_scaled: pygame.Surface | None = None
        self._logo_scaled_for: tuple[int, int] = (0, 0)

    # ── Layout helpers ───────────────────────────────────────────

    def _card_rect(self) -> pygame.Rect:
        w = min(680, self.width - 80)
        h = 460
        x = (self.width - w) // 2
        # No logo above the card any more — center vertically with a
        # small upward bias so the Play button below isn't crammed
        # against the bottom edge.
        y = max(40, (self.height - h) // 2 - 30)
        return pygame.Rect(x, y, w, h)

    def _input_rect(self) -> pygame.Rect:
        c = self._card_rect()
        w = c.w - 80 - 56  # leave room for dice button
        h = 46
        x = c.x + 40
        y = c.y + 80
        return pygame.Rect(x, y, w, h)

    def _dice_rect(self) -> pygame.Rect:
        ir = self._input_rect()
        return pygame.Rect(ir.right + 8, ir.y, 48, ir.h)

    def _slider_rect(self) -> pygame.Rect:
        c = self._card_rect()
        ir = self._input_rect()
        w = c.w - 80
        h = 8
        x = c.x + 40
        y = ir.bottom + 56
        return pygame.Rect(x, y, w, h)

    def _slider_knob_x(self) -> int:
        sr = self._slider_rect()
        t = (self.world_radius - MIN_RADIUS) / max(1, MAX_RADIUS - MIN_RADIUS)
        return int(sr.x + t * sr.w)

    def _difficulty_rects(self) -> tuple[pygame.Rect, pygame.Rect, pygame.Rect]:
        """Easy / Hard / Desolation segmented-button rects."""
        c = self._card_rect()
        w = c.w - 80
        h = 46
        x = c.x + 40
        y = self._slider_rect().bottom + 60
        gap = 10
        third = (w - 2 * gap) // 3
        easy = pygame.Rect(x, y, third, h)
        hard = pygame.Rect(x + third + gap, y, third, h)
        des = pygame.Rect(
            x + 2 * (third + gap), y, w - 2 * (third + gap), h,
        )
        return easy, hard, des

    def _play_rect(self) -> pygame.Rect:
        w, h = 220, 56
        x = (self.width - w) // 2
        easy_rect, _, _ = self._difficulty_rects()
        # Sit just below the card so the button visually anchors the form.
        y = easy_rect.bottom + 40
        return pygame.Rect(x, y, w, h)

    # ── Main loop ────────────────────────────────────────────────

    def run(self, screen: pygame.Surface, clock: pygame.time.Clock) -> MenuResult | None:
        """Block until the player clicks Play or presses Escape."""
        from compprog_pygame.audio import music
        # Re-assert the menu track in case the player just returned
        # from a game; idempotent if already playing.
        music.play("menu")
        while self.result is None and not self.quit:
            dt_ms = clock.tick(60)
            dt = dt_ms / 1000.0

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.quit = True
                elif event.type == pygame.VIDEORESIZE:
                    screen = pygame.display.get_surface()
                    self.width = screen.get_width()
                    self.height = screen.get_height()
                    self._bg_cache = None
                    self._gradient_cache = None
                elif event.type == pygame.KEYDOWN:
                    self._on_key(event)
                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    self._on_click(event.pos)
                elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                    self._dragging_slider = False
                elif event.type == pygame.MOUSEMOTION:
                    if self._dragging_slider:
                        self._update_slider(event.pos[0])

            # Tick animation timers
            self._dice_pulse = max(0.0, self._dice_pulse - dt)
            self._play_pulse = max(0.0, self._play_pulse - dt)
            for p in self._particles:
                p["x"] += p["vx"] * dt
                p["y"] += p["vy"] * dt
                if p["y"] < -0.05:
                    p["y"] = 1.05
                    p["x"] = random.random()
                if p["x"] < -0.05:
                    p["x"] = 1.05
                elif p["x"] > 1.05:
                    p["x"] = -0.05

            self._draw(screen)
            pygame.display.flip()

        return self.result

    # ── Input handling ───────────────────────────────────────────

    def _on_key(self, event: pygame.event.Event) -> None:
        if event.key == pygame.K_ESCAPE:
            self.quit = True
            return
        if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
            self._start_game()
            return

        if not self.input_active:
            return

        if event.key == pygame.K_BACKSPACE:
            self.seed_text = self.seed_text[:-1]
        elif event.key == pygame.K_DELETE:
            self.seed_text = ""
        else:
            ch = event.unicode
            if ch and ch.isalnum() and len(self.seed_text) < MAX_SEED_LEN:
                self.seed_text += ch

    def _on_click(self, pos: tuple[int, int]) -> None:
        # Seed input focus
        if self._input_rect().collidepoint(pos):
            self.input_active = True
        else:
            self.input_active = False

        # Random-seed dice button
        if self._dice_rect().collidepoint(pos):
            self.seed_text = "".join(
                random.choices(string.ascii_lowercase + string.digits, k=8)
            )
            self.input_active = True
            self._dice_pulse = 0.4
            return

        # Slider interaction (generous vertical hit area)
        sr = self._slider_rect()
        slider_hit = pygame.Rect(sr.x - 10, sr.y - 16, sr.w + 20, sr.h + 32)
        if slider_hit.collidepoint(pos):
            self._dragging_slider = True
            self._update_slider(pos[0])
            return

        # Difficulty buttons
        easy_rect, hard_rect, des_rect = self._difficulty_rects()
        if easy_rect.collidepoint(pos):
            self.difficulty = Difficulty.EASY
            return
        if hard_rect.collidepoint(pos):
            self.difficulty = Difficulty.HARD
            return
        if des_rect.collidepoint(pos):
            self.difficulty = Difficulty.DESOLATION
            return

        if self._play_rect().collidepoint(pos):
            self._start_game()

    def _update_slider(self, mouse_x: int) -> None:
        sr = self._slider_rect()
        t = max(0.0, min(1.0, (mouse_x - sr.x) / sr.w))
        self.world_radius = int(MIN_RADIUS + t * (MAX_RADIUS - MIN_RADIUS))

    def _start_game(self) -> None:
        if not self.seed_text.strip():
            self.seed_text = "".join(
                random.choices(string.ascii_letters + string.digits, k=8)
            )
        self.result = MenuResult(
            seed=self.seed_text.strip(),
            world_radius=self.world_radius,
            difficulty=self.difficulty,
        )

    # ── Drawing ──────────────────────────────────────────────────

    def _ensure_gradient(self) -> pygame.Surface:
        size = (self.width, self.height)
        if self._gradient_cache is None or self._gradient_size != size:
            surf = pygame.Surface(size).convert()
            r1, g1, b1 = BACKGROUND_TOP
            r2, g2, b2 = BACKGROUND_BOT
            h = max(1, self.height)
            for y in range(h):
                t = y / h
                # Ease the gradient toward the bottom for a vignetted feel.
                t = t * t * (3 - 2 * t)
                col = (
                    int(r1 + (r2 - r1) * t),
                    int(g1 + (g2 - g1) * t),
                    int(b1 + (b2 - b1) * t),
                )
                pygame.draw.line(surf, col, (0, y), (self.width, y))
            self._gradient_cache = surf
            self._gradient_size = size
        return self._gradient_cache

    def _draw_hex_field(self, surface: pygame.Surface, t_ms: int) -> None:
        """Drifting hex tile field behind the menu card."""
        size = 46  # hex radius in pixels
        w = _SQRT3 * size  # column width (pointy-top)
        h = 1.5 * size  # row height
        # Slow scroll over time
        ox = (t_ms * 0.012) % w
        oy = (t_ms * 0.006) % h

        cols = int(self.width / w) + 3
        rows = int(self.height / h) + 3
        col_start = -2
        row_start = -2

        for row in range(row_start, rows):
            for col in range(col_start, cols):
                # Pointy-top axial: stagger every other row
                cx = col * w + (w / 2 if row % 2 else 0) - ox
                cy = row * h - oy
                tint = self._bg_tints.get((col & 31, row & 31))
                pts = _hex_points(cx, cy, size - 1)
                if tint is not None:
                    # Tinted hex with subtle pulse
                    pulse = 0.5 + 0.5 * math.sin(t_ms * 0.001 + (col + row) * 0.5)
                    a = int(28 + 36 * pulse)
                    fill = (tint[0], tint[1], tint[2], a)
                    _draw_polygon_alpha(surface, fill, pts)
                # Outline (very faint)
                pygame.draw.polygon(surface, (40, 52, 80), pts, 1)

    def _draw_particles(self, surface: pygame.Surface, t_ms: int) -> None:
        for p in self._particles:
            x = int(p["x"] * self.width)
            y = int(p["y"] * self.height)
            twinkle = 0.6 + 0.4 * math.sin(t_ms * 0.002 + p["phase"])
            a = int(p["a"] * twinkle)
            r = max(1, int(p["r"]))
            _circle_alpha(surface, (220, 230, 255, a), (x, y), r)

    def _draw_card(self, surface: pygame.Surface, rect: pygame.Rect) -> None:
        # Drop shadow
        shadow = pygame.Surface((rect.w + 40, rect.h + 40), pygame.SRCALPHA)
        for i in range(8):
            a = 30 - i * 3
            if a <= 0:
                break
            pygame.draw.rect(
                shadow,
                (0, 0, 0, a),
                pygame.Rect(20 - i, 24 - i, rect.w + i * 2, rect.h + i * 2),
                border_radius=18,
            )
        surface.blit(shadow, (rect.x - 20, rect.y - 20))

        # Translucent panel
        panel = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
        pygame.draw.rect(panel, CARD_BG, panel.get_rect(), border_radius=18)
        # Inner highlight stripe near top
        hi = pygame.Rect(0, 0, rect.w, 2)
        pygame.draw.rect(panel, (255, 255, 255, 22), hi, border_radius=18)
        surface.blit(panel, rect.topleft)

        # Border (double-stroke for crispness)
        pygame.draw.rect(surface, CARD_BORDER, rect, width=2, border_radius=18)
        inner = rect.inflate(-6, -6)
        pygame.draw.rect(surface, CARD_BORDER_HI, inner, width=1, border_radius=15)

    def _get_logo(self) -> pygame.Surface | None:
        """Return the logo scaled to fit the current screen, or ``None``."""
        if self._logo_base is None:
            return None
        max_w = int(self.width * LOGO_MAX_W_FRAC)
        max_h = LOGO_MAX_H
        bw, bh = self._logo_base.get_size()
        scale = min(max_w / bw, max_h / bh, 1.0)
        target = (max(1, int(bw * scale)), max(1, int(bh * scale)))
        if self._logo_scaled is None or self._logo_scaled_for != target:
            self._logo_scaled = pygame.transform.smoothscale(self._logo_base, target)
            self._logo_scaled_for = target
        return self._logo_scaled

    def _draw_title(self, surface: pygame.Surface, t_ms: int) -> None:
        logo = self._get_logo()
        card_top = self._card_rect().y
        pulse = 0.6 + 0.4 * math.sin(t_ms * 0.0018)

        if logo is not None:
            lw, lh = logo.get_size()
            lx = (self.width - lw) // 2
            ly = max(20, card_top - lh - 24)

            # Pulsing soft halo behind the logo (additive, gold-tinted)
            halo = pygame.Surface((lw + 80, lh + 80), pygame.SRCALPHA)
            for i, (rad, a_base) in enumerate(((36, 22), (22, 36), (12, 56))):
                a = int(a_base * pulse)
                pygame.draw.ellipse(
                    halo,
                    (*TITLE_GLOW, a),
                    pygame.Rect(40 - rad, 40 - rad, lw + rad * 2, lh + rad * 2),
                )
            surface.blit(halo, (lx - 40, ly - 40), special_flags=pygame.BLEND_ADD)

            # Drop shadow
            shadow = pygame.Surface((lw, lh), pygame.SRCALPHA)
            shadow.blit(logo, (0, 0))
            shadow.fill((0, 0, 0, 180), special_flags=pygame.BLEND_RGBA_MULT)
            surface.blit(shadow, (lx + 4, ly + 6))

            surface.blit(logo, (lx, ly))

            # Subtitle just under the logo
            subtitle = self.subtitle_font.render(MENU_SUBTITLE, True, MUTED_TEXT)
            surface.blit(
                subtitle,
                ((self.width - subtitle.get_width()) // 2, ly + lh + 4),
            )
            return

        # ── Text fallback (used when the PNG is missing) ─────────
        title_str = MENU_TITLE
        title_surf = self.title_font.render(title_str, True, TITLE_COLOR)
        tw, th = title_surf.get_size()
        tx = (self.width - tw) // 2
        ty = max(40, card_top - th - 80)

        glow_layers = (
            (28, int(70 * pulse)),
            (18, int(110 * pulse)),
            (10, int(160 * pulse)),
        )
        for radius, alpha in glow_layers:
            glow = pygame.Surface((tw + radius * 2, th + radius * 2), pygame.SRCALPHA)
            tinted = self.title_font.render(title_str, True, TITLE_GLOW)
            tinted.set_alpha(alpha)
            for dx in (-radius, 0, radius):
                for dy in (-radius, 0, radius):
                    glow.blit(tinted, (radius + dx, radius + dy))
            surface.blit(glow, (tx - radius, ty - radius), special_flags=pygame.BLEND_ADD)

        shadow_surf = self.title_font.render(title_str, True, (0, 0, 0))
        shadow_surf.set_alpha(180)
        surface.blit(shadow_surf, (tx + 3, ty + 4))
        surface.blit(title_surf, (tx, ty))

        bar_w = int(tw * 0.55)
        bar_x = (self.width - bar_w) // 2
        bar_y = ty + th + 6
        pygame.draw.line(surface, ACCENT, (bar_x, bar_y), (bar_x + bar_w, bar_y), 3)
        for cx in (bar_x, bar_x + bar_w):
            pygame.draw.polygon(
                surface,
                ACCENT_BRIGHT,
                [(cx, bar_y - 5), (cx + 5, bar_y), (cx, bar_y + 5), (cx - 5, bar_y)],
            )

        subtitle = self.subtitle_font.render(MENU_SUBTITLE, True, MUTED_TEXT)
        surface.blit(
            subtitle,
            ((self.width - subtitle.get_width()) // 2, bar_y + 14),
        )

    def _draw(self, surface: pygame.Surface) -> None:
        t_ms = pygame.time.get_ticks() - self._t0
        mouse = pygame.mouse.get_pos()

        # Background gradient
        surface.blit(self._ensure_gradient(), (0, 0))

        # Hex field + particles on a single alpha overlay so blends compose.
        overlay = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
        self._draw_hex_field(overlay, t_ms)
        self._draw_particles(overlay, t_ms)
        surface.blit(overlay, (0, 0))

        # Vignette (radial-ish via four-edge gradient)
        self._draw_vignette(surface)

        # Card
        card = self._card_rect()
        self._draw_card(surface, card)

        # ── Seed input ───────────────────────────────────────────
        ir = self._input_rect()
        label = self.label_font.render(MENU_SEED_LABEL.upper(), True, ACCENT)
        surface.blit(label, (ir.x, ir.y - 26))

        border = INPUT_ACTIVE_BORDER if self.input_active else INPUT_BORDER
        pygame.draw.rect(surface, INPUT_BG, ir, border_radius=10)
        pygame.draw.rect(surface, border, ir, width=2, border_radius=10)

        display_text = self.seed_text if self.seed_text else ""
        txt_surf = self.input_font.render(display_text, True, TEXT_COLOR)
        surface.blit(txt_surf, (ir.x + 14, ir.y + (ir.h - txt_surf.get_height()) // 2))

        if self.input_active and (pygame.time.get_ticks() // 500) % 2 == 0:
            cx = ir.x + 14 + txt_surf.get_width() + 2
            cy = ir.y + 9
            pygame.draw.line(surface, TEXT_COLOR, (cx, cy), (cx, cy + ir.h - 18), 2)

        if not self.seed_text:
            ph = self.hint_font.render(MENU_SEED_PLACEHOLDER, True, MUTED_TEXT)
            surface.blit(ph, (ir.x + 14, ir.y + (ir.h - ph.get_height()) // 2))

        # Dice button
        dr = self._dice_rect()
        dice_hover = dr.collidepoint(mouse)
        dice_bg = BUTTON_HOVER if dice_hover else BUTTON_BG
        if self._dice_pulse > 0:
            dice_bg = BUTTON_ACTIVE
        pygame.draw.rect(surface, dice_bg, dr, border_radius=10)
        pygame.draw.rect(surface, ACCENT if dice_hover or self._dice_pulse > 0 else INPUT_BORDER,
                         dr, width=2, border_radius=10)
        _draw_dice_icon(surface, dr.center, color=TEXT_COLOR)

        # ── Map-size slider ──────────────────────────────────────
        sr = self._slider_rect()
        slider_label = self.label_font.render(MENU_MAP_SIZE_LABEL.upper(), True, ACCENT)
        surface.blit(slider_label, (sr.x, sr.y - 30))

        # Track shadow
        track_shadow = sr.move(0, 2)
        pygame.draw.rect(surface, (0, 0, 0, 90), track_shadow, border_radius=4)
        # Track
        pygame.draw.rect(surface, SLIDER_TRACK, sr, border_radius=4)
        # Filled portion
        knob_x = self._slider_knob_x()
        filled = pygame.Rect(sr.x, sr.y, max(0, knob_x - sr.x), sr.h)
        pygame.draw.rect(surface, SLIDER_FILL, filled, border_radius=4)
        # Tick marks at quarters
        for i in range(1, 4):
            tx = sr.x + int(i * sr.w / 4)
            pygame.draw.line(surface, (90, 100, 130), (tx, sr.y - 3), (tx, sr.bottom + 3), 1)
        # Knob (outer ring + inner fill)
        pygame.draw.circle(surface, SLIDER_KNOB_RING, (knob_x, sr.centery), 12)
        pygame.draw.circle(surface, SLIDER_KNOB, (knob_x, sr.centery), 9)
        pygame.draw.circle(surface, (180, 130, 40), (knob_x, sr.centery), 9, 1)

        # Friendly size label + numeric value (right-aligned)
        size_str = f"{_size_label(self.world_radius)}  ·  r={self.world_radius}"
        val_text = self.value_font.render(size_str, True, TEXT_COLOR)
        surface.blit(
            val_text,
            (sr.right - val_text.get_width(), sr.y - 28),
        )

        # ── Difficulty buttons ──────────────────────────────────
        easy_rect, hard_rect, des_rect = self._difficulty_rects()
        diff_label = self.label_font.render(MENU_DIFFICULTY_LABEL.upper(), True, ACCENT)
        surface.blit(diff_label, (easy_rect.x, easy_rect.y - 26))

        for rect, diff, label, icon in (
            (easy_rect, Difficulty.EASY, MENU_DIFFICULTY_EASY, "leaf"),
            (hard_rect, Difficulty.HARD, MENU_DIFFICULTY_HARD, "skull"),
            (des_rect, Difficulty.DESOLATION, MENU_DIFFICULTY_DESOLATION, "flame"),
        ):
            selected = self.difficulty == diff
            hovered = rect.collidepoint(mouse)
            if selected:
                bg = BUTTON_ACTIVE
                border = ACCENT_BRIGHT
            elif hovered:
                bg = BUTTON_HOVER
                border = CARD_BORDER_HI
            else:
                bg = BUTTON_BG
                border = INPUT_BORDER
            pygame.draw.rect(surface, bg, rect, border_radius=10)
            pygame.draw.rect(surface, border, rect, width=2, border_radius=10)
            # Selection check-mark glyph
            if selected:
                pygame.draw.circle(surface, ACCENT_BRIGHT, (rect.x + 16, rect.centery), 5)
                pygame.draw.circle(surface, (30, 50, 90), (rect.x + 16, rect.centery), 5, 1)
            # Icon (right-aligned)
            icon_cx = rect.right - 22
            _draw_diff_icon(surface, (icon_cx, rect.centery), icon,
                            color=ACCENT_BRIGHT if selected else MUTED_TEXT)
            # Label centered in the zone between the selection dot
            # and the icon so they never overlap when buttons are
            # narrow (e.g. the 3-column difficulty row).
            txt = self.input_font.render(label, True, BUTTON_TEXT)
            text_left = rect.x + 28
            text_right = icon_cx - 12
            text_zone_w = max(1, text_right - text_left)
            surface.blit(
                txt,
                (text_left + (text_zone_w - txt.get_width()) // 2,
                 rect.y + (rect.h - txt.get_height()) // 2),
            )

        # Difficulty description below the buttons
        if self.difficulty == Difficulty.EASY:
            diff_desc = MENU_DIFFICULTY_EASY_DESC
        elif self.difficulty == Difficulty.HARD:
            diff_desc = MENU_DIFFICULTY_HARD_DESC
        else:
            diff_desc = MENU_DIFFICULTY_DESOLATION_DESC
        desc_surf = self.hint_font.render(diff_desc, True, MUTED_TEXT)
        card = self._card_rect()
        surface.blit(
            desc_surf,
            (card.x + (card.w - desc_surf.get_width()) // 2, easy_rect.bottom + 12),
        )

        # ── Play button ──────────────────────────────────────────
        pr = self._play_rect()
        hovered = pr.collidepoint(mouse)
        if hovered and self._play_pulse <= 0:
            self._play_pulse = 0.6
        # Animated outer glow when hovered
        if hovered:
            glow = pygame.Surface((pr.w + 40, pr.h + 40), pygame.SRCALPHA)
            for i in range(6):
                a = 60 - i * 9
                if a <= 0:
                    break
                pygame.draw.rect(
                    glow,
                    (*ACCENT_BRIGHT, a),
                    pygame.Rect(20 - i * 2, 20 - i * 2,
                                pr.w + i * 4, pr.h + i * 4),
                    border_radius=14 + i,
                )
            surface.blit(glow, (pr.x - 20, pr.y - 20))

        # Vertical gradient fill for the button
        btn_surf = pygame.Surface((pr.w, pr.h), pygame.SRCALPHA)
        top_col = BUTTON_HOVER if hovered else BUTTON_BG
        bot_col = BUTTON_ACTIVE if hovered else (20, 38, 72)
        for y in range(pr.h):
            t = y / pr.h
            col = (
                int(top_col[0] + (bot_col[0] - top_col[0]) * t),
                int(top_col[1] + (bot_col[1] - top_col[1]) * t),
                int(top_col[2] + (bot_col[2] - top_col[2]) * t),
                255,
            )
            pygame.draw.line(btn_surf, col, (0, y), (pr.w, y))
        # Round corners by masking
        mask = pygame.Surface((pr.w, pr.h), pygame.SRCALPHA)
        pygame.draw.rect(mask, (255, 255, 255, 255), mask.get_rect(), border_radius=12)
        btn_surf.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
        surface.blit(btn_surf, pr.topleft)
        pygame.draw.rect(surface, ACCENT_BRIGHT if hovered else ACCENT,
                         pr, width=2, border_radius=12)

        btn_text = self.button_font.render(MENU_PLAY_BUTTON.upper(), True, BUTTON_TEXT)
        # Center text + arrow
        text_x = pr.x + (pr.w - btn_text.get_width()) // 2 - 10
        text_y = pr.y + (pr.h - btn_text.get_height()) // 2
        surface.blit(btn_text, (text_x, text_y))
        # Right-pointing chevron
        arrow_x = text_x + btn_text.get_width() + 10
        cy = pr.centery
        pygame.draw.polygon(
            surface,
            ACCENT_BRIGHT,
            [(arrow_x, cy - 8), (arrow_x + 12, cy), (arrow_x, cy + 8)],
        )

        # Hint
        hint = self.hint_font.render(MENU_HINT, True, MUTED_TEXT)
        surface.blit(hint, ((self.width - hint.get_width()) // 2, self.height - 32))

    def _draw_vignette(self, surface: pygame.Surface) -> None:
        """Soft dark vignette around the screen edges."""
        vig = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
        edge = max(80, min(self.width, self.height) // 5)
        for i in range(edge):
            a = int(140 * (1 - i / edge) ** 2)
            if a <= 0:
                continue
            col = (0, 0, 0, a)
            # Top/bottom strips
            pygame.draw.line(vig, col, (0, i), (self.width, i))
            pygame.draw.line(vig, col, (0, self.height - 1 - i), (self.width, self.height - 1 - i))
            # Left/right strips
            pygame.draw.line(vig, col, (i, 0), (i, self.height))
            pygame.draw.line(vig, col, (self.width - 1 - i, 0), (self.width - 1 - i, self.height))
        surface.blit(vig, (0, 0))


# ── Drawing primitives ───────────────────────────────────────────


def _hex_points(cx: float, cy: float, size: float) -> list[tuple[int, int]]:
    """Pointy-top hexagon vertices."""
    pts = []
    for i in range(6):
        ang = math.pi / 180 * (60 * i - 30)
        pts.append((int(cx + size * math.cos(ang)), int(cy + size * math.sin(ang))))
    return pts


def _draw_polygon_alpha(
    surface: pygame.Surface,
    color: tuple[int, int, int, int],
    points: list[tuple[int, int]],
) -> None:
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    minx, miny = min(xs), min(ys)
    maxx, maxy = max(xs), max(ys)
    w = max(1, maxx - minx + 1)
    h = max(1, maxy - miny + 1)
    layer = pygame.Surface((w, h), pygame.SRCALPHA)
    shifted = [(x - minx, y - miny) for x, y in points]
    pygame.draw.polygon(layer, color, shifted)
    surface.blit(layer, (minx, miny))


def _circle_alpha(
    surface: pygame.Surface,
    color: tuple[int, int, int, int],
    pos: tuple[int, int],
    radius: int,
) -> None:
    layer = pygame.Surface((radius * 2 + 2, radius * 2 + 2), pygame.SRCALPHA)
    pygame.draw.circle(layer, color, (radius + 1, radius + 1), radius)
    surface.blit(layer, (pos[0] - radius - 1, pos[1] - radius - 1))


def _draw_dice_icon(
    surface: pygame.Surface,
    center: tuple[int, int],
    *,
    color: tuple[int, int, int],
) -> None:
    cx, cy = center
    s = 18
    rect = pygame.Rect(cx - s // 2, cy - s // 2, s, s)
    pygame.draw.rect(surface, color, rect, width=2, border_radius=4)
    # Five-dot face
    for dx, dy in ((-5, -5), (5, -5), (0, 0), (-5, 5), (5, 5)):
        pygame.draw.circle(surface, color, (cx + dx, cy + dy), 1)


def _draw_diff_icon(
    surface: pygame.Surface,
    center: tuple[int, int],
    kind: str,
    *,
    color: tuple[int, int, int],
) -> None:
    cx, cy = center
    if kind == "leaf":
        # Small leaf shape from two arcs
        rect = pygame.Rect(cx - 8, cy - 8, 16, 16)
        pygame.draw.arc(surface, color, rect, math.pi * 0.25, math.pi * 1.25, 2)
        pygame.draw.line(surface, color, (cx - 6, cy + 6), (cx + 6, cy - 6), 2)
    elif kind == "skull":
        # Tiny skull glyph
        pygame.draw.circle(surface, color, (cx, cy - 1), 7, 2)
        pygame.draw.circle(surface, color, (cx - 3, cy - 1), 1)
        pygame.draw.circle(surface, color, (cx + 3, cy - 1), 1)
        pygame.draw.line(surface, color, (cx - 3, cy + 5), (cx + 3, cy + 5), 2)
    elif kind == "flame":
        # Stylised flame: outer teardrop + inner highlight
        outer = [
            (cx, cy - 9),
            (cx + 6, cy - 1),
            (cx + 5, cy + 5),
            (cx, cy + 8),
            (cx - 5, cy + 5),
            (cx - 6, cy - 1),
            (cx - 2, cy - 4),
        ]
        pygame.draw.polygon(surface, color, outer, 2)
        pygame.draw.line(surface, color, (cx, cy + 4), (cx, cy - 2), 2)
