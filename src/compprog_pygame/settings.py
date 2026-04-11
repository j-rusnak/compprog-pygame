from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class GameSettings:
    title: str = "Physics Tetris"
    width: int = 600
    height: int = 700
    fps: int = 60

    # Play-area grid (10 columns x 20 rows like classic Tetris)
    columns: int = 10
    rows: int = 20
    cell_size: int = 36  # pixels per cell

    # Physics
    gravity: float = 765.0  # pixels/s² downward
    spawn_interval: float = 2.0  # seconds between new pieces
    physics_steps: int = 10  # sub-steps per frame for stability

    # Row clear
    row_fill_threshold: float = 0.90  # fraction of row width that counts as "full"


PROJECT_ROOT = Path(__file__).resolve().parents[2]
ASSET_DIR = PROJECT_ROOT / "assets"
DEFAULT_SETTINGS = GameSettings()