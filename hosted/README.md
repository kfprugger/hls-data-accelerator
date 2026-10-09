# Hosted HLS deployer

The hosted portal at **https://hls.jbatl.dev** runs the same FastAPI backend, React UI and deployment scripts as the local orchestrator. It replaces the former Azure Functions / Static Web App host; it does not replace the HDS Functions used for healthcare data export.

## Architecture

- `hls-gateway` is the only external Container App. Entra organizations sign-in identifies a user; tenant-and-user pairs authorize access, with whole-tenant access only by explicit opt-in. The gateway proxies UI, API and streaming logs to that user's internal sandbox without buffering SSE.
- A sandbox is `hls-sbx-<12 hex characters of SHA256(tid:oid)>`, with internal ingress on 7071, 2 vCPU / 4 GiB and exactly one replica. Maximum five sandboxes. After two hours without activity and with no active runs, the gateway deletes the app. A new sandbox restores its history from Azure Files.
- `sthlsdeployer` has an SMB share and registry table, both `sandboxes`. The environment storage mount is `sandboxes`; each sandbox mounts only its own user-key subdirectory at `/data`. The volume sets `uid=10001,gid=10001,dir_mode=0750,file_mode=0640,nobrl,mfsymlinks,cache=strict` so the non-root runtime owns its files. Kubelet creates the `subPath` directory on first mount; confirm that behavior in the live platform smoke test before any full deployment.
- `id-hls-gateway` has Contributor on `rg-hls-deployer`, Storage Table Data Contributor on the storage account, Key Vault Secrets User on the vault, Managed Identity Operator on `id-hls-sandbox`, and AcrPull on `acrhlsdeployer`. The sandbox identity has only AcrPull.
- `cae-hls-deployer` is a Consumption environment in `westus2`, logging to `log-hls-deployer`. `kv-hls-deployer` holds `gateway-client-secret` and `gateway-session-key`; the app uses managed-identity Key Vault references. No storage account keys are emitted by Bicep: the environment mount obtains its key through `listKeys()` inside the deployment.
- Both images are private ACR images. Each release archives committed HLS source. WardFlow cardiology source comes from the data-only image `hls-wardflow-bundle:<full commit>`, published from an operator machine with the wardflow checkout (`-PublishWardflowBundle`), so CI never holds credentials for the private WardFlow repository. The commit is recorded in `/app/wardflow/.pinned-commit`. The Docker build context contains no working-tree credentials or history. Builds target `linux/amd64`.
- Sandbox tool pins are in `sandbox/Dockerfile`: Azure CLI 2.91.0, PowerShell 7.6.6, Az 16.4.0, Bicep 0.48.1 and AzCopy 10.32.8, plus explicit extension versions. Update pins deliberately and rerun platform acceptance before using a new image.

## First bootstrap

Prerequisites: PowerShell 7.2+, Azure CLI with Bicep and the `containerapp` extension, `git`, `tar`, `gh`, and a local Wardflow checkout. The Azure operator needs app-registration/service-principal creation rights and Owner, or User Access Administrator plus Contributor, at subscription scope (inherited/group assignments are accepted; constrained role assignments are not). The bootstrap preflight checks directory roles or the member app-creation policy, subscription role assignments, and `gh` authenticated as `kfprugger` with admin access to `kfprugger/hls-data-accelerator`, failing closed before creating the RG if it cannot verify them. Cloudflare token permissions are Zone:Read and DNS:Edit for **jbatl.dev only**. The operator loads the token into `CLOUDFLARE_API_TOKEN` from their own secret store; it is not stored in or fetched from `kv-hls-deployer`.

All commands below run from the repository root after the hosted implementation is committed. The script deliberately builds `HEAD`, not uncommitted files. It never logs in, switches subscriptions, or changes branches itself.

```powershell
# Explicit interactive setup; the script refuses any other current tenant/subscription.
az login --use-device-code --tenant c77e97fc-1859-4575-8c8b-53d74bc35a63
az account set --subscription 0525a464-e087-4084-a24e-a90396a83c15
az extension add --name containerapp --upgrade
az bicep install

# gh must be authenticated as kfprugger for OIDC and repository configuration.
gh auth status
# Load CLOUDFLARE_API_TOKEN from your own secret store into this process; never save it in source.
./hosted/Deploy-HostedOrchestrator.ps1 -BootstrapEntra -PublishWardflowBundle
```

That one invocation performs this sequence:

1. Assert the current Azure subscription **and tenant**, complete the bootstrap permission preflight, then deploy the foundation (`deployGateway=false`). This breaks the new-registry / new-image / new-secret dependency cycle without deploying a placeholder container.
2. Grant the invoking bootstrap principal Key Vault Secrets Officer on this vault so it can initialize secrets. Create/update `hls-deployer-portal` as `AzureADMultipleOrgs` with default-FQDN and `https://hls.jbatl.dev/auth/callback` Web redirects, optional email/upn ID-token claims, and delegated openid, profile, email and User.Read permissions. Mint a 12-month app secret only if absent or within 30 days of expiry; store it directly in Key Vault. Create the random session-signing key only if absent.
3. Inspect the repository's OIDC customization (including immutable owner/repository IDs), create/update the single-tenant `hls-deployer-github` app and main-branch federation, grant AcrPush on the registry plus Contributor on the RG, and set `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID` repository secrets. This step does not change `WARDFLOW_REF`.
4. Publish `hls-wardflow-bundle:<WardFlow HEAD>` from the local checkout (committed `caldova-cardio/` only), then set `WARDFLOW_REF` only after the bundle exists. Archive HLS HEAD into a temporary context, run both ACR builds, and deploy the actual gateway image and sandbox-image setting. Wait up to 10 minutes for the latest revision to be Running/Healthy (RunningAtMaxScale also qualifies) and its default-FQDN `/healthz` to return HTTP 200; image-only releases use the same gate.
5. With `CLOUDFLARE_API_TOKEN`, upsert a **DNS-only** CNAME `hls` to the gateway FQDN and TXT `asuid.hls` to its verification ID. Wait for public DNS, register the custom domain with binding `Disabled`, then deploy its ACA managed certificate and `SniEnabled` binding. Wait up to 20 minutes for the custom-domain HTTPS `/healthz` to return HTTP 200. Keep Cloudflare proxying **off** for managed-certificate validation and renewal. Without the token, the gateway still works on its default FQDN; existing TLS bindings are preserved, and new binding is explicitly skipped.

To ship new cardiology code, commit it on WardFlow `jb-dev`, then publish its bundle. This also sets the `WARDFLOW_REF` repository variable when `gh` is signed in as `kfprugger`, and releases images built from it:

```powershell
./hosted/Deploy-HostedOrchestrator.ps1 -PublishWardflowBundle -SkipInfra -ImageTag "$(git rev-parse --short HEAD)-wf$(git -C ~/git/.worktrees/wardflow-jb-dev rev-parse --short HEAD)"
```

To finish DNS after an initial run without a Cloudflare token, load the token and run:

```powershell
./hosted/Deploy-HostedOrchestrator.ps1 -SkipImages
```

The default parameters pin the approved subscription, tenant, RG and region, Wardflow worktree `~/git/.worktrees/wardflow-jb-dev`, and custom domain `hls.jbatl.dev`. `-ImageTag` defaults to the HLS short commit SHA. `-ClientId`, `-AllowedUsers` and `-AllowedTenants` override bootstrap settings; existing gateway settings are preserved on later infrastructure deployments unless overridden. `-CustomDomain ''` deploys without a custom binding. `-SkipImages` expects both specified tags already in ACR. `-SkipInfra` requires an existing bootstrapped gateway and updates its image and `HLS_SANDBOX_IMAGE` without reapplying infrastructure, DNS, secrets or allowlists.

For unattended normal releases, neither Graph permissions nor the bootstrap operator's vault data role are required. The bootstrap role can be revoked after provisioning if another authorized operator owns secret rotation. Re-run `-BootstrapEntra -SkipImages` before the client secret expires. This retains the session key and normalizes app permissions and callbacks.

## Release flow

`.github/workflows/hosted-orchestrator.yml` runs on pushes to `main`, or manual dispatch on `main`. Actions use GitHub OIDC through `azure/login@v2`; no Azure deployment password is stored. The federated credential only trusts `refs/heads/main`.

1. Check out HLS and require repository variable `WARDFLOW_REF` (or the manual `wardflow_commit` input) to be a full commit SHA whose `hls-wardflow-bundle` is already in ACR; the build fails closed otherwise.
2. Invoke `Deploy-HostedOrchestrator.ps1 -SkipInfra -WardflowCommit <sha>` with a unique `<HLS SHA>-<run ID>-<attempt>` image tag. ACR builds `hls-gateway:<tag>` and `hls-orchestrator-sandbox:<tag>` (copying WardFlow from the bundle) and the script rolls out the gateway plus its desired sandbox image.
3. Existing sandboxes are changed only when their `active_runs` is zero; active deployments retain their original runtime until safe to update. Image publishing does not restart one-shot data loaders.

Infrastructure changes are operator-run full script deployments, not CI role-assignment writes. Concurrent releases are serialized and an in-flight release is never canceled by a newer push.

## Allowlist operations

