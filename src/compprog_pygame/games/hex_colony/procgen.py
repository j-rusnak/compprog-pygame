"""Deterministic seed-based procedural terrain generation for Hex Colony.

Uses layered value noise evaluated at hex-pixel positions to produce
natural-looking terrain features: lakes, rivers, mountain ranges, forests,
clearings, and fibre/stone deposits.  Every output is fully determined by
the alphanumeric seed string.
"""

from __future__ import annotations

import hashlib
import math
import random as _random
from typing import Sequence

from compprog_pygame.games.hex_colony.hex_grid import HexCoord, HexGrid, HexTile, Terrain, hex_to_pixel
from compprog_pygame.games.hex_colony.settings import HexColonySettings


# ── Seed → integer ───────────────────────────────────────────────

def seed_to_int(seed: str) -> int:
    """Convert an arbitrary alphanumeric seed string to a stable integer."""
    return int(hashlib.sha256(seed.encode("utf-8")).hexdigest(), 16)


# ── Deterministic value-noise (no external deps) ────────────────

class _NoiseLayer:
    """Single layer of smoothed lattice noise.  Fully deterministic."""

    def __init__(self, rng: _random.Random, scale: float) -> None:
        self.scale = scale
        # Build a 256-entry permutation table
        self._perm = list(range(256))
        rng.shuffle(self._perm)
        self._perm *= 2  # double for easy wrapping
        # Random gradient-ish values
        self._vals = [rng.uniform(-1.0, 1.0) for _ in range(256)]

    def _hash(self, ix: int, iy: int) -> float:
        return self._vals[self._perm[self._perm[ix & 255] + (iy & 255)] & 255]

    def sample(self, x: float, y: float) -> float:
        sx = x / self.scale
        sy = y / self.scale
        ix, iy = int(math.floor(sx)), int(math.floor(sy))
        fx, fy = sx - ix, sy - iy
        # Smoothstep
        ux = fx * fx * (3 - 2 * fx)
        uy = fy * fy * (3 - 2 * fy)
        v00 = self._hash(ix, iy)
        v10 = self._hash(ix + 1, iy)
        v01 = self._hash(ix, iy + 1)
        v11 = self._hash(ix + 1, iy + 1)
        return _lerp(_lerp(v00, v10, ux), _lerp(v01, v11, ux), uy)


def _lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


class NoiseMap:
    """Multi-octave value noise, seeded deterministically."""

    def __init__(self, rng: _random.Random, octaves: int = 4,
                 base_scale: float = 200.0, persistence: float = 0.5) -> None:
        self._layers: list[tuple[_NoiseLayer, float]] = []
        amp = 1.0
        scale = base_scale
        for _ in range(octaves):
            self._layers.append((_NoiseLayer(rng, scale), amp))
            scale /= 2.0
            amp *= persistence

    def sample(self, x: float, y: float) -> float:
        """Return noise in roughly [-1, 1]."""
        total = 0.0
        max_amp = 0.0
        for layer, amp in self._layers:
            total += layer.sample(x, y) * amp
            max_amp += amp
        return total / max_amp if max_amp else 0.0


# ── Impassable terrain helpers ────────────────────────────────────

IMPASSABLE = frozenset({Terrain.WATER, Terrain.MOUNTAIN})
SAFE_RADIUS = 2  # fixed 2-tile exclusion zone around the camp


def _is_passable(terrain: Terrain) -> bool:
    return terrain not in IMPASSABLE


# ── River carving ────────────────────────────────────────────────

