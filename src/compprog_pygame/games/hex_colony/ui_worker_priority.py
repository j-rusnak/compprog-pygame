"""Worker-priority UI: bottom-bar tab + fullscreen Edit Hierarchy modal.

Tab
---
Shows placed worker-buildings grouped by priority tier, each card
labeled with ``workers/max``.  An ``Edit Hierarchy`` button on the
right opens the drag-and-drop overlay.

Edit Hierarchy overlay
----------------------
Full-screen modal.  A strip of tabs at the top lets the player switch
between disconnected building networks — workers can't cross
network boundaries, so each network has its own independent priority
queue.  Each tier is a horizontal row of building cards.  The user
may:
* Drag a card to another tier (including an always-present empty row
  at the bottom, which creates a new tier on drop).
* Drop between two cards in a tier to reorder within the tier.
* Switch networks with the tabs above the tier list.
* Close with the Done button (upper-right) or Escape.

Tier ordering drives the auto-assignment in
:meth:`compprog_pygame.games.hex_colony.world.World._assign_workers`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pygame

from compprog_pygame.games.hex_colony.buildings import (
    BUILDING_MAX_WORKERS,
    Building,
    BuildingType,
)
from compprog_pygame.games.hex_colony.ui import (
    Fonts,
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
    render_text_clipped,
)
from compprog_pygame.games.hex_colony.ui_bottom_bar import BuildingsTabContent

if TYPE_CHECKING:
    from compprog_pygame.games.hex_colony.world import Network, World


_CARD_W = 132
_CARD_H = 54
_CARD_GAP = 8
_TIER_GAP = 10
_TIER_LABEL_W = 70
_EDIT_BTN_W = 140
_EDIT_BTN_H = 36
_LOG_ROW_H = 38  # always-present Logistics row
_LOG_BTN_W = 28  # +/- button width


def _card_icon(btype: BuildingType, size: int = 28) -> pygame.Surface | None:
    """Pick the same preview sprite the Buildings tab uses for a card."""
    # Harvester buildings use the resource icon for visual consistency
    # with the Buildings tab.
    from compprog_pygame.games.hex_colony.resource_icons import get_resource_icon
    res = BuildingsTabContent._HARVEST_ICON_RESOURCE.get(btype)
    if res is not None:
        return get_resource_icon(res, size - 8)
    return BuildingsTabContent._get_building_preview(btype, size)


def _card_label(btype: BuildingType) -> str:
    return BuildingsTabContent._LABEL.get(btype, btype.name.title())


def _draw_building_card(
    surface: pygame.Surface, rect: pygame.Rect, b: Building,
    *, ghost: bool = False, highlighted: bool = False,
) -> None:
    """Render a single building card with icon + name + workers/max."""
    bg = UI_TAB_ACTIVE if highlighted else UI_TAB_INACTIVE
    bg_surf = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
    bg_surf.fill(bg)
    if ghost:
        bg_surf.set_alpha(170)
    surface.blit(bg_surf, rect.topleft)
    border = UI_ACCENT if highlighted else UI_BORDER
    pygame.draw.rect(surface, border, rect, width=2, border_radius=4)

    icon = _card_icon(b.type, 28)
    icon_x = rect.x + 6
    if icon is not None:
        surface.blit(icon, (icon_x, rect.y + 4))
        name_x = icon_x + icon.get_width() + 4
    else:
        name_x = rect.x + 8

    name = render_text_clipped(
        Fonts.body(), _card_label(b.type), UI_TEXT, rect.right - name_x - 4,
    )
    surface.blit(name, (name_x, rect.y + 6))

    stat_text = f"{b.workers}/{b.max_workers}"
    stat_surf = Fonts.small().render(stat_text, True, UI_MUTED)
    surface.blit(stat_surf, (
        rect.right - stat_surf.get_width() - 6,
        rect.bottom - stat_surf.get_height() - 4,
    ))


# ── Bottom-bar tab ───────────────────────────────────────────────

class WorkerPriorityTabContent(TabContent):
    """Read-only summary of the current worker-priority hierarchy."""

    def __init__(self) -> None:
        self.on_open_edit: "callable | None" = None
        self.on_toggle_auto: "callable | None" = None
        self._edit_btn_rect: pygame.Rect = pygame.Rect(0, 0, 0, 0)
        self._auto_btn_rect: pygame.Rect = pygame.Rect(0, 0, 0, 0)
        self._edit_hover: bool = False
        self._auto_hover: bool = False
        self._scroll: int = 0
        self._selected_net_id: int | None = None
        self._net_tab_rects: list[tuple[pygame.Rect, int]] = []

    def _pick_network(self, world: "World") -> "Network | None":
        if not world.networks:
            self._selected_net_id = None
            return None
        # If remembered id still exists, keep it.
        for n in world.networks:
            if n.id == self._selected_net_id:
                return n
        # Otherwise pick the first.
        self._selected_net_id = world.networks[0].id
        return world.networks[0]

    def _draw_network_tabs(
        self, surface: pygame.Surface, rect: pygame.Rect, world: "World",
        selected: "Network | None",
    ) -> None:
        self._net_tab_rects = []
        if len(world.networks) <= 1:
            return
        x = rect.x
        y = rect.y
        pad = 10
        for n in world.networks:
            label = Fonts.small().render(n.name, True, UI_TEXT)
            tab_w = label.get_width() + pad * 2
            tab_rect = pygame.Rect(x, y, tab_w, rect.h)
            bg = UI_TAB_ACTIVE if selected is n else UI_TAB_INACTIVE
            bg_surf = pygame.Surface((tab_rect.w, tab_rect.h), pygame.SRCALPHA)
            bg_surf.fill(bg)
            surface.blit(bg_surf, tab_rect.topleft)
            pygame.draw.rect(
                surface, UI_ACCENT if selected is n else UI_BORDER,
                tab_rect, width=1, border_radius=3,
            )
            surface.blit(label, (
                tab_rect.centerx - label.get_width() // 2,
                tab_rect.centery - label.get_height() // 2,
            ))
            self._net_tab_rects.append((tab_rect, n.id))
            x += tab_w + 4

    def draw_content(
        self, surface: pygame.Surface, rect: pygame.Rect, world: "World",
    ) -> None:
        selected = self._pick_network(world)
        is_auto = selected.worker_auto if selected is not None else True

        # Right-aligned Edit Hierarchy button.
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
            surface, UI_ACCENT, self._edit_btn_rect,
            width=2, border_radius=4,
        )
        label = Fonts.body().render("Edit Hierarchy", True, UI_TEXT)
        surface.blit(label, (
            self._edit_btn_rect.centerx - label.get_width() // 2,
            self._edit_btn_rect.centery - label.get_height() // 2,
        ))

        # Auto toggle button left of Edit.
        _AUTO_BTN_W = 70
        self._auto_btn_rect = pygame.Rect(
            self._edit_btn_rect.left - _AUTO_BTN_W - 8,
            rect.y + (rect.h - _EDIT_BTN_H) // 2,
            _AUTO_BTN_W, _EDIT_BTN_H,
        )
        _GREEN = (40, 120, 60)
        _GREEN_HI = (60, 150, 80)
        _RED = (120, 40, 40)
        _RED_HI = (150, 60, 60)
        auto_base = _GREEN if is_auto else _RED
        auto_hi = _GREEN_HI if is_auto else _RED_HI
        auto_bg = pygame.Surface(
            (self._auto_btn_rect.w, self._auto_btn_rect.h), pygame.SRCALPHA,
        )
        auto_bg.fill((*(auto_hi if self._auto_hover else auto_base), 235))
        surface.blit(auto_bg, self._auto_btn_rect.topleft)
        pygame.draw.rect(
            surface, UI_BORDER, self._auto_btn_rect,
            width=2, border_radius=4,
        )
        auto_label = Fonts.body().render("Auto", True, UI_TEXT)
        surface.blit(auto_label, (
            self._auto_btn_rect.centerx - auto_label.get_width() // 2,
            self._auto_btn_rect.centery - auto_label.get_height() // 2,
        ))

        # Network tab strip (if there are multiple networks).
        tabs_rect = pygame.Rect(
            rect.x + 6, rect.y + 4,
            self._auto_btn_rect.left - rect.x - 12, 22,
        )
        tabs_h = 0
        if len(world.networks) > 1:
            self._draw_network_tabs(surface, tabs_rect, world, selected)
            tabs_h = tabs_rect.h + 4
        else:
            self._net_tab_rects = []

        # Tier list (left side).
        list_rect = pygame.Rect(
            rect.x + 6, rect.y + 6 + tabs_h,
            self._edit_btn_rect.left - rect.x - 12,
            rect.h - 12 - tabs_h,
        )
        tiers = selected.priority if selected is not None else []
        if not tiers:
            msg = Fonts.body().render(
                "No worker buildings placed yet.", True, UI_MUTED,
            )
            surface.blit(msg, (list_rect.x + 4, list_rect.y + 4))
            return

        # Draw tiers top→bottom, clipped to list_rect.
        prev_clip = surface.get_clip()
        surface.set_clip(list_rect)
        y = list_rect.y - self._scroll
        # Logistics summary row (read-only in the tab).
        if selected is not None:
            active = sum(
                1 for p in world.population.people
                if p.is_logistics and p.home is not None
                and selected.contains(p.home)
            )
            log_surf = Fonts.small().render(
                f"Logistics: {active}/{selected.logistics_target}",
                True, UI_ACCENT,
            )
            surface.blit(log_surf, (list_rect.x + 2, y + 2))
            y += log_surf.get_height() + 4
        for ti, tier in enumerate(tiers):
            label_surf = Fonts.small().render(
                f"Tier {ti + 1}", True, UI_ACCENT,
            )
            surface.blit(label_surf, (list_rect.x + 2, y + 4))
            x = list_rect.x + _TIER_LABEL_W
            for b in tier:
                card_rect = pygame.Rect(x, y, _CARD_W, _CARD_H - 12)
                _draw_building_card(surface, card_rect, b)
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
            if self._auto_btn_rect.collidepoint(event.pos):
                if self.on_toggle_auto is not None:
                    self.on_toggle_auto(self._selected_net_id)
                return True
            if self._edit_btn_rect.collidepoint(event.pos):
                if self.on_open_edit is not None:
                    self.on_open_edit()
                return True
            for tab_rect, net_id in self._net_tab_rects:
                if tab_rect.collidepoint(event.pos):
                    self._selected_net_id = net_id
                    return True
        return False


# ── Edit Hierarchy drag-drop overlay ─────────────────────────────

_OVERLAY_TITLE_H = 44
_OVERLAY_PAD = 20
_ROW_H = 64          # one tier row (minimum height)
_ROW_LABEL_W = 70
_ROW_V_GAP = 8
_OV_CARD_W = 132
_OV_CARD_H = 48
_OV_CARD_GAP = 8
_OV_CARD_GAP_Y = 6   # vertical gap between wrapped card rows
_DONE_BTN_W = 110
_DONE_BTN_H = 32
_OV_AUTO_W = 110     # worker-overlay Auto button width
_GREEN: tuple[int, int, int] = (60, 145, 75)
_GREEN_HI: tuple[int, int, int] = (75, 175, 90)
_RED: tuple[int, int, int] = (165, 70, 70)
_RED_HI: tuple[int, int, int] = (200, 90, 90)
_EMPTY_ROW_HINT = "Drop here to create a new tier"


class WorkerPriorityOverlay(Panel):
    """Fullscreen drag-and-drop editor for worker-priority tiers."""

    def __init__(self) -> None:
        super().__init__()
        self.visible: bool = False
        self.world: "World | None" = None
        # Active drag state.  Either a card OR a whole tier is being
        # dragged at any given time.
        self._drag_building: Building | None = None
        self._drag_mouse_offset: tuple[int, int] = (0, 0)
        self._drag_origin_tier: int = -1
        self._drag_origin_index: int = -1
        # Tier-drag: when set to a tier index, dragging the row label
        # moves the whole tier (including all its cards) to a new
        # vertical position in the priority list.
        self._drag_tier: int = -1
        self._mouse_pos: tuple[int, int] = (0, 0)
        # Hit-test rects (rebuilt every draw).
        self._card_rects: list[
            tuple[pygame.Rect, int, int, Building]
        ] = []  # (rect, tier_idx, card_idx, building)
        self._row_rects: list[tuple[pygame.Rect, int]] = []  # (rect, tier_idx)
        # Per-tier label rect (drag handle for tier-level reorder).
        self._tier_label_rects: list[tuple[pygame.Rect, int]] = []
        self._empty_row_rect: pygame.Rect = pygame.Rect(0, 0, 0, 0)
        self._done_rect: pygame.Rect = pygame.Rect(0, 0, 0, 0)
        self._auto_rect: pygame.Rect = pygame.Rect(0, 0, 0, 0)
        self._scroll: int = 0
        # Per-network tab bar state.
        self._selected_net_id: int | None = None
        self._net_tab_rects: list[tuple[pygame.Rect, int]] = []
        # Logistics +/- buttons for the currently displayed network.
        self._log_minus_rect: pygame.Rect = pygame.Rect(0, 0, 0, 0)
        self._log_plus_rect: pygame.Rect = pygame.Rect(0, 0, 0, 0)
        # Callback for the in-overlay Auto button.  Wired by
        # ``Game.__init__`` to ``_on_toggle_worker_auto`` so toggling
        # auto here behaves identically to toggling it from the
        # bottom-bar tab.
        self.on_toggle_auto: "callable | None" = None

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
        # Centered panel covering most of the screen.
        w = min(screen_w - 80, 1200)
        h = min(screen_h - 80, 720)
        x = (screen_w - w) // 2
        y = (screen_h - h) // 2
        self.rect = pygame.Rect(x, y, w, h)

    def draw(self, surface: pygame.Surface, world: "World") -> None:
        if not self.visible:
            return
        self.world = world
        # Dim background.
        dim = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
        dim.fill((0, 0, 0, 170))
        surface.blit(dim, (0, 0))

        draw_panel_bg(surface, self.rect, accent_edge="top")

        # Title bar.
        title_rect = pygame.Rect(
            self.rect.x, self.rect.y, self.rect.w, _OVERLAY_TITLE_H,
        )
        title_surf = Fonts.title().render(
            "Edit Worker Priority", True, UI_TEXT,
        )
        surface.blit(title_surf, (
            title_rect.x + _OVERLAY_PAD,
            title_rect.centery - title_surf.get_height() // 2,
        ))
        hint_text = (
            "Auto mode active — disable Auto to customise."
            if (self._current_network() or None) is not None
            and self._current_network().worker_auto
            else "Drag cards between tiers.  Higher tier = higher priority."
        )
        hint = Fonts.small().render(hint_text, True, UI_MUTED)
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

        # Auto on/off toggle (mirrors the bottom-bar button so the
        # user doesn't have to close the overlay to flip auto mode).
        current_net = self._current_network()
        self._auto_rect = pygame.Rect(
            self._done_rect.left - _OV_AUTO_W - 8,
            title_rect.centery - _DONE_BTN_H // 2,
            _OV_AUTO_W, _DONE_BTN_H,
        )
        if current_net is not None:
            on = current_net.worker_auto
            label = "Auto: ON" if on else "Auto: OFF"
            base = _GREEN if on else _RED
            hi = _GREEN_HI if on else _RED_HI
            hov = self._auto_rect.collidepoint(self._mouse_pos)
            ab = pygame.Surface(
                (self._auto_rect.w, self._auto_rect.h), pygame.SRCALPHA,
            )
            ab.fill((*(hi if hov else base), 235))
            surface.blit(ab, self._auto_rect.topleft)
            pygame.draw.rect(
                surface, UI_BORDER, self._auto_rect,
                width=2, border_radius=4,
            )
            txt = Fonts.body().render(label, True, UI_TEXT)
            surface.blit(txt, (
                self._auto_rect.centerx - txt.get_width() // 2,
                self._auto_rect.centery - txt.get_height() // 2,
            ))

        # Scrollable tier area.
        area = pygame.Rect(
            self.rect.x + _OVERLAY_PAD,
            self.rect.y + _OVERLAY_TITLE_H + _OVERLAY_PAD // 2,
            self.rect.w - _OVERLAY_PAD * 2,
            self.rect.bottom - self.rect.y
            - _OVERLAY_TITLE_H - _OVERLAY_PAD * 2,
        )

        # Network tab strip just inside the area (only shown if more
        # than one network exists).
        self._net_tab_rects = []
        tabs_h = 0
        if len(world.networks) > 1:
            tabs_rect = pygame.Rect(area.x, area.y, area.w, 28)
            self._draw_network_tabs(surface, tabs_rect, world, current_net)
            tabs_h = tabs_rect.h + 6
        area = pygame.Rect(
            area.x, area.y + tabs_h,
            area.w, area.h - tabs_h,
        )

        prev_clip = surface.get_clip()
        surface.set_clip(area)

        tiers = current_net.priority if current_net is not None else []
        self._card_rects = []
        self._row_rects = []
        self._tier_label_rects = []

        y = area.y - self._scroll

        # Always-present Logistics row at the top of the list.
        if current_net is not None:
            log_rect = pygame.Rect(area.x, y, area.w, _LOG_ROW_H)
            self._draw_logistics_row(surface, log_rect, current_net, world)
            y += _LOG_ROW_H + _ROW_V_GAP
        else:
            self._log_minus_rect = pygame.Rect(0, 0, 0, 0)
            self._log_plus_rect = pygame.Rect(0, 0, 0, 0)

        for ti, tier in enumerate(tiers):
            # Skip drawing the tier we're dragging in its original slot.
            if ti == self._drag_tier:
                continue
            row_h = self._tier_row_height(tier, area.w)
            row_rect = pygame.Rect(area.x, y, area.w, row_h)
            self._draw_row(surface, row_rect, tier, ti)
            self._row_rects.append((row_rect, ti))
            y += row_h + _ROW_V_GAP

        # Always-present empty row at the bottom for "create new tier".
        empty_rect = pygame.Rect(area.x, y, area.w, _ROW_H)
        self._empty_row_rect = empty_rect
        self._draw_empty_row(surface, empty_rect)

        surface.set_clip(prev_clip)

        # Drag ghost on top of everything.
        if self._drag_tier >= 0 and current_net is not None:
            tiers_now = current_net.priority
            if 0 <= self._drag_tier < len(tiers_now):
                tier = tiers_now[self._drag_tier]
                row_h = self._tier_row_height(tier, area.w)
                gx, gy = self._mouse_pos
                ox, oy = self._drag_mouse_offset
                ghost_rect = pygame.Rect(
                    area.x, gy - oy, area.w, row_h,
                )
                ghost_surf = pygame.Surface(
                    (ghost_rect.w, ghost_rect.h), pygame.SRCALPHA,
                )
                ghost_surf.fill((40, 60, 80, 200))
                surface.blit(ghost_surf, ghost_rect.topleft)
                pygame.draw.rect(
                    surface, UI_ACCENT, ghost_rect,
                    width=2, border_radius=4,
                )
                lbl = Fonts.body().render(
                    f"Tier {self._drag_tier + 1}", True, UI_ACCENT,
                )
                surface.blit(lbl, (
                    ghost_rect.x + 8,
                    ghost_rect.y + 6,
                ))
        elif self._drag_building is not None:
            gx, gy = self._mouse_pos
            ox, oy = self._drag_mouse_offset
            ghost_rect = pygame.Rect(
                gx - ox, gy - oy, _OV_CARD_W, _OV_CARD_H,
            )
            _draw_building_card(
                surface, ghost_rect, self._drag_building,
                ghost=True, highlighted=True,
            )

    def _draw_network_tabs(
        self, surface: pygame.Surface, rect: pygame.Rect, world: "World",
        selected: "Network | None",
    ) -> None:
        self._net_tab_rects = []
        x = rect.x
        for n in world.networks:
            label = Fonts.body().render(n.name, True, UI_TEXT)
            pad_x = 14
            tab_w = label.get_width() + pad_x * 2
            tab_rect = pygame.Rect(x, rect.y, tab_w, rect.h)
            bg = UI_TAB_ACTIVE if selected is n else UI_TAB_INACTIVE
            bg_surf = pygame.Surface(
                (tab_rect.w, tab_rect.h), pygame.SRCALPHA,
            )
            bg_surf.fill(bg)
            surface.blit(bg_surf, tab_rect.topleft)
            pygame.draw.rect(
                surface, UI_ACCENT if selected is n else UI_BORDER,
                tab_rect, width=2, border_radius=4,
            )
            surface.blit(label, (
                tab_rect.centerx - label.get_width() // 2,
                tab_rect.centery - label.get_height() // 2,
            ))
            self._net_tab_rects.append((tab_rect, n.id))
            x += tab_w + 6

    def _tier_row_height(
        self, tier: list[Building], row_w: int,
    ) -> int:
        """Compute the vertical height needed for *tier* given the
        wrap width.  The row contains an integer number of card rows
        with vertical gaps between them."""
        max_cards_w = max(1, row_w - _ROW_LABEL_W - 8)
        per_card = _OV_CARD_W + _OV_CARD_GAP
        n = max(1, len(tier))
        per_row = max(1, (max_cards_w + _OV_CARD_GAP) // per_card)
        rows = (n + per_row - 1) // per_row
        rows = max(1, rows)
        cards_h = rows * _OV_CARD_H + (rows - 1) * _OV_CARD_GAP_Y
        return max(_ROW_H, cards_h + 16)  # +pad above and below

    def _draw_row(
        self, surface: pygame.Surface, rect: pygame.Rect,
        tier: list[Building], tier_idx: int,
    ) -> None:
        bg = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
        bg.fill((24, 32, 42, 180))
        surface.blit(bg, rect.topleft)
        pygame.draw.rect(surface, UI_BORDER, rect, width=1, border_radius=4)

        # Tier label is also the drag handle for tier reorder.
        label = Fonts.body().render(
            f"Tier {tier_idx + 1}", True, UI_ACCENT,
        )
        label_rect = pygame.Rect(
            rect.x + 4, rect.y + 4, _ROW_LABEL_W - 8, rect.h - 8,
        )
        surface.blit(label, (
            label_rect.x + 4,
            label_rect.y + 4,
        ))
        # Faint grip dots beneath the label hint that it's draggable.
        for i in range(3):
            pygame.draw.circle(
                surface, UI_MUTED,
                (label_rect.x + 8 + i * 6, label_rect.y + label.get_height() + 12),
                2,
            )
        self._tier_label_rects.append((label_rect, tier_idx))

        # Wrap cards into multiple rows so they don't overflow.
        max_cards_w = max(1, rect.w - _ROW_LABEL_W - 8)
        per_card = _OV_CARD_W + _OV_CARD_GAP
        per_row = max(1, (max_cards_w + _OV_CARD_GAP) // per_card)

        cy = rect.y + 8
        for i, b in enumerate(tier):
            col = i % per_row
            row = i // per_row
            x = rect.x + _ROW_LABEL_W + col * per_card
            y = cy + row * (_OV_CARD_H + _OV_CARD_GAP_Y)
            # Skip drawing the card we're dragging in its original slot.
            if (b is self._drag_building
                    and tier_idx == self._drag_origin_tier
                    and i == self._drag_origin_index):
                continue
            card_rect = pygame.Rect(x, y, _OV_CARD_W, _OV_CARD_H)
            _draw_building_card(surface, card_rect, b)
            self._card_rects.append((card_rect, tier_idx, i, b))

    def _draw_empty_row(
        self, surface: pygame.Surface, rect: pygame.Rect,
    ) -> None:
        bg = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
        bg.fill((20, 28, 36, 140))
        surface.blit(bg, rect.topleft)
        pygame.draw.rect(
            surface, UI_BORDER, rect, width=1, border_radius=4,
        )
        # Dashed outline look via a second thinner rect.
        pygame.draw.rect(
            surface, UI_ACCENT, rect.inflate(-6, -6),
            width=1, border_radius=3,
        )
        hint = Fonts.small().render(_EMPTY_ROW_HINT, True, UI_MUTED)
        surface.blit(hint, (
            rect.centerx - hint.get_width() // 2,
            rect.centery - hint.get_height() // 2,
        ))

    def _draw_logistics_row(
        self, surface: pygame.Surface, rect: pygame.Rect,
        net: "Network", world: "World",
    ) -> None:
        """Draw the persistent Logistics row with +/- controls and
        record the click rects so handle_event can adjust the target."""
        bg = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
        bg.fill((30, 40, 52, 200))
        surface.blit(bg, rect.topleft)
        pygame.draw.rect(surface, UI_ACCENT, rect, width=1, border_radius=4)

        label = Fonts.body().render("Logistics", True, UI_TEXT)
        surface.blit(label, (
            rect.x + 12,
            rect.centery - label.get_height() // 2,
        ))

        # Count currently-assigned logistics workers in this network.
        active = 0
        for p in world.population.people:
            if not p.is_logistics or p.home is None:
                continue
            home_net = None
            for n in world.networks:
                if n.contains(p.home):
                    home_net = n
                    break
            if home_net is net:
                active += 1
        count_text = f"{active}/{net.logistics_target}"
        count_surf = Fonts.body().render(count_text, True, UI_TEXT)

        # Lay out -   count   + from right side.
        pad = 10
        right = rect.right - pad
        self._log_plus_rect = pygame.Rect(
            right - _LOG_BTN_W,
            rect.centery - _LOG_BTN_W // 2,
            _LOG_BTN_W, _LOG_BTN_W,
        )
        right = self._log_plus_rect.left - 8
        count_x = right - count_surf.get_width()
        surface.blit(count_surf, (
            count_x, rect.centery - count_surf.get_height() // 2,
        ))
        right = count_x - 8
        self._log_minus_rect = pygame.Rect(
            right - _LOG_BTN_W,
            rect.centery - _LOG_BTN_W // 2,
            _LOG_BTN_W, _LOG_BTN_W,
        )
        # Draw buttons.
        for r, glyph in (
            (self._log_minus_rect, "-"), (self._log_plus_rect, "+"),
        ):
            bg2 = pygame.Surface((r.w, r.h), pygame.SRCALPHA)
            hovered = r.collidepoint(self._mouse_pos)
            bg2.fill(UI_TAB_HOVER if hovered else UI_TAB_INACTIVE)
            surface.blit(bg2, r.topleft)
            pygame.draw.rect(surface, UI_ACCENT, r, width=2, border_radius=4)
            g = Fonts.title().render(glyph, True, UI_TEXT)
            surface.blit(g, (
                r.centerx - g.get_width() // 2,
                r.centery - g.get_height() // 2,
            ))

    # ── Events ───────────────────────────────────────────────────

    def handle_event(self, event: pygame.event.Event) -> bool:
        if not self.visible:
            return False
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            self._cancel_drag()
            self.visible = False
            return True
        if not hasattr(event, "pos"):
            return False

        if event.type == pygame.MOUSEMOTION:
            self._mouse_pos = event.pos
            return True

        if event.type == pygame.MOUSEWHEEL:
            # Wheel events don't have .pos but we still want to swallow
            # them when the overlay is visible to avoid camera zooming.
            self._scroll = max(0, self._scroll - event.y * 30)
            return True

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            self._mouse_pos = event.pos
            if self._done_rect.collidepoint(event.pos):
                self._cancel_drag()
                self.visible = False
                return True
            net = self._current_network()
            # Auto on/off button — always active so the player can flip
            # auto without leaving the overlay.
            if net is not None and self._auto_rect.collidepoint(event.pos):
                if self.on_toggle_auto is not None:
                    self.on_toggle_auto(self._selected_net_id)
                return True
            is_auto = net is not None and net.worker_auto
            # Logistics +/- buttons (disabled in auto mode).
            if net is not None and not is_auto:
                if self._log_minus_rect.collidepoint(event.pos):
                    net.logistics_target = max(0, net.logistics_target - 1)
                    return True
                if self._log_plus_rect.collidepoint(event.pos):
                    net.logistics_target += 1
                    return True
            # Network tab click → switch active network.
            for tab_rect, net_id in self._net_tab_rects:
                if tab_rect.collidepoint(event.pos):
                    self._selected_net_id = net_id
                    self._cancel_drag()
                    return True
            # Start drag if mouse is over a card (disabled in auto mode).
            if not is_auto:
                # Tier-label drag (whole tier reorder) takes precedence
                # over card drag because the label is on the left side
                # of the row, separate from card hit boxes.
                for label_rect, ti in self._tier_label_rects:
                    if label_rect.collidepoint(event.pos):
                        self._drag_tier = ti
                        self._drag_mouse_offset = (
                            event.pos[0] - label_rect.x,
                            event.pos[1] - label_rect.y,
                        )
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
            return True  # consume click inside overlay

        if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            self._mouse_pos = event.pos
            if self._drag_tier >= 0:
                self._drop_tier(event.pos)
            elif self._drag_building is not None:
                self._drop(event.pos)
            return True
        return False

    # ── Drag drop bookkeeping ────────────────────────────────────

    def _cancel_drag(self) -> None:
        self._drag_building = None
        self._drag_origin_tier = -1
        self._drag_origin_index = -1
        self._drag_tier = -1

    def _drop_tier(self, pos: tuple[int, int]) -> None:
        """Drop the tier currently being dragged at *pos* — reorder
        the network's priority list so the dragged tier moves before
        whatever row the cursor is over.  Drop on the empty row to
        move the tier to the bottom; drop outside any row to cancel."""
        if self.world is None or self._drag_tier < 0:
            return
        net = self._current_network()
        if net is None:
            self._drag_tier = -1
            return
        tiers = net.priority
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
            target_ti = len(tiers)  # move to the end
        if target_ti is None:
            self._drag_tier = -1
            return

        moving = tiers.pop(src)
        # Account for index shift when removing from before target.
        if target_ti > src:
            target_ti -= 1
        target_ti = max(0, min(len(tiers), target_ti))
        tiers.insert(target_ti, moving)
        # Drop empties just in case.
        net.priority = [t for t in tiers if t]
        self._drag_tier = -1

    def _drop(self, pos: tuple[int, int]) -> None:
        if self.world is None or self._drag_building is None:
            return
        net = self._current_network()
        if net is None:
            self._cancel_drag()
            return
        tiers = net.priority
        b = self._drag_building
        origin_ti = self._drag_origin_tier
        origin_ci = self._drag_origin_index

        # Decide target: a row, the empty row, or nothing (cancel).
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

        # Remove from origin tier.
        if 0 <= origin_ti < len(tiers):
            try:
                tiers[origin_ti].remove(b)
            except ValueError:
                pass
        # If new tier, append.
        if create_new:
            # Remove empty origin tier (if the drag emptied it).
            tiers[:] = [t for t in tiers if t]
            tiers.append([b])
            self._cancel_drag()
            return
        # Compute insertion index based on x position within the row.
        assert target_ti is not None
        row_rect = None
        for rect, ti in self._row_rects:
            if ti == target_ti:
                row_rect = rect
                break
        # target_ti may reference an index that shifted after removal.
        # After removal, indexing is unchanged (we use the original
        # tier_idx, and we only rebuild on next draw), so this is fine
        # as long as we clamp.
        target_ti_adj = target_ti
        # If target tier is now past the end (origin tier was removed),
        # clamp down.
        if target_ti_adj >= len(tiers):
            target_ti_adj = len(tiers) - 1
        # If origin tier became empty and was before target, it gets
        # pruned below — adjust index.
        target_tier = tiers[target_ti_adj]
        insert_idx = len(target_tier)
        if row_rect is not None:
            # Use x-position of mouse vs card centers.
            rel_x = pos[0] - (row_rect.x + _ROW_LABEL_W)
            slot = rel_x // (_OV_CARD_W + _OV_CARD_GAP)
            insert_idx = max(0, min(len(target_tier), int(slot)))
        target_tier.insert(insert_idx, b)
        # Prune any tiers that became empty from the origin removal.
        tiers[:] = [t for t in tiers if t]
        self._cancel_drag()


__all__ = [
    "WorkerPriorityOverlay",
    "WorkerPriorityTabContent",
]
