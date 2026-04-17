"""Cross-tile procedural terrain overlays for Hex Colony.

Analyses terrain clusters (connected components of the same biome) and
generates pixel-art overlay items that span multiple tiles.  A depth map
is computed for each cluster so that interior tiles get larger / more
prominent art while edges get smaller details.

Mountains export a per-tile depth map so the renderer can colour tiles
from dark foothills to snowy peaks and draw contour ridge lines.
"""

from __future__ import annotations

import random as _random
from dataclasses import dataclass

from compprog_pygame.games.hex_colony.hex_grid import HexCoord, HexGrid, HexTile, Terrain, hex_to_pixel

# ── Overlay item data classes ────────────────────────────────────

@dataclass(slots=True)
class OverlayTree:
    wx: float; wy: float
    trunk_h: float; crown_rx: float; crown_ry: float
    crown_color: tuple[int, int, int]
    trunk_color: tuple[int, int, int]
    highlight_color: tuple[int, int, int]
    style: str  # "canopy", "conifer", "round"

@dataclass(slots=True)
class OverlayRock:
    wx: float; wy: float
    w: float; h: float
    color: tuple[int, int, int]
    highlight_color: tuple[int, int, int]

@dataclass(slots=True)
class OverlayBush:
    wx: float; wy: float
    radius: float
    color: tuple[int, int, int]
    berry_color: tuple[int, int, int] | None

@dataclass(slots=True)
class OverlayGrassTuft:
    wx: float; wy: float
    h: float; color: tuple[int, int, int]

@dataclass(slots=True)
class OverlayRipple:
    wx: float; wy: float
    w: float; phase_offset: float

@dataclass(slots=True)
class OverlayCrystal:
    wx: float; wy: float
    h: float; w: float
    color: tuple[int, int, int]
    highlight_color: tuple[int, int, int]
    angle: float  # tilt angle in radians

@dataclass(slots=True)
class OverlayRuin:
    """Remnant of old human civilization — pillars, walls, arches."""
    wx: float; wy: float
    variant: int  # 0=pillar, 1=broken wall, 2=arch
    color: tuple[int, int, int]
    highlight_color: tuple[int, int, int]
    coord: tuple[int, int]  # (q, r) for the hex this ruin sits on

OverlayItem = (
    OverlayTree | OverlayRock
    | OverlayBush | OverlayGrassTuft | OverlayRipple | OverlayCrystal
    | OverlayRuin
)

# ── Cluster analysis ────────────────────────────────────────────

_FOREST_GROUP = frozenset({Terrain.FOREST, Terrain.DENSE_FOREST})

def _terrain_group(terrain: Terrain) -> str:
    if terrain in _FOREST_GROUP:
        return "forest"
    return terrain.name


def _find_terrain_clusters(
    grid: HexGrid,
) -> list[tuple[str, set[HexCoord], dict[HexCoord, int]]]:
    """DFS flood-fill to find connected components, with BFS-calculated depth maps."""
    visited: set[HexCoord] = set()
    clusters: list[tuple[str, set[HexCoord], dict[HexCoord, int]]] = []

    for tile in grid.tiles():
        coord = tile.coord
        if coord in visited:
            continue
        group = _terrain_group(tile.terrain)

        component: set[HexCoord] = set()
        queue = [coord]
        while queue:
            c = queue.pop()
            if c in visited:
                continue
            t = grid.get(c)
            if t is None or _terrain_group(t.terrain) != group:
                continue
            visited.add(c)
            component.add(c)
            for nb in c.neighbors():
                if nb not in visited:
                    queue.append(nb)

        # Depth BFS from edge inward
        depth: dict[HexCoord, int] = {}
        edge_queue: list[HexCoord] = []
        for c in component:
            for nb in c.neighbors():
                if nb not in component:
                    depth[c] = 0
                    edge_queue.append(c)
                    break
        if not edge_queue:
            for c in component:
                depth[c] = 0
            edge_queue = list(component)

        idx = 0
        while idx < len(edge_queue):
            c = edge_queue[idx]
            idx += 1
            for nb in c.neighbors():
                if nb in component and nb not in depth:
                    depth[nb] = depth[c] + 1
                    edge_queue.append(nb)

        clusters.append((group, component, depth))

    return clusters


# ── Deterministic seed ───────────────────────────────────────────

