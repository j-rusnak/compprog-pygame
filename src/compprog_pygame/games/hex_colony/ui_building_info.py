"""Building info popup — shown when a hex with a building is selected.

The panel anchors to the right side of the screen.  Height is clamped
to the available space between the resource bar and the bottom bar;
if content overflows, the recipe list / tier info scrolls via the
mouse wheel.

Set ``BuildingInfoPanel.building`` to show it, or ``None`` to hide.
"""

from __future__ import annotations

import typing
from dataclasses import dataclass
from typing import TYPE_CHECKING

import pygame

from compprog_pygame.games.hex_colony.buildings import (
    BUILDING_COSTS,
    BUILDING_HOUSING,
    BuildingType,
)
from compprog_pygame.games.hex_colony import params
from compprog_pygame.games.hex_colony.strings import (
    building_label,
    resource_name,
    INFO_INPUTS_HEADER,
    INFO_OUTPUTS_HEADER,
    INFO_OTHER_HEADER,
    INFO_MATERIALS_HEADER,
    INFO_SELECT_RECIPE,
    INFO_SELECT_RECIPE_DD,
    INFO_OPEN_TECH_TREE,
    INFO_MAX_TIER,
    INFO_STONE_DEFAULT,
)
from compprog_pygame.games.hex_colony.resources import (
    MATERIAL_RECIPES,
    MaterialRecipe,
    Resource,
    recipes_for_station,
)
from compprog_pygame.games.hex_colony.resource_icons import get_resource_icon
from compprog_pygame.games.hex_colony.tech_tree import (
    is_building_available,
    is_resource_available,
)
from compprog_pygame.games.hex_colony.ui import (
    Fonts,
    Panel,
    RESOURCE_COLORS,
    RESOURCE_ICONS,
    UI_ACCENT,
    UI_BAD,
    UI_BG,
    UI_BORDER,
    UI_MUTED,
    UI_OK,
    UI_TEXT,
    draw_panel_bg,
    render_text_clipped,
    set_tooltip,
    wrap_text,
)

if TYPE_CHECKING:
    from compprog_pygame.games.hex_colony.buildings import Building
    from compprog_pygame.games.hex_colony.world import World


_PANEL_W = 260
_PADDING = 12
_LINE_H = 24
_SMALL_LINE_H = 20
_SPACER_H = 8
_TOP_MARGIN = 48          # stay below 38px resource bar
_BOTTOM_MARGIN = 44       # stay above 32px bottom tab strip
_SCROLLBAR_W = 6





# ── Content item types (lightweight DSL) ─────────────────────────

@dataclass
class _Line:
    """A single line of text."""
    text: str
    color: tuple[int, int, int]
    font: pygame.font.Font
    height: int


@dataclass
class _IconLine:
    """A line of text preceded by a 16px resource icon."""
    resource: Resource
    text: str
    color: tuple[int, int, int]
    height: int = _SMALL_LINE_H


@dataclass
class _Spacer:
    height: int = _SPACER_H


@dataclass
class _RecipeBtn:
    craft_type: BuildingType
    selected: bool
    height: int = _LINE_H + 4


@dataclass
class _MaterialRecipeBtn:
    recipe: MaterialRecipe
    selected: bool
    height: int = _LINE_H + 4


@dataclass
class _TechTreeBtn:
    height: int = _LINE_H + 10


@dataclass
class _PossessBtn:
    """Button shown on rival TRIBAL_CAMP popups so the player can
    inspect the controlling clanker (read-only)."""
    height: int = _LINE_H + 10


@dataclass
class _StorageResBtn:
    resource: Resource
    selected: bool
    height: int = _SMALL_LINE_H + 2


@dataclass
class _GathererOutputBtn:
    resource: Resource | None  # None means "both"
    selected: bool
    height: int = _SMALL_LINE_H + 2


@dataclass
class _QuarryOutputBtn:
    resource: Resource | None  # None means stone (default)
    selected: bool
    height: int = _SMALL_LINE_H + 2


@dataclass
class _RecipeDropdownHeader:
    """Clickable header that toggles the recipe dropdown open/closed."""
    label: str
    is_open: bool
    height: int = _LINE_H + 4


_Item = (
    _Line | _IconLine | _Spacer | _RecipeBtn | _MaterialRecipeBtn
    | _TechTreeBtn | _PossessBtn | _StorageResBtn | _GathererOutputBtn
    | _QuarryOutputBtn | _RecipeDropdownHeader
)


