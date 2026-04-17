"""Game-specific settings for Hex Colony."""

from __future__ import annotations

from dataclasses import dataclass

from compprog_pygame.games.hex_colony import params


@dataclass(frozen=True, slots=True)
class HexColonySettings:
    # Display
    hex_size: int = params.HEX_SIZE
    fps: int = params.FPS

    # Starting resources
    start_wood: int = params.START_WOOD
    start_fiber: int = params.START_FIBER
    start_stone: int = params.START_STONE
    start_food: int = params.START_FOOD

    # Starting people
    start_population: int = params.START_POPULATION

    # World generation
    world_radius: int = params.DEFAULT_WORLD_RADIUS

    # People movement
    person_speed: float = params.PERSON_SPEED

    # Resource gathering rates (units per second per worker)
    gather_wood: float = params.GATHER_RATE_WOOD
    gather_fiber: float = params.GATHER_RATE_FIBER
    gather_stone: float = params.GATHER_RATE_STONE
    gather_food: float = params.GATHER_RATE_FOOD

    # Food consumption per person per second
    food_consumption: float = params.FOOD_CONSUMPTION_PER_PERSON

    # Cheat/debug: bypass all tier, tech, and inventory gates.  When
    # enabled, any building can be placed regardless of unlock state
    # and locked content is still shown in the UI (useful for testing).
    god_mode: bool = False
