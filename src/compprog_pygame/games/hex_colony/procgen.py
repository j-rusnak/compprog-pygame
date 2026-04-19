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
from dataclasses import replace as _replace

from compprog_pygame.games.hex_colony.hex_grid import HexCoord, HexGrid, HexTile, Terrain, hex_to_pixel
from compprog_pygame.games.hex_colony.settings import HexColonySettings
from compprog_pygame.games.hex_colony import params


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

IMPASSABLE = frozenset({Terrain.WATER, Terrain.MOUNTAIN, Terrain.STONE_DEPOSIT})

# Terrain where buildings cannot be placed (subset of IMPASSABLE).
# Stone deposits are impassable for people but players can build on them.
UNBUILDABLE = frozenset({Terrain.WATER, Terrain.MOUNTAIN})

SAFE_RADIUS = params.SAFE_ZONE_RADIUS


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
            tile.food_amount = 0.0
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


# ── Ore vein generation ──────────────────────────────────────────

def _generate_ore_veins(
    grid: HexGrid,
    rng: _random.Random,
    settings: HexColonySettings,
    ore_terrain: Terrain,
    num_veins: int,
    vein_min: int,
    vein_max: int,
) -> None:
    """Generate clusters of ore veins on any non-water tile.

    Each vein starts at a random seed tile and grows outward via BFS
    with random chance, producing natural-looking irregular clusters.
    The underlying terrain appearance is preserved in ``tile.underlying_terrain``.
    """
    origin = HexCoord(0, 0)
    radius = settings.world_radius
    # Eligible tiles: any land tile not in safe zone and not water
    eligible = [
        c for c in grid.coords()
        if c.distance(origin) > SAFE_RADIUS + 2
        and grid[c].terrain not in {Terrain.WATER, Terrain.MOUNTAIN,
                                     Terrain.IRON_VEIN, Terrain.COPPER_VEIN}
    ]
    if not eligible:
        return

    placed: set[HexCoord] = set()

    for _ in range(num_veins):
        if not eligible:
            break
        seed = rng.choice(eligible)
        vein_size = rng.randint(vein_min, vein_max)

        # BFS growth from seed
        frontier = [seed]
        vein_tiles: list[HexCoord] = []
        visited: set[HexCoord] = {seed}

        while frontier and len(vein_tiles) < vein_size:
            rng.shuffle(frontier)
            cur = frontier.pop(0)
            tile = grid.get(cur)
            if tile is None:
                continue
            if cur in placed:
                continue
            if tile.terrain in {Terrain.WATER, Terrain.MOUNTAIN,
                                Terrain.IRON_VEIN, Terrain.COPPER_VEIN}:
                continue
            if cur.distance(origin) <= SAFE_RADIUS:
                continue

            # Place ore on this tile
            tile.underlying_terrain = tile.terrain
            tile.terrain = ore_terrain
            if ore_terrain == Terrain.IRON_VEIN:
                lo, hi = params.TILE_RESOURCE_IRON_VEIN
            else:
                lo, hi = params.TILE_RESOURCE_COPPER_VEIN
            tile.resource_amount = rng.uniform(lo, hi)
            tile.food_amount = 0.0
            vein_tiles.append(cur)
            placed.add(cur)

            # Add neighbors as candidates with decreasing probability
            for nb in cur.neighbors():
                if nb not in visited:
                    visited.add(nb)
                    if rng.random() < params.ORE_VEIN_NEIGHBOR_EXPAND_CHANCE:
                        frontier.append(nb)

        # Remove used tiles from eligible pool
        eligible = [c for c in eligible if c not in placed]


# ── Public API ───────────────────────────────────────────────────

def _generate_single_region(seed: str, settings: HexColonySettings) -> HexGrid:
    """Create a single hex region centered at (0, 0).

    Kept for backwards compatibility / single-region testing — the live
    game now uses :func:`generate_terrain` which produces a continuous
    7-region map with seamless borders.
    """
    grid, _ = _build_multi_region_terrain(seed, settings, region_centres=[HexCoord(0, 0)])
    return grid


