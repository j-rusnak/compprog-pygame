"""In-game guide / info overlay for Hex Colony.

Multi-page overlay toggled with the **I** key.  Each page covers a
different facet of the game so new players can learn the mechanics
without leaving the session.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pygame

from compprog_pygame.games.hex_colony.ui import (
    Fonts,
    Panel,
    UI_ACCENT,
    UI_BORDER,
    UI_MUTED,
    UI_OVERLAY,
    UI_TAB_ACTIVE,
    UI_TAB_HOVER,
    UI_TAB_INACTIVE,
    UI_TEXT,
    draw_panel_bg,
)
from compprog_pygame.games.hex_colony.strings import (
    GUIDE_PAGES,
    GUIDE_WINDOW_TITLE,
    GUIDE_DISMISS,
)

if TYPE_CHECKING:
    from compprog_pygame.games.hex_colony.world import World

# ── Page data ────────────────────────────────────────────────────
# Each page is (title, list-of-lines).  Lines starting with "#" are
# rendered as section headers; others as body text.

_PAGES = GUIDE_PAGES

_PAGE_TAB_H = 32
_LINE_H = 24
_MARGIN = 28
_PAD = 20


class InfoGuideOverlay(Panel):
    """Multi-page in-game guide overlay, toggled with I."""

    def __init__(self) -> None:
        super().__init__()
        self.visible = False
        self._page: int = 0
        self._scroll: int = 0
        self._tab_rects: list[pygame.Rect] = []
        self._mouse_pos: tuple[int, int] = (0, 0)

    def toggle(self) -> None:
        self.visible = not self.visible
        if self.visible:
            self._scroll = 0

    def layout(self, screen_w: int, screen_h: int) -> None:
        self.rect = pygame.Rect(0, 0, screen_w, screen_h)

    def draw(self, surface: pygame.Surface, world: "World") -> None:
        if not self.visible:
            return
        sw, sh = surface.get_size()

        overlay = pygame.Surface((sw, sh), pygame.SRCALPHA)
        overlay.fill(UI_OVERLAY)
        surface.blit(overlay, (0, 0))

        # Panel
        pw = min(700, sw - 60)
        ph = min(560, sh - 60)
        px = (sw - pw) // 2
        py = (sh - ph) // 2
        panel = pygame.Rect(px, py, pw, ph)
        draw_panel_bg(surface, panel, accent_edge="top")

        # Title
        title = Fonts.title().render(GUIDE_WINDOW_TITLE, True, UI_TEXT)
        surface.blit(title, (px + _PAD, py + 10))

        # Page tabs
        self._tab_rects = []
        tx = px + _PAD
        ty = py + 42
        for i, (page_title, _) in enumerate(_PAGES):
            label = Fonts.small().render(page_title, True, UI_TEXT)
            tw = label.get_width() + 16
            tab_rect = pygame.Rect(tx, ty, tw, _PAGE_TAB_H)
            active = i == self._page
            hovered = tab_rect.collidepoint(self._mouse_pos)
            if active:
                bg_color = UI_TAB_ACTIVE
            elif hovered:
                bg_color = UI_TAB_HOVER
            else:
                bg_color = UI_TAB_INACTIVE
            bg = pygame.Surface((tab_rect.w, tab_rect.h), pygame.SRCALPHA)
            bg.fill(bg_color)
            surface.blit(bg, tab_rect.topleft)
            border = UI_ACCENT if active else UI_BORDER
            pygame.draw.rect(surface, border, tab_rect, width=1, border_radius=3)
            surface.blit(label, (
                tab_rect.centerx - label.get_width() // 2,
                tab_rect.centery - label.get_height() // 2,
            ))
            self._tab_rects.append(tab_rect)
            tx += tw + 4

        # Content area
        content_top = ty + _PAGE_TAB_H + 8
        content_rect = pygame.Rect(
            px + _MARGIN, content_top,
            pw - _MARGIN * 2, py + ph - content_top - 30,
        )
        prev_clip = surface.get_clip()
        surface.set_clip(content_rect)

        _, lines = _PAGES[self._page]
        y = content_rect.y - self._scroll
        header_font = Fonts.label()
        body_font = Fonts.body()

        for line in lines:
            if not line:
                y += _LINE_H // 2
                continue
            if line.startswith("#"):
                text = line.lstrip("# ")
                surf = header_font.render(text, True, UI_ACCENT)
            else:
                surf = body_font.render(line, True, UI_TEXT)
            surface.blit(surf, (content_rect.x, y))
            y += _LINE_H

        self._content_h = int(y + self._scroll - content_rect.y)
        surface.set_clip(prev_clip)

        # Hint
        hint = Fonts.small().render(
            GUIDE_DISMISS, True, UI_MUTED,
        )
        surface.blit(hint, (
            px + (pw - hint.get_width()) // 2,
            py + ph - hint.get_height() - 10,
        ))

    def handle_event(self, event: pygame.event.Event) -> bool:
        if not self.visible:
            return False
        if event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_i, pygame.K_ESCAPE):
                self.visible = False
                return True
            if event.key == pygame.K_LEFT:
                self._page = max(0, self._page - 1)
                self._scroll = 0
                return True
            if event.key == pygame.K_RIGHT:
                self._page = min(len(_PAGES) - 1, self._page + 1)
                self._scroll = 0
                return True
        if event.type == pygame.MOUSEMOTION:
            self._mouse_pos = event.pos
            return True
        if event.type == pygame.MOUSEWHEEL:
            self._scroll = max(0, self._scroll - event.y * 24)
            return True
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            for i, tab_rect in enumerate(self._tab_rects):
                if tab_rect.collidepoint(event.pos):
                    self._page = i
                    self._scroll = 0
                    return True
            return True  # consume click
        return True  # consume all events while visible


__all__ = ["InfoGuideOverlay"]
