# Offline ML Performance Autotuning

This document explains the offline machine-learning system that picks
performance knobs for `hex_colony` based on the current world state.
There is **no ML library at runtime** — all the “learning” happens
offline in a sweep + train pipeline, and the result is a static
lookup table baked into source.

---

## 1. Why offline-only?

Hex Colony ships as a deterministic, single-binary PyInstaller exe.
We can’t pull in `sklearn`/`torch` for one feature, and we don’t want
non-determinism creeping into world simulation. So instead of training
a live model, we:

1. **Sweep** every interesting (scenario × knob combo) cell offline.
2. **Train** picks the best combo per scenario from CSV.
3. **Bake** the chosen combos as a Python `dict` literal in
   [`perf_autotune.py`](../src/compprog_pygame/games/hex_colony/perf_autotune.py).
4. At runtime, the game **classifies** the live world into one of
   those scenarios and `dict.get`s the right knobs every 2 seconds.

The runtime cost is one dict lookup per 2 s — effectively zero. The
“intelligence” is entirely in the offline trainer.

---

## 2. The three components

| File | Role |
|---|---|
| [`src/compprog_pygame/games/hex_colony/perf_autotune.py`](../src/compprog_pygame/games/hex_colony/perf_autotune.py) | Runtime: knob registry, world classifier, profile lookup, applier |
| [`tools/perf_sweep.py`](../tools/perf_sweep.py) | Offline: headlessly times every (scenario × combo) cell, streams to CSV |
| [`tools/perf_train.py`](../tools/perf_train.py) | Offline: reads CSV, picks best combo per scenario, rewrites `AUTOTUNE_PROFILES` block |

---

## 3. How to use it

### Quick workflow (a few minutes)

```powershell
$env:PYTHONPATH = "src"
python tools/perf_sweep.py --quick --frames 30 --out perf_sweep_quick.csv
python tools/perf_train.py --in perf_sweep_quick.csv --budget-ms 50
git diff src/compprog_pygame/games/hex_colony/perf_autotune.py
```

That overwrites the `AUTOTUNE_PROFILES` block in `perf_autotune.py`
with freshly chosen knob values, then you commit the file.

### Full sweep (slower, more accurate)

```powershell
python tools/perf_sweep.py --frames 60 --out perf_sweep_full.csv
python tools/perf_train.py --in perf_sweep_full.csv --budget-ms 16
```

### Flags

`perf_sweep.py`:

* `--quick` – use the small `QUICK_KNOB_GRID` (8 combos) instead of
  the full 80-combo grid.
* `--frames N` – timed frames per cell (warmup is fixed at 5).
* `--out PATH` – CSV destination (default `perf_sweep.csv`).
* `--seed N` – world seed (default 42 for repeatability).

`perf_train.py`:

* `--in PATH` – sweep CSV input.
* `--budget-ms F` – p95 frame-time budget. Combos under budget are
  preferred (lowest fidelity cost wins); if no combo meets it, the
  fastest combo is chosen as a fallback.

---

## 4. How it works internally

### 4.1 Knob registry (`KNOBS`)

Each tunable parameter is declared with a `Knob` dataclass:

```python
Knob(
    name="ENEMY_RETARGET_BUDGET_PER_TICK",
    getter=lambda: params.ENEMY_RETARGET_BUDGET_PER_TICK,
    setter=lambda v: setattr(params, "ENEMY_RETARGET_BUDGET_PER_TICK", int(v)),
    min_v=4, max_v=60, default=20,
    fidelity_cost=_retarget_fidelity,
)
```

* `getter`/`setter` mutate `params.py` at runtime (live reconfig).
* `fidelity_cost` is a unit-less function `f(value) → [0, ~1]` where
  **0 = full fidelity**, **1 = noticeably degraded gameplay**.
  The trainer prefers low-fidelity-cost combos under the time budget.

Currently three knobs are registered:

| Knob | Effect | Range |
|---|---|---|
| `ENEMY_RETARGET_BUDGET_PER_TICK` | Max enemies that recompute their A* path per tick | 4–60 |
| `ENEMY_PATHFIND_MAX_DEPTH` | Max nodes A* expands before giving up | 400–3000 |
| `UNREACHABLE_RECHECK_INTERVAL` | Seconds between retries when an enemy can’t find a target | 0.25–2.5 |

### 4.2 World classifier (`classify_world`)

Buckets the live world into a discrete scenario key:

