"""Resource-supply priority UI: bottom-bar tab + drag-drop overlay.

Mirror of :mod:`ui_demand_priority` operating on
:attr:`Network.supply_priority` / :attr:`Network.supply_auto`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from compprog_pygame.games.hex_colony.ui_priority_common import (
    PriorityOverlayBase,
    PrioritySpec,
    PriorityTabContent,
)

if TYPE_CHECKING:
    from compprog_pygame.games.hex_colony.buildings import Building
    from compprog_pygame.games.hex_colony.resources import Resource
    from compprog_pygame.games.hex_colony.world import World


def _building_supply_resources(
    b: "Building", world: "World",
) -> list["Resource"]:
    sup = world._building_supply(b)
    return [r for r, amt in sup.items() if amt > 1e-3]


_SUPPLY_SPEC = PrioritySpec(
    kind="supply",
    title_overlay="Edit Resource Supply",
    edit_btn_label="Edit Supply",
    empty_message="No buildings supply resources yet.",
    get_tiers=lambda net: net.supply_priority,
    set_tiers=lambda net, tiers: setattr(net, "supply_priority", tiers),
    get_auto=lambda net: net.supply_auto,
    set_auto=lambda net, v: setattr(net, "supply_auto", v),
    get_resources=_building_supply_resources,
    auto_recompute=lambda world, members: world._auto_supply_tiers(members),
)


class SupplyPriorityTabContent(PriorityTabContent):
    def __init__(self) -> None:
        super().__init__(_SUPPLY_SPEC)


class SupplyPriorityOverlay(PriorityOverlayBase):
    def __init__(self) -> None:
        super().__init__(_SUPPLY_SPEC)


__all__ = ["SupplyPriorityOverlay", "SupplyPriorityTabContent"]
