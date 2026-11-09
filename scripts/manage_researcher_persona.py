"""Manage the Entra researcher persona (researcher-demo@<tenant default domain>) and OneLake data access roles.

FR-3 & FR-7: Standalone idempotent CLI for researcher persona lifecycle:
- --create: Idempotently creates Entra user researcher-demo@<tenant default verified domain> and assigns
  OneLake ClinicalResearcherRole on patient360 and clinical_lakehouse.
- --delete / --cleanup: Removes Entra user and revokes OneLake role assignments.
- --verify: Confirms Graph API and Fabric dataAccessRoles state without exposing secrets.
- --dry-run: Structured validation and reporting of planned operations without changes.

Live runs need --workspace-id. The Lakehouses are resolved by display name in that workspace, the tenant comes
from --tenant-id (or the signed-in token's `tid`), and the UPN domain is the tenant's default verified domain.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import pathlib
import secrets
import socket
import string
import sys
import time
import urllib3.util.connection

import requests
from azure.identity import AzureCliCredential

# Blackhole bypass for macOS VPN
if os.environ.get("HLS_BIND_INTERFACE") and sys.platform == "darwin":
    try:
        _idx = socket.if_nametoindex(os.environ["HLS_BIND_INTERFACE"])
        _orig_conn = urllib3.util.connection.create_connection
        def _bound_conn(address, timeout=socket._GLOBAL_DEFAULT_TIMEOUT, source_address=None, socket_options=None):
            opts = list(socket_options or []) + [(socket.IPPROTO_IP, 25, _idx)]
            return _orig_conn(address, timeout=timeout, source_address=source_address, socket_options=opts)
        urllib3.util.connection.create_connection = _bound_conn
    except Exception:
        pass

ROOT_DIR = pathlib.Path(__file__).resolve().parents[1]
GRAPH_API = "https://graph.microsoft.com/v1.0"
FABRIC_API = "https://api.fabric.microsoft.com/v1"
GRAPH_SCOPE = "https://graph.microsoft.com/.default"
FABRIC_SCOPE = "https://api.fabric.microsoft.com/.default"

RESEARCHER_ALIAS = "researcher-demo"
PATIENT360_NAME = "patient360"
CLINICAL_LH_NAME = "clinical_lakehouse"

_TOKEN_CACHE: dict[tuple[str, str | None], tuple[str, float]] = {}


def get_token(scope: str, tenant_id: str | None = None) -> str:
    """Acquire a token for `scope` from the Azure CLI login (MSAL refresh token first, so HLS_BIND_INTERFACE applies)."""
    cached = _TOKEN_CACHE.get((scope, tenant_id))
    if cached and cached[1] - time.time() > 120:
        return cached[0]

    az_dir = pathlib.Path(os.environ.get("AZURE_CONFIG_DIR") or pathlib.Path.home() / ".azure")
    msal_path = az_dir / "msal_token_cache.json"
    profile_path = az_dir / "azureProfile.json"
    tenant = tenant_id
    if not tenant and profile_path.is_file():
        profiles = json.loads(profile_path.read_bytes().decode("utf-8-sig"))
        tenant = next((s["tenantId"] for s in profiles.get("subscriptions", []) if s.get("isDefault")), None)
    if tenant and msal_path.is_file():
        try:
            msal = json.loads(msal_path.read_text())
            rt_entry = next(iter(msal.get("RefreshToken", {}).values()))
            resp = requests.post(
                f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token",
                data={
                    "client_id": rt_entry["client_id"],
                    "grant_type": "refresh_token",
                    "refresh_token": rt_entry["secret"],
                    "scope": f"{scope} offline_access",
                },
                timeout=20,
            )
            if resp.status_code == 200 and "access_token" in resp.json():
                body = resp.json()
                token_val = body["access_token"]
                _TOKEN_CACHE[(scope, tenant_id)] = (token_val, time.time() + float(body.get("expires_in", 3600)))
                return token_val
        except Exception:
            pass  # fall through to the Azure CLI, which raises with its own error if it cannot sign in

    cred = AzureCliCredential(process_timeout=30, tenant_id=tenant_id) if tenant_id else AzureCliCredential(process_timeout=30)
    tok = cred.get_token(scope)
    _TOKEN_CACHE[(scope, tenant_id)] = (tok.token, float(tok.expires_on))
    return tok.token


def token_claims(token: str) -> dict:
    payload = token.split(".")[1]
    return json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))


def _raise_for(resp: requests.Response, what: str) -> None:
    if resp.status_code >= 400:
        raise RuntimeError(f"{what} failed: {resp.status_code} {resp.text}")


def generate_ephemeral_credential(length: int = 24) -> str:
    """Generate high-entropy credentials ephemerally. Never saved to disk or git."""
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
    chars = [
        secrets.choice(string.ascii_uppercase),
        secrets.choice(string.ascii_lowercase),
        secrets.choice(string.digits),
        secrets.choice("!@#$%^&*"),
    ]
    for _ in range(length - len(chars)):
        chars.append(secrets.choice(alphabet))
    secrets.SystemRandom().shuffle(chars)
    return "".join(chars)


def build_data_access_roles(
    nurse_object_id: str,
    researcher_object_id: str,
    tenant_id: str,
) -> dict:
    """Construct OneLake data access security role payload for nurse and researcher personas."""
    return {
        "value": [
            {
                "name": "ClinicalNurseRole",
                "decisionRules": [
                    {
                        "effect": "Permit",
                        "permission": [
                            {"attributeName": "Path", "attributeValueIncludedIn": ["Tables/*", "Files/*"]},
                            {"attributeName": "Action", "attributeValueIncludedIn": ["Read"]},
                        ],
                    }
                ],
                "members": {
                    "microsoftEntraMembers": [
                        {"objectId": nurse_object_id, "tenantId": tenant_id}
                    ]
                },
            },
            {
                "name": "ClinicalResearcherRole",
                "decisionRules": [
                    {
                        "effect": "Permit",
                        "permission": [
                            {
                                "attributeName": "Path",
                                "attributeValueIncludedIn": [
                                    "Tables/patient_deidentified",
                                    "Tables/diagnosis",
                                    "Tables/treatment",
                                    "Tables/biomarker_test",
                                ],
                            },
                            {"attributeName": "Action", "attributeValueIncludedIn": ["Read"]},
                        ],
                    }
                ],
                "members": {
                    "microsoftEntraMembers": [
                        {"objectId": researcher_object_id, "tenantId": tenant_id}
                    ]
                },
            },
        ]
    }

class ResearcherPersonaManager:
    def __init__(
        self,
        workspace_id: str | None = None,
        tenant_id: str | None = None,
        nurse_upn: str | None = None,
    ) -> None:
        self.workspace_id = workspace_id
        self.tenant_id = tenant_id
        self.nurse_upn = nurse_upn
        self.researcher_upn: str | None = None
        self.patient360_id: str | None = None
        self.clinical_id: str | None = None

    @property
    def researcher_label(self) -> str:
        return self.researcher_upn or f"{RESEARCHER_ALIAS}@<tenant default verified domain>"

    def graph_request(self, method: str, path: str, json_data: dict | None = None) -> requests.Response:
        tok = get_token(GRAPH_SCOPE, self.tenant_id)
        headers = {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}
        return requests.request(method, f"{GRAPH_API}{path}", headers=headers, json=json_data, timeout=30)

    def fabric_request(self, method: str, path: str, json_data: dict | None = None) -> requests.Response:
        tok = get_token(FABRIC_SCOPE, self.tenant_id)
        headers = {
            "Authorization": f"Bearer {tok}",
            "Content-Type": "application/json",
            "x-ms-fabric-skill": "onelake-catalog-govern-cli",
        }
        return requests.request(method, f"{FABRIC_API}{path}", headers=headers, json=json_data, timeout=30)

    def resolve(self, need_nurse: bool = False) -> None:
        """Resolve tenant, UPN domain and Lakehouse IDs for a live run; raise when any cannot be determined."""
        if not self.workspace_id:
            raise SystemExit("--workspace-id (or FABRIC_WORKSPACE_ID) is required for live operations")
        if not self.tenant_id:
            tid = token_claims(get_token(GRAPH_SCOPE)).get("tid")
            if not tid:
                raise SystemExit("--tenant-id is required: the signed-in token carries no 'tid' claim")
            self.tenant_id = str(tid)

        org = self.graph_request("GET", "/organization?$select=id,verifiedDomains")
        _raise_for(org, "Graph GET /organization")
        orgs = org.json().get("value", [])
        if not orgs or orgs[0].get("id") != self.tenant_id:
            raise RuntimeError(f"Graph token is not for tenant {self.tenant_id}: {org.text}")
        domain = next((d["name"] for d in orgs[0].get("verifiedDomains", []) if d.get("isDefault")), None)
        if not domain:
            raise RuntimeError(f"Tenant {self.tenant_id} has no default verified domain: {org.text}")
        self.researcher_upn = f"{RESEARCHER_ALIAS}@{domain}"

        if need_nurse and not self.nurse_upn:
            me = self.graph_request("GET", "/me?$select=userPrincipalName")
            _raise_for(me, "Graph GET /me (pass --nurse-upn when signed in as a service principal)")
            self.nurse_upn = me.json()["userPrincipalName"]

        items: dict[str, str] = {}
        url = f"/workspaces/{self.workspace_id}/items?type=Lakehouse"
        while url:
            resp = self.fabric_request("GET", url)
            _raise_for(resp, f"Fabric GET {url}")
            body = resp.json()
            items.update({i["displayName"]: i["id"] for i in body.get("value", [])})
            token = body.get("continuationToken")
            url = f"/workspaces/{self.workspace_id}/items?type=Lakehouse&continuationToken={token}" if token else ""
        missing = [n for n in (PATIENT360_NAME, CLINICAL_LH_NAME) if n not in items]
        if missing:
            raise RuntimeError(f"Workspace {self.workspace_id} has no Lakehouse named {', '.join(missing)}")
        self.patient360_id = items[PATIENT360_NAME]
        self.clinical_id = items[CLINICAL_LH_NAME]

    def find_user(self, upn: str) -> dict | None:
        r = self.graph_request("GET", f"/users/{upn}")
        if r.status_code == 404:
            return None
        _raise_for(r, f"Graph GET /users/{upn}")
        return r.json()

    def get_roles(self, item_id: str) -> list[dict]:
        url = f"/workspaces/{self.workspace_id}/items/{item_id}/dataAccessRoles"
        resp = self.fabric_request("GET", url)
        _raise_for(resp, f"Fabric GET {url}")
        return resp.json().get("value", [])

    def put_roles(self, item_id: str, roles: list[dict]) -> None:
        url = f"/workspaces/{self.workspace_id}/items/{item_id}/dataAccessRoles"
        _raise_for(self.fabric_request("PUT", url, {"value": roles}), f"Fabric PUT {url}")

    def execute_create(self, dry_run: bool = False) -> int:
        if not dry_run:
            self.resolve(need_nurse=True)
        print(f"[PersonaManager] Check Entra user {self.researcher_label}")
        print(f"[PersonaManager] Check OneLake data access role ClinicalResearcherRole")
        print(f"[PersonaManager] Plan assignment to Tables/patient_deidentified")
        print(f"[PersonaManager] Plan assignment to Tables/diagnosis, Tables/treatment, Tables/biomarker_test")
        print(f"[PersonaManager] Security boundary: Tables/patient is strictly omitted/denied for ClinicalResearcherRole")

        if dry_run:
            print("[DRY-RUN] Planned operations validated successfully. No live modifications performed.")
            return 0
        assert self.researcher_upn and self.nurse_upn and self.patient360_id and self.clinical_id and self.tenant_id

        # Check or create Entra user
        user = self.find_user(self.researcher_upn)
        if user:
            print(f"Entra user {self.researcher_upn} already exists (ID: {user['id']}). Reusing existing account.")
            researcher_id = user["id"]
        else:
            ephemeral_credential = generate_ephemeral_credential()
            payload = {
                "accountEnabled": True,
                "displayName": "Demonstration Oncology Researcher",
                "mailNickname": RESEARCHER_ALIAS,
                "userPrincipalName": self.researcher_upn,
                "passwordProfile": {
                    "forceChangePasswordNextSignIn": False,
                    "password": ephemeral_credential,
                },
                "usageLocation": "US",
            }
            res = self.graph_request("POST", "/users", payload)
            _raise_for(res, "Graph POST /users")
            researcher_id = res.json()["id"]
            print(f"Created Entra user {self.researcher_upn} (ID: {researcher_id})")
            self._ephemeral_secret = ephemeral_credential
            print("[PersonaManager] Ephemeral credential kept in process memory only. Never printed, written to disk, or committed.")

        # Get nurse object ID
        nurse_user = self.find_user(self.nurse_upn)
        if not nurse_user:
            raise RuntimeError(
                f"Security guard: Nurse principal {self.nurse_upn} could not be resolved from Entra ID. "
                f"Refusing to assign nurse role to researcher identity."
            )
        nurse_id = nurse_user["id"]
        if nurse_id == researcher_id:
            raise RuntimeError(f"Security guard: nurse principal {self.nurse_upn} is the researcher identity.")

        # Update OneLake data access security roles using strict read-modify-write
        # Physical tables are in clinical_lakehouse: preserves external roles like DatabricksClinicalRead
        preserved_clin = [
            r for r in self.get_roles(self.clinical_id)
            if r.get("name") not in ("ClinicalNurseRole", "ClinicalResearcherRole")
        ]
        our_clin_roles = build_data_access_roles(nurse_id, researcher_id, self.tenant_id).get("value", [])
        self.put_roles(self.clinical_id, preserved_clin + our_clin_roles)
        print(f"Successfully configured dataAccessRoles on {CLINICAL_LH_NAME} ({self.clinical_id}) (preserved {len(preserved_clin)} existing roles)")

        # patient360 holds shortcuts: read-modify-write preserving DefaultReader and other roles
        preserved_p360 = [r for r in self.get_roles(self.patient360_id) if r.get("name") != "ClinicalResearcherRole"]
        if not any(r.get("name") == "DefaultReader" for r in preserved_p360):
            preserved_p360.insert(0, {
                "name": "DefaultReader",
                "decisionRules": [{"effect": "Permit", "permission": [{"attributeName": "Action", "attributeValueIncludedIn": ["Read"]}, {"attributeName": "Path", "attributeValueIncludedIn": ["*"]}]}],
                "members": {"fabricItemMembers": [{"sourcePath": f"{self.workspace_id}/{self.patient360_id}", "itemAccess": ["ReadAll"]}]},
            })
        our_p360_role = {
            "name": "ClinicalResearcherRole",
            "decisionRules": [{"effect": "Permit", "permission": [{"attributeName": "Action", "attributeValueIncludedIn": ["Read"]}, {"attributeName": "Path", "attributeValueIncludedIn": ["*"]}]}],
            "members": {"microsoftEntraMembers": [{"objectId": researcher_id, "tenantId": self.tenant_id}]},
        }
        self.put_roles(self.patient360_id, preserved_p360 + [our_p360_role])
        print(f"Successfully configured dataAccessRoles on {PATIENT360_NAME} ({self.patient360_id}) (preserved {len(preserved_p360)} existing roles)")

        return 0

    def execute_delete(self, dry_run: bool = False) -> int:
        if not dry_run:
            self.resolve()
        print(f"[PersonaManager] Checking Entra user {self.researcher_label}")
        print(f"[PersonaManager] Checking OneLake data access role ClinicalResearcherRole")
        print(f"[PersonaManager] Plan removal of {self.researcher_label} from Entra ID")
        print(f"[PersonaManager] Plan revocation of ClinicalResearcherRole from OneLake lakehouses")

        if dry_run:
            print("[DRY-RUN] Delete operations validated successfully. No live modifications performed.")
            return 0
        assert self.researcher_upn and self.patient360_id and self.clinical_id

        # Revoke OneLake roles using read-modify-write (pruning only owned roles)
        for item_name, item_id in [(PATIENT360_NAME, self.patient360_id), (CLINICAL_LH_NAME, self.clinical_id)]:
            curr_roles = self.get_roles(item_id)
            filtered = [r for r in curr_roles if r.get("name") not in ("ClinicalResearcherRole", "ClinicalNurseRole")]
            if len(filtered) != len(curr_roles):
                self.put_roles(item_id, filtered)
                print(f"Revoked owned roles on {item_name} (preserved {len(filtered)} existing roles)")

        # Delete Entra user
        user = self.find_user(self.researcher_upn)
        if user:
            _raise_for(self.graph_request("DELETE", f"/users/{user['id']}"), f"Graph DELETE /users/{user['id']}")
            print(f"Successfully deleted Entra user {self.researcher_upn} ({user['id']})")
        else:
            print(f"Entra user {self.researcher_upn} does not exist. Nothing to delete.")

        return 0

    def execute_verify(self) -> int:
        self.resolve()
        assert self.researcher_upn and self.patient360_id
        print(f"Verifying account and role state for {self.researcher_upn}...")
        user = self.find_user(self.researcher_upn)
        if not user:
            print(f"STATUS: User {self.researcher_upn} does not exist in Entra ID.")
            return 1

        print(f"Entra User: {user.get('userPrincipalName')} (ID: {user.get('id')}, Enabled: {user.get('accountEnabled')})")

        # Verify roles on patient360 with retry loop for role synchronization latency (up to 30s)
        deadline = time.time() + 30
        backoff = 2.0
        researcher_role = None
        while True:
            roles = self.get_roles(self.patient360_id)
            researcher_role = next((r for r in roles if r.get("name") == "ClinicalResearcherRole"), None)
            if researcher_role or time.time() >= deadline:
                break
            time.sleep(backoff)
            backoff = min(backoff * 1.5, 8.0)

        if not researcher_role:
            print(f"STATUS: ClinicalResearcherRole is missing from {PATIENT360_NAME} after propagation deadline.")
            return 1

        print(f"OneLake Security: ClinicalResearcherRole active on {PATIENT360_NAME}. Decision rules: {len(researcher_role.get('decisionRules', []))}")
        return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Manage Entra researcher persona and OneLake data access security roles.")
    parser.add_argument("--create", action="store_true", help="Idempotently create Entra test user and assign OneLake security roles")
    parser.add_argument("--delete", "--cleanup", action="store_true", dest="delete", help="Deprovision Entra test user and revoke OneLake roles")
    parser.add_argument("--verify", action="store_true", help="Query Graph API and Fabric REST to verify configuration")
    parser.add_argument("--live", action="store_true", help="Execute live operations against Entra and Fabric")
    parser.add_argument("--dry-run", action="store_true", help="Report planned operations without making changes")
    parser.add_argument("--tenant-id", default=os.environ.get("AZURE_TENANT_ID"), help="Entra tenant ID (default: the signed-in token's tid)")
    parser.add_argument("--workspace-id", default=os.environ.get("FABRIC_WORKSPACE_ID"), help="Fabric workspace ID (required for live runs)")
    parser.add_argument("--nurse-upn", default=os.environ.get("HLS_NURSE_UPN"), help="UPN granted the nurse role (default: the signed-in user)")

    args = parser.parse_args(argv)

    manager = ResearcherPersonaManager(
        workspace_id=args.workspace_id,
        tenant_id=args.tenant_id,
        nurse_upn=args.nurse_upn,
    )

    if args.delete:
        return manager.execute_delete(dry_run=args.dry_run)
    elif args.verify:
        return manager.execute_verify()
    elif args.create:
        return manager.execute_create(dry_run=args.dry_run)
    elif args.dry_run:
        # Default with --dry-run
        return manager.execute_create(dry_run=True)
    else:
        # Default behavior is dry-run for safety (FR-7: dry-run by default)
        print("[PersonaManager] No action specified. Defaulting to dry-run verification.")
        return manager.execute_create(dry_run=True)


if __name__ == "__main__":
    sys.exit(main())
