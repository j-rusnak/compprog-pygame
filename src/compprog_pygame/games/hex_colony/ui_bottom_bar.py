"""Bottom bar panel — tabbed panel for buildings, info, and future content.

The bottom bar has two visual layers:

1. **Tab strip** — a row of clickable tab buttons along the bottom edge.
2. **Content area** — a panel that slides up when a tab is active,
   showing that tab's ``TabContent``.

Clicking the active tab again collapses the content area.

Adding a tab
~~~~~~~~~~~~
See the docstring in ``ui.py`` for the general pattern.  In short:

1.  Subclass ``TabContent`` from ``ui.py``.
2.  Override ``draw_content(surface, rect, world)`` with your rendering.
3.  Call ``bottom_bar.add_tab("MyLabel", MyContent())`` or add it inside
    ``_create_default_tabs()``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import pygame

from compprog_pygame.games.hex_colony.buildings import (
    BUILDING_COSTS,
    BuildingType,
)
from compprog_pygame.games.hex_colony.resources import Resource

from compprog_pygame.games.hex_colony.ui import (
    Panel,
    TabContent,
    UI_ACCENT,
    UI_BG,
    UI_BORDER,
    UI_MUTED,
    UI_TAB_ACTIVE,
    UI_TAB_HOVER,
    UI_TAB_INACTIVE,
    UI_TEXT,
    draw_panel_bg,
)

if TYPE_CHECKING:
    from compprog_pygame.games.hex_colony.world import World


# ── Layout constants ─────────────────────────────────────────────

_TAB_HEIGHT = 32
_CONTENT_HEIGHT = 140
_TAB_MIN_WIDTH = 90
_TAB_PAD_X = 16


# ── Tab definition ───────────────────────────────────────────────

@dataclass
class _Tab:
    label: str
    content: TabContent
    label_surf: pygame.Surface | None = None


# ── Placeholder tab contents ─────────────────────────────────────

class BuildingsTabContent(TabContent):
    """Grid of available buildings with costs.

    Selecting a building here activates build mode.  The actual placement
    is handled by ``Game._on_left_click``.
    """

    BUILDABLE = [
        BuildingType.HOUSE,
        BuildingType.PATH,
        BuildingType.WOODCUTTER,
        BuildingType.QUARRY,
        BuildingType.GATHERER,
        BuildingType.STORAGE,
    ]

    _ICON: dict[BuildingType, str] = {
        BuildingType.HOUSE: "\u26fa",       # ⛺
        BuildingType.PATH: "\u2505",        # ┅
        BuildingType.WOODCUTTER: "\u2692",  # ⚒
        BuildingType.QUARRY: "\u26cf",      # ⛏
        BuildingType.GATHERER: "\u2618",    # ☘
        BuildingType.STORAGE: "\u2302",     # ⌂
    }

    _COLOR: dict[BuildingType, tuple[int, int, int]] = {
        BuildingType.HOUSE: (170, 140, 90),
        BuildingType.PATH: (185, 165, 120),
        BuildingType.WOODCUTTER: (160, 100, 50),
        BuildingType.QUARRY: (170, 170, 160),
        BuildingType.GATHERER: (100, 180, 80),
        BuildingType.STORAGE: (140, 120, 100),
    }

    _RES_ICON: dict[Resource, str] = {
        Resource.WOOD: "\u25b2",
        Resource.FIBER: "\u2022",
        Resource.STONE: "\u25a0",
        Resource.FOOD: "\u2665",
    }

    _RES_COL: dict[Resource, tuple[int, int, int]] = {
        Resource.WOOD: (160, 100, 50),
        Resource.FIBER: (120, 200, 80),
        Resource.STONE: (170, 170, 160),
        Resource.FOOD: (220, 100, 80),
    }

    _DESC: dict[BuildingType, str] = {
        BuildingType.HOUSE: "Houses 5 colonists",
        BuildingType.PATH: "Connects buildings",
        BuildingType.WOODCUTTER: "Harvests nearby wood",
        BuildingType.QUARRY: "Harvests nearby stone",
        BuildingType.GATHERER: "Gathers fiber & food",
        BuildingType.STORAGE: "Stores 100 resources",
    }

    def __init__(self) -> None:
        self._font = pygame.font.Font(None, 24)
        self._small = pygame.font.Font(None, 20)
        self.hovered: int = -1
        self.selected_building: BuildingType | None = None
        self.delete_active = False
        self._on_select: "_BuildingSelectCallback | None" = None
        self._on_delete_toggle: "callable | None" = None

    def set_on_select(self, callback: "_BuildingSelectCallback") -> None:
        """Register a callback: ``callback(building_type | None)``."""
        self._on_select = callback

    def set_on_delete_toggle(self, callback) -> None:
        """Register a callback: ``callback(active: bool)``."""
        self._on_delete_toggle = callback

    def draw_content(
        self, surface: pygame.Surface, rect: pygame.Rect, world: World,
    ) -> None:
        card_w = 120
        card_h = rect.h - 20
        gap = 12
        x = rect.x + 10
        y = rect.y + 10

        for idx, btype in enumerate(self.BUILDABLE):
            card_rect = pygame.Rect(x, y, card_w, card_h)

            # Background
            is_sel = self.selected_building == btype
            is_hov = self.hovered == idx
            if is_sel:
                bg_col = UI_TAB_ACTIVE
            elif is_hov:
                bg_col = UI_TAB_HOVER
            else:
                bg_col = UI_TAB_INACTIVE

            card_bg = pygame.Surface((card_w, card_h), pygame.SRCALPHA)
            card_bg.fill(bg_col)
            surface.blit(card_bg, card_rect.topleft)
            border_col = UI_ACCENT if is_sel else UI_BORDER
            pygame.draw.rect(surface, border_col, card_rect, width=2, border_radius=4)

            # Icon + name
            icon = self._ICON.get(btype, "?")
            color = self._COLOR.get(btype, (200, 200, 200))
            icon_surf = self._font.render(icon, True, color)
            name_surf = self._font.render(btype.name.capitalize(), True, UI_TEXT)
            surface.blit(icon_surf, (x + 6, y + 6))
            surface.blit(name_surf, (x + 6 + icon_surf.get_width() + 4, y + 6))

            # Cost
            cost = BUILDING_COSTS[btype]
            cy = y + 6 + name_surf.get_height() + 4
            for res, amount in cost.costs.items():
                ri = self._small.render(self._RES_ICON[res], True, self._RES_COL[res])
                rv = self._small.render(str(amount), True, UI_MUTED)
                can_afford = world.inventory[res] >= amount
                if not can_afford:
                    rv = self._small.render(str(amount), True, (200, 60, 60))
                surface.blit(ri, (x + 8, cy))
                surface.blit(rv, (x + 8 + ri.get_width() + 2, cy))
                cy += rv.get_height() + 1

            # Description
            desc = self._DESC.get(btype)
            if desc:
                desc_surf = self._small.render(desc, True, UI_MUTED)
                surface.blit(desc_surf, (x + 8, y + card_h - desc_surf.get_height() - 4))

            x += card_w + gap

        # Delete tool card
        del_idx = len(self.BUILDABLE)
        card_rect = pygame.Rect(x, y, card_w, card_h)
        is_sel = self.delete_active
        is_hov = self.hovered == del_idx
        if is_sel:
            bg_col = (60, 20, 20, 220)
        elif is_hov:
            bg_col = UI_TAB_HOVER
        else:
            bg_col = UI_TAB_INACTIVE
        card_bg = pygame.Surface((card_w, card_h), pygame.SRCALPHA)
        card_bg.fill(bg_col)
        surface.blit(card_bg, card_rect.topleft)
        border_col = (200, 60, 60) if is_sel else UI_BORDER
        pygame.draw.rect(surface, border_col, card_rect, width=2, border_radius=4)
        icon_surf = self._font.render("\u2716", True, (200, 60, 60))  # ✖
        name_surf = self._font.render("Delete", True, UI_TEXT)
        surface.blit(icon_surf, (x + 6, y + 6))
        surface.blit(name_surf, (x + 6 + icon_surf.get_width() + 4, y + 6))
        hint_surf = self._small.render("50% refund", True, UI_MUTED)
        surface.blit(hint_surf, (x + 8, y + 6 + name_surf.get_height() + 4))

    def handle_event(
        self, event: pygame.event.Event, rect: pygame.Rect,
    ) -> bool:
        if event.type == pygame.MOUSEMOTION:
            self._update_hover(event.pos, rect)
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if rect.collidepoint(event.pos):
                idx = self._card_index_at(event.pos, rect)
                del_idx = len(self.BUILDABLE)
                if idx == del_idx:
                    # Toggle delete mode
                    self.delete_active = not self.delete_active
                    if self.delete_active:
                        self.selected_building = None
                        if self._on_select:
                            self._on_select(None)
                    if self._on_delete_toggle:
                        self._on_delete_toggle(self.delete_active)
                    return True
                elif 0 <= idx < len(self.BUILDABLE):
                    btype = self.BUILDABLE[idx]
                    if self.selected_building == btype:
                        self.selected_building = None
                    else:
                        self.selected_building = btype
                        self.delete_active = False
                        if self._on_delete_toggle:
                            self._on_delete_toggle(False)
                    if self._on_select:
                        self._on_select(self.selected_building)
                    return True
        return False

    def _update_hover(self, pos: tuple[int, int], rect: pygame.Rect) -> None:
        if not rect.collidepoint(pos):
            self.hovered = -1
            return
        self.hovered = self._card_index_at(pos, rect)

    def _card_index_at(self, pos: tuple[int, int], rect: pygame.Rect) -> int:
        card_w, gap = 120, 12
        local_x = pos[0] - rect.x - 10
        if local_x < 0:
            return -1
        idx = int(local_x // (card_w + gap))
        if local_x % (card_w + gap) > card_w:
            return -1
        return idx


# Callback type alias
_BuildingSelectCallback = "callable"


class InfoTabContent(TabContent):
    """Placeholder for a tile/colony info tab — extend later."""

    def __init__(self) -> None:
        self._font = pygame.font.Font(None, 22)

    def draw_content(
        self, surface: pygame.Surface, rect: pygame.Rect, world: World,
    ) -> None:
        mins, secs = divmod(int(world.time_elapsed), 60)
        text = self._font.render(
            f"Colony age: {mins}:{secs:02d}   |   "
            f"Population: {world.population.count}   |   "
            f"Buildings: {sum(1 for b in world.buildings.buildings if b.type != BuildingType.PATH)}",
            True, UI_MUTED,
        )
        surface.blit(text, (rect.x + 10, rect.y + rect.h // 2 - text.get_height() // 2))


# ── BottomBar panel ──────────────────────────────────────────────

class BottomBar(Panel):
    """Tabbed panel anchored to the bottom of the screen."""

    def __init__(self) -> None:
        super().__init__()
        self._tabs: list[_Tab] = []
        self._active: int = -1  # -1 = collapsed
        self._tab_font = pygame.font.Font(None, 24)
        self._tab_rects: list[pygame.Rect] = []
        self._hover_tab: int = -1
        self._content_rect = pygame.Rect(0, 0, 0, 0)
        self._create_default_tabs()

    @property
    def buildings_tab(self) -> BuildingsTabContent | None:
        for tab in self._tabs:
            if isinstance(tab.content, BuildingsTabContent):
                return tab.content
        return None

    def _create_default_tabs(self) -> None:
        self.add_tab("Buildings", BuildingsTabContent())
        self.add_tab("Info", InfoTabContent())

    def add_tab(self, label: str, content: TabContent) -> None:
        self._tabs.append(_Tab(label=label, content=content))
        self._rebuild_labels()

    def _rebuild_labels(self) -> None:
        for tab in self._tabs:
            tab.label_surf = self._tab_font.render(tab.label, True, UI_TEXT)

    def layout(self, screen_w: int, screen_h: int) -> None:
        total_h = _TAB_HEIGHT + (_CONTENT_HEIGHT if self._active >= 0 else 0)
        self.rect = pygame.Rect(0, screen_h - total_h, screen_w, total_h)

        # Tab strip rects
        self._tab_rects = []
        x = 4
        for tab in self._tabs:
            w = max(_TAB_MIN_WIDTH, (tab.label_surf.get_width() if tab.label_surf else 60) + _TAB_PAD_X * 2)
            tr = pygame.Rect(x, screen_h - total_h, w, _TAB_HEIGHT)
            self._tab_rects.append(tr)
            x += w + 2

        # Content area
        if self._active >= 0:
            self._content_rect = pygame.Rect(
                0, screen_h - total_h + _TAB_HEIGHT, screen_w, _CONTENT_HEIGHT,
            )
        else:
            self._content_rect = pygame.Rect(0, 0, 0, 0)

    def draw(self, surface: pygame.Surface, world: World) -> None:
        sw, sh = surface.get_size()

        # Content area background
        if self._active >= 0:
            draw_panel_bg(surface, self._content_rect, accent_edge="top")

        # Tab strip background
        strip_rect = pygame.Rect(0, self.rect.y, sw, _TAB_HEIGHT)
        strip_bg = pygame.Surface((sw, _TAB_HEIGHT), pygame.SRCALPHA)
        strip_bg.fill(UI_BG)
        surface.blit(strip_bg, strip_rect.topleft)

        # Individual tabs
        for idx, (tab, tr) in enumerate(zip(self._tabs, self._tab_rects)):
            is_active = idx == self._active
            is_hover = idx == self._hover_tab

            if is_active:
                col = UI_TAB_ACTIVE
            elif is_hover:
                col = UI_TAB_HOVER
            else:
                col = UI_TAB_INACTIVE

            tab_bg = pygame.Surface((tr.w, tr.h), pygame.SRCALPHA)
            tab_bg.fill(col)
            surface.blit(tab_bg, tr.topleft)
            border_col = UI_ACCENT if is_active else UI_BORDER
            pygame.draw.rect(surface, border_col, tr, width=2, border_radius=4)

            if tab.label_surf:
                lx = tr.x + (tr.w - tab.label_surf.get_width()) // 2
                ly = tr.y + (tr.h - tab.label_surf.get_height()) // 2
                surface.blit(tab.label_surf, (lx, ly))

        # Active tab content
        if 0 <= self._active < len(self._tabs):
            self._tabs[self._active].content.draw_content(
                surface, self._content_rect, world,
            )

    def handle_event(self, event: pygame.event.Event) -> bool:
        if event.type == pygame.MOUSEMOTION:
            self._hover_tab = -1
            for idx, tr in enumerate(self._tab_rects):
                if tr.collidepoint(event.pos):
                    self._hover_tab = idx
                    break
            # Forward to active tab content
            if self._active >= 0 and self._content_rect.collidepoint(event.pos):
                self._tabs[self._active].content.handle_event(
                    event, self._content_rect,
                )
                return True

        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            # Tab click
            for idx, tr in enumerate(self._tab_rects):
                if tr.collidepoint(event.pos):
                    if idx == self._active:
                        self._active = -1  # collapse
                    else:
                        self._active = idx
                    # Relayout to resize rect
                    sw, sh = pygame.display.get_surface().get_size()
                    self.layout(sw, sh)
                    return True
            # Content click
            if self._active >= 0 and self._content_rect.collidepoint(event.pos):
                return self._tabs[self._active].content.handle_event(
                    event, self._content_rect,
                )

        # Consume events that land inside our rect to prevent world interaction
        if hasattr(event, "pos") and self.rect.collidepoint(event.pos):
            return True
        return False
