"""Shared test helpers for orchestrator unit tests."""
import atexit
import os
import sys
import tempfile
from pathlib import Path

_SERVER_DATA_DIR: tempfile.TemporaryDirectory | None = None


def get_isolated_local_server():
    """Import and return local_server under a test-owned data directory.

    The temporary directory stays active for the process lifetime.
    Background threads and SQLite connections stay valid until process exit.
    This helper cleans up the directory at process exit.
    """
    global _SERVER_DATA_DIR
    if _SERVER_DATA_DIR is None:
        _SERVER_DATA_DIR = tempfile.TemporaryDirectory(prefix="hls-test-server-data-")

        def _cleanup():
            global _SERVER_DATA_DIR
            if _SERVER_DATA_DIR is not None:
                try:
                    if "shared.database" in sys.modules:
                        sys.modules["shared.database"].shutdown_database()
                except Exception:
                    pass
                _SERVER_DATA_DIR.cleanup()
                _SERVER_DATA_DIR = None

        atexit.register(_cleanup)

    os.environ["HLS_DATA_DIR"] = _SERVER_DATA_DIR.name

    orchestrator_dir = str(Path(__file__).resolve().parents[1])
    if orchestrator_dir not in sys.path:
        sys.path.insert(0, orchestrator_dir)

    import local_server

    assert_database_isolated()
    return local_server


def assert_database_isolated() -> None:
    """Assert that shared.database.DB_PATH is not inside the repository."""
    from shared import database as db

    repo_root = Path(__file__).resolve().parents[2]
    db_path = db.DB_PATH.resolve()
    assert not db_path.is_relative_to(repo_root), (
        f"shared.database.DB_PATH ({db_path}) is inside repository ({repo_root})"
    )
    if db.BACKUP_PATH is not None:
        backup_path = db.BACKUP_PATH.resolve()
        assert not backup_path.is_relative_to(repo_root), (
            f"shared.database.BACKUP_PATH ({backup_path}) is inside repository ({repo_root})"
        )
