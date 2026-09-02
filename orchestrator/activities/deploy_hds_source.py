"""Deploy Microsoft's HDS v1.4.0 source package into an existing Fabric workspace."""

from __future__ import annotations

from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, as_completed, wait
from contextlib import nullcontext
from datetime import datetime, timezone
import argparse
import base64
import fnmatch
import hashlib
import json
import logging
import re
import shutil
import subprocess
import sys
import threading
import time
import tempfile
from pathlib import Path
from typing import Any, Callable

import requests

from shared.fabric_client import FabricClient
from shared.onelake_client import OneLakeClient

logger = logging.getLogger(__name__)

HDS_VERSION = "1.4.0"
DTT_VERSION = "0.3.1.1271"
STAGING_PATCH_VERSION = "2026-08-04.2"
COMPANY_PREFIX = "healthcare1"
TECHNICAL_PREFIX = "msft"
DEPLOYMENT_LAKEHOUSE = "deployment_lakehouse"
ENVIRONMENT_NAME = "healthcare1_msft_environment"
REPO_ROOT = Path(__file__).resolve().parents[2]
VENDOR_ROOT = REPO_ROOT / "vendor" / "microsoft-hds" / HDS_VERSION
HDS_ROOT = VENDOR_ROOT / "HDS.SourceCode"
DTT_ROOT = VENDOR_ROOT / "DTT.SourceCode"
BOOTSTRAP_ROOT = HDS_ROOT / "src" / "tools" / "fabric_depolyment_notebooks"
BUILD_ROOT = REPO_ROOT / ".hds-build" / HDS_VERSION
ARTIFACT_ROOT_NAME = "hds-build-artifacts"
LIBRARY_RELATIVE_PATH = Path("healthcare-libraries") / HDS_VERSION
VALIDATION_NOTEBOOK_NAMES = {
    "build_artifacts_validator.ipynb",
    "copy_sampledata.ipynb",
    "deployment_validator.ipynb",
}
MANAGED_LAKEHOUSE_NAMES = {
    "admin": "healthcare1_msft_admin",
    "bronze": "healthcare1_msft_bronze",
    "silver": "healthcare1_msft_silver",
    "omop": "healthcare1_msft_gold_omop",
    "cma-gold": "healthcare1_msft_gold_cma",
    "poa-gold": "healthcare1_msft_poa_gold",
    "customer-insights": "healthcare1_msft_customer_insights",
}
DEPLOYMENT_STAGE_NAMES = (
    "lakehouses_and_tables_deployer",
    "notebook_deployer",
    "pipeline_deployer",
    "powerbi_deployer",
    "update_admin_config",
    "deployment_validator",
)
CONTROL_PLANE_CONCURRENCY = 2
SOURCE_SETUP_CONCURRENCY = 4
DEPLOYMENT_STAGE_DEPENDENCIES: dict[str, tuple[str, ...]] = {
    "lakehouses_and_tables_deployer": (),
    "notebook_deployer": (),
    "pipeline_deployer": ("notebook_deployer",),
    "powerbi_deployer": ("lakehouses_and_tables_deployer",),
    "update_admin_config": ("notebook_deployer",),
    "deployment_validator": (
        "lakehouses_and_tables_deployer",
        "notebook_deployer",
        "pipeline_deployer",
        "powerbi_deployer",
        "update_admin_config",
    ),
}
HYDRATION_SHARDS: tuple[tuple[str, str], ...] = (
    ("silver", "silver"),
    ("other", "admin,bronze,omop,poa_gold,cma_gold,customer_insights"),
)
_HYDRATION_RESERVATION_LOCK = threading.Lock()
_NOTEBOOK_JOB_SLOTS = threading.BoundedSemaphore(CONTROL_PLANE_CONCURRENCY)
REQUIRED_PIPELINES = {
    "healthcare1_msft_clinical_data_foundation_ingestion",
    "healthcare1_msft_imaging_with_clinical_foundation_ingestion",
    "healthcare1_msft_omop_analytics",
}

_EVENT_LOCK = threading.Lock()
_EVENT_TIMINGS: dict[tuple[str, int], dict[str, Any]] = {}
_TERMINAL_EVENT_STATUSES = {"blocked", "failed", "skipped", "succeeded"}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _reset_event_timings() -> None:
    with _EVENT_LOCK:
        _EVENT_TIMINGS.clear()


def _event(
    name: str,
    status: str,
    detail: str,
    *,
    attempt: int = 1,
    job_id: str = "",
) -> None:
    """Emit replay-safe node timing from the process that performed the work."""
    emitted_at = _utc_now()
    monotonic_now = time.monotonic()
    key = (name, attempt)
    with _EVENT_LOCK:
        timing = _EVENT_TIMINGS.setdefault(
            key,
            {"startedAt": emitted_at, "startedMonotonic": monotonic_now},
        )
        elapsed_seconds = round(monotonic_now - timing["startedMonotonic"], 3)
        payload: dict[str, Any] = {
            "detail": detail.replace("\n", " "),
            "emittedAt": emitted_at,
            "startedAt": timing["startedAt"],
            "elapsedSeconds": elapsed_seconds,
            "attempt": attempt,
        }
        if job_id:
            payload["jobId"] = job_id
        if status in _TERMINAL_EVENT_STATUSES:
            payload["finishedAt"] = emitted_at
    print(
        f"@@HDS_SOURCE|{name}|{status}|{json.dumps(payload, separators=(',', ':'), sort_keys=True)}@@",
        flush=True,
    )


def managed_artifact_name(name: str) -> str:
    """Map source artifact names to the observed managed-deployment contract."""
    raw = name.removesuffix(".ipynb").removesuffix(".json")
    key = raw.strip().lower()
    lakehouse_key = key.replace("_", "-")
    if lakehouse_key in MANAGED_LAKEHOUSE_NAMES:
        return MANAGED_LAKEHOUSE_NAMES[lakehouse_key]
    friendly = {
        "care management analytics semantic model": "cma_semantic_model",
        "care management analytics bi report": "cma_report",
        "patient outreach analytics semantic model": "poa_semantic_model",
        "patient outreach analytics bi report": "poa_report",
    }
    if key in friendly:
        return f"{COMPANY_PREFIX}_{TECHNICAL_PREFIX}_{friendly[key]}"
    normalized = re.sub(r"[^a-z0-9_]+", "_", key).strip("_")
    if normalized.startswith(f"{TECHNICAL_PREFIX}_"):
        return f"{COMPANY_PREFIX}_{normalized}"
    return f"{COMPANY_PREFIX}_{TECHNICAL_PREFIX}_{normalized}"


def _replace_notebook_text(notebook: dict[str, Any], replacements: dict[str, str]) -> None:
    for cell in notebook.get("cells", []):
        source = cell.get("source", [])
        if isinstance(source, str):
            source = [source]
        patched: list[str] = []
        for line in source:
            for old, new in replacements.items():
                line = line.replace(old, new)
            patched.append(line)
        cell["source"] = patched


