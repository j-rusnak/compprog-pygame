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


TUTORIAL_STEPS: list[_TutorialStep] = [
    _TutorialStep(
        id="welcome",
        title="Welcome to Hex Colony!",
        lines=[
            "You've crash-landed on an alien world.",
            "Your crew needs Food to survive \u2014 without it",
            "your colonists will starve!",
            "",
            "Let's get started by setting up food production.",
        ],
        trigger=lambda w, ctx: ctx.get("time", 0) < 2.0,
    ),
    _TutorialStep(
        id="build_gatherer",
        title="Build a Gatherer",
        lines=[
            "Open the Buildings tab at the bottom of the",
            "screen and select \u201cGatherer\u201d.",
            "",
            "Place it on a grass/plains tile near your Camp.",
            "Gatherers harvest Food from surrounding tiles.",
        ],
        trigger=lambda w, ctx: not _has_building_count(w, BuildingType.GATHERER),
        after="welcome",
    ),
    _TutorialStep(
        id="connect_paths",
        title="Connect with Paths",
        lines=[
            "Your Gatherer needs a path connection to the",
            "Camp so workers can reach it.",
            "",
            "Select \u201cPath\u201d from Buildings, click near the",
            "Camp, then click near the Gatherer to lay a",
            "route automatically.",
        ],
        trigger=lambda w, ctx: (
            _has_building_count(w, BuildingType.GATHERER)
            and not _has_workers_at(w, BuildingType.GATHERER)
        ),
        after="build_gatherer",
    ),
    _TutorialStep(
        id="food_producing",
        title="Food Production Started!",
        lines=[
            "Great! Workers are now gathering Food.",
            "Click on the Gatherer to see its info panel.",
            "It defaults to Food \u2014 you can switch to Fiber",
            "later if you need it for crafting.",
            "",
            "Keep an eye on the Food counter in the top bar.",
        ],
        trigger=lambda w, ctx: _has_workers_at(w, BuildingType.GATHERER),
        after="connect_paths",
    ),
    _TutorialStep(
        id="build_woodcutter",
        title="Gather More Resources",
        lines=[
            "You'll need Wood and Stone to build more.",
            "",
            "Place a Woodcutter on a forest tile and a",
            "Quarry on a mountain tile, then connect them",
            "with Paths.",
        ],
        trigger=lambda w, ctx: (
            _has_workers_at(w, BuildingType.GATHERER)
            and not _has_building_count(w, BuildingType.WOODCUTTER)
        ),
        after="food_producing",
    ),
    _TutorialStep(
        id="build_habitat",
        title="Build a Habitat",
        lines=[
            "Your Camp can only house a few colonists.",
            "Build a Habitat to provide more housing \u2014",
            "colonists will reproduce when they have food",
            "and a home with room.",
            "",
            "More people means more workers!",
        ],
        trigger=lambda w, ctx: (
            _has_building_count(w, BuildingType.WOODCUTTER)
            and not _has_building_count(w, BuildingType.HABITAT)
        ),
        after="build_woodcutter",
    ),
    _TutorialStep(
        id="workshop_crafting",
        title="Workshop Crafting",
        lines=[
            "Your Workshop can craft materials and buildings.",
            "",
            "Click on the Workshop, then select a recipe",
            "from the dropdown menu. Workers will craft it",
            "using resources from your global inventory.",
        ],
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
        id="forge_smelting",
        title="Forge \u2014 Smelt Ores",
        lines=[
            "The Forge smelts raw Iron and Copper into bars.",
            "",
            "Click on the Forge and pick a material recipe",
            "to start smelting. You'll need bars to craft",
            "advanced buildings and components.",
        ],
        trigger=lambda w, ctx: (
            _has_building_count(w, BuildingType.FORGE)
            and _has_workers_at(w, BuildingType.FORGE)
            and all(
                b.recipe is None
                for b in w.buildings.by_type(BuildingType.FORGE)
            )
        ),
        after=None,  # can trigger independently
    ),
    _TutorialStep(
        id="research",
        title="Research New Tech",
        lines=[
            "Your Research Center can unlock new buildings",
            "and recipes.",
            "",
            "Click on it and select a technology to research.",
            "Research consumes resources over time. Open the",
            "Tech Tree to see what's available.",
        ],
        trigger=lambda w, ctx: (
            _has_building_count(w, BuildingType.RESEARCH_CENTER)
            and _has_workers_at(w, BuildingType.RESEARCH_CENTER)
            and ctx.get("researched_count", 0) == 0
        ),
        after=None,
    ),
    _TutorialStep(
        id="population_growing",
        title="Population Growing!",
        lines=[
            "Your colony is expanding. More colonists means",
            "you can staff more buildings.",
            "",
            "Check the Workers tab to see how workers are",
            "assigned. Logistics workers move resources",
            "between buildings automatically.",
        ],
        trigger=lambda w, ctx: _population(w) >= 10,
        after="build_habitat",
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
        for step in TUTORIAL_STEPS:
            if step.id in self._dismissed:
                continue
            if step.after is not None and step.after not in self._dismissed:
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
            self._dismissed.add(self._current_step.id)
            self._current_step = None
        self._visible = False
        self._cooldown = 3.0  # seconds before next hint

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
        label = font.render("Got it", True, (255, 255, 255))
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
