"""Menu screen for Hex Colony — title, seed entry, map-size slider, and play button."""

from __future__ import annotations

import random
import string
from dataclasses import dataclass

import pygame

from compprog_pygame.games.hex_colony.settings import HexColonySettings

# ── Colours ──────────────────────────────────────────────────────

BACKGROUND = (9, 12, 25)
TITLE_COLOR = (242, 244, 255)
ACCENT = (200, 160, 60)
TEXT_COLOR = (242, 244, 255)
MUTED_TEXT = (140, 150, 175)
INPUT_BG = (16, 24, 45)
INPUT_BORDER = (60, 70, 100)
INPUT_ACTIVE_BORDER = ACCENT
BUTTON_BG = (30, 50, 90)
BUTTON_HOVER = (50, 75, 130)
BUTTON_TEXT = (242, 244, 255)
SLIDER_TRACK = (60, 70, 100)
SLIDER_FILL = ACCENT
SLIDER_KNOB = (255, 220, 100)

MAX_SEED_LEN = 24

_DEFAULTS = HexColonySettings()
MIN_RADIUS = 40
MAX_RADIUS = 120


@dataclass
class MenuResult:
    """What the menu hands off to the game."""
    seed: str
    world_radius: int


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
        self._dragging_slider = False
        self.result: MenuResult | None = None
        self.quit = False

        # Fonts
        self.title_font = pygame.font.Font(None, 80)
        self.subtitle_font = pygame.font.Font(None, 30)
        self.input_font = pygame.font.Font(None, 34)
        self.button_font = pygame.font.Font(None, 38)
        self.hint_font = pygame.font.Font(None, 22)
        self.slider_font = pygame.font.Font(None, 28)

    # ── Layout helpers ───────────────────────────────────────────

    def _input_rect(self) -> pygame.Rect:
        w = min(400, self.width - 60)
        h = 44
        x = (self.width - w) // 2
        y = self.height // 2 - 40
        return pygame.Rect(x, y, w, h)

    def _slider_rect(self) -> pygame.Rect:
        """Track rectangle for the map-size slider."""
        ir = self._input_rect()
        w = ir.w
        h = 10
        x = ir.x
        y = ir.bottom + 50
        return pygame.Rect(x, y, w, h)

    def _slider_knob_x(self) -> int:
        sr = self._slider_rect()
        t = (self.world_radius - MIN_RADIUS) / max(1, MAX_RADIUS - MIN_RADIUS)
        return int(sr.x + t * sr.w)

    def _play_rect(self) -> pygame.Rect:
        w, h = 180, 50
        x = (self.width - w) // 2
        y = self._slider_rect().bottom + 50
        return pygame.Rect(x, y, w, h)

    # ── Main loop ────────────────────────────────────────────────

    def run(self, screen: pygame.Surface, clock: pygame.time.Clock) -> MenuResult | None:
        """Block until the player clicks Play or presses Escape."""
        while self.result is None and not self.quit:
            clock.tick(60)

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.quit = True
                elif event.type == pygame.VIDEORESIZE:
                    screen = pygame.display.get_surface()
                    self.width = screen.get_width()
                    self.height = screen.get_height()
                elif event.type == pygame.KEYDOWN:
                    self._on_key(event)
                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    self._on_click(event.pos)
                elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                    self._dragging_slider = False
                elif event.type == pygame.MOUSEMOTION:
                    if self._dragging_slider:
                        self._update_slider(event.pos[0])

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

        # Slider interaction (generous vertical hit area)
        sr = self._slider_rect()
        slider_hit = pygame.Rect(sr.x - 8, sr.y - 14, sr.w + 16, sr.h + 28)
        if slider_hit.collidepoint(pos):
            self._dragging_slider = True
            self._update_slider(pos[0])
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
        )

    # ── Drawing ──────────────────────────────────────────────────

    def _draw(self, surface: pygame.Surface) -> None:
        surface.fill(BACKGROUND)

        # Title
        title = self.title_font.render("Hex Colony", True, TITLE_COLOR)
        surface.blit(title, ((self.width - title.get_width()) // 2, self.height // 4 - 30))

        subtitle = self.subtitle_font.render(
            "A people-driven logistics game", True, MUTED_TEXT
        )
        surface.blit(subtitle, ((self.width - subtitle.get_width()) // 2, self.height // 4 + 50))

        # ── Seed input ───────────────────────────────────────────
        label = self.subtitle_font.render("World Seed", True, TEXT_COLOR)
        ir = self._input_rect()
        surface.blit(label, (ir.x, ir.y - 28))

        border = INPUT_ACTIVE_BORDER if self.input_active else INPUT_BORDER
        pygame.draw.rect(surface, INPUT_BG, ir, border_radius=8)
        pygame.draw.rect(surface, border, ir, width=2, border_radius=8)

        display_text = self.seed_text if self.seed_text else ""
        txt_surf = self.input_font.render(display_text, True, TEXT_COLOR)
        surface.blit(txt_surf, (ir.x + 12, ir.y + (ir.h - txt_surf.get_height()) // 2))

        if self.input_active and (pygame.time.get_ticks() // 500) % 2 == 0:
            cx = ir.x + 12 + txt_surf.get_width() + 2
            cy = ir.y + 8
            pygame.draw.line(surface, TEXT_COLOR, (cx, cy), (cx, cy + ir.h - 16), 2)

        if not self.seed_text:
            ph = self.hint_font.render("Leave blank for random seed", True, MUTED_TEXT)
            surface.blit(ph, (ir.x + 12, ir.y + (ir.h - ph.get_height()) // 2))

        # ── Map-size slider ──────────────────────────────────────
        sr = self._slider_rect()
        slider_label = self.subtitle_font.render("Map Size", True, TEXT_COLOR)
        surface.blit(slider_label, (sr.x, sr.y - 28))

        # Track
        pygame.draw.rect(surface, SLIDER_TRACK, sr, border_radius=5)
        # Filled portion
        knob_x = self._slider_knob_x()
        filled = pygame.Rect(sr.x, sr.y, knob_x - sr.x, sr.h)
        pygame.draw.rect(surface, SLIDER_FILL, filled, border_radius=5)
        # Knob
        pygame.draw.circle(surface, SLIDER_KNOB, (knob_x, sr.centery), 10)

        # Numeric value
        val_text = self.slider_font.render(str(self.world_radius), True, TEXT_COLOR)
        surface.blit(val_text, (sr.right + 14, sr.centery - val_text.get_height() // 2))

        # ── Play button ──────────────────────────────────────────
        pr = self._play_rect()
        mouse = pygame.mouse.get_pos()
        hovered = pr.collidepoint(mouse)
        bg = BUTTON_HOVER if hovered else BUTTON_BG
        pygame.draw.rect(surface, bg, pr, border_radius=10)
        pygame.draw.rect(surface, ACCENT, pr, width=2, border_radius=10)
        btn_text = self.button_font.render("Play", True, BUTTON_TEXT)
        surface.blit(btn_text, (pr.x + (pr.w - btn_text.get_width()) // 2,
                                pr.y + (pr.h - btn_text.get_height()) // 2))

        # Hint
        hint = self.hint_font.render("Enter seed  •  ENTER or click Play  •  ESC to go back", True, MUTED_TEXT)
        surface.blit(hint, ((self.width - hint.get_width()) // 2, self.height - 40))
