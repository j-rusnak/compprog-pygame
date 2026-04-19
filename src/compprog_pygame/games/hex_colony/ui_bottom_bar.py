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
from compprog_pygame.games.hex_colony.render_buildings import (
    draw_assembler,
    draw_bridge,
    draw_chemical_plant,
    draw_conveyor,
    draw_forge,
    draw_habitat,
    draw_mining_machine,
    draw_path,
    draw_refinery,
    draw_research_center,
    draw_rocket_silo,
    draw_solar_array,
    draw_storage,
    draw_wall,
    draw_well,
    draw_workshop,
)
from compprog_pygame.games.hex_colony.tech_tree import is_building_available
from compprog_pygame.games.hex_colony.strings import (
    building_short_label,
    building_description,
    BUILDING_CATEGORY_NAMES,
    STATS_COLONY_AGE,
    STATS_POPULATION,
    STATS_BUILDINGS,
    TAB_BUILDINGS,
)
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


# ── Shared icons ─────────────────────────────────────────────────

# Cache of red-X "close/delete" icons keyed by pixel size.  The sprite
# is used everywhere a menu shows a close or delete affordance so the
# UI reads consistently.
_RED_X_CACHE: dict[int, pygame.Surface] = {}


def _get_red_x_icon(size: int) -> pygame.Surface:
    """Return a procedurally-drawn red-X icon of the given pixel size."""
    cached = _RED_X_CACHE.get(size)
    if cached is not None:
        return cached
    surf = pygame.Surface((size, size), pygame.SRCALPHA)
    pad = max(2, size // 6)
    # Dark red shadow behind for readability on pale backgrounds.
    shadow = (90, 10, 10)
    body = (235, 60, 60)
    hilite = (255, 150, 150)
    thick = max(2, size // 6)
    # Shadow (one pixel down-right)
    pygame.draw.line(surf, shadow, (pad + 1, pad + 1),
                     (size - pad + 1, size - pad + 1), thick + 1)
    pygame.draw.line(surf, shadow, (size - pad + 1, pad + 1),
                     (pad + 1, size - pad + 1), thick + 1)
    # Main strokes
    pygame.draw.line(surf, body, (pad, pad),
                     (size - pad, size - pad), thick)
    pygame.draw.line(surf, body, (size - pad, pad),
                     (pad, size - pad), thick)
    # Highlight stroke (thin, offset up-left) to give dimensionality
    hlw = max(1, thick // 3)
    pygame.draw.line(surf, hilite, (pad, pad - 1),
                     (size - pad, size - pad - 1), hlw)
    pygame.draw.line(surf, hilite, (size - pad, pad - 1),
                     (pad, size - pad - 1), hlw)
    _RED_X_CACHE[size] = surf
    return surf


def get_red_x_icon(size: int) -> pygame.Surface:
    """Public accessor for the shared red-X sprite."""
    return _get_red_x_icon(size)


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
        (BUILDING_CATEGORY_NAMES[0], [BuildingType.RESEARCH_CENTER, BuildingType.ROCKET_SILO]),
        (BUILDING_CATEGORY_NAMES[1], [BuildingType.HABITAT]),
        (BUILDING_CATEGORY_NAMES[2], [BuildingType.WOODCUTTER, BuildingType.QUARRY,
                      BuildingType.GATHERER, BuildingType.FARM, BuildingType.WELL,
                      BuildingType.MINING_MACHINE, BuildingType.SOLAR_ARRAY]),
        (BUILDING_CATEGORY_NAMES[3], [BuildingType.WORKSHOP, BuildingType.FORGE,
                        BuildingType.ASSEMBLER, BuildingType.REFINERY,
                        BuildingType.CHEMICAL_PLANT, BuildingType.STORAGE]),
        (BUILDING_CATEGORY_NAMES[4], [BuildingType.PATH, BuildingType.BRIDGE,
                        BuildingType.CONVEYOR, BuildingType.WALL]),
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
        BuildingType.MINING_MACHINE: "\u26cf",
        BuildingType.FARM: "\u2668",
        BuildingType.WELL: "\u25ce",
        BuildingType.WALL: "\u2588",
        BuildingType.WORKSHOP: "\u2699",
        BuildingType.FORGE: "\u2692",
        BuildingType.ASSEMBLER: "\u25a6",
        BuildingType.RESEARCH_CENTER: "\u2261",
        BuildingType.CHEMICAL_PLANT: "\u269b",
        BuildingType.CONVEYOR: "\u21d2",
        BuildingType.SOLAR_ARRAY: "\u2600",
        BuildingType.ROCKET_SILO: "\u29bf",
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
        BuildingType.MINING_MACHINE: (95, 95, 110),
        BuildingType.FARM: (100, 160, 50),
        BuildingType.WELL: (60, 100, 180),
        BuildingType.WALL: (160, 155, 145),
        BuildingType.WORKSHOP: (180, 140, 60),
        BuildingType.FORGE: (110, 100, 92),
        BuildingType.ASSEMBLER: (120, 140, 165),
        BuildingType.RESEARCH_CENTER: (70, 130, 200),
        BuildingType.CHEMICAL_PLANT: (100, 160, 130),
        BuildingType.CONVEYOR: (200, 180, 90),
        BuildingType.SOLAR_ARRAY: (60, 100, 200),
        BuildingType.ROCKET_SILO: (235, 235, 240),
    }

    _DESC: dict[BuildingType, str] = {
        bt: building_description(bt.name)
        for bt in BuildingType
        if building_description(bt.name)
    }

    _LABEL: dict[BuildingType, str] = {
        bt: building_short_label(bt.name)
        for bt in BuildingType
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

    # Procedural draw function per building type, used to render a
    # small preview icon for the building-menu card instead of a
    # colored square.  Building types not in this map fall back to
    # the unicode glyph in ``_ICON``.
    _BUILDING_DRAWERS: dict[BuildingType, "callable"] = {
        BuildingType.HABITAT: draw_habitat,
        BuildingType.STORAGE: draw_storage,
        BuildingType.WORKSHOP: draw_workshop,
        BuildingType.FORGE: draw_forge,
        BuildingType.ASSEMBLER: draw_assembler,
        BuildingType.RESEARCH_CENTER: draw_research_center,
        BuildingType.WALL: draw_wall,
        BuildingType.MINING_MACHINE: draw_mining_machine,
        BuildingType.PATH: draw_path,
        BuildingType.CHEMICAL_PLANT: draw_chemical_plant,
        BuildingType.CONVEYOR: draw_conveyor,
        BuildingType.SOLAR_ARRAY: draw_solar_array,
        BuildingType.ROCKET_SILO: draw_rocket_silo,
    }

    # Cache of building-sprite preview surfaces, keyed by (btype, size).
    # Built lazily the first time a card is drawn; preview surfaces are
    # zoom-independent so the cache never needs invalidation.
    _preview_cache: dict[tuple[BuildingType, int], pygame.Surface] = {}

    @classmethod
    def _get_building_preview(
        cls, btype: BuildingType, size: int,
    ) -> pygame.Surface | None:
        drawer = cls._BUILDING_DRAWERS.get(btype)
        if drawer is None:
            return None
        key = (btype, size)
        cached = cls._preview_cache.get(key)
        if cached is not None:
            return cached
        surf = pygame.Surface((size, size), pygame.SRCALPHA)
        # Leave some padding so tall buildings (chimneys/roofs) fit.
        r = max(4, int(size * 0.45))
        cx = size // 2
        cy = int(size * 0.62)  # bias downward — most drawers stack upward
        if btype == BuildingType.WALL:
            drawer(surf, cx, cy, r, 1.0, [], 0, 0)
        elif btype == BuildingType.PATH:
            # Path preview: isolated hub centred in the icon.
            drawer(surf, cx, size // 2, r, 1.0, [], 0, 0)
        else:
            drawer(surf, cx, cy, r, 1.0)
        cls._preview_cache[key] = surf
        return surf

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
        # resource they produce; other buildings show a small
        # procedural preview of the building itself.  Remaining
        # types fall back to the unicode glyph from ``_ICON``.
        icon_res = self._HARVEST_ICON_RESOURCE.get(btype)
        if icon_res is not None:
            icon = get_resource_icon(icon_res, 20)
        else:
            preview = self._get_building_preview(btype, 28)
            if preview is not None:
                icon = preview
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

        icon = _get_red_x_icon(24)
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
        mins, secs = divmod(int(world.real_time_elapsed), 60)
        n_buildings = sum(
            1 for b in world.buildings.buildings
            if b.type != BuildingType.PATH
            and getattr(b, "faction", "SURVIVOR") == "SURVIVOR"
        )
        items = [
            (STATS_COLONY_AGE, f"{mins}:{secs:02d}"),
            (STATS_POPULATION, str(world.population.count)),
            (STATS_BUILDINGS, str(n_buildings)),
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
        self._close_rect = pygame.Rect(0, 0, 0, 0)
        self._create_default_tabs()

    @property
    def buildings_tab(self) -> BuildingsTabContent | None:
        for tab in self._tabs:
            if isinstance(tab.content, BuildingsTabContent):
                return tab.content
        return None

    def _create_default_tabs(self) -> None:
        self.add_tab(TAB_BUILDINGS, BuildingsTabContent())

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

        # Close button (only when a tab is open).  Drawn on top of the
        # content so it stays clickable; sits in the upper-right corner
        # of the content area.
        if self._active >= 0:
            sz = 22
            self._close_rect = pygame.Rect(
                self._content_rect.right - sz - 6,
                self._content_rect.top + 6,
                sz, sz,
            )
            mouse = pygame.mouse.get_pos()
            hover = self._close_rect.collidepoint(mouse)
            bg_col = (60, 20, 20, 230) if hover else (34, 34, 40, 200)
            bg = pygame.Surface((sz, sz), pygame.SRCALPHA)
            bg.fill(bg_col)
            surface.blit(bg, self._close_rect.topleft)
            pygame.draw.rect(
                surface, (200, 80, 80), self._close_rect,
                width=2, border_radius=4,
            )
            icon = _get_red_x_icon(sz - 8)
            surface.blit(icon, (
                self._close_rect.x + 4, self._close_rect.y + 4,
            ))
        else:
            self._close_rect = pygame.Rect(0, 0, 0, 0)

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
            if self._active >= 0 and self._close_rect.collidepoint(event.pos):
                self._active = -1
                sw, sh = pygame.display.get_surface().get_size()
                self.layout(sw, sh)
                return True
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
