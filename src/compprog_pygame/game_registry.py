"""Central registry of available mini-games.

Each game is described by a :class:`GameInfo` dataclass.  The ``launch``
callable receives ``(screen, clock)`` and runs the game loop, returning
when the player exits back to the menu.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import pygame


class LaunchFn(Protocol):
    """Signature every game's launcher must satisfy."""

    def __call__(self, screen: pygame.Surface, clock: pygame.time.Clock) -> None: ...


@dataclass(frozen=True, slots=True)
class GameInfo:
    """Metadata for a single mini-game."""

    name: str  # short title shown on home screen
    description: str  # one-liner shown below the title
    color: tuple[int, int, int]  # accent colour for the card
    launch: LaunchFn  # called with (screen, clock) to run the game


# Module-level list — games register themselves at import time.
_games: list[GameInfo] = []


def register(info: GameInfo) -> None:
    """Add a game to the global list (call at module scope)."""
    _games.append(info)


def all_games() -> list[GameInfo]:
    """Return every registered game (import order)."""
    return list(_games)
