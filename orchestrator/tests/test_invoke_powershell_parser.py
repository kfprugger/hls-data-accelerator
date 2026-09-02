from __future__ import annotations

import importlib
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


_MISSING = object()


class FakePowerShellProcess:
    def __init__(self, stdout_lines) -> None:
        self.stdout = iter(stdout_lines)
        self.pid = 12345
        self.returncode = 0

    def poll(self):
        return None

    def wait(self) -> int:
        return self.returncode


class CompletedWaitRaceProcess(FakePowerShellProcess):
    def wait(self) -> int:
        self.returncode = 0
        raise OSError(22, "bad parameter or other API misuse")


class HeartbeatAfterFirstLineStdout:
    def __init__(self, first_line: str, trigger_heartbeat) -> None:
        self._first_line = first_line
        self._trigger_heartbeat = trigger_heartbeat
        self._sent_first_line = False
        self._triggered = False

    def __iter__(self):
        return self

    def __next__(self) -> str:
        if not self._sent_first_line:
            self._sent_first_line = True
            return self._first_line
        if not self._triggered:
            self._triggered = True
            self._trigger_heartbeat()
        raise StopIteration


class ControlledHeartbeatEvent:
    def __init__(self) -> None:
        self.wait_calls = 0
        self.set_called = False

    def wait(self, _timeout: float) -> bool:
        self.wait_calls += 1
        return self.wait_calls > 1

    def set(self) -> None:
        self.set_called = True


