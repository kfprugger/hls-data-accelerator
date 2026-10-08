#Requires -Version 7.2
[CmdletBinding()]
param(
    [string]$SubscriptionId = '0525a464-e087-4084-a24e-a90396a83c15',
    [string]$TenantId = 'c77e97fc-1859-4575-8c8b-53d74bc35a63',
    [string]$ResourceGroup = 'rg-hls-deployer',
    [string]$Location = 'westus2',
    [string]$WardflowPath = '~/git/.worktrees/wardflow-jb-dev',
    [string]$WardflowCommit = '',
    [switch]$PublishWardflowBundle,
    [string]$ImageTag = '',
    [switch]$SkipInfra,
    [switch]$SkipImages,
    [switch]$BootstrapEntra,
    [string]$CustomDomain = 'hls.jbatl.dev',
    [string]$ClientId = $env:HLS_CLIENT_ID,
    [string]$AllowedUsers = '8d038e6a-9b7d-4cb8-bbcf-e84dff156478:joey@brakekat.com,c77e97fc-1859-4575-8c8b-53d74bc35a63:joey@jbatl.dev,72f988bf-86f1-41af-91ab-2d7cd011db47:jbrakefield@microsoft.com',
    [string]$AllowedTenants = ''
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$repoRoot = Split-Path $PSScriptRoot -Parent
$githubRepo = 'kfprugger/hls-data-accelerator'
$registry = 'acrhlsdeployer'
$vault = 'kv-hls-deployer'
$groupId = "/subscriptions/$SubscriptionId/resourceGroups/$ResourceGroup"
$registryId = "$groupId/providers/Microsoft.ContainerRegistry/registries/$registry"
$vaultId = "$groupId/providers/Microsoft.KeyVault/vaults/$vault"
$template = Join-Path $PSScriptRoot 'infra/main.bicep'

function Invoke-AzJson([string[]]$Arguments) {
    $result = & az @Arguments --subscription $SubscriptionId --only-show-errors --output json
    if ($LASTEXITCODE -ne 0) { throw "Azure CLI failed: $($Arguments[0..([Math]::Min(2, $Arguments.Count - 1))] -join ' ')" }
    if ($result) { return ($result -join "`n" | ConvertFrom-Json -AsHashtable) }
}
function Invoke-Native([string]$Program, [string[]]$Arguments) {
    & $Program @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$Program failed (exit $LASTEXITCODE)." }
}
function Get-JwtClaims([string]$Token) {
    $encoded = $Token.Split('.')[1].Replace('-', '+').Replace('_', '/')
    $encoded = $encoded.PadRight($encoded.Length + ((4 - $encoded.Length % 4) % 4), '=')
    return ([Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($encoded)) | ConvertFrom-Json -AsHashtable)
}
function Get-PinnedToken([string]$Resource) {
    $result = Invoke-AzJson @('account', 'get-access-token', '--resource', $Resource)
    $claims = Get-JwtClaims $result.accessToken
    $audiences = @($Resource.TrimEnd('/'))
    if ($Resource -eq 'https://graph.microsoft.com/') { $audiences += '00000003-0000-0000-c000-000000000000' }
    if ($claims.tid -ne $TenantId -or $claims.aud.TrimEnd('/') -notin $audiences) {
        throw 'Refusing a token from an unexpected tenant or audience. No Graph or Key Vault write was sent.'
    }
    return $result.accessToken
}
function Invoke-Graph([string]$Method, [string]$Path, [object]$Body = $null) {
    $args = @{
        Method = $Method; Uri = "https://graph.microsoft.com/v1.0/$Path"
        Headers = @{ Authorization = "Bearer $(Get-PinnedToken 'https://graph.microsoft.com/')" }
        ContentType = 'application/json'
    }
    if ($null -ne $Body) { $args.Body = $Body | ConvertTo-Json -Depth 20 -Compress }
    # Responses containing passwords are captured only by the caller, never logged.
    return Invoke-RestMethod @args
}
function Assert-BootstrapPermissions {
    if ($account.user.type -ne 'user') { throw '-BootstrapEntra requires a signed-in user, not a service principal.' }
    if (-not (Get-Command gh -ErrorAction SilentlyContinue)) { throw 'Bootstrap requires gh authenticated as kfprugger with repository admin access.' }
    $login = & gh api user --jq .login
    if ($LASTEXITCODE -ne 0 -or $login -ne 'kfprugger') { throw 'Bootstrap requires gh authenticated as kfprugger. No resources have been created.' }
    $admin = & gh api "repos/$githubRepo" --jq .permissions.admin
    if ($LASTEXITCODE -ne 0 -or $admin -ne 'true') { throw "Bootstrap requires kfprugger to have admin permission on $githubRepo. No resources have been created." }

    $canCreateApps = $false
    try {
        $path = 'me/memberOf/microsoft.graph.directoryRole?%24select=roleTemplateId'
        do {
            $page = Invoke-Graph GET $path
            # Global Administrator, Application Administrator, Cloud Application Administrator, Application Developer.
            $canCreateApps = $canCreateApps -or @($page.value | Where-Object { $_.roleTemplateId -in @(
                '62e90394-69f5-4237-9190-012177145e10', '9b895d92-2cd3-44c7-9d02-a6ac2d5ea5c3',
                '158c047a-c907-4556-b7ef-446551a6b5f7', 'cf1c38e5-3621-4004-a7cb-879624dced7c') }).Count -gt 0
            $next = $page.PSObject.Properties['@odata.nextLink']
            $path = if ($next) { ([string]$next.Value).Replace('https://graph.microsoft.com/v1.0/', '') } else { '' }
        } while ($path -and -not $canCreateApps)
    } catch { Write-Verbose "Cannot establish app-creation rights from directory roles: $($_.Exception.Message)" }
    if (-not $canCreateApps) {
        try {
            $me = Invoke-Graph GET 'me?%24select=id,userType'
            $policy = Invoke-Graph GET 'policies/authorizationPolicy'
            $canCreateApps = $me.userType -eq 'Member' -and $policy.defaultUserRolePermissions.allowedToCreateApps -eq $true
        } catch { Write-Verbose "Cannot establish app-creation rights from authorization policy: $($_.Exception.Message)" }
    }
    if (-not $canCreateApps) { throw 'Cannot verify permission to create Entra applications. Activate an application-creation directory role or enable member app registration and permit Graph policy reads. No resources have been created.' }

    $claims = Get-JwtClaims (Get-PinnedToken 'https://management.azure.com/')
    $scope = "/subscriptions/$SubscriptionId"
    try {
        $roles = @(Invoke-AzJson @('role', 'assignment', 'list', '--assignee', $claims.oid,
            '--scope', $scope, '--include-inherited', '--include-groups', '--all'))
    } catch { throw 'Cannot inspect subscription role assignments for the signed-in user. Bootstrap requires verifiable Owner or User Access Administrator access; no resources have been created.' }
    $permitted = @($roles | Where-Object {
        $_.roleDefinitionName -in @('Owner', 'User Access Administrator') -and -not $_.condition -and
        ($_.scope -ieq $scope -or $_.scope -eq '/' -or $_.scope -match '^/providers/Microsoft.Management/managementGroups/[^/]+$')
    })
    if (-not $permitted.Count) { throw "Bootstrap requires Owner or User Access Administrator at subscription $SubscriptionId (including inherited/group assignments), without a role-assignment condition. Activate the role before retrying; no resources have been created." }
}
function Ensure-Application([string]$Name, [hashtable]$Properties) {
    $query = [Uri]::EscapeDataString("displayName eq '$Name'")
    $apps = @((Invoke-Graph GET "applications?`$filter=$query").value)
    if ($apps.Count -gt 1) { throw "Multiple Entra applications named $Name; resolve the ambiguity before bootstrap." }
    if ($apps.Count -eq 0) { return Invoke-Graph POST 'applications' (@{ displayName = $Name } + $Properties) }
    $app = $apps[0]
    $null = Invoke-Graph PATCH "applications/$($app.id)" $Properties
    return $app
}
function Ensure-ServicePrincipal([string]$AppId) {
    $query = [Uri]::EscapeDataString("appId eq '$AppId'")
    $principals = @((Invoke-Graph GET "servicePrincipals?`$filter=$query").value)
    if ($principals.Count -gt 1) { throw "Ambiguous service principal for $AppId." }
    if ($principals.Count -eq 1) { return $principals[0] }
    return Invoke-Graph POST 'servicePrincipals' @{ appId = $AppId }
}
function Ensure-Role([string]$PrincipalId, [string]$Role, [string]$Scope, [string]$PrincipalType = 'ServicePrincipal') {
    $assignments = @(Invoke-AzJson @('role', 'assignment', 'list', '--scope', $Scope, '--all'))
    if ($assignments | Where-Object { $_.principalId -eq $PrincipalId -and $_.roleDefinitionName -eq $Role -and $_.scope -ieq $Scope }) { return }
    $null = Invoke-AzJson @('role', 'assignment', 'create', '--assignee-object-id', $PrincipalId,
        '--assignee-principal-type', $PrincipalType, '--role', $Role, '--scope', $Scope)
}
function Get-VaultSecret([string]$Name) {
    for ($attempt = 0; $attempt -lt 18; $attempt++) {
        try {
            return Invoke-RestMethod -Uri "https://$vault.vault.azure.net/secrets/${Name}?api-version=7.4" `
                -Headers @{ Authorization = "Bearer $(Get-PinnedToken 'https://vault.azure.net')" }
        } catch {
            $status = if ($_.Exception.Response) { [int]$_.Exception.Response.StatusCode } else { 0 }
            if ($status -eq 404) { return $null }
            if ($status -ne 403 -or $attempt -eq 17) { throw }
            Start-Sleep -Seconds 10 # New vault RBAC assignments propagate asynchronously.
        }
    }
}
function Set-VaultSecret([string]$Name, [string]$Value, [Nullable[long]]$Expires = $null) {
    $body = @{ value = $Value; attributes = @{ enabled = $true } }
    if ($null -ne $Expires) { $body.attributes.exp = $Expires }
    $null = Invoke-RestMethod -Method Put -Uri "https://$vault.vault.azure.net/secrets/${Name}?api-version=7.4" `
        -Headers @{ Authorization = "Bearer $(Get-PinnedToken 'https://vault.azure.net')" } `
        -ContentType 'application/json' -Body ($body | ConvertTo-Json -Depth 5 -Compress)
}
function Deploy-Infrastructure([bool]$Gateway, [string]$Domain = '', [bool]$Certificate = $false) {
    $parameters = @{
        location = @{ value = $Location }; gatewayImage = @{ value = $gatewayImage }
        sandboxImage = @{ value = $sandboxImage }; clientId = @{ value = [string]$ClientId }
        allowedUsers = @{ value = $AllowedUsers }; allowedTenants = @{ value = $AllowedTenants }
        deployGateway = @{ value = $Gateway }; customDomain = @{ value = $Domain }
        enableManagedCertificate = @{ value = $Certificate }
    }
    $parameterFile = Join-Path ([IO.Path]::GetTempPath()) "hls-parameters-$([Guid]::NewGuid().ToString('N')).json"
    try {
        @{ '$schema' = 'https://schema.management.azure.com/schemas/2019-04-01/deploymentParameters.json#'; contentVersion = '1.0.0.0'; parameters = $parameters } |
            ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $parameterFile
        $deployment = Invoke-AzJson @('deployment', 'group', 'create', '--resource-group', $ResourceGroup,
            '--name', 'hosted-orchestrator', '--template-file', $template, '--parameters', "@$parameterFile")
        return $deployment.properties.outputs
    } finally { Remove-Item -LiteralPath $parameterFile -Force -ErrorAction SilentlyContinue }
}
function Set-CloudflareRecord([string]$ZoneId, [string]$Type, [string]$Name, [string]$Content) {
    $headers = @{ Authorization = "Bearer $env:CLOUDFLARE_API_TOKEN" }
    $url = "https://api.cloudflare.com/client/v4/zones/$ZoneId/dns_records"
    $response = Invoke-RestMethod -Uri "${url}?type=$Type&name=$([Uri]::EscapeDataString($Name))" -Headers $headers
    if (-not $response.success) { throw "Cloudflare could not read DNS record $Name." }
    $records = @($response.result)
    if ($records.Count -gt 1) { throw "Multiple Cloudflare $Type records for $Name; refusing to overwrite ambiguous DNS." }
    $body = @{ type = $Type; name = $Name; content = $Content; ttl = 120 }
    if ($Type -eq 'CNAME') { $body.proxied = $false }
    $method = 'Post'
    if ($records.Count -eq 1) { $method = 'Put'; $url += "/$($records[0].id)" }
    $result = Invoke-RestMethod -Method $method -Uri $url -Headers $headers -ContentType 'application/json' -Body ($body | ConvertTo-Json)
    if (-not $result.success) { throw "Cloudflare could not write DNS record $Name." }
}
function Wait-PublicDns([string]$Name, [string]$Type, [string]$Expected) {
    for ($attempt = 0; $attempt -lt 40; $attempt++) {
        $reply = Invoke-RestMethod -Uri "https://cloudflare-dns.com/dns-query?name=$Name&type=$Type" -Headers @{ Accept = 'application/dns-json' }
        if ($reply.PSObject.Properties['Answer'] -and @($reply.Answer | Where-Object { $_.data.Trim('"').TrimEnd('.') -ieq $Expected.TrimEnd('.') }).Count) { return }
        Start-Sleep -Seconds 15
    }
    throw "Public $Type DNS for $Name has not propagated; rerun after it resolves to $Expected."
}
function Wait-GatewayHealth([string]$Fqdn, [int]$TimeoutMinutes, [switch]$CheckRevision) {
    $deadline = [DateTimeOffset]::UtcNow.AddMinutes($TimeoutMinutes)
    $lastStatus = 'not checked'
    do {
        try {
            $ready = $true
            if ($CheckRevision) {
                $app = Invoke-AzJson @('containerapp', 'show', '--resource-group', $ResourceGroup, '--name', 'hls-gateway')
                $revisionName = $app.properties.latestRevisionName
                $ready = $false
                if ($revisionName) {
                    $revision = Invoke-AzJson @('containerapp', 'revision', 'show', '--resource-group', $ResourceGroup,
                        '--name', 'hls-gateway', '--revision', $revisionName)
                    $lastStatus = "$revisionName running=$($revision.properties.runningState) health=$($revision.properties.healthState)"
                    $ready = $revision.properties.runningState -in @('Running', 'RunningAtMaxScale') -and $revision.properties.healthState -eq 'Healthy'
                }
            }
            if ($ready) {
                $response = Invoke-WebRequest -Uri "https://$Fqdn/healthz" -TimeoutSec 20 -MaximumRedirection 0
                $lastStatus = "HTTP $($response.StatusCode)"
                if ($response.StatusCode -eq 200) { Write-Host "Gateway healthy: https://$Fqdn"; return }
            }
        } catch { $lastStatus = $_.Exception.Message }
        Start-Sleep -Seconds 15
    } while ([DateTimeOffset]::UtcNow -lt $deadline)
    throw "Gateway did not become healthy at https://$Fqdn/healthz within $TimeoutMinutes minutes. Last observation: $lastStatus"
}
function Initialize-GitHub {
    $raw = & gh api "repos/$githubRepo/actions/oidc/customization/sub"
    if ($LASTEXITCODE -ne 0) { throw 'Cannot inspect GitHub OIDC customization; refusing to guess the federated subject.' }
    $customization = $raw | ConvertFrom-Json -AsHashtable
    if (-not $customization['use_default'] -and ($customization['include_claim_keys'] -join ',') -ne 'repo,context') {
        throw 'OIDC uses an unsupported custom subject template (expected repo,context). Inspect the actual token subject before provisioning federation.'
    }
    $rawRepo = & gh api "repos/$githubRepo"
    if ($LASTEXITCODE -ne 0) { throw 'Cannot read GitHub immutable repository and owner IDs.' }
    $repo = $rawRepo | ConvertFrom-Json -AsHashtable
    $prefix = "repo:$githubRepo"
    if ($customization['use_immutable_subject']) { $prefix = "repo:$($repo.owner.login)@$($repo.owner.id)/$($repo.name)@$($repo.id)" }
    if ($customization['sub_claim_prefix']) { $prefix = $customization['sub_claim_prefix'].TrimEnd(':') }
    $subject = "${prefix}:ref:refs/heads/main"
    $app = Ensure-Application 'hls-deployer-github' @{ signInAudience = 'AzureADMyOrg' }
    $principal = Ensure-ServicePrincipal $app.appId
    $credential = @{
        name = 'github-main'; issuer = 'https://token.actions.githubusercontent.com'; subject = $subject
        audiences = @('api://AzureADTokenExchange'); description = "$githubRepo main branch releases"
    }
    $credentials = @((Invoke-Graph GET "applications/$($app.id)/federatedIdentityCredentials").value)
    $existing = @($credentials | Where-Object name -eq 'github-main')
    if ($existing.Count) { $null = Invoke-Graph PATCH "applications/$($app.id)/federatedIdentityCredentials/$($existing[0].id)" $credential }
    else { $null = Invoke-Graph POST "applications/$($app.id)/federatedIdentityCredentials" $credential }
    Ensure-Role $principal.id 'AcrPush' $registryId
    Ensure-Role $principal.id 'Contributor' $groupId
    foreach ($secret in @{ AZURE_CLIENT_ID = $app.appId; AZURE_TENANT_ID = $TenantId; AZURE_SUBSCRIPTION_ID = $SubscriptionId }.GetEnumerator()) {
        $secret.Value | & gh secret set $secret.Key --repo $githubRepo
        if ($LASTEXITCODE -ne 0) { throw "Could not set GitHub secret $($secret.Key)." }
    }
    Write-Host "GitHub federation configured: $subject"
}
function Publish-WardflowBundle([string]$Commit) {
    $stage = Join-Path ([IO.Path]::GetTempPath()) "hls-wardflow-$([Guid]::NewGuid().ToString('N'))"
    try {
        $null = New-Item -ItemType Directory -Path $stage
        $archive = Join-Path $stage 'wardflow.tar'
        Invoke-Native git @('-C', $WardflowPath, 'archive', '--format=tar', "--output=$archive", $Commit, 'caldova-cardio')
        $context = Join-Path $stage 'context'
        $null = New-Item -ItemType Directory -Path $context
        Invoke-Native tar @('-xf', $archive, '-C', $context)
        Set-Content -LiteralPath (Join-Path $context '.pinned-commit') -Value $Commit -NoNewline
        Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'sandbox/wardflow-bundle.Dockerfile') -Destination (Join-Path $context 'Dockerfile')
        Write-Host "Publishing WardFlow bundle $Commit (committed source only)."
        Invoke-Native az @('acr', 'build', '--subscription', $SubscriptionId, '--registry', $registry, '--platform', 'linux/amd64',
            '--image', "hls-wardflow-bundle:$Commit", '--file', 'Dockerfile', $context)
    } finally { if (Test-Path -LiteralPath $stage) { Remove-Item -LiteralPath $stage -Recurse -Force } }
    if ((Get-Command gh -ErrorAction SilentlyContinue) -and ((& gh api user --jq .login 2>$null) -eq 'kfprugger')) {
        Invoke-Native gh @('variable', 'set', 'WARDFLOW_REF', '--repo', $githubRepo, '--body', $Commit)
        Write-Host "GitHub variable WARDFLOW_REF set to $Commit; CI releases now use this bundle."
    } else {
        Write-Warning "Set GitHub variable WARDFLOW_REF to $Commit so CI releases use this bundle."
    }
}

# Fail closed against the CURRENT CLI context, before any resource or Graph write.
$accountJson = & az account show --output json --only-show-errors
if ($LASTEXITCODE -ne 0) { throw "Authenticate first: az login --use-device-code --tenant $TenantId" }
$account = $accountJson | ConvertFrom-Json -AsHashtable
if ($account.id -ne $SubscriptionId -or $account.tenantId -ne $TenantId) {
    throw "Wrong Azure context. Run: az login --use-device-code --tenant $TenantId ; az account set --subscription $SubscriptionId"
}
if ($BootstrapEntra) { Assert-BootstrapPermissions }
if (-not $ImageTag) {
    $ImageTag = & git -C $repoRoot rev-parse --short HEAD
    if ($LASTEXITCODE -ne 0) { throw 'Cannot resolve the HLS source commit.' }
}
if ($ImageTag -notmatch '^[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}$') { throw 'ImageTag is not a valid OCI tag.' }
$gatewayImage = "$registry.azurecr.io/hls-gateway:$ImageTag"
$sandboxImage = "$registry.azurecr.io/hls-orchestrator-sandbox:$ImageTag"
if ($WardflowCommit -and $WardflowCommit -notmatch '^[0-9a-f]{40}$') { throw 'WardflowCommit must be a full 40-character commit SHA.' }
if ($PublishWardflowBundle -or (-not $WardflowCommit -and ($BootstrapEntra -or -not $SkipImages))) {
    $WardflowPath = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($WardflowPath)
    if (-not $WardflowCommit) { $WardflowCommit = & git -C $WardflowPath rev-parse HEAD }
    if ($LASTEXITCODE -ne 0 -or -not $WardflowCommit) { throw "WardflowPath must be the wardflow checkout, or pass -WardflowCommit: $WardflowPath" }
}
$wardflowCommit = $WardflowCommit
$wardflowBundleImage = "$registry.azurecr.io/hls-wardflow-bundle:$wardflowCommit"
$exists = Invoke-AzJson @('group', 'exists', '--name', $ResourceGroup)
$existingApp = $null
if ($exists) { $existingApp = @(Invoke-AzJson @('containerapp', 'list', '--resource-group', $ResourceGroup)) | Where-Object name -eq 'hls-gateway' }
if ($existingApp) {
    $currentEnv = $existingApp.properties.template.containers[0].env
    if (-not $ClientId) { $ClientId = ($currentEnv | Where-Object name -eq 'HLS_CLIENT_ID').value }
    if (-not $PSBoundParameters.ContainsKey('AllowedUsers')) {
        $savedUsers = @($currentEnv | Where-Object name -eq 'HLS_ALLOWED_USERS')
        if ($savedUsers.Count) { $AllowedUsers = [string]$savedUsers[0].value }
    }
    if (-not $PSBoundParameters.ContainsKey('AllowedTenants')) { $AllowedTenants = ($currentEnv | Where-Object name -eq 'HLS_ALLOWED_TENANTS').value }
}
if ($SkipInfra -and -not $existingApp) { throw '-SkipInfra requires an already bootstrapped hls-gateway.' }
if (-not $SkipInfra) {
    $null = Invoke-AzJson @('group', 'create', '--name', $ResourceGroup, '--location', $Location)
    $foundation = Deploy-Infrastructure $false
    $defaultFqdn = "hls-gateway.$($foundation.environmentDefaultDomain.value)"
} else { $defaultFqdn = $existingApp.properties.configuration.ingress.fqdn }

if ($BootstrapEntra) {
    $armClaims = Get-JwtClaims (Get-PinnedToken 'https://management.azure.com/')
    Ensure-Role $armClaims.oid 'Key Vault Secrets Officer' $vaultId 'User'
    $redirects = @("https://$defaultFqdn/auth/callback", 'https://hls.jbatl.dev/auth/callback')
    if ($CustomDomain) { $redirects += "https://$CustomDomain/auth/callback" }
    $portal = Ensure-Application 'hls-deployer-portal' @{
        signInAudience = 'AzureADMultipleOrgs'
        web = @{ redirectUris = @($redirects | Select-Object -Unique) }
        optionalClaims = @{ idToken = @(@{ name = 'email'; essential = $false }, @{ name = 'upn'; essential = $false }) }
        requiredResourceAccess = @(@{
            resourceAppId = '00000003-0000-0000-c000-000000000000'
            resourceAccess = @(
                @{ id = '37f7f235-527c-4136-accd-4a02d197296e'; type = 'Scope' }
                @{ id = '14dad69e-099b-42c9-810b-d002981feec1'; type = 'Scope' }
                @{ id = '64a6cdd6-aab1-4aaf-94b8-3cc8405e90d0'; type = 'Scope' }
                @{ id = 'e1fe6dd8-ba31-4d61-89e7-88639da4683d'; type = 'Scope' }
            )
        })
    }
    $null = Ensure-ServicePrincipal $portal.appId
    $ClientId = $portal.appId
    $clientSecret = Get-VaultSecret 'gateway-client-secret'
    $expires = if ($clientSecret -and $clientSecret.attributes.PSObject.Properties['exp']) { [long]$clientSecret.attributes.exp } else { 0 }
    if (-not $clientSecret -or ($expires -gt 0 -and $expires -lt [DateTimeOffset]::UtcNow.AddDays(30).ToUnixTimeSeconds())) {
        $expiry = [DateTimeOffset]::UtcNow.AddMonths(12)
        $password = Invoke-Graph POST "applications/$($portal.id)/addPassword" @{
            passwordCredential = @{ displayName = 'hosted-gateway'; endDateTime = $expiry.ToString('o') }
        }
        Set-VaultSecret 'gateway-client-secret' $password.secretText $expiry.ToUnixTimeSeconds()
        $password = $null
    }
    $clientSecret = $null
    $sessionSecret = Get-VaultSecret 'gateway-session-key'
    if (-not $sessionSecret) {
        Set-VaultSecret 'gateway-session-key' ([Convert]::ToBase64String([Security.Cryptography.RandomNumberGenerator]::GetBytes(64)))
    }
    $sessionSecret = $null
    Initialize-GitHub
}
if (-not $ClientId) { throw 'No portal client ID. First run with -BootstrapEntra, or provide -ClientId and provision both gateway secrets in Key Vault.' }

if ($PublishWardflowBundle) { Publish-WardflowBundle $wardflowCommit }
if (-not $SkipImages) {
    $bundleTags = @()
    try { $bundleTags = @(Invoke-AzJson @('acr', 'repository', 'show-tags', '--name', $registry, '--repository', 'hls-wardflow-bundle')) } catch { $bundleTags = @() }
    if ($bundleTags -notcontains $wardflowCommit) {
        throw "WardFlow bundle $wardflowCommit is not in $registry. Publish it from a machine with the wardflow checkout: ./hosted/Deploy-HostedOrchestrator.ps1 -PublishWardflowBundle -SkipInfra"
    }
    $stage = Join-Path ([IO.Path]::GetTempPath()) "hls-build-$([Guid]::NewGuid().ToString('N'))"
    try {
        $null = New-Item -ItemType Directory -Path $stage
        $sourceTar = Join-Path $stage 'source.tar'
        Invoke-Native git @('-C', $repoRoot, 'archive', '--format=tar', "--output=$sourceTar", 'HEAD')
        $context = Join-Path $stage 'context'
        $null = New-Item -ItemType Directory -Path $context
        Invoke-Native tar @('-xf', $sourceTar, '-C', $context)
        # ACR must use the sandbox-specific source allowlist, not the root emulator exclusions.
        Copy-Item -LiteralPath (Join-Path $context 'hosted/sandbox/Dockerfile.dockerignore') -Destination (Join-Path $context '.dockerignore') -Force
        Write-Host "Building committed HLS $ImageTag with WardFlow bundle $wardflowCommit (uncommitted changes are not shipped)."
        Invoke-Native az @('acr', 'build', '--subscription', $SubscriptionId, '--registry', $registry, '--platform', 'linux/amd64',
            '--build-arg', "WARDFLOW_BUNDLE_IMAGE=$wardflowBundleImage",
            '--image', "hls-orchestrator-sandbox:$ImageTag", '--file', 'hosted/sandbox/Dockerfile', $context)
        Invoke-Native az @('acr', 'build', '--subscription', $SubscriptionId, '--registry', $registry, '--platform', 'linux/amd64',
            '--image', "hls-gateway:$ImageTag", '--file', 'Dockerfile', (Join-Path $context 'hosted/gateway'))
    } finally { if (Test-Path -LiteralPath $stage) { Remove-Item -LiteralPath $stage -Recurse -Force } }
}

if ($SkipInfra) {
    $null = Invoke-AzJson @('containerapp', 'update', '--name', 'hls-gateway', '--resource-group', $ResourceGroup,
        '--image', $gatewayImage, '--set-env-vars', "HLS_SANDBOX_IMAGE=$sandboxImage")
    Wait-GatewayHealth $defaultFqdn 10 -CheckRevision
} else {
    $boundDomain = ''
    $boundCertificate = $false
    if ($existingApp -and $CustomDomain) {
        $binding = @($existingApp.properties.configuration.ingress['customDomains'] | Where-Object { $_.name -eq $CustomDomain -and $_.bindingType -eq 'SniEnabled' })
        if ($binding.Count) { $boundDomain = $CustomDomain; $boundCertificate = $true }
    }
    $outputs = Deploy-Infrastructure $true $boundDomain $boundCertificate
    Wait-GatewayHealth $outputs.gatewayFqdn.value 10 -CheckRevision
    if ($CustomDomain -and $env:CLOUDFLARE_API_TOKEN) {
        if (-not $CustomDomain.EndsWith('.jbatl.dev', [StringComparison]::OrdinalIgnoreCase)) { throw 'Automatic DNS is restricted to subdomains of zone jbatl.dev.' }
        $zones = Invoke-RestMethod -Uri 'https://api.cloudflare.com/client/v4/zones?name=jbatl.dev' -Headers @{ Authorization = "Bearer $env:CLOUDFLARE_API_TOKEN" }
        if (-not $zones.success -or @($zones.result).Count -ne 1) { throw 'Cloudflare token must have Zone:Read and DNS:Edit access to jbatl.dev.' }
        $zoneId = $zones.result[0].id
        Set-CloudflareRecord $zoneId 'CNAME' $CustomDomain $outputs.gatewayFqdn.value
        Set-CloudflareRecord $zoneId 'TXT' "asuid.$CustomDomain" $outputs.customDomainVerificationId.value
        Wait-PublicDns $CustomDomain 'CNAME' $outputs.gatewayFqdn.value
        Wait-PublicDns "asuid.$CustomDomain" 'TXT' $outputs.customDomainVerificationId.value
        if (-not $boundCertificate) { $null = Deploy-Infrastructure $true $CustomDomain $false }
        $outputs = Deploy-Infrastructure $true $CustomDomain $true
        Wait-GatewayHealth $CustomDomain 20
    } elseif ($CustomDomain) {
        Write-Warning 'CLOUDFLARE_API_TOKEN is absent: DNS and new custom-domain certificate binding skipped. Existing TLS binding is preserved; otherwise use the default gateway FQDN. Rerun with the token and -SkipImages to bind the domain.'
    }
}
Write-Host "Gateway image: $gatewayImage"
Write-Host "Sandbox image: $sandboxImage (existing sandboxes update only when no deployment is active)."
Write-Host "Default gateway URL: https://$defaultFqdn"
Write-Host "Custom domain requested: $CustomDomain. Use it only after the managed certificate is bound."
