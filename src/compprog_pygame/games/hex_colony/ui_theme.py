"""Shared UI theme: fonts, button primitives, and text helpers.

All panels should use this module for fonts and drawing primitives
instead of creating their own. This keeps the look consistent and
avoids bugs where text overflows or layout is inconsistent across
panels.

Font tiers
----------
Tiny  (16) -- tooltips, timestamps
Small (20) -- secondary info, compact labels
Body  (22) -- default in-panel text
Label (26) -- panel section headings, buttons
Title (32) -- panel titles
Hero  (52) -- full-screen overlay titles

Never instantiate ``pygame.font.Font`` directly in a panel; call
``Fonts.body()`` etc. instead. Fonts are lazily initialised so
``pygame.font.init()`` must have been called first.

Key helpers
-----------
``render_text_clipped(font, text, color, max_w)`` -- returns a surface
    guaranteed to fit in ``max_w`` pixels (truncates with ellipsis).
``draw_button(surface, rect, label, state)`` -- standard button.
``draw_panel_box(surface, rect, *, title)`` -- titled panel background.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import pygame


# ── Colour palette ───────────────────────────────────────────────

UI_BG = (16, 24, 45, 220)
UI_BG_OPAQUE = (16, 24, 45)
UI_BG_SOLID = (20, 30, 54)
UI_TEXT = (242, 244, 255)
UI_MUTED = (140, 150, 175)
UI_ACCENT = (200, 160, 60)
UI_BORDER = (60, 70, 100)
UI_BORDER_LIGHT = (90, 100, 130)

UI_TAB_ACTIVE = (35, 50, 85, 240)
UI_TAB_HOVER = (30, 42, 72, 200)
UI_TAB_INACTIVE = (16, 24, 45, 200)

UI_BTN_BG = (30, 50, 90)
UI_BTN_HOVER = (50, 75, 130)
UI_BTN_ACTIVE = (70, 100, 160)
UI_BTN_DISABLED = (35, 40, 55)

UI_OK = (120, 200, 120)
UI_WARN = (220, 180, 70)
UI_BAD = (200, 70, 70)
UI_OVERLAY = (0, 0, 0, 160)


# ── Fonts (lazy singletons) ──────────────────────────────────────

class Fonts:
    """Lazy-initialised shared font cache.

    Call e.g. ``Fonts.body()`` to get the shared 22px font.
    """

    _cache: dict[int, pygame.font.Font] = {}

    @classmethod
    def _get(cls, size: int) -> pygame.font.Font:
        f = cls._cache.get(size)
        if f is None:
            f = pygame.font.Font(None, size)
            cls._cache[size] = f
        return f

    @classmethod
    def tiny(cls) -> pygame.font.Font: return cls._get(16)

    @classmethod
    def small(cls) -> pygame.font.Font: return cls._get(20)

    @classmethod
    def body(cls) -> pygame.font.Font: return cls._get(22)

    @classmethod
    def label(cls) -> pygame.font.Font: return cls._get(26)

    @classmethod
    def title(cls) -> pygame.font.Font: return cls._get(32)

    @classmethod
    def hero(cls) -> pygame.font.Font: return cls._get(52)


# ── Text helpers ─────────────────────────────────────────────────

def render_text_clipped(
    font: pygame.font.Font,
    text: str,
    color: tuple[int, int, int],
    max_w: int,
) -> pygame.Surface:
    """Render *text* and truncate with ellipsis if wider than *max_w*."""
    if max_w <= 0:
        return font.render("", True, color)
    if font.size(text)[0] <= max_w:
        return font.render(text, True, color)
    ellipsis = "\u2026"
    ell_w = font.size(ellipsis)[0]
    if ell_w >= max_w:
        return font.render(ellipsis, True, color)
    # Binary search for longest prefix that fits with ellipsis
    lo, hi = 0, len(text)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if font.size(text[:mid])[0] + ell_w <= max_w:
            lo = mid
        else:
            hi = mid - 1
    return font.render(text[:lo] + ellipsis, True, color)


def wrap_text(
    font: pygame.font.Font, text: str, max_w: int,
) -> list[str]:
    """Greedy word-wrap *text* into lines no wider than *max_w*."""
    if max_w <= 0 or not text:
        return [text] if text else []
    words = text.split()
    if not words:
        return []
    lines: list[str] = []
    current = words[0]
    for w in words[1:]:
        test = current + " " + w
        if font.size(test)[0] <= max_w:
            current = test
        else:
            lines.append(current)
            current = w
    lines.append(current)
    return lines


# ── Button primitive ─────────────────────────────────────────────

ButtonState = Literal["normal", "hover", "active", "disabled"]


@dataclass
class ButtonStyle:
    radius: int = 6
    border_w: int = 2
    pad_x: int = 12


def draw_button(
    surface: pygame.Surface,
    rect: pygame.Rect,
    label: str,
    *,
    state: ButtonState = "normal",
    font: pygame.font.Font | None = None,
    style: ButtonStyle | None = None,
    icon: str | None = None,
) -> None:
    """Draw a styled button with optional leading icon."""
    if font is None:
        font = Fonts.label()
    if style is None:
        style = ButtonStyle()

    if state == "disabled":
        bg = UI_BTN_DISABLED
        border = UI_BORDER
        text_col = UI_MUTED
    elif state == "active":
        bg = UI_BTN_ACTIVE
        border = UI_ACCENT
        text_col = UI_TEXT
    elif state == "hover":
        bg = UI_BTN_HOVER
        border = UI_ACCENT
        text_col = UI_TEXT
    else:
        bg = UI_BTN_BG
        border = UI_BORDER
        text_col = UI_TEXT

    pygame.draw.rect(surface, bg, rect, border_radius=style.radius)
    pygame.draw.rect(
        surface, border, rect, width=style.border_w, border_radius=style.radius,
    )

    display = f"{icon}  {label}" if icon else label
    max_text_w = rect.w - style.pad_x * 2
    text_surf = render_text_clipped(font, display, text_col, max_text_w)
    tx = rect.x + (rect.w - text_surf.get_width()) // 2
    ty = rect.y + (rect.h - text_surf.get_height()) // 2
    surface.blit(text_surf, (tx, ty))


# ── Panel backgrounds ────────────────────────────────────────────

def draw_panel_bg(
    surface: pygame.Surface,
    rect: pygame.Rect,
    *,
    accent_edge: str | None = "top",
    radius: int = 6,
) -> None:
    """Translucent panel background with optional accent stripe."""
    if rect.w <= 0 or rect.h <= 0:
        return
    bg = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
    bg.fill(UI_BG)
    surface.blit(bg, rect.topleft)
    pygame.draw.rect(surface, UI_BORDER, rect, width=2, border_radius=radius)
    if accent_edge == "top":
        pygame.draw.line(
            surface, UI_ACCENT, (rect.left + 2, rect.top),
            (rect.right - 2, rect.top), 2,
        )
    elif accent_edge == "bottom":
        pygame.draw.line(
            surface, UI_ACCENT, (rect.left + 2, rect.bottom - 1),
            (rect.right - 2, rect.bottom - 1), 2,
        )


def draw_titled_panel(
    surface: pygame.Surface,
    rect: pygame.Rect,
    title: str,
    *,
    title_font: pygame.font.Font | None = None,
    title_color: tuple[int, int, int] = UI_TEXT,
    radius: int = 8,
) -> int:
    """Draw a solid titled panel; return the y position where content starts."""
    if title_font is None:
        title_font = Fonts.title()
    bg = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
    bg.fill(UI_BG)
    surface.blit(bg, rect.topleft)
    pygame.draw.rect(surface, UI_BORDER, rect, width=2, border_radius=radius)
    pygame.draw.line(
        surface, UI_ACCENT, (rect.left, rect.top), (rect.right, rect.top), 3,
    )
    title_surf = render_text_clipped(
        title_font, title, title_color, rect.w - 32,
    )
    surface.blit(
        title_surf,
        (rect.centerx - title_surf.get_width() // 2, rect.top + 14),
    )
    return rect.top + 14 + title_surf.get_height() + 12


# ── Progress bar primitive ───────────────────────────────────────

def draw_progress_bar(
    surface: pygame.Surface,
    rect: pygame.Rect,
    frac: float,
    *,
    fg: tuple[int, int, int] = UI_OK,
    bg: tuple[int, int, int] = (40, 45, 60),
    border: tuple[int, int, int] = UI_BORDER,
) -> None:
    """Draw a filled progress bar. *frac* is clamped to [0, 1]."""
    frac = max(0.0, min(1.0, frac))
    pygame.draw.rect(surface, bg, rect, border_radius=3)
    if frac > 0 and rect.w > 2:
        fill_w = max(1, int((rect.w - 2) * frac))
        fill = pygame.Rect(rect.x + 1, rect.y + 1, fill_w, rect.h - 2)
        pygame.draw.rect(surface, fg, fill, border_radius=3)
    pygame.draw.rect(surface, border, rect, width=1, border_radius=3)
