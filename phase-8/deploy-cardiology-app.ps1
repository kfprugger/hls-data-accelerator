[CmdletBinding()]
param (
    [Parameter(Mandatory)][string]$ResourceGroupName,
    [string]$Location = "eastus2",
    [hashtable]$Tags = @{},
    [string]$ExpectedTenantId = "8d038e6a-9b7d-4cb8-bbcf-e84dff156478",
    [string]$ExpectedSubscriptionId = "9bbee190-dc61-4c58-ab47-1275cb04018f",
    [string]$CardiologyAppPath = "",
    [string[]]$CardiologyAppUsers = @(),
    # Additional reviewers must also be assigned sign-in users. The deployer reviews by default.
    [string[]]$CardiologyReviewerUsers = @(),
    # Lowercase letters and digits only (Azure naming; also keeps it inert inside
    # the JMESPath and OData string literals built from it). Bicep caps it at 12.
    # Options = 'None': ValidatePattern ignores case unless told otherwise.
    # \A...\z, not ^...$: .NET's $ also matches before a trailing newline.
    [ValidatePattern('\A[a-z0-9]{1,12}\z', Options = 'None')][string]$Prefix = "cardioe2e",
    # HDS data the app serves: it reads gold over the Fabric SQL endpoint (the
    # app identity gets Viewer on the workspace) and writes FHIR first (FHIR
    # Data Contributor on the service). Defaults: the med-0906 environment.
    [ValidatePattern('\A[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\z')][string]$FabricWorkspaceId = "f8f84d68-cfa1-4460-95d1-943fac43248a",
    [ValidatePattern('\A[a-z0-9-]+\.datawarehouse\.fabric\.microsoft\.com\z')][string]$FabricSqlHost = "nkhahdl5to4ezo6p5bg76flepa-nbg7r6fbz5qejforsq72yqzeri.datawarehouse.fabric.microsoft.com",
    [ValidatePattern('\A[A-Za-z0-9_]{1,128}\z')][string]$FabricGoldDatabase = "healthcare1_reporting_gold",
    [ValidatePattern('\A/subscriptions/[0-9a-f-]{36}/resourceGroups/[A-Za-z0-9._()-]+/providers/Microsoft\.HealthcareApis/workspaces/[a-z0-9]+/fhirservices/[a-z0-9]+\z')][string]$FhirServiceId = "/subscriptions/9bbee190-dc61-4c58-ab47-1275cb04018f/resourceGroups/rg-med-0906/providers/Microsoft.HealthcareApis/workspaces/hdwsfrzkspw34dzci/fhirservices/fhirfrzkspw34dzci",
    [ValidatePattern('\Ahttps://[a-z0-9-]+\.fhir\.azurehealthcareapis\.com\z')][string]$FhirUrl = "https://hdwsfrzkspw34dzci-fhirfrzkspw34dzci.fhir.azurehealthcareapis.com",
    # Masimo pulse-oximeter stream the app reads pulse rate and SpO2 from: an
    # Eventhouse KQL database in workspace -FabricWorkspaceId. No extra grant:
    # the identity's workspace Viewer role covers KQL reads there.
    [ValidatePattern('\Ahttps://[a-z0-9-]+(\.[a-z0-9-]+)?\.kusto\.fabric\.microsoft\.com\z')][string]$EventhouseQueryUri = "https://trd-0vj4c1a07qab5cxg8f.z0.kusto.fabric.microsoft.com",
    [ValidatePattern('\A[A-Za-z0-9_.-]{1,260}\z')][string]$EventhouseDatabase = "MasimoEventhouse"
)

# Phase 8 — Cardiology App.
#
# Builds the private cardiology app (kfprugger/caldova-cardio-e2e, from a local
# checkout) into one image, deploys it to Azure Container Apps with
# bicep/cardiology-app.bicep, puts Entra sign-in in front of it, and does not
# report success until the live URL answers health and enforces sign-in.
#
# Only accounts assigned to the app registration can sign in: the deploying
# az user always, plus -CardiologyAppUsers. /api/health stays anonymous so the
# orchestrator can probe it.
#
# The app's user-assigned identity is given the HDS access its live profile
# needs (Viewer on Fabric workspace -FabricWorkspaceId, FHIR Data Contributor on
# -FhirServiceId) before any revision that uses it is deployed. Workspace Viewer
# also covers its KQL reads of -EventhouseDatabase, so that needs no grant.

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Split-Path -Parent $ScriptRoot
$Template = Join-Path $RepoRoot "bicep/cardiology-app.bicep"
$AppRepo = "kfprugger/caldova-cardio-e2e"
$AppBranch = "feature/cardiology-integration"
$ImageRepo = "cardiology-app"
$DefaultAccessRole = "00000000-0000-0000-0000-000000000000"
$FhirDataContributor = "5a1fc7df-4bf1-4951-a576-89034ee01acd"
$FabricApi = "https://api.fabric.microsoft.com"
$script:authContainerUri = ""
$script:appIdentityResourceId = ""

function Get-AuthConfigUrl {
    return "https://management.azure.com/subscriptions/$ExpectedSubscriptionId/resourceGroups/$ResourceGroupName/providers/Microsoft.App/containerApps/$appName/authConfigs/current?api-version=2026-07-01"
}

function Get-AuthConfig {
    return (Invoke-Az @("rest", "--method", "GET", "--url", (Get-AuthConfigUrl), "--query", "properties", "-o", "json")).Out | ConvertFrom-Json
}

function Invoke-Az {
    param ([Parameter(Mandatory)][string[]]$Arguments, [switch]$AllowFailure)
    $lines = & az @Arguments --only-show-errors 2>&1
    $code = $LASTEXITCODE
    $out = ($lines | Where-Object { $_ -isnot [System.Management.Automation.ErrorRecord] }) -join "`n"
    $err = ($lines | Where-Object { $_ -is [System.Management.Automation.ErrorRecord] }) -join "`n"
    # Only the command words are echoed: later arguments can carry a client secret.
    if ($code -ne 0 -and -not $AllowFailure) { throw "az $($Arguments[0..1] -join ' ') failed (exit $code): $err" }
    return [pscustomobject]@{ Code = $code; Out = $out; Err = $err }
}

function Get-Output {
    param ($Outputs, [string]$Name)
    # Azure CLI re-cases output names, so match case-insensitively.
    $prop = $Outputs.PSObject.Properties | Where-Object { $_.Name -ieq $Name } | Select-Object -First 1
    if (-not $prop -or -not $prop.Value.value) { throw "Deployment output '$Name' is missing." }
    return [string]$prop.Value.value
}

# StrictMode throws on a missing property; control-plane JSON omits unset ones.
function Get-Prop {
    param ($Object, [string]$Name)
    if ($null -ne $Object -and $Object.PSObject.Properties[$Name]) { return $Object.$Name }
    return $null
}

# The one auth config this deployer writes (PUT whole) and accepts. Nonce
# validation is explicit because the service allows turning it off.
function Get-IntendedAuthConfig([string]$ClientId) {
    $login = [ordered]@{ preserveUrlFragmentsForLogins = $false; nonce = [ordered]@{ validateNonce = $true } }
    if ($script:authContainerUri) {
        $login.tokenStore = [ordered]@{
            enabled = $true
            azureBlobStorage = [ordered]@{
                blobContainerUri = $script:authContainerUri
                managedIdentityResourceId = $script:appIdentityResourceId
            }
        }
    }
    return [ordered]@{
        platform = [ordered]@{ enabled = $true }
        globalValidation = [ordered]@{ unauthenticatedClientAction = "RedirectToLoginPage"; redirectToProvider = "azureactivedirectory"; excludedPaths = @("/api/health", "/api/ready") }
        identityProviders = [ordered]@{ azureActiveDirectory = [ordered]@{
            enabled = $true
            registration = [ordered]@{ clientId = $ClientId; clientSecretSettingName = "microsoft-provider-authentication-secret"; openIdIssuer = "https://login.microsoftonline.com/$ExpectedTenantId/v2.0" }
            validation = [ordered]@{ defaultAuthorizationPolicy = [ordered]@{ allowedApplications = @() } }
        } }
        login = $login
        httpSettings = [ordered]@{ requireHttps = $true }
    }
}

