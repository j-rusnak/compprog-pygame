"""Main game loop for Hex Colony."""

from __future__ import annotations

import gc

import pygame

from compprog_pygame.games.hex_colony.buildings import (
    BuildingType,
)
from compprog_pygame.games.hex_colony.camera import Camera
from compprog_pygame.games.hex_colony.people import Task
from compprog_pygame.games.hex_colony.hex_grid import pixel_to_hex, Terrain, HexCoord
from compprog_pygame.games.hex_colony.renderer import Renderer
from compprog_pygame.games.hex_colony.settings import HexColonySettings
from compprog_pygame.games.hex_colony.ui import UIManager
from compprog_pygame.games.hex_colony.ui_bottom_bar import BottomBar
from compprog_pygame.games.hex_colony.ui_building_info import BuildingInfoPanel
from compprog_pygame.games.hex_colony.ui_game_over import GameOverOverlay
from compprog_pygame.games.hex_colony.ui_help_overlay import HelpOverlay
from compprog_pygame.games.hex_colony.ui_pause_menu import PauseOverlay
from compprog_pygame.games.hex_colony.ui_resource_bar import ResourceBar
from compprog_pygame.games.hex_colony.ui_tile_info import TileInfoPanel
from compprog_pygame.games.hex_colony.world import World
from compprog_pygame.games.hex_colony.notifications import NotificationManager
from compprog_pygame.games.hex_colony.awakening_cutscene import AwakeningCutscene
from compprog_pygame.games.hex_colony.settings import Difficulty
from compprog_pygame.games.hex_colony.tech_tree import (
    TechTree, TierTracker, TECH_REQUIREMENTS, TECH_NODES,
    TIERS, TIER_BUILDING_REQUIREMENTS,
)
from compprog_pygame.games.hex_colony.procgen import UNBUILDABLE
from compprog_pygame.games.hex_colony.blueprints import BlueprintManager
from compprog_pygame.games.hex_colony.supply_chain import draw_supply_lines
from compprog_pygame.games.hex_colony.ui_minimap import MinimapPanel
from compprog_pygame.games.hex_colony.ui_stats import StatsTabContent
from compprog_pygame.games.hex_colony.ui_tech_tree import TechTreeOverlay
from compprog_pygame.games.hex_colony.ui_advanced_stats import AdvancedStatsOverlay
from compprog_pygame.games.hex_colony.ui_worker_priority import (
    WorkerPriorityOverlay,
    WorkerPriorityTabContent,
)
from compprog_pygame.games.hex_colony.ui_demand_priority import (
    DemandPriorityOverlay,
    DemandPriorityTabContent,
)
from compprog_pygame.games.hex_colony.ui_supply_priority import (
    SupplyPriorityOverlay,
    SupplyPriorityTabContent,
)
from compprog_pygame.games.hex_colony.ui_tier_popup import TierPopup
from compprog_pygame.games.hex_colony.ui_tutorial import TutorialPanel
from compprog_pygame.games.hex_colony import params
from compprog_pygame.games.hex_colony.perf_monitor import PerfMonitor
from compprog_pygame.games.hex_colony.logistics_monitor import LogisticsMonitor
from compprog_pygame.games.hex_colony.strings import (
    building_label,
    NOTIF_RESEARCH_COMPLETE,
    NOTIF_GOD_MODE_ON,
    NOTIF_GOD_MODE_OFF,
    NOTIF_GOD_SPAWN_ON,
    NOTIF_GOD_SPAWN_OFF,
    NOTIF_REQUIRES_RESEARCH,
    NOTIF_REQUIRES_TIER,
    NOTIF_BUILT,
    NOTIF_BUILT_PATH,
    NOTIF_AWAKENING_TRIGGERED,
    TAB_WORKERS,
    TAB_DEMAND,
    TAB_SUPPLY,
    TAB_STATS,
)

# Build-mode palette order
BUILDABLE = [
    BuildingType.HABITAT,
    BuildingType.PATH,
    BuildingType.BRIDGE,
    BuildingType.WALL,
    BuildingType.WOODCUTTER,
    BuildingType.QUARRY,
    BuildingType.GATHERER,
    BuildingType.STORAGE,
    BuildingType.REFINERY,
    BuildingType.MINING_MACHINE,
    BuildingType.FARM,
    BuildingType.WELL,
    BuildingType.WORKSHOP,
    BuildingType.RESEARCH_CENTER,
    # Tier 4+ industrial buildings (visible after their unlocking tech)
    BuildingType.CHEMICAL_PLANT,
    BuildingType.CONVEYOR,
    BuildingType.SOLAR_ARRAY,
    BuildingType.ROCKET_SILO,
    BuildingType.OIL_DRILL,
    BuildingType.OIL_REFINERY,
    BuildingType.PIPE,
    BuildingType.FLUID_TANK,
    BuildingType.TURRET,
    BuildingType.TRAP,
]


def _hex_line(a: HexCoord, b: HexCoord) -> list[HexCoord]:
    """Return a contiguous straight-ish hex chain from ``a`` to ``b``
    (inclusive of both endpoints) using cube-coordinate interpolation.
    """
    n = a.distance(b)
    if n == 0:
        return [a]
    out: list[HexCoord] = []
    # Convert axial -> cube.
    ax, az = a.q, a.r
    ay = -ax - az
    bx, bz = b.q, b.r
    by = -bx - bz
    for i in range(n + 1):
        t = i / n
        x = ax + (bx - ax) * t
        y = ay + (by - ay) * t
        z = az + (bz - az) * t
        # cube round
        rx, ry, rz = round(x), round(y), round(z)
        dx, dy, dz = abs(rx - x), abs(ry - y), abs(rz - z)
        if dx > dy and dx > dz:
            rx = -ry - rz
        elif dy > dz:
            ry = -rx - rz
        else:
            rz = -rx - ry
        out.append(HexCoord(rx, rz))
    return out


