"""Game-over overlay for Hex Colony.

Shown when the colony fails. Displays a cause-specific title and
flavor line, a stat block summarising the run, and buttons for
returning to the main menu or quitting.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Callable

import pygame

from compprog_pygame.games.hex_colony.ui import (
    Fonts,
    Panel,
    UI_BAD,
    UI_MUTED,
    UI_OVERLAY,
    UI_TEXT,
    draw_button,
    draw_titled_panel,
    wrap_text,
)
from compprog_pygame.games.hex_colony.tech_tree import TIERS
from compprog_pygame.games.hex_colony.strings import (
    GAME_OVER_TITLE,
    GAME_OVER_BUTTONS,
    GAME_OVER_TITLE_NO_SURVIVORS,
    GAME_OVER_TITLE_CAMP_DESTROYED,
    GAME_OVER_REASON_NO_SURVIVORS,
    GAME_OVER_REASON_CAMP_DESTROYED,
    GAME_OVER_STAT_TIME,
    GAME_OVER_STAT_TIER,
    GAME_OVER_STAT_RESEARCH,
    GAME_OVER_STAT_BUILDINGS,
    GAME_OVER_STAT_PEAK_POP,
    GAME_OVER_STAT_FINAL_POP,
    GAME_OVER_STAT_ENEMIES,
    GAME_OVER_STAT_WAVES,
)

if TYPE_CHECKING:
    from compprog_pygame.games.hex_colony.world import World
    from compprog_pygame.games.hex_colony.tech_tree import TechTree
    from compprog_pygame.games.hex_colony.colony import TierTracker


_BUTTON_W = 280
_BUTTON_H = 48
_BUTTON_GAP = 12
_BUTTONS = GAME_OVER_BUTTONS

_STAT_ROW_GAP = 6
_REASON_GAP = 18
_STATS_GAP = 22


_CAUSE_TITLES = {
    "camp_destroyed": GAME_OVER_TITLE_CAMP_DESTROYED,
    "no_survivors":   GAME_OVER_TITLE_NO_SURVIVORS,
}
_CAUSE_REASONS = {
    "camp_destroyed": GAME_OVER_REASON_CAMP_DESTROYED,
    "no_survivors":   GAME_OVER_REASON_NO_SURVIVORS,
}


class GameOverOverlay(Panel):
    """Full-screen overlay shown when the game ends."""

    def __init__(self) -> None:
        super().__init__()
        # Panel.visible gates UIManager draw/event dispatch; keep it
        # in sync with .active (Game flips both when world.game_over).
        self.visible = False
        self.active = False
        self._hovered: int = -1
        self._btn_rects: list[pygame.Rect] = []

        self.on_return_to_menu: Callable[[], None] | None = None
        self.on_quit: Callable[[], None] | None = None

        # Optional context wired by Game so we can report tier/research
        # in the summary.  Both default to None and the panel falls
        # back to "—" when missing.
        self.tier_tracker: "TierTracker | None" = None
        self.tech_tree: "TechTree | None" = None

    def layout(self, screen_w: int, screen_h: int) -> None:
        self.rect = pygame.Rect(0, 0, screen_w, screen_h)

    # ── Stat collection ─────────────────────────────────────────

    def _collect_stats(self, world: "World") -> list[tuple[str, str]]:
        secs_total = int(world.real_time_elapsed)
        h, rem = divmod(secs_total, 3600)
        m, s = divmod(rem, 60)
        time_str = f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"

        n_bld = sum(
            1 for b in world.buildings.buildings
            if getattr(b, "faction", "SURVIVOR") == "SURVIVOR"
        )

        if (self.tier_tracker is not None
                and 0 <= self.tier_tracker.current_tier < len(TIERS)):
            tier_name = TIERS[self.tier_tracker.current_tier].name
            tier_str = f"{tier_name} (T{self.tier_tracker.current_tier + 1})"
        else:
            tier_str = "—"

        if self.tech_tree is not None:
            try:
                total_nodes = len(self.tech_tree.all_nodes())
            except Exception:
                total_nodes = 0
            done = self.tech_tree.researched_count
            tech_str = f"{done} / {total_nodes}" if total_nodes else str(done)
        else:
            tech_str = "—"

        combat = getattr(world, "combat", None)
        kills = getattr(combat, "enemies_killed", 0) if combat else 0
        waves = getattr(combat, "waves_triggered", 0) if combat else 0

        peak_pop = getattr(world, "peak_population", 0)
        final_pop = world.player_population_count

        return [
            (GAME_OVER_STAT_TIME,      time_str),
            (GAME_OVER_STAT_TIER,      tier_str),
            (GAME_OVER_STAT_RESEARCH,  tech_str),
            (GAME_OVER_STAT_BUILDINGS, str(n_bld)),
            (GAME_OVER_STAT_PEAK_POP,  str(peak_pop)),
            (GAME_OVER_STAT_FINAL_POP, str(final_pop)),
            (GAME_OVER_STAT_ENEMIES,   str(kills)),
            (GAME_OVER_STAT_WAVES,     str(waves)),
        ]

    # ── Drawing ─────────────────────────────────────────────────

    def draw(self, surface: pygame.Surface, world: "World") -> None:
        self.visible = self.active
        if not self.active:
            return

        sw, sh = surface.get_size()
        overlay = pygame.Surface((sw, sh), pygame.SRCALPHA)
        overlay.fill(UI_OVERLAY)
        surface.blit(overlay, (0, 0))

        reason_key = getattr(world, "game_over_reason", None)
        title = _CAUSE_TITLES.get(reason_key, GAME_OVER_TITLE)
        flavor = _CAUSE_REASONS.get(reason_key, "")
        stats = self._collect_stats(world)

        body_font = Fonts.body()
        label_font = Fonts.label()
        hero_font = Fonts.hero()

        pw = max(_BUTTON_W + 120, 560)
        flavor_w = pw - 60
        flavor_lines = wrap_text(body_font, flavor, flavor_w) if flavor else []
        flavor_h = (
            len(flavor_lines) * body_font.get_linesize()
            if flavor_lines else 0
        )

        row_h = label_font.get_linesize() + _STAT_ROW_GAP
        n_rows = (len(stats) + 1) // 2
        stats_h = n_rows * row_h

        title_h = hero_font.get_linesize() + 12
        ph = (
            title_h + _REASON_GAP + flavor_h + _STATS_GAP + stats_h
            + 32
            + len(_BUTTONS) * _BUTTON_H
            + (len(_BUTTONS) - 1) * _BUTTON_GAP
            + 32
        )
        pw = min(pw, sw - 40)
        ph = min(ph, sh - 40)
        px = (sw - pw) // 2
        py = (sh - ph) // 2

        panel = pygame.Rect(px, py, pw, ph)
        content_y = draw_titled_panel(
            surface, panel, title,
            title_color=UI_BAD, title_font=hero_font,
        )

        y = content_y + _REASON_GAP
        for line in flavor_lines:
            surf = body_font.render(line, True, UI_MUTED)
            surface.blit(surf, (
                px + (pw - surf.get_width()) // 2, y,
            ))
            y += body_font.get_linesize()

        y += _STATS_GAP
        col_w = (pw - 60) // 2
        col_x = (px + 30, px + 30 + col_w)
        for i, (label, value) in enumerate(stats):
            cx = col_x[i % 2]
            cy = y + (i // 2) * row_h
            lbl = label_font.render(label, True, UI_MUTED)
            val = label_font.render(value, True, UI_TEXT)
            surface.blit(lbl, (cx, cy))
            val_x = cx + col_w - 12 - val.get_width()
            surface.blit(val, (val_x, cy))

        self._btn_rects = []
        bx = px + (pw - _BUTTON_W) // 2
        by = (
            py + ph - 24
            - len(_BUTTONS) * _BUTTON_H
            - (len(_BUTTONS) - 1) * _BUTTON_GAP
        )
        for idx, label in enumerate(_BUTTONS):
            rect = pygame.Rect(bx, by, _BUTTON_W, _BUTTON_H)
            state = "hover" if idx == self._hovered else "normal"
            draw_button(surface, rect, label, state=state)
            self._btn_rects.append(rect)
            by += _BUTTON_H + _BUTTON_GAP

    # ── Input ───────────────────────────────────────────────────

    def handle_event(self, event: pygame.event.Event) -> bool:
        if not self.active:
            return False

        if event.type == pygame.MOUSEMOTION:
            self._hovered = -1
            for i, r in enumerate(self._btn_rects):
                if r.collidepoint(event.pos):
                    self._hovered = i
                    break
            return True

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            for i, r in enumerate(self._btn_rects):
                if r.collidepoint(event.pos):
                    if i == 0 and self.on_return_to_menu:
                        self.on_return_to_menu()
                    elif i == 1 and self.on_quit:
                        self.on_quit()
                    return True
            return True

        return True
