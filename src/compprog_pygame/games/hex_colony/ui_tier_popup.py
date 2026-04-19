"""Tier-advancement pop-up for Hex Colony.

Appears when the player reaches a new tier, showing the tier name,
unlocked buildings, and the next tier's requirements.  Dismissed by
clicking anywhere or pressing Escape/Enter.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pygame

from compprog_pygame.games.hex_colony.buildings import BuildingType
from compprog_pygame.games.hex_colony.ui import (
    Fonts,
    Panel,
    UI_ACCENT,
    UI_MUTED,
    UI_OVERLAY,
    UI_TEXT,
    draw_titled_panel,
)

if TYPE_CHECKING:
    from compprog_pygame.games.hex_colony.tech_tree import TierInfo
    from compprog_pygame.games.hex_colony.world import World

_BUILDING_LABEL: dict[BuildingType, str] = {
    BuildingType.HABITAT: "Habitat",
    BuildingType.PATH: "Path",
    BuildingType.BRIDGE: "Bridge",
    BuildingType.WALL: "Wall",
    BuildingType.WOODCUTTER: "Woodcutter",
    BuildingType.QUARRY: "Quarry",
    BuildingType.GATHERER: "Gatherer",
    BuildingType.STORAGE: "Storage",
    BuildingType.REFINERY: "Refinery",
    BuildingType.MINING_MACHINE: "Mining Machine",
    BuildingType.FARM: "Farm",
    BuildingType.WELL: "Well",
    BuildingType.WORKSHOP: "Workshop",
    BuildingType.FORGE: "Forge",
    BuildingType.ASSEMBLER: "Assembler",
    BuildingType.RESEARCH_CENTER: "Research Center",
}

_LINE_H = 26
_SECTION_GAP = 14
_MARGIN = 24


class TierPopup(Panel):
    """Full-screen overlay announcing a new tier."""

    def __init__(self) -> None:
        super().__init__()
        self.visible = False
        self._current_tier: "TierInfo | None" = None
        self._next_tier: "TierInfo | None" = None

    def show(
        self, current_tier: "TierInfo", next_tier: "TierInfo | None",
    ) -> None:
        self._current_tier = current_tier
        self._next_tier = next_tier
        self.visible = True

    def layout(self, screen_w: int, screen_h: int) -> None:
        self.rect = pygame.Rect(0, 0, screen_w, screen_h)

    def draw(self, surface: pygame.Surface, world: "World") -> None:
        if not self.visible or self._current_tier is None:
            return
        sw, sh = surface.get_size()

        overlay = pygame.Surface((sw, sh), pygame.SRCALPHA)
        overlay.fill(UI_OVERLAY)
        surface.blit(overlay, (0, 0))

        # Compute panel height dynamically.
        cur = self._current_tier
        nxt = self._next_tier
        lines = 0
        # Title + description + gap
        lines += 2
        # Unlocked buildings
        if cur.unlocks_buildings:
            lines += 1 + len(cur.unlocks_buildings)
        lines += 1  # gap
        # Next tier section
        if nxt is not None:
            lines += 1  # header
            lines += 1  # name
            req_lines = 0
            reqs = nxt.requirements
            if "population" in reqs:
                req_lines += 1
            if "buildings_placed" in reqs:
                req_lines += 1
            if "resource_gathered" in reqs:
                req_lines += len(reqs["resource_gathered"])
            if "research_count" in reqs:
                req_lines += 1
            lines += req_lines
        else:
            lines += 1  # "Max tier reached"

        pw = 460
        ph = 100 + lines * _LINE_H + _SECTION_GAP * 3 + 50
        pw = min(pw, sw - 40)
        ph = min(ph, sh - 40)
        px = (sw - pw) // 2
        py = (sh - ph) // 2
        panel = pygame.Rect(px, py, pw, ph)

        title_text = f"Tier {cur.level}: {cur.name}"
        content_y = draw_titled_panel(
            surface, panel, title_text,
            title_color=(255, 215, 0),
        )

        y = content_y
        body = Fonts.body()
        label = Fonts.label()
        small = Fonts.small()

        # Description
        desc_surf = body.render(cur.description, True, UI_MUTED)
        surface.blit(desc_surf, (px + _MARGIN, y))
        y += _LINE_H + _SECTION_GAP

        # Unlocked buildings
        if cur.unlocks_buildings:
            header = label.render("Unlocked Buildings:", True, UI_ACCENT)
            surface.blit(header, (px + _MARGIN, y))
            y += _LINE_H
            for bt in cur.unlocks_buildings:
                name = _BUILDING_LABEL.get(bt, bt.name.replace("_", " ").title())
                bullet = body.render(f"  \u2022 {name}", True, UI_TEXT)
                surface.blit(bullet, (px + _MARGIN, y))
                y += _LINE_H
        else:
            note = body.render("No new buildings unlocked.", True, UI_MUTED)
            surface.blit(note, (px + _MARGIN, y))
            y += _LINE_H

        y += _SECTION_GAP

        # Next tier
        if nxt is not None:
            header = label.render(
                f"Next: Tier {nxt.level} \u2014 {nxt.name}", True, UI_ACCENT,
            )
            surface.blit(header, (px + _MARGIN, y))
            y += _LINE_H

            nxt_desc = small.render(nxt.description, True, UI_MUTED)
            surface.blit(nxt_desc, (px + _MARGIN, y))
            y += _LINE_H

            reqs = nxt.requirements
            if "population" in reqs:
                txt = body.render(
                    f"  \u2022 Population: {reqs['population']}", True, UI_TEXT,
                )
                surface.blit(txt, (px + _MARGIN, y))
                y += _LINE_H
            if "buildings_placed" in reqs:
                txt = body.render(
                    f"  \u2022 Buildings: {reqs['buildings_placed']}",
                    True, UI_TEXT,
                )
                surface.blit(txt, (px + _MARGIN, y))
                y += _LINE_H
            if "resource_gathered" in reqs:
                for res_name, amount in reqs["resource_gathered"].items():
                    txt = body.render(
                        f"  \u2022 {res_name.replace('_', ' ').title()}: {amount}",
                        True, UI_TEXT,
                    )
                    surface.blit(txt, (px + _MARGIN, y))
                    y += _LINE_H
            if "research_count" in reqs:
                txt = body.render(
                    f"  \u2022 Research completed: {reqs['research_count']}",
                    True, UI_TEXT,
                )
                surface.blit(txt, (px + _MARGIN, y))
                y += _LINE_H
        else:
            congrats = label.render(
                "Maximum tier reached!", True, (255, 215, 0),
            )
            surface.blit(congrats, (px + _MARGIN, y))
            y += _LINE_H

        # Dismiss hint
        hint = small.render(
            "Click anywhere or press Escape to continue", True, UI_MUTED,
        )
        surface.blit(hint, (
            px + (pw - hint.get_width()) // 2,
            py + ph - hint.get_height() - 14,
        ))

    def handle_event(self, event: pygame.event.Event) -> bool:
        if not self.visible:
            return False
        if event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_ESCAPE, pygame.K_RETURN, pygame.K_SPACE):
                self.visible = False
                return True
        if event.type == pygame.MOUSEBUTTONDOWN:
            self.visible = False
            return True
        return True  # consume all events while visible


__all__ = ["TierPopup"]