def _managed_name_override_source() -> str:
    return '''# Managed-equivalent artifact naming adapter generated by hls-data-accelerator.
original_build_artifact_name = build_artifact_name
def build_artifact_name(name: str) -> str:
    import re
    aliases = {
        "admin": "healthcare1_msft_admin",
        "bronze": "healthcare1_msft_bronze",
        "silver": "healthcare1_msft_silver",
        "omop": "healthcare1_msft_gold_omop",
        "poa-gold": "healthcare1_msft_poa_gold",
        "customer-insights": "healthcare1_msft_customer_insights",
        "cma-gold": "healthcare1_msft_gold_cma",
        "cma_gold": "healthcare1_msft_gold_cma",
        "care management analytics bi report": "healthcare1_msft_cma_report",
        "patient outreach analytics semantic model": "healthcare1_msft_poa_semantic_model",
        "patient outreach analytics bi report": "healthcare1_msft_poa_report",
        "care management analytics semantic model": "healthcare1_msft_cma_semantic_model",
    }
    key = name.strip().lower()
    if key in aliases:
        return aliases[key]
    normalized = re.sub(r"[^a-z0-9_]+", "_", key).strip("_")
    if normalized.startswith("msft_"):
        return f"healthcare1_{normalized}"
    return f"healthcare1_msft_{normalized}"

def build_notebook_display_name(source_filename: str, use_COMPANY_PREFIX: bool = True, use_TECHNICAL_PREFIX: bool = True) -> str:
    base_name = source_filename.removesuffix(".ipynb")
    return build_artifact_name(base_name)

LAKEHOUSE_NAME_MAP = {
    logical_key: build_artifact_name(base_name)
    for logical_key, base_name in LOGICAL_LAKEHOUSES.items()
}
LAKEHOUSE_NAME_MAP.update({
    base_name: build_artifact_name(base_name)
    for base_name in LOGICAL_LAKEHOUSES.values()
})

SEMANTIC_MODELS = [
    {"name": "Care Management Analytics Semantic Model", "dir": f"{BASE_DIST_PATH}/healthcare-artifacts/{ARTIFACT_VERSION}/care-management-analytics/Datasets/CareManagementAnalytics", "lakehouse_binding": "cma-gold", "model_file": "model.bim", "definition_file": "definition.pbism", "placeholders": {"%%sql_endpoint%%": "sqlEndpoint", "%%default_lakehouse_name%%": "lakehouseName"}, "id_var": "CMA_SM_ID"},
    {"name": "Patient Outreach Analytics Semantic Model", "dir": f"{BASE_DIST_PATH}/healthcare-artifacts/{ARTIFACT_VERSION}/patient-outreach-analytics-advanced/Datasets/PatientOutreachAdvanced", "lakehouse_binding": "poa-gold", "model_file": "model.bim", "definition_file": "definition.pbidataset", "placeholders": {"%%sql_endpoint%%": "sqlEndpoint", "%%default_lakehouse_name%%": "lakehouseName"}, "id_var": "POA_SM_ID"},
]
REPORTS = [
    {"name": "Care Management Analytics BI Report", "dir": f"{BASE_DIST_PATH}/healthcare-artifacts/{ARTIFACT_VERSION}/care-management-analytics/Reports/CareManagementAnalytics", "semantic_model_ref": "Care Management Analytics Semantic Model", "theme_file": "CY24SU08.json"},
    {"name": "Patient Outreach Analytics BI Report", "dir": f"{BASE_DIST_PATH}/healthcare-artifacts/{ARTIFACT_VERSION}/patient-outreach-analytics-advanced/Reports/PatientOutreachAdvanced", "semantic_model_ref": "Patient Outreach Analytics Semantic Model", "theme_file": "CY24SU02.json"},
]
print("✓ Managed-equivalent artifact naming adapter loaded")
'''


def _patch_common_config(notebook: dict[str, Any]) -> None:
    _replace_notebook_text(
        notebook,
        {
            'COMPANY_PREFIX = "healthcare"': 'COMPANY_PREFIX = "healthcare1"',
            'TECHNICAL_PREFIX = ""': 'TECHNICAL_PREFIX = "msft"',
            '    "msft_config_notebook"  # Referenced by 50+ notebooks via: %run msft_config_notebook': '    # Config notebook receives the same managed prefix as every runtime notebook.',
        },
    )
    for cell in notebook.get("cells", []):
        source = "".join(cell.get("source", []))
        if "original_build_artifact_name = build_artifact_name" in source:
            cell["source"] = _managed_name_override_source().splitlines(keepends=True)


def _patch_environment_deployer(notebook: dict[str, Any]) -> None:
    for cell in notebook.get("cells", []):
        source = "".join(cell.get("source", []))
        if "def get_or_create_environment" in source:
            source = source.replace(
                '        # raise ValueError(error_msg)\n    else:',
                '        return env_id\n    else:',
            )
        if "def publish_environment" in source:
            old = '''        print("  This operation can take several minutes to complete.")
        print("  Please check the Fabric portal to confirm publishing is complete before using this environment.")
        return True'''
            new = '''        print("  Waiting for environment publishing to complete...")
        deadline = time.time() + (75 * 60)
        while time.time() < deadline:
            status_response = fabric_client.get(f"/v1/workspaces/{workspace_id}/environments/{environment_id}")
            if status_response.ok:
                status_payload = status_response.json()
                state = str((status_payload.get("publishDetails") or {}).get("state", "")).lower()
                if state in {"success", "succeeded", "published", "active"}:
                    print(f"  ✓ Environment publish completed: {state}")
                    return True
                if state in {"failed", "cancelled", "canceled"}:
                    raise RuntimeError(f"Environment publish failed: {status_payload}")
            time.sleep(30)
        raise TimeoutError("Environment publish did not complete within 75 minutes")'''
            if old not in source:
                raise ValueError("environment_deployer publish block no longer matches v1.4.0")
            source = source.replace(old, new)
        cell["source"] = source.splitlines(keepends=True)


