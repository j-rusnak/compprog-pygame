"""Headless performance sweep — generates training data for perf_train.py.

Drives :class:`World` in a tight loop with no renderer, sweeping a grid
of knob settings across a handful of canned scenarios.  Each row of the
output CSV captures:

    scenario, n_buildings, n_enemies, knob_*, mean_ms, p95_ms

Run from the repo root:

    $env:PYTHONPATH = "src"
    python tools/perf_sweep.py --out perf_sweep.csv

Optional flags:
    --frames N      simulated frames per (scenario, knob-combo) cell.
    --quick         run a small grid (~30 cells) instead of full sweep.

The script avoids importing pygame (which would require a display).
``World.update`` is the only thing being timed.
"""

from __future__ import annotations

import argparse
import csv
import itertools
import os
import sys
import time
from pathlib import Path

# Allow running as a script from the repo root.
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

# pygame-ce needs an SDL video driver even when no window is opened
# (font/image modules call SDL_Init).  Use the dummy driver so the
# sweep runs in CI / SSH sessions.
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
# Disable the perf-monitor JSONL writer — we have our own timing here.
os.environ["HEX_COLONY_PERF"] = "0"

import pygame  # noqa: E402  (after env vars)
pygame.init()

from compprog_pygame.games.hex_colony import params, perf_autotune  # noqa: E402
from compprog_pygame.games.hex_colony.buildings import BuildingType  # noqa: E402
from compprog_pygame.games.hex_colony.combat import Enemy  # noqa: E402
from compprog_pygame.games.hex_colony.hex_grid import HexCoord, hex_to_pixel  # noqa: E402
from compprog_pygame.games.hex_colony.settings import (  # noqa: E402
    Difficulty, HexColonySettings,
)
from compprog_pygame.games.hex_colony.world import World  # noqa: E402


# ── Scenario builders ─────────────────────────────────────────────


def _new_world(seed: str, world_radius: int) -> World:
    s = HexColonySettings(world_radius=world_radius,
                          difficulty=Difficulty.HARD)
    return World.generate(s, seed=seed)


def _spawn_filler_buildings(world: World, n: int) -> int:
    """Place up to ``n`` cheap buildings on grass tiles around camp.

    Returns how many it actually placed (the map has finite room).
    """
    placed = 0
    camp = world.player_colony.camp_coord
    radius = 1
    while placed < n and radius < 60:
        for dq in range(-radius, radius + 1):
            for dr in range(-radius, radius + 1):
                if abs(dq + dr) > radius:
                    continue
                if max(abs(dq), abs(dr), abs(dq + dr)) != radius:
                    continue
                c = HexCoord(camp.q + dq, camp.r + dr)
                tile = world.grid.get(c)
                if tile is None or tile.building is not None:
                    continue
                if tile.terrain.name in ("WATER", "MOUNTAIN", "WASTELAND"):
                    continue
                # Alternate between two cheap building types.
                btype = (BuildingType.HABITAT if placed % 2 == 0
                         else BuildingType.STORAGE)
                b = world.buildings.place(btype, c)
                tile.building = b
                placed += 1
                if placed >= n:
                    return placed
        radius += 1
    return placed


def _spawn_enemies(world: World, n: int) -> None:
    """Spawn ``n`` SCOUTs at the map edge so they have to traverse."""
    if n <= 0:
        return
    edge = world.combat._pick_edge_spawn_point(world)
    size = world.settings.hex_size
    type_data = params.ENEMY_TYPE_DATA["SCOUT"]
    for _ in range(n):
        e = Enemy(
            type_name="SCOUT",
            coord=edge,
            health=float(type_data["hp"]),
            max_health=float(type_data["hp"]),
            damage=float(type_data["damage"]),
            bounty=int(type_data.get("bounty", 0)),
        )
        e.attack_timer = float(type_data["attack_cd"])
        e.move_timer = float(type_data["move_period"])
        wx, wy = hex_to_pixel(edge, size)
        e.px, e.py = wx, wy
        e.next_target_px, e.next_target_py = wx, wy
        world.combat.enemies.append(e)


SCENARIOS: list[dict] = [
    {"name": "small_calm",    "buildings":  20, "enemies":   0},
    {"name": "small_active",  "buildings":  20, "enemies":  20},
    {"name": "medium_calm",   "buildings": 100, "enemies":   0},
    {"name": "medium_active", "buildings": 100, "enemies":  30},
    {"name": "medium_swarm",  "buildings": 100, "enemies":  80},
    {"name": "large_calm",    "buildings": 250, "enemies":   0},
    {"name": "large_active",  "buildings": 250, "enemies":  40},
    {"name": "large_swarm",   "buildings": 250, "enemies": 120},
    {"name": "huge_calm",     "buildings": 500, "enemies":   0},
    {"name": "huge_active",   "buildings": 500, "enemies":  60},
    {"name": "huge_swarm",    "buildings": 500, "enemies": 200},
]