# Canonical form for comparison: keys sorted; nulls, empty objects, and empty
# arrays dropped (the service adds and omits those freely). Booleans are kept.
function ConvertTo-Canonical($Value) {
    if ($null -eq $Value) { return $null }
    if ($Value -is [System.Collections.IDictionary] -or $Value -is [System.Management.Automation.PSCustomObject]) {
        $names = @(if ($Value -is [System.Collections.IDictionary]) { $Value.Keys } else { $Value.PSObject.Properties | ForEach-Object { $_.Name } })
        $out = [ordered]@{}
        foreach ($name in ($names | Sort-Object -CaseSensitive)) {
            # Read into a variable first: $(...) as an argument would turn a
            # one-element array into a scalar.
            $raw = $null
            if ($Value -is [System.Collections.IDictionary]) { $raw = $Value[$name] } else { $raw = $Value.$name }
            $item = ConvertTo-Canonical -Value $raw
            if ($null -ne $item) { $out[$name] = $item }
        }
        if ($out.Count) { return $out } else { return $null }
    }
    if ($Value -is [string]) { return $Value }
    if ($Value -is [System.Collections.IEnumerable]) {
        $items = @(foreach ($entry in $Value) { $c = ConvertTo-Canonical $entry; if ($null -ne $c) { ,$c } })
        if ($items.Count) { return ,$items } else { return $null }
    }
    return $Value
}

# First path at which two canonical documents differ, or "".
function Get-FirstDifference($Want, $Got, [string]$Path = "") {
    if ($Want -is [System.Collections.IDictionary] -and $Got -is [System.Collections.IDictionary]) {
        foreach ($key in (@($Want.Keys) + @($Got.Keys) | Sort-Object -Unique -CaseSensitive)) {
            if (-not $Want.Contains($key)) { return "$Path$key (unexpected)" }
            if (-not $Got.Contains($key)) { return "$Path$key (missing)" }
            $difference = Get-FirstDifference $Want[$key] $Got[$key] "$Path$key."
            if ($difference) { return $difference }
        }
        return ""
    }
    if ((ConvertTo-Json -InputObject $Want -Compress -Depth 20) -ceq (ConvertTo-Json -InputObject $Got -Compress -Depth 20)) { return "" }
    return $(if ($Path) { $Path.TrimEnd(".") } else { "(root)" })
}

# The exact access policy, read from the control plane. The auth config must be
# exactly Get-IntendedAuthConfig for this client (only the service-set
# isAutoProvisioned flag is ignored): anything else, including a setting this
# script never names, is a deviation. Ingress must be HTTPS-only with no CORS
# policy and no additional ports (an extra port is served around the sign-in
# sidecar), on the default HTTP transport.
function Get-AccessPolicyProblem {
    param ($Auth, $Ingress, [string]$ClientId = "")
    if (-not $Auth) { return "no sign-in configuration" }
    $actual = ConvertTo-Canonical $Auth
    $aad = $null  # assigned directly: an if-expression would enumerate the dictionary
    if ($actual -and $actual.Contains("identityProviders") -and $actual["identityProviders"].Contains("azureActiveDirectory")) { $aad = $actual["identityProviders"]["azureActiveDirectory"] }
    if ($aad) { $aad.Remove("isAutoProvisioned") }
    if (-not $ClientId -and $aad -and $aad.Contains("registration") -and $aad["registration"].Contains("clientId")) { $ClientId = $aad["registration"]["clientId"] }
    if (-not $ClientId) { return "sign-in names no client" }
    $difference = Get-FirstDifference (ConvertTo-Canonical (Get-IntendedAuthConfig $ClientId)) $actual
    if ($difference) { return "sign-in configuration differs from the intended policy at $difference" }
    if ($Ingress) {
        if ((Get-Prop $Ingress "allowInsecure") -ne $false) { return "ingress allows plain HTTP" }
        if (Get-Prop $Ingress "corsPolicy") { return "ingress has a CORS policy" }
        if (@(Get-Prop $Ingress "additionalPortMappings" | Where-Object { $_ }).Count) { return "ingress has additional ports" }
        if ("$(Get-Prop $Ingress 'transport')" -ne "Auto") { return "ingress transport is $(Get-Prop $Ingress 'transport'), not Auto" }
    }
    return ""
}

function Deploy-Template {
    param ([string]$Image, [bool]$UseRegistry, [string]$Revision, [string]$PrincipalId, [string]$AuthSecret = "")
    $paramsFile = New-TemporaryFile
    try {
        & chmod 600 $paramsFile  # may hold the sign-in client secret
        $parameters = @{
            prefix = @{ value = $Prefix }
            location = @{ value = $Location }
            principalId = @{ value = $PrincipalId }
            containerImage = @{ value = $Image }
            useRegistryImage = @{ value = $UseRegistry }
            revision = @{ value = $Revision }
            tags = @{ value = $Tags }
            chatModel = @{ value = $chat.Name }
            chatModelVersion = @{ value = $chat.Version }
            chatCapacity = @{ value = $chat.Capacity }
            fabricSqlHost = @{ value = $FabricSqlHost }
            fabricGoldDatabase = @{ value = $FabricGoldDatabase }
            fhirUrl = @{ value = $FhirUrl }
            eventhouseQueryUri = @{ value = $EventhouseQueryUri }
            eventhouseDatabase = @{ value = $EventhouseDatabase }
            authTenantId = @{ value = $ExpectedTenantId }
            authClientId = @{ value = "" }
            operatorObjectIds = @{ value = @() }
            reviewerObjectIds = @{ value = @() }
        }
        if ($UseRegistry) {
            $parameters.authClientId.value = $script:appId
            $parameters.operatorObjectIds.value = @($script:allowed)
            $parameters.reviewerObjectIds.value = @($script:reviewers)
        }
        # A container app deployment replaces its whole secret set; pass the
        # sign-in secret back so an authenticated app keeps working.
        if ($AuthSecret) { $parameters.authClientSecret = @{ value = $AuthSecret } }
        @{
            '$schema' = "https://schema.management.azure.com/schemas/2019-04-01/deploymentParameters.json#"
            contentVersion = "1.0.0.0"
            parameters = $parameters
        } | ConvertTo-Json -Depth 10 | Set-Content -Path $paramsFile -Encoding utf8
        $name = "cardiology-app-$(Get-Date -Format 'yyyyMMddHHmmss')"
        $result = Invoke-Az @("deployment", "group", "create", "-g", $ResourceGroupName, "-n", $name,
            "--template-file", $Template, "--parameters", "@$paramsFile", "--query", "properties.outputs", "-o", "json")
        return $result.Out | ConvertFrom-Json
    } finally {
        Remove-Item $paramsFile -ErrorAction SilentlyContinue
    }
}

Write-Host "Phase 8: Cardiology App" -ForegroundColor Cyan

# ── Context ──────────────────────────────────────────────────────────────────
$account = (Invoke-Az @("account", "show", "-o", "json")).Out | ConvertFrom-Json
if ($account.tenantId -ne $ExpectedTenantId -or $account.id -ne $ExpectedSubscriptionId) {
    throw "Azure CLI is on tenant $($account.tenantId) / subscription $($account.id); expected $ExpectedTenantId / $ExpectedSubscriptionId."
}
Write-Host "  ✓ Azure CLI: $($account.user.name) on $($account.name)" -ForegroundColor Green
$deployerId = (Invoke-Az @("ad", "signed-in-user", "show", "--query", "id", "-o", "tsv")).Out.Trim()
if (-not $deployerId) { throw "Could not resolve the signed-in user's object id." }

