# Refreshing Data Agent schema selections

Fabric can accept and publish an agent definition containing name-only or stale
schema references. Publication alone does not prove those tables are usable.
The agent explorer can show "This schema has been deleted or you don't have
permission to view it" even though the lakehouse still exists.

## Prerequisites

- PowerShell 7.2+ and Azure CLI, signed in to the intended tenant with `az login`. The required `-TenantId` pins token acquisition and is checked before any Fabric request; the shared Azure CLI default is not changed.
- Permission to read and update the agents, publish their staging configuration,
  and read the underlying datasource metadata.
- Hydrated draft metadata: open each affected agent in Fabric and click **Refresh**,
  then let its datasource explorer finish loading. `getDefinition` alone does not
  reliably hydrate an agent that has never been opened.
- No unpublished instruction, example-query, or datasource-setting changes.
  Publish or reconcile those edits first. The command restores the published
  table contract, not a new table selection.

This utility reselects metadata; it does not refresh SQL endpoint data, populate
tables, create grounding tables, change permissions, or configure Operations Agents.

## Preview (no definition updates or publication)

From the repository root:

```powershell
.\utilities\Refresh-DataAgentSchemas.ps1 -TenantId '<tenant-guid>' -WorkspaceId '<workspace-guid>'
```

All Data Agents in the workspace are discovered, including companion imaging
agents. For a workspace that also contains unrelated agents, explicitly scope
the operation:

```powershell
.\utilities\Refresh-DataAgentSchemas.ps1 `
    -TenantId '<tenant-guid>' `
    -WorkspaceId '<workspace-guid>' `
    -AgentName 'Patient 360', 'Clinical Triage', 'HDS Multi-Layer Imaging Cohort Agent'
```

## Apply

```powershell
.\utilities\Refresh-DataAgentSchemas.ps1 `
    -TenantId '<tenant-guid>' `
    -WorkspaceId '<workspace-guid>' `
    -AgentName 'Patient 360', 'Clinical Triage', 'HDS Multi-Layer Imaging Cohort Agent' `
    -Apply `
    -BackupDirectory '.\state-tracking\data-agent-refresh'
```

`-Apply` is required for writes; `-WhatIf` previews the apply actions without
creating backup files or changing agents. Store backups outside version control:
definitions can contain tenant-specific instructions and datasource identifiers.

The command:

1. Reads all targeted definitions and completes all-agent preflight before writes.
2. Preserves published Lakehouse/KQL table and function selections, source identity,
   instructions, examples, and non-table datasource configuration.
3. Uses current draft schema/table/group/column IDs. Explicit column subsets are
   retained; a published name-only table selects all its current columns.
4. Rejects missing tables/functions/columns, ambiguous table names across schemas,
   unhydrated metadata, and unpublished non-selection edits instead of silently
   dropping or expanding the intended table contract.
5. Checks that the definition has not changed since preflight, saves a before
   backup, updates the draft, and publishes.
6. Verifies draft and published table/schema IDs, selections, and preserved
   non-table configuration, then saves an after backup.

Agents are processed sequentially. If an update or publication fails, the command
stops and reports the error; previously completed agents remain updated. Use the
before backup to inspect the original definition. For a timed-out write, inspect
the reported Fabric operation before retrying.

## Missing tables and permissions


A selected aggregate KQL Functions node without selected individual function
metadata is rejected rather than silently deselected. Refresh or reconcile that
published selection in Fabric before applying the utility.

A missing table is a deployment/data issue, not something schema refresh can fix.
In particular, the five `agent_*` grounding tables referenced by Payer Ops Triage
and Healthcare Graph Agent must exist before their contracts can be refreshed.
This command deliberately fails if they are absent.

If references resolve but a user still sees the warning, verify that user's
access to the source and SQL analytics endpoint. Agents execute under the asking
user's permissions. See [Fabric Data Agent concepts](https://learn.microsoft.com/fabric/data-science/concept-data-agent).

Deployment scripts that reconstruct name-only selections can reintroduce the
problem. Rerun this utility after refreshing metadata when necessary; it is not
automatically invoked during deployment.

## Offline tests

```powershell
.\utilities\tests\test_data_agent_refresh.ps1
.\phase-7\tests\test_data_agent_selection.ps1
```

The refresh tests use mocked Azure CLI and Fabric HTTP calls. They do not contact
Fabric or resume any agent repairs.
