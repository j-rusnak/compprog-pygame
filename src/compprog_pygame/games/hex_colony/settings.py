"""Game-specific settings for Hex Colony."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class HexColonySettings:
    # Display
    hex_size: int = 32  # radius of each hex in pixels (center to vertex)
    fps: int = 60

    # Starting resources
    start_wood: int = 50
    start_fiber: int = 20
    start_stone: int = 30
    start_food: int = 80

    # Starting people
    start_population: int = 5

    # World generation
    world_radius: int = 20  # hex radius of the generated map

    # People movement
    person_speed: float = 60.0  # pixels per second

    # Resource gathering rates (units per second per worker)
    gather_wood: float = 1.0
    gather_fiber: float = 0.8
    gather_stone: float = 0.6
    gather_food: float = 1.2

    # Food consumption per person per second
    food_consumption: float = 0.02
