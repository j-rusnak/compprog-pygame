"""Rendering for Hex Colony — draws tiles, buildings, people, and HUD."""

from __future__ import annotations

import math

import pygame

from compprog_pygame.games.hex_colony.buildings import Building, BuildingType
from compprog_pygame.games.hex_colony.camera import Camera
from compprog_pygame.games.hex_colony.hex_grid import (
    HexCoord,
    HexTile,
    Terrain,
    hex_corners,
    hex_to_pixel,
)
from compprog_pygame.games.hex_colony.people import Person, Task
from compprog_pygame.games.hex_colony.resources import Inventory, Resource
from compprog_pygame.games.hex_colony.world import World

# ── Colour palette ───────────────────────────────────────────────

BACKGROUND = (9, 12, 25)

TERRAIN_COLORS: dict[Terrain, tuple[int, int, int]] = {
    Terrain.GRASS: (76, 140, 60),
    Terrain.FOREST: (34, 100, 34),
    Terrain.DENSE_FOREST: (18, 70, 22),
    Terrain.STONE_DEPOSIT: (140, 140, 130),
    Terrain.WATER: (40, 90, 180),
    Terrain.FIBER_PATCH: (120, 160, 60),
    Terrain.MOUNTAIN: (110, 100, 90),
}

BUILDING_COLORS: dict[BuildingType, tuple[int, int, int]] = {
    BuildingType.CAMP: (200, 160, 60),
    BuildingType.WOODCUTTER: (160, 100, 50),
    BuildingType.QUARRY: (170, 170, 160),
    BuildingType.GATHERER: (100, 180, 80),
    BuildingType.STORAGE: (140, 120, 100),
}

PERSON_COLOR = (230, 210, 170)
PERSON_GATHER_COLOR = (180, 220, 120)
HUD_BG = (16, 24, 45, 200)
HUD_TEXT = (242, 244, 255)
MUTED_TEXT = (140, 150, 175)
HIGHLIGHT_COLOR = (255, 255, 100)

RESOURCE_ICONS: dict[Resource, str] = {
    Resource.WOOD: "W",
    Resource.FIBER: "F",
    Resource.STONE: "S",
    Resource.FOOD: "Fd",
}


