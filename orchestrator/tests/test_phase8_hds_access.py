from __future__ import annotations

import copy
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from typing import Any

from activities.deploy_cardiology_app import HDS_PARAMETERS
from activities.invoke_powershell import CARDIOLOGY_HDS_PARAMETERS, _build_deploy_args
from shared.deployment_validation import cardiology_hds_access_check
from shared.models import DeploymentConfig

REPO = Path(__file__).resolve().parents[2]
PHASE8_SCRIPT = REPO / "phase-8" / "deploy-cardiology-app.ps1"
DEPLOY_ALL = REPO / "Deploy-All.ps1"

FHIR_ID = "/subscriptions/00000000-0000-0000-0000-000000000001/resourceGroups/rg-hds/providers/Microsoft.HealthcareApis/workspaces/ws1/fhirservices/fhir1"
FHIR_URL = "https://ws1-fhir1.fhir.azurehealthcareapis.com"
WORKSPACE = "11111111-2222-3333-4444-555555555555"
SQL_HOST = "abc-def.datawarehouse.fabric.microsoft.com"
FHIR_DATA_CONTRIBUTOR = "5a1fc7df-4bf1-4951-a576-89034ee01acd"
EVENTHOUSE_URI = "https://trd-abc123.z9.kusto.fabric.microsoft.com"


def _pwsh(script: str, **env: str) -> subprocess.CompletedProcess:
    return subprocess.run(["pwsh", "-NoProfile", "-NonInteractive", "-Command", script], check=False, text=True,
                          capture_output=True, env={**os.environ, **env}, timeout=60)


def _result(proc: subprocess.CompletedProcess) -> Any:
    lines = [line for line in proc.stdout.splitlines() if line.startswith("RESULT:")]
    if proc.returncode != 0 or not lines:
        raise AssertionError(f"pwsh failed ({proc.returncode}): {proc.stderr or proc.stdout}")
    return json.loads(lines[-1][len("RESULT:"):])


class _Az:
    def __init__(self, stdout: Any = None, returncode: int = 0) -> None:
        self.stdout = "" if stdout is None else json.dumps(stdout)
        self.returncode = returncode
        self.stderr = ""


