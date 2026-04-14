"""Main game loop for Hex Colony."""

from __future__ import annotations

import pygame

from compprog_pygame.games.hex_colony.buildings import (
    BUILDING_COSTS,
    BuildingType,
)
from compprog_pygame.games.hex_colony.camera import Camera
from compprog_pygame.games.hex_colony.hex_grid import pixel_to_hex
from compprog_pygame.games.hex_colony.renderer import Renderer
from compprog_pygame.games.hex_colony.settings import HexColonySettings
from compprog_pygame.games.hex_colony.world import World

# Build-mode palette order
BUILDABLE = [
    BuildingType.WOODCUTTER,
    BuildingType.QUARRY,
    BuildingType.GATHERER,
    BuildingType.STORAGE,
]


class Game:
    """Top-level game object — owns the world, camera, and renderer."""

    def __init__(self, settings: HexColonySettings | None = None, seed: str = "default") -> None:
        self.settings = settings or HexColonySettings()
        self.world = World.generate(self.settings, seed=seed)
        self.camera: Camera | None = None
        self.renderer = Renderer()
        self.running = True
        self.build_mode: BuildingType | None = None

    # ── Public entry point ───────────────────────────────────────

    def run(self, screen: pygame.Surface, clock: pygame.time.Clock) -> None:
        w, h = screen.get_size()
        self.camera = Camera(w, h)

        while self.running:
            dt = clock.tick(self.settings.fps) / 1000.0
            dt = min(dt, 0.05)  # clamp large spikes

            for event in pygame.event.get():
                self._handle_event(event)

            self.world.update(dt)
            self.renderer.draw(screen, self.world, self.camera)

            # Build-mode indicator
            if self.build_mode is not None:
                self._draw_build_mode_hint(screen)

            pygame.display.flip()

    # ── Event handling ───────────────────────────────────────────

    def _handle_event(self, event: pygame.event.Event) -> None:
        assert self.camera is not None

        if event.type == pygame.QUIT:
            self.running = False

        elif event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                if self.build_mode is not None:
                    self.build_mode = None
                else:
                    self.running = False
            elif event.key == pygame.K_b:
                # Cycle build mode
                self._cycle_build_mode()

        elif event.type == pygame.VIDEORESIZE:
            screen = pygame.display.get_surface()
            self.camera.resize(screen.get_width(), screen.get_height())

        elif event.type == pygame.MOUSEBUTTONDOWN:
            if event.button == 1:  # left click
                self._on_left_click(event.pos)
            elif event.button == 2:  # middle click — pan start
                self.camera.start_drag(event.pos)
            elif event.button == 3:  # right click — pan start
                self.camera.start_drag(event.pos)
            elif event.button == 4:  # scroll up
                self.camera.zoom_at(event.pos, 1.1)
            elif event.button == 5:  # scroll down
                self.camera.zoom_at(event.pos, 1 / 1.1)

        elif event.type == pygame.MOUSEBUTTONUP:
            if event.button in (2, 3):
                self.camera.stop_drag()

        elif event.type == pygame.MOUSEMOTION:
            self.camera.drag(event.pos)

        elif event.type == pygame.MOUSEWHEEL:
            pos = pygame.mouse.get_pos()
            factor = 1.1 ** event.y
            self.camera.zoom_at(pos, factor)

    # ── Click actions ────────────────────────────────────────────

    def _on_left_click(self, screen_pos: tuple[int, int]) -> None:
        assert self.camera is not None
        wx, wy = self.camera.screen_to_world(*screen_pos)
        coord = pixel_to_hex(wx, wy, self.settings.hex_size)

        if coord not in self.world.grid:
            return

        if self.build_mode is not None:
            self._try_place_building(coord)
        else:
            # Select tile
            self.renderer.selected_hex = coord

    def _try_place_building(self, coord) -> None:
        tile = self.world.grid[coord]
        # Can't build on water
        from compprog_pygame.games.hex_colony.hex_grid import Terrain
        if tile.terrain == Terrain.WATER:
            return
        # Can't build where there's already a building
        if tile.building is not None:
            return
        # Check cost
        cost = BUILDING_COSTS[self.build_mode]
        for res, amount in cost.costs.items():
            if self.world.inventory[res] < amount:
                return  # can't afford
        # Spend resources
        for res, amount in cost.costs.items():
            self.world.inventory.spend(res, amount)
        # Place building
        building = self.world.buildings.place(self.build_mode, coord)
        tile.building = building
        self.build_mode = None

    def _cycle_build_mode(self) -> None:
        if self.build_mode is None:
            self.build_mode = BUILDABLE[0]
        else:
            idx = BUILDABLE.index(self.build_mode)
            next_idx = (idx + 1) % len(BUILDABLE)
            self.build_mode = BUILDABLE[next_idx]

    def _draw_build_mode_hint(self, surface: pygame.Surface) -> None:
        font = pygame.font.Font(None, 26)
        text = f"Build: {self.build_mode.name}  [B] cycle  [ESC] cancel"
        surf = font.render(text, True, (255, 255, 100))
        surface.blit(surf, (surface.get_width() // 2 - surf.get_width() // 2, 10))
