"""Generate placeholder sprite PNGs from the current procedural drawing code.

Run this script to create initial sprite assets::

    python -m compprog_pygame.games.hex_colony.generate_sprites

Sprites are saved to ``assets/sprites/`` and can be replaced with custom
pixel art of the same dimensions.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure src is on path
_project_root = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(_project_root / "src"))

import pygame

from compprog_pygame.games.hex_colony.render_buildings import (
    draw_camp,
    draw_gatherer,
    draw_habitat,
    draw_house,
    draw_overcrowded,
    draw_quarry,
    draw_storage,
    draw_woodcutter,
    draw_refinery,
    draw_farm,
    draw_well,
    draw_bridge,
    draw_wall,
    draw_turret,
    draw_trap,
    draw_enemy,
    draw_tribal_camp,
    draw_pipe,
    draw_fluid_tank,
    draw_mining_machine,
    draw_workshop,
    draw_forge,
    draw_assembler,
    draw_research_center,
    draw_chemical_plant,
    draw_conveyor,
    draw_solar_array,
    draw_rocket_silo,
    draw_oil_drill,
    draw_oil_refinery,
    draw_ancient_tower,
)
from compprog_pygame.games.hex_colony.render_overlays import (
    draw_bush,
    draw_crystal,
    draw_grass,
    draw_rock,
    draw_tree,
    draw_ruin,
)
from compprog_pygame.games.hex_colony.overlay import (
    OverlayBush,
    OverlayCrystal,
    OverlayGrassTuft,
    OverlayRock,
    OverlayRuin,
    OverlayTree,
)
from compprog_pygame.games.hex_colony.sprites import SPRITE_DIR, sprites


# Sprite canvas size (pixels). Buildings are drawn at hex_radius=24, zoom=1.0
_SIZE = 64
_HALF = _SIZE // 2
_R = 24  # building radius parameter
_Z = 1.0  # zoom


def _make_surface() -> pygame.Surface:
    return pygame.Surface((_SIZE, _SIZE), pygame.SRCALPHA)


def _save(surf: pygame.Surface, *parts: str) -> None:
    path = SPRITE_DIR.joinpath(*parts)
    path.parent.mkdir(parents=True, exist_ok=True)
    pygame.image.save(surf, str(path))
    print(f"  saved {path.relative_to(SPRITE_DIR)}")


def _generate_buildings() -> None:
    print("Generating building sprites...")

    s = _make_surface()
    draw_camp(s, _HALF, _HALF, _R, _Z)
    _save(s, "buildings", "camp.png")

    s = _make_surface()
    draw_house(s, _HALF, _HALF, _R, _Z)
    _save(s, "buildings", "house.png")

    s = _make_surface()
    draw_habitat(s, _HALF, _HALF, _R, _Z)
    _save(s, "buildings", "habitat.png")

    s = _make_surface()
    draw_woodcutter(s, _HALF, _HALF, _R, _Z)
    _save(s, "buildings", "woodcutter.png")

    s = _make_surface()
    draw_quarry(s, _HALF, _HALF, _R, _Z)
    _save(s, "buildings", "quarry.png")

    s = _make_surface()
    draw_gatherer(s, _HALF, _HALF, _R, _Z)
    _save(s, "buildings", "gatherer.png")

    s = _make_surface()
    draw_storage(s, _HALF, _HALF, _R, _Z)
    _save(s, "buildings", "storage.png")

    s = _make_surface()
    draw_overcrowded(s, _HALF, _HALF, _R, _Z)
    _save(s, "buildings", "overcrowded.png")

    s = _make_surface()
    draw_refinery(s, _HALF, _HALF, _R, _Z)
    _save(s, "buildings", "refinery.png")

    s = _make_surface()
    draw_farm(s, _HALF, _HALF, _R, _Z)
    _save(s, "buildings", "farm.png")

    s = _make_surface()
    draw_well(s, _HALF, _HALF, _R, _Z)
    _save(s, "buildings", "well.png")

    # Bridge uses the path-like interface but we render a standalone tile
    s = _make_surface()
    draw_bridge(s, _HALF, _HALF, _R, _Z, [], 0, 0)
    _save(s, "buildings", "bridge.png")

    # Wall uses the path-like interface
    s = _make_surface()
    draw_wall(s, _HALF, _HALF, _R, _Z, [], 0, 0)
    _save(s, "buildings", "wall.png")

    # Defense buildings.
    s = _make_surface()
    draw_turret(s, _HALF, _HALF, _R, _Z)
    _save(s, "buildings", "turret.png")

    s = _make_surface()
    draw_trap(s, _HALF, _HALF, _R, _Z)
    _save(s, "buildings", "trap.png")

    # Tribal camp (enemy spawn).
    s = _make_surface()
    draw_tribal_camp(s, _HALF, _HALF, _R, _Z)
    _save(s, "buildings", "tribal_camp.png")

    # Crafting / production buildings.
    s = _make_surface()
    draw_workshop(s, _HALF, _HALF, _R, _Z)
    _save(s, "buildings", "workshop.png")

    s = _make_surface()
    draw_forge(s, _HALF, _HALF, _R, _Z)
    _save(s, "buildings", "forge.png")

    s = _make_surface()
    draw_assembler(s, _HALF, _HALF, _R, _Z)
    _save(s, "buildings", "assembler.png")

    s = _make_surface()
    draw_chemical_plant(s, _HALF, _HALF, _R, _Z)
    _save(s, "buildings", "chemical_plant.png")

    # Research Center is much taller than other buildings; render onto
    # a larger canvas so the antenna/dish aren't clipped.
    big_size = _SIZE * 2
    big_half = big_size // 2
    s = pygame.Surface((big_size, big_size), pygame.SRCALPHA)
    draw_research_center(s, big_half, big_half, _R, _Z)
    _save(s, "buildings", "research_center.png")

    # Mining / extraction.
    s = _make_surface()
    draw_mining_machine(s, _HALF, _HALF, _R, _Z)
    _save(s, "buildings", "mining_machine.png")

    s = _make_surface()
    draw_oil_drill(s, _HALF, _HALF, _R, _Z)
    _save(s, "buildings", "oil_drill.png")

    s = _make_surface()
    draw_oil_refinery(s, _HALF, _HALF, _R, _Z)
    _save(s, "buildings", "oil_refinery.png")

    # Fluid network.
    s = _make_surface()
    draw_pipe(s, _HALF, _HALF, _R, _Z, [], 0, 0)
    _save(s, "buildings", "pipe.png")

    s = _make_surface()
    draw_fluid_tank(s, _HALF, _HALF, _R, _Z)
    _save(s, "buildings", "fluid_tank.png")

    # Logistics.
    s = _make_surface()
    draw_conveyor(s, _HALF, _HALF, _R, _Z, None, 0, 0)
    _save(s, "buildings", "conveyor.png")

    # Power.
    s = _make_surface()
    draw_solar_array(s, _HALF, _HALF, _R, _Z)
    _save(s, "buildings", "solar_array.png")

    # Endgame: rocket silo (rocket extends well above the hex; use a
    # larger canvas so the nose cone isn't clipped).
    s = pygame.Surface((_SIZE, _SIZE * 2), pygame.SRCALPHA)
    draw_rocket_silo(s, _HALF, _SIZE + _HALF // 2, _R, _Z)
    _save(s, "buildings", "rocket_silo.png")

    # Ancient threat tower.
    s = pygame.Surface((_SIZE, _SIZE * 2), pygame.SRCALPHA)
    draw_ancient_tower(s, _HALF, _SIZE + _HALF // 2, _R, _Z)
    _save(s, "buildings", "ancient_tower.png")


def _generate_overlays() -> None:
    print("Generating overlay sprites...")

    # Clear sprite manager so draw_* functions use procedural fallback
    # instead of blitting existing (possibly empty) sprites
    sprites._sprites.clear()
    sprites._loaded = False

    # Tree — canopy style
    tree_canopy = OverlayTree(
        wx=0, wy=0,
        trunk_h=12, crown_rx=8, crown_ry=6,
        crown_color=(30, 100, 35),
        trunk_color=(90, 65, 30),
        highlight_color=(60, 140, 65),
        style="canopy",
    )
    s = _make_surface()
    draw_tree(s, tree_canopy, _HALF, _HALF + 10, _Z, 1)
    _save(s, "overlays", "tree_canopy.png")

    # Tree — conifer style
    tree_conifer = OverlayTree(
        wx=0, wy=0,
        trunk_h=10, crown_rx=6, crown_ry=10,
        crown_color=(20, 80, 28),
        trunk_color=(90, 65, 30),
        highlight_color=(40, 120, 50),
        style="conifer",
    )
    s = _make_surface()
    draw_tree(s, tree_conifer, _HALF, _HALF + 10, _Z, 1)
    _save(s, "overlays", "tree_conifer.png")

    # Tree — round style
    tree_round = OverlayTree(
        wx=0, wy=0,
        trunk_h=8, crown_rx=7, crown_ry=7,
        crown_color=(40, 110, 40),
        trunk_color=(90, 65, 30),
        highlight_color=(70, 150, 70),
        style="round",
    )
    s = _make_surface()
    draw_tree(s, tree_round, _HALF, _HALF + 8, _Z, 1)
    _save(s, "overlays", "tree_round.png")

    # Rock
    rock = OverlayRock(
        wx=0, wy=0,
        w=6, h=4,
        color=(140, 138, 130),
        highlight_color=(180, 178, 170),
    )
    s = _make_surface()
    draw_rock(s, rock, _HALF, _HALF, _Z, 1)
    _save(s, "overlays", "rock.png")

    # Bush
    bush = OverlayBush(
        wx=0, wy=0,
        radius=5,
        color=(50, 120, 45),
        berry_color=(200, 60, 60),
    )
    s = _make_surface()
    draw_bush(s, bush, _HALF, _HALF, _Z, 1)
    _save(s, "overlays", "bush.png")

    # Grass tuft
    grass = OverlayGrassTuft(
        wx=0, wy=0,
        h=5,
        color=(80, 160, 60),
    )
    s = _make_surface()
    draw_grass(s, grass, _HALF, _HALF, _Z, 1)
    _save(s, "overlays", "grass.png")

    # Crystal — iron
    crystal_iron = OverlayCrystal(
        wx=0, wy=0,
        h=16, w=7,
        color=(160, 100, 70),
        highlight_color=(200, 140, 100),
        angle=0.2,
    )
    s = _make_surface()
    draw_crystal(s, crystal_iron, _HALF, _HALF + 8, _Z, 1)
    _save(s, "overlays", "crystal_iron.png")

    # Crystal — copper
    crystal_copper = OverlayCrystal(
        wx=0, wy=0,
        h=16, w=7,
        color=(70, 160, 110),
        highlight_color=(110, 200, 150),
        angle=-0.15,
    )
    s = _make_surface()
    draw_crystal(s, crystal_copper, _HALF, _HALF + 8, _Z, 1)
    _save(s, "overlays", "crystal_copper.png")

    # Ruins — three variants
    for variant in range(3):
        ruin = OverlayRuin(
            wx=0, wy=0,
            variant=variant,
            color=(120, 110, 95),
            highlight_color=(160, 150, 130),
            coord=(0, 0),
        )
        s = _make_surface()
        draw_ruin(s, ruin, _HALF, _HALF, _Z, 1)
        _save(s, "overlays", f"ruin_{variant}.png")


def _generate_people() -> None:
    print("Generating people sprites...")

    from compprog_pygame.games.hex_colony.render_utils import (
        PERSON_COLOR,
        PERSON_GATHER_COLOR,
        PERSON_HAIR,
        PERSON_SKIN,
        _darken,
    )

    def _draw_person(surface: pygame.Surface, cx: int, cy: int, body_color: tuple) -> None:
        iz = 1
        head_r = 3
        body_h = 4
        leg_h = 2
        body_w = 1
        leg_col = _darken(body_color, 0.6)
        pygame.draw.line(surface, leg_col, (cx - body_w, cy - leg_h), (cx - body_w, cy), iz)
        pygame.draw.line(surface, leg_col, (cx + body_w, cy - leg_h), (cx + body_w, cy), iz)
        pygame.draw.rect(surface, body_color,
                         (cx - body_w - iz, cy - leg_h - body_h,
                          body_w * 2 + iz * 2, body_h))
        head_y = cy - body_h - leg_h - head_r
        pygame.draw.circle(surface, PERSON_SKIN, (cx, head_y), head_r)
        pygame.draw.circle(surface, PERSON_HAIR, (cx, head_y - iz), head_r,
                           draw_top_left=True, draw_top_right=True)

    # Person — idle
    s = pygame.Surface((16, 24), pygame.SRCALPHA)
    _draw_person(s, 8, 18, PERSON_COLOR)
    _save(s, "people", "person_idle.png")

    # Person — gathering
    s = pygame.Surface((16, 24), pygame.SRCALPHA)
    _draw_person(s, 8, 18, PERSON_GATHER_COLOR)
    # Add gathering indicator dot
    pygame.draw.circle(s, (200, 180, 60), (12, 10), 2)
    _save(s, "people", "person_gather.png")


def _generate_enemies() -> None:
    print("Generating enemy sprites...")
    from compprog_pygame.games.hex_colony import params
    for type_name, data in params.ENEMY_TYPE_DATA.items():
        s = _make_surface()
        # Draw at higher zoom so the procedural enemy fills the canvas.
        draw_enemy(
            s, _HALF, _HALF,
            type_name, data["color"], data["radius_px"], 1.6,
        )
        _save(s, "enemies", f"{data['sprite']}.png")


def main() -> None:
    pygame.init()
    # Need a display surface for convert_alpha() to work
    pygame.display.set_mode((1, 1), pygame.HIDDEN)

    _generate_buildings()
    _generate_overlays()
    _generate_people()
    _generate_enemies()

    print(f"\nAll sprites saved to {SPRITE_DIR}")
    pygame.quit()


if __name__ == "__main__":
    main()
