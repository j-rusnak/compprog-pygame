"""Technology tree and tier progression for Hex Colony.

Two progression systems:
1. **Tiers** — accessed via the Ship Wreckage (camp).  Each tier unlocks
   core buildings/features.  Requirements include population, resources
   delivered, buildings placed, and research count.
2. **Tech Tree** — accessed via the Research Center.  Each node costs
   resources + time and unlocks niche/optional features.

All data is driven by ``params.TIER_DATA`` and ``params.TECH_TREE_DATA``
so balancing changes need only touch params.py.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from compprog_pygame.games.hex_colony.buildings import BuildingType
from compprog_pygame.games.hex_colony.resources import Resource
from compprog_pygame.games.hex_colony import params


# ═══════════════════════════════════════════════════════════════════
#  Tech Tree (Research Center)
# ═══════════════════════════════════════════════════════════════════

@dataclass
class TechNode:
    """A single research node."""
    key: str
    name: str
    description: str
    cost: dict[Resource, int]
    time: float  # seconds to research
    prerequisites: list[str]
    unlocks: list[BuildingType]
    unlock_resources: list[Resource]
    position: tuple[int, int]  # grid (col, row) for visual layout


def _build_tech_nodes() -> dict[str, TechNode]:
    nodes: dict[str, TechNode] = {}
    for key, data in params.TECH_TREE_DATA.items():
        cost = {Resource[k]: v for k, v in data["cost"].items()}
        unlocks = [BuildingType[b] for b in data.get("unlocks", [])]
        unlock_resources = [
            Resource[r] for r in data.get("unlock_resources", [])
        ]
        nodes[key] = TechNode(
            key=key,
            name=data["name"],
            description=data["description"],
            cost=cost,
            time=data["time"],
            prerequisites=list(data.get("prerequisites", [])),
            unlocks=unlocks,
            unlock_resources=unlock_resources,
            position=tuple(data.get("position", (0, 0))),
        )
    return nodes


TECH_NODES: dict[str, TechNode] = _build_tech_nodes()

# Reverse lookup: which tech key unlocks a building?
TECH_REQUIREMENTS: dict[BuildingType, str] = {}
for _key, _node in TECH_NODES.items():
    for _bt in _node.unlocks:
        TECH_REQUIREMENTS[_bt] = _key

# Reverse lookup: which tech key unlocks a specific recipe/resource?
# Resources NOT in this map are unconditionally available (subject to
# their producing station being available).
RESOURCE_TECH_REQUIREMENTS: dict[Resource, str] = {}
for _key, _node in TECH_NODES.items():
    for _res in _node.unlock_resources:
        RESOURCE_TECH_REQUIREMENTS[_res] = _key


class TechTree:
    """Tracks researched technologies for a single game session."""

    def __init__(self) -> None:
        self.researched: set[str] = set()
        self.current_research: str | None = None
        self.research_progress: float = 0.0  # seconds elapsed on the
                                             # currently active node
        # Saved state for nodes the player started but switched away
        # from.  Each entry is {"progress": float, "consumed":
        # {Resource: float}} so they can resume exactly where they
        # left off (with the resources they already paid retained).
        self._saved: dict[str, dict] = {}
        # Resources already consumed for the active node.
        self._consumed: dict[Resource, float] = {}

    @property
    def researched_count(self) -> int:
        return len(self.researched)

    def is_unlocked(self, key: str) -> bool:
        return key in self.researched

    def can_research(self, key: str) -> bool:
        """Check if prerequisites are met (ignores cost)."""
        if key in self.researched:
            return False
        node = TECH_NODES.get(key)
        if node is None:
            return False
        return all(p in self.researched for p in node.prerequisites)

    def start_research(self, key: str) -> None:
        """Begin researching a tech node.

        Switching mid-research preserves the previous node's progress
        and consumed resources under :attr:`_saved` so it can be
        resumed later.  If *key* was previously paused, its saved
        state is restored.

        No-op if *key* is unknown, already researched, or its
        prerequisites aren't all met (defensive guard against any
        caller that forgets to check :meth:`can_research` first).
        """
        if not self.can_research(key):
            return
        # Save the currently active node's state (if any).
        if (self.current_research is not None
                and self.current_research != key):
            self._saved[self.current_research] = {
                "progress": self.research_progress,
                "consumed": dict(self._consumed),
            }
        # Restore *key*'s state if it was paused, else start fresh.
        if key == self.current_research:
            return
        saved = self._saved.pop(key, None)
        if saved is not None:
            self.research_progress = float(saved.get("progress", 0.0))
            self._consumed = dict(saved.get("consumed", {}))
        else:
            self.research_progress = 0.0
            self._consumed = {}
        self.current_research = key

    def cancel_research(self) -> None:
        # Preserve progress under _saved so the player can resume.
        if self.current_research is not None:
            self._saved[self.current_research] = {
                "progress": self.research_progress,
                "consumed": dict(self._consumed),
            }
        self.current_research = None
        self.research_progress = 0.0
        self._consumed = {}

    def update(
        self, dt: float, world: object | None = None,
        faction: str = "SURVIVOR",
    ) -> str | None:
        """Advance research by *dt* seconds, consuming resources from
        the Research Center's on-site storage (preferred) and the
        owning faction's inventory (fallback) as work happens.

        * Requires at least one Research Center building **owned by
          *faction*** to be placed AND staffed by at least one worker
          (when *world* is provided).
        * Progress is scaled by the total worker count across that
          faction's research centers.
        * Each tick attempts to advance ``effective_dt`` seconds of
          work and consumes a proportional share of each input.  If
          a required input is short, progress is throttled to the
          worst-case available ratio.
        * Returns the tech key when fully completed.
        """
        if self.current_research is None:
            return None
        node = TECH_NODES.get(self.current_research)
        if node is None:
            self.current_research = None
            return None
        # Gate on a built and staffed Research Center owned by *faction*.
        rc_list: list = []
        worker_total = 0
        if world is not None:
            from compprog_pygame.games.hex_colony.buildings import (
                BuildingType,
            )
            rc_list = [
                rc for rc in world.buildings.by_type(BuildingType.RESEARCH_CENTER)
                if getattr(rc, "faction", "SURVIVOR") == faction
            ]
            if not rc_list:
                return None
            worker_total = sum(rc.workers for rc in rc_list)
            if worker_total <= 0:
                # Has the building but nobody to run it.
                return None

        # Effective time advanced this tick scales with worker count.
        worker_factor = max(1, worker_total) if world is not None else 1
        effective_dt = dt * worker_factor

        time_left = max(0.0, node.time - self.research_progress)
        if time_left <= 0:
            target_progress = node.time
        else:
            target_progress = min(
                node.time, self.research_progress + effective_dt,
            )

        # How much of each input we'd need to reach target_progress.
        # Pull fallback inventory from *faction*'s colony state.
        inv = None
        if world is not None:
            colony = world.colonies.get(faction) if hasattr(world, "colonies") else None
            inv = colony.inventory if colony is not None else getattr(world, "inventory", None)
        for res, total_amount in node.cost.items():
            already = self._consumed.get(res, 0.0)
            needed_total = (target_progress / node.time) * total_amount
            need_now = max(0.0, needed_total - already)
            if need_now <= 0:
                continue
            if inv is None:
                # No inventory available — pretend cost is free.
                self._consumed[res] = needed_total
                continue
            took = 0.0
            # Prefer pulling from any Research Center's on-site
            # storage first (logistics fills it up like a workshop).
            # Drain the RC with the most of this resource first so
            # multiple centers stay balanced \u2014 otherwise the same
            # rc_list[0] would always be drained, leaving others
            # over-stocked and dropping their demand to zero, which
            # halts deliveries to all centers.
            rc_sorted = sorted(
                rc_list,
                key=lambda rc: rc.storage.get(res, 0.0),
                reverse=True,
            )
            for rc in rc_sorted:
                if took >= need_now:
                    break
                have_here = rc.storage.get(res, 0.0)
                if have_here <= 0:
                    continue
                pull = min(need_now - took, have_here)
                rc.storage[res] = have_here - pull
                if rc.storage[res] <= 1e-6:
                    rc.storage.pop(res, None)
                took += pull
            # Fall back to the global inventory for the remainder.
            if took < need_now:
                rem = need_now - took
                avail = inv[res]
                pull = min(rem, avail)
                if pull > 0:
                    inv.spend(res, pull)
                    took += pull
            if took > 0:
                self._consumed[res] = already + took

        # Actual progress is the minimum consumed / total_cost ratio,
        # multiplied by node.time.  Use a small epsilon when checking
        # ratios to avoid floating-point 99%-stuck issues.
        if node.cost:
            min_ratio = 1.0
            for res, total_amount in node.cost.items():
                if total_amount <= 0:
                    continue
                ratio = self._consumed.get(res, 0.0) / total_amount
                # Snap near-complete ratios to 1.0 to prevent the
                # research from stalling at 99% due to float rounding.
                if ratio >= 1.0 - 1e-9:
                    ratio = 1.0
                if ratio < min_ratio:
                    min_ratio = ratio
            self.research_progress = min(node.time, min_ratio * node.time)
        else:
            # Free research — just advance.
            self.research_progress = target_progress

        # Mark research centers active so renderers / stats reflect it.
        for rc in rc_list:
            rc.active = True

        if self.research_progress >= node.time:
            completed = self.current_research
            self.researched.add(completed)
            self.current_research = None
            self.research_progress = 0.0
            self._consumed = {}
            return completed
        return None

    def is_building_unlocked(self, btype: BuildingType) -> bool:
        """Return True if the building has no tech requirement or it's been researched."""
        req = TECH_REQUIREMENTS.get(btype)
        if req is None:
            return True
        return req in self.researched

    def available_techs(self) -> list[str]:
        """Return tech keys that can currently be researched (prereqs met, not yet done)."""
        return [k for k in TECH_NODES if self.can_research(k)]

    def all_nodes(self) -> list[TechNode]:
        return list(TECH_NODES.values())