if ((Invoke-Az @("group", "exists", "-n", $ResourceGroupName)).Out.Trim() -ne "true") {
    $tagArgs = @($Tags.GetEnumerator() | ForEach-Object { "$($_.Key)=$($_.Value)" })
    $createArgs = @("group", "create", "-n", $ResourceGroupName, "-l", $Location, "-o", "none")
    if ($tagArgs.Count) { $createArgs += @("--tags") + $tagArgs }
    Invoke-Az $createArgs | Out-Null
    Write-Host "  ✓ Created resource group $ResourceGroupName" -ForegroundColor Green
}

# ── Existing app ─────────────────────────────────────────────────────────────
$appName = "$Prefix-app"
$acrQuery = '[?tags."hls-workload"==''cardiology-app''].name | [0]'

function Get-AppIngress {
    return (Invoke-Az @("containerapp", "show", "-g", $ResourceGroupName, "-n", $appName, "--query", "properties.configuration.ingress", "-o", "json")).Out | ConvertFrom-Json
}
function Stop-AppRevisions {
    $activeRevisions = (Invoke-Az @("containerapp", "revision", "list", "-g", $ResourceGroupName, "-n", $appName,
        "--query", "[?properties.active].name", "-o", "tsv")).Out -split "`n" | Where-Object { $_ }
    foreach ($revisionName in $activeRevisions) {
        Invoke-Az @("containerapp", "revision", "deactivate", "-g", $ResourceGroupName, "-n", $appName, "--revision", $revisionName, "-o", "none") | Out-Null
    }
}

# Discovery is a list query, so an empty result positively means the app does
# not exist yet (objects, not bare images, so an app with no image still counts).
# If discovery itself fails, the app may exist in any state: take its revisions
# offline (best effort) and stop, rather than continue as if it were fresh.
try {
    $existing = @((Invoke-Az @("containerapp", "list", "-g", $ResourceGroupName,
        "--query", "[?name=='$appName'].{image: properties.template.containers[0].image}", "-o", "json")).Out | ConvertFrom-Json | ForEach-Object { $_ })
} catch {
    Write-Host "  ! Could not determine whether $appName exists; taking any of its revisions offline before stopping" -ForegroundColor Yellow
    try { Stop-AppRevisions } catch { Write-Host "    (no revisions could be deactivated: $($_.Exception.Message))" -ForegroundColor Yellow }
    throw
}
$appExists = $existing.Count -gt 0
# The image only decides the build path; quarantine below covers any existing app.
$hasRegistryImage = $appExists -and "$(Get-Prop $existing[0] 'image')" -match "\.azurecr\.io/${ImageRepo}:"

# ── Identity facts the access checks compare against ────────────────────────
# The external FQDN is <app>.<environment domain>, known before ingress turns
# external, so the callback can be registered first. Assignees are exactly the
# deploying user plus -CardiologyAppUsers; an unknown user is an error, never
# silently dropped from the allowlist.
function Resolve-IdentityFacts {
    $domain = (Invoke-Az @("containerapp", "env", "show", "-g", $ResourceGroupName, "-n", "$Prefix-cae",
        "--query", "properties.defaultDomain", "-o", "tsv")).Out.Trim()
    if (-not $domain) { throw "The Container Apps environment $Prefix-cae has no default domain." }
    $script:envDomain = $domain
    $script:fqdn = "$appName.$domain"
    $script:appUrl = "https://$($script:fqdn)"
    $script:redirect = "$($script:appUrl)/.auth/login/aad/callback"
    $users = @($deployerId)
    foreach ($upn in $CardiologyAppUsers | Where-Object { $_ }) {
        $id = (Invoke-Az @("ad", "user", "show", "--id", $upn, "--query", "id", "-o", "tsv")).Out.Trim()
        if (-not $id) { throw "Requested sign-in user $upn was not found." }
        $users += $id
    }
    $script:allowed = @($users | Select-Object -Unique)
    $reviewers = @($deployerId)
    foreach ($upn in $CardiologyReviewerUsers | Where-Object { $_ }) {
        $id = (Invoke-Az @("ad", "user", "show", "--id", $upn, "--query", "id", "-o", "tsv")).Out.Trim()
        if (-not $id -or $script:allowed -notcontains $id) { throw "Reviewer $upn must be an assigned CardiologyAppUsers account." }
        $reviewers += $id
    }
    $script:reviewers = @($reviewers | Select-Object -Unique)
}
$displayName = "cardiology-app-$ResourceGroupName"
$ownerTag = "hls-cardiology-app:$($account.id)/$($ResourceGroupName.ToLowerInvariant())/$appName"

# A list query, so an empty result positively means "no service principal" and
# a failed lookup throws (fail closed) rather than reading as absent.
function Get-ServicePrincipalId([string]$ClientId) {
    $ids = @((Invoke-Az @("ad", "sp", "list", "--filter", "appId eq '$ClientId'", "--query", "[].id", "-o", "json")).Out | ConvertFrom-Json | ForEach-Object { $_ })
    if ($ids.Count -gt 1) { throw "More than one service principal exists for $ClientId." }
    if ($ids.Count) { return [string]$ids[0] }
    return ""
}
# Owners of the application and of its service principal (an enterprise-app
# owner can grant itself access), other than the deploying user.
function Get-ForeignOwners([string]$AppObjectId, [string]$ServicePrincipalId) {
    $owners = @((Invoke-Az @("ad", "app", "owner", "list", "--id", $AppObjectId, "--query", "[].id", "-o", "json")).Out | ConvertFrom-Json | ForEach-Object { $_ })
    if ($ServicePrincipalId) {
        $owners += @((Invoke-Az @("ad", "sp", "owner", "list", "--id", $ServicePrincipalId, "--query", "[].id", "-o", "json")).Out | ConvertFrom-Json | ForEach-Object { $_ })
    }
    return @($owners | Where-Object { $_ -and $_ -ne $deployerId } | Sort-Object -Unique)
}
# Graph pages this collection; follow @odata.nextLink so no grant is missed.
function Get-AppAssignments([string]$ServicePrincipalId) {
    $all = @(); $url = "https://graph.microsoft.com/v1.0/servicePrincipals/$ServicePrincipalId/appRoleAssignedTo"
    while ($url) {
        $page = (Invoke-Az @("rest", "--method", "GET", "--url", $url, "-o", "json")).Out | ConvertFrom-Json
        $all += @($page.value)
        $url = if ($page.PSObject.Properties["@odata.nextLink"]) { $page."@odata.nextLink" } else { $null }
    }
    return ,$all
}
# Registration-level access state for a client: its sole redirect is this app's
# exact web callback; no SPA or public-client redirects (they also receive
# codes) or public-client flows; single-tenant; no implicit access tokens; the
# owner tag; no other owner on the application or its service principal;
# assignment required; and the assignees. -AssigneesAtMost accepts a missing
# assignee (quarantine: that is not weaker); otherwise they must match exactly.
function Get-RegistrationProblem([string]$ClientId, [switch]$AssigneesAtMost) {
    $app = (Invoke-Az @("ad", "app", "show", "--id", $ClientId, "-o", "json")).Out | ConvertFrom-Json
    $web = Get-Prop $app "web"
    $registered = @(Get-Prop $web "redirectUris" | Where-Object { $_ })
    if ($registered.Count -ne 1 -or $registered -cnotcontains $redirect) { return "registration $ClientId redirect URIs are not exactly the callback $redirect" }
    if (@(Get-Prop (Get-Prop $app "spa") "redirectUris" | Where-Object { $_ }).Count -or @(Get-Prop (Get-Prop $app "publicClient") "redirectUris" | Where-Object { $_ }).Count) { return "registration $ClientId has SPA or public-client redirect URIs" }
    if ((Get-Prop $app "isFallbackPublicClient") -eq $true) { return "registration $ClientId allows public-client flows" }
    if ((Get-Prop $app "signInAudience") -ne "AzureADMyOrg") { return "registration $ClientId is not single-tenant" }
    if ((Get-Prop (Get-Prop $web "implicitGrantSettings") "enableAccessTokenIssuance") -eq $true) { return "registration $ClientId issues implicit access tokens" }
    if (@(Get-Prop $app "tags") -cnotcontains $ownerTag) { return "registration $ClientId lacks the owner tag $ownerTag" }
    $servicePrincipal = Get-ServicePrincipalId $ClientId
    if (-not $servicePrincipal) { return "registration $ClientId has no service principal" }
    $others = @(Get-ForeignOwners $app.id $servicePrincipal)
    if ($others.Count) { return "registration $ClientId or its service principal has other owners ($($others -join ', '))" }
    $required = (Invoke-Az @("ad", "sp", "show", "--id", $servicePrincipal, "--query", "appRoleAssignmentRequired", "-o", "tsv")).Out.Trim()
    if ($required -ne "true") { return "app assignment is not required" }
    $assigned = @(Get-AppAssignments $servicePrincipal | ForEach-Object { $_ } | ForEach-Object { $_.principalId } | Sort-Object -Unique)
    $extra = @($assigned | Where-Object { $allowed -notcontains $_ })
    if ($extra.Count) { return "unrequested accounts are assigned ($($extra -join ', '))" }
    if (-not $AssigneesAtMost -and @($allowed | Where-Object { $assigned -notcontains $_ }).Count) { return "requested accounts are not all assigned" }
    return ""
}