class HdsAccessValidationTests(unittest.TestCase):
    """Completion validation fails unless the app can reach its HDS data."""

    CONFIG = {
        "resource_group_name": "rg-test",
        "expected_subscription_id": "sub",
        "cardiology_fabric_workspace_id": WORKSPACE,
        "cardiology_fabric_sql_host": SQL_HOST,
        "cardiology_fabric_gold_database": "gold_db",
        "cardiology_fhir_service_id": FHIR_ID,
        "cardiology_fhir_url": FHIR_URL,
        "cardiology_eventhouse_query_uri": EVENTHOUSE_URI,
        "cardiology_eventhouse_database": "PulseOx",
    }
    GOOD = {
        "app": {
            "identities": {"/subscriptions/sub/.../cardioe2e-app-id": {"principalId": "pid", "clientId": "cid"}},
            "env": [
                {"name": "CALDOVA_PROFILE", "value": "live"},
                {"name": "AZURE_CLIENT_ID", "value": "cid"},
                {"name": "CALDOVA_FABRIC_SQL_HOST", "value": SQL_HOST},
                {"name": "CALDOVA_FABRIC_GOLD_DATABASE", "value": "gold_db"},
                {"name": "CALDOVA_FHIR_URL", "value": FHIR_URL},
                {"name": "CALDOVA_EVENTHOUSE_QUERY_URI", "value": EVENTHOUSE_URI},
                {"name": "CALDOVA_EVENTHOUSE_DATABASE", "value": "PulseOx"},
            ],
        },
        # The service returns the scope in its own casing.
        "fhir_scopes": [FHIR_ID.replace("resourceGroups", "resourcegroups")],
        "pages": [
            {"value": [{"principal": {"id": "someone"}, "role": "Admin"}], "continuationUri": "page-2"},
            {"value": [{"principal": {"id": "pid", "type": "ServicePrincipal"}, "role": "Viewer"}]},
        ],
    }

    def check(self, state: dict[str, Any]) -> dict[str, str]:
        pages = iter(state["pages"])

        def az_run(args: list[str]) -> _Az:
            if args[1:3] == ["containerapp", "list"]:
                return _Az([{"name": "cardioe2e-app", "fqdn": "cardio.example.test", "tags": {"hls-workload": "cardiology-app"}}])
            if args[1:3] == ["containerapp", "show"]:
                return _Az(state["app"])
            if args[1:4] == ["role", "assignment", "list"]:
                self.assertEqual(args[args.index("--scope") + 1], FHIR_ID)
                self.assertEqual(args[args.index("--assignee-object-id") + 1], "pid")
                self.assertEqual(args[args.index("--role") + 1], FHIR_DATA_CONTRIBUTOR)
                return _Az(state["fhir_scopes"])
            if args[1:4] == ["rest", "--method", "GET"]:
                if args[5] != "page-2":
                    self.assertEqual(args[5], f"https://api.fabric.microsoft.com/v1/workspaces/{WORKSPACE}/roleAssignments")
                return _Az(next(pages))
            raise AssertionError(f"unexpected az call {args}")

        return cardiology_hds_access_check(self.CONFIG, az_run)

    def variant(self, change) -> dict[str, Any]:
        state = copy.deepcopy(self.GOOD)
        change(state)
        return state

    def test_passes_only_with_both_grants_and_matching_settings(self) -> None:
        def env(state: dict[str, Any], name: str, value: str | None) -> None:
            state["app"]["env"] = [e for e in state["app"]["env"] if e["name"] != name]
            if value is not None:
                state["app"]["env"].append({"name": name, "value": value})

        cases = [
            ("exact access", self.GOOD, "pass"),
            ("no FHIR grant", self.variant(lambda s: s.update(fhir_scopes=[])), "fail"),
            ("FHIR grant on another service only", self.variant(lambda s: s.update(fhir_scopes=[FHIR_ID + "x"])), "fail"),
            ("no Fabric role", self.variant(lambda s: s["pages"][1].update(value=[])), "fail"),
            ("Fabric Contributor, not Viewer", self.variant(lambda s: s["pages"][1]["value"][0].update(role="Contributor")), "fail"),
            ("Fabric role for another principal", self.variant(lambda s: s["pages"][1]["value"][0]["principal"].update(id="other")), "fail"),
            ("AZURE_CLIENT_ID names another identity", self.variant(lambda s: env(s, "AZURE_CLIENT_ID", "other")), "fail"),
            ("FHIR URL missing", self.variant(lambda s: env(s, "CALDOVA_FHIR_URL", None)), "fail"),
            ("SQL host of another workspace", self.variant(lambda s: env(s, "CALDOVA_FABRIC_SQL_HOST", "x.datawarehouse.fabric.microsoft.com")), "fail"),
            ("gold database differs", self.variant(lambda s: env(s, "CALDOVA_FABRIC_GOLD_DATABASE", "silver")), "fail"),
            ("Eventhouse URI missing", self.variant(lambda s: env(s, "CALDOVA_EVENTHOUSE_QUERY_URI", None)), "fail"),
            ("Eventhouse database differs", self.variant(lambda s: env(s, "CALDOVA_EVENTHOUSE_DATABASE", "MasimoEventhouse")), "fail"),
            ("two identities", self.variant(lambda s: s["app"]["identities"].update(other={"principalId": "p2", "clientId": "c2"})), "fail"),
            ("no identity", self.variant(lambda s: s["app"].update(identities=None)), "fail"),
        ]
        for label, state, expected in cases:
            with self.subTest(label):
                result = self.check(state)
                self.assertEqual(result["status"], expected, result["detail"])


class HdsParameterPassThroughTests(unittest.TestCase):
    def test_orchestrator_defaults_reach_deploy_all(self) -> None:
        config = DeploymentConfig(fabric_workspace_name="med-test", tags={"env": "test"}).model_dump()
        command = _build_deploy_args(config)[4]
        for key, parameter in CARDIOLOGY_HDS_PARAMETERS.items():
            self.assertIn(f"-{parameter} '{config[key]}'", command)

    @unittest.skipIf(shutil.which("pwsh") is None, "PowerShell is required")
    def test_emitted_parameter_names_exist_on_the_scripts(self) -> None:
        probe = r'''
$names = @{}
foreach ($path in @($env:PHASE8, $env:DEPLOY_ALL)) {
    $tokens = $null; $errors = $null
    $ast = [System.Management.Automation.Language.Parser]::ParseFile($path, [ref]$tokens, [ref]$errors)
    if ($errors.Count) { throw "$path does not parse: $($errors[0].Message)" }
    $names[[IO.Path]::GetFileName($path)] = @($ast.ParamBlock.Parameters | ForEach-Object { $_.Name.VariablePath.UserPath })
}
"RESULT:" + ($names | ConvertTo-Json -Compress)
'''
        names = _result(_pwsh(probe, PHASE8=str(PHASE8_SCRIPT), DEPLOY_ALL=str(DEPLOY_ALL)))
        self.assertLessEqual(set(HDS_PARAMETERS.values()), set(names["deploy-cardiology-app.ps1"]))
        self.assertLessEqual(set(CARDIOLOGY_HDS_PARAMETERS.values()), set(names["Deploy-All.ps1"]))


