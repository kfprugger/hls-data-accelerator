#!/usr/bin/env python3
"""Manage, publish, backup, and restore Fabric Data Agents (Patient 360).

Usage:
    python scripts/manage_patient360_agent.py --backup <path>
    python scripts/manage_patient360_agent.py --restore <path> [--dry-run]
    python scripts/manage_patient360_agent.py --apply
    python scripts/manage_patient360_agent.py --status
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import pathlib
import sys
import time
from typing import Any, Dict, List, Optional

import requests

ROOT = str(pathlib.Path(__file__).resolve().parent.parent)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from scripts.verify_data_agent_qa import FABRIC_API, get_delegated_token

SKILL_NAME = "fabric-data-agent-draft-testing"


class Patient360AgentManager:
    def __init__(
        self,
        workspace_name: str = "med-1103a",
        agent_name: str = "Patient 360",
        token: Optional[str] = None,
    ):
        self.workspace_name = workspace_name
        self.agent_name = agent_name
        self.token = token if token is not None else get_delegated_token()
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "x-ms-fabric-skill": SKILL_NAME,
            "Content-Type": "application/json",
        }
        self.workspace_id: Optional[str] = None
        self.agent_id: Optional[str] = None

    def resolve_workspace(self) -> str:
        if self.workspace_id:
            return self.workspace_id
        if len(self.workspace_name) == 36 and self.workspace_name.count("-") == 4:
            self.workspace_id = self.workspace_name
            return self.workspace_id
        r = requests.get(f"{FABRIC_API}/workspaces", headers=self.headers, timeout=30)
        r.raise_for_status()
        matched = next((w for w in r.json().get("value", []) if w.get("displayName") == self.workspace_name), None)
        if not matched:
            raise RuntimeError(f"Workspace '{self.workspace_name}' not found")
        self.workspace_id = matched["id"]
        return self.workspace_id

    def resolve_agent(self) -> Dict[str, Any]:
        ws_id = self.resolve_workspace()
        r = requests.get(f"{FABRIC_API}/workspaces/{ws_id}/items?type=DataAgent", headers=self.headers, timeout=30)
        r.raise_for_status()
        agents = r.json().get("value", [])
        matched = next((a for a in agents if a.get("displayName") == self.agent_name), None)
        if not matched:
            raise RuntimeError(f"Data Agent '{self.agent_name}' not found in workspace '{self.workspace_name}'")
        self.agent_id = matched["id"]
        return matched

    def get_definition(self) -> Dict[str, Any]:
        ws_id = self.resolve_workspace()
        agent = self.resolve_agent()
        agent_id = agent["id"]

        r = requests.post(f"{FABRIC_API}/workspaces/{ws_id}/items/{agent_id}/getDefinition", headers=self.headers, timeout=60)
        if r.status_code == 200:
            return r.json()
        if r.status_code != 202:
            raise RuntimeError(f"getDefinition returned {r.status_code}: {r.text}")

        loc = r.headers.get("Location")
        if not loc:
            raise RuntimeError("getDefinition returned 202 without Location header")

        for _ in range(60):
            time.sleep(2)
            poll = requests.get(loc, headers=self.headers, timeout=30)
            if poll.status_code != 200:
                continue
            pdata = poll.json()
            status = pdata.get("status")
            if status == "Succeeded":
                res = requests.get(f"{loc}/result", headers=self.headers, timeout=30)
                return res.json()
            if status in ("Failed", "Cancelled"):
                raise RuntimeError(f"getDefinition operation {status}: {pdata}")
        raise TimeoutError("getDefinition timed out after 120s")

    def backup(self, output_path: str) -> None:
        def_data = self.get_definition()
        p = pathlib.Path(output_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(def_data, f, indent=2)
        parts = def_data.get("definition", {}).get("parts", [])
        print(f"Backed up {len(parts)} definition parts to {output_path}")

    def update_definition(self, definition_parts: List[Dict[str, Any]]) -> None:
        ws_id = self.resolve_workspace()
        agent = self.resolve_agent()
        agent_id = agent["id"]

        payload = {"definition": {"parts": definition_parts}}
        r = requests.post(
            f"{FABRIC_API}/workspaces/{ws_id}/dataAgents/{agent_id}/updateDefinition",
            headers=self.headers,
            json=payload,
            timeout=60,
        )
        if r.status_code == 200:
            return
        if r.status_code != 202:
            raise RuntimeError(f"updateDefinition returned {r.status_code}: {r.text}")

        loc = r.headers.get("Location")
        if not loc:
            raise RuntimeError("updateDefinition returned 202 without Location header")

        for _ in range(60):
            time.sleep(2)
            poll = requests.get(loc, headers=self.headers, timeout=30)
            if poll.status_code != 200:
                continue
            pdata = poll.json()
            status = pdata.get("status")
            if status == "Succeeded":
                return
            if status in ("Failed", "Cancelled"):
                raise RuntimeError(f"updateDefinition operation {status}: {pdata}")
        raise TimeoutError("updateDefinition timed out after 120s")

    def select_schema_elements(
        self,
        silver_tables: List[str] = None,
        kql_tables: List[str] = None,
        kql_functions: List[str] = None,
    ) -> None:
        ws_id = self.resolve_workspace()
        agent = self.resolve_agent()
        agent_id = agent["id"]

        if silver_tables is None:
            silver_tables = [
                "Patient", "Condition", "Device", "Location", "Encounter",
                "Basic", "Observation", "MedicationRequest", "Procedure", "Immunization"
            ]
        if kql_tables is None:
            kql_tables = ["TelemetryRaw", "AlertHistory"]
        if kql_functions is None:
            kql_functions = [
                "agent_CurrentAlertSeverity", "agent_LowOxygen", "agent_TelemetrySevenDaySummary",
                "agent_CurrentDeviceSummary", "agent_ClinicalAggregateSummary"
            ]

        # Discover datasources on draft/staging
        r = requests.get(f"{FABRIC_API}/workspaces/{ws_id}/dataAgents/{agent_id}/staging/datasources", headers=self.headers, timeout=30)
        datasources = r.json().get("value", []) if r.status_code == 200 else []

        for ds in datasources:
            ds_id = ds.get("artifactId") or ds.get("id")
            ds_type = ds.get("type")
            elems_url = f"{FABRIC_API}/workspaces/{ws_id}/dataAgents/{agent_id}/staging/datasources/{ds_id}/elements"

            def traverse_and_select(root_id=""):
                q = f"?rootId={requests.utils.quote(root_id)}" if root_id else ""
                res = requests.get(f"{elems_url}{q}", headers=self.headers, timeout=30)
                if not res.ok:
                    return
                for item in res.json().get("value", []):
                    itype = item.get("type")
                    name = item.get("displayName")
                    iid = item.get("id")
                    cur_sel = bool(item.get("isSelected"))

                    if itype == "Table":
                        desired = (name in silver_tables) if ds_type == "lakehouse_tables" else (name in kql_tables)
                        if cur_sel != desired:
                            requests.patch(
                                f"{elems_url}?id={requests.utils.quote(iid)}",
                                headers=self.headers,
                                json={"isSelected": desired},
                                timeout=30,
                            )
                    elif itype in ("Function", "kusto.function"):
                        desired = name in kql_functions
                        if cur_sel != desired:
                            requests.patch(
                                f"{elems_url}?id={requests.utils.quote(iid)}",
                                headers=self.headers,
                                json={"isSelected": desired},
                                timeout=30,
                            )
                    elif itype in ("Schemas", "Schema", "Tables", "Functions", "table_grouping", "function_grouping") and item.get("hasSubElements"):
                        traverse_and_select(iid)

            traverse_and_select()

    def publish(self, description: str = "Patient 360 production configuration") -> None:
        ws_id = self.resolve_workspace()
        agent = self.resolve_agent()
        agent_id = agent["id"]

        r = requests.post(
            f"{FABRIC_API}/workspaces/{ws_id}/dataAgents/{agent_id}/staging/publish",
            headers=self.headers,
            json={"publishedDescription": description},
            timeout=60,
        )
        if not r.ok:
            raise RuntimeError(f"Publish failed ({r.status_code}): {r.text}")

    def restore(self, backup_path: str, dry_run: bool = False) -> None:
        p = pathlib.Path(backup_path)
        if not p.is_file():
            raise FileNotFoundError(f"Backup file not found: {backup_path}")
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)

        raw_parts = data.get("definition", {}).get("parts", [])
        if not raw_parts:
            raise ValueError(f"No definition parts found in backup file {backup_path}")

        print(f"Restore source: {backup_path}")
        print(f"Found {len(raw_parts)} parts:")
        for idx, part in enumerate(raw_parts, 1):
            path = part.get("path")
            ptype = part.get("payloadType")
            plen = len(part.get("payload", ""))
            print(f"  [{idx:2d}] {path} ({ptype}, {plen} bytes)")

        if dry_run:
            print(f"Dry-run: Would write {len(raw_parts)} definition parts to '{self.agent_name}'. Exiting 0.")
            return

        print(f"Applying definition parts to '{self.agent_name}'...")
        self.update_definition(raw_parts)
        print("Selecting schema elements...")
        self.select_schema_elements()
        print("Publishing restored configuration...")
        self.publish(description="Restored from backup: " + p.name)
        print("Restore completed successfully.")


def main() -> int:
    parser = argparse.ArgumentParser(description="Manage, publish, backup, and restore Fabric Data Agent (Patient 360)")
    parser.add_argument("--workspace", default=os.environ.get("FABRIC_WORKSPACE_NAME", "med-1103a"), help="Workspace name or ID")
    parser.add_argument("--agent-name", default="Patient 360", help="Data Agent display name")
    parser.add_argument("--backup", type=str, help="Path to write definition backup JSON")
    parser.add_argument("--restore", type=str, help="Path to read definition backup JSON from")
    parser.add_argument("--dry-run", action="store_true", help="Print actions without modifying live Fabric item")
    parser.add_argument("--apply", action="store_true", help="Deploy/update the fixed Patient 360 definition and publish")
    parser.add_argument("--status", action="store_true", help="Check status of Data Agent")

    args = parser.parse_args()

    try:
        manager = Patient360AgentManager(workspace_name=args.workspace, agent_name=args.agent_name)

        if args.backup:
            manager.backup(args.backup)
            return 0

        if args.restore:
            manager.restore(args.restore, dry_run=args.dry_run)
            return 0

        if args.apply:
            # Re-read and apply definition per deploy-data-agents.ps1
            # We can invoke pwsh deploy-data-agents.ps1 -Patient360Only
            # or apply definition parts directly.
            print(f"Applying fixed definition to '{args.agent_name}' in workspace '{args.workspace}'...")
            # Run the deployment script for Patient 360
            import subprocess
            cmd = [
                "pwsh", "-NoProfile", "phase-2/deploy-data-agents.ps1",
                "-FabricWorkspaceName", args.workspace,
                "-Patient360Only"
            ]
            env = dict(os.environ)
            env["HLS_FABRIC_TOKEN"] = manager.token
            p = subprocess.run(cmd, cwd=ROOT, env=env, capture_output=True, text=True)
            print(p.stdout)
            if p.returncode != 0:
                print(p.stderr, file=sys.stderr)
                return p.returncode
            print(f"✓ Fixed definition applied and published successfully for '{args.agent_name}'.")
            return 0

        if args.status:
            ag = manager.resolve_agent()
            print(f"Data Agent: {ag.get('displayName')} (ID: {ag.get('id')})")
            return 0

        parser.print_help()
        return 0

    except Exception as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
