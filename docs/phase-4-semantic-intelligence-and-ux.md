# Phase 4 — Semantic Intelligence + UX

Phase 4 turns validated Silver, Gold, imaging, and real-time state into clinical experiences: cohorting, Power BI imaging, OHIF viewing, Fabric ontologies, Patient 360, and Clinical Triage.

[← Phase 3](phase-3-hds-bridge-and-row-gates.md) · [Main README](../README.md) · [Interactive diagram](diagrams/phase-4-semantic-intelligence-and-ux.html) · [Diagram source](diagrams/phase-4-semantic-intelligence-and-ux.dataflow.json) · [Next: Phase 5 →](phase-5-bedside-alerting-and-action.md)

<a href="diagrams/phase-4-semantic-intelligence-and-ux.html">
  <img src="diagrams/phase-4-semantic-intelligence-and-ux.visual-check.1440x900.light.png#gh-light-mode-only" alt="Phase 4 flow from governed Silver, Gold, imaging, and Eventhouse data through reporting materialization and ontology projections into Power BI, OHIF, cohorting, Patient 360, and Clinical Triage">
  <img src="diagrams/phase-4-semantic-intelligence-and-ux.visual-check.1440x900.dark.png#gh-dark-mode-only" alt="Phase 4 flow from governed Silver, Gold, imaging, and Eventhouse data through reporting materialization and ontology projections into Power BI, OHIF, cohorting, Patient 360, and Clinical Triage">
</a>

## Exit contract

Phase 4 is complete only when:

- The imaging cohort Data Agent can query the Gold OMOP and imaging context.
- `healthcare1_reporting_gold` is materialized with study, patient, and viewer-link facts.
- The Power BI imaging report is bound to its semantic model.
- The OHIF viewer and DICOMweb proxy are reachable and the proxy indexes at least one selected study.
- The DICOMweb proxy managed identity can read OneLake through the required Fabric workspace role.
- Ontology projection tables exist and the selected ontology definitions contain entity bindings and relationships.
- Patient 360 and Clinical Triage have their KQL, Silver, and ontology datasources in the published definition.

## Prerequisites

