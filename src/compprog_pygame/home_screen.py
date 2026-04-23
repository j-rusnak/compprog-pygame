"""Main menu screen — RePioneer logo, Play button, animated starfield.

Shows the game's hero logo over a space-themed background with a single
Play button that launches the (only) registered game.  Pressing Escape
quits the application.
"""

from __future__ import annotations

import math
import random

import pygame

from compprog_pygame.audio import music
from compprog_pygame.game_registry import GameInfo, all_games
from compprog_pygame.games.hex_colony.strings import (
    HOME_HINT,
    HOME_NO_GAMES,
    MENU_PLAY_BUTTON,
)
from compprog_pygame.settings import ASSET_DIR

# ── Colours ──────────────────────────────────────────────────────
BACKGROUND_TOP = (3, 4, 12)
BACKGROUND_BOT = (10, 6, 28)
NEBULA_A = (60, 30, 110)
NEBULA_B = (20, 50, 110)
TEXT_COLOR = (242, 244, 255)
MUTED_TEXT = (150, 160, 185)
ACCENT = (220, 176, 70)
ACCENT_BRIGHT = (255, 220, 110)
TITLE_GLOW = (255, 198, 92)
BUTTON_BG = (30, 50, 90)
BUTTON_HOVER = (55, 82, 140)
BUTTON_ACTIVE = (75, 110, 175)
BUTTON_TEXT = (242, 244, 255)

LOGO_PATH = ASSET_DIR / "sprites" / "ui" / "menu_logo.png"
LOGO_MAX_W_FRAC = 0.62
LOGO_MAX_H = 320
LOGO_TOP_FRAC = 0.18  # logo top as a fraction of screen height

NUM_STARS = 220
NUM_BIG_STARS = 18
NUM_SHOOTING = 2


def _circle_alpha(
    surface: pygame.Surface,
    color: tuple[int, int, int, int],
    center: tuple[int, int],
    radius: int,
) -> None:
    d = radius * 2 + 2
    tmp = pygame.Surface((d, d), pygame.SRCALPHA)
    pygame.draw.circle(tmp, color, (radius + 1, radius + 1), radius)
    surface.blit(tmp, (center[0] - radius - 1, center[1] - radius - 1))


