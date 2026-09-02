"""Phase 1: Deploy base Azure infrastructure.

Ports logic from phase-1/deploy.ps1:
- Ensure resource group
- Deploy infra.bicep (Event Hub, ACR, Storage, Key Vault, Managed Identity)
- Build emulator container image in ACR
- Deploy emulator.bicep (Masimo ACI container with system-assigned identity)
- Assign Event Hubs Data Sender role to emulator MI
"""

from __future__ import annotations

import logging
import subprocess
import time
from typing import Any

from shared.azure_client import AzureClient

logger = logging.getLogger(__name__)


def _stop_container_if_present(
    resource_group: str,
    container_name: str,
    runner: Any = subprocess.run,
) -> bool:
    shown = runner(
        ["az", "container", "show", "--resource-group", resource_group, "--name", container_name, "--query", "instanceView.state", "-o", "tsv"],
        capture_output=True,
        text=True,
    )
    if shown.returncode != 0 or shown.stdout.strip() not in {"Running", "Pending", "Waiting"}:
        return False
    stopped = runner(
        ["az", "container", "stop", "--resource-group", resource_group, "--name", container_name, "--only-show-errors"],
        capture_output=True,
        text=True,
    )
    if stopped.returncode != 0:
        raise RuntimeError(f"Could not stop active data producer {container_name}: {stopped.stderr}")
    logger.info("Stopped active data producer for scaffolding-only mode: %s", container_name)
    return True


def run(config: dict[str, Any]) -> dict[str, Any]:
    """Execute Phase 1: Base Azure Infrastructure.

    Args:
        config: DeploymentConfig as dict.

    Returns:
        Resource IDs and names created in this phase.
    """
    start = time.time()
    client = AzureClient()

    rg_name = config["resource_group_name"]
    location = config["location"]
    tags = config.get("tags", {})
    admin_group = config.get("admin_security_group", "")

    # Resolve admin security group object ID
    admin_group_id = ""
    if admin_group:
        try:
            admin_group_id = client.resolve_security_group_id(admin_group)
            logger.info("Admin group '%s' → %s", admin_group, admin_group_id)
        except Exception as e:
            logger.warning("Could not resolve admin group '%s': %s", admin_group, e)

    # 1. Ensure resource group
    client.ensure_resource_group(rg_name, location, tags)
    if config.get("scaffolding_only", False):
        for producer_name in ("masimo-emulator-grp", "synthea-generator-job", "fhir-loader-job", "dicom-loader-job", "claim-emulator-grp"):
            _stop_container_if_present(rg_name, producer_name)

    # Sanitize and truncate fabric_workspace_name to form appNamePrefix
    fabric_workspace_name = config.get("fabric_workspace_name", "")
    app_name_prefix = "masimo"
    if fabric_workspace_name:
        import re
        sanitized = "".join(c.lower() for c in fabric_workspace_name if c.isalnum())
        if sanitized and sanitized[0].isdigit():
            sanitized = "m" + sanitized
        sanitized = sanitized[:8]
        while len(sanitized) < 3:
            sanitized += "m"
        if re.match(r"^[a-z][a-z0-9]{2,7}$", sanitized):
            app_name_prefix = sanitized

    logger.info("Using base resource name prefix: '%s'", app_name_prefix)

    # 2. Deploy infra.bicep
    skip_fabric = config.get("skip_fabric", False)
    skip_emulator = config.get("scaffolding_only", False)
    parameters = {
        "appNamePrefix": app_name_prefix
    }
    if admin_group_id:
        parameters["adminGroupObjectId"] = admin_group_id
    if skip_fabric:
        parameters["deployEventHubs"] = False

    infra_outputs = client.deploy_bicep(
        resource_group=rg_name,
        deployment_name="infra",
        template_file="infra.bicep",
        parameters=parameters,
        tags=tags,
    )

    acr_name = infra_outputs.get("acrName", "")
    event_hub_namespace = infra_outputs.get("eventHubNamespace", "")
    event_hub_name = infra_outputs.get("eventHubName", "telemetry-stream")
    storage_account = infra_outputs.get("storageAccountName", "")
    managed_identity_id = infra_outputs.get("managedIdentityId", "")
    managed_identity_client_id = infra_outputs.get("managedIdentityClientId", "")

    # 3. Build emulator container image
    if acr_name and not skip_fabric and not skip_emulator:
        import os

        emulator_context = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
        )
        try:
            image_uri = client.build_container_image(
                resource_group=rg_name,
                acr_name=acr_name,
                image_name="masimo-emulator",
                image_tag="v1",
                docker_context_path=emulator_context,
            )
            logger.info("Emulator image: %s", image_uri)
        except Exception as e:
            logger.warning("ACR build failed (may already exist): %s", e)

    # 4. Deploy emulator.bicep
    emulator_outputs = {}
    if not skip_fabric and not skip_emulator:
        emulator_outputs = client.deploy_bicep(
            resource_group=rg_name,
            deployment_name="emulator",
            template_file="emulator.bicep",
            parameters={
                "acrName": acr_name,
                "eventHubNamespace": event_hub_namespace,
                "eventHubName": event_hub_name,
            },
            tags=tags,
        )

    duration = time.time() - start

    return {
        "phase": "Phase 1: Base Azure Infrastructure",
        "duration_seconds": duration,
        "resources": {
            "resource_group_name": rg_name,
            "acr_name": acr_name,
            "event_hub_namespace": event_hub_namespace,
            "event_hub_name": event_hub_name,
            "storage_account_name": storage_account,
            "managed_identity_id": managed_identity_id,
            "managed_identity_client_id": managed_identity_client_id,
            **{f"emulator_{k}": v for k, v in emulator_outputs.items()},
        },
    }