class Game:
    """Top-level game object — owns the world, camera, and renderer."""

    def __init__(
        self,
        settings: HexColonySettings | None = None,
        seed: str = "default",
        world: World | None = None,
    ) -> None:
        self.settings = settings or HexColonySettings()
        # Allow the caller to pass a world that was generated on a
        # background thread (so the intro cutscene can mask the
        # generation latency).  Falls back to synchronous generation
        # for callers that don't care about load time (e.g. tests).
        self.world = world if world is not None else World.generate(
            self.settings, seed=seed,
        )
        self.camera: Camera | None = None
        self.renderer = Renderer()
        self.running = True
        self.quit_to_desktop = False
        self.build_mode: BuildingType | None = None
        self.delete_mode = False
        self.sandbox = False
        # God mode: bypass tech/tier/inventory gates and reveal all
        # locked content in the UI.  Toggle at runtime with F1.
        self.god_mode: bool = self.settings.god_mode
        # God-mode-only tool: when set to a key in
        # ``params.ENEMY_TYPE_DATA``, left-clicking the world spawns
        # one enemy of that type at the clicked hex.  F2 cycles
        # through enemy types; right-click cancels.
        self._spawn_enemy_mode: str | None = None
        self._build_dragging = False
        self._delete_dragging = False
        # Anchor for path chain placement: after first PATH click, the
        # second click places paths along the BFS route between them.
        self._path_anchor: HexCoord | None = None
        # Cache for the path-chain preview BFS so we don't re-run a
        # whole-grid pathfind every frame while the player hovers in
        # PATH build mode.  Key = (anchor, ghost_coord, build_mode,
        # topology_version, allow_bridges, bridge_stock).
        self._path_preview_cache_key: tuple | None = None
        self._path_preview_cache_route: list = []
        self._hint_font = pygame.font.Font(None, 26)
        self._sim_speed: float = 3.0  # 1x (=3), 2x (=6), 3x (=9), 10x (=30)
        self._real_time_elapsed: float = 0.0
        # Real-time seconds since the player most recently advanced a
        # tier. Used by the tutorial system for tier-timed hints.
        self._time_in_current_tier: float = 0.0
        self._drag_button: int = 0  # which mouse button started camera drag

        # Tech tree, tier tracker & notifications.  These are now
        # owned by the player's :class:`ColonyState` (so non-player
        # have their own independent copies); ``Game`` just keeps
        # references for the UI panels that haven't been refactored
        # to look them up via the world.
        self.tech_tree = self.world.player_colony.tech_tree
        self.tier_tracker = self.world.player_colony.tier_tracker
        self.notifications = NotificationManager()
        self.world.notifications = self.notifications
        self.blueprints = BlueprintManager()

        # UI
        self.ui = UIManager()
        self._resource_bar = ResourceBar()
        self._bottom_bar = BottomBar()
        self._building_info = BuildingInfoPanel()
        self._tile_info = TileInfoPanel()
        self._pause_overlay = PauseOverlay()
        self._game_over_overlay = GameOverOverlay()
        self._help_overlay = HelpOverlay()
        self._minimap = MinimapPanel()
        self._tech_tree_overlay = TechTreeOverlay()
        self._advanced_stats_overlay = AdvancedStatsOverlay()
        self._worker_priority_overlay = WorkerPriorityOverlay()
        self._demand_priority_overlay = DemandPriorityOverlay()
        self._supply_priority_overlay = SupplyPriorityOverlay()
        self._tier_popup = TierPopup()
        self._tutorial = TutorialPanel()
        self.ui.add_panel(self._resource_bar)
        self.ui.add_panel(self._bottom_bar)
        self.ui.add_panel(self._building_info)
        self.ui.add_panel(self._tile_info)
        self.ui.add_panel(self._minimap)
        self.ui.add_panel(self._help_overlay)
        self.ui.add_panel(self._tech_tree_overlay)
        self.ui.add_panel(self._advanced_stats_overlay)
        self.ui.add_panel(self._worker_priority_overlay)
        self.ui.add_panel(self._demand_priority_overlay)
        self.ui.add_panel(self._supply_priority_overlay)
        self.ui.add_panel(self._tier_popup)
        self.ui.add_panel(self._tutorial)
        self.ui.add_panel(self._pause_overlay)
        self.ui.add_panel(self._game_over_overlay)

        # Worker-priority tab (opens the drag-and-drop overlay).
        self._worker_priority_tab = WorkerPriorityTabContent()
        self._worker_priority_tab.on_open_edit = self._on_open_worker_priority
        self._worker_priority_tab.on_toggle_auto = self._on_toggle_worker_auto
        self._worker_priority_overlay.on_toggle_auto = self._on_toggle_worker_auto
        self._bottom_bar.add_tab(TAB_WORKERS, self._worker_priority_tab)

        # Demand-priority tab (opens its own drag-and-drop overlay).
        self._demand_priority_tab = DemandPriorityTabContent()
        self._demand_priority_tab.on_open_edit = self._on_open_demand_priority
        self._demand_priority_tab.on_toggle_auto = self._on_toggle_demand_auto
        self._bottom_bar.add_tab(TAB_DEMAND, self._demand_priority_tab)

        # Supply-priority tab (mirrors the demand one).
        self._supply_priority_tab = SupplyPriorityTabContent()
        self._supply_priority_tab.on_open_edit = self._on_open_supply_priority
        self._supply_priority_tab.on_toggle_auto = self._on_toggle_supply_auto
        self._bottom_bar.add_tab(TAB_SUPPLY, self._supply_priority_tab)

        # Add Stats tab to bottom bar
        self._stats_tab = StatsTabContent()
        self._bottom_bar.add_tab(TAB_STATS, self._stats_tab)

        # Info tab retired; the top-right Help button now exposes a
        # richer, tier-aware guide via ``HelpOverlay``.

        # Wire building tab -> build mode
        buildings_tab = self._bottom_bar.buildings_tab
        if buildings_tab:
            buildings_tab.set_on_select(self._on_building_selected)
            buildings_tab.set_on_delete_toggle(self._on_delete_toggled)
            buildings_tab.building_inventory = self.world.building_inventory
            buildings_tab.tech_tree = self.tech_tree
            buildings_tab.tier_tracker = self.tier_tracker
            buildings_tab.god_mode_getter = lambda: self.god_mode

        # Give other panels references for unlock filtering
        self._building_info.tech_tree = self.tech_tree
        self._building_info.god_mode_getter = lambda: self.god_mode
        self._stats_tab.tech_tree = self.tech_tree
        self._stats_tab.tier_tracker = self.tier_tracker
        self._stats_tab.god_mode_getter = lambda: self.god_mode
        self._stats_tab.on_open_advanced = self._on_open_advanced_stats

        # Advanced Stats overlay: share history with the stats tab so
        # the graphs cover the whole session, not just time-since-open.
        self._advanced_stats_overlay.history = self._stats_tab.history
        self._advanced_stats_overlay.tech_tree = self.tech_tree
        self._advanced_stats_overlay.tier_tracker = self.tier_tracker
        self._advanced_stats_overlay.god_mode_getter = lambda: self.god_mode

        # Help overlay: dynamic tier/tech-aware guide reached via the
        # top-right Help button (or H / I keys).
        self._help_overlay.set_state(self.tech_tree, self.tier_tracker)
        self._resource_bar.set_on_help(self._help_overlay.toggle)
        self._resource_bar.set_on_research(self._on_open_tech_tree)

        # Wire pause overlay callbacks
        self._pause_overlay.on_resume = self._on_pause_resume
        self._pause_overlay.on_return_to_menu = self._on_pause_return_to_menu
        self._pause_overlay.on_quit = self._on_pause_quit
        self._pause_overlay.on_graphics_changed = self._on_graphics_changed

        # Wire sandbox population buttons
        self._resource_bar.set_on_pop_change(self._on_pop_change)

        # Wire building info -> tech tree overlay
        self._building_info.on_open_tech_tree = self._on_open_tech_tree
        self._building_info.tier_tracker = self.tier_tracker
        self._tech_tree_overlay.on_close = self._on_close_tech_tree
        self._tech_tree_overlay.tech_tree = self.tech_tree

        # ``world.tech_tree`` is now a property pointing at the
        # player's colony; no assignment needed.

        # Wire game-over overlay callbacks
        self._game_over_overlay.on_return_to_menu = self._on_pause_return_to_menu
        self._game_over_overlay.on_quit = self._on_pause_quit
        self._game_over_overlay.tier_tracker = self.tier_tracker
        self._game_over_overlay.tech_tree = self.tech_tree

        # Background performance monitor — instruments _tick phases
        # and writes attributed spike records to a JSONL log from a
        # daemon thread.  Disabled by setting HEX_COLONY_PERF=0.
        self.perf = PerfMonitor(fps_target=self.settings.fps)
        # Background logistics monitor — periodically snapshots
        # per-network supply/demand, hauler tasks and starved
        # buildings to ``hex_colony_logistics.jsonl`` from a daemon
        # thread.  Disabled by setting HEX_COLONY_LOGISTICS=0.
        self.logistics_mon = LogisticsMonitor()

        # Active mid-game cutscene (currently only the ancient-tech
        # awakening).  When set, the world simulation is paused and
        # the cutscene drives the camera + tower-rise animation.
        self._awakening_cutscene: AwakeningCutscene | None = None

    # ── Public entry point ───────────────────────────────────────

    def run(self, screen: pygame.Surface, clock: pygame.time.Clock) -> None:
        w, h = screen.get_size()
        self.camera = Camera(w, h)
        self._minimap.camera = self.camera
        self.ui.layout(w, h)

        # ── GC tuning to eliminate the "occasional" multi-100 ms
        # frame stalls caused by Python's generational collector
        # walking every tracked object once the colony grows large.
        # ``gc.freeze`` moves all currently-allocated objects (the
        # entire world, sprites, fonts, UI, etc.) into a permanent
        # generation that future passes skip.  We then disable the
        # automatic collector and run a small, bounded gen-0 sweep
        # ourselves once per second from the main loop.  This trades
        # one predictable ~1 ms collection per second for the
        # unpredictable multi-frame freezes the player was seeing.
        prev_gc_enabled = gc.isenabled()
        prev_gc_thresholds = gc.get_threshold()
        gc.collect()
        gc.freeze()
        gc.disable()
        gc_accum = 0.0
        self.perf.start()
        self.logistics_mon.start()
        try:
            while self.running:
                dt = clock.tick(self.settings.fps) / 1000.0
                dt = min(dt, 0.05)  # clamp large spikes
                # Begin perf frame *after* clock.tick so the vsync /
                # frame-cap wait isn't counted as a spike.
                self.perf.frame_begin()
                gc_accum += dt
                if gc_accum >= 1.0:
                    # Cheap young-generation pass; older generations
                    # were frozen above so this stays tiny.
                    with self.perf.section("gc"):
                        gc.collect(0)
                    gc_accum = 0.0
                self._tick(screen, clock, dt)
                self.perf.frame_end()
        finally:
            self.perf.stop()
            self.logistics_mon.stop()
            gc.unfreeze()
            gc.set_threshold(*prev_gc_thresholds)
            if prev_gc_enabled:
                gc.enable()

    def _tick(
        self, screen: pygame.Surface, clock: pygame.time.Clock, dt: float,
    ) -> None:
        assert self.camera is not None

        with self.perf.section("events"):
            for event in pygame.event.get():
                self._handle_event(event)

        # Mid-game cutscene takes precedence over world updates.
        if self._awakening_cutscene is not None and self._awakening_cutscene.active:
            self._awakening_cutscene.tick(dt)
            if not self._awakening_cutscene.active:
                self._awakening_cutscene = None
        elif not self._pause_overlay.visible and not self.world.game_over:
            with self.perf.section("input_camera"):
                self._update_keyboard_pan(dt)
                self._update_alt_overlay()
                self._update_ghost_building()
            with self.perf.section("world_update"):
                self.world.update(dt * self._sim_speed)
                self.world.real_time_elapsed += dt
            # Pending ancient-tech awakening — hand control to the cutscene.
            if (self._awakening_cutscene is None
                    and self.world.ancient.pending_awakening is not None):
                self._start_awakening_cutscene()
            with self.perf.section("logistics_mon"):
                self.logistics_mon.maybe_sample(self.world)
            with self.perf.section("stats_sample"):
                # Sample stats every frame regardless of whether the
                # Stats tab is currently visible — the user wants
                # historical data from t=0, not just from when they
                # first opened the tab.
                self._stats_tab.history.sample(self.world)
            with self.perf.section("research_tier"):
                # Player research progress
                completed = self.tech_tree.update(
                    dt * self._sim_speed, self.world, "SURVIVOR",
                )
                if completed:
                    node = TECH_NODES[completed]
                    self.notifications.push(
                        NOTIF_RESEARCH_COMPLETE.format(name=node.name), (100, 255, 100),
                    )
                # Expose research count for tier checks.
                self.world.player_colony.tech_research_count = self.tech_tree.researched_count
                # Player tier advancement
                if self.tier_tracker.try_advance(self.world, "SURVIVOR"):
                    tier = TIERS[self.tier_tracker.current_tier]
                    next_tier = (
                        TIERS[self.tier_tracker.current_tier + 1]
                        if self.tier_tracker.current_tier + 1 < len(TIERS)
                        else None
                    )
                    self._tier_popup.show(tier, next_tier)
                    self._time_in_current_tier = 0.0
                else:
                    self._time_in_current_tier += dt
            self.notifications.update(dt)
            self._real_time_elapsed += dt
            with self.perf.section("tutorial"):
                # Tutorial triggers
                self._tutorial.check_triggers(self.world, {
                    "time": self.world.time_elapsed,
                    "real_time": self._real_time_elapsed,
                    "dt": dt,
                    "researched_count": self.tech_tree.researched_count,
                    "current_tier_level": self.tier_tracker.current_tier,
                    "time_in_tier": self._time_in_current_tier,
                })
        self.camera.update(dt)
        self._resource_bar.delete_mode = self.delete_mode
        self._resource_bar.sim_speed = self._sim_speed
        self._resource_bar.tier_tracker = self.tier_tracker
        self._resource_bar.tech_tree = self.tech_tree
        self._resource_bar.world = self.world
        with self.perf.section("render_world"):
            self.renderer.draw(screen, self.world, self.camera, dt=dt)
        with self.perf.section("supply_lines"):
            # Supply chain lines for selected building
            draw_supply_lines(
                screen, self.world, self.camera,
                self.renderer.selected_hex, self.renderer._water_tick,
                self.settings.hex_size,
            )
        with self.perf.section("ui_draw"):
            self.ui.draw(screen, self.world)
            self.notifications.draw(screen)
            if self.god_mode and self._spawn_enemy_mode is not None:
                self._draw_spawn_tool_hud(screen)
        if self._awakening_cutscene is not None:
            self._awakening_cutscene.draw_overlay(screen)

        with self.perf.section("flip"):
            pygame.display.flip()

    # ── Event handling ───────────────────────────────────────────

    def _handle_event(self, event: pygame.event.Event) -> None:
        assert self.camera is not None

        if event.type == pygame.QUIT:
            self.running = False
            self.quit_to_desktop = True
            return

        # Cutscene swallows input first while playing.
        if self._awakening_cutscene is not None and self._awakening_cutscene.active:
            self._awakening_cutscene.handle_event(event)
            return

        # Let UI consume events first
        # Sync game-over overlay before event dispatch to avoid 1-frame leak
        self._game_over_overlay.active = self.world.game_over
        if self.ui.handle_event(event):
            return

        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
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
                    self._pause_overlay.show()
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
            elif event.key in (pygame.K_h, pygame.K_i):
                self._help_overlay.toggle()
            elif event.key == pygame.K_1:
                self._sim_speed = 3.0
            elif event.key == pygame.K_2:
                self._sim_speed = 6.0
            elif event.key == pygame.K_3:
                self._sim_speed = 9.0
            elif event.key == pygame.K_5:
                self._sim_speed = 30.0
            elif event.key == pygame.K_F1:
                # Toggle god mode at runtime
                self.god_mode = not self.god_mode
                msg = NOTIF_GOD_MODE_ON if self.god_mode else NOTIF_GOD_MODE_OFF
                col = (255, 215, 0) if self.god_mode else (200, 200, 200)
                self.notifications.push(msg, col)
                if not self.god_mode:
                    # Disable any active god-only tools.
                    self._spawn_enemy_mode = None
            elif event.key == pygame.K_F2 and self.god_mode:
                # Cycle the enemy-spawn tool: None -> SCOUT -> BRUTE
                # -> COLOSSUS -> None.
                self._cycle_spawn_enemy_mode()

        elif event.type == pygame.VIDEORESIZE:
            screen = pygame.display.get_surface()
            w, h = screen.get_width(), screen.get_height()
            self.camera.resize(w, h)
            self.ui.layout(w, h)

        elif event.type == pygame.MOUSEBUTTONDOWN:
            if event.button == 1:  # left click
                self._on_left_click(event.pos)
                # PATH/WALL use click-to-anchor chain placement; no drag.
                if (self.build_mode is not None
                        and self.build_mode not in (BuildingType.PATH, BuildingType.WALL)):
                    self._build_dragging = True
                elif self.delete_mode:
                    self._delete_dragging = True
            elif event.button == 2:  # middle click — pan start
                self.camera.start_drag(event.pos)
                self._drag_button = 2
            elif event.button == 3:  # right click
                if self._spawn_enemy_mode is not None:
                    self._spawn_enemy_mode = None
                    self.notifications.push(NOTIF_GOD_SPAWN_OFF, (200, 200, 200))
                elif self.build_mode is not None:
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
                elif self.renderer.selected_hex is not None:
                    self.renderer.selected_hex = None
                    self._building_info.building = None
                    self._tile_info.tile = None
                else:
                    self.camera.start_drag(event.pos)
                    self._drag_button = 3

        elif event.type == pygame.MOUSEBUTTONUP:
            if event.button == 1:
                self._build_dragging = False
                self._delete_dragging = False
            if event.button in (2, 3) and event.button == self._drag_button:
                self.camera.stop_drag()
                self._drag_button = 0

        elif event.type == pygame.MOUSEMOTION:
            # If the user released the drag button while outside the
            # window (or over a UI element that swallowed the event),
            # pygame may never deliver MOUSEBUTTONUP — the camera
            # would stay glued to the cursor.  Re-poll the actual
            # button state and stop the drag if it's no longer held.
            if self._drag_button:
                pressed = pygame.mouse.get_pressed(num_buttons=5)
                if not pressed[self._drag_button - 1]:
                    self.camera.stop_drag()
                    self._drag_button = 0
                else:
                    self.camera.drag(event.pos)
            if self._build_dragging and self.build_mode is not None:
                if not pygame.mouse.get_pressed(num_buttons=5)[0]:
                    self._build_dragging = False
                else:
                    wx, wy = self.camera.screen_to_world(*event.pos)
                    coord = pixel_to_hex(wx, wy, self.settings.hex_size)
                    if coord in self.world.grid:
                        self._try_place_building(coord)
            elif self._delete_dragging and self.delete_mode:
                if not pygame.mouse.get_pressed(num_buttons=5)[0]:
                    self._delete_dragging = False
                else:
                    wx, wy = self.camera.screen_to_world(*event.pos)
                    coord = pixel_to_hex(wx, wy, self.settings.hex_size)
                    if coord in self.world.grid:
                        self._try_delete_building(coord)

        elif event.type in (
            pygame.WINDOWLEAVE, pygame.WINDOWFOCUSLOST,
            pygame.WINDOWMINIMIZED,
        ):
            # Cursor left the window or window lost focus — cancel
            # any in-progress drag so it doesn't get stuck on.
            if self._drag_button:
                self.camera.stop_drag()
                self._drag_button = 0
            self._build_dragging = False
            self._delete_dragging = False

        elif event.type == pygame.MOUSEWHEEL:
            pos = pygame.mouse.get_pos()
            factor = 1.1 ** event.y
            self.camera.zoom_at(pos, factor)

    # ── Keyboard camera pan ────────────────────────────────────────

    _PAN_SPEED = 400  # world-pixels per second at zoom 1.0

    def _update_keyboard_pan(self, dt: float) -> None:
        assert self.camera is not None
        keys = pygame.key.get_pressed()
        dx = dy = 0.0
        if keys[pygame.K_w] or keys[pygame.K_UP]:
            dy -= 1
        if keys[pygame.K_s] or keys[pygame.K_DOWN]:
            dy += 1
        if keys[pygame.K_a] or keys[pygame.K_LEFT]:
            dx -= 1
        if keys[pygame.K_d] or keys[pygame.K_RIGHT]:
            dx += 1
        if dx or dy:
            speed = self._PAN_SPEED / self.camera.zoom * dt
            self.camera.x += dx * speed
            self.camera.y += dy * speed

    # ── Click actions ────────────────────────────────────────────

    def _on_left_click(self, screen_pos: tuple[int, int]) -> None:
        assert self.camera is not None
        wx, wy = self.camera.screen_to_world(*screen_pos)
        coord = pixel_to_hex(wx, wy, self.settings.hex_size)

        if coord not in self.world.grid:
            return

        # God-mode enemy spawn tool takes precedence over all other
        # left-click actions (build/delete/select).
        if self.god_mode and self._spawn_enemy_mode is not None:
            self._spawn_enemy_at(coord)
            return

        if self.delete_mode:
            self._try_delete_building(coord)
        elif self.build_mode is not None:
            if self.build_mode in (BuildingType.PATH, BuildingType.WALL):
                self._handle_path_click(coord)
            else:
                self._try_place_building(coord)
        else:
            # Select tile
            self.renderer.selected_hex = coord
            # Show building info if there's a building, otherwise show tile info
            building = self.world.buildings.at(coord)
            if building is not None and building.faction == "SURVIVOR":
                self._building_info.building = building
                self._tile_info.tile = None
                self._tile_info.has_ruin = False
            else:
                # Empty tile or non-player building: show tile info.
                # so the player still gets terrain context.
                self._building_info.building = None
                tile = self.world.grid.get(coord)
                self._tile_info.tile = tile
                self._tile_info.coord = coord
                self._tile_info.has_ruin = self.renderer.has_ruin_at(coord)

    # ── God-mode enemy spawn tool ────────────────────────────────

    def _cycle_spawn_enemy_mode(self) -> None:
        """F2 in god mode cycles through enemy types and OFF."""
        from compprog_pygame.games.hex_colony import params
        types = list(params.ENEMY_TYPE_DATA.keys())
        if self._spawn_enemy_mode is None:
            self._spawn_enemy_mode = types[0] if types else None
        else:
            try:
                idx = types.index(self._spawn_enemy_mode)
            except ValueError:
                idx = -1
            nxt = idx + 1
            self._spawn_enemy_mode = types[nxt] if nxt < len(types) else None
        if self._spawn_enemy_mode is None:
            self.notifications.push(NOTIF_GOD_SPAWN_OFF, (200, 200, 200))
        else:
            # Disable conflicting build/delete modes while spawn tool is active.
            self.build_mode = None
            self._build_dragging = False
            self.delete_mode = False
            btab = self._bottom_bar.buildings_tab
            if btab:
                btab.selected_building = None
                btab.delete_active = False
            label = self._spawn_enemy_mode.title()
            self.notifications.push(
                NOTIF_GOD_SPAWN_ON.format(name=label), (255, 215, 0),
            )

    def _spawn_enemy_at(self, coord) -> None:
        """Spawn one enemy of the active spawn-tool type at ``coord``."""
        type_name = self._spawn_enemy_mode
        if type_name is None:
            return
        combat = getattr(self.world, "combat", None)
        if combat is None:
            return
        # Reuse the existing helper, but force the spawn point to the
        # exact clicked tile (not a random nearby walkable hex) so the
        # tool feels precise.
        from compprog_pygame.games.hex_colony import params
        from compprog_pygame.games.hex_colony.combat import Enemy
        from compprog_pygame.games.hex_colony.hex_grid import hex_to_pixel
        data = params.ENEMY_TYPE_DATA.get(type_name)
        if data is None:
            return
        e = Enemy(
            type_name=type_name,
            coord=coord,
            health=float(data["hp"]),
            max_health=float(data["hp"]),
            damage=float(data["damage"]),
            bounty=int(data.get("bounty", 0)),
        )
        e.attack_timer = float(data["attack_cd"])
        e.move_timer = float(data["move_period"])
        wx, wy = hex_to_pixel(coord, self.settings.hex_size)
        e.px, e.py = wx, wy
        e.next_target_px, e.next_target_py = wx, wy
        combat.enemies.append(e)

    def _draw_spawn_tool_hud(self, surface) -> None:
        """Small banner near the cursor showing the active enemy type."""
        if self._spawn_enemy_mode is None:
            return
        from compprog_pygame.games.hex_colony import params
        data = params.ENEMY_TYPE_DATA.get(self._spawn_enemy_mode)
        if data is None:
            return
        mx, my = pygame.mouse.get_pos()
        label = f"Spawn: {self._spawn_enemy_mode.title()}"
        text = self._hint_font.render(label, True, (255, 230, 120))
        pad = 6
        bw, bh = text.get_width() + pad * 2, text.get_height() + pad * 2
        bx, by = mx + 18, my + 18
        sw, sh = surface.get_size()
        if bx + bw > sw:
            bx = sw - bw - 4
        if by + bh > sh:
            by = sh - bh - 4
        bg = pygame.Surface((bw, bh), pygame.SRCALPHA)
        bg.fill((20, 20, 30, 200))
        surface.blit(bg, (bx, by))
        pygame.draw.rect(surface, (255, 215, 0), (bx, by, bw, bh), 1)
        # Color preview swatch
        col = data.get("color", (200, 200, 200))
        pygame.draw.circle(surface, col, (bx + pad + 4, by + bh // 2), 5)
        surface.blit(text, (bx + pad + 14, by + pad))

    # ── Mid-game cutscenes ───────────────────────────────────────

    def _start_awakening_cutscene(self) -> None:
        """Spin up the awakening cutscene for the pending event."""
        assert self.camera is not None
        event = self.world.ancient.pending_awakening
        if event is None:
            return

        threat = self.world.ancient

        def _apply(tower):
            changed = threat.apply_tower(self.world, tower)
            # Mark every changed coord dirty so the renderer redraws
            # them with the wasteland palette.
            for c in changed:
                self.renderer.invalidate_tile(c)
                self._minimap.invalidate(c)

        def _commit(tower):
            threat.commit_tower(tower)

        def _finish():
            threat.finalize_event()

        self._awakening_cutscene = AwakeningCutscene(
            event, self.world, self.camera,
            on_apply_tower=_apply,
            on_commit_tower=_commit,
            on_finish=_finish,
        )
        # Push a one-shot toast so the player knows what just started.
        self.notifications.push(
            NOTIF_AWAKENING_TRIGGERED, (220, 130, 255),
        )

    def _try_place_building(self, coord, silent: bool = False) -> bool:
        tile = self.world.grid[coord]
        # Can't build on unbuildable terrain (water, mountain, oil pool) —
        # except bridges on water and oil drills on oil deposits.
        if tile.terrain in UNBUILDABLE:
            if not (self.build_mode == BuildingType.BRIDGE and tile.terrain == Terrain.WATER) \
               and not (self.build_mode == BuildingType.OIL_DRILL and tile.terrain == Terrain.OIL_DEPOSIT):
                return False
        # Oil drills must go on oil deposits — no exceptions.
        if self.build_mode == BuildingType.OIL_DRILL and tile.terrain != Terrain.OIL_DEPOSIT:
            if not silent:
                self.notifications.push(
                    "Oil Drill must be placed on an Oil Deposit", (255, 150, 80),
                )
            return False
        # Tech tree gate (bypassed in god mode)
        if not self.god_mode and not self.tech_tree.is_building_unlocked(self.build_mode):
            req = TECH_REQUIREMENTS.get(self.build_mode)
            if req is not None and not silent:
                node = TECH_NODES[req]
                self.notifications.push(
                    NOTIF_REQUIRES_RESEARCH.format(name=node.name), (255, 150, 80),
                )
            return False
        # Tier gate (bypassed in god mode)
        if not self.god_mode and not self.tier_tracker.is_building_unlocked(self.build_mode):
            req_tier = TIER_BUILDING_REQUIREMENTS.get(self.build_mode, 0)
            tier_info = TIERS[req_tier]
            if not silent:
                self.notifications.push(
                    NOTIF_REQUIRES_TIER.format(level=req_tier, name=tier_info.name), (255, 150, 80),
                )
            return False
        # Check existing building
        existing = tile.building
        _PATH_LIKE = {BuildingType.PATH, BuildingType.BRIDGE, BuildingType.CONVEYOR}
        if existing is not None:
            # Cannot build on top of (or replace) an AI building.
            if existing.faction != "SURVIVOR":
                return False
            # Can only build on top of a path/bridge (not wall, camp, or other buildings)
            if existing.type not in _PATH_LIKE:
                return False
            # Can't place another path-like or wall on a path-like
            if self.build_mode in _PATH_LIKE or self.build_mode == BuildingType.WALL:
                return False
        # Check cost (skip in sandbox or god mode)
        free_build = self.sandbox or self.god_mode
        if not free_build:
            if self.world.building_inventory[self.build_mode] < 1:
                return False  # no stock
            self.world.building_inventory.spend(self.build_mode)
        # If building on top of a path/bridge, return it to inventory
        if existing is not None and existing.type in _PATH_LIKE:
            if not free_build:
                self.world.building_inventory.add(existing.type)
            self.world.buildings.remove(existing)
            tile.building = None
        # Place building
        building = self.world.buildings.place(self.build_mode, coord)
        tile.building = building
        # Quarry QoL: when the only mineable resource in range is a
        # single ore type (iron OR copper, but not both, and no
        # stone/mountain), auto-select it so the player doesn't have
        # to open the building panel and click.  Stone remains the
        # default (quarry_output=None) whenever stone is available.
        if self.build_mode == BuildingType.QUARRY:
            self._auto_select_quarry_output(building)
        # Clear overlays on the tile so building is visible — but keep
        # them under paths/bridges so the player still sees the tree /
        # ore / fiber sprite under the path tile.
        if self.build_mode not in _PATH_LIKE:
            self.renderer.remove_overlays_at(coord, self.settings.hex_size)
        self._minimap.invalidate(coord)
        # Record to blueprint if recording
        if self.blueprints.is_recording:
            self.blueprints.record_building(coord, self.build_mode)
        # Notification
        if not silent:
            self.notifications.push(NOTIF_BUILT.format(name=building_label(self.build_mode.name)))
        self.world.mark_housing_dirty()
        # Trigger 2: notify the ancient-tech threat about ruin disturbance.
        self.world.ancient.notify_built(self.world, building)
        return True

    def _handle_path_click(self, coord) -> None:
        """Path chain placement.

        First click sets the chain anchor (no path placed yet —
        a green preview shows the hypothetical route).
        Second click computes the route from the anchor to the
        clicked tile (using bridges for water crossings if the player
        has them unlocked and in stock), places the appropriate
        building type on each tile along the route *including the
        anchor*, truncated by inventory, and moves the anchor to the
        last placed tile so the chain can continue.
        """
        if self._path_anchor is None:
            # First click — just set the anchor, don't place anything.
            tile = self.world.grid.get(coord)
            if tile is None:
                return
            self._path_anchor = coord
            return

        if coord == self._path_anchor:
            # Re-clicking the anchor cancels the chain.
            self._path_anchor = None
            self.renderer.path_preview = []
            return

        # WALL chain placement: simple hex-line from anchor to clicked
        # tile, place WALL on every empty land tile along the way
        # (skipping existing buildings, water, mountains).
        if self.build_mode == BuildingType.WALL:
            line_coords = _hex_line(self._path_anchor, coord)
            free_build = self.sandbox or self.god_mode
            wall_stock = (
                10 ** 9 if free_build
                else self.world.building_inventory[BuildingType.WALL]
            )
            placed = 0
            last_placed: HexCoord | None = None
            original_mode = self.build_mode
            try:
                for step in line_coords:
                    tile = self.world.grid.get(step)
                    if tile is None:
                        break
                    if tile.building is not None:
                        last_placed = step
                        continue
                    if wall_stock <= 0:
                        break
                    self.build_mode = BuildingType.WALL
                    if self._try_place_building(step, silent=True):
                        placed += 1
                        last_placed = step
                        wall_stock -= 1
                    else:
                        # Skip this hex but continue (e.g. water)
                        continue
            finally:
                self.build_mode = original_mode
            if last_placed is not None:
                self._path_anchor = last_placed
            return

        bridges_unlocked = (
            self.god_mode
            or (self.tech_tree.is_building_unlocked(BuildingType.BRIDGE)
                and self.tier_tracker.is_building_unlocked(BuildingType.BRIDGE))
        )
        free_build = self.sandbox or self.god_mode
        bridge_stock = (
            10 ** 9 if free_build
            else self.world.building_inventory[BuildingType.BRIDGE]
        )
        route = self.world.find_path_route(
            self._path_anchor, coord,
            allow_bridges=bridges_unlocked,
            bridge_stock=bridge_stock,
        )
        if not route:
            # Unreachable / unbuildable target — move anchor here.
            tile = self.world.grid.get(coord)
            if tile is not None:
                self._path_anchor = coord
            else:
                self._path_anchor = None
                self.renderer.path_preview = []
            return

        # Prepend the anchor tile itself to the route so it gets
        # placed as well (unless it already has a building).
        anchor_tile = self.world.grid.get(self._path_anchor)
        if (anchor_tile is not None
                and anchor_tile.building is None):
            from compprog_pygame.games.hex_colony.hex_grid import Terrain
            if anchor_tile.terrain == Terrain.WATER:
                anchor_btype = BuildingType.BRIDGE
            else:
                anchor_btype = BuildingType.PATH
            route = [(self._path_anchor, anchor_btype)] + list(route)

        path_stock = (
            10 ** 9 if free_build
            else self.world.building_inventory[BuildingType.PATH]
        )
        bridge_stock_left = bridge_stock

        placed = 0
        last_placed: HexCoord | None = None
        original_mode = self.build_mode
        try:
            for step, btype in route:
                tile = self.world.grid.get(step)
                if tile is None:
                    break
                if tile.building is not None:
                    # Already a path/bridge here — skip without spending.
                    last_placed = step
                    continue
                if btype == BuildingType.BRIDGE:
                    if bridge_stock_left <= 0:
                        break
                else:
                    if path_stock <= 0:
                        break
                self.build_mode = btype
                if self._try_place_building(step, silent=True):
                    placed += 1
                    last_placed = step
                    if btype == BuildingType.BRIDGE:
                        bridge_stock_left -= 1
                    else:
                        path_stock -= 1
                else:
                    break
        finally:
            self.build_mode = original_mode

        if placed > 0:
            label = "tile" if placed == 1 else "tiles"
            self.notifications.push(NOTIF_BUILT_PATH.format(count=placed, label=label))
        # Exit path placement mode after placing.
        self._path_anchor = None
        self.renderer.path_preview = []
        self.build_mode = None
        btab = self._bottom_bar.buildings_tab
        if btab:
            btab.selected_building = None

    def _auto_select_quarry_output(self, building) -> None:
        """If a freshly-placed quarry has exactly one ore type in range
        (and no stone source), default its output to that ore so the
        player doesn't have to open the building panel."""
        from compprog_pygame.games.hex_colony.supply_chain import _hex_range
        from compprog_pygame.games.hex_colony.resources import Resource
        grid = self.world.grid
        has_stone = False
        has_iron = False
        has_copper = False
        for nb in _hex_range(building.coord, params.COLLECTION_RADIUS):
            if nb == building.coord:
                continue
            tile = grid.get(nb)
            if tile is None:
                continue
            t = tile.terrain
            if t in (Terrain.STONE_DEPOSIT, Terrain.MOUNTAIN):
                has_stone = True
            elif t == Terrain.IRON_VEIN:
                has_iron = True
            elif t == Terrain.COPPER_VEIN:
                has_copper = True
        # Stone is the default output (quarry_output=None).  Only
        # auto-switch when stone isn't available AND exactly one ore
        # type is present.
        if has_stone:
            return
        if has_iron and not has_copper:
            building.quarry_output = Resource.IRON
        elif has_copper and not has_iron:
            building.quarry_output = Resource.COPPER

    def _try_delete_building(self, coord) -> None:
        """Delete a building at the given coordinate, refunding half its cost."""
        tile = self.world.grid[coord]
        building = tile.building
        if building is None:
            return
        # Can't delete the camp
        if building.type == BuildingType.CAMP:
            return
        # Player cannot demolish non-player faction buildings.
        if building.faction != "SURVIVOR":
            return
        # Unassign workers and residents referencing this building
        for person in self.world.population.people:
            if person.workplace is building:
                person.workplace = None
                person.carry_resource = None
                person.target_hex = None
                person.task = Task.IDLE
                person.path = []
                building.workers = max(0, building.workers - 1)
            if person.home is building:
                person.home = None
        # Return building to inventory
        if not self.sandbox:
            self.world.building_inventory.add(building.type)
        # Remove building
        self.world.buildings.remove(building)
        tile.building = None
        # Restore the overlay pixel art (trees, ore crystals, fiber,
        # etc.) that was NaN-marked when the building was originally
        # placed on this tile.  Without this call, deleting a quarry
        # from an iron vein leaves a bare tile even though the ore
        # is still there.
        self.renderer.regenerate_overlays_at(coord, self.world)
        # Targeted tile layer redraw so cleared tile shows terrain
        self.renderer.invalidate_tile(coord)
        self._minimap.invalidate(coord)
        self.world.mark_housing_dirty()

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

    def _on_pause_resume(self) -> None:
        """Callback from pause overlay Resume button."""

    def _on_open_tech_tree(self) -> None:
        """Open the tech tree overlay and pause the game."""
        self._tech_tree_overlay.visible = True
        self._tech_tree_overlay.tech_tree = self.tech_tree

    def _on_close_tech_tree(self) -> None:
        """Close the tech tree overlay (unpause is automatic — overlay consumes events)."""
        pass

    def _on_open_advanced_stats(self) -> None:
        """Open the Advanced Statistics popup."""
        self._advanced_stats_overlay.visible = True

    def _on_open_worker_priority(self) -> None:
        """Open the Edit Worker Priority drag-drop modal."""
        self._worker_priority_overlay.visible = True

    def _on_toggle_worker_auto(self, net_id: int | None) -> None:
        """Toggle worker-priority auto mode for the selected network.
        When turning auto on, immediately recompute the flat tier list
        and auto logistics target."""
        if net_id is None:
            return
        for n in self.world.networks:
            if n.id == net_id:
                n.worker_auto = not n.worker_auto
                if n.worker_auto:
                    self.world._refresh_worker_priorities(
                        {n.id: n for n in self.world.networks},
                    )
                return

    def _on_open_demand_priority(self) -> None:
        """Open the Edit Resource Demand drag-drop modal."""
        self._demand_priority_overlay.visible = True

    def _on_toggle_demand_auto(self, net_id: int | None) -> None:
        """Bottom-bar Auto button: flip the selected network's auto
        flag.  When turning auto back on, immediately recompute the
        tier layout so the player sees the change without waiting for
        the next network rebuild."""
        if net_id is None:
            return
        for n in self.world.networks:
            if n.id == net_id:
                n.demand_auto = not n.demand_auto
                if n.demand_auto:
                    n.demand_priority = self.world._auto_demand_tiers(
                        list(n.buildings),
                    )
                return

    def _on_open_supply_priority(self) -> None:
        """Open the Edit Resource Supply drag-drop modal."""
        self._supply_priority_overlay.visible = True

    def _on_toggle_supply_auto(self, net_id: int | None) -> None:
        if net_id is None:
            return
        for n in self.world.networks:
            if n.id == net_id:
                n.supply_auto = not n.supply_auto
                if n.supply_auto:
                    n.supply_priority = self.world._auto_supply_tiers(
                        list(n.buildings),
                    )
                return

    def _on_pause_return_to_menu(self) -> None:
        """Callback from pause overlay Return to Main Menu button."""
        self.running = False

    def _on_pause_quit(self) -> None:
        """Callback from pause overlay Quit button."""
        self.running = False
        self.quit_to_desktop = True

    def _on_graphics_changed(self, quality: str) -> None:
        """Callback from options menu when graphics quality changes."""
        self.renderer.graphics_quality = quality

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
            if target.workplace is not None:
                target.workplace.workers = max(0, target.workplace.workers - 1)
            pop.people.remove(target)
        self.world.mark_population_changed()

    # ── Alt overlay toggle ───────────────────────────────────────

    def _update_alt_overlay(self) -> None:
        """Show resource overlay while Alt is held."""
        keys = pygame.key.get_pressed()
        self.renderer.show_resource_overlay = keys[pygame.K_LALT] or keys[pygame.K_RALT]

    # ── Ghost building preview ───────────────────────────────────

    def _update_ghost_building(self) -> None:
        """Update the ghost building preview coord based on mouse position."""
        assert self.camera is not None
        if self.build_mode is None:
            self.renderer.ghost_building = None
            self.renderer.ghost_coord = None
            self.renderer.ghost_valid = False
            self.renderer.path_preview = []
            self._path_anchor = None
            return

        # Switching to a non-chain build mode cancels any chain anchor.
        if self.build_mode not in (BuildingType.PATH, BuildingType.WALL):
            self._path_anchor = None

        self.renderer.ghost_building = self.build_mode
        mx, my = pygame.mouse.get_pos()
        wx, wy = self.camera.screen_to_world(mx, my)
        coord = pixel_to_hex(wx, wy, self.settings.hex_size)

        # Show ghost on any valid grid tile; mark red if not placeable
        if coord in self.world.grid:
            self.renderer.ghost_coord = coord
            self.renderer.ghost_valid = self._can_place_at(coord)
        else:
            self.renderer.ghost_coord = None
            self.renderer.ghost_valid = False

        # Wall chain preview (straight hex line).
        if (self.build_mode == BuildingType.WALL
                and self._path_anchor is not None
                and self.renderer.ghost_coord is not None
                and self.renderer.ghost_coord != self._path_anchor):
            self.renderer.path_preview = _hex_line(
                self._path_anchor, self.renderer.ghost_coord,
            )
            return

        # Path chain preview
        if (self.build_mode == BuildingType.PATH
                and self._path_anchor is not None
                and self.renderer.ghost_coord is not None
                and self.renderer.ghost_coord != self._path_anchor):
            bridges_unlocked = (
                self.god_mode
                or (self.tech_tree.is_building_unlocked(BuildingType.BRIDGE)
                    and self.tier_tracker.is_building_unlocked(BuildingType.BRIDGE))
            )
            free_build = self.sandbox or self.god_mode
            bridge_stock = (
                10 ** 9 if free_build
                else self.world.building_inventory[BuildingType.BRIDGE]
            )
            cache_key = (
                self._path_anchor,
                self.renderer.ghost_coord,
                bridges_unlocked,
                bridge_stock,
                self.world._topology_version,
            )
            if cache_key == self._path_preview_cache_key:
                route = self._path_preview_cache_route
            else:
                route = self.world.find_path_route(
                    self._path_anchor, self.renderer.ghost_coord,
                    allow_bridges=bridges_unlocked,
                    bridge_stock=bridge_stock,
                )
                self._path_preview_cache_key = cache_key
                self._path_preview_cache_route = route
            if route:
                # Prepend anchor tile so preview includes it.
                anchor_tile = self.world.grid.get(self._path_anchor)
                full_route = []
                if anchor_tile is not None and anchor_tile.building is None:
                    full_route.append((self._path_anchor, BuildingType.PATH))
                full_route.extend(route)
                if free_build:
                    self.renderer.path_preview = [c for c, _ in full_route]
                else:
                    path_stock = self.world.building_inventory[BuildingType.PATH]
                    bridge_stock_left = bridge_stock
                    preview: list[HexCoord] = []
                    for step, btype in full_route:
                        tile = self.world.grid.get(step)
                        if tile is not None and tile.building is None:
                            if btype == BuildingType.BRIDGE:
                                if bridge_stock_left <= 0:
                                    break
                                bridge_stock_left -= 1
                            else:
                                if path_stock <= 0:
                                    break
                                path_stock -= 1
                        preview.append(step)
                    self.renderer.path_preview = preview
            else:
                self.renderer.path_preview = []
        elif (self.build_mode in (BuildingType.PATH, BuildingType.WALL)
              and self._path_anchor is not None):
            # Show anchor tile highlighted even before a second point
            # is chosen, so the player sees where the chain starts.
            self.renderer.path_preview = [self._path_anchor]
        else:
            self.renderer.path_preview = []

    def _can_place_at(self, coord) -> bool:
        """Check if the current build_mode can be placed at coord."""
        from compprog_pygame.games.hex_colony.procgen import UNBUILDABLE
        tile = self.world.grid.get(coord)
        if tile is None:
            return False
        if tile.terrain in UNBUILDABLE:
            if not (self.build_mode == BuildingType.BRIDGE and tile.terrain == Terrain.WATER):
                return False
        # Tech tree gate
        if not self.tech_tree.is_building_unlocked(self.build_mode):
            return False
        # Tier gate
        if not self.tier_tracker.is_building_unlocked(self.build_mode):
            return False
        # Building inventory check (skip in sandbox)
        if not self.sandbox:
            if self.world.building_inventory[self.build_mode] < 1:
                return False
        _PATH_LIKE = {BuildingType.PATH, BuildingType.BRIDGE, BuildingType.CONVEYOR}
        existing = tile.building
        if existing is not None:
            if existing.type not in _PATH_LIKE:
                return False
            if self.build_mode in _PATH_LIKE or self.build_mode == BuildingType.WALL:
                return False
        return True
