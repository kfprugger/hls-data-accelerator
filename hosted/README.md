# Hosted HLS deployer

The hosted deployer runs the same FastAPI backend, React UI and deployment scripts as the local orchestrator inside Azure Container Apps. It replaces the former Azure Functions / Static Web App host; it does not replace the HDS Functions used for healthcare data export.

## Access

Admission to any hosted deployment evaluates the gateway's boolean access rule (`hosted/gateway/policy.py:104-105`): a user is admitted iff `((tid, oid) in HLS_ALLOWED_USERS or (tid, email) in HLS_ALLOWED_USERS or tid in HLS_ALLOWED_TENANTS)`. Because `tid` is the user's home tenant, B2B guest accounts are not admitted by a tenant entry.

The reference deployment at **https://hls.jbatl.dev** admits accounts whose home tenant is the Microsoft corporate tenant `72f988bf-86f1-41af-91ab-2d7cd011db47` (`microsoft.com` work accounts) plus a few operator accounts set in `HLS_ALLOWED_USERS`.

Anyone who deploys their own orchestrator from this repository approves their own domains, tenants, or users:
- **Whole-tenant approval via `-AllowedDomains <domain>` or `-AllowedTenants <tenantId>`**: `-AllowedDomains` resolves each domain at deploy time through Microsoft OpenID discovery (`https://login.microsoftonline.com/<domain>/v2.0/.well-known/openid-configuration`), and approving a domain admits that whole tenant. Consumer Microsoft-account tenants (`9188040d-6c67-4c5b-b112-36a304b66dad` and `f8cdef31-a31e-4b4a-93e4-5f571e91255a`) are refused by design. The gateway itself maintains only tenant GUID and user allowlists; it evaluates no runtime domain rules.
- **Individual user approval via `-AllowedUsers <tenantId:email>` or `<tenantId:oid>`**: Grants access only to specific users within specific tenants. Matching is case-insensitive on email and strict on tenant ID.
- **Fork default**: Forked deployments receive **no default allowlist**. A fresh deployment without an existing gateway refuses to deploy unless at least one allowed user, tenant, or domain is explicitly provided.
## Self-hosting your own orchestrator

### Prerequisites

- PowerShell 7.2+ (`pwsh`)
- Azure CLI with Bicep and the `containerapp` extension:
  ```powershell
  az extension add --name containerapp --upgrade
  az bicep install
  ```
- Git, tar, and GitHub CLI (`gh`) authenticated with repository admin rights on your target repository for GitHub Actions OIDC federation.
- Azure permissions: subscription Owner or User Access Administrator plus Contributor (to create user-assigned identities and role assignments), plus directory permissions to create Entra App Registrations.
- (Optional) Cloudflare API token with `Zone:Read` and `DNS:Edit` permissions for your DNS zone if using automated custom domain DNS and ACA managed certificates.

### Deployment profile

Copy `hosted/profiles/example.psd1` to `hosted/profiles/<name>.psd1` and configure your environment:

```powershell
@{
    SubscriptionId = '<your-subscription-guid>'
    TenantId       = '<your-tenant-guid>'
    ResourceGroup  = 'rg-hls-deployer'
    Location       = 'westus2'
    GitHubRepo     = '<your-github-org-or-user>/hls-data-accelerator'
    CustomDomain   = 'hls.example.com'
    DnsZone        = 'example.com'
    AllowedDomains = 'example.com'
    AllowedUsers   = '<your-tenant-guid>:admin@example.com'
    # Registry, Vault, and Storage default to deterministic names (acrhls<hash>, kv-hls-<hash>, sthls<hash>)
}
```

Parameter precedence:
1. Explicit command-line parameters outrank all other sources.
   - `-AllowedUsers` explicitly sets or replaces allowed users. Pass `''` to clear all allowed users.
   - `-AllowedTenants` explicitly sets or replaces allowed tenants. Pass `''` to clear all allowed tenants.
   - `-AllowedDomains` resolves domains to tenant IDs. The script adds resolved tenant IDs to the allowed tenants.