# ── Multi-region map (player region + AI tribe neighbours) ───────

# Number of AI tribe camps spawned in the surrounding ring (out of 6 neighbours).
_AI_TRIBE_COUNT: int = 3


def _neighbor_region_offsets(radius: int) -> list[tuple[int, int]]:
    """Hex-of-hexes meta-grid offsets for the 6 neighbour regions.

    Each neighbour region of axial radius ``radius`` is centred at a
    distance ``2*radius+1`` from origin, arranged so the seven regions
    (centre + 6 neighbours) tessellate without gaps or overlap.
    """
    R = radius
    return [
        (2 * R + 1, -R),
        (R, R + 1),
        (-R - 1, 2 * R + 1),
        (-(2 * R + 1), R),
        (-R, -R - 1),
        (R + 1, -(2 * R + 1)),
    ]


def _build_multi_region_terrain(
    seed: str,
    settings: HexColonySettings,
    region_centres: list[HexCoord],
    progress_callback=None,
) -> tuple[HexGrid, dict[HexCoord, float]]:
    """Build a hex grid covering one or more region areas with a single
    continuous noise field, so seams between adjacent regions disappear.

    Edge shaping is computed against the OVERALL bounding hex of the
    union of all regions (centred on origin), so the centre region stays
    calm and mountains/water naturally appear at the outer rim.

    *progress_callback* (if provided) is invoked as ``cb(fraction, label)``
    with ``fraction`` in [0.0, 1.0] after each major generation pass so
    the loading screen can show real progress.
    """
    def _report(p: float, label: str) -> None:
        if progress_callback is not None:
            try:
                progress_callback(min(1.0, max(0.0, p)), label)
            except Exception:
                pass

    seed_int = seed_to_int(seed)
    rng = _random.Random(seed_int)

    radius = settings.world_radius
    hex_size = settings.hex_size

    # Effective overall radius: distance from origin to the farthest
    # corner of any region centre, plus the region radius itself.
    if region_centres:
        max_centre_dist = max(c.distance(HexCoord(0, 0)) for c in region_centres)
    else:
        max_centre_dist = 0
    effective_radius = max(radius, max_centre_dist + radius)

    # Scale noise with the size of a SINGLE region (not the multi-region
    # union) so biomes/landmarks stay the same size as the original
    # single-region map; the multi-region change just extends that style
    # outward seamlessly.
    scale_factor = max(1.0, radius / 20.0)

    # Build all noise layers ONCE — this is what makes neighbour regions
    # continuous with the centre.  Sample them anywhere in pixel space.
    # ``detail_noise`` was 3 octaves; 2 octaves render visually
    # identically at this scale and shave a noticeable slice off the
    # per-hex noise cost in Pass 1.
    elevation_noise = NoiseMap(rng, octaves=5, base_scale=260.0 * scale_factor, persistence=0.50)
    moisture_noise = NoiseMap(rng, octaves=3, base_scale=300.0 * scale_factor, persistence=0.50)
    detail_noise = NoiseMap(rng, octaves=2, base_scale=80.0 * scale_factor, persistence=0.6)
    mountain_noise = NoiseMap(rng, octaves=2, base_scale=280.0 * scale_factor, persistence=0.40)
    lake_noise = NoiseMap(rng, octaves=2, base_scale=300.0 * scale_factor, persistence=0.40)
    _report(0.02, "Carving terrain")

    grid = HexGrid()
    elevation: dict[HexCoord, float] = {}
    lake_affinity_map: dict[HexCoord, float] = {}
    origin = HexCoord(0, 0)

    # --- Pass 1: assign raw terrain from noise across all regions ----
    seen: set[HexCoord] = set()
    n_regions = max(1, len(region_centres))
    for ri, centre in enumerate(region_centres):
        for q in range(-radius, radius + 1):
            r1 = max(-radius, -q - radius)
            r2 = min(radius, -q + radius)
            for r in range(r1, r2 + 1):
                coord = HexCoord(centre.q + q, centre.r + r)
                if coord in seen:
                    continue
                seen.add(coord)
                px, py = hex_to_pixel(coord, hex_size)

                elev = elevation_noise.sample(px, py)
                moist = moisture_noise.sample(px, py)
                det = detail_noise.sample(px, py)
                mtn_affinity = mountain_noise.sample(px, py)
                lake_affinity = lake_noise.sample(px, py)

                # Edge ratio against the overall map (not per region).
                dist = coord.distance(origin)
                edge_t = (dist / effective_radius) if effective_radius > 0 else 0.0
                if edge_t > 1.0:
                    edge_t = 1.0

                # Same edge-shape curve as before, applied globally.
                if edge_t < 0.6:
                    dampen = 1.0 - 0.3 * (edge_t / 0.6)
                    elev *= dampen
                else:
                    outer_t = (edge_t - 0.6) / 0.4
                    elev *= 0.7 + 0.6 * outer_t
                if edge_t > 0.9:
                    rim = (edge_t - 0.9) / 0.1
                    elev *= 1.0 - 0.3 * rim

                elevation[coord] = elev
                lake_affinity_map[coord] = lake_affinity

                terrain = _classify(elev, moist, det, edge_t,
                                    mtn_affinity, lake_affinity)
                amount = _resource_amount(terrain, rng)
                food = _food_amount(terrain, rng)
                grid.set_tile(HexTile(coord=coord, terrain=terrain,
                                      resource_amount=amount,
                                      food_amount=food))
        # Pass 1 occupies 0.02 → 0.55 of the bar.
        _report(0.02 + 0.53 * (ri + 1) / n_regions, "Carving terrain")

    # --- Pass 3: lakes ------------------------------------------------
    _expand_lakes(grid, rng, elevation, lake_affinity_map)
    _report(0.62, "Filling lakes")

    # --- Pass 4: rivers ----------------------------------------------
    # Keep river LENGTH/meander tuned to a single-region scale so they
    # don't become absurdly long; just spawn more of them for the wider
    # multi-region world.
    if len(region_centres) <= 1:
        river_count = rng.randint(3, 5)
    else:
        river_count = rng.randint(6, 10)
    _carve_rivers(grid, rng, settings, elevation,
                  lake_affinity_map, count=river_count)
    _report(0.78, "Carving rivers")

    # --- Pass 5: stone deposits ringing mountain peaks ---------------
    _ring_mountains_with_stone(grid, rng)
    _report(0.82, "Placing stone deposits")

    # --- Pass 5b: ore veins (scaled to overall map size) -------------
    iron_veins = max(params.ORE_IRON_VEIN_COUNT_MIN,
                     params.ORE_IRON_VEIN_COUNT_BASE
                     + effective_radius // params.ORE_IRON_VEIN_COUNT_RADIUS_DIVISOR)
    copper_veins = max(params.ORE_COPPER_VEIN_COUNT_MIN,
                       params.ORE_COPPER_VEIN_COUNT_BASE
                       + effective_radius // params.ORE_COPPER_VEIN_COUNT_RADIUS_DIVISOR)
    ore_settings = _replace(settings, world_radius=effective_radius) \
        if effective_radius != radius else settings
    _generate_ore_veins(grid, rng, ore_settings, Terrain.IRON_VEIN,
                        num_veins=iron_veins,
                        vein_min=params.ORE_IRON_VEIN_SIZE_MIN,
                        vein_max=params.ORE_IRON_VEIN_SIZE_MAX)
    _generate_ore_veins(grid, rng, ore_settings, Terrain.COPPER_VEIN,
                        num_veins=copper_veins,
                        vein_min=params.ORE_COPPER_VEIN_SIZE_MIN,
                        vein_max=params.ORE_COPPER_VEIN_SIZE_MAX)
    _report(0.92, "Scattering ore veins")

    # --- Pass 6: clear safe zone around centre origin ----------------
    for q2 in range(-SAFE_RADIUS, SAFE_RADIUS + 1):
        for r2 in range(max(-SAFE_RADIUS, -q2 - SAFE_RADIUS),
                        min(SAFE_RADIUS, -q2 + SAFE_RADIUS) + 1):
            nb = HexCoord(q2, r2)
            tile = grid.get(nb)
            if tile is not None:
                tile.terrain = Terrain.GRASS
                tile.resource_amount = 0.0
                tile.food_amount = 0.0
                tile.underlying_terrain = None
    _soften_clearing_fringe(grid, origin, SAFE_RADIUS)

    # --- Pass 6b: starter resource clusters --------------------------
    _ensure_starter_resources(grid, rng, origin)

    # --- Pass 6c: guaranteed nearby ore ------------------------------
    _ensure_nearby_ore(grid, rng, origin)
    _report(0.97, "Preparing landing site")

    # --- Pass 7: connectivity from the safe-zone outward -------------
    _ensure_connectivity(grid, rng, effective_radius)
    _report(1.0, "Finalising")

    return grid, elevation


def generate_terrain(
    seed: str, settings: HexColonySettings,
    progress_callback=None,
) -> tuple[HexGrid, list[HexCoord]]:
    """Create the central player region plus 6 surrounding neighbour regions.

    Terrain is generated with a single shared noise field so borders
    between regions are seamless and biomes (forests, lakes, rivers)
    naturally span across multiple regions.

    Returns ``(grid, ai_camp_coords)`` where ``ai_camp_coords`` is the
    list of axial coordinates where AI tribe camps should be placed
    (3 of the 6 neighbour-region centres, chosen deterministically from
    the world seed).

    *progress_callback*, if provided, is called as ``cb(fraction, label)``
    with ``fraction`` ramping from 0.0 to 1.0 over the course of
    generation.  Safe to call from a background thread.
    """
    radius = settings.world_radius
    offsets = _neighbor_region_offsets(radius)
    centres = [HexCoord(0, 0)] + [HexCoord(dq, dr) for dq, dr in offsets]

    grid, _elev = _build_multi_region_terrain(
        seed, settings, centres,
        progress_callback=progress_callback,
    )

    # Deterministically pick 3 of the 6 neighbour centres for AI tribes.
    selector_rng = _random.Random(seed_to_int(seed) ^ 0xA17C_AAFE)
    camp_indices = set(selector_rng.sample(range(6), _AI_TRIBE_COUNT))
    ai_camp_coords = [centres[i + 1] for i in sorted(camp_indices)]
    return grid, ai_camp_coords


# ── Starter-area resource guarantee ──────────────────────────────

_STARTER_SEARCH_RADIUS = 15
_STARTER_CLUSTER_SIZE = 4


def _count_terrain_near(
    grid: HexGrid, origin: HexCoord, targets: set[Terrain], radius: int,
) -> int:
    count = 0
    for q in range(-radius, radius + 1):
        for r in range(max(-radius, -q - radius),
                       min(radius, -q + radius) + 1):
            c = HexCoord(q, r)
            if c.distance(origin) > radius:
                continue
            tile = grid.get(c)
            if tile is not None and tile.terrain in targets:
                count += 1
    return count


def _stamp_cluster(
    grid: HexGrid,
    rng: _random.Random,
    origin: HexCoord,
    terrain: Terrain,
    size: int,
    resource_range: tuple[float, float],
    search_radius: int,
) -> None:
    """Replace a small grassy cluster near spawn with *terrain* tiles.

    Picks a grassy tile in a ring just outside the safe zone (so the
    spawn clearing stays clean) but within *search_radius*, then grows
    a BFS cluster of *size* tiles, converting each to *terrain* with
    a resource amount drawn from *resource_range*.
    """
    # Candidate seed tiles: grass just outside the safe zone, within
    # search_radius of origin, with enough grassy neighbours to grow.
    inner = SAFE_RADIUS + 1
    candidates: list[HexCoord] = []
    for q in range(-search_radius, search_radius + 1):
        for r in range(max(-search_radius, -q - search_radius),
                       min(search_radius, -q + search_radius) + 1):
            c = HexCoord(q, r)
            d = c.distance(origin)
            if d < inner or d > search_radius:
                continue
            tile = grid.get(c)
            if tile is None or tile.terrain != Terrain.GRASS:
                continue
            # Need some grassy room for a cluster.
            grassy_nb = sum(
                1 for nb in c.neighbors()
                if grid.get(nb) is not None
                and grid.get(nb).terrain == Terrain.GRASS
                and nb.distance(origin) > SAFE_RADIUS
            )
            if grassy_nb >= 2:
                candidates.append(c)
    if not candidates:
        return
    # Prefer candidates closer to origin to keep the starter ring tight.
    candidates.sort(key=lambda c: c.distance(origin))
    # Pick a random seed from the closest third for determinism-friendly
    # variety.
    pool_end = max(1, len(candidates) // 3)
    seed = rng.choice(candidates[:pool_end])

    placed: set[HexCoord] = set()
    frontier = [seed]
    lo, hi = resource_range
    while frontier and len(placed) < size:
        rng.shuffle(frontier)
        cur = frontier.pop(0)
        if cur in placed:
            continue
        tile = grid.get(cur)
        if tile is None or tile.terrain != Terrain.GRASS:
            continue
        if cur.distance(origin) <= SAFE_RADIUS:
            continue
        tile.terrain = terrain
        tile.resource_amount = rng.uniform(lo, hi)
        if terrain == Terrain.FIBER_PATCH:
            flo, fhi = params.TILE_RESOURCE_BERRY_PATCH
            tile.food_amount = rng.uniform(flo, fhi)
        placed.add(cur)
        for nb in cur.neighbors():
            if nb not in placed:
                frontier.append(nb)


def _ensure_starter_resources(
    grid: HexGrid, rng: _random.Random, origin: HexCoord,
) -> None:
    """Ensure wood, stone, and fibre tiles exist near the spawn."""
    wood_terrains = {Terrain.FOREST, Terrain.DENSE_FOREST}
    stone_terrains = {Terrain.STONE_DEPOSIT}
    fibre_terrains = {Terrain.FIBER_PATCH}
    # Each category needs at least 3 tiles near spawn so the first
    # gatherer assignment doesn't starve.
    min_count = 3
    r = _STARTER_SEARCH_RADIUS

    if _count_terrain_near(grid, origin, wood_terrains, r) < min_count:
        _stamp_cluster(
            grid, rng, origin, Terrain.FOREST,
            _STARTER_CLUSTER_SIZE, params.TILE_RESOURCE_FOREST, r,
        )
    if _count_terrain_near(grid, origin, stone_terrains, r) < min_count:
        lo_hi = getattr(params, "TILE_RESOURCE_STONE_DEPOSIT", (3.0, 6.0))
        _stamp_cluster(
            grid, rng, origin, Terrain.STONE_DEPOSIT,
            _STARTER_CLUSTER_SIZE, lo_hi, r,
        )
    if _count_terrain_near(grid, origin, fibre_terrains, r) < min_count:
        lo_hi = getattr(params, "TILE_RESOURCE_FIBER_PATCH", (2.0, 5.0))
        _stamp_cluster(
            grid, rng, origin, Terrain.FIBER_PATCH,
            _STARTER_CLUSTER_SIZE, lo_hi, r,
        )


# ── Nearby ore-vein guarantee ────────────────────────────────────

_ORE_SEARCH_RADIUS = 25
_ORE_CLUSTER_SIZE = 4


def _stamp_ore_cluster(
    grid: HexGrid,
    rng: _random.Random,
    origin: HexCoord,
    ore_terrain: Terrain,
    size: int,
    resource_range: tuple[float, float],
    search_radius: int,
) -> None:
    """Place a small ore vein cluster within *search_radius* of origin.

    Works like ``_stamp_cluster`` but converts any non-water/mountain
    tile (preserving ``underlying_terrain``) instead of requiring grass.
    """
    inner = SAFE_RADIUS + 3
    blocked = {
        Terrain.WATER, Terrain.MOUNTAIN,
        Terrain.IRON_VEIN, Terrain.COPPER_VEIN,
    }
    candidates: list[HexCoord] = []
    for q in range(-search_radius, search_radius + 1):
        for r in range(max(-search_radius, -q - search_radius),
                       min(search_radius, -q + search_radius) + 1):
            c = HexCoord(q, r)
            d = c.distance(origin)
            if d < inner or d > search_radius:
                continue
            tile = grid.get(c)
            if tile is None or tile.terrain in blocked:
                continue
            if tile.building is not None:
                continue
            candidates.append(c)
    if not candidates:
        return
    candidates.sort(key=lambda c: c.distance(origin))
    pool_end = max(1, len(candidates) // 3)
    seed = rng.choice(candidates[:pool_end])

    placed: set[HexCoord] = set()
    frontier = [seed]
    lo, hi = resource_range
    while frontier and len(placed) < size:
        rng.shuffle(frontier)
        cur = frontier.pop(0)
        if cur in placed:
            continue
        tile = grid.get(cur)
        if tile is None or tile.terrain in blocked:
            continue
        if cur.distance(origin) <= SAFE_RADIUS:
            continue
        tile.underlying_terrain = tile.terrain
        tile.terrain = ore_terrain
        tile.resource_amount = rng.uniform(lo, hi)
        tile.food_amount = 0.0
        placed.add(cur)
        for nb in cur.neighbors():
            if nb not in placed:
                frontier.append(nb)


def _ensure_nearby_ore(
    grid: HexGrid, rng: _random.Random, origin: HexCoord,
) -> None:
    """Guarantee at least one iron vein and one copper vein within 25 tiles."""
    r = _ORE_SEARCH_RADIUS
    iron_terrains = {Terrain.IRON_VEIN}
    copper_terrains = {Terrain.COPPER_VEIN}

    if _count_terrain_near(grid, origin, iron_terrains, r) < 1:
        _stamp_ore_cluster(
            grid, rng, origin, Terrain.IRON_VEIN,
            _ORE_CLUSTER_SIZE, params.TILE_RESOURCE_IRON_VEIN, r,
        )
    if _count_terrain_near(grid, origin, copper_terrains, r) < 1:
        _stamp_ore_cluster(
            grid, rng, origin, Terrain.COPPER_VEIN,
            _ORE_CLUSTER_SIZE, params.TILE_RESOURCE_COPPER_VEIN, r,
        )


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
        lo, hi = params.TILE_RESOURCE_FOREST
        return rng.uniform(lo, hi)
    if terrain == Terrain.STONE_DEPOSIT:
        lo, hi = params.TILE_RESOURCE_STONE_DEPOSIT
        return rng.uniform(lo, hi)
    if terrain == Terrain.FIBER_PATCH:
        lo, hi = params.TILE_RESOURCE_FIBER_PATCH
        return rng.uniform(lo, hi)
    if terrain == Terrain.MOUNTAIN:
        lo, hi = params.TILE_RESOURCE_MOUNTAIN
        return rng.uniform(lo, hi)
    return 0.0


def _food_amount(terrain: Terrain, rng: _random.Random) -> float:
    """Food available on fiber/berry patch tiles."""
    if terrain == Terrain.FIBER_PATCH:
        lo, hi = params.TILE_RESOURCE_BERRY_PATCH
        return rng.uniform(lo, hi)
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
                    tile.food_amount = 0.0


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
                tile.food_amount = 0.0


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
        tile.food_amount = 0.0

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
            t.food_amount = 0.0
            # Only recheck reachability when the grid actually changed
            if _flood_passable(grid, start, _excluded) & border_tiles:
                return

        cur = nxt
