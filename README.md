# compprog-pygame

A small Pygame mini-game launcher with a home screen. The flagship game is
**Hex Colony** — a hex-grid colony / logistics sim with research, combat
against ancient machines, and ~50 distinct buildings. A secondary game,
**Physics Tetris**, is also included as a smaller self-contained
prototype.

The project is built on `pygame-ce` (imported as `pygame`) plus `pymunk`
for physics.

---

## Requirements

| Requirement | Version |
|---|---|
| Python | **3.11 or newer** (3.13+ recommended for `hex_colony`) |
| OS | Windows 10/11 (primary), Linux/macOS should work but build tooling is PowerShell-only |
| GPU | Anything that runs SDL2 — no dedicated GPU required |
| Disk | ~250 MB including the dev virtualenv |

Runtime Python packages (installed automatically by the steps below):

- `pygame-ce >= 2.5.5, < 3`
- `pymunk >= 7.0, < 8`

Optional dev packages (installed via the `[dev]` extra):

- `pyinstaller >= 6.0` — Windows executable build
- `pytest >= 8.0` — test runner

---

## First-time setup (Windows / PowerShell)

From the repository root:

```powershell
# 1. Create a virtual environment in the repo (only needed once).
python -m venv .venv

# 2. If your execution policy blocks activation scripts, allow them
#    for THIS process only (does not affect the system policy).
Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned

# 3. Activate the venv. Your prompt should now start with "(.venv)".
.\.venv\Scripts\Activate.ps1

# 4. Upgrade pip and install the project in editable mode with dev extras.
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

### Linux / macOS equivalent

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

> The `-e` flag installs in editable mode so that any code change is
> picked up the next time you run the game — no reinstall required.

---

## Running the game

With the venv active:

```powershell
python -m compprog_pygame
```

This opens the launcher's **home screen** where you can click a game
card to launch it. Press `Esc` from the home screen to quit.

### Alternative: using the VS Code task

If you opened the repo in VS Code, the **`Run Game`** task is
pre-configured (`Terminal > Run Task… > Run Game`). It sets
`PYTHONPATH=src` automatically and uses the workspace's selected
Python interpreter.

### Alternative: from the command line without activating the venv

```powershell
$env:PYTHONPATH = "src"
.\.venv\Scripts\python.exe -m compprog_pygame
```

---

## Games

### Hex Colony

Hex-grid colony sim. Crash-land, harvest resources, expand a road
network, research the tech tree, and survive periodic waves of ancient
machines awakened by your activity.

**Default keybindings (in-game):**

| Key | Action |
|---|---|
| `Esc` | Cancel current build/delete tool, or open the pause menu |
| `B` | Cycle through buildable building types |
| `X` | Toggle delete mode |
| `H` or `I` | Toggle the help overlay |
| `Tab` | Toggle sandbox mode (free resources, dev only) |
| `1` / `2` / `3` / `5` | Set sim speed: 3× / 6× / 9× / 30× |
| `F1` | Toggle god mode (dev) |
| `F2` | Cycle the enemy-spawn tool while in god mode |
| Mouse wheel | Zoom in / out |
| Middle-click drag | Pan the camera |
| Right-click | Pan the camera (alt) / cancel current tool |
| Left-click | Place / delete / select buildings, depending on the active tool |

Press **`H`** in-game at any time for the in-app help overlay; the
in-game tutorial walks you through the first few mechanics
automatically.

### Physics Tetris

A small Tetris variant where pieces fall and collide as physics bodies
(`pymunk`).

- Difficulty menu: choose **Easy** or **Hard**, click **Play**.
- In gameplay, click and drag to draw a temporary guide line.
- Press `Esc` to return to the home screen.

---

## Running the tests

```powershell
python -m pytest
```

Or, if the venv is not active:

```powershell
$env:PYTHONPATH = "src"; python -m pytest tests/ -x
```

The current test suite is intentionally small (settings + asset-path
sanity checks). New tests should live under `tests/`.

---

## Building a Windows executable

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\build.ps1
```

This invokes PyInstaller using `CompProgGame.spec`, bundling the
`assets/` directory and producing a one-file windowed executable.

Output:

- `dist/CompProgGame.exe`

The build also leaves intermediate files under `build/` which can be
deleted safely.

---

## Project layout

```text
.
├── assets/                       # Fonts, audio, images, sprites
├── docs/
│   └── HEX_COLONY_ARCHITECTURE.md  # Definitive architectural reference
├── src/
│   └── compprog_pygame/
│       ├── __main__.py           # Entry point: python -m compprog_pygame
│       ├── home_screen.py        # Game launcher
│       ├── game_registry.py      # Registered games list
│       ├── settings.py
│       └── games/
│           ├── hex_colony/       # ~50 modules — flagship game
│           └── physics_tetris/   # Small physics-based Tetris variant
├── tests/                        # pytest suite
├── tools/
│   └── build.ps1                 # PyInstaller wrapper
├── CompProgGame.spec             # PyInstaller spec
├── pyproject.toml                # Build & dependency metadata
└── README.md
```

For Hex Colony specifically, see
[`docs/HEX_COLONY_ARCHITECTURE.md`](docs/HEX_COLONY_ARCHITECTURE.md)
for the module map, data-flow diagrams, and an
"I want to do X → edit Y" cheat sheet.

---

## Troubleshooting

- **`ModuleNotFoundError: No module named 'compprog_pygame'`** — the
  venv is not active, or you skipped `pip install -e .[dev]`. Activate
  it (`.\.venv\Scripts\Activate.ps1`) and re-run, or set
  `PYTHONPATH=src` for that shell.
- **`ExecutionPolicy` error when activating the venv** — run
  `Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned`
  in the same PowerShell window first.
- **Black / blank window or missing assets** — confirm you ran the game
  from the repository root so relative `assets/` paths resolve.
- **Performance issues in Hex Colony** — set
  `HEX_COLONY_PERF=1` (writes spike samples to
  `hex_colony_perf.jsonl`) and `HEX_COLONY_LOGISTICS=0` to disable the
  logistics monitor if it is contributing overhead.