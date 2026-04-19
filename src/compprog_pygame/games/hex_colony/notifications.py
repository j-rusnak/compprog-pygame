"""Toast notification system for Hex Colony.

Provides a simple queue of dismissible messages that appear in the
top-right corner and fade out after a short duration.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pygame


@dataclass
class _Toast:
    text: str
    color: tuple[int, int, int]
    remaining: float  # seconds left to display
    alpha: int = 255


class NotificationManager:
    """Manages on-screen toast notifications."""

    DURATION = 4.0       # seconds each toast lives
    FADE_TIME = 0.8      # seconds of fade-out at end
    MAX_VISIBLE = 5      # max toasts shown at once
    TOAST_HEIGHT = 28
    TOAST_PAD = 4
    TOAST_MARGIN_X = 10
    TOAST_MARGIN_Y = 48  # below resource bar

    def __init__(self) -> None:
        self._toasts: list[_Toast] = []
        self._font: pygame.font.Font | None = None

    def _get_font(self) -> pygame.font.Font:
        if self._font is None:
            self._font = pygame.font.Font(None, 22)
        return self._font

    def push(self, text: str, color: tuple[int, int, int] = (242, 244, 255)) -> None:
        """Add a new toast notification."""
        self._toasts.append(_Toast(text=text, color=color, remaining=self.DURATION))
        # Trim old toasts if too many
        while len(self._toasts) > self.MAX_VISIBLE * 2:
            self._toasts.pop(0)

    def update(self, dt: float) -> None:
        """Advance timers and remove expired toasts."""
        for toast in self._toasts:
            toast.remaining -= dt
            if toast.remaining < self.FADE_TIME:
                toast.alpha = max(0, int(255 * (toast.remaining / self.FADE_TIME)))
        self._toasts = [t for t in self._toasts if t.remaining > 0]

    def draw(self, surface: pygame.Surface) -> None:
        """Draw toasts in the top-right corner."""
        font = self._get_font()
        sw = surface.get_width()
        visible = self._toasts[-self.MAX_VISIBLE:]
        y = self.TOAST_MARGIN_Y
        for toast in visible:
            text_surf = font.render(toast.text, True, toast.color)
            tw, th = text_surf.get_size()
            box_w = tw + 16
            box_h = max(th + 8, self.TOAST_HEIGHT)
            bx = sw - box_w - self.TOAST_MARGIN_X
            by = y

            # Background
            bg = pygame.Surface((box_w, box_h), pygame.SRCALPHA)
            bg.fill((16, 24, 45, min(180, toast.alpha)))
            pygame.draw.rect(bg, (60, 70, 100, min(200, toast.alpha)),
                             (0, 0, box_w, box_h), width=1)
            surface.blit(bg, (bx, by))

            # Text
            text_surf.set_alpha(toast.alpha)
            surface.blit(text_surf, (bx + 8, by + (box_h - th) // 2))

            y += box_h + self.TOAST_PAD