def _tile_seed(coord: HexCoord) -> int:
    q = coord.q & 0xFFFFFFFF
    r = coord.r & 0xFFFFFFFF
    seed = 137
    seed ^= q + 0x9E3779B9 + ((seed << 6) & 0xFFFFFFFF) + ((seed >> 2) & 0x3FFFFFFF)
    seed &= 0xFFFFFFFF
    seed ^= r + 0x9E3779B9 + ((seed << 6) & 0xFFFFFFFF) + ((seed >> 2) & 0x3FFFFFFF)
    return seed & 0xFFFFFFFF


# ── Public API ───────────────────────────────────────────────────

def build_overlays(
    grid: HexGrid, hex_size: int, seed: int = 0,
) -> tuple[list[OverlayItem], dict[HexCoord, tuple[int, int]]]:
    """Analyse terrain clusters; return overlay items and mountain depth map."""
    clusters = _find_terrain_clusters(grid)
    items: list[tuple[float, OverlayItem]] = []
    mountain_depths: dict[HexCoord, tuple[int, int]] = {}

    for group, tiles, depth_map in clusters:
        if group == Terrain.MOUNTAIN.name:
            items.extend(
                _gen_mountain_cluster(tiles, depth_map, hex_size, mountain_depths),
            )
            continue

        for coord in tiles:
            rng = _random.Random(_tile_seed(coord))
            d = depth_map.get(coord, 0)
            wx, wy = hex_to_pixel(coord, hex_size)
            terrain = grid[coord].terrain

            if group == "forest":
                items.extend(_gen_forest_tile(wx, wy, hex_size, d, terrain, rng))
            elif terrain == Terrain.STONE_DEPOSIT:
                items.extend(_gen_stone_tile(wx, wy, hex_size, d, rng))
            elif terrain == Terrain.WATER:
                items.extend(_gen_water_tile(wx, wy, hex_size, d, rng))
            elif terrain == Terrain.FIBER_PATCH:
                items.extend(_gen_fiber_tile(wx, wy, hex_size, d, rng))
            elif terrain == Terrain.GRASS:
                items.extend(_gen_grass_tile(wx, wy, hex_size, rng))
            elif terrain in (Terrain.IRON_VEIN, Terrain.COPPER_VEIN):
                tile = grid[coord]
                items.extend(_gen_ore_tile(wx, wy, hex_size, terrain, tile, rng))

    items.sort(key=lambda pair: pair[0])
    sorted_items = [item for _, item in items]

    # ── Ruins: rare remnants of old human civilization ─────────
    sorted_items.extend(_gen_ruins(grid, hex_size, seed))

    return sorted_items, mountain_depths


# ── Forest ───────────────────────────────────────────────────────

def _make_canopy_tree(
    wx: float, wy: float, s: int, is_dense: bool, rng: _random.Random,
) -> tuple[float, OverlayItem]:
    ox = rng.uniform(-s * 0.3, s * 0.3)
    oy = rng.uniform(-s * 0.3, s * 0.3)
    cr = s * rng.uniform(0.7, 1.2) * (1.2 if is_dense else 1.0)
    return (wy + oy, OverlayTree(
        wx=wx + ox, wy=wy + oy,
        trunk_h=s * rng.uniform(0.4, 0.7),
        crown_rx=cr, crown_ry=cr * rng.uniform(0.7, 0.9),
        crown_color=rng.choice(
            [(18, 68, 22), (22, 78, 28), (14, 58, 18)]
            if is_dense else [(32, 95, 34), (42, 115, 42), (28, 85, 28)]
        ),
        trunk_color=rng.choice([(80, 55, 30), (70, 48, 25), (90, 62, 35)]),
        highlight_color=rng.choice([(38, 98, 38), (28, 85, 28)]),
        style="canopy",
    ))