def _find_lake_bodies(grid: HexGrid) -> list[set[HexCoord]]:
    """Find distinct connected components of water tiles (lakes)."""
    visited: set[HexCoord] = set()
    lakes: list[set[HexCoord]] = []
    for coord in grid.coords():
        if coord in visited:
            continue
        tile = grid.get(coord)
        if tile is None or tile.terrain != Terrain.WATER:
            continue
        # BFS to find this lake body
        body: set[HexCoord] = set()
        queue = [coord]
        while queue:
            c = queue.pop()
            if c in visited:
                continue
            t = grid.get(c)
            if t is None or t.terrain != Terrain.WATER:
                continue
            visited.add(c)
            body.add(c)
            for nb in c.neighbors():
                if nb not in visited:
                    queue.append(nb)
        if len(body) >= 3:  # only count meaningful lakes
            lakes.append(body)
    return lakes


def _lake_edge_tiles(grid: HexGrid, lake: set[HexCoord]) -> list[HexCoord]:
    """Return land tiles directly adjacent to a lake body."""
    edges: set[HexCoord] = set()
    for c in lake:
        for nb in c.neighbors():
            if nb not in lake:
                tile = grid.get(nb)
                if tile is not None and tile.terrain != Terrain.WATER:
                    edges.add(nb)
    return list(edges)


