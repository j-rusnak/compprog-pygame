"""In-game guide / info overlay for Hex Colony.

Multi-page overlay toggled with the **I** key.  Each page covers a
different facet of the game so new players can learn the mechanics
without leaving the session.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pygame

from compprog_pygame.games.hex_colony.ui import (
    Fonts,
    Panel,
    UI_ACCENT,
    UI_BORDER,
    UI_MUTED,
    UI_OVERLAY,
    UI_TAB_ACTIVE,
    UI_TAB_HOVER,
    UI_TAB_INACTIVE,
    UI_TEXT,
    draw_panel_bg,
)

if TYPE_CHECKING:
    from compprog_pygame.games.hex_colony.world import World

# ── Page data ────────────────────────────────────────────────────
# Each page is (title, list-of-lines).  Lines starting with "#" are
# rendered as section headers; others as body text.

_PAGES: list[tuple[str, list[str]]] = [
    ("Getting Started", [
        "# Welcome to Hex Colony!",
        "You've crash-landed on an alien world.  Build a thriving",
        "colony by harvesting resources, constructing buildings,",
        "and managing your growing population.",
        "",
        "# First Steps",
        "1. Place Paths to connect your Camp to resource tiles.",
        "2. Build a Woodcutter on a forest tile for Wood.",
        "3. Build a Quarry on a mountain tile for Stone.",
        "4. Build a Gatherer on a plains tile for Fiber.",
        "5. Place a Storage building to stockpile excess goods.",
        "6. Build a Habitat to house more colonists.",
        "",
        "# Tips",
        "\u2022 Buildings must be connected to the Camp by Paths.",
        "\u2022 Workers are assigned automatically (see Workers tab).",
        "\u2022 Hold Alt to see the resource overlay on the map.",
    ]),
    ("Buildings", [
        "# Harvesting Buildings",
        "\u2022 Woodcutter \u2014 harvests Wood from forests.",
        "\u2022 Quarry \u2014 harvests Stone (or ores) from mountains.",
        "\u2022 Gatherer \u2014 harvests Fiber from plains.",
        "\u2022 Farm \u2014 produces Food (requires research).",
        "\u2022 Well \u2014 produces Food from water tiles (requires research).",
        "",
        "# Production Buildings",
        "\u2022 Workshop \u2014 crafts materials and buildings from recipes.",
        "\u2022 Forge \u2014 smelts metals and crafts advanced items.",
        "\u2022 Assembler \u2014 assembles complex components (Tier 2).",
        "\u2022 Refinery \u2014 processes raw ores into metals (requires research).",
        "\u2022 Mining Machine \u2014 deep-mines resources (Tier 2).",
        "",
        "# Infrastructure",
        "\u2022 Path / Bridge \u2014 connects buildings into a network.",
        "\u2022 Wall \u2014 decorative barrier, blocks pathfinding.",
        "\u2022 Storage \u2014 stockpiles resources for the network.",
        "\u2022 Habitat \u2014 houses colonists; more residents = growth.",
        "\u2022 Research Center \u2014 unlocks new technologies.",
    ]),
    ("Resources & Crafting", [
        "# Raw Resources",
        "\u2022 Wood \u2014 from Woodcutters on forest tiles.",
        "\u2022 Stone \u2014 from Quarries on mountain tiles.",
        "\u2022 Fiber \u2014 from Gatherers on plains.",
        "\u2022 Food \u2014 from Farms, Wells, or Gatherers.",
        "",
        "# Crafted Materials",
        "Workshops, Forges, and Assemblers transform raw",
        "resources into processed materials.  Set a recipe on",
        "the building via its info panel (click the building).",
        "",
        "# Logistics",
        "Logistics workers automatically move resources between",
        "buildings in the same network.  They pick up from",
        "suppliers and deliver to consumers based on the",
        "demand and supply priority hierarchies.",
        "",
        "# Building Recipes",
        "Some buildings can craft other buildings as items.",
        "The crafted building appears in your inventory and",
        "can be placed on the map without additional cost.",
    ]),
    ("Workers & Logistics", [
        "# Worker Assignment",
        "Workers are assigned to buildings based on the priority",
        "hierarchy in the Workers tab.  Higher-tier buildings are",
        "staffed first.  Drag cards in the Edit Hierarchy overlay",
        "to re-order priorities.",
        "",
        "# Auto Mode",
        "By default, worker assignment is automatic: all buildings",
        "share one tier, and logistics workers are allocated as",
        "1 per every 3 buildings.  Toggle Auto off to customise.",
        "",
        "# Logistics Workers",
        "Logistics workers carry resources between buildings.",
        "Adjust the logistics count with +/- in the Workers tab.",
        "More logistics workers means faster resource delivery.",
        "",
        "# Demand & Supply Priority",
        "The Demand tab controls which buildings receive resources",
        "first.  The Supply tab controls which buildings are drawn",
        "from first.  Both support Auto and Manual modes.",
    ]),
    ("Research & Tiers", [
        "# Research",
        "Build a Research Center and select a technology to",
        "research.  Research consumes resources over time.",
        "Completed research unlocks new buildings and recipes.",
        "",
        "# Tech Tree",
        "Open the tech tree from the Research Center's info",
        "panel to see all available and locked technologies.",
        "Some techs require prerequisites to be researched first.",
        "",
        "# Tiers",
        "The colony progresses through tiers as you meet",
        "requirements (population, buildings, resources, research).",
        "Each tier may unlock new building types.",
        "",
        "Tier 0: Crash Site \u2014 starting buildings.",
        "Tier 1: Foothold \u2014 8 pop, 6 buildings.",
        "Tier 2: Settlement \u2014 15 pop, 100 Food, 1 research.",
        "Tier 3: Colony \u2014 25 pop, 50 Iron, 25 Copper, 3 research.",
    ]),
    ("Controls", [
        "# Camera",
        "\u2022 WASD / Arrow keys \u2014 pan the camera.",
        "\u2022 Scroll wheel \u2014 zoom in / out.",
        "\u2022 Middle click + drag \u2014 pan the camera.",
        "",
        "# Building",
        "\u2022 Left click \u2014 select tile / place building.",
        "\u2022 Right click \u2014 cancel build / deselect.",
        "\u2022 B \u2014 cycle build mode.",
        "\u2022 X \u2014 toggle delete mode.",
        "",
        "# Interface",
        "\u2022 I \u2014 toggle this info guide.",
        "\u2022 H \u2014 toggle quick controls reference.",
        "\u2022 1 / 2 / 3 \u2014 set game speed.",
        "\u2022 Tab \u2014 toggle sandbox mode.",
        "\u2022 Alt (hold) \u2014 show resource overlay.",
        "\u2022 Escape \u2014 pause menu.",
        "\u2022 F1 \u2014 toggle god mode.",
    ]),
]

_PAGE_TAB_H = 32
_LINE_H = 24
_MARGIN = 28
_PAD = 20


class InfoGuideOverlay(Panel):
    """Multi-page in-game guide overlay, toggled with I."""

    def __init__(self) -> None:
        super().__init__()
        self.visible = False
        self._page: int = 0
        self._scroll: int = 0
        self._tab_rects: list[pygame.Rect] = []
        self._mouse_pos: tuple[int, int] = (0, 0)

    def toggle(self) -> None:
        self.visible = not self.visible
        if self.visible:
            self._scroll = 0

    def layout(self, screen_w: int, screen_h: int) -> None:
        self.rect = pygame.Rect(0, 0, screen_w, screen_h)

    def draw(self, surface: pygame.Surface, world: "World") -> None:
        if not self.visible:
            return
        sw, sh = surface.get_size()

        overlay = pygame.Surface((sw, sh), pygame.SRCALPHA)
        overlay.fill(UI_OVERLAY)
        surface.blit(overlay, (0, 0))

        # Panel
        pw = min(700, sw - 60)
        ph = min(560, sh - 60)
        px = (sw - pw) // 2
        py = (sh - ph) // 2
        panel = pygame.Rect(px, py, pw, ph)
        draw_panel_bg(surface, panel, accent_edge="top")

        # Title
        title = Fonts.title().render("Game Guide", True, UI_TEXT)
        surface.blit(title, (px + _PAD, py + 10))

        # Page tabs
        self._tab_rects = []
        tx = px + _PAD
        ty = py + 42
        for i, (page_title, _) in enumerate(_PAGES):
            label = Fonts.small().render(page_title, True, UI_TEXT)
            tw = label.get_width() + 16
            tab_rect = pygame.Rect(tx, ty, tw, _PAGE_TAB_H)
            active = i == self._page
            hovered = tab_rect.collidepoint(self._mouse_pos)
            if active:
                bg_color = UI_TAB_ACTIVE
            elif hovered:
                bg_color = UI_TAB_HOVER
            else:
                bg_color = UI_TAB_INACTIVE
            bg = pygame.Surface((tab_rect.w, tab_rect.h), pygame.SRCALPHA)
            bg.fill(bg_color)
            surface.blit(bg, tab_rect.topleft)
            border = UI_ACCENT if active else UI_BORDER
            pygame.draw.rect(surface, border, tab_rect, width=1, border_radius=3)
            surface.blit(label, (
                tab_rect.centerx - label.get_width() // 2,
                tab_rect.centery - label.get_height() // 2,
            ))
            self._tab_rects.append(tab_rect)
            tx += tw + 4

        # Content area
        content_top = ty + _PAGE_TAB_H + 8
        content_rect = pygame.Rect(
            px + _MARGIN, content_top,
            pw - _MARGIN * 2, py + ph - content_top - 30,
        )
        prev_clip = surface.get_clip()
        surface.set_clip(content_rect)

        _, lines = _PAGES[self._page]
        y = content_rect.y - self._scroll
        header_font = Fonts.label()
        body_font = Fonts.body()

        for line in lines:
            if not line:
                y += _LINE_H // 2
                continue
            if line.startswith("#"):
                text = line.lstrip("# ")
                surf = header_font.render(text, True, UI_ACCENT)
            else:
                surf = body_font.render(line, True, UI_TEXT)
            surface.blit(surf, (content_rect.x, y))
            y += _LINE_H

        self._content_h = int(y + self._scroll - content_rect.y)
        surface.set_clip(prev_clip)

        # Hint
        hint = Fonts.small().render(
            "Press I or Escape to close", True, UI_MUTED,
        )
        surface.blit(hint, (
            px + (pw - hint.get_width()) // 2,
            py + ph - hint.get_height() - 10,
        ))

    def handle_event(self, event: pygame.event.Event) -> bool:
        if not self.visible:
            return False
        if event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_i, pygame.K_ESCAPE):
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
            self._scroll = max(0, self._scroll - event.y * 24)
            return True
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            for i, tab_rect in enumerate(self._tab_rects):
                if tab_rect.collidepoint(event.pos):
                    self._page = i
                    self._scroll = 0
                    return True
            return True  # consume click
        return True  # consume all events while visible


__all__ = ["InfoGuideOverlay"]
