"""Comprehensive in-game Help / Guide overlay for Hex Colony.

Replaces the legacy ``HelpOverlay`` (controls reference) and
``InfoGuideOverlay`` (multi-page guide).  Opened via the **Help**
button in the top-right of the screen, the **H** or **I** keys, or
``Escape`` to dismiss.

Content is **dynamic** and rebuilt every time the panel is shown:

* Buildings, recipes and tech nodes are filtered by the player's
  current tier and researched tech, so a fresh player only sees what
  they can actually use.  As they progress, more entries appear.
* Each entry includes everything a new player needs to act on it
  (cost, crafting station, inputs/outputs, prerequisites).
* Tier and research progress display live values so the panel can
  also serve as a "what should I do next" reference.

The overlay is intentionally self-contained: the only world/state
inputs it needs are passed via :meth:`set_state` from ``Game``
during construction.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import pygame

from compprog_pygame.games.hex_colony.buildings import (
    BUILDING_COSTS, BUILDING_HARVEST_RESOURCES, BUILDING_HOUSING,
    BUILDING_MAX_WORKERS, BUILDING_STORAGE_CAPACITY, BuildingType,
)
from compprog_pygame.games.hex_colony import params
from compprog_pygame.games.hex_colony.resources import (
    FLUID_RESOURCES, MATERIAL_RECIPES, RAW_RESOURCES, Resource,
)
from compprog_pygame.games.hex_colony.strings import (
    BUILDING_DESCRIPTIONS,
    HELP_BINDINGS,
    building_label,
    resource_name,
)
from compprog_pygame.games.hex_colony.tech_tree import (
    TECH_NODES,
    TECH_REQUIREMENTS,
    RESOURCE_TECH_REQUIREMENTS,
    TIER_BUILDING_REQUIREMENTS,
    TIERS,
    is_building_available,
    is_resource_available,
)
from compprog_pygame.games.hex_colony.ui import (
    Fonts,
    Panel,
    UI_ACCENT,
    UI_BAD,
    UI_BORDER,
    UI_MUTED,
    UI_OK,
    UI_OVERLAY,
    UI_TAB_ACTIVE,
    UI_TAB_HOVER,
    UI_TAB_INACTIVE,
    UI_TEXT,
    draw_panel_bg,
    set_tooltip,
)

if TYPE_CHECKING:
    from compprog_pygame.games.hex_colony.tech_tree import (
        TechTree, TierTracker,
    )
    from compprog_pygame.games.hex_colony.world import World


# ── Styling ──────────────────────────────────────────────────────

_PAGE_TAB_H = 32
_LINE_H = 22
_SECTION_GAP = 10
_MARGIN = 24
_PAD = 20

_HEADER_COLOR = (255, 215, 120)
_SUBHEADER_COLOR = (180, 220, 255)
_BAD_COLOR = (240, 130, 130)
_GOOD_COLOR = UI_OK


@dataclass
class _Line:
    """A single rendered text line in the help body."""

    text: str
    color: tuple[int, int, int] = UI_TEXT
    font_key: str = "body"          # "body" | "small" | "label" | "title"
    indent: int = 0                  # px


_PAGES: tuple[str, ...] = (
    "Getting Started",
    "This Tier",
    "Buildings",
    "Recipes",
    "Research",
    "Controls",
)

# One-line tooltip per page so first-time players know what each tab
# contains before clicking.
_PAGE_TOOLTIPS: dict[str, str] = {
    "Getting Started": (
        "First-time orientation: the core gameplay loop, the first "
        "buildings to place, and where to find more help."
    ),
    "This Tier": (
        "What you can do at your current tier, the goals to reach "
        "the next tier, and research that's ready right now."
    ),
    "Buildings": (
        "Every building you've unlocked: cost, crafting station, "
        "workers, housing, storage, and what it harvests."
    ),
    "Recipes": (
        "All raw resources, every crafted material with its inputs "
        "and time, and the placeable building recipes."
    ),
    "Research": (
        "Tech nodes grouped by status: ready to research, already "
        "researched, and locked.  Includes cost, time, and unlocks."
    ),
    "Controls": (
        "Keyboard and mouse reference for movement, building, and "
        "diagnostic overlays."
    ),
}


def _font_for(key: str) -> pygame.font.Font:
    if key == "title":
        return Fonts.title()
    if key == "label":
        return Fonts.label()
    if key == "small":
        return Fonts.small()
    return Fonts.body()


# ── Help button rect (drawn by ResourceBar; click handled here) ──

# The Game wires the resource bar so its Help button toggles this
# overlay; no global state is required.


# ── Overlay panel ────────────────────────────────────────────────

class HelpOverlay(Panel):
    """Comprehensive, tier-aware in-game guide."""

    def __init__(self) -> None:
        super().__init__()
        self.visible = False
        self.tech_tree: "TechTree | None" = None
        self.tier_tracker: "TierTracker | None" = None
        self._page: int = 0
        self._scroll: int = 0
        self._content_h: int = 0
        self._tab_rects: list[pygame.Rect] = []
        self._mouse_pos: tuple[int, int] = (0, 0)
        self._close_rect: pygame.Rect = pygame.Rect(0, 0, 0, 0)

    # ── Public API ───────────────────────────────────────────────

    def set_state(
        self,
        tech_tree: "TechTree | None",
        tier_tracker: "TierTracker | None",
    ) -> None:
        self.tech_tree = tech_tree
        self.tier_tracker = tier_tracker

    def toggle(self) -> None:
        self.visible = not self.visible
        if self.visible:
            self._scroll = 0

    def show(self) -> None:
        self.visible = True
        self._scroll = 0

    def hide(self) -> None:
        self.visible = False

    # ── Panel hooks ──────────────────────────────────────────────

    def layout(self, screen_w: int, screen_h: int) -> None:
        self.rect = pygame.Rect(0, 0, screen_w, screen_h)

    def draw(self, surface: pygame.Surface, world: "World") -> None:
        if not self.visible:
            return
        sw, sh = surface.get_size()

        overlay = pygame.Surface((sw, sh), pygame.SRCALPHA)
        overlay.fill(UI_OVERLAY)
        surface.blit(overlay, (0, 0))

        pw = min(820, sw - 60)
        ph = min(640, sh - 80)
        px = (sw - pw) // 2
        py = (sh - ph) // 2
        panel = pygame.Rect(px, py, pw, ph)
        draw_panel_bg(surface, panel, accent_edge="top")

        # Title.
        title_surf = Fonts.title().render("Help & Guide", True, UI_TEXT)
        surface.blit(title_surf, (px + _PAD, py + 10))

        # Close button (top-right inside panel).
        sz = 24
        self._close_rect = pygame.Rect(
            px + pw - sz - 10, py + 12, sz, sz,
        )
        hover_close = self._close_rect.collidepoint(self._mouse_pos)
        bg_col = (60, 20, 20, 230) if hover_close else (34, 34, 40, 200)
        bg = pygame.Surface((sz, sz), pygame.SRCALPHA)
        bg.fill(bg_col)
        surface.blit(bg, self._close_rect.topleft)
        pygame.draw.rect(
            surface, (200, 80, 80), self._close_rect,
            width=2, border_radius=4,
        )
        x_font = Fonts.label()
        x_surf = x_font.render("\u00d7", True, (255, 200, 200))
        surface.blit(x_surf, (
            self._close_rect.centerx - x_surf.get_width() // 2,
            self._close_rect.centery - x_surf.get_height() // 2 - 1,
        ))

        # Page tabs.
        self._tab_rects = []
        tx = px + _PAD
        ty = py + 50
        tab_font = Fonts.small()
        for i, page_title in enumerate(_PAGES):
            label = tab_font.render(page_title, True, UI_TEXT)
            tw = label.get_width() + 18
            tab_rect = pygame.Rect(tx, ty, tw, _PAGE_TAB_H)
            active = i == self._page
            hovered = tab_rect.collidepoint(self._mouse_pos)
            if active:
                bg_color = UI_TAB_ACTIVE
            elif hovered:
                bg_color = UI_TAB_HOVER
            else:
                bg_color = UI_TAB_INACTIVE
            tab_bg = pygame.Surface((tab_rect.w, tab_rect.h), pygame.SRCALPHA)
            tab_bg.fill(bg_color)
            surface.blit(tab_bg, tab_rect.topleft)
            border = UI_ACCENT if active else UI_BORDER
            pygame.draw.rect(surface, border, tab_rect, width=1, border_radius=3)
            surface.blit(label, (
                tab_rect.centerx - label.get_width() // 2,
                tab_rect.centery - label.get_height() // 2,
            ))
            self._tab_rects.append(tab_rect)
            tx += tw + 4
            if hovered:
                tip = _PAGE_TOOLTIPS.get(page_title)
                if tip:
                    set_tooltip(tip, title=page_title)

        # Content area.
        content_top = ty + _PAGE_TAB_H + 8
        content_rect = pygame.Rect(
            px + _MARGIN, content_top,
            pw - _MARGIN * 2 - 16, py + ph - content_top - 38,
        )
        prev_clip = surface.get_clip()
        surface.set_clip(content_rect)

        lines = self._build_lines(world)
        y = content_rect.y - self._scroll
        for line in lines:
            if not line.text:
                y += _LINE_H // 2
                continue
            font = _font_for(line.font_key)
            surf = font.render(line.text, True, line.color)
            surface.blit(surf, (content_rect.x + line.indent, y))
            y += _LINE_H

        self._content_h = max(0, int(y + self._scroll - content_rect.y))
        surface.set_clip(prev_clip)

        # Scrollbar.
        if self._content_h > content_rect.h:
            track_x = content_rect.right + 4
            track = pygame.Rect(track_x, content_rect.y, 8, content_rect.h)
            pygame.draw.rect(surface, (40, 50, 70), track, border_radius=4)
            ratio = content_rect.h / self._content_h
            thumb_h = max(20, int(track.h * ratio))
            max_scroll = max(1, self._content_h - content_rect.h)
            offset = int(
                (track.h - thumb_h) * (self._scroll / max_scroll),
            )
            thumb = pygame.Rect(track_x, track.y + offset, 8, thumb_h)
            pygame.draw.rect(surface, UI_ACCENT, thumb, border_radius=4)

        # Hint at bottom.
        hint_font = Fonts.small()
        hint = hint_font.render(
            "Scroll to read \u2022 click tabs to switch \u2022 H or Esc to close",
            True, UI_MUTED,
        )
        surface.blit(hint, (
            px + (pw - hint.get_width()) // 2,
            py + ph - hint.get_height() - 12,
        ))

    def handle_event(self, event: pygame.event.Event) -> bool:
        if not self.visible:
            return False
        if event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_h, pygame.K_i, pygame.K_ESCAPE):
                self.visible = False
                return True
            if event.key == pygame.K_LEFT:
                self._page = max(0, self._page - 1)
                self._scroll = 0
                return True
            if event.key == pygame.K_RIGHT:
                self._page = min(len(_PAGES) - 1, self._page + 1)
                self._scroll = 0
                return True
        if event.type == pygame.MOUSEMOTION:
            self._mouse_pos = event.pos
            return True
        if event.type == pygame.MOUSEWHEEL:
            self._scroll = max(0, self._scroll - event.y * 36)
            return True
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self._close_rect.collidepoint(event.pos):
                self.visible = False
                return True
            for i, tab_rect in enumerate(self._tab_rects):
                if tab_rect.collidepoint(event.pos):
                    self._page = i
                    self._scroll = 0
                    return True
            return True  # consume click
        return True  # consume all events while visible

    # ── Content builders ─────────────────────────────────────────

    def _current_tier_level(self) -> int:
        return self.tier_tracker.current_tier if self.tier_tracker else 0

    def _build_lines(self, world: "World") -> list[_Line]:
        page = _PAGES[self._page]
        if page == "Getting Started":
            return self._page_getting_started()
        if page == "This Tier":
            return self._page_this_tier(world)
        if page == "Buildings":
            return self._page_buildings()
        if page == "Recipes":
            return self._page_recipes()
        if page == "Research":
            return self._page_research()
        if page == "Controls":
            return self._page_controls()
        return []

    # -- Page: Getting Started -----------------------------------

    def _page_getting_started(self) -> list[_Line]:
        lvl = self._current_tier_level()
        lines: list[_Line] = []
        lines.append(_Line("Welcome to RePioneer", _HEADER_COLOR, "label"))
        lines.append(_Line(
            "You crash-landed on an alien world. Build food production,",
        ))
        lines.append(_Line(
            "expand housing, climb the Tier ladder, and finally",
        ))
        lines.append(_Line(
            "assemble a Rocket to escape the planet.",
        ))
        lines.append(_Line(""))
        lines.append(_Line("Core loop", _SUBHEADER_COLOR, "label"))
        lines.append(_Line("\u2022 Place harvesters next to the resource you want."))
        lines.append(_Line(
            "\u2022 Connect every building back to the Ship Wreckage with Paths",
            indent=14,
        ))
        lines.append(_Line(
            "  \u2014 if it isn't on a network, no workers will reach it.",
            indent=14,
        ))
        lines.append(_Line(
            "\u2022 Logistics workers (one per ~3 buildings) automatically",
        ))
        lines.append(_Line(
            "  shuttle resources from suppliers to consumers.",
            indent=14,
        ))
        lines.append(_Line(
            "\u2022 Click a building to assign / unassign workers and pick recipes."
        ))
        lines.append(_Line(""))
        lines.append(_Line("Recommended first builds", _SUBHEADER_COLOR, "label"))
        lines.append(_Line("1. Gatherer on a fiber patch  \u2192 Food + Fiber"))
        lines.append(_Line("2. Woodcutter on a forest      \u2192 Wood"))
        lines.append(_Line("3. Quarry on a stone deposit   \u2192 Stone"))
        lines.append(_Line("4. Path: connect everything to the Ship Wreckage"))
        lines.append(_Line("5. Habitat to grow your population"))
        lines.append(_Line(""))
        lines.append(_Line("Where to read more", _SUBHEADER_COLOR, "label"))
        lines.append(_Line("\u2022 \u201cThis Tier\u201d \u2014 what you can do right now."))
        lines.append(_Line("\u2022 \u201cBuildings\u201d \u2014 cost, station, role for everything unlocked."))
        lines.append(_Line("\u2022 \u201cRecipes\u201d \u2014 inputs, outputs and craft times."))
        lines.append(_Line("\u2022 \u201cResearch\u201d \u2014 what's ready to research and what it unlocks."))
        lines.append(_Line(""))
        lines.append(_Line(
            f"You are currently on Tier {lvl}: "
            f"{TIERS[lvl].name if lvl < len(TIERS) else 'Max'}.",
            _HEADER_COLOR,
        ))
        return lines

    # -- Page: This Tier -----------------------------------------

    def _page_this_tier(self, world: "World") -> list[_Line]:
        lines: list[_Line] = []
        lvl = self._current_tier_level()
        if lvl >= len(TIERS):
            lines.append(_Line("Maximum tier reached", _HEADER_COLOR, "label"))
            return lines
        tier = TIERS[lvl]
        lines.append(_Line(
            f"Tier {lvl}: {tier.name}", _HEADER_COLOR, "label",
        ))
        lines.append(_Line(tier.description, UI_MUTED))
        lines.append(_Line(""))

        # Buildings/resources unlocked AT this tier (and via tech in this tier).
        lines.append(_Line(
            "Unlocked this tier (and earlier)", _SUBHEADER_COLOR, "label",
        ))
        unlocked = [
            bt for bt in BuildingType
            if is_building_available(bt, self.tech_tree, self.tier_tracker)
            and bt not in (BuildingType.CAMP, BuildingType.HOUSE,
                           BuildingType.TRIBAL_CAMP)
        ]
        if unlocked:
            for bt in unlocked:
                lines.append(_Line(
                    f"\u2022 {building_label(bt.name)}",
                    UI_TEXT, indent=14,
                ))
        else:
            lines.append(_Line("(none)", UI_MUTED, indent=14))
        lines.append(_Line(""))

        # Goals to reach next tier.
        if lvl + 1 < len(TIERS):
            next_tier = TIERS[lvl + 1]
            lines.append(_Line(
                f"Next \u2192 Tier {lvl + 1}: {next_tier.name}",
                _SUBHEADER_COLOR, "label",
            ))
            progress = (
                self.tier_tracker.check_requirements(world)
                if self.tier_tracker is not None else {}
            )
            if progress:
                for name, (cur, req) in progress.items():
                    done = cur >= req
                    color = _GOOD_COLOR if done else UI_TEXT
                    mark = "\u2713" if done else "\u2718"
                    lines.append(_Line(
                        f"  {mark} {name}: {int(cur)} / {int(req)}",
                        color, indent=14,
                    ))
            else:
                lines.append(_Line("  (no requirements listed)", UI_MUTED))
            lines.append(_Line(""))
            # Buildings unlocked at the *next* tier.
            new_buildings = [
                bt for bt in next_tier.unlocks_buildings
            ]
            if new_buildings:
                lines.append(_Line(
                    "Tier reward (placeable once you advance):",
                    _SUBHEADER_COLOR,
                ))
                for bt in new_buildings:
                    lines.append(_Line(
                        f"\u2022 {building_label(bt.name)}",
                        UI_TEXT, indent=14,
                    ))
                lines.append(_Line(""))

        # Active research / what's available now.
        if self.tech_tree is not None:
            available = self.tech_tree.available_techs()
            if available:
                lines.append(_Line(
                    "Research ready now (open the Research Center):",
                    _SUBHEADER_COLOR, "label",
                ))
                for k in available:
                    node = TECH_NODES[k]
                    cost = ", ".join(
                        f"{int(v)} {resource_name(r.name)}"
                        for r, v in node.cost.items()
                    ) or "Free"
                    unlocks = []
                    unlocks.extend(building_label(b.name) for b in node.unlocks)
                    unlocks.extend(
                        resource_name(r.name) for r in node.unlock_resources
                    )
                    unlock_txt = ", ".join(unlocks) or "(no unlock!)"
                    lines.append(_Line(
                        f"\u2022 {node.name}  \u2014  {cost}  \u2014  {int(node.time)}s",
                        indent=14,
                    ))
                    lines.append(_Line(
                        f"   unlocks: {unlock_txt}",
                        UI_MUTED, "small", indent=22,
                    ))
                lines.append(_Line(""))

        # Tips for this tier.
        lines.append(_Line("Tier tips", _SUBHEADER_COLOR, "label"))
        for tip in _TIER_TIPS.get(lvl, ()):
            lines.append(_Line(f"\u2022 {tip}"))
        return lines

    # -- Page: Buildings -----------------------------------------

    def _page_buildings(self) -> list[_Line]:
        lines: list[_Line] = []
        lines.append(_Line(
            "Every building you've unlocked", _HEADER_COLOR, "label",
        ))
        lines.append(_Line(
            "Cost is paid once when placed. Most placeables must be",
            UI_MUTED,
        ))
        lines.append(_Line(
            "crafted at a station first \u2014 the station appears below the cost.",
            UI_MUTED,
        ))
        lines.append(_Line(""))
        # Group by category that BuildingsTabContent uses.
        groups: list[tuple[str, list[BuildingType]]] = [
            ("Housing & Science", [
                BuildingType.HABITAT, BuildingType.RESEARCH_CENTER,
            ]),
            ("Resource gathering", [
                BuildingType.WOODCUTTER, BuildingType.QUARRY,
                BuildingType.GATHERER, BuildingType.FARM,
                BuildingType.WELL, BuildingType.MINING_MACHINE,
                BuildingType.OIL_DRILL, BuildingType.SOLAR_ARRAY,
            ]),
            ("Crafting & Storage", [
                BuildingType.WORKSHOP, BuildingType.FORGE,
                BuildingType.ASSEMBLER, BuildingType.REFINERY,
                BuildingType.CHEMICAL_PLANT, BuildingType.OIL_REFINERY,
                BuildingType.STORAGE, BuildingType.FLUID_TANK,
            ]),
            ("Logistics & Defense", [
                BuildingType.PATH, BuildingType.BRIDGE,
                BuildingType.CONVEYOR, BuildingType.PIPE,
                BuildingType.WALL,
            ]),
            ("Endgame", [BuildingType.ROCKET_SILO]),
        ]
        any_shown = False
        for cat_name, types in groups:
            visible = [
                bt for bt in types
                if is_building_available(bt, self.tech_tree, self.tier_tracker)
            ]
            if not visible:
                continue
            any_shown = True
            lines.append(_Line(cat_name, _SUBHEADER_COLOR, "label"))
            for bt in visible:
                lines.extend(self._building_block(bt))
                lines.append(_Line(""))
        if not any_shown:
            lines.append(_Line(
                "No buildings unlocked yet \u2014 keep playing!", UI_MUTED,
            ))
        # Locked preview list.
        locked = self._locked_buildings_preview()
        if locked:
            lines.append(_Line(""))
            lines.append(_Line(
                "Locked \u2014 unlock these next", _SUBHEADER_COLOR, "label",
            ))
            for bt, why in locked:
                lines.append(_Line(
                    f"\u2022 {building_label(bt.name)}  \u2014  {why}",
                    UI_MUTED, indent=14,
                ))
        return lines

    def _building_block(self, bt: BuildingType) -> list[_Line]:
        lines: list[_Line] = []
        lines.append(_Line(
            building_label(bt.name), UI_TEXT, "label", indent=14,
        ))
        desc = BUILDING_DESCRIPTIONS.get(bt.name)
        if desc:
            lines.append(_Line(desc, UI_MUTED, "small", indent=22))
        cost = BUILDING_COSTS.get(bt)
        if cost and cost.costs:
            cost_txt = ", ".join(
                f"{v} {resource_name(r.name)}" for r, v in cost.costs.items()
            )
            lines.append(_Line(
                f"Cost: {cost_txt}", UI_TEXT, "small", indent=22,
            ))
        else:
            lines.append(_Line("Cost: free", UI_MUTED, "small", indent=22))
        station_name = params.BUILDING_RECIPE_STATION.get(bt.name)
        if station_name:
            lines.append(_Line(
                f"Crafted at: {building_label(station_name)}",
                UI_TEXT, "small", indent=22,
            ))
        # Workers / housing / storage details.
        details: list[str] = []
        mw = BUILDING_MAX_WORKERS.get(bt, 0)
        if mw > 0:
            details.append(f"{mw} max worker{'s' if mw != 1 else ''}")
        h = BUILDING_HOUSING.get(bt, 0)
        if h > 0:
            details.append(f"houses {h}")
        s = BUILDING_STORAGE_CAPACITY.get(bt, 0)
        if s > 0:
            details.append(f"storage {s}")
        if details:
            lines.append(_Line(
                "  " + "  \u2022  ".join(details),
                UI_MUTED, "small", indent=22,
            ))
        # If it's a harvester, show what it harvests.
        harvests = BUILDING_HARVEST_RESOURCES.get(bt)
        if harvests:
            txt = ", ".join(resource_name(r.name) for r in harvests)
            lines.append(_Line(
                f"Harvests: {txt}", UI_TEXT, "small", indent=22,
            ))
        return lines

    def _locked_buildings_preview(self) -> list[tuple[BuildingType, str]]:
        out: list[tuple[BuildingType, str]] = []
        for bt in BuildingType:
            if bt in (BuildingType.CAMP, BuildingType.HOUSE,
                      BuildingType.TRIBAL_CAMP):
                continue
            if is_building_available(bt, self.tech_tree, self.tier_tracker):
                continue
            tier_req = TIER_BUILDING_REQUIREMENTS.get(bt)
            tech_req = TECH_REQUIREMENTS.get(bt)
            reasons = []
            if tier_req is not None:
                reasons.append(
                    f"requires Tier {tier_req}: {TIERS[tier_req].name}"
                )
            if tech_req is not None:
                reasons.append(f"requires research: {TECH_NODES[tech_req].name}")
            if not reasons:
                continue
            out.append((bt, " & ".join(reasons)))
            if len(out) >= 12:
                break
        return out

    # -- Page: Recipes -------------------------------------------

    def _collect_unlockable_recipes(
        self,
    ) -> list[tuple[str, tuple[int, int, int], list[tuple[Resource, object, str]]]]:
        """Group locked material recipes into ``(label, color, items)``.

        Three buckets:
          * "Ready to research now" — the unlock node has all
            prerequisites met (i.e. ``can_research`` is True).
          * "Coming soon" — the unlock node is one step away (its
            prerequisites are either researched or themselves
            ``can_research``-able).
          * "Future tiers" — everything else still locked.

        Items inside a bucket are sorted by node name then resource
        name for stability.
        """
        if self.tech_tree is None:
            return []
        tt = self.tech_tree

        ready: list[tuple[Resource, object, str]] = []
        soon: list[tuple[Resource, object, str]] = []
        later: list[tuple[Resource, object, str]] = []

        for res, recipe in MATERIAL_RECIPES.items():
            if is_resource_available(res, tt, self.tier_tracker):
                continue
            node_key = RESOURCE_TECH_REQUIREMENTS.get(res)
            if node_key is None or node_key not in TECH_NODES:
                continue
            node = TECH_NODES[node_key]
            if tt.can_research(node_key):
                ready.append((res, recipe, node_key))
            elif all(
                p in tt.researched or tt.can_research(p)
                for p in node.prerequisites
            ):
                soon.append((res, recipe, node_key))
            else:
                later.append((res, recipe, node_key))

        def _sort(items):
            return sorted(
                items, key=lambda x: (TECH_NODES[x[2]].name, x[0].name),
            )

        return [
            ("Ready to research now", _GOOD_COLOR, _sort(ready)),
            ("Coming soon (one tech away)", _SUBHEADER_COLOR, _sort(soon)),
            ("Future tiers", UI_MUTED, _sort(later)),
        ]

    def _page_recipes(self) -> list[_Line]:
        lines: list[_Line] = []
        lines.append(_Line("Raw resources", _HEADER_COLOR, "label"))
        lines.append(_Line(
            "Harvested directly from the map by placing the right",
            UI_MUTED,
        ))
        lines.append(_Line(
            "harvester adjacent to the matching terrain.", UI_MUTED,
        ))
        lines.append(_Line(""))
        terrain_to_harvester = {
            Resource.WOOD:   "Woodcutter on Forest / Dense Forest",
            Resource.STONE:  "Quarry adjacent to Mountain / Stone Deposit",
            Resource.FIBER:  "Gatherer on Fiber Patch / Grass",
            Resource.FOOD:   "Gatherer on Fiber, Farm anywhere; Well boosts farms",
            Resource.IRON:   "Quarry adjacent to Iron Vein (or Mining Machine)",
            Resource.COPPER: "Quarry adjacent to Copper Vein (or Mining Machine)",
            Resource.OIL:    "Oil Drill placed directly on an Oil Deposit",
        }
        for r in RAW_RESOURCES:
            if not is_resource_available(r, self.tech_tree, self.tier_tracker):
                continue
            lines.append(_Line(
                f"\u2022 {resource_name(r.name)}", UI_TEXT, "body", indent=14,
            ))
            lines.append(_Line(
                f"   {terrain_to_harvester.get(r, 'Unknown')}",
                UI_MUTED, "small", indent=22,
            ))
        lines.append(_Line(""))
        lines.append(_Line(
            "Crafted materials", _HEADER_COLOR, "label",
        ))
        lines.append(_Line(
            "Each material is crafted at one station from the inputs",
            UI_MUTED,
        ))
        lines.append(_Line(
            "shown below. Click the station and pick the recipe.", UI_MUTED,
        ))
        lines.append(_Line(""))
        # Group by station.
        by_station: dict[str, list[tuple[Resource, object]]] = {}
        for res, recipe in MATERIAL_RECIPES.items():
            if not is_resource_available(res, self.tech_tree, self.tier_tracker):
                continue
            by_station.setdefault(recipe.station, []).append((res, recipe))
        for station_name in sorted(by_station):
            lines.append(_Line(
                f"At {building_label(station_name)}",
                _SUBHEADER_COLOR, "label",
            ))
            for res, recipe in by_station[station_name]:
                inputs_txt = ", ".join(
                    f"{v} {resource_name(r.name)}"
                    for r, v in recipe.inputs.items()
                ) or "(none)"
                fluid_note = (
                    "  [fluid \u2014 needs Pipes]"
                    if res in FLUID_RESOURCES else ""
                )
                lines.append(_Line(
                    (
                        f"\u2022 {recipe.output_amount} \u00d7 "
                        f"{resource_name(res.name)}{fluid_note}"
                    ),
                    UI_TEXT, "body", indent=14,
                ))
                lines.append(_Line(
                    f"   needs {inputs_txt}  \u2014  {int(recipe.time)}s",
                    UI_MUTED, "small", indent=22,
                ))
            lines.append(_Line(""))

        # ── Locked recipes that the player could unlock right now ──
        # Surface every material that *would* be available if the
        # player researched a specific node — so they know which tech
        # to chase to expand their crafting options.  Only show
        # recipes whose unlock node is either already available to
        # research or whose prerequisites are themselves close
        # (researched / available).  This keeps the list focused on
        # near-term goals rather than dumping the entire end-game.
        locked_groups = self._collect_unlockable_recipes()
        if locked_groups:
            lines.append(_Line(
                "Locked \u2014 unlock by researching",
                _HEADER_COLOR, "label",
            ))
            lines.append(_Line(
                "Each row shows the recipe you'd gain and the tech",
                UI_MUTED,
            ))
            lines.append(_Line(
                "node that unlocks it.  Open the Tech Tree to begin.",
                UI_MUTED,
            ))
            lines.append(_Line(""))
            for status_label, group_color, items in locked_groups:
                if not items:
                    continue
                lines.append(_Line(
                    status_label, group_color, "label",
                ))
                for res, recipe, node_key in items:
                    node = TECH_NODES.get(node_key)
                    node_name = node.name if node else node_key
                    fluid_note = (
                        "  [fluid \u2014 needs Pipes]"
                        if res in FLUID_RESOURCES else ""
                    )
                    lines.append(_Line(
                        (
                            f"\u2022 {recipe.output_amount} \u00d7 "
                            f"{resource_name(res.name)}"
                            f"{fluid_note}  ("
                            f"{building_label(recipe.station)})"
                        ),
                        UI_TEXT, "body", indent=14,
                    ))
                    lines.append(_Line(
                        f"   research: {node_name}",
                        _SUBHEADER_COLOR, "small", indent=22,
                    ))
                lines.append(_Line(""))

        # ── Placeable building recipes, grouped by station ─────
        lines.append(_Line(
            "Buildings crafted at a station", _HEADER_COLOR, "label",
        ))
        lines.append(_Line(
            "These are constructed by workers at the listed station,",
            UI_MUTED,
        ))
        lines.append(_Line(
            "then carried out and placed on the map.", UI_MUTED,
        ))
        lines.append(_Line(""))
        buildings_by_station: dict[str, list[BuildingType]] = {}
        for bt in BuildingType:
            if bt in (BuildingType.CAMP, BuildingType.TRIBAL_CAMP):
                continue
            if not is_building_available(bt, self.tech_tree, self.tier_tracker):
                continue
            st = params.BUILDING_RECIPE_STATION.get(bt.name)
            if not st:
                continue
            buildings_by_station.setdefault(st, []).append(bt)
        for station_name in sorted(buildings_by_station):
            lines.append(_Line(
                f"At {building_label(station_name)}",
                _SUBHEADER_COLOR, "label",
            ))
            for bt in sorted(
                buildings_by_station[station_name], key=lambda b: b.name,
            ):
                cost = BUILDING_COSTS.get(bt)
                cost_items = cost.costs.items() if cost else ()
                cost_txt = ", ".join(
                    f"{v} {resource_name(r.name)}"
                    for r, v in cost_items
                ) or "Free"
                lines.append(_Line(
                    f"\u2022 {building_label(bt.name)}",
                    UI_TEXT, "body", indent=14,
                ))
                lines.append(_Line(
                    f"   needs {cost_txt}",
                    UI_MUTED, "small", indent=22,
                ))
            lines.append(_Line(""))
        return lines

    # -- Page: Research ------------------------------------------

    def _page_research(self) -> list[_Line]:
        lines: list[_Line] = []
        lines.append(_Line("Research overview", _HEADER_COLOR, "label"))
        lines.append(_Line(
            "Build a Research Center, click it, and select a node to",
            UI_MUTED,
        ))
        lines.append(_Line(
            "research. Workers consume resources over time to complete it.",
            UI_MUTED,
        ))
        lines.append(_Line(""))
        if self.tech_tree is None:
            return lines
        done = self.tech_tree.researched
        available_keys = set(self.tech_tree.available_techs())

        def _block(title: str, keys: list[str], colour: tuple) -> None:
            if not keys:
                return
            lines.append(_Line(title, colour, "label"))
            for k in keys:
                node = TECH_NODES[k]
                cost = ", ".join(
                    f"{int(v)} {resource_name(r.name)}"
                    for r, v in node.cost.items()
                ) or "Free"
                lines.append(_Line(
                    f"\u2022 {node.name}  \u2014  {cost}  \u2014  {int(node.time)}s",
                    UI_TEXT, "body", indent=14,
                ))
                if node.description:
                    lines.append(_Line(
                        f"   {node.description}",
                        UI_MUTED, "small", indent=22,
                    ))
                unlocks: list[str] = []
                unlocks.extend(building_label(b.name) for b in node.unlocks)
                unlocks.extend(
                    resource_name(r.name) for r in node.unlock_resources
                )
                if unlocks:
                    lines.append(_Line(
                        f"   unlocks: {', '.join(unlocks)}",
                        _SUBHEADER_COLOR, "small", indent=22,
                    ))
                if node.prerequisites:
                    pr = ", ".join(
                        TECH_NODES[p].name for p in node.prerequisites
                        if p in TECH_NODES
                    )
                    lines.append(_Line(
                        f"   needs: {pr}", UI_MUTED, "small", indent=22,
                    ))
            lines.append(_Line(""))

        researched_keys = sorted(done, key=lambda k: TECH_NODES[k].name)
        ready_keys = sorted(available_keys, key=lambda k: TECH_NODES[k].name)
        locked_keys = sorted(
            (k for k in TECH_NODES if k not in done and k not in available_keys),
            key=lambda k: TECH_NODES[k].name,
        )

        _block("Ready to research now", ready_keys, _GOOD_COLOR)
        _block("Already researched", researched_keys, UI_MUTED)
        _block("Locked (prerequisites pending)", locked_keys, _BAD_COLOR)
        return lines

    # -- Page: Controls ------------------------------------------

    def _page_controls(self) -> list[_Line]:
        lines: list[_Line] = []
        lines.append(_Line("Controls reference", _HEADER_COLOR, "label"))
        lines.append(_Line(""))
        for key, desc in HELP_BINDINGS:
            lines.append(_Line(
                f"  {key:<18}{desc}", UI_TEXT, "body", indent=14,
            ))
        lines.append(_Line(""))
        lines.append(_Line("Logistics tip", _SUBHEADER_COLOR, "label"))
        lines.append(_Line(
            "Hold Alt to overlay supply/demand arrows on the selected",
        ))
        lines.append(_Line(
            "building \u2014 useful for diagnosing why a workshop is starving.",
        ))
        return lines


# Tier-specific advice surfaced on the "This Tier" page.
_TIER_TIPS: dict[int, tuple[str, ...]] = {
    0: (
        "Connect every harvester to the Ship Wreckage with Paths.",
        "Watch your Food: a starving colony shrinks fast.",
    ),
    1: (
        "Place a Storage building so excess Wood/Stone doesn't clog your harvesters.",
        "Build extra Habitats well before the population cap pinches.",
    ),
    2: (
        "Research Metallurgy to start smelting Iron and Copper Bars.",
        "Workshops can craft Workshops \u2014 keep at least one free for buildings.",
    ),
    3: (
        "Stockpile Bricks and Concrete \u2014 you'll need them for Tier 4 / 5.",
        "Mining Machines burn Charcoal; queue a Forge with the Charcoal recipe.",
    ),
    4: (
        "Conveyors double walking speed; lay them along your busiest routes.",
        "The Chemical Plant is the only path to Plastic and Rocket Fuel.",
    ),
    5: (
        "Oil Drills sit ON oil tiles; connect them to refineries with Pipes.",
        "Workers can't carry fluids \u2014 plan pipe layouts ahead of time.",
    ),
    6: (
        "Cluster Solar Arrays around your busiest crafting hubs (+25% each).",
        "Batteries and Advanced Circuits gate the rest of the tech tree.",
    ),
    7: (
        "Rocket Parts need Steel, Electronics and Reinforced Concrete.",
        "Multiple Assemblers crafting in parallel will make the launch trivial.",
    ),
}


__all__ = ["HelpOverlay"]