def _patch_lakehouse_deployer(notebook: dict[str, Any]) -> None:
    parameter_cell = {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {"tags": ["parameters"], "run_control": {"frozen": False}},
        "outputs": [],
        "source": [
            'HYDRATION_LAKEHOUSE_KEYS = ""\n',
            '\n',
            'def hydration_lakehouse_selected(name: str) -> bool:\n',
            '    selected = {item.strip().lower().replace("-", "_") for item in str(HYDRATION_LAKEHOUSE_KEYS).split(",") if item.strip()}\n',
            '    normalized = str(name).strip().lower().replace("-", "_")\n',
            '    return not selected or normalized in selected\n',
        ],
    }
    notebook.setdefault("cells", []).insert(0, parameter_cell)
    discovery_patched = False
    orchestration_patched = False
    for cell in notebook.get("cells", []):
        source = "".join(cell.get("source", []))
        if "def discover_and_create_tables" in source:
            marker = '''        for base_lakehouse_name in lakehouse_names:
            # Apply prefix pattern to lakehouse name (but NOT to table names)'''
            replacement = '''        for base_lakehouse_name in lakehouse_names:
            if not hydration_lakehouse_selected(base_lakehouse_name):
                continue
            # Apply prefix pattern to lakehouse name (but NOT to table names)'''
            if marker not in source:
                raise ValueError("lakehouse deployer table loop no longer matches v1.4.0")
            source = source.replace(marker, replacement)
            discovery_patched = True
        if "def start_lakehouses_and_tables_deployment" in source:
            start_marker = '    print("\\n" + "=" * 80)'
            if start_marker not in source:
                raise ValueError("lakehouse deployer orchestration start no longer matches v1.4.0")
            source = source.replace(
                start_marker,
                '    selected_lakehouses = [name for name in LAKEHOUSES_TO_CREATE if hydration_lakehouse_selected(name)]\n\n' + start_marker,
                1,
            )
            source = source.replace(
                "lakehouses_to_create=LAKEHOUSES_TO_CREATE",
                "lakehouses_to_create=selected_lakehouses",
            )
            orchestration_patched = True
        cell["source"] = source.splitlines(keepends=True)
    if not discovery_patched or not orchestration_patched:
        raise ValueError("lakehouse deployer shard patch did not find required cells")


def _patch_notebook_deployer(notebook: dict[str, Any]) -> None:
    _replace_notebook_text(
        notebook,
        {
            "prefixed_env_name = build_artifact_name(TARGET_ENVIRONMENT_NAME)": f'prefixed_env_name = "{ENVIRONMENT_NAME}"',
            "if notebook_display_name in existing_notebook_names:": "if False and notebook_display_name in existing_notebook_names:",
        },
    )


def _patch_pipeline_deployer(notebook: dict[str, Any]) -> None:
    for cell in notebook.get("cells", []):
        source = "".join(cell.get("source", []))
        if "def deploy_pipeline(" not in source:
            continue
        source = source.replace(
            '''    if pipeline_name in existing_pipelines:
        print(f"  ⏭️  Skipped (already exists): {pipeline_name}")
        return True, "skipped_exists"
    
    try:
        url = f"/v1/workspaces/{workspace_id}/dataPipelines"''',
            '''    try:
        existing_id = existing_pipelines.get(pipeline_name)
        url = (f"/v1/workspaces/{workspace_id}/dataPipelines/{existing_id}/updateDefinition" if existing_id else f"/v1/workspaces/{workspace_id}/dataPipelines")''',
        )
        source = source.replace(
            '            "displayName": pipeline_name,\n            "description": f"Deployed from {capability}",',
            '            **({"displayName": pipeline_name, "description": f"Deployed from {capability}"} if not existing_id else {}),',
        )
        source = source.replace(
            '            print(f"  ✅ Created: {pipeline_name} (ID: {pipeline_id})")\n            return True, "created"',
            '            action = "Updated" if existing_id else "Created"\n            print(f"  ✅ {action}: {pipeline_name} (ID: {pipeline_id or existing_id})")\n            return True, "updated" if existing_id else "created"',
        )
        cell["source"] = source.splitlines(keepends=True)


def _patch_powerbi_deployer(notebook: dict[str, Any]) -> None:
    replacements = {
        "sm_failed = 0\nsm_skipped = 0": "sm_failed = 0\nsm_skipped = 0\nsm_errors = []",
        "sm_failed += 1\n        print(f\"  ❌ Failed to deploy semantic model '{name}': {ex}\\n\")": "sm_failed += 1\n        sm_errors.append(f\"{name}: {ex}\")\n        print(f\"  ❌ Failed to deploy semantic model '{name}': {ex}\\n\")",
        "rep_failed = 0\nrep_skipped = 0": "rep_failed = 0\nrep_skipped = 0\nrep_errors = []",
        "rep_failed += 1\n        print(f\"  ❌ Failed to deploy report '{name}': {ex}\\n\")": "rep_failed += 1\n        rep_errors.append(f\"{name}: {ex}\")\n        print(f\"  ❌ Failed to deploy report '{name}': {ex}\\n\")",
        'target_names = {\n        _normalize_name(manifest_key),\n        _normalize_name(manifest_key.replace("-", "_")),\n    }': 'target_names = {\n        _normalize_name(manifest_key),\n        _normalize_name(manifest_key.replace("-", "_")),\n        _normalize_name(build_artifact_name(manifest_key)),\n    }',
    }
    patched = set()
    summary_patched = False
    for cell in notebook.get("cells", []):
        source = "".join(cell.get("source", []))
        for old, new in replacements.items():
            if old in source:
                source = source.replace(old, new)
                patched.add(old)
        marker = 'print("=" * 120 + "\\n")'
        if marker in source and "Total deployed:" in source:
            source = source.replace(
                marker,
                marker
                + '\nif sm_errors or rep_errors:'
                + '\n    deployment_errors = " | ".join(sm_errors + rep_errors)'
                + '\n    try:'
                + '\n        mssparkutils.fs.put(f"{BASE_DIST_PATH}/powerbi-deployer-errors.txt", deployment_errors, True)'
                + '\n    except Exception as diagnostic_ex:'
                + '\n        print(f"Could not persist Power BI diagnostics: {diagnostic_ex}")'
                + '\n    raise RuntimeError("Power BI deployment failures: " + deployment_errors)',
            )
            summary_patched = True
        cell["source"] = source.splitlines(keepends=True)
    if len(patched) != len(replacements) or not summary_patched:
        raise ValueError("powerbi deployer error propagation blocks no longer match v1.4.0")


def _patch_omop_pipeline(path: Path) -> None:
    """Retain only Silver-to-Gold OMOP work after the clinical pipeline has populated Silver."""
    pipeline = json.loads(path.read_text(encoding="utf-8"))
    activities = pipeline.get("properties", {}).get("activities", [])
    retained = [activity for activity in activities if activity.get("name") == "omop_silver_gold_transformation"]
    if len(retained) != 1:
        raise ValueError(f"OMOP pipeline contract changed; expected one Silver-to-Gold activity in {path}")
    retained[0]["dependsOn"] = []
    pipeline["properties"]["activities"] = retained
    path.write_text(json.dumps(pipeline, separators=(",", ":")), encoding="utf-8")


def patch_notebook(source: Path, destination: Path) -> None:
    notebook = json.loads(source.read_text(encoding="utf-8"))
    _replace_notebook_text(
        notebook,
        {"%run msft_config_notebook": "%run healthcare1_msft_config_notebook"},
    )
    if source.name == "common_deployment_config.ipynb":
        _patch_common_config(notebook)
    elif source.name == "environment_deployer.ipynb":
        _patch_environment_deployer(notebook)
    elif source.name == "lakehouses_and_tables_deployer.ipynb":
        _patch_lakehouse_deployer(notebook)
    elif source.name == "notebook_deployer.ipynb":
        _patch_notebook_deployer(notebook)
    elif source.name == "pipeline_deployer.ipynb":
        _patch_pipeline_deployer(notebook)
    elif source.name == "powerbi_deployer.ipynb":
        _patch_powerbi_deployer(notebook)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(notebook, separators=(",", ":")), encoding="utf-8")


