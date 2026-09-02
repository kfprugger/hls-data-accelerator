"""Behavioral deployment validation keyed to the requested feature set."""

from __future__ import annotations

import base64
import json
import re
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from typing import Any


def _check(name: str, passed: bool, detail: str) -> dict[str, str]:
    return {"name": name, "status": "pass" if passed else "fail", "detail": detail}


def _items(resources: dict[str, Any], item_type: str, *name_parts: str) -> list[dict[str, Any]]:
    wanted_type = item_type.lower()
    parts = tuple(part.lower() for part in name_parts)
    return [
        item
        for item in resources.get("fabric") or []
        if str(item.get("type") or "").lower() == wanted_type
        and (not parts or all(part in str(item.get("name") or "").lower() for part in parts))
    ]


def _azure(resources: dict[str, Any], full_type: str, *name_parts: str) -> list[dict[str, Any]]:
    wanted_type = full_type.lower()
    parts = tuple(part.lower() for part in name_parts)
    return [
        resource
        for resource in resources.get("azure") or []
        if str(resource.get("fullType") or resource.get("type") or "").lower() == wanted_type
        and (not parts or all(part in str(resource.get("name") or "").lower() for part in parts))
    ]


def _legacy_continuation_requires_fabric(config: dict[str, Any]) -> bool:
    """Recognize runs created before reuse_fabric_rti existed."""
    if not config.get("continue_from_instance_id"):
        return False
    downstream_skip_fields = (
        "skip_rti_phase2",
        "skip_data_agents",
        "skip_ontology",
        "skip_activator",
        "skip_quality_measures",
        "skip_phase7",
    )
    return any(not config.get(field, False) for field in downstream_skip_fields)


def fabric_features_expected(config: dict[str, Any]) -> bool:
    return bool(
        not config.get("skip_fabric", False)
        or config.get("reuse_fabric_rti", False)
        or _legacy_continuation_requires_fabric(config)
    )


def fabric_runtime_expected(config: dict[str, Any]) -> bool:
    return bool(not config.get("scaffolding_only", False) and fabric_features_expected(config))

def effective_validation_config(config: dict[str, Any]) -> dict[str, Any]:
    """Return the feature set that the selected phase-only mode actually runs."""
    effective = dict(config)
    if any(effective.get(field) for field in ("phase2_only", "phase3_only", "phase4_only", "phase7_only")):
        effective["continue_from_instance_id"] = ""
    if effective.get("phase2_only"):
        effective.update(skip_data_agents=True, skip_imaging=True, skip_ontology=True, skip_activator=True, skip_quality_measures=True, skip_phase7=True)
    elif effective.get("phase3_only"):
        effective.update(skip_fabric=True, reuse_fabric_rti=False, skip_hds_pipelines=True, skip_data_agents=True, skip_ontology=True, skip_activator=True, skip_quality_measures=True, skip_phase7=True)
    elif effective.get("phase4_only"):
        effective.update(skip_fabric=True, reuse_fabric_rti=False, skip_hds_pipelines=True, skip_imaging=True, skip_quality_measures=True, skip_phase7=True)
    elif effective.get("phase7_only"):
        effective.update(skip_fabric=True, reuse_fabric_rti=False, skip_hds_pipelines=True, skip_data_agents=True, skip_imaging=True, skip_ontology=True, skip_activator=True, skip_quality_measures=True, skip_phase7=False)
    return effective