class InvokePowershellParserTests(unittest.TestCase):
    def setUp(self) -> None:
        self._orchestrator_dir = str(Path(__file__).resolve().parents[1])
        self._inserted_path = False
        if self._orchestrator_dir not in sys.path:
            sys.path.insert(0, self._orchestrator_dir)
            self._inserted_path = True

        self._saved_modules = {
            name: sys.modules.get(name, _MISSING)
            for name in (
                "activities",
                "activities.invoke_powershell",
                "shared",
                "shared.policy_tags",
            )
        }
        shared_module = sys.modules.get("shared")
        self._saved_shared_policy_tags_attr = (
            getattr(shared_module, "policy_tags", _MISSING)
            if shared_module is not None
            else _MISSING
        )
        sys.modules.pop("activities.invoke_powershell", None)
        self.addCleanup(self._cleanup_imports)

        self.invoke_powershell = importlib.import_module("activities.invoke_powershell")

    def _cleanup_imports(self) -> None:
        for module_name, module in self._saved_modules.items():
            if module is _MISSING:
                sys.modules.pop(module_name, None)
            else:
                sys.modules[module_name] = module
        shared_module = sys.modules.get("shared")
        if shared_module is not None:
            if self._saved_shared_policy_tags_attr is _MISSING:
                if hasattr(shared_module, "policy_tags"):
                    delattr(shared_module, "policy_tags")
            else:
                setattr(
                    shared_module,
                    "policy_tags",
                    self._saved_shared_policy_tags_attr,
                )
        if self._inserted_path:
            sys.path.remove(self._orchestrator_dir)

    def parse_lines(self, *lines: str) -> list[tuple[str, str, str, str]]:
        events: list[tuple[str, str, str, str]] = []
        process = FakePowerShellProcess([f"{line}\n" for line in lines])

        with patch.object(
            self.invoke_powershell.subprocess,
            "Popen",
            return_value=process,
        ):
            exit_code = self.invoke_powershell._run_powershell(
                ["pwsh", "-NoProfile", "-Command", "Deploy-All.ps1"],
                lambda *event: events.append(event),
            )

        self.assertEqual(exit_code, 0)
        return events

    def test_quiet_running_step_emits_heartbeat_before_next_powershell_line(self) -> None:
        events: list[tuple[str, str, str, str]] = []
        captured_thread_target = {}
        created_events: list[ControlledHeartbeatEvent] = []

        def trigger_heartbeat() -> None:
            target = captured_thread_target.get("target")
            if target is None:
                raise AssertionError("heartbeat thread was not started")
            target()

        process = FakePowerShellProcess(
            HeartbeatAfterFirstLineStdout(
                "|  STEP 2: Fabric RTI Enrichment  |\n",
                trigger_heartbeat,
            )
        )

        class CapturedThread:
            def __init__(self, target, daemon: bool = False) -> None:
                captured_thread_target["target"] = target
                self.daemon = daemon

            def start(self) -> None:
                pass

            def join(self, timeout=None) -> None:
                captured_thread_target["join_timeout"] = timeout

        def event_factory() -> ControlledHeartbeatEvent:
            event = ControlledHeartbeatEvent()
            created_events.append(event)
            return event

        monotonic_values = iter([100.0, 101.0, 132.0])

        def fake_monotonic() -> float:
            return next(monotonic_values)

        with self.assertLogs(self.invoke_powershell.logger, level="INFO") as logs:
            with (
                patch.object(self.invoke_powershell.subprocess, "Popen", return_value=process),
                patch.object(self.invoke_powershell.threading, "Thread", new=CapturedThread),
                patch.object(self.invoke_powershell.threading, "Event", new=event_factory),
                patch.object(self.invoke_powershell.time, "monotonic", new=fake_monotonic),
            ):
                exit_code = self.invoke_powershell._run_powershell(
                    ["pwsh", "-NoProfile", "-Command", "Deploy-All.ps1"],
                    lambda *event: events.append(event),
                )

        self.assertEqual(exit_code, 0)
        self.assertIn(("step_start", "Fabric RTI Enrichment", "", ""), events)
        self.assertEqual(created_events[0].wait_calls, 2)
        self.assertTrue(created_events[0].set_called)
        self.assertIn(
            "Still running Fabric RTI Enrichment — waiting for PowerShell output (31s quiet)",
            "\n".join(logs.output),
        )

    def assert_sidecar_warning_substep(
        self,
        events: list[tuple[str, str, str, str]],
        *,
        sidecar_name: str,
        source_line: str,
        duration: str,
        expected_warning_detail: str,
        expected_substep_status: str,
    ) -> None:
        self.assertIn(
            ("step_warning", sidecar_name, expected_warning_detail, duration),
            events,
        )
        self.assertFalse(
            any(
                event == "step_failed" and step_name == sidecar_name
                for event, step_name, _detail, _duration in events
            ),
            events,
        )

        matching_substeps = [
            event
            for event in events
            if event[0] == "substep_update" and event[1] == sidecar_name
        ]
        self.assertEqual(len(matching_substeps), 1, events)
        _event, _step_name, payload_json, substep_duration = matching_substeps[0]
        self.assertEqual(substep_duration, duration)
        self.assertEqual(
            json.loads(payload_json),
            {"status": expected_substep_status, "detail": source_line},
        )

    def test_sidecar_pipeline_with_display_name_is_hds_substep(self) -> None:
        self.assertTrue(
            self.invoke_powershell.is_hds_pipeline_substep(
                "Sidecar Pipeline: healthcare1_msft_sdoh_ingestion"
            )
        )

    def test_failed_sidecar_result_and_summary_lines_are_non_blocking_substeps(
        self,
    ) -> None:
        sidecar_name = "Sidecar Pipeline: healthcare1_msft_sdoh_ingestion"
        cases = [
            {
                "name": "dash result line",
                "line": f"✗ {sidecar_name} - 0.4 min",
                "duration": "0.4 min",
                "warning_detail": "",
                "substep_status": "warning",
            },
            {
                "name": "status summary row",
                "line": f"✗ {sidecar_name}  Failed: trigger unavailable  12 sec",
                "duration": "12 sec",
                "warning_detail": f"✗ {sidecar_name}  Failed: trigger unavailable  12 sec",
                "substep_status": "failed",
            },
        ]

        for case in cases:
            with self.subTest(case=case["name"]):
                line = case["line"]
                events = self.parse_lines(line)

                self.assert_sidecar_warning_substep(
                    events,
                    sidecar_name=sidecar_name,
                    source_line=line,
                    duration=case["duration"],
                    expected_warning_detail=case["warning_detail"],
                    expected_substep_status=case["substep_status"],
                )


    def test_successful_sidecar_summary_does_not_create_warning_name(self) -> None:
        sidecar_name = "Sidecar Pipeline: healthcare1_msft_claims_data_ingestion"
        for raw_status in ("COMPLETED", "INVOKED"):
            with self.subTest(raw_status=raw_status):
                line = f"✓  {sidecar_name} {raw_status}       12.4 min"
                events = self.parse_lines(line)
                updates = [event for event in events if event[0] == "substep_update"]
                warnings = [event for event in events if event[0] == "step_warning"]

                self.assertGreaterEqual(len(updates), 1, events)
                self.assertTrue(all(update[1] == sidecar_name for update in updates), events)
                self.assertEqual(json.loads(updates[-1][2])["status"], "succeeded")
                self.assertEqual(warnings, [])

    def test_reuse_fabric_rti_does_not_emit_skip_fabric(self) -> None:
        args = self.invoke_powershell._build_deploy_args({
            "fabric_workspace_name": "med-test",
            "reuse_fabric_rti": True,
            "skip_fabric": False,
        })

        command = " ".join(args)
        self.assertIn("-ReuseFabricRti", command)
        self.assertNotIn("-SkipFabric", command)

    def test_hds_source_skip_preserves_pipeline_execution(self) -> None:
        args = self.invoke_powershell._build_deploy_args({
            "fabric_workspace_name": "med-test",
            "skip_hds_source": True,
            "skip_hds_pipelines": False,
        })

        command = " ".join(args)
        self.assertIn("-SkipHdsSource", command)
        self.assertNotIn("-SkipHdsPipelines", command)

    def test_scaffolding_only_is_forwarded_to_deploy_all(self) -> None:
        for tags in ({}, {"Owner": "Clinical Ops"}):
            with self.subTest(tags=tags):
                args = self.invoke_powershell._build_deploy_args({
                    "fabric_workspace_name": "med-test",
                    "scaffolding_only": True,
                    "tags": tags,
                })

                self.assertIn("-ScaffoldingOnly", " ".join(args))


    def test_reseed_data_is_forwarded_in_file_and_tagged_command_modes(self) -> None:
        for tags in ({}, {"Owner": "Clinical Ops"}):
            with self.subTest(tags=tags):
                args = self.invoke_powershell._build_deploy_args({
                    "fabric_workspace_name": "med-test",
                    "reseed_data": True,
                    "tags": tags,
                })

                command = " ".join(args)
                self.assertIn("-ReseedData", command)
                self.assertNotIn("-ReusePatients", command)

    def test_reseed_data_defaults_to_omitted_switch(self) -> None:
        args = self.invoke_powershell._build_deploy_args({
            "fabric_workspace_name": "med-test",
        })

        self.assertNotIn("-ReseedData", " ".join(args))

    def test_reseed_and_reuse_are_rejected_before_powershell_launch(self) -> None:
        with self.assertRaisesRegex(ValueError, "mutually exclusive"):
            self.invoke_powershell._build_deploy_args({
                "fabric_workspace_name": "med-test",
                "reuse_patients": True,
                "reseed_data": True,
            })

    def test_hds_source_marker_emits_substep(self) -> None:
        events = self.parse_lines("@@HDS_SOURCE|upload|succeeded|42 files@@")
        self.assertIn(
            (
                "substep_update",
                "HDS Source: upload",
                '{"status": "succeeded", "detail": "42 files"}',
                "",
            ),
            events,
        )

    def test_hds_source_marker_preserves_origin_timing_metadata(self) -> None:
        marker_payload = json.dumps({
            "detail": "42 files",
            "emittedAt": "2026-08-02T14:00:02Z",
            "startedAt": "2026-08-02T14:00:00Z",
            "finishedAt": "2026-08-02T14:00:02Z",
            "elapsedSeconds": 2.0,
            "attempt": 1,
            "jobId": "job-42",
        }, separators=(",", ":"))
        events = self.parse_lines(f"@@HDS_SOURCE|upload|succeeded|{marker_payload}@@")

        event = next(item for item in events if item[0] == "substep_update")
        parsed_payload = json.loads(event[2])
        self.assertEqual(parsed_payload["detail"], "42 files")
        self.assertEqual(parsed_payload["startedAt"], "2026-08-02T14:00:00Z")
        self.assertEqual(parsed_payload["finishedAt"], "2026-08-02T14:00:02Z")
        self.assertEqual(parsed_payload["elapsedSeconds"], 2.0)
        self.assertEqual(parsed_payload["jobId"], "job-42")

    def test_completed_process_wait_race_preserves_exit_code(self) -> None:
        process = CompletedWaitRaceProcess(["deployment complete\n"])
        with patch.object(self.invoke_powershell.subprocess, "Popen", return_value=process):
            exit_code = self.invoke_powershell._run_powershell(
                ["pwsh", "-NoProfile", "-Command", "Deploy-All.ps1"]
            )

        self.assertEqual(exit_code, 0)

if __name__ == "__main__":
    unittest.main()
