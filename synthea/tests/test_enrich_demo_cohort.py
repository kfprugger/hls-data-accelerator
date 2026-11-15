from __future__ import annotations

from datetime import date
from pathlib import Path
import sys
import unittest

SYNTHEA_DIR = Path(__file__).resolve().parents[1]
if str(SYNTHEA_DIR) not in sys.path:
    sys.path.insert(0, str(SYNTHEA_DIR))

from enrich_demo_cohort import build_resources


class EnrichDemoCohortLocationTests(unittest.TestCase):
    def test_each_appointment_has_location_participant_resolving_to_generated_location(self):
        patients = [{"id": f"pt-{i:03d}"} for i in range(10)]
        resources = build_resources(patients, date(2026, 10, 5))

        locations_by_id = {
            r["id"]: r for r in resources if r.get("resourceType") == "Location"
        }
        self.assertGreater(len(locations_by_id), 0, "Bundle must contain generated Location resources")

        appointments = [r for r in resources if r.get("resourceType") == "Appointment"]
        self.assertEqual(len(appointments), 10, "Should generate one appointment per patient")

        for appt in appointments:
            participants = appt.get("participant", [])
            location_participants = [
                p for p in participants
                if (p.get("actor", {}).get("type") == "Location" or
                    str(p.get("actor", {}).get("reference", "")).startswith("Location/"))
            ]
            self.assertEqual(
                len(location_participants), 1,
                f"Appointment {appt['id']} must have exactly one Location participant, found: {participants}"
            )
            loc_ref = location_participants[0]["actor"]["reference"]
            loc_id = loc_ref.split("/", 1)[1]
            self.assertIn(
                loc_id, locations_by_id,
                f"Location reference {loc_ref} must resolve to a generated Location in the bundle"
            )


if __name__ == "__main__":
    unittest.main()
