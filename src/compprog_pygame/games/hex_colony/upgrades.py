"""Building upgrade framework for Hex Colony.

Each building type can have a chain of upgrade levels.  Upgrading a
building in-place costs resources and improves its stats (workers,
storage, gathering rate, housing, etc.).

The framework defines:

- ``UpgradeLevel`` — one tier of improvements for a building type.
- ``UPGRADE_CHAINS`` — maps each upgradeable ``BuildingType`` to its
  ordered list of upgrade levels (level 0 is the base building).
- ``apply_upgrade`` / ``can_upgrade`` — helpers used by the game loop.

To add upgrades for a new building, add an entry to ``UPGRADE_CHAINS``.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from compprog_pygame.games.hex_colony.buildings import (
    Building,
    BuildingType,
    BUILDING_MAX_WORKERS,
    BUILDING_HOUSING,
    BUILDING_STORAGE_CAPACITY,
)
from compprog_pygame.games.hex_colony.resources import Resource


@dataclass(frozen=True)
class UpgradeLevel:
    """One upgrade tier for a building type."""

    name: str                           # display name for this tier
    cost: dict[Resource, int]           # resources required to upgrade
    max_workers_bonus: int = 0          # added to base max workers
    housing_bonus: int = 0              # added to base housing capacity
    storage_bonus: int = 0              # added to base storage capacity
    gather_rate_mult: float = 1.0       # multiplier on gather rate


# ── Upgrade chains ───────────────────────────────────────────────
# Level 0 = base building (no cost).  Each subsequent level is an
# upgrade that can be purchased in-place.

UPGRADE_CHAINS: dict[BuildingType, list[UpgradeLevel]] = {
    BuildingType.WOODCUTTER: [
        UpgradeLevel(name="Woodcutter", cost={}),
        UpgradeLevel(
            name="Improved Woodcutter",
            cost={Resource.WOOD: 15, Resource.STONE: 10},
            max_workers_bonus=1,
            gather_rate_mult=1.25,
        ),
        UpgradeLevel(
            name="Advanced Woodcutter",
            cost={Resource.WOOD: 25, Resource.IRON: 8},
            max_workers_bonus=2,
            storage_bonus=15,
            gather_rate_mult=1.5,
        ),
    ],
    BuildingType.QUARRY: [
        UpgradeLevel(name="Quarry", cost={}),
        UpgradeLevel(
            name="Improved Quarry",
            cost={Resource.STONE: 15, Resource.WOOD: 10},
            max_workers_bonus=1,
            gather_rate_mult=1.25,
        ),
        UpgradeLevel(
            name="Advanced Quarry",
            cost={Resource.STONE: 25, Resource.IRON: 10},
            max_workers_bonus=2,
            storage_bonus=15,
            gather_rate_mult=1.5,
        ),
    ],
    BuildingType.GATHERER: [
        UpgradeLevel(name="Gatherer", cost={}),
        UpgradeLevel(
            name="Improved Gatherer",
            cost={Resource.WOOD: 12, Resource.FIBER: 10},
            max_workers_bonus=1,
            gather_rate_mult=1.3,
        ),
    ],
    BuildingType.HABITAT: [
        UpgradeLevel(name="Habitat", cost={}),
        UpgradeLevel(
            name="Expanded Habitat",
            cost={Resource.IRON: 6, Resource.WOOD: 10, Resource.STONE: 8},
            housing_bonus=4,
        ),
    ],
    BuildingType.STORAGE: [
        UpgradeLevel(name="Storage", cost={}),
        UpgradeLevel(
            name="Large Storage",
            cost={Resource.WOOD: 25, Resource.STONE: 15},
            storage_bonus=100,
        ),
    ],
    BuildingType.REFINERY: [
        UpgradeLevel(name="Refinery", cost={}),
        UpgradeLevel(
            name="Advanced Refinery",
            cost={Resource.IRON: 12, Resource.COPPER: 8, Resource.STONE: 10},
            max_workers_bonus=1,
            gather_rate_mult=1.4,
            storage_bonus=10,
        ),
    ],
    BuildingType.FARM: [
        UpgradeLevel(name="Farm", cost={}),
        UpgradeLevel(
            name="Irrigated Farm",
            cost={Resource.WOOD: 15, Resource.STONE: 10, Resource.FIBER: 8},
            max_workers_bonus=1,
            gather_rate_mult=1.3,
            storage_bonus=15,
        ),
    ],
    BuildingType.WALL: [
        UpgradeLevel(name="Wall", cost={}),
        UpgradeLevel(
            name="Reinforced Wall",
            cost={Resource.STONE: 12, Resource.IRON: 4},
        ),
    ],
}


def max_level(btype: BuildingType) -> int:
    """Return the highest upgrade level for a building type (0 if not upgradeable)."""
    chain = UPGRADE_CHAINS.get(btype)
    if chain is None:
        return 0
    return len(chain) - 1


def get_level_info(btype: BuildingType, level: int) -> UpgradeLevel | None:
    """Return the ``UpgradeLevel`` for a given building type and level."""
    chain = UPGRADE_CHAINS.get(btype)
    if chain is None or level < 0 or level >= len(chain):
        return None
    return chain[level]


def next_upgrade(building: Building) -> UpgradeLevel | None:
    """Return the next ``UpgradeLevel`` if one exists, else ``None``."""
    chain = UPGRADE_CHAINS.get(building.type)
    if chain is None:
        return None
    next_lvl = getattr(building, "upgrade_level", 0) + 1
    if next_lvl >= len(chain):
        return None
    return chain[next_lvl]


def can_upgrade(building: Building, inventory) -> bool:
    """Check if the building can be upgraded (has next level and player can afford it)."""
    info = next_upgrade(building)
    if info is None:
        return False
    for res, amount in info.cost.items():
        if inventory[res] < amount:
            return False
    return True


def apply_upgrade(building: Building, inventory) -> bool:
    """Upgrade a building in-place.  Deducts cost and adjusts stats.

    Returns ``True`` on success, ``False`` if upgrade is not possible.
    """
    info = next_upgrade(building)
    if info is None:
        return False
    # Check cost
    for res, amount in info.cost.items():
        if inventory[res] < amount:
            return False
    # Deduct cost
    for res, amount in info.cost.items():
        inventory.spend(res, amount)
    # Apply stat bonuses
    current_level = getattr(building, "upgrade_level", 0)
    new_level = current_level + 1
    building.upgrade_level = new_level  # type: ignore[attr-defined]
    # Adjust storage capacity
    building.storage_capacity = (
        BUILDING_STORAGE_CAPACITY.get(building.type, 0)
        + sum(
            lvl.storage_bonus
            for lvl in UPGRADE_CHAINS[building.type][: new_level + 1]
        )
    )
    return True


def effective_max_workers(building: Building) -> int:
    """Return the effective max workers including upgrade bonuses."""
    base = BUILDING_MAX_WORKERS.get(building.type, 0)
    chain = UPGRADE_CHAINS.get(building.type)
    if chain is None:
        return base
    level = getattr(building, "upgrade_level", 0)
    bonus = sum(chain[i].max_workers_bonus for i in range(level + 1))
    return base + bonus


def effective_housing(building: Building) -> int:
    """Return the effective housing capacity including upgrade bonuses."""
    base = BUILDING_HOUSING.get(building.type, 0)
    chain = UPGRADE_CHAINS.get(building.type)
    if chain is None:
        return base
    level = getattr(building, "upgrade_level", 0)
    bonus = sum(chain[i].housing_bonus for i in range(level + 1))
    return base + bonus


def effective_gather_mult(building: Building) -> float:
    """Return the cumulative gather rate multiplier for the building's upgrade level."""
    chain = UPGRADE_CHAINS.get(building.type)
    if chain is None:
        return 1.0
    level = getattr(building, "upgrade_level", 0)
    mult = 1.0
    for i in range(1, level + 1):
        mult *= chain[i].gather_rate_mult
    return mult
