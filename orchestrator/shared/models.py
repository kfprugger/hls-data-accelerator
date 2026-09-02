"""Pydantic models for deployment configuration and state."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, model_validator


class PhaseStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"
    WAITING_FOR_INPUT = "waiting_for_input"
    CANCELLED = "cancelled"


class DeploymentConfig(BaseModel):
    """All parameters needed to run a full deployment."""

    # Azure
    resource_group_name: str = "rg-medtech-rti-fhir"
    location: str = "eastus"
    admin_security_group: str = "sg-azure-admins"
    tags: dict[str, str] = Field(default_factory=dict)

    # FHIR / Synthea
    patient_count: int = 100

    # Fabric
    fabric_workspace_name: str
    fabric_api_base: str = "https://api.fabric.microsoft.com/v1"
    expected_tenant_id: str = "8d038e6a-9b7d-4cb8-bbcf-e84dff156478"
    expected_subscription_id: str = "9bbee190-dc61-4c58-ab47-1275cb04018f"

    # Phase control
    scaffolding_only: bool = False
    skip_base_infra: bool = False
    skip_fhir: bool = False
    skip_dicom: bool = False
    skip_fabric: bool = False
    reuse_fabric_rti: bool = False
    reuse_patients: bool = False
    reseed_data: bool = False
    use_cached_synthea: bool = False
    skip_synthea: bool = False
    skip_device_assoc: bool = False
    skip_fhir_export: bool = False
    skip_rti_phase2: bool = False
    skip_hds_pipelines: bool = False
    skip_hds_source: bool = False
    skip_data_agents: bool = False
    skip_imaging: bool = False
    skip_ontology: bool = False
    skip_activator: bool = False
    skip_quality_measures: bool = False
    phase2_only: bool = False
    phase3_only: bool = False
    rebuild_containers: bool = False

    require_bronze_clinical_fhir: bool = False
    require_bronze_imaging_dicom: bool = False
    skip_phase7: bool = False
    skip_payer_rti: bool = False
    skip_payer_activator: bool = False
    skip_ops_agent: bool = False
    skip_graph_agent: bool = False
    payer_ops_email: str = ""
    claim_event_rate_per_minute: int = 60
    # Phase 3 / 4
    dicom_toolkit_path: str = ""
    alert_email: str = ""
    alert_tier_threshold: str = "URGENT"
    alert_cooldown_minutes: int = 15

    # Optional overrides (auto-discovered if blank)
    silver_lakehouse_id: str = ""
    silver_lakehouse_name: str = ""
    kusto_uri: str = ""
    event_hub_namespace: str = ""
    event_hub_name: str = "telemetry-stream"
    fhir_service_url: str = ""

    @model_validator(mode="after")
    def validate_patient_data_mode(self) -> "DeploymentConfig":
        if self.reuse_patients and self.reseed_data:
            raise ValueError("reuse_patients and reseed_data are mutually exclusive")
        if self.use_cached_synthea:
            self.patient_count = 100
        return self


class StepResult(BaseModel):
    """Result of a single deployment step."""

    name: str
    success: bool
    duration_seconds: float = 0.0
    detail: str = ""
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class PhaseResult(BaseModel):
    """Result of a deployment phase (group of steps)."""

    phase: str
    status: PhaseStatus = PhaseStatus.PENDING
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    resources: dict[str, str] = Field(default_factory=dict)
    steps: list[StepResult] = Field(default_factory=list)
    duration_seconds: float = 0.0
    error: str | None = None


class DeploymentState(BaseModel):
    """Full deployment state — stored in SQLite DB (JSON fallback in state-tracking/)."""

    instance_id: str = ""
    config: DeploymentConfig | None = None
    status: PhaseStatus = PhaseStatus.PENDING
    phases: list[PhaseResult] = Field(default_factory=list)
    started_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    completed_at: str | None = None

    # Accumulated resource IDs across phases
    resources: dict[str, Any] = Field(default_factory=dict)
