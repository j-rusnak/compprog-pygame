"""Statistics tab — concise numeric colony summary.

The bottom-bar Stats tab shows at-a-glance colony numbers (tier,
population, housing, buildings, research, stockpile totals).  Detailed
per-resource graphs and advanced analysis live in the
``AdvancedStatsOverlay`` popup, reachable from the "Advanced Statistics"
button rendered here.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pygame

from compprog_pygame.games.hex_colony.buildings import BuildingType
from compprog_pygame.games.hex_colony.resources import (
    PROCESSED_RESOURCES,
    RAW_RESOURCES,
    Resource,
)
from compprog_pygame.games.hex_colony.tech_tree import is_resource_available
from compprog_pygame.games.hex_colony.ui import (
    Fonts,
    TabContent,
    UI_ACCENT,
    UI_BG,
    UI_BORDER,
    UI_MUTED,
    UI_OK,
    UI_TEXT,
)
from compprog_pygame.games.hex_colony.ui_advanced_stats import StatsHistory

if TYPE_CHECKING:
    from compprog_pygame.games.hex_colony.tech_tree import TechTree, TierTracker
    from compprog_pygame.games.hex_colony.world import World


_HOMELESS_COLOR = (220, 90, 90)


class StatsTabContent(TabContent):
    """Compact numeric dashboard; delegates graphs to the advanced popup."""

    def __init__(self) -> None:
        self.history: StatsHistory = StatsHistory()
        self.tech_tree: "TechTree | None" = None
        self.tier_tracker: "TierTracker | None" = None
        self.god_mode_getter: "callable | None" = None
        self.on_open_advanced: "callable | None" = None
        self._adv_btn: pygame.Rect = pygame.Rect(0, 0, 0, 0)

    # ── Helpers ──────────────────────────────────────────────────

    def _god(self) -> bool:
        return bool(self.god_mode_getter and self.god_mode_getter())

    def _count_stock(
        self, world: "World", group: frozenset[Resource],
    ) -> int:
        god = self._god()
        total = 0.0
        for res in group:
            if god or is_resource_available(
                res, self.tech_tree, self.tier_tracker,
            ):
                total += world.inventory[res]
        return int(total)

    # ── Drawing ──────────────────────────────────────────────────

    def draw_content(
        self, surface: pygame.Surface, rect: pygame.Rect, world: "World",
    ) -> None:
        # Note: stats sampling is driven by Game.run() every frame so
        # history captures data from t=0, regardless of whether this
        # tab has ever been viewed.
        from compprog_pygame.games.hex_colony.tech_tree import TIERS
        tier = self.tier_tracker.current_tier if self.tier_tracker else 0
        tier_name = TIERS[tier].name if self.tier_tracker else ""
        pop = world.population.count
        housing = world.connected_housing()
        homeless = max(0, pop - housing)
        n_buildings = sum(
            1 for b in world.buildings.buildings
            if b.type not in (BuildingType.PATH, BuildingType.BRIDGE,
                              BuildingType.CAMP, BuildingType.WALL)
            and getattr(b, "faction", "SURVIVOR") == "SURVIVOR"
        )
        idle = sum(
            1 for p in world.population.people
            if p.workplace is None and p.workplace_target is None
        )
        research_count = getattr(world, "_tech_research_count", 0)
        raw_stock = self._count_stock(world, RAW_RESOURCES)
        processed_stock = self._count_stock(world, PROCESSED_RESOURCES)
        time_s = int(world.real_time_elapsed)

        # Stat cards + Advanced button
        btn_w = 170
        stat_area = pygame.Rect(
            rect.x, rect.y, rect.w - btn_w - 12, rect.h,
        )
        pop_color = _HOMELESS_COLOR if homeless > 0 else UI_TEXT
        stats: list[tuple[str, str, tuple[int, int, int]]] = [
            ("Tier", f"{tier}  {tier_name}", (255, 215, 0)),
            ("Population", f"{pop}/{housing}", pop_color),
            ("Buildings", f"{n_buildings}", UI_TEXT),
            ("Idle workers", f"{idle}",
             UI_OK if idle == 0 else UI_ACCENT),
            ("Research", f"{research_count}", UI_TEXT),
            ("Raw stock", f"{raw_stock}", UI_TEXT),
            ("Processed", f"{processed_stock}", UI_TEXT),
            ("Time", _fmt_time(time_s), UI_MUTED),
        ]

        cols = 4
        rows = (len(stats) + cols - 1) // cols
        cell_w = max(90, stat_area.w // cols)
        cell_h = max(44, stat_area.h // max(1, rows))
        for i, (label, value, color) in enumerate(stats):
            cx = stat_area.x + (i % cols) * cell_w
            cy = stat_area.y + (i // cols) * cell_h
            cell = pygame.Rect(cx + 4, cy + 2, cell_w - 8, cell_h - 4)
            pygame.draw.rect(surface, UI_BG, cell, border_radius=4)
            pygame.draw.rect(surface, UI_BORDER, cell, width=1, border_radius=4)
            lbl = Fonts.tiny().render(label, True, UI_MUTED)
            surface.blit(lbl, (cell.x + 6, cell.y + 4))
            val = Fonts.body().render(value, True, color)
            if val.get_width() > cell.w - 10:
                val = Fonts.small().render(value, True, color)
            surface.blit(val, (
                cell.x + 6,
                cell.bottom - val.get_height() - 4,
            ))

        # Advanced Statistics button
        self._adv_btn = pygame.Rect(
            rect.right - btn_w - 4, rect.y + 6,
            btn_w, rect.h - 12,
        )
        mouse_pos = pygame.mouse.get_pos()
        hovered = self._adv_btn.collidepoint(mouse_pos)
        bg = UI_ACCENT if hovered else UI_BG
        pygame.draw.rect(surface, bg, self._adv_btn, border_radius=6)
        pygame.draw.rect(
            surface, UI_BORDER, self._adv_btn, width=2, border_radius=6,
        )
        title = Fonts.body().render("Advanced", True, UI_TEXT)
        sub = Fonts.small().render("Statistics", True, UI_TEXT)
        icon = Fonts.label().render("\u2261", True, UI_ACCENT)
        cx = self._adv_btn.centerx
        cy = self._adv_btn.centery
        surface.blit(icon, (cx - icon.get_width() // 2, cy - 36))
        surface.blit(title, (cx - title.get_width() // 2, cy - 6))
        surface.blit(sub, (cx - sub.get_width() // 2, cy + 14))

    def handle_event(
        self, event: pygame.event.Event, rect: pygame.Rect,
    ) -> bool:
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self._adv_btn.collidepoint(event.pos):
                if self.on_open_advanced is not None:
                    self.on_open_advanced()
                return True
        return False


def _fmt_time(seconds: int) -> str:
    m, s = divmod(seconds, 60)
    if m >= 60:
        h, m = divmod(m, 60)
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"