# Runs the deployer's HDS-access statements (extracted from its AST, never the
# script itself) against a stubbed az that simulates FHIR RBAC and Fabric.
GRANT_HARNESS = r'''
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$tokens = $null; $errors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile($env:PHASE8, [ref]$tokens, [ref]$errors)
if ($errors.Count) { throw "parse: $($errors[0].Message)" }
$statements = @($ast.EndBlock.Statements)
$start = @(0..($statements.Count - 1) | Where-Object { $statements[$_].Extent.Text -like '$appIdentity = *' })[0]
$end = @($start..($statements.Count - 1) | Where-Object { $statements[$_].Extent.Text -eq 'Resolve-IdentityFacts' })[0]
$constants = @($statements | Where-Object { $_.Extent.Text -match '^\$(FhirDataContributor|FabricApi) = ' } | ForEach-Object { $_.Extent.Text })
$helpers = @('Get-Prop', 'Get-Output' | ForEach-Object { $name = $_; $ast.Find({ param($n) $n -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $n.Name -eq $name }, $true).Extent.Text })
$block = ($helpers + $constants + @($statements[$start..($end - 1)] | ForEach-Object { $_.Extent.Text })) -join "`n"

$state = $env:SCENARIO | ConvertFrom-Json
$ResourceGroupName = "rg-test"; $Prefix = "cardioe2e"; $RepoRoot = "/repo"; $Location = "eastus2"; $Tags = @{}
$FabricWorkspaceId = $env:WORKSPACE; $FhirServiceId = $env:FHIR_ID; $FhirUrl = $env:FHIR_URL
$calls = [System.Collections.Generic.List[string]]::new()
$bodies = [System.Collections.Generic.List[object]]::new()
function Start-Sleep { param($Seconds, $Milliseconds) }
function Invoke-Az {
    param ([Parameter(Mandatory)][string[]]$Arguments, [switch]$AllowFailure)
    $line = $Arguments -join " "
    $calls.Add($line)
    $bodyAt = [array]::IndexOf($Arguments, "--body")
    if ($bodyAt -ge 0) { $bodies.Add((Get-Content -Raw $Arguments[$bodyAt + 1].Substring(1) | ConvertFrom-Json)) }
    $out = $null
    switch -Wildcard ($line) {
        "identity show*" { $out = '{"id":"/subscriptions/s/resourceGroups/rg-test/providers/Microsoft.ManagedIdentity/userAssignedIdentities/cardioe2e-app-id","clientId":"cid","principalId":"pid"}' }
        "deployment group create*" { $out = '{"authContainerUri":{"type":"String","value":"https://st.blob.core.windows.net/auth-tokens"}}' }
        "resource show*" { $out = $state.audience }
        "role assignment list*" { $out = if ($state.fhirGranted) { ConvertTo-Json -InputObject @($FhirServiceId.Replace("resourceGroups", "resourcegroups")) } else { "[]" } }
        "role assignment create*" { $state.fhirGranted = $true; $out = "" }
        "rest --method GET*" {
            if ($line -notlike "*page=2*") {
                $out = @{ value = @(@{ principal = @{ id = "someone" }; role = "Admin" }); continuationUri = "$env:ROLES_URL`?page=2" } | ConvertTo-Json -Depth 5
            } else {
                $mine = @(if ($state.fabricRole) { @{ id = "ra-pid"; principal = @{ id = "pid"; type = "ServicePrincipal" }; role = $state.fabricRole } })
                $out = @{ value = $mine } | ConvertTo-Json -Depth 5
            }
        }
        "rest --method POST*" {
            if ($state.fabricError) { return [pscustomobject]@{ Code = 1; Out = ""; Err = "Forbidden($($state.fabricError))" } }
            $state.fabricRole = "Viewer"; $out = "{}"
        }
        "rest --method PATCH*" { $state.fabricRole = "Viewer"; $out = "{}" }
    }
    if ($null -eq $out) { throw "unexpected az call: $line" }
    return [pscustomobject]@{ Code = 0; Out = $out; Err = "" }
}
$failure = $null
try { . ([scriptblock]::Create($block)) 6>$null } catch { $failure = $_.Exception.Message }
"RESULT:" + (@{ calls = @($calls); bodies = @($bodies); error = $failure } | ConvertTo-Json -Depth 6 -Compress)
'''