`HLS_ALLOWED_USERS` is a comma-separated list of `<tenant GUID>:<email>` or `<tenant GUID>:<object GUID>` pairs. Both the verified tenant ID and the user identifier must match; email matching is case-insensitive. Email claims are tenant-controlled: the same email from another tenant is denied. Prefer object-ID pairs when enrolling users; the 403 page tells them to send their tenant ID and object ID to the operator. Email remains available for display.

`HLS_ALLOWED_TENANTS` is a separate, explicit whole-tenant opt-in. Adding a tenant admits all its users, not merely the listed pairs. It defaults to empty (no tenant-wide access); empty both lists denies everyone. Defaults allow the three tenant-bound accounts below, not those email strings from arbitrary tenants.

```powershell
az containerapp update --subscription 0525a464-e087-4084-a24e-a90396a83c15 `
  --resource-group rg-hls-deployer --name hls-gateway `
  --set-env-vars 'HLS_ALLOWED_USERS=8d038e6a-9b7d-4cb8-bbcf-e84dff156478:joey@brakekat.com,c77e97fc-1859-4575-8c8b-53d74bc35a63:joey@jbatl.dev,72f988bf-86f1-41af-91ab-2d7cd011db47:jbrakefield@microsoft.com' 'HLS_ALLOWED_TENANTS='
```

Do not use `--replace-env-vars`: it would erase required runtime settings. User sign-in does not grant access to their Azure tenant. Each user authenticates Azure CLI and Azure PowerShell from the sandbox's device-code UI. A Conditional Access policy that blocks device code must be fixed by the user's tenant administrator, or the user must run locally; there is no service-principal fallback.

## Security and persistence

- Portal authentication and deployment authorization are separate. The host identity cannot deploy into users' tenants. Azure credentials are never retained on the share: device-code tokens and CLI/PowerShell caches live only in the container's writable home and vanish when the sandbox is deleted or restarted. Use logout to clear both caches without deleting history. A recreated or restarted sandbox requires new device-code logins. Restrict access to deployment history and logs even though the share is not a credential store.
- `kv-hls-deployer` and `sthlsdeployer` carry `SecurityControl=Ignore`. Without it, the jbatl.dev tenant's MCAPSGov "Deploy and Modify" policies disable their public network access and storage shared-key access, which breaks Key Vault references, the gateway's table registry and the Container Apps SMB mount (it needs the account key). Access stays RBAC-only except that SMB mount. The policy-compliant alternative is a VNet-integrated environment with private endpoints and an NFS Premium share.
- SQLite uses a local WAL database. Backups are first produced as a closed local SQLite file, then copied to a temporary file on `/data` and atomically published with `os.replace`; restore copies the snapshot locally before opening it. No SQLite connection or lock touches SMB.
- Internal ingress and a per-sandbox random gateway secret guard the backend. The gateway strips client-supplied `X-HLS-*` headers and injects authenticated identity headers; public health is the sole backend gateway-key exception. The app and its sandbox run as non-root users.
- Azure Files subpaths and internal ingress provide application isolation, not a hostile-code / tenant-grade storage boundary: all sandboxes share an ACA environment and SMB share. Trusted allowlisted operators must not be treated as arbitrary untrusted code runners. The gateway's RG Contributor permission is intentionally powerful and confined to the dedicated host RG.
- Storage requires TLS 1.2, HTTPS and no public blob access. Key Vault uses RBAC, 90-day soft delete and purge protection. Secret values are never template outputs, command-line arguments or GitHub variables. Restrict diagnostics and operator access accordingly.
- Per-deployment teardown is subscription/tenant-pinned and removes owned deployment front ends, not the shared hosted control plane. Databricks' isolated `fhir-export-databricks` copy lives in the deployment storage account and is removed with that deployment's RG. Sandbox expiry does not delete deployment resources or persistent history.
- Before an initial Databricks snapshot copy, the destination container is emptied and verified empty. Sorted, case-sensitive relative blob-name manifests must match source-before, source-after and destination; equal counts alone do not pass. Add-later fresh FHIR exports also empty the destination first, preventing stale files from previous attempts.
- The source cutover does not delete any previously deployed Functions/SWA resources automatically. Inventory and explicitly retire old infrastructure separately, after preserving any history.

## Costs and checks

The gateway remains warm (0.5 vCPU / 1 GiB, one replica); each sandbox remains at 2 vCPU / 4 GiB while allocated. The maximum five concurrent sandboxes means up to 10 vCPU / 20 GiB in addition to the gateway. Idle eviction limits sandbox runtime, but active deployments are not killed to reduce costs. Additional charges are ACR Basic and builds, Azure Files used capacity/transactions, table operations, Key Vault calls, Log Analytics ingestion/30-day retention, and networking. ACA managed certificates have no separate certificate purchase. Consult current westus2 prices and observed duty cycle before budgeting; this is not a zero-cost service. Set RG budgets and monitor persistent Files and log growth.

