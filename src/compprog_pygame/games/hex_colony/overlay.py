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

from compprog_pygame.games.hex_colony.hex_grid import HexCoord, HexGrid, Terrain, hex_to_pixel

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

OverlayItem = (
    OverlayTree | OverlayRock
    | OverlayBush | OverlayGrassTuft | OverlayRipple
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
    grid: HexGrid, hex_size: int,
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

    items.sort(key=lambda pair: pair[0])
    return [item for _, item in items], mountain_depths


# ── Forest ───────────────────────────────────────────────────────

def _gen_forest_tile(
    wx: float, wy: float, s: int, depth: int, terrain: Terrain, rng: _random.Random,
) -> list[tuple[float, OverlayItem]]:
    is_dense = terrain == Terrain.DENSE_FOREST
    items: list[tuple[float, OverlayItem]] = []

    if depth >= 4:
        for _ in range(rng.randint(1, 2)):
            ox = rng.uniform(-s * 0.3, s * 0.3)
            oy = rng.uniform(-s * 0.3, s * 0.3)
            cr = s * rng.uniform(0.7, 1.2) * (1.2 if is_dense else 1.0)
            items.append((wy + oy, OverlayTree(
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
            )))
    elif depth >= 2:
        n = rng.randint(2, 3) if is_dense else rng.randint(1, 2)
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
        for _ in range(rng.randint(1, 2)):
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
    n = rng.randint(2, 4) if depth >= 1 else rng.randint(1, 3)
    for _ in range(n):
        ox = rng.uniform(-s * 0.42, s * 0.42)
        oy = rng.uniform(-s * 0.35, s * 0.35)
        r = s * rng.uniform(0.08, 0.18) * (1.0 + depth * 0.12)
        berry: tuple[int, int, int] | None = None
        if rng.random() > 0.3:
            berry = rng.choice([(200, 60, 60), (180, 50, 120), (220, 180, 40)])
        items.append((wy + oy, OverlayBush(
            wx=wx + ox, wy=wy + oy, radius=r,
            color=rng.choice([(100, 150, 50), (130, 170, 65)]),
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
