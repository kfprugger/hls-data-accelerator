import unittest

from monitor_blocking_errors import blocking_messages


class MonitorBlockingErrorsTests(unittest.TestCase):
    def test_expected_metadata_readiness_retry_is_not_blocking(self) -> None:
        deployment = {
            "runtimeStatus": "Running",
            "customStatus": {
                "status": "running",
                "currentPhase": "PHASE 3: IMAGING & REPORTING",
                "logs": [
                    {
                        "level": "success",
                        "message": (
                            "Reporting SQL metadata not ready (attempt 3/20): "
                            "Traceback: Invalid object name 'dbo.DicomFileReporting'"
                        ),
                    }
                ],
            },
        }

        self.assertEqual(blocking_messages(deployment, include_warning_logs=True), [])

    def test_unexpected_traceback_remains_blocking(self) -> None:
        deployment = {
            "runtimeStatus": "Running",
            "customStatus": {
                "status": "running",
                "currentPhase": "Deploying",
                "logs": [{"level": "info", "message": "Traceback (most recent call last): boom"}],
            },
        }

        self.assertEqual(len(blocking_messages(deployment)), 1)


if __name__ == "__main__":
    unittest.main()
