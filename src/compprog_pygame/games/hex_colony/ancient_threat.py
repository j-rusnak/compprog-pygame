"""Ancient technology threat — escalating environmental hazard.

When the player's colony grows past certain population thresholds OR
disturbs enough buried ruins, ancient machines rise from the ground.
Each tower converts everything within a 2-tile radius into wasteland,
deleting whatever the player had built there.

This module owns the trigger logic and the persistent state.  The
actual cinematic transition is handled by
:mod:`compprog_pygame.games.hex_colony.awakening_cutscene`; this module
just produces an :class:`AwakeningEvent` when the next awakening should
fire and exposes the helpers the cutscene needs to "rise" each tower
and apply its damage.
"""

from __future__ import annotations

import random as _random
from dataclasses import dataclass, field

from compprog_pygame.games.hex_colony import params
from compprog_pygame.games.hex_colony.hex_grid import HexCoord, Terrain
from compprog_pygame.games.hex_colony.overlay import OverlayRuin


@dataclass(slots=True)
class AncientTower:
    """A single risen ancient tower sitting on a hex.

    ``rise_progress`` is animated 0 -> 1 by the cutscene as the tower
    emerges from the ground; the renderer uses it to scale and reveal
    the sprite.  Once the cutscene finishes the tower is permanent.
    """
    coord: HexCoord
    radius: int = 2
    rise_progress: float = 1.0


@dataclass(slots=True)
class AwakeningEvent:
    """Snapshot of a pending awakening, queued for the cutscene."""
    index: int                        # 0-based: which awakening is this
    tower_coords: list[HexCoord] = field(default_factory=list)


