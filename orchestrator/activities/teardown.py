"""Durable teardown activity: the shared ownership-aware teardown in ``shared.full_teardown``.

Runs as the Function App's managed identity. The hosted app has no ambient subscription context, so
the request must name both ``subscription_id`` and ``expected_tenant_id``; every token and ARM,
Graph, Fabric and Databricks call is pinned to them.
"""

from __future__ import annotations

import logging
from typing import Any

from shared.full_teardown import CredentialTokens, DeploymentTeardown, TeardownRefused, TeardownSpec

logger = logging.getLogger(__name__)

_LEVELS = {"error": logging.ERROR, "warn": logging.WARNING}


class _LogReport:
    def __init__(self) -> None:
        self.phases: list[dict[str, str]] = []

    def log(self, level: str, message: str) -> None:
        logger.log(_LEVELS.get(level, logging.INFO), "%s", message)

    def phase(self, name: str, status: str) -> None:
        phase = next((p for p in self.phases if p["phase"] == name), None)
        if phase is None:
            self.phases.append({"phase": name, "status": status})
        else:
            phase["status"] = status


def spec_from_config(config: dict[str, Any]) -> TeardownSpec:
    return TeardownSpec(
        workspace_name=config.get("fabric_workspace_name") or "",
        resource_group_name=config.get("resource_group_name") or "",
        delete_workspace=bool(config.get("delete_workspace", False)),
        delete_azure_rg=bool(config.get("delete_azure_rg", True)),
        subscription_id=config.get("subscription_id") or "",
        expected_tenant_id=config.get("expected_tenant_id") or "",
        front_end_resource_groups=[g.strip() for g in config.get("front_end_resource_groups") or [] if g.strip()],
        discover_front_ends=bool(config.get("discover_front_ends", True)),
    )


def run(config: dict[str, Any]) -> dict[str, Any]:
    """Tear down one deployment and its owned front ends; never raises for a refused request."""
    from azure.identity import DefaultAzureCredential

    spec = spec_from_config(config)
    report = _LogReport()
    try:
        tokens = CredentialTokens(DefaultAzureCredential(), spec.expected_tenant_id)
        result = DeploymentTeardown(spec, tokens, report).run()
    except TeardownRefused as refused:
        logger.error("Teardown refused; nothing was deleted: %s", refused)
        return {"status": "refused", "reason": str(refused), "phases": report.phases}
    result["phases"] = report.phases
    return result
