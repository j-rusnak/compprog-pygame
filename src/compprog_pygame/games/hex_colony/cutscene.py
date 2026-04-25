"""Intro cutscene played while the world generates in the background.

The cutscene shows the survivors' ship in space, has the captain and
scientist exchange dialog, then takes a mysterious hit and crashes to
Earth as the screen fades to black.

The cutscene runs entirely on the main thread; world generation happens
on a worker thread (see :mod:`__init__._launch`).  The cutscene blocks
the final transition until the world has finished generating, so the
player never sees a black "loading" screen.

No regular game UI is shown during the cutscene — only the dialog box
and a small "click to continue" mouse hint.
"""

from __future__ import annotations

import math
import random as _random
from dataclasses import dataclass
from typing import Callable

import pygame

from compprog_pygame.games.hex_colony.sprites import sprites
from compprog_pygame.settings import ASSET_DIR


# ── Dialog script ────────────────────────────────────────────────

# Each beat: (speaker_name, text, ship_state, side)
#   ship_state: "intact" | "damaged"
#   side:       "left"   | "right"  — which side of the screen the
#               speaker portrait appears on
_DIALOG: list[tuple[str, str, str, str]] = [
    ("Captain",
     "Captain's log: after three long years adrift, our long-range "
     "scanners finally caught a glimpse of Earth.",
     "intact", "left"),
    ("Scientist",
     "Atmospheric readings match the historical archives, Captain. "
     "We really did make it home.",
     "intact", "right"),
    ("Captain",
     "Take her in slow, Doctor. I'd like a proper look before we set "
     "down and have ourselves a wander.",
     "intact", "left"),
    # ── impact ──
    ("Captain",
     "Whoa — what in the void was THAT?!",
     "damaged", "left"),
    ("Scientist",
     "Multiple hull breaches! Engines two and three are gone — "
     "I think we're going down!",
     "damaged", "right"),
    ("Captain",
     "Brace for impact!!",
     "damaged", "left"),
]


# ── Phase constants ──────────────────────────────────────────────

_PHASE_FADE_IN = "fade_in"    # fade up from black into the establishing shot
_PHASE_OPENING = "opening"     # brief hold on the establishing shot
_PHASE_DIALOG = "dialog"       # cycling through _DIALOG
_PHASE_IMPACT_FLASH = "impact"  # white flash between beats 3 and 4
_PHASE_CRASHING = "crashing"   # ship falls, screen shakes
_PHASE_FADING = "fading"       # fade to black
_PHASE_DONE = "done"

_FADE_IN_TIME = 1.2
_OPENING_HOLD = 2.0     # seconds
_MIN_BEAT_TIME = 0.6    # min seconds before a click can advance
_IMPACT_FLASH_TIME = 0.55
_CRASH_TIME = 3.6
_FADE_TIME = 1.6
_BEAT_INDEX_OF_IMPACT = 3  # the first "damaged" beat — flash happens before it

# How far the ship is offset to the left of centre, as a fraction of
# screen width.  Negative = leftwards.
_SHIP_X_OFFSET_FRAC = -0.06
# Ship width as a fraction of screen width.  Slightly larger than the
# previous 0.42 for more presence on screen.
_SHIP_WIDTH_FRAC = 0.50

# Earth position in the background sprite, as fractions of screen.
# These mirror ``tools/generate_cutscene_sprites.make_space_bg`` where
# Earth is rendered in the upper-right of the frame.
_EARTH_X_FRAC = 0.70
_EARTH_Y_FRAC = 0.35
_EARTH_R_FRAC = 0.24  # of min(w, h)
# Background zoom-in during the crash + fade phases.  1.0 = no zoom.
_BG_ZOOM_END = 2.4


