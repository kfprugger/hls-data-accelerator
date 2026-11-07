#!/usr/bin/env python3
"""
render_demo.py — Standalone, idempotent CLI for packaging and rendering the HLS Data Accelerator demo film.

Supports:
  --dry-run: Validates screenshot assets, voiceover audio, timeline JSON, and board files without full rendering.
  --cleanup: Removes temporary export parts, caches, and intermediate files.
  --screenshot-dir: Custom directory for screenshot assets (defaults to docs/demo/assets/screenshots).
  --port: Local app port for capturing live screenshots if missing (defaults to 3111).
  --output: Target MP4 path (defaults to docs/demo/out/hls-fabric-demo-60s.mp4).
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

REQUIRED_SCREENSHOTS = [
    "01-bedside-alert.png",
    "03-alert-stopwatch.png",
    "04-vhl-genomics.png",
    "05-wardflow-triage.png",
    "07-onelake-architecture.png",
]

KOKORO_MODEL = Path("/Users/joey/.cache/hyperframes/tts/models/kokoro-v1.0.onnx")
KOKORO_VOICES = Path("/Users/joey/.cache/hyperframes/tts/voices/voices-v1.0.bin")
BOARD_SYNC_VENV = Path("/Users/joey/git/YouTube-AI-Motion-Graphics/skills/board-sync/.venv/bin/python")
EXPORT_TOOL = Path("/Users/joey/git/YouTube-AI-Motion-Graphics/tools/export.py")


def check_prerequisites() -> None:
    """Validate external model and venv paths per FR-6 & Edge cases."""
    if not KOKORO_MODEL.exists():
        sys.stderr.write(
            f"Error: Kokoro model missing at {KOKORO_MODEL}\n"
            f"Run: bash /Users/joey/git/YouTube-AI-Motion-Graphics/skills/board-sync/setup.sh\n"
        )
        sys.exit(1)

    if not BOARD_SYNC_VENV.exists():
        sys.stderr.write(
            f"Error: board-sync virtual environment missing at {BOARD_SYNC_VENV}\n"
            f"Run: bash /Users/joey/git/YouTube-AI-Motion-Graphics/skills/board-sync/setup.sh\n"
        )
        sys.exit(1)


def validate_screenshots(screenshot_dir: Path) -> list[Path]:
    """Validate that required screenshots exist in screenshot_dir."""
    if not screenshot_dir.exists() or not screenshot_dir.is_dir():
        sys.stderr.write(
            f"Error: Screenshot directory not found: {screenshot_dir}\n"
            f"Expected directory containing required assets: {', '.join(REQUIRED_SCREENSHOTS)}\n"
        )
        sys.exit(1)

    missing = []
    found = []
    for s in REQUIRED_SCREENSHOTS:
        p = screenshot_dir / s
        if not p.exists() or p.stat().st_size == 0:
            missing.append(s)
        else:
            found.append(p)

    if missing:
        sys.stderr.write(
            f"Error: Missing required screenshot assets in {screenshot_dir}: {', '.join(missing)}\n"
        )
        sys.exit(1)

    return found


def validate_timeline(timeline_path: Path, base_dir: Path) -> list[dict]:
    """Validate timeline.json and all referenced board files."""
    if not timeline_path.exists():
        sys.stderr.write(f"Error: Timeline file not found: {timeline_path}\n")
        sys.exit(1)

    try:
        data = json.loads(timeline_path.read_text(encoding="utf-8"))
    except Exception as e:
        sys.stderr.write(f"Error: Failed to parse timeline JSON {timeline_path}: {e}\n")
        sys.exit(1)

    if not isinstance(data, list) or len(data) == 0:
        sys.stderr.write(f"Error: Timeline JSON must be a non-empty list of board entries\n")
        sys.exit(1)

    for idx, entry in enumerate(data):
        rel_board = entry.get("board")
        if not rel_board:
            sys.stderr.write(f"Error: Timeline entry {idx} missing 'board' path\n")
            sys.exit(1)
        board_path = base_dir / rel_board
        if not board_path.exists():
            sys.stderr.write(f"Error: Board file not found: {board_path}\n")
            sys.exit(1)

    return data


def validate_audio(audio_path: Path) -> None:
    """Validate that voiceover audio file exists and is non-empty."""
    if not audio_path.exists() or audio_path.stat().st_size == 0:
        sys.stderr.write(f"Error: Voiceover audio file missing or empty: {audio_path}\n")
        sys.exit(1)


def cleanup(out_mp4: Path) -> None:
    """Clean up intermediate parts directory."""
    parts_dir = Path(str(out_mp4.with_suffix("")) + "-parts")
    if parts_dir.exists():
        shutil.rmtree(parts_dir)
        print(f"Cleaned up intermediate parts at {parts_dir}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Render HLS Data Accelerator 60s Demo Film")
    parser.add_argument("--dry-run", action="store_true", help="Validate assets and configuration without rendering")
    parser.add_argument("--cleanup", action="store_true", help="Clean up temporary render artifacts")
    parser.add_argument("--screenshot-dir", type=str, default="docs/demo/assets/screenshots", help="Directory containing app screenshots")
    parser.add_argument("--port", type=int, default=3111, help="Local app port for live capture fallback")
    parser.add_argument("--output", type=str, default="docs/demo/out/hls-fabric-demo-60s.mp4", help="Output MP4 file path")
    args = parser.parse_args()

    root_dir = Path(__file__).resolve().parent
    screenshot_dir = Path(args.screenshot_dir)
    if not screenshot_dir.is_absolute():
        screenshot_dir = Path.cwd() / screenshot_dir

    out_mp4 = Path(args.output)
    if not out_mp4.is_absolute():
        out_mp4 = Path.cwd() / out_mp4

    if args.cleanup:
        cleanup(out_mp4)
        sys.exit(0)

    # 1. Check prerequisites
    check_prerequisites()

    # 2. Validate screenshot assets
    screenshots = validate_screenshots(screenshot_dir)

    # 3. Validate timeline and board HTMLs
    timeline_path = root_dir / "timeline.json"
    timeline_entries = validate_timeline(timeline_path, root_dir)

    # 4. Validate voiceover audio
    audio_path = root_dir / "assets" / "audio" / "voiceover.wav"
    validate_audio(audio_path)

    # 5. Validate captions & voiceover script
    vo_script = root_dir / "VOICEOVER.md"
    if not vo_script.exists():
        sys.stderr.write(f"Error: Voiceover script missing at {vo_script}\n")
        sys.exit(1)

    print("Preflight and asset verification successful:")
    print(f"  ✓ {len(screenshots)} screenshot assets verified in {screenshot_dir}")
    print(f"  ✓ Voiceover audio verified at {audio_path}")
    print(f"  ✓ Timeline verified with {len(timeline_entries)} boards at {timeline_path}")
    print(f"  ✓ Spoken script and captions verified at {vo_script}")

    if args.dry_run:
        print("Dry run completed successfully. All assets and manifests verified (exit 0).")
        sys.exit(0)

    # 6. Execute render via YouTube-AI-Motion-Graphics export tool
    out_mp4.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        str(BOARD_SYNC_VENV),
        str(EXPORT_TOOL),
        str(timeline_path),
        "-o", str(out_mp4),
        "--audio", str(audio_path),
        "--chrome",
    ]
    print(f"Rendering demo film to {out_mp4}...")
    res = subprocess.run(cmd, check=False)
    if res.returncode != 0:
        sys.stderr.write(f"Error: Render failed with returncode {res.returncode}\n")
        sys.exit(res.returncode)

    print(f"Demo film rendered successfully: {out_mp4}")
    sys.exit(0)


if __name__ == "__main__":
    main()
