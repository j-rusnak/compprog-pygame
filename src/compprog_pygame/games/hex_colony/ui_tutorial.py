"""Step-by-step tutorial system for Hex Colony.

Shows contextual pop-up hints as the player progresses through early
gameplay.  Each step has a trigger condition and is shown at most once.
The tutorial panel floats near the top-left of the screen.
"""

from __future__ import annotations

import math
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
    BUILDING_CATEGORY_NAMES,
)
from compprog_pygame.settings import ASSET_DIR

if TYPE_CHECKING:
    from compprog_pygame.games.hex_colony.world import World
    from compprog_pygame.games.hex_colony.ui_bottom_bar import BottomBar


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
    # When True the panel is rendered as a large centered modal with
    # bigger text — used for the first few onboarding hints.
    centered: bool = False
    # Optional sprite (relative to assets/) shown inside a centered
    # tutorial panel between the body text and the dismiss button.
    image: str | None = None
    # Optional callable returning a screen-space rect to point an
    # animated arrow at.  Re-evaluated every frame so the arrow can
    # walk the player through a multi-step UI flow (open tab → pick
    # subtab → pick card).  Returns None when nothing should be
    # highlighted right now.
    arrow_fn: Callable[["BottomBar"], pygame.Rect | None] | None = None


def _has_building_count(world: "World", btype: BuildingType, n: int = 1) -> bool:
    return len(world.buildings.by_type(btype)) >= n


def _has_workers_at(world: "World", btype: BuildingType) -> bool:
    for b in world.buildings.by_type(btype):
        if b.workers > 0:
            return True
    return False


def _population(world: "World") -> int:
    return world.player_population_count


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


def _is_hard_mode(world: "World") -> bool:
    """True if this run was started on a difficulty that has enemies
    (HARD/Evolution or DESOLATION)."""
    from compprog_pygame.games.hex_colony.settings import Difficulty
    settings = getattr(world, "settings", None)
    if settings is None:
        return False
    diff = getattr(settings, "difficulty", None)
    return diff in (Difficulty.HARD, Difficulty.DESOLATION)


def _waves_triggered(world: "World") -> int:
    """Total number of enemy waves that have spawned so far."""
    combat = getattr(world, "combat", None)
    if combat is None:
        return 0
    return int(getattr(combat, "waves_triggered", 0))


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


# ── Arrow target helpers ─────────────────────────────────────────
#
# These read the live state of ``BottomBar`` / ``BuildingsTabContent``
# to figure out which on-screen rect the player should click next.
# The buildings tab is the very first tab added to ``BottomBar``
# (index 0) and ``BuildingsTabContent`` keeps subtab and card rects
# updated each frame in ``draw_content``.

_BUILDINGS_TAB_INDEX = 0  # Order matches ``BottomBar._create_default_tabs``.


def _buildings_tab_rect(bb: "BottomBar") -> pygame.Rect | None:
    rects = getattr(bb, "_tab_rects", None)
    if not rects or _BUILDINGS_TAB_INDEX >= len(rects):
        return None
    return rects[_BUILDINGS_TAB_INDEX]


def _buildings_tab_open(bb: "BottomBar") -> bool:
    return getattr(bb, "_active", -1) == _BUILDINGS_TAB_INDEX


def _category_index(bb: "BottomBar", name: str) -> int | None:
    btab = bb.buildings_tab
    if btab is None:
        return None
    for i, (cat_name, _) in enumerate(btab._visible_categories):
        if cat_name == name:
            return i
    return None


def _category_subtab_rect(bb: "BottomBar", name: str) -> pygame.Rect | None:
    btab = bb.buildings_tab
    if btab is None:
        return None
    idx = _category_index(bb, name)
    if idx is None:
        return None
    rects = btab._cat_tab_rects
    if idx >= len(rects):
        return None
    return rects[idx]


def _building_card_rect(
    bb: "BottomBar", btype: BuildingType,
) -> pygame.Rect | None:
    btab = bb.buildings_tab
    if btab is None:
        return None
    for rect, bt in btab._card_rects:
        if bt == btype:
            return rect
    return None


