#!/usr/bin/env python3
"""PR pipeline validation script for HDS.Template-OpenSource.

Provides CLI commands that wrap Makefile targets for consistent
execution in both CI pipelines and local developer environments.

Commands:
    setup       - Create venv and install dependencies (make ci-venv-create-setup)
    build       - Build the project (make ci-build)
    lint        - Run linter (make lint)
    all         - Run setup + build + lint

Usage:
    python azure_pipeline_scripts.py all
    python azure_pipeline_scripts.py build
    python azure_pipeline_scripts.py lint
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent

STATUS_PASS = "\u2705 PASS"
STATUS_FAIL = "\u274c FAIL"

SEPARATOR = "=" * 70


def _run_make(target: str, display_name: str) -> None:
    """Run a Makefile target and report pass/fail."""
    print(f"\n{SEPARATOR}")
    print(f"  {display_name}")
    print(f"{SEPARATOR}\n")

    # Set AGENT_NAME so Makefile skips venv activation check
    # (venv paths are used explicitly in all targets)
    env = {**os.environ, "AGENT_NAME": "local-pipeline"}

    result = subprocess.run(
        ["make", target],
        cwd=ROOT_DIR,
        env=env,
    )

    if result.returncode != 0:
        print(f"\n{STATUS_FAIL}: {display_name}")
        raise RuntimeError(f"{display_name} failed with exit code {result.returncode}")

    print(f"\n{STATUS_PASS}: {display_name}")


def setup() -> None:
    """Create virtualenv and install dependencies."""
    _run_make("ci-venv-create-setup", "Install dependencies")


def build() -> None:
    """Build the project including ExportProcessor."""
    _run_make("ci-build", "Build")

    # Verify dist directory was created
    dist_dir = ROOT_DIR / "dist"
    if not dist_dir.exists() or not any(dist_dir.iterdir()):
        raise RuntimeError(f"Build produced no output in {dist_dir}")

    print(f"  Build artifacts in: {dist_dir}")


def lint() -> None:
    """Run linter."""
    _run_make("lint", "Lint")


def run_all() -> None:
    """Run all pipeline steps in sequence."""
    setup()
    build()
    lint()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="HDS.Template-OpenSource PR pipeline validation"
    )
    parser.add_argument(
        "command",
        nargs="?",
        default="all",
        choices=["setup", "build", "lint", "all"],
        help="Pipeline command to execute (default: all)",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()

    try:
        commands = {
            "setup": setup,
            "build": build,
            "lint": lint,
            "all": run_all,
        }
        commands[args.command]()
    except Exception as exc:
        print(f"\n{STATUS_FAIL}: {exc}", file=sys.stderr)
        return 1

    print(f"\n{SEPARATOR}")
    print(f"  {STATUS_PASS}: Pipeline step '{args.command}' completed successfully")
    print(f"{SEPARATOR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())