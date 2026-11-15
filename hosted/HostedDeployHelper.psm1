# Hosted Deployer Helper Module
# Provides domain validation, OpenID discovery resolution, profile loading, and deterministic naming.

function Test-AllowedDomain {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [string]$Domain
    )

    if ([string]::IsNullOrWhiteSpace($Domain)) {
        throw "Domain name cannot be empty."
    }

    $trimmed = $Domain.Trim()

    # Reject reserved meta-tenants before any network call
    if ($trimmed -in @('common', 'organizations', 'consumers')) {
        throw "Domain '$trimmed' is a reserved Entra meta-tenant and cannot be used as an allowed domain."
    }

    # Reject illegal characters: / ? # @ % : or whitespace
    if ($trimmed -match '[/?#@%:\s]') {
        throw "Domain '$trimmed' contains invalid characters (slashes, query, fragments, @, %, colons, or whitespace)."
    }

    # Total length cannot exceed 253 characters
    if ($trimmed.Length -gt 253) {
        throw "Domain '$trimmed' exceeds maximum DNS length of 253 characters."
    }

    $labels = $trimmed.Split('.')
    if ($labels.Count -lt 2) {
        throw "Domain '$trimmed' must have at least two labels (e.g. example.com)."
    }

    foreach ($label in $labels) {
        if ($label.Length -lt 1 -or $label.Length -gt 63) {
            throw "Domain '$trimmed' contains a label with invalid length ($($label.Length)). Labels must be between 1 and 63 characters."
        }
        if ($label -notmatch '^[a-zA-Z0-9]([a-zA-Z0-9-]*[a-zA-Z0-9])?$') {
            throw "Domain '$trimmed' contains an invalid label '$label'. Labels must contain only alphanumeric characters and hyphens, and cannot start or end with a hyphen."
        }
    }

    return $trimmed
}

function Resolve-AllowedDomain {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [string]$Domain,

        [Parameter(Mandatory = $false)]
        [Alias('HttpFetch')]
        [scriptblock]$HttpFetcher = $null
    )

    $validDomain = Test-AllowedDomain -Domain $Domain

    $url = "https://login.microsoftonline.com/$validDomain/v2.0/.well-known/openid-configuration"

    $config = $null
    try {
        if ($null -ne $HttpFetcher) {
            $config = & $HttpFetcher $url $validDomain
        } else {
            $config = Invoke-RestMethod -Uri $url -MaximumRedirection 0 -TimeoutSec 15
        }
    } catch {
        throw "Failed to resolve OpenID configuration for domain '$validDomain': $($_.Exception.Message)"
    }

    if ($null -eq $config) {
        throw "OpenID configuration for domain '$validDomain' returned no content."
    }

    $issuer = $null
    if ($config -is [System.Collections.IDictionary] -and $config.Contains('issuer')) {
        $issuer = [string]$config['issuer']
    } elseif ($config.PSObject -and $config.PSObject.Properties['issuer']) {
        $issuer = [string]$config.issuer
    }

    if ([string]::IsNullOrWhiteSpace($issuer)) {
        throw "OpenID configuration for domain '$validDomain' does not contain an 'issuer' claim."
    }

    # Issuer must match ^https://login\.microsoftonline\.com/<GUID>/v2\.0$
    $guidPattern = '^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$'
    if ($issuer -match '^https://login\.microsoftonline\.com/(?<tid>[^/]+)/v2\.0$') {
        $tid = $Matches['tid']
        if ($tid -notmatch $guidPattern) {
            throw "Domain '$validDomain' returned issuer '$issuer' with non-GUID tenant ID '$tid'."
        }
    } else {
        throw "Domain '$validDomain' returned issuer '$issuer' with an invalid host or endpoint format. Expected https://login.microsoftonline.com/<GUID>/v2.0."
    }

    $tenantId = $tid.ToLowerInvariant()

    # Refuse consumer Microsoft-account tenants
    if ($tenantId -in (Get-ConsumerTenantIds)) {
        throw "Domain '$validDomain' resolved to consumer Microsoft-account tenant '$tenantId', which is refused."
    }

    return $tenantId
}

function Resolve-AllowedDomains {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $false)]
        [object]$Domains,

        [Parameter(Mandatory = $false)]
        [string]$CurrentAllowedTenants = '',

        [Parameter(Mandatory = $false)]
        [scriptblock]$HttpFetcher = $null
    )

    $domainList = @()
    if ($null -ne $Domains) {
        if ($Domains -is [string]) {
            $domainList = @($Domains -split ',' | ForEach-Object { $_.Trim() } | Where-Object { $_ })
        } elseif ($Domains -is [System.Collections.IEnumerable]) {
            foreach ($item in $Domains) {
                if ($item -is [string]) {
                    $domainList += @($item -split ',' | ForEach-Object { $_.Trim() } | Where-Object { $_ })
                }
            }
        }
    }

    # Initialize ordered unique list of tenants
    $tenants = [System.Collections.Generic.List[string]]::new()
    if (-not [string]::IsNullOrWhiteSpace($CurrentAllowedTenants)) {
        foreach ($t in ($CurrentAllowedTenants -split ',')) {
            $clean = $t.Trim().ToLowerInvariant()
            if ($clean -and -not $tenants.Contains($clean)) {
                $tenants.Add($clean)
            }
        }
    }

    foreach ($d in $domainList) {
        $tid = Resolve-AllowedDomain -Domain $d -HttpFetcher $HttpFetcher
        Write-Host "Resolved domain $d -> tenant $tid"
        if (-not $tenants.Contains($tid)) {
            $tenants.Add($tid)
        }
    }

    return ($tenants -join ',')
}

