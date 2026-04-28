"""Combat system — ancient mechanical enemies versus the player.

This module owns every runtime entity related to combat:

* :class:`Enemy`            — a moving ancient machine with HP and damage.
* :class:`Projectile`       — a turret/camp laser bolt in flight.
* :class:`CombatManager`    — per-frame tick: spawns waves, moves enemies,
  resolves attacks, fires defensive weapons, removes dead entities.

The simulation is intentionally light-weight:

* enemies move discrete hex-by-hex on a timer (``move_period``) instead of
  pixel-perfect interpolation — keeps the cost down even with hundreds of
  enemies on the field;
* enemy *visual* position is interpolated between hexes for smoothness;
* path-finding is a bounded BFS that treats enemy-blocking buildings
  (walls, factories, the camp …) and impassable terrain as obstacles —
  walls funnel enemies onto turret killzones, exactly like the player
  would expect.

All numeric balance lives in :mod:`params`.
"""

from __future__ import annotations

import heapq
import math
import random as _random
from collections import deque
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from compprog_pygame.games.hex_colony import params
from compprog_pygame.games.hex_colony.buildings import (
    Building, BuildingType,
)
from compprog_pygame.games.hex_colony.hex_grid import (
    HexCoord, hex_to_pixel,
)

if TYPE_CHECKING:
    from compprog_pygame.games.hex_colony.world import World


# ── Enemy / Projectile dataclasses ─────────────────────────────────


@dataclass(slots=True)
class Enemy:
    """A single ancient-tech invader."""
    type_name: str                       # key into params.ENEMY_TYPE_DATA
    coord: HexCoord                      # current logical hex
    px: float = 0.0                      # interpolated pixel x
    py: float = 0.0                      # interpolated pixel y
    target_coord: HexCoord | None = None # next hex on the current path
    next_target_px: float = 0.0
    next_target_py: float = 0.0
    move_timer: float = 0.0              # countdown to next 1-hex step
    attack_timer: float = 0.0            # countdown to next attack swing
    retarget_timer: float = 0.0          # countdown to re-evaluating path
    path: list[HexCoord] = field(default_factory=list)
    health: float = 0.0
    max_health: float = 0.0
    damage: float = 0.0
    bounty: int = 0
    target_building_id: int = 0          # id() of the building the enemy
                                         # is currently chewing on (0 = none)
    dead: bool = False
    # ── Status effects (Frost Turret) ──
    slow_factor: float = 0.0             # 0 = normal, 0.5 = 50% slower
    slow_remaining: float = 0.0          # seconds of slow remaining


@dataclass(slots=True)
class Projectile:
    """A turret / camp-laser bolt travelling to a fixed enemy."""
    src_px: float
    src_py: float
    dst_px: float
    dst_py: float
    travelled: float = 0.0               # distance covered so far (px)
    distance: float = 0.0                # total straight-line distance (px)
    speed: float = 320.0                 # px per second
    damage: float = 10.0
    target_id: int = 0                   # id() of the enemy that was aimed at
    color: tuple[int, int, int] = (255, 200, 100)
    # ── Optional area-of-effect / status effects ──
    splash_radius_px: float = 0.0        # 0 = single-target hit
    splash_falloff: float = 0.5          # damage multiplier for outer ring
    slow_factor: float = 0.0             # 0 = no slow, applied on hit
    slow_duration: float = 0.0           # seconds of slow on hit


# ── Combat manager ─────────────────────────────────────────────────


