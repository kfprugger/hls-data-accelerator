"""Apply generated synthetic demo inputs before FHIR export or HDS POA ingestion.

No generated data is stored in the repository. Azure CLI authentication always
uses the explicitly supplied subscription and inherits AZURE_CONFIG_DIR.
"""
from __future__ import annotations

import argparse
import base64
from collections import Counter
from datetime import date, datetime, timezone
import json
import subprocess
import sys
import time
from urllib.error import HTTPError
from urllib.parse import urljoin, urlsplit
from urllib.request import Request, urlopen

from enrich_demo_cohort import build_resources, transaction_bundles
from outreach_demo_sources import build_outreach_sources

FABRIC = "https://api.fabric.microsoft.com"
NOTEBOOK_NAME = "Seed_Outreach_Demo_Sources"


def azure_json(subscription: str, *arguments: str):
    result = subprocess.run(
        ["az", *arguments, "--subscription", subscription, "-o", "json"],
        capture_output=True, text=True, shell=sys.platform == "win32", check=False,
    )
    if result.returncode:
        raise RuntimeError(f"Azure CLI {arguments[0]} failed: {result.stderr.strip()}")
    return json.loads(result.stdout)


class Client:
    def __init__(self, base: str, subscription: str):
        self.base = base.rstrip("/")
        self.subscription = subscription
        self._token = ""
        self._expires = 0.0

    def request(self, method: str, url: str, body=None):
        url = urljoin(self.base + "/", url)
        parsed = urlsplit(url)
        # Fabric LRO/Job Location headers can use a regional WABI host. Poll the
        # same v1 path through the public API, keeping credentials on that origin.
        if (self.base == FABRIC and parsed.scheme == "https" and parsed.hostname
                and parsed.hostname.endswith(".analysis.windows.net") and parsed.path.startswith("/v1/")):
            url = FABRIC + parsed.path + ("?" + parsed.query if parsed.query else "")
        if urlsplit(url)[:2] != urlsplit(self.base)[:2]:
            raise RuntimeError("Refusing to send credentials to a different API origin")
        if time.time() >= self._expires - 300:
            token = azure_json(self.subscription, "account", "get-access-token", "--resource", self.base)
            self._token = token["accessToken"]
            self._expires = float(token.get("expires_on") or time.time() + 1800)
        headers = {"Authorization": f"Bearer {self._token}", "Content-Type": "application/json"}
        if self.base == FABRIC:
            headers["x-ms-fabric-skill"] = "spark-cli"
        else:
            headers["Accept"] = "application/fhir+json"
        request = Request(url, data=json.dumps(body).encode() if body is not None else None,
                          headers=headers, method=method)
        try:
            with urlopen(request, timeout=120) as response:
                raw = response.read()
                return response.status, response.headers, json.loads(raw) if raw else {}
        except HTTPError as error:
            raise RuntimeError(f"{method} {url}: HTTP {error.code}: {error.read().decode()}") from None

    def items(self, url: str):
        while url:
            _, _, page = self.request("GET", url)
            yield from page["value"]
            url = page.get("continuationUri")

    def wait(self, url: str, success: str, timeout: int = 1800):
        deadline = time.monotonic() + timeout
        previous = None
        while time.monotonic() < deadline:
            _, _, result = self.request("GET", url)
            status = result.get("status")
            if status != previous:
                print(f"Fabric status: {status}", flush=True)
                previous = status
            if status == success:
                return result
            if status not in {"NotStarted", "Running", "InProgress"}:
                raise RuntimeError(f"Fabric operation did not {success}: {json.dumps(result)}")
            time.sleep(15)
        raise TimeoutError(f"Fabric operation timed out after {timeout}s: {url}")

    def update(self, url: str, body: dict):
        status, headers, result = self.request("POST", url, body)
        if status == 202:
            self.wait(headers["Location"], "Succeeded")
        elif status not in (200, 201):
            raise RuntimeError(f"Fabric definition update returned HTTP {status}: {result}")
        return result


