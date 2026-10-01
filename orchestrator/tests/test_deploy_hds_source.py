from __future__ import annotations

import base64
import csv
import hashlib
import json
import io
import shutil
import tempfile
import threading
import time
from contextlib import ExitStack, redirect_stdout
import unittest
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import patch
import zipfile

from activities import deploy_hds_source as hds
from shared.fabric_client import FabricClient
from shared.onelake_client import CHUNK_SIZE, OneLakeClient


class _Token:
    token = "test-token"


class _Credential:
    def get_token(self, _scope):
        return _Token()


class _Response:
    def __init__(self, status_code=201, payload=None):
        self.status_code = status_code
        self.headers = {}
        self.content = b"" if payload is None else json.dumps(payload).encode()
        self._payload = payload or {}
        self.text = ""

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(self.status_code)

    def json(self):
        return self._payload


class _ContractFabric:
    def __init__(self, missing: str | None = None):
        self.expected = hds.expected_source_contract(hds.BUILD_ROOT)
        self.missing = missing

    def list_items(self, _workspace_id, _item_type=None, max_retries=3):
        items = []
        counter = 0
        for item_type, names in self.expected.items():
            for name in names:
                if name == self.missing:
                    continue
                counter += 1
                items.append({"id": str(counter), "type": item_type, "displayName": name})
        items.append({"id": "environment", "type": "Environment", "displayName": hds.ENVIRONMENT_NAME})
        items.append({"id": "master", "type": "Notebook", "displayName": "master_deployer"})
        return items

    def call(self, _method, endpoint, body=None, max_retries=3):
        if endpoint.endswith("/environments"):
            return {"value": [{"id": "environment", "displayName": hds.ENVIRONMENT_NAME}]}
        if "jobs/instances" in endpoint:
            return {"value": [{"id": "job", "status": "Completed"}]}
        return {}


def _write_test_wheel(path: Path, entries: dict[str, bytes]) -> None:
    name, version = path.name.split("-")[:2]
    record = f"{name}-{version}.dist-info/RECORD"
    entries.setdefault(f"{name}-{version}.dist-info/WHEEL", b"Wheel-Version: 1.0\nRoot-Is-Purelib: true\nTag: py3-none-any\n")
    entries.setdefault(f"{name}-{version}.dist-info/METADATA", f"Metadata-Version: 2.1\nName: {name}\nVersion: {version}\n".encode())
    rows = io.StringIO(newline="")
    writer = csv.writer(rows, lineterminator="\n")
    for name, content in sorted(entries.items()):
        digest = base64.urlsafe_b64encode(hashlib.sha256(content).digest()).decode().rstrip("=")
        writer.writerow([name, f"sha256={digest}", len(content)])
    writer.writerow([record, "", ""])
    with zipfile.ZipFile(path, "w") as archive:
        for name, content in entries.items():
            archive.writestr(name, content)
        archive.writestr(record, rows.getvalue())


