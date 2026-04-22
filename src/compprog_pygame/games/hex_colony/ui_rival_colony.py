"""Diplomacy / rival-colony overlay panel.

Full-screen modal overlay that lets the player inspect the AI rival
("The Other Colony"), see their progression, watch the rocket-race
threat fill, and take diplomatic actions: send gifts, propose trades,
declare war, or sue for peace.

Toggled with the ``R`` key from :mod:`game`.  Reads its data from
``world.rivals[0]`` (the game currently spawns a single rival) and
delegates all state changes to :class:`RivalColony` methods so the
panel is purely a view + button layer.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pygame

from compprog_pygame.games.hex_colony.resources import Resource
from compprog_pygame.games.hex_colony import params
from compprog_pygame.games.hex_colony import strings as S
from compprog_pygame.games.hex_colony.ui import Panel
from compprog_pygame.games.hex_colony.ui_theme import (
    Fonts,
    UI_ACCENT,
    UI_BORDER,
    UI_BORDER_LIGHT,
    UI_MUTED,
    UI_OVERLAY,
    UI_TEXT,
    draw_panel_bg,
    draw_progress_bar,
)
from compprog_pygame.games.hex_colony.rival_colony import (
    DIPLOMACY_COLORS,
    DEFAULT_TRADES,
    DiplomacyState,
    GIFT_AMOUNTS,
    GIFT_RESOURCES,
    TradeOffer,
)

if TYPE_CHECKING:
    from compprog_pygame.games.hex_colony.world import World
    from compprog_pygame.games.hex_colony.rival_colony import RivalColony


# ── Layout constants ────────────────────────────────────────────

_PAD = 18
_LINE_H = 26
_BTN_H = 36
_BTN_W = 150
_PANEL_W = 880
_PANEL_H = 620
_BAR_H = 18

_STATE_LABELS: dict[DiplomacyState, str] = {
    DiplomacyState.HOSTILE: S.RIVAL_STATE_HOSTILE,
    DiplomacyState.TENSE:   S.RIVAL_STATE_TENSE,
    DiplomacyState.NEUTRAL: S.RIVAL_STATE_NEUTRAL,
    DiplomacyState.FRIENDLY: S.RIVAL_STATE_FRIENDLY,
    DiplomacyState.ALLIED:  S.RIVAL_STATE_ALLIED,
}

# Sub-page identifiers for the action area.
_VIEW_MAIN = "main"
_VIEW_GIFT = "gift"
_VIEW_TRADE = "trade"


def _draw_button(
    surface: pygame.Surface,
    rect: pygame.Rect,
    label: str,
    *,
    hovered: bool,
    enabled: bool = True,
    accent: tuple[int, int, int] = UI_ACCENT,
) -> None:
    """Draw a flat button with hover + disabled visual states."""
    if enabled:
        bg_col = (50, 60, 90, 240) if hovered else (32, 38, 56, 220)
        border = accent if hovered else UI_BORDER_LIGHT
        text_col = UI_TEXT
    else:
        bg_col = (28, 30, 40, 200)
        border = UI_BORDER
        text_col = UI_MUTED
    bg = pygame.Surface(rect.size, pygame.SRCALPHA)
    bg.fill(bg_col)
    surface.blit(bg, rect.topleft)
    pygame.draw.rect(surface, border, rect, width=2, border_radius=4)
    txt = Fonts.body().render(label, True, text_col)
    surface.blit(
        txt,
        (rect.centerx - txt.get_width() // 2,
         rect.centery - txt.get_height() // 2),
    )


class RivalColonyOverlay(Panel):
    """Full-screen diplomacy panel for the AI rival colony."""

    def __init__(self) -> None:
        super().__init__()
        self.visible = False
        self._mouse_pos: tuple[int, int] = (0, 0)
        self._view: str = _VIEW_MAIN
        # Hit-test rects rebuilt every draw; mapped to a callable that
        # mutates rival or view state when the click lands.
        self._hit_rects: list[tuple[pygame.Rect, callable]] = []
        # Stored notification target — set on first draw so button
        # callbacks can route player → rival messages there.
        self._notifications = None
        # Selected resource in the gift sub-view.
        self._gift_res: Resource | None = None

    # ── Public API ───────────────────────────────────────────────

    def toggle(self) -> None:
        self.visible = not self.visible
        if self.visible:
            self._view = _VIEW_MAIN
            self._gift_res = None

    def show(self) -> None:
        self.visible = True
        self._view = _VIEW_MAIN

    def hide(self) -> None:
        self.visible = False

    # ── Panel hooks ──────────────────────────────────────────────

    def layout(self, screen_w: int, screen_h: int) -> None:
        self.rect = pygame.Rect(0, 0, screen_w, screen_h)

    def draw(self, surface: pygame.Surface, world: "World") -> None:
        if not self.visible:
            return
        self._notifications = world.notifications
        self._hit_rects.clear()
        sw, sh = surface.get_size()

        # Dim background.
        overlay = pygame.Surface((sw, sh), pygame.SRCALPHA)
        overlay.fill(UI_OVERLAY)
        surface.blit(overlay, (0, 0))

        pw = min(_PANEL_W, sw - 60)
        ph = min(_PANEL_H, sh - 80)
        px = (sw - pw) // 2
        py = (sh - ph) // 2
        panel = pygame.Rect(px, py, pw, ph)
        draw_panel_bg(surface, panel, accent_edge="top")

        if not world.rivals:
            self._draw_no_rival(surface, panel)
            return

        rival = world.rivals[0]
        self._draw_header(surface, panel, rival)

        # Split body into left summary and right action area.
        body_top = panel.top + 70
        body_bot = panel.bottom - 50
        col_split = panel.left + int(pw * 0.55)
        left_rect = pygame.Rect(
            panel.left + _PAD, body_top,
            col_split - panel.left - _PAD * 2, body_bot - body_top,
        )
        right_rect = pygame.Rect(
            col_split, body_top,
            panel.right - col_split - _PAD, body_bot - body_top,
        )

        self._draw_summary(surface, left_rect, rival)
        if self._view == _VIEW_MAIN:
            self._draw_actions(surface, right_rect, world, rival)
        elif self._view == _VIEW_GIFT:
            self._draw_gift_view(surface, right_rect, world, rival)
        elif self._view == _VIEW_TRADE:
            self._draw_trade_view(surface, right_rect, world, rival)

        # Footer hint.
        hint_surf = Fonts.small().render(
            S.RIVAL_PANEL_DISMISS, True, UI_MUTED,
        )
        surface.blit(
            hint_surf,
            (panel.centerx - hint_surf.get_width() // 2,
             panel.bottom - hint_surf.get_height() - 14),
        )

    # ── Sub-renderers ────────────────────────────────────────────

    def _draw_no_rival(self, surface: pygame.Surface, panel: pygame.Rect) -> None:
        msg = Fonts.title().render(
            S.RIVAL_PANEL_TITLE, True, UI_TEXT,
        )
        surface.blit(
            msg,
            (panel.centerx - msg.get_width() // 2, panel.top + 30),
        )
        body = Fonts.body().render(
            "No rival colony exists in this world.",
            True, UI_MUTED,
        )
        surface.blit(
            body,
            (panel.centerx - body.get_width() // 2,
             panel.centery - body.get_height() // 2),
        )

    def _draw_header(
        self, surface: pygame.Surface, panel: pygame.Rect,
        rival: "RivalColony",
    ) -> None:
        title = Fonts.title().render(rival.name, True, UI_TEXT)
        surface.blit(title, (panel.left + _PAD, panel.top + 14))

        # Diplomacy state badge.
        state = rival.state
        badge_col = DIPLOMACY_COLORS[state]
        label = _STATE_LABELS[state]
        font = Fonts.label()
        surf = font.render(label, True, (10, 10, 20))
        bw, bh = surf.get_width() + 20, surf.get_height() + 6
        bx = panel.right - _PAD - bw
        by = panel.top + 22
        bg = pygame.Surface((bw, bh), pygame.SRCALPHA)
        bg.fill((*badge_col, 230))
        surface.blit(bg, (bx, by))
        pygame.draw.rect(surface, UI_BORDER, (bx, by, bw, bh),
                         width=2, border_radius=4)
        surface.blit(surf, (bx + 10, by + 3))

        # Subtitle: "The Other Colony"
        sub = Fonts.small().render(S.RIVAL_PANEL_TITLE, True, UI_MUTED)
        surface.blit(sub, (panel.left + _PAD, panel.top + 14 + title.get_height()))

    def _draw_summary(
        self, surface: pygame.Surface, rect: pygame.Rect,
        rival: "RivalColony",
    ) -> None:
        x = rect.left
        y = rect.top
        body = Fonts.body()
        small = Fonts.small()

        # Relation bar (-100..+100).
        lbl = body.render(S.RIVAL_PANEL_REL_LABEL, True, UI_TEXT)
        surface.blit(lbl, (x, y))
        y += lbl.get_height() + 4
        bar = pygame.Rect(x, y, rect.width, _BAR_H)
        # 0..1 mapping for draw_progress_bar
        frac = (rival.relation + 100.0) / 200.0
        # Color bar by current diplomacy band.
        col = DIPLOMACY_COLORS[rival.state]
        draw_progress_bar(surface, bar, frac, fg=col)
        rel_txt = small.render(
            f"{int(rival.relation):+d} / 100", True, UI_MUTED,
        )
        surface.blit(
            rel_txt,
            (rect.right - rel_txt.get_width(), y + _BAR_H + 2),
        )
        y += _BAR_H + 26

        # Tier / power / pop / buildings rows.
        from compprog_pygame.games.hex_colony.tech_tree import TIERS
        tier_name = TIERS[rival.tier].name if rival.tier < len(TIERS) else "?"
        rows = [
            (S.RIVAL_PANEL_TIER_LABEL,    f"{tier_name} ({rival.tier})"),
            (S.RIVAL_PANEL_POWER_LABEL,   f"{rival.power_rating} / 10"),
            (S.RIVAL_PANEL_POPULATION,    str(rival.population)),
            (S.RIVAL_PANEL_BUILDINGS,     str(rival.building_count)),
        ]
        for k, v in rows:
            ks = body.render(k, True, UI_MUTED)
            vs = body.render(v, True, UI_TEXT)
            surface.blit(ks, (x, y))
            surface.blit(vs, (rect.right - vs.get_width(), y))
            y += _LINE_H

        y += 8

        # Rocket assembly bar (or "not yet building" placeholder).
        rk_lbl = body.render(S.RIVAL_PANEL_ROCKET_LABEL, True, UI_TEXT)
        surface.blit(rk_lbl, (x, y))
        y += rk_lbl.get_height() + 4
        rk_bar = pygame.Rect(x, y, rect.width, _BAR_H)
        if rival.rocket_started:
            from compprog_pygame.games.hex_colony.rival_colony import _ROCKET_TIME  # noqa: PLC2701
            rk_frac = min(1.0, rival.rocket_progress / _ROCKET_TIME)
            draw_progress_bar(
                surface, rk_bar, rk_frac, fg=(220, 90, 90),
            )
            eta = rival.rocket_eta_seconds or 0.0
            eta_txt = small.render(
                f"ETA: {int(eta)}s", True, (220, 140, 140),
            )
            surface.blit(eta_txt, (x, y + _BAR_H + 2))
        else:
            draw_progress_bar(surface, rk_bar, 0.0)
            ph = small.render(S.RIVAL_PANEL_ROCKET_LOCKED, True, UI_MUTED)
            surface.blit(ph, (x, y + _BAR_H + 2))
        y += _BAR_H + 28

        # Recent events log.
        ev_lbl = body.render(S.RIVAL_PANEL_LOG_HEADER, True, UI_TEXT)
        surface.blit(ev_lbl, (x, y))
        y += ev_lbl.get_height() + 4
        log_rect = pygame.Rect(x, y, rect.width, rect.bottom - y)
        log_bg = pygame.Surface(log_rect.size, pygame.SRCALPHA)
        log_bg.fill((20, 22, 32, 180))
        surface.blit(log_bg, log_rect.topleft)
        pygame.draw.rect(surface, UI_BORDER, log_rect, width=1)
        # Recent first.
        line_y = log_rect.top + 6
        if not rival.log:
            ph = small.render(S.RIVAL_PANEL_NO_EVENTS, True, UI_MUTED)
            surface.blit(ph, (log_rect.left + 8, line_y))
        else:
            for entry in reversed(rival.log):
                if line_y + small.get_height() > log_rect.bottom - 4:
                    break
                line = small.render(entry.text, True, entry.color)
                surface.blit(line, (log_rect.left + 8, line_y))
                line_y += small.get_height() + 2

    def _draw_actions(
        self, surface: pygame.Surface, rect: pygame.Rect,
        world: "World", rival: "RivalColony",
    ) -> None:
        body = Fonts.body()
        title = Fonts.label().render(S.RIVAL_PANEL_ACTIONS, True, UI_ACCENT)
        surface.blit(title, (rect.left, rect.top))
        y = rect.top + title.get_height() + 12
        # Build a 2-column button grid.
        bw = (rect.width - 14) // 2
        col_x = [rect.left, rect.left + bw + 14]

        def btn(label: str, action, *, enabled: bool = True,
                accent: tuple[int, int, int] = UI_ACCENT) -> None:
            nonlocal y, _slot
            r = pygame.Rect(col_x[_slot % 2], y, bw, _BTN_H)
            hov = enabled and r.collidepoint(self._mouse_pos)
            _draw_button(surface, r, label, hovered=hov,
                         enabled=enabled, accent=accent)
            if enabled:
                self._hit_rects.append((r, action))
            _slot += 1
            if _slot % 2 == 0:
                y += _BTN_H + 10

        _slot = 0
        btn(S.RIVAL_BTN_GIFT, lambda: self._set_view(_VIEW_GIFT))
        btn(S.RIVAL_BTN_TRADE, lambda: self._set_view(_VIEW_TRADE),
            enabled=rival.state != DiplomacyState.HOSTILE)
        if rival.war_declared:
            btn(S.RIVAL_BTN_PEACE,
                lambda: rival.sue_for_peace(world, self._notifications),
                accent=(200, 200, 100))
        else:
            btn(S.RIVAL_BTN_WAR,
                lambda: rival.declare_war(self._notifications),
                accent=(220, 100, 100))
        # Pad to even slot count for clean layout.
        if _slot % 2 != 0:
            y += _BTN_H + 10

        # Diplomacy hint text.
        if rival.war_declared:
            hint_txt = S.RIVAL_PEACE_HINT.format(
                amount=params.RIVAL_PEACE_TRIBUTE_AMOUNT,
                resource=S.resource_name(params.RIVAL_PEACE_TRIBUTE_RESOURCE),
            )
            hint = body.render(hint_txt, True, UI_MUTED)
            surface.blit(hint, (rect.left, y + 4))

    def _draw_gift_view(
        self, surface: pygame.Surface, rect: pygame.Rect,
        world: "World", rival: "RivalColony",
    ) -> None:
        title = Fonts.label().render(S.RIVAL_GIFT_TITLE, True, UI_ACCENT)
        surface.blit(title, (rect.left, rect.top))
        y = rect.top + title.get_height() + 6
        hint = Fonts.small().render(S.RIVAL_GIFT_HINT, True, UI_MUTED)
        surface.blit(hint, (rect.left, y))
        y += hint.get_height() + 12

        # Resource picker — 2 columns.
        bw = (rect.width - 14) // 2
        body = Fonts.body()
        for i, res in enumerate(GIFT_RESOURCES):
            col = i % 2
            row = i // 2
            r = pygame.Rect(rect.left + col * (bw + 14),
                            y + row * (_BTN_H + 8),
                            bw, _BTN_H)
            owned = int(world.player_colony.inventory[res])
            label = f"{S.resource_name(res.name)} ({owned})"
            hov = r.collidepoint(self._mouse_pos)
            selected = (self._gift_res == res)
            accent = UI_ACCENT if selected else UI_BORDER_LIGHT
            _draw_button(surface, r, label, hovered=hov,
                         enabled=owned > 0, accent=accent)
            if owned > 0:
                self._hit_rects.append(
                    (r, (lambda rr=res: self._set_gift_res(rr))),
                )
        y += ((len(GIFT_RESOURCES) + 1) // 2) * (_BTN_H + 8) + 8

        # Amount picker — only if a resource is selected.
        if self._gift_res is not None:
            amt_lbl = body.render(
                f"Send: {S.resource_name(self._gift_res.name)}",
                True, UI_TEXT,
            )
            surface.blit(amt_lbl, (rect.left, y))
            y += amt_lbl.get_height() + 6
            owned = int(world.player_colony.inventory[self._gift_res])
            for i, amt in enumerate(GIFT_AMOUNTS):
                r = pygame.Rect(
                    rect.left + i * (bw // 2 + 8), y,
                    bw // 2, _BTN_H,
                )
                hov = r.collidepoint(self._mouse_pos)
                _draw_button(
                    surface, r, str(amt), hovered=hov,
                    enabled=owned >= amt,
                )
                if owned >= amt:
                    self._hit_rects.append(
                        (r, (lambda a=amt: self._do_gift(world, rival, a))),
                    )
            y += _BTN_H + 12

        # Back button.
        back = pygame.Rect(rect.left, rect.bottom - _BTN_H,
                           _BTN_W, _BTN_H)
        hov = back.collidepoint(self._mouse_pos)
        _draw_button(surface, back, S.RIVAL_BTN_BACK, hovered=hov)
        self._hit_rects.append((back, lambda: self._set_view(_VIEW_MAIN)))

    def _draw_trade_view(
        self, surface: pygame.Surface, rect: pygame.Rect,
        world: "World", rival: "RivalColony",
    ) -> None:
        title = Fonts.label().render(S.RIVAL_TRADE_TITLE, True, UI_ACCENT)
        surface.blit(title, (rect.left, rect.top))
        y = rect.top + title.get_height() + 6
        hint = Fonts.small().render(S.RIVAL_TRADE_HINT, True, UI_MUTED)
        surface.blit(hint, (rect.left, y))
        y += hint.get_height() + 10

        body = Fonts.body()
        small = Fonts.small()
        inv = world.player_colony.inventory
        rival_inv = rival.colony.inventory
        for offer in DEFAULT_TRADES:
            r = pygame.Rect(rect.left, y, rect.width, _BTN_H + 4)
            give_n = S.resource_name(offer.give_res.name)
            get_n = S.resource_name(offer.get_res.name)
            label = S.RIVAL_TRADE_FORMAT.format(
                give_amt=offer.give_amt, give=give_n,
                get_amt=offer.get_amt, get=get_n,
            )
            player_can = inv[offer.give_res] >= offer.give_amt
            rival_has = rival_inv[offer.get_res] >= offer.get_amt
            enabled = player_can and rival_has
            hov = r.collidepoint(self._mouse_pos)
            _draw_button(surface, r, label, hovered=hov, enabled=enabled)
            if enabled:
                self._hit_rects.append(
                    (r, (lambda o=offer: rival.propose_trade(
                        world, o, self._notifications))),
                )
            elif not player_can:
                tag = small.render(" (you lack stock)", True, (200, 140, 90))
                surface.blit(
                    tag,
                    (r.right - tag.get_width() - 6,
                     r.bottom - tag.get_height() - 4),
                )
            elif not rival_has:
                tag = small.render(" (they lack stock)", True, (200, 140, 90))
                surface.blit(
                    tag,
                    (r.right - tag.get_width() - 6,
                     r.bottom - tag.get_height() - 4),
                )
            y += _BTN_H + 10
            if y + _BTN_H > rect.bottom - _BTN_H - 8:
                break

        # Back button.
        back = pygame.Rect(rect.left, rect.bottom - _BTN_H,
                           _BTN_W, _BTN_H)
        hov = back.collidepoint(self._mouse_pos)
        _draw_button(surface, back, S.RIVAL_BTN_BACK, hovered=hov)
        self._hit_rects.append((back, lambda: self._set_view(_VIEW_MAIN)))

    # ── Internal helpers ─────────────────────────────────────────

    def _set_view(self, view: str) -> None:
        self._view = view
        self._gift_res = None

    def _set_gift_res(self, res: Resource) -> None:
        self._gift_res = res

    def _do_gift(
        self, world: "World", rival: "RivalColony", amount: int,
    ) -> None:
        if self._gift_res is None:
            return
        rival.send_gift(world, self._gift_res, amount, self._notifications)

    # ── Event handling ───────────────────────────────────────────

    def handle_event(self, event: pygame.event.Event) -> bool:
        if not self.visible:
            return False
        if event.type == pygame.MOUSEMOTION:
            self._mouse_pos = event.pos
            return True
        if event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_r, pygame.K_ESCAPE):
                # ESC: pop sub-view first, then close.
                if self._view != _VIEW_MAIN:
                    self._view = _VIEW_MAIN
                    self._gift_res = None
                else:
                    self.visible = False
                return True
            return True  # swallow all keys while modal
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            for rect, action in self._hit_rects:
                if rect.collidepoint(event.pos):
                    action()
                    return True
            return True
        if event.type == pygame.MOUSEBUTTONUP:
            return True
        return False
