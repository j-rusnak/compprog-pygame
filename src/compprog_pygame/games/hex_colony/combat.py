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
        for tc in tower_coords:
            for type_name, count in comp:
                for _ in range(count):
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
        for type_name, base_count in params.POST_AWAKENING_WAVE_COMPOSITION:
            count = max(0, int(round(base_count * scale)))
            for _ in range(count):
                self._spawn_enemy_near(world, type_name, edge_coord)
        for _ in range(pop_bonus):
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

        if self.enemies:
            self._tick_enemies(world, dt)
        if self.projectiles:
            self._tick_projectiles(world, dt)
        # Defensive weapons (camp laser + turrets).
        self._tick_defenders(world, dt)

        # Sweep dead entities.
        if self.enemies:
            self.enemies[:] = [e for e in self.enemies if not e.dead]
        if self.projectiles:
            self.projectiles[:] = [
                p for p in self.projectiles if p.travelled < p.distance
            ]

    # ── Spawning helpers ─────────────────────────────────────────

    def _spawn_enemy_near(self, world: "World", type_name: str,
                          near: HexCoord) -> None:
        data = params.ENEMY_TYPE_DATA.get(type_name)
        if data is None:
            return
        coord = self._pick_spawn_tile(world, near)
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

    def _tick_enemies(self, world: "World", dt: float) -> None:
        size = world.settings.hex_size
        retarget_ok = float(params.ENEMY_RETARGET_INTERVAL)
        retarget_fail = float(params.ENEMY_RETARGET_FAIL_INTERVAL)
        type_data = params.ENEMY_TYPE_DATA
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
            if enemy.retarget_timer <= 0.0:
                self._update_enemy_target(world, enemy)
                if enemy.path or enemy.target_building_id != 0:
                    enemy.retarget_timer = retarget_ok
                else:
                    enemy.retarget_timer = retarget_fail

            # If adjacent to current target building, attack it.
            if self._try_attack_adjacent(world, enemy, dt):
                continue

            # Otherwise progress along the path.
            enemy.move_timer -= dt
            if enemy.move_timer <= 0.0:
                self._advance_one_hex(world, enemy)
                enemy.move_timer = period

    def _update_enemy_target(self, world: "World", enemy: Enemy) -> None:
        """BFS to nearest player-faction blocking building; cache the path."""
        target = self._find_nearest_player_target(world, enemy.coord)
        if target is None:
            enemy.target_building_id = 0
            enemy.path = []
            enemy.target_coord = None
            return
        enemy.target_building_id = id(target)
        path = self._bfs_path(world, enemy.coord, target.coord,
                              max_depth=params.ENEMY_PATHFIND_MAX_DEPTH,
                              attack_dest=True)
        # Drop the first hex (== current coord).
        if path and path[0] == enemy.coord:
            path = path[1:]
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
                             dt: float) -> bool:
        """If a player building / colonist is on or adjacent to the
        enemy, attack it.  Returns True if an attack occurred this
        frame (so the caller skips the move step).
        """
        # Look for adjacent player buildings first.
        target_b: Building | None = None
        for c in (enemy.coord, *enemy.coord.neighbors()):
            tile = world.grid.get(c)
            if tile is None or tile.building is None:
                continue
            b = tile.building
            if b.faction != "SURVIVOR":
                continue
            if b.type.name not in params.ENEMY_BUILDING_BLOCKERS:
                continue
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
        tile = world.grid.get(b.coord)
        if tile is not None and tile.building is b:
            tile.building = None
        try:
            world.buildings.remove(b)
        except Exception:
            pass
        world.mark_housing_dirty()
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

    def _tick_defenders(self, world: "World", dt: float) -> None:
        if not self.enemies:
            return
        size = world.settings.hex_size
        # Defender weapons never modify the buildings list (they only
        # spawn projectiles), so we can iterate it directly.
        for b in world.buildings.buildings:
            if b.faction != "SURVIVOR":
                continue
            if b.type == BuildingType.TURRET:
                self._fire_weapon(
                    world, b, size, dt,
                    range_hex=params.TURRET_RANGE_HEXES,
                    damage=params.TURRET_DAMAGE,
                    reload=params.TURRET_RELOAD_SECONDS,
                    speed=params.TURRET_PROJECTILE_SPEED,
                    color=(255, 220, 120),
                )
            elif b.type == BuildingType.CAMP:
                # The crashed ship is always armed: it auto-targets
                # the closest enemy within its short range.
                self._fire_weapon(
                    world, b, size, dt,
                    range_hex=params.CAMP_LASER_RANGE_HEXES,
                    damage=params.CAMP_LASER_DAMAGE,
                    reload=params.CAMP_LASER_RELOAD_SECONDS,
                    speed=600.0,
                    color=(120, 255, 220),
                )

    def _fire_weapon(self, world: "World", b: Building, size: int,
                     dt: float, *, range_hex: int, damage: float,
                     reload: float, speed: float,
                     color: tuple[int, int, int]) -> None:
        b.weapon_cooldown = max(0.0, b.weapon_cooldown - dt)
        if b.weapon_cooldown > 0.0:
            return
        target = self._closest_enemy_in_range(b.coord, range_hex)
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
                                range_hex: int) -> Enemy | None:
        best: Enemy | None = None
        best_d: int = range_hex + 1
        for e in self.enemies:
            if e.dead:
                continue
            d = origin.distance(e.coord)
            if d <= range_hex and d < best_d:
                best, best_d = e, d
        return best

    # ── Projectiles ──────────────────────────────────────────────

    def _tick_projectiles(self, world: "World", dt: float) -> None:
        for p in self.projectiles:
            p.travelled += p.speed * dt
            if p.travelled < p.distance:
                continue
            # Resolve hit.
            for e in self.enemies:
                if e.dead:
                    continue
                if id(e) != p.target_id:
                    continue
                e.health -= p.damage
                if e.health <= 0.0:
                    e.dead = True
                    self._on_enemy_killed(world, e)
                break

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
                  attack_dest: bool) -> list[HexCoord]:
        """A* from ``start`` to a tile adjacent to ``goal`` (when
        ``attack_dest`` is True) or ``goal`` itself otherwise.

        ``max_depth`` is interpreted as the maximum number of nodes
        expanded \u2014 with a hex-distance heuristic this is plenty for
        the full map and dramatically cheaper than a flood BFS.

        Returns the path including the start tile, or [] if no route
        was found within the budget.
        """
        if start == goal:
            return [start]
        ignore = goal if attack_dest else None

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
                if not self._is_walkable(world, nb,
                                         ignore_building_at=ignore):
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

    def _find_nearest_player_target(self, world: "World",
                                    origin: HexCoord) -> Building | None:
        """Pick the player-faction blocking building whose hex is
        closest to ``origin`` (Chebyshev / hex distance), breaking
        ties by ``ENEMY_TARGET_PRIORITY`` order.
        """
        priority = params.ENEMY_TARGET_PRIORITY
        best: Building | None = None
        best_key: tuple[int, int] | None = None
        for b in world.buildings.buildings:
            if b.faction != "SURVIVOR":
                continue
            tname = b.type.name
            if tname not in params.ENEMY_BUILDING_BLOCKERS:
                continue
            try:
                pidx = priority.index(tname)
            except ValueError:
                pidx = len(priority)
            d = origin.distance(b.coord)
            key = (d, pidx)
            if best_key is None or key < best_key:
                best, best_key = b, key
        return best
