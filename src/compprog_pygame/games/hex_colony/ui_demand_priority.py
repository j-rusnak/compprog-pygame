"""Resource-demand priority UI: bottom-bar tab + drag-drop overlay.

Thin wrappers around :mod:`ui_priority_common` configured to operate
on :attr:`Network.demand_priority` /
:attr:`Network.demand_auto`.
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
    from compprog_pygame.games.hex_colony.world import Network, World


def _building_demand_resources(
    b: "Building", world: "World",
) -> list["Resource"]:
    """Return the list of Resources this building currently demands.

    Uses the same private helper that the logistics scheduler does so
    that the UI matches the simulator exactly.
    """
    demand = world._building_demand(b)
    return [r for r, need in demand.items() if need > 1e-3]


_DEMAND_SPEC = PrioritySpec(
    kind="demand",
    title_overlay="Edit Resource Demand",
    edit_btn_label="Edit Demand",
    empty_message="No buildings demand resources yet.",
    get_tiers=lambda net: net.demand_priority,
    set_tiers=lambda net, tiers: setattr(net, "demand_priority", tiers),
    get_auto=lambda net: net.demand_auto,
    set_auto=lambda net, v: setattr(net, "demand_auto", v),
    get_resources=_building_demand_resources,
    auto_recompute=lambda world, members: world._auto_demand_tiers(members),
)


class DemandPriorityTabContent(PriorityTabContent):
    def __init__(self) -> None:
        super().__init__(_DEMAND_SPEC)


class DemandPriorityOverlay(PriorityOverlayBase):
    def __init__(self) -> None:
        super().__init__(_DEMAND_SPEC)


__all__ = ["DemandPriorityOverlay", "DemandPriorityTabContent"]