Local static checks (no login or deployment required):

```powershell
az bicep build --file hosted/infra/main.bicep --outfile /tmp/hls-hosted-main.json
$tokens = $null; $errors = $null
[System.Management.Automation.Language.Parser]::ParseFile((Resolve-Path hosted/Deploy-HostedOrchestrator.ps1), [ref]$tokens, [ref]$errors) | Out-Null
if ($errors) { $errors | Format-List; throw 'PowerShell parse failed' }
actionlint .github/workflows/hosted-orchestrator.yml
```

A successful static check is not proof of live DNS, OIDC, secret resolution or a deployment. Run the following checks after authorized platform bootstrap and before starting any full HLS workload deployment.

## Platform acceptance checks

Record results for the exact gateway/sandbox image tags before any full deployment; rerun after platform changes. Use disposable test resources and identities, never real production workloads for the smoke test.

1. **Allowed and denied identities:** sign in with an approved tenant/email pair, an approved tenant/object-ID pair, and a denied identity. Confirm a matching email in a different tenant receives 403 and no sandbox. Verify explicit tenant-wide opt-in separately and remove it afterwards.
2. **Sandbox mount and history:** create a new sandbox with a previously unused user key; prove kubelet creates its share subdirectory and UID/GID 10001 can write `/data`. Save form/deployment history, wait for its snapshot, delete/recreate the sandbox, and verify history is restored without SQLite locks on SMB. Azure authentication must not survive restart/recreation.
3. **Proxy and streaming:** load the UI and call an API through the gateway; verify the sandbox cannot be reached publicly and forged `X-HLS-*` headers do not cross the boundary. Open `/api/deploy/{id}/logs/stream` for a smoke run and observe incremental SSE events rather than a buffered final response.
4. **Device-code login and logout:** complete both Azure CLI and Azure PowerShell sign-ins for the selected tenant/subscription, check both contexts, then log out and confirm both are cleared. If Conditional Access blocks device code, verify the actionable explanation; do not bypass it.
5. **Rayfin audiences:** locally decode the ephemeral `RAYFIN_TOKEN` JWT used by each command without logging the token. Verify the expected tenant and Fabric audience (`https://api.fabric.microsoft.com`) for management/up, and Power BI audience (`https://analysis.windows.net/powerbi/api`) for build/semantic-model probes. Confirm real commands accept those audiences.
6. **Idle-only image rollover:** publish a new image while a smoke run is active; confirm that sandbox retains its existing image. After `active_runs` becomes zero, confirm the new image is applied, history remains and credentials require reauthentication after restart.
7. **Custom-domain HTTPS:** verify `https://hls.jbatl.dev/healthz` returns HTTP 200 with a trusted certificate, sign-in returns through the custom-domain callback, DNS remains unproxied, and the gateway's latest revision is healthy.

### Current deployment verification (2026-10-08)

- Public custom-domain HTTPS health passed; the gateway is hosted in the approved jbatl.dev subscription.
- A real `joey@brakekat.com` portal sign-in created an internal sandbox and served the deployment UI.
- In that sandbox, UID 10001 successfully wrote, renamed, read and deleted a file on `/data`.
- Azure CLI 2.91 uses `https://login.microsoft.com/device`; the corrected live sandbox API issued both Azure CLI and Az PowerShell device codes. A regression test covers this URL. Logout was reproduced failing on an already-empty PowerShell context, then verified returning HTTP 200/`signed_out` both in the Linux image and on the live sandbox after disconnecting before clearing the context. The deployment wizard no longer substitutes mock subscriptions or capacities for missing Azure credentials.
- On 2026-10-09, the customer completed Azure CLI authentication in the real sandbox as `joey@brakekat.com`, tenant `8d038e6a-9b7d-4cb8-bbcf-e84dff156478`, subscription `9bbee190-dc61-4c58-ab47-1275cb04018f`. A real SDK token also resolved to that customer tenant. PowerShell authentication remained pending in its separate cache.
- Databricks region preflight initially failed on Azure CLI 2.91's unsupported subscription argument to `account list-locations`. The corrected subscription-pinned ARM lookup passed against the cached BrakeKat account, alongside Rayfin/tool and cardiology quota/app-registration checks. This local correction smoke does not substitute for hosted end-to-end acceptance.
- **Pending:** completing customer PowerShell sign-in, full hosted preflight, the cross-tenant deployment with all add-ons, deployment evaluation, teardown, and the main-branch GitHub OIDC release. Do not treat gateway health or static checks as proof of those paths.
