"""Trigger the cross-platform build workflow on GitHub from a local
Windows (or any) machine and download the resulting Windows + macOS
artifacts.

This relies on the GitHub Actions workflow at
``.github/workflows/build-native.yml`` to do the actual building on
GitHub-hosted runners — that's the only way to get a real macOS .app
without owning a Mac.

Requires the GitHub CLI (``gh``) to be installed and authenticated:
    https://cli.github.com/

Usage::

    python tools/build_cross.py            # trigger + wait + download
    python tools/build_cross.py --no-wait  # trigger only
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path


WORKFLOW_FILE = "build-native.yml"
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DOWNLOAD_DIR = PROJECT_ROOT / "dist-cross"


def _find_gh() -> str:
    """Locate the ``gh`` executable.

    ``shutil.which`` only inspects this process's ``PATH``, which on
    Windows can be missing entries that the user's shell sees (e.g.
    when ``gh`` was installed *after* the terminal started, or only
    into the per-user ``PATH`` and the parent process inherited the
    machine ``PATH``).  Fall back to common install locations and
    finally to a direct ``gh --version`` invocation through the shell
    so we still find it whenever PowerShell can.
    """
    found = shutil.which("gh")
    if found:
        return found

    candidates: list[Path] = []
    if sys.platform == "win32":
        program_files = [
            os.environ.get("ProgramFiles"),
            os.environ.get("ProgramFiles(x86)"),
            os.environ.get("ProgramW6432"),
            os.environ.get("LOCALAPPDATA"),
        ]
        for base in program_files:
            if not base:
                continue
            candidates.append(Path(base) / "GitHub CLI" / "gh.exe")
            candidates.append(
                Path(base) / "Programs" / "GitHub CLI" / "gh.exe"
            )
    else:
        candidates.append(Path("/usr/local/bin/gh"))
        candidates.append(Path("/opt/homebrew/bin/gh"))
        candidates.append(Path.home() / ".local" / "bin" / "gh")

    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)

    # Last resort: ask the shell to resolve it.  This catches PATH
    # entries that exist in the user's interactive shell but not in
    # this Python process's environment.
    try:
        subprocess.run(
            "gh --version",
            shell=True, check=True,
            capture_output=True, text=True,
        )
        return "gh"
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        return ""


def _require_gh() -> str:
    gh = _find_gh()
    if not gh:
        sys.exit(
            "GitHub CLI ('gh') not found.  Install it from "
            "https://cli.github.com/ and run `gh auth login` first.\n"
            "If it is installed, open a NEW terminal so PATH refreshes, "
            "or pass the full path to gh.exe via the GH_PATH env var."
        )
    # Allow override via env var.
    override = os.environ.get("GH_PATH")
    if override:
        return override
    return gh


def _current_branch() -> str | None:
    """Return the local repo's current branch name, or None on failure."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            check=True, cwd=PROJECT_ROOT,
            capture_output=True, text=True,
        )
        branch = result.stdout.strip()
        if branch and branch != "HEAD":
            return branch
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        pass
    return None


def _branch_is_pushed(branch: str) -> bool:
    """Return True if the local branch tip exists on origin."""
    try:
        local = subprocess.run(
            ["git", "rev-parse", branch],
            check=True, cwd=PROJECT_ROOT,
            capture_output=True, text=True,
        ).stdout.strip()
        remote = subprocess.run(
            ["git", "ls-remote", "origin", f"refs/heads/{branch}"],
            check=True, cwd=PROJECT_ROOT,
            capture_output=True, text=True,
        ).stdout.strip().split("\t", 1)
        if not remote or not remote[0]:
            return False
        return local == remote[0]
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        # If we can't tell, don't block — assume it's fine.
        return True


def trigger_and_download(*, wait: bool = True, ref: str | None = None) -> None:
    gh = _require_gh()

    if ref is None:
        ref = _current_branch()

    if ref is not None and not _branch_is_pushed(ref):
        sys.exit(
            f"Branch '{ref}' is not up-to-date on origin.\n"
            "Push your latest commits first (e.g. `git push`), otherwise "
            "the GitHub Actions runner will rebuild stale code and the "
            "produced binaries will be missing your most recent fixes."
        )

    print(f"Using GitHub CLI: {gh}")
    if ref:
        print(f"Triggering workflow '{WORKFLOW_FILE}' on ref '{ref}'…")
        subprocess.run(
            [gh, "workflow", "run", WORKFLOW_FILE, "--ref", ref],
            check=True, cwd=PROJECT_ROOT,
        )
    else:
        print(f"Triggering workflow '{WORKFLOW_FILE}' on default branch…")
        subprocess.run(
            [gh, "workflow", "run", WORKFLOW_FILE],
            check=True, cwd=PROJECT_ROOT,
        )

    if not wait:
        print("Workflow triggered.  Check progress with: gh run watch")
        return

    print("Waiting for the most recent run to start…")
    # Get the most recent run id for this workflow on the chosen branch.
    list_cmd = [
        gh, "run", "list",
        "--workflow", WORKFLOW_FILE,
        "--limit", "1",
        "--json", "databaseId",
    ]
    if ref:
        list_cmd.extend(["--branch", ref])
    result = subprocess.run(
        list_cmd,
        check=True, cwd=PROJECT_ROOT, capture_output=True, text=True,
    )
    import json
    runs = json.loads(result.stdout)
    if not runs:
        sys.exit("No workflow runs found after triggering.")
    run_id = str(runs[0]["databaseId"])

    print(f"Watching run {run_id}…")
    subprocess.run(
        [gh, "run", "watch", run_id, "--exit-status"],
        check=True, cwd=PROJECT_ROOT,
    )

    DOWNLOAD_DIR.mkdir(exist_ok=True)
    print(f"Downloading artifacts into {DOWNLOAD_DIR}…")
    subprocess.run(
        [gh, "run", "download", run_id, "--dir", str(DOWNLOAD_DIR)],
        check=True, cwd=PROJECT_ROOT,
    )
    print(f"\nDone. Artifacts available under: {DOWNLOAD_DIR}")


def _cli() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--no-wait", action="store_true",
        help="Trigger the workflow but don't wait or download artifacts.",
    )
    parser.add_argument(
        "--ref", default=None,
        help=(
            "Git branch / tag / SHA to build.  Defaults to the local "
            "current branch (so what you see is what gets built)."
        ),
    )
    args = parser.parse_args()
    trigger_and_download(wait=not args.no_wait, ref=args.ref)


if __name__ == "__main__":
    _cli()