class HomeScreen:
    """Main menu: hero logo + Play button on a space backdrop."""

    def __init__(self, width: int, height: int) -> None:
        self.width = width
        self.height = height
        self.games = all_games()
        self.selected: GameInfo | None = None
        self.quit = False

        # Fonts
        self.button_font = pygame.font.Font(None, 40)
        self.hint_font = pygame.font.Font(None, 22)

        # Animation state
        self._t0 = pygame.time.get_ticks()
        self._bg_cache: pygame.Surface | None = None
        self._bg_cache_size: tuple[int, int] = (0, 0)
        self._play_pulse = 0.0

        # Stars (deterministic so they don't reshuffle on resize)
        rng = random.Random(0x57A75)
        self._stars = [
            {
                "x": rng.uniform(0, 1),
                "y": rng.uniform(0, 1),
                "r": rng.uniform(0.4, 1.4),
                "a": rng.uniform(60, 200),
                "phase": rng.uniform(0, math.tau),
                "tw": rng.uniform(0.8, 2.4),
                "drift": rng.uniform(-0.003, 0.003),
            }
            for _ in range(NUM_STARS)
        ]
        # A handful of brighter, larger stars with cross-glints
        self._big_stars = [
            {
                "x": rng.uniform(0.05, 0.95),
                "y": rng.uniform(0.05, 0.95),
                "r": rng.uniform(1.6, 2.6),
                "a": rng.uniform(180, 240),
                "phase": rng.uniform(0, math.tau),
                "tw": rng.uniform(0.6, 1.6),
                "tint": rng.choice(((220, 230, 255), (255, 230, 200), (200, 220, 255))),
            }
            for _ in range(NUM_BIG_STARS)
        ]
        # Shooting stars (timer-driven)
        self._shooters: list[dict] = []
        self._next_shooter_in = rng.uniform(2.0, 6.0)
        self._shooter_rng = rng

        # Logo
        self._logo_base: pygame.Surface | None = None
        try:
            if LOGO_PATH.is_file():
                self._logo_base = pygame.image.load(str(LOGO_PATH)).convert_alpha()
        except (pygame.error, OSError):
            self._logo_base = None
        self._logo_scaled: pygame.Surface | None = None
        self._logo_scaled_for: tuple[int, int] = (0, 0)

    def resize(self, width: int, height: int) -> None:
        self.width = width
        self.height = height
        self._bg_cache = None
        self._logo_scaled = None

    # ── Logo ─────────────────────────────────────────────────────

    def _get_logo(self) -> pygame.Surface | None:
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

    # ── Layout ───────────────────────────────────────────────────

    def _logo_rect(self) -> pygame.Rect | None:
        logo = self._get_logo()
        if logo is None:
            return None
        lw, lh = logo.get_size()
        lx = (self.width - lw) // 2
        ly = int(self.height * LOGO_TOP_FRAC)
        return pygame.Rect(lx, ly, lw, lh)

    def _play_rect(self) -> pygame.Rect:
        w, h = 260, 64
        x = (self.width - w) // 2
        lr = self._logo_rect()
        if lr is not None:
            y = lr.bottom + 56
        else:
            y = int(self.height * 0.55)
        # Keep button on-screen even on very short windows
        y = min(y, self.height - h - 70)
        return pygame.Rect(x, y, w, h)

    # ── Main loop ────────────────────────────────────────────────

    def run(self, screen: pygame.Surface, clock: pygame.time.Clock) -> GameInfo | None:
        # Start (or keep playing) the menu theme.  No-op if already
        # playing or if no menu.ogg exists yet.
        music.play("menu")
        while not self.selected and not self.quit:
            dt_ms = clock.tick(60)
            dt = dt_ms / 1000.0

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.quit = True
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        self.quit = True
                    elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
                        self._start_game()
                elif event.type == pygame.VIDEORESIZE:
                    screen = pygame.display.get_surface()
                    self.resize(screen.get_width(), screen.get_height())
                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    self._on_click(event.pos)

            self._tick_animation(dt)
            self._draw(screen)
            pygame.display.flip()

        return self.selected

    def _start_game(self) -> None:
        if self.games:
            self.selected = self.games[0]

    def _on_click(self, pos: tuple[int, int]) -> None:
        if not self.games:
            return
        if self._play_rect().collidepoint(pos):
            self._start_game()

    # ── Animation ────────────────────────────────────────────────

    def _tick_animation(self, dt: float) -> None:
        self._play_pulse = max(0.0, self._play_pulse - dt)
        # Slow horizontal drift on the background stars
        for s in self._stars:
            s["x"] += s["drift"] * dt
            if s["x"] < -0.02:
                s["x"] += 1.04
            elif s["x"] > 1.02:
                s["x"] -= 1.04

        # Shooting stars
        self._next_shooter_in -= dt
        if self._next_shooter_in <= 0 and len(self._shooters) < NUM_SHOOTING:
            rng = self._shooter_rng
            angle = rng.uniform(math.pi * 0.15, math.pi * 0.35)
            speed = rng.uniform(0.6, 1.0)
            self._shooters.append({
                "x": rng.uniform(0.0, 0.6),
                "y": rng.uniform(0.0, 0.4),
                "vx": math.cos(angle) * speed,
                "vy": math.sin(angle) * speed,
                "life": 1.0,
            })
            self._next_shooter_in = rng.uniform(3.5, 8.0)
        for s in self._shooters:
            s["x"] += s["vx"] * dt
            s["y"] += s["vy"] * dt
            s["life"] -= dt * 0.6
        self._shooters[:] = [
            s for s in self._shooters
            if s["life"] > 0 and s["x"] < 1.2 and s["y"] < 1.2
        ]

    # ── Drawing ──────────────────────────────────────────────────

    def _ensure_background(self) -> pygame.Surface:
        size = (self.width, self.height)
        if self._bg_cache is not None and self._bg_cache_size == size:
            return self._bg_cache
        surf = pygame.Surface(size).convert()
        # Vertical gradient
        r1, g1, b1 = BACKGROUND_TOP
        r2, g2, b2 = BACKGROUND_BOT
        h = max(1, self.height)
        for y in range(h):
            t = y / h
            t = t * t * (3 - 2 * t)
            col = (
                int(r1 + (r2 - r1) * t),
                int(g1 + (g2 - g1) * t),
                int(b1 + (b2 - b1) * t),
            )
            pygame.draw.line(surf, col, (0, y), (self.width, y))

        self._bg_cache = surf
        self._bg_cache_size = size
        return surf

    def _draw_stars(self, surface: pygame.Surface, t_ms: int) -> None:
        # Small twinkling stars
        for s in self._stars:
            x = int(s["x"] * self.width)
            y = int(s["y"] * self.height)
            twinkle = 0.55 + 0.45 * math.sin(t_ms * 0.001 * s["tw"] + s["phase"])
            a = int(s["a"] * twinkle)
            if a <= 4:
                continue
            r = max(1, int(s["r"]))
            _circle_alpha(surface, (220, 230, 255, a), (x, y), r)

        # Larger stars with a four-point glint
        for s in self._big_stars:
            x = int(s["x"] * self.width)
            y = int(s["y"] * self.height)
            twinkle = 0.5 + 0.5 * math.sin(t_ms * 0.001 * s["tw"] + s["phase"])
            a = int(s["a"] * twinkle)
            if a <= 6:
                continue
            tint = s["tint"]
            r = max(2, int(s["r"]))
            _circle_alpha(surface, (*tint, a), (x, y), r)
            glint_len = int(8 + 6 * twinkle)
            glint = pygame.Surface(
                (glint_len * 2 + 2, glint_len * 2 + 2), pygame.SRCALPHA,
            )
            ga = int(min(255, a * 0.7))
            pygame.draw.line(glint, (*tint, ga), (0, glint_len), (glint_len * 2, glint_len), 1)
            pygame.draw.line(glint, (*tint, ga), (glint_len, 0), (glint_len, glint_len * 2), 1)
            surface.blit(glint, (x - glint_len, y - glint_len), special_flags=pygame.BLEND_ADD)

        # Shooting stars
        if not self._shooters:
            return
        tail = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
        for s in self._shooters:
            x = int(s["x"] * self.width)
            y = int(s["y"] * self.height)
            tail_len = 80
            tx = int(x - s["vx"] * tail_len)
            ty = int(y - s["vy"] * tail_len)
            a = int(220 * max(0.0, min(1.0, s["life"])))
            if a <= 0:
                continue
            steps = 12
            for i in range(steps):
                t = i / steps
                ax = int(x + (tx - x) * t)
                ay = int(y + (ty - y) * t)
                seg_a = int(a * (1 - t))
                pygame.draw.circle(tail, (255, 240, 220, seg_a), (ax, ay), max(1, 2 - int(t * 2)))
        surface.blit(tail, (0, 0), special_flags=pygame.BLEND_ADD)

    def _draw_logo(self, surface: pygame.Surface, t_ms: int) -> None:
        logo = self._get_logo()
        if logo is None:
            font = pygame.font.Font(None, 110)
            title = font.render("RePioneer", True, ACCENT_BRIGHT)
            x = (self.width - title.get_width()) // 2
            y = int(self.height * LOGO_TOP_FRAC)
            surface.blit(title, (x, y))
            return

        lr = self._logo_rect()
        assert lr is not None
        lw, lh = logo.get_size()

        # Drop shadow
        shadow = pygame.Surface((lw, lh), pygame.SRCALPHA)
        shadow.blit(logo, (0, 0))
        shadow.fill((0, 0, 0, 180), special_flags=pygame.BLEND_RGBA_MULT)
        surface.blit(shadow, (lr.x + 4, lr.y + 6))

        surface.blit(logo, lr.topleft)

    def _draw_play_button(self, surface: pygame.Surface, mouse: tuple[int, int]) -> None:
        pr = self._play_rect()
        hovered = pr.collidepoint(mouse)
        if hovered and self._play_pulse <= 0:
            self._play_pulse = 0.6

        if hovered:
            glow = pygame.Surface((pr.w + 40, pr.h + 40), pygame.SRCALPHA)
            for i in range(6):
                a = 60 - i * 9
                if a <= 0:
                    break
                pygame.draw.rect(
                    glow,
                    (*ACCENT_BRIGHT, a),
                    pygame.Rect(20 - i * 2, 20 - i * 2, pr.w + i * 4, pr.h + i * 4),
                    border_radius=14 + i,
                )
            surface.blit(glow, (pr.x - 20, pr.y - 20))

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
        mask = pygame.Surface((pr.w, pr.h), pygame.SRCALPHA)
        pygame.draw.rect(mask, (255, 255, 255, 255), mask.get_rect(), border_radius=14)
        btn_surf.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
        surface.blit(btn_surf, pr.topleft)
        pygame.draw.rect(
            surface,
            ACCENT_BRIGHT if hovered else ACCENT,
            pr, width=2, border_radius=14,
        )

        btn_text = self.button_font.render(MENU_PLAY_BUTTON.upper(), True, BUTTON_TEXT)
        text_x = pr.x + (pr.w - btn_text.get_width()) // 2 - 10
        text_y = pr.y + (pr.h - btn_text.get_height()) // 2
        surface.blit(btn_text, (text_x, text_y))
        arrow_x = text_x + btn_text.get_width() + 10
        cy = pr.centery
        pygame.draw.polygon(
            surface,
            ACCENT_BRIGHT,
            [(arrow_x, cy - 8), (arrow_x + 12, cy), (arrow_x, cy + 8)],
        )

    def _draw(self, surface: pygame.Surface) -> None:
        t_ms = pygame.time.get_ticks() - self._t0
        mouse = pygame.mouse.get_pos()

        surface.blit(self._ensure_background(), (0, 0))
        self._draw_stars(surface, t_ms)
        self._draw_logo(surface, t_ms)

        if self.games:
            self._draw_play_button(surface, mouse)
            hint = self.hint_font.render(HOME_HINT, True, MUTED_TEXT)
            surface.blit(
                hint,
                ((self.width - hint.get_width()) // 2, self.height - 36),
            )
        else:
            no_games = self.hint_font.render(HOME_NO_GAMES, True, MUTED_TEXT)
            surface.blit(
                no_games,
                ((self.width - no_games.get_width()) // 2, self.height // 2),
            )
