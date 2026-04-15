"""Pause menu and options overlay for Hex Colony.

States
------
* ``None``      — hidden (not drawing, not consuming events)
* ``"pause"``   — main pause menu: Resume / Options / Return to Main Menu / Quit
* ``"options"`` — placeholder settings sub-menu
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Callable

import pygame

from compprog_pygame.games.hex_colony.ui import (
    Panel,
    UI_ACCENT,
    UI_BG,
    UI_BORDER,
    UI_MUTED,
    UI_TEXT,
)

if TYPE_CHECKING:
    from compprog_pygame.games.hex_colony.world import World

# ── Layout constants ─────────────────────────────────────────────

_BUTTON_W = 280
_BUTTON_H = 48
_BUTTON_GAP = 14
_BUTTON_BG = (30, 50, 90)
_BUTTON_HOVER = (50, 75, 130)
_BUTTON_TEXT = (242, 244, 255)
_OVERLAY_COLOR = (0, 0, 0, 120)

_PAUSE_BUTTONS = ["Resume", "Options", "Return to Main Menu", "Quit"]


class PauseOverlay(Panel):
    """Full-screen overlay with pause menu and options sub-menu."""

    def __init__(self) -> None:
        super().__init__()
        self.state: str | None = None
        self.visible = False
        self._title_font = pygame.font.Font(None, 52)
        self._btn_font = pygame.font.Font(None, 34)
        self._label_font = pygame.font.Font(None, 28)
        self._small_font = pygame.font.Font(None, 22)
        self._hovered: int = -1

        # Graphics quality: "high", "medium", "low"
        self.graphics_quality: str = "high"

        # Callbacks wired by Game
        self.on_resume: Callable[[], None] | None = None
        self.on_return_to_menu: Callable[[], None] | None = None
        self.on_quit: Callable[[], None] | None = None
        self.on_graphics_changed: Callable[[str], None] | None = None

    # ── State helpers ────────────────────────────────────────────

    def show(self) -> None:
        self.state = "pause"
        self.visible = True
        self._hovered = -1

    def hide(self) -> None:
        self.state = None
        self.visible = False
        self._hovered = -1

    # ── Panel interface ──────────────────────────────────────────

    def layout(self, screen_w: int, screen_h: int) -> None:
        self.rect = pygame.Rect(0, 0, screen_w, screen_h)

    # ── Drawing ──────────────────────────────────────────────────

    def draw(self, surface: pygame.Surface, world: World) -> None:
        if self.state is None:
            return
        sw, sh = surface.get_size()

        # Dark backdrop
        overlay = pygame.Surface((sw, sh), pygame.SRCALPHA)
        overlay.fill(_OVERLAY_COLOR)
        surface.blit(overlay, (0, 0))

        if self.state == "pause":
            self._draw_pause(surface, sw, sh)
        elif self.state == "options":
            self._draw_options(surface, sw, sh)

    def _draw_pause(self, surface: pygame.Surface, sw: int, sh: int) -> None:
        pw, ph, px, py = self._pause_panel_rect(sw, sh)
        self._draw_panel_box(surface, px, py, pw, ph, "Paused")

        by = py + 70
        bx = px + (pw - _BUTTON_W) // 2
        for idx, label in enumerate(_PAUSE_BUTTONS):
            self._draw_button(surface, bx, by, label, idx == self._hovered)
            by += _BUTTON_H + _BUTTON_GAP

    def _draw_options(self, surface: pygame.Surface, sw: int, sh: int) -> None:
        pw, ph, px, py = self._options_panel_rect(sw, sh)
        self._draw_panel_box(surface, px, py, pw, ph, "Options")

        # ── Graphics quality setting ─────────────────────────────
        sy = py + 80
        lbl = self._label_font.render("Graphics Quality", True, UI_TEXT)
        surface.blit(lbl, (px + 30, sy))

        # Quality selector button (hover index 1)
        qval = self.graphics_quality.capitalize()
        qual_rect = pygame.Rect(px + pw - 30 - 120, sy - 4, 120, 32)
        is_qual_hov = self._hovered == 1
        bg = _BUTTON_HOVER if is_qual_hov else _BUTTON_BG
        pygame.draw.rect(surface, bg, qual_rect, border_radius=6)
        border = UI_ACCENT if is_qual_hov else UI_BORDER
        pygame.draw.rect(surface, border, qual_rect, width=2, border_radius=6)
        val_surf = self._label_font.render(qval, True, _BUTTON_TEXT)
        surface.blit(val_surf, (qual_rect.x + (qual_rect.w - val_surf.get_width()) // 2,
                                qual_rect.y + (qual_rect.h - val_surf.get_height()) // 2))

        sy += 50
        descriptions = {
            "high": "Full gradients, overlays, and contours",
            "medium": "Blended colors, overlays, no triangle gradients",
            "low": "Flat tile colors and buildings only",
        }
        desc = descriptions.get(self.graphics_quality, "")
        desc_surf = self._small_font.render(desc, True, UI_MUTED)
        surface.blit(desc_surf, (px + 30, sy))

        # Placeholder rows
        sy += 40
        placeholders = [
            ("Music Volume", "\u2014"),
            ("Sound Effects", "\u2014"),
        ]
        for label, value in placeholders:
            lbl2 = self._label_font.render(label, True, UI_TEXT)
            val2 = self._label_font.render(value, True, UI_MUTED)
            surface.blit(lbl2, (px + 30, sy))
            surface.blit(val2, (px + pw - 30 - val2.get_width(), sy))
            sy += 40

        # Back button (hover index 0)
        bx = px + (pw - _BUTTON_W) // 2
        by = py + ph - _BUTTON_H - 20
        self._draw_button(surface, bx, by, "Back", self._hovered == 0)

    # ── Geometry helpers ─────────────────────────────────────────

    @staticmethod
    def _pause_panel_rect(sw: int, sh: int) -> tuple[int, int, int, int]:
        pw = _BUTTON_W + 60
        ph = 80 + len(_PAUSE_BUTTONS) * (_BUTTON_H + _BUTTON_GAP) + 20
        return pw, ph, (sw - pw) // 2, (sh - ph) // 2

    @staticmethod
    def _options_panel_rect(sw: int, sh: int) -> tuple[int, int, int, int]:
        pw, ph = 400, 380
        return pw, ph, (sw - pw) // 2, (sh - ph) // 2

    # ── Draw helpers ─────────────────────────────────────────────

    def _draw_panel_box(
        self, surface: pygame.Surface,
        px: int, py: int, pw: int, ph: int, title: str,
    ) -> None:
        panel_rect = pygame.Rect(px, py, pw, ph)
        bg = pygame.Surface((pw, ph), pygame.SRCALPHA)
        bg.fill(UI_BG)
        surface.blit(bg, (px, py))
        pygame.draw.rect(surface, UI_BORDER, panel_rect, width=2, border_radius=8)
        pygame.draw.line(surface, UI_ACCENT, (px, py), (px + pw, py), 2)
        title_surf = self._title_font.render(title, True, UI_TEXT)
        surface.blit(title_surf, (px + (pw - title_surf.get_width()) // 2, py + 20))

    def _draw_button(
        self, surface: pygame.Surface,
        x: int, y: int, label: str, hovered: bool,
    ) -> None:
        rect = pygame.Rect(x, y, _BUTTON_W, _BUTTON_H)
        bg = _BUTTON_HOVER if hovered else _BUTTON_BG
        pygame.draw.rect(surface, bg, rect, border_radius=8)
        border = UI_ACCENT if hovered else UI_BORDER
        pygame.draw.rect(surface, border, rect, width=2, border_radius=8)
        txt = self._btn_font.render(label, True, _BUTTON_TEXT)
        surface.blit(txt, (x + (_BUTTON_W - txt.get_width()) // 2,
                           y + (_BUTTON_H - txt.get_height()) // 2))

    # ── Event handling ───────────────────────────────────────────

    def handle_event(self, event: pygame.event.Event) -> bool:
        if self.state is None:
            return False

        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            if self.state == "options":
                self.state = "pause"
                self._hovered = -1
            elif self.state == "pause":
                self.hide()
                if self.on_resume:
                    self.on_resume()
            return True

        if event.type == pygame.MOUSEMOTION:
            self._update_hover(event.pos)
            return True

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            self._handle_click(event.pos)
            return True

        # Consume everything else to block world interaction
        return True

    def _update_hover(self, pos: tuple[int, int]) -> None:
        self._hovered = -1
        sw, sh = pygame.display.get_surface().get_size()

        if self.state == "pause":
            pw, _, px, py = self._pause_panel_rect(sw, sh)
            by = py + 70
            bx = px + (pw - _BUTTON_W) // 2
            for idx in range(len(_PAUSE_BUTTONS)):
                if pygame.Rect(bx, by, _BUTTON_W, _BUTTON_H).collidepoint(pos):
                    self._hovered = idx
                    return
                by += _BUTTON_H + _BUTTON_GAP

        elif self.state == "options":
            pw, ph, px, py = self._options_panel_rect(sw, sh)
            # Quality button
            qual_rect = pygame.Rect(px + pw - 30 - 120, py + 80 - 4, 120, 32)
            if qual_rect.collidepoint(pos):
                self._hovered = 1
                return
            # Back button
            bx = px + (pw - _BUTTON_W) // 2
            by = py + ph - _BUTTON_H - 20
            if pygame.Rect(bx, by, _BUTTON_W, _BUTTON_H).collidepoint(pos):
                self._hovered = 0
                return
            self._hovered = -1

    def _handle_click(self, pos: tuple[int, int]) -> None:
        sw, sh = pygame.display.get_surface().get_size()

        if self.state == "pause":
            pw, _, px, py = self._pause_panel_rect(sw, sh)
            by = py + 70
            bx = px + (pw - _BUTTON_W) // 2
            for idx in range(len(_PAUSE_BUTTONS)):
                if pygame.Rect(bx, by, _BUTTON_W, _BUTTON_H).collidepoint(pos):
                    if idx == 0:    # Resume
                        self.hide()
                        if self.on_resume:
                            self.on_resume()
                    elif idx == 1:  # Options
                        self.state = "options"
                        self._hovered = -1
                    elif idx == 2:  # Return to Main Menu
                        if self.on_return_to_menu:
                            self.on_return_to_menu()
                    elif idx == 3:  # Quit
                        if self.on_quit:
                            self.on_quit()
                    return
                by += _BUTTON_H + _BUTTON_GAP

        elif self.state == "options":
            pw, ph, px, py = self._options_panel_rect(sw, sh)
            # Quality button click
            qual_rect = pygame.Rect(px + pw - 30 - 120, py + 80 - 4, 120, 32)
            if qual_rect.collidepoint(pos):
                cycle = {"high": "medium", "medium": "low", "low": "high"}
                self.graphics_quality = cycle[self.graphics_quality]
                if self.on_graphics_changed:
                    self.on_graphics_changed(self.graphics_quality)
                return
            # Back button click
            bx = px + (pw - _BUTTON_W) // 2
            by = py + ph - _BUTTON_H - 20
            if pygame.Rect(bx, by, _BUTTON_W, _BUTTON_H).collidepoint(pos):
                self.state = "pause"
                self._hovered = -1