2. Live gateway configuration is authoritative on redeploy.
   - Profile `AllowedUsers` and `AllowedTenants` never apply on redeploy; live values are authoritative (including absent or empty) unless explicit parameters are passed.
   - The script preserves live `HLS_ALLOWED_USERS` and `HLS_ALLOWED_TENANTS` values when you do not pass those parameters.
   - The script preserves empty live allowlists.
   - The script does not apply profile `AllowedDomains` on redeploy unless you pass `-AllowedDomains` on the command line.
3. Deployment profiles apply on a fresh deployment (when no gateway exists yet).
   - The script uses profile `AllowedUsers`, `AllowedTenants`, and `AllowedDomains` when parameters are not bound.
4. Fork default applies when you do not specify allowlists.
   - Fork deployments receive no default allowlist. A fresh deployment without allowlist entries refuses to deploy.

### Revoking access

To revoke access so it sticks across future redeployments:
- To revoke all tenant access: run with `-AllowedTenants ''` (or update `HLS_ALLOWED_TENANTS=""` via Azure CLI).
- To revoke all user access: run with `-AllowedUsers ''` (or update `HLS_ALLOWED_USERS=""` via Azure CLI).

The live gateway configuration is authoritative. Future profile redeployments keep the empty allowlist. They do not re-add profile domains or users. `-SkipInfra` ignores allowlist parameters because it only updates container images and preserves existing container environment variables.
### WardFlow cardiology dependency

The core HLS accelerator (Phases 1–7 medallion lakehouse, FHIR synthetic ingestion, Rayfin imaging, and Databricks) is open source. The optional cardiology persona app (`caldova-cardio`) resides in a separate private repository.

- **Forks without WardFlow**: Pass `-WardflowCommit none` or leave `-WardflowPath` unset. The deployment builds an empty bundle `hls-wardflow-bundle:none`. The base accelerator and all other add-ons work normally; if cardiology is selected, it fails fast in the add-on execution step. The script defaults `WardflowCommit` to `none` only when neither `WardflowPath` nor `WardflowCommit` is set. When a WardFlow bundle must be published or resolved, if `WardflowPath` is set but the directory is missing or not a git checkout, the script halts with an error. Runs that do not publish or resolve a bundle (such as `-SkipImages` or `-WardflowCommit none` without `-PublishWardflowBundle`) do not check `WardflowPath`.
- **Operators with WardFlow**: Check out WardFlow locally, point `-WardflowPath` to it, and pass `-PublishWardflowBundle`. The script packages `caldova-cardio` and `rayfin-wardflow-persona-app`, publishing `hls-wardflow-bundle:<commit>` to ACR and setting the GitHub `WARDFLOW_REF` variable for CI releases. Both target paths must exist at the target commit. The script updates `WARDFLOW_REF` only on an explicit `-PublishWardflowBundle`. It never overwrites an existing 40-character commit SHA with `none`.

### Initial bootstrap command

```powershell
az login --use-device-code --tenant <your-tenant-guid>
az account set --subscription <your-subscription-guid>

# Bootstrap foundation, Entra app registration, GitHub OIDC federation, and deploy gateway
./hosted/Deploy-HostedOrchestrator.ps1 -DeploymentProfile <name> -BootstrapEntra -WardflowCommit none
```

Without a custom domain or Cloudflare token, the gateway is accessible via its default Azure Container Apps FQDN (`https://<app>.<defaultDomain>`).

## Operator deployment profiles

Each operator keeps their deployment profile outside Git (copy `hosted/profiles/example.psd1` to a local file, such as `~/.config/hls-hosted/profiles/<name>.psd1`, or pass the path directly to `-DeploymentProfile`):

```powershell
az login --use-device-code --tenant <tenant-id>
az account set --subscription <subscription-id>

# Full redeployment with bootstrap and WardFlow bundling
./hosted/Deploy-HostedOrchestrator.ps1 -DeploymentProfile ~/.config/hls-hosted/profiles/operator.psd1 -BootstrapEntra -PublishWardflowBundle

# Image-only release (e.g. after code changes without infra changes)
./hosted/Deploy-HostedOrchestrator.ps1 -DeploymentProfile ~/.config/hls-hosted/profiles/operator.psd1 -SkipInfra
```
## Safe allowlist operations

