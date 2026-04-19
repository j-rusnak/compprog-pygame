"""Tech tree popup overlay — full-screen visual tech tree.

Opened via the Research Center's "Open Tech Tree" button.  Shows a
node graph with connecting lines, coloured by status (researched /
available / locked).

Nodes are auto-sized to the overlay; the viewport is scrollable with
the mouse wheel (or middle-click drag) when the graph overflows.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pygame

from compprog_pygame.games.hex_colony.tech_tree import TECH_NODES
from compprog_pygame.games.hex_colony.resource_icons import get_resource_icon
from compprog_pygame.games.hex_colony.ui import (
    Fonts,
    Panel,
    RESOURCE_COLORS,
    RESOURCE_ICONS,
    UI_ACCENT,
    UI_BORDER,
    UI_MUTED,
    UI_OVERLAY,
    UI_TEXT,
    draw_button,
    draw_titled_panel,
    render_text_clipped,
    set_tooltip,
)

if TYPE_CHECKING:
    from compprog_pygame.games.hex_colony.tech_tree import TechTree
    from compprog_pygame.games.hex_colony.world import World


_NODE_W = 200
_NODE_H = 116
_NODE_GAP_X = 56
_NODE_GAP_Y = 40
_GRAPH_MARGIN = 40

_COL_RESEARCHED = (60, 160, 80)
_COL_AVAILABLE = (70, 130, 200)
_COL_LOCKED = (80, 80, 90)
_COL_ACTIVE = (220, 180, 50)


class TechTreeOverlay(Panel):
    """Full-screen overlay showing the tech tree graph."""

    def __init__(self) -> None:
        super().__init__()
        self.visible = False
        self.tech_tree: TechTree | None = None
        self._screen_w = 0
        self._screen_h = 0
        self._node_rects: dict[str, pygame.Rect] = {}
        self._close_rect = pygame.Rect(0, 0, 0, 0)
        self._viewport: pygame.Rect = pygame.Rect(0, 0, 0, 0)
        self._scroll_x: int = 0
        self._scroll_y: int = 0
        self._dragging: bool = False
        self._drag_last: tuple[int, int] = (0, 0)
        self._graph_size: tuple[int, int] = (0, 0)
        self.on_close: "callable | None" = None

    def layout(self, screen_w: int, screen_h: int) -> None:
        self._screen_w = screen_w
        self._screen_h = screen_h
        self.rect = pygame.Rect(0, 0, screen_w, screen_h)

    def draw(self, surface: pygame.Surface, world: World) -> None:
        if not self.visible or self.tech_tree is None:
            return

        sw, sh = self._screen_w, self._screen_h
        overlay = pygame.Surface((sw, sh), pygame.SRCALPHA)
        overlay.fill(UI_OVERLAY)
        surface.blit(overlay, (0, 0))

        margin = 40
        panel = pygame.Rect(
            margin, margin, sw - margin * 2, sh - margin * 2,
        )
        content_y = draw_titled_panel(surface, panel, "Technology Tree")

        # Close button
        close_sz = 32
        self._close_rect = pygame.Rect(
            panel.right - close_sz - 12, panel.top + 12,
            close_sz, close_sz,
        )
        from compprog_pygame.games.hex_colony.ui_advanced_stats import (
            _draw_close_button,
        )
        _draw_close_button(
            surface, self._close_rect,
            hover=self._close_rect.collidepoint(pygame.mouse.get_pos()),
        )

        # Active research banner
        banner_y = content_y
        tt = self.tech_tree
        if tt.current_research is not None:
            node = TECH_NODES.get(tt.current_research)
            if node is not None:
                pct = int(tt.research_progress / node.time * 100)
                banner = Fonts.body().render(
                    f"Researching: {node.name} ({pct}%)",
                    True, _COL_ACTIVE,
                )
                surface.blit(banner, (panel.x + 20, banner_y))
                banner_y += banner.get_height() + 4

        # Viewport for the scrollable graph
        self._viewport = pygame.Rect(
            panel.x + 8, banner_y + 8,
            panel.w - 16, panel.bottom - banner_y - 20,
        )

        # Compute full graph size
        nodes = list(TECH_NODES.values())
        if nodes:
            max_col = max(n.position[0] for n in nodes)
            max_row = max(n.position[1] for n in nodes)
        else:
            max_col = max_row = 0
        graph_w = (
            (max_col + 1) * _NODE_W + max_col * _NODE_GAP_X + _GRAPH_MARGIN * 2
        )
        graph_h = (
            (max_row + 1) * _NODE_H + max_row * _NODE_GAP_Y + _GRAPH_MARGIN * 2
        )
        self._graph_size = (graph_w, graph_h)

        # Clamp scroll
        max_sx = max(0, graph_w - self._viewport.w)
        max_sy = max(0, graph_h - self._viewport.h)
        self._scroll_x = max(0, min(self._scroll_x, max_sx))
        self._scroll_y = max(0, min(self._scroll_y, max_sy))

        # Draw graph into viewport with clipping
        prev_clip = surface.get_clip()
        surface.set_clip(self._viewport)

        origin_x = self._viewport.x + _GRAPH_MARGIN - self._scroll_x
        origin_y = self._viewport.y + _GRAPH_MARGIN - self._scroll_y

        def node_pos(n) -> tuple[int, int]:
            return (
                origin_x + n.position[0] * (_NODE_W + _NODE_GAP_X),
                origin_y + n.position[1] * (_NODE_H + _NODE_GAP_Y),
            )

        # Connecting lines
        for node in nodes:
            nx, ny = node_pos(node)
            for prereq_key in node.prerequisites:
                prereq = TECH_NODES.get(prereq_key)
                if prereq is None:
                    continue
                px, py = node_pos(prereq)
                line_col = (
                    _COL_RESEARCHED
                    if prereq_key in tt.researched else UI_BORDER
                )
                pygame.draw.line(
                    surface, line_col,
                    (px + _NODE_W // 2, py + _NODE_H),
                    (nx + _NODE_W // 2, ny), 2,
                )

        self._node_rects = {}
        for node in nodes:
            nx, ny = node_pos(node)
            node_rect = pygame.Rect(nx, ny, _NODE_W, _NODE_H)
            self._node_rects[node.key] = node_rect

            if node.key in tt.researched:
                bg_col = _COL_RESEARCHED
                status = "Researched"
            elif node.key == tt.current_research:
                bg_col = _COL_ACTIVE
                pct = int(tt.research_progress / node.time * 100)
                status = f"In Progress ({pct}%)"
            elif tt.can_research(node.key):
                bg_col = _COL_AVAILABLE
                status = "Available"
            else:
                bg_col = _COL_LOCKED
                # When a node has multiple prerequisites and only some
                # are met, surface which ones are still missing so the
                # player can see at a glance why they can't research it
                # yet (rather than guessing from the connecting lines).
                missing = [
                    p for p in node.prerequisites
                    if p not in tt.researched
                ]
                if 0 < len(missing) < len(node.prerequisites):
                    miss_names = ", ".join(
                        TECH_NODES[m].name for m in missing
                        if m in TECH_NODES
                    )
                    status = f"Locked: needs {miss_names}"
                else:
                    status = "Locked"

            pygame.draw.rect(surface, bg_col, node_rect, border_radius=6)
            pygame.draw.rect(
                surface, UI_BORDER, node_rect, width=1, border_radius=6,
            )

            inner_w = _NODE_W - 12
            name = render_text_clipped(
                Fonts.body(), node.name, UI_TEXT, inner_w,
            )
            surface.blit(name, (nx + 6, ny + 4))
            stat = render_text_clipped(
                Fonts.small(), status, (220, 220, 220), inner_w,
            )
            surface.blit(stat, (nx + 6, ny + 26))

            # Cost + time
            cost_y = ny + _NODE_H - 22
            cost_x = nx + 6
            mx_pos, my_pos = pygame.mouse.get_pos()
            for res, amount in node.cost.items():
                col = RESOURCE_COLORS[res]
                icon_surf = get_resource_icon(res, 14)
                amt_surf = Fonts.small().render(f"{amount}", True, col)
                chunk_w = icon_surf.get_width() + 2 + amt_surf.get_width()
                if cost_x + chunk_w > nx + _NODE_W - 40:
                    break
                surface.blit(icon_surf, (cost_x, cost_y + 2))
                # Hover tooltip on the icon itself
                icon_rect = pygame.Rect(
                    cost_x, cost_y + 2,
                    icon_surf.get_width(), icon_surf.get_height(),
                )
                if (self._viewport.collidepoint((mx_pos, my_pos))
                        and icon_rect.collidepoint((mx_pos, my_pos))):
                    set_tooltip(res.name.replace("_", " ").title())
                surface.blit(amt_surf, (cost_x + icon_surf.get_width() + 2,
                                        cost_y))
                cost_x += chunk_w + 6
            time_surf = Fonts.small().render(
                f"{node.time:.0f}s", True, UI_MUTED,
            )
            surface.blit(time_surf, (
                nx + _NODE_W - time_surf.get_width() - 6, cost_y,
            ))

            # ── Unlocks row (building previews + hover-cost tooltip) ──
            if node.unlocks:
                unlock_y = ny + 46
                lbl_surf = Fonts.tiny().render("Unlocks:", True, UI_MUTED)
                surface.blit(lbl_surf, (nx + 6, unlock_y))
                ux = nx + 6 + lbl_surf.get_width() + 4
                uy = unlock_y - 2
                for unlock_bt in node.unlocks:
                    preview = _get_unlock_preview(unlock_bt, 18)
                    if preview is None:
                        # Fallback: render the building type's name letter.
                        text = unlock_bt.name[:2].title()
                        ph = Fonts.tiny().render(text, True, UI_TEXT)
                        preview_rect = pygame.Rect(ux, uy, 18, 18)
                        pygame.draw.rect(
                            surface, (45, 50, 60), preview_rect,
                            border_radius=3,
                        )
                        surface.blit(ph, (
                            preview_rect.centerx - ph.get_width() // 2,
                            preview_rect.centery - ph.get_height() // 2,
                        ))
                    else:
                        preview_rect = pygame.Rect(ux, uy, 18, 18)
                        surface.blit(preview, preview_rect.topleft)
                    if (self._viewport.collidepoint((mx_pos, my_pos))
                            and preview_rect.collidepoint(
                                (mx_pos, my_pos))):
                        set_tooltip(_unlock_tooltip(unlock_bt))
                    ux += 22
                    if ux > nx + _NODE_W - 22:
                        break

        surface.set_clip(prev_clip)

        # Scroll hint
        if max_sx > 0 or max_sy > 0:
            hint = Fonts.tiny().render(
                "Scroll wheel or middle-drag to pan", True, UI_MUTED,
            )
            surface.blit(hint, (
                panel.right - hint.get_width() - 16,
                panel.bottom - hint.get_height() - 10,
            ))

    def handle_event(self, event: pygame.event.Event) -> bool:
        if not self.visible or self.tech_tree is None:
            return False

        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            self._close()
            return True

        if event.type == pygame.MOUSEWHEEL:
            # Shift = horizontal, otherwise vertical.
            mods = pygame.key.get_mods()
            if mods & pygame.KMOD_SHIFT:
                self._scroll_x -= event.y * 40
            else:
                self._scroll_y -= event.y * 40
            return True

        if event.type == pygame.MOUSEBUTTONDOWN:
            if event.button == 1:
                if self._close_rect.collidepoint(event.pos):
                    self._close()
                    return True
                if self._viewport.collidepoint(event.pos):
                    for key, rect in self._node_rects.items():
                        if rect.collidepoint(event.pos):
                            if self.tech_tree.can_research(key):
                                self.tech_tree.start_research(key)
                            return True
                return True
            if event.button == 2:
                if self._viewport.collidepoint(event.pos):
                    self._dragging = True
                    self._drag_last = event.pos
                    return True

        if event.type == pygame.MOUSEBUTTONUP and event.button == 2:
            self._dragging = False
            return True

        if event.type == pygame.MOUSEMOTION and self._dragging:
            dx = event.pos[0] - self._drag_last[0]
            dy = event.pos[1] - self._drag_last[1]
            self._scroll_x -= dx
            self._scroll_y -= dy
            self._drag_last = event.pos
            return True

        if hasattr(event, "pos"):
            return True
        return False

    def _close(self) -> None:
        self.visible = False
        if self.on_close is not None:
            self.on_close()


# ── Helpers for the unlocks row ───────────────────────────────────

def _get_unlock_preview(btype, size: int):
    """Return a small preview surface for *btype*, or None if unavailable."""
    from compprog_pygame.games.hex_colony.ui_bottom_bar import (
        BuildingsTabContent,
    )
    return BuildingsTabContent._get_building_preview(btype, size)


def _unlock_tooltip(btype) -> str:
    """Return a one-line tooltip describing *btype* and its build cost."""
    from compprog_pygame.games.hex_colony.buildings import BUILDING_COSTS
    name = btype.name.replace("_", " ").title()
    cost = BUILDING_COSTS.get(btype)
    if cost is None or not cost.costs:
        return f"{name} — Free"
    parts = [
        f"{amt} {res.name.replace('_', ' ').title()}"
        for res, amt in cost.costs.items()
    ]
    return f"{name} — " + ", ".join(parts)