def _build_wheel(source_root: Path, destination: Path, expected: str) -> Path:
    before = set(destination.glob("*.whl"))
    with tempfile.TemporaryDirectory(prefix="hds-wheel-") as temporary:
        build_source = Path(temporary) / source_root.name
        shutil.copytree(
            source_root,
            build_source,
            ignore=shutil.ignore_patterns("build", "*.egg-info", "__pycache__", "*.pyc"),
        )
        subprocess.run(
            [sys.executable, "-m", "pip", "wheel", "--no-deps", "--wheel-dir", str(destination), str(build_source)],
            check=True,
        )
    created = set(destination.glob("*.whl")) - before
    matches = [path for path in created if fnmatch.fnmatch(path.name.lower(), expected.lower())]
    if len(matches) != 1:
        raise ValueError(f"Expected exactly one newly built {expected}, found {[p.name for p in matches]}")
    return matches[0]


def _validate_expected_tree(root: Path, spec: dict[str, Any], relative: Path = Path()) -> None:
    for name, value in spec.items():
        if name == "__files__":
            for pattern in value:
                if not list((root / relative).glob(pattern)):
                    raise FileNotFoundError(f"Validator artifact missing: {relative / pattern}")
            continue
        if isinstance(value, dict):
            target = root / relative / name
            if not target.is_dir():
                raise FileNotFoundError(f"Validator directory missing: {relative / name}")
            _validate_expected_tree(root, value, relative / name)


def _source_checksum() -> str:
    digest = hashlib.sha256()
    digest.update(STAGING_PATCH_VERSION.encode())
    for root in (HDS_ROOT, DTT_ROOT):
        for path in sorted(item for item in root.rglob("*") if item.is_file()):
            digest.update(path.relative_to(VENDOR_ROOT).as_posix().encode())
            digest.update(path.stat().st_size.to_bytes(8, "big"))
            digest.update(path.read_bytes())
    return digest.hexdigest()


def stage_source_payload(force: bool = False) -> Path:
    """Build wheels and patched bootstrap/runtime notebooks outside vendor/."""
    if not HDS_ROOT.is_dir() or not DTT_ROOT.is_dir():
        raise FileNotFoundError(f"Vendored HDS/DTT source missing under {VENDOR_ROOT}")
    checksum = _source_checksum()
    marker = BUILD_ROOT / ".source-checksum"
    if not force and marker.exists() and marker.read_text().strip() == checksum:
        validate_staged_payload(BUILD_ROOT)
        return BUILD_ROOT

    if BUILD_ROOT.exists():
        shutil.rmtree(BUILD_ROOT)
    artifact_destination = BUILD_ROOT / ARTIFACT_ROOT_NAME
    shutil.copytree(HDS_ROOT / ARTIFACT_ROOT_NAME, artifact_destination)
    omop_pipelines = list(artifact_destination.rglob("msft_omop_analytics.json"))
    if len(omop_pipelines) != 1:
        raise ValueError(f"Expected one OMOP pipeline definition, found {omop_pipelines}")
    _patch_omop_pipeline(omop_pipelines[0])
    library_destination = artifact_destination / LIBRARY_RELATIVE_PATH
    library_destination.mkdir(parents=True, exist_ok=True)
    _build_wheel(HDS_ROOT, library_destination, f"hds-{HDS_VERSION}-*.whl")
    _build_wheel(DTT_ROOT, library_destination, f"dtt-{DTT_VERSION}-*.whl")

    environment_yml = library_destination / "environment.yml"
    environment_text = environment_yml.read_text(encoding="utf-8")
    if "scipy==1.11.4" not in environment_text:
        environment_text += "      - scipy==1.11.4\n"
        environment_yml.write_text(environment_text, encoding="utf-8")

    deployment_destination = BUILD_ROOT / "bootstrap" / "deployment_notebooks"
    validation_destination = BUILD_ROOT / "bootstrap" / "validation_notebooks"
    for source in sorted(BOOTSTRAP_ROOT.glob("*.ipynb")):
        patch_notebook(source, deployment_destination / source.name)
    for source in sorted((BOOTSTRAP_ROOT / "validation_notebooks").glob("*.ipynb")):
        patch_notebook(source, validation_destination / source.name)

    # Runtime notebooks are uploaded as build artifacts and must use the managed config name.
    for source in sorted(artifact_destination.rglob("*.ipynb")):
        patch_notebook(source, source)

    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(checksum, encoding="utf-8")
    validate_staged_payload(BUILD_ROOT)
    return BUILD_ROOT


def validate_staged_payload(build_root: Path) -> dict[str, Any]:
    artifact_root = build_root / ARTIFACT_ROOT_NAME
    library_root = artifact_root / LIBRARY_RELATIVE_PATH
    hds_wheels = list(library_root.glob(f"hds-{HDS_VERSION}-*.whl"))
    dtt_wheels = list(library_root.glob(f"dtt-{DTT_VERSION}-*.whl"))
    if len(hds_wheels) != 1 or len(dtt_wheels) != 1:
        raise ValueError(f"Expected one HDS and one DTT wheel, found {hds_wheels} / {dtt_wheels}")
    environment = (library_root / "environment.yml").read_text(encoding="utf-8")
    if "scipy==1.11.4" not in environment:
        raise ValueError("Staged environment.yml is missing scipy==1.11.4")

    validator_path = artifact_root / "healthcare-artifacts-validator-config" / "build_artifacts_validator_config.json"
    validator = json.loads(validator_path.read_text(encoding="utf-8"))
    _validate_expected_tree(artifact_root, validator)

    deployment = list((build_root / "bootstrap" / "deployment_notebooks").glob("*.ipynb"))
    validation = list((build_root / "bootstrap" / "validation_notebooks").glob("*.ipynb"))
    if len(deployment) != 9 or {path.name for path in validation} != VALIDATION_NOTEBOOK_NAMES:
        raise ValueError(f"Unexpected bootstrap notebook set: {len(deployment)} / {[p.name for p in validation]}")
    all_notebooks = deployment + validation + list(artifact_root.rglob("*.ipynb"))
    for path in all_notebooks:
        notebook = json.loads(path.read_text(encoding="utf-8"))
        text = json.dumps(notebook)
        if "%run msft_config_notebook" in text:
            raise ValueError(f"Unpatched config notebook reference: {path}")
        if "healthcare1_msft_healthcare1_environment" in text:
            raise ValueError(f"Double-prefixed environment name remains: {path}")
    omop_pipelines = list(artifact_root.rglob("msft_omop_analytics.json"))
    if len(omop_pipelines) != 1:
        raise ValueError(f"Expected one staged OMOP pipeline definition, found {omop_pipelines}")
    omop_pipeline = json.loads(omop_pipelines[0].read_text(encoding="utf-8"))
    omop_activities = omop_pipeline.get("properties", {}).get("activities", [])
    if [activity.get("name") for activity in omop_activities] != ["omop_silver_gold_transformation"]:
        raise ValueError("Staged OMOP pipeline still contains redundant Clinical-to-Bronze/Silver ingestion")
    if omop_activities[0].get("dependsOn"):
        raise ValueError("Staged OMOP Silver-to-Gold activity retains a removed ingestion dependency")
    config_text = (build_root / "bootstrap" / "deployment_notebooks" / "common_deployment_config.ipynb").read_text()
    for expected in ("healthcare1_msft_gold_omop", "healthcare1_msft_gold_cma", "healthcare1_msft_config_notebook"):
        if expected not in config_text:
            raise ValueError(f"Managed naming adapter missing {expected}")
    if "LAKEHOUSE_NAME_MAP.update" not in config_text:
        raise ValueError("Managed lakehouse base-name aliases are missing")
    return {
        "hds_wheel": hds_wheels[0].name,
        "dtt_wheel": dtt_wheels[0].name,
        "deployment_notebooks": len(deployment),
        "validation_notebooks": len(validation),
    }


