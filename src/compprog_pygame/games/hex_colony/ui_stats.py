"""Statistics tab content for Hex Colony bottom bar.

Tracks production/consumption rates and shows a simple sparkline graph
of resource levels over time.
"""

from __future__ import annotations

from collections import deque
from typing import TYPE_CHECKING

import pygame

from compprog_pygame.games.hex_colony.resources import Resource
from compprog_pygame.games.hex_colony.ui import (
    Fonts,
    TabContent,
    UI_MUTED,
    RESOURCE_COLORS,
    RESOURCE_ICONS,
)

if TYPE_CHECKING:
    from compprog_pygame.games.hex_colony.world import World

_HISTORY_LEN = 120
_SAMPLE_INTERVAL = 1.0


class StatsTabContent(TabContent):
    """Shows resource history as sparkline graphs."""

    def __init__(self) -> None:
        self._history: dict[Resource, deque[float]] = {
            r: deque(maxlen=_HISTORY_LEN) for r in Resource
        }
        self._last_sample: float = 0.0
        self._tracked: list[Resource] = [
            Resource.WOOD, Resource.STONE, Resource.FOOD,
            Resource.FIBER, Resource.IRON, Resource.COPPER,
        ]

    def _sample(self, world: World) -> None:
        for res in self._tracked:
            self._history[res].append(world.inventory[res])

    def draw_content(
        self, surface: pygame.Surface, rect: pygame.Rect, world: World,
    ) -> None:
        # Sample at interval
        if world.time_elapsed - self._last_sample >= _SAMPLE_INTERVAL:
            self._sample(world)
            self._last_sample = world.time_elapsed

        # Layout: divide rect into rows for each tracked resource
        n = len(self._tracked)
        row_h = max(16, rect.h // max(1, n))
        y = rect.y + 4
        label_w = 70
        graph_x = rect.x + label_w
        graph_w = rect.w - label_w - 10

        for res in self._tracked:
            color = RESOURCE_COLORS.get(res, (200, 200, 200))
            icon = RESOURCE_ICONS.get(res, "?")
            # Label
            label = Fonts.small().render(f"{icon} {res.name}", True, color)
            surface.blit(label, (rect.x + 6, y + 1))

            # Value
            val = world.inventory[res]
            val_surf = Fonts.tiny().render(f"{val:.0f}", True, UI_MUTED)
            surface.blit(val_surf, (rect.x + 6, y + 13))

            # Sparkline
            data = self._history[res]
            if len(data) >= 2:
                max_val = max(max(data), 1)
                points = []
                for i, v in enumerate(data):
                    px = graph_x + int(i * graph_w / (_HISTORY_LEN - 1))
                    py = y + row_h - 2 - int((v / max_val) * (row_h - 6))
                    points.append((px, py))
                if len(points) >= 2:
                    pygame.draw.lines(surface, color, False, points, 1)

            y += row_h

    def handle_event(
        self, event: pygame.event.Event, rect: pygame.Rect,
    ) -> bool:
        return False
