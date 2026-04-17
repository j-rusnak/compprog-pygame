"""Bottom bar panel — tabbed panel for buildings, info, and stats.

Layout
------
* **Tab strip** (32px tall) — row of clickable tab buttons along the
  bottom edge.  Always visible.
* **Content area** (140px tall) — shown when a tab is active.

Clicking the active tab again collapses the content area.

Adding a tab
~~~~~~~~~~~~
1.  Subclass ``TabContent``.
2.  Override ``draw_content(surface, rect, world)``.
3.  Call ``bottom_bar.add_tab("MyLabel", MyContent())``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import pygame

from compprog_pygame.games.hex_colony.buildings import BuildingType
from compprog_pygame.games.hex_colony.resources import (
    BuildingInventory,
    Resource,
)
from compprog_pygame.games.hex_colony.resource_icons import get_resource_icon
from compprog_pygame.games.hex_colony.tech_tree import is_building_available
from compprog_pygame.games.hex_colony.ui import (
    Fonts,
    Panel,
    TabContent,
    UI_ACCENT,
    UI_BAD,
    UI_BG,
    UI_BORDER,
    UI_MUTED,
    UI_TAB_ACTIVE,
    UI_TAB_HOVER,
    UI_TAB_INACTIVE,
    UI_TEXT,
    draw_panel_bg,
    render_text_clipped,
)

if TYPE_CHECKING:
    from compprog_pygame.games.hex_colony.world import World


# ── Layout constants ─────────────────────────────────────────────

_TAB_HEIGHT = 32
_CONTENT_HEIGHT = 150
_TAB_MIN_WIDTH = 90
_TAB_PAD_X = 16

_CAT_TAB_H = 24
_CARD_H = 96
_CARD_W_MIN = 128
_CARD_W_MAX = 160
_CARD_GAP = 10
_CARD_MARGIN_X = 12


# ── Tab definition ───────────────────────────────────────────────

@dataclass
class _Tab:
    label: str
    content: TabContent
    label_surf: pygame.Surface | None = None


# ── Buildings tab ────────────────────────────────────────────────

class BuildingsTabContent(TabContent):
    """Categorised grid of buildings with inventory counts."""

    _CATEGORIES: list[tuple[str, list[BuildingType]]] = [
        ("Core", [BuildingType.RESEARCH_CENTER]),
        ("Housing", [BuildingType.HABITAT]),
        ("Resource", [BuildingType.WOODCUTTER, BuildingType.QUARRY,
                      BuildingType.GATHERER, BuildingType.FARM, BuildingType.WELL]),
        ("Processing", [BuildingType.WORKSHOP, BuildingType.FORGE,
                        BuildingType.ASSEMBLER, BuildingType.REFINERY,
                        BuildingType.STORAGE]),
        ("Logistics", [BuildingType.PATH, BuildingType.BRIDGE, BuildingType.WALL]),
    ]

    BUILDABLE: list[BuildingType] = []
    for _cat_name, _cat_types in _CATEGORIES:
        BUILDABLE.extend(_cat_types)

    _ICON: dict[BuildingType, str] = {
        BuildingType.HABITAT: "\u2b22",
        BuildingType.PATH: "\u2505",
        BuildingType.BRIDGE: "\u2550",
        BuildingType.WOODCUTTER: "\u2692",
        BuildingType.QUARRY: "\u26cf",
        BuildingType.GATHERER: "\u2618",
        BuildingType.STORAGE: "\u2302",
        BuildingType.REFINERY: "\u2697",
        BuildingType.FARM: "\u2668",
        BuildingType.WELL: "\u25ce",
        BuildingType.WALL: "\u2588",
        BuildingType.WORKSHOP: "\u2699",
        BuildingType.FORGE: "\u2692",
        BuildingType.ASSEMBLER: "\u25a6",
        BuildingType.RESEARCH_CENTER: "\u2261",
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
        BuildingType.FORGE: (110, 100, 92),
        BuildingType.ASSEMBLER: (120, 140, 165),
        BuildingType.RESEARCH_CENTER: (70, 130, 200),
    }

    _DESC: dict[BuildingType, str] = {
        BuildingType.HABITAT: "Houses 6 survivors",
        BuildingType.PATH: "Connects buildings",
        BuildingType.BRIDGE: "Path over water",
        BuildingType.WOODCUTTER: "Harvests wood",
        BuildingType.QUARRY: "Harvests stone",
        BuildingType.GATHERER: "Gathers fiber & food",
        BuildingType.STORAGE: "Stores 100 resources",
        BuildingType.REFINERY: "Processes metals",
        BuildingType.FARM: "Grows food",
        BuildingType.WELL: "Boosts nearby farms",
        BuildingType.WALL: "Defensive wall",
        BuildingType.WORKSHOP: "Crafts buildings",
        BuildingType.FORGE: "Smelts metal bars",
        BuildingType.ASSEMBLER: "Builds advanced parts",
        BuildingType.RESEARCH_CENTER: "Unlocks tech tree",
    }

    _LABEL: dict[BuildingType, str] = {
        BuildingType.HABITAT: "Habitat",
        BuildingType.PATH: "Path",
        BuildingType.BRIDGE: "Bridge",
        BuildingType.WALL: "Wall",
        BuildingType.WOODCUTTER: "Woodcutter",
        BuildingType.QUARRY: "Quarry",
        BuildingType.GATHERER: "Gatherer",
        BuildingType.STORAGE: "Storage",
        BuildingType.REFINERY: "Refinery",
        BuildingType.FARM: "Farm",
        BuildingType.WELL: "Well",
        BuildingType.WORKSHOP: "Workshop",
        BuildingType.FORGE: "Forge",
        BuildingType.ASSEMBLER: "Assembler",
        BuildingType.RESEARCH_CENTER: "Research",
    }

    # Harvester buildings: show the sprite of the resource they yield
    # next to the building name instead of a unicode glyph.
    _HARVEST_ICON_RESOURCE: dict[BuildingType, Resource] = {
        BuildingType.WOODCUTTER: Resource.WOOD,
        BuildingType.QUARRY: Resource.STONE,
        BuildingType.GATHERER: Resource.FIBER,
        BuildingType.FARM: Resource.FOOD,
        BuildingType.WELL: Resource.FOOD,
        BuildingType.REFINERY: Resource.IRON,
    }

    def __init__(self) -> None:
        self.hovered: BuildingType | str | None = None
        self.selected_building: BuildingType | None = None
        self.delete_active = False
        self._on_select: "callable | None" = None
        self._on_delete_toggle: "callable | None" = None
        self.building_inventory: BuildingInventory | None = None
        self.tech_tree = None
        self.tier_tracker = None
        self.god_mode_getter: "callable | None" = None
        self._active_cat: int = 0
        self._cat_tab_rects: list[pygame.Rect] = []
        self._card_rects: list[tuple[pygame.Rect, BuildingType]] = []
        self._delete_rect: pygame.Rect = pygame.Rect(0, 0, 0, 0)

    def set_on_select(self, callback) -> None:
        self._on_select = callback

    def set_on_delete_toggle(self, callback) -> None:
        self._on_delete_toggle = callback

    def _god(self) -> bool:
        return bool(self.god_mode_getter and self.god_mode_getter())

    # ── Drawing ──────────────────────────────────────────────────

    def draw_content(
        self, surface: pygame.Surface, rect: pygame.Rect, world: World,
    ) -> None:
        self._draw_category_tabs(surface, rect)

        _, cat_types = self._CATEGORIES[self._active_cat]
        # Hide locked buildings unless god mode is on.
        if not self._god():
            cat_types = [
                bt for bt in cat_types
                if is_building_available(
                    bt, self.tech_tree, self.tier_tracker,
                )
            ]
        n_cards = len(cat_types) + 1  # +1 for delete
        card_area_y = rect.y + _CAT_TAB_H + 6
        card_area_h = rect.h - _CAT_TAB_H - 12
        available_w = rect.w - _CARD_MARGIN_X * 2

        # Compute card width to fit all cards in the row; clamp to min/max.
        ideal_w = (available_w - (n_cards - 1) * _CARD_GAP) // n_cards
        card_w = max(_CARD_W_MIN, min(_CARD_W_MAX, ideal_w))
        total_w = card_w * n_cards + _CARD_GAP * (n_cards - 1)

        # If cards still don't fit, shrink further down to a hard minimum.
        if total_w > available_w and n_cards > 0:
            card_w = max(
                64, (available_w - _CARD_GAP * (n_cards - 1)) // n_cards,
            )

        card_h = min(_CARD_H, card_area_h)
        x = rect.x + _CARD_MARGIN_X
        y = card_area_y

        self._card_rects = []
        for btype in cat_types:
            card_rect = pygame.Rect(x, y, card_w, card_h)
            self._draw_card(surface, card_rect, btype)
            self._card_rects.append((card_rect, btype))
            x += card_w + _CARD_GAP

        # Delete card
        self._delete_rect = pygame.Rect(x, y, card_w, card_h)
        self._draw_delete_card(surface, self._delete_rect)

    def _draw_category_tabs(
        self, surface: pygame.Surface, rect: pygame.Rect,
    ) -> None:
        cat_font = Fonts.body()
        y = rect.y + 2
        x = rect.x + _CARD_MARGIN_X
        self._cat_tab_rects = []
        for ci, (cat_name, _) in enumerate(self._CATEGORIES):
            tw = cat_font.size(cat_name)[0] + 18
            tr = pygame.Rect(x, y, tw, _CAT_TAB_H)
            self._cat_tab_rects.append(tr)

            is_active = ci == self._active_cat
            bg = UI_TAB_ACTIVE if is_active else UI_TAB_INACTIVE
            tab_bg = pygame.Surface((tw, _CAT_TAB_H), pygame.SRCALPHA)
            tab_bg.fill(bg)
            surface.blit(tab_bg, tr.topleft)
            border = UI_ACCENT if is_active else UI_BORDER
            pygame.draw.rect(surface, border, tr, width=1, border_radius=3)

            label = render_text_clipped(cat_font, cat_name, UI_TEXT, tw - 10)
            surface.blit(label, (
                tr.centerx - label.get_width() // 2,
                tr.centery - label.get_height() // 2,
            ))
            x += tw + 4

    def _draw_card(
        self, surface: pygame.Surface, rect: pygame.Rect,
        btype: BuildingType,
    ) -> None:
        inv = self.building_inventory
        stock = inv[btype] if inv else 0
        has_stock = stock > 0
        is_sel = self.selected_building == btype
        is_hov = self.hovered == btype

        if is_sel:
            bg_col = UI_TAB_ACTIVE
        elif is_hov:
            bg_col = UI_TAB_HOVER
        else:
            bg_col = UI_TAB_INACTIVE

        card_bg = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
        card_bg.fill(bg_col)
        surface.blit(card_bg, rect.topleft)
        border_col = UI_ACCENT if is_sel else UI_BORDER
        pygame.draw.rect(surface, border_col, rect, width=2, border_radius=4)

        inner_w = rect.w - 12

        # Row 1: icon + name.  Harvesters show the sprite of the
        # resource they produce; everything else uses the unicode
        # glyph from ``_ICON``.
        icon_res = self._HARVEST_ICON_RESOURCE.get(btype)
        if icon_res is not None:
            icon = get_resource_icon(icon_res, 20)
        else:
            icon = Fonts.label().render(
                self._ICON.get(btype, "?"), True,
                self._COLOR.get(btype, UI_TEXT),
            )
        surface.blit(icon, (rect.x + 6, rect.y + 4))
        name_max = inner_w - icon.get_width() - 6
        name = render_text_clipped(
            Fonts.body(), self._LABEL.get(btype, btype.name.title()),
            UI_TEXT, name_max,
        )
        surface.blit(name, (
            rect.x + 6 + icon.get_width() + 4, rect.y + 6,
        ))

        # Row 2: stock count.  God mode shows "∞" since placement is
        # free and unbounded.
        if self._god():
            stock_col = UI_TEXT
            stock_text = "∞"
        else:
            stock_col = UI_TEXT if has_stock else UI_BAD
            stock_text = f"x{stock}"
        stock_surf = Fonts.small().render(stock_text, True, stock_col)
        surface.blit(stock_surf, (rect.x + 8, rect.y + 32))

        # Row 3: description (wrapped to width)
        desc = self._DESC.get(btype)
        if desc:
            desc_surf = render_text_clipped(
                Fonts.small(), desc, UI_MUTED, inner_w,
            )
            surface.blit(desc_surf, (
                rect.x + 8, rect.bottom - desc_surf.get_height() - 6,
            ))

    def _draw_delete_card(
        self, surface: pygame.Surface, rect: pygame.Rect,
    ) -> None:
        is_sel = self.delete_active
        is_hov = self.hovered == "delete"
        if is_sel:
            bg_col = (60, 20, 20, 220)
        elif is_hov:
            bg_col = UI_TAB_HOVER
        else:
            bg_col = UI_TAB_INACTIVE
        card_bg = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
        card_bg.fill(bg_col)
        surface.blit(card_bg, rect.topleft)
        border_col = UI_BAD if is_sel else UI_BORDER
        pygame.draw.rect(surface, border_col, rect, width=2, border_radius=4)

        icon = Fonts.label().render("\u2716", True, UI_BAD)
        surface.blit(icon, (rect.x + 6, rect.y + 4))
        inner_w = rect.w - 12
        name = render_text_clipped(
            Fonts.body(), "Delete", UI_TEXT,
            inner_w - icon.get_width() - 6,
        )
        surface.blit(name, (rect.x + 6 + icon.get_width() + 4, rect.y + 6))
        hint = render_text_clipped(
            Fonts.small(), "Returns to inventory", UI_MUTED, inner_w,
        )
        surface.blit(hint, (
            rect.x + 8, rect.bottom - hint.get_height() - 6,
        ))

    # ── Events ───────────────────────────────────────────────────

    def handle_event(
        self, event: pygame.event.Event, rect: pygame.Rect,
    ) -> bool:
        if event.type == pygame.MOUSEMOTION:
            self._update_hover(event.pos)
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if not rect.collidepoint(event.pos):
                return False
            # Category tabs
            for ci, tr in enumerate(self._cat_tab_rects):
                if tr.collidepoint(event.pos):
                    self._active_cat = ci
                    self.hovered = None
                    return True
            # Delete card
            if self._delete_rect.collidepoint(event.pos):
                self.delete_active = not self.delete_active
                if self.delete_active:
                    self.selected_building = None
                    if self._on_select:
                        self._on_select(None)
                if self._on_delete_toggle:
                    self._on_delete_toggle(self.delete_active)
                return True
            # Building cards
            for card_rect, btype in self._card_rects:
                if card_rect.collidepoint(event.pos):
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
            return True  # consume click in content area
        return False

    def _update_hover(self, pos: tuple[int, int]) -> None:
        self.hovered = None
        for card_rect, btype in self._card_rects:
            if card_rect.collidepoint(pos):
                self.hovered = btype
                return
        if self._delete_rect.collidepoint(pos):
            self.hovered = "delete"


# ── Info tab (shows colony stats) ────────────────────────────────

class InfoTabContent(TabContent):
    """Compact colony info: age, population, buildings."""

    def draw_content(
        self, surface: pygame.Surface, rect: pygame.Rect, world: World,
    ) -> None:
        mins, secs = divmod(int(world.time_elapsed), 60)
        n_buildings = sum(
            1 for b in world.buildings.buildings
            if b.type != BuildingType.PATH
        )
        items = [
            ("Colony age", f"{mins}:{secs:02d}"),
            ("Population", str(world.population.count)),
            ("Buildings", str(n_buildings)),
        ]
        # Lay out in columns
        col_w = rect.w // max(1, len(items))
        y = rect.y + rect.h // 2 - 24
        for i, (label, value) in enumerate(items):
            cx = rect.x + col_w * i + col_w // 2
            lbl_surf = Fonts.small().render(label, True, UI_MUTED)
            val_surf = Fonts.label().render(value, True, UI_TEXT)
            surface.blit(lbl_surf, (cx - lbl_surf.get_width() // 2, y))
            surface.blit(val_surf, (
                cx - val_surf.get_width() // 2,
                y + lbl_surf.get_height() + 4,
            ))


# ── BottomBar panel ──────────────────────────────────────────────

class BottomBar(Panel):
    """Tabbed panel anchored to the bottom of the screen."""

    def __init__(self) -> None:
        super().__init__()
        self._tabs: list[_Tab] = []
        self._active: int = -1
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
        font = Fonts.body()
        for tab in self._tabs:
            tab.label_surf = font.render(tab.label, True, UI_TEXT)

    @property
    def tab_height(self) -> int:
        return _TAB_HEIGHT

    @property
    def total_height(self) -> int:
        return _TAB_HEIGHT + (_CONTENT_HEIGHT if self._active >= 0 else 0)

    def layout(self, screen_w: int, screen_h: int) -> None:
        total_h = self.total_height
        self.rect = pygame.Rect(0, screen_h - total_h, screen_w, total_h)

        self._tab_rects = []
        x = 4
        for tab in self._tabs:
            label_w = tab.label_surf.get_width() if tab.label_surf else 60
            w = max(_TAB_MIN_WIDTH, label_w + _TAB_PAD_X * 2)
            tr = pygame.Rect(x, screen_h - total_h, w, _TAB_HEIGHT)
            self._tab_rects.append(tr)
            x += w + 2

        if self._active >= 0:
            self._content_rect = pygame.Rect(
                0, screen_h - total_h + _TAB_HEIGHT,
                screen_w, _CONTENT_HEIGHT,
            )
        else:
            self._content_rect = pygame.Rect(0, 0, 0, 0)

    def draw(self, surface: pygame.Surface, world: World) -> None:
        sw, _ = surface.get_size()

        # Content background
        if self._active >= 0:
            draw_panel_bg(surface, self._content_rect, accent_edge="top")

        # Tab strip
        strip_rect = pygame.Rect(0, self.rect.y, sw, _TAB_HEIGHT)
        strip_bg = pygame.Surface((sw, _TAB_HEIGHT), pygame.SRCALPHA)
        strip_bg.fill(UI_BG)
        surface.blit(strip_bg, strip_rect.topleft)

        for idx, (tab, tr) in enumerate(zip(self._tabs, self._tab_rects)):
            is_active = idx == self._active
            is_hover = idx == self._hover_tab

            col = (UI_TAB_ACTIVE if is_active
                   else UI_TAB_HOVER if is_hover
                   else UI_TAB_INACTIVE)
            tab_bg = pygame.Surface((tr.w, tr.h), pygame.SRCALPHA)
            tab_bg.fill(col)
            surface.blit(tab_bg, tr.topleft)
            border_col = UI_ACCENT if is_active else UI_BORDER
            pygame.draw.rect(surface, border_col, tr, width=2, border_radius=4)

            if tab.label_surf is not None:
                lx = tr.x + (tr.w - tab.label_surf.get_width()) // 2
                ly = tr.y + (tr.h - tab.label_surf.get_height()) // 2
                surface.blit(tab.label_surf, (lx, ly))

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
            if self._active >= 0 and self._content_rect.collidepoint(event.pos):
                self._tabs[self._active].content.handle_event(
                    event, self._content_rect,
                )
                return True

        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            for idx, tr in enumerate(self._tab_rects):
                if tr.collidepoint(event.pos):
                    if idx == self._active:
                        self._active = -1
                    else:
                        self._active = idx
                    sw, sh = pygame.display.get_surface().get_size()
                    self.layout(sw, sh)
                    return True
            if self._active >= 0 and self._content_rect.collidepoint(event.pos):
                return self._tabs[self._active].content.handle_event(
                    event, self._content_rect,
                )

        if hasattr(event, "pos") and self.rect.collidepoint(event.pos):
            return True