class BuildingInfoPanel(Panel):
    """Pop-up panel showing details about the selected building."""

    def __init__(self) -> None:
        super().__init__()
        self.building: Building | None = None
        self._screen_w = 0
        self._screen_h = 0
        self._recipe_rects: list[tuple[pygame.Rect, BuildingType]] = []
        self._mat_recipe_rects: list[tuple[pygame.Rect, MaterialRecipe]] = []
        self._storage_res_rects: list[tuple[pygame.Rect, Resource]] = []
        self._gatherer_output_rects: list[tuple[pygame.Rect, Resource | None]] = []
        self._quarry_output_rects: list[tuple[pygame.Rect, Resource | None]] = []
        self._tech_tree_btn: pygame.Rect | None = None
        self._possess_btn: pygame.Rect | None = None
        self._recipe_dropdown_open: bool = False
        self._recipe_dropdown_btn: pygame.Rect | None = None
        # Floating-overlay rect + internal scroll offset, used so the
        # recipe dropdown can fit on screen even when there are many
        # recipes (e.g. the assembler with all techs researched).
        self._recipe_dropdown_rect: pygame.Rect | None = None
        self._dropdown_scroll: int = 0
        self.on_open_tech_tree: typing.Callable[[], None] | None = None
        self.on_possess: typing.Callable[["Building"], None] | None = None
        # When set, buildings owned by this faction are shown in the
        # full inspector view (read-only) just like the player's own.
        self.possessed_faction_id: str | None = None
        self.tier_tracker: typing.Any = None
        self.tech_tree: typing.Any = None
        self.god_mode_getter: typing.Callable[[], bool] | None = None
        self._scroll: int = 0
        self._content_h: int = 0
        self._view_h: int = 0
        self._content_rect: pygame.Rect = pygame.Rect(0, 0, 0, 0)

    def layout(self, screen_w: int, screen_h: int) -> None:
        self._screen_w = screen_w
        self._screen_h = screen_h
        # Placeholder rect; actual rect set in draw() based on content.
        self.rect = pygame.Rect(screen_w - _PANEL_W - 10, _TOP_MARGIN, _PANEL_W, 100)

    # ── Drawing ──────────────────────────────────────────────────

    def draw(self, surface: pygame.Surface, world: World) -> None:
        if self.building is None:
            self._recipe_rects = []
            self._mat_recipe_rects = []
            self._gatherer_output_rects = []
            self._quarry_output_rects = []
            self._tech_tree_btn = None
            self._possess_btn = None
            self._recipe_dropdown_open = False
            self._recipe_dropdown_btn = None
            self._recipe_dropdown_rect = None
            self._dropdown_scroll = 0
            return

        items = self._build_items(world)
        content_h = sum(item.height for item in items) + _PADDING * 2
        max_panel_h = self._screen_h - _TOP_MARGIN - _BOTTOM_MARGIN
        panel_h = min(content_h, max(120, max_panel_h))

        x = self._screen_w - _PANEL_W - 10
        y = max(_TOP_MARGIN, (self._screen_h - panel_h) // 2)
        if y + panel_h > self._screen_h - _BOTTOM_MARGIN:
            y = self._screen_h - _BOTTOM_MARGIN - panel_h
        y = max(_TOP_MARGIN, y)

        self.rect = pygame.Rect(x, y, _PANEL_W, panel_h)
        self._content_rect = pygame.Rect(
            x + 1, y + 1, _PANEL_W - 2, panel_h - 2,
        )
        self._content_h = content_h
        self._view_h = panel_h

        # Clamp scroll
        max_scroll = max(0, content_h - panel_h)
        self._scroll = max(0, min(self._scroll, max_scroll))

        draw_panel_bg(surface, self.rect, accent_edge="top")

        # Clip content to panel interior.
        prev_clip = surface.get_clip()
        surface.set_clip(self._content_rect)

        cy = y + _PADDING - self._scroll
        self._recipe_rects = []
        self._mat_recipe_rects = []
        self._storage_res_rects = []
        self._gatherer_output_rects = []
        self._quarry_output_rects = []
        self._tech_tree_btn = None
        self._possess_btn = None

        for item in items:
            if isinstance(item, _Spacer):
                cy += item.height
                continue
            # Cull lines that fall entirely outside the visible area.
            if cy + item.height < y or cy > y + panel_h:
                cy += item.height
                continue
            if isinstance(item, _Line):
                max_w = _PANEL_W - _PADDING * 2
                # Reserve space for scrollbar if shown.
                if max_scroll > 0:
                    max_w -= _SCROLLBAR_W + 4
                surf = render_text_clipped(
                    item.font, item.text, item.color, max_w,
                )
                surface.blit(surf, (x + _PADDING, cy))
            elif isinstance(item, _IconLine):
                icon_size = 16
                icon_surf = get_resource_icon(item.resource, icon_size)
                icon_x = x + _PADDING + 4
                icon_y = cy + (item.height - icon_size) // 2
                surface.blit(icon_surf, (icon_x, icon_y))
                # Tooltip when hovering over the icon itself.
                icon_rect = pygame.Rect(icon_x, icon_y, icon_size, icon_size)
                if icon_rect.collidepoint(pygame.mouse.get_pos()):
                    set_tooltip(
                        resource_name(item.resource.name),
                    )
                max_w = _PANEL_W - _PADDING * 2 - icon_size - 8
                if max_scroll > 0:
                    max_w -= _SCROLLBAR_W + 4
                surf = render_text_clipped(
                    Fonts.small(), item.text, item.color, max_w,
                )
                surface.blit(surf, (icon_x + icon_size + 4, cy + 2))
            elif isinstance(item, _RecipeBtn):
                self._draw_recipe_btn(surface, x, cy, item, world)
            elif isinstance(item, _MaterialRecipeBtn):
                self._draw_material_recipe_btn(surface, x, cy, item, world)
            elif isinstance(item, _StorageResBtn):
                self._draw_storage_res_btn(surface, x, cy, item)
            elif isinstance(item, _GathererOutputBtn):
                self._draw_gatherer_output_btn(surface, x, cy, item)
            elif isinstance(item, _QuarryOutputBtn):
                self._draw_quarry_output_btn(surface, x, cy, item)
            elif isinstance(item, _RecipeDropdownHeader):
                self._draw_recipe_dropdown_header(surface, x, cy, item)
            elif isinstance(item, _TechTreeBtn):
                self._draw_tech_btn(surface, x, cy)
            elif isinstance(item, _PossessBtn):
                self._draw_possess_btn(surface, x, cy)
            cy += item.height

        surface.set_clip(prev_clip)

        # Scrollbar
        if max_scroll > 0:
            self._draw_scrollbar(surface, max_scroll)

        # Floating recipe-options overlay (drawn last so it sits on top
        # of the rest of the panel and does not push other content).
        if (self._recipe_dropdown_open
                and self._recipe_dropdown_btn is not None):
            self._draw_recipe_dropdown_overlay(surface, world)

    def _draw_recipe_btn(
        self, surface: pygame.Surface, x: int, cy: int, item: _RecipeBtn,
        world: World,
    ) -> None:
        btn_rect = pygame.Rect(
            x + _PADDING, cy, _PANEL_W - _PADDING * 2, _LINE_H,
        )
        bg = UI_ACCENT if item.selected else UI_BG
        pygame.draw.rect(surface, bg, btn_rect, border_radius=3)
        pygame.draw.rect(surface, UI_BORDER, btn_rect, width=1, border_radius=3)
        label = building_label(item.craft_type.name)
        label_col = UI_TEXT
        surf = render_text_clipped(
            Fonts.small(), label, label_col, btn_rect.w - 12,
        )
        surface.blit(surf, (btn_rect.x + 6, btn_rect.y + 3))
        self._recipe_rects.append((btn_rect, item.craft_type))

    def _draw_material_recipe_btn(
        self, surface: pygame.Surface, x: int, cy: int,
        item: _MaterialRecipeBtn, world: World,
    ) -> None:
        btn_rect = pygame.Rect(
            x + _PADDING, cy, _PANEL_W - _PADDING * 2, _LINE_H,
        )
        bg = UI_ACCENT if item.selected else UI_BG
        pygame.draw.rect(surface, bg, btn_rect, border_radius=3)
        pygame.draw.rect(surface, UI_BORDER, btn_rect, width=1, border_radius=3)

        # Output icon + name on the left.
        icon_size = 16
        out_icon = get_resource_icon(item.recipe.output, icon_size)
        icon_x = btn_rect.x + 4
        icon_y = btn_rect.centery - icon_size // 2
        surface.blit(out_icon, (icon_x, icon_y))
        label = (
            f"{resource_name(item.recipe.output.name)}"
            f" \u00d7{item.recipe.output_amount}"
        )
        surf = render_text_clipped(
            Fonts.small(), label, UI_TEXT, btn_rect.w - icon_size - 12,
        )
        surface.blit(surf, (icon_x + icon_size + 4, btn_rect.y + 3))
        self._mat_recipe_rects.append((btn_rect, item.recipe))

    def _draw_storage_res_btn(
        self, surface: pygame.Surface, x: int, cy: int,
        item: _StorageResBtn,
    ) -> None:
        btn_rect = pygame.Rect(
            x + _PADDING, cy, _PANEL_W - _PADDING * 2, _SMALL_LINE_H + 2,
        )
        bg = UI_ACCENT if item.selected else UI_BG
        pygame.draw.rect(surface, bg, btn_rect, border_radius=3)
        pygame.draw.rect(surface, UI_BORDER, btn_rect, width=1, border_radius=3)
        icon_size = 14
        icon_surf = get_resource_icon(item.resource, icon_size)
        icon_x = btn_rect.x + 4
        icon_y = btn_rect.centery - icon_size // 2
        surface.blit(icon_surf, (icon_x, icon_y))
        label = resource_name(item.resource.name)
        surf = render_text_clipped(
            Fonts.small(), label, UI_TEXT, btn_rect.w - icon_size - 12,
        )
        surface.blit(surf, (icon_x + icon_size + 6, btn_rect.y + 2))
        self._storage_res_rects.append((btn_rect, item.resource))

    def _draw_gatherer_output_btn(
        self, surface: pygame.Surface, x: int, cy: int,
        item: _GathererOutputBtn,
    ) -> None:
        btn_rect = pygame.Rect(
            x + _PADDING, cy, _PANEL_W - _PADDING * 2, _SMALL_LINE_H + 2,
        )
        bg = UI_ACCENT if item.selected else UI_BG
        pygame.draw.rect(surface, bg, btn_rect, border_radius=3)
        pygame.draw.rect(surface, UI_BORDER, btn_rect, width=1, border_radius=3)
        if item.resource is not None:
            icon_size = 14
            icon_surf = get_resource_icon(item.resource, icon_size)
            icon_x = btn_rect.x + 4
            icon_y = btn_rect.centery - icon_size // 2
            surface.blit(icon_surf, (icon_x, icon_y))
            label = resource_name(item.resource.name)
            surf = render_text_clipped(
                Fonts.small(), label, UI_TEXT, btn_rect.w - icon_size - 12,
            )
            surface.blit(surf, (icon_x + icon_size + 6, btn_rect.y + 2))
        else:
            label = "Both (Food & Fiber)"
            surf = render_text_clipped(
                Fonts.small(), label, UI_TEXT, btn_rect.w - 12,
            )
            surface.blit(surf, (btn_rect.x + 6, btn_rect.y + 2))
        self._gatherer_output_rects.append((btn_rect, item.resource))

    def _draw_quarry_output_btn(
        self, surface: pygame.Surface, x: int, cy: int,
        item: _QuarryOutputBtn,
    ) -> None:
        btn_rect = pygame.Rect(
            x + _PADDING, cy, _PANEL_W - _PADDING * 2, _SMALL_LINE_H + 2,
        )
        bg = UI_ACCENT if item.selected else UI_BG
        pygame.draw.rect(surface, bg, btn_rect, border_radius=3)
        pygame.draw.rect(surface, UI_BORDER, btn_rect, width=1, border_radius=3)
        if item.resource is not None:
            icon_size = 14
            icon_surf = get_resource_icon(item.resource, icon_size)
            icon_x = btn_rect.x + 4
            icon_y = btn_rect.centery - icon_size // 2
            surface.blit(icon_surf, (icon_x, icon_y))
            label = resource_name(item.resource.name)
            surf = render_text_clipped(
                Fonts.small(), label, UI_TEXT, btn_rect.w - icon_size - 12,
            )
            surface.blit(surf, (icon_x + icon_size + 6, btn_rect.y + 2))
        else:
            icon_size = 14
            icon_surf = get_resource_icon(Resource.STONE, icon_size)
            icon_x = btn_rect.x + 4
            icon_y = btn_rect.centery - icon_size // 2
            surface.blit(icon_surf, (icon_x, icon_y))
            label = INFO_STONE_DEFAULT
            surf = render_text_clipped(
                Fonts.small(), label, UI_TEXT, btn_rect.w - icon_size - 12,
            )
            surface.blit(surf, (icon_x + icon_size + 6, btn_rect.y + 2))
        self._quarry_output_rects.append((btn_rect, item.resource))

    def _draw_recipe_dropdown_header(
        self, surface: pygame.Surface, x: int, cy: int,
        item: _RecipeDropdownHeader,
    ) -> None:
        btn_rect = pygame.Rect(
            x + _PADDING, cy, _PANEL_W - _PADDING * 2, _LINE_H,
        )
        mx, my = pygame.mouse.get_pos()
        hover = btn_rect.collidepoint(mx, my)
        bg = (55, 65, 85) if hover else (45, 55, 75)
        pygame.draw.rect(surface, bg, btn_rect, border_radius=3)
        pygame.draw.rect(surface, UI_ACCENT, btn_rect, width=1, border_radius=3)
        surf = render_text_clipped(
            Fonts.small(), item.label, UI_TEXT, btn_rect.w - 12,
        )
        surface.blit(surf, (btn_rect.x + 6, btn_rect.y + 3))
        self._recipe_dropdown_btn = btn_rect

    def _gather_recipe_options(
        self, world: World,
    ) -> tuple[
        list[tuple[BuildingType, bool]],
        list[tuple[MaterialRecipe, bool]],
    ]:
        """Return (building_recipes, material_recipes) lists of
        (recipe, selected) tuples for the current crafting building,
        already filtered by tech/tier (unless god-mode)."""
        b = self.building
        assert b is not None
        god = bool(self.god_mode_getter and self.god_mode_getter())

        building_recipes: list[tuple[BuildingType, bool]] = []
        for bname, sname in params.BUILDING_RECIPE_STATION.items():
            if sname != b.type.name:
                continue
            craft_type = BuildingType[bname]
            if not god and not is_building_available(
                craft_type, self.tech_tree, self.tier_tracker,
            ):
                continue
            building_recipes.append(
                (craft_type, b.recipe == craft_type),
            )

        station_recipes = recipes_for_station(b.type.name)
        if not god:
            station_recipes = [
                mr for mr in station_recipes
                if is_resource_available(
                    mr.output, self.tech_tree, self.tier_tracker,
                )
            ]
        material_recipes = [
            (mr, b.recipe == mr.output) for mr in station_recipes
        ]
        return building_recipes, material_recipes

    def _draw_recipe_dropdown_overlay(
        self, surface: pygame.Surface, world: World,
    ) -> None:
        """Draw the open recipe list as a floating overlay anchored to
        the dropdown header.  Materials are listed first (so they're
        always visible immediately), then buildings.  The overlay is
        clamped to fit on screen and scrolls with the mouse wheel
        when it would otherwise overflow."""
        assert self._recipe_dropdown_btn is not None
        b = self.building
        if b is None:
            return

        building_recipes, material_recipes = self._gather_recipe_options(world)
        if not building_recipes and not material_recipes:
            return

        # Reset the rects — they're populated only in the overlay now.
        self._recipe_rects = []
        self._mat_recipe_rects = []

        gap = 2
        row_h = _LINE_H + gap
        header_pad = _SMALL_LINE_H + gap
        n_rows = len(building_recipes) + len(material_recipes)
        # Two section headers ("Materials" + "Buildings") when both
        # kinds of recipes exist; one header when only one.
        n_headers = (
            (1 if material_recipes else 0)
            + (1 if building_recipes else 0)
        )
        content_h = n_rows * row_h + n_headers * header_pad + _PADDING

        x = self._recipe_dropdown_btn.x
        w = self._recipe_dropdown_btn.w
        # Cap the overlay to the visible screen between the resource
        # bar and the bottom bar so long recipe lists never run
        # off-screen.
        max_h = max(120, self._screen_h - _TOP_MARGIN - _BOTTOM_MARGIN)
        total_h = min(content_h, max_h)

        # Open below the header by default; flip above if there isn't
        # room.  When content overflows even the larger side, pin the
        # overlay flush against the side that has more room.
        space_below = self._screen_h - _BOTTOM_MARGIN - (
            self._recipe_dropdown_btn.bottom + 2
        )
        space_above = self._recipe_dropdown_btn.top - 2 - _TOP_MARGIN
        if total_h <= space_below:
            y = self._recipe_dropdown_btn.bottom + 2
        elif total_h <= space_above:
            y = self._recipe_dropdown_btn.top - total_h - 2
        elif space_below >= space_above:
            y = self._recipe_dropdown_btn.bottom + 2
        else:
            y = max(_TOP_MARGIN, self._recipe_dropdown_btn.top - total_h - 2)

        rect = pygame.Rect(x, y, w, total_h)
        bg = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
        bg.fill((20, 26, 34, 245))
        surface.blit(bg, rect.topleft)
        pygame.draw.rect(surface, UI_ACCENT, rect, width=2, border_radius=4)

        # Stash for event handling (scroll + outside-click detection).
        self._recipe_dropdown_rect = rect

        max_scroll = max(0, content_h - total_h)
        self._dropdown_scroll = max(
            0, min(self._dropdown_scroll, max_scroll),
        )

        prev_clip = surface.get_clip()
        surface.set_clip(rect)

        cy = y + _PADDING // 2 - self._dropdown_scroll

        # Materials first so intermediates are always visible without
        # scrolling past the (potentially long) building list.
        if material_recipes:
            hdr = render_text_clipped(
                Fonts.small(), INFO_MATERIALS_HEADER, UI_MUTED, w - 12,
            )
            surface.blit(hdr, (x + 6, cy))
            cy += header_pad
            for mrec, selected in material_recipes:
                self._draw_material_recipe_btn(
                    surface, x - _PADDING, cy,
                    _MaterialRecipeBtn(mrec, selected=selected), world,
                )
                cy += row_h

        if building_recipes:
            hdr = render_text_clipped(
                Fonts.small(), "Buildings:", UI_MUTED, w - 12,
            )
            surface.blit(hdr, (x + 6, cy))
            cy += header_pad
            for craft_type, selected in building_recipes:
                self._draw_recipe_btn(
                    surface, x - _PADDING, cy,
                    _RecipeBtn(craft_type, selected=selected), world,
                )
                cy += row_h

        surface.set_clip(prev_clip)

        # Scrollbar when content is taller than visible area.
        if max_scroll > 0:
            track = pygame.Rect(
                rect.right - _SCROLLBAR_W - 2, rect.top + 4,
                _SCROLLBAR_W, rect.h - 8,
            )
            pygame.draw.rect(surface, UI_BG, track, border_radius=3)
            visible_frac = total_h / content_h
            thumb_h = max(20, int(track.h * visible_frac))
            pos_frac = self._dropdown_scroll / max_scroll
            thumb_y = track.y + int((track.h - thumb_h) * pos_frac)
            thumb = pygame.Rect(track.x, thumb_y, track.w, thumb_h)
            pygame.draw.rect(surface, UI_BORDER, thumb, border_radius=3)

    def _draw_tech_btn(self, surface: pygame.Surface, x: int, cy: int) -> None:
        btn_rect = pygame.Rect(
            x + _PADDING, cy + 4, _PANEL_W - _PADDING * 2, _LINE_H + 4,
        )
        pygame.draw.rect(surface, UI_ACCENT, btn_rect, border_radius=4)
        pygame.draw.rect(surface, UI_BORDER, btn_rect, width=2, border_radius=4)
        surf = Fonts.body().render(INFO_OPEN_TECH_TREE, True, UI_TEXT)
        surface.blit(surf, (
            btn_rect.centerx - surf.get_width() // 2,
            btn_rect.centery - surf.get_height() // 2,
        ))
        self._tech_tree_btn = btn_rect

    def _draw_possess_btn(
        self, surface: pygame.Surface, x: int, cy: int,
    ) -> None:
        btn_rect = pygame.Rect(
            x + _PADDING, cy + 4, _PANEL_W - _PADDING * 2, _LINE_H + 4,
        )
        pygame.draw.rect(surface, UI_ACCENT, btn_rect, border_radius=4)
        pygame.draw.rect(surface, UI_BORDER, btn_rect, width=2, border_radius=4)
        surf = Fonts.body().render("Possess", True, UI_TEXT)
        surface.blit(surf, (
            btn_rect.centerx - surf.get_width() // 2,
            btn_rect.centery - surf.get_height() // 2,
        ))
        self._possess_btn = btn_rect

    def _draw_scrollbar(self, surface: pygame.Surface, max_scroll: int) -> None:
        track = pygame.Rect(
            self.rect.right - _SCROLLBAR_W - 2,
            self.rect.top + 4,
            _SCROLLBAR_W,
            self.rect.h - 8,
        )
        pygame.draw.rect(surface, UI_BG, track, border_radius=3)
        visible_frac = self._view_h / self._content_h
        thumb_h = max(20, int(track.h * visible_frac))
        pos_frac = self._scroll / max_scroll
        thumb_y = track.y + int((track.h - thumb_h) * pos_frac)
        thumb = pygame.Rect(track.x, thumb_y, track.w, thumb_h)
        pygame.draw.rect(surface, UI_BORDER, thumb, border_radius=3)

    # ── Content building ─────────────────────────────────────────

    def _build_items(self, world: World) -> list[_Item]:
        items: list[_Item] = []
        b = self.building
        assert b is not None

        def line(text: str, color: tuple[int, int, int] = UI_TEXT,
                 font: pygame.font.Font | None = None) -> None:
            if font is None:
                font = Fonts.body()
            h = _LINE_H if font.get_height() > 18 else _SMALL_LINE_H
            items.append(_Line(text, color, font, h))

        # Title
        label = building_label(b.type.name)
        items.append(_Line(label, UI_ACCENT, Fonts.title(), 34))
        items.append(_Spacer(4))

        # Rival faction (TRIBAL_CAMP) — minimal read-only popup with
        # a Possess button.  We deliberately skip the rest of the
        # player-facing controls (recipes, workers, storage) because
        # those would let the player meddle with AI buildings.  When
        # the player is *currently possessing* this faction, fall
        # through to the full info view so they can read the same
        # stats as their own buildings.
        b_faction = getattr(b, "faction", "SURVIVOR")
        is_possessed_view = (
            b_faction != "SURVIVOR"
            and self.possessed_faction_id == b_faction
        )
        if (b.type == BuildingType.TRIBAL_CAMP
                and b_faction != "SURVIVOR"
                and not is_possessed_view):
            line(f"Faction: {b.faction}", UI_MUTED, Fonts.small())
            line("A rival colony's home base.", UI_MUTED, Fonts.small())
            items.append(_Spacer())
            items.append(_PossessBtn())
            return items

        # Housing
        cap = BUILDING_HOUSING.get(b.type, 0)
        if cap > 0:
            if b.type == BuildingType.CAMP and b.residents > cap:
                line(f"Residents: ({cap}+{b.residents - cap})/{cap}",
                     UI_BAD, Fonts.body())
            else:
                line(f"Residents: {b.residents}/{cap}", UI_TEXT, Fonts.body())

        # Camp-specific: tier info
        if b.type == BuildingType.CAMP:
            items.append(_Spacer())
            pop = world.player_population_count
            total_housing = world.connected_housing()
            homeless = max(0, pop - total_housing)
            line(f"Population: {pop}/{total_housing}")
            if homeless > 0:
                line(f"Homeless: {homeless}", UI_BAD)

            if self.tier_tracker is not None:
                self._append_tier_info(items, world, line)

        # Workers
        if b.max_workers > 0:
            line(f"Workers: {b.workers}/{b.max_workers}")

        # Storage.  For crafting stations with an active material
        # recipe, split the display into "Inputs" and "Outputs" so
        # the per-ingredient capacity (2x recipe amount) is visible
        # alongside the produced item.
        if b.storage_capacity > 0:
            items.append(_Spacer())
            split = (
                b.type in (
                    BuildingType.WORKSHOP, BuildingType.FORGE,
                    BuildingType.REFINERY, BuildingType.ASSEMBLER,
                    BuildingType.CHEMICAL_PLANT, BuildingType.OIL_REFINERY,
                )
                and isinstance(b.recipe, Resource)
            )
            if split:
                mrec = MATERIAL_RECIPES.get(b.recipe)
            else:
                mrec = None

            if split and mrec is not None:
                input_set = set(mrec.inputs.keys())
                output_res = mrec.output
                input_held = sum(
                    b.storage.get(r, 0.0) for r in mrec.inputs
                )
                output_held = b.stored_total - input_held
                line(
                    f"Output: {int(output_held)}/{b.storage_capacity}"
                )
                # Inputs section — always show every required ingredient
                # so the player can see a 0/N slot before logistics
                # delivers any.
                line(INFO_INPUTS_HEADER, UI_MUTED, Fonts.small())
                for res, req_amt in mrec.inputs.items():
                    have = int(b.storage.get(res, 0.0))
                    cap = req_amt * 2
                    items.append(_IconLine(
                        res,
                        f"{resource_name(res.name)}: {have}/{cap}",
                        RESOURCE_COLORS[res],
                    ))
                # Outputs section — what this station produces.
                line(INFO_OUTPUTS_HEADER, UI_MUTED, Fonts.small())
                out_have = int(b.storage.get(output_res, 0.0))
                items.append(_IconLine(
                    output_res,
                    f"{resource_name(output_res.name)}: {out_have}",
                    RESOURCE_COLORS[output_res],
                ))
                # Any other stored resources (legacy buffer, etc.).
                others = [
                    (r, a) for r, a in b.storage.items()
                    if a > 0 and r not in input_set and r != output_res
                ]
                if others:
                    line(INFO_OTHER_HEADER, UI_MUTED, Fonts.small())
                    for res, amount in others:
                        items.append(_IconLine(
                            res,
                            f"{resource_name(res.name)}: {int(amount)}",
                            RESOURCE_COLORS[res],
                        ))
            else:
                line(f"Storage: {int(b.stored_total)}/{b.storage_capacity}")
                # For consumer buildings whose inputs are NOT served by
                # the recipe-split branch above (Mining Machine fuels;
                # Research Center research costs), enumerate every
                # required input with a have/cap line so the player
                # can see deliveries arrive in real time.
                input_rows: list[tuple[Resource, float, float]] = []
                if b.type == BuildingType.MINING_MACHINE:
                    cap_for_fuel = b.storage_capacity * 0.4
                    for fuel_name in params.MINING_MACHINE_FUELS:
                        fr = Resource[fuel_name]
                        input_rows.append(
                            (fr, b.storage.get(fr, 0.0), cap_for_fuel),
                        )
                elif (b.type == BuildingType.RESEARCH_CENTER
                      and self.tech_tree is not None
                      and getattr(self.tech_tree, "current_research", None)):
                    from compprog_pygame.games.hex_colony.tech_tree import (
                        TECH_NODES,
                    )
                    node = TECH_NODES.get(self.tech_tree.current_research)
                    consumed = getattr(self.tech_tree, "_consumed", {}) or {}
                    if node is not None:
                        for res, total_amt in node.cost.items():
                            already = consumed.get(res, 0.0)
                            remaining = max(0.0, total_amt - already)
                            input_rows.append(
                                (res, b.storage.get(res, 0.0), remaining),
                            )

                if input_rows:
                    line(INFO_INPUTS_HEADER, UI_MUTED, Fonts.small())
                    input_set = {r for r, _, _ in input_rows}
                    for res, have, cap in input_rows:
                        items.append(_IconLine(
                            res,
                            f"{resource_name(res.name)}: "
                            f"{int(have)}/{int(cap)}",
                            RESOURCE_COLORS[res],
                        ))
                    other_lines = [
                        (r, a) for r, a in b.storage.items()
                        if a > 0 and r not in input_set
                    ]
                    if other_lines:
                        line(INFO_OTHER_HEADER, UI_MUTED, Fonts.small())
                        for res, amount in other_lines:
                            items.append(_IconLine(
                                res,
                                f"{resource_name(res.name)}: "
                                f"{int(amount)}",
                                RESOURCE_COLORS[res],
                            ))
                else:
                    for res, amount in b.storage.items():
                        if amount > 0:
                            items.append(_IconLine(
                                res,
                                f"{resource_name(res.name)}: "
                                f"{int(amount)}",
                                RESOURCE_COLORS[res],
                            ))

        # STORAGE building: let the player pick which single resource
        # this storage is dedicated to.  Shown as a scrollable list of
        # buttons with resource icon + name.  Clicking selects /
        # deselects.  Only raw + processed resources are offered
        # (buildings themselves aren't storable).  Fluids are excluded
        # — those go in FLUID_TANK and travel through pipes only.
        if b.type == BuildingType.STORAGE:
            from compprog_pygame.games.hex_colony.resources import (
                RAW_RESOURCES, PROCESSED_RESOURCES, FLUID_RESOURCES,
            )
            items.append(_Spacer())
            current = b.stored_resource
            line(
                f"Stores: {resource_name(current.name) if current else '(none selected)'}",
                UI_ACCENT if current else UI_MUTED,
            )
            items.append(_Spacer(2))
            god = bool(self.god_mode_getter and self.god_mode_getter())
            for res in list(RAW_RESOURCES) + [
                r for r in Resource if r in PROCESSED_RESOURCES
            ]:
                if res in FLUID_RESOURCES:
                    continue
                if not god and not is_resource_available(
                    res, self.tech_tree, self.tier_tracker,
                ):
                    continue
                items.append(_StorageResBtn(
                    resource=res, selected=(current == res),
                ))
                items.append(_Spacer(2))

        # FLUID_TANK building: like STORAGE, but only fluids are
        # selectable.  Tanks participate in the pipe network for the
        # selected fluid only.
        if b.type == BuildingType.FLUID_TANK:
            from compprog_pygame.games.hex_colony.resources import (
                FLUID_RESOURCES,
            )
            items.append(_Spacer())
            current = b.stored_resource
            line(
                f"Stores: {resource_name(current.name) if current else '(none selected)'}",
                UI_ACCENT if current else UI_MUTED,
            )
            items.append(_Spacer(2))
            god = bool(self.god_mode_getter and self.god_mode_getter())
            for res in [r for r in Resource if r in FLUID_RESOURCES]:
                if not god and not is_resource_available(
                    res, self.tech_tree, self.tier_tracker,
                ):
                    continue
                items.append(_StorageResBtn(
                    resource=res, selected=(current == res),
                ))
                items.append(_Spacer(2))

        # GATHERER building: let the player pick food or fiber.
        if b.type == BuildingType.GATHERER:
            items.append(_Spacer())
            current = b.gatherer_output
            label = resource_name(current.name) if current else resource_name('FOOD')
            line(f"Gathers: {label}", UI_ACCENT)
            items.append(_Spacer(2))
            for res in [Resource.FOOD, Resource.FIBER]:
                items.append(_GathererOutputBtn(
                    resource=res, selected=(current == res),
                ))
                items.append(_Spacer(2))

        # QUARRY building: let the player pick stone, iron, or copper.
        if b.type == BuildingType.QUARRY:
            items.append(_Spacer())
            current = b.quarry_output
            if current is None:
                label = resource_name('STONE')
            else:
                label = resource_name(current.name)
            line(f"Mining: {label}", UI_ACCENT)
            items.append(_Spacer(2))
            items.append(_QuarryOutputBtn(
                resource=None, selected=(current is None),
            ))
            items.append(_Spacer(2))
            for res in [Resource.IRON, Resource.COPPER]:
                items.append(_QuarryOutputBtn(
                    resource=res, selected=(current == res),
                ))
                items.append(_Spacer(2))

        # Crafting stations — Workshop / Forge / Refinery / Assembler /
        # Chemical Plant / Oil Refinery.
        if b.type in (
            BuildingType.WORKSHOP,
            BuildingType.FORGE,
            BuildingType.REFINERY,
            BuildingType.ASSEMBLER,
            BuildingType.CHEMICAL_PLANT,
            BuildingType.OIL_REFINERY,
        ):
            items.append(_Spacer())

            # Active recipe + progress + cost breakdown.
            if b.recipe is not None:
                if isinstance(b.recipe, BuildingType):
                    recipe_label = building_label(b.recipe.name)
                    line(f"Crafting: {recipe_label}", UI_ACCENT)
                    pct = int(
                        b.craft_progress / params.WORKSHOP_CRAFT_TIME * 100
                    )
                    line(f"Progress: {pct}%")
                    cost = BUILDING_COSTS[b.recipe]
                    for res, amount in cost.costs.items():
                        has = world.inventory[res] >= amount
                        col = RESOURCE_COLORS[res] if has else UI_BAD
                        items.append(_IconLine(res, f"{amount}", col))
                else:
                    # Material recipe — b.recipe is a Resource.
                    mrec = MATERIAL_RECIPES.get(b.recipe)
                    if mrec is not None:
                        name = resource_name(b.recipe.name)
                        line(f"Crafting: {name} \u00d7{mrec.output_amount}",
                             UI_ACCENT)
                        pct = int(b.craft_progress / mrec.time * 100)
                        line(f"Progress: {pct}%")
                        for res, amount in mrec.inputs.items():
                            has = world.inventory[res] >= amount
                            col = RESOURCE_COLORS[res] if has else UI_BAD
                            items.append(_IconLine(res, f"{amount}", col))
            else:
                line(INFO_SELECT_RECIPE, UI_MUTED)

            items.append(_Spacer(4))

            # Dropdown header for recipe selection.
            if b.recipe is not None:
                if isinstance(b.recipe, BuildingType):
                    dd_label = building_label(b.recipe.name)
                else:
                    dd_label = resource_name(b.recipe.name)
            else:
                dd_label = INFO_SELECT_RECIPE_DD
            arrow = "\u25bc" if self._recipe_dropdown_open else "\u25b6"
            items.append(_RecipeDropdownHeader(
                label=f"{arrow} {dd_label}",
                is_open=self._recipe_dropdown_open,
            ))
            items.append(_Spacer(2))

            # NOTE: Recipe option list is drawn as a floating overlay
            # in ``_draw_recipe_dropdown_overlay`` so it does not push
            # the rest of the panel content around when opened.

        # Research Center button
        if b.type == BuildingType.RESEARCH_CENTER:
            items.append(_Spacer())
            items.append(_TechTreeBtn())

        return items

    def _append_tier_info(
        self, items: list[_Item], world: World, line,
    ) -> None:
        from compprog_pygame.games.hex_colony.tech_tree import TIERS
        items.append(_Spacer())
        cur = self.tier_tracker.current_tier
        info = TIERS[cur]
        line(f"Tier {cur}: {info.name}", (255, 215, 0))
        # Wrap description
        inner_w = _PANEL_W - _PADDING * 2
        for wl in wrap_text(Fonts.small(), info.description, inner_w):
            line(wl, UI_MUTED, Fonts.small())
        if info.unlocks_buildings:
            names = ", ".join(
                building_label(bt.name)
                for bt in info.unlocks_buildings
            )
            for wl in wrap_text(Fonts.small(), f"Unlocked: {names}", inner_w):
                line(wl, UI_TEXT, Fonts.small())

        if cur + 1 < len(TIERS):
            items.append(_Spacer())
            nxt = TIERS[cur + 1]
            line(f"Next \u2192 Tier {cur + 1}: {nxt.name}", UI_ACCENT)
            progress = self.tier_tracker.check_requirements(world)
            for name, (current, required) in progress.items():
                done = current >= required
                col = UI_OK if done else UI_TEXT
                marker = "\u2713" if done else "\u2022"
                line(f"  {marker} {name}: {int(current)}/{int(required)}",
                     col, Fonts.small())
            if nxt.unlocks_buildings:
                names = ", ".join(
                    building_label(bt.name)
                    for bt in nxt.unlocks_buildings
                )
                for wl in wrap_text(
                    Fonts.small(), f"  Unlocks: {names}", inner_w,
                ):
                    line(wl, UI_MUTED, Fonts.small())
        else:
            line(INFO_MAX_TIER, UI_MUTED, Fonts.small())

    # ── Events ───────────────────────────────────────────────────

    def handle_event(self, event: pygame.event.Event) -> bool:
        if self.building is None:
            return False
        if not hasattr(event, "pos"):
            return False
        # Read-only mode for AI buildings — even when the player is
        # possessing the faction.  Allow scroll wheel for browsing
        # but swallow any clicks so the player can't change recipes
        # or assign workers on the AI's behalf.
        b_faction = getattr(self.building, "faction", "SURVIVOR")
        if b_faction != "SURVIVOR":
            in_panel = self.rect.collidepoint(event.pos)
            if not in_panel:
                return False
            if event.type == pygame.MOUSEWHEEL:
                self._scroll = max(
                    0, self._scroll - event.y * 30,
                )
                return True
            if event.type == pygame.MOUSEBUTTONDOWN:
                if event.button == 4:
                    self._scroll = max(0, self._scroll - 30)
                    return True
                if event.button == 5:
                    self._scroll += 30
                    return True
                # The Possess button lives inside the read-only AI
                # popup — let it fire before swallowing the click.
                if (event.button == 1
                        and self._possess_btn is not None
                        and self._possess_btn.collidepoint(event.pos)):
                    if (self.on_possess is not None
                            and self.building is not None):
                        self.on_possess(self.building)
                    return True
                # Swallow other clicks to prevent recipe/worker mods.
                return True
            return True
        # When the recipe dropdown is open, allow clicks on the
        # floating option rects even if they fall outside the panel.
        in_panel = self.rect.collidepoint(event.pos)
        in_dropdown = bool(
            self._recipe_dropdown_open
            and self._recipe_dropdown_rect is not None
            and self._recipe_dropdown_rect.collidepoint(event.pos)
        )
        if not in_panel and not in_dropdown:
            if (event.type == pygame.MOUSEBUTTONDOWN
                    and self._recipe_dropdown_open):
                for btn_rect, _ in self._recipe_rects:
                    if btn_rect.collidepoint(event.pos):
                        break
                else:
                    for btn_rect, _ in self._mat_recipe_rects:
                        if btn_rect.collidepoint(event.pos):
                            break
                    else:
                        # Click outside both panel and overlay options
                        # closes the dropdown without consuming the
                        # event.
                        self._recipe_dropdown_open = False
                        return False
            else:
                return False

        if event.type == pygame.MOUSEWHEEL:
            # Scroll the recipe dropdown when the cursor is over it,
            # otherwise scroll the panel itself.
            mx, my = pygame.mouse.get_pos()
            if (self._recipe_dropdown_open
                    and self._recipe_dropdown_rect is not None
                    and self._recipe_dropdown_rect.collidepoint((mx, my))):
                self._dropdown_scroll -= event.y * 30
                if self._dropdown_scroll < 0:
                    self._dropdown_scroll = 0
                return True
            self._scroll -= event.y * 30
            max_scroll = max(0, self._content_h - self._view_h)
            self._scroll = max(0, min(self._scroll, max_scroll))
            return True

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self._tech_tree_btn is not None and self._tech_tree_btn.collidepoint(event.pos):
                if self.on_open_tech_tree is not None:
                    self.on_open_tech_tree()
                return True
            if (self._possess_btn is not None
                    and self._possess_btn.collidepoint(event.pos)):
                if self.on_possess is not None and self.building is not None:
                    self.on_possess(self.building)
                return True
            if self.building.type in (
                BuildingType.WORKSHOP,
                BuildingType.FORGE,
                BuildingType.REFINERY,
                BuildingType.ASSEMBLER,
                BuildingType.CHEMICAL_PLANT,
                BuildingType.OIL_REFINERY,
            ):
                # Dropdown header toggle.
                if (self._recipe_dropdown_btn is not None
                        and self._recipe_dropdown_btn.collidepoint(event.pos)):
                    self._recipe_dropdown_open = not self._recipe_dropdown_open
                    return True
                for btn_rect, craft_type in self._recipe_rects:
                    if btn_rect.collidepoint(event.pos):
                        if self.building.recipe == craft_type:
                            self.building.recipe = None
                            self.building.craft_progress = 0.0
                        else:
                            self.building.recipe = craft_type
                            self.building.craft_progress = 0.0
                        self._recipe_dropdown_open = False
                        return True
                for btn_rect, mrec in self._mat_recipe_rects:
                    if btn_rect.collidepoint(event.pos):
                        if self.building.recipe == mrec.output:
                            self.building.recipe = None
                            self.building.craft_progress = 0.0
                        else:
                            self.building.recipe = mrec.output
                            self.building.craft_progress = 0.0
                        self._recipe_dropdown_open = False
                        return True
            if self.building.type in (
                BuildingType.STORAGE, BuildingType.FLUID_TANK,
            ):
                for btn_rect, res in self._storage_res_rects:
                    if btn_rect.collidepoint(event.pos):
                        if self.building.stored_resource == res:
                            self.building.stored_resource = None
                        else:
                            self.building.stored_resource = res
                        return True
            if self.building.type == BuildingType.GATHERER:
                for btn_rect, res in self._gatherer_output_rects:
                    if btn_rect.collidepoint(event.pos):
                        self.building.gatherer_output = res
                        return True
            if self.building.type == BuildingType.QUARRY:
                for btn_rect, res in self._quarry_output_rects:
                    if btn_rect.collidepoint(event.pos):
                        self.building.quarry_output = res
                        return True
        return True  # consume any click inside the panel
