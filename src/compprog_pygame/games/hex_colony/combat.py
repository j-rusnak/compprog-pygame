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
        # Pre-built table of axial offsets per ring distance, keyed
        # by max distance.  Used by ``_closest_enemy_in_range`` to
        # iterate only the hexes inside a turret's range.
        self._range_offsets: dict[int, list[tuple[int, int]]] = {}

    def invalidate_terrain_cache(self) -> None:
        """Drop the static walkable-terrain cache (call after world regen)."""
        self._terrain_walkable_cache = None

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
        # 1) Static terrain walkability — cache forever.
        if self._terrain_walkable_cache is None:
            terrain_blockers = params.ENEMY_TERRAIN_BLOCKERS
            self._terrain_walkable_cache = {
                t.coord for t in world.grid.tiles()
                if t.terrain.name not in terrain_blockers
            }
        valid_coords = self._terrain_walkable_cache

        # 2) Blockers + weapon-bearing buildings in a single pass.
        blocker_set = params.ENEMY_BUILDING_BLOCKERS
        blocker_targets: list[Building] = []
        blocker_coords: set[HexCoord] = set()
        blocker_by_coord: dict[HexCoord, Building] = {}
        weapon_buildings: list[tuple[Building, str]] = []
        TURRET = BuildingType.TURRET
        CAMP = BuildingType.CAMP
        for b in world.buildings.buildings:
            if b.faction != "SURVIVOR":
                continue
            btype = b.type
            if btype.name in blocker_set:
                blocker_targets.append(b)
                blocker_coords.add(b.coord)
                blocker_by_coord[b.coord] = b
            if btype is TURRET:
                weapon_buildings.append((b, "TURRET"))
            elif btype is CAMP:
                weapon_buildings.append((b, "CAMP"))

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
            "blocker_coords": blocker_coords,
            "blocker_by_coord": blocker_by_coord,
            "blocker_targets": blocker_targets,
            "weapon_buildings": weapon_buildings,
            "enemy_index": enemy_index,
            "enemy_by_id": enemy_by_id,
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
        valid_coords: set[HexCoord] = ctx["valid_coords"]
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
                self._update_enemy_target(
                    world, enemy, blocker_targets,
                    valid_coords, blocker_coords,
                )
                if enemy.path or enemy.target_building_id != 0:
                    enemy.retarget_timer = retarget_ok
                else:
                    enemy.retarget_timer = retarget_fail

            # If adjacent to current target building, attack it.
            if self._try_attack_adjacent(world, enemy, dt, blocker_by_coord):
                continue

            # Otherwise progress along the path.
            enemy.move_timer -= dt
            if enemy.move_timer <= 0.0:
                self._advance_one_hex(world, enemy)
                enemy.move_timer = period

    def _update_enemy_target(self, world: "World", enemy: Enemy,
                             blocker_targets: list[Building],
                             valid_coords: set[HexCoord],
                             blocker_coords: set[HexCoord]) -> None:
        """A* from the enemy toward the nearest *reachable* SURVIVOR
        blocker.

        The heuristic is the minimum hex distance to any blocker, and
        the goal test is "current tile is adjacent to a blocker".  This
        gives us correct behaviour in two important cases:

        * if the closest blocker by raw distance is walled off, A*
          naturally falls through to the next-nearest reachable one
          rather than getting stuck (the old multi-target BFS handled
          this too);
        * because A* is heuristic-guided, it scales to the full ~80-
          radius map.  A pure flood BFS bounded at ~1500 nodes only
          covers ~22 hexes, which is why enemies spawned at edge
          ancient towers used to just sit there — the player's base
          was outside the BFS horizon.
        """
        if not blocker_targets:
            enemy.target_building_id = 0
            enemy.path = []
            enemy.target_coord = None
            return

        blocker_by_coord: dict[HexCoord, Building] = {
            b.coord: b for b in blocker_targets
        }
        priority_idx = params.ENEMY_TARGET_PRIORITY_INDEX
        fallback = len(priority_idx)

        # Edge case: enemy is already on / adjacent to a blocker.
        start = enemy.coord
        adj_target: Building | None = None
        adj_key: tuple[int, int] | None = None
        if start in blocker_by_coord:
            adj_target = blocker_by_coord[start]
            adj_key = (0, priority_idx.get(adj_target.type.name, fallback))
        for nb in start.neighbors():
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

        # Multi-target A*.  Heuristic = min hex distance to any blocker
        # minus one (we only need to reach an adjacent tile).
        blocker_list = list(blocker_by_coord.keys())

        def heuristic(c: HexCoord) -> int:
            best = 1_000_000
            for bc in blocker_list:
                d = c.distance(bc)
                if d < best:
                    best = d
                    if best <= 1:
                        return 0
            return best - 1 if best > 0 else 0

        max_depth = int(params.ENEMY_PATHFIND_MAX_DEPTH)
        open_heap: list[tuple[int, int, HexCoord]] = []
        tie = 0
        heapq.heappush(open_heap, (heuristic(start), tie, start))
        g_score: dict[HexCoord, int] = {start: 0}
        prev: dict[HexCoord, HexCoord] = {}
        found_endpoint: HexCoord | None = None
        found_target: Building | None = None
        expanded = 0
        while open_heap:
            _, _, cur = heapq.heappop(open_heap)
            # Goal test: adjacent to any blocker.
            best_adj: Building | None = None
            best_adj_key: tuple[int, int] | None = None
            for nb in cur.neighbors():
                b = blocker_by_coord.get(nb)
                if b is None:
                    continue
                k = (0, priority_idx.get(b.type.name, fallback))
                if best_adj_key is None or k < best_adj_key:
                    best_adj, best_adj_key = b, k
            if best_adj is not None:
                found_endpoint = cur
                found_target = best_adj
                break
            expanded += 1
            if expanded > max_depth:
                break
            cur_g = g_score[cur]
            for nb in cur.neighbors():
                if nb not in valid_coords:
                    continue
                if nb in blocker_coords:
                    # Other blockers act as walls (they'll be picked
                    # up by the goal test above when we're adjacent).
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

        if found_target is None or found_endpoint is None:
            # Nothing in range — wander toward the map centre / camp
            # so the enemy doesn't sit at its spawn forever waiting
            # for a building to come within A* horizon.  We pick the
            # walkable neighbour that most reduces hex-distance to the
            # fallback target.
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
        """
        # Look for adjacent player buildings via the per-tick blocker
        # dict — avoids 7 grid.get + attribute lookups per enemy.
        target_b: Building | None = blocker_by_coord.get(enemy.coord)
        if target_b is None:
            for c in enemy.coord.neighbors():
                b = blocker_by_coord.get(c)
                if b is not None:
                    target_b = b
                    break
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
                     color: tuple[int, int, int]) -> None:
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
            if e is None or e.dead:
                continue
            e.health -= p.damage
            if e.health <= 0.0:
                e.dead = True
                self._on_enemy_killed(world, e)

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