def _gen_forest_tile(
    wx: float, wy: float, s: int, depth: int, terrain: Terrain, rng: _random.Random,
) -> list[tuple[float, OverlayItem]]:
    is_dense = terrain == Terrain.DENSE_FOREST
    items: list[tuple[float, OverlayItem]] = []

    if depth >= 4:
        # Deep interior: one large canopy tree (skip ~40% of dense-forest tiles)
        if is_dense and rng.random() < 0.4:
            pass  # skip for density reduction
        else:
            items.append(_make_canopy_tree(wx, wy, s, is_dense, rng))
    elif depth >= 2:
        n = rng.randint(1, 2) if is_dense else rng.randint(1, 1)
        for _ in range(n):
            ox = rng.uniform(-s * 0.4, s * 0.4)
            oy = rng.uniform(-s * 0.35, s * 0.35)
            cr = s * rng.uniform(0.32, 0.55) * (1.1 if is_dense else 1.0)
            items.append((wy + oy, OverlayTree(
                wx=wx + ox, wy=wy + oy,
                trunk_h=s * rng.uniform(0.2, 0.4),
                crown_rx=cr, crown_ry=cr * rng.uniform(0.85, 1.0),
                crown_color=rng.choice(
                    [(22, 72, 26), (30, 88, 34), (18, 64, 20)]
                    if is_dense else [(38, 105, 40), (48, 125, 48), (32, 95, 32)]
                ),
                trunk_color=(85, 58, 32),
                highlight_color=rng.choice([(48, 118, 48), (38, 100, 38)]),
                style="conifer",
            )))
    else:
        # Edge tiles: sparse small trees + grass tufts for natural blending
        if rng.random() < 0.6:  # only ~60% of edge tiles get a tree
            ox = rng.uniform(-s * 0.42, s * 0.42)
            oy = rng.uniform(-s * 0.38, s * 0.38)
            cr = s * rng.uniform(0.12, 0.24) * (1.1 if is_dense else 1.0)
            items.append((wy + oy, OverlayTree(
                wx=wx + ox, wy=wy + oy,
                trunk_h=s * rng.uniform(0.06, 0.16),
                crown_rx=cr, crown_ry=cr,
                crown_color=rng.choice(
                    [(28, 85, 30), (38, 108, 40)]
                    if is_dense else [(42, 118, 44), (52, 138, 52)]
                ),
                trunk_color=(85, 58, 32),
                highlight_color=rng.choice([(52, 132, 52), (42, 112, 42)]),
                style="round",
            )))
        # Blend grass tufts on forest edges
        for _ in range(rng.randint(1, 3)):
            ox = rng.uniform(-s * 0.45, s * 0.45)
            oy = rng.uniform(-s * 0.4, s * 0.4)
            items.append((wy + oy, OverlayGrassTuft(
                wx=wx + ox, wy=wy + oy,
                h=rng.uniform(2, 4),
                color=rng.choice([(75, 140, 55), (65, 125, 48), (85, 150, 62)]),
            )))
    return items


# ── Mountains (top-down depth colouring) ─────────────────────────

def _gen_mountain_cluster(
    tiles: set[HexCoord],
    depth_map: dict[HexCoord, int],
    hex_size: int,
    mountain_depths: dict[HexCoord, tuple[int, int]],
) -> list[tuple[float, OverlayItem]]:
    """Populate mountain depth map and place small edge-rock details."""
    items: list[tuple[float, OverlayItem]] = []
    s = hex_size

    if not tiles:
        return items

    max_depth = max(depth_map.values()) if depth_map else 0

    # Export per-tile (depth, max_depth) for depth-based tile colouring
    for coord in tiles:
        mountain_depths[coord] = (depth_map.get(coord, 0), max_depth)

    # Small rocks on foothill (edge) tiles for detail
    for coord in tiles:
        d = depth_map.get(coord, 0)
        if d > 2:
            continue
        tile_rng = _random.Random(_tile_seed(coord))
        wx, wy = hex_to_pixel(coord, s)
        n_rocks = tile_rng.randint(1, 3) if d <= 1 else tile_rng.randint(0, 2)
        for _ in range(n_rocks):
            ox = tile_rng.uniform(-s * 0.35, s * 0.35)
            oy = tile_rng.uniform(-s * 0.3, s * 0.3)
            rw = s * tile_rng.uniform(0.1, 0.22)
            rh = s * tile_rng.uniform(0.08, 0.18)
            items.append((wy + oy, OverlayRock(
                wx=wx + ox, wy=wy + oy,
                w=rw, h=rh,
                color=tile_rng.choice([(100, 90, 80), (90, 82, 72), (110, 100, 90)]),
                highlight_color=(130, 125, 118),
            )))

    return items


# ── Stone deposits ───────────────────────────────────────────────

def _gen_stone_tile(
    wx: float, wy: float, s: int, depth: int, rng: _random.Random,
) -> list[tuple[float, OverlayItem]]:
    items: list[tuple[float, OverlayItem]] = []
    n = rng.randint(2, 4) if depth >= 2 else rng.randint(1, 3)
    for _ in range(n):
        ox = rng.uniform(-s * 0.42, s * 0.42)
        oy = rng.uniform(-s * 0.35, s * 0.35)
        w = s * rng.uniform(0.12, 0.28) * (1.0 + depth * 0.15)
        h = w * rng.uniform(0.6, 1.0)
        items.append((wy + oy, OverlayRock(
            wx=wx + ox, wy=wy + oy, w=w, h=h,
            color=rng.choice([(155, 155, 145), (135, 135, 125), (165, 162, 155)]),
            highlight_color=rng.choice([(180, 180, 172), (170, 170, 162)]),
        )))
    return items


