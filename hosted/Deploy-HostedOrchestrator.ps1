#Requires -Version 7.2
[CmdletBinding()]
param(
    [string]$SubscriptionId = '',
    [string]$TenantId = '',
    [string]$ResourceGroup = 'rg-hls-deployer',
    [string]$Location = 'westus2',
    [string]$WardflowPath = '',
    [string]$WardflowCommit = '',
    [switch]$PublishWardflowBundle,
    [string]$ImageTag = '',
    [switch]$SkipInfra,
    [switch]$SkipImages,
    [switch]$BootstrapEntra,
    [string]$CustomDomain = '',
    [string]$DnsZone = '',
    [string]$ClientId = $env:HLS_CLIENT_ID,
    [string]$AllowedUsers = '',
    [string]$AllowedTenants = '',
    [string[]]$AllowedDomains = @(),
    [string]$DeploymentProfile = '',
    [string]$GitHubRepo = '',
    [string]$Registry = '',
    [string]$Vault = '',
    [string]$Storage = ''
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$repoRoot = Split-Path $PSScriptRoot -Parent

Import-Module (Join-Path $PSScriptRoot 'HostedDeployHelper.psm1') -Force

$profileData = @{}
if ($DeploymentProfile) {
    $profileData = Import-DeploymentProfile -ProfileName $DeploymentProfile -ProfilesDir (Join-Path $PSScriptRoot 'profiles')
}

if (-not $PSBoundParameters.ContainsKey('SubscriptionId') -and $profileData.ContainsKey('SubscriptionId')) { $SubscriptionId = $profileData['SubscriptionId'] }
if (-not $PSBoundParameters.ContainsKey('TenantId') -and $profileData.ContainsKey('TenantId')) { $TenantId = $profileData['TenantId'] }
if (-not $PSBoundParameters.ContainsKey('ResourceGroup') -and $profileData.ContainsKey('ResourceGroup')) { $ResourceGroup = $profileData['ResourceGroup'] }
if (-not $PSBoundParameters.ContainsKey('Location') -and $profileData.ContainsKey('Location')) { $Location = $profileData['Location'] }
if (-not $PSBoundParameters.ContainsKey('WardflowPath') -and $profileData.ContainsKey('WardflowPath')) { $WardflowPath = $profileData['WardflowPath'] }
if (-not $PSBoundParameters.ContainsKey('WardflowCommit') -and $profileData.ContainsKey('WardflowCommit')) { $WardflowCommit = $profileData['WardflowCommit'] }
if (-not $PSBoundParameters.ContainsKey('CustomDomain') -and $profileData.ContainsKey('CustomDomain')) { $CustomDomain = $profileData['CustomDomain'] }
if (-not $PSBoundParameters.ContainsKey('DnsZone') -and $profileData.ContainsKey('DnsZone')) { $DnsZone = $profileData['DnsZone'] }
if (-not $PSBoundParameters.ContainsKey('ClientId') -and $profileData.ContainsKey('ClientId')) { $ClientId = $profileData['ClientId'] }
if (-not $PSBoundParameters.ContainsKey('AllowedUsers') -and $profileData.ContainsKey('AllowedUsers')) { $AllowedUsers = $profileData['AllowedUsers'] }
if (-not $PSBoundParameters.ContainsKey('AllowedTenants') -and $profileData.ContainsKey('AllowedTenants')) { $AllowedTenants = $profileData['AllowedTenants'] }
if (-not $PSBoundParameters.ContainsKey('AllowedDomains') -and $profileData.ContainsKey('AllowedDomains')) { $AllowedDomains = @($profileData['AllowedDomains']) }
if (-not $PSBoundParameters.ContainsKey('GitHubRepo') -and $profileData.ContainsKey('GitHubRepo')) { $GitHubRepo = $profileData['GitHubRepo'] }
if (-not $PSBoundParameters.ContainsKey('Registry') -and $profileData.ContainsKey('Registry')) { $Registry = $profileData['Registry'] }
if (-not $PSBoundParameters.ContainsKey('Vault') -and $profileData.ContainsKey('Vault')) { $Vault = $profileData['Vault'] }
if (-not $PSBoundParameters.ContainsKey('Storage') -and $profileData.ContainsKey('Storage')) { $Storage = $profileData['Storage'] }

$hasExplicitRegistry = $PSBoundParameters.ContainsKey('Registry') -or ($profileData -and $profileData.ContainsKey('Registry'))
$hasExplicitVault = $PSBoundParameters.ContainsKey('Vault') -or ($profileData -and $profileData.ContainsKey('Vault'))
$hasExplicitStorage = $PSBoundParameters.ContainsKey('Storage') -or ($profileData -and $profileData.ContainsKey('Storage'))
$hasExplicitCustomDomain = $PSBoundParameters.ContainsKey('CustomDomain') -or ($profileData -and $profileData.ContainsKey('CustomDomain'))

if (-not $SubscriptionId) { throw 'SubscriptionId is required (pass -SubscriptionId or specify in -DeploymentProfile).' }
if (-not $TenantId) { throw 'TenantId is required (pass -TenantId or specify in -DeploymentProfile).' }

if (-not $GitHubRepo) {
    try {
        $originUrl = (& git -C $repoRoot config --get remote.origin.url 2>$null)
        if ($originUrl -and $originUrl -match 'github\.com[:/](?<owner>[^/]+)/(?<repo>[^/]+?)(?:\.git)?$') {
            $GitHubRepo = "$($Matches['owner'])/$($Matches['repo'])"
        }
    } catch { Write-Verbose "Cannot derive GitHubRepo from origin: $($_.Exception.Message)" }
}

if ($CustomDomain -and $DnsZone) {
    Test-CustomDomainDnsZone -CustomDomain $CustomDomain -DnsZone $DnsZone
}

$registry = $Registry
$vault = $Vault
$storage = $Storage
$githubRepo = $GitHubRepo
$groupId = "/subscriptions/$SubscriptionId/resourceGroups/$ResourceGroup"
$registryId = ''
$vaultId = ''
$template = Join-Path $PSScriptRoot 'infra/main.bicep'

function Invoke-AzJson([string[]]$Arguments) {
    $errFile = [System.IO.Path]::GetTempFileName()
    try {
        $result = & az @Arguments --subscription $SubscriptionId --only-show-errors --output json 2>$errFile
        $cmdName = $(@($Arguments[0..([Math]::Min(2, $Arguments.Count - 1))]) -join ' ')
        $rawErr = if (Test-Path -LiteralPath $errFile) { Get-Content -LiteralPath $errFile -Raw } else { $null }
        $errText = if ($rawErr) { [string]$rawErr.Trim() } else { '' }
        if ($LASTEXITCODE -ne 0) {
            $msg = "Azure CLI failed: $cmdName"
            if ($errText) { $msg += ": $errText" }
            throw $msg
        }
        if ($errText) {
            Write-Warning "Azure CLI ($cmdName): $errText"
        }
        if ($result) {
            $jsonText = ($result -join "`n").Trim()
            if ($jsonText) {
                return ($jsonText | ConvertFrom-Json)
            }
        }
    } finally {
        Remove-Item -LiteralPath $errFile -Force -ErrorAction SilentlyContinue
    }
}
function Invoke-Native([string]$Program, [string[]]$Arguments) {
    & $Program @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$Program failed (exit $LASTEXITCODE)." }
}
function Invoke-AcrBuild([string]$Context, [string]$Image, [string]$File, [string[]]$Extra = @()) {
    # az acr build resolves --file against the current directory first; build from inside the
    # staged context so a same-named file in the caller's directory is never uploaded instead.
    Push-Location -LiteralPath $Context
    try {
        Invoke-Native az (@('acr', 'build', '--subscription', $SubscriptionId, '--registry', $registry, '--platform', 'linux/amd64',
            '--image', $Image, '--file', $File) + $Extra + @('.'))
    } finally { Pop-Location }
}
function Get-JwtClaims([string]$Token) {
    $encoded = $Token.Split('.')[1].Replace('-', '+').Replace('_', '/')
    $encoded = $encoded.PadRight($encoded.Length + ((4 - $encoded.Length % 4) % 4), '=')
    return ([Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($encoded)) | ConvertFrom-Json -AsHashtable)
}
function Get-PinnedToken([string]$Resource) {
    $result = Invoke-AzJson @('account', 'get-access-token', '--resource', $Resource)
    $claims = Get-JwtClaims $result.accessToken
    # Entra may issue the audience as the resource URI or as the resource's first-party application ID.
    $aliases = @{
        'https://graph.microsoft.com'    = @('00000003-0000-0000-c000-000000000000')
        'https://vault.azure.net'        = @('cfa8b339-82a2-471a-a3c9-0fc0be7a4093')
        'https://management.azure.com'   = @('797f4846-ba00-4fd7-ba43-dac1f8f63013', 'https://management.core.windows.net')
    }
    $audiences = @($Resource.TrimEnd('/')) + @($aliases[$Resource.TrimEnd('/')] | Where-Object { $_ })
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
    if (-not $githubRepo) { throw 'GitHubRepo owner/name is required for bootstrap.' }
    if (-not (Get-Command gh -ErrorAction SilentlyContinue)) { throw "Bootstrap requires gh authenticated with repository admin access on $githubRepo." }
    $login = & gh api user --jq .login
    if ($LASTEXITCODE -ne 0 -or -not $login) { throw 'Bootstrap requires gh to be authenticated. No resources have been created.' }
    $admin = & gh api "repos/$githubRepo" --jq .permissions.admin
    if ($LASTEXITCODE -ne 0 -or $admin -ne 'true') { throw "Bootstrap requires current gh user ($login) to have admin permission on $githubRepo. No resources have been created." }

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
            '--scope', $scope, '--include-inherited', '--include-groups'))
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
    $assignments = @(Invoke-AzJson @('role', 'assignment', 'list', '--scope', $Scope))
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
            $response = $_.Exception.PSObject.Properties['Response']
            $status = if ($response -and $response.Value) { [int]$response.Value.StatusCode } else { 0 }
            if ($status -eq 404) { return $null }
            # 403: new vault RBAC assignments propagate asynchronously; 0: a new vault's DNS/endpoint is not ready yet.
            if ($status -notin @(0, 403) -or $attempt -eq 17) { throw }
            Start-Sleep -Seconds 10
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
        registryName = @{ value = $registry }
        storageAccountName = @{ value = $storage }
        keyVaultName = @{ value = $vault }
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
    $canonicalRepo = if ($repo.full_name) { $repo.full_name } else { $githubRepo }
    $prefix = "repo:$canonicalRepo"
    if ($customization['use_immutable_subject']) { $prefix = "repo:$($repo.owner.login)@$($repo.owner.id)/$($repo.name)@$($repo.id)" }
    if ($customization['sub_claim_prefix']) { $prefix = $customization['sub_claim_prefix'].TrimEnd(':') }
    $subject = "${prefix}:ref:refs/heads/main"
    $app = Ensure-Application 'hls-deployer-github' @{ signInAudience = 'AzureADMyOrg' }
    $principal = Ensure-ServicePrincipal $app.appId
    $credential = @{
        name = 'github-main'; issuer = 'https://token.actions.githubusercontent.com'; subject = $subject
        audiences = @('api://AzureADTokenExchange'); description = "$canonicalRepo main branch releases"
    }
    $credentials = @((Invoke-Graph GET "applications/$($app.id)/federatedIdentityCredentials").value)
    $existing = @($credentials | Where-Object name -eq 'github-main')
    if ($existing.Count) { $null = Invoke-Graph PATCH "applications/$($app.id)/federatedIdentityCredentials/$($existing[0].id)" $credential }
    else { $null = Invoke-Graph POST "applications/$($app.id)/federatedIdentityCredentials" $credential }
    Ensure-Role $principal.id 'AcrPush' $registryId
    Ensure-Role $principal.id 'Contributor' $groupId
    foreach ($secret in @{ AZURE_CLIENT_ID = $app.appId; AZURE_TENANT_ID = $TenantId; AZURE_SUBSCRIPTION_ID = $SubscriptionId }.GetEnumerator()) {
        $secret.Value | & gh secret set $secret.Key --repo $canonicalRepo
        if ($LASTEXITCODE -ne 0) { throw "Could not set GitHub secret $($secret.Key)." }
    }
    Write-Host "GitHub federation configured: $subject"
}
function Publish-WardflowBundle([string]$Commit, [switch]$SetGitHubVariable) {
    if (-not $Commit) { throw 'WardflowCommit is required to publish a bundle.' }
    $stage = Join-Path ([IO.Path]::GetTempPath()) "hls-wardflow-$([Guid]::NewGuid().ToString('N'))"
    try {
        $null = New-Item -ItemType Directory -Path $stage
        $context = Join-Path $stage 'context'
        $null = New-Item -ItemType Directory -Path $context

        if ($Commit -eq 'none') {
            Write-Host "Publishing empty WardFlow bundle (none)."
            Set-Content -LiteralPath (Join-Path $context '.pinned-commit') -Value 'none' -NoNewline
        } else {
            if (-not $WardflowPath) { throw "WardflowPath must be the wardflow checkout to publish bundle $Commit." }
            $resolvedWardflowPath = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($WardflowPath)
            if (-not (Test-Path -LiteralPath $resolvedWardflowPath)) {
                throw "WardFlow checkout path not found: $WardflowPath"
            }
            # Inspect commit tree for available paths (H-5)
            $treeItems = @(Invoke-Native git @('-C', $resolvedWardflowPath, 'ls-tree', '--name-only', $Commit))
            $targets = @('caldova-cardio', 'rayfin-wardflow-persona-app')
            foreach ($target in $targets) {
                if ($treeItems -notcontains $target) {
                    throw "WardFlow commit $Commit lacks required path '$target'."
                }
            }
            $archive = Join-Path $stage 'wardflow.tar'
            Invoke-Native git (@('-C', $resolvedWardflowPath, 'archive', '--format=tar', "--output=$archive", $Commit) + $targets)
            Invoke-Native tar @('-xf', $archive, '-C', $context)
            Set-Content -LiteralPath (Join-Path $context '.pinned-commit') -Value $Commit -NoNewline
        }

        Set-Content -LiteralPath (Join-Path $context '.dockerignore') -Value "Dockerfile`n.dockerignore"
        Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'sandbox/wardflow-bundle.Dockerfile') -Destination (Join-Path $context 'Dockerfile')
        Write-Host "Publishing WardFlow bundle $Commit (committed source only)."
        Invoke-AcrBuild $context "hls-wardflow-bundle:$Commit" 'Dockerfile'
    } finally { if (Test-Path -LiteralPath $stage) { Remove-Item -LiteralPath $stage -Recurse -Force } }

    if ($SetGitHubVariable) {
        $canSetVar = $false
        if ($githubRepo -and (Get-Command gh -ErrorAction SilentlyContinue)) {
            $admin = & gh api "repos/$githubRepo" --jq .permissions.admin 2>$null
            if ($LASTEXITCODE -eq 0 -and $admin -eq 'true') {
                $canSetVar = $true
            }
        }
        if ($canSetVar) {
            $shouldSet = $true
            if ($Commit -eq 'none') {
                $existingRef = (& gh variable get WARDFLOW_REF --repo $githubRepo 2>$null)
                if ($LASTEXITCODE -eq 0 -and $existingRef -and $existingRef.Trim() -match '^[0-9a-f]{40}$') {
                    $shouldSet = $false
                    Write-Host "Existing GitHub variable WARDFLOW_REF is a commit SHA ($($existingRef.Trim())); preserving it and not replacing with 'none'."
                }
            }
            if ($shouldSet) {
                Invoke-Native gh @('variable', 'set', 'WARDFLOW_REF', '--repo', $githubRepo, '--body', $Commit)
                Write-Host "GitHub variable WARDFLOW_REF set to $Commit; CI releases now use this bundle."
            }
        } else {
            Write-Warning "Set GitHub variable WARDFLOW_REF to $Commit on $githubRepo so CI releases use this bundle."
        }
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

$exists = Invoke-AzJson @('group', 'exists', '--name', $ResourceGroup)
$existingApp = $null
if ($exists) {
    $apps = Invoke-AzJson @('containerapp', 'list', '--resource-group', $ResourceGroup)
    [object[]]$appList = if ($apps -is [System.Collections.IDictionary]) { ,$apps } else { $apps }
    foreach ($app in $appList) {
        if ($app -and $app.PSObject.Properties['name'] -and $app.name -eq 'hls-gateway') {
            $existingApp = $app
            break
        }
    }
}
if ($existingApp) {
    $currentEnv = $existingApp.properties.template.containers[0].env
    if (-not $ClientId) { $ClientId = ($currentEnv | Where-Object name -eq 'HLS_CLIENT_ID').value }

    # N-5: On a redeploy, the live gateway allowlist is authoritative.
    # Profile AllowedUsers and AllowedTenants never apply on a redeploy; live values
    # are authoritative (including absent or empty) unless explicit parameters are passed.
    $savedUsers = @($currentEnv | Where-Object { $_ -and $_.PSObject.Properties['name'] -and $_.name -eq 'HLS_ALLOWED_USERS' })
    $savedTenants = @($currentEnv | Where-Object { $_ -and $_.PSObject.Properties['name'] -and $_.name -eq 'HLS_ALLOWED_TENANTS' })

    if (-not $PSBoundParameters.ContainsKey('AllowedUsers')) {
        $AllowedUsers = ''
        if ($savedUsers.Count -gt 0) {
            $prop = $savedUsers[0].PSObject.Properties['value']
            if ($prop -and $prop.Value) { $AllowedUsers = [string]$prop.Value }
        }
    }
    if (-not $PSBoundParameters.ContainsKey('AllowedTenants')) {
        $AllowedTenants = ''
        if ($savedTenants.Count -gt 0) {
            $prop = $savedTenants[0].PSObject.Properties['value']
            if ($prop -and $prop.Value) { $AllowedTenants = [string]$prop.Value }
        }
    }
    if (-not $PSBoundParameters.ContainsKey('AllowedDomains')) {
        $AllowedDomains = @()
    }

    # H-4: When a gateway already exists and registry, key vault or storage names were not given
    # (param or profile), read them from the live deployment.
    if (-not $hasExplicitRegistry) {
        $server = ''
        if ($existingApp.properties.configuration.PSObject.Properties['registries'] -and $existingApp.properties.configuration.registries.Count -gt 0) {
            $server = $existingApp.properties.configuration.registries[0].server
        }
        if ($server -and $server.EndsWith('.azurecr.io', [StringComparison]::OrdinalIgnoreCase)) {
            $Registry = $server.Substring(0, $server.Length - 11)
        } else {
            $existingImage = $existingApp.properties.template.containers[0].image
            $imageHost = $existingImage.Split('/')[0]
            if ($imageHost.EndsWith('.azurecr.io', [StringComparison]::OrdinalIgnoreCase)) {
                $Registry = $imageHost.Substring(0, $imageHost.Length - 11)
            }
        }
    }
    if (-not $hasExplicitVault) {
        if ($existingApp.properties.configuration.PSObject.Properties['secrets']) {
            foreach ($sec in $existingApp.properties.configuration.secrets) {
                if ($sec.keyVaultUrl -and $sec.keyVaultUrl -match '^https://(?<vaultName>[^.]+)\.vault\.azure\.net') {
                    $Vault = $Matches['vaultName']
                    break
                }
            }
        }
    }
    if (-not $hasExplicitStorage) {
        $savedStorage = ($currentEnv | Where-Object name -eq 'HLS_STORAGE_ACCOUNT')
        if ($savedStorage -and $savedStorage.value) {
            $Storage = [string]$savedStorage.value
        }
    }
    # Keep an existing custom-domain binding (read it from live when not given)
    if (-not $hasExplicitCustomDomain) {
        if ($existingApp.properties.configuration.ingress.PSObject.Properties['customDomains']) {
            $existingDomains = @($existingApp.properties.configuration.ingress.customDomains)
            if ($existingDomains.Count -gt 0 -and $existingDomains[0].name) {
                $CustomDomain = [string]$existingDomains[0].name
            }
        }
    }
} else {
    if (-not $PSBoundParameters.ContainsKey('AllowedUsers') -and $profileData.ContainsKey('AllowedUsers')) {
        $AllowedUsers = $profileData['AllowedUsers']
    }
    if (-not $PSBoundParameters.ContainsKey('AllowedTenants') -and $profileData.ContainsKey('AllowedTenants')) {
        $AllowedTenants = $profileData['AllowedTenants']
    }
    if (-not $PSBoundParameters.ContainsKey('AllowedDomains') -and $profileData.ContainsKey('AllowedDomains')) {
        $AllowedDomains = @($profileData['AllowedDomains'])
    }
}

$deterministic = Get-DeterministicResourceNames -SubscriptionId $SubscriptionId -ResourceGroup $ResourceGroup
$computedRegistryUsed = $false
$computedVaultUsed = $false
$computedStorageUsed = $false

if (-not $Registry) { $Registry = $deterministic.Registry; $computedRegistryUsed = $true }
if (-not $Vault) { $Vault = $deterministic.Vault; $computedVaultUsed = $true }
if (-not $Storage) { $Storage = $deterministic.Storage; $computedStorageUsed = $true }

$registry = $Registry
$vault = $Vault
$storage = $Storage
$groupId = "/subscriptions/$SubscriptionId/resourceGroups/$ResourceGroup"
$registryId = "$groupId/providers/Microsoft.ContainerRegistry/registries/$registry"
$vaultId = "$groupId/providers/Microsoft.KeyVault/vaults/$vault"

if ($CustomDomain -and $DnsZone) {
    Test-CustomDomainDnsZone -CustomDomain $CustomDomain -DnsZone $DnsZone
}

if ($exists) {
    $rawReg = Invoke-AzJson @('acr', 'list', '--resource-group', $ResourceGroup)
    $existingRegNames = @()
    if ($rawReg) {
        foreach ($r in @($rawReg)) { if ($r -and $r.PSObject.Properties['name']) { $existingRegNames += [string]$r.name } }
    }
    $rawVaults = Invoke-AzJson @('keyvault', 'list', '--resource-group', $ResourceGroup)
    $existingVaultNames = @()
    if ($rawVaults) {
        foreach ($v in @($rawVaults)) { if ($v -and $v.PSObject.Properties['name']) { $existingVaultNames += [string]$v.name } }
    }
    $rawStorage = Invoke-AzJson @('storage', 'account', 'list', '--resource-group', $ResourceGroup)
    $existingStorageNames = @()
    if ($rawStorage) {
        foreach ($s in @($rawStorage)) { if ($s -and $s.PSObject.Properties['name']) { $existingStorageNames += [string]$s.name } }
    }
    if ($existingApp) {
        if ($computedRegistryUsed -and ($existingRegNames -notcontains $Registry)) {
            throw "Gateway exists in '$ResourceGroup', but container registry could not be resolved from live deployment and computed name '$Registry' does not exist in the resource group."
        }
        if ($computedVaultUsed -and ($existingVaultNames -notcontains $Vault)) {
            throw "Gateway exists in '$ResourceGroup', but key vault could not be resolved from live deployment and computed name '$Vault' does not exist in the resource group."
        }
        if ($computedStorageUsed -and ($existingStorageNames -notcontains $Storage)) {
            throw "Gateway exists in '$ResourceGroup', but storage account could not be resolved from live deployment and computed name '$Storage' does not exist in the resource group."
        }
    }

    if ($existingRegNames.Count -gt 0 -and ($existingRegNames -notcontains $Registry)) {
        throw "Found existing container registry '$($existingRegNames -join ',')' in '$ResourceGroup' differing from target '$Registry'. Refusing to create a second registry beside the live one."
    }
    if ($existingVaultNames.Count -gt 0 -and ($existingVaultNames -notcontains $Vault)) {
        throw "Found existing key vault '$($existingVaultNames -join ',')' in '$ResourceGroup' differing from target '$Vault'. Refusing to create a second key vault beside the live one."
    }
    if ($existingStorageNames.Count -gt 0 -and ($existingStorageNames -notcontains $Storage)) {
        throw "Found existing storage account '$($existingStorageNames -join ',')' in '$ResourceGroup' differing from target '$Storage'. Refusing to create a second storage account beside the live one."
    }
}

# Consumer Microsoft-account tenants are refused for AllowedTenants and AllowedDomains
$consumerTenants = Get-ConsumerTenantIds
$cleanTenants = [System.Collections.Generic.List[string]]::new()
if ($AllowedTenants) {
    foreach ($t in ($AllowedTenants -split ',')) {
        $raw = $t.Trim()
        if (-not $raw) { continue }
        $parsedGuid = [guid]::Empty
        if (-not [guid]::TryParse($raw, [ref]$parsedGuid)) {
            throw "AllowedTenants entry '$t' is not a valid GUID."
        }
        $cleanTenant = $parsedGuid.ToString('D').ToLowerInvariant()
        if ($cleanTenant -in $consumerTenants) {
            throw "Tenant '$t' is a consumer Microsoft-account tenant, which is refused."
        }
        if (-not $cleanTenants.Contains($cleanTenant)) {
            $cleanTenants.Add($cleanTenant)
        }
    }
}
$AllowedTenants = ($cleanTenants -join ',')

# Validate and resolve AllowedDomains before any Azure writes (H-9)
if ($AllowedDomains -and $AllowedDomains.Count -gt 0) {
    $AllowedTenants = Resolve-AllowedDomains -Domains $AllowedDomains -CurrentAllowedTenants $AllowedTenants
}
# Clean and strip empty entries from AllowedUsers (H-8)
$cleanUsers = [System.Collections.Generic.List[string]]::new()
if ($AllowedUsers) {
    foreach ($u in ($AllowedUsers -split ',')) {
        $clean = $u.Trim()
        if ($clean -and -not $cleanUsers.Contains($clean)) {
            $cleanUsers.Add($clean)
        }
    }
}
$AllowedUsers = ($cleanUsers -join ',')

# On a fresh deployment refuse to continue if users and tenants are both empty (H-8)
if (-not $existingApp) {
    if ([string]::IsNullOrWhiteSpace($AllowedUsers) -and [string]::IsNullOrWhiteSpace($AllowedTenants)) {
        throw 'Fresh deployment requires at least one allowed user, tenant, or domain. Refusing to deploy an orchestrator with empty allowlists.'
    }
}

# Image resolution (H-2)
$gatewayImage = $null
$sandboxImage = $null

if ($SkipImages -and $existingApp -and -not $PSBoundParameters.ContainsKey('ImageTag')) {
    $gatewayImage = [string]$existingApp.properties.template.containers[0].image
    $sandboxEnv = @($currentEnv | Where-Object name -eq 'HLS_SANDBOX_IMAGE')
    if ($sandboxEnv.Count -gt 0 -and $sandboxEnv[0].value) {
        $sandboxImage = [string]$sandboxEnv[0].value
    } else {
        $sandboxImage = "$registry.azurecr.io/hls-orchestrator-sandbox:latest"
    }
    if ($gatewayImage -match ':([^:]+)$') {
        $ImageTag = $Matches[1]
    }
} else {
    if (-not $ImageTag) {
        $ImageTag = & git -C $repoRoot rev-parse --short HEAD
        if ($LASTEXITCODE -ne 0) { throw 'Cannot resolve the HLS source commit.' }
    }
    if ($ImageTag -notmatch '^[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}$') { throw 'ImageTag is not a valid OCI tag.' }
    $gatewayImage = "$registry.azurecr.io/hls-gateway:$ImageTag"
    $sandboxImage = "$registry.azurecr.io/hls-orchestrator-sandbox:$ImageTag"
}

# WardFlow resolution (H-1)
if ($WardflowCommit -and $WardflowCommit -ne 'none' -and $WardflowCommit -notmatch '^[0-9a-f]{40}$') {
    throw 'WardflowCommit must be a full 40-character commit SHA or "none".'
}

$needsWardflow = $PublishWardflowBundle -or (-not $WardflowCommit -and -not $SkipImages)
if ($needsWardflow -and $WardflowPath) {
    $resolvedWardflowPath = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($WardflowPath)
    if (-not (Test-Path -LiteralPath $resolvedWardflowPath)) {
        throw "WardflowPath '$WardflowPath' was specified but the path does not exist."
    }
    $rev = (& git -C $resolvedWardflowPath rev-parse HEAD 2>$null)
    if ($LASTEXITCODE -ne 0 -or $rev -notmatch '^[0-9a-f]{40}$') {
        throw "WardflowPath '$WardflowPath' is not a git checkout."
    }
    if (-not $WardflowCommit) {
        $WardflowCommit = $rev.Trim()
    }
}

if (-not $WardflowCommit) {
    $WardflowCommit = 'none'
}
$wardflowCommit = $WardflowCommit
$wardflowBundleImage = "$registry.azurecr.io/hls-wardflow-bundle:$wardflowCommit"
if ($SkipInfra -and -not $existingApp) { throw '-SkipInfra requires an already bootstrapped hls-gateway.' }
if (-not $SkipInfra) {
    $null = Invoke-AzJson @('group', 'create', '--name', $ResourceGroup, '--location', $Location)
    $foundation = Deploy-Infrastructure $false
    $defaultFqdn = "hls-gateway.$($foundation.environmentDefaultDomain.value)"
} else { $defaultFqdn = $existingApp.properties.configuration.ingress.fqdn }

if ($BootstrapEntra) {
    $armClaims = Get-JwtClaims (Get-PinnedToken 'https://management.azure.com/')
    Ensure-Role $armClaims.oid 'Key Vault Secrets Officer' $vaultId 'User'
    $redirects = @("https://$defaultFqdn/auth/callback")
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

if ($PublishWardflowBundle) { Publish-WardflowBundle $wardflowCommit -SetGitHubVariable }
if (-not $SkipImages) {
    $bundleTags = @()
    try { $bundleTags = @(Invoke-AzJson @('acr', 'repository', 'show-tags', '--name', $registry, '--repository', 'hls-wardflow-bundle')) } catch { $bundleTags = @() }
    if ($bundleTags -notcontains $wardflowCommit) {
        if ($wardflowCommit -eq 'none') {
            Write-Host "WardFlow bundle 'none' missing in $registry; building empty bundle."
            Publish-WardflowBundle 'none'
        } else {
            throw "WardFlow bundle $wardflowCommit is not in $registry. Publish it from a machine with the wardflow checkout: ./hosted/Deploy-HostedOrchestrator.ps1 -PublishWardflowBundle -SkipInfra"
        }
    }
    $stage = Join-Path ([IO.Path]::GetTempPath()) "hls-build-$([Guid]::NewGuid().ToString('N'))"
    try {
        $null = New-Item -ItemType Directory -Path $stage
        $sourceTar = Join-Path $stage 'source.tar'
        # Archive one resolved SHA so the baked HLS_IMAGE_COMMIT (hotfix marker check) names exactly the shipped source.
        $sourceCommit = (& git -C $repoRoot rev-parse HEAD).Trim()
        if ($LASTEXITCODE -ne 0 -or $sourceCommit -notmatch '^[0-9a-f]{40}$') { throw 'Cannot resolve the full HLS source commit.' }
        Invoke-Native git @('-C', $repoRoot, 'archive', '--format=tar', "--output=$sourceTar", $sourceCommit)
        $context = Join-Path $stage 'context'
        $null = New-Item -ItemType Directory -Path $context
        Invoke-Native tar @('-xf', $sourceTar, '-C', $context)
        # ACR must use the sandbox-specific source allowlist, not the root emulator exclusions.
        Copy-Item -LiteralPath (Join-Path $context 'hosted/sandbox/Dockerfile.dockerignore') -Destination (Join-Path $context '.dockerignore') -Force
        Write-Host "Building committed HLS $ImageTag with WardFlow bundle $wardflowCommit (uncommitted changes are not shipped)."
        # Compile the pinned viewer once in ACR, not in the user's credential-bearing 4 GiB sandbox.
        $ohifTag = '9a2d2c3d1367-manifest-v1'
        $ohifImage = "$registry.azurecr.io/hls-ohif-static:$ohifTag"
        $repositories = @(Invoke-AzJson @('acr', 'repository', 'list', '--name', $registry))
        $ohifTags = @()
        if ($repositories -contains 'hls-ohif-static') {
            $ohifTags = @(Invoke-AzJson @('acr', 'repository', 'show-tags', '--name', $registry, '--repository', 'hls-ohif-static'))
        }
        if ($ohifTags -notcontains $ohifTag) {
            Invoke-AcrBuild (Join-Path $context 'hosted/sandbox') "hls-ohif-static:$ohifTag" 'ohif.Dockerfile'
        }
        Invoke-AcrBuild $context "hls-orchestrator-sandbox:$ImageTag" 'hosted/sandbox/Dockerfile' @('--build-arg', "WARDFLOW_BUNDLE_IMAGE=$wardflowBundleImage", '--build-arg', "OHIF_VIEWER_IMAGE=$ohifImage", '--build-arg', "HLS_IMAGE_COMMIT=$sourceCommit")
        Invoke-AcrBuild (Join-Path $context 'hosted/gateway') "hls-gateway:$ImageTag" 'Dockerfile'
    } finally { if (Test-Path -LiteralPath $stage) { Remove-Item -LiteralPath $stage -Recurse -Force } }
}

if ($SkipInfra) {
    $null = Invoke-AzJson @('containerapp', 'update', '--name', 'hls-gateway', '--resource-group', $ResourceGroup,
        '--image', $gatewayImage, '--set-env-vars', "HLS_SANDBOX_IMAGE=$sandboxImage")
    Wait-GatewayHealth $defaultFqdn 10 -CheckRevision
} else {
    $boundDomain = ''
    $boundCertificate = $false
    if ($existingApp -and $CustomDomain -and $existingApp.properties.configuration.ingress.PSObject.Properties['customDomains']) {
        $binding = @($existingApp.properties.configuration.ingress.customDomains | Where-Object { $_.name -eq $CustomDomain -and $_.bindingType -eq 'SniEnabled' })
        if ($binding.Count) { $boundDomain = $CustomDomain; $boundCertificate = $true }
    }
    $outputs = Deploy-Infrastructure $true $boundDomain $boundCertificate
    Wait-GatewayHealth $outputs.gatewayFqdn.value 10 -CheckRevision
    if ($CustomDomain -and $env:CLOUDFLARE_API_TOKEN) {
        if (-not $DnsZone) { throw 'DnsZone is required for automatic Cloudflare DNS configuration.' }
        Test-CustomDomainDnsZone -CustomDomain $CustomDomain -DnsZone $DnsZone
        $zones = Invoke-RestMethod -Uri "https://api.cloudflare.com/client/v4/zones?name=$([Uri]::EscapeDataString($DnsZone))" -Headers @{ Authorization = "Bearer $env:CLOUDFLARE_API_TOKEN" }
        if (-not $zones.success -or @($zones.result).Count -ne 1) { throw "Cloudflare token must have Zone:Read and DNS:Edit access to $DnsZone." }
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
