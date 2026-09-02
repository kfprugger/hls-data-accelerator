"""Minimal streaming client for OneLake's ADLS Gen2 endpoint."""

from __future__ import annotations

import time
import os
import shutil
import subprocess
from pathlib import Path
from urllib.parse import quote

import requests
from azure.identity import DefaultAzureCredential

ONELAKE_DFS_BASE = "https://onelake.dfs.fabric.microsoft.com"
STORAGE_SCOPE = "https://storage.azure.com/.default"
CHUNK_SIZE = 4 * 1024 * 1024


class OneLakeClient:
    """Upload local trees to OneLake without buffering complete files in memory."""

    def __init__(self, credential=None, base_url: str = ONELAKE_DFS_BASE) -> None:
        self.credential = credential or DefaultAzureCredential()
        self.base_url = base_url.rstrip("/")

    def _headers(self, content_type: str | None = None) -> dict[str, str]:
        headers = {
            "Authorization": f"Bearer {self.credential.get_token(STORAGE_SCOPE).token}",
            "x-ms-version": "2023-11-03",
        }
        if content_type:
            headers["Content-Type"] = content_type
        return headers

    def _request(
        self,
        method: str,
        url: str,
        *,
        data=None,
        acceptable: set[int] | None = None,
        max_retries: int = 4,
    ) -> requests.Response:
        allowed = acceptable or {200, 201, 202}
        for attempt in range(1, max_retries + 1):
            response = requests.request(
                method,
                url,
                headers=self._headers("application/octet-stream" if data is not None else None),
                data=data,
                timeout=120,
            )
            if response.status_code in allowed:
                return response
            retryable = response.status_code == 429 or response.status_code >= 500
            if retryable and attempt < max_retries:
                delay = int(response.headers.get("Retry-After", "0") or "0")
                time.sleep(delay if delay > 0 else min(20, 5 * attempt))
                continue
            response.raise_for_status()
        raise RuntimeError(f"OneLake request exhausted retries: {method} {url}")

    def _base_path(self, workspace_name: str, lakehouse_name: str) -> str:
        workspace = quote(workspace_name, safe="")
        lakehouse = quote(f"{lakehouse_name}.Lakehouse", safe="")
        return f"{self.base_url}/{workspace}/{lakehouse}"

    def _ensure_directory(self, base: str, relative_path: str) -> None:
        current: list[str] = []
        for component in Path(relative_path).parts:
            current.append(component)
            encoded = "/".join(quote(part, safe="") for part in current)
            self._request(
                "PUT",
                f"{base}/{encoded}?resource=directory",
                acceptable={201, 409},
            )

    def upload_file(self, base: str, local_path: Path, remote_path: str) -> int:
        """Upload one file with create/append/flush and return bytes written."""
        encoded = "/".join(quote(part, safe="") for part in Path(remote_path).parts)
        url = f"{base}/{encoded}"
        self._request("PUT", f"{url}?resource=file", acceptable={201})
        position = 0
        with local_path.open("rb") as source:
            while chunk := source.read(CHUNK_SIZE):
                self._request(
                    "PATCH",
                    f"{url}?action=append&position={position}",
                    data=chunk,
                    acceptable={202},
                )
                position += len(chunk)
        self._request(
            "PATCH",
            f"{url}?action=flush&position={position}",
            acceptable={200},
        )
        return position

    def upload_tree(
        self,
        workspace_name: str,
        lakehouse_name: str,
        local_root: Path,
        remote_root: str = "Files/hds-build-artifacts",
    ) -> dict[str, int]:
        """Upload every file under *local_root* and return byte counts by path."""
        base = self._base_path(workspace_name, lakehouse_name)
        self._ensure_directory(base, remote_root)
        results: dict[str, int] = {}
        for local_path in sorted(path for path in local_root.rglob("*") if path.is_file()):
            relative = local_path.relative_to(local_root).as_posix()
            remote_path = f"{remote_root}/{relative}"
            parent = str(Path(remote_path).parent)
            self._ensure_directory(base, parent)
            results[remote_path] = self.upload_file(base, local_path, remote_path)
        return results
    def upload_tree_with_azcopy(
        self,
        workspace_name: str,
        lakehouse_name: str,
        local_root: Path,
        remote_root: str = "Files/hds-build-artifacts",
    ) -> dict[str, int]:
        """Bulk-upload a local tree with Microsoft's parallel AzCopy engine."""
        executable = shutil.which("azcopy")
        if not executable:
            raise RuntimeError(
                "AzCopy is required for HDS bulk upload. Install it from "
                "https://learn.microsoft.com/azure/storage/common/storage-use-azcopy-v10"
            )

        source = f"{local_root.resolve()}/*"
        destination = f"{self._base_path(workspace_name, lakehouse_name)}/{remote_root.strip('/')}"
        environment = os.environ.copy()
        environment.setdefault("AZCOPY_AUTO_LOGIN_TYPE", "AZCLI")
        if environment.get("AZURE_TENANT_ID"):
            environment.setdefault("AZCOPY_TENANT_ID", environment["AZURE_TENANT_ID"])

        process = subprocess.run(
            [
                executable,
                "copy",
                source,
                destination,
                "--recursive=true",
                "--overwrite=ifSourceNewer",
                "--trusted-microsoft-suffixes=fabric.microsoft.com",
                "--output-level=essential",
            ],
            env=environment,
            capture_output=True,
            text=True,
            timeout=30 * 60,
        )
        if process.returncode != 0:
            detail = (process.stderr or process.stdout or "AzCopy failed").strip()
            raise RuntimeError(f"AzCopy OneLake upload failed: {detail}")

        return {
            f"{remote_root.rstrip('/')}/{path.relative_to(local_root).as_posix()}": path.stat().st_size
            for path in local_root.rglob("*")
            if path.is_file()
        }