# ── Water ────────────────────────────────────────────────────────

def _gen_water_tile(
    wx: float, wy: float, s: int, depth: int, rng: _random.Random,
) -> list[tuple[float, OverlayItem]]:
    items: list[tuple[float, OverlayItem]] = []
    # More ripples in deeper water
    n = rng.randint(3, 5) if depth >= 2 else rng.randint(1, 3)
    for _ in range(n):
        ox = rng.uniform(-s * 0.4, s * 0.4)
        oy = rng.uniform(-s * 0.3, s * 0.3)
        w = rng.uniform(3, 8) if depth < 2 else rng.uniform(5, 12)
        items.append((wy + oy, OverlayRipple(
            wx=wx + ox, wy=wy + oy,
            w=w, phase_offset=rng.uniform(0, 6.28),
        )))
    return items


# ── Fiber patches ────────────────────────────────────────────────

def _gen_fiber_tile(
    wx: float, wy: float, s: int, depth: int, rng: _random.Random,
) -> list[tuple[float, OverlayItem]]:
    items: list[tuple[float, OverlayItem]] = []
    n = rng.randint(4, 7) if depth >= 1 else rng.randint(3, 5)
    for _ in range(n):
        ox = rng.uniform(-s * 0.44, s * 0.44)
        oy = rng.uniform(-s * 0.38, s * 0.38)
        r = s * rng.uniform(0.14, 0.26) * (1.0 + depth * 0.15)
        berry: tuple[int, int, int] | None = None
        if rng.random() > 0.2:
            berry = rng.choice([(200, 60, 60), (180, 50, 120), (220, 180, 40)])
        items.append((wy + oy, OverlayBush(
            wx=wx + ox, wy=wy + oy, radius=r,
            color=rng.choice([(85, 140, 42), (110, 160, 55), (70, 130, 38)]),
            berry_color=berry,
        )))
    return items


# ── Grass ────────────────────────────────────────────────────────

def _gen_grass_tile(
    wx: float, wy: float, s: int, rng: _random.Random,
) -> list[tuple[float, OverlayItem]]:
    items: list[tuple[float, OverlayItem]] = []
    for _ in range(rng.randint(3, 7)):
        ox = rng.uniform(-s * 0.48, s * 0.48)
        oy = rng.uniform(-s * 0.4, s * 0.4)
        items.append((wy + oy, OverlayGrassTuft(
            wx=wx + ox, wy=wy + oy,
            h=rng.uniform(2, 5),
            color=rng.choice([(90, 160, 70), (70, 130, 50), (100, 175, 85)]),
        )))
    return items


# ── Ore veins (crystals on existing terrain) ─────────────────────

_IRON_CRYSTAL_COLORS = [(160, 100, 70), (140, 85, 60), (180, 115, 80)]
_IRON_HIGHLIGHT = [(200, 150, 120), (190, 140, 110)]
_COPPER_CRYSTAL_COLORS = [(70, 160, 110), (55, 140, 95), (80, 175, 120)]
_COPPER_HIGHLIGHT = [(120, 210, 160), (110, 200, 150)]

_MATH_PI = 3.14159265


def _gen_ore_tile(
    wx: float, wy: float, s: int, terrain: Terrain, tile: HexTile,
    rng: _random.Random,
) -> list[tuple[float, OverlayItem]]:
    """Generate crystal overlays for ore veins on top of underlying terrain overlays."""
    items: list[tuple[float, OverlayItem]] = []

    # First, generate the underlying terrain's overlays so the ground looks normal
    underlying = tile.underlying_terrain
    if underlying == Terrain.GRASS:
        items.extend(_gen_grass_tile(wx, wy, s, rng))
    elif underlying in (Terrain.FOREST, Terrain.DENSE_FOREST):
        # A few sparse grass tufts instead of full trees — ore cleared the canopy
        for _ in range(rng.randint(1, 3)):
            ox = rng.uniform(-s * 0.45, s * 0.45)
            oy = rng.uniform(-s * 0.4, s * 0.4)
            items.append((wy + oy, OverlayGrassTuft(
                wx=wx + ox, wy=wy + oy,
                h=rng.uniform(2, 4),
                color=rng.choice([(75, 140, 55), (65, 125, 48)]),
            )))
    elif underlying == Terrain.FIBER_PATCH:
        items.extend(_gen_fiber_tile(wx, wy, s, 0, rng))

    # Now place ore crystals on top
    is_iron = terrain == Terrain.IRON_VEIN
    colors = _IRON_CRYSTAL_COLORS if is_iron else _COPPER_CRYSTAL_COLORS
    highlights = _IRON_HIGHLIGHT if is_iron else _COPPER_HIGHLIGHT

    n_crystals = rng.randint(2, 5)
    for _ in range(n_crystals):
        ox = rng.uniform(-s * 0.35, s * 0.35)
        oy = rng.uniform(-s * 0.3, s * 0.3)
        h = s * rng.uniform(0.2, 0.5)
        w = s * rng.uniform(0.08, 0.18)
        angle = rng.uniform(-_MATH_PI / 6, _MATH_PI / 6)
        items.append((wy + oy, OverlayCrystal(
            wx=wx + ox, wy=wy + oy,
            h=h, w=w,
            color=rng.choice(colors),
            highlight_color=rng.choice(highlights),
            angle=angle,
        )))
    return items