# An existing cardiology app must never be served under a weaker policy. This
# runs before any other work (source, model, infrastructure), so nothing that
# fails earlier can leave a weakened app online. If the app exists (whatever
# image it runs) and its access state is not the intended one (the auth config
# and ingress, Get-AccessPolicyProblem; the registration, its service principal,
# and assignees, Get-RegistrationProblem), or cannot be read, take it offline:
# an earlier run may have failed part-way, or someone may have loosened it. The
# registration itself is not edited here.
if ($appExists) {
    try {
        Resolve-IdentityFacts  # inside the boundary: a failed lookup quarantines too
        # Recover intended token-store coordinates from this deployment's own
        # outputs before comparing policy; an enabled store is not a weakness.
        $priorState = Invoke-Az @("deployment", "group", "show", "-g", $ResourceGroupName,
            "-n", "$Prefix-state-bootstrap", "--query", "properties.outputs", "-o", "json") -AllowFailure
        if ($priorState.Code -eq 0 -and $priorState.Out) {
            $script:authContainerUri = Get-Output ($priorState.Out | ConvertFrom-Json) "authContainerUri"
            $script:appIdentityResourceId = (Invoke-Az @("identity", "show", "-g", $ResourceGroupName,
                "-n", "$Prefix-app-id", "--query", "id", "-o", "tsv")).Out.Trim()
        }
        $currentAuth = Get-AuthConfig
        $weakness = Get-AccessPolicyProblem $currentAuth (Get-AppIngress)
        if (-not $weakness) {
            $weakness = Get-RegistrationProblem ([string]$currentAuth.identityProviders.azureActiveDirectory.registration.clientId) -AssigneesAtMost
        }
    } catch { $weakness = "access state unreadable: $($_.Exception.Message)" }
    if ($weakness) {
        Stop-AppRevisions
        Write-Host "  ! $appName was not enforcing the intended sign-in policy ($weakness); its revisions are offline until it is" -ForegroundColor Yellow
    }
}
# ── Source checkout ──────────────────────────────────────────────────────────
if (-not $CardiologyAppPath) { $CardiologyAppPath = Join-Path (Split-Path -Parent $RepoRoot) "caldova-cardio-e2e" }
if (-not (Test-Path (Join-Path $CardiologyAppPath ".git"))) {
    Write-Host "  Cloning $AppRepo to $CardiologyAppPath" -ForegroundColor Gray
    $cloned = $false
    if (Get-Command gh -ErrorAction SilentlyContinue) {
        & gh repo clone $AppRepo $CardiologyAppPath -- --branch $AppBranch
        $cloned = $LASTEXITCODE -eq 0
    }
    if (-not $cloned) {
        & git clone --branch $AppBranch "https://github.com/$AppRepo.git" $CardiologyAppPath
        if ($LASTEXITCODE -ne 0) { throw "Could not clone $AppRepo. Sign in with 'gh auth login' as an account with access." }
    }
}
if (-not (Test-Path (Join-Path $CardiologyAppPath "Dockerfile"))) {
    throw "$CardiologyAppPath has no root Dockerfile; check out $AppBranch of $AppRepo."
}
$sha = (& git -C $CardiologyAppPath rev-parse --short=12 HEAD).Trim()
if ($LASTEXITCODE -ne 0 -or -not $sha) { throw "Could not read the checkout's commit." }
$dirty = & git -C $CardiologyAppPath status --porcelain
$tag = if ($dirty) { "$sha-dirty-$(Get-Date -Format 'yyyyMMddHHmmss')" } else { $sha }
Write-Host "  ✓ Source $CardiologyAppPath @ $tag" -ForegroundColor Green

# ── Chat model ───────────────────────────────────────────────────────────────
# DataZoneStandard keeps inference in the US data zone. Its quota is counted
# across the whole zone (every US region reports the same usage), so another
# region adds no capacity. An environment keeps the model it already runs; a new
# one gets the first candidate the zone can still hold, sized to fit.
$modelCandidates = @(
    @{ Name = "gpt-5.6-luna"; Version = "2026-07-09" },
    @{ Name = "gpt-5.5"; Version = "2026-04-24" }
)
$wantedCapacity = 100; $minimumCapacity = 50
$chat = $null
$aiName = (Invoke-Az @("cognitiveservices", "account", "list", "-g", $ResourceGroupName, "--query", $acrQuery, "-o", "tsv")).Out.Trim()
if ($aiName) {
    $existingModels = @((Invoke-Az @("cognitiveservices", "account", "deployment", "list", "-g", $ResourceGroupName, "-n", $aiName, "-o", "json")).Out | ConvertFrom-Json | ForEach-Object { $_ })
    foreach ($candidate in $modelCandidates) {
        $found = @($existingModels | Where-Object { $_.name -eq $candidate.Name -and $_.sku.name -eq "DataZoneStandard" }) | Select-Object -First 1
        if ($found) {
            $chat = @{ Name = $found.name; Version = $found.properties.model.version; Capacity = [int]$found.sku.capacity }
            Write-Host "  = Keeping this environment's model $($chat.Name)" -ForegroundColor Gray
            break
        }
    }
}
if (-not $chat) {
    $usage = @((Invoke-Az @("cognitiveservices", "usage", "list", "-l", $Location, "-o", "json")).Out | ConvertFrom-Json | ForEach-Object { $_ })
    $offered = @((Invoke-Az @("cognitiveservices", "model", "list", "-l", $Location, "-o", "json")).Out | ConvertFrom-Json | ForEach-Object { $_ })
    foreach ($candidate in $modelCandidates) {
        $isOffered = @($offered | Where-Object { (Get-Prop $_.model "name") -eq $candidate.Name -and (Get-Prop $_.model "version") -eq $candidate.Version -and
            @(Get-Prop $_.model "skus" | ForEach-Object { Get-Prop $_ "name" }) -contains "DataZoneStandard" }).Count -gt 0
        $quota = @($usage | Where-Object { $_.name.value -eq "OpenAI.DataZoneStandard.$($candidate.Name)" }) | Select-Object -First 1
        if (-not $isOffered -or -not $quota) { Write-Host "  = $($candidate.Name) DataZoneStandard is not offered in $Location" -ForegroundColor Gray; continue }
        $free = [int][Math]::Floor([double]$quota.limit - [double]$quota.currentValue)
        if ([Math]::Min($wantedCapacity, $free) -ge $minimumCapacity) {
            $chat = @{ Name = $candidate.Name; Version = $candidate.Version; Capacity = [Math]::Min($wantedCapacity, $free) }
            break
        }
        Write-Host "  = $($candidate.Name): only $free of its US data-zone quota is free" -ForegroundColor Gray
    }
    if (-not $chat) { throw "No chat model fits the free US data-zone quota (need $minimumCapacity); free capacity or request more quota." }
}
Write-Host "  ✓ Model $($chat.Name) $($chat.Version), DataZoneStandard capacity $($chat.Capacity)" -ForegroundColor Green
if ($hasRegistryImage) {
    Write-Host "  = $appName already runs a registry image; building the new revision directly" -ForegroundColor Gray
} else {
    Write-Host "  Deploying infrastructure (placeholder image)..." -ForegroundColor Gray
    Deploy-Template -Image "mcr.microsoft.com/k8se/quickstart:latest" -UseRegistry $false -Revision "placeholder" -PrincipalId $deployerId | Out-Null
}
$acrName = (Invoke-Az @("acr", "list", "-g", $ResourceGroupName, "--query", $acrQuery, "-o", "tsv")).Out.Trim()
if (-not $acrName) { throw "The cardiology app registry was not found in $ResourceGroupName." }
Write-Host "  ✓ Infrastructure ready (registry $acrName)" -ForegroundColor Green

