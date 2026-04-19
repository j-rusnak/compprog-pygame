"""Step-by-step tutorial system for Hex Colony.

Shows contextual pop-up hints as the player progresses through early
gameplay.  Each step has a trigger condition and is shown at most once.
The tutorial panel floats near the top-left of the screen.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Callable

import pygame

from compprog_pygame.games.hex_colony.buildings import BuildingType
from compprog_pygame.games.hex_colony.resources import Resource
from compprog_pygame.games.hex_colony.ui import (
    Fonts,
    Panel,
    UI_ACCENT,
    UI_BORDER,
    UI_MUTED,
    UI_TEXT,
    draw_panel_bg,
    wrap_text,
)
from compprog_pygame.games.hex_colony.strings import (
    TUTORIAL_STEPS as _TUTORIAL_TEXT,
    TUTORIAL_DISMISS_BUTTON,
)

if TYPE_CHECKING:
    from compprog_pygame.games.hex_colony.world import World


# ── Tutorial step definitions ────────────────────────────────────

@dataclass
class _TutorialStep:
    """A single tutorial hint."""
    id: str
    title: str
    lines: list[str]
    # Callable(world, game_context) -> bool.  When True the step is
    # shown.  ``game_context`` is a dict with extra game state
    # (e.g. build_mode, building counts, etc.).
    trigger: Callable[["World", dict], bool]
    # Optional: only show this step after the given step id has been
    # dismissed.
    after: str | None = None


def _has_building_count(world: "World", btype: BuildingType, n: int = 1) -> bool:
    return len(world.buildings.by_type(btype)) >= n


def _has_workers_at(world: "World", btype: BuildingType) -> bool:
    for b in world.buildings.by_type(btype):
        if b.workers > 0:
            return True
    return False


def _population(world: "World") -> int:
    return world.population.count


def _research_done(world: "World", node_id: str) -> bool:
    """True if the named tech tree node has been researched."""
    tt = getattr(world, "tech_tree", None)
    if tt is None:
        return False
    completed = getattr(tt, "completed", None)
    if completed is None:
        return False
    try:
        return node_id in completed
    except TypeError:
        return False


def _has_building(world: "World", type_name: str) -> bool:
    """True if any building of the named BuildingType has been placed."""
    from compprog_pygame.games.hex_colony.buildings import BuildingType
    bt = getattr(BuildingType, type_name, None)
    if bt is None:
        return False
    try:
        return any(True for _ in world.buildings.by_type(bt))
    except Exception:
        return False


# Build a lookup from step id -> text dict for quick access.
_TEXT_BY_ID: dict[str, dict] = {d["id"]: d for d in _TUTORIAL_TEXT}  # type: ignore[arg-type]

def _text(step_id: str) -> tuple[str, list[str]]:
    """Return (title, lines) for *step_id* from the centralised strings."""
    entry = _TEXT_BY_ID[step_id]
    return entry["title"], list(entry["lines"])  # type: ignore[arg-type]


# Steps dismissed with a zero cooldown so the next hint fires
# immediately instead of after the default delay.  Used for tightly
# paired hints (housing → tier goal).
_INSTANT_FOLLOWUP: set[str] = {"build_habitat"}


TUTORIAL_STEPS: list[_TutorialStep] = [
    _TutorialStep(
        id="welcome",
        title=_text("welcome")[0],
        lines=_text("welcome")[1],
        trigger=lambda w, ctx: ctx.get("time", 0) < 2.0,
    ),
    _TutorialStep(
        id="build_gatherer",
        title=_text("build_gatherer")[0],
        lines=_text("build_gatherer")[1],
        trigger=lambda w, ctx: not _has_building_count(w, BuildingType.GATHERER),
        after="welcome",
    ),
    _TutorialStep(
        id="connect_paths",
        title=_text("connect_paths")[0],
        lines=_text("connect_paths")[1],
        trigger=lambda w, ctx: (
            _has_building_count(w, BuildingType.GATHERER)
            and not _has_workers_at(w, BuildingType.GATHERER)
        ),
        after="build_gatherer",
    ),
    _TutorialStep(
        id="food_producing",
        title=_text("food_producing")[0],
        lines=_text("food_producing")[1],
        trigger=lambda w, ctx: _has_workers_at(w, BuildingType.GATHERER),
        after="connect_paths",
    ),
    _TutorialStep(
        id="build_woodcutter",
        title=_text("build_woodcutter")[0],
        lines=_text("build_woodcutter")[1],
        trigger=lambda w, ctx: (
            _has_workers_at(w, BuildingType.GATHERER)
            and not _has_building_count(w, BuildingType.WOODCUTTER)
        ),
        after="food_producing",
    ),
    _TutorialStep(
        id="build_habitat",
        title=_text("build_habitat")[0],
        lines=_text("build_habitat")[1],
        trigger=lambda w, ctx: (
            _has_building_count(w, BuildingType.WOODCUTTER)
            and not _has_building_count(w, BuildingType.HABITAT)
        ),
        after="build_woodcutter",
    ),
    _TutorialStep(
        id="tier_goal",
        title=_text("tier_goal")[0],
        lines=_text("tier_goal")[1],
        # Fires immediately after the housing popup is dismissed so
        # the player always gets the tier-goal explanation right
        # after the habitat hint.
        trigger=lambda w, ctx: True,
        after="build_habitat",
    ),
    _TutorialStep(
        id="workshop_crafting",
        title=_text("workshop_crafting")[0],
        lines=_text("workshop_crafting")[1],
        trigger=lambda w, ctx: (
            _has_building_count(w, BuildingType.WORKSHOP)
            and _has_workers_at(w, BuildingType.WORKSHOP)
            and all(
                b.recipe is None
                for b in w.buildings.by_type(BuildingType.WORKSHOP)
            )
        ),
        after="build_habitat",
    ),
    _TutorialStep(
        id="mining_smelting",
        title=_text("mining_smelting")[0],
        lines=_text("mining_smelting")[1],
        # 30 s after the player reaches tier 2 (Settlement).
        trigger=lambda w, ctx: (
            ctx.get("current_tier_level", 0) >= 2
            and ctx.get("time_in_tier", 0.0) >= 30.0
        ),
        after=None,
    ),
    _TutorialStep(
        id="research",
        title=_text("research")[0],
        lines=_text("research")[1],
        # 30 s after the player reaches tier 1 (Foothold).
        trigger=lambda w, ctx: (
            ctx.get("current_tier_level", 0) >= 1
            and ctx.get("time_in_tier", 0.0) >= 30.0
        ),
        after=None,
    ),
    _TutorialStep(
        id="population_growing",
        title=_text("population_growing")[0],
        lines=_text("population_growing")[1],
        trigger=lambda w, ctx: _population(w) >= 10,
        after="build_habitat",
    ),
    _TutorialStep(
        id="useful_controls",
        title=_text("useful_controls")[0],
        lines=_text("useful_controls")[1],
        trigger=lambda w, ctx: ctx.get("real_time", 0) >= 120.0,
        after=None,
    ),
    # ── Tier 4+ feature tutorials ─────────────────────────────────
    _TutorialStep(
        id="industrial_intro",
        title=_text("industrial_intro")[0],
        lines=_text("industrial_intro")[1],
        # Fires shortly after entering Industrial tier (0-indexed: 3).
        trigger=lambda w, ctx: (
            ctx.get("current_tier_level", 0) >= 3
            and ctx.get("time_in_tier", 0.0) >= 5.0
        ),
        after=None,
    ),
    _TutorialStep(
        id="conveyor_intro",
        title=_text("conveyor_intro")[0],
        lines=_text("conveyor_intro")[1],
        # ~25 s after entering tier 4 \u2014 by then Conveyor research is realistic.
        trigger=lambda w, ctx: (
            ctx.get("current_tier_level", 0) >= 3
            and ctx.get("time_in_tier", 0.0) >= 15.0
        ),
        after="industrial_intro",
    ),
    _TutorialStep(
        id="chemical_plant_intro",
        title=_text("chemical_plant_intro")[0],
        lines=_text("chemical_plant_intro")[1],
        # 60 s into tier 4 \u2014 player has likely started Basic Chemistry.
        trigger=lambda w, ctx: (
            ctx.get("current_tier_level", 0) >= 3
            and ctx.get("time_in_tier", 0.0) >= 30.0
        ),
        after="industrial_intro",
    ),
    _TutorialStep(
        id="automation_intro",
        title=_text("automation_intro")[0],
        lines=_text("automation_intro")[1],
        trigger=lambda w, ctx: ctx.get("current_tier_level", 0) >= 5,
        after=None,
    ),
    _TutorialStep(
        id="solar_array_intro",
        title=_text("solar_array_intro")[0],
        lines=_text("solar_array_intro")[1],
        trigger=lambda w, ctx: (
            ctx.get("current_tier_level", 0) >= 5
            and ctx.get("time_in_tier", 0.0) >= 15.0
        ),
        after="automation_intro",
    ),
    _TutorialStep(
        id="spacefarer_intro",
        title=_text("spacefarer_intro")[0],
        lines=_text("spacefarer_intro")[1],
        trigger=lambda w, ctx: ctx.get("current_tier_level", 0) >= 6,
        after=None,
    ),
    _TutorialStep(
        id="rocket_silo_intro",
        title=_text("rocket_silo_intro")[0],
        lines=_text("rocket_silo_intro")[1],
        trigger=lambda w, ctx: (
            ctx.get("current_tier_level", 0) >= 6
            and ctx.get("time_in_tier", 0.0) >= 15.0
        ),
        after="spacefarer_intro",
    ),
    # ── Petrochemical tier (inserted between Industrial and Automation) ──
    _TutorialStep(
        id="petrochemical_intro",
        title=_text("petrochemical_intro")[0],
        lines=_text("petrochemical_intro")[1],
        trigger=lambda w, ctx: ctx.get("current_tier_level", 0) >= 4,
        after=None,
    ),
    _TutorialStep(
        id="oil_deposit_intro",
        title=_text("oil_deposit_intro")[0],
        lines=_text("oil_deposit_intro")[1],
        # Fire when the player has researched petroleum_engineering or
        # has reached the Petrochemical tier and has discovered an oil
        # tile (we proxy "has discovered" with time-in-tier).
        trigger=lambda w, ctx: (
            ctx.get("current_tier_level", 0) >= 4
            and ctx.get("time_in_tier", 0.0) >= 8.0
        ),
        after="petrochemical_intro",
    ),
    _TutorialStep(
        id="oil_drill_intro",
        title=_text("oil_drill_intro")[0],
        lines=_text("oil_drill_intro")[1],
        trigger=lambda w, ctx: _research_done(w, "petroleum_engineering"),
        after="oil_deposit_intro",
    ),
    _TutorialStep(
        id="oil_refinery_intro",
        title=_text("oil_refinery_intro")[0],
        lines=_text("oil_refinery_intro")[1],
        trigger=lambda w, ctx: (
            _research_done(w, "petroleum_engineering")
            and _has_building(w, "OIL_DRILL")
        ),
        after="oil_drill_intro",
    ),
    _TutorialStep(
        id="advanced_materials_intro",
        title=_text("advanced_materials_intro")[0],
        lines=_text("advanced_materials_intro")[1],
        trigger=lambda w, ctx: ctx.get("current_tier_level", 0) >= 5,
        after="petrochemical_intro",
    ),
]


# ── Tutorial panel ───────────────────────────────────────────────

_PANEL_W = 320
_PAD = 14
_LINE_H = 20
_TITLE_H = 28
_BTN_W = 80
_BTN_H = 28


class TutorialPanel(Panel):
    """Floating tutorial hint panel."""

    def __init__(self) -> None:
        super().__init__()
        self.active: bool = True  # master switch
        self._dismissed: set[str] = set()
        self._current_step: _TutorialStep | None = None
        self._visible: bool = False
        self._btn_rect: pygame.Rect = pygame.Rect(0, 0, 0, 0)
        self._screen_w: int = 0
        self._screen_h: int = 0
        # Cooldown: don't show the next step immediately after dismiss.
        self._cooldown: float = 0.0

    def layout(self, screen_w: int, screen_h: int) -> None:
        self._screen_w = screen_w
        self._screen_h = screen_h
        self.rect = pygame.Rect(16, 50, _PANEL_W, 100)

    def check_triggers(self, world: "World", ctx: dict) -> None:
        """Called each frame to see if a new tutorial step should show."""
        if not self.active:
            return
        if self._visible:
            return  # already showing something
        if self._cooldown > 0:
            self._cooldown -= ctx.get("dt", 1 / 60)
            return
        # Lookup so we can check an `after` step's trigger state.
        steps_by_id = {s.id: s for s in TUTORIAL_STEPS}
        for step in TUTORIAL_STEPS:
            if step.id in self._dismissed:
                continue
            if step.after is not None and step.after not in self._dismissed:
                # Only block while the earlier step is still applicable
                # (its trigger currently fires).  Once the earlier step
                # becomes irrelevant — e.g. the player skipped past it
                # — this step should still eventually appear.
                prev = steps_by_id.get(step.after)
                prev_applicable = False
                if prev is not None:
                    try:
                        prev_applicable = bool(prev.trigger(world, ctx))
                    except Exception:
                        prev_applicable = False
                if prev_applicable:
                    continue
            try:
                if step.trigger(world, ctx):
                    self._current_step = step
                    self._visible = True
                    return
            except Exception:
                # Don't crash on trigger errors.
                continue

    def dismiss(self) -> None:
        if self._current_step is not None:
            dismissed_id = self._current_step.id
            self._dismissed.add(dismissed_id)
            self._current_step = None
            # Tightly paired hints skip the usual cooldown so the next
            # tip appears on the very next frame.
            self._cooldown = 0.0 if dismissed_id in _INSTANT_FOLLOWUP else 3.0
        else:
            self._cooldown = 3.0
        self._visible = False

    def draw(self, surface: pygame.Surface, world: "World") -> None:
        if not self._visible or self._current_step is None:
            return
        step = self._current_step
        font = Fonts.small()
        title_font = Fonts.label()

        # Compute panel height from content.
        rendered_lines = step.lines
        content_h = _TITLE_H + len(rendered_lines) * _LINE_H + _BTN_H + _PAD * 3

        x = 16
        y = 50
        w = _PANEL_W
        h = content_h
        # Make sure it doesn't go off screen.
        if y + h > self._screen_h - 50:
            h = self._screen_h - 50 - y

        panel_rect = pygame.Rect(x, y, w, h)
        self.rect = panel_rect

        # Background with gold accent.
        draw_panel_bg(surface, panel_rect, accent_edge="top")
        # Gold top edge.
        pygame.draw.line(
            surface, (220, 180, 60),
            (x + 1, y + 1), (x + w - 2, y + 1), 2,
        )

        cy = y + _PAD
        # Title.
        title_surf = title_font.render(step.title, True, (255, 215, 100))
        surface.blit(title_surf, (x + _PAD, cy))
        cy += _TITLE_H

        # Body lines.
        for line in rendered_lines:
            if not line:
                cy += _LINE_H // 2
                continue
            surf = font.render(line, True, UI_TEXT)
            surface.blit(surf, (x + _PAD, cy))
            cy += _LINE_H

        # "Got it" button.
        cy += _PAD // 2
        btn_x = x + w - _BTN_W - _PAD
        btn_y = min(cy, y + h - _BTN_H - _PAD // 2)
        self._btn_rect = pygame.Rect(btn_x, btn_y, _BTN_W, _BTN_H)
        mx, my = pygame.mouse.get_pos()
        hover = self._btn_rect.collidepoint(mx, my)
        bg = (80, 160, 80) if hover else (60, 130, 60)
        pygame.draw.rect(surface, bg, self._btn_rect, border_radius=4)
        pygame.draw.rect(surface, (100, 200, 100), self._btn_rect, 1, border_radius=4)
        label = font.render(TUTORIAL_DISMISS_BUTTON, True, (255, 255, 255))
        surface.blit(label, (
            self._btn_rect.centerx - label.get_width() // 2,
            self._btn_rect.centery - label.get_height() // 2,
        ))

        # Step counter (e.g. "2 / 10").
        done = len(self._dismissed)
        total = len(TUTORIAL_STEPS)
        counter = font.render(f"{done + 1} / {total}", True, UI_MUTED)
        surface.blit(counter, (x + _PAD, btn_y + (_BTN_H - counter.get_height()) // 2))

    def handle_event(self, event: pygame.event.Event) -> bool:
        if not self._visible or self._current_step is None:
            return False
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self._btn_rect.collidepoint(event.pos):
                self.dismiss()
                return True
            # Clicking anywhere inside the panel consumes the event.
            if self.rect.collidepoint(event.pos):
                return True
        if event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_RETURN, pygame.K_SPACE):
                if self._visible:
                    self.dismiss()
                    return True
        return False


__all__ = ["TutorialPanel"]
