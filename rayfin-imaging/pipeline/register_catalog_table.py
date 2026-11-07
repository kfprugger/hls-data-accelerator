"""Register the slide catalog as a Delta table (`slides`) in the Lakehouse.

Writes manifest.json as CSV to Files/catalog/slides.csv, then calls the Fabric
"Load Table" API so the catalog can be queried from the SQL analytics endpoint or Power BI.
Uses your Azure CLI login (`az login`).

Usage: python pipeline/register_catalog_table.py
"""
import csv
import io
import json
import os
import pathlib
import subprocess
import tempfile
import time

import requests
from azure.identity import AzureCliCredential
import fabric_config  # noqa: E402

HERE = pathlib.Path(__file__).parent
WORKSPACE_ID = fabric_config.get("WORKSPACE_ID")
LAKEHOUSE_ID = fabric_config.get("LAKEHOUSE_ID")
COLUMNS = [
    "id", "title", "organ", "diagnosis", "project", "case", "vendor", "objectivePower", "mpp",
    "width", "height", "levels", "tileCount", "rawSizeBytes", "gdcFileId", "sourceUrl", "dzi", "raw",
]


def main() -> None:
    manifest = json.loads((HERE.parent / "work" / "lakehouse" / "manifest.json").read_text())
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=COLUMNS, extrasaction="ignore")
    writer.writeheader()
    for slide in manifest["slides"]:
        writer.writerow(slide)

    credential = AzureCliCredential()
    with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False) as tf:
        tf.write(buf.getvalue())
        tmp_csv = tf.name
    try:
        env = {**os.environ, "AZCOPY_AUTO_LOGIN_TYPE": "AZCLI"}
        subprocess.check_call([
            "azcopy", "copy", tmp_csv,
            f"https://onelake.blob.fabric.microsoft.com/{WORKSPACE_ID}/{LAKEHOUSE_ID}/Files/catalog/slides.csv",
            "--overwrite=true", "--trusted-microsoft-suffixes=onelake.blob.fabric.microsoft.com",
            "--log-level=ERROR", "--output-level=essential",
        ], env=env)
    finally:
        os.unlink(tmp_csv)
    token = credential.get_token("https://api.fabric.microsoft.com/.default").token
    url = f"https://api.fabric.microsoft.com/v1/workspaces/{WORKSPACE_ID}/lakehouses/{LAKEHOUSE_ID}/tables/slides/load"
    body = {
        "relativePath": "Files/catalog/slides.csv",
        "pathType": "File",
        "mode": "Overwrite",
        "formatOptions": {"format": "Csv", "header": True, "delimiter": ","},
    }
    resp = requests.post(url, json=body, headers={"Authorization": f"Bearer {token}"}, timeout=60)
    resp.raise_for_status()
    op = resp.headers.get("Location")
    while op:
        time.sleep(3)
        status = requests.get(op, headers={"Authorization": f"Bearer {token}"}, timeout=60).json()
        print(status.get("status"))
        if status.get("status") in ("Succeeded", "Failed"):
            if status.get("status") == "Failed":
                raise SystemExit(json.dumps(status, indent=2))
            break
    print(f"Loaded {len(manifest['slides'])} rows into table `slides`")


if __name__ == "__main__":
    main()