def _arrow_pick_building(
    bb: "BottomBar", category_name: str, btype: BuildingType,
) -> pygame.Rect | None:
    """Walk the player through opening Buildings → subtab → card.

    Returns the rect of whichever element they need to click *next*,
    or ``None`` if everything has already been clicked.
    """
    if not _buildings_tab_open(bb):
        return _buildings_tab_rect(bb)
    btab = bb.buildings_tab
    target_idx = _category_index(bb, category_name)
    if (
        btab is not None
        and target_idx is not None
        and btab._active_cat != target_idx
    ):
        return _category_subtab_rect(bb, category_name)
    # Card already selected — the player has finished the click path.
    if btab is not None and btab.selected_building == btype:
        return None
    return _building_card_rect(bb, btype)


TUTORIAL_STEPS: list[_TutorialStep] = [
    _TutorialStep(
        id="welcome",
        title=_text("welcome")[0],
        lines=_text("welcome")[1],
        trigger=lambda w, ctx: ctx.get("time", 0) < 2.0,
        centered=True,
    ),
    _TutorialStep(
        id="basic_controls",
        title=_text("basic_controls")[0],
        lines=_text("basic_controls")[1],
        trigger=lambda w, ctx: True,
        after="welcome",
        centered=True,
    ),
    _TutorialStep(
        id="build_gatherer",
        title=_text("build_gatherer")[0],
        lines=_text("build_gatherer")[1],
        trigger=lambda w, ctx: not _has_building_count(w, BuildingType.GATHERER),
        after="welcome",
        centered=True,
        image="sprites/fiber_patch_example.png",
        arrow_fn=lambda bb: _arrow_pick_building(
            bb, BUILDING_CATEGORY_NAMES[2], BuildingType.GATHERER,
        ),
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
        centered=True,
        arrow_fn=lambda bb: _arrow_pick_building(
            bb, BUILDING_CATEGORY_NAMES[4], BuildingType.PATH,
        ),
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
        # Only fire once the player has actually researched conveyors.
        trigger=lambda w, ctx: _research_done(w, "conveyor_belts"),
        after="industrial_intro",
    ),
    _TutorialStep(
        id="chemical_plant_intro",
        title=_text("chemical_plant_intro")[0],
        lines=_text("chemical_plant_intro")[1],
        # Only fire once Basic Chemistry has been researched.
        trigger=lambda w, ctx: _research_done(w, "basic_chemistry"),
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
        # Gate on the Solar Panels tech so the hint matches reality.
        trigger=lambda w, ctx: _research_done(w, "solar_panels"),
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
        # Only after Orbital Assembly research unlocks the silo.
        trigger=lambda w, ctx: _research_done(w, "orbital_assembly"),
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
        # Only fire after Petroleum Engineering has actually been
        # researched so the hint matches what the player can build.
        trigger=lambda w, ctx: _research_done(w, "petroleum_engineering"),
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
        id="pipe_intro",
        title=_text("pipe_intro")[0],
        lines=_text("pipe_intro")[1],
        trigger=lambda w, ctx: (
            _research_done(w, "petroleum_engineering")
            and _has_building(w, "OIL_DRILL")
        ),
        after="oil_drill_intro",
    ),
    _TutorialStep(
        id="oil_refinery_intro",
        title=_text("oil_refinery_intro")[0],
        lines=_text("oil_refinery_intro")[1],
        trigger=lambda w, ctx: (
            _research_done(w, "petroleum_engineering")
            and _has_building(w, "OIL_DRILL")
        ),
        after="pipe_intro",
    ),
    _TutorialStep(
        id="advanced_materials_intro",
        title=_text("advanced_materials_intro")[0],
        lines=_text("advanced_materials_intro")[1],
        trigger=lambda w, ctx: ctx.get("current_tier_level", 0) >= 5,
        after="petrochemical_intro",
    ),
    # ── Hard-mode (Evolution) combat tutorials ────────────────────
    _TutorialStep(
        id="first_raid",
        title=_text("first_raid")[0],
        lines=_text("first_raid")[1],
        # Fire once, on hard mode, immediately after the first wave
        # has been spawned (awakening cutscene counts as wave #1).
        trigger=lambda w, ctx: (
            _is_hard_mode(w) and _waves_triggered(w) >= 1
        ),
        after=None,
    ),
]


