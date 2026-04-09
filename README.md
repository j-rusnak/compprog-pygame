# compprog-pygame

A basic but structured Pygame starter project for building a larger game and exporting it to a Windows executable when ready.

This setup uses `pygame-ce`, which keeps the `pygame` import path but is easier to install on newer Python releases.

## What is included

- A `src`-based Python package layout
- A working Pygame game loop with a simple playable prototype
- Asset folders for images, audio, and fonts
- VS Code launch and task configuration
- PyInstaller build support for producing an `.exe`
- A small pytest smoke test

## Project layout

```text
.
|-- .vscode/
|-- assets/
|   |-- audio/
|   |-- fonts/
|   `-- images/
|-- src/
|   `-- compprog_pygame/
|-- tests/
`-- tools/
```

## First-time setup

The repository already supports a local virtual environment in `.venv`.

### PowerShell

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e .[dev]
```

## Run the game

```powershell
python -m compprog_pygame
```

You can also use the VS Code `Run Pygame Project` launch configuration or the `Run Game` task.

## Run tests

```powershell
python -m pytest
```

## Build a Windows executable

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\build.ps1
```

The executable will be written to `dist/CompProgGame.exe`.

## Next development steps

- Replace the placeholder shapes with real art and audio in `assets/`
- Split gameplay into scene, entity, and UI modules as the game grows
- Add save data, menus, and content pipelines once the core loop stabilizes