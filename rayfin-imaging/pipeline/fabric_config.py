"""Fabric workspace and Lakehouse IDs for the pipeline scripts.

Values come from environment variables, or from `fabric.env` at the repository root, which
`scripts/setup_fabric.py` writes. Nothing is hard-coded, so the same scripts work in any tenant.
"""
import os
import pathlib

ENV_FILE = pathlib.Path(__file__).resolve().parents[1] / "fabric.env"
KEYS = (
    "WORKSPACE_ID", "WORKSPACE_NAME", "LAKEHOUSE_ID", "LAKEHOUSE_NAME",
    "CLINICAL_LH", "GENOMICS_LH", "IMAGING_LH", "PATIENT360_LH",
    "GOLD_LH", "PATIENT360_SQL", "PATIENT360_SQL_SERVER",
)

def load() -> dict[str, str]:
    values: dict[str, str] = {}
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                values[k.strip()] = v.strip().strip('"')
    values.update({k: os.environ[k] for k in KEYS if os.environ.get(k)})
    missing = [k for k in ("WORKSPACE_ID", "LAKEHOUSE_ID") if not values.get(k)]
    if missing:
        raise SystemExit(f"Missing {', '.join(missing)}. Run `python scripts/setup_fabric.py --workspace <name>` first.")
    return values


_cfg = None


def get(key: str) -> str:
    global _cfg
    if _cfg is None:
        _cfg = load()
    return _cfg[key]
