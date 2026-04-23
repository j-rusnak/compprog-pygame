"""Offline-trained performance auto-tuner.

This module is the runtime side of the offline ML perf system.  It does
**no** machine learning at runtime — it just looks up a pre-baked
profile based on the current world's complexity and applies it.

How it works
------------
1.  ``classify_world(world)`` extracts a handful of cheap features
    (building / enemy / network counts) and maps them to a *profile
    key* (e.g. ``"medium_mid"``).
2.  ``apply_profile(world, key)`` writes the profile's knob values
    into the matching attributes of :mod:`params` (and any per-world
    runtime overrides).
3.  :func:`maybe_retune` is called from :meth:`World.update` at a
    low cadence (default 2 s) so the running game smoothly slides
    between profiles as the colony grows.

The actual numbers in ``AUTOTUNE_PROFILES`` are emitted by
``tools/perf_train.py`` after a sweep produced by
``tools/perf_sweep.py``.  See ``docs/PERF_AUTOTUNE.md`` for the full
workflow.

Determinism
-----------
Profile selection is a pure function of the world state (counts of
in-game objects), so two runs of the same seed produce identical
profile transitions.  Wall-clock perf has no influence at runtime.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable

from compprog_pygame.games.hex_colony import params

if TYPE_CHECKING:
    from compprog_pygame.games.hex_colony.world import World


# ── Knob registry ──────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class Knob:
    """A tunable parameter the autotuner is allowed to adjust.

    ``getter`` / ``setter`` decouple the knob from where the value
    physically lives — most knobs live in :mod:`params` but a few
    (like :attr:`World._unreachable_recheck_interval`) are per-world
    runtime state.

    ``min_value`` / ``max_value`` clamp the controller so a bad
    profile cannot push gameplay into nonsense regions (e.g. a
    pathfind depth of 0).

    ``fidelity_cost(value)`` returns a unitless penalty (higher = more
    visibly degraded).  The offline trainer picks the lowest-cost knob
    setting that still meets the frame-time budget.
    """

    name: str
    getter: Callable[[], float]
    setter: Callable[[float], None]
    min_value: float
    max_value: float
    default: float
    fidelity_cost: Callable[[float], float]


def _params_getter(name: str) -> Callable[[], float]:
    return lambda: float(getattr(params, name))


def _params_setter(name: str) -> Callable[[float], None]:
    def _set(v: float) -> None:
        setattr(params, name, type(getattr(params, name))(v))
    return _set


# Higher pathfind depth = more accurate enemy routing across the map.
# Below ~600 nodes long-range routing starts failing on big maps.
def _pathfind_fidelity(v: float) -> float:
    return max(0.0, (1500.0 - v) / 1500.0) ** 2


# Higher retarget budget = more enemies can re-evaluate their target
# each tick.  Below ~5 the AI feels sluggish during big waves.
def _retarget_fidelity(v: float) -> float:
    return max(0.0, (40.0 - v) / 40.0) ** 2


# Longer unreachable recheck = stale "starved" overlays for longer.
# 0.5 s is the historical default; up to ~2 s is invisible to humans.
def _unreachable_fidelity(v: float) -> float:
    return max(0.0, (v - 0.5) / 2.0) ** 2


def _get_unreachable_interval() -> float:
    return float(getattr(params, "UNREACHABLE_RECHECK_INTERVAL", 0.5))


def _set_unreachable_interval(v: float) -> None:
    setattr(params, "UNREACHABLE_RECHECK_INTERVAL", float(v))


KNOBS: dict[str, Knob] = {
    "ENEMY_RETARGET_BUDGET_PER_TICK": Knob(
        name="ENEMY_RETARGET_BUDGET_PER_TICK",
        getter=_params_getter("ENEMY_RETARGET_BUDGET_PER_TICK"),
        setter=_params_setter("ENEMY_RETARGET_BUDGET_PER_TICK"),
        min_value=4, max_value=60, default=20,
        fidelity_cost=_retarget_fidelity,
    ),
    "ENEMY_PATHFIND_MAX_DEPTH": Knob(
        name="ENEMY_PATHFIND_MAX_DEPTH",
        getter=_params_getter("ENEMY_PATHFIND_MAX_DEPTH"),
        setter=_params_setter("ENEMY_PATHFIND_MAX_DEPTH"),
        min_value=400, max_value=3000, default=1500,
        fidelity_cost=_pathfind_fidelity,
    ),
    "UNREACHABLE_RECHECK_INTERVAL": Knob(
        name="UNREACHABLE_RECHECK_INTERVAL",
        getter=_get_unreachable_interval,
        setter=_set_unreachable_interval,
        min_value=0.25, max_value=2.5, default=0.5,
        fidelity_cost=_unreachable_fidelity,
    ),
}


# Make sure the new param attribute exists with its default.
if not hasattr(params, "UNREACHABLE_RECHECK_INTERVAL"):
    setattr(params, "UNREACHABLE_RECHECK_INTERVAL", 0.5)


# ── Profile selection ─────────────────────────────────────────────


# Profile key = (size_bucket, threat_bucket).  Each bucket is picked
# from cheap world-state features.  Thresholds were chosen so the
# four most-common gameplay states each get their own profile.
SIZE_THRESHOLDS: list[tuple[int, str]] = [
    (50,  "small"),
    (150, "medium"),
    (350, "large"),
    (10**9, "huge"),
]
THREAT_THRESHOLDS: list[tuple[int, str]] = [
    (5,   "calm"),
    (40,  "active"),
    (10**9, "swarm"),
]


def _bucket(value: int, table: list[tuple[int, str]]) -> str:
    for limit, name in table:
        if value <= limit:
            return name
    return table[-1][1]


def classify_world(world: "World") -> str:
    """Return the profile key for ``world``'s current state.

    Cheap O(1)-ish: just reads list lengths.  Called every couple of
    seconds, never per-frame.
    """
    n_buildings = len(world.buildings.buildings)
    n_enemies = len(world.combat.enemies)
    size = _bucket(n_buildings, SIZE_THRESHOLDS)
    threat = _bucket(n_enemies, THREAT_THRESHOLDS)
    return f"{size}_{threat}"


# ── Baked profiles (overwritten by tools/perf_train.py) ───────────


# Profile values are knob_name → value.  ``DEFAULT_PROFILE`` is used
# when ``classify_world`` returns a key not present in
# ``AUTOTUNE_PROFILES`` (e.g. before the first training run).
DEFAULT_PROFILE: dict[str, float] = {
    name: knob.default for name, knob in KNOBS.items()
}


# Hand-tuned starter profiles.  These are sensible defaults for the
# four most-common gameplay states; ``tools/perf_train.py`` will
# overwrite this dict once a sweep has been collected.  Anything not
# listed falls back to ``DEFAULT_PROFILE``.
AUTOTUNE_PROFILES: dict[str, dict[str, float]] = {
    # --- BEGIN GENERATED BLOCK (perf_train.py) ---
    "huge_active":     {"ENEMY_RETARGET_BUDGET_PER_TICK":    25,
                         "ENEMY_PATHFIND_MAX_DEPTH":   800,
                         "UNREACHABLE_RECHECK_INTERVAL":  1.500},
    "huge_calm":       {"ENEMY_RETARGET_BUDGET_PER_TICK":    25,
                         "ENEMY_PATHFIND_MAX_DEPTH":  1500,
                         "UNREACHABLE_RECHECK_INTERVAL":  0.500},
    "huge_swarm":      {"ENEMY_RETARGET_BUDGET_PER_TICK":    25,
                         "ENEMY_PATHFIND_MAX_DEPTH":   800,
                         "UNREACHABLE_RECHECK_INTERVAL":  1.500},
    "large_active":    {"ENEMY_RETARGET_BUDGET_PER_TICK":    10,
                         "ENEMY_PATHFIND_MAX_DEPTH":   800,
                         "UNREACHABLE_RECHECK_INTERVAL":  0.500},
    "large_calm":      {"ENEMY_RETARGET_BUDGET_PER_TICK":    25,
                         "ENEMY_PATHFIND_MAX_DEPTH":  1500,
                         "UNREACHABLE_RECHECK_INTERVAL":  0.500},
    "large_swarm":     {"ENEMY_RETARGET_BUDGET_PER_TICK":    25,
                         "ENEMY_PATHFIND_MAX_DEPTH":   800,
                         "UNREACHABLE_RECHECK_INTERVAL":  1.500},
    "medium_active":   {"ENEMY_RETARGET_BUDGET_PER_TICK":    10,
                         "ENEMY_PATHFIND_MAX_DEPTH":   800,
                         "UNREACHABLE_RECHECK_INTERVAL":  1.500},
    "medium_calm":     {"ENEMY_RETARGET_BUDGET_PER_TICK":    25,
                         "ENEMY_PATHFIND_MAX_DEPTH":  1500,
                         "UNREACHABLE_RECHECK_INTERVAL":  0.500},
    "medium_swarm":    {"ENEMY_RETARGET_BUDGET_PER_TICK":    25,
                         "ENEMY_PATHFIND_MAX_DEPTH":   800,
                         "UNREACHABLE_RECHECK_INTERVAL":  0.500},
    "small_active":    {"ENEMY_RETARGET_BUDGET_PER_TICK":    10,
                         "ENEMY_PATHFIND_MAX_DEPTH":   800,
                         "UNREACHABLE_RECHECK_INTERVAL":  1.500},
    "small_calm":      {"ENEMY_RETARGET_BUDGET_PER_TICK":    25,
                         "ENEMY_PATHFIND_MAX_DEPTH":  1500,
                         "UNREACHABLE_RECHECK_INTERVAL":  0.500},
    # --- END GENERATED BLOCK (perf_train.py) ---
}


# ── Apply / runtime hook ──────────────────────────────────────────


def apply_profile(profile_key: str) -> dict[str, float]:
    """Write the profile's knob values into the live system.

    Returns the dict that was actually applied (after clamping), so
    callers/UI can show what's currently active.
    """
    profile = AUTOTUNE_PROFILES.get(profile_key, DEFAULT_PROFILE)
    applied: dict[str, float] = {}
    for knob_name, knob in KNOBS.items():
        # Profile may omit a knob — fall back to the default.
        v = float(profile.get(knob_name, DEFAULT_PROFILE[knob_name]))
        v = max(knob.min_value, min(knob.max_value, v))
        knob.setter(v)
        applied[knob_name] = v
    return applied


# Per-world retune state.  We attach a tiny accumulator to the
# World instance the first time we see it so the public API stays a
# single function call.
_RETUNE_INTERVAL_S: float = 2.0


def maybe_retune(world: "World", dt: float) -> None:
    """Reclassify and reapply if enough sim time has passed.

    Safe to call every frame — most calls do nothing but advance a
    counter.
    """
    state = getattr(world, "_autotune_state", None)
    if state is None:
        state = {"accum": 0.0, "key": None, "applied": dict(DEFAULT_PROFILE)}
        # Apply once immediately so opening frames already use a
        # sensible profile rather than the import-time defaults.
        key = classify_world(world)
        state["key"] = key
        state["applied"] = apply_profile(key)
        setattr(world, "_autotune_state", state)
        return

    state["accum"] += dt
    if state["accum"] < _RETUNE_INTERVAL_S:
        return
    state["accum"] = 0.0
    key = classify_world(world)
    if key == state["key"]:
        return
    state["key"] = key
    state["applied"] = apply_profile(key)


def current_status(world: "World") -> dict[str, Any]:
    """Inspector: returns ``{"key": ..., "applied": {...}}`` or
    ``None`` if the autotuner hasn't run for this world yet."""
    state = getattr(world, "_autotune_state", None)
    if state is None:
        return {"key": None, "applied": {}}
    return {"key": state["key"], "applied": dict(state["applied"])}