class HdsPayloadIntegrityTests(unittest.TestCase):
    def setUp(self):
        stack = self.enterContext(ExitStack())
        root = Path(stack.enter_context(tempfile.TemporaryDirectory()))
        source_hds = root / "vendor" / "hds"
        source_dtt = root / "vendor" / "dtt"
        shutil.copytree(hds.HDS_ROOT / hds.ARTIFACT_ROOT_NAME, source_hds / hds.ARTIFACT_ROOT_NAME)
        modules = {
            source_hds: {"hds/__init__.py", "hds/runtime.py"},
            source_dtt: {
                "configuration_compiler/__init__.py",
                "configuration_compiler/config_files_models/__init__.py",
                "configuration_compiler/config_files_models/env/__init__.py",
                "configuration_compiler/config_files_models/env/ext_model.py",
                "configuration_compiler/config_files_models/env/model.py",
                "common/__init__.py", "common/utils/__init__.py", "common/utils/logging.py",
            },
        }
        for source, members in modules.items():
            for member in members:
                path = source / "src" / member
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("VERSION = 1\n", encoding="utf-8")
        stack.enter_context(patch.multiple(
            hds, HDS_ROOT=source_hds, DTT_ROOT=source_dtt,
            VENDOR_ROOT=root / "vendor", BUILD_ROOT=root / "build",
        ))
        self.builder = stack.enter_context(patch.object(hds, "_build_wheel", side_effect=self.build_wheel))
        self.runtime = source_hds / "src" / "hds" / "runtime.py"

    @staticmethod
    def build_wheel(source_root, destination, expected):
        path = destination / expected.replace("*", "py3-none-any")
        entries = {member: (source_root / "src" / member).read_bytes() for member in hds._runtime_modules(source_root)}
        _write_test_wheel(path, entries)
        return hds._tag_wheel(path)

    def wheel(self, package="hds"):
        return next((hds.BUILD_ROOT / hds.ARTIFACT_ROOT_NAME / hds.LIBRARY_RELATIVE_PATH).glob(f"{package}-*.whl"))

    def test_missing_env_source_rejects_staging(self):
        for filename in ("__init__.py", "ext_model.py", "model.py"):
            with self.subTest(filename=filename):
                path = hds.DTT_ROOT / "src/configuration_compiler/config_files_models/env" / filename
                content = path.read_bytes()
                path.unlink()
                try:
                    with self.assertRaisesRegex(ValueError, "DTT source.*" + path.name.replace(".", r"\.")):
                        hds.stage_source_payload()
                    self.assertFalse((hds.BUILD_ROOT / ".source-checksum").exists())
                finally:
                    path.write_bytes(content)

    def test_wheel_missing_module_fails_even_with_valid_record(self):
        hds.stage_source_payload()
        for package, member in (("dtt", "configuration_compiler/config_files_models/env/model.py"), ("hds", "hds/runtime.py")):
            with self.subTest(package=package):
                path = self.wheel(package)
                with zipfile.ZipFile(path) as archive:
                    entries = {name: archive.read(name) for name in archive.namelist() if not name.endswith("/RECORD")}
                del entries[member]
                _write_test_wheel(path, entries)
                with self.assertRaisesRegex(ValueError, "missing runtime modules"):
                    hds.validate_staged_payload(hds.BUILD_ROOT)
                hds.stage_source_payload(force=True)

    def test_unchanged_valid_cache_reuses_wheel_bytes(self):
        hds.stage_source_payload()
        before = self.wheel().read_bytes()
        with patch.object(hds, "_build_wheel", side_effect=AssertionError("Unexpected wheel rebuild")):
            hds.stage_source_payload()
        self.assertEqual(self.wheel().read_bytes(), before)

    def test_changed_source_rebuilds_content_identity_without_version_change(self):
        hds.stage_source_payload()
        name = self.wheel().name
        self.runtime.write_text("VERSION = 2\n", encoding="utf-8")
        hds.stage_source_payload()
        self.assertNotEqual(self.wheel().name, name)
        self.assertEqual(self.wheel().name.split("-")[:2], name.split("-")[:2])
        with zipfile.ZipFile(self.wheel()) as archive:
            self.assertEqual(archive.read("hds/runtime.py"), b"VERSION = 2\n")

    def test_forced_stage_replaces_cached_wheel_bytes(self):
        hds.stage_source_payload()
        with zipfile.ZipFile(self.wheel()) as archive:
            entries = {name: archive.read(name) for name in archive.namelist() if not name.endswith("/RECORD")}
        entries["hds/runtime.py"] = b"VERSION = 'stale cached wheel'\n"
        _write_test_wheel(self.wheel(), entries)
        hds.stage_source_payload(force=True)
        with zipfile.ZipFile(self.wheel()) as archive:
            self.assertEqual(archive.read("hds/runtime.py"), self.runtime.read_bytes())

    def test_forced_identical_build_has_identical_name_bytes_and_package_version(self):
        hds.stage_source_payload()
        before_name, before_bytes = self.wheel().name, self.wheel().read_bytes()
        hds.stage_source_payload(force=True)
        self.assertEqual((self.wheel().name, self.wheel().read_bytes()), (before_name, before_bytes))
        with zipfile.ZipFile(self.wheel()) as archive:
            metadata = archive.read(f"hds-{hds.HDS_VERSION}.dist-info/METADATA")
        self.assertEqual(metadata, f"Metadata-Version: 2.1\nName: hds\nVersion: {hds.HDS_VERSION}\n".encode())

    def test_modified_wheel_with_valid_record_cannot_reuse_old_content_identity(self):
        hds.stage_source_payload()
        with zipfile.ZipFile(self.wheel()) as archive:
            entries = {name: archive.read(name) for name in archive.namelist() if not name.endswith("/RECORD")}
        entries["hds/runtime.py"] = b"VERSION = 2\n"
        _write_test_wheel(self.wheel(), entries)
        with self.assertRaisesRegex(ValueError, "filename does not identify its content"):
            hds.validate_staged_payload(hds.BUILD_ROOT)

    def test_invalid_unchanged_cache_is_rebuilt(self):
        hds.stage_source_payload()
        self.wheel("dtt").write_bytes(b"not a wheel")
        hds.stage_source_payload()
        with zipfile.ZipFile(self.wheel("dtt")) as archive:
            self.assertEqual(archive.read("configuration_compiler/config_files_models/env/model.py"), b"VERSION = 1\n")

    def test_failed_validation_does_not_mark_stage_successful(self):
        with patch.object(hds, "validate_staged_payload", side_effect=ValueError("Incomplete payload")):
            with self.assertRaisesRegex(ValueError, "Incomplete payload"):
                hds.stage_source_payload()
        self.assertFalse((hds.BUILD_ROOT / ".source-checksum").exists())

    def test_generated_build_outputs_do_not_invalidate_cache(self):
        hds.stage_source_payload()
        for relative in ("build/lib/stale.py", "dist/stale.whl", "src/hds.egg-info/PKG-INFO", "src/hds/__pycache__/runtime.pyc"):
            path = hds.HDS_ROOT / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"irrelevant generated artifact")
        with patch.object(hds, "_build_wheel", side_effect=AssertionError("Generated files invalidated source cache")):
            hds.stage_source_payload()
        with zipfile.ZipFile(self.wheel()) as archive:
            self.assertEqual(archive.read("hds/runtime.py"), self.runtime.read_bytes())

    def test_package_discovery_excludes_unpackaged_tools_and_tests(self):
        for source_root, relative in ((hds.DTT_ROOT, "tests/__init__.py"), (hds.DTT_ROOT, "tools/__init__.py"), (hds.HDS_ROOT, "tools/unpackaged.py")):
            path = source_root / "src" / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("raise RuntimeError('not a runtime package')\n", encoding="utf-8")
        hds.stage_source_payload()
        with zipfile.ZipFile(self.wheel("dtt")) as archive:
            self.assertTrue(hds.DTT_ENV_MODULES <= set(archive.namelist()))
            self.assertNotIn("tests/__init__.py", archive.namelist())
            self.assertNotIn("tools/__init__.py", archive.namelist())


