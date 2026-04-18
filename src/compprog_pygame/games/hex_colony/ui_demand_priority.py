"""Resource-demand priority UI: bottom-bar tab + drag-drop overlay.

Mirrors ``ui_worker_priority`` but operates on
:attr:`~compprog_pygame.games.hex_colony.world.Network.demand_priority`
instead of ``priority``.  Each tier is a horizontal row of building
cards.  Logistics workers will satisfy the highest-occupied tier
first; within a tier they balance shipments evenly between members.

An ``Auto`` toggle (green when enabled, red when disabled) controls
whether the tiers are recomputed automatically every rebuild
(non-storage on tier 0, storage on tier 1) or are left for the player
to edit manually.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pygame

from compprog_pygame.games.hex_colony.buildings import (
    Building,
    BuildingType,
)
from compprog_pygame.games.hex_colony.resource_icons import get_resource_icon
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
from compprog_pygame.games.hex_colony.ui_bottom_bar import BuildingsTabContent

if TYPE_CHECKING:
    from compprog_pygame.games.hex_colony.world import Network, World


_CARD_W = 148
_CARD_H = 56
_CARD_GAP = 8
_TIER_GAP = 10
_TIER_LABEL_W = 70
_EDIT_BTN_W = 140
_EDIT_BTN_H = 36
_AUTO_BTN_W = 76
_AUTO_BTN_H = 30
_GREEN = (60, 170, 80)
_GREEN_HI = (90, 200, 110)
_RED = (190, 70, 70)
_RED_HI = (220, 100, 100)


def _card_label(btype: BuildingType) -> str:
    return BuildingsTabContent._LABEL.get(btype, btype.name.title())


def _card_icon(btype: BuildingType, size: int = 28) -> pygame.Surface | None:
    res = BuildingsTabContent._HARVEST_ICON_RESOURCE.get(btype)
    if res is not None:
        return get_resource_icon(res, size - 8)
    return BuildingsTabContent._get_building_preview(btype, size)


def _building_demand_resources(b: Building, world: "World") -> list:
    """Return the list of Resources this building currently demands.

    Uses the same private helper that the logistics scheduler does so
    that the UI matches the simulator exactly.
    """
    demand = world._building_demand(b)
    return [r for r, need in demand.items() if need > 1e-3]


def _draw_demand_card(
    surface: pygame.Surface, rect: pygame.Rect, b: Building,
    world: "World", *, ghost: bool = False, highlighted: bool = False,
) -> None:
    bg = UI_TAB_ACTIVE if highlighted else UI_TAB_INACTIVE
    bg_surf = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
    bg_surf.fill(bg)
    if ghost:
        bg_surf.set_alpha(170)
    surface.blit(bg_surf, rect.topleft)
    border = UI_ACCENT if highlighted else UI_BORDER
    pygame.draw.rect(surface, border, rect, width=2, border_radius=4)

    icon = _card_icon(b.type, 24)
    icon_x = rect.x + 6
    if icon is not None:
        surface.blit(icon, (icon_x, rect.y + 4))
        name_x = icon_x + icon.get_width() + 4
    else:
        name_x = rect.x + 8
    name = render_text_clipped(
        Fonts.body(), _card_label(b.type), UI_TEXT, rect.right - name_x - 4,
    )
    surface.blit(name, (name_x, rect.y + 4))

    # Demand chips along the bottom row — one icon per resource.
    demanded = _building_demand_resources(b, world)
    if not demanded:
        msg = Fonts.small().render("(no demand)", True, UI_MUTED)
        surface.blit(msg, (rect.x + 6, rect.bottom - msg.get_height() - 4))
        return
    chip_size = 16
    cx = rect.x + 6
    cy = rect.bottom - chip_size - 4
    for r in demanded[:6]:
        ic = get_resource_icon(r, chip_size)
        if ic is not None:
            surface.blit(ic, (cx, cy))
        cx += chip_size + 2


# ── Bottom-bar tab ───────────────────────────────────────────────

class DemandPriorityTabContent(TabContent):
    """Read-only summary of the current resource-demand hierarchy."""

    def __init__(self) -> None:
        self.on_open_edit: "callable | None" = None
        self.on_toggle_auto: "callable | None" = None
        self._edit_btn_rect: pygame.Rect = pygame.Rect(0, 0, 0, 0)
        self._edit_hover: bool = False
        self._auto_btn_rect: pygame.Rect = pygame.Rect(0, 0, 0, 0)
        self._auto_hover: bool = False
        self._scroll: int = 0
        self._selected_net_id: int | None = None
        self._net_tab_rects: list[tuple[pygame.Rect, int]] = []

    def _pick_network(self, world: "World") -> "Network | None":
        if not world.networks:
            self._selected_net_id = None
            return None
        for n in world.networks:
            if n.id == self._selected_net_id:
                return n
        self._selected_net_id = world.networks[0].id
        return world.networks[0]

    def _draw_auto_button(
        self, surface: pygame.Surface, net: "Network",
    ) -> None:
        on = net.demand_auto
        base = _GREEN if on else _RED
        hi = _GREEN_HI if on else _RED_HI
        bg = hi if self._auto_hover else base
        bg_surf = pygame.Surface(
            (self._auto_btn_rect.w, self._auto_btn_rect.h), pygame.SRCALPHA,
        )
        bg_surf.fill((*bg, 235))
        surface.blit(bg_surf, self._auto_btn_rect.topleft)
        pygame.draw.rect(
            surface, UI_BORDER, self._auto_btn_rect,
            width=2, border_radius=4,
        )
        label = Fonts.body().render("Auto", True, UI_TEXT)
        surface.blit(label, (
            self._auto_btn_rect.centerx - label.get_width() // 2,
            self._auto_btn_rect.centery - label.get_height() // 2,
        ))

    def draw_content(
        self, surface: pygame.Surface, rect: pygame.Rect, world: "World",
    ) -> None:
        # Right-aligned Edit button.
        self._edit_btn_rect = pygame.Rect(
            rect.right - _EDIT_BTN_W - 10,
            rect.y + (rect.h - _EDIT_BTN_H) // 2,
            _EDIT_BTN_W, _EDIT_BTN_H,
        )
        btn_bg = UI_TAB_HOVER if self._edit_hover else UI_TAB_INACTIVE
        bg_surf = pygame.Surface(
            (self._edit_btn_rect.w, self._edit_btn_rect.h), pygame.SRCALPHA,
        )
        bg_surf.fill(btn_bg)
        surface.blit(bg_surf, self._edit_btn_rect.topleft)
        pygame.draw.rect(
            surface, UI_ACCENT, self._edit_btn_rect, width=2, border_radius=4,
        )
        label = Fonts.body().render("Edit Demand", True, UI_TEXT)
        surface.blit(label, (
            self._edit_btn_rect.centerx - label.get_width() // 2,
            self._edit_btn_rect.centery - label.get_height() // 2,
        ))

        selected = self._pick_network(world)

        # Auto toggle just left of the Edit button.
        self._auto_btn_rect = pygame.Rect(
            self._edit_btn_rect.left - _AUTO_BTN_W - 10,
            rect.y + (rect.h - _AUTO_BTN_H) // 2,
            _AUTO_BTN_W, _AUTO_BTN_H,
        )
        if selected is not None:
            self._draw_auto_button(surface, selected)

        # Network tab strip.
        tabs_rect = pygame.Rect(
            rect.x + 6, rect.y + 4,
            self._auto_btn_rect.left - rect.x - 12, 22,
        )
        tabs_h = 0
        if len(world.networks) > 1:
            self._net_tab_rects = []
            x = tabs_rect.x
            for n in world.networks:
                lbl = Fonts.small().render(n.name, True, UI_TEXT)
                tw = lbl.get_width() + 20
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
        else:
            self._net_tab_rects = []

        list_rect = pygame.Rect(
            rect.x + 6, rect.y + 6 + tabs_h,
            self._auto_btn_rect.left - rect.x - 12,
            rect.h - 12 - tabs_h,
        )
        tiers = selected.demand_priority if selected is not None else []
        if not tiers:
            msg = Fonts.body().render(
                "No buildings demand resources yet.", True, UI_MUTED,
            )
            surface.blit(msg, (list_rect.x + 4, list_rect.y + 4))
            return

        prev_clip = surface.get_clip()
        surface.set_clip(list_rect)
        y = list_rect.y - self._scroll
        for ti, tier in enumerate(tiers):
            label_surf = Fonts.small().render(
                f"Tier {ti + 1}", True, UI_ACCENT,
            )
            surface.blit(label_surf, (list_rect.x + 2, y + 4))
            x = list_rect.x + _TIER_LABEL_W
            for b in tier:
                card_rect = pygame.Rect(x, y, _CARD_W, _CARD_H - 12)
                _draw_demand_card(surface, card_rect, b, world)
                x += _CARD_W + _CARD_GAP
            y += _CARD_H - 12 + _TIER_GAP
        surface.set_clip(prev_clip)

    def handle_event(
        self, event: pygame.event.Event, rect: pygame.Rect,
    ) -> bool:
        if event.type == pygame.MOUSEMOTION:
            self._edit_hover = self._edit_btn_rect.collidepoint(event.pos)
            self._auto_hover = self._auto_btn_rect.collidepoint(event.pos)
            return False
        if event.type == pygame.MOUSEWHEEL:
            self._scroll = max(0, self._scroll - event.y * 20)
            return True
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self._edit_btn_rect.collidepoint(event.pos):
                if self.on_open_edit is not None:
                    self.on_open_edit()
                return True
            if self._auto_btn_rect.collidepoint(event.pos):
                # Toggle handled via ``on_toggle_auto`` if the host
                # provides a hook; otherwise toggle inline using the
                # remembered network id.
                if self.on_toggle_auto is not None:
                    self.on_toggle_auto(self._selected_net_id)
                return True
            for tab_rect, net_id in self._net_tab_rects:
                if tab_rect.collidepoint(event.pos):
                    self._selected_net_id = net_id
                    return True
        return False


# ── Edit overlay ─────────────────────────────────────────────────

_OVERLAY_TITLE_H = 44
_OVERLAY_PAD = 20
_ROW_H = 64
_ROW_LABEL_W = 70
_ROW_V_GAP = 8
_OV_CARD_W = 148
_OV_CARD_H = 52
_OV_CARD_GAP = 8
_DONE_BTN_W = 110
_DONE_BTN_H = 32
_OV_AUTO_W = 96
_OV_AUTO_H = 32
_EMPTY_ROW_HINT = "Drop here to create a new tier"


class DemandPriorityOverlay(Panel):
    """Fullscreen drag-and-drop editor for resource-demand tiers."""

    def __init__(self) -> None:
        super().__init__()
        self.visible: bool = False
        self.world: "World | None" = None
        self._drag_building: Building | None = None
        self._drag_mouse_offset: tuple[int, int] = (0, 0)
        self._drag_origin_tier: int = -1
        self._drag_origin_index: int = -1
        self._mouse_pos: tuple[int, int] = (0, 0)
        self._card_rects: list[
            tuple[pygame.Rect, int, int, Building]
        ] = []
        self._row_rects: list[tuple[pygame.Rect, int]] = []
        self._empty_row_rect: pygame.Rect = pygame.Rect(0, 0, 0, 0)
        self._done_rect: pygame.Rect = pygame.Rect(0, 0, 0, 0)
        self._auto_rect: pygame.Rect = pygame.Rect(0, 0, 0, 0)
        self._scroll: int = 0
        self._selected_net_id: int | None = None
        self._net_tab_rects: list[tuple[pygame.Rect, int]] = []

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
            "Edit Resource Demand", True, UI_TEXT,
        )
        surface.blit(title_surf, (
            title_rect.x + _OVERLAY_PAD,
            title_rect.centery - title_surf.get_height() // 2,
        ))
        hint = Fonts.small().render(
            "Higher tier = first to receive deliveries. "
            "Same-tier buildings split demand evenly.",
            True, UI_MUTED,
        )
        surface.blit(hint, (
            title_rect.x + _OVERLAY_PAD + title_surf.get_width() + 18,
            title_rect.centery - hint.get_height() // 2 + 6,
        ))

        # Done button.
        self._done_rect = pygame.Rect(
            self.rect.right - _DONE_BTN_W - _OVERLAY_PAD,
            title_rect.centery - _DONE_BTN_H // 2,
            _DONE_BTN_W, _DONE_BTN_H,
        )
        done_bg = UI_TAB_HOVER if self._done_rect.collidepoint(
            self._mouse_pos
        ) else UI_TAB_INACTIVE
        bg_surf = pygame.Surface(
            (self._done_rect.w, self._done_rect.h), pygame.SRCALPHA,
        )
        bg_surf.fill(done_bg)
        surface.blit(bg_surf, self._done_rect.topleft)
        pygame.draw.rect(
            surface, UI_ACCENT, self._done_rect, width=2, border_radius=4,
        )
        done_label = Fonts.body().render("Done", True, UI_TEXT)
        surface.blit(done_label, (
            self._done_rect.centerx - done_label.get_width() // 2,
            self._done_rect.centery - done_label.get_height() // 2,
        ))

        current_net = self._current_network()

        # Auto toggle just left of Done.
        self._auto_rect = pygame.Rect(
            self._done_rect.left - _OV_AUTO_W - 10,
            title_rect.centery - _OV_AUTO_H // 2,
            _OV_AUTO_W, _OV_AUTO_H,
        )
        if current_net is not None:
            on = current_net.demand_auto
            base = _GREEN if on else _RED
            hi = _GREEN_HI if on else _RED_HI
            hov = self._auto_rect.collidepoint(self._mouse_pos)
            bg2 = pygame.Surface(
                (self._auto_rect.w, self._auto_rect.h), pygame.SRCALPHA,
            )
            bg2.fill((*(hi if hov else base), 235))
            surface.blit(bg2, self._auto_rect.topleft)
            pygame.draw.rect(
                surface, UI_BORDER, self._auto_rect,
                width=2, border_radius=4,
            )
            txt = Fonts.body().render(
                "Auto: ON" if on else "Auto: OFF", True, UI_TEXT,
            )
            surface.blit(txt, (
                self._auto_rect.centerx - txt.get_width() // 2,
                self._auto_rect.centery - txt.get_height() // 2,
            ))

        # Tier area + network tabs.
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
                tw = lbl.get_width() + 28
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
        tiers = current_net.demand_priority if current_net is not None else []
        self._card_rects = []
        self._row_rects = []
        y = area.y - self._scroll

        for ti, tier in enumerate(tiers):
            row_rect = pygame.Rect(area.x, y, area.w, _ROW_H)
            self._draw_row(surface, row_rect, tier, ti, world)
            self._row_rects.append((row_rect, ti))
            y += _ROW_H + _ROW_V_GAP

        empty_rect = pygame.Rect(area.x, y, area.w, _ROW_H)
        self._empty_row_rect = empty_rect
        self._draw_empty_row(surface, empty_rect)
        surface.set_clip(prev_clip)

        if self._drag_building is not None and current_net is not None:
            gx, gy = self._mouse_pos
            ox, oy = self._drag_mouse_offset
            ghost_rect = pygame.Rect(
                gx - ox, gy - oy, _OV_CARD_W, _OV_CARD_H,
            )
            _draw_demand_card(
                surface, ghost_rect, self._drag_building, world,
                ghost=True, highlighted=True,
            )

    def _draw_row(
        self, surface: pygame.Surface, rect: pygame.Rect,
        tier: list[Building], tier_idx: int, world: "World",
    ) -> None:
        bg = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
        bg.fill((24, 32, 42, 180))
        surface.blit(bg, rect.topleft)
        pygame.draw.rect(surface, UI_BORDER, rect, width=1, border_radius=4)
        label = Fonts.body().render(
            f"Tier {tier_idx + 1}", True, UI_ACCENT,
        )
        surface.blit(label, (
            rect.x + 8, rect.centery - label.get_height() // 2,
        ))
        x = rect.x + _ROW_LABEL_W
        cy = rect.centery - _OV_CARD_H // 2
        for ci, b in enumerate(tier):
            if (b is self._drag_building
                    and tier_idx == self._drag_origin_tier
                    and ci == self._drag_origin_index):
                x += _OV_CARD_W + _OV_CARD_GAP
                continue
            card_rect = pygame.Rect(x, cy, _OV_CARD_W, _OV_CARD_H)
            _draw_demand_card(surface, card_rect, b, world)
            self._card_rects.append((card_rect, tier_idx, ci, b))
            x += _OV_CARD_W + _OV_CARD_GAP

    def _draw_empty_row(
        self, surface: pygame.Surface, rect: pygame.Rect,
    ) -> None:
        bg = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
        bg.fill((20, 28, 36, 140))
        surface.blit(bg, rect.topleft)
        pygame.draw.rect(surface, UI_BORDER, rect, width=1, border_radius=4)
        pygame.draw.rect(
            surface, UI_ACCENT, rect.inflate(-6, -6),
            width=1, border_radius=3,
        )
        hint = Fonts.small().render(_EMPTY_ROW_HINT, True, UI_MUTED)
        surface.blit(hint, (
            rect.centerx - hint.get_width() // 2,
            rect.centery - hint.get_height() // 2,
        ))

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
            if self._done_rect.collidepoint(event.pos):
                self._cancel_drag()
                self.visible = False
                return True
            net = self._current_network()
            if net is not None and self._auto_rect.collidepoint(event.pos):
                net.demand_auto = not net.demand_auto
                if net.demand_auto and self.world is not None:
                    # Immediately re-derive auto tiers so the user sees
                    # the change on the next frame.
                    net.demand_priority = self.world._auto_demand_tiers(
                        list(net.buildings),
                    )
                return True
            for tab_rect, net_id in self._net_tab_rects:
                if tab_rect.collidepoint(event.pos):
                    self._selected_net_id = net_id
                    self._cancel_drag()
                    return True
            # Block drag editing while in auto mode.
            if net is not None and net.demand_auto:
                return True
            for rect, ti, ci, b in self._card_rects:
                if rect.collidepoint(event.pos):
                    self._drag_building = b
                    self._drag_origin_tier = ti
                    self._drag_origin_index = ci
                    self._drag_mouse_offset = (
                        event.pos[0] - rect.x,
                        event.pos[1] - rect.y,
                    )
                    return True
            return True

        if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            self._mouse_pos = event.pos
            if self._drag_building is not None:
                self._drop(event.pos)
            return True
        return False

    def _cancel_drag(self) -> None:
        self._drag_building = None
        self._drag_origin_tier = -1
        self._drag_origin_index = -1

    def _drop(self, pos: tuple[int, int]) -> None:
        if self.world is None or self._drag_building is None:
            return
        net = self._current_network()
        if net is None:
            self._cancel_drag()
            return
        tiers = net.demand_priority
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
        row_rect = None
        for rect, ti in self._row_rects:
            if ti == target_ti:
                row_rect = rect
                break
        target_ti_adj = min(target_ti, len(tiers) - 1)
        target_tier = tiers[target_ti_adj]
        insert_idx = len(target_tier)
        if row_rect is not None:
            rel_x = pos[0] - (row_rect.x + _ROW_LABEL_W)
            slot = rel_x // (_OV_CARD_W + _OV_CARD_GAP)
            insert_idx = max(0, min(len(target_tier), int(slot)))
        target_tier.insert(insert_idx, b)
        tiers[:] = [t for t in tiers if t]
        self._cancel_drag()


__all__ = [
    "DemandPriorityOverlay",
    "DemandPriorityTabContent",
]
