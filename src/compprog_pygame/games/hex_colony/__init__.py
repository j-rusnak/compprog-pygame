"""Hex Colony — a people-driven logistics game on a hexagonal grid.

Importing this module auto-registers the game in the central registry.
"""

from __future__ import annotations

import pygame

from compprog_pygame.game_registry import GameInfo, register
from compprog_pygame.games.hex_colony.game import Game
from compprog_pygame.games.hex_colony.settings import HexColonySettings


def _launch(screen: pygame.Surface, clock: pygame.time.Clock) -> None:
    """Run the Hex Colony game."""
    settings = HexColonySettings()
    game = Game(settings)
    game.run(screen, clock)


register(
    GameInfo(
        name="Hex Colony",
        description="Build a colony with people in a hex-grid wilderness",
        color=(200, 160, 60),
        launch=_launch,
    )
)
