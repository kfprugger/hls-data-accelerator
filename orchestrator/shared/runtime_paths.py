"""Per-sandbox persistent paths; local installations retain their existing layout."""
import os
from pathlib import Path

ORCHESTRATOR_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("HLS_DATA_DIR") or ORCHESTRATOR_DIR)
DATA_DIR.mkdir(parents=True, exist_ok=True)
if os.environ.get("HLS_DATA_DIR"):
    # Every child PowerShell process inherits the same durable ledger location.
    os.environ["HLS_STATE_DIR"] = str(DATA_DIR / "state-tracking")


def state_dir(repo_root: Path | None = None) -> Path:
    return Path(os.environ.get("HLS_STATE_DIR") or (repo_root or ORCHESTRATOR_DIR.parent) / "state-tracking")
