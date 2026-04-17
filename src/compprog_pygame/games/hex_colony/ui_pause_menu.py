"""Pause menu and options overlay for Hex Colony.

States
------
* ``None``      — hidden.
* ``"pause"``   — Resume / Options / Main Menu / Quit.
* ``"options"`` — graphics quality + (future) audio settings.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable

import pygame

from compprog_pygame.games.hex_colony.ui import (
    Fonts,
    Panel,
    UI_ACCENT,
    UI_MUTED,
    UI_OVERLAY,
    UI_TEXT,
    draw_button,
    draw_titled_panel,
)

if TYPE_CHECKING:
    from compprog_pygame.games.hex_colony.world import World


_BUTTON_W = 280
_BUTTON_H = 48
_BUTTON_GAP = 12

_PAUSE_LABELS = ["Resume", "Options", "Return to Main Menu", "Quit"]
_QUALITY_CYCLE = {"high": "medium", "medium": "low", "low": "high"}
_QUALITY_DESC = {
    "high": "Full gradients, overlays, and contours",
    "medium": "Blended colors, overlays, no triangle gradients",
    "low": "Flat tile colors and buildings only",
}


@dataclass
class _ClickTarget:
    rect: pygame.Rect
    action: str
    label: str = ""


class PauseOverlay(Panel):
    """Full-screen overlay with pause menu and options sub-menu."""

    def __init__(self) -> None:
        super().__init__()
        self.state: str | None = None
        self.visible = False
        self._hovered: int = -1
        self._targets: list[_ClickTarget] = []
        self.graphics_quality: str = "medium"

        self.on_resume: Callable[[], None] | None = None
        self.on_return_to_menu: Callable[[], None] | None = None
        self.on_quit: Callable[[], None] | None = None
        self.on_graphics_changed: Callable[[str], None] | None = None

    def show(self) -> None:
        self.state = "pause"
        self.visible = True
        self._hovered = -1

    def hide(self) -> None:
        self.state = None
        self.visible = False
        self._hovered = -1

    def layout(self, screen_w: int, screen_h: int) -> None:
        self.rect = pygame.Rect(0, 0, screen_w, screen_h)

    def draw(self, surface: pygame.Surface, world: World) -> None:
        if self.state is None:
            return
        sw, sh = surface.get_size()

        overlay = pygame.Surface((sw, sh), pygame.SRCALPHA)
        overlay.fill(UI_OVERLAY)
        surface.blit(overlay, (0, 0))

        if self.state == "pause":
            self._draw_pause(surface, sw, sh)
        else:
            self._draw_options(surface, sw, sh)

    def _draw_pause(self, surface: pygame.Surface, sw: int, sh: int) -> None:
        pw = _BUTTON_W + 80
        ph = 90 + len(_PAUSE_LABELS) * (_BUTTON_H + _BUTTON_GAP) + 24
        pw = min(pw, sw - 40)
        ph = min(ph, sh - 40)
        px = (sw - pw) // 2
        py = (sh - ph) // 2
        panel_rect = pygame.Rect(px, py, pw, ph)
        content_y = draw_titled_panel(surface, panel_rect, "Paused")

        self._targets = []
        by = content_y
        bx = px + (pw - _BUTTON_W) // 2
        for idx, label in enumerate(_PAUSE_LABELS):
            btn = pygame.Rect(bx, by, _BUTTON_W, _BUTTON_H)
            state = "hover" if idx == self._hovered else "normal"
            draw_button(surface, btn, label, state=state)
            self._targets.append(
                _ClickTarget(btn, f"pause:{idx}", label),
            )
            by += _BUTTON_H + _BUTTON_GAP

    def _draw_options(self, surface: pygame.Surface, sw: int, sh: int) -> None:
        pw = 460
        ph = 320
        pw = min(pw, sw - 40)
        ph = min(ph, sh - 40)
        px = (sw - pw) // 2
        py = (sh - ph) // 2
        panel_rect = pygame.Rect(px, py, pw, ph)
        content_y = draw_titled_panel(surface, panel_rect, "Options")

        self._targets = []
        inner_x = px + 24
        inner_w = pw - 48
        font_label = Fonts.label()
        font_small = Fonts.small()

        # Graphics quality row
        sy = content_y + 6
        label_surf = font_label.render("Graphics Quality", True, UI_TEXT)
        surface.blit(label_surf, (inner_x, sy))

        btn_w = 130
        btn_h = 34
        qbtn = pygame.Rect(px + pw - 24 - btn_w, sy - 4, btn_w, btn_h)
        is_hov = self._hovered == 0
        draw_button(
            surface, qbtn, self.graphics_quality.capitalize(),
            state="hover" if is_hov else "normal",
        )
        self._targets.append(_ClickTarget(qbtn, "options:quality"))

        desc_surf = font_small.render(
            _QUALITY_DESC.get(self.graphics_quality, ""), True, UI_MUTED,
        )
        surface.blit(desc_surf, (inner_x, sy + 40))

        # Placeholder rows
        sy += 80
        placeholders = [
            ("Music Volume", "\u2014"),
            ("Sound Effects", "\u2014"),
        ]
        for text, value in placeholders:
            lbl = font_label.render(text, True, UI_TEXT)
            val = font_label.render(value, True, UI_MUTED)
            surface.blit(lbl, (inner_x, sy))
            surface.blit(val, (px + pw - 24 - val.get_width(), sy))
            sy += 38

        # Back button
        back_w = 160
        back = pygame.Rect(
            px + (pw - back_w) // 2, py + ph - _BUTTON_H - 20,
            back_w, _BUTTON_H,
        )
        is_hov = self._hovered == 1
        draw_button(surface, back, "Back", state="hover" if is_hov else "normal")
        self._targets.append(_ClickTarget(back, "options:back"))

    def handle_event(self, event: pygame.event.Event) -> bool:
        if self.state is None:
            return False

        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            if self.state == "options":
                self.state = "pause"
                self._hovered = -1
            else:
                self.hide()
                if self.on_resume:
                    self.on_resume()
            return True

        if event.type == pygame.MOUSEMOTION:
            self._hovered = -1
            for i, t in enumerate(self._targets):
                if t.rect.collidepoint(event.pos):
                    self._hovered = i
                    break
            return True

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            for t in self._targets:
                if t.rect.collidepoint(event.pos):
                    self._handle_action(t.action)
                    return True
            return True

        return True

    def _handle_action(self, action: str) -> None:
        if action == "pause:0":
            self.hide()
            if self.on_resume:
                self.on_resume()
        elif action == "pause:1":
            self.state = "options"
            self._hovered = -1
        elif action == "pause:2":
            if self.on_return_to_menu:
                self.on_return_to_menu()
        elif action == "pause:3":
            if self.on_quit:
                self.on_quit()
        elif action == "options:quality":
            self.graphics_quality = _QUALITY_CYCLE[self.graphics_quality]
            if self.on_graphics_changed:
                self.on_graphics_changed(self.graphics_quality)
        elif action == "options:back":
            self.state = "pause"
            self._hovered = -1