# ═══════════════════════════════════════════════════════════════════
#  Tier System (Ship Wreckage / Camp)
# ═══════════════════════════════════════════════════════════════════

@dataclass
class TierInfo:
    """Data for a single tier."""
    level: int
    name: str
    description: str
    unlocks_buildings: list[BuildingType]
    requirements: dict  # raw requirement dict from params


def _build_tiers() -> list[TierInfo]:
    tiers: list[TierInfo] = []
    for i, data in enumerate(params.TIER_DATA):
        unlocks = [BuildingType[b] for b in data.get("unlocks_buildings", [])]
        tiers.append(TierInfo(
            level=i,
            name=data["name"],
            description=data["description"],
            unlocks_buildings=unlocks,
            requirements=dict(data.get("requirements", {})),
        ))
    return tiers


TIERS: list[TierInfo] = _build_tiers()

# Reverse lookup: which tier unlocks a building?
TIER_BUILDING_REQUIREMENTS: dict[BuildingType, int] = {}
for _tier in TIERS:
    for _bt in _tier.unlocks_buildings:
        TIER_BUILDING_REQUIREMENTS[_bt] = _tier.level


class TierTracker:
    """Tracks the player's current tier and progress toward the next."""

    def __init__(self) -> None:
        self.current_tier: int = 0
        # Baselines snapshot at each tier-up so cumulative counters
        # (resources produced, research done) effectively restart at 0
        # for the next tier's goal display.
        self._baseline_produced: dict[str, float] = {}
        self._baseline_research: int = 0

    def check_requirements(
        self, world, faction: str = "SURVIVOR",
    ) -> dict[str, tuple[float, float]]:
        """Return {req_name: (current, required)} for the next tier.

        Values are (current_progress, target).  Returns empty if max tier.
        Population/building/research counts are scoped to *faction*.
        """
        next_level = self.current_tier + 1
        if next_level >= len(TIERS):
            return {}
        reqs = TIERS[next_level].requirements
        progress: dict[str, tuple[float, float]] = {}

        if "population" in reqs:
            # Count people whose home belongs to this faction.
            pop = sum(
                1 for p in world.population.people
                if p.home is not None
                and getattr(p.home, "faction", "SURVIVOR") == faction
            )
            # Backwards-compat: when the faction has no homes yet but
            # is the player, fall back to the global count so the
            # very first tick (before _update_housing runs) still
            # reports the correct starting population.
            if pop == 0 and faction == "SURVIVOR":
                pop = world.population.count
            progress["Population"] = (float(pop), float(reqs["population"]))
        if "buildings_placed" in reqs:
            count = sum(
                1 for b in world.buildings.buildings
                if b.type not in (BuildingType.PATH, BuildingType.BRIDGE,
                                  BuildingType.CAMP, BuildingType.WALL,
                                  BuildingType.TRIBAL_CAMP, BuildingType.HOUSE)
                and getattr(b, "faction", "SURVIVOR") == faction
            )
            progress["Buildings"] = (float(count), float(reqs["buildings_placed"]))
        if "resource_gathered" in reqs:
            from compprog_pygame.games.hex_colony.resources import Resource
            for res_name, target in reqs["resource_gathered"].items():
                res = Resource[res_name]
                baseline = self._baseline_produced.get(res_name, 0.0)
                current = max(0.0, world.total_produced(res, faction) - baseline)
                progress[res_name.capitalize()] = (float(current), float(target))
        if "research_count" in reqs:
            colony = world.colonies.get(faction) if hasattr(world, "colonies") else None
            if colony is not None:
                count = colony.tech_research_count
            else:
                count = getattr(world, '_tech_research_count', 0)
            current = max(0, count - self._baseline_research)
            progress["Research"] = (float(current), float(reqs["research_count"]))

        return progress

    def try_advance(self, world, faction: str = "SURVIVOR") -> bool:
        """Check if all requirements met; if so, advance tier.  Returns True if advanced."""
        progress = self.check_requirements(world, faction)
        if not progress:
            return False  # already max tier
        for current, required in progress.values():
            if current < required:
                return False
        self.current_tier += 1
        # Snapshot baselines so the next tier's resource/research goals
        # display progress starting from 0.
        from compprog_pygame.games.hex_colony.resources import Resource
        self._baseline_produced = {
            r.name: world.total_produced(r, faction) for r in Resource
        }
        colony = world.colonies.get(faction) if hasattr(world, "colonies") else None
        self._baseline_research = (
            colony.tech_research_count if colony is not None
            else getattr(world, '_tech_research_count', 0)
        )
        return True

    def is_building_unlocked(self, btype: BuildingType) -> bool:
        """Return True if the building's tier requirement is met."""
        req_tier = TIER_BUILDING_REQUIREMENTS.get(btype)
        if req_tier is None:
            return True  # no tier restriction
        return self.current_tier >= req_tier