class Renderer:
    """Draws the entire game scene."""

    def __init__(self) -> None:
        self.font = pygame.font.Font(None, 22)
        self.hud_font = pygame.font.Font(None, 28)
        self.small_font = pygame.font.Font(None, 18)
        self.selected_hex: HexCoord | None = None

    # ── Public draw entry point ──────────────────────────────────

    def draw(
        self,
        surface: pygame.Surface,
        world: World,
        camera: Camera,
    ) -> None:
        surface.fill(BACKGROUND)
        self._draw_tiles(surface, world, camera)
        self._draw_buildings(surface, world, camera)
        self._draw_people(surface, world, camera)
        if self.selected_hex is not None:
            self._draw_hex_highlight(surface, self.selected_hex, camera, world.settings.hex_size)
        self._draw_hud(surface, world)

    # ── Hex tiles ────────────────────────────────────────────────

    def _draw_tiles(
        self, surface: pygame.Surface, world: World, camera: Camera
    ) -> None:
        size = world.settings.hex_size
        sw, sh = surface.get_size()
        margin = size * 2 * camera.zoom  # cull margin

        for tile in world.grid.tiles():
            wx, wy = hex_to_pixel(tile.coord, size)
            sx, sy = camera.world_to_screen(wx, wy)
            # Frustum cull
            if sx < -margin or sx > sw + margin or sy < -margin or sy > sh + margin:
                continue

            color = TERRAIN_COLORS.get(tile.terrain, (80, 80, 80))
            corners_world = hex_corners(wx, wy, size)
            corners_screen = [camera.world_to_screen(cx, cy) for cx, cy in corners_world]
            pygame.draw.polygon(surface, color, corners_screen)
            pygame.draw.polygon(surface, _darken(color, 0.6), corners_screen, width=1)

    # ── Buildings ────────────────────────────────────────────────

    def _draw_buildings(
        self, surface: pygame.Surface, world: World, camera: Camera
    ) -> None:
        size = world.settings.hex_size
        for building in world.buildings.buildings:
            wx, wy = hex_to_pixel(building.coord, size)
            sx, sy = camera.world_to_screen(wx, wy)
            r = int(size * 0.5 * camera.zoom)
            color = BUILDING_COLORS.get(building.type, (200, 200, 200))

            # Draw a small filled shape at hex centre
            if building.type == BuildingType.CAMP:
                # Triangle for camp
                pts = [
                    (sx, sy - r),
                    (sx - r, sy + r * 0.7),
                    (sx + r, sy + r * 0.7),
                ]
                pygame.draw.polygon(surface, color, pts)
                pygame.draw.polygon(surface, (255, 220, 100), pts, width=2)
            else:
                # Square for other buildings
                rect = pygame.Rect(sx - r * 0.6, sy - r * 0.6, r * 1.2, r * 1.2)
                pygame.draw.rect(surface, color, rect)
                pygame.draw.rect(surface, _darken(color, 0.6), rect, width=1)

            # Label
            label = self.small_font.render(building.type.name[:4], True, HUD_TEXT)
            surface.blit(label, (sx - label.get_width() // 2, sy + r + 2))

    # ── People ───────────────────────────────────────────────────

    def _draw_people(
        self, surface: pygame.Surface, world: World, camera: Camera
    ) -> None:
        for person in world.population.people:
            sx, sy = camera.world_to_screen(person.px, person.py)
            r = max(3, int(4 * camera.zoom))
            color = PERSON_GATHER_COLOR if person.task == Task.GATHER else PERSON_COLOR
            pygame.draw.circle(surface, color, (int(sx), int(sy)), r)
            pygame.draw.circle(surface, _darken(color, 0.5), (int(sx), int(sy)), r, width=1)

    # ── Selection highlight ──────────────────────────────────────

    def _draw_hex_highlight(
        self,
        surface: pygame.Surface,
        coord: HexCoord,
        camera: Camera,
        size: int,
    ) -> None:
        wx, wy = hex_to_pixel(coord, size)
        corners_world = hex_corners(wx, wy, size)
        corners_screen = [camera.world_to_screen(cx, cy) for cx, cy in corners_world]
        pygame.draw.polygon(surface, HIGHLIGHT_COLOR, corners_screen, width=2)

    # ── HUD overlay ──────────────────────────────────────────────

    def _draw_hud(self, surface: pygame.Surface, world: World) -> None:
        x, y = 10, 10
        line_h = 26
        inv = world.inventory

        # Semi-transparent background panel
        panel_w = 200
        panel_h = line_h * (len(Resource) + 2) + 10
        panel = pygame.Surface((panel_w, panel_h), pygame.SRCALPHA)
        panel.fill(HUD_BG)
        surface.blit(panel, (x, y))

        # Title
        title = self.hud_font.render("Colony", True, HUD_TEXT)
        surface.blit(title, (x + 8, y + 4))
        y += line_h + 4

        # Population
        pop_text = self.font.render(f"People: {world.population.count}", True, HUD_TEXT)
        surface.blit(pop_text, (x + 8, y))
        y += line_h

        # Resources
        for res in Resource:
            icon = RESOURCE_ICONS[res]
            val = inv[res]
            txt = self.font.render(f"{icon}: {val:.0f}", True, HUD_TEXT)
            surface.blit(txt, (x + 8, y))
            y += line_h

        # Bottom bar: selected tile info
        if self.selected_hex is not None:
            tile = world.grid.get(self.selected_hex)
            if tile:
                info_parts = [f"Hex ({tile.coord.q},{tile.coord.r})", tile.terrain.name]
                building = world.buildings.at(self.selected_hex)
                if building:
                    info_parts.append(building.type.name)
                info = "  |  ".join(info_parts)
                info_surf = self.font.render(info, True, MUTED_TEXT)
                surface.blit(
                    info_surf,
                    (surface.get_width() // 2 - info_surf.get_width() // 2,
                     surface.get_height() - 30),
                )


def _darken(color: tuple[int, int, int], factor: float) -> tuple[int, int, int]:
    return tuple(max(0, int(c * factor)) for c in color)  # type: ignore[return-value]