def load_patients(client: Client, page_size: int = 100) -> list[dict]:
    patients = {}
    url = f"{client.base}/Patient?_count={page_size}"
    while url:
        _, _, page = client.request("GET", url)
        if page.get("resourceType") != "Bundle":
            raise RuntimeError(f"Patient search did not return a FHIR Bundle: {page}")
        for entry in page.get("entry", []):
            resource = entry.get("resource", {})
            if resource.get("resourceType") == "Patient":
                patients[resource["id"]] = resource
        next_url = next((link["url"] for link in page.get("link", []) if link["relation"] == "next"), None)
        url = urljoin(url, next_url) if next_url else None
    if not patients:
        raise RuntimeError("FHIR contains no Patients; refusing to generate or replace demo sources")
    return list(patients.values())


def apply_fhir(client: Client, patients: list[dict], as_of: date) -> dict[str, int]:
    resources = build_resources(patients, as_of)
    for number, bundle in enumerate(transaction_bundles(resources), 1):
        status, _, result = client.request("POST", client.base, bundle)
        statuses = [entry.get("response", {}).get("status", "").split(" ", 1)[0]
                    for entry in result.get("entry", [])]
        if status != 200 or len(statuses) != len(bundle["entry"]) or any(code not in {"200", "201"} for code in statuses):
            raise RuntimeError(f"FHIR transaction {number} failed: HTTP {status}: {json.dumps(result)}")
        print(f"FHIR transaction {number}: {len(statuses)} upserts accepted", flush=True)
    counts = dict(sorted(Counter(resource["resourceType"] for resource in resources).items()))
    print("FHIR upsert counts: " + json.dumps(counts, sort_keys=True), flush=True)
    return counts


def outreach_definition(rows_by_table: dict, workspace_id: str, lakehouse: dict) -> dict:
    code = f'''import json
from pyspark.sql import functions as F
import notebookutils

rows_by_table = json.loads({json.dumps(rows_by_table)!r})
# Check every destination before the first overwrite, including on reruns.
for name in rows_by_table:
    if spark.catalog.tableExists(name):
        existing = spark.table(name)
        if existing.count() and "scenario_source" not in existing.columns:
            raise RuntimeError("Refusing to replace non-demo source " + name)
counts = {{}}
for name, rows in rows_by_table.items():
    # A one-patient cohort has no email-open events; retain the event schema.
    df = spark.createDataFrame(rows) if rows else spark.createDataFrame([], spark.createDataFrame(rows_by_table["emailsent"]).schema)
    for field in ("Timestamp", "modifiedon", "createdon", "msdynmkt_journeystarttime", "msdynmkt_journeyendtime"):
        if field in df.columns:
            df = df.withColumn(field, F.to_timestamp(F.col(field)))
    df.write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable(name)
    counts[name] = spark.table(name).count()
    if counts[name] != len(rows):
        raise RuntimeError("Outreach row count mismatch: " + name)
print("OUTREACH_COUNTS=" + json.dumps(counts, sort_keys=True))
notebookutils.notebook.exit(json.dumps(counts, sort_keys=True))
'''
    notebook = {
        "nbformat": 4, "nbformat_minor": 5,
        "metadata": {
            "kernel_info": {"name": "synapse_pyspark"},
            "kernelspec": {"name": "synapse_pyspark", "display_name": "Synapse PySpark"},
            "language_info": {"name": "python"},
            "dependencies": {"lakehouse": {
                "default_lakehouse": lakehouse["id"], "default_lakehouse_name": lakehouse["displayName"],
                "default_lakehouse_workspace_id": workspace_id,
                "known_lakehouses": [{"id": lakehouse["id"]}],
            }},
        },
        "cells": [{"id": "seed-outreach", "cell_type": "code", "metadata": {},
                   "source": code.splitlines(keepends=True), "outputs": [], "execution_count": None}],
    }
    return {"format": "ipynb", "parts": [{"path": "notebook-content.ipynb", "payloadType": "InlineBase64",
            "payload": base64.b64encode(json.dumps(notebook).encode()).decode()}]}


