"""Stage-ETA memory: learned stage durations persisted per-sandbox and pooled across hosted peers."""
from __future__ import annotations

import json
import logging
import math
import os
import re
import statistics
import tempfile
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from shared.runtime_paths import DATA_DIR

logger = logging.getLogger(__name__)

SAMPLES_FILENAME = "stage_eta_samples.json"
MAX_SAMPLES_PER_STAGE = 20
MAX_PEER_FILE_BYTES = 512 * 1024  # 512 KiB cap on peer sample files
AGGREGATE_CACHE_TTL_SEC = 300  # 5 minutes

# Canonical stage keys matching UI phase IDs and add-ons
CANONICAL_STAGE_KEYS = [
    "phase_1_workspace",
    "phase_1_base_infra",
    "phase_1_fhir",
    "phase_1_dicom",
    "phase_2_rti_ingest",
    "phase_3_hds_source",
    "phase_2_rti_enrichment",
    "phase_3_hds_pipelines",
    "phase_4_imaging",
    "phase_4_ontology",
    "phase_2_agents",
    "phase_4_agents",
    "phase_5_alerts",
    "phase_6_quality",
    "phase_7_payer_ops",
    "addon_databricks",
    "addon_cardiology",
    "addon_rayfin",
]

STAGE_KEY_PATTERNS = [
    ("phase_1_workspace", [r"fabric\s*workspace", r"phase\s*1a"]),
    ("phase_1_base_infra", [r"base\s*azure\s*infrastructure", r"azure\s*infrastructure", r"shared\s*hds\s*infrastructure", r"emulator\s*infra", r"phase\s*1b"]),
    ("phase_1_fhir", [r"fhir\s*infrastructure\s*scaffold", r"fhir\s*service", r"synthea", r"phase\s*1c"]),
    ("phase_1_dicom", [r"dicom\s*loader", r"imagingstudy", r"phase\s*1d"]),
    ("phase_2_rti_ingest", [r"fabric\s*rti\s*ingest", r"phase\s*2a", r"phase\s*2:\s*fabric\s*rti(?!\s*enrichment)", r"eventhouse", r"eventstream"]),
    ("phase_3_hds_source", [r"hds\s*source", r"phase\s*2b"]),
    ("phase_2_rti_enrichment", [r"fabric\s*rti\s*enrichment", r"phase\s*2c", r"rti\s*phase\s*2", r"rti\s*enrichment"]),
    ("phase_3_hds_pipelines", [r"hds\s*pipelines?", r"dicom\s*shortcut", r"row\s*gates", r"phase\s*3a"]),
    ("phase_4_imaging", [r"imaging\s*&\s*reporting", r"imaging", r"cohorting", r"dicom\s*viewer", r"phase\s*4a"]),
    ("phase_4_ontology", [r"ontology\s*deployment", r"clinical\s*device\s*ontology", r"deviceassociation", r"phase\s*4:\s*ontology(?![_\s-]*aware)", r"phase\s*4b", r"^ontology$"]),
    ("phase_2_agents", [r"phase\s*2:\s*data\s*agents"]),
    ("phase_4_agents", [r"ontology-aware\s*(?:clinical\s*)?data\s*agents", r"data\s*agents", r"patient\s*360", r"conversational", r"phase\s*4c"]),
    ("phase_5_alerts", [r"data\s*activator", r"reflex", r"clinicalalert(?:activator)?", r"phase\s*5"]),
    ("phase_6_quality", [r"cms\s*quality", r"quality\s*measures", r"population\s*health", r"scorecard", r"\bpdc\b", r"phase\s*6"]),
    ("phase_7_payer_ops", [r"payer\s*rti", r"claim\s*stream", r"claim-stream", r"payer\s*ops", r"healthcareops(?:agent)?", r"graph\s*agent", r"phase\s*7"]),
    ("addon_databricks", [r"^add-on:\s*databricks$", r"^databricks$"]),
    ("addon_cardiology", [r"add-on:\s*cardiology", r"\bcardiology\b"]),
    ("addon_rayfin", [r"add-on:\s*rayfin", r"\brayfin(_apps)?\b"]),
]


