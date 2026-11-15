from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
from dataclasses import replace
from pathlib import Path

import pytest

from hosted.gateway.lifecycle import AzureApps, registry_server_for
from hosted.gateway.policy import Settings

REPO_ROOT = Path(__file__).resolve().parents[2]
HOSTED_DIR = REPO_ROOT / "hosted"
HELPER_PSM1 = HOSTED_DIR / "HostedDeployHelper.psm1"
DEPLOY_PS1 = HOSTED_DIR / "Deploy-HostedOrchestrator.ps1"
PROFILES_DIR = HOSTED_DIR / "profiles"

_FAKE_HOME: tempfile.TemporaryDirectory | None = None


def get_hermetic_home() -> str:
    global _FAKE_HOME
    if _FAKE_HOME is None or not Path(_FAKE_HOME.name).exists():
        _FAKE_HOME = tempfile.TemporaryDirectory(prefix="hls-test-home-")
        home = Path(_FAKE_HOME.name)
        wf_dir = home / "git" / ".worktrees" / "wardflow-jb-dev"
        wf_dir.mkdir(parents=True, exist_ok=True)
        (wf_dir / "caldova-cardio").mkdir(parents=True, exist_ok=True)
        (wf_dir / "rayfin-wardflow-persona-app").mkdir(parents=True, exist_ok=True)
        try:
            subprocess.run(["git", "init", "-q", "-b", "main"], cwd=wf_dir, check=True)
            subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=wf_dir, check=True)
            subprocess.run(["git", "config", "user.name", "Test User"], cwd=wf_dir, check=True)
            (wf_dir / "marker.txt").write_text("wardflow")
            subprocess.run(["git", "add", "."], cwd=wf_dir, check=True)
            subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=wf_dir, check=True)
        except Exception:
            pass
    return _FAKE_HOME.name


def make_synthetic_profile_file() -> Path:
    fd, path_str = tempfile.mkstemp(suffix=".psd1", prefix="synth-profile-")
    os.close(fd)
    path = Path(path_str)
    path.write_text("""@{
    SubscriptionId = '11111111-2222-3333-4444-555555555555'
    TenantId       = '22222222-3333-4444-5555-666666666666'
    ResourceGroup  = 'rg-hls-deployer'
    Location       = 'westus2'
    CustomDomain   = 'hls.example.com'
    DnsZone        = 'example.com'
    AllowedDomains = @('example.com')
    AllowedUsers   = '22222222-3333-4444-5555-666666666666:admin@example.com'
    AllowedTenants = '22222222-3333-4444-5555-666666666666'
    GitHubRepo     = 'example-org/hls-data-accelerator'
    Storage        = 'sthlsdeployer'
    Registry       = 'acrhlsdeployer'
    Vault          = 'kv-hls-deployer'
}""", encoding="utf-8")
    return path

def get_clean_env() -> dict[str, str]:
    env = os.environ.copy()
    for k in [
        "CLOUDFLARE_API_TOKEN",
        "AZURE_CONFIG_DIR",
        "AZURE_SUBSCRIPTION_ID",
        "ARM_SUBSCRIPTION_ID",
        "GITHUB_TOKEN",
        "GH_TOKEN",
    ]:
        env.pop(k, None)
    env["HOME"] = get_hermetic_home()
    return env