`HLS_ALLOWED_USERS` is a comma-separated list of `<tenant GUID>:<email>` or `<tenant GUID>:<object GUID>` pairs. Both tenant ID and user identifier must match; email matching is case-insensitive.

`HLS_ALLOWED_TENANTS` is a comma-separated list of tenant GUIDs. Adding a tenant admits all authenticated users from that tenant.

### Recommended: Update via script (safest)

Re-running the script with `-SkipImages` preserves existing live settings while safely unioning new domains or overriding users. Substitute `<domain-to-approve>` with a domain you own or trust:

```powershell
# Add another domain to the allowed tenants without touching images or clearing existing tenants
./hosted/Deploy-HostedOrchestrator.ps1 -DeploymentProfile ~/.config/hls-hosted/profiles/operator.psd1 -SkipImages -AllowedDomains '<domain-to-approve>'
```
When you omit `-ImageTag`, `-SkipImages` reuses the live gateway image and live sandbox image from Container Apps. It does not rebuild or change images. If you supply an explicit `-ImageTag`, that image tag must already exist in the container registry.

### Direct CLI update

If updating the Container App directly with `az containerapp update`, **always include both `HLS_ALLOWED_USERS` and `HLS_ALLOWED_TENANTS`** to prevent wiping the tenant allowlist. Never use `--replace-env-vars` as that would delete other critical runtime configuration:

```powershell
az containerapp update \
  --subscription <subscription-id> \
  --resource-group rg-hls-deployer \
  --name hls-gateway \
  --set-env-vars \
    'HLS_ALLOWED_USERS=<tenant-id>:<email>,<tenant-id>:<email>' \
    'HLS_ALLOWED_TENANTS=72f988bf-86f1-41af-91ab-2d7cd011db47'
```

## Architecture