# ── HDS access for the app identity ─────────────────────────────────────────
# The live profile reads gold over the Fabric SQL endpoint and writes FHIR
# first, with no fallback. The identity exists now (a fresh app's placeholder
# deployment just created it), and no revision carrying the HDS settings has
# been built yet: both grants are made and confirmed on their control planes
# here, before the revision deploy below. A grant is created only when absent;
# an existing Fabric role of this identity (it is this app's alone) is set to
# Viewer. No other principal's access is touched.
$appIdentity = (Invoke-Az @("identity", "show", "-g", $ResourceGroupName, "-n", "$Prefix-app-id",
    "--query", "{id:id,clientId:clientId,principalId:principalId}", "-o", "json")).Out | ConvertFrom-Json
$appPrincipal = [string](Get-Prop $appIdentity "principalId")
if (-not $appPrincipal -or -not (Get-Prop $appIdentity "clientId")) { throw "The app identity $Prefix-app-id has no principal or client id." }
$script:appIdentityResourceId = [string]$appIdentity.id

# Provision durable operations and Easy Auth token containers before publishing.
# Both use container-scoped managed-identity grants; no storage keys or SAS URLs.
$stateParameters = New-TemporaryFile
try {
    @{
        '$schema' = "https://schema.management.azure.com/schemas/2019-04-01/deploymentParameters.json#"
        contentVersion = "1.0.0.0"
        parameters = @{
            prefix = @{ value = $Prefix }; location = @{ value = $Location }
            tags = @{ value = $Tags }; appPrincipalId = @{ value = $appPrincipal }
        }
    } | ConvertTo-Json -Depth 10 | Set-Content $stateParameters -Encoding utf8
    $stateOutputs = (Invoke-Az @("deployment", "group", "create", "-g", $ResourceGroupName,
        "-n", "$Prefix-state-bootstrap", "--template-file", (Join-Path $RepoRoot "bicep/cardiology-state.bicep"),
        "--parameters", "@$stateParameters", "--query", "properties.outputs", "-o", "json")).Out | ConvertFrom-Json
    $script:authContainerUri = Get-Output $stateOutputs "authContainerUri"
    Write-Host "  ✓ Durable workflow and sign-in token containers provisioned with Entra-only access" -ForegroundColor Green
} finally { Remove-Item $stateParameters -ErrorAction SilentlyContinue }

# The FHIR URL the app is given must be the service it is granted.
$fhirAudience = (Invoke-Az @("resource", "show", "--ids", $FhirServiceId,
    "--query", "properties.authenticationConfiguration.audience", "-o", "tsv")).Out.Trim()
if ($fhirAudience.TrimEnd("/") -ne $FhirUrl) { throw "FHIR service $FhirServiceId serves '$fhirAudience', not $FhirUrl." }

# Exact-scope assignments only; the service returns the scope in its own casing.
function Test-FhirGrant {
    $scopes = @((Invoke-Az @("role", "assignment", "list", "--scope", $FhirServiceId, "--assignee-object-id", $appPrincipal,
        "--role", $FhirDataContributor, "--query", "[].scope", "-o", "json")).Out | ConvertFrom-Json | ForEach-Object { $_ })
    return @($scopes | Where-Object { $_ -eq $FhirServiceId }).Count -gt 0
}
if (Test-FhirGrant) {
    Write-Host "  = App identity already has FHIR Data Contributor on the FHIR service" -ForegroundColor Gray
} else {
    # A just-created identity can take a minute to reach Azure RBAC.
    for ($attempt = 1; $attempt -le 3; $attempt++) {
        try {
            Invoke-Az @("role", "assignment", "create", "--assignee-object-id", $appPrincipal, "--assignee-principal-type", "ServicePrincipal",
                "--role", $FhirDataContributor, "--scope", $FhirServiceId, "-o", "none") | Out-Null
            break
        } catch {
            if ($attempt -eq 3) { throw }
            Write-Host "  FHIR role assignment failed (attempt $attempt/3); waiting 30s for the identity to propagate..." -ForegroundColor Yellow
            Start-Sleep -Seconds 30
        }
    }
    $deadline = (Get-Date).AddMinutes(2)
    while (-not (Test-FhirGrant)) {
        if ((Get-Date) -ge $deadline) { throw "The FHIR Data Contributor assignment for $appPrincipal did not appear on $FhirServiceId within 2 minutes." }
        Start-Sleep -Seconds 10
    }
    Write-Host "  ✓ Granted the app identity FHIR Data Contributor on the FHIR service" -ForegroundColor Green
}

# Fabric returns {errorCode, message}; az embeds that body in its error text.
function Get-FabricError([string]$Text) {
    $body = [regex]::Match($Text, '\{.*\}', [System.Text.RegularExpressions.RegexOptions]::Singleline).Value
    try {
        $fabricError = $body | ConvertFrom-Json
        $code = Get-Prop $fabricError "errorCode"
        if ($code) { return "${code}: $(Get-Prop $fabricError 'message')" }
    } catch { }
    return $Text.Trim()
}
function Invoke-Fabric([string]$Method, [string]$Url, $Body = $null) {
    $arguments = @("rest", "--method", $Method, "--url", $Url, "--resource", $FabricApi,
        "--headers", "Content-Type=application/json", "x-ms-fabric-skill=e2e-medallion-architecture", "-o", "json")
    $bodyFile = $null
    try {
        if ($null -ne $Body) {
            $bodyFile = New-TemporaryFile
            $Body | ConvertTo-Json -Depth 5 | Set-Content $bodyFile -Encoding utf8
            $arguments += @("--body", "@$bodyFile")
        }
        $result = Invoke-Az $arguments -AllowFailure
        if ($result.Code -ne 0) { throw (Get-FabricError $result.Err) }
        if ($result.Out) { return $result.Out | ConvertFrom-Json }
    } finally { if ($bodyFile) { Remove-Item $bodyFile -ErrorAction SilentlyContinue } }
}
$fabricRolesUrl = "$FabricApi/v1/workspaces/$FabricWorkspaceId/roleAssignments"
# Fabric pages this collection; follow continuationUri so no assignment is missed.
function Get-FabricAppRoles {
    $all = @(); $url = $fabricRolesUrl
    while ($url) {
        try { $page = Invoke-Fabric "GET" $url } catch { throw "Could not read the role assignments of Fabric workspace ${FabricWorkspaceId}: $($_.Exception.Message)" }
        $all += @(Get-Prop $page "value" | Where-Object { $_ })
        $url = Get-Prop $page "continuationUri"
    }
    return ,@($all | Where-Object { (Get-Prop (Get-Prop $_ "principal") "id") -eq $appPrincipal })
}
$fabricRoles = Get-FabricAppRoles
if ($fabricRoles.Count -eq 1 -and (Get-Prop $fabricRoles[0] "role") -eq "Viewer") {
    Write-Host "  = App identity is already a Viewer of Fabric workspace $FabricWorkspaceId" -ForegroundColor Gray
} else {
    try {
        if ($fabricRoles.Count) {
            Invoke-Fabric "PATCH" "$fabricRolesUrl/$(Get-Prop $fabricRoles[0] 'id')" @{ role = "Viewer" } | Out-Null
        } else {
            Invoke-Fabric "POST" $fabricRolesUrl @{ principal = @{ id = $appPrincipal; type = "ServicePrincipal" }; role = "Viewer" } | Out-Null
        }
    } catch {
        # Verbatim: e.g. a tenant that does not allow service principals says so here.
        throw "Fabric refused to make the app identity ($appPrincipal) a Viewer of workspace ${FabricWorkspaceId}: $($_.Exception.Message)"
    }
    $deadline = (Get-Date).AddMinutes(2)
    while (-not (($fabricRoles = Get-FabricAppRoles).Count -eq 1 -and (Get-Prop $fabricRoles[0] "role") -eq "Viewer")) {
        if ((Get-Date) -ge $deadline) { throw "The app identity ($appPrincipal) was not a Viewer of Fabric workspace $FabricWorkspaceId within 2 minutes." }
        Start-Sleep -Seconds 10
    }
    Write-Host "  ✓ Made the app identity a Viewer of Fabric workspace $FabricWorkspaceId" -ForegroundColor Green
}


