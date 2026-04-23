"""End-game cutscene played when a Rocket Silo fills with fuel.

Pans the camera to the silo, draws a rocket climbing skyward with a
plume trail, then hands control back to :mod:`game` which flips the
world's ``game_won`` flag and the game-over overlay takes over as a
victory screen.
"""

from __future__ import annotations

from typing import Callable

import pygame

from compprog_pygame.games.hex_colony.hex_grid import hex_to_pixel
from compprog_pygame.games.hex_colony.strings import (
    ROCKET_LAUNCH_TITLE,
    ROCKET_LAUNCH_SUBTITLE,
    ROCKET_LAUNCH_SKIP_HINT,
)


_PHASE_PAN = "pan"       # camera flies to silo coord
_PHASE_IGNITE = "ignite"  # brief pre-launch rumble
_PHASE_RISE = "rise"     # rocket climbs off the top of the screen
_PHASE_FADE = "fade"     # fade to white, hand off to win screen

_PAN_TIME = 1.4
_IGNITE_TIME = 1.2
_RISE_TIME = 3.4
_FADE_TIME = 1.0

_LETTERBOX_FRAC = 0.08
_ZOOM = 1.6


class RocketLaunchCutscene:
    """Cinematic played when the player fills a Rocket Silo."""

    def __init__(
        self, silo_coord, world, camera,
        on_finish: Callable[[], None],
    ) -> None:
        self.world = world
        self.camera = camera
        self._on_finish = on_finish
        self.active: bool = True
        self._done_called: bool = False

        size = world.settings.hex_size
        wx, wy = hex_to_pixel(silo_coord, size)
        self._target_wx: float = wx
        self._target_wy: float = wy
        self._silo_coord = silo_coord

        self._phase: str = _PHASE_PAN
        self._phase_t: float = 0.0

        # Tell the renderer to draw an empty launch pad here for
        # as long as the cutscene is active (so its own rocket
        # sprite isn't doubled up by the silo's static rocket art).
        world.launching_silo_coord = silo_coord

        # Stash camera state so we can restore on finish.
        self._return_zoom: float = camera._target_zoom
        self._return_x: float = camera.x
        self._return_y: float = camera.y
        self._pan_from: tuple[float, float] = (camera.x, camera.y)

        # Rocket vertical offset in *screen* pixels (grows negative as
        # it climbs off the top).
        self._rocket_y_offset: float = 0.0
        # Fade overlay alpha, 0..255.
        self._fade_alpha: float = 0.0
        # Title banner alpha ramp.
        self._title_alpha: float = 0.0

        self._title_font: pygame.font.Font | None = None
        self._subtitle_font: pygame.font.Font | None = None

    # ── Input ────────────────────────────────────────────────────

    def handle_event(self, event: pygame.event.Event) -> bool:
        if not self.active:
            return False
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            self._skip_to_end()
            return True
        return True  # swallow everything else while playing

    def _skip_to_end(self) -> None:
        self._phase = _PHASE_FADE
        self._phase_t = _FADE_TIME
        self._fade_alpha = 255.0
        self._finish()

    # ── Per-frame update ─────────────────────────────────────────

    def tick(self, dt: float) -> None:
        if not self.active:
            return
        # Lock in the cinematic zoom.
        self.camera._target_zoom = max(self.camera._target_zoom, _ZOOM)
        self._phase_t += dt
        if self._phase == _PHASE_PAN:
            self._update_pan()
        elif self._phase == _PHASE_IGNITE:
            self._update_ignite()
        elif self._phase == _PHASE_RISE:
            self._update_rise(dt)
        elif self._phase == _PHASE_FADE:
            self._update_fade()

    def _update_pan(self) -> None:
        t = min(1.0, self._phase_t / _PAN_TIME)
        e = t * t * (3 - 2 * t)
        self.camera.x = self._pan_from[0] + (self._target_wx - self._pan_from[0]) * e
        self.camera.y = self._pan_from[1] + (self._target_wy - self._pan_from[1]) * e
        self._title_alpha = e
        if t >= 1.0:
            self._phase = _PHASE_IGNITE
            self._phase_t = 0.0

    def _update_ignite(self) -> None:
        # Gentle camera shake + hold on silo.
        self._title_alpha = 1.0
        if self._phase_t >= _IGNITE_TIME:
            self._phase = _PHASE_RISE
            self._phase_t = 0.0

    def _update_rise(self, dt: float) -> None:
        t = min(1.0, self._phase_t / _RISE_TIME)
        # Ease-in: slow start, accelerating climb.
        accel = t * t
        # Screen height ~ 1000 px; climb 2000 px to fly well off-screen.
        self._rocket_y_offset = -accel * 2000.0
        self._title_alpha = 1.0 - t * 0.3
        if t >= 1.0:
            self._phase = _PHASE_FADE
            self._phase_t = 0.0

    def _update_fade(self) -> None:
        t = min(1.0, self._phase_t / _FADE_TIME)
        self._fade_alpha = 255.0 * t
        if t >= 1.0:
            self._finish()

    def _finish(self) -> None:
        if self._done_called:
            return
        self._done_called = True
        self.active = False
        self.camera._target_zoom = self._return_zoom
        # Clear the renderer hint so any future re-render of the silo
        # (e.g. the win screen behind the fade) stays consistent.
        if getattr(self.world, "launching_silo_coord", None) == self._silo_coord:
            self.world.launching_silo_coord = None
        self._on_finish()

    # ── Overlay drawing ──────────────────────────────────────────

    def draw_overlay(self, surface: pygame.Surface) -> None:
        if not self.active and self._fade_alpha <= 0:
            return
        sw, sh = surface.get_size()

        # Letterbox bars, faded in with the title.
        bar_h = int(sh * _LETTERBOX_FRAC * max(0.0, min(1.0, self._title_alpha)))
        if bar_h > 0:
            pygame.draw.rect(surface, (0, 0, 0), (0, 0, sw, bar_h))
            pygame.draw.rect(surface, (0, 0, 0), (0, sh - bar_h, sw, bar_h))

        # Rocket sprite drawn at the silo's screen position.
        self._draw_rocket(surface, sw, sh)

        # Title banner
        if self._title_font is None:
            self._title_font = pygame.font.Font(None, 72)
            self._subtitle_font = pygame.font.Font(None, 28)
        alpha = int(255 * max(0.0, min(1.0, self._title_alpha)))
        if alpha > 8:
            title = self._title_font.render(
                ROCKET_LAUNCH_TITLE, True, (240, 240, 255),
            )
            title.set_alpha(alpha)
            tx = (sw - title.get_width()) // 2
            ty = bar_h + max(8, sh // 14)
            surface.blit(title, (tx, ty))
            sub = self._subtitle_font.render(
                ROCKET_LAUNCH_SUBTITLE, True, (200, 210, 230),
            )
            sub.set_alpha(alpha)
            sx = (sw - sub.get_width()) // 2
            surface.blit(sub, (sx, ty + title.get_height() + 4))

        # Skip hint
        if self._subtitle_font is not None and self._phase != _PHASE_FADE:
            hint = self._subtitle_font.render(
                ROCKET_LAUNCH_SKIP_HINT, True, (180, 180, 200),
            )
            hint.set_alpha(int(180 * self._title_alpha))
            surface.blit(hint, (sw - hint.get_width() - 12,
                                sh - hint.get_height() - 12))

        # Full-screen white fade at the end.
        if self._fade_alpha > 0:
            fade = pygame.Surface((sw, sh))
            fade.fill((255, 255, 255))
            fade.set_alpha(int(max(0.0, min(255.0, self._fade_alpha))))
            surface.blit(fade, (0, 0))

    def _draw_rocket(self, surface: pygame.Surface, sw: int, sh: int) -> None:
        """Draw a simple rocket at the silo's on-screen position with
        the current vertical offset applied.  Intentionally vector-
        drawn so it works without extra sprite assets."""
        # Convert silo world coord → screen space.
        scr_x, scr_y = self.camera.world_to_screen(
            self._target_wx, self._target_wy,
        )
        # Add a tiny shake during the ignite phase.
        shake_x = 0.0
        if self._phase == _PHASE_IGNITE:
            import math
            shake_x = math.sin(self._phase_t * 60.0) * 3.0
        cx = scr_x + shake_x
        cy = scr_y + self._rocket_y_offset

        # Rocket body — a tall rounded capsule.
        body_w = 28
        body_h = 70
        body_rect = pygame.Rect(int(cx - body_w / 2), int(cy - body_h),
                                body_w, body_h)
        pygame.draw.rect(surface, (220, 220, 230), body_rect, border_radius=10)
        # Nose cone (triangle).
        nose_h = 26
        nose_points = [
            (cx, cy - body_h - nose_h),
            (cx - body_w / 2, cy - body_h + 4),
            (cx + body_w / 2, cy - body_h + 4),
        ]
        pygame.draw.polygon(surface, (200, 80, 80), nose_points)
        # Window.
        pygame.draw.circle(surface, (120, 180, 230),
                           (int(cx), int(cy - body_h + 22)), 6)
        pygame.draw.circle(surface, (40, 60, 100),
                           (int(cx), int(cy - body_h + 22)), 6, 2)
        # Fins.
        fin_col = (180, 60, 60)
        pygame.draw.polygon(surface, fin_col, [
            (cx - body_w / 2, cy - 8),
            (cx - body_w / 2 - 14, cy + 8),
            (cx - body_w / 2, cy + 2),
        ])
        pygame.draw.polygon(surface, fin_col, [
            (cx + body_w / 2, cy - 8),
            (cx + body_w / 2 + 14, cy + 8),
            (cx + body_w / 2, cy + 2),
        ])

        # Exhaust plume — only during ignite/rise phases.
        if self._phase in (_PHASE_IGNITE, _PHASE_RISE):
            import math
            plume_t = self._phase_t
            flicker = 1.0 + 0.2 * math.sin(plume_t * 40.0)
            base_len = 40 if self._phase == _PHASE_IGNITE else 90
            plume_len = base_len * flicker
            plume_w = body_w * 0.9
            # Outer orange plume.
            pygame.draw.polygon(surface, (255, 150, 60), [
                (cx - plume_w / 2, cy),
                (cx + plume_w / 2, cy),
                (cx, cy + plume_len),
            ])
            # Inner yellow core.
            pygame.draw.polygon(surface, (255, 230, 120), [
                (cx - plume_w / 3, cy),
                (cx + plume_w / 3, cy),
                (cx, cy + plume_len * 0.7),
            ])