_SAMPLES_LOCK = threading.Lock()
_CACHE_LOCK = threading.Lock()
_aggregate_cache: dict[str, Any] | None = None
_aggregate_cache_time: float = 0.0


def resolve_stage_key(stage_name: str) -> str | None:
    """Normalize a phase/step/addon title into a canonical stage key."""
    if not stage_name:
        return None
    normalized = stage_name.strip()
    # If already a canonical key, return as-is
    if normalized in CANONICAL_STAGE_KEYS:
        return normalized
    # Handle direct addon keys like 'databricks', 'cardiology', 'rayfin'
    addon_key = f"addon_{normalized.lower()}"
    if addon_key in CANONICAL_STAGE_KEYS:
        return addon_key

    lower = normalized.lower()
    for stage_key, patterns in STAGE_KEY_PATTERNS:
        for pat in patterns:
            if re.search(pat, lower, re.IGNORECASE):
                return stage_key
    return None


def invalidate_aggregate_cache() -> None:
    """Clear the cached aggregated stage ETAs."""
    global _aggregate_cache, _aggregate_cache_time
    with _CACHE_LOCK:
        _aggregate_cache = None
        _aggregate_cache_time = 0.0


def _samples_file(data_dir: Path | None = None) -> Path:
    target_dir = Path(data_dir or DATA_DIR)
    return target_dir / SAMPLES_FILENAME


def load_own_samples(data_dir: Path | None = None) -> dict[str, list[dict[str, Any]]]:
    """Read own sandbox samples file safely. Returns {} if missing or corrupt."""
    filepath = _samples_file(data_dir)
    if not filepath.is_file():
        return {}
    try:
        content = filepath.read_text(encoding="utf-8")
        data = json.loads(content)
        if isinstance(data, dict):
            cleaned: dict[str, list[dict[str, Any]]] = {}
            for key, samples in data.items():
                if isinstance(samples, list):
                    valid_samples = []
                    for s in samples:
                        if isinstance(s, dict) and "duration_seconds" in s:
                            try:
                                dur = float(s["duration_seconds"])
                                if dur > 0 and not math.isnan(dur) and not math.isinf(dur):
                                    valid_samples.append({
                                        "duration_seconds": round(dur, 2),
                                        "finished_at": str(s.get("finished_at") or ""),
                                    })
                            except (ValueError, TypeError):
                                pass
                    if valid_samples:
                        cleaned[key] = valid_samples
            return cleaned
        return {}
    except Exception as exc:
        logger.warning("Could not read own stage ETA samples from %s: %s", filepath, exc)
        return {}


def save_own_samples(samples: dict[str, list[dict[str, Any]]], data_dir: Path | None = None) -> None:
    """Save own stage samples atomically using a temp file + os.replace in the target directory."""
    target_file = _samples_file(data_dir)
    target_dir = target_file.parent
    target_dir.mkdir(parents=True, exist_ok=True)

    fd, tmp_path_str = tempfile.mkstemp(prefix="stage_eta_", suffix=".tmp", dir=str(target_dir))
    tmp_path = Path(tmp_path_str)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(samples, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, target_file)
    except Exception:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass
        raise


def record_stage_sample(
    stage: str,
    duration_seconds: float,
    finished_at: datetime | None = None,
    data_dir: Path | None = None,
) -> bool:
    """Record a duration sample for a successfully completed stage.
    
    Never records:
    - zero or negative durations
    - non-numeric / nan / inf durations
    - unresolvable stages
    """
    if not isinstance(duration_seconds, (int, float)):
        return False
    if duration_seconds <= 0 or math.isnan(duration_seconds) or math.isinf(duration_seconds):
        return False

    stage_key = resolve_stage_key(stage)
    if not stage_key:
        return False

    finished_iso = (finished_at or datetime.now(timezone.utc)).isoformat()
    new_sample = {
        "duration_seconds": round(float(duration_seconds), 2),
        "finished_at": finished_iso,
    }

    with _SAMPLES_LOCK:
        samples = load_own_samples(data_dir)
        stage_samples = samples.setdefault(stage_key, [])
        stage_samples.append(new_sample)
        # Keep last 20 samples per stage
        samples[stage_key] = stage_samples[-MAX_SAMPLES_PER_STAGE:]
        save_own_samples(samples, data_dir)

    invalidate_aggregate_cache()
    return True


