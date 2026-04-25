from dataclasses import dataclass
from pathlib import Path
import sys


@dataclass(frozen=True, slots=True)
class GameSettings:
    title: str = "CompProg Games"
    # 16:9 aspect ratio so cutscene art and other 16:9 assets render
    # without stretching at the default size.
    width: int = 1280
    height: int = 720
    fps: int = 60

    # Play-area grid (10 columns x 20 rows like classic Tetris)
    columns: int = 10
    rows: int = 20
    cell_size: int = 36  # pixels per cell

    # Physics
    gravity: float = 765.0  # pixels/s² downward
    spawn_interval: float = 5.0  # seconds between new pieces
    physics_steps: int = 20  # sub-steps per frame for stability
    random_spawn_x: bool = True  # spawn across full width vs centre cluster

    # Mouse-drawn lines
    line_lifetime: float = 1.02  # seconds before each segment disappears
    line_thickness: float = 3.0  # collision radius of drawn segments

    # Row clear
    row_fill_threshold: float = 1.0  # fraction of row width that counts as "full"


def easy_settings() -> GameSettings:
    return GameSettings(
        gravity=765.0 * 0.8,
        spawn_interval=5.0,
        line_lifetime=0.5,
        random_spawn_x=False,
    )


def hard_settings() -> GameSettings:
    return GameSettings(
        gravity=765.0,
        spawn_interval=5.0 / 1.5,
        line_lifetime=0.3,
        random_spawn_x=True,
    )


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _resolve_asset_dir() -> Path:
    """Locate the ``assets/`` folder for both source runs and frozen builds.

    PyInstaller one-file builds extract bundled data files to a temp
    directory exposed as ``sys._MEIPASS``; ``--add-data assets;assets``
    places them at ``<_MEIPASS>/assets``.  When running from source
    (or as an editable install), the assets sit next to the
    repository root at ``<PROJECT_ROOT>/assets``.
    """
    # Frozen / PyInstaller bundle.
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        bundled = Path(meipass) / "assets"
        if bundled.is_dir():
            return bundled
    # Next to the executable (one-folder PyInstaller build).
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        sibling = exe_dir / "assets"
        if sibling.is_dir():
            return sibling
    # Source / dev install.
    return PROJECT_ROOT / "assets"


ASSET_DIR = _resolve_asset_dir()
DEFAULT_SETTINGS = GameSettings()