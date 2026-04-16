"""Hex Colony — a survival logistics game on a hexagonal grid.

After crash-landing on a re-evolved Earth, survivors must scavenge
resources and rebuild using advanced technology remnants.

Importing this module auto-registers the game in the central registry.
"""

from __future__ import annotations

import pygame

from compprog_pygame.game_registry import GameInfo, register
from compprog_pygame.games.hex_colony.game import Game
from compprog_pygame.games.hex_colony.menu import HexColonyMenu
from compprog_pygame.games.hex_colony.settings import HexColonySettings


def _launch(screen: pygame.Surface, clock: pygame.time.Clock) -> None:
    """Show the menu, then run the Hex Colony game with the chosen seed."""
    while True:
        menu = HexColonyMenu(screen.get_width(), screen.get_height())
        result = menu.run(screen, clock)
        if result is None:
            return  # player pressed Escape → back to game-select

        from dataclasses import replace
        settings = replace(HexColonySettings(), world_radius=result.world_radius)
        game = Game(settings, seed=result.seed)
        game.run(screen, clock)

        if game.quit_to_desktop:
            raise SystemExit
        # Return to main menu → loop back


register(
    GameInfo(
        name="Hex Colony",
        description="Survive on a re-evolved Earth after your spaceship crash-lands",
        color=(120, 140, 170),
        launch=_launch,
    )
)
