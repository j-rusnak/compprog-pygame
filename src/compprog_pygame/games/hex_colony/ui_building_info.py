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

_BUILDING_LABEL: dict[BuildingType, str] = {
    BuildingType.CAMP: "Ship Wreckage",
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
    BuildingType.RESEARCH_CENTER: "Research Center",
}

WORKSHOP_CRAFTABLE: list[BuildingType] = [
    BuildingType.HABITAT,
    BuildingType.PATH,
    BuildingType.BRIDGE,
    BuildingType.WALL,
    BuildingType.WOODCUTTER,
    BuildingType.QUARRY,
    BuildingType.GATHERER,
    BuildingType.STORAGE,
    BuildingType.REFINERY,
    BuildingType.FARM,
    BuildingType.WELL,
    BuildingType.WORKSHOP,
]


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


_Item = _Line | _IconLine | _Spacer | _RecipeBtn | _MaterialRecipeBtn | _TechTreeBtn


class BuildingInfoPanel(Panel):
    """Pop-up panel showing details about the selected building."""

    def __init__(self) -> None:
        super().__init__()
        self.building: Building | None = None
        self._screen_w = 0
        self._screen_h = 0
        self._recipe_rects: list[tuple[pygame.Rect, BuildingType]] = []
        self._mat_recipe_rects: list[tuple[pygame.Rect, MaterialRecipe]] = []
        self._tech_tree_btn: pygame.Rect | None = None
        self.on_open_tech_tree: typing.Callable[[], None] | None = None
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
            self._tech_tree_btn = None
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
        self._tech_tree_btn = None

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
            elif isinstance(item, _TechTreeBtn):
                self._draw_tech_btn(surface, x, cy)
            cy += item.height

        surface.set_clip(prev_clip)

        # Scrollbar
        if max_scroll > 0:
            self._draw_scrollbar(surface, max_scroll)

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
        label = item.craft_type.name.replace("_", " ").title()
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
            f"{item.recipe.output.name.replace('_', ' ').title()}"
            f" \u00d7{item.recipe.output_amount}"
        )
        surf = render_text_clipped(
            Fonts.small(), label, UI_TEXT, btn_rect.w - icon_size - 12,
        )
        surface.blit(surf, (icon_x + icon_size + 4, btn_rect.y + 3))
        self._mat_recipe_rects.append((btn_rect, item.recipe))

    def _draw_tech_btn(self, surface: pygame.Surface, x: int, cy: int) -> None:
        btn_rect = pygame.Rect(
            x + _PADDING, cy + 4, _PANEL_W - _PADDING * 2, _LINE_H + 4,
        )
        pygame.draw.rect(surface, UI_ACCENT, btn_rect, border_radius=4)
        pygame.draw.rect(surface, UI_BORDER, btn_rect, width=2, border_radius=4)
        surf = Fonts.body().render("\u2261 Open Tech Tree", True, UI_TEXT)
        surface.blit(surf, (
            btn_rect.centerx - surf.get_width() // 2,
            btn_rect.centery - surf.get_height() // 2,
        ))
        self._tech_tree_btn = btn_rect

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
        label = _BUILDING_LABEL.get(b.type, b.type.name.title())
        items.append(_Line(label, UI_ACCENT, Fonts.title(), 34))
        items.append(_Spacer(4))

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
            pop = world.population.count
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

        # Storage
        if b.storage_capacity > 0:
            items.append(_Spacer())
            line(f"Storage: {int(b.stored_total)}/{b.storage_capacity}")
            for res, amount in b.storage.items():
                if amount > 0:
                    items.append(_IconLine(
                        res,
                        f"{res.name.replace('_', ' ').capitalize()}: {int(amount)}",
                        RESOURCE_COLORS[res],
                    ))

        # Crafting stations — Workshop / Forge / Refinery / Assembler.
        if b.type in (
            BuildingType.WORKSHOP,
            BuildingType.FORGE,
            BuildingType.REFINERY,
            BuildingType.ASSEMBLER,
        ):
            items.append(_Spacer())

            # Active recipe + progress + cost breakdown.
            if b.recipe is not None:
                if isinstance(b.recipe, BuildingType):
                    recipe_name = b.recipe.name.replace("_", " ").title()
                    line(f"Crafting: {recipe_name}", UI_ACCENT)
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
                        name = b.recipe.name.replace("_", " ").title()
                        line(f"Crafting: {name} \u00d7{mrec.output_amount}",
                             UI_ACCENT)
                        pct = int(b.craft_progress / mrec.time * 100)
                        line(f"Progress: {pct}%")
                        for res, amount in mrec.inputs.items():
                            has = world.inventory[res] >= amount
                            col = RESOURCE_COLORS[res] if has else UI_BAD
                            items.append(_IconLine(res, f"{amount}", col))
            else:
                line("Select recipe:", UI_MUTED)

            items.append(_Spacer(4))

            # Building recipes (Workshop only).
            if b.type == BuildingType.WORKSHOP:
                god = bool(
                    self.god_mode_getter and self.god_mode_getter()
                )
                for craft_type in WORKSHOP_CRAFTABLE:
                    if not god and not is_building_available(
                        craft_type, self.tech_tree, self.tier_tracker,
                    ):
                        continue
                    items.append(_RecipeBtn(
                        craft_type, selected=(b.recipe == craft_type),
                    ))
                    items.append(_Spacer(2))

            # Material recipes for this station.
            station_recipes = recipes_for_station(b.type.name)
            if not bool(
                self.god_mode_getter and self.god_mode_getter()
            ):
                station_recipes = [
                    mr for mr in station_recipes
                    if is_resource_available(
                        mr.output, self.tech_tree, self.tier_tracker,
                    )
                ]
            if station_recipes:
                if b.type == BuildingType.WORKSHOP:
                    items.append(_Spacer(2))
                    line("Materials:", UI_MUTED, Fonts.small())
                for mrec in station_recipes:
                    items.append(_MaterialRecipeBtn(
                        mrec, selected=(b.recipe == mrec.output),
                    ))
                    items.append(_Spacer(2))

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
                bt.name.replace("_", " ").title()
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
                    bt.name.replace("_", " ").title()
                    for bt in nxt.unlocks_buildings
                )
                for wl in wrap_text(
                    Fonts.small(), f"  Unlocks: {names}", inner_w,
                ):
                    line(wl, UI_MUTED, Fonts.small())
        else:
            line("(Max tier reached)", UI_MUTED, Fonts.small())

    # ── Events ───────────────────────────────────────────────────

    def handle_event(self, event: pygame.event.Event) -> bool:
        if self.building is None:
            return False
        if not hasattr(event, "pos"):
            return False
        if not self.rect.collidepoint(event.pos):
            return False

        if event.type == pygame.MOUSEWHEEL:
            self._scroll -= event.y * 30
            max_scroll = max(0, self._content_h - self._view_h)
            self._scroll = max(0, min(self._scroll, max_scroll))
            return True

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self._tech_tree_btn is not None and self._tech_tree_btn.collidepoint(event.pos):
                if self.on_open_tech_tree is not None:
                    self.on_open_tech_tree()
                return True
            if self.building.type in (
                BuildingType.WORKSHOP,
                BuildingType.FORGE,
                BuildingType.REFINERY,
                BuildingType.ASSEMBLER,
            ):
                for btn_rect, craft_type in self._recipe_rects:
                    if btn_rect.collidepoint(event.pos):
                        if self.building.recipe == craft_type:
                            self.building.recipe = None
                            self.building.craft_progress = 0.0
                        else:
                            self.building.recipe = craft_type
                            self.building.craft_progress = 0.0
                        return True
                for btn_rect, mrec in self._mat_recipe_rects:
                    if btn_rect.collidepoint(event.pos):
                        if self.building.recipe == mrec.output:
                            self.building.recipe = None
                            self.building.craft_progress = 0.0
                        else:
                            self.building.recipe = mrec.output
                            self.building.craft_progress = 0.0
                        return True
        return True  # consume any click inside the panel