@dataclass
class _DialogBox:
    rect: pygame.Rect
    name_font: pygame.font.Font
    body_font: pygame.font.Font
    hint_font: pygame.font.Font

    def draw(
        self,
        surface: pygame.Surface,
        speaker: str,
        text: str,
        click_alpha: int,
    ) -> None:
        # Translucent panel.
        panel = pygame.Surface(self.rect.size, pygame.SRCALPHA)
        panel.fill((10, 14, 24, 215))
        pygame.draw.rect(panel, (200, 210, 230, 255),
                         panel.get_rect(), 2, border_radius=8)
        surface.blit(panel, self.rect.topleft)

        # Speaker name (top-left of the panel).
        name_surf = self.name_font.render(
            speaker, True, (240, 220, 130),
        )
        surface.blit(
            name_surf,
            (self.rect.x + 22, self.rect.y + 12),
        )

        # Wrap the body text to the panel width.
        body_x = self.rect.x + 22
        body_y = self.rect.y + 12 + name_surf.get_height() + 8
        body_w = self.rect.width - 44 - 80  # leave room for the click icon
        line_h = self.body_font.get_linesize()
        for line in _wrap(text, self.body_font, body_w):
            surface.blit(
                self.body_font.render(line, True, (235, 235, 245)),
                (body_x, body_y),
            )
            body_y += line_h

        # Click-to-continue hint (icon + text), bottom-right of the panel.
        icon_sheet = sprites.get("cutscene/click_icon")
        icon_w, icon_h = 36, 46
        if icon_sheet is not None:
            icon = icon_sheet.get(icon_w, icon_h).copy()
            icon.set_alpha(click_alpha)
            surface.blit(
                icon,
                (self.rect.right - 22 - icon_w,
                 self.rect.bottom - 14 - icon_h),
            )
        hint = self.hint_font.render(
            "click to continue", True, (180, 190, 210),
        )
        hint.set_alpha(click_alpha)
        surface.blit(
            hint,
            (self.rect.right - 22 - icon_w - hint.get_width() - 10,
             self.rect.bottom - 14 - icon_h // 2 - hint.get_height() // 2),
        )


def _wrap(text: str, font: pygame.font.Font, max_width: int) -> list[str]:
    """Word-wrap ``text`` to fit within ``max_width`` pixels."""
    words = text.split()
    lines: list[str] = []
    line = ""
    for word in words:
        candidate = word if not line else f"{line} {word}"
        if font.size(candidate)[0] <= max_width:
            line = candidate
        else:
            if line:
                lines.append(line)
            line = word
    if line:
        lines.append(line)
    return lines


class IntroCutscene:
    """Drive the intro sequence — call ``update``/``draw`` every frame.

    The cutscene runs to completion on its own schedule (no longer
    blocked by world readiness).  After it ends the caller is
    responsible for showing a loading screen if the world isn't ready.
    """

    def __init__(self, screen_size: tuple[int, int]) -> None:
        self.w, self.h = screen_size
        self.done: bool = False

        # Phase / timing.
        self._phase: str = _PHASE_FADE_IN
        self._phase_t: float = 0.0
        self._beat_index: int = 0
        self._beat_t: float = 0.0
        self._total_t: float = 0.0

        # Visuals.
        self._ship_offset = (0.0, 0.0)
        self._ship_rot = 0.0
        self._ship_extra_scale = 1.0  # subtle breathing during dialog
        # Crash-specific visual state: how much smaller the ship is
        # relative to its idle size (1.0 → full, 0.0 → vanished),
        # and the absolute pixel position to draw it at instead of the
        # default centre-derived coordinates.
        self._crash_scale = 1.0
        self._crash_pos: tuple[float, float] | None = None
        # Background zoom (1.0 = no zoom).  Centred on Earth.
        self._bg_zoom = 1.0
        self._shake = 0.0
        self._flash_alpha = 0.0
        self._fade_alpha = 0.0
        # Smoothed shake — interpolated toward ``_shake`` so the
        # wobble doesn't pop on/off between phases.
        self._shake_smooth = 0.0
        # Dialog-box slide-in progress (0..1).  Reset every beat so a
        # new line gracefully eases in instead of popping.
        self._dialog_anim = 0.0
        # Pre-rolled debris particles spawned during the crash.
        self._debris: list[dict] = []

        # Fonts.
        self._name_font = pygame.font.Font(None, 32)
        self._body_font = pygame.font.Font(None, 26)
        self._hint_font = pygame.font.Font(None, 18)

        # Dialog box near the bottom of the screen.
        box_w = min(int(self.w * 0.78), 1100)
        box_h = 170
        self._dialog = _DialogBox(
            rect=pygame.Rect(
                (self.w - box_w) // 2,
                self.h - box_h - 40,
                box_w, box_h,
            ),
            name_font=self._name_font,
            body_font=self._body_font,
            hint_font=self._hint_font,
        )
        self._rng = _random.Random(20240419)

    def resize(self, screen_size: tuple[int, int]) -> None:
        """Adapt to a new screen size mid-cutscene.

        Called from :func:`run_cutscene` whenever the window is
        resized (or toggled fullscreen) so the ship/dialog stay
        centred and properly scaled.  Phase, timing, and beat index
        are preserved — only layout-dependent state is recomputed.
        """
        new_w, new_h = screen_size
        if new_w <= 0 or new_h <= 0:
            return
        if (new_w, new_h) == (self.w, self.h):
            return
        self.w, self.h = new_w, new_h
        # Re-anchor the dialog box.
        box_w = min(int(self.w * 0.78), 1100)
        box_h = 170
        self._dialog.rect = pygame.Rect(
            (self.w - box_w) // 2,
            self.h - box_h - 40,
            box_w, box_h,
        )

    # ── Public API ────────────────────────────────────────────────

    def handle_event(self, event: pygame.event.Event) -> None:
        if self._phase == _PHASE_DIALOG and self._beat_t >= _MIN_BEAT_TIME:
            advance = (
                event.type == pygame.MOUSEBUTTONDOWN and event.button == 1
            ) or (
                event.type == pygame.KEYDOWN
                and event.key in (pygame.K_RETURN, pygame.K_SPACE,
                                  pygame.K_ESCAPE)
            )
            if advance:
                self._advance_beat()

    def update(self, dt: float) -> None:
        self._total_t += dt
        self._phase_t += dt
        if self._phase == _PHASE_DIALOG:
            self._beat_t += dt
            # Ease the dialog box in over ~0.35s.
            self._dialog_anim = min(1.0, self._dialog_anim + dt / 0.35)

        # Idle ship animation: a gentle bob + sway + breathing scale
        # while the ship is intact.  After the impact the ship
        # trembles instead until the crash phase takes over.
        if self._phase in (_PHASE_FADE_IN, _PHASE_OPENING, _PHASE_DIALOG,
                           _PHASE_IMPACT_FLASH):
            if self._current_ship_state() == "intact":
                bob_y = math.sin(self._total_t * 1.1) * 6.0
                sway_x = math.sin(self._total_t * 0.7) * 4.0
                self._ship_offset = (sway_x, bob_y)
                self._ship_rot = math.sin(self._total_t * 0.9) * 1.5
                # Keep the ship at a constant scale during the
                # idle hover — size pulsing read as a rendering
                # bug rather than "alive".
                self._ship_extra_scale = 1.0
            else:
                # Damaged but pre-crash: jittery, listing to one side.
                tremor_x = math.sin(self._total_t * 11.0) * 3.5
                tremor_y = math.sin(self._total_t * 13.0 + 0.7) * 2.5
                self._ship_offset = (tremor_x - 6.0, tremor_y + 4.0)
                self._ship_rot = -3.0 + math.sin(
                    self._total_t * 6.0,
                ) * 1.5
                self._ship_extra_scale = 1.0

        if self._phase == _PHASE_FADE_IN:
            t = min(1.0, self._phase_t / _FADE_IN_TIME)
            # Ease-out cubic so the fade settles gently.
            eased = 1.0 - (1.0 - t) ** 3
            self._fade_alpha = 255 * (1.0 - eased)
            if self._phase_t >= _FADE_IN_TIME:
                self._fade_alpha = 0.0
                self._enter_phase(_PHASE_OPENING)

        elif self._phase == _PHASE_OPENING:
            if self._phase_t >= _OPENING_HOLD:
                self._enter_phase(_PHASE_DIALOG)
                self._beat_t = 0.0

        elif self._phase == _PHASE_IMPACT_FLASH:
            # Flash ramps up fast then decays (smooth ease-out).
            t = min(1.0, self._phase_t / _IMPACT_FLASH_TIME)
            self._flash_alpha = max(0.0, 255 * (1.0 - t * t))
            self._shake = 18.0 * max(0.0, 1.0 - t * 1.4)
            if self._phase_t >= _IMPACT_FLASH_TIME:
                self._flash_alpha = 0.0
                self._shake = 0.0
                self._enter_phase(_PHASE_DIALOG)
                self._beat_t = 0.0
                self._dialog_anim = 0.0

        elif self._phase == _PHASE_CRASHING:
            t = min(1.0, self._phase_t / _CRASH_TIME)
            # Trajectory: ease the ship from its current screen
            # position toward the centre of Earth in the background,
            # while shrinking it so it appears to fly into the
            # distance.  We sample the *idle* anchor (centre + offset)
            # as the start point so the curve always begins where the
            # ship was last drawn during dialog.
            start_x = (
                self.w / 2.0 + self.w * _SHIP_X_OFFSET_FRAC
            )
            start_y = self.h * 0.42
            earth_x = self.w * _EARTH_X_FRAC
            earth_y = self.h * _EARTH_Y_FRAC
            # Ease-in-out cubic on the path so it accelerates and then
            # settles into Earth.
            if t < 0.5:
                eased = 4 * t * t * t
            else:
                eased = 1 - (-2 * t + 2) ** 3 / 2
            # Slight downward arc using a quadratic offset so the
            # ship dips before plunging in.
            arc = math.sin(t * math.pi) * self.h * 0.06
            self._crash_pos = (
                start_x + (earth_x - start_x) * eased,
                start_y + (earth_y - start_y) * eased + arc,
            )
            # Shrink to ~12 % of original size as it reaches Earth.
            self._crash_scale = 1.0 - 0.88 * eased
            # Tumbling: accelerating spin with a subtler wobble.
            self._ship_rot = -55.0 * t * t + math.sin(
                self._total_t * 9.0,
            ) * 1.5
            # Background zooms toward Earth simultaneously, telegraphing
            # where the game is going next.
            self._bg_zoom = 1.0 + (_BG_ZOOM_END - 1.0) * eased
            # Shake decays gradually instead of cutting off.
            self._shake = 22.0 * (1.0 - t) + 4.0
            # Spawn debris particles intermittently — from the ship's
            # current world position, not the idle anchor.
            if self._rng.random() < dt * 18.0:
                self._spawn_debris()
            self._update_debris(dt)
            if self._phase_t >= _CRASH_TIME:
                self._shake = 0.0
                self._enter_phase(_PHASE_FADING)

        elif self._phase == _PHASE_FADING:
            t = min(1.0, self._phase_t / _FADE_TIME)
            # Smoothstep so the fade starts slow and settles slow.
            eased = t * t * (3 - 2 * t)
            self._fade_alpha = 255 * eased
            # Continue easing the bg zoom from end-of-crash toward a
            # final, slightly tighter framing on Earth so the camera
            # feels like it's still pushing in as we cut to black.
            self._bg_zoom = _BG_ZOOM_END + 0.6 * eased
            self._update_debris(dt)
            if self._phase_t >= _FADE_TIME:
                self._fade_alpha = 255
                self._enter_phase(_PHASE_DONE)
                self.done = True

        # Smooth the shake value so it ramps in/out instead of popping.
        rate = 14.0
        a = 1.0 - math.exp(-rate * dt)
        self._shake_smooth += (self._shake - self._shake_smooth) * a

    def draw(self, screen: pygame.Surface) -> None:
        # Background — starfield + Earth.  When ``_bg_zoom`` > 1 we
        # crop a window around Earth and stretch it to the full screen
        # so the camera appears to push in toward the planet.
        bg = sprites.get("cutscene/space_bg")
        if bg is not None:
            full_bg = bg.get(self.w, self.h)
            if self._bg_zoom > 1.001:
                zoom = self._bg_zoom
                src_w = max(1, int(self.w / zoom))
                src_h = max(1, int(self.h / zoom))
                # Centre the crop on Earth in the source image, then
                # clamp so the window stays inside the bg surface.
                ex = int(self.w * _EARTH_X_FRAC)
                ey = int(self.h * _EARTH_Y_FRAC)
                src_x = max(0, min(self.w - src_w, ex - src_w // 2))
                src_y = max(0, min(self.h - src_h, ey - src_h // 2))
                sub = full_bg.subsurface(
                    pygame.Rect(src_x, src_y, src_w, src_h),
                )
                scaled = pygame.transform.smoothscale(
                    sub, (self.w, self.h),
                )
                screen.blit(scaled, (0, 0))
            else:
                screen.blit(full_bg, (0, 0))
        else:
            screen.fill((6, 10, 22))

        # Ship.
        ship_state = self._current_ship_state()
        ship_key = ("cutscene/ship_damaged"
                    if ship_state == "damaged" else "cutscene/ship")
        ship = sprites.get(ship_key)
        if ship is not None:
            base_sw = int(
                self.w * _SHIP_WIDTH_FRAC * self._ship_extra_scale
            )
            # Apply crash shrink (1.0 outside crash phase).
            sw = max(8, int(base_sw * self._crash_scale))
            sh = max(4, int(sw * 0.5))
            ship_surf = ship.get(sw, sh)
            if abs(self._ship_rot) > 0.05:
                ship_surf = pygame.transform.rotozoom(
                    ship_surf, self._ship_rot, 1.0,
                )
            if self._crash_pos is not None:
                cx = int(self._crash_pos[0])
                cy = int(self._crash_pos[1])
            else:
                cx = (
                    self.w // 2
                    + int(self.w * _SHIP_X_OFFSET_FRAC)
                    + int(self._ship_offset[0])
                )
                cy = int(self.h * 0.42) + int(self._ship_offset[1])
            if self._shake_smooth > 0.5:
                amp = int(self._shake_smooth)
                cx += self._rng.randint(-amp, amp)
                cy += self._rng.randint(-amp, amp)
            screen.blit(
                ship_surf,
                (cx - ship_surf.get_width() // 2,
                 cy - ship_surf.get_height() // 2),
            )

        # Debris drawn over the ship so chunks visibly fly off it.
        self._draw_debris(screen)

        # Dialog (only during dialog phases).
        if self._phase == _PHASE_DIALOG:
            speaker, text, _state, side = _DIALOG[self._beat_index]
            self._draw_portrait(screen, speaker, side)
            click_alpha = self._click_pulse_alpha()
            self._draw_animated_dialog(screen, speaker, text, click_alpha)

        # Impact flash.
        if self._flash_alpha > 0:
            flash = pygame.Surface((self.w, self.h), pygame.SRCALPHA)
            flash.fill((255, 240, 200, int(self._flash_alpha)))
            screen.blit(flash, (0, 0))

        # Fade overlay (used for both fade-in at the start and fade-out at
        # the end).
        if self._fade_alpha > 0:
            fade = pygame.Surface((self.w, self.h))
            fade.set_alpha(int(self._fade_alpha))
            fade.fill((0, 0, 0))
            screen.blit(fade, (0, 0))

    # ── Internals ─────────────────────────────────────────────────

    def _enter_phase(self, phase: str) -> None:
        self._phase = phase
        self._phase_t = 0.0

    def _advance_beat(self) -> None:
        next_index = self._beat_index + 1
        if next_index >= len(_DIALOG):
            self._enter_phase(_PHASE_CRASHING)
            self._beat_index = next_index  # past end so _current_ship_state stays "damaged"
            return
        # Trigger the impact flash immediately before the first damaged beat.
        if next_index == _BEAT_INDEX_OF_IMPACT:
            self._beat_index = next_index
            self._enter_phase(_PHASE_IMPACT_FLASH)
            self._flash_alpha = 255.0
            return
        self._beat_index = next_index
        self._beat_t = 0.0
        self._dialog_anim = 0.0

    def _current_ship_state(self) -> str:
        if self._phase in (_PHASE_OPENING,):
            return "intact"
        if self._beat_index < _BEAT_INDEX_OF_IMPACT:
            return "intact"
        return "damaged"

    def _click_pulse_alpha(self) -> int:
        if self._beat_t < _MIN_BEAT_TIME:
            return 0
        # Soft pulse 120..255.
        t = (self._beat_t - _MIN_BEAT_TIME) * 2.0
        return int(170 + 85 * (0.5 + 0.5 * math.sin(t * math.pi)))

    def _draw_portrait(
        self, screen: pygame.Surface, speaker: str, side: str,
    ) -> None:
        # After the ship takes the hit, switch the portrait to the
        # "_scared" variant so the survivors visibly react.  Fall back
        # to the calm portrait if the scared sprite isn't shipped.
        scared = self._current_ship_state() == "damaged"
        base = "cutscene/captain" if speaker == "Captain" else "cutscene/scientist"
        key = base + "_scared" if scared else base
        sheet = sprites.get(key)
        if sheet is None:
            sheet = sprites.get(base)
        if sheet is None:
            return
        size = 200
        portrait = sheet.get(size, size)
        # Place above the dialog box, on the indicated side.
        margin = 60
        py = self._dialog.rect.top - size - 12
        if side == "left":
            px = self._dialog.rect.left + margin
        else:
            px = self._dialog.rect.right - margin - size
        # Soft drop shadow / panel behind the portrait.
        bg = pygame.Surface((size + 16, size + 16), pygame.SRCALPHA)
        pygame.draw.circle(
            bg, (10, 14, 24, 180),
            (bg.get_width() // 2, bg.get_height() // 2),
            size // 2 + 6,
        )
        screen.blit(bg, (px - 8, py - 8))
        screen.blit(portrait, (px, py))

    # ── Debris particles ─────────────────────────────────────────

    def _spawn_debris(self) -> None:
        # Use the live crash position when available so debris tracks
        # the ship as it shrinks toward Earth.
        if self._crash_pos is not None:
            cx = int(self._crash_pos[0])
            cy = int(self._crash_pos[1])
        else:
            cx = self.w // 2 + int(self.w * _SHIP_X_OFFSET_FRAC) + int(
                self._ship_offset[0],
            )
            cy = int(self.h * 0.42) + int(self._ship_offset[1])
        # Spread scales with the ship's current visual size so debris
        # doesn't appear far away from the (now tiny) ship.
        spread = max(
            6,
            int(self.w * _SHIP_WIDTH_FRAC * 0.35 * self._crash_scale),
        )
        x = cx + self._rng.randint(-spread, spread)
        y = cy + self._rng.randint(-int(spread * 0.2), int(spread * 0.2))
        # Velocity: mostly outward & downward, with some upward kick.
        vx = self._rng.uniform(-260.0, 80.0)
        vy = self._rng.uniform(-220.0, 60.0)
        self._debris.append({
            "x": float(x), "y": float(y),
            "vx": vx, "vy": vy,
            "size": self._rng.randint(3, 7),
            "color": self._rng.choice([
                (220, 200, 170), (180, 150, 110),
                (240, 180, 90), (160, 140, 120),
            ]),
            "life": 1.6,
            "age": 0.0,
        })

    def _update_debris(self, dt: float) -> None:
        gravity = 520.0
        alive: list[dict] = []
        for d in self._debris:
            d["age"] += dt
            if d["age"] >= d["life"]:
                continue
            d["vy"] += gravity * dt
            d["x"] += d["vx"] * dt
            d["y"] += d["vy"] * dt
            alive.append(d)
        self._debris = alive

    def _draw_debris(self, screen: pygame.Surface) -> None:
        for d in self._debris:
            t = d["age"] / d["life"]
            alpha = max(0, int(255 * (1.0 - t)))
            size = max(1, int(d["size"] * (1.0 - t * 0.4)))
            surf = pygame.Surface((size * 2, size * 2), pygame.SRCALPHA)
            pygame.draw.circle(
                surf, (*d["color"], alpha), (size, size), size,
            )
            screen.blit(
                surf,
                (int(d["x"] - size), int(d["y"] - size)),
            )

    # ── Animated dialog box wrapper ──────────────────────────────

    def _draw_animated_dialog(
        self,
        screen: pygame.Surface,
        speaker: str,
        text: str,
        click_alpha: int,
    ) -> None:
        """Wrap :meth:`_DialogBox.draw` with a slide-up + fade-in
        animation driven by ``self._dialog_anim`` (0..1)."""
        anim = max(0.0, min(1.0, self._dialog_anim))
        # Ease-out cubic for both translation and alpha.
        eased = 1.0 - (1.0 - anim) ** 3
        if eased >= 0.999:
            self._dialog.draw(screen, speaker, text, click_alpha)
            return
        offset_y = int((1.0 - eased) * 32)
        alpha = int(255 * eased)
        layer = pygame.Surface(
            (self._dialog.rect.width, self._dialog.rect.height + 64),
            pygame.SRCALPHA,
        )
        # Render the dialog into the layer at (0, 32) so the
        # translucency multiplies correctly.
        tmp_surface = pygame.Surface(
            (self.w, self.h), pygame.SRCALPHA,
        )
        # Temporarily move the dialog rect to draw into ``tmp_surface``.
        original_rect = self._dialog.rect
        self._dialog.rect = pygame.Rect(0, 0, original_rect.width, original_rect.height)
        self._dialog.draw(tmp_surface, speaker, text, click_alpha)
        self._dialog.rect = original_rect
        layer.blit(tmp_surface, (0, 0))
        layer.set_alpha(alpha)
        screen.blit(
            layer,
            (original_rect.x, original_rect.y + offset_y),
        )


def run_cutscene(
    screen: pygame.Surface,
    clock: pygame.time.Clock,
    *,
    fps: int = 60,
) -> bool:
    """Blocking helper — run the cutscene loop until it finishes.

    Returns ``True`` if the cutscene completed normally, or ``False`` if
    the player closed the window (the caller should propagate quit).

    The cutscene listens for ``pygame.VIDEORESIZE`` events so the
    player can switch fullscreen / resize the window mid-cutscene
    without breaking the layout.
    """
    # Local import so the cutscene module stays a leaf with no upward
    # package dependencies.
    from compprog_pygame.audio import music
    music.play("cutscene")
    cutscene = IntroCutscene(screen.get_size())
    while not cutscene.done:
        dt = clock.tick(fps) / 1000.0
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return False
            if event.type == pygame.VIDEORESIZE:
                # The display surface has already been resized by
                # pygame; sync the cutscene to the new dimensions.
                surf = pygame.display.get_surface()
                if surf is not None:
                    cutscene.resize(surf.get_size())
                continue
            cutscene.handle_event(event)
        # Belt-and-braces: also catch fullscreen toggles or DPI shifts
        # that don't fire VIDEORESIZE on every platform.
        if screen.get_size() != (cutscene.w, cutscene.h):
            cutscene.resize(screen.get_size())
        cutscene.update(min(dt, 0.05))
        cutscene.draw(screen)
        pygame.display.flip()
    return True


def fade_to_black(
    screen: pygame.Surface,
    clock: pygame.time.Clock,
    *,
    duration: float = 0.5,
    fps: int = 60,
) -> bool:
    """Fade whatever is currently on screen to solid black.

    Returns ``False`` if the player quit during the fade.
    """
    snapshot = screen.copy()
    overlay = pygame.Surface(screen.get_size())
    overlay.fill((0, 0, 0))
    elapsed = 0.0
    while elapsed < duration:
        dt = clock.tick(fps) / 1000.0
        elapsed += dt
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return False
        t = min(1.0, elapsed / duration)
        screen.blit(snapshot, (0, 0))
        overlay.set_alpha(int(255 * t))
        screen.blit(overlay, (0, 0))
        pygame.display.flip()
    screen.fill((0, 0, 0))
    pygame.display.flip()
    return True


def run_loading_screen(
    screen: pygame.Surface,
    clock: pygame.time.Clock,
    is_world_ready: Callable[[], bool],
    *,
    fps: int = 60,
    min_duration: float = 0.4,
    progress: Callable[[], float] | None = None,
    label: Callable[[], str] | None = None,
) -> bool:
    """Show a real progress bar until ``is_world_ready()`` is True.

    *progress* (if provided) returns the current generation progress as
    a float in [0.0, 1.0].  *label* (if provided) returns a short
    status string shown under the bar (e.g. "Carving rivers").  When
    no progress callback is supplied the bar fills smoothly over the
    minimum duration so the player still sees motion.

    Always shows at least one frame (and ``min_duration`` seconds total)
    so the player sees clear feedback even if the world finishes very
    quickly.

    Returns ``False`` if the player quit, ``True`` otherwise.
    """
    sub_font = pygame.font.Font(None, 28)
    pct_font = pygame.font.Font(None, 26)
    status_font = pygame.font.Font(None, 22)

    # ── Load and prepare the themed splash artwork ───────────────
    splash_raw: pygame.Surface | None = None
    try:
        splash_raw = pygame.image.load(
            str(ASSET_DIR / "sprites" / "repioneer_landscape.png")
        ).convert_alpha()
    except Exception:
        splash_raw = None

    splash_cache: dict[tuple[int, int], pygame.Surface] = {}

    def _splash_for(target_w: int, target_h: int) -> pygame.Surface | None:
        if splash_raw is None:
            return None
        # Fit inside target box, preserve aspect ratio.  Allow upscale
        # up to 1.4× so smaller windows still look filled.
        sw, sh = splash_raw.get_size()
        scale = min(target_w / sw, target_h / sh)
        scale = max(0.2, min(scale, 1.4))
        size = (max(1, int(sw * scale)), max(1, int(sh * scale)))
        cached = splash_cache.get(size)
        if cached is not None:
            return cached
        surf = pygame.transform.smoothscale(splash_raw, size)
        splash_cache[size] = surf
        return surf

    # ── Pre-rendered starfield (regenerated on resize) ───────────
    star_cache: dict[tuple[int, int], pygame.Surface] = {}

    def _starfield(w: int, h: int) -> pygame.Surface:
        cached = star_cache.get((w, h))
        if cached is not None:
            return cached
        surf = pygame.Surface((w, h)).convert()
        # Vertical gradient: deep navy → near-black at top, hint of
        # warm horizon at the bottom.  Mirrors the splash art palette.
        for y in range(h):
            t = y / max(1, h - 1)
            r = int(8 + (24 - 8) * t)
            g = int(10 + (18 - 10) * t)
            b = int(22 + (40 - 22) * t)
            pygame.draw.line(surf, (r, g, b), (0, y), (w, y))
        # Sparse stars.
        rng = _random.Random(0xCAFE)
        n_stars = (w * h) // 4500
        for _ in range(n_stars):
            sx = rng.randint(0, w - 1)
            sy = rng.randint(0, int(h * 0.7))
            br = rng.randint(120, 230)
            surf.set_at((sx, sy), (br, br, min(255, br + 20)))
        # A handful of brighter twinklers.
        for _ in range(max(6, n_stars // 40)):
            sx = rng.randint(0, w - 1)
            sy = rng.randint(0, int(h * 0.6))
            pygame.draw.circle(surf, (220, 225, 240), (sx, sy), 1)
            pygame.draw.circle(
                surf, (90, 110, 160, 80), (sx, sy), 3, width=1,
            )
        star_cache[(w, h)] = surf
        return surf

    # ── Themed colours (match game UI gold/wood accents) ─────────
    GOLD = (220, 180, 60)
    GOLD_HI = (255, 215, 100)
    WOOD = (60, 40, 26)
    WOOD_HI = (110, 78, 48)
    BAR_BG = (24, 18, 14)
    BAR_FILL = (210, 150, 60)
    BAR_FILL_HI = (255, 205, 110)
    TEXT = (240, 230, 210)
    TEXT_DIM = (180, 165, 135)

    elapsed = 0.0
    first_frame = True
    smooth_p = 0.0
    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return False
            elif event.type == pygame.VIDEORESIZE:
                # Loading screen is resolution-agnostic; just keep
                # going on the new surface (pygame already resized
                # the display).
                pass
        # Draw BEFORE checking readiness so the player always sees at
        # least one frame of the loading screen.
        w, h = screen.get_size()

        # 1. Starfield background (cached per resolution).
        screen.blit(_starfield(w, h), (0, 0))

        # 2. Splash artwork — sized to fill most of the upper area.
        splash = _splash_for(int(w * 0.92), int(h * 0.7))
        bar_w = min(640, int(w * 0.65))
        bar_h = 28
        if splash is not None:
            sx = (w - splash.get_width()) // 2
            # Lift the splash a touch above vertical centre so the
            # progress bar has room beneath it.
            sy = max(8, (h - splash.get_height() - bar_h - 80) // 2)
            screen.blit(splash, (sx, sy))
            bar_y = sy + splash.get_height() + 28
        else:
            # Fallback: draw a centred title if the splash failed.
            fallback_font = pygame.font.Font(None, 72)
            t_surf = fallback_font.render("RePioneer", True, GOLD_HI)
            screen.blit(
                t_surf, (w // 2 - t_surf.get_width() // 2, h // 2 - 100),
            )
            bar_y = h // 2 - 10

        # Determine target progress.
        if progress is not None:
            try:
                target_p = max(0.0, min(1.0, float(progress())))
            except Exception:
                target_p = 0.0
        else:
            # No real progress reported — fake a smooth fill to 95%
            # over the min_duration so the bar at least moves.
            target_p = min(0.95, elapsed / max(0.001, min_duration))
        # Snap to ready when world is ready.
        if not first_frame and is_world_ready():
            target_p = 1.0
        # Ease towards target.
        smooth_p += (target_p - smooth_p) * min(1.0, 8.0 * (1 / fps))

        # 3. Themed wood-frame progress bar.
        bar_x = (w - bar_w) // 2
        # Outer wood frame with bevel.
        frame_pad = 6
        frame_rect = pygame.Rect(
            bar_x - frame_pad, bar_y - frame_pad,
            bar_w + frame_pad * 2, bar_h + frame_pad * 2,
        )
        pygame.draw.rect(screen, WOOD, frame_rect, border_radius=8)
        pygame.draw.rect(
            screen, WOOD_HI, frame_rect, width=2, border_radius=8,
        )
        # Inset gold rim.
        rim_rect = frame_rect.inflate(-4, -4)
        pygame.draw.rect(screen, GOLD, rim_rect, width=1, border_radius=6)
        # Inner bar background.
        bar_rect = pygame.Rect(bar_x, bar_y, bar_w, bar_h)
        pygame.draw.rect(screen, BAR_BG, bar_rect, border_radius=4)

        # Fill.
        fill_w = int(bar_w * smooth_p)
        if fill_w > 0:
            fill_rect = pygame.Rect(bar_x, bar_y, fill_w, bar_h)
            pygame.draw.rect(screen, BAR_FILL, fill_rect, border_radius=4)
            # Highlight along the top half for a polished bevel.
            hi_rect = pygame.Rect(
                bar_x, bar_y, fill_w, max(2, bar_h // 3),
            )
            pygame.draw.rect(screen, BAR_FILL_HI, hi_rect, border_radius=4)
            # Animated shimmer travelling across the fill.
            shimmer_x = (
                bar_x
                + int((elapsed * 0.55) * bar_w) % max(1, bar_w + 80)
                - 80
            )
            if bar_x - 40 < shimmer_x < bar_x + fill_w:
                shimmer = pygame.Surface((40, bar_h), pygame.SRCALPHA)
                for i in range(40):
                    a = int(120 * math.sin(math.pi * i / 40))
                    pygame.draw.line(
                        shimmer, (255, 240, 200, max(0, a)),
                        (i, 0), (i, bar_h),
                    )
                # Clip to filled area only.
                clip_w = min(40, bar_x + fill_w - shimmer_x)
                if clip_w > 0:
                    screen.blit(
                        shimmer, (shimmer_x, bar_y),
                        area=pygame.Rect(0, 0, clip_w, bar_h),
                    )

        # 4. Percent label centred on the bar.
        pct_text = f"{int(round(smooth_p * 100))}%"
        pct_surf = pct_font.render(pct_text, True, TEXT)
        # Subtle drop shadow for readability over the fill.
        shadow = pct_font.render(pct_text, True, (0, 0, 0))
        screen.blit(
            shadow,
            (w // 2 - shadow.get_width() // 2 + 1,
             bar_y + (bar_h - shadow.get_height()) // 2 + 1),
        )
        screen.blit(
            pct_surf,
            (w // 2 - pct_surf.get_width() // 2,
             bar_y + (bar_h - pct_surf.get_height()) // 2),
        )

        # 5. Animated status label below the bar.
        sub_text = ""
        if label is not None:
            try:
                sub_text = label() or ""
            except Exception:
                sub_text = ""
        if not sub_text:
            sub_text = "Carving rivers, scattering stones, planting forests"
        # Animated trailing dots so the player can see the screen is alive
        # even when generation pauses on a single phase.
        dot_count = int(elapsed * 2.0) % 4
        sub_full = sub_text + ("." * dot_count)
        sub_surf = sub_font.render(sub_full, True, TEXT_DIM)
        screen.blit(
            sub_surf,
            (w // 2 - sub_surf.get_width() // 2, bar_y + bar_h + 18),
        )

        # 6. Tiny status line: tagline at bottom edge.
        tag = status_font.render(
            "Survive  \u2022  Reclaim  \u2022  Rebuild", True, GOLD,
        )
        screen.blit(
            tag, (w // 2 - tag.get_width() // 2, h - tag.get_height() - 14),
        )

        pygame.display.flip()
        if not first_frame and elapsed >= min_duration and is_world_ready():
            return True
        first_frame = False
        dt = clock.tick(fps) / 1000.0
        elapsed += dt