# ── Tutorial panel ───────────────────────────────────────────────

_PANEL_W = 320
_PAD = 14
_LINE_H = 20
_TITLE_H = 28
_BTN_W = 80
_BTN_H = 28

# Centered (modal) layout for the first few onboarding steps.
_CENTERED_PANEL_W = 640
_CENTERED_PAD = 28
_CENTERED_LINE_H = 32
_CENTERED_TITLE_H = 48
_CENTERED_BTN_W = 140
_CENTERED_BTN_H = 44
_CENTERED_IMAGE_MAX_H = 220

# Animated arrow.
_ARROW_LEN = 64
_ARROW_HEAD = 22
_ARROW_BOB_AMPL = 10.0
_ARROW_BOB_SPEED = 4.0


# Cache of loaded tutorial images keyed by relative asset path.
_IMAGE_CACHE: dict[str, pygame.Surface | None] = {}


def _load_tutorial_image(rel_path: str) -> pygame.Surface | None:
    cached = _IMAGE_CACHE.get(rel_path)
    if cached is not None or rel_path in _IMAGE_CACHE:
        return cached
    try:
        full = ASSET_DIR / rel_path
        surf = pygame.image.load(str(full)).convert_alpha()
    except Exception:
        surf = None
    _IMAGE_CACHE[rel_path] = surf
    return surf


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
        # Reference to the bottom bar so arrow hints can locate tabs
        # and building cards.  Wired by ``Game`` at construction.
        self._bottom_bar: "BottomBar | None" = None
        # Continuous time accumulator for the arrow bob animation.
        self._arrow_time: float = 0.0
        # Steps whose tooltip has been dismissed but whose arrow_fn
        # still has a non-None target.  These keep pointing at the UI
        # until the player completes the action they describe.
        self._lingering_arrows: list[_TutorialStep] = []

    def set_bottom_bar(self, bb: "BottomBar") -> None:
        self._bottom_bar = bb

    def layout(self, screen_w: int, screen_h: int) -> None:
        self._screen_w = screen_w
        self._screen_h = screen_h
        self.rect = pygame.Rect(16, 50, _PANEL_W, 100)

    def check_triggers(self, world: "World", ctx: dict) -> None:
        """Called each frame to see if a new tutorial step should show."""
        # Always advance the arrow animation clock so pointers wiggle
        # smoothly even while waiting for a trigger cooldown.
        self._arrow_time += ctx.get("dt", 1 / 60)
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
            # Keep the arrow alive after dismiss so the player still
            # has something to follow until they complete the click
            # path the tooltip described.
            if (
                self._current_step.arrow_fn is not None
                and self._current_step not in self._lingering_arrows
            ):
                self._lingering_arrows.append(self._current_step)
            self._current_step = None
            # Tightly paired hints skip the usual cooldown so the next
            # tip appears on the very next frame.
            self._cooldown = 0.0 if dismissed_id in _INSTANT_FOLLOWUP else 3.0
        else:
            self._cooldown = 3.0
        self._visible = False

    def draw(self, surface: pygame.Surface, world: "World") -> None:
        # Lingering arrows from previously dismissed steps.  Drawn
        # first so the active tooltip's arrow (if any) renders on top.
        if self._bottom_bar is not None and self._lingering_arrows:
            still_active: list[_TutorialStep] = []
            for step in self._lingering_arrows:
                # The current step's arrow is rendered below; skip it
                # here to avoid double-drawing.
                if step is self._current_step:
                    still_active.append(step)
                    continue
                try:
                    target = step.arrow_fn(self._bottom_bar)  # type: ignore[misc]
                except Exception:
                    target = None
                if target is None:
                    continue  # action complete \u2014 drop this arrow
                still_active.append(step)
                self._draw_arrow(surface, target)
            self._lingering_arrows = still_active

        if not self._visible or self._current_step is None:
            return
        step = self._current_step
        if step.centered:
            self._draw_centered(surface, step)
        else:
            self._draw_corner(surface, step)

        # Arrow pointing at the next UI target.  Drawn after the panel
        # so it overlays everything else.
        if step.arrow_fn is not None and self._bottom_bar is not None:
            try:
                target = step.arrow_fn(self._bottom_bar)
            except Exception:
                target = None
            if target is not None:
                self._draw_arrow(surface, target)

    def _draw_corner(
        self, surface: pygame.Surface, step: "_TutorialStep",
    ) -> None:
        font = Fonts.small()
        title_font = Fonts.label()

        rendered_lines = step.lines
        content_h = _TITLE_H + len(rendered_lines) * _LINE_H + _BTN_H + _PAD * 3

        x = 16
        y = 50
        w = _PANEL_W
        h = content_h
        if y + h > self._screen_h - 50:
            h = self._screen_h - 50 - y

        panel_rect = pygame.Rect(x, y, w, h)
        self.rect = panel_rect

        draw_panel_bg(surface, panel_rect, accent_edge="top")
        pygame.draw.line(
            surface, (220, 180, 60),
            (x + 1, y + 1), (x + w - 2, y + 1), 2,
        )

        cy = y + _PAD
        title_surf = title_font.render(step.title, True, (255, 215, 100))
        surface.blit(title_surf, (x + _PAD, cy))
        cy += _TITLE_H

        for line in rendered_lines:
            if not line:
                cy += _LINE_H // 2
                continue
            surf = font.render(line, True, UI_TEXT)
            surface.blit(surf, (x + _PAD, cy))
            cy += _LINE_H

        cy += _PAD // 2
        btn_x = x + w - _BTN_W - _PAD
        btn_y = min(cy, y + h - _BTN_H - _PAD // 2)
        self._btn_rect = pygame.Rect(btn_x, btn_y, _BTN_W, _BTN_H)
        self._draw_button(surface, self._btn_rect, font)

        done = len(self._dismissed)
        total = len(TUTORIAL_STEPS)
        counter = font.render(f"{done + 1} / {total}", True, UI_MUTED)
        surface.blit(counter, (x + _PAD, btn_y + (_BTN_H - counter.get_height()) // 2))

    def _draw_centered(
        self, surface: pygame.Surface, step: "_TutorialStep",
    ) -> None:
        body_font = Fonts.label()   # bigger body
        title_font = Fonts.title()  # bigger title
        btn_font = Fonts.label()

        w = min(_CENTERED_PANEL_W, self._screen_w - 80)
        inner_w = w - _CENTERED_PAD * 2

        # Word-wrap each body line to the inner width.
        wrapped: list[str] = []
        for line in step.lines:
            if not line:
                wrapped.append("")
                continue
            wrapped.extend(wrap_text(body_font, line, inner_w))

        # Optional image.
        img_surf: pygame.Surface | None = None
        if step.image:
            raw = _load_tutorial_image(step.image)
            if raw is not None:
                iw, ih = raw.get_size()
                # Scale to fit inside inner_w / _CENTERED_IMAGE_MAX_H,
                # preserving aspect ratio.
                scale = min(inner_w / iw, _CENTERED_IMAGE_MAX_H / ih, 1.0)
                if scale < 1.0:
                    img_surf = pygame.transform.smoothscale(
                        raw, (int(iw * scale), int(ih * scale)),
                    )
                else:
                    img_surf = raw

        body_h = len(wrapped) * _CENTERED_LINE_H
        img_h = (img_surf.get_height() + _CENTERED_PAD) if img_surf else 0
        h = (
            _CENTERED_PAD
            + _CENTERED_TITLE_H
            + body_h
            + img_h
            + _CENTERED_PAD
            + _CENTERED_BTN_H
            + _CENTERED_PAD
        )
        h = min(h, self._screen_h - 40)

        x = (self._screen_w - w) // 2
        y = (self._screen_h - h) // 2
        panel_rect = pygame.Rect(x, y, w, h)
        self.rect = panel_rect

        # Darken the rest of the screen so the modal really reads as
        # "read me before moving on".
        dim = pygame.Surface(
            (self._screen_w, self._screen_h), pygame.SRCALPHA,
        )
        dim.fill((0, 0, 0, 130))
        surface.blit(dim, (0, 0))

        draw_panel_bg(surface, panel_rect, accent_edge="top")
        pygame.draw.rect(
            surface, (220, 180, 60), panel_rect, width=3, border_radius=6,
        )

        cy = y + _CENTERED_PAD
        title_surf = title_font.render(step.title, True, (255, 215, 100))
        surface.blit(title_surf, (
            x + (w - title_surf.get_width()) // 2, cy,
        ))
        cy += _CENTERED_TITLE_H

        for line in wrapped:
            if not line:
                cy += _CENTERED_LINE_H // 2
                continue
            surf = body_font.render(line, True, UI_TEXT)
            surface.blit(surf, (
                x + (w - surf.get_width()) // 2, cy,
            ))
            cy += _CENTERED_LINE_H

        if img_surf is not None:
            cy += _CENTERED_PAD // 2
            surface.blit(img_surf, (
                x + (w - img_surf.get_width()) // 2, cy,
            ))
            cy += img_surf.get_height() + _CENTERED_PAD // 2

        # Button centered near the bottom.
        btn_y = y + h - _CENTERED_BTN_H - _CENTERED_PAD
        btn_x = x + (w - _CENTERED_BTN_W) // 2
        self._btn_rect = pygame.Rect(
            btn_x, btn_y, _CENTERED_BTN_W, _CENTERED_BTN_H,
        )
        self._draw_button(surface, self._btn_rect, btn_font)

        done = len(self._dismissed)
        total = len(TUTORIAL_STEPS)
        counter = Fonts.small().render(
            f"{done + 1} / {total}", True, UI_MUTED,
        )
        surface.blit(counter, (
            x + _CENTERED_PAD,
            btn_y + (_CENTERED_BTN_H - counter.get_height()) // 2,
        ))

    def _draw_button(
        self,
        surface: pygame.Surface,
        rect: pygame.Rect,
        font: pygame.font.Font,
    ) -> None:
        mx, my = pygame.mouse.get_pos()
        hover = rect.collidepoint(mx, my)
        bg = (80, 160, 80) if hover else (60, 130, 60)
        pygame.draw.rect(surface, bg, rect, border_radius=4)
        pygame.draw.rect(surface, (100, 200, 100), rect, 1, border_radius=4)
        label = font.render(TUTORIAL_DISMISS_BUTTON, True, (255, 255, 255))
        surface.blit(label, (
            rect.centerx - label.get_width() // 2,
            rect.centery - label.get_height() // 2,
        ))

    def _draw_arrow(
        self, surface: pygame.Surface, target: pygame.Rect,
    ) -> None:
        """Draw a bobbing arrow pointing down at *target*.

        The arrow sits above the target and pulses on the vertical
        axis to catch the eye.
        """
        bob = math.sin(self._arrow_time * _ARROW_BOB_SPEED) * _ARROW_BOB_AMPL
        tip_x = target.centerx
        tip_y = target.top - 6 + bob
        tail_y = tip_y - _ARROW_LEN
        if tail_y < 0:
            # Target is near the top of the screen \u2014 point upward
            # from below the element instead.
            tip_y = target.bottom + 6 - bob
            tail_y = tip_y + _ARROW_LEN
            head_dir = -1  # arrow points up
        else:
            head_dir = 1   # arrow points down

        color = (255, 210, 70)
        shadow = (40, 25, 0)

        # Shaft (draw shadow first for contrast against bright UI).
        pygame.draw.line(
            surface, shadow, (tip_x + 2, tail_y + 2), (tip_x + 2, tip_y + 2), 8,
        )
        pygame.draw.line(
            surface, color, (tip_x, tail_y), (tip_x, tip_y), 6,
        )

        # Arrowhead.
        h = _ARROW_HEAD
        if head_dir > 0:
            pts = [
                (tip_x, tip_y),
                (tip_x - h, tip_y - h),
                (tip_x + h, tip_y - h),
            ]
        else:
            pts = [
                (tip_x, tip_y),
                (tip_x - h, tip_y + h),
                (tip_x + h, tip_y + h),
            ]
        shadow_pts = [(px + 2, py + 2) for px, py in pts]
        pygame.draw.polygon(surface, shadow, shadow_pts)
        pygame.draw.polygon(surface, color, pts)

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