class _EnvironmentFabric:
    def __init__(self, published, staging=None, retain_old_publish=False, definition_from_staging=False):
        self.published = dict(published)
        self.staging = dict(published if staging is None else staging)
        self.retain_old_publish = retain_old_publish
        self.publish_count = 0
        self.definition_from_staging = definition_from_staging

    def find_item(self, workspace_id, display_name, item_type):
        return {"id": "environment", "displayName": display_name, "type": item_type}

    def get_item_definition(self, workspace_id, item_id):
        return {"parts": [
            {"path": path, "payloadType": "InlineBase64", "payload": base64.b64encode(content).decode()}
            for path, content in (self.staging if self.definition_from_staging else self.published).items()
        ]}

    def call(self, method, endpoint):
        if endpoint.split("?", 1)[0].endswith("/libraries"):
            content = self.staging if "/staging/" in endpoint else self.published
            return {"libraries": [
                {"name": Path(path).name, "libraryType": "Custom"}
                for path in content if path.endswith(".whl")
            ]}
        return {"id": "environment", "properties": {"publishDetails": {"state": "Success"}}}

    def request_content(self, method, endpoint, content, max_retries):
        if endpoint.endswith("/importExternalLibraries"):
            self.staging["Libraries/PublicLibraries/environment.yml"] = content.encode()
        else:
            self.staging["Libraries/CustomLibraries/" + endpoint.rsplit("/", 1)[1].split("?")[0]] = content

    def request_raw(self, method, endpoint):
        if method == "GET" and endpoint.endswith("/libraries/exportExternalLibraries"):
            return SimpleNamespace(content=self.published["Libraries/PublicLibraries/environment.yml"])
        if method == "DELETE" and "/staging/libraries/" in endpoint:
            del self.staging["Libraries/CustomLibraries/" + endpoint.rsplit("/", 1)[1]]
            return _Response(status_code=200)
        if not endpoint.endswith("/staging/publish?beta=false"):
            raise AssertionError(endpoint)
        self.publish_count += 1
        if not self.retain_old_publish:
            self.published = dict(self.staging)
        return _Response(status_code=200)


class HdsEnvironmentIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        library = self.root / hds.ARTIFACT_ROOT_NAME / hds.LIBRARY_RELATIVE_PATH
        library.mkdir(parents=True)
        self.desired = {"Libraries/PublicLibraries/environment.yml": b"dependencies:\n  - pip:\n    - scipy==1.11.4\n"}
        (library / "environment.yml").write_bytes(self.desired["Libraries/PublicLibraries/environment.yml"])
        for package, version in (("hds", hds.HDS_VERSION), ("dtt", hds.DTT_VERSION)):
            wheel = library / f"{package}-{version}-py3-none-any.whl"
            _write_test_wheel(wheel, {f"{package}/runtime.py": b"VERSION = 'repaired'\n"})
            tagged = hds._tag_wheel(wheel)
            self.desired[f"Libraries/CustomLibraries/{tagged.name}"] = tagged.read_bytes()
        self.enterContext(patch.object(hds, "_event"))

    def test_identical_published_bytes_skip_without_publishing_staging_edits(self):
        fabric = _EnvironmentFabric(self.desired, staging={})
        hds._deploy_environment(fabric, "workspace", self.root)
        self.assertEqual(fabric.publish_count, 0)
        self.assertEqual(fabric.published, self.desired)
        self.assertEqual(fabric.staging, {})

    def test_same_named_changed_wheel_is_uploaded_and_published(self):
        for path in self.desired:
            with self.subTest(path=path):
                previous = {**self.desired, path: b"old published bytes"}
                fabric = _EnvironmentFabric(previous, staging=self.desired)
                hds._deploy_environment(fabric, "workspace", self.root)
                self.assertEqual(fabric.publish_count, 1)
                self.assertEqual(fabric.published, self.desired)

    def test_staged_only_same_name_repair_cannot_masquerade_as_published(self):
        published = {}
        staging = {}
        for path, content in self.desired.items():
            if path.endswith(".whl"):
                fields = Path(path).name.split("-")
                legacy_path = "Libraries/CustomLibraries/" + "-".join([*fields[:2], *fields[-3:]])
                published[legacy_path] = b"old live wheel bytes"
                staging[legacy_path] = content
            else:
                published[path] = staging[path] = content
        unrelated = "Libraries/CustomLibraries/unrelated-2.0-py3-none-any.whl"
        published[unrelated] = staging[unrelated] = b"unrelated package"
        fabric = _EnvironmentFabric(published, staging=staging, definition_from_staging=True)
        hds._deploy_environment(fabric, "workspace", self.root)
        self.assertEqual(fabric.publish_count, 1)
        self.assertEqual(fabric.published, {**self.desired, unrelated: b"unrelated package"})

    def test_staged_yaml_does_not_hide_different_published_yaml(self):
        published = {**self.desired, "Libraries/PublicLibraries/environment.yml": b"old published requirements"}
        fabric = _EnvironmentFabric(published, staging=self.desired, definition_from_staging=True)
        hds._deploy_environment(fabric, "workspace", self.root)
        self.assertEqual(fabric.publish_count, 1)
        self.assertEqual(fabric.published, self.desired)

    def test_publish_success_with_old_bytes_is_rejected(self):
        path = next(path for path in self.desired if path.endswith(".whl"))
        previous = {**self.desired, path: b"old wheel bytes"}
        fabric = _EnvironmentFabric(previous, retain_old_publish=True)
        with self.assertRaisesRegex(RuntimeError, "Published environment content does not match"):
            hds._deploy_environment(fabric, "workspace", self.root)
        self.assertEqual(fabric.published, previous)

    def test_definition_permission_error_is_not_treated_as_drift(self):
        fabric = _EnvironmentFabric(self.desired)
        error = hds.requests.HTTPError(response=SimpleNamespace(status_code=403))
        with patch.object(fabric, "get_item_definition", side_effect=error):
            with self.assertRaises(hds.requests.HTTPError):
                hds._deploy_environment(fabric, "workspace", self.root)
        self.assertEqual(fabric.publish_count, 0)
        self.assertEqual(fabric.staging, self.desired)

    def test_definition_without_published_wheels_cannot_skip_publish(self):
        fabric = _EnvironmentFabric({}, staging=self.desired)
        definition = _EnvironmentFabric(self.desired).get_item_definition("workspace", "environment")
        with patch.object(fabric, "get_item_definition", return_value=definition):
            hds._deploy_environment(fabric, "workspace", self.root)
        self.assertEqual(fabric.publish_count, 1)
        self.assertEqual(fabric.published, self.desired)

    def test_inaccessible_environment_is_replaced_and_published(self):
        class Fabric(_EnvironmentFabric):
            orphan_exists = True

            def find_item(self, workspace_id, display_name, item_type):
                return {"id": "orphan", "displayName": display_name, "type": item_type}

            def call(self, method, endpoint):
                if endpoint.endswith("/environments/orphan"):
                    raise hds.requests.HTTPError(response=SimpleNamespace(status_code=404))
                return super().call(method, endpoint)

            def delete_item(self, workspace_id, item_id):
                self.orphan_exists = False

            def request_raw(self, method, endpoint, body=None):
                if endpoint.endswith("/environments"):
                    return _Response(payload={"id": "environment"})
                return super().request_raw(method, endpoint)

        fabric = Fabric({})
        hds._deploy_environment(fabric, "workspace", self.root)
        self.assertFalse(fabric.orphan_exists)
        self.assertEqual(fabric.published, self.desired)


class HdsSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        hds.stage_source_payload()

    def test_hds_events_include_origin_timestamps_and_elapsed_duration(self):
        output = io.StringIO()
        hds._reset_event_timings()
        with (
            patch.object(hds, "_utc_now", side_effect=["2026-08-02T14:00:00Z", "2026-08-02T14:00:02.500000Z"]),
            patch.object(hds.time, "monotonic", side_effect=[100.0, 102.5]),
            redirect_stdout(output),
        ):
            hds._event("upload", "running", "Uploading")
            hds._event("upload", "succeeded", "42 files", job_id="job-42")

        payloads = [json.loads(line.split("|", 3)[3][:-2]) for line in output.getvalue().splitlines()]
        self.assertEqual(payloads[0]["startedAt"], "2026-08-02T14:00:00Z")
        self.assertEqual(payloads[0]["elapsedSeconds"], 0.0)
        self.assertEqual(payloads[1]["emittedAt"], "2026-08-02T14:00:02.500000Z")
        self.assertEqual(payloads[1]["finishedAt"], "2026-08-02T14:00:02.500000Z")
        self.assertEqual(payloads[1]["elapsedSeconds"], 2.5)
        self.assertEqual(payloads[1]["jobId"], "job-42")

    def test_managed_name_contract(self):
        self.assertEqual(hds.managed_artifact_name("omop"), "healthcare1_msft_gold_omop")
        self.assertEqual(hds.managed_artifact_name("cma-gold"), "healthcare1_msft_gold_cma")
        self.assertEqual(hds.managed_artifact_name("cma_gold"), "healthcare1_msft_gold_cma")
        self.assertEqual(
            hds.managed_artifact_name("msft_clinical_data_foundation_ingestion.json"),
            "healthcare1_msft_clinical_data_foundation_ingestion",
        )
        self.assertEqual(hds.managed_artifact_name("msft_config_notebook.ipynb"), "healthcare1_msft_config_notebook")

    def test_staged_payload_is_complete(self):
        summary = hds.validate_staged_payload(hds.BUILD_ROOT)
        self.assertEqual(summary["deployment_notebooks"], 9)
        self.assertEqual(summary["validation_notebooks"], 3)

    def test_staged_customer_insights_goal_mapping_uses_reference_string(self):
        relative = Path("healthcare-configuration") / hds.HDS_VERSION / "_internal" / "fhir4" / "transformation" / "ci" / "goal.columnsconfig.json"
        vendor_path = hds.HDS_ROOT / hds.ARTIFACT_ROOT_NAME / relative
        staged_path = hds.BUILD_ROOT / hds.ARTIFACT_ROOT_NAME / relative
        vendor_config = json.loads(vendor_path.read_text())
        staged_config = json.loads(staged_path.read_text())
        vendor_id = next(column for column in vendor_config["columns"] if column["name"] == "Id")
        staged_id = next(column for column in staged_config["columns"] if column["name"] == "Id")
        vendor_subject = next(column for column in vendor_config["columns"] if column["name"] == "SubjectPatient")
        staged_subject = next(column for column in staged_config["columns"] if column["name"] == "SubjectPatient")
        self.assertEqual(vendor_id["expression"], "idOrig")
        self.assertEqual(staged_id["expression"], "id")
        self.assertEqual(vendor_subject["expression"], "subject.idOrig")
        self.assertEqual(staged_subject["expression"], "regexp_extract(subject.reference, '([^/]+)$', 1)")

    def test_staged_omop_pipeline_does_not_repeat_clinical_ingestion(self):
        staged = next((hds.BUILD_ROOT / hds.ARTIFACT_ROOT_NAME).rglob("msft_omop_analytics.json"))
        vendor = next((hds.HDS_ROOT / hds.ARTIFACT_ROOT_NAME).rglob("msft_omop_analytics.json"))

        staged_activities = json.loads(staged.read_text())["properties"]["activities"]
        vendor_activities = json.loads(vendor.read_text())["properties"]["activities"]

        self.assertEqual(
            [activity["name"] for activity in staged_activities],
            ["omop_silver_gold_transformation"],
        )
        self.assertEqual(staged_activities[0]["dependsOn"], [])
        self.assertEqual(len(vendor_activities), 4)

    def test_staged_core_pipelines_have_one_owner_per_ingest_stage(self):
        artifact_root = hds.BUILD_ROOT / hds.ARTIFACT_ROOT_NAME

        def activity_names(filename: str) -> list[str]:
            pipeline = next(artifact_root.rglob(filename))
            return [
                activity["name"]
                for activity in json.loads(pipeline.read_text())["properties"]["activities"]
            ]

        self.assertEqual(
            activity_names("msft_clinical_data_foundation_ingestion.json"),
            ["raw_process_movement", "fhir_ndjson_bronze_ingestion", "bronze_silver_flatten"],
        )
        self.assertEqual(
            activity_names("msft_imaging_with_clinical_foundation_ingestion.json"),
            [
                "raw_process_movement",
                "imaging_dicom_extract_bronze_ingestion",
                "imaging_bronze_silver_metastore_transformation",
                "imaging_dicom_fhir_conversion",
                "fhir_ndjson_bronze_ingestion",
                "bronze_silver_flatten",
            ],
        )
        self.assertEqual(
            activity_names("msft_omop_analytics.json"),
            ["omop_silver_gold_transformation"],
        )

    def test_contract_reports_missing_artifact(self):
        missing = "healthcare1_msft_gold_omop"
        with self.assertRaisesRegex(RuntimeError, missing):
            hds.validate_source_contract(_ContractFabric(missing), "workspace", hds.BUILD_ROOT)

    def test_contract_accepts_complete_artifact_inventory(self):
        result = hds.validate_source_contract(_ContractFabric(), "workspace", hds.BUILD_ROOT)
        self.assertEqual(result["environment_id"], "environment")
        self.assertEqual(result["master_status"], "Completed")

    def test_ensure_lakehouse_accepts_same_named_sql_endpoint_companion(self):
        class Fabric:
            def list_items(self, _workspace_id):
                return [
                    {"id": "lakehouse", "type": "Lakehouse", "displayName": "deployment_lakehouse"},
                    {"id": "endpoint", "type": "SQLEndpoint", "displayName": "deployment_lakehouse"},
                ]

        item = hds._ensure_item(Fabric(), "workspace", "deployment_lakehouse", "Lakehouse")
        self.assertEqual(item["id"], "lakehouse")
    def test_ensure_missing_lakehouse_recovers_beside_same_named_pipeline(self):
        class Fabric:
            def list_items(self, _workspace_id):
                return [
                    {"id": "pipeline", "type": "DataPipeline", "displayName": "healthcare1_msft_customer_insights"},
                ]

            def call(self, method, endpoint, body):
                self.created = (method, endpoint, body)
                return {"id": "lakehouse", **body}

        fabric = Fabric()
        item = hds._ensure_item(fabric, "workspace", "healthcare1_msft_customer_insights", "Lakehouse")
        self.assertEqual(item["id"], "lakehouse")
        self.assertEqual(fabric.created[2]["type"], "Lakehouse")

    def test_ensure_existing_notebook_wraps_update_definition(self):
        class Fabric:
            updated = None

            def list_items(self, _workspace_id):
                return [{"id": "notebook", "type": "Notebook", "displayName": "master_deployer"}]

            def update_item_definition(self, workspace_id, item_id, definition):
                self.updated = (workspace_id, item_id, definition)

        fabric = Fabric()
        definition = {"format": "ipynb", "parts": []}
        hds._ensure_item(fabric, "workspace", "master_deployer", "Notebook", definition)
        self.assertEqual(
            fabric.updated,
            ("workspace", "notebook", {"definition": definition}),
        )



    def test_managed_lakehouses_are_precreated_with_exact_contract_names(self):
        def ensure(_fabric, _workspace_id, display_name, item_type):
            return {"id": f"id-{display_name}", "displayName": display_name, "type": item_type}

        with patch.object(hds, "_ensure_item", side_effect=ensure), patch.object(hds, "_event"):
            lakehouses = hds._ensure_managed_lakehouses(object(), "workspace")

        self.assertEqual(set(lakehouses), set(hds.MANAGED_LAKEHOUSE_NAMES))
        self.assertEqual(
            {item["displayName"] for item in lakehouses.values()},
            set(hds.MANAGED_LAKEHOUSE_NAMES.values()),
        )

    def test_hds_source_setup_branches_overlap_and_return_named_results(self):
        barrier = threading.Barrier(4)
        entered = []
        lock = threading.Lock()

        def operation(name, result):
            def run(*_args):
                with lock:
                    entered.append(name)
                barrier.wait(timeout=2)
                return result
            return run

        expected_upload = {"artifact": 1}
        expected_environment = {"id": "environment"}
        expected_bootstrap = {"master": {"id": "master"}}
        expected_lakehouses = {"silver": {"id": "silver"}}
        with (
            patch.object(hds, "_upload_source_payload", side_effect=operation("upload", expected_upload)),
            patch.object(hds, "_publish_hds_environment", side_effect=operation("environment", expected_environment)),
            patch.object(hds, "_publish_bootstrap_items", side_effect=operation("bootstrap", expected_bootstrap)),
            patch.object(hds, "_ensure_managed_lakehouses", side_effect=operation("managed_lakehouses", expected_lakehouses)),
        ):
            upload, environment, bootstrap, lakehouses = hds._run_source_setup_wave(
                object(), object(), "workspace", "workspace-id", hds.BUILD_ROOT, "lakehouse-id"
            )

        self.assertEqual(set(entered), {"upload", "environment", "bootstrap", "managed_lakehouses"})
        self.assertIs(upload, expected_upload)
        self.assertIs(environment, expected_environment)
        self.assertIs(bootstrap, expected_bootstrap)
        self.assertIs(lakehouses, expected_lakehouses)

    def test_hds_source_setup_wave_drains_siblings_and_aggregates_failure(self):
        barrier = threading.Barrier(4)
        completed = []
        lock = threading.Lock()

        def operation(name, *, failure=False):
            def run(*_args):
                barrier.wait(timeout=2)
                if failure:
                    raise RuntimeError(f"synthetic {name} failure")
                with lock:
                    completed.append(name)
                return {}
            return run

        with (
            patch.object(hds, "_upload_source_payload", side_effect=operation("upload")),
            patch.object(hds, "_publish_hds_environment", side_effect=operation("environment", failure=True)),
            patch.object(hds, "_publish_bootstrap_items", side_effect=operation("bootstrap")),
            patch.object(hds, "_ensure_managed_lakehouses", side_effect=operation("managed_lakehouses")),
        ):
            with self.assertRaisesRegex(RuntimeError, "environment: synthetic environment failure"):
                hds._run_source_setup_wave(
                    object(), object(), "workspace", "workspace-id", hds.BUILD_ROOT, "lakehouse-id"
                )

        self.assertEqual(set(completed), {"upload", "bootstrap", "managed_lakehouses"})


    def test_notebook_job_parameters_use_official_scheduler_payload(self):
        class Fabric:
            api_base = "https://api.fabric.test/v1"

            def __init__(self):
                self.request = None

            def request_raw(self, method, endpoint, body):
                self.request = (method, endpoint, body)
                response = _Response(status_code=202)
                response.headers["Location"] = "https://api.fabric.test/jobs/instance"
                return response

        fabric = Fabric()
        location = FabricClient.run_notebook_job(
            fabric,
            "workspace",
            "notebook",
            parameters={"HYDRATION_LAKEHOUSE_KEYS": "silver", "retry": 2, "enabled": True},
        )

        self.assertEqual(location, "https://api.fabric.test/jobs/instance")
        method, endpoint, body = fabric.request
        self.assertEqual(method, "POST")
        self.assertEqual(endpoint, "/workspaces/workspace/items/notebook/jobs/RunNotebook/instances")
        self.assertEqual(
            body["parameters"],
            [
                {"name": "HYDRATION_LAKEHOUSE_KEYS", "value": "silver", "type": "Text"},
                {"name": "retry", "value": 2, "type": "Number"},
                {"name": "enabled", "value": True, "type": "Boolean"},
            ],
        )

    def test_two_hydration_shards_are_disjoint_and_concurrent(self):
        class Fabric:
            def __init__(self):
                self.started = []
                self.barrier = threading.Barrier(2)

            def run_notebook_job(self, workspace_id, item_id, parameters=None):
                keys = parameters["HYDRATION_LAKEHOUSE_KEYS"]
                self.started.append(keys)
                return f"https://example.test/jobs/{'silver' if keys == 'silver' else 'other'}"

            def wait_for_item_job(self, job_url, timeout_seconds, progress_callback):
                self.barrier.wait(timeout=2)
                shard = job_url.rsplit("/", 1)[-1]
                return {"id": f"job-{shard}", "status": "Completed"}

        fabric = Fabric()
        with patch.object(hds, "_event"):
            result = hds._run_hydration_shards(fabric, "workspace", "hydrator")

        shard_sets = [{item for item in keys.split(",") if item} for keys in fabric.started]
        self.assertEqual(len(shard_sets), 2)
        self.assertFalse(shard_sets[0] & shard_sets[1])
        self.assertEqual(
            shard_sets[0] | shard_sets[1],
            {key.replace("-", "_") for key in hds.MANAGED_LAKEHOUSE_NAMES},
        )
        self.assertEqual(set(result["shards"]), {"silver", "other"})

    def test_concurrent_hydration_callers_do_not_split_slot_reservations(self):
        class Fabric:
            def __init__(self):
                self.barrier = threading.Barrier(2)
                self.lock = threading.Lock()
                self.counter = 0

            def run_notebook_job(self, workspace_id, item_id, parameters=None):
                with self.lock:
                    self.counter += 1
                    instance = self.counter
                return f"https://example.test/jobs/{instance}"

            def wait_for_item_job(self, job_url, timeout_seconds, progress_callback):
                self.barrier.wait(timeout=2)
                instance = job_url.rsplit("/", 1)[-1]
                return {"id": f"job-{instance}", "status": "Completed"}

        fabric = Fabric()
        with patch.object(hds, "_event"), hds.ThreadPoolExecutor(max_workers=2) as executor:
            futures = [
                executor.submit(hds._run_hydration_shards, fabric, "workspace", "hydrator")
                for _ in range(2)
            ]
            results = [future.result(timeout=5) for future in futures]

        self.assertEqual(len(results), 2)
        self.assertEqual(fabric.counter, 4)

    def test_hds_deployment_scheduler_enforces_dependencies_and_concurrency(self):
        class Fabric:
            def __init__(self):
                self.started = []
                self.completed = []
                self.prerequisites_at_start = {}
                self.active = 0
                self.max_active = 0
                self.lock = threading.Lock()
                self.initial_barrier = threading.Barrier(2)

            def run_notebook_job(self, workspace_id, item_id, parameters=None):
                with self.lock:
                    self.started.append(item_id)
                    self.prerequisites_at_start[item_id] = set(self.completed)
                return f"https://example.test/jobs/{item_id}"

            def wait_for_item_job(self, job_url, timeout_seconds, progress_callback):
                item_id = job_url.rsplit("/", 1)[-1]
                with self.lock:
                    self.active += 1
                    self.max_active = max(self.max_active, self.active)
                try:
                    if item_id == "lakehouses_and_tables_deployer":
                        self.initial_barrier.wait(timeout=2)
                    time.sleep(0.01)
                    payload = {"id": f"job-{item_id}", "status": "Completed"}
                    progress_callback(payload, 5)
                    return payload
                finally:
                    with self.lock:
                        self.active -= 1
                        self.completed.append(item_id)

        fabric = Fabric()
        items = {name: {"id": name} for name in hds.DEPLOYMENT_STAGE_NAMES}
        with patch.object(hds, "_event"):
            jobs = hds._run_deployment_stages(fabric, "workspace", items)

        self.assertEqual(fabric.max_active, hds.CONTROL_PLANE_CONCURRENCY)
        for stage_name, dependencies in hds.DEPLOYMENT_STAGE_DEPENDENCIES.items():
            self.assertTrue(
                set(dependencies) <= fabric.prerequisites_at_start[stage_name],
                f"{stage_name} started before {dependencies}: {fabric.prerequisites_at_start}",
            )
        self.assertEqual(jobs[0]["status"], "Completed")
        self.assertEqual(set(jobs[0]["shards"]), {"silver", "other"})
        self.assertEqual([job["id"] for job in jobs[1:]], [f"job-{name}" for name in hds.DEPLOYMENT_STAGE_NAMES[1:]])

    def test_hds_stage_failure_blocks_unscheduled_dependents(self):
        class Fabric:
            def __init__(self):
                self.started = []

            def run_notebook_job(self, workspace_id, item_id, parameters=None):
                self.started.append(item_id)
                return f"https://example.test/jobs/{item_id}"

            def wait_for_item_job(self, job_url, timeout_seconds, progress_callback):
                item_id = job_url.rsplit("/", 1)[-1]
                if item_id == "powerbi_deployer":
                    raise RuntimeError("synthetic Power BI failure")
                return {"id": f"job-{item_id}", "status": "Completed"}

        fabric = Fabric()
        items = {name: {"id": name} for name in hds.DEPLOYMENT_STAGE_NAMES}
        with patch.object(hds, "_event") as emit:
            with self.assertRaisesRegex(RuntimeError, "powerbi_deployer: synthetic Power BI failure"):
                hds._run_deployment_stages(fabric, "workspace", items)

        self.assertNotIn("deployment_validator", fabric.started)
        blocked = {call.args[0] for call in emit.call_args_list if len(call.args) > 1 and call.args[1] == "blocked"}
        self.assertIn("deployment_validator", blocked)

    def test_fabric_job_wait_reports_each_polled_status(self):
        class Fabric:
            responses = iter([
                _Response(payload={"id": "job", "status": "InProgress"}),
                _Response(payload={"id": "job", "status": "Completed"}),
            ])

            def request_raw(self, _method, _url, *, timeout_seconds=None):
                return next(self.responses)

        progress = []
        result = FabricClient.wait_for_item_job(
            Fabric(),
            "https://example.test/job",
            timeout_seconds=5,
            poll_seconds=0,
            progress_callback=lambda payload, elapsed: progress.append((payload["status"], elapsed)),
        )
        self.assertEqual(result["status"], "Completed")
        self.assertEqual([status for status, _ in progress], ["InProgress", "Completed"])

    def test_onelake_upload_uses_four_mib_offsets_and_final_length(self):
        calls = []

        def fake_request(method, url, headers=None, data=None, timeout=None):
            calls.append((method, url, 0 if data is None else len(data)))
            status = 202 if "action=append" in url else 200 if "action=flush" in url else 201
            return _Response(status)

        with tempfile.TemporaryDirectory() as directory:
            payload = Path(directory) / "payload.bin"
            payload.write_bytes(b"a" * (CHUNK_SIZE + 7))
            client = OneLakeClient(_Credential(), "https://example.test")
            with patch("shared.onelake_client.requests.request", side_effect=fake_request):
                written = client.upload_file("https://example.test/ws/lh", payload, "Files/payload.bin")

        self.assertEqual(written, CHUNK_SIZE + 7)
        append_urls = [url for method, url, _ in calls if method == "PATCH" and "action=append" in url]
        self.assertEqual(append_urls, [
            "https://example.test/ws/lh/Files/payload.bin?action=append&position=0",
            f"https://example.test/ws/lh/Files/payload.bin?action=append&position={CHUNK_SIZE}",
        ])
        self.assertTrue(calls[-1][1].endswith(f"action=flush&position={CHUNK_SIZE + 7}"))

    def test_onelake_tree_upload_uses_azcopy_bulk_transfer(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "config.json").write_text("{}", encoding="utf-8")
            client = OneLakeClient(_Credential(), "https://example.test")
            completed = SimpleNamespace(returncode=0, stdout="", stderr="")
            with (
                patch("shared.onelake_client.shutil.which", return_value="/usr/local/bin/azcopy"),
                patch("shared.onelake_client.subprocess.run", return_value=completed) as run,
            ):
                uploaded = client.upload_tree_with_azcopy("workspace", "deployment_lakehouse", root)

        command = run.call_args.args[0]
        self.assertEqual(command[:2], ["/usr/local/bin/azcopy", "copy"])
        self.assertEqual(command[2], f"{root.resolve()}/*")
        self.assertEqual(
            command[3],
            "https://example.test/workspace/deployment_lakehouse.Lakehouse/Files/hds-build-artifacts",
        )
        self.assertIn("--recursive=true", command)
        self.assertEqual(uploaded, {"Files/hds-build-artifacts/config.json": 2})


if __name__ == "__main__":
    unittest.main()