```
size   ∈ {small, medium, large, huge}      based on building count (≤50, ≤150, ≤350, ∞)
threat ∈ {calm, active, swarm}             based on live enemy count (≤5, ≤40, ∞)
key    = f"{size}_{threat}"                e.g. "large_swarm"
```

This is a pure function of world state — same world ⇒ same key.

### 4.3 Profile applier (`apply_profile`, `maybe_retune`)

`World.update` calls `perf_autotune.maybe_retune(self, dt)` once per
frame. Internally:

* It re-classifies and re-applies at most every 2 s
  (`_RETUNE_PERIOD`).
* If the scenario key changed since last call, it
  `apply_profile(KEY)` — which calls each knob’s setter to overwrite
  the value in `params.py` live.
* If no profile exists for that key it falls back to `DEFAULT_PROFILE`.

### 4.4 Sweep (`tools/perf_sweep.py`)

For each scenario in `SCENARIOS`:

1. Constructs a fresh seeded `World`.
2. Spawns the right number of dummy buildings + enemies for that
   scenario.
3. For each knob combo in `KNOB_GRID` (or `QUICK_KNOB_GRID`):
   * Applies the combo.
   * Runs 5 warmup frames + N timed frames at `dt=0.05`.
   * Records `mean_ms` and `p95_ms` for `World.update`.
4. Streams a row to CSV (with `flush()` after every row, so
   killing the process mid-sweep doesn’t lose all data).

It runs entirely headless via `SDL_VIDEODRIVER=dummy` /
`SDL_AUDIODRIVER=dummy`.

### 4.5 Trainer (`tools/perf_train.py`)

For each scenario (group of CSV rows):

1. **Filter** rows whose `p95_ms ≤ budget_ms`.
2. If any are feasible, **pick the one with the lowest
   `fidelity_cost`** (tie-broken by lowest p95).
3. If none meet the budget, **pick the absolute lowest p95**
   (best-effort fallback).

Then it formats the chosen combos as a Python dict literal and
**replaces the block between**

```
# --- BEGIN GENERATED BLOCK (perf_train.py) ---
# --- END GENERATED BLOCK (perf_train.py) ---
```

inside `perf_autotune.py`. Nothing else in that file is touched, so
the registry, classifier, and applier are safe from the rewriter.

This is the “learning” step: it’s a constrained discrete optimization
over a grid (`min fidelity_cost s.t. p95 ≤ budget`). Conceptually it’s
the same shape as a small policy table you’d learn with reinforcement
learning, but here it’s explicit and reproducible.

---

## 5. Determinism guarantees

* Classification is a pure function of world state — never of
  wall-clock perf. So replays and saves stay deterministic.
* Sweeps use fixed seeds (`--seed 42`), so re-running the trainer
  on the same CSV yields the same `AUTOTUNE_PROFILES`.
* The applier never calls `random` or reads timing data; it just
  copies a dict into `params`.

---

## 6. Adding a new knob

1. Add a `Knob(...)` entry to `KNOBS` in `perf_autotune.py`. Define
   its `fidelity_cost` near the top of the file.
2. Add the knob name to `KNOB_GRID` (and `QUICK_KNOB_GRID`) in
   `tools/perf_sweep.py` with a small set of candidate values.
3. Re-run the sweep + trainer. The CSV header changes automatically
   because it derives column names from `KNOB_GRID.keys()`.

## 7. Adding a new scenario

1. Add it to `SCENARIOS` in `tools/perf_sweep.py` with the right
   `n_buildings`, `n_enemies`, and `terrain_seed` bias.
2. Update `classify_world` in `perf_autotune.py` so the live world
   can actually map onto your new key (otherwise the trainer learns a
   profile no live world will ever look up).
3. Re-run sweep + trainer.

---

## 8. Caveats

* The CSV row reader skips empty/numeric scenario fields, so a
  partially-written sweep file (interrupted run) won’t poison the
  trained table — the bad rows just get ignored.
* p95 frame times in the sweep CSV look very large (hundreds of ms)
  for `*_active` and `*_swarm` scenarios. That’s because the sweep
  runs `World.update` in a tight loop with `dt=0.05`, which compresses
  several real seconds of simulation into 30 frames. The relative
  ordering of combos is what matters — not the absolute numbers.
* If you change the knob list or scenario list, **re-run the sweep**.
  The trainer only fixes the profile dict; it cannot infer values for
  knobs it’s never seen.
