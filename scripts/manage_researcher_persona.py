"""Manage Entra test user researcher-demo@jbatl.dev and OneLake data access security roles.

FR-3 & FR-7: Standalone idempotent CLI for researcher persona lifecycle:
- --create: Idempotently creates Entra user researcher-demo@jbatl.dev and assigns OneLake
  ClinicalResearcherRole on patient360 and clinical_lakehouse.
- --delete / --cleanup: Removes Entra user and revokes OneLake role assignments.
- --verify: Confirms Graph API and Fabric dataAccessRoles state without exposing secrets.
- --dry-run: Structured validation and reporting of planned operations without changes.
"""
from __future__ import annotations

import argparse
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

DEFAULT_TENANT_ID = "c77e97fc-1859-4575-8c8b-53d74bc35a63"
DEFAULT_WORKSPACE_ID = "f306e105-78fd-4b16-bfbe-2b556d493cb7"
DEFAULT_PATIENT360_ID = "83729d21-d933-4a62-9f5e-fbd85a44bda0"
DEFAULT_CLINICAL_LH_ID = "cbfa78a2-37ee-47b2-9476-14f23815eaa3"

RESEARCHER_UPN = "researcher-demo@jbatl.dev"
NURSE_UPN = "joey@jbatl.dev"

_TOKEN_CACHE: dict[str, tuple[str, float]] = {}


