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
import shutil
import subprocess
import sys
from pathlib import Path


WORKFLOW_FILE = "build-native.yml"
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DOWNLOAD_DIR = PROJECT_ROOT / "dist-cross"


def _require_gh() -> None:
    if shutil.which("gh") is None:
        sys.exit(
            "GitHub CLI ('gh') not found.  Install it from "
            "https://cli.github.com/ and run `gh auth login` first."
        )


def trigger_and_download(*, wait: bool = True) -> None:
    _require_gh()

    print(f"Triggering workflow '{WORKFLOW_FILE}' on GitHub…")
    subprocess.run(
        ["gh", "workflow", "run", WORKFLOW_FILE],
        check=True, cwd=PROJECT_ROOT,
    )

    if not wait:
        print("Workflow triggered.  Check progress with: gh run watch")
        return

    print("Waiting for the most recent run to start…")
    # Get the most recent run id for this workflow.
    result = subprocess.run(
        ["gh", "run", "list",
         "--workflow", WORKFLOW_FILE,
         "--limit", "1",
         "--json", "databaseId"],
        check=True, cwd=PROJECT_ROOT, capture_output=True, text=True,
    )
    import json
    runs = json.loads(result.stdout)
    if not runs:
        sys.exit("No workflow runs found after triggering.")
    run_id = str(runs[0]["databaseId"])

    print(f"Watching run {run_id}…")
    subprocess.run(
        ["gh", "run", "watch", run_id, "--exit-status"],
        check=True, cwd=PROJECT_ROOT,
    )

    DOWNLOAD_DIR.mkdir(exist_ok=True)
    print(f"Downloading artifacts into {DOWNLOAD_DIR}…")
    subprocess.run(
        ["gh", "run", "download", run_id, "--dir", str(DOWNLOAD_DIR)],
        check=True, cwd=PROJECT_ROOT,
    )
    print(f"\nDone. Artifacts available under: {DOWNLOAD_DIR}")


def _cli() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--no-wait", action="store_true",
        help="Trigger the workflow but don't wait or download artifacts.",
    )
    args = parser.parse_args()
    trigger_and_download(wait=not args.no_wait)


if __name__ == "__main__":
    _cli()