class CombatManager:
    """Owns enemies + projectiles and ticks the combat loop."""

    def __init__(self) -> None:
        self.enemies: list[Enemy] = []
        self.projectiles: list[Projectile] = []
        # Wave bookkeeping.
        # ``waves_triggered`` counts every wave that has been spawned so
        # far (awakening waves + post-awakening periodic waves).
        self.waves_triggered: int = 0
        self.awakening_waves_triggered: int = 0
        # Cumulative enemy kills across the session (for the
        # game-over summary).
        self.enemies_killed: int = 0
        # Seconds of in-game time until the next post-awakening wave.
        # ``None`` means "not scheduled yet".  Set when the final
        # awakening cutscene finishes.
        self.next_periodic_wave_in: float | None = None
        # Persistent RNG so post-awakening wave variety is deterministic
        # given the world seed.
        self._rng: _random.Random = _random.Random()
        # Cache of every grid hex with walkable terrain.  Terrain is
        # static during a session, so this is built once on first
        # tick and reused forever.  ``invalidate_terrain_cache()``
        # forces a rebuild (e.g. world regen).
        self._terrain_walkable_cache: set[HexCoord] | None = None
        # Cached neighbour-coord table indexed by walkable HexCoord.
        # Built lazily alongside ``_terrain_walkable_cache`` and used
        # by the per-tick BFS to avoid allocating 6 fresh HexCoords
        # for every node \u2014 which used to dominate frame time once
        # enemies were spawned (~470ms / tick at 150 enemies).
        self._walkable_neighbors: dict[HexCoord, tuple[HexCoord, ...]] | None = None
        # Same graph as ``_walkable_neighbors`` but keyed by raw
        # ``(q, r)`` tuples \u2014 used by the multi-source BFS to skip
        # the slow custom ``HexCoord.__hash__`` (~3x BFS speedup).
        self._walkable_neighbors_t: dict[tuple[int, int], tuple[tuple[int, int], ...]] | None = None
        # Cached SURVIVOR-blocker / target / wall scan + multi-source
        # BFS distance field.  Building topology only changes when a
        # building is placed or destroyed, which bumps
        # ``world._topology_version`` \u2014 we just compare that on
        # each tick instead of needing manual invalidation hooks.
        self._cached_topology_version: int = -1
        self._cached_blocker_targets: list[Building] = []
        self._cached_blocker_coords: set[HexCoord] = set()
        self._cached_blocker_by_coord: dict[HexCoord, Building] = {}
        self._cached_wall_coords: set[HexCoord] = set()
        self._cached_target_coords: set[HexCoord] = set()
        self._cached_weapon_buildings: list[tuple[Building, str]] = []
        self._cached_target_dist: dict[tuple[int, int], int] = {}
        self._cached_target_t: set[tuple[int, int]] = set()
        # Pre-built table of axial offsets per ring distance, keyed
        # by max distance.  Used by ``_closest_enemy_in_range`` to
        # iterate only the hexes inside a turret's range.
        self._range_offsets: dict[int, list[tuple[int, int]]] = {}

    def invalidate_terrain_cache(self) -> None:
        """Drop the static walkable-terrain cache (call after world regen)."""
        self._terrain_walkable_cache = None
        self._walkable_neighbors = None
        self._walkable_neighbors_t = None
        self._cached_topology_version = -1

    def _enemy_count_mult(self, world: "World") -> int:
        """Per-difficulty enemy spawn-count multiplier."""
        from compprog_pygame.games.hex_colony.settings import Difficulty
        if (getattr(world.settings, "difficulty", None)
                == Difficulty.DESOLATION):
            return int(params.DESOLATION_ENEMY_COUNT_MULT)
        return 1

    # ── Public hooks ────────────────────────────────────────────

    def configure_seed(self, seed: str) -> None:
        """Seed the RNG once the world seed is known."""
        self._rng = _random.Random(
            (abs(hash(seed)) & 0xFFFFFFFF) ^ 0xC0FFEE
        )

    def spawn_awakening_wave(self, world: "World",
                             tower_coords: list[HexCoord]) -> None:
        """Spawn the wave associated with a freshly-finished awakening.

        ``tower_coords`` are the hexes of the towers that just rose.
        Each tower spits out the per-tower composition for the current
        awakening index; the awakening_index counter is then bumped.
        """
        idx = min(self.awakening_waves_triggered,
                  len(params.WAVE_COMPOSITION_PER_TOWER) - 1)
        comp = params.WAVE_COMPOSITION_PER_TOWER[idx]
        count_mult = self._enemy_count_mult(world)
        for tc in tower_coords:
            for type_name, count in comp:
                for _ in range(count * count_mult):
                    self._spawn_enemy_near(world, type_name, tc)
        self.awakening_waves_triggered += 1
        self.waves_triggered += 1
        # If this was the LAST awakening, schedule the first periodic
        # wave with the configured grace period.
        if (self.awakening_waves_triggered
                >= params.AWAKENING_MAX_COUNT):
            self.next_periodic_wave_in = float(
                params.POST_AWAKENING_GRACE_PERIOD,
            )

    def spawn_periodic_wave(self, world: "World") -> None:
        """Spawn a post-awakening wave from a random map edge."""
        # Roll composition with scaling.
        scale = 1.0 + (self.waves_triggered
                       - self.awakening_waves_triggered
                       ) * params.POST_AWAKENING_COUNT_GROWTH
        pop_bonus = (world.player_population_count
                     // max(1, params.POST_AWAKENING_POP_DIVISOR))
        edge_coord = self._pick_edge_spawn_point(world)
        count_mult = self._enemy_count_mult(world)
        for type_name, base_count in params.POST_AWAKENING_WAVE_COMPOSITION:
            count = max(0, int(round(base_count * scale))) * count_mult
            for _ in range(count):
                self._spawn_enemy_near(world, type_name, edge_coord)
        for _ in range(pop_bonus * count_mult):
            self._spawn_enemy_near(world, "SCOUT", edge_coord)
        self.waves_triggered += 1
        # Schedule the next one.
        post_idx = self.waves_triggered - self.awakening_waves_triggered
        interval = max(
            params.POST_AWAKENING_WAVE_INTERVAL_MIN,
            params.POST_AWAKENING_WAVE_INTERVAL_BASE
            - post_idx * params.POST_AWAKENING_WAVE_INTERVAL_DECAY_PER_WAVE,
        )
        self.next_periodic_wave_in = float(interval)

    # ── Per-frame tick ──────────────────────────────────────────

    def tick(self, world: "World", dt: float) -> None:
        if dt <= 0.0:
            return
        # Schedule periodic waves.
        if self.next_periodic_wave_in is not None:
            self.next_periodic_wave_in -= dt
            if self.next_periodic_wave_in <= 0.0:
                self.spawn_periodic_wave(world)

        # Nothing to simulate? Skip the (potentially expensive)
        # per-tick context build entirely.  Pre-awakening worlds spend
        # all their time in this branch, and the BFS distance field
        # over the whole walkable map was the main culprit behind the
        # "lag on world load" reports.
        if not self.enemies and not self.projectiles:
            return

        # Build all per-tick caches in one place so every sub-tick can
        # read from O(1)-friendly data structures instead of repeating
        # O(buildings) / O(enemies) scans.
        ctx = self._build_tick_context(world)

        if self.enemies:
            self._tick_enemies(world, dt, ctx)
        if self.projectiles:
            self._tick_projectiles(world, dt, ctx)
        # Defensive weapons (camp laser + turrets).
        self._tick_defenders(world, dt, ctx)

        # Sweep dead entities.
        if self.enemies:
            self.enemies[:] = [e for e in self.enemies if not e.dead]
        if self.projectiles:
            self.projectiles[:] = [
                p for p in self.projectiles if p.travelled < p.distance
            ]

    def _build_tick_context(self, world: "World") -> dict:
        """Construct the per-tick caches every sub-tick reuses.

        Returns a dict with:
          - ``valid_coords``     set[HexCoord] of walkable terrain (static).
          - ``blocker_coords``   set[HexCoord] of SURVIVOR blocker buildings.
          - ``blocker_by_coord`` dict[HexCoord, Building].
          - ``blocker_targets``  list[Building] of targetable SURVIVOR blockers.
          - ``weapon_buildings`` list[(Building, str)] for turret/camp.
          - ``enemy_index``      dict[HexCoord, list[Enemy]] (live only).
          - ``enemy_by_id``      dict[int, Enemy].
        """
        # 1) Static terrain walkability + neighbour table \u2014 cached
        # forever (terrain doesn't change).  ``_walkable_neighbors``
        # maps each walkable HexCoord to a tuple of its walkable
        # HexCoord neighbours, so the per-tick BFS doesn't allocate
        # any HexCoords or call ``HexCoord.__hash__`` on offset
        # tuples.  We *also* keep a parallel raw-tuple variant of
        # the same graph keyed by ``(q, r)`` ints \u2014 native tuples
        # hash 2-3x faster than the HexCoord dataclass, which makes
        # the multi-source BFS over a 100k-hex map ~3x cheaper.
        if self._terrain_walkable_cache is None:
            terrain_blockers = params.ENEMY_TERRAIN_BLOCKERS
            self._terrain_walkable_cache = {
                t.coord for t in world.grid.tiles()
                if t.terrain.name not in terrain_blockers
            }
            wset = self._terrain_walkable_cache
            wn: dict[HexCoord, tuple[HexCoord, ...]] = {}
            wnt: dict[tuple[int, int], tuple[tuple[int, int], ...]] = {}
            for c in wset:
                cq, cr = c.q, c.r
                neighbours = (
                    HexCoord(cq + 1, cr),
                    HexCoord(cq + 1, cr - 1),
                    HexCoord(cq, cr - 1),
                    HexCoord(cq - 1, cr),
                    HexCoord(cq - 1, cr + 1),
                    HexCoord(cq, cr + 1),
                )
                walkable_nb = tuple(nb for nb in neighbours if nb in wset)
                wn[c] = walkable_nb
                wnt[(cq, cr)] = tuple((nb.q, nb.r) for nb in walkable_nb)
            self._walkable_neighbors = wn
            self._walkable_neighbors_t = wnt
        valid_coords = self._terrain_walkable_cache
        walkable_neighbors = self._walkable_neighbors
        walkable_neighbors_t = self._walkable_neighbors_t
        assert walkable_neighbors is not None and walkable_neighbors_t is not None

        # 2) Blockers + weapon-bearing buildings \u2014 cached across
        # ticks and rebuilt only when topology changes.  Building
        # placements/removals bump ``world._topology_version`` so
        # comparing it gives us automatic invalidation with no
        # manual hooks at every demolish/place site.  The big cost
        # baked in here is the multi-source BFS distance field; at
        # 150 enemies it cost ~470ms / tick before being cached.
        topo_v = getattr(world, "_topology_version", 0)
        if topo_v != self._cached_topology_version:
            blocker_set = params.ENEMY_BUILDING_BLOCKERS
            wall_set = params.ENEMY_PATHABLE_WALL_TYPES
            blocker_targets: list[Building] = []
            blocker_coords: set[HexCoord] = set()
            blocker_by_coord: dict[HexCoord, Building] = {}
            wall_coords: set[HexCoord] = set()
            target_coords: set[HexCoord] = set()
            weapon_buildings: list[tuple[Building, str]] = []
            TURRET = BuildingType.TURRET
            CANNON = BuildingType.CANNON_TURRET
            MORTAR = BuildingType.MORTAR_TURRET
            FROST = BuildingType.FROST_TURRET
            CAMP = BuildingType.CAMP
            for b in world.buildings.buildings:
                if b.faction != "SURVIVOR":
                    continue
                btype = b.type
                tname = btype.name
                if tname in blocker_set:
                    blocker_targets.append(b)
                    # Multi-tile buildings (e.g. Research Center)
                    # occupy ``b.coord`` plus every coord in
                    # ``b.footprint``.  Register every occupied tile
                    # so (a) the multi-source BFS can spread out from
                    # the entire footprint instead of just the anchor
                    # \u2014 the anchor of a 7-hex flower is fully
                    # surrounded by other footprint tiles, so a BFS
                    # from the anchor alone never escapes \u2014 and
                    # (b) an enemy adjacent to *any* footprint tile
                    # can find the building via ``blocker_by_coord``
                    # and attack it.  Without this, enemies stand on
                    # the outer ring around a Research Center forever
                    # without ever recognising it as a target.
                    is_wall = tname in wall_set
                    for occ in (b.coord, *b.footprint):
                        blocker_coords.add(occ)
                        blocker_by_coord[occ] = b
                        if is_wall:
                            wall_coords.add(occ)
                        else:
                            target_coords.add(occ)
                if btype is TURRET:
                    weapon_buildings.append((b, "TURRET"))
                elif btype is CANNON:
                    weapon_buildings.append((b, "CANNON"))
                elif btype is MORTAR:
                    weapon_buildings.append((b, "MORTAR"))
                elif btype is FROST:
                    weapon_buildings.append((b, "FROST"))
                elif btype is CAMP:
                    weapon_buildings.append((b, "CAMP"))

            # Multi-source BFS distance field used as the A*
            # heuristic for the (common) walls-solid pathfinding
            # phase.  Walls and other real targets act as obstacles.
            #
            # Two perf tricks:
            #   * Run the BFS in raw ``(q, r)`` tuple space \u2014 native
            #     tuples hash ~3x faster than the custom HexCoord
            #     dataclass, and we only convert back at the end.
            #   * Cap the spread depth at ``BFS_MAX_DEPTH`` (which is
            #     a multiple of ENEMY_PATHFIND_MAX_DEPTH).  Hexes
            #     further than the cap aren't reachable by phase-1
            #     A* anyway \u2014 enemies that far out wander toward
            #     the camp until they get into BFS range.  On a
            #     ~120k-hex map this cuts rebuild from ~800ms to
            #     ~50ms.
            target_dist: dict[tuple[int, int], int] = {}
            # Cap how far the BFS spreads.  The heuristic is only
            # consulted by phase-1 gradient descent, which itself
            # caps at ``cur_d + 4`` steps from the enemy's start.
            # Anything beyond ``BFS_MAX_DEPTH`` hexes from a target
            # is irrelevant to phase-1 pathing \u2014 enemies that far
            # out simply wander toward the camp until they enter
            # range.  On a ~120k-hex map this caps rebuild at the
            # area of the BFS ball (\u224b 3 d\u00b2) rather than the
            # entire map.
            BFS_MAX_DEPTH = int(getattr(
                params, "ENEMY_BFS_MAX_DEPTH", 200,
            ))
            if target_coords:
                wall_t: set[tuple[int, int]] = {
                    (c.q, c.r) for c in wall_coords
                }
                target_t: set[tuple[int, int]] = {
                    (c.q, c.r) for c in target_coords
                }
                queue_t: deque[tuple[int, int]] = deque()
                for tt in target_t:
                    target_dist[tt] = 0
                    queue_t.append(tt)
                wnt_get = walkable_neighbors_t.get
                EMPTY_T: tuple[tuple[int, int], ...] = ()
                while queue_t:
                    cur_t = queue_t.popleft()
                    d = target_dist[cur_t] + 1
                    if d > BFS_MAX_DEPTH:
                        continue
                    for nb_t in wnt_get(cur_t, EMPTY_T):
                        if nb_t in target_dist:
                            continue
                        if nb_t in wall_t or nb_t in target_t:
                            continue
                        target_dist[nb_t] = d
                        queue_t.append(nb_t)

            self._cached_blocker_targets = blocker_targets
            self._cached_blocker_coords = blocker_coords
            self._cached_blocker_by_coord = blocker_by_coord
            self._cached_wall_coords = wall_coords
            self._cached_target_coords = target_coords
            self._cached_weapon_buildings = weapon_buildings
            self._cached_target_dist = target_dist
            # Cache the tuple-keyed target set too so phase-1
            # gradient descent doesn't have to rebuild it on every
            # retarget.
            self._cached_target_t = (
                target_t if target_coords else set()
            )
            self._cached_topology_version = topo_v

        blocker_targets = self._cached_blocker_targets
        blocker_coords = self._cached_blocker_coords
        blocker_by_coord = self._cached_blocker_by_coord
        wall_coords = self._cached_wall_coords
        target_coords = self._cached_target_coords
        weapon_buildings = self._cached_weapon_buildings
        target_dist = self._cached_target_dist

        # 3) Spatial enemy index + id lookup for projectiles.
        enemy_index: dict[HexCoord, list[Enemy]] = {}
        enemy_by_id: dict[int, Enemy] = {}
        for e in self.enemies:
            if e.dead:
                continue
            enemy_by_id[id(e)] = e
            bucket = enemy_index.get(e.coord)
            if bucket is None:
                enemy_index[e.coord] = [e]
            else:
                bucket.append(e)

        return {
            "valid_coords": valid_coords,
            "walkable_neighbors": walkable_neighbors,
            "walkable_neighbors_t": walkable_neighbors_t,
            "blocker_coords": blocker_coords,
            "blocker_by_coord": blocker_by_coord,
            "blocker_targets": blocker_targets,
            "wall_coords": wall_coords,
            "target_coords": target_coords,
            "target_t": self._cached_target_t,
            "weapon_buildings": weapon_buildings,
            "enemy_index": enemy_index,
            "enemy_by_id": enemy_by_id,
            "target_dist": target_dist,
        }

    def _range_offsets_for(self, range_hex: int) -> list[tuple[int, int]]:
        """Return cached axial offsets covering all hexes within ``range_hex``.

        Sorted by hex distance ascending so callers iterate inner rings
        first \u2014 letting them break out as soon as a target is found at
        the smallest possible distance.
        """
        cached = self._range_offsets.get(range_hex)
        if cached is not None:
            return cached
        offsets: list[tuple[int, tuple[int, int]]] = []
        for dq in range(-range_hex, range_hex + 1):
            for dr in range(-range_hex, range_hex + 1):
                if abs(dq + dr) > range_hex:
                    continue
                d = (abs(dq) + abs(dr) + abs(dq + dr)) // 2
                if d > range_hex:
                    continue
                offsets.append((d, (dq, dr)))
        offsets.sort(key=lambda x: x[0])
        flat = [off for _, off in offsets]
        self._range_offsets[range_hex] = flat
        return flat

    # ── Spawning helpers ─────────────────────────────────────────

    def _spawn_enemy_near(self, world: "World", type_name: str,
                          near: HexCoord) -> None:
        data = params.ENEMY_TYPE_DATA.get(type_name)
        if data is None:
            return
        from compprog_pygame.games.hex_colony.settings import Difficulty
        is_desolation = (
            getattr(world.settings, "difficulty", None)
            == Difficulty.DESOLATION
        )
        hp_mult = params.DESOLATION_ENEMY_HP_MULT if is_desolation else 1.0
        dmg_mult = params.DESOLATION_ENEMY_DAMAGE_MULT if is_desolation else 1.0
        coord = self._pick_spawn_tile(world, near)
        e = Enemy(
            type_name=type_name,
            coord=coord,
            health=float(data["hp"]) * hp_mult,
            max_health=float(data["hp"]) * hp_mult,
            damage=float(data["damage"]) * dmg_mult,
            bounty=int(data.get("bounty", 0)),
        )
        e.attack_timer = float(data["attack_cd"])
        e.move_timer = float(data["move_period"])
        size = world.settings.hex_size
        wx, wy = hex_to_pixel(coord, size)
        e.px, e.py = wx, wy
        e.next_target_px, e.next_target_py = wx, wy
        self.enemies.append(e)

    def _pick_spawn_tile(self, world: "World", near: HexCoord) -> HexCoord:
        """Pick a walkable hex within ENEMY_SPAWN_RADIUS of ``near``."""
        rad = params.ENEMY_SPAWN_RADIUS
        if rad <= 0:
            return near
        candidates: list[HexCoord] = [near]
        for dq in range(-rad, rad + 1):
            for dr in range(-rad, rad + 1):
                if abs(dq + dr) > rad:
                    continue
                c = HexCoord(near.q + dq, near.r + dr)
                if c in world.grid and self._is_walkable(world, c):
                    candidates.append(c)
        return self._rng.choice(candidates)

    def _pick_edge_spawn_point(self, world: "World") -> HexCoord:
        """Pick a random walkable hex near the map edge for a raid."""
        camp = world.player_colony.camp_coord
        # Find the maximum distance from camp present in the grid, then
        # pick a tile in roughly the outer ring.
        far_tiles: list[HexCoord] = []
        max_dist = 0
        for tile in world.grid.tiles():
            d = tile.coord.distance(camp)
            if d > max_dist:
                max_dist = d
        edge_band = max(8, max_dist - 3)
        for tile in world.grid.tiles():
            d = tile.coord.distance(camp)
            if d < edge_band:
                continue
            if not self._is_walkable(world, tile.coord):
                continue
            far_tiles.append(tile.coord)
        if not far_tiles:
            return camp
        return self._rng.choice(far_tiles)

    # ── Enemy update ─────────────────────────────────────────────

    def _tick_enemies(self, world: "World", dt: float, ctx: dict) -> None:
        size = world.settings.hex_size
        retarget_ok = float(params.ENEMY_RETARGET_INTERVAL)
        retarget_fail = float(params.ENEMY_RETARGET_FAIL_INTERVAL)
        type_data = params.ENEMY_TYPE_DATA
        blocker_targets: list[Building] = ctx["blocker_targets"]
        blocker_coords: set[HexCoord] = ctx["blocker_coords"]
        blocker_by_coord: dict[HexCoord, Building] = ctx["blocker_by_coord"]
        wall_coords: set[HexCoord] = ctx["wall_coords"]
        target_coords: set[HexCoord] = ctx["target_coords"]
        target_dist: dict[tuple[int, int], int] = ctx["target_dist"]
        valid_coords: set[HexCoord] = ctx["valid_coords"]
        wall_hp = float(
            params.BUILDING_MAX_HEALTH.get(
                "WALL", params.BUILDING_DEFAULT_MAX_HEALTH,
            )
        )
        # Per-tick budget of expensive retargets (A* + scan).  The rest
        # are deferred to the next tick by leaving their timer at <= 0
        # so they get picked up next frame.
        retarget_budget = int(params.ENEMY_RETARGET_BUDGET_PER_TICK)
        for enemy in self.enemies:
            if enemy.dead:
                continue
            data = type_data.get(enemy.type_name)
            if data is None:
                enemy.dead = True
                continue
            period = float(data["move_period"])
            # Smooth visual interpolation toward the next-hex target.
            if enemy.target_coord is not None and period > 0.0:
                t = 1.0 - max(0.0, enemy.move_timer / period)
                cx, cy = hex_to_pixel(enemy.coord, size)
                enemy.px = cx + (enemy.next_target_px - cx) * t
                enemy.py = cy + (enemy.next_target_py - cy) * t
            elif enemy.target_coord is None:
                # No movement target — sit on hex centre.
                enemy.px, enemy.py = hex_to_pixel(enemy.coord, size)

            # Re-target on a timer.  When the previous attempt failed
            # (no path), the timer is set to the longer fail interval
            # so we don't spend every frame doing fruitless A*.
            enemy.retarget_timer -= dt
            if enemy.retarget_timer <= 0.0 and retarget_budget > 0:
                retarget_budget -= 1
                # Per-enemy cost (in hex-step equivalents) of breaking
                # through one wall hex.  ``time_to_break = wall_hp /
                # dps``; converted to "how many ordinary movement
                # steps would take the same amount of real time".
                # Min 2 so the planner never prefers a wall over a
                # detour of equal length.
                attack_cd = float(data["attack_cd"])
                damage = float(data["damage"]) or 1.0
                dps = damage / max(attack_cd, 0.05)
                time_to_break = wall_hp / max(dps, 0.01)
                wall_step_cost = max(
                    2, int(math.ceil(time_to_break / max(period, 0.05)))
                )
                self._update_enemy_target(
                    world, enemy, blocker_targets,
                    valid_coords, blocker_coords, wall_coords,
                    target_coords, blocker_by_coord, target_dist,
                    wall_step_cost, ctx,
                )
                if enemy.path or enemy.target_building_id != 0:
                    enemy.retarget_timer = retarget_ok
                else:
                    enemy.retarget_timer = retarget_fail

            # If adjacent to current target building, attack it.
            if self._try_attack_adjacent(world, enemy, dt, blocker_by_coord):
                continue

            # Otherwise progress along the path.
            # Frost slow: scale dt down while a slow effect is active.
            move_dt = dt
            if enemy.slow_remaining > 0.0 and enemy.slow_factor > 0.0:
                enemy.slow_remaining -= dt
                if enemy.slow_remaining <= 0.0:
                    enemy.slow_remaining = 0.0
                    enemy.slow_factor = 0.0
                else:
                    move_dt = dt * max(0.0, 1.0 - enemy.slow_factor)
            enemy.move_timer -= move_dt
            if enemy.move_timer <= 0.0:
                self._advance_one_hex(world, enemy)
                enemy.move_timer = period

    def _update_enemy_target(self, world: "World", enemy: Enemy,
                             blocker_targets: list[Building],
                             valid_coords: set[HexCoord],
                             blocker_coords: set[HexCoord],
                             wall_coords: set[HexCoord],
                             target_coords: set[HexCoord],
                             blocker_by_coord: dict[HexCoord, Building],
                             target_dist: dict[tuple[int, int], int],
                             wall_step_cost: int,
                             ctx: dict) -> None:
        """A* from the enemy toward the nearest *reachable* SURVIVOR
        target building, with walls handled lazily.

        Two phases:

        1. **Walls-solid A***  (the common case).  Walls block
           movement; the heuristic is the pre-computed BFS distance
           to a real target.  This is the same fast search the combat
           system has used for a long time, and it succeeds whenever
           there is *any* wall-free path to a target \u2014 the player's
           outer ring of walls is bypassed by going around.

        2. **Walls-passable A***  (fallback).  Only runs if phase 1
           found nothing.  Walls cost ``wall_step_cost`` hex-steps to
           traverse; the heuristic is raw hex distance to any target
           (admissible and tight, so A* converges quickly).  This
           handles the case where the player has fully surrounded a
           target with walls \u2014 the enemy correctly decides to break
           through the *cheapest* wall ring.

        Net effect: enemies route around walls when there is *any*
        detour, and break through them only when the detour is
        impossible \u2014 which matches the player's intuition.
        """
        if not blocker_targets:
            enemy.target_building_id = 0
            enemy.path = []
            enemy.target_coord = None
            return

        priority_idx = params.ENEMY_TARGET_PRIORITY_INDEX
        fallback = len(priority_idx)
        start = enemy.coord

        # Edge case: enemy is already adjacent to (or standing on) a
        # *real* target.  Walls are skipped here because we'd rather
        # ignore them and let the A* below decide whether to break
        # through to something better.
        adj_target: Building | None = None
        adj_key: tuple[int, int] | None = None
        on_b = blocker_by_coord.get(start)
        if on_b is not None and start not in wall_coords:
            adj_target = on_b
            adj_key = (0, priority_idx.get(on_b.type.name, fallback))
        for nb in start.neighbors():
            if nb in wall_coords:
                continue
            b = blocker_by_coord.get(nb)
            if b is None:
                continue
            key = (1, priority_idx.get(b.type.name, fallback))
            if adj_key is None or key < adj_key:
                adj_target, adj_key = b, key
        if adj_target is not None:
            enemy.target_building_id = id(adj_target)
            enemy.path = []
            enemy.target_coord = None
            enemy.next_target_px, enemy.next_target_py = (
                hex_to_pixel(enemy.coord, world.settings.hex_size)
            )
            return

        max_depth = int(params.ENEMY_PATHFIND_MAX_DEPTH)

        BIG = 1_000_000

        # Phase 1: walls solid.  We already have a BFS distance field
        # (``target_dist``) over the same graph A* would search, so
        # *gradient descent* on that field finds an optimal path in
        # O(path_length) hex steps \u2014 typically <50 \u2014 instead
        # of an O(max_depth) A* search.  This is the big-win
        # replacement for the previous ~1500-node-per-retarget phase-1
        # A*, which dominated frames once enough enemies were alive.
        found_target = None
        found_endpoint = None
        prev: dict[HexCoord, HexCoord] = {}
        # Cached neighbour table avoids allocating 6 fresh HexCoords
        # per gradient-descent step.  In hot retarget paths this used
        # to dominate (~47ms / tick) once enough enemies were alive.
        wn = ctx["walkable_neighbors"]
        wnt = ctx["walkable_neighbors_t"]
        target_t_set: set[tuple[int, int]] = ctx["target_t"]
        EMPTY: tuple[HexCoord, ...] = ()
        EMPTY_T: tuple[tuple[int, int], ...] = ()
        wn_get = wn.get
        wnt_get = wnt.get
        td_get = target_dist.get  # tuple-keyed
        start_t = (start.q, start.r)
        if start_t in target_dist:
            cur = start
            cur_t = start_t
            cur_d = target_dist[start_t]
            for _ in range(cur_d + 4):
                # Goal test: any neighbour is a *real* target?
                best_b: Building | None = None
                best_k: tuple[int, int] | None = None
                for nb in wn_get(cur, EMPTY):
                    if nb not in target_coords:
                        continue
                    b = blocker_by_coord.get(nb)
                    if b is None:
                        continue
                    k = (0, priority_idx.get(b.type.name, fallback))
                    if best_k is None or k < best_k:
                        best_b, best_k = b, k
                if best_b is not None:
                    found_target = best_b
                    found_endpoint = cur
                    break
                # Step to the neighbour with the smallest target_dist.
                next_nb: HexCoord | None = None
                next_nb_t: tuple[int, int] | None = None
                next_d = cur_d
                # Iterate HexCoord and tuple neighbours in lockstep
                # \u2014 they are the same graph in two key formats.
                hex_nbs = wn_get(cur, EMPTY)
                tup_nbs = wnt_get(cur_t, EMPTY_T)
                for i, nb_t in enumerate(tup_nbs):
                    if nb_t in target_t_set:
                        continue
                    d = td_get(nb_t)
                    if d is None:
                        continue
                    if d < next_d:
                        next_d = d
                        next_nb = hex_nbs[i]
                        next_nb_t = nb_t
                if next_nb is None or next_nb_t is None:
                    break
                prev[next_nb] = cur
                cur = next_nb
                cur_t = next_nb_t
                cur_d = next_d

        # Phase 2: walls passable, but only if phase 1 turned up
        # nothing.  Heuristic = pre-computed multi-source BFS distance
        # to a real target *with walls treated as cost-1*.  This is
        # admissible (true wall cost is wall_step_cost \u2265 1) and
        # gives us O(1) per-node lookups instead of an O(targets)
        # ``min`` over every target per node \u2014 which used to cost
        # ~30ms per retarget and dominated frames once enemies got
        # walled in.  Built lazily on first phase-2 use per tick so
        # the common case (phase 1 succeeds) pays nothing.
        if found_target is None:
            if not target_coords:
                self._set_wander_step(world, enemy, valid_coords,
                                      blocker_coords)
                return
            # Per-tick budget for phase-2 retargets.  Phase 2 is
            # significantly more expensive than phase 1 (walls add
            # high-cost edges that drag out A* exploration), so we
            # cap how many enemies can run it on the same tick.  The
            # overflow simply waits one retarget interval.
            phase2_used = ctx.get("phase2_used", 0)
            phase2_budget = int(getattr(
                params, "ENEMY_PHASE2_BUDGET_PER_TICK", 4,
            ))
            if phase2_used >= phase2_budget:
                self._set_wander_step(world, enemy, valid_coords,
                                      blocker_coords)
                return
            ctx["phase2_used"] = phase2_used + 1
            target_dist_passable = ctx.get("target_dist_passable")
            if target_dist_passable is None:
                target_dist_passable = self._build_passable_dist(
                    target_coords, valid_coords,
                )
                ctx["target_dist_passable"] = target_dist_passable

            def h_phase2(c: HexCoord) -> int:
                d = target_dist_passable.get(c)
                if d is None:
                    return BIG
                return d - 1 if d > 0 else 0

            found_target, found_endpoint, prev = self._astar(
                start=start,
                valid_coords=valid_coords,
                target_coords=target_coords,
                blocker_by_coord=blocker_by_coord,
                priority_idx=priority_idx,
                fallback=fallback,
                heuristic=h_phase2,
                max_depth=max_depth // 4,
                wall_coords=wall_coords,
                wall_step_cost=wall_step_cost,
            )

        if found_target is None or found_endpoint is None:
            # Nothing in range — wander toward the map centre / camp
            # so the enemy doesn't sit at its spawn forever waiting
            # for a building to come within A* horizon.
            self._set_wander_step(world, enemy, valid_coords,
                                  blocker_coords)
            return

        # Reconstruct path from start → found_endpoint.
        path: list[HexCoord] = [found_endpoint]
        while path[-1] in prev:
            path.append(prev[path[-1]])
        path.reverse()
        if path and path[0] == start:
            path = path[1:]

        enemy.target_building_id = id(found_target)
        enemy.path = path
        if enemy.path:
            enemy.target_coord = enemy.path[0]
            tx, ty = hex_to_pixel(enemy.target_coord, world.settings.hex_size)
            enemy.next_target_px, enemy.next_target_py = tx, ty
        else:
            enemy.target_coord = None
            enemy.next_target_px, enemy.next_target_py = (
                hex_to_pixel(enemy.coord, world.settings.hex_size)
            )

    def _build_passable_dist(
        self,
        target_coords: set[HexCoord],
        valid_coords: set[HexCoord],
    ) -> dict[HexCoord, int]:
        """Multi-source BFS distance to nearest real target with walls
        treated as cost-1 (passable).  Used as the phase-2 A*
        heuristic.  ``target_coords`` are the source set; the BFS
        spreads through every walkable hex (including walls).  Cost
        is O(|walkable_coords|).
        """
        dist: dict[HexCoord, int] = {}
        if not target_coords:
            return dist
        queue: deque[HexCoord] = deque()
        for tc in target_coords:
            dist[tc] = 0
            queue.append(tc)
        while queue:
            cur = queue.popleft()
            d = dist[cur] + 1
            for nb in cur.neighbors():
                if nb in dist:
                    continue
                if nb not in valid_coords:
                    continue
                if nb in target_coords:
                    continue  # other targets are solid in the heuristic
                dist[nb] = d
                queue.append(nb)
        return dist

    def _astar(
        self,
        *,
        start: HexCoord,
        valid_coords: set[HexCoord],
        target_coords: set[HexCoord],
        blocker_by_coord: dict[HexCoord, Building],
        priority_idx: dict[str, int],
        fallback: int,
        heuristic,
        max_depth: int,
        wall_coords: set[HexCoord],
        wall_step_cost: int | None,
    ) -> tuple["Building | None", "HexCoord | None", dict[HexCoord, HexCoord]]:
        """Single A* search.  ``wall_step_cost=None`` means walls are
        solid (treated like real targets); a non-None integer means
        walls are passable at that per-step cost.  Returns
        ``(target, endpoint, prev_map)`` where the path can be
        reconstructed by walking ``prev_map`` from ``endpoint``.
        """
        open_heap: list[tuple[int, int, HexCoord]] = []
        tie = 0
        heapq.heappush(open_heap, (heuristic(start), tie, start))
        g_score: dict[HexCoord, int] = {start: 0}
        prev: dict[HexCoord, HexCoord] = {}
        expanded = 0
        while open_heap:
            _, _, cur = heapq.heappop(open_heap)
            cur_g = g_score[cur]
            # Goal test: adjacent to any *real* target (walls don't
            # count \u2014 they aren't worth attacking on their own).
            best_adj: Building | None = None
            best_adj_key: tuple[int, int] | None = None
            for nb in cur.neighbors():
                if nb not in target_coords:
                    continue
                b = blocker_by_coord.get(nb)
                if b is None:
                    continue
                k = (0, priority_idx.get(b.type.name, fallback))
                if best_adj_key is None or k < best_adj_key:
                    best_adj, best_adj_key = b, k
            if best_adj is not None:
                return best_adj, cur, prev
            expanded += 1
            if expanded > max_depth:
                break
            for nb in cur.neighbors():
                if nb not in valid_coords:
                    continue
                if nb in target_coords:
                    # Real targets are solid \u2014 picked up by the goal
                    # test above when we're adjacent.
                    continue
                if nb in wall_coords:
                    if wall_step_cost is None:
                        continue  # phase 1: walls block movement
                    step_cost = wall_step_cost
                else:
                    step_cost = 1
                tentative = cur_g + step_cost
                old = g_score.get(nb)
                if old is not None and tentative >= old:
                    continue
                g_score[nb] = tentative
                prev[nb] = cur
                tie += 1
                heapq.heappush(
                    open_heap,
                    (tentative + heuristic(nb), tie, nb),
                )
        return None, None, prev

    def _set_wander_step(self, world: "World", enemy: Enemy,
                         valid_coords: set[HexCoord],
                         blocker_coords: set[HexCoord]) -> None:
        """Fallback when no SURVIVOR blocker is reachable: step one
        hex toward the map centre (camp coord, falling back to (0,0)
        if the camp is gone).  Called every retarget tick so the
        enemy keeps moving inwards until it finds something to fight.
        """
        enemy.target_building_id = 0
        # Pick fallback goal: the camp if it still exists, else origin.
        fallback = HexCoord(0, 0)
        try:
            fallback = world.player_colony.camp_coord
        except Exception:
            pass
        cur = enemy.coord
        cur_dist = cur.distance(fallback)
        if cur_dist == 0:
            enemy.path = []
            enemy.target_coord = None
            return
        # Pick the walkable neighbour minimising distance to fallback.
        best: HexCoord | None = None
        best_d = cur_dist
        for nb in cur.neighbors():
            if nb not in valid_coords:
                continue
            if nb in blocker_coords:
                continue
            d = nb.distance(fallback)
            if d < best_d:
                best_d = d
                best = nb
        if best is None:
            # Boxed in by water/mountain/blockers — accept any walkable
            # neighbour just so we make some movement.
            for nb in cur.neighbors():
                if nb in valid_coords and nb not in blocker_coords:
                    best = nb
                    break
        if best is None:
            enemy.path = []
            enemy.target_coord = None
            return
        enemy.path = [best]
        enemy.target_coord = best
        tx, ty = hex_to_pixel(best, world.settings.hex_size)
        enemy.next_target_px, enemy.next_target_py = tx, ty

    def _advance_one_hex(self, world: "World", enemy: Enemy) -> None:
        if not enemy.path:
            enemy.target_coord = None
            return
        next_hex = enemy.path[0]
        # Re-validate walkability — a building may have been placed.
        if not self._is_walkable(world, next_hex):
            enemy.path = []
            enemy.target_coord = None
            enemy.retarget_timer = 0.0
            return
        enemy.coord = next_hex
        enemy.path.pop(0)
        # Step on a TRAP if one is here.
        tile = world.grid.get(next_hex)
        if tile is not None and tile.building is not None and \
                tile.building.type == BuildingType.TRAP and \
                tile.building.faction == "SURVIVOR":
            self._detonate_trap(world, tile.building, enemy)
        # Update interpolation endpoint.
        if enemy.path:
            enemy.target_coord = enemy.path[0]
            tx, ty = hex_to_pixel(enemy.target_coord, world.settings.hex_size)
            enemy.next_target_px, enemy.next_target_py = tx, ty
        else:
            enemy.target_coord = None
            enemy.next_target_px, enemy.next_target_py = (
                hex_to_pixel(enemy.coord, world.settings.hex_size)
            )

    def _try_attack_adjacent(self, world: "World", enemy: Enemy,
                             dt: float,
                             blocker_by_coord: dict[HexCoord, Building],
                             ) -> bool:
        """If a player building / colonist is on or adjacent to the
        enemy, attack it.  Returns True if an attack occurred this
        frame (so the caller skips the move step).

        Preference order: a real target (camp, habitat, factory,
        turret \u2026) on or adjacent to the enemy is always chosen
        over a wall.  Walls are only attacked when there is nothing
        else to hit \u2014 which means the A*-planned path runs
        through that wall and there are no nearby targets to pursue
        opportunistically.
        """
        wall_set = params.ENEMY_PATHABLE_WALL_TYPES
        target_b: Building | None = None
        wall_b: Building | None = None
        on_b = blocker_by_coord.get(enemy.coord)
        if on_b is not None:
            if on_b.type.name in wall_set:
                wall_b = on_b
            else:
                target_b = on_b
        if target_b is None:
            for c in enemy.coord.neighbors():
                b = blocker_by_coord.get(c)
                if b is None:
                    continue
                if b.type.name in wall_set:
                    if wall_b is None:
                        wall_b = b
                    continue
                target_b = b
                break
        if target_b is None:
            # Prefer the wall on the planned path (if any) so the
            # enemy makes progress toward its real target instead of
            # randomly chewing on a side wall.
            if enemy.path:
                next_coord = enemy.path[0]
                planned = blocker_by_coord.get(next_coord)
                if planned is not None and planned.type.name in wall_set:
                    target_b = planned
            if target_b is None:
                target_b = wall_b
        if target_b is None:
            return False

        enemy.attack_timer -= dt
        if enemy.attack_timer <= 0.0:
            data = params.ENEMY_TYPE_DATA[enemy.type_name]
            enemy.attack_timer = float(data["attack_cd"])
            self._damage_building(world, target_b, enemy.damage)
            # Also chance-damage a colonist on the same tile.
            self._maybe_damage_colonist(world, target_b.coord, enemy.damage * 0.5)
        return True

    def _damage_building(self, world: "World", b: Building,
                         amount: float) -> None:
        b.health -= amount
        if b.health <= 0.0:
            self._destroy_building(world, b)

    def _destroy_building(self, world: "World", b: Building) -> None:
        # ``world.demolish`` clears every tile the building occupied
        # (anchor + footprint) and removes it from the manager, which
        # matters for multi-tile buildings like the Research Center.
        try:
            world.demolish(b)
        except Exception:
            pass
        world.mark_housing_dirty()
        # Emergency safety net: if the player just lost their last
        # basic producer and has none of its resource on hand they
        # would have no way to bootstrap back.  Grant a free copy
        # in their build inventory so they can restart production.
        self._maybe_grant_emergency_refund(world, b)
        # Notify the player.
        notif = getattr(world, "notifications", None)
        if notif is not None:
            from compprog_pygame.games.hex_colony.strings import (
                NOTIF_BUILDING_DESTROYED, building_label,
            )
            notif.push(
                NOTIF_BUILDING_DESTROYED.format(name=building_label(b.type.name)),
                (255, 110, 90),
            )

    # Producer-type → resource(s) that being out of would soft-lock
    # the player.  WOOD/STONE have unique producers; FIBER comes only
    # from gatherers (food has farms, so we don't gate on it).
    _EMERGENCY_RESOURCES: dict[BuildingType, tuple[str, ...]] = {
        BuildingType.WOODCUTTER: ("WOOD",),
        BuildingType.QUARRY:     ("STONE",),
        BuildingType.GATHERER:   ("FIBER",),
    }

    def _maybe_grant_emergency_refund(
        self, world: "World", destroyed: Building,
    ) -> None:
        if destroyed.faction != "SURVIVOR":
            return
        # Desolation explicitly disables the safety net — the player is
        # meant to be able to soft-lock themselves.
        from compprog_pygame.games.hex_colony.settings import Difficulty
        if (getattr(world.settings, "difficulty", None)
                == Difficulty.DESOLATION):
            return
        btype = destroyed.type
        res_names = self._EMERGENCY_RESOURCES.get(btype)
        if res_names is None:
            return
        # Any other player-owned producer of the same type left?
        for other in world.buildings.buildings:
            if (other.type is btype
                    and other.faction == "SURVIVOR"
                    and other is not destroyed):
                return
        # Player has any of the resource(s) it produces?
        from compprog_pygame.games.hex_colony.resources import Resource
        inv = world.player_colony.inventory
        for name in res_names:
            res = getattr(Resource, name, None)
            if res is not None and inv[res] > 0:
                return
        # Soft-lock incoming — grant one free building.
        world.player_colony.building_inventory.add(btype, 1)
        notif = getattr(world, "notifications", None)
        if notif is not None:
            from compprog_pygame.games.hex_colony.strings import (
                NOTIF_EMERGENCY_REFUND, building_label,
            )
            notif.push(
                NOTIF_EMERGENCY_REFUND.format(name=building_label(btype.name)),
                (130, 220, 130),
            )

    def _detonate_trap(self, world: "World", trap: Building,
                       trigger: Enemy) -> None:
        dmg = float(params.TRAP_DAMAGE)
        # Hit the trigger and any adjacent enemies for half damage.
        for e in self.enemies:
            if e.dead:
                continue
            if e is trigger:
                e.health -= dmg
            elif e.coord.distance(trap.coord) <= 1:
                e.health -= dmg * 0.5
            if e.health <= 0:
                e.dead = True
                self._on_enemy_killed(world, e)
        # Trap is consumed.
        trap.health = 0.0
        self._destroy_building(world, trap)

    def _on_enemy_killed(self, world: "World", e: Enemy) -> None:
        self.enemies_killed += 1
        if e.bounty > 0:
            from compprog_pygame.games.hex_colony.resources import Resource
            world.player_colony.inventory.add(Resource.WOOD, e.bounty)

    def _maybe_damage_colonist(self, world: "World", coord: HexCoord,
                               amount: float) -> None:
        """If a colonist is standing on or adjacent to ``coord``,
        deal them ``amount`` damage.  At zero HP they die and the
        colony loses one population unit."""
        for person in world.population.people:
            if person.dead:
                continue
            if person.hex_pos.distance(coord) > 1:
                continue
            person.health -= amount
            if person.health <= 0.0:
                person.health = 0.0
                person.dead = True
                # Detach from home so the housing pass drops them.
                home = getattr(person, "home", None)
                if home is not None:
                    home.residents = max(0, home.residents - 1)
                    person.home = None
                world.mark_population_changed()
                notif = getattr(world, "notifications", None)
                if notif is not None:
                    from compprog_pygame.games.hex_colony.strings import (
                        NOTIF_COLONIST_KILLED,
                    )
                    notif.push(NOTIF_COLONIST_KILLED, (255, 90, 90))
            return  # at most one casualty per swing

    # ── Defender weapons (camp laser + turrets) ──────────────────

    def _tick_defenders(self, world: "World", dt: float, ctx: dict) -> None:
        if not self.enemies:
            return
        size = world.settings.hex_size
        enemy_index: dict[HexCoord, list[Enemy]] = ctx["enemy_index"]
        # Pre-filtered list: only buildings with weapons.  Avoids
        # walking the whole O(buildings) list every frame.
        for b, kind in ctx["weapon_buildings"]:
            if kind == "TURRET":
                # Wall-mounted turrets get a small range bonus from
                # their elevated platform.
                turret_range = params.TURRET_RANGE_HEXES
                if getattr(b, "wall_mounted", False):
                    turret_range += params.TURRET_WALL_RANGE_BONUS
                self._fire_weapon(
                    world, b, size, dt, enemy_index,
                    range_hex=turret_range,
                    damage=params.TURRET_DAMAGE,
                    reload=params.TURRET_RELOAD_SECONDS,
                    speed=params.TURRET_PROJECTILE_SPEED,
                    color=(255, 220, 120),
                )
            elif kind == "CANNON":
                self._fire_weapon(
                    world, b, size, dt, enemy_index,
                    range_hex=params.CANNON_TURRET_RANGE_HEXES,
                    damage=params.CANNON_TURRET_DAMAGE,
                    reload=params.CANNON_TURRET_RELOAD_SECONDS,
                    speed=params.CANNON_TURRET_PROJECTILE_SPEED,
                    color=(255, 140, 80),
                )
            elif kind == "MORTAR":
                self._fire_weapon(
                    world, b, size, dt, enemy_index,
                    range_hex=params.MORTAR_TURRET_RANGE_HEXES,
                    damage=params.MORTAR_TURRET_DAMAGE,
                    reload=params.MORTAR_TURRET_RELOAD_SECONDS,
                    speed=params.MORTAR_TURRET_PROJECTILE_SPEED,
                    color=(255, 220, 120),
                    splash_radius_px=float(
                        params.MORTAR_TURRET_SPLASH_RADIUS_HEXES * size
                    ),
                    splash_falloff=params.MORTAR_TURRET_SPLASH_FALLOFF,
                )
            elif kind == "FROST":
                self._fire_weapon(
                    world, b, size, dt, enemy_index,
                    range_hex=params.FROST_TURRET_RANGE_HEXES,
                    damage=params.FROST_TURRET_DAMAGE,
                    reload=params.FROST_TURRET_RELOAD_SECONDS,
                    speed=params.FROST_TURRET_PROJECTILE_SPEED,
                    color=(140, 220, 255),
                    slow_factor=params.FROST_TURRET_SLOW_FACTOR,
                    slow_duration=params.FROST_TURRET_SLOW_DURATION,
                )
            else:  # "CAMP"
                self._fire_weapon(
                    world, b, size, dt, enemy_index,
                    range_hex=params.CAMP_LASER_RANGE_HEXES,
                    damage=params.CAMP_LASER_DAMAGE,
                    reload=params.CAMP_LASER_RELOAD_SECONDS,
                    speed=600.0,
                    color=(120, 255, 220),
                )

    def _fire_weapon(self, world: "World", b: Building, size: int,
                     dt: float,
                     enemy_index: dict[HexCoord, list[Enemy]],
                     *, range_hex: int, damage: float,
                     reload: float, speed: float,
                     color: tuple[int, int, int],
                     splash_radius_px: float = 0.0,
                     splash_falloff: float = 0.5,
                     slow_factor: float = 0.0,
                     slow_duration: float = 0.0) -> None:
        b.weapon_cooldown = max(0.0, b.weapon_cooldown - dt)
        if b.weapon_cooldown > 0.0:
            return
        target = self._closest_enemy_in_range(b.coord, range_hex,
                                              enemy_index)
        if target is None:
            return
        b.weapon_cooldown = float(reload)
        sx, sy = hex_to_pixel(b.coord, size)
        ex, ey = target.px, target.py
        dist = math.hypot(ex - sx, ey - sy)
        proj = Projectile(
            src_px=sx, src_py=sy, dst_px=ex, dst_py=ey,
            distance=dist, speed=float(speed), damage=float(damage),
            target_id=id(target), color=color,
            splash_radius_px=float(splash_radius_px),
            splash_falloff=float(splash_falloff),
            slow_factor=float(slow_factor),
            slow_duration=float(slow_duration),
        )
        self.projectiles.append(proj)

    def _closest_enemy_in_range(self, origin: HexCoord,
                                range_hex: int,
                                enemy_index: dict[HexCoord, list[Enemy]],
                                ) -> Enemy | None:
        """Find the closest live enemy within ``range_hex`` of ``origin``.

        Uses the per-tick spatial index to iterate hexes in expanding
        rings instead of scanning every enemy in the world.  With a
        4-hex range that's at most 61 dict lookups per turret.
        """
        if not enemy_index:
            return None
        offsets = self._range_offsets_for(range_hex)
        oq, orr = origin.q, origin.r
        for dq, dr in offsets:
            bucket = enemy_index.get(HexCoord(oq + dq, orr + dr))
            if bucket is None:
                continue
            for e in bucket:
                if not e.dead:
                    return e
        return None

    # ── Projectiles ──────────────────────────────────────────────

    def _tick_projectiles(self, world: "World", dt: float, ctx: dict) -> None:
        enemy_by_id: dict[int, Enemy] = ctx["enemy_by_id"]
        for p in self.projectiles:
            p.travelled += p.speed * dt
            if p.travelled < p.distance:
                continue
            # Resolve hit — O(1) lookup via the per-tick id index.
            e = enemy_by_id.get(p.target_id)
            primary_alive = e is not None and not e.dead
            if primary_alive:
                e.health -= p.damage
                if p.slow_factor > 0.0 and p.slow_duration > 0.0:
                    # Apply / refresh the slow effect.  Stronger
                    # slow overrides a weaker one; same strength
                    # refreshes the timer.
                    if p.slow_factor >= e.slow_factor:
                        e.slow_factor = p.slow_factor
                        e.slow_remaining = max(e.slow_remaining, p.slow_duration)
                if e.health <= 0.0:
                    e.dead = True
                    self._on_enemy_killed(world, e)
            # Splash damage: hit every other live enemy whose pixel
            # position is within ``splash_radius_px`` of the impact
            # point.  Damage is reduced by ``splash_falloff``.
            if p.splash_radius_px > 0.0:
                rsq = p.splash_radius_px * p.splash_radius_px
                splash_dmg = p.damage * p.splash_falloff
                if splash_dmg > 0.0:
                    for other in self.enemies:
                        if other is e or other.dead:
                            continue
                        dxp = other.px - p.dst_px
                        dyp = other.py - p.dst_py
                        if dxp * dxp + dyp * dyp <= rsq:
                            other.health -= splash_dmg
                            if p.slow_factor > 0.0 and p.slow_duration > 0.0:
                                if p.slow_factor >= other.slow_factor:
                                    other.slow_factor = p.slow_factor
                                    other.slow_remaining = max(
                                        other.slow_remaining, p.slow_duration,
                                    )
                            if other.health <= 0.0:
                                other.dead = True
                                self._on_enemy_killed(world, other)

    # ── Path-finding helpers ─────────────────────────────────────

    def _is_walkable(self, world: "World", coord: HexCoord,
                     ignore_building_at: HexCoord | None = None) -> bool:
        tile = world.grid.get(coord)
        if tile is None:
            return False
        if tile.terrain.name in params.ENEMY_TERRAIN_BLOCKERS:
            return False
        if tile.building is not None and tile.building.coord != ignore_building_at:
            if tile.building.type.name in params.ENEMY_BUILDING_BLOCKERS:
                return False
        return True

    def _bfs_path(self, world: "World", start: HexCoord, goal: HexCoord,
                  *, max_depth: int,
                  attack_dest: bool,
                  valid_coords: set[HexCoord] | None = None,
                  blocker_coords: set[HexCoord] | None = None,
                  ) -> list[HexCoord]:
        """A* from ``start`` to a tile adjacent to ``goal`` (when
        ``attack_dest`` is True) or ``goal`` itself otherwise.

        ``max_depth`` is interpreted as the maximum number of nodes
        expanded \u2014 with a hex-distance heuristic this is plenty for
        the full map and dramatically cheaper than a flood BFS.

        ``valid_coords`` and ``blocker_coords`` are pre-computed sets
        (built once per tick by :meth:`_tick_enemies`) used to skip
        per-node attribute lookups.  When omitted we fall back to the
        slow per-tile checks via :meth:`_is_walkable`.

        Returns the path including the start tile, or [] if no route
        was found within the budget.
        """
        if start == goal:
            return [start]
        ignore = goal if attack_dest else None

        # Build a fast `is_walkable` closure.  When the per-tick
        # sets are available it reduces to two set lookups per call;
        # otherwise we fall back to the original method.
        if valid_coords is not None and blocker_coords is not None:
            def is_walkable(c: HexCoord) -> bool:
                if c not in valid_coords:
                    return False
                if c in blocker_coords and c != ignore:
                    return False
                return True
        else:
            def is_walkable(c: HexCoord) -> bool:
                return self._is_walkable(world, c,
                                         ignore_building_at=ignore)

        def heuristic(c: HexCoord) -> int:
            # We want to *reach* a tile adjacent to the goal, so the
            # admissible heuristic is max(0, dist - 1).
            d = c.distance(goal)
            return d - 1 if attack_dest else d

        # Open set: (f_score, tie_breaker, coord)
        open_heap: list[tuple[int, int, HexCoord]] = []
        tie = 0
        heapq.heappush(open_heap, (heuristic(start), tie, start))
        g_score: dict[HexCoord, int] = {start: 0}
        prev: dict[HexCoord, HexCoord] = {}
        found: HexCoord | None = None
        expanded = 0
        while open_heap:
            _, _, cur = heapq.heappop(open_heap)
            if attack_dest:
                if cur.distance(goal) <= 1 and cur != goal:
                    found = cur
                    break
            else:
                if cur == goal:
                    found = cur
                    break
            expanded += 1
            if expanded > max_depth:
                break
            cur_g = g_score[cur]
            for nb in cur.neighbors():
                if not is_walkable(nb):
                    continue
                tentative = cur_g + 1
                old = g_score.get(nb)
                if old is not None and tentative >= old:
                    continue
                g_score[nb] = tentative
                prev[nb] = cur
                tie += 1
                heapq.heappush(
                    open_heap,
                    (tentative + heuristic(nb), tie, nb),
                )
        if found is None:
            return []
        # Reconstruct.
        path: list[HexCoord] = [found]
        while path[-1] in prev:
            path.append(prev[path[-1]])
        path.reverse()
        return path

    def _find_nearest_player_target(self, origin: HexCoord,
                                    blockers: list[Building]
                                    ) -> Building | None:
        """Pick the player-faction blocking building whose hex is
        closest to ``origin`` (Chebyshev / hex distance), breaking
        ties by ``ENEMY_TARGET_PRIORITY`` order.

        ``blockers`` is the pre-filtered list of SURVIVOR buildings
        whose type is in ``ENEMY_BUILDING_BLOCKERS`` (built once per
        tick by :meth:`_tick_enemies`).
        """
        priority_idx = params.ENEMY_TARGET_PRIORITY_INDEX
        fallback = len(priority_idx)
        best: Building | None = None
        best_key: tuple[int, int] | None = None
        for b in blockers:
            pidx = priority_idx.get(b.type.name, fallback)
            d = origin.distance(b.coord)
            key = (d, pidx)
            if best_key is None or key < best_key:
                best, best_key = b, key
        return best
