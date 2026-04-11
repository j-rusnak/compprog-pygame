from dataclasses import dataclass, replace
from pathlib import Path


@dataclass(frozen=True, slots=True)
class GameSettings:
    title: str = "Physics Tetris"
    width: int = 900
    height: int = 800
    fps: int = 60

    # Play-area grid (10 columns x 20 rows like classic Tetris)
    columns: int = 10
    rows: int = 20
    cell_size: int = 36  # pixels per cell

    # Physics
    gravity: float = 765.0  # pixels/s² downward
    spawn_interval: float = 3.5  # seconds between new pieces
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
        spawn_interval=3.5,
        line_lifetime=0.5,
        random_spawn_x=False,
    )


def hard_settings() -> GameSettings:
    return GameSettings(
        gravity=765.0,
        spawn_interval=3.5 / 1.5,
        line_lifetime=0.3,
        random_spawn_x=True,
    )


PROJECT_ROOT = Path(__file__).resolve().parents[2]
ASSET_DIR = PROJECT_ROOT / "assets"
DEFAULT_SETTINGS = GameSettings()