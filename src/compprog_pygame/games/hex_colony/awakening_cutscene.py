"""Mid-game cutscene played when an ancient awakening fires.

Pans the camera to each tower-coordinate, shows the tower rising out
of the ground, then converts the surrounding hexes to wasteland (also
deleting any buildings caught in the radius).  When the cutscene
finishes the towers are committed to the world and the game resumes.

The cutscene runs *inside* the game loop — game.py routes per-frame
control to ``AwakeningCutscene.tick`` instead of the normal world
update while ``cutscene.active`` is True.  The renderer continues to
draw the world (so the player sees the actual changes happening).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable

import pygame

from compprog_pygame.games.hex_colony import params
from compprog_pygame.games.hex_colony.ancient_threat import (
    AncientTower, AwakeningEvent,
)
from compprog_pygame.games.hex_colony.hex_grid import hex_to_pixel


_PHASE_INTRO = "intro"      # screen rumble + dim, no camera move yet
_PHASE_PAN = "pan"          # camera flies to next tower coord
_PHASE_RISE = "rise"        # tower scales up, then wasteland applied
_PHASE_HOLD = "hold"        # brief pause to let player see the damage
_PHASE_OUTRO = "outro"      # camera fades back / returns control
_PHASE_DONE = "done"


@dataclass
class _Subject:
    tower: AncientTower
    target_wx: float
    target_wy: float


class AwakeningCutscene:
    """Cinematic that introduces the towers spawned by an awakening."""

    def __init__(
        self, event: AwakeningEvent, world, camera,
        on_apply_tower: Callable[[AncientTower], None],
        on_commit_tower: Callable[[AncientTower], None],
        on_finish: Callable[[], None],
    ) -> None:
        self.event = event
        self.world = world
        self.camera = camera
        self._on_apply = on_apply_tower
        self._on_commit = on_commit_tower
        self._on_finish = on_finish
        self.active: bool = True

        size = world.settings.hex_size
        self._subjects: list[_Subject] = []
        for coord in event.tower_coords:
            wx, wy = hex_to_pixel(coord, size)
            self._subjects.append(_Subject(
                tower=AncientTower(coord=coord,
                                   radius=params.AWAKENING_TOWER_RADIUS,
                                   rise_progress=0.0),
                target_wx=wx, target_wy=wy,
            ))

        self._index: int = 0  # which subject is being processed
        self._phase: str = _PHASE_INTRO
        self._phase_t: float = 0.0
        # Stash the camera state so we can restore it at the end.
        self._return_zoom: float = camera._target_zoom
        self._return_x: float = camera.x
        self._return_y: float = camera.y
        self._pan_from: tuple[float, float] = (camera.x, camera.y)
        # Title banner timing
        self._title_alpha: float = 0.0
        self._title_font: pygame.font.Font | None = None
        self._subtitle_font: pygame.font.Font | None = None
        # Has the wasteland been applied for the current subject yet?
        self._damage_applied: bool = False

    # ── Skip / input ─────────────────────────────────────────────

    def handle_event(self, event: pygame.event.Event) -> bool:
        """Return True if the event was consumed by the cutscene."""
        if not self.active:
            return False
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            self._skip_to_end()
            return True
        return True  # swallow everything else while playing

    def _skip_to_end(self) -> None:
        """Apply any unprocessed towers and finish."""
        for sub in self._subjects[self._index:]:
            sub.tower.rise_progress = 1.0
            self._on_apply(sub.tower)
            self._on_commit(sub.tower)
        self._index = len(self._subjects)
        self._phase = _PHASE_OUTRO
        self._phase_t = params.AWAKENING_OUTRO_TIME

    # ── Per-frame update ─────────────────────────────────────────

    def tick(self, dt: float) -> None:
        if not self.active:
            return
        # Keep zoom locked tighter so the towers feel monumental.
        self.camera._target_zoom = max(self.camera._target_zoom,
                                       params.AWAKENING_ZOOM)
        self._phase_t += dt
        if self._phase == _PHASE_INTRO:
            self._title_alpha = min(1.0, self._phase_t /
                                    params.AWAKENING_INTRO_TIME)
            if self._phase_t >= params.AWAKENING_INTRO_TIME:
                self._begin_pan_to_current()
        elif self._phase == _PHASE_PAN:
            self._update_pan()
        elif self._phase == _PHASE_RISE:
            self._update_rise(dt)
        elif self._phase == _PHASE_HOLD:
            if self._phase_t >= params.AWAKENING_HOLD_TIME:
                self._advance_subject()
        elif self._phase == _PHASE_OUTRO:
            self._title_alpha = max(0.0, 1.0 - self._phase_t /
                                    params.AWAKENING_OUTRO_TIME)
            self._update_outro()
            if self._phase_t >= params.AWAKENING_OUTRO_TIME:
                self._finish()

    def _begin_pan_to_current(self) -> None:
        if self._index >= len(self._subjects):
            self._begin_outro()
            return
        self._pan_from = (self.camera.x, self.camera.y)
        self._phase = _PHASE_PAN
        self._phase_t = 0.0
        self._damage_applied = False

    def _update_pan(self) -> None:
        sub = self._subjects[self._index]
        t = min(1.0, self._phase_t / params.AWAKENING_PAN_TIME)
        # Ease in/out
        e = t * t * (3 - 2 * t)
        self.camera.x = self._pan_from[0] + (sub.target_wx - self._pan_from[0]) * e
        self.camera.y = self._pan_from[1] + (sub.target_wy - self._pan_from[1]) * e
        if t >= 1.0:
            self._phase = _PHASE_RISE
            self._phase_t = 0.0

    def _update_rise(self, dt: float) -> None:
        sub = self._subjects[self._index]
        rise_total = params.AWAKENING_RISE_TIME
        prog = min(1.0, self._phase_t / rise_total)
        # Ease-out so the tower bursts up fast then settles.
        sub.tower.rise_progress = 1.0 - (1.0 - prog) ** 2

        # Apply wasteland at ~70 % of the rise — the moment the tower
        # is mostly out — so the destruction is visible while the
        # camera is still on it.
        if not self._damage_applied and prog >= 0.7:
            self._on_apply(sub.tower)
            self._damage_applied = True

        if prog >= 1.0:
            sub.tower.rise_progress = 1.0
            if not self._damage_applied:
                self._on_apply(sub.tower)
                self._damage_applied = True
            self._on_commit(sub.tower)
            self._phase = _PHASE_HOLD
            self._phase_t = 0.0

    def _advance_subject(self) -> None:
        self._index += 1
        if self._index >= len(self._subjects):
            self._begin_outro()
        else:
            self._begin_pan_to_current()

    def _begin_outro(self) -> None:
        self._phase = _PHASE_OUTRO
        self._phase_t = 0.0
        self._pan_from = (self.camera.x, self.camera.y)

    def _update_outro(self) -> None:
        t = min(1.0, self._phase_t / params.AWAKENING_OUTRO_TIME)
        e = t * t * (3 - 2 * t)
        self.camera.x = self._pan_from[0] + (self._return_x - self._pan_from[0]) * e
        self.camera.y = self._pan_from[1] + (self._return_y - self._pan_from[1]) * e
        # Restore zoom toward the player's original setting.
        self.camera._target_zoom = (
            params.AWAKENING_ZOOM
            + (self._return_zoom - params.AWAKENING_ZOOM) * e
        )

    def _finish(self) -> None:
        self.active = False
        self.camera._target_zoom = self._return_zoom
        # Spawn the combat wave associated with this awakening.  We do
        # this *before* ``_on_finish`` so the awakening_index in the
        # threat module hasn't been bumped yet — the combat manager
        # uses ``self.event.tower_coords`` directly anyway.
        try:
            tower_coords = [s.tower.coord for s in self._subjects]
            self.world.combat.spawn_awakening_wave(self.world, tower_coords)
        except Exception:
            pass
        self._on_finish()

    # ── Overlay drawing ──────────────────────────────────────────

    def draw_overlay(self, surface: pygame.Surface) -> None:
        """Letterbox bars + title text on top of the world render."""
        if not self.active:
            return
        sw, sh = surface.get_size()

        # Letterbox bars — solid bars top/bottom, slide in during intro
        # and back out during outro.  Use the title alpha as the slide
        # factor so all three animate together.
        bar_h = int(sh * params.AWAKENING_LETTERBOX_FRAC * self._title_alpha)
        if bar_h > 0:
            pygame.draw.rect(surface, (0, 0, 0), (0, 0, sw, bar_h))
            pygame.draw.rect(surface, (0, 0, 0), (0, sh - bar_h, sw, bar_h))
            # Faint magenta accent line
            line_col = (160, 60, 200)
            pygame.draw.line(surface, line_col, (0, bar_h), (sw, bar_h), 1)
            pygame.draw.line(surface, line_col,
                             (0, sh - bar_h - 1), (sw, sh - bar_h - 1), 1)

        # Title banner during intro/outro and brief banner per tower
        if self._title_font is None:
            self._title_font = pygame.font.Font(None, 64)
            self._subtitle_font = pygame.font.Font(None, 26)

        alpha = int(255 * self._title_alpha)
        if alpha > 8:
            title = self._title_font.render(
                params.AWAKENING_TITLE_TEXT, True, (240, 200, 255),
            )
            title.set_alpha(alpha)
            tx = (sw - title.get_width()) // 2
            ty = bar_h + max(8, sh // 14)
            surface.blit(title, (tx, ty))

            sub = self._subtitle_font.render(
                params.AWAKENING_SUBTITLE_TEXT, True, (200, 180, 220),
            )
            sub.set_alpha(alpha)
            sx = (sw - sub.get_width()) // 2
            surface.blit(sub, (sx, ty + title.get_height() + 4))

        # Tiny "skip" hint in the corner.
        if self._title_font is not None and self._phase != _PHASE_OUTRO:
            hint_font = self._subtitle_font
            assert hint_font is not None
            hint = hint_font.render(
                params.AWAKENING_SKIP_HINT, True, (180, 180, 200),
            )
            hint.set_alpha(int(180 * self._title_alpha))
            surface.blit(hint, (sw - hint.get_width() - 12,
                                sh - hint.get_height() - 12))
