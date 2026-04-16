"""Technology tree framework for Hex Colony.

The tech tree gates access to advanced buildings behind research costs.
Each ``Tech`` has a resource cost and a set of ``BuildingType``s it
unlocks.  The ``TechTree`` tracks which techs have been researched.

Buildings in ``TECH_REQUIREMENTS`` cannot be built until the required
tech is unlocked.  Buildings *not* listed are available from the start.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto

from compprog_pygame.games.hex_colony.buildings import BuildingType
from compprog_pygame.games.hex_colony.resources import Resource


class Tech(Enum):
    METALLURGY = auto()     # unlocks Refinery
    AGRICULTURE = auto()    # unlocks Farm
    HYDRAULICS = auto()     # unlocks Well
    ENGINEERING = auto()    # unlocks Bridge


@dataclass(frozen=True)
class TechInfo:
    """Metadata for a single technology."""
    name: str
    description: str
    cost: dict[Resource, int]
    unlocks: frozenset[BuildingType]
    prerequisites: frozenset[Tech] = frozenset()


# ── Tech definitions ─────────────────────────────────────────────

TECH_DATA: dict[Tech, TechInfo] = {
    Tech.METALLURGY: TechInfo(
        name="Metallurgy",
        description="Smelt raw ore into usable metal",
        cost={Resource.IRON: 10, Resource.STONE: 15},
        unlocks=frozenset({BuildingType.REFINERY}),
    ),
    Tech.AGRICULTURE: TechInfo(
        name="Agriculture",
        description="Cultivate crops for steady food",
        cost={Resource.WOOD: 20, Resource.FIBER: 15},
        unlocks=frozenset({BuildingType.FARM}),
    ),
    Tech.HYDRAULICS: TechInfo(
        name="Hydraulics",
        description="Harness water to irrigate farms",
        cost={Resource.STONE: 20, Resource.IRON: 5},
        unlocks=frozenset({BuildingType.WELL}),
        prerequisites=frozenset({Tech.AGRICULTURE}),
    ),
    Tech.ENGINEERING: TechInfo(
        name="Engineering",
        description="Build structures over difficult terrain",
        cost={Resource.WOOD: 15, Resource.STONE: 10},
        unlocks=frozenset({BuildingType.BRIDGE}),
    ),
}

# Reverse lookup: which tech is needed for a building?
TECH_REQUIREMENTS: dict[BuildingType, Tech] = {}
for _tech, _info in TECH_DATA.items():
    for _bt in _info.unlocks:
        TECH_REQUIREMENTS[_bt] = _tech


class TechTree:
    """Tracks researched technologies for a single game session."""

    def __init__(self) -> None:
        self.researched: set[Tech] = set()

    def is_unlocked(self, tech: Tech) -> bool:
        return tech in self.researched

    def can_research(self, tech: Tech) -> bool:
        """Check if prerequisites are met (ignores cost)."""
        info = TECH_DATA[tech]
        return info.prerequisites.issubset(self.researched) and tech not in self.researched

    def research(self, tech: Tech) -> None:
        self.researched.add(tech)

    def is_building_unlocked(self, btype: BuildingType) -> bool:
        """Return True if the building has no tech requirement or it's been researched."""
        req = TECH_REQUIREMENTS.get(btype)
        if req is None:
            return True
        return req in self.researched

    def available_techs(self) -> list[Tech]:
        """Return techs that can currently be researched (prereqs met, not yet done)."""
        return [t for t in Tech if self.can_research(t)]