def _carve_rivers(
    grid: HexGrid,
    rng: _random.Random,
    settings: HexColonySettings,
    elevation: dict[HexCoord, float],
    lake_affinity: dict[HexCoord, float],
    count: int = 3,
) -> None:
    """Carve long, meandering rivers that connect lakes to distant points.

    Rivers originate from lake edges and wind their way across the map,
    cutting through forests, plains, and even mountains.  They meander
    using noise-guided direction offsets so they never travel in a
    straight line.
    """
    origin = HexCoord(0, 0)
    radius = settings.world_radius
    min_river_len = max(12, radius // 4)

    # Find lake bodies and their edges
    lakes = _find_lake_bodies(grid)

    # Build a set of all lake tile coords for stop detection
    all_lake_tiles: set[HexCoord] = set()
    for lake in lakes:
        all_lake_tiles |= lake

    # Build wander noise for meandering (separate from terrain noise)
    wander_noise = NoiseMap(rng, octaves=2,
                            base_scale=120.0 * max(1.0, radius / 20.0),
                            persistence=0.5)

    carved_river_tiles: set[HexCoord] = set()
    used_lakes: set[int] = set()  # indices of lakes we already started from

    # Decide river origin style distribution:
    #   ~40% lake-origin, ~30% mountain/highland, ~30% map-edge/random
    origin_styles: list[str] = []
    for _ in range(count):
        roll = rng.random()
        if roll < 0.40 and lakes:
            origin_styles.append("lake")
        elif roll < 0.70:
            origin_styles.append("highland")
        else:
            origin_styles.append("edge")

    for river_idx in range(count):
        start: HexCoord | None = None
        source_lake: set[HexCoord] = set()
        lake_i: int = -1
        style = origin_styles[river_idx]

        if style == "lake" and lakes:
            # Pick a lake to start from (prefer larger lakes, avoid reuse)
            available = [(i, lake) for i, lake in enumerate(lakes) if i not in used_lakes]
            if not available:
                available = list(enumerate(lakes))
            available.sort(key=lambda x: -len(x[1]))
            pick_idx = rng.randint(0, min(2, len(available) - 1))
            lake_i, source_lake = available[pick_idx]
            used_lakes.add(lake_i)
            edges = _lake_edge_tiles(grid, source_lake)
            edges = [e for e in edges if e.distance(origin) > SAFE_RADIUS]
            if edges:
                start = rng.choice(edges)

        elif style == "highland":
            # Start from high-elevation terrain (mountain foothills, ridges)
            highland = [
                c for c in grid.coords()
                if elevation.get(c, 0) > 0.12
                and c.distance(origin) > SAFE_RADIUS + 2
                and grid[c].terrain not in {Terrain.WATER}
            ]
            if highland:
                rng.shuffle(highland)
                start = highland[0]

        # Fallback / "edge" style: random tile in outer half of map
        if start is None:
            edge_candidates = [
                c for c in grid.coords()
                if c.distance(origin) > max(SAFE_RADIUS + 3, radius * 0.4)
                and grid[c].terrain not in IMPASSABLE
            ]
            if edge_candidates:
                start = rng.choice(edge_candidates)
        if start is None:
            continue

        # Pick a target — vary between lake targets and non-lake targets
        target: HexCoord | None = None
        target_is_lake = False
        # 40% chance to target a lake, 60% target a random distant point
        other_lakes = [(i, lake) for i, lake in enumerate(lakes) if i != lake_i]
        far_lakes = []
        for oi, olake in other_lakes:
            avg_q = sum(c.q for c in olake) / len(olake)
            avg_r = sum(c.r for c in olake) / len(olake)
            centroid = HexCoord(round(avg_q), round(avg_r))
            dist = start.distance(centroid)
            if dist > min_river_len:
                far_lakes.append((centroid, dist))
        if far_lakes and rng.random() < 0.40:
            far_lakes.sort(key=lambda x: x[1])
            target = far_lakes[rng.randint(0, min(2, len(far_lakes) - 1))][0]
            target_is_lake = True
        if target is None:
            # Pick a random distant point on the map
            angle = rng.uniform(0, 2 * math.pi)
            tq = round(start.q + math.cos(angle) * radius * 0.6)
            tr = round(start.r + math.sin(angle) * radius * 0.6)
            target = HexCoord(tq, tr)

        # Walk from start toward target with heavy meandering
        cur = start
        visited: set[HexCoord] = set()
        path: list[HexCoord] = []
        max_steps = max(100, radius * 3)

        for step in range(max_steps):
            if cur in visited:
                break
            visited.add(cur)
            tile = grid.get(cur)
            if tile is None:
                break
            if cur.distance(origin) <= SAFE_RADIUS:
                break
            path.append(cur)

            # Stop if we reached another lake body (only for lake-targeting rivers)
            if (target_is_lake
                    and len(path) > min_river_len
                    and cur in all_lake_tiles
                    and cur not in source_lake):
                break

            # Direction scoring: blend target-seeking with noise-based wander
            neighbors = cur.neighbors()
            rng.shuffle(neighbors)

            # Sample wander noise at current position for direction bias
            hex_size = settings.hex_size
            cpx, cpy = hex_to_pixel(cur, hex_size)
            wander_val = wander_noise.sample(cpx, cpy)  # -1..1

            best, best_score = None, float('inf')
            for nb in neighbors:
                if nb in visited:
                    continue
                nb_tile = grid.get(nb)
                if nb_tile is None:
                    continue
                if nb.distance(origin) <= SAFE_RADIUS:
                    continue

                # Distance to target — gently pull toward it
                dist_to_target = nb.distance(target)
                cur_dist = cur.distance(target)
                # Reward getting closer, but weakly so meandering dominates
                approach = (dist_to_target - cur_dist) * 0.3

                # Wander component: use noise to favor certain directions
                npx, npy = hex_to_pixel(nb, hex_size)
                nb_wander = wander_noise.sample(npx * 1.7, npy * 1.7)
                wander_pull = nb_wander * 1.5

                # Slight downhill preference (rivers naturally flow down)
                elev_diff = elevation.get(nb, 0) - elevation.get(cur, 0)
                elev_pull = elev_diff * 0.4

                score = approach + wander_pull + elev_pull
                if score < best_score:
                    best, best_score = nb, score

            # Extra meander: 40% chance to pick a random valid neighbor instead
            if best is not None and rng.random() < 0.40:
                valid = [nb for nb in neighbors
                         if nb not in visited and grid.get(nb) is not None
                         and nb.distance(origin) > SAFE_RADIUS]
                if valid:
                    best = rng.choice(valid)

            if best is None:
                # Stuck — try any unvisited neighbor
                fallback = [nb for nb in neighbors
                            if nb not in visited and grid.get(nb) is not None
                            and nb.distance(origin) > SAFE_RADIUS]
                if fallback:
                    best = rng.choice(fallback)

            if best is None:
                break
            cur = best

        # Only keep rivers that are long enough to be recognizable
        if len(path) < min_river_len:
            continue

        # Paint the river path (width 1 — narrow winding water)
        for coord in path:
            if coord.distance(origin) <= SAFE_RADIUS:
                continue
            tile = grid.get(coord)
            if tile is None:
                continue
            tile.terrain = Terrain.WATER
            tile.resource_amount = 0.0
            carved_river_tiles.add(coord)


def _soften_clearing_fringe(grid: HexGrid, origin: HexCoord, safe_r: int) -> None:
    """Downgrade dense forest to regular forest in the ring just outside the clearing."""
    fringe_r = safe_r + 1
    for q in range(-fringe_r, fringe_r + 1):
        r1 = max(-fringe_r, -q - fringe_r)
        r2 = min(fringe_r, -q + fringe_r)
        for r in range(r1, r2 + 1):
            coord = HexCoord(q, r)
            if coord.distance(origin) != fringe_r:
                continue
            tile = grid.get(coord)
            if tile is not None and tile.terrain == Terrain.DENSE_FOREST:
                tile.terrain = Terrain.FOREST


# ── Public API ───────────────────────────────────────────────────

def generate_terrain(seed: str, settings: HexColonySettings) -> HexGrid:
    """Create the full hex grid with deterministic, natural-looking terrain."""
    seed_int = seed_to_int(seed)
    rng = _random.Random(seed_int)

    radius = settings.world_radius
    hex_size = settings.hex_size

    # Scale noise with map size so biomes grow proportionally on larger maps
    # A radius-20 map uses the base values; larger maps scale up.
    scale_factor = max(1.0, radius / 20.0)

    # Build several noise layers for different terrain aspects
    elevation_noise = NoiseMap(rng, octaves=5, base_scale=260.0 * scale_factor, persistence=0.50)
    moisture_noise = NoiseMap(rng, octaves=3, base_scale=300.0 * scale_factor, persistence=0.50)
    detail_noise = NoiseMap(rng, octaves=3, base_scale=80.0 * scale_factor, persistence=0.6)
    # Mountain-range noise: large blobs for distinct mountain biomes
    mountain_noise = NoiseMap(rng, octaves=2, base_scale=280.0 * scale_factor, persistence=0.40)
    # Lake-basin noise: large blobs for lake districts
    lake_noise = NoiseMap(rng, octaves=2, base_scale=300.0 * scale_factor, persistence=0.40)

    grid = HexGrid()
    elevation: dict[HexCoord, float] = {}
    lake_affinity_map: dict[HexCoord, float] = {}
    origin = HexCoord(0, 0)

    # --- Pass 1: assign raw terrain from noise -----------------------
    for q in range(-radius, radius + 1):
        r1 = max(-radius, -q - radius)
        r2 = min(radius, -q + radius)
        for r in range(r1, r2 + 1):
            coord = HexCoord(q, r)
            px, py = hex_to_pixel(coord, hex_size)

            elev = elevation_noise.sample(px, py)
            moist = moisture_noise.sample(px, py)
            det = detail_noise.sample(px, py)
            mtn_affinity = mountain_noise.sample(px, py)  # high = mountain-prone
            lake_affinity = lake_noise.sample(px, py)      # low = lake-prone

            # Edge ratio: 0 at centre, 1 at border
            dist = coord.distance(origin)
            edge_t = dist / radius if radius > 0 else 0.0

            # Edge shaping: dampen elevation in the inner 60% of the map
            # (keeping the centre calm with mostly forest), then amplify
            # in the outer ring so mountains and water appear at borders.
            if edge_t < 0.6:
                # Inner zone: gently compress elevation toward zero
                dampen = 1.0 - 0.3 * (edge_t / 0.6)  # 1.0 at centre → 0.7 at 60%
                elev *= dampen
            else:
                # Outer zone: transition from dampened (0.7) back up and beyond
                outer_t = (edge_t - 0.6) / 0.4  # 0..1 across outer 40%
                elev *= 0.7 + 0.6 * outer_t  # 0.7 → 1.3 at border

            # Still softly depress the very outermost ring so the map
            # doesn't end abruptly with tall mountains at the boundary.
            if edge_t > 0.9:
                rim = (edge_t - 0.9) / 0.1  # 0..1 in last 10%
                elev *= 1.0 - 0.3 * rim

            elevation[coord] = elev
            lake_affinity_map[coord] = lake_affinity

            terrain = _classify(elev, moist, det, edge_t, mtn_affinity, lake_affinity)
            amount = _resource_amount(terrain, rng)
            grid.set_tile(HexTile(coord=coord, terrain=terrain, resource_amount=amount))

    # --- Pass 2: (clearing deferred to after all post-processing) ---

    # --- Pass 3: expand lakes around high lake-affinity zones --------
    _expand_lakes(grid, rng, elevation, lake_affinity_map)

    # --- Pass 4: carve rivers starting from lake edges ---------------
    # Ensure at least 3 real rivers; more on larger maps
    min_rivers = 3
    max_rivers = max(5, 3 + radius // 20)
    river_count = rng.randint(min_rivers, max_rivers)
    _carve_rivers(grid, rng, settings, elevation, lake_affinity_map, count=river_count)

    # --- Pass 5: ring mountains with stone deposits ------------------
    _ring_mountains_with_stone(grid, rng)

    # --- Pass 6: clear safe zone + soften fringe (rendered last) ----
    for q2 in range(-SAFE_RADIUS, SAFE_RADIUS + 1):
        for r2 in range(max(-SAFE_RADIUS, -q2 - SAFE_RADIUS),
                        min(SAFE_RADIUS, -q2 + SAFE_RADIUS) + 1):
            nb = HexCoord(q2, r2)
            tile = grid.get(nb)
            if tile is not None:
                tile.terrain = Terrain.GRASS
                tile.resource_amount = 0.0
    _soften_clearing_fringe(grid, origin, SAFE_RADIUS)

    # --- Pass 7: ensure connectivity from safe-zone edge to map border
    _ensure_connectivity(grid, rng, radius)

    return grid


def _classify(elev: float, moist: float, detail: float, edge_t: float,
              mtn_affinity: float = 0.0, lake_affinity: float = 0.0) -> Terrain:
    """Map noise values to a terrain type with strong biome clustering.

    *edge_t* ranges from 0 (map centre) to 1 (map border).
    *mtn_affinity* clusters mountains: only high-affinity zones get peaks.
    *lake_affinity* clusters water: only low-affinity (negative) zones get lakes.

    The classifier is designed to produce large contiguous biome regions
    rather than noisy salt-and-pepper terrain.
    """
    # Ease thresholds toward the edges
    water_thresh  = -0.30 + 0.06 * edge_t
    mtn_thresh    =  0.36 - 0.10 * edge_t
    stone_thresh  =  0.26 - 0.06 * edge_t

    # ── Water biome: requires both low elevation AND lake-basin affinity ──
    if elev < water_thresh and lake_affinity < -0.10:
        return Terrain.WATER
    # Very deep depressions become water regardless (rare basin lakes)
    if elev < water_thresh - 0.18:
        return Terrain.WATER

    # ── Mountain biome: requires high elevation AND strong mtn affinity ──
    if elev > mtn_thresh and mtn_affinity > 0.12:
        return Terrain.MOUNTAIN

    # ── Stone foothills: high elevation or edge of mountain affinity ──
    if elev > stone_thresh and mtn_affinity > -0.05:
        return Terrain.STONE_DEPOSIT

    # ── Forest biomes: driven primarily by moisture ──
    # Dense forest: high moisture regions
    if moist > 0.10:
        return Terrain.DENSE_FOREST
    # Regular forest: moderate moisture
    if moist > -0.15:
        return Terrain.FOREST

    # ── Grass plains biome: low moisture ──
    if moist < -0.20:
        # Fiber patches embedded in grass plains
        if detail < -0.10 and elev > -0.08:
            return Terrain.FIBER_PATCH
        return Terrain.GRASS

    # ── Transition zone: fiber or grass ──
    if detail < -0.15 and elev > -0.08:
        return Terrain.FIBER_PATCH
    return Terrain.GRASS


def _resource_amount(terrain: Terrain, rng: _random.Random) -> float:
    if terrain in (Terrain.FOREST, Terrain.DENSE_FOREST):
        return rng.uniform(20, 60)
    if terrain == Terrain.STONE_DEPOSIT:
        return rng.uniform(30, 80)
    if terrain == Terrain.FIBER_PATCH:
        return rng.uniform(15, 40)
    if terrain == Terrain.MOUNTAIN:
        return rng.uniform(50, 120)
    return 0.0


def _expand_lakes(grid: HexGrid, rng: _random.Random,
                  elevation: dict[HexCoord, float],
                  lake_affinity: dict[HexCoord, float]) -> None:
    """Grow existing water tiles into larger lakes in lake-basin zones.

    Expansion is much more aggressive where lake_affinity is strongly
    negative (lake-basin zones), creating a few large lakes rather than
    many small puddles.
    """
    water_tiles = [
        c for c in grid.coords()
        if grid[c].terrain == Terrain.WATER
    ]
    origin = HexCoord(0, 0)
    for coord in water_tiles:
        la = lake_affinity.get(coord, 0.0)
        # In lake basins (la < -0.05), expand aggressively
        # Outside basins, expand rarely
        if la < -0.15:
            expand_chance = 0.42
            elev_gate = -0.07
        elif la < -0.05:
            expand_chance = 0.20
            elev_gate = -0.12
        else:
            expand_chance = 0.03
            elev_gate = -0.22

        if rng.random() < expand_chance:
            for nb in coord.neighbors():
                tile = grid.get(nb)
                if tile is None or tile.terrain == Terrain.WATER:
                    continue
                if nb.distance(origin) <= SAFE_RADIUS:
                    continue
                e = elevation.get(nb, 0.0)
                if e < elev_gate and rng.random() < 0.45:
                    tile.terrain = Terrain.WATER
                    tile.resource_amount = 0.0


def _ring_mountains_with_stone(grid: HexGrid, rng: _random.Random) -> None:
    """Ensure most mountain tiles are surrounded by stone deposits."""
    mountain_coords = [
        c for c in grid.coords()
        if grid[c].terrain == Terrain.MOUNTAIN
    ]
    origin = HexCoord(0, 0)
    for coord in mountain_coords:
        for nb in coord.neighbors():
            tile = grid.get(nb)
            if tile is None:
                continue
            if tile.terrain in (Terrain.WATER, Terrain.MOUNTAIN):
                continue
            if nb.distance(origin) <= SAFE_RADIUS:
                continue
            if rng.random() < 0.75:
                tile.terrain = Terrain.STONE_DEPOSIT
                tile.resource_amount = rng.uniform(30, 80)


# ── Connectivity guarantee ───────────────────────────────────────

def _flood_passable(grid: HexGrid, start: HexCoord,
                    exclude: set[HexCoord]) -> set[HexCoord]:
    """BFS over passable tiles starting from *start*, ignoring *exclude*."""
    visited: set[HexCoord] = set()
    queue = [start]
    while queue:
        cur = queue.pop()
        if cur in visited:
            continue
        visited.add(cur)
        for nb in cur.neighbors():
            if nb in visited or nb in exclude:
                continue
            tile = grid.get(nb)
            if tile is not None and _is_passable(tile.terrain):
                queue.append(nb)
    return visited


def _ensure_connectivity(grid: HexGrid, rng: _random.Random,
                         radius: int) -> None:
    """Guarantee at least half of safe-zone edge tiles can reach the map border.

    For each safe-zone edge tile that can't reach the border, carve a
    passable corridor outward until it connects to a tile that *can* reach
    the border (or hits the border itself).
    """
    origin = HexCoord(0, 0)

    # Collect safe-zone interior tiles (we exclude them from pathfinding
    # targets — they don't count as "reaching the border").
    safe_tiles: set[HexCoord] = set()
    for q in range(-SAFE_RADIUS, SAFE_RADIUS + 1):
        for r in range(max(-SAFE_RADIUS, -q - SAFE_RADIUS),
                       min(SAFE_RADIUS, -q + SAFE_RADIUS) + 1):
            safe_tiles.add(HexCoord(q, r))

    # Identify safe-zone edge tiles (distance == SAFE_RADIUS from origin)
    edge_tiles = [c for c in safe_tiles if c.distance(origin) == SAFE_RADIUS]

    # Identify map-border tiles
    border_tiles: set[HexCoord] = set()
    for c in grid.coords():
        if c.distance(origin) == radius:
            border_tiles.add(c)

    # Test connectivity for each edge tile
    connected_count = 0
    disconnected: list[HexCoord] = []

    for et in edge_tiles:
        tile = grid.get(et)
        if tile is None or not _is_passable(tile.terrain):
            disconnected.append(et)
            continue
        reachable = _flood_passable(grid, et, safe_tiles - {et})
        if reachable & border_tiles:
            connected_count += 1
        else:
            disconnected.append(et)

    needed = max(0, (len(edge_tiles) + 1) // 2 - connected_count)
    if needed == 0:
        return

    # Sort disconnected tiles for determinism, then try to carve paths
    rng.shuffle(disconnected)
    for et in disconnected[:needed]:
        _carve_path_to_border(grid, rng, et, safe_tiles, border_tiles, radius)


def _carve_path_to_border(
    grid: HexGrid,
    rng: _random.Random,
    start: HexCoord,
    safe_tiles: set[HexCoord],
    border_tiles: set[HexCoord],
    radius: int,
) -> None:
    """Carve a passable corridor from *start* outward towards the map border.

    At each step we pick the non-safe neighbour closest to the border that
    is currently impassable and convert it to grass, or step through an
    already-passable tile.  Stops when the flood from *start* can reach
    any border tile.
    """
    origin = HexCoord(0, 0)
    cur = start
    visited: set[HexCoord] = {cur}

    # Make sure start itself is passable
    tile = grid.get(cur)
    if tile is not None and not _is_passable(tile.terrain):
        tile.terrain = Terrain.GRASS
        tile.resource_amount = 0.0

    # Compute reachability once; only re-check after actually carving a tile.
    _excluded = safe_tiles - {start}
    if _flood_passable(grid, start, _excluded) & border_tiles:
        return

    for _ in range(radius * 3):
        # Pick best neighbour: furthest from origin, prefer already passable
        candidates = []
        for nb in cur.neighbors():
            if nb in visited or nb in safe_tiles:
                continue
            t = grid.get(nb)
            if t is None:
                continue
            candidates.append(nb)

        if not candidates:
            break

        # Sort: prefer passable tiles first, then by distance from origin (desc)
        def _sort_key(c: HexCoord) -> tuple[int, int]:
            t = grid[c]
            passable = 0 if _is_passable(t.terrain) else 1
            return (passable, -c.distance(origin))

        candidates.sort(key=_sort_key)
        nxt = candidates[0]
        visited.add(nxt)

        t = grid.get(nxt)
        if t is not None and not _is_passable(t.terrain):
            t.terrain = Terrain.GRASS
            t.resource_amount = 0.0
            # Only recheck reachability when the grid actually changed
            if _flood_passable(grid, start, _excluded) & border_tiles:
                return

        cur = nxt
