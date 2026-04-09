from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class GameSettings:
    title: str = "CompProg Pygame"
    width: int = 1280
    height: int = 720
    fps: int = 60
    player_speed: float = 360.0
    pickup_radius: int = 16


PROJECT_ROOT = Path(__file__).resolve().parents[2]
ASSET_DIR = PROJECT_ROOT / "assets"
DEFAULT_SETTINGS = GameSettings()