def feature_presence_checks(resources: dict[str, Any], config: dict[str, Any]) -> list[dict[str, str]]:
    checks: list[dict[str, str]] = []
    workspace = resources.get("workspace") or {}
    workspace_exists = bool(workspace.get("id"))

    if fabric_features_expected(config):
        rti_requirements = (
            ("Eventstream", ("masimo", "telemetry"), "Masimo Eventstream"),
            ("Eventhouse", ("masimo",), "Masimo Eventhouse"),
            ("KQLDatabase", ("masimo",), "Masimo KQL database"),
            ("KQLDashboard", ("masimo",), "Masimo KQL dashboard"),
        )
        checks.append(_check("Fabric workspace exists", workspace_exists, workspace.get("name", "Workspace missing")))
        for item_type, parts, label in rti_requirements:
            found = _items(resources, item_type, *parts)
            checks.append(_check(label, bool(found), found[0].get("name", "Missing") if found else "Missing"))

    if config.get("scaffolding_only", False) or not config.get("skip_hds_pipelines", False):
        for item_type, parts, label in (
            ("Lakehouse", ("healthcare1_msft_admin",), "HDS admin lakehouse"),
            ("Lakehouse", ("healthcare1_msft_bronze",), "HDS Bronze lakehouse"),
            ("Lakehouse", ("healthcare1_msft_silver",), "HDS Silver lakehouse"),
            ("Lakehouse", ("healthcare1_msft_gold_omop",), "HDS Gold OMOP lakehouse"),
            ("DataPipeline", ("healthcare1_msft_clinical_data_foundation_ingestion",), "Clinical foundation pipeline"),
            ("DataPipeline", ("healthcare1_msft_imaging_with_clinical_foundation_ingestion",), "Imaging pipeline"),
            ("DataPipeline", ("healthcare1_msft_omop_analytics",), "OMOP pipeline"),
        ):
            found = _items(resources, item_type, *parts)
            checks.append(_check(label, bool(found), found[0].get("name", "Missing") if found else "Missing"))

    if not config.get("skip_data_agents", False):
        for name in ("Patient 360", "Clinical Triage"):
            found = _items(resources, "DataAgent", name.lower())
            checks.append(_check(f"Data Agent: {name}", bool(found), found[0].get("name", "Missing") if found else "Missing"))

    if not config.get("skip_imaging", False):
        for item_type, parts, label in (
            ("Report", ("imagingreport",), "Imaging report"),
            ("SemanticModel", ("imagingreport",), "Imaging semantic model"),
            ("Lakehouse", ("reporting", "gold"), "Imaging reporting lakehouse"),
        ):
            found = _items(resources, item_type, *parts)
            checks.append(_check(label, bool(found), found[0].get("name", "Missing") if found else "Missing"))
        checks.append(_check("DICOM proxy Container App", bool(_azure(resources, "Microsoft.App/containerApps", "dicom", "proxy")), "Required by OHIF"))
        checks.append(_check("OHIF Static Web App", bool(_azure(resources, "Microsoft.Web/staticSites", "dicom", "ohif")), "Required by imaging report links"))

    if not config.get("skip_ontology", False):
        found = _items(resources, "Ontology", "clinicaldeviceontology")
        checks.append(_check("Clinical device ontology", bool(found), found[0].get("name", "Missing") if found else "Missing"))

    if not config.get("skip_activator", False) and config.get("alert_email"):
        found = _items(resources, "Reflex")
        checks.append(_check("Clinical alert Activator", bool(found), found[0].get("name", "Missing") if found else "Missing"))

    if not config.get("skip_quality_measures", False):
        report = _items(resources, "Report", "population health", "quality dashboard")
        model = _items(resources, "SemanticModel", "population health", "quality semantic model")
        checks.append(_check("Population health quality report", bool(report), report[0].get("name", "Missing") if report else "Missing"))
        checks.append(_check("Population health quality semantic model", bool(model), model[0].get("name", "Missing") if model else "Missing"))

    if not config.get("skip_phase7", False):
        if not config.get("skip_payer_rti", False) and not config.get("scaffolding_only", False):
            claim_emulator = _azure(resources, "Microsoft.ContainerInstance/containerGroups", "claim", "emulator")
            checks.append(_check("Payer claim emulator", bool(claim_emulator), claim_emulator[0].get("name", "Missing") if claim_emulator else "Missing"))
        if not config.get("skip_ops_agent", False):
            for name in ("HealthcareOpsAgent", "Payer Ops Triage"):
                found = _items(resources, "DataAgent", name.lower()) + _items(resources, "OperationsAgent", name.lower())
                checks.append(_check(f"Payer agent: {name}", bool(found), found[0].get("name", "Missing") if found else "Missing"))
        if not config.get("skip_graph_agent", False):
            found = _items(resources, "DataAgent", "healthcare graph agent")
            checks.append(_check("Healthcare Graph Agent", bool(found), found[0].get("name", "Missing") if found else "Missing"))
        if not config.get("skip_payer_activator", False) and config.get("payer_ops_email"):
            found = _items(resources, "Reflex", "payer")
            checks.append(_check("Payer operations Activator", bool(found), found[0].get("name", "Missing") if found else "Missing"))

    return checks


