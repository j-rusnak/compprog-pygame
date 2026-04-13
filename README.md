# compprog-pygame

A small Pygame mini-game collection with a home screen, currently featuring a playable Physics Tetris prototype and tooling to build a Windows executable.

The project uses `pygame-ce` (imported as `pygame`) plus `pymunk` for physics.

## Current status

- Home screen that lists registered mini-games
- Physics Tetris is fully wired and playable
- Physics Tetris includes an Easy/Hard difficulty selector
- Portal Tetris files exist as placeholders but are not currently registered in the menu
- PyInstaller build script is included for Windows executable export

## Project layout

```text
.
|-- .vscode/
|   |-- launch.json
|   `-- tasks.json
|-- assets/
|   |-- audio/
|   |-- fonts/
|   `-- images/
|-- src/
|   `-- compprog_pygame/
|       |-- __main__.py
|       |-- game_registry.py
|       |-- home_screen.py
|       |-- settings.py
|       `-- games/
|           |-- physics_tetris/
|           `-- portal_tetris/  (scaffold only)
|-- tests/
|   `-- test_settings.py
|-- tools/
|   `-- build.ps1
|-- CompProgGame.spec
`-- pyproject.toml
```

## Setup (PowerShell)

If you do not already have a local virtual environment:

```powershell
python -m venv .venv
```

Activate and install dependencies:

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e .[dev]
```

## Run the game

From the repository root:

```powershell
python -m compprog_pygame
```

You can also run:

- VS Code launch config: `Run Pygame Project`
- VS Code task: `Run Game`

## Controls

- Home screen: click a game card to launch, press `Esc` to quit
- Physics Tetris menu: choose difficulty, click `Play`, press `Esc` to return
- Physics Tetris gameplay: click and drag to draw temporary guide lines, press `Esc` to go back to the home screen

## Run tests

```powershell
python -m pytest
```

Current tests are lightweight sanity checks around settings and asset-path wiring.

## Build a Windows executable

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\build.ps1
```

This runs PyInstaller in one-file windowed mode and includes the `assets` directory.

Expected output:

- `dist/CompProgGame.exe`

## Notes

- Python requirement: `>=3.11`
- Runtime dependencies: `pygame-ce`, `pymunk`
- Dev dependencies include `pyinstaller` and `pytest`