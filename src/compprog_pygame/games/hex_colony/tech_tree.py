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
    position: tuple[int, int]  # grid (col, row) for visual layout


def _build_tech_nodes() -> dict[str, TechNode]:
    nodes: dict[str, TechNode] = {}
    for key, data in params.TECH_TREE_DATA.items():
        cost = {Resource[k]: v for k, v in data["cost"].items()}
        unlocks = [BuildingType[b] for b in data.get("unlocks", [])]
        nodes[key] = TechNode(
            key=key,
            name=data["name"],
            description=data["description"],
            cost=cost,
            time=data["time"],
            prerequisites=list(data.get("prerequisites", [])),
            unlocks=unlocks,
            position=tuple(data.get("position", (0, 0))),
        )
    return nodes


TECH_NODES: dict[str, TechNode] = _build_tech_nodes()

# Reverse lookup: which tech key unlocks a building?
TECH_REQUIREMENTS: dict[BuildingType, str] = {}
for _key, _node in TECH_NODES.items():
    for _bt in _node.unlocks:
        TECH_REQUIREMENTS[_bt] = _key


class TechTree:
    """Tracks researched technologies for a single game session."""

    def __init__(self) -> None:
        self.researched: set[str] = set()
        self.current_research: str | None = None
        self.research_progress: float = 0.0  # seconds elapsed

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
        """Begin researching a tech node (resets progress)."""
        self.current_research = key
        self.research_progress = 0.0

    def cancel_research(self) -> None:
        self.current_research = None
        self.research_progress = 0.0

    def update(self, dt: float) -> str | None:
        """Advance research by *dt* seconds.  Returns the key if completed."""
        if self.current_research is None:
            return None
        node = TECH_NODES.get(self.current_research)
        if node is None:
            self.current_research = None
            return None
        self.research_progress += dt
        if self.research_progress >= node.time:
            completed = self.current_research
            self.researched.add(completed)
            self.current_research = None
            self.research_progress = 0.0
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

    def check_requirements(self, world) -> dict[str, tuple[float, float]]:
        """Return {req_name: (current, required)} for the next tier.

        Values are (current_progress, target).  Returns empty if max tier.
        """
        next_level = self.current_tier + 1
        if next_level >= len(TIERS):
            return {}
        reqs = TIERS[next_level].requirements
        progress: dict[str, tuple[float, float]] = {}

        if "population" in reqs:
            progress["Population"] = (
                float(world.population.count),
                float(reqs["population"]),
            )
        if "buildings_placed" in reqs:
            # Count non-path, non-camp buildings
            count = sum(
                1 for b in world.buildings.buildings
                if b.type not in (BuildingType.PATH, BuildingType.BRIDGE,
                                  BuildingType.CAMP, BuildingType.WALL)
            )
            progress["Buildings"] = (float(count), float(reqs["buildings_placed"]))
        if "resource_gathered" in reqs:
            from compprog_pygame.games.hex_colony.resources import Resource
            for res_name, target in reqs["resource_gathered"].items():
                res = Resource[res_name]
                current = world.inventory[res]
                progress[res_name.capitalize()] = (float(current), float(target))
        if "research_count" in reqs:
            count = getattr(world, '_tech_research_count', 0)
            progress["Research"] = (float(count), float(reqs["research_count"]))

        return progress

    def try_advance(self, world) -> bool:
        """Check if all requirements met; if so, advance tier.  Returns True if advanced."""
        progress = self.check_requirements(world)
        if not progress:
            return False  # already max tier
        for current, required in progress.values():
            if current < required:
                return False
        self.current_tier += 1
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
    """True iff the resource is raw OR its producing station is available."""
    from compprog_pygame.games.hex_colony.resources import (
        MATERIAL_RECIPES,
        RAW_RESOURCES,
    )
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
