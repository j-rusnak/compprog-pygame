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
            # Quadratic ease-in on the fall; gentler leftward drift
            # so the trajectory feels heavy rather than swinging.
            self._ship_offset = (
                -90.0 * t - 15.0 * (t * t),
                self.h * 0.65 * (t * t),
            )
            # Tumbling: accelerating spin with a subtler wobble.
            self._ship_rot = -55.0 * t * t + math.sin(
                self._total_t * 9.0,
            ) * 1.5
            # Shake decays gradually instead of cutting off.
            self._shake = 22.0 * (1.0 - t) + 4.0
            # Spawn debris particles intermittently.
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
        # Background — starfield + Earth.
        bg = sprites.get("cutscene/space_bg")
        if bg is not None:
            screen.blit(bg.get(self.w, self.h), (0, 0))
        else:
            screen.fill((6, 10, 22))

        # Ship.
        ship_state = self._current_ship_state()
        ship_key = ("cutscene/ship_damaged"
                    if ship_state == "damaged" else "cutscene/ship")
        ship = sprites.get(ship_key)
        if ship is not None:
            sw = int(self.w * _SHIP_WIDTH_FRAC * self._ship_extra_scale)
            sh = int(sw * 0.5)
            ship_surf = ship.get(sw, sh)
            if abs(self._ship_rot) > 0.05:
                ship_surf = pygame.transform.rotozoom(
                    ship_surf, self._ship_rot, 1.0,
                )
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
        key = "cutscene/captain" if speaker == "Captain" else "cutscene/scientist"
        sheet = sprites.get(key)
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
        cx = self.w // 2 + int(self.w * _SHIP_X_OFFSET_FRAC) + int(
            self._ship_offset[0],
        )
        cy = int(self.h * 0.42) + int(self._ship_offset[1])
        # Spawn from a small region around the ship centre.
        spread = int(self.w * _SHIP_WIDTH_FRAC * 0.35)
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
    title_font = pygame.font.Font(None, 56)
    sub_font = pygame.font.Font(None, 24)
    pct_font = pygame.font.Font(None, 22)
    title_surf = title_font.render(
        "Generating world\u2026", True, (220, 225, 240),
    )
    elapsed = 0.0
    first_frame = True
    # Smoothed progress: lerps toward the latest reported value so
    # the bar moves smoothly even if the worker reports in chunks.
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
        screen.fill((0, 0, 0))
        screen.blit(
            title_surf,
            (w // 2 - title_surf.get_width() // 2, h // 2 - 90),
        )

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

        # Progress bar.
        bar_w = min(560, int(w * 0.6))
        bar_h = 22
        bar_x = (w - bar_w) // 2
        bar_y = h // 2 - 10
        # Frame.
        pygame.draw.rect(
            screen, (50, 60, 80),
            (bar_x - 2, bar_y - 2, bar_w + 4, bar_h + 4),
            border_radius=6,
        )
        pygame.draw.rect(
            screen, (18, 22, 32),
            (bar_x, bar_y, bar_w, bar_h),
            border_radius=4,
        )
        # Fill.
        fill_w = int(bar_w * smooth_p)
        if fill_w > 0:
            pygame.draw.rect(
                screen, (90, 160, 230),
                (bar_x, bar_y, fill_w, bar_h),
                border_radius=4,
            )
            # Subtle highlight stripe along the top of the fill.
            pygame.draw.rect(
                screen, (140, 200, 255),
                (bar_x, bar_y, fill_w, max(2, bar_h // 4)),
                border_radius=4,
            )

        # Percent label centred on the bar.
        pct_text = f"{int(round(smooth_p * 100))}%"
        pct_surf = pct_font.render(pct_text, True, (230, 235, 245))
        screen.blit(
            pct_surf,
            (w // 2 - pct_surf.get_width() // 2,
             bar_y + (bar_h - pct_surf.get_height()) // 2),
        )

        # Status label below the bar.
        sub_text = ""
        if label is not None:
            try:
                sub_text = label() or ""
            except Exception:
                sub_text = ""
        if not sub_text:
            sub_text = "Carving rivers, scattering stones, planting forests\u2026"
        sub_surf = sub_font.render(sub_text, True, (140, 150, 170))
        screen.blit(
            sub_surf,
            (w // 2 - sub_surf.get_width() // 2, bar_y + bar_h + 16),
        )

        pygame.display.flip()
        if not first_frame and elapsed >= min_duration and is_world_ready():
            return True
        first_frame = False
        dt = clock.tick(fps) / 1000.0
        elapsed += dt
