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
from compprog_pygame.games.hex_colony.ui import UIManager
from compprog_pygame.games.hex_colony.ui_bottom_bar import BottomBar
from compprog_pygame.games.hex_colony.ui_building_info import BuildingInfoPanel
from compprog_pygame.games.hex_colony.ui_resource_bar import ResourceBar
from compprog_pygame.games.hex_colony.world import World

# Build-mode palette order
BUILDABLE = [
    BuildingType.HOUSE,
    BuildingType.PATH,
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
        self.delete_mode = False
        self.sandbox = False
        self._build_dragging = False
        self._hint_font = pygame.font.Font(None, 26)

        # UI
        self.ui = UIManager()
        self._resource_bar = ResourceBar()
        self._bottom_bar = BottomBar()
        self._building_info = BuildingInfoPanel()
        self.ui.add_panel(self._resource_bar)
        self.ui.add_panel(self._bottom_bar)
        self.ui.add_panel(self._building_info)

        # Wire building tab -> build mode
        buildings_tab = self._bottom_bar.buildings_tab
        if buildings_tab:
            buildings_tab.set_on_select(self._on_building_selected)
            buildings_tab.set_on_delete_toggle(self._on_delete_toggled)

        # Wire sandbox population buttons
        self._resource_bar.set_on_pop_change(self._on_pop_change)

    # ── Public entry point ───────────────────────────────────────

    def run(self, screen: pygame.Surface, clock: pygame.time.Clock) -> None:
        w, h = screen.get_size()
        self.camera = Camera(w, h)
        self.ui.layout(w, h)

        while self.running:
            dt = clock.tick(self.settings.fps) / 1000.0
            dt = min(dt, 0.05)  # clamp large spikes

            for event in pygame.event.get():
                self._handle_event(event)

            self.world.update(dt)
            self._resource_bar.delete_mode = self.delete_mode
            self.renderer.draw(screen, self.world, self.camera, dt=dt)
            self.ui.draw(screen, self.world)

            pygame.display.flip()

    # ── Event handling ───────────────────────────────────────────

    def _handle_event(self, event: pygame.event.Event) -> None:
        assert self.camera is not None

        if event.type == pygame.QUIT:
            self.running = False
            return

        # Let UI consume events first
        if self.ui.handle_event(event):
            return

        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                if self.build_mode is not None:
                    self.build_mode = None
                    btab = self._bottom_bar.buildings_tab
                    if btab:
                        btab.selected_building = None
                elif self.delete_mode:
                    self.delete_mode = False
                    btab = self._bottom_bar.buildings_tab
                    if btab:
                        btab.delete_active = False
                else:
                    self.running = False
            elif event.key == pygame.K_TAB:
                self.sandbox = not self.sandbox
                self._resource_bar.sandbox = self.sandbox
            elif event.key == pygame.K_b:
                # Cycle build mode
                self._cycle_build_mode()
            elif event.key == pygame.K_x:
                # Toggle delete mode
                self.delete_mode = not self.delete_mode
                if self.delete_mode:
                    self.build_mode = None
                    btab = self._bottom_bar.buildings_tab
                    if btab:
                        btab.selected_building = None
                        btab.delete_active = True
                else:
                    btab = self._bottom_bar.buildings_tab
                    if btab:
                        btab.delete_active = False

        elif event.type == pygame.VIDEORESIZE:
            screen = pygame.display.get_surface()
            w, h = screen.get_width(), screen.get_height()
            self.camera.resize(w, h)
            self.ui.layout(w, h)

        elif event.type == pygame.MOUSEBUTTONDOWN:
            if event.button == 1:  # left click
                self._on_left_click(event.pos)
                if self.build_mode is not None:
                    self._build_dragging = True
            elif event.button == 2:  # middle click — pan start
                self.camera.start_drag(event.pos)
            elif event.button == 3:  # right click
                if self.build_mode is not None:
                    self.build_mode = None
                    self._build_dragging = False
                    btab = self._bottom_bar.buildings_tab
                    if btab:
                        btab.selected_building = None
                elif self.delete_mode:
                    self.delete_mode = False
                    btab = self._bottom_bar.buildings_tab
                    if btab:
                        btab.delete_active = False
                else:
                    self.camera.start_drag(event.pos)
            elif event.button == 4:  # scroll up
                self.camera.zoom_at(event.pos, 1.1)
            elif event.button == 5:  # scroll down
                self.camera.zoom_at(event.pos, 1 / 1.1)

        elif event.type == pygame.MOUSEBUTTONUP:
            if event.button == 1:
                self._build_dragging = False
            if event.button in (2, 3):
                self.camera.stop_drag()

        elif event.type == pygame.MOUSEMOTION:
            self.camera.drag(event.pos)
            if self._build_dragging and self.build_mode is not None:
                wx, wy = self.camera.screen_to_world(*event.pos)
                coord = pixel_to_hex(wx, wy, self.settings.hex_size)
                if coord in self.world.grid:
                    self._try_place_building(coord)

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

        if self.delete_mode:
            self._try_delete_building(coord)
        elif self.build_mode is not None:
            self._try_place_building(coord)
        else:
            # Select tile
            self.renderer.selected_hex = coord
            # Show building info if there's a building
            building = self.world.buildings.at(coord)
            self._building_info.building = building

    def _try_place_building(self, coord) -> None:
        tile = self.world.grid[coord]
        # Can't build on water
        from compprog_pygame.games.hex_colony.hex_grid import Terrain
        if tile.terrain == Terrain.WATER:
            return
        # Check existing building
        existing = tile.building
        if existing is not None:
            # Can only build on top of a path (not camp, not other buildings)
            if existing.type != BuildingType.PATH:
                return
            # Can't place another path on a path
            if self.build_mode == BuildingType.PATH:
                return
        # Check cost (skip in sandbox mode)
        if not self.sandbox:
            cost = BUILDING_COSTS[self.build_mode]
            for res, amount in cost.costs.items():
                if self.world.inventory[res] < amount:
                    return  # can't afford
            for res, amount in cost.costs.items():
                self.world.inventory.spend(res, amount)
        # If building on top of a path, refund path cost and remove it
        if existing is not None and existing.type == BuildingType.PATH:
            if not self.sandbox:
                path_cost = BUILDING_COSTS[BuildingType.PATH]
                for res, amount in path_cost.costs.items():
                    self.world.inventory[res] += amount
            self.world.buildings.remove(existing)
            tile.building = None
        # Place building
        building = self.world.buildings.place(self.build_mode, coord)
        tile.building = building
        # Clear overlays on the tile so building is visible
        self.renderer.remove_overlays_at(coord, self.settings.hex_size)

    def _try_delete_building(self, coord) -> None:
        """Delete a building at the given coordinate, refunding half its cost."""
        tile = self.world.grid[coord]
        building = tile.building
        if building is None:
            return
        # Can't delete the camp
        if building.type == BuildingType.CAMP:
            return
        # Refund half the cost (rounded down)
        if not self.sandbox:
            cost = BUILDING_COSTS[building.type]
            for res, amount in cost.costs.items():
                self.world.inventory[res] += amount // 2
        # Remove building
        self.world.buildings.remove(building)
        tile.building = None
        # Invalidate tile layer cache so cleared tile redraws
        self.renderer._tile_layer = None

    def _on_building_selected(self, btype: BuildingType | None) -> None:
        """Callback from the Buildings tab when a building card is clicked."""
        self.build_mode = btype
        if btype is not None:
            self.delete_mode = False

    def _on_delete_toggled(self, active: bool) -> None:
        """Callback from the Buildings tab when delete card is clicked."""
        self.delete_mode = active
        if active:
            self.build_mode = None

    def _cycle_build_mode(self) -> None:
        self.delete_mode = False
        if self.build_mode is None:
            self.build_mode = BUILDABLE[0]
        else:
            idx = BUILDABLE.index(self.build_mode)
            next_idx = (idx + 1) % len(BUILDABLE)
            self.build_mode = BUILDABLE[next_idx]
        # Sync to buildings tab
        btab = self._bottom_bar.buildings_tab
        if btab:
            btab.selected_building = self.build_mode

    def _on_pop_change(self, delta: int) -> None:
        """Sandbox callback: add or remove population."""
        from compprog_pygame.games.hex_colony.hex_grid import HexCoord
        if delta > 0:
            # Spawn at camp — housing assignment handled by _update_housing
            self.world.population.spawn(HexCoord(0, 0), self.settings.hex_size)
        elif delta < 0 and self.world.population.people:
            # Remove last person
            pop = self.world.population
            target = pop.people[-1]
            if target.home is not None:
                target.home.residents = max(0, target.home.residents - 1)
            pop.people.remove(target)
