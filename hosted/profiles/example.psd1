# Example deployment profile for forked HLS hosted orchestrators.
# Copy to <name>.psd1 and invoke Deploy-HostedOrchestrator.ps1 -DeploymentProfile <name>
@{
    # SubscriptionId = '<azure-subscription-guid>'
    # TenantId       = '<azure-tenant-guid>'
    # ResourceGroup  = 'rg-hls-deployer'
    # Location       = 'westus2'
    # GitHubRepo     = '<github-owner>/<github-repo>'
    # CustomDomain   = 'hls.example.com'
    # DnsZone        = 'example.com'
    # AllowedDomains = 'example.com'
    # AllowedUsers   = '<tenant-guid>:user@example.com'
    # AllowedTenants = '<tenant-guid>'
    # WardflowPath   = ''
    # Registry       = '' # Defaults to deterministic name: acrhls<hash>
    # Vault          = '' # Defaults to deterministic name: kv-hls-<hash>
    # Storage        = '' # Defaults to deterministic name: sthls<hash>
}
