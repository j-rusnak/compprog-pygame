"""Faction framework for Hex Colony.

Defines the two factions:

- **SURVIVOR** — the player's faction. Uses futuristic buildings
  (camp, habitat, etc.) and advanced technology.
- **PRIMITIVE** — AI-controlled enemies. Uses primitive structures
  (houses / huts) and organic materials.

This module provides the ``Faction`` enum and per-faction metadata.
AI behaviour will be added in a future module.
"""

from __future__ import annotations

from enum import Enum, auto

from compprog_pygame.games.hex_colony.buildings import BuildingType


class Faction(Enum):
    SURVIVOR = auto()   # player faction — futuristic tech
    PRIMITIVE = auto()   # AI enemy — primitive huts, tribal


# Buildings that belong to each faction
FACTION_BUILDINGS: dict[Faction, frozenset[BuildingType]] = {
    Faction.SURVIVOR: frozenset({
        BuildingType.CAMP,
        BuildingType.HABITAT,
        BuildingType.PATH,
        BuildingType.BRIDGE,
        BuildingType.WOODCUTTER,
        BuildingType.QUARRY,
        BuildingType.GATHERER,
        BuildingType.STORAGE,
        BuildingType.REFINERY,
        BuildingType.MINING_MACHINE,
        BuildingType.FARM,
        BuildingType.WELL,
        BuildingType.WALL,
    }),
    Faction.PRIMITIVE: frozenset({
        BuildingType.HOUSE,
    }),
}


def faction_for_building(btype: BuildingType) -> Faction:
    """Return which faction a building type belongs to."""
    for faction, buildings in FACTION_BUILDINGS.items():
        if btype in buildings:
            return faction
    return Faction.SURVIVOR