def _resource_group(resource: dict[str, Any]) -> str:
    match = re.search(r"/resourceGroups/([^/]+)", str(resource.get("id") or ""), flags=re.IGNORECASE)
    return match.group(1) if match else ""


def _url_bytes(url: str, *, timeout: int = 20) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "med-device-deployment-validator/1.0"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        if response.status != 200:
            raise RuntimeError(f"HTTP {response.status}")
        return response.read()


def _swa_check(resources: dict[str, Any], config: dict[str, Any], az_run: Callable[..., Any]) -> dict[str, str]:
    sites = _azure(resources, "Microsoft.Web/staticSites", "dicom", "ohif")
    if not sites:
        return _check("OHIF HTTP availability", False, "Static Web App missing")
    site = sites[0]
    args = ["az", "staticwebapp", "show", "--name", site["name"], "--resource-group", _resource_group(site), "--query", "defaultHostname", "-o", "tsv"]
    subscription = config.get("expected_subscription_id")
    if subscription:
        args.extend(["--subscription", subscription])
    proc = az_run(args)
    hostname = proc.stdout.strip() if proc.returncode == 0 else ""
    if not hostname:
        return _check("OHIF HTTP availability", False, "Could not resolve Static Web App hostname")
    try:
        index = _url_bytes(f"https://{hostname}/").decode("utf-8", errors="replace")
        bundle_match = re.search(r'<script[^>]+src=["\']([^"\']+\.js)["\']', index, flags=re.IGNORECASE)
        if not bundle_match:
            return _check("OHIF HTTP availability", False, "index.html has no JavaScript entry bundle")
        bundle_url = urllib.request.urljoin(f"https://{hostname}/", bundle_match.group(1))
        bundle = _url_bytes(bundle_url)
        return _check("OHIF HTTP availability", len(bundle) > 1024, f"HTTP 200; entry bundle {len(bundle)} bytes")
    except Exception as exc:
        return _check("OHIF HTTP availability", False, f"{type(exc).__name__}: {exc}")


def _proxy_check(resources: dict[str, Any], config: dict[str, Any], az_run: Callable[..., Any]) -> dict[str, str]:
    apps = _azure(resources, "Microsoft.App/containerApps", "dicom", "proxy")
    if not apps:
        return _check("DICOM proxy health", False, "Container App missing")
    app = apps[0]
    args = ["az", "containerapp", "show", "--name", app["name"], "--resource-group", _resource_group(app), "--query", "properties.configuration.ingress.fqdn", "-o", "tsv"]
    subscription = config.get("expected_subscription_id")
    if subscription:
        args.extend(["--subscription", subscription])
    proc = az_run(args)
    hostname = proc.stdout.strip() if proc.returncode == 0 else ""
    if not hostname:
        return _check("DICOM proxy health", False, "Could not resolve Container App hostname")
    last_error = "Proxy health did not respond"
    for attempt in range(1, 4):
        try:
            payload = json.loads(_url_bytes(f"https://{hostname}/health", timeout=30))
            healthy = payload.get("status") == "ok" and int(payload.get("studies") or 0) > 0
            return _check("DICOM proxy health", healthy, f"status={payload.get('status')}, studies={payload.get('studies', 0)}")
        except Exception as exc:
            last_error = f"attempt {attempt}/3 {type(exc).__name__}: {exc}"
            if attempt < 3:
                time.sleep(10)
    return _check("DICOM proxy health", False, last_error)