# ═══════════════════════════════════════════════════════════════════
#  Combined availability helpers (tech + tier)
# ═══════════════════════════════════════════════════════════════════

def is_building_available(
    btype: BuildingType,
    tech_tree: "TechTree | None",
    tier_tracker: "TierTracker | None",
) -> bool:
    """True iff both tech-tree and tier requirements are satisfied."""
    if tech_tree is not None and not tech_tree.is_building_unlocked(btype):
        return False
    if tier_tracker is not None and not tier_tracker.is_building_unlocked(btype):
        return False
    return True


def is_resource_available(
    res: Resource,
    tech_tree: "TechTree | None",
    tier_tracker: "TierTracker | None",
) -> bool:
    """True iff the resource is reachable: any tech-tree gate is
    satisfied AND its producing station is available."""
    from compprog_pygame.games.hex_colony.resources import (
        MATERIAL_RECIPES,
        RAW_RESOURCES,
    )
    # Direct recipe gate: a tech may unlock a specific resource even
    # when its producing station has been available since tier 0.
    req_key = RESOURCE_TECH_REQUIREMENTS.get(res)
    if req_key is not None:
        if tech_tree is None or req_key not in tech_tree.researched:
            return False
    if res in RAW_RESOURCES:
        return True
    recipe = MATERIAL_RECIPES.get(res)
    if recipe is None:
        return True
    # recipe.station is a BuildingType enum member name
    try:
        btype = BuildingType[recipe.station]
    except KeyError:
        return True
    return is_building_available(btype, tech_tree, tier_tracker)
