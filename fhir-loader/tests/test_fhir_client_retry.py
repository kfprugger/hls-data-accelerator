from __future__ import annotations

import builtins
import json
import threading
import unittest
from unittest.mock import patch
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
import sys

FHIR_LOADER_DIR = Path(__file__).resolve().parents[1]
if str(FHIR_LOADER_DIR) not in sys.path:
    sys.path.insert(0, str(FHIR_LOADER_DIR))

# Mock /app/*.json before importing load_fhir
original_open = builtins.open


def fake_open(path, *args, **kwargs):
    if path == "/app/device_registry.json":
        return original_open(FHIR_LOADER_DIR / "device_registry.json", *args, **kwargs)
    if path == "/app/atlanta_providers.json":
        return original_open(FHIR_LOADER_DIR / "atlanta_providers.json", *args, **kwargs)
    return original_open(path, *args, **kwargs)


builtins.open = fake_open
try:
    import requests
    import load_fhir
    from load_fhir import FHIRClient
finally:
    builtins.open = original_open


class StubFhirHandler(BaseHTTPRequestHandler):
    responses_queue: list[tuple[int, dict | str]] = []
    received_requests: list[dict] = []
    lock = threading.Lock()

    def log_message(self, format, *args):
        pass  # Quiet test output

    def _handle(self):
        with self.lock:
            self.received_requests.append({
                "method": self.command,
                "path": self.path,
                "headers": dict(self.headers),
            })
            if self.responses_queue:
                status, body = self.responses_queue.pop(0)
            else:
                status, body = 200, {"total": 0}

        if isinstance(body, dict):
            payload = json.dumps(body).encode("utf-8")
            content_type = "application/fhir+json"
        else:
            payload = body.encode("utf-8")
            content_type = "text/plain"

        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    do_GET = _handle
    do_POST = _handle
    do_PUT = _handle
    do_DELETE = _handle


class FhirClientRetryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = HTTPServer(("127.0.0.1", 0), StubFhirHandler)
        cls.server_thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.server_thread.start()
        cls.port = cls.server.server_address[1]
        cls.base_url = f"http://127.0.0.1:{cls.port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        with StubFhirHandler.lock:
            StubFhirHandler.responses_queue.clear()
            StubFhirHandler.received_requests.clear()
        self.client = FHIRClient(self.base_url)
        self.client.access_token = "fake-test-token"
        self.client.token_expiry = datetime.now() + timedelta(hours=1)

    def test_transient_503_twice_then_200_succeeds(self):
        with StubFhirHandler.lock:
            StubFhirHandler.responses_queue = [
                (503, "Service Unavailable"),
                (503, "Service Unavailable"),
                (200, {"total": 42}),
            ]

        # In a client without retry, the first 503 triggers raise_for_status() and fails.
        # With HTTPAdapter Retry, it retries and succeeds on the 3rd attempt.
        count = self.client.get_count("Patient")
        self.assertEqual(count, 42)
        with StubFhirHandler.lock:
            self.assertEqual(len(StubFhirHandler.received_requests), 3)

    def test_non_retryable_400_fails_fast_without_retries(self):
        with StubFhirHandler.lock:
            StubFhirHandler.responses_queue = [
                (400, "Bad Request: invalid resourceType"),
            ]

        with self.assertRaises(requests.exceptions.HTTPError) as ctx:
            self.client.post_resource({"resourceType": "InvalidResource"})

        self.assertEqual(ctx.exception.response.status_code, 400)
        with StubFhirHandler.lock:
            self.assertEqual(len(StubFhirHandler.received_requests), 1)


    def test_get_count_raises_on_http_403(self):
        """R-2: FHIRClient.get_count raises HTTPError on 403 response."""
        with StubFhirHandler.lock:
            StubFhirHandler.responses_queue = [
                (403, {"resourceType": "OperationOutcome", "issue": [{"severity": "error", "code": "forbidden"}]}),
            ]

        with self.assertRaises(requests.exceptions.HTTPError) as ctx:
            self.client.get_count("Patient")

        self.assertEqual(ctx.exception.response.status_code, 403)
        with StubFhirHandler.lock:
            self.assertEqual(len(StubFhirHandler.received_requests), 1)

    def test_search_raises_on_http_403(self):
        """R-2: FHIRClient.search raises HTTPError on 403 response."""
        with StubFhirHandler.lock:
            StubFhirHandler.responses_queue = [
                (403, {"resourceType": "OperationOutcome", "issue": [{"severity": "error", "code": "forbidden"}]}),
            ]

        with self.assertRaises(requests.exceptions.HTTPError) as ctx:
            self.client.search("Location")

        self.assertEqual(ctx.exception.response.status_code, 403)
        with StubFhirHandler.lock:
            self.assertEqual(len(StubFhirHandler.received_requests), 1)

    def test_search_returns_entries_and_feeds_location_cache(self):
        """search() returns Bundle entries; fetch_existing_locations maps them for reuse."""
        bundle = {
            "resourceType": "Bundle",
            "entry": [
                {"resource": {
                    "resourceType": "Location",
                    "id": "existing-loc-1",
                    "identifier": [{"system": "https://github.com/synthetichealth/synthea", "value": "loc-001"}],
                }},
                {"resource": {"resourceType": "Location", "identifier": [{"system": "s", "value": "no-id"}]}},
            ],
        }
        with StubFhirHandler.lock:
            StubFhirHandler.responses_queue = [(200, bundle), (200, bundle)]

        self.assertEqual(self.client.search("Location"), bundle["entry"])
        self.assertEqual(
            load_fhir.fetch_existing_locations(self.client),
            {"Location?identifier=https://github.com/synthetichealth/synthea|loc-001": "Location/existing-loc-1"},
        )

    def test_search_returns_empty_list_for_bundle_without_entries(self):
        with StubFhirHandler.lock:
            StubFhirHandler.responses_queue = [(200, {"resourceType": "Bundle", "total": 0})]

        self.assertEqual(self.client.search("Location"), [])

    def test_main_readiness_loop_retries_on_http_403(self):
        """R-2: main() readiness loop retries on 403 instead of passing/breaking on attempt 0."""
        with StubFhirHandler.lock:
            StubFhirHandler.responses_queue = [
                (403, {"resourceType": "OperationOutcome", "issue": [{"severity": "error", "code": "forbidden"}]}),
                (403, {"resourceType": "OperationOutcome", "issue": [{"severity": "error", "code": "forbidden"}]}),
                (200, {"total": 42}),
            ]

        with patch.object(load_fhir, "FHIR_SERVICE_URL", self.base_url), \
             patch.object(FHIRClient, "_get_token", return_value="fake-token"), \
             patch("load_fhir.time.sleep") as mock_sleep, \
             patch("load_fhir.load_canonical_manifest", side_effect=RuntimeError("stop_after_readiness")):
            try:
                load_fhir.main()
            except RuntimeError as exc:
                self.assertEqual(str(exc), "stop_after_readiness")

            self.assertEqual(mock_sleep.call_count, 2)
            mock_sleep.assert_called_with(10)
            with StubFhirHandler.lock:
                self.assertEqual(len(StubFhirHandler.received_requests), 3)

if __name__ == "__main__":
    unittest.main()