def _proxy_viewer_check(resources: dict[str, Any], config: dict[str, Any], az_run: Callable[..., Any]) -> dict[str, str]:
    apps = _azure(resources, "Microsoft.App/containerApps", "dicom", "proxy")
    if not apps:
        return _check("OHIF HTTP availability", False, "DICOM proxy Container App missing")
    app = apps[0]
    args = ["az", "containerapp", "show", "--name", app["name"], "--resource-group", _resource_group(app), "--query", "properties.configuration.ingress.fqdn", "-o", "tsv"]
    subscription = config.get("expected_subscription_id")
    if subscription:
        args.extend(["--subscription", subscription])
    proc = az_run(args)
    hostname = proc.stdout.strip() if proc.returncode == 0 else ""
    if not hostname:
        return _check("OHIF HTTP availability", False, "Could not resolve proxy-hosted viewer hostname")
    try:
        index = _url_bytes(f"https://{hostname}/").decode("utf-8", errors="replace")
        bundle_match = re.search(r'<script[^>]+src=["\']([^"\']+\.js)["\']', index, flags=re.IGNORECASE)
        if not bundle_match:
            return _check("OHIF HTTP availability", False, "Proxy-hosted index has no JavaScript entry bundle")
        bundle_url = urllib.request.urljoin(f"https://{hostname}/", bundle_match.group(1))
        bundle = _url_bytes(bundle_url)
        return _check("OHIF HTTP availability", len(bundle) > 1024, f"proxy-hosted HTTP 200; entry bundle {len(bundle)} bytes")
    except Exception as exc:
        return _check("OHIF HTTP availability", False, f"{type(exc).__name__}: {exc}")


def _eventhub_consumption_check(resources: dict[str, Any], config: dict[str, Any], az_run: Callable[..., Any], entity_name: str) -> dict[str, str]:
    namespaces = _azure(resources, "Microsoft.EventHub/namespaces")
    check_name = f"Eventstream consumption: {entity_name}"
    if not namespaces:
        return _check(check_name, False, "Event Hub namespace missing")
    namespace = namespaces[0]
    args = [
        "az", "monitor", "metrics", "list",
        "--resource", namespace.get("id", ""),
        "--metric", "IncomingMessages", "OutgoingMessages",
        "--filter", f"EntityName eq '{entity_name}'",
        "--interval", "PT1M", "--aggregation", "Total", "--offset", "15m", "-o", "json",
    ]
    subscription = config.get("expected_subscription_id")
    if subscription:
        args.extend(["--subscription", subscription])
    proc = az_run(args)
    if proc.returncode != 0:
        return _check(check_name, False, proc.stderr.strip() or "Metric query failed")
    try:
        values = json.loads(proc.stdout).get("value") or []
        totals: dict[str, float] = {}
        for metric in values:
            points = [point for series in (metric.get("timeseries") or []) for point in (series.get("data") or [])]
            totals[str((metric.get("name") or {}).get("value"))] = sum(float(point.get("total") or 0) for point in points[-10:])
        incoming = totals.get("IncomingMessages", 0)
        outgoing = totals.get("OutgoingMessages", 0)
        return _check(check_name, incoming > 0 and outgoing > 0, f"15m incoming={incoming:.0f}, outgoing={outgoing:.0f}")
    except Exception as exc:
        return _check(check_name, False, f"Metric response invalid: {exc}")


def _pipeline_checks(resources: dict[str, Any], fabric_client_factory: Callable[[], Any]) -> list[dict[str, str]]:
    workspace_id = str((resources.get("workspace") or {}).get("id") or "")
    if not workspace_id:
        return [_check("HDS pipeline outcomes", False, "Workspace ID missing")]
    required = [
        item
        for item in resources.get("fabric") or []
        if str(item.get("type") or "").lower() == "datapipeline"
        and any(part in str(item.get("name") or "").lower() for part in ("clinical_data_foundation", "imaging_with_clinical", "omop_analytics", "msft_cma", "claims_data_ingestion", "sdoh_ingestion"))
    ]
    checks: list[dict[str, str]] = []
    client = fabric_client_factory()
    for item in required:
        name = str(item.get("name") or item.get("id"))
        try:
            result = client.call("GET", f"/workspaces/{workspace_id}/items/{item['id']}/jobs/instances?limit=1", max_retries=2)
            latest = (result.get("value") or [{}])[0]
            status = str(latest.get("status") or "Missing")
            checks.append(_check(f"Pipeline completed: {name}", status == "Completed", status))
        except Exception as exc:
            checks.append(_check(f"Pipeline completed: {name}", False, f"{type(exc).__name__}: {exc}"))
    return checks or [_check("HDS pipeline outcomes", False, "Required pipelines missing")]


