"""People (colonists) for Hex Colony.

People are the core unit — they gather resources, build, and carry goods.
Each person has a current hex position, a task assignment, and simple
interpolated movement between hexes.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import TYPE_CHECKING

from compprog_pygame.games.hex_colony.hex_grid import HexCoord, hex_to_pixel

if TYPE_CHECKING:
    from compprog_pygame.games.hex_colony.world import World


class Task(Enum):
    IDLE = auto()
    GATHER = auto()       # walking to or harvesting at a resource tile
    BUILD = auto()        # constructing a building
    HAUL = auto()         # carrying resources back to camp
    RELOCATE = auto()     # moving to a new home (house)
    COMMUTE = auto()      # walking along a path to an assigned workplace
    LOGISTICS_IDLE = auto()   # logistics worker waiting for an assignment
    LOGISTICS_PICKUP = auto() # logistics worker walking to a supply source
    LOGISTICS_DELIVER = auto()# logistics worker walking to a demand dest


@dataclass(slots=True)
class Person:
    """A single colonist."""
    id: int
    hex_pos: HexCoord           # current logical hex
    px: float = 0.0             # pixel x (interpolated)
    py: float = 0.0             # pixel y (interpolated)
    task: Task = Task.IDLE
    target_hex: HexCoord | None = None
    path: list[HexCoord] = field(default_factory=list)
    work_timer: float = 0.0     # time spent on current work action
    carry_resource: object | None = None  # (Resource, amount) tuple when hauling
    home: object | None = None  # Building reference (dwelling)
    workplace: object | None = None  # Building reference — where they currently
                                     # work.  Set only once the person has
                                     # physically arrived at the assigned
                                     # building.  Contributes to that
                                     # building's active worker count.
    workplace_target: object | None = None  # Building reference — where the
                                            # worker-priority system wants
                                            # this person to go.  While
                                            # `workplace_target != workplace`
                                            # the person is commuting.
    # Logistics state.  ``is_logistics`` is True iff the worker has been
    # assigned to the "Logistics" slot in the worker-priority menu for
    # the network containing their home.  A logistics worker ignores
    # ``workplace`` / ``workplace_target`` and instead carries items
    # between supply and demand buildings.
    is_logistics: bool = False
    # Current logistics pickup and drop-off buildings.  ``None`` when
    # the worker is between jobs (LOGISTICS_IDLE).
    logistics_src: object | None = None
    logistics_dst: object | None = None
    logistics_res: object | None = None  # Resource being transported
    logistics_amount: float = 0.0        # units currently carried

    def snap_to_hex(self, size: int) -> None:
        """Set pixel position to centre of current hex."""
        self.px, self.py = hex_to_pixel(self.hex_pos, size)


class PopulationManager:
    """Manages all people in the colony."""

    def __init__(self) -> None:
        self.people: list[Person] = []
        self._next_id = 0

    def spawn(self, coord: HexCoord, hex_size: int) -> Person:
        p = Person(id=self._next_id, hex_pos=coord)
        p.snap_to_hex(hex_size)
        # Slight random offset so people don't stack perfectly
        p.px += random.uniform(-4, 4)
        p.py += random.uniform(-4, 4)
        self._next_id += 1
        self.people.append(p)
        return p

    @property
    def count(self) -> int:
        return len(self.people)

    def idle_people(self) -> list[Person]:
        """Return idle people who have a home (available for work tasks)."""
        return [p for p in self.people if p.task == Task.IDLE and p.home is not None]

    def update(self, dt: float, world: World, hex_size: int) -> None:
        """Advance all people by *dt* seconds."""
        speed = world.settings.person_speed  # px/s
        for person in self.people:
            if person.path:
                # Move toward next hex in path
                target = person.path[0]
                tx, ty = hex_to_pixel(target, hex_size)
                dx, dy = tx - person.px, ty - person.py
                dist = math.hypot(dx, dy)
                step = speed * dt
                if dist <= step:
                    person.px, person.py = tx, ty
                    person.hex_pos = target
                    person.path.pop(0)
                    if not person.path:
                        # Arrival hooks
                        if person.task == Task.RELOCATE:
                            person.task = Task.IDLE
                        elif person.task == Task.COMMUTE:
                            target_b = person.workplace_target
                            if (target_b is not None
                                    and person.hex_pos == target_b.coord):
                                person.workplace = target_b
                                person.task = Task.GATHER
                            else:
                                # Target vanished or moved; clear.
                                person.task = Task.IDLE
                        elif person.task == Task.LOGISTICS_PICKUP:
                            # Signal to world._update_logistics to pick
                            # up from logistics_src on the next tick.
                            # The world runs after population.update so
                            # it can react to the arrived state.
                            pass
                        elif person.task == Task.LOGISTICS_DELIVER:
                            pass
                else:
                    person.px += dx / dist * step
                    person.py += dy / dist * step