def get_stage_etas(
    data_dir: Path | None = None,
    shared_data_dir: Path | None = None,
    force_refresh: bool = False,
) -> dict[str, Any]:
    """Aggregate own samples plus peer sandboxes if HLS_SHARED_DATA_DIR is set.
    
    Returns per-stage median minutes and sample count, cached for 5 minutes.
    """
    global _aggregate_cache, _aggregate_cache_time

    now = time.monotonic()
    if not force_refresh and _aggregate_cache is not None:
        if (now - _aggregate_cache_time) < AGGREGATE_CACHE_TTL_SEC:
            return _aggregate_cache

    with _CACHE_LOCK:
        # Check again under lock
        now = time.monotonic()
        if not force_refresh and _aggregate_cache is not None:
            if (now - _aggregate_cache_time) < AGGREGATE_CACHE_TTL_SEC:
                return _aggregate_cache

        durations_by_stage: dict[str, list[float]] = {}

        # Hosted pooling: inspect all subfolders in HLS_SHARED_DATA_DIR (own subfolder included)
        shared_dir_str = str(shared_data_dir) if shared_data_dir else os.environ.get("HLS_SHARED_DATA_DIR")
        is_hosted = False
        if shared_dir_str:
            shared_dir = Path(shared_dir_str)
            if shared_dir.is_dir():
                is_hosted = True
                try:
                    peer_dirs = list(shared_dir.iterdir())
                except Exception as exc:
                    logger.warning("Could not list shared data dir %s: %s", shared_dir, exc)
                    peer_dirs = []

                for peer_dir in peer_dirs:
                    if not peer_dir.is_dir():
                        continue

                    peer_file = peer_dir / SAMPLES_FILENAME
                    if peer_file.is_file():
                        try:
                            if peer_file.stat().st_size > MAX_PEER_FILE_BYTES:
                                logger.warning(
                                    "Skipping oversized peer sample file %s (%d bytes)",
                                    peer_file,
                                    peer_file.stat().st_size,
                                )
                                continue
                            peer_content = peer_file.read_text(encoding="utf-8")
                            peer_data = json.loads(peer_content)
                            if isinstance(peer_data, dict):
                                for stage_key, samples in peer_data.items():
                                    if stage_key not in CANONICAL_STAGE_KEYS:
                                        continue
                                    if isinstance(samples, list):
                                        for s in samples:
                                            if isinstance(s, dict) and "duration_seconds" in s:
                                                try:
                                                    dur = float(s["duration_seconds"])
                                                    if dur > 0 and not math.isnan(dur) and not math.isinf(dur):
                                                        durations_by_stage.setdefault(stage_key, []).append(dur)
                                                except (ValueError, TypeError):
                                                    pass
                        except Exception as exc:
                            logger.warning("Could not read peer stage ETA samples from %s: %s", peer_file, exc)

        if not is_hosted:
            # Standalone / non-hosted mode: load own samples directly
            effective_data_dir = Path(data_dir or DATA_DIR)
            own_samples = load_own_samples(effective_data_dir)
            for stage_key, samples in own_samples.items():
                if stage_key not in CANONICAL_STAGE_KEYS:
                    continue
                if isinstance(samples, list):
                    for s in samples:
                        if isinstance(s, dict) and "duration_seconds" in s:
                            try:
                                dur = float(s["duration_seconds"])
                                if dur > 0 and not math.isnan(dur) and not math.isinf(dur):
                                    durations_by_stage.setdefault(stage_key, []).append(dur)
                            except (ValueError, TypeError):
                                pass

        # Compute median minutes and sample count per canonical stage
        stages_result: dict[str, dict[str, Any]] = {}
        for stage_key in CANONICAL_STAGE_KEYS:
            durs = durations_by_stage.get(stage_key, [])
            count = len(durs)
            if count > 0:
                med_sec = statistics.median(durs)
                med_min = round(med_sec / 60.0, 1)
            else:
                med_min = 0.0
            stages_result[stage_key] = {
                "median_minutes": med_min,
                "sample_count": count,
            }

        result = {
            "stages": stages_result,
        }
        _aggregate_cache = result
        _aggregate_cache_time = now
        return result