# For a fresh app the environment exists only now; for an existing one this
# re-raises any lookup failure the quarantine above already acted on.
Resolve-IdentityFacts

# Offline = no active revision (quarantined now, or left offline by an earlier
# failed run). Nothing answers at the edge, so sign-in is verified on the control
# plane only, and the latest revision is reactivated after publishing.
$activeNow = @((Invoke-Az @("containerapp", "revision", "list", "-g", $ResourceGroupName, "-n", $appName,
    "--query", "[?properties.active].name", "-o", "tsv")).Out -split "`n" | Where-Object { $_ })
$offline = $activeNow.Count -eq 0

# ── Entra sign-in, enforced BEFORE the app image is served ───────────────────
# Until sign-in is verified the app serves only what it served before: nothing
# public on a fresh deployment (the placeholder has internal ingress), the
# previous signed-in revision on a rerun, or nothing if it was quarantined above.
# The cardiology app itself is never reachable anonymously, including when any
# step below fails.
$isExternal = (Get-Prop (Get-AppIngress) "external") -eq $true

# The registration is bound to this app by its sign-in callback (the Container
# Apps FQDN is unique) and marked with the owner tag. Lookup is by exact name.
# It is reused only when its sole redirect URI is this app's exact web callback
# (case-sensitive), or rebound when it carries the owner tag and its sole web
# redirect is an earlier FQDN of the same app (the environment was recreated).
# Either way it must have no SPA or public-client redirect, no public-client
# flows, and no owner other than the deploying user on the application or its
# service principal. Anything else is refused before any change, never edited.
$named = @((Invoke-Az @("ad", "app", "list", "--filter", "displayName eq '$displayName'",
    "--query", "[].{appId:appId,id:id,uris:web.redirectUris,spa:spa.redirectUris,public:publicClient.redirectUris,fallback:isFallbackPublicClient,tags:tags}", "-o", "json")).Out |
    ConvertFrom-Json | ForEach-Object { $_ } | Where-Object { $_ })
$bound = @($named | Where-Object { @($_.uris) -ccontains $redirect })
$earlierCallback = "^https://$([regex]::Escape($appName))\.[a-z0-9-]+\.[a-z0-9-]+\.azurecontainerapps\.io/\.auth/login/aad/callback$"
$owned = @($named | Where-Object { @($_.tags) -ccontains $ownerTag })
function Assert-UsableRegistration($Candidate) {
    if (@($Candidate.spa | Where-Object { $_ }).Count -or @($Candidate.public | Where-Object { $_ }).Count) {
        throw "App registration $displayName also has SPA or public-client redirect URIs; refusing to use it."
    }
    if ($Candidate.fallback -eq $true) { throw "App registration $displayName allows public-client flows; refusing to use it." }
    $others = @(Get-ForeignOwners $Candidate.id (Get-ServicePrincipalId $Candidate.appId))
    if ($others.Count) { throw "App registration $displayName or its service principal has other owners ($($others -join ', ')) who can change it; refusing to use it." }
}
if ($bound.Count -gt 1) { throw "$($bound.Count) app registrations named $displayName are bound to $redirect; remove the extras." }
if ($bound.Count -eq 1) {
    # Exclusive binding: a registration that also serves other callbacks is shared,
    # and its assignments are reconciled below, so it is refused, never edited.
    if (@($bound[0].uris).Count -ne 1) { throw "App registration $displayName also lists other redirect URIs; refusing to reuse a shared registration." }
    $registration = $bound[0]
    Assert-UsableRegistration $registration
    Write-Host "  = Reusing app registration $displayName" -ForegroundColor Gray
} elseif ($owned.Count -eq 1 -and $named.Count -eq 1 -and @($owned[0].uris).Count -eq 1 -and @($owned[0].uris)[0] -cmatch $earlierCallback) {
    $registration = $owned[0]
    Assert-UsableRegistration $registration
    Invoke-Az @("ad", "app", "update", "--id", $registration.appId, "--web-redirect-uris", $redirect) | Out-Null
    Write-Host "  ✓ Rebound app registration $displayName from $(@($owned[0].uris)[0]) to this app's callback" -ForegroundColor Green
} elseif ($named.Count -gt 0) {
    throw "App registration $displayName exists but is not bound to $redirect; refusing to take it over."
} else {
    $registration = (Invoke-Az @("ad", "app", "create", "--display-name", $displayName, "--sign-in-audience", "AzureADMyOrg",
        "--web-redirect-uris", $redirect, "--enable-id-token-issuance", "true", "--query", "{appId:appId,id:id,tags:tags}", "-o", "json")).Out | ConvertFrom-Json
    Write-Host "  ✓ Created app registration $displayName" -ForegroundColor Green
}
$appId = $registration.appId
# Single-tenant, ID tokens only (no implicit access tokens), and the owner tag.
Invoke-Az @("ad", "app", "update", "--id", $appId, "--sign-in-audience", "AzureADMyOrg",
    "--enable-id-token-issuance", "true", "--enable-access-token-issuance", "false") | Out-Null
if (@($registration.tags) -cnotcontains $ownerTag) {
    $tagFile = New-TemporaryFile
    try {
        @{ tags = @(@($registration.tags | Where-Object { $_ }) + $ownerTag) } | ConvertTo-Json | Set-Content $tagFile -Encoding utf8
        Invoke-Az @("rest", "--method", "PATCH", "--url", "https://graph.microsoft.com/v1.0/applications/$($registration.id)",
            "--headers", "Content-Type=application/json", "--body", "@$tagFile", "-o", "none") | Out-Null
    } finally { Remove-Item $tagFile -ErrorAction SilentlyContinue }
}
$spId = Get-ServicePrincipalId $appId
if (-not $spId) { $spId = (Invoke-Az @("ad", "sp", "create", "--id", $appId, "--query", "id", "-o", "tsv")).Out.Trim() }
# Only assigned users may sign in.
Invoke-Az @("ad", "sp", "update", "--id", $spId, "--set", "appRoleAssignmentRequired=true") | Out-Null