@dataclass(slots=True)
class AncientThreat:
    """World-level state for the ancient-tech threat."""

    # Persistent
    awakening_index: int = 0          # how many awakenings have already fired
    disturbance: int = 0              # ruin tiles disturbed by the player
    disturbed_ruins: set[tuple[int, int]] = field(default_factory=set)
    towers: list[AncientTower] = field(default_factory=list)
    # Set of hex coords occupied by an active tower, for fast lookup.
    tower_coords: set[HexCoord] = field(default_factory=set)

    # Transient — drained by game.py on the next tick
    pending_awakening: AwakeningEvent | None = None

    # ── Triggers ─────────────────────────────────────────────────

    def tick(self, world) -> None:
        """Check escalation thresholds; queue an awakening if reached.

        Called once per ``World.update``.  Cheap — just a few int
        comparisons and (when triggered) a one-shot site selection.
        """
        if self.pending_awakening is not None:
            return  # cutscene already queued
        if self.awakening_index >= params.AWAKENING_MAX_COUNT:
            return

        # Trigger 1 — population threshold.
        pop = world.player_population_count
        pop_threshold = params.AWAKENING_POP_THRESHOLDS[
            min(self.awakening_index, len(params.AWAKENING_POP_THRESHOLDS) - 1)
        ]
        # Trigger 2 — disturbance threshold.
        dist_threshold = params.AWAKENING_DISTURBANCE_THRESHOLDS[
            min(self.awakening_index, len(params.AWAKENING_DISTURBANCE_THRESHOLDS) - 1)
        ]

        if pop >= pop_threshold or self.disturbance >= dist_threshold:
            self.pending_awakening = self._prepare_event(world)

    def notify_built(self, world, building) -> None:
        """Called from game.py whenever the player places a building.

        Increments the disturbance counter when the placement sits on
        or next to a previously-undisturbed ruin tile.
        """
        renderer = getattr(world, "_renderer_ref", None)
        if renderer is None:
            return
        coord = building.coord
        candidates = [coord] + coord.neighbors()
        for c in candidates:
            key = (c.q, c.r)
            if key in self.disturbed_ruins:
                continue
            if renderer.has_ruin_at(c):
                self.disturbed_ruins.add(key)
                self.disturbance += 1

    # ── Event preparation ────────────────────────────────────────

    def _prepare_event(self, world) -> AwakeningEvent:
        """Choose tower locations for the next awakening."""
        rng = _random.Random(
            (abs(hash(getattr(world, "seed", "default"))) & 0xFFFFFFFF)
            ^ (0xAC1E0 + self.awakening_index)
        )
        n_towers = params.AWAKENING_TOWERS_PER_EVENT[
            min(self.awakening_index, len(params.AWAKENING_TOWERS_PER_EVENT) - 1)
        ]

        chosen: list[HexCoord] = []
        used: set[HexCoord] = set(self.tower_coords)
        camp = world.player_colony.camp_coord

        # Prefer tiles that already have a ruin overlay — feels like
        # the ruins themselves are awakening.  Only one tower per
        # ruin cluster, so a single set of ruins never births a swarm.
        renderer = getattr(world, "_renderer_ref", None)
        ruin_coords: list[HexCoord] = []
        seen_clusters: set[int] = set()
        if renderer is not None:
            cluster_candidates: list[tuple[int, HexCoord]] = []
            for item in renderer._static_overlays:
                if not isinstance(item, OverlayRuin):
                    continue
                if item.wx != item.wx:  # NaN — removed
                    continue
                rc = HexCoord(item.coord[0], item.coord[1])
                if rc in used:
                    continue
                tile = world.grid.get(rc)
                if tile is None or tile.terrain == Terrain.WASTELAND:
                    continue
                # Stay outside the camp safety bubble.
                if rc.distance(camp) < params.AWAKENING_MIN_CAMP_DISTANCE:
                    continue
                cluster_candidates.append((item.cluster_id, rc))

            # Shuffle so which tile within a cluster gets picked is
            # randomised, then keep the first occurrence per cluster id.
            rng.shuffle(cluster_candidates)
            for cid, rc in cluster_candidates:
                if cid in seen_clusters:
                    continue
                seen_clusters.add(cid)
                ruin_coords.append(rc)

        rng.shuffle(ruin_coords)
        # Pick well-separated ruin sites first.
        for rc in ruin_coords:
            if len(chosen) >= n_towers:
                break
            if all(rc.distance(c) >= params.AWAKENING_TOWER_SEPARATION
                   for c in chosen):
                chosen.append(rc)
                used.add(rc)

        # If we still need more towers, pick random buildable hexes a
        # bit further out from camp so the player notices them but
        # they don't directly demolish the spaceship.
        if len(chosen) < n_towers:
            fallback: list[HexCoord] = []
            for tile in world.grid.tiles():
                c = tile.coord
                if c in used:
                    continue
                if tile.terrain in (Terrain.WATER, Terrain.MOUNTAIN,
                                    Terrain.WASTELAND):
                    continue
                d = c.distance(camp)
                if d < params.AWAKENING_MIN_CAMP_DISTANCE:
                    continue
                if d > params.AWAKENING_MAX_CAMP_DISTANCE:
                    continue
                fallback.append(c)
            rng.shuffle(fallback)
            for c in fallback:
                if len(chosen) >= n_towers:
                    break
                if all(c.distance(o) >= params.AWAKENING_TOWER_SEPARATION
                       for o in chosen):
                    chosen.append(c)
                    used.add(c)

            # Relaxation pass — if the strict separation didn't yield
            # enough sites (small map, lots of water), gradually shrink
            # the spacing requirement until we hit the target count.
            if len(chosen) < n_towers:
                sep = params.AWAKENING_TOWER_SEPARATION
                while len(chosen) < n_towers and sep > 2:
                    sep = max(2, sep // 2)
                    for c in fallback:
                        if len(chosen) >= n_towers:
                            break
                        if c in used:
                            continue
                        if all(c.distance(o) >= sep for o in chosen):
                            chosen.append(c)
                            used.add(c)

        return AwakeningEvent(index=self.awakening_index,
                              tower_coords=chosen)

    # ── Cutscene callbacks ───────────────────────────────────────

    def apply_tower(self, world, tower: AncientTower) -> set[HexCoord]:
        """Convert hexes within ``tower.radius`` to wasteland and
        delete any buildings there.  Returns the set of changed coords
        so the renderer can refresh those tiles.
        """
        changed: set[HexCoord] = set()
        center = tower.coord

        # All hexes within radius (including the tower's own tile).
        for tile in world.grid.tiles():
            if tile.coord.distance(center) > tower.radius:
                continue
            terrain = tile.terrain
            # Leave bedrock terrain alone — it's already harsh and
            # converting it would look weird (water turning to dirt).
            if terrain in (Terrain.WATER, Terrain.MOUNTAIN):
                continue
            if terrain == Terrain.WASTELAND and tile.coord != center:
                continue

            # Delete any building on this tile (except the tower hex —
            # we want the tower itself to "occupy" that tile).
            existing = tile.building
            if existing is not None:
                world.buildings.remove(existing)
                tile.building = None
                world.mark_housing_dirty()

            tile.terrain = Terrain.WASTELAND
            tile.underlying_terrain = None
            tile.resource_amount = 0.0
            tile.food_amount = 0.0
            world.pending_depleted_tiles.add(tile.coord)
            changed.add(tile.coord)

        return changed

    def commit_tower(self, tower: AncientTower) -> None:
        """Add a freshly-risen tower to the persistent list."""
        self.towers.append(tower)
        self.tower_coords.add(tower.coord)

    def finalize_event(self) -> None:
        """Mark the queued event as consumed — bumps the index."""
        self.pending_awakening = None
        self.awakening_index += 1
