"""Train an offline performance profile table from a sweep CSV.

Reads ``perf_sweep.csv`` (produced by ``tools/perf_sweep.py``) and for
every scenario name picks the knob combination with the **lowest
fidelity cost** that still keeps p95 frame time under the configured
budget.  The selected per-scenario knob settings are written back into
``src/compprog_pygame/games/hex_colony/perf_autotune.py`` between the
``--- BEGIN GENERATED BLOCK ---`` / ``--- END GENERATED BLOCK ---``
markers.

Usage::

    $env:PYTHONPATH = "src"
    python tools/perf_train.py --in perf_sweep.csv --budget-ms 12

``--budget-ms`` is the per-frame ``World.update`` budget *in addition*
to the rendering budget.  At 60 FPS the total frame budget is 16.67 ms
and rendering typically eats 4-6 ms, so 10-12 ms for the sim is a sane
default.

The trainer never imports pygame and has no runtime dependency on the
game itself — it's a pure CSV → dict → file rewrite.
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from collections import defaultdict
from pathlib import Path

# Allow running as a script from the repo root.
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from compprog_pygame.games.hex_colony.perf_autotune import KNOBS  # noqa: E402


KNOB_NAMES = list(KNOBS.keys())
PROFILES_PATH = (ROOT / "src" / "compprog_pygame" / "games"
                 / "hex_colony" / "perf_autotune.py")
BEGIN_MARK = "    # --- BEGIN GENERATED BLOCK (perf_train.py) ---"
END_MARK = "    # --- END GENERATED BLOCK (perf_train.py) ---"


def _fidelity_cost(combo: dict[str, float]) -> float:
    return sum(KNOBS[k].fidelity_cost(float(v)) for k, v in combo.items())


def _safe_p95(r: dict) -> float | None:
    v = r.get("p95_ms")
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _pick_best(rows: list[dict], budget_ms: float) -> dict[str, float]:
    """For one scenario's rows, choose the lowest-fidelity-cost knob
    combo whose p95 is under ``budget_ms``.  If none make the budget,
    fall back to the row with the lowest p95.
    """
    valid = [r for r in rows if _safe_p95(r) is not None]
    feasible = [r for r in valid if _safe_p95(r) <= budget_ms]
    if feasible:
        best = min(feasible,
                   key=lambda r: (_fidelity_cost(_combo(r)),
                                  _safe_p95(r) or 0.0))
    elif valid:
        best = min(valid, key=lambda r: _safe_p95(r) or 0.0)
    else:
        # No valid rows for this scenario — return the registry default.
        from compprog_pygame.games.hex_colony.perf_autotune import (
            DEFAULT_PROFILE,
        )
        return dict(DEFAULT_PROFILE)
    return _combo(best)


def _combo(row: dict) -> dict[str, float]:
    combo: dict[str, float] = {}
    for k in KNOB_NAMES:
        v = row.get(k)
        if v is None or v == "":
            continue
        try:
            iv = int(v)
            fv = float(v)
            combo[k] = iv if iv == fv else fv
        except (TypeError, ValueError):
            try:
                combo[k] = float(v)
            except (TypeError, ValueError):
                # Row is malformed for this knob — skip it.
                continue
    return combo


def _format_profiles(profiles: dict[str, dict[str, float]]) -> str:
    """Render the dict as the source-file block between the markers."""
    lines: list[str] = []
    name_w = max(len(s) for s in profiles) + 4  # for the comma & quotes
    for scenario in sorted(profiles):
        combo = profiles[scenario]
        # First knob on the same line as the scenario key, the rest
        # aligned underneath — mirrors the hand-tuned starter block.
        items = list(combo.items())
        if not items:
            continue
        head = f'    "{scenario}":'
        head = head.ljust(4 + name_w + 2)
        prefix = head + "{"
        first_k, first_v = items[0]
        lines.append(f'{prefix}"{first_k}": {_fmt_value(first_v)},')
        indent = " " * (len(prefix) + 1)
        for i, (k, v) in enumerate(items[1:]):
            tail = "}," if i == len(items) - 2 else ","
            lines.append(f'{indent}"{k}": {_fmt_value(v)}{tail}')
    return "\n".join(lines)


def _fmt_value(v: float | int) -> str:
    if isinstance(v, int):
        return f"{v:>5d}"
    return f"{v:>6.3f}"


def _rewrite_profiles(new_block: str) -> None:
    src = PROFILES_PATH.read_text(encoding="utf-8")
    pattern = re.compile(
        rf"({re.escape(BEGIN_MARK)}\n)(.*?)(\n{re.escape(END_MARK)})",
        re.DOTALL,
    )
    if not pattern.search(src):
        raise SystemExit(
            f"could not find generated block markers in {PROFILES_PATH}"
        )
    new_src = pattern.sub(rf"\1{new_block}\3", src)
    PROFILES_PATH.write_text(new_src, encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--in", dest="inp", default="perf_sweep.csv",
                    help="Sweep CSV path.")
    ap.add_argument("--budget-ms", type=float, default=12.0,
                    help="Per-frame sim budget for World.update (ms).")
    ap.add_argument("--dry-run", action="store_true",
                    help="Print the new profile block without writing.")
    args = ap.parse_args()

    inp = Path(args.inp)
    if not inp.exists():
        raise SystemExit(f"sweep file not found: {inp}")

    rows_by_scenario: dict[str, list[dict]] = defaultdict(list)
    with inp.open(newline="") as f:
        for r in csv.DictReader(f):
            scenario = (r.get("scenario") or "").strip()
            # Skip rows whose scenario field looks numeric or empty —
            # they are usually fragments of a partially-written line.
            if not scenario:
                continue
            try:
                float(scenario)
                continue  # purely numeric, treat as junk
            except ValueError:
                pass
            rows_by_scenario[scenario].append(r)
    if not rows_by_scenario:
        raise SystemExit(
            f"sweep file {inp} contains no data rows — re-run "
            f"tools/perf_sweep.py to populate it."
        )

    profiles: dict[str, dict[str, float]] = {}
    print(f"[train] budget = {args.budget_ms:.1f} ms p95 per frame")
    print(f"[train] {len(rows_by_scenario)} scenarios in {inp}")
    for scenario, rows in rows_by_scenario.items():
        chosen = _pick_best(rows, args.budget_ms)
        profiles[scenario] = chosen
        match = next(
            (r for r in rows if all(
                str(chosen[k]) == str(_combo(r).get(k)) for k in chosen
            )),
            None,
        )
        p95_v = _safe_p95(match) if match else None
        p95 = p95_v if p95_v is not None else float("nan")
        cost = _fidelity_cost(chosen)
        print(f"  {scenario:<15s} p95={p95:5.2f}ms  "
              f"fidelity_cost={cost:5.3f}  {chosen}")

    block = _format_profiles(profiles)
    if args.dry_run:
        print("\n[train] --dry-run — would write the following block:\n")
        print(block)
        return 0

    _rewrite_profiles(block)
    print(f"[train] wrote {len(profiles)} profiles into {PROFILES_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
