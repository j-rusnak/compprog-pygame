"""Camera / viewport for scrolling and zooming the hex map."""

from __future__ import annotations


class Camera:
    """Tracks offset and zoom for the top-down view."""

    MIN_ZOOM = 0.3
    MAX_ZOOM = 3.0

    def __init__(self, screen_w: int, screen_h: int) -> None:
        self.screen_w = screen_w
        self.screen_h = screen_h
        # World offset: the pixel position of the camera centre in world coords
        self.x: float = 0.0
        self.y: float = 0.0
        self.zoom: float = 1.0
        self._dragging = False
        self._drag_start: tuple[int, int] = (0, 0)
        self._cam_start: tuple[float, float] = (0.0, 0.0)

    def resize(self, w: int, h: int) -> None:
        self.screen_w = w
        self.screen_h = h

    # ── Input helpers ─────────────────────────────────────────────

    def start_drag(self, mouse_pos: tuple[int, int]) -> None:
        self._dragging = True
        self._drag_start = mouse_pos
        self._cam_start = (self.x, self.y)

    def drag(self, mouse_pos: tuple[int, int]) -> None:
        if not self._dragging:
            return
        dx = mouse_pos[0] - self._drag_start[0]
        dy = mouse_pos[1] - self._drag_start[1]
        self.x = self._cam_start[0] - dx / self.zoom
        self.y = self._cam_start[1] - dy / self.zoom

    def stop_drag(self) -> None:
        self._dragging = False

    def zoom_at(self, mouse_pos: tuple[int, int], factor: float) -> None:
        """Zoom towards/away from the mouse position."""
        old_zoom = self.zoom
        self.zoom = max(self.MIN_ZOOM, min(self.MAX_ZOOM, self.zoom * factor))
        # Adjust offset so the point under the cursor stays fixed
        mx = mouse_pos[0] - self.screen_w / 2
        my = mouse_pos[1] - self.screen_h / 2
        self.x += mx * (1 / old_zoom - 1 / self.zoom)
        self.y += my * (1 / old_zoom - 1 / self.zoom)

    # ── Coordinate conversion ────────────────────────────────────

    def world_to_screen(self, wx: float, wy: float) -> tuple[float, float]:
        sx = (wx - self.x) * self.zoom + self.screen_w / 2
        sy = (wy - self.y) * self.zoom + self.screen_h / 2
        return sx, sy

    def screen_to_world(self, sx: float, sy: float) -> tuple[float, float]:
        wx = (sx - self.screen_w / 2) / self.zoom + self.x
        wy = (sy - self.screen_h / 2) / self.zoom + self.y
        return wx, wy
