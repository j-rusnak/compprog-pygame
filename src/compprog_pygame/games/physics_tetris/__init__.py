"""Physics Tetris — the original falling-blocks game with pymunk physics.

Importing this module auto-registers the game in the central registry.
"""

from __future__ import annotations

import pygame

from compprog_pygame.game_registry import GameInfo, register
from compprog_pygame.games.physics_tetris.game import Game
from compprog_pygame.settings import easy_settings, hard_settings


def _launch(screen: pygame.Surface, clock: pygame.time.Clock) -> None:
    """Run the Physics Tetris difficulty picker then the game loop."""
    from compprog_pygame.games.physics_tetris.difficulty_menu import DifficultyMenu

    menu = DifficultyMenu(screen.get_width(), screen.get_height())
    settings = menu.run(screen, clock)
    if settings is None:
        return  # user pressed Escape → back to game-select

    game = Game(settings)
    game.clock = clock
    game.screen = pygame.display.get_surface()
    game.run()


register(
    GameInfo(
        name="Physics Tetris",
        description="Draw lines to redirect falling blocks",
        color=(80, 160, 255),
        launch=_launch,
    )
)
