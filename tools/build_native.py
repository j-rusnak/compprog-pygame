"""Native single-file exporter for the compprog-pygame game.

Running ``build_native()`` on a host machine produces one self-contained
artifact for that host OS that needs no Python install, no pip
dependencies, and no extra files to run:

* Windows  -> ``dist/CompProgGame.exe``  (single ``.exe``)
* macOS    -> ``dist/CompProgGame.app``  (single ``.app`` bundle that
              double-clicks to run)

The artifact embeds the Python interpreter, ``pygame-ce``, ``pymunk``,
and the ``assets/`` folder.

Cross-compilation note
----------------------
PyInstaller cannot build a Windows ``.exe`` from macOS or vice versa.
To ship a binary for both platforms you must run this script once on a
Windows machine and once on a macOS machine.  The function itself is
fully cross-platform and will do the right thing on either host.

Usage::

    python tools/build_native.py            # build for the host OS
    python tools/build_native.py --name Foo # custom artifact name
"""

from __future__ import annotations

import argparse
import platform
import shutil
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENTRY_POINT = PROJECT_ROOT / "src" / "compprog_pygame" / "__main__.py"
ASSETS_DIR = PROJECT_ROOT / "assets"
DEFAULT_NAME = "CompProgGame"


def _ensure_pyinstaller(python: str) -> None:
    """Install PyInstaller into the active interpreter if it's missing."""
    try:
        subprocess.run(
            [python, "-c", "import PyInstaller"],
            check=True, capture_output=True,
        )
    except subprocess.CalledProcessError:
        print("PyInstaller not found — installing into current interpreter…")
        subprocess.run(
            [python, "-m", "pip", "install", "pyinstaller>=6.0"],
            check=True,
        )


def build_native(
    name: str = DEFAULT_NAME,
    *,
    clean: bool = True,
) -> Path:
    """Build a single-file native executable for the current host OS.

    Returns the path to the produced artifact (``.exe`` on Windows,
    ``.app`` bundle on macOS, single binary on Linux).
    """
    if not ENTRY_POINT.exists():
        raise FileNotFoundError(f"Entry point not found: {ENTRY_POINT}")
    if not ASSETS_DIR.exists():
        raise FileNotFoundError(f"Assets folder not found: {ASSETS_DIR}")

    python = sys.executable
    _ensure_pyinstaller(python)

    # PyInstaller's --add-data uses ';' on Windows, ':' elsewhere.
    sep = ";" if platform.system() == "Windows" else ":"
    add_data = f"{ASSETS_DIR}{sep}assets"

    cmd = [
        python, "-m", "PyInstaller",
        "--noconfirm",
        "--onefile",
        "--windowed",          # no console window on Win/macOS
        "--name", name,
        "--add-data", add_data,
        # Make sure the game packages are pulled in even though they
        # are imported dynamically via the registry.
        "--collect-submodules", "compprog_pygame",
        str(ENTRY_POINT),
    ]
    if clean:
        cmd.insert(3, "--clean")

    print("Running:", " ".join(cmd))
    subprocess.run(cmd, check=True, cwd=PROJECT_ROOT)

    dist_dir = PROJECT_ROOT / "dist"
    system = platform.system()
    if system == "Windows":
        artifact = dist_dir / f"{name}.exe"
    elif system == "Darwin":
        # --windowed on macOS produces a self-contained .app bundle.
        # The bundle is a directory but macOS treats it as a single
        # double-clickable file.
        artifact = dist_dir / f"{name}.app"
    else:
        artifact = dist_dir / name

    if not artifact.exists():
        raise RuntimeError(
            f"Build finished but expected artifact is missing: {artifact}"
        )

    size_mb = _path_size_mb(artifact)
    print(f"\nBuild succeeded: {artifact}  ({size_mb:.1f} MB)")
    return artifact


def _path_size_mb(path: Path) -> float:
    if path.is_file():
        return path.stat().st_size / (1024 * 1024)
    total = 0
    for p in path.rglob("*"):
        if p.is_file():
            total += p.stat().st_size
    return total / (1024 * 1024)


def _cli() -> None:
    parser = argparse.ArgumentParser(description="Build a native single-file game.")
    parser.add_argument("--name", default=DEFAULT_NAME, help="Artifact name.")
    parser.add_argument(
        "--no-clean", action="store_true",
        help="Skip PyInstaller's --clean step (faster rebuilds).",
    )
    args = parser.parse_args()

    if not shutil.which(sys.executable):
        print(f"Using interpreter: {sys.executable}")

    build_native(name=args.name, clean=not args.no_clean)


if __name__ == "__main__":
    _cli()