def _notebook_definition(path: Path, lakehouse_id: str = "", workspace_id: str = "") -> dict[str, Any]:
    notebook = json.loads(path.read_text(encoding="utf-8"))
    if lakehouse_id:
        dependencies = notebook.setdefault("metadata", {}).setdefault("dependencies", {})
        dependencies["lakehouse"] = {
            "default_lakehouse": lakehouse_id,
            "default_lakehouse_name": DEPLOYMENT_LAKEHOUSE,
            "default_lakehouse_workspace_id": workspace_id,
        }
    payload = base64.b64encode(json.dumps(notebook).encode("utf-8")).decode("ascii")
    return {"format": "ipynb", "parts": [{"path": "artifact.content.ipynb", "payload": payload, "payloadType": "InlineBase64"}]}


def _ensure_item(
    fabric: FabricClient,
    workspace_id: str,
    display_name: str,
    item_type: str,
    definition: dict[str, Any] | None = None,
    folder_id: str | None = None,
) -> dict[str, Any]:
    all_items = fabric.list_items(workspace_id)
    same_name = [item for item in all_items if item.get("displayName") == display_name]
    existing = next((item for item in same_name if item.get("type") == item_type), None)
    if existing:
        if definition:
            fabric.update_item_definition(workspace_id, existing["id"], {"definition": definition})
        return existing
    # Lakehouses intentionally share names with their generated SQL endpoints and,
    # for customer insights, a Microsoft HDS DataPipeline.
    allowed_companion_types = {"SQLEndpoint", "DataPipeline"} if item_type == "Lakehouse" else set()
    wrong_type = [
        item for item in same_name
        if item.get("type") != item_type and item.get("type") not in allowed_companion_types
    ]
    if wrong_type:
        raise RuntimeError(f"Fabric name conflict for {display_name}: {wrong_type}")
    body: dict[str, Any] = {"displayName": display_name, "type": item_type}
    if definition:
        body["definition"] = definition
    if folder_id:
        body["folderId"] = folder_id
    created = fabric.call("POST", f"/workspaces/{workspace_id}/items", body)
    if not isinstance(created, dict) or not created.get("id"):
        refreshed = fabric.find_item(workspace_id, display_name, item_type)
        if not refreshed:
            raise RuntimeError(f"Fabric did not return or expose created item {display_name}")
        return refreshed
    return created


def _ensure_folder(fabric: FabricClient, workspace_id: str, name: str) -> str:
    response = fabric.call("GET", f"/workspaces/{workspace_id}/folders") or {}
    folders = response.get("value", []) if isinstance(response, dict) else []
    existing = next((folder for folder in folders if folder.get("displayName") == name), None)
    if existing:
        return str(existing["id"])
    created = fabric.call("POST", f"/workspaces/{workspace_id}/folders", {"displayName": name})
    if not isinstance(created, dict) or not created.get("id"):
        raise RuntimeError(f"Fabric did not return folder id for {name}")
    return str(created["id"])


