import base64
import json
import subprocess
import threading
import time
import unittest

from shared.live_credentials import LiveCredentialProbe

TENANT, OTHER, SUB, NOW = "tenant-a", "tenant-b", "sub-1", 1_000_000.0


def jwt(tid=TENANT, exp=NOW + 3600):
    body = base64.urlsafe_b64encode(json.dumps({"tid": tid, "exp": exp, "upn": "u@example.com"}).encode()).decode().rstrip("=")
    return f"h.{body}.SIGNATURE-SECRET"


def done(stdout="", code=0, stderr=""):
    return subprocess.CompletedProcess([], code, stdout, stderr)


class Probe(unittest.TestCase):
    def probe(self, cli_token=lambda resource: jwt(), pwsh=lambda: done(json.dumps({"tid": TENANT, "exp": NOW + 3600})), api_status=200):
        def run(args, **kwargs):
            if args[0] == "pwsh":
                return pwsh()
            if args[:3] == ["az", "account", "show"]:
                return done(json.dumps({"id": SUB, "tenantId": TENANT, "name": "S", "user": {"name": "u@example.com"}}))
            resource = args[args.index("--resource") + 1]
            token = cli_token(resource)
            return token if isinstance(token, subprocess.CompletedProcess) else done(json.dumps({"accessToken": token}))
        bodies = {"subscriptions": {"state": "Enabled", "tenantId": TENANT}, "workspaces": {"value": []}, "me": {"id": "oid"}}
        fetch = lambda method, url, headers: (api_status, next(b for k, b in bodies.items() if k in url))
        return LiveCredentialProbe(run=run, fetch=fetch, clock=lambda: NOW).probe(SUB)

    def failed(self, result):
        return {c["name"]: c["detail"] for c in result["checks"] if c["status"] == "fail"}

    def test_valid_credentials_pass_every_audience_and_call(self):
        result = self.probe()
        self.assertTrue(result["ok"], self.failed(result))
        names = [c["name"] for c in result["checks"]]
        for expected in ("Azure CLI Databricks token", "Az PowerShell Fabric token", "ARM subscription read", "Graph identity read"):
            self.assertIn(expected, names)

    def test_token_from_another_tenant_fails_that_audience_only(self):
        result = self.probe(cli_token=lambda r: jwt(tid=OTHER) if r.startswith("2ff8") else jwt())
        self.assertFalse(result["ok"])
        self.assertEqual(list(self.failed(result)), ["Azure CLI Databricks token"])
        self.assertIn("is not the subscription tenant", self.failed(result)["Azure CLI Databricks token"])

    def test_token_about_to_expire_fails(self):
        result = self.probe(pwsh=lambda: done(json.dumps({"tid": TENANT, "exp": NOW + 60})))
        self.assertEqual(set(self.failed(result)), {"Az PowerShell ARM token", "Az PowerShell Fabric token"})

    def test_cached_login_that_cannot_mint_a_token_fails_and_skips_dependent_call(self):
        result = self.probe(cli_token=lambda r: done(code=1, stderr="AADSTS70043: refresh token expired") if "graph" in r else jwt())
        failed = self.failed(result)
        self.assertIn("AADSTS70043", failed["Azure CLI Graph token"])
        self.assertEqual(failed["Graph identity read"], "skipped: no Graph token")

    def test_service_rejection_fails_even_with_valid_tokens(self):
        self.assertEqual({"ARM subscription read", "Fabric workspace list", "Graph identity read"}, set(self.failed(self.probe(api_status=403))))

    def test_calls_to_one_tool_never_overlap_because_they_share_a_token_cache(self):
        running, overlaps, lock = {"az": 0, "pwsh": 0}, [], threading.Lock()
        def run(args, **kwargs):
            tool = args[0]
            with lock:
                running[tool] += 1
                if running[tool] > 1:
                    overlaps.append(tool)
            time.sleep(0.01)
            with lock:
                running[tool] -= 1
            if tool == "pwsh":
                return done(json.dumps({"tid": TENANT, "exp": NOW + 3600}))
            if args[:3] == ["az", "account", "show"]:
                return done(json.dumps({"id": SUB, "tenantId": TENANT, "name": "S", "user": {"name": "u"}}))
            return done(json.dumps({"accessToken": jwt()}))
        fetch = lambda method, url, headers: (200, {"state": "Enabled", "tenantId": TENANT, "value": [], "id": "x"})
        self.assertTrue(LiveCredentialProbe(run=run, fetch=fetch, clock=lambda: NOW).probe(SUB)["ok"])
        self.assertEqual(overlaps, [])

    def test_result_never_contains_a_token(self):
        self.assertNotIn("SIGNATURE-SECRET", json.dumps(self.probe()))


if __name__ == "__main__":
    unittest.main()