def run_pwsh(script: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    """Execute pwsh command with HostedDeployHelper module imported."""
    full_script = f"""
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
Import-Module "{HELPER_PSM1}" -Force
{script}
"""
    result = subprocess.run(
        ["pwsh", "-NoProfile", "-NonInteractive", "-Command", full_script],
        capture_output=True,
        text=True,
        check=False,
        env=get_clean_env(),
    )
    if check and result.returncode != 0:
        raise RuntimeError(
            f"pwsh failed (exit {result.returncode}):\nSTDOUT: {result.stdout}\nSTDERR: {result.stderr}"
        )
    return result


def run_deploy_script(
    cli_args: list[str],
    *,
    sub_id: str = "11111111-2222-3333-4444-555555555555",
    tenant_id: str = "22222222-3333-4444-5555-666666666666",
    existing_app: dict | None = None,
    group_exists: bool | None = None,
    mock_acrs: list[dict] | None = None,
    mock_vaults: list[dict] | None = None,
    mock_storages: list[dict] | None = None,
    mock_domains: dict[str, str] | None = None,
    gh_vars: dict[str, str] | None = None,
    deploy_script_path: Path = DEPLOY_PS1,
) -> tuple[subprocess.CompletedProcess[str], dict | None]:
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tf:
        bicep_out_file = tf.name

    existing_app_ps = (
        f"$global:existingApp = ('{json.dumps(existing_app)}' | ConvertFrom-Json)"
        if existing_app
        else "$global:existingApp = $null"
    )
    group_exists_ps = (
        f"$global:groupExists = ${str(group_exists).lower()}"
        if group_exists is not None
        else "$global:groupExists = $null"
    )
    acrs_ps = (
        f"$global:mockAcrs = ('{json.dumps(mock_acrs)}' | ConvertFrom-Json)"
        if mock_acrs
        else "$global:mockAcrs = @()"
    )
    vaults_ps = (
        f"$global:mockVaults = ('{json.dumps(mock_vaults)}' | ConvertFrom-Json)"
        if mock_vaults
        else "$global:mockVaults = @()"
    )
    storages_ps = (
        f"$global:mockStorages = ('{json.dumps(mock_storages)}' | ConvertFrom-Json)"
        if mock_storages
        else "$global:mockStorages = @()"
    )
    domains_ps = (
        f"$global:mockDomains = ('{json.dumps(mock_domains)}' | ConvertFrom-Json -AsHashtable)"
        if mock_domains
        else "$global:mockDomains = @{}"
    )
    gh_vars_ps = (
        f"$global:ghVars = ('{json.dumps(gh_vars)}' | ConvertFrom-Json -AsHashtable)"
        if gh_vars
        else "$global:ghVars = @{}"
    )

    def format_cli_arg(arg: str) -> str:
        if arg.startswith("-") and " " not in arg and "," not in arg:
            return arg
        return "'" + arg.replace("'", "''") + "'"

    call_args = list(cli_args)
    temp_profile_to_clean: Path | None = None
    for i, a in enumerate(call_args):
        if a == "-DeploymentProfile" and i + 1 < len(call_args):
            if call_args[i + 1] == "jbatl":
                temp_profile_to_clean = make_synthetic_profile_file()
                call_args[i + 1] = str(temp_profile_to_clean)
    if "-SubscriptionId" not in call_args and "-DeploymentProfile" not in call_args:
        call_args.extend(["-SubscriptionId", sub_id, "-TenantId", tenant_id])
    args_str = " ".join(format_cli_arg(a) for a in call_args)

    pwsh_code = f"""
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$subId = '{sub_id}'
$tenantId = '{tenant_id}'
{existing_app_ps}
{group_exists_ps}
{acrs_ps}
{vaults_ps}
{storages_ps}
{domains_ps}
{gh_vars_ps}
$global:ghSetVars = @{{}}
$global:fedCredBody = $null

# The deploy script reads the HLS checkout through git. Stub those calls so tests
# never depend on, or change, the repository checkout. Other paths reach real git.
$global:stubRepoRoot = [System.IO.Path]::GetFullPath('{Path(deploy_script_path).resolve().parents[1]}').TrimEnd('/', '\\')
$global:realGit = (Get-Command git -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1)
function global:git {{
    if ($args.Count -ge 2 -and $args[0] -eq '-C' -and
        [System.IO.Path]::GetFullPath([string]$args[1]).TrimEnd('/', '\\') -eq $global:stubRepoRoot) {{
        $rest = @($args | Select-Object -Skip 2)
        $global:LASTEXITCODE = 0
        if ($rest[0] -eq 'config' -and $rest -contains 'remote.origin.url') {{
            return 'https://github.com/kfprugger/hls-data-accelerator.git'
        }}
        if ($rest[0] -eq 'rev-parse' -and $rest -contains '--short') {{ return 'abc1234' }}
        if ($rest[0] -eq 'rev-parse') {{ return ('a' * 40) }}
        throw "Unexpected git call against the HLS checkout in tests: git $($args -join ' ')"
    }}
    if (-not $global:realGit) {{ throw 'git is not installed.' }}
    & $global:realGit.Source @args
}}

function global:az {{
    $global:LASTEXITCODE = 0
    if ($args[0] -eq 'account' -and $args[1] -eq 'show') {{
        $currSub = if ($SubscriptionId) {{ $SubscriptionId }} else {{ $subId }}
        $currTen = if ($TenantId) {{ $TenantId }} else {{ $tenantId }}
        return (@{{ id = $currSub; tenantId = $currTen; user = @{{ type = 'user'; name = 'test-user' }} }} | ConvertTo-Json -Compress)
    }}
    if ($args[0] -eq 'account' -and $args[1] -eq 'get-access-token') {{
        $currTen = if ($TenantId) {{ $TenantId }} else {{ $tenantId }}
        $res = 'https://management.azure.com/'
        for ($i = 0; $i -lt $args.Count; $i++) {{
            if ($args[$i] -eq '--resource' -and $i + 1 -lt $args.Count) {{ $res = $args[$i + 1] }}
        }}
        $hdr = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes('{{"alg":"none"}}'))
        $pldObj = @{{ tid = $currTen; oid = '00000000-0000-0000-0000-000000000001'; aud = $res }}
        $pld = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes(($pldObj | ConvertTo-Json -Compress)))
        return (@{{ accessToken = "$hdr.$pld.sig" }} | ConvertTo-Json -Compress)
    }}
    if ($args[0] -eq 'role' -and $args[1] -eq 'assignment' -and $args[2] -eq 'create') {{
        return '{{}}'
    }}
    if ($args[0] -eq 'role' -and $args[1] -eq 'assignment' -and $args[2] -eq 'list') {{
        $sub = if ($SubscriptionId) {{ $SubscriptionId }} else {{ $subId }}
        return (@(@{{ roleDefinitionName = 'Owner'; scope = "/subscriptions/$sub"; condition = $null; principalId = '00000000-0000-0000-0000-000000000001' }}) | ConvertTo-Json -Compress)
    }}
    if ($args[0] -eq 'group' -and $args[1] -eq 'exists') {{
        if ($global:groupExists -ne $null) {{
            if ($global:groupExists) {{ return 'true' }} else {{ return 'false' }}
        }}
        if ($global:existingApp) {{ return 'true' }} else {{ return 'false' }}
    }}
    if ($args[0] -eq 'containerapp' -and $args[1] -eq 'list') {{
        if ($global:existingApp) {{ return (@($global:existingApp) | ConvertTo-Json -Compress -Depth 10) }}
        return '[]'
    }}
    if ($args[0] -eq 'acr' -and $args[1] -eq 'list') {{
        if ($global:mockAcrs) {{ return (@($global:mockAcrs) | ConvertTo-Json -Compress) }}
        return '[]'
    }}
    if ($args[0] -eq 'keyvault' -and $args[1] -eq 'list') {{
        if ($global:mockVaults) {{ return (@($global:mockVaults) | ConvertTo-Json -Compress) }}
        return '[]'
    }}
    if ($args[0] -eq 'storage' -and $args[1] -eq 'account' -and $args[2] -eq 'list') {{
        if ($global:mockStorages) {{ return (@($global:mockStorages) | ConvertTo-Json -Compress) }}
        return '[]'
    }}
    if ($args[0] -eq 'group' -and $args[1] -eq 'create') {{ return '{{}}' }}
    if ($args[0] -eq 'containerapp' -and $args[1] -eq 'show') {{
        return (@{{ properties = @{{ latestRevisionName = 'hls-gateway--rev1' }} }} | ConvertTo-Json -Compress)
    }}
    if ($args[0] -eq 'containerapp' -and $args[1] -eq 'revision' -and $args[2] -eq 'show') {{
        return (@{{ properties = @{{ runningState = 'Running'; healthState = 'Healthy' }} }} | ConvertTo-Json -Compress)
    }}
    if ($args[0] -eq 'containerapp' -and $args[1] -eq 'update') {{ return '{{}}' }}
    if ($args[0] -eq 'deployment' -and $args[1] -eq 'group' -and $args[2] -eq 'create') {{
        for ($i = 0; $i -lt $args.Count; $i++) {{
            if ($args[$i] -eq '--parameters' -and $i + 1 -lt $args.Count) {{
                $paramFile = $args[$i + 1].TrimStart('@')
                Copy-Item -LiteralPath $paramFile -Destination '{bicep_out_file}' -Force
            }}
        }}
        return (@{{ properties = @{{ outputs = @{{ environmentDefaultDomain = @{{ value = 'mock.azurecontainerapps.io' }}; gatewayFqdn = @{{ value = 'mock-gw.mock.azurecontainerapps.io' }}; customDomainVerificationId = @{{ value = 'mock-verify' }} }} }} }} | ConvertTo-Json -Compress -Depth 10)
    }}
    return '{{}}'
}}

function global:Invoke-RestMethod {{
    param([Parameter(ValueFromRemainingArguments)]$callArgs)
    $uri = ''
    $body = $null
    for ($i = 0; $i -lt $callArgs.Count; $i++) {{
        $argName = ([string]$callArgs[$i]).TrimEnd(':')
        if ($argName -eq '-Uri' -and $i + 1 -lt $callArgs.Count) {{ $uri = $callArgs[$i + 1] }}
        if ($argName -eq '-Body' -and $i + 1 -lt $callArgs.Count) {{ $body = $callArgs[$i + 1] }}
    }}
    if ($uri -like '*login.microsoftonline.com*') {{
        $tid = '72f988bf-86f1-41af-91ab-2d7cd011db47'
        if ($uri -match 'login\\.microsoftonline\\.com/([^/]+)/') {{
            $matchedDomain = $Matches[1]
            if ($global:mockDomains -and $global:mockDomains.ContainsKey($matchedDomain)) {{
                $tid = $global:mockDomains[$matchedDomain]
            }}
        }}
        return @{{ issuer = "https://login.microsoftonline.com/$tid/v2.0" }}
    }}

    if ($uri -like '*api.cloudflare.com/client/v4/zones*') {{
        if ($uri -like '*/dns_records*') {{
            return @{{ success = $true; result = @(@{{ id = 'dns-rec-1'; name = 'mock-name'; type = 'CNAME'; content = 'old.target' }}) }}
        }}
        return @{{ success = $true; result = @(@{{ id = 'mock-zone-id'; name = 'mock-zone' }}) }}
    }}

    if ($uri -like '*graph.microsoft.com*') {{
        if ($uri -like '*memberOf/microsoft.graph.directoryRole*') {{
            return [pscustomobject]@{{ value = @([pscustomobject]@{{ roleTemplateId = '62e90394-69f5-4237-9190-012177145e10' }}) }}
        }}
        if ($uri -like '*applications*federatedIdentityCredentials*') {{
            if ($body) {{
                $global:fedCredBody = ($body | ConvertFrom-Json)
            }}
            return @{{ value = @() }}
        }}
        if ($uri -like '*applications*addPassword*') {{
            return @{{ secretText = 'mock-generated-secret-val' }}
        }}
        if ($uri -like '*applications?*' -or $uri -like '*servicePrincipals?*') {{
            return @{{ value = @() }}
        }}
        if ($uri -like '*applications' -or $uri -like '*servicePrincipals') {{
            return @{{ id = 'mock-obj-id-123'; appId = '11111111-2222-3333-4444-555555555555'; displayName = 'mock-app' }}
        }}
        return @{{ value = @() }}
    }}

    if ($uri -like '*.vault.azure.net*') {{
        return @{{ value = 'mock-secret-val'; attributes = @{{ exp = 0; enabled = $true }} }}
    }}

    return @{{ success = $true; result = @() }}
}}

function global:Invoke-WebRequest {{
    return [pscustomobject]@{{ StatusCode = 200 }}
}}

function global:gh {{
    $global:LASTEXITCODE = 0
    if ($args[0] -eq 'api') {{
        if ($args[1] -like 'repos/*/actions/oidc/customization/sub') {{
            return (@{{ use_default = $true }} | ConvertTo-Json -Compress)
        }}
        if ($args[1] -like 'repos/*/actions/variables/*') {{
            $varName = $args[1].Split('/')[-1]
            if ($global:ghVars -and $global:ghVars.ContainsKey($varName)) {{
                return (@{{ value = $global:ghVars[$varName] }} | ConvertTo-Json -Compress)
            }}
            $global:LASTEXITCODE = 1
            return ''
        }}
        if ($args[1] -eq 'user') {{
            if ($args -contains '--jq') {{ return 'mock-user' }}
            return (@{{ login = 'mock-user'; id = 12345 }} | ConvertTo-Json -Compress)
        }}
        if ($args[1] -like 'repos/*') {{
            if ($args -contains '--jq') {{ return 'true' }}
            return (@{{ id = 12345; name = 'hls-data-accelerator'; full_name = 'kfprugger/hls-data-accelerator'; owner = @{{ id = 67890; login = 'kfprugger' }}; permissions = @{{ admin = $true }} }} | ConvertTo-Json -Compress)
        }}
    }}
    if ($args[0] -eq 'variable' -and $args[1] -eq 'get') {{
        $varName = $args[2]
        if ($global:ghVars -and $global:ghVars.ContainsKey($varName)) {{
            return $global:ghVars[$varName]
        }}
        $global:LASTEXITCODE = 1
        return ''
    }}
    if ($args[0] -eq 'variable' -and $args[1] -eq 'set') {{
        $varName = $args[2]
        $varBody = ''
        for ($i = 0; $i -lt $args.Count; $i++) {{
            if ($args[$i] -eq '--body' -and $i + 1 -lt $args.Count) {{ $varBody = $args[$i + 1] }}
        }}
        $global:ghSetVars[$varName] = $varBody
        return ''
    }}
    if ($args[0] -eq 'secret' -and $args[1] -eq 'set') {{
        return ''
    }}
    return ''
}}

& '{deploy_script_path}' {args_str}

$meta = @{{
    ghSetVars = $global:ghSetVars
    fedCredBody = $global:fedCredBody
}}
Write-Output "---DEPLOY_METADATA_JSON---"
Write-Output ($meta | ConvertTo-Json -Compress -Depth 10)
"""

    try:
        result = subprocess.run(
            ["pwsh", "-NoProfile", "-NonInteractive", "-Command", pwsh_code],
            capture_output=True,
            text=True,
            check=False,
            env=get_clean_env(),
        )
        metadata = {}
        if "---DEPLOY_METADATA_JSON---" in result.stdout:
            parts = result.stdout.split("---DEPLOY_METADATA_JSON---")
            try:
                metadata = json.loads(parts[1].strip().splitlines()[0])
            except Exception:
                pass
        result.metadata = metadata  # type: ignore[attr-defined]

        bicep_params = None
        p = Path(bicep_out_file)
        if p.exists() and p.stat().st_size > 0:
            with open(p) as f:
                bicep_params = json.load(f).get("parameters")
    finally:
        Path(bicep_out_file).unlink(missing_ok=True)
        if temp_profile_to_clean:
            temp_profile_to_clean.unlink(missing_ok=True)
    return result, bicep_params


class TestGatewayRegistryDerivation:
    def test_derives_registry_server_for_two_different_registries(self):
        reg1 = registry_server_for("acrhlsdeployer.azurecr.io/hls-orchestrator-sandbox:new")
        assert reg1 == "acrhlsdeployer.azurecr.io"
        reg2 = registry_server_for("customforkacr.azurecr.io/team/hls-sandbox:v2")
        assert reg2 == "customforkacr.azurecr.io"

    def test_derives_third_registry_host(self):
        reg = registry_server_for("ghcr.io/org/repo:tag")
        assert reg == "ghcr.io"

    def test_refuses_hostless_image(self):
        with pytest.raises(ValueError, match="sandbox_image has no registry server"):
            registry_server_for("hls-orchestrator-sandbox:latest")

    def test_azure_apps_spec_uses_derived_registry(self):
        settings_base = Settings(
            client_id="portal-client",
            client_secret="secret",
            session_key="x" * 32,
            public_base_url="https://hls.test",
            allowed_users=frozenset(),
            allowed_tenants=frozenset(),
            subscription_id="sub-123",
            resource_group="rg-test",
            environment_id="/subscriptions/sub-123/resourceGroups/rg-test/providers/Microsoft.App/managedEnvironments/cae-test",
            environment_domain="test.domain",
            sandbox_image="registryA.azurecr.io/sandbox:v1",
            sandbox_identity_id="/subscriptions/sub-123/resourceGroups/rg-test/providers/Microsoft.ManagedIdentity/userAssignedIdentities/id-test",
            storage_account="sttest",
            azure_client_id="id-client",
        )
        apps = object.__new__(AzureApps)
        apps.settings = settings_base
        apps.location = "westus2"

        spec1 = apps.spec({"app_name": "app1", "gateway_key": "k", "email": "a@b.com", "oid": "o1", "tid": "t1", "RowKey": "rk1"})
        assert spec1["properties"]["configuration"]["registries"] == [
            {"server": "registryA.azurecr.io", "identity": settings_base.sandbox_identity_id}
        ]

        apps2 = object.__new__(AzureApps)
        apps2.settings = replace(settings_base, sandbox_image="registryB.azurecr.io/other:tag")
        apps2.location = "westus2"
        spec2 = apps2.spec({"app_name": "app2", "gateway_key": "k", "email": "a@b.com", "oid": "o1", "tid": "t1", "RowKey": "rk2"})
        assert spec2["properties"]["configuration"]["registries"] == [
            {"server": "registryB.azurecr.io", "identity": settings_base.sandbox_identity_id}
        ]


class TestDomainValidation:
    @pytest.mark.parametrize("invalid_domain,expected_phrase", [
        ("common", "reserved entra meta-tenant"),
        ("organizations", "reserved entra meta-tenant"),
        ("consumers", "reserved entra meta-tenant"),
        ("example.com/path", "invalid characters"),
        ("example.com?query", "invalid characters"),
        ("example.com#frag", "invalid characters"),
        ("user@example.com", "invalid characters"),
        ("example.com:8080", "invalid characters"),
        ("example .com", "invalid characters"),
        ("singlelabel", "at least two labels"),
        (".leadingdot.com", "label with invalid length"),
        ("trailingdot.com.", "label with invalid length"),
        ("-leadinghyphen.com", "invalid label"),
        ("trailinghyphen-.com", "invalid label"),
        ("label..empty.com", "label with invalid length"),
        ("a" * 64 + ".com", "label with invalid length"),
        ("a" * 250 + ".com", "exceeds maximum dns length"),
    ])
    def test_invalid_domains_refused(self, invalid_domain: str, expected_phrase: str):
        script = f'Test-AllowedDomain -Domain "{invalid_domain}"'
        res = run_pwsh(script, check=False)
        assert res.returncode != 0
        combined = f"{res.stdout} {res.stderr}".lower()
        assert expected_phrase in combined

    @pytest.mark.parametrize("valid_domain", [
        ("example.com"),
        ("sub.domain.example.com"),
        ("EXAMPLE.COM"),
        ("example.org"),
        ("123domain.example"),
    ])
    def test_valid_domains_accepted(self, valid_domain: str):
        script = f'Test-AllowedDomain -Domain "{valid_domain}"'
        res = run_pwsh(script, check=True)
        assert res.stdout.strip() == valid_domain.strip()


class TestIssuerResolutionAndValidation:
    def test_valid_issuer_yields_guid(self):
        script = """
$mockFetch = {
    param($url, $domain)
    return @{ issuer = 'https://login.microsoftonline.com/72f988bf-86f1-41af-91ab-2d7cd011db47/v2.0' }
}
Resolve-AllowedDomain -Domain 'microsoft.com' -HttpFetcher $mockFetch
"""
        res = run_pwsh(script, check=True)
        assert res.stdout.strip() == "72f988bf-86f1-41af-91ab-2d7cd011db47"

    @pytest.mark.parametrize("consumer_guid", [
        "9188040d-6c67-4c5b-b112-36a304b66dad",
        "f8cdef31-a31e-4b4a-93e4-5f571e91255a",
    ])
    def test_consumer_tenant_issuer_refused(self, consumer_guid: str):
        script = f"""
$mockFetch = {{
    param($url, $domain)
    return @{{ issuer = "https://login.microsoftonline.com/{consumer_guid}/v2.0" }}
}}
Resolve-AllowedDomain -Domain 'live.com' -HttpFetcher $mockFetch
"""
        res = run_pwsh(script, check=False)
        assert res.returncode != 0
        combined = " ".join(f"{res.stdout} {res.stderr}".split())
        assert "consumer Microsoft-account tenant" in combined

    def test_foreign_issuer_host_refused(self):
        script = """
$mockFetch = {
    param($url, $domain)
    return @{ issuer = 'https://evil.example.org/72f988bf-86f1-41af-91ab-2d7cd011db47/v2.0' }
}
Resolve-AllowedDomain -Domain 'example.org' -HttpFetcher $mockFetch
"""
        res = run_pwsh(script, check=False)
        assert res.returncode != 0
        combined = " ".join(f"{res.stdout} {res.stderr}".split())
        assert "invalid host or endpoint format" in combined

    def test_non_guid_issuer_tenant_refused(self):
        script = """
$mockFetch = {
    param($url, $domain)
    return @{ issuer = 'https://login.microsoftonline.com/not-a-guid/v2.0' }
}
Resolve-AllowedDomain -Domain 'bad.com' -HttpFetcher $mockFetch
"""
        res = run_pwsh(script, check=False)
        assert res.returncode != 0
        combined = " ".join(f"{res.stdout} {res.stderr}".split())
        assert "non-GUID tenant ID" in combined


class TestDnsZoneValidation:
    def test_dns_zone_subdomain_mismatch_refused(self):
        script = 'Test-CustomDomainDnsZone -CustomDomain "hls.other.com" -DnsZone "example.com"'
        res = run_pwsh(script, check=False)
        assert res.returncode != 0
        combined = " ".join(f"{res.stdout} {res.stderr}".split()).lower()
        assert "must be a subdomain of dnszone" in combined

    def test_dns_zone_apex_refused(self):
        script = 'Test-CustomDomainDnsZone -CustomDomain "example.com" -DnsZone "example.com"'
        res = run_pwsh(script, check=False)
        assert res.returncode != 0
        combined = " ".join(f"{res.stdout} {res.stderr}".split()).lower()
        assert "must be a subdomain of dnszone" in combined

    def test_dns_zone_matching_subdomain_accepted(self):
        script = 'Test-CustomDomainDnsZone -CustomDomain "hls.example.com" -DnsZone "example.com"'
        res = run_pwsh(script, check=True)
        assert res.returncode == 0

class TestProfileLoadingAndPrecedence:
    def test_synthetic_profile_loads_and_contains_expected_keys(self, tmp_path: Path):
        prof = tmp_path / "custom.psd1"
        prof.write_text("""@{
    SubscriptionId = '11111111-2222-3333-4444-555555555555'
    TenantId       = '22222222-3333-4444-5555-666666666666'
    ResourceGroup  = 'rg-hls-deployer'
    Location       = 'westus2'
    CustomDomain   = 'hls.example.com'
    DnsZone        = 'example.com'
    AllowedDomains = @('example.com')
    AllowedUsers   = '22222222-3333-4444-5555-666666666666:admin@example.com'
    AllowedTenants = '22222222-3333-4444-5555-666666666666'
}""", encoding="utf-8")
        script = f"""
$p = Import-DeploymentProfile -Name 'custom' -ProfilesDir '{tmp_path}'
$p | ConvertTo-Json -Compress
"""
        res = run_pwsh(script, check=True)
        data = json.loads(res.stdout.strip())
        guid_re = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
        assert guid_re.match(data["SubscriptionId"])
        assert guid_re.match(data["TenantId"])
        assert data["ResourceGroup"] == "rg-hls-deployer"
        assert "CustomDomain" in data
        assert "DnsZone" in data
        assert "AllowedDomains" in data
        for u in data["AllowedUsers"].split(","):
            u = u.strip()
            parts = u.split(":")
            assert len(parts) == 2
            assert guid_re.match(parts[0])
            assert ("@" in parts[1]) or guid_re.match(parts[1])

    def test_deployment_profile_path_form_works(self, tmp_path: Path):
        prof = tmp_path / "external-profile.psd1"
        prof.write_text("""@{
    SubscriptionId = '11111111-2222-3333-4444-555555555555'
    TenantId       = '22222222-3333-4444-5555-666666666666'
    ResourceGroup  = 'rg-hls-deployer'
    Location       = 'westus2'
    CustomDomain   = 'hls.example.com'
    DnsZone        = 'example.com'
    AllowedDomains = @('example.com')
    AllowedUsers   = '22222222-3333-4444-5555-666666666666:admin@example.com'
    AllowedTenants = '22222222-3333-4444-5555-666666666666'
}""", encoding="utf-8")
        script = f"""
$p = Import-DeploymentProfile -Name '{prof}'
$p | ConvertTo-Json -Compress
"""
        res = run_pwsh(script, check=True)
        data = json.loads(res.stdout.strip())
        assert data["CustomDomain"] == "hls.example.com"
        assert data["SubscriptionId"] == "11111111-2222-3333-4444-555555555555"

    def test_example_profile_loads_cleanly(self):
        script = f"""
$p = Import-DeploymentProfile -Name 'example' -ProfilesDir '{PROFILES_DIR}'
$p | ConvertTo-Json -Compress
"""
        res = run_pwsh(script, check=True)
        data = json.loads(res.stdout.strip())
        assert isinstance(data, dict)
        assert len(data) == 0

    def test_unknown_profile_key_throws(self):
        script = """
$temp = New-TemporaryFile
Set-Content -Path $temp.FullName -Value "@{ ResourceGroup = 'rg-test'; InvalidUnknownKey = 'val' }"
try {
    Import-DeploymentProfile -Path $temp.FullName
} finally {
    Remove-Item -LiteralPath $temp.FullName -Force
}
"""
        res = run_pwsh(script, check=False)
        assert res.returncode != 0
        combined = " ".join(f"{res.stdout} {res.stderr}".split())
        assert "Unknown key 'InvalidUnknownKey'" in combined


    def test_bare_name_ignores_cwd_file_and_directory_and_loads_from_profiles_dir(self, tmp_path: Path):
        profiles_dir = tmp_path / "profiles"
        profiles_dir.mkdir()
        (profiles_dir / "op.psd1").write_text("@{ ResourceGroup = 'rg-from-profiles' }", encoding="utf-8")
        (profiles_dir / "prod.psd1").write_text("@{ ResourceGroup = 'rg-prod-from-profiles' }", encoding="utf-8")

        cwd_dir = tmp_path / "cwd"
        cwd_dir.mkdir()
        (cwd_dir / "op.psd1").write_text("@{ ResourceGroup = 'rg-from-cwd-shadow' }", encoding="utf-8")
        (cwd_dir / "prod").mkdir()
        (cwd_dir / "rel").mkdir()
        (cwd_dir / "rel" / "local.psd1").write_text("@{ ResourceGroup = 'rg-from-rel-path' }", encoding="utf-8")

        home_dir = Path(get_hermetic_home())
        (home_dir / "home-prof.psd1").write_text("@{ ResourceGroup = 'rg-from-tilde' }", encoding="utf-8")

        script = f"""
Push-Location -LiteralPath '{cwd_dir}'
try {{
    $p1 = Import-DeploymentProfile -Name 'op' -ProfilesDir '{profiles_dir}'
    $p2 = Import-DeploymentProfile -Name 'op.psd1' -ProfilesDir '{profiles_dir}'
    $p3 = Import-DeploymentProfile -Name 'prod' -ProfilesDir '{profiles_dir}'
    $p4 = Import-DeploymentProfile -Name './rel/local.psd1' -ProfilesDir '{profiles_dir}'
    $p5 = Import-DeploymentProfile -Name '~/home-prof.psd1' -ProfilesDir '{profiles_dir}'
    @{{
        p1 = $p1.ResourceGroup
        p2 = $p2.ResourceGroup
        p3 = $p3.ResourceGroup
        p4 = $p4.ResourceGroup
        p5 = $p5.ResourceGroup
    }} | ConvertTo-Json -Compress
}} finally {{
    Pop-Location
}}
"""
        res = run_pwsh(script, check=True)
        out = json.loads(res.stdout.strip())
        assert out["p1"] == "rg-from-profiles"
        assert out["p2"] == "rg-from-profiles"
        assert out["p3"] == "rg-prod-from-profiles"
        assert out["p4"] == "rg-from-rel-path"
        assert out["p5"] == "rg-from-tilde"
    def test_profile_precedence_parameter_beats_profile_beats_default(self):
        res, params = run_deploy_script(
            [
                "-DeploymentProfile", "jbatl",
                "-AllowedUsers", "11111111-2222-3333-4444-555555555555:explicit-user@example.com",
                "-SkipImages",
                "-ClientId", "11111111-2222-3333-4444-555555555555",
            ]
        )
        assert res.returncode == 0
        assert params is not None
        assert params["allowedUsers"]["value"] == "11111111-2222-3333-4444-555555555555:explicit-user@example.com"

    def test_profile_precedence_live_gateway_allowlist_beats_profile_when_unbound(self):
        existing_app = {
            "name": "hls-gateway",
            "properties": {
                "template": {
                    "containers": [
                        {
                            "image": "acrhlsdeployer.azurecr.io/hls-gateway:live",
                            "env": [
                                {"name": "HLS_CLIENT_ID", "value": "11111111-2222-3333-4444-555555555555"},
                                {"name": "HLS_ALLOWED_USERS", "value": "11111111-2222-3333-4444-555555555555:live-user-only@example.com"},
                                {"name": "HLS_ALLOWED_TENANTS", "value": "33333333-4444-5555-6666-777777777777"},
                            ],
                        }
                    ]
                },
                "configuration": {
                    "registries": [],
                    "ingress": {"customDomains": [], "fqdn": "hls-gateway.mock.azurecontainerapps.io"},
                },
            },
        }
        res, params = run_deploy_script(
            ["-DeploymentProfile", "jbatl", "-SkipImages"],
            existing_app=existing_app,
        )
        assert res.returncode == 0
        assert params is not None
        assert params["allowedUsers"]["value"] == "11111111-2222-3333-4444-555555555555:live-user-only@example.com"
        assert params["allowedTenants"]["value"] == "33333333-4444-5555-6666-777777777777"

    def test_redeploy_live_empty_string_env_var_beats_profile(self):
        # Shape 1: entry with value: ""
        existing_app = {
            "name": "hls-gateway",
            "properties": {
                "template": {
                    "containers": [
                        {
                            "image": "acrhlsdeployer.azurecr.io/hls-gateway:live",
                            "env": [
                                {"name": "HLS_CLIENT_ID", "value": "11111111-2222-3333-4444-555555555555"},
                                {"name": "HLS_ALLOWED_USERS", "value": ""},
                                {"name": "HLS_ALLOWED_TENANTS", "value": ""},
                            ],
                        }
                    ]
                },
                "configuration": {
                    "registries": [],
                    "ingress": {"customDomains": [], "fqdn": "hls-gateway.mock.azurecontainerapps.io"},
                },
            },
        }
        res, params = run_deploy_script(["-DeploymentProfile", "jbatl", "-SkipImages"], existing_app=existing_app)
        assert res.returncode == 0
        assert params is not None
        assert params["allowedUsers"]["value"] == ""
        assert params["allowedTenants"]["value"] == ""

    def test_redeploy_live_missing_value_prop_env_var_beats_profile(self):
        # Shape 2: entry without value property
        existing_app = {
            "name": "hls-gateway",
            "properties": {
                "template": {
                    "containers": [
                        {
                            "image": "acrhlsdeployer.azurecr.io/hls-gateway:live",
                            "env": [
                                {"name": "HLS_CLIENT_ID", "value": "11111111-2222-3333-4444-555555555555"},
                                {"name": "HLS_ALLOWED_USERS"},
                                {"name": "HLS_ALLOWED_TENANTS"},
                            ],
                        }
                    ]
                },
                "configuration": {
                    "registries": [],
                    "ingress": {"customDomains": [], "fqdn": "hls-gateway.mock.azurecontainerapps.io"},
                },
            },
        }
        res, params = run_deploy_script(["-DeploymentProfile", "jbatl", "-SkipImages"], existing_app=existing_app)
        assert res.returncode == 0
        assert params is not None
        assert params["allowedUsers"]["value"] == ""
        assert params["allowedTenants"]["value"] == ""

    def test_redeploy_live_no_env_entry_beats_profile(self):
        # Shape 3: no entry at all
        existing_app = {
            "name": "hls-gateway",
            "properties": {
                "template": {
                    "containers": [
                        {
                            "image": "acrhlsdeployer.azurecr.io/hls-gateway:live",
                            "env": [
                                {"name": "HLS_CLIENT_ID", "value": "11111111-2222-3333-4444-555555555555"},
                            ],
                        }
                    ]
                },
                "configuration": {
                    "registries": [],
                    "ingress": {"customDomains": [], "fqdn": "hls-gateway.mock.azurecontainerapps.io"},
                },
            },
        }
        res, params = run_deploy_script(["-DeploymentProfile", "jbatl", "-SkipImages"], existing_app=existing_app)
        assert res.returncode == 0
        assert params is not None
        assert params["allowedUsers"]["value"] == ""
        assert params["allowedTenants"]["value"] == ""


class TestFreshDeployAllowlistRefusal:
    def test_fresh_deploy_with_empty_allowlists_refused(self):
        res, _ = run_deploy_script(["-SkipImages", "-ClientId", "11111111-2222-3333-4444-555555555555"])
        assert res.returncode != 0
        combined = f"{res.stdout} {res.stderr}".lower()
        assert "fresh deployment requires at least one allowed user, tenant, or domain" in combined

    def test_allowed_domains_populates_allowed_tenants(self):
        res, params = run_deploy_script(
            [
                "-AllowedDomains", "microsoft.com",
                "-SkipImages",
                "-ClientId", "11111111-2222-3333-4444-555555555555",
            ]
        )
        assert res.returncode == 0
        assert params is not None
        assert params["allowedTenants"]["value"] == "72f988bf-86f1-41af-91ab-2d7cd011db47"

    @pytest.mark.parametrize("consumer_guid", [
        "9188040d-6c67-4c5b-b112-36a304b66dad",
        "9188040D-6C67-4C5B-B112-36A304B66DAD",
        "{9188040d-6c67-4c5b-b112-36a304b66dad}",
        "9188040d6c674c5bb11236a304b66dad",
        "f8cdef31-a31e-4b4a-93e4-5f571e91255a",
        "F8CDEF31-A31E-4B4A-93E4-5F571E91255A",
        "{f8cdef31-a31e-4b4a-93e4-5f571e91255a}",
        "f8cdef31a31e4b4a93e45f571e91255a",
    ])
    def test_allowed_tenants_refuses_consumer_tenant_guids(self, consumer_guid: str):
        res, params = run_deploy_script(
            [
                "-AllowedTenants", consumer_guid,
                "-SkipImages",
                "-ClientId", "11111111-2222-3333-4444-555555555555",
            ]
        )
        assert res.returncode != 0
        assert params is None
        combined = " ".join(f"{res.stdout} {res.stderr}".split()).lower()
        assert "consumer" in combined and "microsoft-account tenant" in combined
        assert "domain '" not in combined

    def test_allowed_tenants_refuses_non_guid_entry(self):
        res, params = run_deploy_script(
            [
                "-AllowedTenants", "not-a-valid-guid",
                "-SkipImages",
                "-ClientId", "11111111-2222-3333-4444-555555555555",
            ]
        )
        assert res.returncode != 0
        assert params is None
        combined = " ".join(f"{res.stdout} {res.stderr}".split())
        assert "not-a-valid-guid" in combined and "not a valid GUID" in combined

    def test_allowed_tenants_normalizes_braced_and_nodash_guids(self):
        res, params = run_deploy_script(
            [
                "-AllowedTenants", "{72F988BF-86F1-41AF-91AB-2D7CD011DB47},72f988bf86f141af91ab2d7cd011db47",
                "-SkipImages",
                "-ClientId", "11111111-2222-3333-4444-555555555555",
            ]
        )
        assert res.returncode == 0
        assert params is not None
        assert params["allowedTenants"]["value"] == "72f988bf-86f1-41af-91ab-2d7cd011db47"
class TestDeployScriptScenarios:
    def test_profile_reproduces_exact_live_allowlist_and_names(self):
        existing_app = {
            "name": "hls-gateway",
            "properties": {
                "template": {
                    "containers": [
                        {
                            "image": "acrhlsdeployer.azurecr.io/hls-gateway:live",
                            "env": [
                                {"name": "HLS_CLIENT_ID", "value": "11111111-2222-3333-4444-555555555555"},
                                {
                                    "name": "HLS_ALLOWED_USERS",
                                    "value": (
                                        "11111111-2222-3333-4444-555555555555:user1@example.com,"
                                        "22222222-3333-4444-5555-666666666666:user2@example.com"
                                    ),
                                },
                                {"name": "HLS_ALLOWED_TENANTS", "value": "72f988bf-86f1-41af-91ab-2d7cd011db47"},
                            ],
                        }
                    ]
                },
                "configuration": {
                    "registries": [{"server": "acrhlsdeployer.azurecr.io"}],
                    "secrets": [{"name": "sec1", "keyVaultUrl": "https://kv-mock.vault.azure.net/secrets/sec1"}],
                    "ingress": {
                        "customDomains": [{"name": "hls.example.com", "bindingType": "SniEnabled"}],
                        "fqdn": "hls-gateway.mock.azurecontainerapps.io",
                    },
                },
            },
        }
        res, params = run_deploy_script(
            ["-DeploymentProfile", "jbatl", "-SkipImages", "-ClientId", "11111111-2222-3333-4444-555555555555"],
            existing_app=existing_app,
        )
        assert res.returncode == 0
        assert params is not None
        assert params["allowedTenants"]["value"] == "72f988bf-86f1-41af-91ab-2d7cd011db47"
        assert params["allowedUsers"]["value"] == (
            "11111111-2222-3333-4444-555555555555:user1@example.com,"
            "22222222-3333-4444-5555-666666666666:user2@example.com"
        )
        assert params["registryName"]["value"] == "acrhlsdeployer"
        assert params["keyVaultName"]["value"] == "kv-hls-deployer"
        assert params["storageAccountName"]["value"] == "sthlsdeployer"
        assert params["customDomain"]["value"] == "hls.example.com"
        assert params["enableManagedCertificate"]["value"] is True

    def test_wardflow_path_check_only_when_bundle_or_images_needed(self):
        # 1. Nonexistent WardflowPath with -WardflowCommit none and -SkipImages does NOT throw
        res, params = run_deploy_script(
            [
                "-DeploymentProfile", "jbatl",
                "-WardflowPath", "/nonexistent/fake/wardflow/dir",
                "-WardflowCommit", "none",
                "-SkipImages",
                "-ClientId", "11111111-2222-3333-4444-555555555555",
            ]
        )
        assert res.returncode == 0
        assert params is not None

        # 2. Nonexistent WardflowPath with -PublishWardflowBundle DOES throw
        res2, _ = run_deploy_script(
            [
                "-DeploymentProfile", "jbatl",
                "-WardflowPath", "/nonexistent/fake/wardflow/dir",
                "-PublishWardflowBundle",
                "-SkipImages",
                "-ClientId", "11111111-2222-3333-4444-555555555555",
            ]
        )
        assert res2.returncode != 0
        combined2 = " ".join(f"{res2.stdout} {res2.stderr}".split())
        assert "was specified but the path" in combined2 and "does not exist" in combined2

    def test_publish_wardflow_bundle_none_preserves_existing_sha_in_github(self):

        res, _ = run_deploy_script(
            [
                "-WardflowCommit", "none",
                "-PublishWardflowBundle",
                "-SkipImages",
                "-ClientId", "11111111-2222-3333-4444-555555555555",
                "-AllowedUsers", "11111111-2222-3333-4444-555555555555:admin@example.com",
            ],
            gh_vars={"WARDFLOW_REF": "0123456789abcdef0123456789abcdef01234567"},
        )
        combined = f"{res.stdout} {res.stderr}"
        assert "preserving it and not replacing with 'none'" in combined
        # N-3 assertion: WARDFLOW_REF is not overwritten in GitHub
        gh_set = res.metadata.get("ghSetVars", {})  # type: ignore[attr-defined]
        assert "WARDFLOW_REF" not in gh_set

    def test_bootstrap_entra_federated_credential_canonical_repo_casing(self):
        res, _ = run_deploy_script(
            [
                "-BootstrapEntra",
                "-GitHubRepo", "KfPrugger/HLS-Data-Accelerator",
                "-SkipImages",
                "-ClientId", "11111111-2222-3333-4444-555555555555",
                "-AllowedUsers", "11111111-2222-3333-4444-555555555555:admin@example.com",
            ]
        )
        assert res.returncode == 0
        fed_body = res.metadata.get("fedCredBody")  # type: ignore[attr-defined]
        assert fed_body is not None
        assert fed_body.get("subject") == "repo:kfprugger/hls-data-accelerator:ref:refs/heads/main"

    def test_skip_images_without_tag_reuses_live_gateway_and_sandbox_images(self):
        existing_app = {
            "name": "hls-gateway",
            "properties": {
                "template": {
                    "containers": [
                        {
                            "image": "acrhlsdeployer.azurecr.io/hls-gateway:live-gw-tag-999",
                            "env": [
                                {"name": "HLS_CLIENT_ID", "value": "11111111-2222-3333-4444-555555555555"},
                                {"name": "HLS_ALLOWED_USERS", "value": "11111111-2222-3333-4444-555555555555:u1@example.com"},
                                {"name": "HLS_SANDBOX_IMAGE", "value": "acrhlsdeployer.azurecr.io/hls-orchestrator-sandbox:live-sbx-tag-888"},
                            ],
                        }
                    ]
                },
                "configuration": {
                    "registries": [],
                    "ingress": {"customDomains": [], "fqdn": "hls-gateway.mock.azurecontainerapps.io"},
                },
            },
        }
        res, params = run_deploy_script(["-DeploymentProfile", "jbatl", "-SkipImages"], existing_app=existing_app)
        assert res.returncode == 0
        assert params is not None
        assert params["gatewayImage"]["value"] == "acrhlsdeployer.azurecr.io/hls-gateway:live-gw-tag-999"
        assert params["sandboxImage"]["value"] == "acrhlsdeployer.azurecr.io/hls-orchestrator-sandbox:live-sbx-tag-888"

    def test_live_gateway_tenant_revocation_sticks(self):
        existing_app = {
            "name": "hls-gateway",
            "properties": {
                "template": {
                    "containers": [
                        {
                            "image": "acrhlsdeployer.azurecr.io/hls-gateway:live",
                            "env": [
                                {"name": "HLS_CLIENT_ID", "value": "11111111-2222-3333-4444-555555555555"},
                                {"name": "HLS_ALLOWED_USERS", "value": "11111111-2222-3333-4444-555555555555:u1@example.com"},
                                {"name": "HLS_ALLOWED_TENANTS", "value": ""},
                            ],
                        }
                    ]
                },
                "configuration": {
                    "registries": [],
                    "ingress": {"customDomains": [], "fqdn": "hls-gateway.mock.azurecontainerapps.io"},
                },
            },
        }
        res, params = run_deploy_script(["-DeploymentProfile", "jbatl", "-SkipImages"], existing_app=existing_app)
        assert res.returncode == 0
        assert params is not None
        assert params["allowedTenants"]["value"] == ""

    def test_live_gateway_user_revocation_sticks(self):
        existing_app = {
            "name": "hls-gateway",
            "properties": {
                "template": {
                    "containers": [
                        {
                            "image": "acrhlsdeployer.azurecr.io/hls-gateway:live",
                            "env": [
                                {"name": "HLS_CLIENT_ID", "value": "11111111-2222-3333-4444-555555555555"},
                                {"name": "HLS_ALLOWED_USERS", "value": ""},
                                {"name": "HLS_ALLOWED_TENANTS", "value": "72f988bf-86f1-41af-91ab-2d7cd011db47"},
                            ],
                        }
                    ]
                },
                "configuration": {
                    "registries": [],
                    "ingress": {"customDomains": [], "fqdn": "hls-gateway.mock.azurecontainerapps.io"},
                },
            },
        }
        res, params = run_deploy_script(["-DeploymentProfile", "jbatl", "-SkipImages"], existing_app=existing_app)
        assert res.returncode == 0
        assert params is not None
        assert params["allowedUsers"]["value"] == ""

    def test_existing_resources_different_names_throw_error_before_write(self):
        res, _ = run_deploy_script(
            ["-AllowedUsers", "11111111-2222-3333-4444-555555555555:test-u@example.com", "-SkipImages", "-ClientId", "11111111-2222-3333-4444-555555555555"],
            group_exists=True,
            existing_app=None,
            mock_acrs=[{"name": "differingacr"}],
        )
        assert res.returncode != 0
        combined = f"{res.stdout} {res.stderr}"
        assert "differingacr" in combined


class TestDeterministicResourceNames:
    def test_deterministic_names_validity(self):
        script = """
$res = Get-DeterministicResourceNames -SubscriptionId '11111111-2222-3333-4444-555555555555' -ResourceGroup 'rg-hls-deployer'
$res | ConvertTo-Json -Compress
"""
        res = run_pwsh(script, check=True)
        data = json.loads(res.stdout.strip())
        assert data["Registry"].startswith("acrhls")
        assert len(data["Registry"]) <= 50
        assert data["Vault"].startswith("kv-hls-")
        assert len(data["Vault"]) <= 24
        assert data["Storage"].startswith("sthls")
        assert len(data["Storage"]) <= 24


class TestInvokeAzJson:
    def test_invoke_az_json_throws_with_command_name_and_stderr(self):
        script = f"""
$SubscriptionId = '11111111-2222-3333-4444-555555555555'
$code = Get-Content -LiteralPath '{DEPLOY_PS1}' -Raw
$fnDef = [System.Text.RegularExpressions.Regex]::Match($code, '(?ms)function Invoke-AzJson\\b.*?^\\}}').Value
. ([scriptblock]::Create($fnDef))

$mockAz = [System.IO.Path]::GetTempFileName() + '.sh'
Set-Content -Path $mockAz -Value @'
#!/bin/sh
echo 'ERROR: AuthorizationFailed: The client does not have authorization.' >&2
exit 1
'@
chmod +x $mockAz
function global:az {{ & $mockAz @args }}
try {{
    Invoke-AzJson @('group', 'show', '--name', 'test-rg')
}} finally {{
    Remove-Item -LiteralPath $mockAz -Force -ErrorAction SilentlyContinue
}}
"""
        res = run_pwsh(script, check=False)
        assert res.returncode != 0
        combined = f"{res.stdout} {res.stderr}"
        assert "Azure CLI failed: group show --name" in combined
        assert "AuthorizationFailed" in combined

    def test_invoke_az_json_forwards_stderr_warning_and_parses_stdout(self):
        script = f"""
$SubscriptionId = '11111111-2222-3333-4444-555555555555'
$code = Get-Content -LiteralPath '{DEPLOY_PS1}' -Raw
$fnDef = [System.Text.RegularExpressions.Regex]::Match($code, '(?ms)function Invoke-AzJson\\b.*?^\\}}').Value
. ([scriptblock]::Create($fnDef))

$mockAz = [System.IO.Path]::GetTempFileName() + '.sh'
Set-Content -Path $mockAz -Value @'
#!/bin/sh
echo 'WARNING: CLI will deprecate something soon.' >&2
echo '{{"id":"mock-id","name":"mock-name"}}'
exit 0
'@
chmod +x $mockAz
function global:az {{ & $mockAz @args }}
try {{
    $res = Invoke-AzJson @('account', 'show')
    Write-Host "PARSED:$($res.id):$($res.name)"
}} finally {{
    Remove-Item -LiteralPath $mockAz -Force -ErrorAction SilentlyContinue
}}
"""
        res = run_pwsh(script, check=True)
        assert "PARSED:mock-id:mock-name" in res.stdout
        assert "WARNING: Azure CLI (account show): WARNING: CLI will deprecate something soon." in (res.stdout + res.stderr)