# Subset used by ``--quick`` — drops the huge tier (which dominates
# sweep wall-clock time) so a full quick sweep finishes in seconds.
QUICK_SCENARIOS: list[dict] = [
    s for s in SCENARIOS if not s["name"].startswith("huge_")
]


# ── Knob grid ─────────────────────────────────────────────────────


KNOB_GRID = {
    "ENEMY_RETARGET_BUDGET_PER_TICK": [6, 12, 20, 30, 45],
    "ENEMY_PATHFIND_MAX_DEPTH":       [600, 1000, 1500, 2200],
    "UNREACHABLE_RECHECK_INTERVAL":   [0.5, 1.0, 1.5, 2.0],
}

QUICK_KNOB_GRID = {
    "ENEMY_RETARGET_BUDGET_PER_TICK": [10, 25],
    "ENEMY_PATHFIND_MAX_DEPTH":       [800, 1500],
    "UNREACHABLE_RECHECK_INTERVAL":   [0.5, 1.5],
}


def _knob_combos(grid: dict[str, list]) -> list[dict[str, float]]:
    keys = list(grid)
    combos = []
    for vals in itertools.product(*(grid[k] for k in keys)):
        combos.append(dict(zip(keys, vals)))
    return combos


# ── Timing loop ───────────────────────────────────────────────────


def _time_world(world: World, frames: int, dt: float) -> tuple[float, float]:
    """Run ``world.update`` ``frames`` times; return (mean_ms, p95_ms)."""
    samples: list[float] = []
    # Warmup: 5 frames so any first-call lazy caches are built.
    for _ in range(5):
        world.update(dt)
    for _ in range(frames):
        t0 = time.perf_counter()
        world.update(dt)
        samples.append((time.perf_counter() - t0) * 1000.0)
    samples.sort()
    n = len(samples)
    mean = sum(samples) / n
    p95 = samples[min(n - 1, int(n * 0.95))]
    return mean, p95


# ── Main ──────────────────────────────────────────────────────────


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default="perf_sweep.csv",
                    help="Output CSV path.")
    ap.add_argument("--frames", type=int, default=120,
                    help="Frames timed per cell (default 120).")
    ap.add_argument("--seed", default="sweep-seed",
                    help="World seed (kept constant across cells).")
    ap.add_argument("--world-radius", type=int, default=60,
                    help="World radius for sweep (default 60).")
    ap.add_argument("--quick", action="store_true",
                    help="Use a small knob grid for a fast sanity sweep.")
    args = ap.parse_args()

    grid = QUICK_KNOB_GRID if args.quick else KNOB_GRID
    scenarios = QUICK_SCENARIOS if args.quick else SCENARIOS
    combos = _knob_combos(grid)

    out_path = Path(args.out)
    fieldnames = (
        ["scenario", "n_buildings", "n_enemies"]
        + list(grid.keys())
        + ["mean_ms", "p95_ms"]
    )
    n_cells = len(scenarios) * len(combos)
    cell = 0
    print(f"[sweep] {len(scenarios)} scenarios x {len(combos)} knob "
          f"combos = {n_cells} cells x {args.frames} frames",
          flush=True)
    with out_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        f.flush()
        for scenario in scenarios:
            world = _new_world(args.seed, args.world_radius)
            actual_b = _spawn_filler_buildings(world, scenario["buildings"])
            _spawn_enemies(world, scenario["enemies"])
            n_e = len(world.combat.enemies)
            for combo in combos:
                cell += 1
                # Apply knobs directly (bypass profiles for the sweep).
                for k, v in combo.items():
                    perf_autotune.KNOBS[k].setter(v)
                # Detach the autotuner so it doesn't fight us.
                world._autotune_state = {  # type: ignore[attr-defined]
                    "accum": -1e9, "key": "_sweep_locked", "applied": dict(combo)
                }
                mean_ms, p95_ms = _time_world(world, args.frames, dt=0.05)
                row = {
                    "scenario": scenario["name"],
                    "n_buildings": actual_b,
                    "n_enemies": n_e,
                    **combo,
                    "mean_ms": round(mean_ms, 3),
                    "p95_ms": round(p95_ms, 3),
                }
                writer.writerow(row)
                f.flush()
                print(f"[{cell}/{n_cells}] {scenario['name']:<14s} "
                      f"{combo} -> mean={mean_ms:5.2f}ms "
                      f"p95={p95_ms:5.2f}ms", flush=True)
    print(f"[sweep] wrote {out_path}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
