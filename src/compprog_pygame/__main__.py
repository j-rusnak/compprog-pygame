"""Entry point for the compprog-pygame game collection."""

import sys
from pathlib import Path

import pygame

from compprog_pygame.audio import music
from compprog_pygame.settings import DEFAULT_SETTINGS

# Import every game sub-package so they register with the game registry.
# physics_tetris is intentionally not imported — RePioneer is the only
# accessible game right now.
import compprog_pygame.games.hex_colony  # noqa: F401

from compprog_pygame.home_screen import HomeScreen


def _asset_root() -> Path:
    """Return the directory that holds bundled ``assets/`` at runtime.

    PyInstaller one-file builds extract data files under ``sys._MEIPASS``;
    in a normal source checkout we walk up from this file to the repo
    root.
    """
    base = getattr(sys, "_MEIPASS", None)
    if base:
        return Path(base)
    return Path(__file__).resolve().parent.parent.parent


def _set_window_icon() -> None:
    """Load the high-res logo as the window/taskbar icon.

    The .exe icon (set by PyInstaller via ``--icon``) only controls the
    file's icon in Explorer.  The taskbar and Alt-Tab thumbnail are
    driven by ``pygame.display.set_icon``, so we have to load it
    ourselves at startup.
    """
    # Tell Windows this process is its own application, otherwise the
    # taskbar groups us under the generic "python" / PyInstaller
    # bootloader identity and shows their icon instead of ours.
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                "compprog.repioneer.1"
            )
        except Exception:
            pass

    icon_path = _asset_root() / "assets" / "sprites" / "logo1.png"
    if not icon_path.is_file():
        return
    try:
        # NOTE: don't call convert_alpha() here — it requires a display
        # mode to exist, but set_icon must run *before* set_mode for the
        # window manager to honour it.
        icon = pygame.image.load(str(icon_path))
        # Crop transparent border so the artwork fills the taskbar slot.
        bbox = icon.get_bounding_rect()
        if bbox.width and bbox.height:
            icon = icon.subsurface(bbox).copy()
        # Pygame upscales the icon for the taskbar; feed it 256×256.
        icon = pygame.transform.smoothscale(icon, (256, 256))
        pygame.display.set_icon(icon)
    except Exception as e:
        print(f"[icon] failed to set window icon: {e}")


def main() -> None:
    pygame.init()
    # Bring the audio mixer up early so the first music.play() at the
    # home screen has zero latency.  Failures (e.g. headless CI) are
    # logged and the game runs silently.
    music.init()
    try:
        # set_icon must be called *before* the first set_mode for the
        # window manager to honour it.
        _set_window_icon()
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
        music.shutdown()
        pygame.quit()


if __name__ == "__main__":
    main()