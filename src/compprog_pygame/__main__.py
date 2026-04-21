"""Entry point for the compprog-pygame game collection."""

import pygame

from compprog_pygame.settings import DEFAULT_SETTINGS

# Import every game sub-package so they register with the game registry.
# physics_tetris is intentionally not imported — RePioneer is the only
# accessible game right now.
import compprog_pygame.games.hex_colony  # noqa: F401

from compprog_pygame.home_screen import HomeScreen


def main() -> None:
    pygame.init()
    try:
        screen = pygame.display.set_mode(
            (DEFAULT_SETTINGS.width, DEFAULT_SETTINGS.height), pygame.RESIZABLE,
        )
        pygame.display.set_caption("CompProg Games")
        clock = pygame.time.Clock()

        # Loop: home screen → game → back to home screen
        while True:
            home = HomeScreen(screen.get_width(), screen.get_height())
            choice = home.run(screen, clock)
            if choice is None:
                break  # user quit

            choice.launch(screen, clock)

            # After the game returns, refresh the screen reference
            # (it may have been resized) and loop back.
            screen = pygame.display.get_surface()
    finally:
        pygame.quit()


if __name__ == "__main__":
    main()