# ── Ruins (rare old human society remnants) ──────────────────────

_RUIN_COLORS = [
    ((120, 110, 95), (160, 150, 130)),   # sandstone
    ((90, 85, 80), (130, 125, 115)),     # grey stone
    ((100, 90, 75), (145, 135, 115)),    # weathered brick
]

def _gen_ruins(
    grid: HexGrid, hex_size: int, seed: int = 0,
) -> list[OverlayRuin]:
    """Scatter 1-3 ruin *clusters* of 5-8 pieces each across the map.

    Cluster count scales with map size: a larger radius increases the
    upper bound.  Cluster pieces are placed on adjacent passable tiles
    via a small BFS so ruins feel like a single site rather than an
    even scatter.
    """
    from compprog_pygame.games.hex_colony import params
    from compprog_pygame.games.hex_colony.procgen import UNBUILDABLE

    origin = HexCoord(0, 0)
    # Map radius as a proxy for scale.
    map_radius = max(
        (abs(t.coord.q) + abs(t.coord.r) + abs(t.coord.q + t.coord.r)) // 2
        for t in grid.tiles()
    )

    # Tiles eligible to *host* ruins (cluster pieces).
    eligible_coords: set[HexCoord] = {
        tile.coord for tile in grid.tiles()
        if tile.terrain not in UNBUILDABLE
    }
    # Valid cluster centres must also be far from camp.
    centre_candidates = [
        c for c in eligible_coords
        if c.distance(origin) >= params.RUINS_MIN_DISTANCE
    ]
    if not centre_candidates:
        return []

    rng = _random.Random((seed or 0) ^ 0xA17C1E5)

    # Base cluster count plus optional extras for larger maps.
    base = rng.randint(params.RUINS_CLUSTERS_MIN, params.RUINS_CLUSTERS_MAX)
    extras = max(0, map_radius // max(1, params.RUINS_EXTRA_CLUSTER_RADIUS))
    target_clusters = base + extras

    # Pick well-separated cluster centres.
    rng.shuffle(centre_candidates)
    centres: list[HexCoord] = []
    for cand in centre_candidates:
        if len(centres) >= target_clusters:
            break
        if all(
            cand.distance(c) >= params.RUINS_CLUSTER_SEPARATION
            for c in centres
        ):
            centres.append(cand)

    ruins: list[OverlayRuin] = []
    used: set[HexCoord] = set()

    for centre in centres:
        # Gather candidate tiles within the cluster radius via BFS.
        frontier: list[HexCoord] = [centre]
        ring: list[HexCoord] = []
        visited: set[HexCoord] = {centre}
        while frontier:
            nxt: list[HexCoord] = []
            for coord in frontier:
                if (
                    coord in eligible_coords
                    and coord not in used
                ):
                    ring.append(coord)
                for nb in coord.neighbors():
                    if nb in visited:
                        continue
                    visited.add(nb)
                    if nb.distance(centre) <= params.RUINS_CLUSTER_RADIUS:
                        nxt.append(nb)
            frontier = nxt

        if not ring:
            continue

        rng.shuffle(ring)
        target = rng.randint(
            params.RUINS_PIECES_MIN, params.RUINS_PIECES_MAX,
        )
        pieces = ring[:target]

        for coord in pieces:
            used.add(coord)
            wx, wy = hex_to_pixel(coord, hex_size)
            variant = rng.randint(0, 2)
            color, highlight = rng.choice(_RUIN_COLORS)
            ruins.append(OverlayRuin(
                wx=wx, wy=wy,
                variant=variant,
                color=color, highlight_color=highlight,
                coord=(coord.q, coord.r),
            ))

    return ruins
