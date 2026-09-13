"""Deterministic synthetic Dynamics-style source rows consumed by the native HDS IDM adapter."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from enrich_demo_cohort import resource_id


def build_outreach_sources(patients: list[dict], as_of: date) -> dict[str, list[dict]]:
    stamp = datetime.combine(as_of - timedelta(days=30), datetime.min.time(), tzinfo=timezone.utc).isoformat()
    journey = resource_id("outreach", "journey")
    email = resource_id("outreach", "email")
    service = resource_id("outreach", "service")
    tables = {
        "contact_partitioned": [],
        "msemr_codeableconcept_partitioned": [{"msemr_codeableconceptid": service, "msemr_code": "185349003"}],
        "msdynmkt_journey_partitioned": [{"msdynmkt_journeyid": journey, "msdynmkt_baseversionjourneyid": journey,
            "msdynmkt_journeystarttime": stamp, "msdynmkt_journeyendtime": stamp, "msdynmkt_name": "Synthetic preventive-care outreach",
            "modifiedon": stamp, "msdynmkt_versionnumber": 1, "statuscode": 1, "statecode": 1, "createdon": stamp, "msemr_serviceline": service}],
        "msdynmkt_email_partitioned": [{"Id": email, "msdynmkt_subject": "Synthetic check-up reminder", "msdynmkt_name": "Synthetic demo appointment reminder",
            "statuscode": 1, "msdynmkt_fromname": "Synthetic Care Team", "msdynmkt_replytoemail": "noreply@example.invalid",
            "msdynmkt_emailcontentlanguage": 1033, "msdynmkt_fromemail": "noreply@example.invalid", "statecode": 0, "modifiedon": stamp, "createdon": stamp}],
        "msdynmkt_journeyinstance_partitioned": [],
        "emailsent": [],
        "emailopened": [],
    }
    for index, patient in enumerate(sorted(patients, key=lambda p: p["id"])):
        contact = resource_id(patient["id"], "outreach-contact")
        instance = resource_id(patient["id"], "journey-instance")
        tables["contact_partitioned"].append({"contactid": contact, "modifiedon": stamp, "msemr_azurefhirid": patient["id"]})
        tables["msdynmkt_journeyinstance_partitioned"].append({"modifiedon": stamp, "createdon": stamp, "msdynmkt_journeyinstancestate": 1,
            "msdynmkt_journeydefinitionid": journey, "msdynmkt_journeyinstanceid": instance, "msdynmkt_targetentity": "contact", "msdynmkt_targetid": contact})
        for event_type in (["emailsent", "emailopened"] if index % 3 else ["emailsent"]):
            event_id = resource_id(patient["id"], event_type)
            tables[event_type].append({"Timestamp": stamp, "IdempotencyId": event_id, "InternalMarketingInteractionId": event_id,
                "ProfileId": contact, "ProfileType": "contact", "CustomerJourneyId": journey, "MessageId": email,
                "JourneyRunId": instance, "JourneyActionId": resource_id(journey, "email-action"), "OrganizationId": resource_id("outreach", "organization")})
    for rows in tables.values():
        for row in rows:
            row["scenario_source"] = "synthetic-demo-enrichment"
    return tables