# Reconcile to exactly the requested accounts: a user dropped from
# -CardiologyAppUsers loses access on the next deploy.
$assignmentsUrl = "https://graph.microsoft.com/v1.0/servicePrincipals/$spId/appRoleAssignedTo"
$existingAssignments = Get-AppAssignments $spId
foreach ($assignment in $existingAssignments | Where-Object { $allowed -notcontains $_.principalId }) {
    Invoke-Az @("rest", "--method", "DELETE", "--url", "$assignmentsUrl/$($assignment.id)", "-o", "none") | Out-Null
}
$currentPrincipals = @($existingAssignments | ForEach-Object { $_.principalId })
foreach ($principal in $allowed | Where-Object { $currentPrincipals -notcontains $_ }) {
    $bodyFile = New-TemporaryFile
    try {
        @{ principalId = $principal; resourceId = $spId; appRoleId = $DefaultAccessRole } | ConvertTo-Json | Set-Content $bodyFile -Encoding utf8
        Invoke-Az @("rest", "--method", "POST", "--url", $assignmentsUrl,
            "--headers", "Content-Type=application/json", "--body", "@$bodyFile", "-o", "none") | Out-Null
    } finally { Remove-Item $bodyFile -ErrorAction SilentlyContinue }
}
$verified = @(Get-AppAssignments $spId | ForEach-Object { $_ } | ForEach-Object { $_.principalId } | Sort-Object -Unique)
if (($verified -join ",") -ne (@($allowed | Sort-Object) -join ",")) { throw "App assignments do not match the requested sign-in accounts." }
Write-Host "  ✓ Sign-in limited to $($verified.Count) assigned account(s)" -ForegroundColor Green

