"""Resource bar panel — top-of-screen tier progression display.

Shows tier level/name, population, and tier requirement progress on the
left. Active research + mode indicators on the right.  Items are
omitted gracefully when space is tight so nothing ever overflows.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pygame

from compprog_pygame.games.hex_colony.ui import (
    Fonts,
    Panel,
    UI_ACCENT,
    UI_BAD,
    UI_BORDER,
    UI_MUTED,
    UI_OK,
    UI_TEXT,
    draw_panel_bg,
    render_text_clipped,
)
from compprog_pygame.games.hex_colony.strings import (
    RESOURCE_BAR_DELETE,
    RESOURCE_BAR_SANDBOX,
    RESOURCE_BAR_MAX_TIER,
)

if TYPE_CHECKING:
    from compprog_pygame.games.hex_colony.tech_tree import TechTree, TierTracker
    from compprog_pygame.games.hex_colony.world import World


_PERSON_COLOR = (230, 210, 170)
_TIER_COLOR = (255, 215, 0)

_BAR_HEIGHT = 38
_PADDING_X = 12
_ITEM_GAP = 16
_GROUP_GAP = 22


class ResourceBar(Panel):
    """Top bar showing tier progression and population."""

    def __init__(self) -> None:
        super().__init__()
        self.sandbox = False
        self.delete_mode = False
        self.sim_speed: float = 1.0
        self._on_pop_change: "callable | None" = None
        self.tier_tracker: "TierTracker | None" = None
        self.tech_tree: "TechTree | None" = None
        self.world: "World | None" = None
        self._btn_minus = pygame.Rect(0, 0, 0, 0)
        self._btn_plus = pygame.Rect(0, 0, 0, 0)

    def set_on_pop_change(self, callback) -> None:
        self._on_pop_change = callback

    def layout(self, screen_w: int, screen_h: int) -> None:
        self.rect = pygame.Rect(0, 0, screen_w, _BAR_HEIGHT)

    def draw(self, surface: pygame.Surface, world: World) -> None:
        draw_panel_bg(surface, self.rect, accent_edge="bottom")
        cy = self.rect.centery
        font_val = Fonts.body()
        font_small = Fonts.small()
        font_icon = Fonts.label()

        # Right side first — reserve space so the left side can truncate.
        right_end = self._draw_right_side(surface, cy, font_val, font_small)

        left_max_x = right_end - _ITEM_GAP
        x = _PADDING_X

        x = self._draw_population(surface, x, cy, left_max_x, world,
                                  font_val, font_icon)
        if x >= left_max_x:
            return

        if x + 8 < left_max_x:
            pygame.draw.line(surface, UI_BORDER,
                             (x, 8), (x, _BAR_HEIGHT - 8), 1)
            x += _GROUP_GAP // 2

        self._draw_tier(surface, x, cy, left_max_x, world,
                        font_val, font_small)

    def _draw_population(
        self, surface: pygame.Surface, x: int, cy: int, max_x: int,
        world: World,
        font_val: pygame.font.Font, font_icon: pygame.font.Font,
    ) -> int:
        pop = world.population.count
        housing = world.connected_housing()
        pop_color = UI_BAD if pop > housing else UI_TEXT
        icon = font_icon.render("\u263a", True, _PERSON_COLOR)
        text = font_val.render(f"{pop}/{housing}", True, pop_color)
        if x + icon.get_width() + 4 + text.get_width() > max_x:
            return x
        surface.blit(icon, (x, cy - icon.get_height() // 2))
        x += icon.get_width() + 4
        surface.blit(text, (x, cy - text.get_height() // 2))
        x += text.get_width() + 6

        if self.sandbox:
            btn_sz = 20
            btn_y = cy - btn_sz // 2
            if x + btn_sz * 2 + 4 <= max_x:
                self._btn_minus = pygame.Rect(x, btn_y, btn_sz, btn_sz)
                pygame.draw.rect(surface, UI_BORDER, self._btn_minus, border_radius=3)
                ms = font_val.render("\u2212", True, UI_TEXT)
                surface.blit(ms, (
                    self._btn_minus.centerx - ms.get_width() // 2,
                    self._btn_minus.centery - ms.get_height() // 2,
                ))
                x += btn_sz + 2
                self._btn_plus = pygame.Rect(x, btn_y, btn_sz, btn_sz)
                pygame.draw.rect(surface, UI_BORDER, self._btn_plus, border_radius=3)
                ps = font_val.render("+", True, UI_TEXT)
                surface.blit(ps, (
                    self._btn_plus.centerx - ps.get_width() // 2,
                    self._btn_plus.centery - ps.get_height() // 2,
                ))
                x += btn_sz + 4
        return x

    def _draw_tier(
        self, surface: pygame.Surface, x: int, cy: int, max_x: int,
        world: World,
        font_val: pygame.font.Font, font_small: pygame.font.Font,
    ) -> int:
        if self.tier_tracker is None:
            return x
        from compprog_pygame.games.hex_colony.tech_tree import TIERS
        lvl = self.tier_tracker.current_tier
        tier_name = TIERS[lvl].name if lvl < len(TIERS) else "Max"

        tier_label = render_text_clipped(
            font_val, f"Tier {lvl}: {tier_name}", _TIER_COLOR, max_x - x,
        )
        surface.blit(tier_label, (x, cy - tier_label.get_height() // 2))
        x += tier_label.get_width() + _ITEM_GAP

        progress = self.tier_tracker.check_requirements(world)
        if not progress:
            if x + 80 <= max_x:
                m = font_small.render(RESOURCE_BAR_MAX_TIER, True, UI_MUTED)
                surface.blit(m, (x, cy - m.get_height() // 2))
                x += m.get_width()
            return x

        arrow = font_small.render("\u2192", True, UI_MUTED)
        if x + arrow.get_width() + 6 >= max_x:
            return x
        surface.blit(arrow, (x, cy - arrow.get_height() // 2))
        x += arrow.get_width() + 6

        for name, (current, required) in progress.items():
            chunk = f"{name}: {int(current)}/{int(required)}"
            chunk_w = font_small.size(chunk)[0]
            if x + chunk_w > max_x:
                dots = font_small.render("\u2026", True, UI_MUTED)
                if x + dots.get_width() <= max_x:
                    surface.blit(dots, (x, cy - dots.get_height() // 2))
                    x += dots.get_width()
                break
            done = current >= required
            col = UI_OK if done else UI_TEXT
            label = font_small.render(f"{name}:", True, UI_MUTED)
            surface.blit(label, (x, cy - label.get_height() // 2))
            x += label.get_width() + 4
            val = font_small.render(
                f"{int(current)}/{int(required)}", True, col,
            )
            surface.blit(val, (x, cy - val.get_height() // 2))
            x += val.get_width() + _ITEM_GAP
        return x

    def _draw_right_side(
        self, surface: pygame.Surface, cy: int,
        font_val: pygame.font.Font, font_small: pygame.font.Font,
    ) -> int:
        """Draw right-aligned indicators. Returns leftmost x used."""
        rx = self.rect.right - _PADDING_X

        if self.delete_mode:
            s = font_val.render(RESOURCE_BAR_DELETE, True, UI_BAD)
            rx -= s.get_width()
            surface.blit(s, (rx, cy - s.get_height() // 2))
            rx -= _ITEM_GAP

        if self.sandbox:
            s = font_val.render(RESOURCE_BAR_SANDBOX, True, UI_ACCENT)
            rx -= s.get_width()
            surface.blit(s, (rx, cy - s.get_height() // 2))
            rx -= _ITEM_GAP

        if self.sim_speed > 1.0:
            s = font_val.render(f"{self.sim_speed:.0f}x", True, UI_ACCENT)
            rx -= s.get_width()
            surface.blit(s, (rx, cy - s.get_height() // 2))
            rx -= _ITEM_GAP

        if self.tech_tree is not None and self.tech_tree.current_research is not None:
            from compprog_pygame.games.hex_colony.tech_tree import TECH_NODES
            node = TECH_NODES.get(self.tech_tree.current_research)
            if node is not None:
                pct = int(self.tech_tree.research_progress / node.time * 100)
                s = font_small.render(
                    f"\u2261 {node.name}: {pct}%", True, UI_ACCENT,
                )
                rx -= s.get_width()
                surface.blit(s, (rx, cy - s.get_height() // 2))
                rx -= _ITEM_GAP

        return rx

    def handle_event(self, event: pygame.event.Event) -> bool:
        if not self.sandbox:
            return False
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self._btn_minus.collidepoint(event.pos):
                if self._on_pop_change:
                    self._on_pop_change(-1)
                return True
            if self._btn_plus.collidepoint(event.pos):
                if self._on_pop_change:
                    self._on_pop_change(1)
                return True
        return False