- `hls-gateway` is the only external Container App. Entra organizations sign-in identifies a user; tenant-and-user pairs or allowed tenant GUIDs authorize access. The gateway proxies UI, API and streaming logs to that user's internal sandbox without buffering SSE. The gateway discovers the container registry directly from `HLS_SANDBOX_IMAGE` rather than requiring a separate registry URL environment variable.
- A sandbox is `hls-sbx-<12 hex characters of SHA256(tid:oid)>`, with internal ingress on 7071, 2 vCPU / 4 GiB and exactly one replica. Maximum five concurrent sandboxes. After two hours without activity and with no active runs, the gateway deletes the sandbox container app. A new sandbox restores its state from Azure Files.
- The storage account has an SMB share and registry table, both named `sandboxes`. The environment storage mount is `sandboxes`; each sandbox mounts its own user-key subdirectory at `/data` and mounts the entire shared Azure Files share at `/data-share`. The volume sets `uid=10001,gid=10001,dir_mode=0750,file_mode=0640,nobrl,mfsymlinks,cache=strict` so the non-root runtime owns its files.
- **Security model note and cross-sandbox data isolation**: Every sandbox mounts the whole `sandboxes` share at `/data-share` (only its own subdirectory at `/data`). Cross-user isolation of history files relies on application code (peer SQLite databases are opened read-only; import occurs only for a verified matching target tenant and subscription), while Azure credentials are sealed with a per-sandbox key (`.encrypted-azure-auth.bin` encrypted via AES-256-GCM with a 256-bit key derived from `HLS_GATEWAY_KEY` and the user's `tid:oid`). Seal writes, restores, sign-out and the startup cleanup serialize on an exclusive-create `.encrypted-azure-auth.bin.lock` file beside the seal, because the `nobrl` mount does not share byte-range locks between sandboxes. This shared storage volume visibility is a known architectural limit.
- `id-hls-gateway` has Contributor on the resource group, Storage Table Data Contributor on the storage account, Key Vault Secrets User on the vault, Managed Identity Operator on `id-hls-sandbox`, and AcrPull on the container registry. The sandbox identity has AcrPull only.
- The Container Apps environment logs to Log Analytics. Key Vault holds `gateway-client-secret` and `gateway-session-key`; the gateway uses managed-identity Key Vault references.

## Release flow

`.github/workflows/hosted-orchestrator.yml` runs on pushes to `main` or manual dispatch on `main`. Actions use GitHub OIDC through `azure/login@v2`; no long-lived Azure deployment password is stored. The federated credential trusts `refs/heads/main`.

1. Check out HLS and verify repository variable `WARDFLOW_REF` (or manual `wardflow_commit` input) is a 40-hex commit SHA or `none`.
2. Invoke `Deploy-HostedOrchestrator.ps1 -SkipInfra -WardflowCommit <sha>` with a unique `<HLS SHA>-<run ID>-<attempt>` image tag. ACR builds `hls-gateway:<tag>` and `hls-orchestrator-sandbox:<tag>` (using `node:22-bookworm-slim` in the UI build stage) and rolls out the gateway plus its desired sandbox image.
3. Existing sandboxes update only when their active run count is zero; active deployments retain their original runtime until safe to update.

## Local static checks

Run static checks offline without Azure login:

```powershell
az bicep build --file hosted/infra/main.bicep --outfile /tmp/hls-hosted-main.json
$tokens = $null; $errors = $null
[System.Management.Automation.Language.Parser]::ParseFile((Resolve-Path hosted/Deploy-HostedOrchestrator.ps1), [ref]$tokens, [ref]$errors) | Out-Null
if ($errors) { $errors | Format-List; throw 'PowerShell parse failed' }
```

Run test suite:
```bash
python -m pytest hosted -q
```

## Platform acceptance checks

Run the following checks after platform bootstrap and before starting deployment workloads:

1. **Allowed and denied identities:** Sign in with an approved tenant/email pair, an approved tenant/object-ID pair, and a denied identity. Confirm a matching email in a different tenant receives 403 and no sandbox. Confirm the 403 page directs the user to ask the deployer's operator and displays their tenant ID and object ID.
2. **Sandbox mount and history:** Create a new sandbox with a previously unused user key; prove kubelet creates its share subdirectory and UID/GID 10001 can write `/data`. Save form/deployment history, wait for its snapshot, delete/recreate the sandbox, and verify history is restored without SQLite locks on SMB. Azure authentication must not survive restart/recreation.
3. **Proxy and streaming:** Load the UI and call an API through the gateway; verify the sandbox cannot be reached publicly and forged `X-HLS-*` headers do not cross the boundary. Open `/api/deploy/{id}/logs/stream` for a smoke run and observe incremental SSE events rather than a buffered final response.
4. **Device-code login and logout:** Complete both Azure CLI and Azure PowerShell sign-ins for the selected tenant/subscription, check both contexts, then log out and confirm both are cleared. If Conditional Access blocks device code, verify the actionable explanation; do not bypass it.
5. **Rayfin audiences:** Locally decode the ephemeral `RAYFIN_TOKEN` JWT used by each command without logging the token. Verify the expected tenant and Fabric audience (`https://api.fabric.microsoft.com`) for management/up, and Power BI audience (`https://analysis.windows.net/powerbi/api`) for build/semantic-model probes. Confirm real commands accept those audiences.
6. **Idle-only image rollover:** Publish a new image while a smoke run is active; confirm that sandbox retains its existing image. After active runs become zero, confirm the new image is applied and history remains. A complete current-format auth seal restores credentials when the sandbox key is unchanged. Legacy, invalid or foreign seals require a new Azure sign-in; recreating a sandbox rotates its key and does not restore its previous seal.
7. **Custom-domain HTTPS:** Verify `https://<CustomDomain>/healthz` returns HTTP 200 with a trusted certificate, sign-in returns through the custom-domain callback, DNS remains unproxied, and the gateway's latest revision is healthy.