# The client secret Container Apps uses to redeem sign-in codes. A secret is
# proven live by a client-credentials token request as this app. Entra
# replicates credential changes gradually and, for minutes after one, refuses a
# valid secret intermittently (AADSTS7000215), so one token proves a secret and
# refusal counts only when it persists until -Until. Each attempt is one
# HttpClient POST cancelled at min(10 s, time left); PostAsync buffers the whole
# body before completing, so the deadline covers connection, headers, and body.
# The installed secret is reused while it authenticates; otherwise a credential
# is ADDED. Credentials are never deleted here, so a failed or overlapping run
# cannot revoke the secret the app is using. Never printed; cleared at script end.
$tokenClient = [System.Net.Http.HttpClient]::new()
$tokenClient.Timeout = [System.Threading.Timeout]::InfiniteTimeSpan  # each attempt carries its own deadline
# Everything that holds the secret or the HTTP clients runs inside this try, so
# every exit (including a rejected credential or a failed auth update) cleans up.
$browser = $null
try {
    function Test-ClientSecret([string]$Value, [datetime]$Until = (Get-Date).AddSeconds(30)) {
        if (-not $Value) { return $false }
        $form = "client_id=$appId&scope=$([uri]::EscapeDataString('https://graph.microsoft.com/.default'))&grant_type=client_credentials&client_secret=$([uri]::EscapeDataString($Value))"
        while (($left = ($Until - (Get-Date)).TotalMilliseconds) -gt 0) {
            $cancel = [System.Threading.CancellationTokenSource]::new([TimeSpan]::FromMilliseconds([Math]::Min(10000, $left)))
            $response = $null; $content = $null
            try {
                $content = [System.Net.Http.StringContent]::new($form, [System.Text.Encoding]::UTF8, "application/x-www-form-urlencoded")
                $response = $tokenClient.PostAsync("https://login.microsoftonline.com/$ExpectedTenantId/oauth2/v2.0/token", $content, $cancel.Token).GetAwaiter().GetResult()
                if ($response.IsSuccessStatusCode -and ($response.Content.ReadAsStringAsync().GetAwaiter().GetResult() | ConvertFrom-Json).access_token) { return $true }
            } catch { } finally { if ($response) { $response.Dispose() }; if ($content) { $content.Dispose() }; $cancel.Dispose() }
            $left = ($Until - (Get-Date)).TotalMilliseconds
            if ($left -gt 0) { Start-Sleep -Milliseconds ([int][Math]::Min(5000, $left)) }
        }
        return $false
    }
    function Get-InstalledSecret {
        $auth = Invoke-Az @("rest", "--method", "GET", "--url", (Get-AuthConfigUrl), "--query", "properties", "-o", "json") -AllowFailure
        try { $settingName = ($auth.Out | ConvertFrom-Json).identityProviders.azureActiveDirectory.registration.clientSecretSettingName } catch { $settingName = "" }
        if ($auth.Code -ne 0 -or -not $settingName) { return "" }
        $installed = Invoke-Az @("containerapp", "secret", "show", "-g", $ResourceGroupName, "-n", $appName,
            "--secret-name", $settingName, "--query", "value", "-o", "tsv") -AllowFailure
        if ($installed.Code -eq 0) { return $installed.Out.Trim() } else { return "" }
    }
    $secret = Get-InstalledSecret
    if (Test-ClientSecret $secret) {
        Write-Host "  = Reusing the installed sign-in secret; it authenticates as the app" -ForegroundColor DarkGray
    } else {
        $credentialName = "container-apps-auth-$(Get-Date -Format 'yyyyMMddHHmmss')"
        $secret = (Invoke-Az @("ad", "app", "credential", "reset", "--id", $appId, "--append", "--display-name", $credentialName,
            "--years", "1", "--query", "password", "-o", "tsv")).Out.Trim()
        if (-not (Test-ClientSecret $secret -Until (Get-Date).AddMinutes(3))) {
            throw "The new sign-in credential $credentialName was not accepted within 3 minutes."
        }
        Write-Host "  ✓ Added sign-in credential $credentialName" -ForegroundColor Green
    }
    # az reads the secret from a chmod-600 file (@file expansion), so it never
    # appears in a process argument list (the "=" form also keeps a leading "-"
    # from being read as a flag).
    $secretFile = New-TemporaryFile
    try {
        & chmod 600 $secretFile
        [System.IO.File]::WriteAllText($secretFile.FullName, $secret)
        Invoke-Az @("containerapp", "auth", "microsoft", "update", "-g", $ResourceGroupName, "-n", $appName,
            "--client-id", $appId, "--client-secret=@$($secretFile.FullName)",
            # The v2 issuer names the tenant; the CLI rejects --tenant-id alongside it.
            "--issuer", "https://login.microsoftonline.com/$ExpectedTenantId/v2.0", "--yes", "-o", "none") | Out-Null
    } finally { Remove-Item $secretFile -ErrorAction SilentlyContinue }
    # Then replace the whole auth config with exactly the intended policy, so a
    # loosened setting (another provider, an extra audience, an open redirect,
    # plain HTTP) is removed rather than left beside the fields the CLI updates.
    $authBody = @{ properties = (Get-IntendedAuthConfig $appId) }
    $authFile = New-TemporaryFile
    try {
        $authBody | ConvertTo-Json -Depth 20 | Set-Content $authFile -Encoding utf8
        Invoke-Az @("rest", "--method", "PUT", "--headers", "Content-Type=application/json", "--body", "@$($authFile.FullName)", "-o", "none",
            "--url", (Get-AuthConfigUrl)) | Out-Null
    } finally { Remove-Item $authFile -ErrorAction SilentlyContinue }

    # Easy Auth redirects only browser requests (others get 401), so probe as one,
    # without following the redirect, and require it to land on this tenant's sign-in.
    $handler = [System.Net.Http.HttpClientHandler]::new()
    $handler.AllowAutoRedirect = $false
    $browser = [System.Net.Http.HttpClient]::new($handler)
    $browser.Timeout = [TimeSpan]::FromSeconds(15)
    $browser.DefaultRequestHeaders.UserAgent.ParseAdd("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0 Safari/537.36")
    $browser.DefaultRequestHeaders.Accept.ParseAdd("text/html,application/xhtml+xml")
    $signIn = "https://login.microsoftonline.com/$ExpectedTenantId/"
    function Test-SignInEnforced {
        try {
            $response = $browser.GetAsync("$appUrl/").GetAwaiter().GetResult()
            try {
                $location = if ($response.Headers.Location) { $response.Headers.Location.AbsoluteUri } else { "" }
                # The redirect must name exactly this registration and this app's callback.
                # Assigned directly: an `if` expression would unroll the collection into strings.
                $query = $null
                if ($location) { $query = [System.Web.HttpUtility]::ParseQueryString(([uri]$location).Query) }
                if ([int]$response.StatusCode -eq 302 -and $location.StartsWith($signIn) -and
                    ((@($query.GetValues("client_id")) -join ",") -ceq $appId) -and ((@($query.GetValues("redirect_uri")) -join ",") -ceq $redirect)) { return "" }
                return "unauthenticated browser request to / returned $([int]$response.StatusCode) (Location '$location')"
            } finally { $response.Dispose() }
        } catch { return "sign-in probe: $($_.Exception.Message)" }
    }

    # Control plane: the exact access policy for this registration
    # (Get-AccessPolicyProblem), the registration, its service principal, and
    # exactly the requested assignees (Get-RegistrationProblem), and an installed
    # client secret that authenticates as the app (without it the redirect works
    # but every sign-in callback fails).
    # Before publishing, ingress is not yet ours: the publishing template deploy
    # replaces it (a weak ingress already quarantined the app above), so the
    # pre-publish gate checks everything except ingress (-BeforePublish).
    function Test-AuthConfig([switch]$BeforePublish) {
        $cfg = Get-AuthConfig
        $ingress = $null
        if (-not $BeforePublish) { $ingress = Get-AppIngress }
        $weakness = Get-AccessPolicyProblem $cfg $ingress $appId
        if ($weakness) { return $weakness }
        $settingName = Get-Prop (Get-Prop (Get-Prop (Get-Prop $cfg "identityProviders") "azureActiveDirectory") "registration") "clientSecretSettingName"
        $secretNames = @((Invoke-Az @("containerapp", "secret", "list", "-g", $ResourceGroupName, "-n", $appName, "--query", "[].name", "-o", "tsv")).Out -split "`n")
        if (-not $settingName -or $secretNames -notcontains $settingName) { return "client secret '$settingName' is missing from the app" }
        $registrationProblem = Get-RegistrationProblem $appId
        if ($registrationProblem) { return $registrationProblem }
        if (-not (Test-ClientSecret (Get-InstalledSecret))) { return "the installed client secret does not authenticate as $appId" }
        return ""
    }

    $problem = Test-AuthConfig -BeforePublish
    if ($problem) { throw "Container Apps sign-in is not correctly configured ($problem); the app image was not published." }
    # Then the live edge, when something answers there: not offline (no active
    # revision) and not a fresh app still on internal ingress.
    if (-not $offline -and $isExternal) {
        $deadline = (Get-Date).AddMinutes(5)
        $problem = Test-SignInEnforced
        while ($problem -and (Get-Date) -lt $deadline) { Start-Sleep -Seconds 10; $problem = Test-SignInEnforced }
        if ($problem) { throw "Sign-in was not enforced within 5 minutes; the app image was not published: $problem" }
    }
    Write-Host "  ✓ Entra sign-in enforced" -ForegroundColor Green


# ── Image ────────────────────────────────────────────────────────────────────
# $builtTags, not $tags: PowerShell names are case-insensitive and $Tags is the resource-tag parameter.
$builtTags = Invoke-Az @("acr", "repository", "show-tags", "-n", $acrName, "--repository", $ImageRepo, "-o", "tsv") -AllowFailure
if ($builtTags.Code -eq 0 -and ($builtTags.Out -split "`n") -contains $tag) {
    Write-Host "  = Image ${ImageRepo}:$tag already built" -ForegroundColor Gray
} else {
    Write-Host "  Building ${ImageRepo}:$tag in $acrName (a few minutes)..." -ForegroundColor Gray
    & az acr build --registry $acrName --image "${ImageRepo}:$tag" --file (Join-Path $CardiologyAppPath "Dockerfile") $CardiologyAppPath --only-show-errors
    if ($LASTEXITCODE -ne 0) { throw "az acr build failed for ${ImageRepo}:$tag." }
    Write-Host "  ✓ Built ${ImageRepo}:$tag" -ForegroundColor Green
}
    # ── App revision (role assignments can take a minute to reach the pull) ──
    $loginServer = (Invoke-Az @("acr", "show", "-n", $acrName, "--query", "loginServer", "-o", "tsv")).Out.Trim()
    for ($attempt = 1; $attempt -le 3; $attempt++) {
        try {
            Deploy-Template -Image "$loginServer/${ImageRepo}:$tag" -UseRegistry $true -Revision $tag -PrincipalId $deployerId -AuthSecret $secret | Out-Null
            break
        } catch {
            if ($attempt -eq 3) { throw }
            Write-Host "  Revision deploy failed (attempt $attempt/3); waiting 30s for role propagation..." -ForegroundColor Yellow
            Start-Sleep -Seconds 30
        }
    }
    # The template replaced ingress, so the full policy (ingress included) must
    # hold now, before any quarantined revision is brought back. If it does not,
    # take the app offline again rather than serve it.
    $problem = Test-AuthConfig
    if ($problem) {
        Stop-AppRevisions
        throw "The access policy does not hold after publishing ($problem); $appName is offline."
    }
    # An unchanged template creates no new revision, so an offline app would
    # stay offline. The full policy holds; bring the latest revision back.
    if ($offline) {
        $latest = (Invoke-Az @("containerapp", "show", "-g", $ResourceGroupName, "-n", $appName,
            "--query", "properties.latestRevisionName", "-o", "tsv")).Out.Trim()
        $isActive = (Invoke-Az @("containerapp", "revision", "show", "-g", $ResourceGroupName, "-n", $appName,
            "--revision", $latest, "--query", "properties.active", "-o", "tsv")).Out.Trim()
        if ($isActive -ne "true") {
            Invoke-Az @("containerapp", "revision", "activate", "-g", $ResourceGroupName, "-n", $appName, "--revision", $latest, "-o", "none") | Out-Null
        }
        Write-Host "  ✓ Revision $latest back online behind sign-in" -ForegroundColor Green
    }
    Write-Host "  ✓ Revision $tag deployed to $appUrl" -ForegroundColor Green

    # ── Readiness gate: the new revision is live AND still behind sign-in ────
    $deadline = (Get-Date).AddMinutes(5)
    $healthOk = $false; $problem = "not checked"
    while ((Get-Date) -lt $deadline -and -not ($healthOk -and -not $problem)) {
        try {
            $health = Invoke-RestMethod -Uri "$appUrl/api/ready" -TimeoutSec 15
            $healthOk = $health.status -eq "ok" -and $health.profile -eq "live" -and $health.revision -eq $tag
            $problem = if ($healthOk) { Test-SignInEnforced } else { "readiness reported status=$($health.status) profile=$($health.profile) revision=$($health.revision)" }
        } catch { $healthOk = $false; $problem = "health: $($_.Exception.Message)" }
        if (-not ($healthOk -and -not $problem)) { Start-Sleep -Seconds 10 }
    }
    if (-not $healthOk -or $problem) { throw "Cardiology app did not become ready at $appUrl within 5 minutes: $problem" }
    $problem = Test-AuthConfig
    if ($problem) { throw "Sign-in configuration broke during the revision deploy: $problem" }
} finally { if ($browser) { $browser.Dispose() }; $tokenClient.Dispose(); $secret = $null }

Write-Host "  ✓ $appUrl ready on revision $tag; source health is reported separately and sign-in is enforced" -ForegroundColor Green
Write-Host ""
Write-Host "CARDIOLOGY_APP_URL=$appUrl"
Write-Host "Phase 8 Cardiology App complete." -ForegroundColor Green