@unittest.skipIf(shutil.which("pwsh") is None, "PowerShell is required")
class HdsGrantBehaviourTests(unittest.TestCase):
    ROLES_URL = f"https://api.fabric.microsoft.com/v1/workspaces/{WORKSPACE}/roleAssignments"

    def run_grants(self, **scenario: Any) -> dict[str, Any]:
        state = {"audience": FHIR_URL, "fhirGranted": False, "fabricRole": None, "fabricError": "", **scenario}
        return _result(_pwsh(GRANT_HARNESS, PHASE8=str(PHASE8_SCRIPT), SCENARIO=json.dumps(state), WORKSPACE=WORKSPACE,
                             FHIR_ID=FHIR_ID, FHIR_URL=FHIR_URL, ROLES_URL=self.ROLES_URL))

    @staticmethod
    def writes(result: dict[str, Any]) -> list[str]:
        return [c for c in result["calls"] if c.startswith(("role assignment create", "rest --method POST", "rest --method PATCH"))]

    def test_fresh_identity_gets_both_grants(self) -> None:
        result = self.run_grants()
        self.assertIsNone(result["error"])
        self.assertEqual(len(self.writes(result)), 2, result["calls"])
        create = self.writes(result)[0].split()
        self.assertEqual(create[create.index("--assignee-object-id") + 1], "pid")
        self.assertEqual(create[create.index("--assignee-principal-type") + 1], "ServicePrincipal")
        self.assertEqual(create[create.index("--role") + 1], FHIR_DATA_CONTRIBUTOR)
        self.assertEqual(create[create.index("--scope") + 1], FHIR_ID)
        self.assertTrue(self.writes(result)[1].startswith(f"rest --method POST --url {self.ROLES_URL} "))
        self.assertEqual(result["bodies"], [{"principal": {"id": "pid", "type": "ServicePrincipal"}, "role": "Viewer"}])
        # The durable state and token containers exist before the identity is granted HDS access.
        state = [i for i, c in enumerate(result["calls"]) if c.startswith("deployment group create") and "cardioe2e-state-bootstrap" in c]
        grants = [i for i, c in enumerate(result["calls"]) if c.startswith(("role assignment create", "rest --method POST"))]
        self.assertEqual(len(state), 1, result["calls"])
        self.assertLess(state[0], grants[0])

    def test_existing_grants_are_left_alone(self) -> None:
        result = self.run_grants(fhirGranted=True, fabricRole="Viewer")  # Viewer only on page two
        self.assertIsNone(result["error"])
        self.assertEqual(self.writes(result), [])

    def test_another_fabric_role_of_the_identity_becomes_viewer(self) -> None:
        result = self.run_grants(fhirGranted=True, fabricRole="Contributor")
        self.assertIsNone(result["error"])
        self.assertEqual([w.split()[4] for w in self.writes(result)], [f"{self.ROLES_URL}/ra-pid"])
        self.assertTrue(self.writes(result)[0].startswith("rest --method PATCH"))
        self.assertEqual(result["bodies"], [{"role": "Viewer"}])

    def test_fabric_refusal_fails_with_fabrics_reason(self) -> None:
        refusal = {"errorCode": "PrincipalTypeNotSupported", "message": "Service principals are not allowed by the tenant."}
        result = self.run_grants(fhirGranted=True, fabricError=json.dumps(refusal))
        self.assertIn("PrincipalTypeNotSupported: Service principals are not allowed by the tenant.", result["error"] or "")

    def test_mismatched_fhir_url_fails_before_any_grant(self) -> None:
        result = self.run_grants(audience="https://other-fhir.fhir.azurehealthcareapis.com")
        self.assertIn("not " + FHIR_URL, result["error"] or "")
        self.assertEqual(self.writes(result), [])
        self.assertFalse([c for c in result["calls"] if c.startswith(("role assignment", "rest"))])


