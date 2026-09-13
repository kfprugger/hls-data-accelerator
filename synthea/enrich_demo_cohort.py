"""Add deterministic reporting scenarios to existing synthetic patients without replacing them."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from uuid import UUID, uuid5

NAMESPACE = UUID("73590e85-86db-46ab-8a17-549b208963cc")
PROVENANCE_SYSTEM = "https://brakekat.com/hls/demo-provenance"


def resource_id(*parts: object) -> str:
    return str(uuid5(NAMESPACE, ":".join(map(str, parts))))


def build_resources(patients: list[dict], as_of: date) -> list[dict]:
    """FHIR resources are source inputs, explicitly tagged synthetic and safe to upsert by ID."""
    resources = []
    payer_types = [("Medicare", "MCR"), ("Medicaid", "MCD"), ("Commercial", "COMM")]
    for name, code in payer_types:
        resources.append({"resourceType": "Organization", "id": resource_id("payer", name), "active": True,
                          "name": f"Synthetic Demo {name}", "type": [{"coding": [{"code": "pay"}]}]})
    for index, patient in enumerate(sorted(patients, key=lambda p: p["id"])):
        patient_id = patient["id"]
        patient_ref = {"reference": f"Patient/{patient_id}"}
        payer_name, payer_code = payer_types[index % len(payer_types)]
        resources.append({"resourceType": "Coverage", "id": resource_id(patient_id, "coverage"), "status": "active",
                          "beneficiary": patient_ref, "payor": [{"reference": f"Organization/{resource_id('payer', payer_name)}", "display": f"Synthetic Demo {payer_name}"}],
                          "type": {"coding": [{"system": "http://terminology.hl7.org/CodeSystem/v3-ActCode", "code": payer_code, "display": payer_name}], "text": payer_name},
                          "period": {"start": f"{as_of.year}-01-01", "end": f"{as_of.year}-12-31"}})
        start = datetime.combine(as_of - timedelta(days=1 + index % 28), datetime.min.time(), tzinfo=timezone.utc) + timedelta(hours=14)
        resources.append({"resourceType": "Appointment", "id": resource_id(patient_id, "appointment"),
                          "status": "fulfilled" if index % 3 else "booked", "description": "Synthetic demo preventive-care outreach appointment",
                          "serviceType": [{"coding": [{"system": "http://snomed.info/sct", "code": "185349003", "display": "Encounter for check up"}]}],
                          "start": start.isoformat(), "end": (start + timedelta(minutes=30)).isoformat(),
                          "created": (start - timedelta(days=7)).isoformat(),
                          "participant": [{"actor": patient_ref, "status": "accepted"}]})
        # Qualifying scenarios are explicit synthetic clinical additions, not inferred diagnoses.
        if index >= 30:
            continue
        for code, name in [("44054006", "Type 2 diabetes mellitus"), ("59621000", "Essential hypertension")]:
            resources.append({"resourceType": "Condition", "id": resource_id(patient_id, "condition", code),
                              "clinicalStatus": {"coding": [{"system": "http://terminology.hl7.org/CodeSystem/condition-clinical", "code": "active"}]},
                              "verificationStatus": {"coding": [{"system": "http://terminology.hl7.org/CodeSystem/condition-ver-status", "code": "confirmed"}]},
                              "code": {"coding": [{"system": "http://snomed.info/sct", "code": code, "display": name}], "text": name},
                              "subject": patient_ref, "recordedDate": f"{as_of.year}-01-01"})
        months = range(1, as_of.month + 1) if index % 2 == 0 else range(1, as_of.month + 1, 2)
        for code, name in [("860975", "metformin 500 MG Oral Tablet"), ("314076", "lisinopril 10 MG Oral Tablet"), ("617314", "atorvastatin 20 MG Oral Tablet")]:
            for month in months:
                resources.append({"resourceType": "MedicationRequest", "id": resource_id(patient_id, "medication", code, as_of.year, month),
                                  "status": "active", "intent": "order", "subject": patient_ref,
                                  "authoredOn": f"{as_of.year}-{month:02d}-01",
                                  "medicationCodeableConcept": {"coding": [{"system": "http://www.nlm.nih.gov/research/umls/rxnorm", "code": code, "display": name}], "text": name},
                                  "dispenseRequest": {"expectedSupplyDuration": {"value": 30, "unit": "days", "system": "http://unitsofmeasure.org", "code": "d"}}})
    for resource in resources:
        resource["meta"] = {"tag": [{"system": PROVENANCE_SYSTEM, "code": "synthetic-demo-enrichment", "display": "Synthetic demo source; not an observed clinical event"}]}
    return resources


def transaction_bundles(resources: list[dict], batch_size: int = 200):
    if batch_size < 1 or batch_size > 400:
        raise ValueError("FHIR transaction batch size must be between 1 and 400")
    for offset in range(0, len(resources), batch_size):
        yield {"resourceType": "Bundle", "type": "transaction", "entry": [
            {"fullUrl": f"urn:uuid:{resource['id']}", "resource": resource,
             "request": {"method": "PUT", "url": f"{resource['resourceType']}/{resource['id']}"}}
            for resource in resources[offset:offset + batch_size]]}
