from __future__ import annotations

import json
import unittest
from unittest.mock import patch

import requests

from shared.fabric_client import FabricClient


def response(status=200, payload=None, headers=None):
    result = requests.Response()
    result.status_code = status
    result.url = "https://api.fabric.test/v1/items"
    result._content = json.dumps(payload or {}).encode()
    result.headers.update(headers or {})
    return result


class Clock:
    def __init__(self):
        self.now = 0.0
        self.sleeps = []

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


class FabricTransportTests(unittest.TestCase):
    def setUp(self):
        self.client = FabricClient.__new__(FabricClient)
        self.client.api_base = "https://api.fabric.test/v1"
        self.clock = Clock()
        self.enterContext(patch.object(self.client, "_headers", return_value={}))
        self.enterContext(patch("shared.fabric_client.time.monotonic", self.clock.monotonic))
        self.enterContext(patch("shared.fabric_client.time.sleep", self.clock.sleep))

    def invoke(self, entrypoint, method="GET", **kwargs):
        if entrypoint == "request_content":
            return self.client.request_content(method, "/items", b"payload", **kwargs)
        return getattr(self.client, entrypoint)(method, "/items", **kwargs)

    def test_reads_recover_from_transport_failure_with_bounded_attempts(self):
        for entrypoint in ("call", "request_raw", "request_content"):
            for error_type in (
                requests.ConnectionError,
                requests.exceptions.ChunkedEncodingError,
                requests.ReadTimeout,
            ):
                with self.subTest(entrypoint=entrypoint, error=error_type.__name__):
                    self.clock.sleeps.clear()
                    with patch("shared.fabric_client.requests.request", side_effect=[
                        error_type("response lost"), response(payload={"id": "existing"}),
                    ]) as send:
                        result = self.invoke(entrypoint)
                    payload = result if entrypoint == "call" else result.json()
                    self.assertEqual(payload["id"], "existing")
                    self.assertEqual(send.call_count, 2)
                    self.assertEqual(self.clock.sleeps, [5])
                    with patch("shared.fabric_client.requests.request", side_effect=error_type("offline")) as send:
                        with self.assertRaises(error_type):
                            self.invoke(entrypoint, max_retries=2)
                    self.assertEqual(send.call_count, 2)

    def test_real_http_rejection_and_tls_failure_are_not_network_retries(self):
        for entrypoint in ("call", "request_raw", "request_content"):
            for failure in (
                response(403, {"error": {"code": "InsufficientPrivileges"}}),
                requests.exceptions.SSLError("certificate rejected"),
            ):
                with self.subTest(entrypoint=entrypoint, failure=type(failure).__name__):
                    self.clock.sleeps.clear()
                    if isinstance(failure, requests.Response):
                        request_args = {"return_value": failure}
                        expected_error = requests.HTTPError
                    else:
                        request_args = {"side_effect": failure}
                        expected_error = requests.exceptions.SSLError
                    with patch("shared.fabric_client.requests.request", **request_args) as send:
                        with self.assertRaises(expected_error):
                            self.invoke(entrypoint)
                    self.assertEqual(send.call_count, 1)
                    self.assertEqual(self.clock.sleeps, [])

    def test_ambiguous_mutation_failures_never_duplicate_server_side_effects(self):
        for entrypoint in ("call", "request_raw", "request_content"):
            for failure in (
                requests.ConnectionError("connection reset after commit"),
                requests.ReadTimeout("response lost after commit"),
                requests.exceptions.ChunkedEncodingError("truncated response after commit"),
                response(503),
            ):
                with self.subTest(entrypoint=entrypoint, failure=type(failure).__name__):
                    committed = []

                    def commit_then_fail(*args, **kwargs):
                        committed.append("new-job")
                        if isinstance(failure, Exception):
                            raise failure
                        return failure

                    with patch("shared.fabric_client.requests.request", side_effect=commit_then_fail):
                        with self.assertRaises(requests.RequestException):
                            self.invoke(entrypoint, "POST")
                    self.assertEqual(committed, ["new-job"])

    def test_connect_timeout_can_retry_mutation_before_any_commit(self):
        for entrypoint in ("call", "request_raw", "request_content"):
            with self.subTest(entrypoint=entrypoint):
                attempts = []
                committed = []

                def send(*args, **kwargs):
                    attempts.append(None)
                    if len(attempts) == 1:
                        raise requests.ConnectTimeout("connection not established")
                    committed.append("new-job")
                    return response(201, {"id": "new-job"})

                with patch("shared.fabric_client.requests.request", side_effect=send):
                    result = self.invoke(entrypoint, "POST")
                payload = result if entrypoint == "call" else result.json()
                self.assertEqual(payload["id"], "new-job")
                self.assertEqual(committed, ["new-job"])

    def test_throttling_preserves_retry_after(self):
        for entrypoint in ("call", "request_raw", "request_content"):
            with self.subTest(entrypoint=entrypoint):
                self.clock.sleeps.clear()
                with patch("shared.fabric_client.requests.request", side_effect=[
                    response(429, headers={"Retry-After": "7"}),
                    response(201, {"id": "created"}),
                ]):
                    result = self.invoke(entrypoint, "POST")
                payload = result if entrypoint == "call" else result.json()
                self.assertEqual(payload["id"], "created")
                self.assertEqual(self.clock.sleeps, [7])

    def test_lro_poll_failure_does_not_replay_accepted_post(self):
        accepted = response(202, headers={"Location": "https://api.fabric.test/v1/operations/one", "Retry-After": "0"})
        committed = []

        def create(*args, **kwargs):
            committed.append("one")
            return accepted

        with (
            patch("shared.fabric_client.requests.request", side_effect=create),
            patch("shared.fabric_client.requests.get", side_effect=[
                requests.ReadTimeout("poll response lost"),
                response(payload={"status": "Succeeded"}),
            ]),
        ):
            result = self.client.call("POST", "/items")
        self.assertEqual(result["status"], "Succeeded")
        self.assertEqual(committed, ["one"])

    def test_lro_retry_after_cannot_schedule_request_after_deadline(self):
        accepted = response(202, headers={"Location": "https://api.fabric.test/v1/operations/one", "Retry-After": "100"})
        with patch("shared.fabric_client.requests.get") as get:
            with self.assertRaises(TimeoutError):
                self.client._poll_lro(accepted, timeout_seconds=3)
        self.assertEqual(get.call_count, 0)
        self.assertEqual(self.clock.now, 3)

    def test_lro_network_failures_and_late_success_cannot_escape_deadline(self):
        accepted = response(202, headers={"Location": "https://api.fabric.test/v1/operations/one", "Retry-After": "0"})
        with patch("shared.fabric_client.requests.get", side_effect=requests.ConnectionError("offline")) as get:
            with self.assertRaises(TimeoutError):
                self.client._poll_lro(accepted, timeout_seconds=3)
        self.assertEqual(get.call_count, 3)
        self.assertEqual(self.clock.now, 3)

        def late_success(*args, **kwargs):
            self.assertLessEqual(kwargs["timeout"], 3)
            self.clock.now += 4
            return response(payload={"status": "Succeeded"})

        with patch("shared.fabric_client.requests.get", side_effect=late_success):
            with self.assertRaises(TimeoutError):
                self.client._poll_lro(accepted, timeout_seconds=3)

    def test_job_poll_retry_after_and_network_backoff_share_overall_budget(self):
        for failure in (response(429, headers={"Retry-After": "100"}), requests.ReadTimeout("offline")):
            with self.subTest(failure=type(failure).__name__):
                self.clock.now = 0

                def send(*args, **kwargs):
                    self.assertLessEqual(kwargs["timeout"], 3)
                    if isinstance(failure, Exception):
                        self.clock.now += 2
                        raise failure
                    return failure

                with patch("shared.fabric_client.requests.request", side_effect=send) as request:
                    with self.assertRaises(TimeoutError):
                        self.client.wait_for_item_job("https://api.fabric.test/v1/jobs/one", timeout_seconds=3)
                self.assertEqual(request.call_count, 1)
                self.assertEqual(self.clock.now, 3)

    def test_deduped_job_remains_failure(self):
        with patch("shared.fabric_client.requests.request", return_value=response(payload={"status": "Deduped"})):
            with self.assertRaises(RuntimeError):
                self.client.wait_for_item_job("https://api.fabric.test/v1/jobs/one", timeout_seconds=3)


if __name__ == "__main__":
    unittest.main()