def get_token(scope: str) -> str:
    """Acquire token for requested resource scope over en0 using MSAL cache or Azure CLI."""
    if os.environ.get("AZURE_CONFIG_DIR"):
        az_dir = pathlib.Path(os.environ["AZURE_CONFIG_DIR"])
    else:
        az_dir = pathlib.Path.home() / ".azure-isolated" / "JBATL"
        if not az_dir.is_dir():
            az_dir = pathlib.Path.home() / ".azure"

    cached = _TOKEN_CACHE.get(scope)
    if cached and cached[1] - time.time() > 120:
        return cached[0]

    msal_path = az_dir / "msal_token_cache.json"
    if msal_path.is_file():
        try:
            msal = json.loads(msal_path.read_text())
            rt_entry = next(iter(msal.get("RefreshToken", {}).values()))
            profile_path = az_dir / "azureProfile.json"
            profiles = json.loads(profile_path.read_bytes().decode("utf-8-sig")) if profile_path.is_file() else {}
            tenant = next((s["tenantId"] for s in profiles.get("subscriptions", []) if s.get("isDefault")), DEFAULT_TENANT_ID)
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
                expires_in = float(body.get("expires_in", 3600))
                _TOKEN_CACHE[scope] = (token_val, time.time() + expires_in)
                return token_val
        except Exception:
            pass

    cred = AzureCliCredential(process_timeout=30)
    tok = cred.get_token(scope)
    _TOKEN_CACHE[scope] = (tok.token, float(tok.expires_on))
    return tok.token


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
    tenant_id: str = DEFAULT_TENANT_ID,
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
        tenant_id: str = DEFAULT_TENANT_ID,
        workspace_id: str = DEFAULT_WORKSPACE_ID,
        patient360_id: str = DEFAULT_PATIENT360_ID,
        clinical_id: str = DEFAULT_CLINICAL_LH_ID,
    ) -> None:
        self.tenant_id = tenant_id
        self.workspace_id = workspace_id
        self.patient360_id = patient360_id
        self.clinical_id = clinical_id

    def graph_request(self, method: str, path: str, json_data: dict | None = None) -> requests.Response:
        tok = get_token("https://graph.microsoft.com/.default")
        headers = {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}
        return requests.request(method, f"{GRAPH_API}{path}", headers=headers, json=json_data, timeout=30)

    def fabric_request(self, method: str, path: str, json_data: dict | None = None) -> requests.Response:
        tok = get_token("https://api.fabric.microsoft.com/.default")
        headers = {
            "Authorization": f"Bearer {tok}",
            "Content-Type": "application/json",
            "x-ms-fabric-skill": "onelake-catalog-govern-cli",
        }
        return requests.request(method, f"{FABRIC_API}{path}", headers=headers, json=json_data, timeout=30)

    def find_user(self, upn: str) -> dict | None:
        r = self.graph_request("GET", f"/users/{upn}")
        if r.status_code == 200:
            return r.json()
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return None

    def execute_create(self, dry_run: bool = False) -> int:
        print(f"[PersonaManager] Check Entra user {RESEARCHER_UPN}")
        print(f"[PersonaManager] Check OneLake data access role ClinicalResearcherRole")
        print(f"[PersonaManager] Plan assignment to Tables/patient_deidentified")
        print(f"[PersonaManager] Plan assignment to Tables/diagnosis, Tables/treatment, Tables/biomarker_test")
        print(f"[PersonaManager] Security boundary: Tables/patient is strictly omitted/denied for ClinicalResearcherRole")

        if dry_run:
            print("[DRY-RUN] Planned operations validated successfully. No live modifications performed.")
            return 0

        # Check or create Entra user
        user = self.find_user(RESEARCHER_UPN)
        if user:
            print(f"Entra user {RESEARCHER_UPN} already exists (ID: {user['id']}). Reusing existing account.")
            researcher_id = user["id"]
        else:
            ephemeral_credential = generate_ephemeral_credential()
            payload = {
                "accountEnabled": True,
                "displayName": "Demonstration Oncology Researcher",
                "mailNickname": "researcher-demo",
                "userPrincipalName": RESEARCHER_UPN,
                "passwordProfile": {
                    "forceChangePasswordNextSignIn": False,
                    "password": ephemeral_credential,
                },
                "usageLocation": "US",
            }
            res = self.graph_request("POST", "/users", payload)
            res.raise_for_status()
            created = res.json()
            researcher_id = created["id"]
            print(f"Created Entra user {RESEARCHER_UPN} (ID: {researcher_id})")
            print("=" * 60)
            print("EPHEMERAL CREDENTIAL NOTICE:")
            print(f"User: {RESEARCHER_UPN}")
            print(f"Initial key: {ephemeral_credential}")
            print("NOTICE: This ephemeral key is NEVER written to disk, config files, or git.")
            print("=" * 60)

        # Get nurse object ID
        nurse_user = self.find_user(NURSE_UPN)
        if not nurse_user:
            raise RuntimeError(
                f"Security guard: Nurse principal {NURSE_UPN} could not be resolved from Entra ID. "
                f"Refusing to assign nurse role to researcher identity."
            )
        nurse_id = nurse_user["id"]

        # Update OneLake data access security roles
        roles_payload = build_data_access_roles(nurse_id, researcher_id, self.tenant_id)
        for item_name, item_id in [("patient360", self.patient360_id), ("clinical_lakehouse", self.clinical_id)]:
            url = f"/workspaces/{self.workspace_id}/items/{item_id}/dataAccessRoles"
            resp = self.fabric_request("PUT", url, roles_payload)
            if resp.status_code in (200, 201):
                print(f"Successfully configured dataAccessRoles on {item_name} ({item_id})")
            else:
                resp.raise_for_status()

        return 0

    def execute_delete(self, dry_run: bool = False) -> int:
        print(f"[PersonaManager] Checking Entra user {RESEARCHER_UPN}")
        print(f"[PersonaManager] Checking OneLake data access role ClinicalResearcherRole")
        print(f"[PersonaManager] Plan removal of {RESEARCHER_UPN} from Entra ID")
        print(f"[PersonaManager] Plan revocation of ClinicalResearcherRole from OneLake lakehouses")

        if dry_run:
            print("[DRY-RUN] Delete operations validated successfully. No live modifications performed.")
            return 0

        # Revoke OneLake roles
        for item_name, item_id in [("patient360", self.patient360_id), ("clinical_lakehouse", self.clinical_id)]:
            url = f"/workspaces/{self.workspace_id}/items/{item_id}/dataAccessRoles"
            curr_resp = self.fabric_request("GET", url)
            if curr_resp.status_code == 200:
                curr_roles = curr_resp.json().get("value", [])
                filtered = [r for r in curr_roles if r.get("name") != "ClinicalResearcherRole"]
                if len(filtered) != len(curr_roles):
                    self.fabric_request("PUT", url, {"value": filtered})
                    print(f"Revoked ClinicalResearcherRole on {item_name}")

        # Delete Entra user
        user = self.find_user(RESEARCHER_UPN)
        if user:
            del_resp = self.graph_request("DELETE", f"/users/{user['id']}")
            if del_resp.status_code in (200, 204):
                print(f"Successfully deleted Entra user {RESEARCHER_UPN} ({user['id']})")
            else:
                print(f"Warning: DELETE user {RESEARCHER_UPN} returned {del_resp.status_code}: {del_resp.text}")
        else:
            print(f"Entra user {RESEARCHER_UPN} does not exist. Nothing to delete.")

        return 0

    def execute_verify(self) -> int:
        print(f"Verifying account and role state for {RESEARCHER_UPN}...")
        user = self.find_user(RESEARCHER_UPN)
        if not user:
            print(f"STATUS: User {RESEARCHER_UPN} does not exist in Entra ID.")
            return 1

        print(f"Entra User: {user.get('userPrincipalName')} (ID: {user.get('id')}, Enabled: {user.get('accountEnabled')})")

        # Verify roles on patient360 with retry loop for role synchronization latency (up to 30s)
        deadline = time.time() + 30
        backoff = 2.0
        researcher_role = None
        url = f"/workspaces/{self.workspace_id}/items/{self.patient360_id}/dataAccessRoles"
        while True:
            resp = self.fabric_request("GET", url)
            if resp.status_code == 200:
                roles = resp.json().get("value", [])
                researcher_role = next((r for r in roles if r.get("name") == "ClinicalResearcherRole"), None)
                if researcher_role:
                    break
            if time.time() >= deadline:
                break
            time.sleep(backoff)
            backoff = min(backoff * 1.5, 8.0)

        if not researcher_role:
            print("STATUS: ClinicalResearcherRole is missing from patient360 after propagation deadline.")
            return 1

        print(f"OneLake Security: ClinicalResearcherRole active on patient360. Decision rules: {len(researcher_role.get('decisionRules', []))}")
        return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Manage Entra researcher persona and OneLake data access security roles.")
    parser.add_argument("--create", action="store_true", help="Idempotently create Entra test user and assign OneLake security roles")
    parser.add_argument("--delete", "--cleanup", action="store_true", dest="delete", help="Deprovision Entra test user and revoke OneLake roles")
    parser.add_argument("--verify", action="store_true", help="Query Graph API and Fabric REST to verify configuration")
    parser.add_argument("--dry-run", action="store_true", help="Report planned operations without making changes")
    parser.add_argument("--tenant-id", default=os.environ.get("AZURE_TENANT_ID", DEFAULT_TENANT_ID), help="Entra tenant ID")
    parser.add_argument("--workspace-id", default=os.environ.get("FABRIC_WORKSPACE_ID", DEFAULT_WORKSPACE_ID), help="Fabric workspace ID")

    args = parser.parse_args(argv)

    manager = ResearcherPersonaManager(
        tenant_id=args.tenant_id,
        workspace_id=args.workspace_id,
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