function Get-ConsumerTenantIds {
    return @(
        '9188040d-6c67-4c5b-b112-36a304b66dad', # Personal Microsoft Accounts
        'f8cdef31-a31e-4b4a-93e4-5f571e91255a'  # Consumers / MSA
    )
}

$ConsumerTenantIds = Get-ConsumerTenantIds

function Import-DeploymentProfile {
    [CmdletBinding(DefaultParameterSetName = 'ByName')]
    param(
        [Parameter(Mandatory = $true, ParameterSetName = 'ByName', Position = 0)]
        [Alias('Name')]
        [string]$ProfileName,

        [Parameter(Mandatory = $false, ParameterSetName = 'ByName')]
        [string]$ProfilesDir = '',

        [Parameter(Mandatory = $true, ParameterSetName = 'ByPath')]
        [string]$Path
    )

    $profilePath = if ($PSCmdlet.ParameterSetName -eq 'ByPath') {
        $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($Path)
    } else {
        $isPath = [System.IO.Path]::IsPathRooted($ProfileName) -or
                  $ProfileName.Contains('/') -or
                  $ProfileName.Contains('\') -or
                  $ProfileName.StartsWith('~')
        if ($isPath) {
            $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($ProfileName)
        } else {
            if (-not $ProfilesDir) {
                $ProfilesDir = Join-Path $PSScriptRoot 'profiles'
            }
            $fileName = if ($ProfileName.EndsWith('.psd1', [StringComparison]::OrdinalIgnoreCase)) {
                $ProfileName
            } else {
                "$ProfileName.psd1"
            }
            Join-Path $ProfilesDir $fileName
        }
    }
    if (-not (Test-Path -LiteralPath $profilePath -PathType Leaf)) {
        throw "Deployment profile not found at '$profilePath'."
    }
    $data = Import-PowerShellDataFile -LiteralPath $profilePath

    $allowedKeys = @(
        'SubscriptionId',
        'TenantId',
        'ResourceGroup',
        'Location',
        'WardflowPath',
        'WardflowCommit',
        'CustomDomain',
        'DnsZone',
        'ClientId',
        'AllowedUsers',
        'AllowedTenants',
        'AllowedDomains',
        'GitHubRepo',
        'Registry',
        'Vault',
        'Storage'
    )

    foreach ($key in $data.Keys) {
        if ($key -notin $allowedKeys) {
            throw "Unknown key '$key' in deployment profile '$profilePath'."
        }
    }

    return $data
}

function Get-DeterministicResourceNames {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [string]$SubscriptionId,

        [Parameter(Mandatory = $true)]
        [string]$ResourceGroup
    )

    $subRg = "$SubscriptionId/$ResourceGroup".ToLowerInvariant()
    $bytes = [System.Text.Encoding]::UTF8.GetBytes($subRg)
    $sha = [System.Security.Cryptography.SHA256]::Create().ComputeHash($bytes)
    $hex = [System.BitConverter]::ToString($sha).Replace('-', '').ToLowerInvariant()
    $suffix = $hex.Substring(0, 8)

    return @{
        Registry = "acrhls$suffix"
        Vault    = "kv-hls-$suffix"
        Storage  = "sthls$suffix"
    }
}

function Test-CustomDomainDnsZone {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $false)]
        [string]$CustomDomain,

        [Parameter(Mandatory = $false)]
        [string]$DnsZone
    )

    if ($CustomDomain -and $DnsZone) {
        $trimmedDomain = $CustomDomain.Trim().TrimEnd('.')
        $trimmedZone = $DnsZone.Trim().TrimEnd('.')
        if (-not $trimmedDomain.EndsWith(".$trimmedZone", [StringComparison]::OrdinalIgnoreCase)) {
            throw "CustomDomain '$CustomDomain' must be a subdomain of DnsZone '$DnsZone'."
        }
    }
}

Export-ModuleMember -Function @(
    'Test-AllowedDomain',
    'Resolve-AllowedDomain',
    'Resolve-AllowedDomains',
    'Import-DeploymentProfile',
    'Get-DeterministicResourceNames',
    'Test-CustomDomainDnsZone',
    'Get-ConsumerTenantIds'
) -Variable @('ConsumerTenantIds')
