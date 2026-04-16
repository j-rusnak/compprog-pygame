"""Camera / viewport for scrolling and zooming the hex map."""

from __future__ import annotations

from compprog_pygame.games.hex_colony import params


class Camera:
    """Tracks offset and zoom for the top-down view."""

    MIN_ZOOM = params.CAMERA_ZOOM_MIN
    MAX_ZOOM = params.CAMERA_ZOOM_MAX
    _ZOOM_SMOOTH = 50.0  # lerp speed for zoom smoothing (higher = snappier)

    def __init__(self, screen_w: int, screen_h: int) -> None:
        self.screen_w = screen_w
        self.screen_h = screen_h
        # World offset: the pixel position of the camera centre in world coords
        self.x: float = 0.0
        self.y: float = 0.0
        self.zoom: float = 1.0
        self._target_zoom: float = 1.0
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
        """Zoom towards/away from the mouse position (smoothed)."""
        self._target_zoom = max(self.MIN_ZOOM, min(self.MAX_ZOOM, self._target_zoom * factor))
        self._zoom_mouse = mouse_pos

    def update(self, dt: float) -> None:
        """Call once per frame to apply smooth zoom interpolation."""
        if abs(self.zoom - self._target_zoom) < 1e-6:
            self.zoom = self._target_zoom
            return
        old_zoom = self.zoom
        t = min(1.0, self._ZOOM_SMOOTH * dt)
        self.zoom = old_zoom + (self._target_zoom - old_zoom) * t
        # Adjust offset so the point under the cursor stays fixed
        mp = getattr(self, "_zoom_mouse", (self.screen_w // 2, self.screen_h // 2))
        mx = mp[0] - self.screen_w / 2
        my = mp[1] - self.screen_h / 2
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
