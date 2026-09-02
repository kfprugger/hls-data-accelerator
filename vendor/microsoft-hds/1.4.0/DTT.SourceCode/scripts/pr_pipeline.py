#!/usr/bin/env python3
"""PR pipeline validation script for DTT wheel build.

Commands:
    build-wheel   - Build wheel using PEP 517
    verify-wheel  - Verify wheel structure and contents
    compare-wheel - Compare built wheel tree against master reference
    all           - Run build + verify + compare
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
SRC_DIR = ROOT_DIR / "src"
DIST_DIR = ROOT_DIR / "dist"
SCRIPTS_DIR = ROOT_DIR / "scripts"
MASTER_TREE_FILE = SCRIPTS_DIR / "master_wheel_tree.txt"

STATUS_PASS = "✅ PASS"
STATUS_FAIL = "❌ FAIL"
STATUS_WARN = "⚠️ WARNING"


def _get_wheel_tree(wheel_path: Path) -> set[str]:
    """Extract file tree from a wheel, excluding dist-info and directories."""
    with zipfile.ZipFile(wheel_path) as z:
        return {
            name for name in z.namelist()
            if not name.endswith("/")
            and ".dist-info/" not in name
            and ".data/" not in name
        }


def build_wheel() -> None:
    """Build a wheel using PEP 517."""
    if DIST_DIR.exists():
        shutil.rmtree(DIST_DIR)

    subprocess.run(
        [sys.executable, "-m", "build", "--wheel"],
        cwd=ROOT_DIR,
        check=True,
    )
    print(f"{STATUS_PASS}: Wheel build completed")


def verify_wheel() -> None:
    """Verify wheel structure and contents."""
    wheels = sorted(DIST_DIR.glob("*.whl")) if DIST_DIR.exists() else []
    if not wheels:
        raise RuntimeError(f"No wheel files found in {DIST_DIR}")

    for wheel_path in wheels:
        with zipfile.ZipFile(wheel_path) as wheel:
            members = wheel.namelist()

        py_files = [
            n for n in members
            if n.endswith(".py") and ".dist-info/" not in n and ".data/" not in n
        ]

        if not py_files:
            raise RuntimeError(f"Wheel {wheel_path.name} has no Python modules")

        if any(n.startswith("src/") for n in members):
            raise RuntimeError(f"Wheel {wheel_path.name} leaks src/ into package")

        forbidden = (".github/", ".pipelines/", "tests/", "test/")
        leaked = [n for n in members if n.startswith(forbidden)]
        if leaked:
            raise RuntimeError(
                f"Wheel {wheel_path.name} contains unintended files: {', '.join(leaked[:5])}"
            )

        has_init = any(n.endswith("/__init__.py") for n in py_files)
        has_top_level = any("/" not in n for n in py_files)
        if not has_init and not has_top_level:
            raise RuntimeError(
                f"Wheel {wheel_path.name} has no importable Python modules"
            )

    print(f"{STATUS_PASS}: Wheel verification passed for {len(wheels)} wheel(s)")


def compare_wheel() -> None:
    """Compare built wheel file tree against master reference tree."""
    if not MASTER_TREE_FILE.exists():
        raise RuntimeError(f"Master wheel tree not found: {MASTER_TREE_FILE}")

    wheels = sorted(DIST_DIR.glob("*.whl")) if DIST_DIR.exists() else []
    if not wheels:
        raise RuntimeError(f"No wheel files found in {DIST_DIR}")

    master_tree = {
        line.strip() for line in MASTER_TREE_FILE.read_text().splitlines()
        if line.strip()
    }

    built_tree = _get_wheel_tree(wheels[0])

    missing = sorted(master_tree - built_tree)
    extra = sorted(built_tree - master_tree)

    if missing:
        print(f"\n{STATUS_FAIL}: Files in master wheel but MISSING from built wheel ({len(missing)}):")
        for f in missing:
            print(f"  - {f}")

    if extra:
        print(f"\n{STATUS_WARN}: Files in built wheel but NOT in master wheel ({len(extra)}):")
        for f in extra:
            print(f"  + {f}")

    if missing:
        raise RuntimeError(
            f"Built wheel is missing {len(missing)} file(s) from master reference"
        )

    if not missing and not extra:
        print(f"{STATUS_PASS}: Built wheel tree matches master reference exactly ({len(master_tree)} files)")
    elif not missing and extra:
        print(f"{STATUS_PASS}: Built wheel contains all master files + {len(extra)} new file(s)")


def run_all() -> None:
    """Run all pipeline steps."""
    build_wheel()
    verify_wheel()
    compare_wheel()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="DTT PR pipeline validation")
    parser.add_argument(
        "command",
        nargs="?",
        default="all",
        choices=["build-wheel", "verify-wheel", "compare-wheel", "all"],
        help="Pipeline command to execute",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()

    try:
        commands = {
            "build-wheel": build_wheel,
            "verify-wheel": verify_wheel,
            "compare-wheel": compare_wheel,
            "all": run_all,
        }
        commands[args.command]()
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
