"""Clanker possession panel.

When the player clicks **Possess** on a rival faction's TRIBAL_CAMP,
the game records the chosen :class:`Clanker` and shows this read-only
panel along the right edge of the screen.  The panel is purely
diagnostic — it never lets the player issue commands to the AI; it
only surfaces what the clanker can see and the recent decisions it
has made, so the player can verify that the AI is behaving like a
real opponent (researching, expanding, crafting, growing population)
rather than just dropping random buildings.

The panel is fed a :class:`Clanker` reference at runtime via
``set_clanker``.  Setting it to ``None`` hides the panel.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Callable

import pygame

from compprog_pygame.games.hex_colony.buildings import (
    BUILDING_HOUSING,
    BuildingType,
)
from compprog_pygame.games.hex_colony.resources import Resource
from compprog_pygame.games.hex_colony.strings import (
    building_label,
    resource_name,
)
from compprog_pygame.games.hex_colony.ui import (
    Fonts,
    Panel,
    UI_ACCENT,
    UI_BAD,
    UI_BG,
    UI_BORDER,
    UI_MUTED,
    UI_OK,
    UI_TEXT,
    draw_panel_bg,
    render_text_clipped,
)
from compprog_pygame.games.hex_colony.ui_theme import wrap_text

if TYPE_CHECKING:
    from compprog_pygame.games.hex_colony.clankers import Clanker
    from compprog_pygame.games.hex_colony.world import World


_PANEL_W = 320
_PADDING = 12
_LINE_H = 20
_HEADER_H = 26
_BTN_H = 28
_TOP_MARGIN = 48
_BOTTOM_MARGIN = 44
_LOG_LINE_H = 18
_LOG_FEED_PORTION = 0.45  # fraction of panel height reserved for the log feed


class ClankerPossessionPanel(Panel):
    """Right-side read-only summary of a possessed clanker."""

    def __init__(self) -> None:
        super().__init__()
        self.clanker: "Clanker | None" = None
        self.on_unpossess: Callable[[], None] | None = None
        self.on_view_all_logs: Callable[[], None] | None = None
        self._unpossess_btn: pygame.Rect | None = None
        self._view_all_btn: pygame.Rect | None = None
        self._screen_w = 0
        self._screen_h = 0
        self.visible = False

    # ── External setters ─────────────────────────────────────────

    def set_clanker(self, clanker: "Clanker | None") -> None:
        self.clanker = clanker
        self.visible = clanker is not None

    # ── Panel API ────────────────────────────────────────────────

    def layout(self, screen_w: int, screen_h: int) -> None:
        self._screen_w = screen_w
        self._screen_h = screen_h
        h = max(200, screen_h - _TOP_MARGIN - _BOTTOM_MARGIN)
        self.rect = pygame.Rect(
            screen_w - _PANEL_W - 10, _TOP_MARGIN, _PANEL_W, h,
        )

    def draw(self, surface: pygame.Surface, world: "World") -> None:
        if self.clanker is None:
            return
        # Re-layout in case the screen size changed.
        self.layout(self._screen_w or surface.get_width(),
                    self._screen_h or surface.get_height())
        draw_panel_bg(surface, self.rect, accent_edge="top")

        x = self.rect.x
        y = self.rect.y
        w = self.rect.w
        h = self.rect.h
        prev_clip = surface.get_clip()
        surface.set_clip(self.rect)

        cy = y + _PADDING

        # ── Header ──────────────────────────────────────────────
        title_text = f"Possessing: {self.clanker.faction_id}"
        title_surf = Fonts.title().render(title_text, True, UI_ACCENT)
        surface.blit(title_surf, (x + _PADDING, cy))
        cy += 34

        # Unpossess button.
        btn_rect = pygame.Rect(
            x + w - _PADDING - 100, y + _PADDING, 100, _BTN_H,
        )
        pygame.draw.rect(surface, UI_BG, btn_rect, border_radius=4)
        pygame.draw.rect(surface, UI_BORDER, btn_rect, width=1, border_radius=4)
        un_surf = Fonts.small().render("Unpossess", True, UI_TEXT)
        surface.blit(
            un_surf,
            (btn_rect.centerx - un_surf.get_width() // 2,
             btn_rect.centery - un_surf.get_height() // 2),
        )
        self._unpossess_btn = btn_rect

        # Compute how much vertical space the log feed gets.
        feed_h = int((h - (cy - y)) * _LOG_FEED_PORTION)
        body_h = h - (cy - y) - feed_h - _PADDING

        body_rect = pygame.Rect(x, cy, w, body_h)
        feed_rect = pygame.Rect(
            x, cy + body_h, w, feed_h,
        )

        self._draw_body(surface, body_rect, world)
        self._draw_feed(surface, feed_rect, world)

        surface.set_clip(prev_clip)

    # ── Sections ─────────────────────────────────────────────────

    def _draw_body(
        self, surface: pygame.Surface, rect: pygame.Rect, world: "World",
    ) -> None:
        assert self.clanker is not None
        clanker = self.clanker
        colony = clanker.colony
        x, y, w, _ = rect

        prev_clip = surface.get_clip()
        surface.set_clip(rect)
        cy = y

        def header(text: str) -> None:
            nonlocal cy
            surf = Fonts.body().render(text, True, UI_ACCENT)
            surface.blit(surf, (x + _PADDING, cy))
            cy += _HEADER_H

        def line(text: str, color=UI_TEXT) -> None:
            nonlocal cy
            surf = render_text_clipped(
                Fonts.small(), text, color, w - _PADDING * 2,
            )
            surface.blit(surf, (x + _PADDING, cy))
            cy += _LINE_H

        # ── Tier / research progress ───────────────────────────
        tier = colony.tier_tracker
        from compprog_pygame.games.hex_colony.tech_tree import TIERS
        tier_name = (
            TIERS[tier.current_tier].name
            if 0 <= tier.current_tier < len(TIERS) else "?"
        )
        header("Progression")
        line(f"Tier: {tier.current_tier}  ({tier_name})")
        tt = colony.tech_tree
        line(f"Tech researched: {tt.researched_count}", UI_MUTED)
        if tt.current_research is not None:
            from compprog_pygame.games.hex_colony.tech_tree import TECH_NODES
            node = TECH_NODES.get(tt.current_research)
            cur_name = node.name if node is not None else tt.current_research
            line(f"Researching: {cur_name}", UI_OK)
        else:
            line("Researching: \u2014", UI_MUTED)
        cy += 6

        # ── Population & workers ───────────────────────────────
        my_pop = world.faction_population_count(clanker.faction_id)
        my_cap = sum(
            BUILDING_HOUSING.get(b.type, 0)
            for b in world.buildings.buildings
            if getattr(b, "faction", "SURVIVOR") == clanker.faction_id
        )
        # Worker / idle split.
        employed = 0
        idle = 0
        for p in world.population.people:
            home = getattr(p, "home", None)
            if home is None:
                continue
            if getattr(home, "faction", "SURVIVOR") != clanker.faction_id:
                continue
            if getattr(p, "workplace", None) is not None:
                employed += 1
            else:
                idle += 1
        header("Population")
        line(f"Colonists: {my_pop} / {my_cap}")
        line(f"  Employed: {employed}", UI_OK)
        line(f"  Idle: {idle}",
             UI_BAD if idle > 0 and employed == 0 else UI_MUTED)
        cy += 6

        # ── Networks ──────────────────────────────────────────
        nets = [n for n in world.networks
                if getattr(n, "faction", "SURVIVOR") == clanker.faction_id]
        own_b = [b for b in world.buildings.buildings
                 if getattr(b, "faction", "SURVIVOR") == clanker.faction_id]
        header("Logistics")
        line(f"Buildings: {len(own_b)}")
        line(f"Networks: {len(nets)}", UI_MUTED)
        if nets:
            largest = max(len(getattr(n, "buildings", [])) for n in nets)
            line(f"Largest network: {largest} buildings", UI_MUTED)
        cy += 6

        # ── Inventory (top resources) ─────────────────────────
        inv_items = [
            (r, colony.inventory[r]) for r in Resource
            if colony.inventory[r] > 0
        ]
        inv_items.sort(key=lambda t: -t[1])
        header("Inventory")
        if not inv_items:
            line("(empty)", UI_MUTED)
        else:
            for r, amt in inv_items[:10]:
                line(f"  {resource_name(r.name)}: {int(amt)}")
        cy += 6

        # ── Building stockpile ────────────────────────────────
        bi = colony.building_inventory
        bi_items = [
            (bt, bi[bt]) for bt in BuildingType if bi[bt] > 0
        ]
        bi_items.sort(key=lambda t: -t[1])
        header("Building stockpile")
        if not bi_items:
            line("(empty)", UI_MUTED)
        else:
            for bt, amt in bi_items[:8]:
                line(f"  {building_label(bt.name)}: {int(amt)}")

        surface.set_clip(prev_clip)

    def _draw_feed(
        self, surface: pygame.Surface, rect: pygame.Rect, world: "World",
    ) -> None:
        assert self.clanker is not None
        x, y, w, h = rect

        # Section background — slight tint to set the log apart.
        pygame.draw.rect(surface, UI_BG, rect)
        pygame.draw.line(
            surface, UI_BORDER, (x, y), (x + w, y), width=1,
        )

        prev_clip = surface.get_clip()
        surface.set_clip(rect)
        cy = y + 6

        title = Fonts.body().render("AI decisions", True, UI_ACCENT)
        surface.blit(title, (x + _PADDING, cy))

        # "View all" button on the right of the feed header — opens
        # a modal so the player can read every log entry, including
        # ones that don't fit in the side panel.
        view_all_label = Fonts.small().render("View all", True, UI_TEXT)
        btn_w = view_all_label.get_width() + 16
        btn_h = view_all_label.get_height() + 6
        view_btn = pygame.Rect(
            x + w - _PADDING - btn_w, cy - 1, btn_w, btn_h,
        )
        pygame.draw.rect(surface, UI_BG, view_btn, border_radius=4)
        pygame.draw.rect(surface, UI_BORDER, view_btn, width=1, border_radius=4)
        surface.blit(view_all_label, (
            view_btn.centerx - view_all_label.get_width() // 2,
            view_btn.centery - view_all_label.get_height() // 2,
        ))
        self._view_all_btn = view_btn

        cy += 24

        log = list(self.clanker.log)
        # Show newest last so the feed reads top \u2192 bottom oldest \u2192 newest,
        # but trim from the front to fit the available space.
        max_lines = max(1, (y + h - cy) // _LOG_LINE_H)
        if len(log) > max_lines:
            log = log[-max_lines:]
        if not log:
            line_surf = Fonts.small().render(
                "(no decisions yet)", True, UI_MUTED,
            )
            surface.blit(line_surf, (x + _PADDING, cy))
        else:
            for sim_t, msg in log:
                ts = f"[{int(sim_t):4d}s]" if sim_t >= 0 else "[ \u2014  ]"
                text = f"{ts} {msg}"
                line_surf = render_text_clipped(
                    Fonts.small(), text, UI_TEXT, w - _PADDING * 2,
                )
                surface.blit(line_surf, (x + _PADDING, cy))
                cy += _LOG_LINE_H

        surface.set_clip(prev_clip)

    # ── Events ───────────────────────────────────────────────────

    def handle_event(self, event: pygame.event.Event) -> bool:
        if not self.visible or self.clanker is None:
            return False
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if (self._unpossess_btn is not None
                    and self._unpossess_btn.collidepoint(event.pos)):
                if self.on_unpossess is not None:
                    self.on_unpossess()
                return True
            if (self._view_all_btn is not None
                    and self._view_all_btn.collidepoint(event.pos)):
                if self.on_view_all_logs is not None:
                    self.on_view_all_logs()
                return True
            # Swallow clicks inside the panel so the world doesn't
            # also react.
            if self.rect.collidepoint(event.pos):
                return True
        elif hasattr(event, "pos") and self.rect.collidepoint(event.pos):
            return True
        return False


# ═══════════════════════════════════════════════════════════════════
#  Full log overlay (modal popup)
# ═══════════════════════════════════════════════════════════════════


class ClankerLogOverlay(Panel):
    """Modal popup that shows the *entire* possessed clanker log.

    Word-wraps each entry, supports mouse-wheel scroll, and dims the
    rest of the screen.  Read-only — closes via the X button or by
    pressing Escape.
    """

    _MARGIN = 80
    _ENTRY_PAD = 6
    _SCROLL_STEP = 40

    def __init__(self) -> None:
        super().__init__()
        self.clanker: "Clanker | None" = None
        self.on_close: Callable[[], None] | None = None
        self.visible = False
        self._screen_w = 0
        self._screen_h = 0
        self._scroll = 0
        self._content_h = 0
        self._close_btn: pygame.Rect | None = None

    def open_for(self, clanker: "Clanker | None") -> None:
        self.clanker = clanker
        self.visible = clanker is not None
        self._scroll = 0

    def layout(self, screen_w: int, screen_h: int) -> None:
        self._screen_w = screen_w
        self._screen_h = screen_h
        self.rect = pygame.Rect(
            self._MARGIN, self._MARGIN,
            screen_w - self._MARGIN * 2,
            screen_h - self._MARGIN * 2,
        )

    def draw(self, surface: pygame.Surface, world: "World") -> None:
        if not self.visible or self.clanker is None:
            return
        self.layout(surface.get_width(), surface.get_height())

        # Dim the rest of the screen.
        dim = pygame.Surface(
            (surface.get_width(), surface.get_height()), pygame.SRCALPHA,
        )
        dim.fill((0, 0, 0, 160))
        surface.blit(dim, (0, 0))

        # Modal background.
        draw_panel_bg(surface, self.rect, accent_edge="top")

        x = self.rect.x
        y = self.rect.y
        w = self.rect.w
        h = self.rect.h

        # Title.
        title = Fonts.title().render(
            f"AI decision log — {self.clanker.faction_id}",
            True, UI_ACCENT,
        )
        surface.blit(title, (x + _PADDING, y + _PADDING))

        # Close button (top-right).
        close_label = Fonts.body().render("Close", True, UI_TEXT)
        btn_w = close_label.get_width() + 24
        btn_h = close_label.get_height() + 8
        btn = pygame.Rect(
            x + w - _PADDING - btn_w, y + _PADDING, btn_w, btn_h,
        )
        pygame.draw.rect(surface, UI_BG, btn, border_radius=4)
        pygame.draw.rect(surface, UI_BORDER, btn, width=1, border_radius=4)
        surface.blit(close_label, (
            btn.centerx - close_label.get_width() // 2,
            btn.centery - close_label.get_height() // 2,
        ))
        self._close_btn = btn

        # Help line.
        help_surf = Fonts.small().render(
            "Scroll with mouse wheel · Esc to close",
            True, UI_MUTED,
        )
        surface.blit(help_surf, (x + _PADDING, y + _PADDING + 36))

        # Body region — clipped scrollable text.
        body_top = y + _PADDING + 64
        body = pygame.Rect(
            x + _PADDING, body_top,
            w - _PADDING * 2, h - (body_top - y) - _PADDING,
        )
        prev_clip = surface.get_clip()
        surface.set_clip(body)

        font = Fonts.small()
        line_h = font.get_height() + 2
        cy = body.y - self._scroll
        text_w = body.w

        log = list(self.clanker.log)
        if not log:
            empty = font.render("(no decisions yet)", True, UI_MUTED)
            surface.blit(empty, (body.x, body.y))
            self._content_h = line_h
        else:
            total = 0
            for sim_t, msg in log:
                ts = f"[{int(sim_t):5d}s] "
                ts_surf = font.render(ts, True, UI_MUTED)
                ts_w = ts_surf.get_width()
                wrapped = wrap_text(font, msg, max(40, text_w - ts_w))
                if not wrapped:
                    wrapped = [""]
                # Only blit the timestamp on the first wrapped line.
                surface.blit(ts_surf, (body.x, cy))
                first = True
                for ln in wrapped:
                    line_surf = font.render(ln, True, UI_TEXT)
                    surface.blit(
                        line_surf,
                        (body.x + (ts_w if first else ts_w), cy),
                    )
                    if not first:
                        # Subsequent lines get indented under the
                        # timestamp; nothing else to do.
                        pass
                    cy += line_h
                    first = False
                cy += self._ENTRY_PAD
                total += line_h * len(wrapped) + self._ENTRY_PAD
            self._content_h = total

        surface.set_clip(prev_clip)

        # Clamp scroll.
        max_scroll = max(0, self._content_h - body.h)
        if self._scroll > max_scroll:
            self._scroll = max_scroll

    def handle_event(self, event: pygame.event.Event) -> bool:
        if not self.visible:
            return False
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            if self.on_close is not None:
                self.on_close()
            return True
        if event.type == pygame.MOUSEBUTTONDOWN:
            if event.button == 1:
                if (self._close_btn is not None
                        and self._close_btn.collidepoint(event.pos)):
                    if self.on_close is not None:
                        self.on_close()
                    return True
                # Modal — swallow clicks elsewhere.
                return True
            if event.button == 4:
                self._scroll = max(0, self._scroll - self._SCROLL_STEP)
                return True
            if event.button == 5:
                self._scroll += self._SCROLL_STEP
                return True
        if event.type == pygame.MOUSEWHEEL:
            self._scroll = max(0, self._scroll - event.y * self._SCROLL_STEP)
            return True
        # Modal overlay — eat any other events too so they don't
        # leak through to the world.
        if hasattr(event, "pos"):
            return True
        return False