def _powerbi_query_check(resources: dict[str, Any], config: dict[str, Any], az_run: Callable[..., Any], model_name: str, dax: str) -> dict[str, str]:
    workspace_id = str((resources.get("workspace") or {}).get("id") or "")
    models = _items(resources, "SemanticModel", model_name.lower())
    if not workspace_id or not models:
        return _check(f"Power BI query: {model_name}", False, "Workspace or semantic model missing")
    args = ["az", "account", "get-access-token", "--resource", "https://analysis.windows.net/powerbi/api", "--query", "accessToken", "-o", "tsv"]
    subscription = config.get("expected_subscription_id")
    if subscription:
        args.extend(["--subscription", subscription])
    proc = az_run(args)
    token = proc.stdout.strip() if proc.returncode == 0 else ""
    if not token:
        return _check(f"Power BI query: {model_name}", False, proc.stderr.strip() or "Power BI token unavailable")
    dataset_id = models[0]["id"]
    url = f"https://api.powerbi.com/v1.0/myorg/groups/{workspace_id}/datasets/{dataset_id}/executeQueries"
    body = json.dumps({"queries": [{"query": dax}], "serializerSettings": {"includeNulls": True}}).encode()
    request = urllib.request.Request(url, data=body, method="POST", headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.loads(response.read())
        rows = (((payload.get("results") or [{}])[0].get("tables") or [{}])[0].get("rows") or [])
        return _check(f"Power BI query: {model_name}", bool(rows), f"dataset={dataset_id}, rows={len(rows)}")
    except Exception as exc:
        return _check(f"Power BI query: {model_name}", False, f"{type(exc).__name__}: {exc}")


def _quality_report_binding_check(resources: dict[str, Any], fabric_client_factory: Callable[[], Any]) -> dict[str, str]:
    check_name = "Quality report semantic model binding"
    workspace_id = str((resources.get("workspace") or {}).get("id") or "")
    reports = _items(resources, "Report", "population health", "quality dashboard")
    models = _items(resources, "SemanticModel", "population health", "quality semantic model")
    if not workspace_id or not reports or not models:
        return _check(check_name, False, "Workspace, quality report, or quality semantic model missing")
    try:
        definition = fabric_client_factory().get_item_definition(workspace_id, reports[0]["id"])
        pbir_part = next(part for part in definition.get("parts") or [] if part.get("path") == "definition.pbir")
        pbir = json.loads(base64.b64decode(pbir_part["payload"]).decode("utf-8"))
        connection = str((((pbir.get("datasetReference") or {}).get("byConnection") or {}).get("connectionString") or ""))
        model_id = str(models[0]["id"])
        bound = f"semanticmodelid={model_id}".lower() in connection.lower()
        return _check(check_name, bound, f"report={reports[0]['id']}, semanticModel={model_id}")
    except Exception as exc:
        return _check(check_name, False, f"{type(exc).__name__}: {exc}")


def runtime_feature_checks(
    resources: dict[str, Any],
    config: dict[str, Any],
    az_run: Callable[..., Any],
    fabric_client_factory: Callable[[], Any],
) -> list[dict[str, str]]:
    checks: list[dict[str, str]] = []
    if fabric_runtime_expected(config):
        checks.append(_eventhub_consumption_check(resources, config, az_run, "telemetry-stream"))
    if not config.get("scaffolding_only", False) and not config.get("skip_phase7", False) and not config.get("skip_payer_rti", False):
        checks.append(_eventhub_consumption_check(resources, config, az_run, "claim-stream"))
    if not config.get("skip_hds_pipelines", False):
        checks.extend(_pipeline_checks(resources, fabric_client_factory))
    if not config.get("skip_imaging", False):
        checks.append(_proxy_check(resources, config, az_run))
        viewer_check = _swa_check(resources, config, az_run)
        if viewer_check["status"] == "fail":
            viewer_check = _proxy_viewer_check(resources, config, az_run)
        checks.append(viewer_check)
        checks.append(_powerbi_query_check(resources, config, az_run, "ImagingReport", "EVALUATE ROW(\"Rows\", COUNTROWS('DicomFile'))"))
    if not config.get("skip_quality_measures", False):
        checks.append(_quality_report_binding_check(resources, fabric_client_factory))
        checks.append(_powerbi_query_check(resources, config, az_run, "Population Health & Quality Semantic Model", "EVALUATE ROW(\"Rows\", COUNTROWS('agg_quality_measures'))"))
    return checks
