from __future__ import annotations

import json
import io
import tempfile
import threading
import time
from contextlib import redirect_stdout
import unittest
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import patch

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

    def test_staged_payload_is_complete_and_vendor_is_immutable(self):
        vendor = hds.HDS_ROOT / "src" / "tools" / "fabric_depolyment_notebooks" / "notebook_deployer.ipynb"
        before = vendor.read_bytes()
        summary = hds.validate_staged_payload(hds.BUILD_ROOT)
        self.assertEqual(summary["deployment_notebooks"], 9)
        self.assertEqual(summary["validation_notebooks"], 3)
        self.assertEqual(vendor.read_bytes(), before)

    def test_staged_hydration_notebook_has_parameterized_lakehouse_filter(self):
        staged_path = hds.BUILD_ROOT / "bootstrap" / "deployment_notebooks" / "lakehouses_and_tables_deployer.ipynb"
        notebook = json.loads(staged_path.read_text())
        parameter_cells = [cell for cell in notebook["cells"] if "parameters" in cell.get("metadata", {}).get("tags", [])]
        self.assertEqual(len(parameter_cells), 1)
        parameter_source = "".join(parameter_cells[0]["source"])
        notebook_source = "\n".join("".join(cell.get("source", [])) for cell in notebook["cells"])
        self.assertIn("HYDRATION_LAKEHOUSE_KEYS", parameter_source)
        self.assertIn("hydration_lakehouse_selected(base_lakehouse_name)", notebook_source)
        self.assertIn("lakehouses_to_create=selected_lakehouses", notebook_source)

    def test_staged_powerbi_deployer_propagates_artifact_failures(self):
        staged = hds.BUILD_ROOT / "bootstrap" / "deployment_notebooks" / "powerbi_deployer.ipynb"
        notebook = json.loads(staged.read_text())
        source = "\n".join("".join(cell.get("source", [])) for cell in notebook["cells"])

        self.assertIn("sm_errors.append", source)
        self.assertIn("rep_errors.append", source)
        self.assertIn("Power BI deployment failures", source)
        self.assertIn("powerbi-deployer-errors.txt", source)
        self.assertIn("_normalize_name(build_artifact_name(manifest_key))", source)


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


    def test_hds_environment_reuses_complete_published_payload(self):
        class Fabric:
            def find_item(self, workspace_id, display_name, item_type):
                return {"id": "environment", "displayName": display_name, "type": item_type}

            def call(self, method, endpoint):
                if endpoint.endswith("/staging/libraries"):
                    return {"customLibraries": {"wheelFiles": [
                        "dtt-0.3.1.1271-py3-none-any.whl",
                        "hds-1.4.0-py3-none-any.whl",
                    ]}}
                return {"id": "environment", "properties": {"publishDetails": {"state": "Success"}}}

        with patch.object(hds, "_event"):
            result = hds._deploy_environment(Fabric(), "workspace", hds.BUILD_ROOT)

        self.assertEqual(result["properties"]["publishDetails"]["state"], "Success")

    def test_hds_environment_replaces_inaccessible_existing_item(self):
        class Fabric:
            deleted = []
            created = []

            def find_item(self, workspace_id, display_name, item_type):
                return {"id": "orphan", "displayName": display_name, "type": item_type}

            def call(self, method, endpoint):
                if endpoint.endswith("/environments/orphan"):
                    response = SimpleNamespace(status_code=404)
                    raise hds.requests.HTTPError(response=response)
                if endpoint.endswith("/staging/libraries"):
                    return {"customLibraries": {"wheelFiles": [
                        "dtt-0.3.1.1271-py3-none-any.whl",
                        "hds-1.4.0-py3-none-any.whl",
                    ]}}
                return {"id": "replacement", "properties": {"publishDetails": {"state": "Success"}}}

            def delete_item(self, workspace_id, item_id):
                self.deleted.append((workspace_id, item_id))

            def request_raw(self, method, endpoint, body=None):
                self.created.append((method, endpoint, body))
                return _Response(payload={"id": "replacement", "properties": {"publishDetails": {"state": "Success"}}})

        fabric = Fabric()
        with patch.object(hds, "_event"), patch.object(hds.time, "sleep"):
            result = hds._deploy_environment(fabric, "workspace", hds.BUILD_ROOT)

        self.assertEqual(fabric.deleted, [("workspace", "orphan")])
        self.assertEqual(fabric.created[0][1], "/workspaces/workspace/environments")
        self.assertEqual(result["id"], "replacement")

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

            def request_raw(self, _method, _url):
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