DEPLOY_ALL_HARNESS = r'''
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$tokens = $null; $errors = $null
$phase8 = [System.Management.Automation.Language.Parser]::ParseFile($env:PHASE8, [ref]$tokens, [ref]$errors)
$all = [System.Management.Automation.Language.Parser]::ParseFile($env:DEPLOY_ALL, [ref]$tokens, [ref]$errors)
# A stand-in phase-8 script with the real parameter block that reports what it was given.
$ScriptDir = $env:STUB_DIR
New-Item -ItemType Directory -Force (Join-Path $ScriptDir "phase-8") | Out-Null
Set-Content (Join-Path $ScriptDir "phase-8/deploy-cardiology-app.ps1") ("[CmdletBinding()]`n" + $phase8.ParamBlock.Extent.Text + "`n" + '"RESULT:" + (@($PSBoundParameters.Keys | Sort-Object) + @("FhirUrl=$FhirUrl", "EventhouseQueryUri=$EventhouseQueryUri") | ConvertTo-Json -Compress)')
function Emit-PhaseTransition { param($Phase, $Label, $StepCount) }
function Invoke-Step { param($StepName, $Description, [scriptblock]$Action) & $Action }
function Assert-LastExternalCommandSucceeded { param($Name) }
$ResourceGroupName = "rg-test"; $Location = "eastus2"; $Tags = @{}
$ExpectedTenantId = "t"; $ExpectedSubscriptionId = "s"; $CardiologyAppPath = ""; $CardiologyAppUsers = @(); $CardiologyReviewerUsers = @()
$CardiologyFabricWorkspaceId = ""; $CardiologyFabricSqlHost = ""; $CardiologyFabricGoldDatabase = ""; $CardiologyFhirServiceId = ""
$CardiologyFhirUrl = $env:CARDIOLOGY_FHIR_URL
$CardiologyEventhouseQueryUri = $env:CARDIOLOGY_EVENTHOUSE_QUERY_URI; $CardiologyEventhouseDatabase = ""
. ([scriptblock]::Create($all.Find({ param($n) $n -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $n.Name -eq 'Invoke-CardiologyAppPhase' }, $true).Extent.Text))
Invoke-CardiologyAppPhase
'''


@unittest.skipIf(shutil.which("pwsh") is None, "PowerShell is required")
class DeployAllForwardingTests(unittest.TestCase):
    def run_phase(self, fhir_url: str, eventhouse_uri: str = "") -> subprocess.CompletedProcess:
        with tempfile.TemporaryDirectory() as stub_dir:
            return _pwsh(DEPLOY_ALL_HARNESS, PHASE8=str(PHASE8_SCRIPT), DEPLOY_ALL=str(DEPLOY_ALL), STUB_DIR=stub_dir,
                         CARDIOLOGY_FHIR_URL=fhir_url, CARDIOLOGY_EVENTHOUSE_QUERY_URI=eventhouse_uri)

    def bound(self, fhir_url: str, eventhouse_uri: str = "") -> list[str]:
        return _result(self.run_phase(fhir_url, eventhouse_uri))

    def test_set_values_override_and_empty_values_keep_the_phase8_defaults(self) -> None:
        overridden = self.bound(FHIR_URL, EVENTHOUSE_URI)
        self.assertIn("FhirUrl", overridden)
        self.assertIn(f"FhirUrl={FHIR_URL}", overridden)
        self.assertIn(f"EventhouseQueryUri={EVENTHOUSE_URI}", overridden)
        defaulted = self.bound("")
        self.assertNotIn("FhirUrl", defaulted)
        self.assertNotIn("FabricWorkspaceId", defaulted)
        self.assertNotIn("EventhouseQueryUri", defaulted)
        self.assertNotIn(f"FhirUrl={FHIR_URL}", defaulted)
        self.assertIn("EventhouseQueryUri=https://trd-0vj4c1a07qab5cxg8f.z0.kusto.fabric.microsoft.com", defaulted)

    def test_eventhouse_uri_outside_fabric_kusto_is_rejected(self) -> None:
        for uri in ["http://trd-abc123.z9.kusto.fabric.microsoft.com", "https://evil.example.com",
                    "https://trd-abc123.kusto.windows.net", "https://trd.z9.kusto.fabric.microsoft.com.evil.com"]:
            with self.subTest(uri):
                proc = self.run_phase(FHIR_URL, uri)
                self.assertNotEqual(proc.returncode, 0)
                self.assertIn("EventhouseQueryUri", proc.stderr + proc.stdout)


if __name__ == "__main__":
    unittest.main()
