"""Per-faction colony state.

Originally Hex Colony had a single global ``Inventory``,
``BuildingInventory``, ``TechTree``, and ``TierTracker`` hanging off
``World``.  That made it impossible for AI rivals ("clankers") to
play the game alongside the player without stealing resources from
the same pool.

A :class:`ColonyState` bundles every piece of run-time progression
state that *belongs to a single faction* (player or AI).  The world
holds one of these per faction in ``World.colonies``, keyed by the
``faction`` string also stamped on every :class:`Building` and
:class:`Network` that faction owns.

Convenience aliases on ``World`` (``world.inventory``,
``world.building_inventory`` …) point at the *player* colony so
existing UI code keeps working untouched.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from compprog_pygame.games.hex_colony.hex_grid import HexCoord
from compprog_pygame.games.hex_colony.resources import (
    BuildingInventory,
    Inventory,
    Resource,
)
from compprog_pygame.games.hex_colony.tech_tree import TechTree, TierTracker


@dataclass
class ColonyState:
    """All state owned by one faction.

    *faction_id* is the stable string used everywhere else (e.g.
    ``"SURVIVOR"`` for the player, ``"PRIMITIVE_0"``, ``"PRIMITIVE_1"``
    for clankers).  *camp_coord* is the hex of the faction's home
    base — the player's CAMP, or a clanker's TRIBAL_CAMP — and acts
    as the BFS root for housing connectivity for that colony.
    """
    faction_id: str
    camp_coord: HexCoord
    is_player: bool = False
    inventory: Inventory = field(default_factory=Inventory)
    building_inventory: BuildingInventory = field(default_factory=BuildingInventory)
    tech_tree: TechTree = field(default_factory=TechTree)
    tier_tracker: TierTracker = field(default_factory=TierTracker)
    # Cumulative resources produced (harvested or crafted) by this
    # colony's buildings.  Used by the per-faction tier tracker so
    # spending a resource doesn't undo "gather X total" requirements.
    total_produced: dict[Resource, float] = field(
        default_factory=lambda: {r: 0.0 for r in Resource}
    )
    # Mirror of the legacy ``world._tech_research_count`` field —
    # ``TierTracker.check_requirements`` reads this for the
    # "research_count" tier requirement.  Updated each tick from
    # ``tech_tree.researched_count``.
    tech_research_count: int = 0