def apply_outreach(client: Client, patients: list[dict], as_of: date, workspace_id: str, bronze_name: str | None):
    root = f"/v1/workspaces/{workspace_id}"
    _, _, workspace = client.request("GET", root)
    capacities = list(client.items("/v1/capacities"))
    if not any(item["id"] == workspace.get("capacityId") and item.get("state") == "Active" for item in capacities):
        raise RuntimeError("Workspace must be assigned to an active Fabric capacity")
    lakehouses = [item for item in client.items(root + "/lakehouses")
                  if item["displayName"] == bronze_name] if bronze_name else [
                      item for item in client.items(root + "/lakehouses") if "bronze" in item["displayName"].lower()]
    if len(lakehouses) != 1:
        raise RuntimeError(f"Expected exactly one Bronze lakehouse, found {len(lakehouses)}")
    lakehouse = lakehouses[0]
    print(f"Bronze lakehouse: {lakehouse['displayName']} ({lakehouse['id']})", flush=True)
    rows = build_outreach_sources(patients, as_of)
    definition = outreach_definition(rows, workspace_id, lakehouse)
    notebooks = [item for item in client.items(root + "/items?type=Notebook") if item["displayName"] == NOTEBOOK_NAME]
    if len(notebooks) > 1:
        raise RuntimeError(f"Ambiguous notebook name: {NOTEBOOK_NAME}")
    if notebooks:
        notebook_id = notebooks[0]["id"]
        # Do not change the definition or submit a competing job while a prior run is active.
        for job in client.items(f"{root}/items/{notebook_id}/jobs/instances"):
            if job.get("status") in {"NotStarted", "Running", "InProgress"}:
                client.wait(f"{root}/items/{notebook_id}/jobs/instances/{job['id']}", "Completed")
        client.update(f"{root}/notebooks/{notebook_id}/updateDefinition", {"definition": definition})
    else:
        client.update(root + "/items", {"displayName": NOTEBOOK_NAME, "type": "Notebook", "definition": definition})
        notebooks = [item for item in client.items(root + "/items?type=Notebook") if item["displayName"] == NOTEBOOK_NAME]
        if len(notebooks) != 1:
            raise RuntimeError("Created outreach notebook could not be uniquely resolved")
        notebook_id = notebooks[0]["id"]
    status, headers, result = client.request("POST", f"{root}/items/{notebook_id}/jobs/instances?jobType=RunNotebook", {
        "executionData": {"configuration": {"useStarterPool": True, "defaultLakehouse": {
            "id": lakehouse["id"], "name": lakehouse["displayName"], "workspaceId": workspace_id,
        }}}})
    if status != 202:
        raise RuntimeError(f"RunNotebook returned HTTP {status}: {result}")
    job_url = headers["Location"]
    print(f"Outreach notebook {notebook_id}; job {job_url}", flush=True)
    client.wait(job_url, "Completed")
    # Completed implies the notebook's persisted-table count assertions all passed.
    counts = {name: len(values) for name, values in rows.items()}
    print("Outreach table counts verified by notebook: " + json.dumps(counts, sort_keys=True), flush=True)
    return counts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("fhir", "outreach"))
    parser.add_argument("--subscription", required=True)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--fhir-url")
    source.add_argument("--resource-group", help="Discover the FHIR service; skip only if none exists")
    parser.add_argument("--as-of", type=date.fromisoformat, default=datetime.now(timezone.utc).date())
    parser.add_argument("--workspace-id")
    parser.add_argument("--bronze-lakehouse-name")
    args = parser.parse_args()
    if args.mode == "outreach" and not args.workspace_id:
        parser.error("outreach requires --workspace-id")
    fhir_url = args.fhir_url
    if args.resource_group:
        services = azure_json(args.subscription, "resource", "list", "--resource-group", args.resource_group,
                              "--resource-type", "Microsoft.HealthcareApis/workspaces/fhirservices")
        if not services:
            print("Skipping demo enrichment: no FHIR service exists in the resource group", flush=True)
            return
        if len(services) != 1:
            raise RuntimeError("Expected exactly one FHIR service; specify --fhir-url")
        fhir_url = f"https://{services[0]['name'].replace('/', '-')}.fhir.azurehealthcareapis.com"
    fhir = Client(fhir_url, args.subscription)
    patients = load_patients(fhir)
    print(f"FHIR patients: {len(patients)}; as_of: {args.as_of}", flush=True)
    if args.mode == "fhir":
        apply_fhir(fhir, patients, args.as_of)
    else:
        apply_outreach(Client(FABRIC, args.subscription), patients, args.as_of, args.workspace_id, args.bronze_lakehouse_name)


if __name__ == "__main__":
    main()