- [Phase 3](phase-3-hds-bridge-and-row-gates.md) completed with populated Silver imaging and Gold OMOP state.
- The Fabric tenant enables Data Agents and Fabric IQ/Ontology.
- Azure can deploy the viewer frontend and DICOMweb proxy.
- The companion [`FabricDicomCohortingToolkit`](https://github.com/kfprugger/FabricDicomCohortingToolkit) is available. Preflight and deployment clone it to the sibling path when missing.

## Imaging and cohorting path

The companion toolkit deploys four connected capabilities.

### Cohorting Data Agent

The HDS Multi-Layer Imaging Cohort Agent uses Gold OMOP and imaging metadata for questions such as:

- Which COPD patients have chest CT studies?
- How many patients have both a target condition and an imaging study?
- Which studies belong to a clinically defined cohort?

### OHIF and DICOMweb

| Component | Platform | Role |
|---|---|---|
| OHIF viewer | Azure web surface | Interactive DICOM study viewing |
| DICOMweb proxy | Azure container app | Reads selected `.dcm` files from OneLake and serves DICOMweb responses |
| OneLake source | HDS Bronze shortcut | Holds the re-tagged study hierarchy |

The proxy needs a Fabric workspace role that grants OneLake DFS reads. A portal-only Viewer role is insufficient; the deployment assigns the required Contributor access.

### Reporting materialization

The toolkit creates or reuses `healthcare1_reporting_gold`, deploys its materialization notebook, resolves the healthy OHIF base URL, and writes deep-linkable study rows.

### Imaging report

The Power BI project reads the reporting lakehouse through Direct Lake and exposes cohort, modality, patient, study, and viewer-link experiences.

## Ontology path

[`phase-4/deploy-ontology.ps1`](../phase-4/deploy-ontology.ps1) builds typed projection tables and deploys ontology definitions through the Fabric API.

### ClinicalDeviceOntology

The clinical ontology can bind:

- Patient, Encounter, Condition, MedicationRequest, Observation, and ImagingStudy from HDS Silver projections.
- Device and DeviceAssociation from Silver-managed tables.
- DeviceTelemetry as an Eventhouse time-series binding.

Clinical alerts remain available through KQL and Activator when an AlertHistory ontology binding is not supported by the current Fabric import surface.

### DevicePayerOntology

When quality Gold state is available and selected, the payer-oriented ontology adds Claim, Payer, Diagnosis, PatientDiagnosis, Medication Adherence, Care Gap, Patient Risk, and High-Cost Claimant entities. It is kept separate so clinical agents are not grounded in payer-first semantics.

Existing ontologies are preserved by default to avoid a gap. Use `-ReplaceOntology` only when an intentional rebuild is required.

## Clinical Data Agents

[`phase-2/deploy-data-agents.ps1`](../phase-2/deploy-data-agents.ps1) creates or updates:

| Agent | Primary task | Data sources |
|---|---|---|
| Patient 360 | Build a single-patient clinical and current-vitals view | Eventhouse KQL, HDS Silver SQL, ClinicalDeviceOntology |
| Clinical Triage | Prioritize current device alerts and resolve affected patients | Eventhouse KQL, HDS Silver SQL, ClinicalDeviceOntology |
| Imaging Cohort | Find clinically defined populations with imaging | Gold OMOP, Silver imaging/reporting context |

A draft definition update is not the exit gate. The intended datasources must be present in the published agent configuration.

## Run it

A full deployment is recommended because it coordinates all Phase 4 prerequisites.

Historical targeted switches split this conceptual phase into two repairs.

Imaging/cohorting only:

```powershell
./Deploy-All.ps1 `
  -Phase3 `
  -FabricWorkspaceName "<fabric-workspace>" `
  -ResourceGroupName "<resource-group>" `
  -Location "eastus"
```

Ontology and ontology-aware clinical agents, without Phase 5 alerting:

```powershell
./Deploy-All.ps1 `
  -Phase4 `
  -FabricWorkspaceName "<fabric-workspace>" `
  -ResourceGroupName "<resource-group>" `
  -Location "eastus" `
  -SkipActivator
```

Override the companion repository path only when the sibling default is unsuitable:

```powershell
./Deploy-All.ps1 -Phase3 -DicomToolkitPath "<path-to-FabricDicomCohortingToolkit>" ...
```

## Verify before Phase 5

- Query the reporting Gold study table and confirm the `viewer_url` values point to the deployed healthy viewer.
- Open a report study link and render the DICOM instances through the proxy.
- Call the proxy health endpoint and require an indexed study count greater than zero.
- Inspect each ontology definition for entity types, data bindings, relationships, and contextualizations.
- Ask Patient 360 for the patient attached to a known active device and require both current KQL vitals and Silver clinical facts.
- Ask Clinical Triage for current urgent/critical devices and require patient resolution.
- Ask the cohort agent for a condition-plus-imaging cohort and require grounded results.

## Common failures

| Symptom | Check |
|---|---|
| Gold OMOP preflight fails | Complete Phase 3 OMOP and row gates before imaging deployment |
| OHIF opens but no study renders | Check proxy health, OneLake role, DICOM index, and study UID deep link |
| Reporting rows have no viewer URL | Viewer must be healthy before the materialization notebook runs |
| Ontology import fails | Check projection tables, Fabric IQ tenant enablement, and unsupported binding shapes |
| Existing ontology does not change | Preservation is the default; use `-ReplaceOntology` only for an intentional rebuild |
| Agent exists but ignores ontology | Inspect and publish the agent definition containing the ontology datasource |

## Source map

- [`Deploy-All.ps1`](../Deploy-All.ps1) — imaging toolkit coordination, ontology projection, and agent binding
- [`phase-4/deploy-ontology.ps1`](../phase-4/deploy-ontology.ps1) — ontology definition and deployment
- [`phase-4/deploy-graph-model.py`](../phase-4/deploy-graph-model.py) — graph model construction support
- [`phase-2/deploy-data-agents.ps1`](../phase-2/deploy-data-agents.ps1) — Patient 360 and Clinical Triage
- [`docs/ONTOLOGY-SETUP-GUIDE.md`](ONTOLOGY-SETUP-GUIDE.md) — ontology-specific setup notes

[← Phase 3 — HDS Bridge + Row Gates](phase-3-hds-bridge-and-row-gates.md) · [Next: Phase 5 — Bedside Alerting + Action →](phase-5-bedside-alerting-and-action.md)
