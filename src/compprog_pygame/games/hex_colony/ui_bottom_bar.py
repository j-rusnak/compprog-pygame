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
    BuildingType,
)
from compprog_pygame.games.hex_colony.resources import BuildingInventory

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
    """Grid of available buildings organized by category.

    Shows building inventory counts and allows placement when stock > 0.
    """

    # Category definitions
    _CATEGORIES: list[tuple[str, list[BuildingType]]] = [
        ("Housing", [BuildingType.HABITAT]),
        ("Resource", [BuildingType.WOODCUTTER, BuildingType.QUARRY,
                      BuildingType.GATHERER, BuildingType.FARM, BuildingType.WELL]),
        ("Processing", [BuildingType.WORKSHOP, BuildingType.REFINERY, BuildingType.STORAGE]),
        ("Logistics", [BuildingType.PATH, BuildingType.BRIDGE, BuildingType.WALL]),
    ]

    # Flat list of all buildable types (for index mapping)
    BUILDABLE: list[BuildingType] = []
    for _cat_name, _cat_types in _CATEGORIES:
        BUILDABLE.extend(_cat_types)

    _ICON: dict[BuildingType, str] = {
        BuildingType.HABITAT: "\u2b22",     # ⬢
        BuildingType.PATH: "\u2505",        # ┅
        BuildingType.BRIDGE: "\u2550",      # ═
        BuildingType.WOODCUTTER: "\u2692",  # ⚒
        BuildingType.QUARRY: "\u26cf",      # ⛏
        BuildingType.GATHERER: "\u2618",    # ☘
        BuildingType.STORAGE: "\u2302",     # ⌂
        BuildingType.REFINERY: "\u2697",    # ⚗
        BuildingType.FARM: "\u2668",        # ♨
        BuildingType.WELL: "\u25ce",        # ◎
        BuildingType.WALL: "\u2588",        # █
        BuildingType.WORKSHOP: "\u2699",    # ⚙
    }

    _COLOR: dict[BuildingType, tuple[int, int, int]] = {
        BuildingType.HABITAT: (140, 155, 175),
        BuildingType.PATH: (185, 165, 120),
        BuildingType.BRIDGE: (140, 100, 55),
        BuildingType.WOODCUTTER: (160, 100, 50),
        BuildingType.QUARRY: (170, 170, 160),
        BuildingType.GATHERER: (100, 180, 80),
        BuildingType.STORAGE: (140, 120, 100),
        BuildingType.REFINERY: (90, 80, 100),
        BuildingType.FARM: (100, 160, 50),
        BuildingType.WELL: (60, 100, 180),
        BuildingType.WALL: (160, 155, 145),
        BuildingType.WORKSHOP: (180, 140, 60),
    }

    _DESC: dict[BuildingType, str] = {
        BuildingType.HABITAT: "Houses 6 survivors",
        BuildingType.PATH: "Connects buildings",
        BuildingType.BRIDGE: "Path over water",
        BuildingType.WOODCUTTER: "Harvests nearby wood",
        BuildingType.QUARRY: "Harvests nearby stone",
        BuildingType.GATHERER: "Gathers fiber & food",
        BuildingType.STORAGE: "Stores 100 resources",
        BuildingType.REFINERY: "Processes iron/copper",
        BuildingType.FARM: "Grows food steadily",
        BuildingType.WELL: "Boosts adjacent farms",
        BuildingType.WALL: "Defensive stone wall",
        BuildingType.WORKSHOP: "Crafts buildings",
    }

    def __init__(self) -> None:
        self._font = pygame.font.Font(None, 24)
        self._small = pygame.font.Font(None, 20)
        self._cat_font = pygame.font.Font(None, 22)
        self.hovered: int = -1
        self.selected_building: BuildingType | None = None
        self.delete_active = False
        self._on_select: "_BuildingSelectCallback | None" = None
        self._on_delete_toggle: "callable | None" = None
        self.building_inventory: BuildingInventory | None = None
        self._active_cat: int = 0  # which category tab is active

    def set_on_select(self, callback: "_BuildingSelectCallback") -> None:
        self._on_select = callback

    def set_on_delete_toggle(self, callback) -> None:
        self._on_delete_toggle = callback

    def draw_content(
        self, surface: pygame.Surface, rect: pygame.Rect, world: World,
    ) -> None:
        # Draw category tabs at top of content area
        cat_tab_h = 22
        cat_tab_y = rect.y + 2
        cat_x = rect.x + 6
        cat_tab_rects: list[pygame.Rect] = []
        for ci, (cat_name, _) in enumerate(self._CATEGORIES):
            tw = self._cat_font.size(cat_name)[0] + 16
            tr = pygame.Rect(cat_x, cat_tab_y, tw, cat_tab_h)
            cat_tab_rects.append(tr)
            is_active = ci == self._active_cat
            bg = UI_TAB_ACTIVE if is_active else UI_TAB_INACTIVE
            tab_bg = pygame.Surface((tw, cat_tab_h), pygame.SRCALPHA)
            tab_bg.fill(bg)
            surface.blit(tab_bg, tr.topleft)
            border = UI_ACCENT if is_active else UI_BORDER
            pygame.draw.rect(surface, border, tr, width=1, border_radius=3)
            label = self._cat_font.render(cat_name, True, UI_TEXT)
            surface.blit(label, (cat_x + 8, cat_tab_y + 2))
            cat_x += tw + 4
        self._cat_tab_rects = cat_tab_rects

        # Draw building cards for active category
        _, cat_types = self._CATEGORIES[self._active_cat]
        card_w = 120
        card_h = rect.h - cat_tab_h - 16
        gap = 12
        x = rect.x + 10
        y = rect.y + cat_tab_h + 8

        inv = self.building_inventory
        for idx, btype in enumerate(cat_types):
            card_rect = pygame.Rect(x, y, card_w, card_h)
            global_idx = self.BUILDABLE.index(btype)

            is_sel = self.selected_building == btype
            is_hov = self.hovered == global_idx
            stock = inv[btype] if inv else 0
            has_stock = stock > 0

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
            surface.blit(icon_surf, (x + 6, y + 4))
            surface.blit(name_surf, (x + 6 + icon_surf.get_width() + 4, y + 4))

            # Stock count
            stock_color = UI_TEXT if has_stock else (200, 60, 60)
            stock_surf = self._small.render(f"x{stock}", True, stock_color)
            surface.blit(stock_surf, (x + 8, y + 4 + name_surf.get_height() + 2))

            # Description
            desc = self._DESC.get(btype)
            if desc:
                desc_surf = self._small.render(desc, True, UI_MUTED)
                surface.blit(desc_surf, (x + 8, y + card_h - desc_surf.get_height() - 4))

            x += card_w + gap

        # Delete tool card
        card_rect = pygame.Rect(x, y, card_w, card_h)
        is_sel = self.delete_active
        del_global = len(self.BUILDABLE)
        is_hov = self.hovered == del_global
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
        icon_surf = self._font.render("\u2716", True, (200, 60, 60))
        name_surf = self._font.render("Delete", True, UI_TEXT)
        surface.blit(icon_surf, (x + 6, y + 4))
        surface.blit(name_surf, (x + 6 + icon_surf.get_width() + 4, y + 4))
        hint_surf = self._small.render("Returns to inventory", True, UI_MUTED)
        surface.blit(hint_surf, (x + 8, y + 4 + name_surf.get_height() + 2))

    def handle_event(
        self, event: pygame.event.Event, rect: pygame.Rect,
    ) -> bool:
        if event.type == pygame.MOUSEMOTION:
            self._update_hover(event.pos, rect)
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if rect.collidepoint(event.pos):
                # Check category tab clicks
                for ci, tr in enumerate(getattr(self, '_cat_tab_rects', [])):
                    if tr.collidepoint(event.pos):
                        self._active_cat = ci
                        self.hovered = -1
                        return True
                # Check building card clicks
                _, cat_types = self._CATEGORIES[self._active_cat]
                cat_tab_h = 22
                idx = self._card_index_at(event.pos, rect, len(cat_types), cat_tab_h)
                del_idx = len(cat_types)
                if idx == del_idx:
                    self.delete_active = not self.delete_active
                    if self.delete_active:
                        self.selected_building = None
                        if self._on_select:
                            self._on_select(None)
                    if self._on_delete_toggle:
                        self._on_delete_toggle(self.delete_active)
                    return True
                elif 0 <= idx < len(cat_types):
                    btype = cat_types[idx]
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
        _, cat_types = self._CATEGORIES[self._active_cat]
        cat_tab_h = 22
        local_idx = self._card_index_at(pos, rect, len(cat_types), cat_tab_h)
        if local_idx < 0:
            self.hovered = -1
        elif local_idx >= len(cat_types):
            # Delete card
            self.hovered = len(self.BUILDABLE)
        else:
            self.hovered = self.BUILDABLE.index(cat_types[local_idx])

    def _card_index_at(self, pos: tuple[int, int], rect: pygame.Rect,
                       num_cards: int, cat_tab_h: int) -> int:
        card_w, gap = 120, 12
        local_x = pos[0] - rect.x - 10
        local_y = pos[1] - rect.y - cat_tab_h - 8
        if local_x < 0 or local_y < 0:
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