def expected_source_contract(build_root: Path) -> dict[str, set[str]]:
    artifact_root = build_root / ARTIFACT_ROOT_NAME
    manifest_path = artifact_root / "healthcare-configuration" / HDS_VERSION / "system-configurations" / "LakehouseHydrationManifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    notebooks = {managed_artifact_name(path.name) for path in artifact_root.rglob("Notebooks/*.ipynb")}
    pipelines = {managed_artifact_name(path.name) for path in artifact_root.rglob("DataPipelines/*.json")}
    return {
        "Lakehouse": {MANAGED_LAKEHOUSE_NAMES[key] for key in manifest},
        "Notebook": notebooks,
        "DataPipeline": pipelines,
        "SemanticModel": {managed_artifact_name("Care Management Analytics Semantic Model"), managed_artifact_name("Patient Outreach Analytics Semantic Model")},
        "Report": {managed_artifact_name("Care Management Analytics BI Report"), managed_artifact_name("Patient Outreach Analytics BI Report")},
    }


def validate_source_contract(
    fabric: FabricClient,
    workspace_id: str,
    build_root: Path,
    master_job: dict[str, Any] | None = None,
) -> dict[str, Any]:
    expected = expected_source_contract(build_root)
    items = fabric.list_items(workspace_id)
    by_type: dict[str, set[str]] = {}
    for item in items:
        by_type.setdefault(str(item.get("type")), set()).add(str(item.get("displayName")))
    missing: dict[str, list[str]] = {}
    for item_type, names in expected.items():
        absent = sorted(names - by_type.get(item_type, set()))
        if absent:
            missing[item_type] = absent
    for required in REQUIRED_PIPELINES:
        if required not in by_type.get("DataPipeline", set()):
            missing.setdefault("DataPipeline", []).append(required)

    environment = next(
        (item for item in items if item.get("type") == "Environment" and item.get("displayName") == ENVIRONMENT_NAME),
        None,
    )
    if not environment:
        missing["Environment"] = [ENVIRONMENT_NAME]
    if master_job is None:
        for job_item_name in ("deployment_validator", "master_deployer"):
            job_item = next(
                (item for item in items if item.get("type") == "Notebook" and item.get("displayName") == job_item_name),
                None,
            )
            if not job_item:
                continue
            jobs = fabric.call("GET", f"/workspaces/{workspace_id}/items/{job_item['id']}/jobs/instances?limit=1") or {}
            values = jobs.get("value", []) if isinstance(jobs, dict) else []
            candidate = values[0] if values else None
            if candidate and str(candidate.get("status", "")).lower() in {"completed", "succeeded"}:
                master_job = candidate
                break
    if not master_job or str(master_job.get("status", "")).lower() not in {"completed", "succeeded"}:
        missing["DeploymentJob"] = ["Completed deployment_validator or master_deployer RunNotebook job"]
    if missing:
        raise RuntimeError(f"HDS source contract incomplete: {json.dumps(missing, sort_keys=True)}")
    return {"expected": {key: len(value) for key, value in expected.items()}, "environment_id": environment["id"], "master_status": master_job.get("status")}

def _deploy_environment(
    fabric: FabricClient,
    workspace_id: str,
    build_root: Path,
) -> dict[str, Any]:
    """Stage and publish Microsoft's environment payload without a Spark notebook."""
    environment_name = ENVIRONMENT_NAME
    environment = fabric.find_item(workspace_id, environment_name, "Environment")
    if environment is None:
        response = fabric.request_raw(
            "POST",
            f"/workspaces/{workspace_id}/environments",
            {
                "displayName": environment_name,
                "description": "Healthcare libraries environment with HDS and DTT packages",
            },
        )
        environment = response.json()
    environment_id = str(environment["id"])
    base_endpoint = f"/workspaces/{workspace_id}/environments/{environment_id}"
    library_root = build_root / ARTIFACT_ROOT_NAME / LIBRARY_RELATIVE_PATH
    wheel_paths = sorted(library_root.glob("*.whl"))
    if not wheel_paths:
        raise FileNotFoundError(f"No HDS environment wheels found under {library_root}")
    environment_yml = library_root / "environment.yml"
    if not environment_yml.is_file():
        raise FileNotFoundError(f"HDS environment definition not found: {environment_yml}")

    try:
        details = fabric.call("GET", base_endpoint)
    except requests.HTTPError as exc:
        if exc.response is None or exc.response.status_code != 404:
            raise
        _event("environment", "running", f"Replacing inaccessible environment item: {environment_id}")
        fabric.delete_item(workspace_id, environment_id)
        response = fabric.request_raw(
            "POST",
            f"/workspaces/{workspace_id}/environments",
            {
                "displayName": environment_name,
                "description": "Healthcare libraries environment with HDS and DTT packages",
            },
        )
        environment = response.json()
        environment_id = str(environment["id"])
        base_endpoint = f"/workspaces/{workspace_id}/environments/{environment_id}"
        details = environment
    try:
        staging = fabric.call("GET", f"{base_endpoint}/staging/libraries")
    except requests.HTTPError as exc:
        if exc.response is None or exc.response.status_code != 404:
            raise
        staging = {}
    staged_wheels = set((staging.get("customLibraries") or {}).get("wheelFiles") or [])
    required_wheels = {path.name for path in wheel_paths}
    published_state = str((details.get("properties", {}).get("publishDetails") or {}).get("state") or "")
    if published_state.lower() == "success" and required_wheels <= staged_wheels:
        _event("environment", "succeeded", f"Environment already published: {environment_id}")
        return details

    _event("environment", "running", f"Staging {len(wheel_paths)} Microsoft HDS/DTT wheels")
    for wheel_path in wheel_paths:
        fabric.request_content(
            "POST",
            f"{base_endpoint}/staging/libraries/{wheel_path.name}?beta=false",
            wheel_path.read_bytes(),
            max_retries=60,
        )
    fabric.request_content(
        "POST",
        f"{base_endpoint}/staging/libraries/importExternalLibraries",
        environment_yml.read_text(encoding="utf-8"),
        max_retries=60,
    )
    verify_deadline = time.time() + (10 * 60)
    while True:
        staging = fabric.call("GET", f"{base_endpoint}/staging/libraries")
        staged_wheels = set((staging.get("customLibraries") or {}).get("wheelFiles") or [])
        missing_wheels = required_wheels - staged_wheels
        if not missing_wheels:
            break
        if time.time() >= verify_deadline:
            raise RuntimeError(f"Environment wheel staging validation failed: {sorted(missing_wheels)}")
        time.sleep(10)

    fabric.request_raw("POST", f"{base_endpoint}/staging/publish")
    deadline = time.time() + (75 * 60)
    last_emit = -60
    started_at = time.time()
    while time.time() < deadline:
        details = fabric.call("GET", base_endpoint)
        publish_details = details.get("properties", {}).get("publishDetails") or {}
        state = str(publish_details.get("state") or "Unknown")
        elapsed = int(time.time() - started_at)
        if elapsed - last_emit >= 60:
            minutes, seconds = divmod(elapsed, 60)
            _event("environment", "running", f"Environment publish is {state}; elapsed {minutes}m {seconds}s")
            last_emit = elapsed
        if state.lower() in {"success", "succeeded", "published", "active"}:
            _event("environment", "succeeded", f"Environment published: {environment_id}")
            return details
        if state.lower() in {"failed", "cancelled", "canceled"}:
            raise RuntimeError(f"Environment publish failed: {publish_details}")
        time.sleep(30)
    raise TimeoutError("Environment publish did not complete within 75 minutes")


def _upload_source_payload(
    onelake: OneLakeClient,
    workspace_name: str,
    build_root: Path,
) -> Any:
    _event("upload", "running", "Streaming build artifacts to OneLake")
    try:
        uploaded = onelake.upload_tree_with_azcopy(
            workspace_name,
            DEPLOYMENT_LAKEHOUSE,
            build_root / ARTIFACT_ROOT_NAME,
        )
    except Exception as exc:
        _event("upload", "failed", str(exc))
        raise
    _event("upload", "succeeded", f"{len(uploaded)} files")
    return uploaded


def _publish_hds_environment(
    fabric: FabricClient,
    workspace_id: str,
    build_root: Path,
) -> dict[str, Any]:
    _event("environment", "running", "Deploying Microsoft HDS/DTT environment payload")
    try:
        return _deploy_environment(fabric, workspace_id, build_root)
    except Exception as exc:
        _event("environment", "failed", str(exc))
        raise


def _publish_bootstrap_items(
    fabric: FabricClient,
    workspace_id: str,
    build_root: Path,
    deployment_lakehouse_id: str,
) -> dict[str, dict[str, Any]]:
    _event("bootstrap", "running", "Publishing HDS deployment and validation notebooks")
    try:
        deployment_folder = _ensure_folder(fabric, workspace_id, "deployment_notebooks")
        validation_folder = _ensure_folder(fabric, workspace_id, "validation_notebooks")
        bootstrap_items: dict[str, dict[str, Any]] = {}
        for folder, folder_id in (("deployment_notebooks", deployment_folder), ("validation_notebooks", validation_folder)):
            for path in sorted((build_root / "bootstrap" / folder).glob("*.ipynb")):
                definition = _notebook_definition(path, deployment_lakehouse_id, workspace_id)
                bootstrap_items[path.stem] = _ensure_item(
                    fabric,
                    workspace_id,
                    path.stem,
                    "Notebook",
                    definition,
                    folder_id,
                )
    except Exception as exc:
        _event("bootstrap", "failed", str(exc))
        raise
    _event("bootstrap", "succeeded", f"{len(bootstrap_items)} notebooks published")
    return bootstrap_items


def _ensure_managed_lakehouses(
    fabric: FabricClient,
    workspace_id: str,
) -> dict[str, dict[str, Any]]:
    """Create managed-equivalent Lakehouse items before table hydration begins."""
    _event("managed_lakehouses", "running", "Ensuring seven managed HDS Lakehouses")
    try:
        lakehouses = {
            key: _ensure_item(fabric, workspace_id, name, "Lakehouse")
            for key, name in sorted(MANAGED_LAKEHOUSE_NAMES.items())
        }
    except Exception as exc:
        _event("managed_lakehouses", "failed", str(exc))
        raise
    _event("managed_lakehouses", "succeeded", f"{len(lakehouses)} Lakehouses ready")
    return lakehouses


def _run_source_setup_wave(
    fabric: FabricClient,
    onelake: OneLakeClient,
    workspace_name: str,
    workspace_id: str,
    build_root: Path,
    deployment_lakehouse_id: str,
) -> tuple[Any, dict[str, Any], dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    """Publish independent source prerequisites concurrently and drain every branch."""
    operations = {
        "upload": (_upload_source_payload, (onelake, workspace_name, build_root)),
        "environment": (_publish_hds_environment, (fabric, workspace_id, build_root)),
        "bootstrap": (
            _publish_bootstrap_items,
            (fabric, workspace_id, build_root, deployment_lakehouse_id),
        ),
        "managed_lakehouses": (_ensure_managed_lakehouses, (fabric, workspace_id)),
    }
    results: dict[str, Any] = {}
    failures: dict[str, Exception] = {}
    with ThreadPoolExecutor(max_workers=SOURCE_SETUP_CONCURRENCY) as executor:
        futures = {
            executor.submit(operation, *arguments): name
            for name, (operation, arguments) in operations.items()
        }
        for future in as_completed(futures):
            name = futures[future]
            try:
                results[name] = future.result()
            except Exception as exc:
                failures[name] = exc
    if failures:
        details = "; ".join(f"{name}: {error}" for name, error in sorted(failures.items()))
        raise RuntimeError(f"HDS source setup wave failed: {details}")
    return (
        results["upload"],
        results["environment"],
        results["bootstrap"],
        results["managed_lakehouses"],
    )


def _execute_notebook_stage_job(
    fabric: FabricClient,
    workspace_id: str,
    item_id: str,
    event_name: str,
    progress_detail: str,
    parameters: dict[str, Any] | None = None,
    *,
    acquire_slot: bool = True,
) -> dict[str, Any]:
    progress_state = {"last_status": "", "last_emit": -60}

    def report_progress(payload: dict[str, Any], elapsed_seconds: int) -> None:
        status = str(payload.get("status") or "Unknown")
        if status != progress_state["last_status"] or elapsed_seconds - progress_state["last_emit"] >= 60:
            job_id = str(payload.get("id") or "pending-id")
            _event(event_name, "running", f"{progress_detail} is {status}", job_id=job_id)
            progress_state["last_status"] = status
            progress_state["last_emit"] = elapsed_seconds
    slot = _NOTEBOOK_JOB_SLOTS if acquire_slot else nullcontext()
    with slot:
        job_url = fabric.run_notebook_job(workspace_id, item_id, parameters=parameters)
        return fabric.wait_for_item_job(
            job_url,
            timeout_seconds=90 * 60,
            progress_callback=report_progress,
        )


def _run_hydration_shards(
    fabric: FabricClient,
    workspace_id: str,
    item_id: str,
) -> dict[str, Any]:
    if not HYDRATION_SHARDS:
        raise ValueError("At least one hydration shard is required")
    jobs: dict[str, dict[str, Any]] = {}
    failures: dict[str, Exception] = {}
    with _HYDRATION_RESERVATION_LOCK:
        for _ in HYDRATION_SHARDS:
            _NOTEBOOK_JOB_SLOTS.acquire()

    def run_shard(shard_name: str, lakehouse_keys: str) -> dict[str, Any]:
        event_name = f"lakehouse_hydration_{shard_name}"
        _event(event_name, "running", f"Hydrating Lakehouses: {lakehouse_keys or 'all'}")
        try:
            job = _execute_notebook_stage_job(
                fabric,
                workspace_id,
                item_id,
                event_name,
                f"Hydration shard {shard_name}",
                parameters={"HYDRATION_LAKEHOUSE_KEYS": lakehouse_keys},
                acquire_slot=False,
            )
        except Exception as exc:
            _event(event_name, "failed", str(exc))
            raise
        _event(
            event_name,
            "succeeded",
            f"Hydration shard {shard_name} completed",
            job_id=str(job.get("id", "")),
        )
        return job

    try:
        with ThreadPoolExecutor(max_workers=len(HYDRATION_SHARDS)) as executor:
            futures = {
                executor.submit(run_shard, shard_name, lakehouse_keys): shard_name
                for shard_name, lakehouse_keys in HYDRATION_SHARDS
            }
            for future in as_completed(futures):
                shard_name = futures[future]
                try:
                    jobs[shard_name] = future.result()
                except Exception as exc:
                    failures[shard_name] = exc
    finally:
        for _ in HYDRATION_SHARDS:
            _NOTEBOOK_JOB_SLOTS.release()
    if failures:
        details = "; ".join(f"{name}: {error}" for name, error in sorted(failures.items()))
        raise RuntimeError(f"Hydration shard failure: {details}")
    return {
        "id": ",".join(str(jobs[name].get("id", "")) for name, _ in HYDRATION_SHARDS),
        "status": "Completed",
        "shards": jobs,
    }


def _run_deployment_stage(
    fabric: FabricClient,
    workspace_id: str,
    bootstrap_items: dict[str, dict[str, Any]],
    stage_name: str,
) -> dict[str, Any]:
    index = DEPLOYMENT_STAGE_NAMES.index(stage_name) + 1
    stage = bootstrap_items[stage_name]
    _event(
        stage_name,
        "running",
        f"HDS stage {index}/{len(DEPLOYMENT_STAGE_NAMES)} starting",
    )
    try:
        if stage_name == "lakehouses_and_tables_deployer":
            job = _run_hydration_shards(fabric, workspace_id, str(stage["id"]))
        else:
            job = _execute_notebook_stage_job(
                fabric,
                workspace_id,
                str(stage["id"]),
                stage_name,
                f"HDS stage {index}/{len(DEPLOYMENT_STAGE_NAMES)}",
            )
    except Exception as exc:
        _event(stage_name, "failed", str(exc))
        raise
    _event(
        stage_name,
        "succeeded",
        f"HDS stage {index}/{len(DEPLOYMENT_STAGE_NAMES)} completed",
        job_id=str(job.get("id", "")),
    )
    return job


def _mark_blocked(stage_names: tuple[str, ...], detail: str) -> None:
    for stage_name in stage_names:
        _event(stage_name, "blocked", detail)


def _run_deployment_stages(
    fabric: FabricClient,
    workspace_id: str,
    bootstrap_items: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """Run the Microsoft stages as a fail-fast bounded dependency scheduler."""
    pending = set(DEPLOYMENT_STAGE_NAMES)
    completed: dict[str, dict[str, Any]] = {}
    running: dict[Any, str] = {}
    failures: dict[str, Exception] = {}

    with ThreadPoolExecutor(max_workers=CONTROL_PLANE_CONCURRENCY) as executor:
        while pending or running:
            if not failures:
                ready = [
                    stage_name
                    for stage_name in DEPLOYMENT_STAGE_NAMES
                    if stage_name in pending
                    and all(dependency in completed for dependency in DEPLOYMENT_STAGE_DEPENDENCIES[stage_name])
                ]
                while ready and len(running) < CONTROL_PLANE_CONCURRENCY:
                    stage_name = ready.pop(0)
                    pending.remove(stage_name)
                    future = executor.submit(
                        _run_deployment_stage,
                        fabric,
                        workspace_id,
                        bootstrap_items,
                        stage_name,
                    )
                    running[future] = stage_name

            if not running:
                if failures:
                    break
                if pending:
                    blocked = tuple(name for name in DEPLOYMENT_STAGE_NAMES if name in pending)
                    _mark_blocked(blocked, "Blocked by invalid or cyclic HDS stage dependencies")
                    raise RuntimeError(f"HDS stage dependency deadlock: {', '.join(blocked)}")
                break

            finished, _ = wait(tuple(running), return_when=FIRST_COMPLETED)
            for future in finished:
                stage_name = running.pop(future)
                try:
                    completed[stage_name] = future.result()
                except Exception as exc:
                    failures[stage_name] = exc

        if failures:
            blocked = tuple(name for name in DEPLOYMENT_STAGE_NAMES if name in pending)
            _mark_blocked(blocked, "Blocked by prior HDS stage failure")
            details = "; ".join(f"{name}: {error}" for name, error in sorted(failures.items()))
            raise RuntimeError(f"HDS dependency DAG failed: {details}")

    return [completed[name] for name in DEPLOYMENT_STAGE_NAMES]


def run(
    config: dict[str, Any],
    resources: dict[str, Any],
    *,
    fabric: FabricClient | None = None,
    onelake: OneLakeClient | None = None,
) -> dict[str, Any]:
    """Activity entry point used by local PowerShell and Durable Functions."""
    _reset_event_timings()
    _event("payload", "running", "Building and validating Microsoft HDS v1.4.0 payload")
    try:
        build_root = stage_source_payload()
        payload_summary = validate_staged_payload(build_root)
    except Exception as exc:
        _event("payload", "failed", str(exc))
        raise
    _event("payload", "succeeded", json.dumps(payload_summary, sort_keys=True))

    workspace_name = str(config.get("fabric_workspace_name") or resources.get("fabric_workspace_name") or "")
    workspace_id = str(config.get("fabric_workspace_id") or resources.get("fabric_workspace_id") or "")
    if not workspace_name:
        raise ValueError("fabric_workspace_name is required")
    fabric = fabric or FabricClient(config.get("fabric_api_base", "https://api.fabric.microsoft.com/v1"))
    if not workspace_id:
        workspace = fabric.find_workspace(workspace_name)
        if not workspace:
            raise RuntimeError(f"Fabric workspace not found: {workspace_name}")
        workspace_id = str(workspace["id"])

    _event("deployment_lakehouse", "running", f"Ensuring {DEPLOYMENT_LAKEHOUSE}")
    try:
        deployment_lakehouse = _ensure_item(fabric, workspace_id, DEPLOYMENT_LAKEHOUSE, "Lakehouse")
    except Exception as exc:
        _event("deployment_lakehouse", "failed", str(exc))
        raise
    _event("deployment_lakehouse", "succeeded", str(deployment_lakehouse["id"]))

    onelake = onelake or OneLakeClient()
    uploaded, _environment, bootstrap_items, _managed_lakehouses = _run_source_setup_wave(
        fabric,
        onelake,
        workspace_name,
        workspace_id,
        build_root,
        str(deployment_lakehouse["id"]),
    )

    _event("master", "running", "Running isolated HDS deployment stages")
    try:
        deployment_jobs = _run_deployment_stages(fabric, workspace_id, bootstrap_items)
    except Exception as exc:
        _event("master", "failed", str(exc))
        raise
    master_job = deployment_jobs[-1]
    _event(
        "master",
        "succeeded",
        f"{len(deployment_jobs)} isolated HDS deployment stages completed",
        job_id=str(master_job.get("id", "")),
    )

    _event("contract", "running", "Validating managed-equivalent HDS artifacts")
    try:
        contract = validate_source_contract(fabric, workspace_id, build_root, master_job)
    except Exception as exc:
        _event("contract", "failed", str(exc))
        raise
    _event("contract", "succeeded", json.dumps(contract["expected"], sort_keys=True))
    return {
        "success": True,
        "resources": {
            "hds_source_version": HDS_VERSION,
            "hds_deployment_lakehouse_id": str(deployment_lakehouse["id"]),
            "hds_environment_id": str(contract["environment_id"]),
            "hds_master_job_id": str(master_job.get("id", "")),
            "fabric_workspace_id": workspace_id,
            "fabric_workspace_name": workspace_name,
        },
        "contract": contract,
    }


def _cli(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Deploy Microsoft HDS v1.4.0 source")
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--workspace-id", default="")
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument("--contract-only", action="store_true")
    args = parser.parse_args(argv)
    try:
        build_root = stage_source_payload()
        if args.validate_only:
            validate_staged_payload(build_root)
            print("HDS source payload validation passed.")
            return 0
        fabric = FabricClient()
        workspace_id = args.workspace_id
        if not workspace_id:
            workspace = fabric.find_workspace(args.workspace)
            if not workspace:
                raise RuntimeError(f"Fabric workspace not found: {args.workspace}")
            workspace_id = str(workspace["id"])
        if args.contract_only:
            result = validate_source_contract(fabric, workspace_id, build_root)
        else:
            result = run({"fabric_workspace_name": args.workspace, "fabric_workspace_id": workspace_id}, {}, fabric=fabric)
        for key, value in result.get("resources", {}).items():
            print(f"##ORCH_RESOURCE:{key}={value}")
        print(json.dumps(result, sort_keys=True))
        return 0
    except Exception as exc:
        _event("fatal", "failed", str(exc))
        logger.exception("HDS source deployment failed")
        return 1


def main() -> None:
    raise SystemExit(_cli())


if __name__ == "__main__":
    main()
