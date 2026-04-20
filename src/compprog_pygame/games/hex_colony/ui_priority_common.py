"""Shared widgets for the Demand and Supply priority UI tabs.

Both tabs render building cards grouped into priority tiers, with:

* A network selector strip across the top.
* A resource-filter dropdown that hides cards which neither demand
  nor supply (depending on the kind) the chosen resource.
* Vertical scrolling so larger colonies fit.
* Compact cards that auto-fit the building name + resource chips.
* An ``Auto`` toggle that flips the corresponding ``*_auto`` flag on
  every network in view.
* An ``Edit`` button that opens the tier-editor overlay (a separate
  panel which subclasses :class:`PriorityOverlayBase`).

The simulator-side structures (``Network.demand_priority`` /
``Network.supply_priority`` and their auto flags) are unchanged — the
only role of this module is to draw / edit them.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable

import pygame

from compprog_pygame.games.hex_colony.buildings import (
    Building,
    BuildingType,
)
from compprog_pygame.games.hex_colony.resource_icons import get_resource_icon
from compprog_pygame.games.hex_colony.resources import Resource
from compprog_pygame.games.hex_colony.ui import (
    Fonts,
    Panel,
    TabContent,
    UI_ACCENT,
    UI_BORDER,
    UI_MUTED,
    UI_TAB_ACTIVE,
    UI_TAB_HOVER,
    UI_TAB_INACTIVE,
    UI_TEXT,
    draw_panel_bg,
    render_text_clipped,
)
from compprog_pygame.games.hex_colony.ui_bottom_bar import BuildingsTabContent

if TYPE_CHECKING:
    from compprog_pygame.games.hex_colony.world import Network, World


# ── Styling constants ────────────────────────────────────────────

_GREEN = (60, 170, 80)
_GREEN_HI = (90, 200, 110)
_RED = (190, 70, 70)
_RED_HI = (220, 100, 100)

_CARD_H = 40
_CARD_V_PAD = 4
_CARD_H_PAD = 6
_CARD_GAP_X = 6
_CARD_GAP_Y = 4
_CARD_ICON = 20
_CARD_CHIP = 12
_CARD_MIN_W = 110
_CARD_MAX_W = 220

_TIER_ROW_PAD = 6
_TIER_LABEL_W = 56
_TIER_GAP_Y = 6

_BTN_H = 28
_AUTO_BTN_W = 76
_EDIT_BTN_W = 110
_FILTER_BTN_W = 130

_DROPDOWN_ROW_H = 26
_DROPDOWN_W = 200
_DROPDOWN_MAX_VISIBLE = 8


# ── Spec ─────────────────────────────────────────────────────────

@dataclass
class PrioritySpec:
    """All the per-kind behaviour that differs between Demand and
    Supply versions of the panel."""
    kind: str  # "demand" or "supply"
    title_overlay: str  # e.g. "Edit Resource Demand"
    edit_btn_label: str  # e.g. "Edit Demand"
    empty_message: str  # shown when no buildings have anything
    get_tiers: Callable[["Network"], list[list[Building]]]
    set_tiers: Callable[["Network", list[list[Building]]], None]
    get_auto: Callable[["Network"], bool]
    set_auto: Callable[["Network", bool], None]
    get_resources: Callable[[Building, "World"], list[Resource]]
    auto_recompute: Callable[["World", list[Building]], list[list[Building]]]


def _all_resources_in_view(
    spec: PrioritySpec, world: "World", net: "Network",
) -> list[Resource]:
    seen: list[Resource] = []
    seen_set: set[Resource] = set()
    for tier in spec.get_tiers(net):
        for b in tier:
            for r in spec.get_resources(b, world):
                if r not in seen_set:
                    seen_set.add(r)
                    seen.append(r)
    seen.sort(key=lambda r: r.name)
    return seen


# ── Card rendering ───────────────────────────────────────────────

def _card_label(btype: BuildingType) -> str:
    return BuildingsTabContent._LABEL.get(btype, btype.name.title())


def _card_icon(btype: BuildingType) -> pygame.Surface | None:
    res = BuildingsTabContent._HARVEST_ICON_RESOURCE.get(btype)
    if res is not None:
        return get_resource_icon(res, _CARD_ICON - 4)
    return BuildingsTabContent._get_building_preview(btype, _CARD_ICON)


def _measure_card_width(
    b: Building, resources: list[Resource],
) -> int:
    """Width that fits icon + name + chips + padding."""
    name_w = Fonts.small().size(_card_label(b.type))[0]
    chip_w = max(0, len(resources) * (_CARD_CHIP + 2) - 2)
    inner = _CARD_ICON + 4 + max(name_w, chip_w)
    total = inner + _CARD_H_PAD * 2
    return max(_CARD_MIN_W, min(_CARD_MAX_W, total))


def _draw_card(
    surface: pygame.Surface, rect: pygame.Rect, b: Building,
    resources: list[Resource], *,
    ghost: bool = False, highlighted: bool = False,
) -> None:
    bg = UI_TAB_ACTIVE if highlighted else UI_TAB_INACTIVE
    bg_surf = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
    bg_surf.fill(bg)
    if ghost:
        bg_surf.set_alpha(170)
    surface.blit(bg_surf, rect.topleft)
    border = UI_ACCENT if highlighted else UI_BORDER
    pygame.draw.rect(surface, border, rect, width=1, border_radius=3)

    icon = _card_icon(b.type)
    icon_x = rect.x + _CARD_H_PAD
    icon_y = rect.y + (rect.h - _CARD_ICON) // 2 - 6
    name_x = icon_x
    if icon is not None:
        surface.blit(icon, (icon_x, rect.y + _CARD_V_PAD))
        name_x = icon_x + _CARD_ICON + 4
    name = render_text_clipped(
        Fonts.small(), _card_label(b.type), UI_TEXT,
        rect.right - name_x - _CARD_H_PAD,
    )
    surface.blit(name, (name_x, rect.y + _CARD_V_PAD))

    cx = rect.x + _CARD_H_PAD
    cy = rect.bottom - _CARD_CHIP - _CARD_V_PAD
    for r in resources[:8]:
        ic = get_resource_icon(r, _CARD_CHIP)
        if ic is not None:
            surface.blit(ic, (cx, cy))
        cx += _CARD_CHIP + 2


# ── Auto / Edit / Filter buttons ─────────────────────────────────

def _draw_auto_button(
    surface: pygame.Surface, rect: pygame.Rect, on: bool, hover: bool,
) -> None:
    base = _GREEN if on else _RED
    hi = _GREEN_HI if on else _RED_HI
    bg = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
    bg.fill((*(hi if hover else base), 235))
    surface.blit(bg, rect.topleft)
    pygame.draw.rect(surface, UI_BORDER, rect, width=2, border_radius=4)
    label = Fonts.body().render("Auto", True, UI_TEXT)
    surface.blit(label, (
        rect.centerx - label.get_width() // 2,
        rect.centery - label.get_height() // 2,
    ))


def _draw_text_button(
    surface: pygame.Surface, rect: pygame.Rect, text: str, hover: bool,
    *, accent: tuple[int, int, int] = UI_ACCENT,
) -> None:
    bg_color = UI_TAB_HOVER if hover else UI_TAB_INACTIVE
    bg = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
    bg.fill(bg_color)
    surface.blit(bg, rect.topleft)
    pygame.draw.rect(surface, accent, rect, width=2, border_radius=4)
    label = Fonts.body().render(text, True, UI_TEXT)
    surface.blit(label, (
        rect.centerx - label.get_width() // 2,
        rect.centery - label.get_height() // 2,
    ))


# ── Generic tab content ──────────────────────────────────────────

class PriorityTabContent(TabContent):
    """Bottom-bar tab that lists buildings grouped by tier with
    filter / scroll / auto / edit affordances.

    Subclassed not — the spec controls all per-kind behaviour.
    """

    def __init__(self, spec: PrioritySpec) -> None:
        self.spec = spec
        self.on_open_edit: Callable[[], None] | None = None
        self.on_toggle_auto: Callable[[int | None], None] | None = None
        self._scroll: int = 0
        self._selected_net_id: int | None = None
        self._filter_resource: Resource | None = None
        self._filter_open: bool = False

        self._edit_btn_rect = pygame.Rect(0, 0, 0, 0)
        self._auto_btn_rect = pygame.Rect(0, 0, 0, 0)
        self._filter_btn_rect = pygame.Rect(0, 0, 0, 0)
        self._dropdown_rects: list[tuple[pygame.Rect, Resource | None]] = []
        self._net_tab_rects: list[tuple[pygame.Rect, int]] = []
        self._mouse_pos: tuple[int, int] = (0, 0)

    # ── Network helpers ───────────────────────────────────────

    def _pick_network(self, world: "World") -> "Network | None":
        if not world.networks:
            self._selected_net_id = None
            return None
        for n in world.networks:
            if n.id == self._selected_net_id:
                return n
        self._selected_net_id = world.networks[0].id
        return world.networks[0]

    def _filtered_tiers(
        self, world: "World", net: "Network",
    ) -> list[list[Building]]:
        """Strip cards that have no resources in this kind, optionally
        further restrict to ones touching ``self._filter_resource``.
        Returns tiers; empty tiers are dropped entirely."""
        result: list[list[Building]] = []
        for tier in self.spec.get_tiers(net):
            kept: list[Building] = []
            for b in tier:
                resources = self.spec.get_resources(b, world)
                if not resources:
                    continue
                if (self._filter_resource is not None
                        and self._filter_resource not in resources):
                    continue
                kept.append(b)
            if kept:
                result.append(kept)
        return result

    # ── Layout ────────────────────────────────────────────────

    def draw_content(
        self, surface: pygame.Surface, rect: pygame.Rect, world: "World",
    ) -> None:
        # Right side: edit / auto / filter buttons.
        cy = rect.y + (rect.h - _BTN_H) // 2
        self._edit_btn_rect = pygame.Rect(
            rect.right - _EDIT_BTN_W - 8, cy, _EDIT_BTN_W, _BTN_H,
        )
        self._auto_btn_rect = pygame.Rect(
            self._edit_btn_rect.left - _AUTO_BTN_W - 6,
            cy, _AUTO_BTN_W, _BTN_H,
        )
        self._filter_btn_rect = pygame.Rect(
            self._auto_btn_rect.left - _FILTER_BTN_W - 6,
            cy, _FILTER_BTN_W, _BTN_H,
        )

        selected = self._pick_network(world)

        _draw_text_button(
            surface, self._edit_btn_rect, self.spec.edit_btn_label,
            self._edit_btn_rect.collidepoint(self._mouse_pos),
        )
        if selected is not None:
            on = self.spec.get_auto(selected)
            _draw_auto_button(
                surface, self._auto_btn_rect, on,
                self._auto_btn_rect.collidepoint(self._mouse_pos),
            )
        # Filter button label.
        filter_label = (
            "Filter: All" if self._filter_resource is None
            else f"Filter: {self._filter_resource.name.title()}"
        )
        _draw_text_button(
            surface, self._filter_btn_rect, filter_label,
            self._filter_btn_rect.collidepoint(self._mouse_pos),
        )

        # Top: network tab strip (if multiple networks).
        tabs_rect = pygame.Rect(
            rect.x + 6, rect.y + 4,
            self._filter_btn_rect.left - rect.x - 12, 22,
        )
        tabs_h = 0
        self._net_tab_rects = []
        if len(world.networks) > 1:
            x = tabs_rect.x
            for n in world.networks:
                lbl = Fonts.small().render(n.name, True, UI_TEXT)
                tw = lbl.get_width() + 18
                tr = pygame.Rect(x, tabs_rect.y, tw, tabs_rect.h)
                bg = UI_TAB_ACTIVE if selected is n else UI_TAB_INACTIVE
                bgs = pygame.Surface((tr.w, tr.h), pygame.SRCALPHA)
                bgs.fill(bg)
                surface.blit(bgs, tr.topleft)
                pygame.draw.rect(
                    surface, UI_ACCENT if selected is n else UI_BORDER,
                    tr, width=1, border_radius=3,
                )
                surface.blit(lbl, (
                    tr.centerx - lbl.get_width() // 2,
                    tr.centery - lbl.get_height() // 2,
                ))
                self._net_tab_rects.append((tr, n.id))
                x += tw + 4
            tabs_h = tabs_rect.h + 4

        # List area.
        list_rect = pygame.Rect(
            rect.x + 6, rect.y + 6 + tabs_h,
            self._filter_btn_rect.left - rect.x - 12,
            rect.h - 12 - tabs_h,
        )
        tiers = (
            self._filtered_tiers(world, selected)
            if selected is not None else []
        )
        if not tiers:
            msg = Fonts.body().render(self.spec.empty_message, True, UI_MUTED)
            surface.blit(msg, (list_rect.x + 4, list_rect.y + 4))
        else:
            self._draw_tier_list(surface, list_rect, tiers, world)

        # Filter dropdown (drawn last so it floats on top).
        if self._filter_open and selected is not None:
            self._draw_dropdown(surface, world, selected)

    def _draw_tier_list(
        self, surface: pygame.Surface, area: pygame.Rect,
        tiers: list[list[Building]], world: "World",
    ) -> None:
        prev_clip = surface.get_clip()
        surface.set_clip(area)
        y = area.y - self._scroll
        max_card_w = max(0, area.w - _TIER_LABEL_W - _TIER_ROW_PAD)

        for ti, tier in enumerate(tiers):
            rows: list[list[tuple[Building, int]]] = [[]]
            row_w = 0
            for b in tier:
                resources = self.spec.get_resources(b, world)
                cw = _measure_card_width(b, resources)
                if rows[-1] and row_w + cw + _CARD_GAP_X > max_card_w:
                    rows.append([])
                    row_w = 0
                rows[-1].append((b, cw))
                row_w += cw + _CARD_GAP_X

            tier_h = (
                len(rows) * (_CARD_H + _CARD_GAP_Y) - _CARD_GAP_Y
            )
            label = Fonts.small().render(
                f"Tier {ti + 1}", True, UI_ACCENT,
            )
            surface.blit(label, (area.x + 2, y + 4))

            for row in rows:
                x = area.x + _TIER_LABEL_W
                for b, cw in row:
                    card_rect = pygame.Rect(x, y, cw, _CARD_H)
                    _draw_card(
                        surface, card_rect, b,
                        self.spec.get_resources(b, world),
                    )
                    x += cw + _CARD_GAP_X
                y += _CARD_H + _CARD_GAP_Y
            y += _TIER_GAP_Y - _CARD_GAP_Y

        # Save total content height so wheel scrolling can clamp.
        self._content_h = max(0, int(y + self._scroll - area.y))
        surface.set_clip(prev_clip)

    def _draw_dropdown(
        self, surface: pygame.Surface, world: "World", net: "Network",
    ) -> None:
        items: list[tuple[str, Resource | None]] = [("All resources", None)]
        for r in _all_resources_in_view(self.spec, world, net):
            items.append((r.name.replace("_", " ").title(), r))

        n_visible = min(_DROPDOWN_MAX_VISIBLE, len(items))
        total_h = n_visible * _DROPDOWN_ROW_H
        # Open upward so the dropdown stays inside the bottom bar.
        x = self._filter_btn_rect.x
        y = self._filter_btn_rect.top - total_h - 2
        if y < 0:
            y = self._filter_btn_rect.bottom + 2
        rect = pygame.Rect(x, y, _DROPDOWN_W, total_h)
        bg = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
        bg.fill((20, 26, 34, 245))
        surface.blit(bg, rect.topleft)
        pygame.draw.rect(surface, UI_ACCENT, rect, width=2, border_radius=4)

        self._dropdown_rects = []
        ry = y
        for label_str, r in items[:n_visible]:
            row = pygame.Rect(x, ry, _DROPDOWN_W, _DROPDOWN_ROW_H)
            hover = row.collidepoint(self._mouse_pos)
            if hover:
                hl = pygame.Surface((row.w, row.h), pygame.SRCALPHA)
                hl.fill(UI_TAB_HOVER)
                surface.blit(hl, row.topleft)
            ix = row.x + 6
            if r is not None:
                ic = get_resource_icon(r, 16)
                if ic is not None:
                    surface.blit(ic, (ix, row.y + (row.h - 16) // 2))
                ix += 20
            txt = Fonts.small().render(label_str, True, UI_TEXT)
            surface.blit(txt, (ix, row.y + (row.h - txt.get_height()) // 2))
            self._dropdown_rects.append((row, r))
            ry += _DROPDOWN_ROW_H

    # ── Events ────────────────────────────────────────────────

    def handle_event(
        self, event: pygame.event.Event, rect: pygame.Rect,
    ) -> bool:
        if event.type == pygame.MOUSEMOTION:
            self._mouse_pos = event.pos
            return False
        if event.type == pygame.MOUSEWHEEL:
            self._scroll = max(0, self._scroll - event.y * 24)
            return True
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            self._mouse_pos = event.pos
            # Dropdown click first (so it eats clicks before everything
            # else when open).
            if self._filter_open:
                for row, r in self._dropdown_rects:
                    if row.collidepoint(event.pos):
                        self._filter_resource = r
                        self._filter_open = False
                        return True
                self._filter_open = False
                # Fall through so a click on the filter button itself
                # toggles cleanly.
            if self._filter_btn_rect.collidepoint(event.pos):
                self._filter_open = not self._filter_open
                return True
            if self._edit_btn_rect.collidepoint(event.pos):
                if self.on_open_edit is not None:
                    self.on_open_edit()
                return True
            if self._auto_btn_rect.collidepoint(event.pos):
                if self.on_toggle_auto is not None:
                    self.on_toggle_auto(self._selected_net_id)
                return True
            for tr, nid in self._net_tab_rects:
                if tr.collidepoint(event.pos):
                    self._selected_net_id = nid
                    return True
        return False

    @property
    def selected_net_id(self) -> int | None:
        return self._selected_net_id


# ── Generic edit overlay ─────────────────────────────────────────

_OVERLAY_TITLE_H = 44
_OVERLAY_PAD = 18
_OV_ROW_PAD_Y = 6
_OV_ROW_LABEL_W = 70
_OV_ROW_GAP = 8
_DONE_BTN_W = 100
_DONE_BTN_H = 30
_OV_AUTO_W = 96
_OV_FILTER_W = 150
_EMPTY_HINT = "Drop here to create a new tier"


class PriorityOverlayBase(Panel):
    """Fullscreen drag-and-drop editor for a tier list."""

    def __init__(self, spec: PrioritySpec) -> None:
        super().__init__()
        self.spec = spec
        self.visible: bool = False
        self.world: "World | None" = None
        self._drag_building: Building | None = None
        self._drag_origin_tier: int = -1
        self._drag_origin_index: int = -1
        self._drag_offset: tuple[int, int] = (0, 0)
        self._mouse_pos: tuple[int, int] = (0, 0)
        self._card_rects: list[
            tuple[pygame.Rect, int, int, Building]
        ] = []
        self._row_rects: list[tuple[pygame.Rect, int]] = []
        # Tier-level drag (label is the handle).
        self._tier_label_rects: list[tuple[pygame.Rect, int]] = []
        self._drag_tier: int = -1
        self._empty_row_rect: pygame.Rect = pygame.Rect(0, 0, 0, 0)
        self._done_rect: pygame.Rect = pygame.Rect(0, 0, 0, 0)
        self._auto_rect: pygame.Rect = pygame.Rect(0, 0, 0, 0)
        self._filter_rect: pygame.Rect = pygame.Rect(0, 0, 0, 0)
        self._scroll: int = 0
        self._selected_net_id: int | None = None
        self._net_tab_rects: list[tuple[pygame.Rect, int]] = []
        self._filter_resource: Resource | None = None
        self._filter_open: bool = False
        self._dropdown_rects: list[tuple[pygame.Rect, Resource | None]] = []

    def _current_network(self) -> "Network | None":
        if self.world is None or not self.world.networks:
            self._selected_net_id = None
            return None
        for n in self.world.networks:
            if n.id == self._selected_net_id:
                return n
        self._selected_net_id = self.world.networks[0].id
        return self.world.networks[0]

    def layout(self, screen_w: int, screen_h: int) -> None:
        w = min(screen_w - 80, 1200)
        h = min(screen_h - 80, 720)
        self.rect = pygame.Rect(
            (screen_w - w) // 2, (screen_h - h) // 2, w, h,
        )

    def _filtered_tiers(
        self, net: "Network",
    ) -> list[list[Building]]:
        if self.world is None:
            return []
        result: list[list[Building]] = []
        for tier in self.spec.get_tiers(net):
            kept: list[Building] = []
            for b in tier:
                resources = self.spec.get_resources(b, self.world)
                if not resources:
                    continue
                if (self._filter_resource is not None
                        and self._filter_resource not in resources):
                    continue
                kept.append(b)
            result.append(kept)  # keep empty tiers as drop targets
        return result

    def draw(self, surface: pygame.Surface, world: "World") -> None:
        if not self.visible:
            return
        self.world = world
        dim = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
        dim.fill((0, 0, 0, 170))
        surface.blit(dim, (0, 0))
        draw_panel_bg(surface, self.rect, accent_edge="top")

        title_rect = pygame.Rect(
            self.rect.x, self.rect.y, self.rect.w, _OVERLAY_TITLE_H,
        )
        title_surf = Fonts.title().render(
            self.spec.title_overlay, True, UI_TEXT,
        )
        surface.blit(title_surf, (
            title_rect.x + _OVERLAY_PAD,
            title_rect.centery - title_surf.get_height() // 2,
        ))

        # Done / Auto / Filter buttons.
        cy = title_rect.centery
        self._done_rect = pygame.Rect(
            self.rect.right - _DONE_BTN_W - _OVERLAY_PAD,
            cy - _DONE_BTN_H // 2, _DONE_BTN_W, _DONE_BTN_H,
        )
        _draw_text_button(
            surface, self._done_rect, "Done",
            self._done_rect.collidepoint(self._mouse_pos),
        )
        self._auto_rect = pygame.Rect(
            self._done_rect.left - _OV_AUTO_W - 8,
            cy - _DONE_BTN_H // 2, _OV_AUTO_W, _DONE_BTN_H,
        )
        current_net = self._current_network()
        if current_net is not None:
            on = self.spec.get_auto(current_net)
            label = "Auto: ON" if on else "Auto: OFF"
            base = _GREEN if on else _RED
            hi = _GREEN_HI if on else _RED_HI
            hov = self._auto_rect.collidepoint(self._mouse_pos)
            bg = pygame.Surface(
                (self._auto_rect.w, self._auto_rect.h), pygame.SRCALPHA,
            )
            bg.fill((*(hi if hov else base), 235))
            surface.blit(bg, self._auto_rect.topleft)
            pygame.draw.rect(
                surface, UI_BORDER, self._auto_rect,
                width=2, border_radius=4,
            )
            txt = Fonts.body().render(label, True, UI_TEXT)
            surface.blit(txt, (
                self._auto_rect.centerx - txt.get_width() // 2,
                self._auto_rect.centery - txt.get_height() // 2,
            ))
        self._filter_rect = pygame.Rect(
            self._auto_rect.left - _OV_FILTER_W - 8,
            cy - _DONE_BTN_H // 2, _OV_FILTER_W, _DONE_BTN_H,
        )
        flbl = (
            "Filter: All" if self._filter_resource is None
            else f"Filter: {self._filter_resource.name.title()}"
        )
        _draw_text_button(
            surface, self._filter_rect, flbl,
            self._filter_rect.collidepoint(self._mouse_pos),
        )

        # Tier area below the title, with optional network tab strip.
        area = pygame.Rect(
            self.rect.x + _OVERLAY_PAD,
            self.rect.y + _OVERLAY_TITLE_H + _OVERLAY_PAD // 2,
            self.rect.w - _OVERLAY_PAD * 2,
            self.rect.bottom - self.rect.y
            - _OVERLAY_TITLE_H - _OVERLAY_PAD * 2,
        )
        self._net_tab_rects = []
        tabs_h = 0
        if len(world.networks) > 1:
            tabs_rect = pygame.Rect(area.x, area.y, area.w, 28)
            x = tabs_rect.x
            for n in world.networks:
                lbl = Fonts.body().render(n.name, True, UI_TEXT)
                tw = lbl.get_width() + 24
                tr = pygame.Rect(x, tabs_rect.y, tw, tabs_rect.h)
                bg = UI_TAB_ACTIVE if current_net is n else UI_TAB_INACTIVE
                bgs = pygame.Surface((tr.w, tr.h), pygame.SRCALPHA)
                bgs.fill(bg)
                surface.blit(bgs, tr.topleft)
                pygame.draw.rect(
                    surface, UI_ACCENT if current_net is n else UI_BORDER,
                    tr, width=2, border_radius=4,
                )
                surface.blit(lbl, (
                    tr.centerx - lbl.get_width() // 2,
                    tr.centery - lbl.get_height() // 2,
                ))
                self._net_tab_rects.append((tr, n.id))
                x += tw + 6
            tabs_h = tabs_rect.h + 6
        area = pygame.Rect(area.x, area.y + tabs_h, area.w, area.h - tabs_h)

        prev_clip = surface.get_clip()
        surface.set_clip(area)
        tiers = (
            self._filtered_tiers(current_net) if current_net is not None
            else []
        )
        self._card_rects = []
        self._row_rects = []
        self._tier_label_rects = []
        y = area.y - self._scroll

        max_w = max(0, area.w - _OV_ROW_LABEL_W - _OV_ROW_GAP)
        for ti, tier in enumerate(tiers):
            if ti == self._drag_tier:
                continue
            rows: list[list[tuple[Building, int]]] = [[]]
            row_w = 0
            for b in tier:
                if (b is self._drag_building
                        and ti == self._drag_origin_tier):
                    continue
                resources = self.spec.get_resources(b, world)
                cw = _measure_card_width(b, resources)
                if rows[-1] and row_w + cw + _CARD_GAP_X > max_w:
                    rows.append([])
                    row_w = 0
                rows[-1].append((b, cw))
                row_w += cw + _CARD_GAP_X
            tier_h = max(
                _CARD_H,
                len(rows) * (_CARD_H + _CARD_GAP_Y) - _CARD_GAP_Y,
            )
            row_rect = pygame.Rect(
                area.x, y - _OV_ROW_PAD_Y, area.w,
                tier_h + _OV_ROW_PAD_Y * 2,
            )
            bg = pygame.Surface(
                (row_rect.w, row_rect.h), pygame.SRCALPHA,
            )
            bg.fill((24, 32, 42, 180))
            surface.blit(bg, row_rect.topleft)
            pygame.draw.rect(
                surface, UI_BORDER, row_rect, width=1, border_radius=4,
            )
            label = Fonts.body().render(
                f"Tier {ti + 1}", True, UI_ACCENT,
            )
            surface.blit(label, (
                row_rect.x + 8,
                row_rect.centery - label.get_height() // 2,
            ))
            label_rect = pygame.Rect(
                row_rect.x + 4, row_rect.y + 4,
                _OV_ROW_LABEL_W - 8, row_rect.h - 8,
            )
            self._tier_label_rects.append((label_rect, ti))
            self._row_rects.append((row_rect, ti))

            ry = y
            ci_global = 0
            for row in rows:
                x = area.x + _OV_ROW_LABEL_W
                for b, cw in row:
                    cr = pygame.Rect(x, ry, cw, _CARD_H)
                    _draw_card(
                        surface, cr, b,
                        self.spec.get_resources(b, world),
                    )
                    self._card_rects.append((cr, ti, ci_global, b))
                    x += cw + _CARD_GAP_X
                    ci_global += 1
                ry += _CARD_H + _CARD_GAP_Y
            y = row_rect.bottom + _TIER_GAP_Y

        # Always-present empty row for new tier creation.
        empty_rect = pygame.Rect(
            area.x, y, area.w, _CARD_H + _OV_ROW_PAD_Y * 2,
        )
        self._empty_row_rect = empty_rect
        bg = pygame.Surface((empty_rect.w, empty_rect.h), pygame.SRCALPHA)
        bg.fill((20, 28, 36, 140))
        surface.blit(bg, empty_rect.topleft)
        pygame.draw.rect(
            surface, UI_ACCENT, empty_rect.inflate(-6, -6),
            width=1, border_radius=3,
        )
        hint = Fonts.small().render(_EMPTY_HINT, True, UI_MUTED)
        surface.blit(hint, (
            empty_rect.centerx - hint.get_width() // 2,
            empty_rect.centery - hint.get_height() // 2,
        ))
        surface.set_clip(prev_clip)

        # Drag ghost.
        if self._drag_tier >= 0 and current_net is not None:
            tiers_now = self.spec.get_tiers(current_net)
            if 0 <= self._drag_tier < len(tiers_now):
                _gx, gy = self._mouse_pos
                _ox, oy = self._drag_offset
                ghost_h = max(_CARD_H + _OV_ROW_PAD_Y * 2, 48)
                ghost_rect = pygame.Rect(
                    area.x, gy - oy, area.w, ghost_h,
                )
                gs = pygame.Surface(
                    (ghost_rect.w, ghost_rect.h), pygame.SRCALPHA,
                )
                gs.fill((40, 60, 80, 200))
                surface.blit(gs, ghost_rect.topleft)
                pygame.draw.rect(
                    surface, UI_ACCENT, ghost_rect,
                    width=2, border_radius=4,
                )
                lbl = Fonts.body().render(
                    f"Tier {self._drag_tier + 1}", True, UI_ACCENT,
                )
                surface.blit(lbl, (
                    ghost_rect.x + 8,
                    ghost_rect.centery - lbl.get_height() // 2,
                ))
        elif self._drag_building is not None and current_net is not None:
            resources = self.spec.get_resources(self._drag_building, world)
            cw = _measure_card_width(self._drag_building, resources)
            gx, gy = self._mouse_pos
            ox, oy = self._drag_offset
            ghost_rect = pygame.Rect(gx - ox, gy - oy, cw, _CARD_H)
            _draw_card(
                surface, ghost_rect, self._drag_building, resources,
                ghost=True, highlighted=True,
            )

        # Filter dropdown last (top-most).
        if self._filter_open and current_net is not None:
            self._draw_dropdown(surface, world, current_net)

    def _draw_dropdown(
        self, surface: pygame.Surface, world: "World", net: "Network",
    ) -> None:
        items: list[tuple[str, Resource | None]] = [("All resources", None)]
        for r in _all_resources_in_view(self.spec, world, net):
            items.append((r.name.replace("_", " ").title(), r))
        n_visible = min(_DROPDOWN_MAX_VISIBLE, len(items))
        total_h = n_visible * _DROPDOWN_ROW_H
        x = self._filter_rect.x
        y = self._filter_rect.bottom + 2
        rect = pygame.Rect(x, y, _DROPDOWN_W, total_h)
        bg = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
        bg.fill((20, 26, 34, 245))
        surface.blit(bg, rect.topleft)
        pygame.draw.rect(surface, UI_ACCENT, rect, width=2, border_radius=4)
        self._dropdown_rects = []
        ry = y
        for label_str, r in items[:n_visible]:
            row = pygame.Rect(x, ry, _DROPDOWN_W, _DROPDOWN_ROW_H)
            hover = row.collidepoint(self._mouse_pos)
            if hover:
                hl = pygame.Surface((row.w, row.h), pygame.SRCALPHA)
                hl.fill(UI_TAB_HOVER)
                surface.blit(hl, row.topleft)
            ix = row.x + 6
            if r is not None:
                ic = get_resource_icon(r, 16)
                if ic is not None:
                    surface.blit(ic, (ix, row.y + (row.h - 16) // 2))
                ix += 20
            txt = Fonts.small().render(label_str, True, UI_TEXT)
            surface.blit(txt, (ix, row.y + (row.h - txt.get_height()) // 2))
            self._dropdown_rects.append((row, r))
            ry += _DROPDOWN_ROW_H

    def handle_event(self, event: pygame.event.Event) -> bool:
        if not self.visible:
            return False
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            self._cancel_drag()
            self.visible = False
            return True
        if not hasattr(event, "pos"):
            if event.type == pygame.MOUSEWHEEL:
                self._scroll = max(0, self._scroll - event.y * 30)
                return True
            return False

        if event.type == pygame.MOUSEMOTION:
            self._mouse_pos = event.pos
            return True

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            self._mouse_pos = event.pos
            # Dropdown gets first dibs.
            if self._filter_open:
                for row, r in self._dropdown_rects:
                    if row.collidepoint(event.pos):
                        self._filter_resource = r
                        self._filter_open = False
                        return True
                self._filter_open = False
            if self._filter_rect.collidepoint(event.pos):
                self._filter_open = not self._filter_open
                return True
            if self._done_rect.collidepoint(event.pos):
                self._cancel_drag()
                self.visible = False
                return True
            net = self._current_network()
            if net is not None and self._auto_rect.collidepoint(event.pos):
                self.spec.set_auto(net, not self.spec.get_auto(net))
                if self.spec.get_auto(net) and self.world is not None:
                    self.spec.set_tiers(
                        net,
                        self.spec.auto_recompute(
                            self.world, list(net.buildings),
                        ),
                    )
                return True
            for tab_rect, net_id in self._net_tab_rects:
                if tab_rect.collidepoint(event.pos):
                    self._selected_net_id = net_id
                    self._cancel_drag()
                    return True
            if net is not None and self.spec.get_auto(net):
                # No drag editing while auto is on.
                return True
            # Tier-label drag (whole tier reorder) takes precedence
            # because labels sit to the left of cards.
            for label_rect, ti in self._tier_label_rects:
                if label_rect.collidepoint(event.pos):
                    self._drag_tier = ti
                    self._drag_offset = (
                        event.pos[0] - label_rect.x,
                        event.pos[1] - label_rect.y,
                    )
                    return True
            for rect, ti, ci, b in self._card_rects:
                if rect.collidepoint(event.pos):
                    self._drag_building = b
                    self._drag_origin_tier = ti
                    self._drag_origin_index = ci
                    self._drag_offset = (
                        event.pos[0] - rect.x,
                        event.pos[1] - rect.y,
                    )
                    return True
            return True

        if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            self._mouse_pos = event.pos
            if self._drag_tier >= 0:
                self._drop_tier(event.pos)
            elif self._drag_building is not None:
                self._drop(event.pos)
            return True
        return False

    def _cancel_drag(self) -> None:
        self._drag_building = None
        self._drag_origin_tier = -1
        self._drag_origin_index = -1
        self._drag_tier = -1

    def _drop_tier(self, pos: tuple[int, int]) -> None:
        """Reorder the dragged tier within the current network's
        tier list based on the drop position."""
        if self.world is None or self._drag_tier < 0:
            return
        net = self._current_network()
        if net is None:
            self._drag_tier = -1
            return
        tiers = self.spec.get_tiers(net)
        src = self._drag_tier
        if not (0 <= src < len(tiers)):
            self._drag_tier = -1
            return
        target_ti: int | None = None
        for rect, ti in self._row_rects:
            if rect.collidepoint(pos):
                target_ti = ti
                break
        if target_ti is None and self._empty_row_rect.collidepoint(pos):
            target_ti = len(tiers)
        if target_ti is None:
            self._drag_tier = -1
            return
        moving = tiers.pop(src)
        if target_ti > src:
            target_ti -= 1
        target_ti = max(0, min(len(tiers), target_ti))
        tiers.insert(target_ti, moving)
        self.spec.set_tiers(net, [t for t in tiers if t])
        self._drag_tier = -1

    def _drop(self, pos: tuple[int, int]) -> None:
        if self.world is None or self._drag_building is None:
            return
        net = self._current_network()
        if net is None:
            self._cancel_drag()
            return
        tiers = self.spec.get_tiers(net)
        b = self._drag_building
        origin_ti = self._drag_origin_tier

        target_ti: int | None = None
        create_new = False
        for rect, ti in self._row_rects:
            if rect.collidepoint(pos):
                target_ti = ti
                break
        if target_ti is None and self._empty_row_rect.collidepoint(pos):
            create_new = True
        if target_ti is None and not create_new:
            self._cancel_drag()
            return

        if 0 <= origin_ti < len(tiers):
            try:
                tiers[origin_ti].remove(b)
            except ValueError:
                pass

        if create_new:
            tiers[:] = [t for t in tiers if t]
            tiers.append([b])
            self._cancel_drag()
            return

        assert target_ti is not None
        target_ti_adj = min(target_ti, len(tiers) - 1)
        tiers[target_ti_adj].append(b)
        tiers[:] = [t for t in tiers if t]
        self._cancel_drag()
