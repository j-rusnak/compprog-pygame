"""Hex Colony — a survival logistics game on a hexagonal grid.

After crash-landing on a re-evolved Earth, survivors must scavenge
resources and rebuild using advanced technology remnants.

Importing this module auto-registers the game in the central registry.
"""

from __future__ import annotations

import threading

import pygame

from compprog_pygame.game_registry import GameInfo, register
from compprog_pygame.games.hex_colony.cutscene import (
    fade_to_black,
    run_cutscene,
    run_loading_screen,
)
from compprog_pygame.games.hex_colony.game import Game
from compprog_pygame.games.hex_colony.menu import HexColonyMenu
from compprog_pygame.games.hex_colony.settings import HexColonySettings
from compprog_pygame.games.hex_colony.world import World


def _launch(screen: pygame.Surface, clock: pygame.time.Clock) -> None:
    """Show the menu, then run the Hex Colony game with the chosen seed."""
    while True:
        menu = HexColonyMenu(screen.get_width(), screen.get_height())
        result = menu.run(screen, clock)
        if result is None:
            return  # player pressed Escape → back to game-select

        from dataclasses import replace
        settings = replace(HexColonySettings(), world_radius=result.world_radius)

        # Generate the world on a background thread while the intro
        # cutscene plays, so the player never sits on a black screen.
        gen_state: dict[str, object] = {
            "progress": 0.0,
            "label": "Carving terrain",
        }

        def _on_progress(fraction: float, label: str) -> None:
            # Plain dict assignment is atomic enough for our use —
            # the loading screen reads these from the main thread.
            gen_state["progress"] = float(fraction)
            gen_state["label"] = label

        def _worker() -> None:
            try:
                gen_state["world"] = World.generate(
                    settings, seed=result.seed,
                    progress_callback=_on_progress,
                )
            except BaseException as exc:  # noqa: BLE001 — rethrown on main thread
                gen_state["error"] = exc

        thread = threading.Thread(target=_worker, daemon=True)
        thread.start()

        # Quick fade from the menu to black so the cutscene's own fade-in
        # picks up cleanly from a black screen.
        if not fade_to_black(screen, clock, duration=0.4):
            thread.join()
            raise SystemExit

        completed = run_cutscene(screen, clock)
        if not completed:
            # Player closed the window during the cutscene — wait for
            # the worker so we don't leak it, then propagate the quit.
            thread.join()
            raise SystemExit

        # The cutscene finishes on its own schedule.  Always show the
        # loading screen briefly afterward so the player gets visible
        # feedback (instead of just sitting on a black screen) — it
        # exits as soon as the world is ready.
        def _world_ready() -> bool:
            return "world" in gen_state or "error" in gen_state

        def _get_progress() -> float:
            return float(gen_state.get("progress", 0.0))

        def _get_label() -> str:
            return str(gen_state.get("label", ""))

        if not run_loading_screen(
            screen, clock, _world_ready,
            progress=_get_progress, label=_get_label,
        ):
            thread.join()
            raise SystemExit

        # Worker should be done by now; join just in case.
        thread.join()
        if "error" in gen_state:
            raise gen_state["error"]  # type: ignore[misc]
        world = gen_state["world"]  # type: ignore[assignment]

        game = Game(settings, seed=result.seed, world=world)  # type: ignore[arg-type]
        game.run(screen, clock)

        if game.quit_to_desktop:
            raise SystemExit
        # Return to main menu → loop back


register(
    GameInfo(
        name="Hex Colony",
        description="Survive on a re-evolved Earth after your spaceship crash-lands",
        color=(120, 140, 170),
        launch=_launch,
    )
)
