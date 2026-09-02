# Microsoft HDS v1.4.0 Source Deployment Guide

HDS is deployed automatically from Microsoft source. Do not create a Healthcare Data Solution item in the Fabric portal and do not add a placeholder item to satisfy downstream checks.

## Source and generated content

- Immutable source: `vendor/microsoft-hds/1.4.0/HDS.SourceCode` and `DTT.SourceCode`
- Generated stage: `.hds-build/1.4.0`
- Deployment entry point: `hds-source/Deploy-HdsSource.ps1`
- Shared implementation: `orchestrator/activities/deploy_hds_source.py`

The stage contains Microsoft build artifacts, one HDS wheel, one DTT wheel, patched deployment notebooks, and `environment.yml` with `scipy==1.11.4`.

## Local validation

```powershell
pwsh -NoProfile -File ./setup-prereqs.ps1
pwsh -NoProfile -File ./hds-source/Deploy-HdsSource.ps1 `
  -FabricWorkspaceName local-validation `
  -ValidateOnly
```

`-ValidateOnly` makes no cloud calls. It verifies:

- the Microsoft artifact validator manifest;
- exact HDS and DTT wheel versions and cardinality;
- nine deployment notebooks and three validation notebooks;
- managed lakehouse, config-notebook, and environment names;
- `%run healthcare1_msft_config_notebook` references;
- absence of `healthcare1_msft_environment` and unresolved adapter state.

## Automated deployment flow

`Deploy-All.ps1` validates the payload before its first cloud mutation. After workspace and RTI foundation creation, it:

1. Creates or reuses `deployment_lakehouse`.
2. Streams `hds-build-artifacts` to OneLake in 4 MiB chunks.
3. Creates `deployment_notebooks` and `validation_notebooks` folders.
4. Creates or updates all Microsoft bootstrap notebook definitions.
5. Attaches `deployment_lakehouse` to `master_deployer`.
6. Starts `RunNotebook` and follows its returned job location.
7. Waits for environment publishing and the master job to complete.
8. Validates the live artifact contract.
9. Runs RTI enrichment and the existing ordered HDS pipelines.

## Live contract check

```powershell
pwsh -NoProfile -File ./hds-source/Deploy-HdsSource.ps1 `
  -FabricWorkspaceName "hls-demo" `
  -ContractOnly
```

The contract requires the published `healthcare1_environment`, expected lakehouses, all source notebooks and pipelines, semantic models and reports, required Clinical/Imaging/OMOP pipelines, and a completed `master_deployer` job.

## Expected core artifacts

| Type | Name |
|---|---|
| Environment | `healthcare1_environment` |
| Lakehouse | `healthcare1_msft_admin` |
| Lakehouse | `healthcare1_msft_bronze` |
| Lakehouse | `healthcare1_msft_silver` |
| Lakehouse | `healthcare1_msft_gold_omop` |
| Lakehouse | `healthcare1_msft_gold_cma` |
| Notebook | `healthcare1_msft_config_notebook` |
| Pipeline | `healthcare1_msft_clinical_data_foundation_ingestion` |
| Pipeline | `healthcare1_msft_imaging_with_clinical_foundation_ingestion` |
| Pipeline | `healthcare1_msft_omop_analytics` |

## Retry and conflict rules

- Exact same-type/name items are reused or updated.
- Existing lakehouse tables and folders are reused.
- A same-name item of another type fails with the conflicting item ID.
- Names are never suffixed because that breaks downstream references.
- 429, 5xx, and Fabric inbound-policy denials are retried.
- Other 4xx responses fail immediately.
- Environment publish fails after 75 minutes; the master job fails after 90 minutes.

## Troubleshooting

### Missing `orchestrator/.venv`

Run:

```powershell
pwsh -NoProfile -File ./setup-prereqs.ps1
```

The deployment wrapper never installs Python packages during a cloud run.

### Payload validation failure

Delete `.hds-build/1.4.0` and rerun `-ValidateOnly`. Do not edit `vendor/`. If vendor integrity differs from the Microsoft download, restore the original source package first.

### Environment publish failure

Open `healthcare1_environment` in Fabric and inspect publish details. Resolve the reported library conflict, then rerun the same deployment. The source phase reuses the environment and reconciles its definitions.

### Missing pipeline placeholders

The host validator reports every missing display name. Confirm source notebooks deployed under their `healthcare1_msft_*` names and rerun the source phase. The deployment never treats a skipped pipeline as success.

### Fabric inbound communication policy

`RequestDeniedByInboundPolicy` is transient in this workflow and receives bounded retries. If it persists, correct the tenant/workspace inbound policy; do not bypass contract validation.

### Downstream row gates fail

First run `-ContractOnly`. If the contract passes, inspect Clinical, Imaging, and OMOP job histories and the Bronze/Silver row counts emitted by `phase-2/storage-access-trusted-workspace.ps1`.

## Teardown

The normal teardown removes all source-created items and then deletes `deployment_notebooks` and `validation_notebooks`. It does not delete or modify the local vendored Microsoft source.
