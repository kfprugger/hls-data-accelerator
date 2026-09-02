#!/usr/bin/env python3
"""Generate the deterministic canonical healthcare fixture used by deployments."""
from __future__ import annotations

import hashlib
import json
import random
import shutil
import uuid
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

FIXTURE_VERSION = "1.0.0"
AS_OF_DATE = datetime(2026, 7, 1, 12, 0, tzinfo=timezone.utc)
FIXTURE_NAMESPACE = uuid.UUID("7f3f0f14-c8f2-4a57-8d44-a1306fa8cb8e")
PATIENT_COUNT = 100

ATLANTA_HOSPITALS = [
    "emory-university-hospital", "piedmont-atlanta-hospital", "grady-memorial-hospital",
    "northside-hospital", "wellstar-kennestone-hospital", "choa-egleston",
    "choa-scottish-rite", "choa-hughes-spalding",
]
ATLANTA_HOSPITAL_ZIPS = {
    "emory-university-hospital": "30322", "piedmont-atlanta-hospital": "30309",
    "grady-memorial-hospital": "30303", "northside-hospital": "30342",
    "wellstar-kennestone-hospital": "30060", "choa-egleston": "30322",
    "choa-scottish-rite": "30342", "choa-hughes-spalding": "30303",
}

CONDITIONS = [
    ("44054006", "Type 2 diabetes mellitus"),
    ("59621000", "Essential hypertension"),
    ("84114007", "Heart failure"),
    ("13645005", "Chronic obstructive lung disease"),
    ("195967001", "Asthma"),
    ("162864005", "Body mass index 30+ - obesity"),
    ("233604007", "Pneumonia"),
    ("433144002", "Chronic kidney disease stage 3"),
    ("36923009", "Major depressive disorder"),
    ("254637007", "Lung cancer"),
]

PAYER_PROFILES = [
    {"id": "payer-medicare", "name": "Medicare", "category": "Medicare", "type_code": "EHCPOL", "type_display": "Medicare policy"},
    {"id": "payer-medicaid", "name": "Georgia Medicaid", "category": "Medicaid", "type_code": "MCPOL", "type_display": "Medicaid managed care"},
    {"id": "payer-commercial", "name": "BrakeKat Synthetic Commercial", "category": "Commercial", "type_code": "HIP", "type_display": "Commercial health plan"},
    {"id": "payer-uninsured", "name": "Self Pay", "category": "Uninsured", "type_code": "SELF-PAY", "type_display": "Self pay"},
]

RACE_ETHNICITY_PROFILES = [
    {"race_code": "2106-3", "race_display": "White", "ethnicity_code": "2186-5", "ethnicity_display": "Not Hispanic or Latino"},
    {"race_code": "2054-5", "race_display": "Black or African American", "ethnicity_code": "2186-5", "ethnicity_display": "Not Hispanic or Latino"},
    {"race_code": "2028-9", "race_display": "Asian", "ethnicity_code": "2186-5", "ethnicity_display": "Not Hispanic or Latino"},
    {"race_code": "2076-8", "race_display": "Native Hawaiian or Other Pacific Islander", "ethnicity_code": "2186-5", "ethnicity_display": "Not Hispanic or Latino"},
    {"race_code": "2106-3", "race_display": "White", "ethnicity_code": "2135-2", "ethnicity_display": "Hispanic or Latino"},
]

FIRST_NAMES = ["Alex", "Blake", "Casey", "Devon", "Emery", "Frankie", "Gray", "Harper", "Indigo", "Jordan"]
LAST_NAMES = ["Adams", "Brooks", "Chen", "Diaz", "Evans", "Foster", "Green", "Hayes", "Irwin", "Jones"]

PDC_MEDICATIONS = [
    ("860975", "Metformin 500 MG Oral Tablet", "PDC-DR"),
    ("314076", "Lisinopril 10 MG Oral Tablet", "PDC-RASA"),
    ("617314", "Atorvastatin 20 MG Oral Tablet", "PDC-STA"),
]


def stable_uuid(kind: str, *parts: object) -> str:
    return str(uuid.uuid5(FIXTURE_NAMESPACE, ":".join([kind, *(str(part) for part in parts)])))


def iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def entry(resource: dict[str, Any]) -> dict[str, Any]:
    return {"fullUrl": f"urn:uuid:{resource['id']}", "resource": resource}


def patient_demographic_extensions(idx: int) -> list[dict[str, Any]]:
    profile = RACE_ETHNICITY_PROFILES[idx % len(RACE_ETHNICITY_PROFILES)]
    race_code, race_display = profile["race_code"], profile["race_display"]
    ethnicity_code, ethnicity_display = profile["ethnicity_code"], profile["ethnicity_display"]
    return [
        {
            "url": "http://hl7.org/fhir/us/core/StructureDefinition/us-core-race",
            "extension": [
                {"url": "ombCategory", "valueCoding": {"system": "urn:oid:2.16.840.1.113883.6.238", "code": race_code, "display": race_display}},
                {"url": "text", "valueString": race_display},
            ],
        },
        {
            "url": "http://hl7.org/fhir/us/core/StructureDefinition/us-core-ethnicity",
            "extension": [
                {"url": "ombCategory", "valueCoding": {"system": "urn:oid:2.16.840.1.113883.6.238", "code": ethnicity_code, "display": ethnicity_display}},
                {"url": "text", "valueString": ethnicity_display},
            ],
        },
    ]


def patient_resource(idx: int, patient_id: str) -> dict[str, Any]:
    age = 8 + (idx % 10) if idx % 8 in (5, 6, 7) else 35 + (idx % 50)
    birth_date = AS_OF_DATE.date().replace(year=AS_OF_DATE.year - age)
    first = FIRST_NAMES[idx % len(FIRST_NAMES)]
    last = LAST_NAMES[(idx // len(FIRST_NAMES)) % len(LAST_NAMES)]
    return {
        "resourceType": "Patient",
        "id": patient_id,
        "active": True,
        "identifier": [
            {"system": "https://brakekat.example/fhir/synthetic-mrn", "value": f"SYN-{idx + 1:06d}", "type": {"text": "Synthetic MRN"}}
        ],
        "name": [{"use": "official", "text": f"{first} {last}", "family": last, "given": [first]}],
        "gender": "female" if idx % 2 == 0 else "male",
        "birthDate": birth_date.isoformat(),
        "extension": patient_demographic_extensions(idx),
        "address": [{
            "use": "home",
            "line": [f"{100 + idx} Synthetic Care Way"],
            "city": "Atlanta",
            "state": "GA",
            "postalCode": ATLANTA_HOSPITAL_ZIPS[ATLANTA_HOSPITALS[idx % len(ATLANTA_HOSPITALS)]],
            "country": "US",
        }],
    }


def encounter_resource(idx: int, patient_id: str, sequence: int, class_code: str, start: datetime, end: datetime) -> dict[str, Any]:
    hospital = ATLANTA_HOSPITALS[idx % len(ATLANTA_HOSPITALS)]
    encounter_id = stable_uuid("encounter", idx, sequence)
    resource: dict[str, Any] = {
        "resourceType": "Encounter",
        "id": encounter_id,
        "status": "finished",
        "class": {"system": "http://terminology.hl7.org/CodeSystem/v3-ActCode", "code": class_code, "display": {"AMB": "ambulatory", "EMER": "emergency", "IMP": "inpatient encounter"}[class_code]},
        "type": [{"coding": [{"system": "http://snomed.info/sct", "code": "308335008", "display": "Patient encounter procedure"}]}],
        "subject": {"reference": f"urn:uuid:{patient_id}"},
        "period": {"start": iso(start), "end": iso(end)},
        "serviceProvider": {"reference": f"Organization/{hospital}", "display": hospital.replace("-", " ").title()},
        "location": [{"location": {"reference": f"Location?identifier=https://brakekat.example/location|{hospital}", "display": hospital.replace("-", " ").title()}, "status": "completed"}],
        "participant": [{"individual": {"reference": f"Practitioner?identifier=http://hl7.org/fhir/sid/us-npi|99998{idx + 10000}"}}],
    }
    if class_code in {"IMP", "EMER"}:
        resource["hospitalization"] = {
            "admitSource": {"text": "Emergency" if class_code == "EMER" else "Physician referral"},
            "dischargeDisposition": {"text": "Home"},
            "reAdmission": {"text": "Re-admission"} if sequence == 4 else {"text": "No readmission"},
        }
    return resource


def condition_resource(idx: int, sequence: int, patient_id: str, encounter_id: str, code: str, display: str) -> dict[str, Any]:
    return {
        "resourceType": "Condition",
        "id": stable_uuid("condition", idx, sequence),
        "clinicalStatus": {"coding": [{"system": "http://terminology.hl7.org/CodeSystem/condition-clinical", "code": "active"}]},
        "verificationStatus": {"coding": [{"system": "http://terminology.hl7.org/CodeSystem/condition-ver-status", "code": "confirmed"}]},
        "category": [{"coding": [{"system": "http://terminology.hl7.org/CodeSystem/condition-category", "code": "encounter-diagnosis"}]}],
        "code": {"coding": [{"system": "http://snomed.info/sct", "code": code, "display": display}], "text": display},
        "subject": {"reference": f"urn:uuid:{patient_id}"},
        "encounter": {"reference": f"urn:uuid:{encounter_id}"},
        "onsetDateTime": iso(AS_OF_DATE - timedelta(days=365 * (1 + sequence))),
        "recordedDate": iso(AS_OF_DATE - timedelta(days=30 + sequence)),
    }


def observation_resource(idx: int, sequence: int, patient_id: str, encounter_id: str, code: str, display: str, value: float, unit: str, category: str = "laboratory") -> dict[str, Any]:
    return {
        "resourceType": "Observation",
        "id": stable_uuid("observation", idx, sequence, code),
        "status": "final",
        "category": [{"coding": [{"system": "http://terminology.hl7.org/CodeSystem/observation-category", "code": category}]}],
        "code": {"coding": [{"system": "http://loinc.org", "code": code, "display": display}], "text": display},
        "subject": {"reference": f"urn:uuid:{patient_id}"},
        "encounter": {"reference": f"urn:uuid:{encounter_id}"},
        "effectiveDateTime": iso(AS_OF_DATE - timedelta(days=sequence * 28)),
        "valueQuantity": {"value": value, "unit": unit, "system": "http://unitsofmeasure.org", "code": unit},
    }


def medication_resource(idx: int, sequence: int, patient_id: str, encounter_id: str, code: str, display: str) -> dict[str, Any]:
    return {
        "resourceType": "MedicationRequest",
        "id": stable_uuid("medication", idx, sequence, code),
        "status": "active",
        "intent": "order",
        "medicationCodeableConcept": {"coding": [{"system": "http://www.nlm.nih.gov/research/umls/rxnorm", "code": code, "display": display}], "text": display},
        "subject": {"reference": f"urn:uuid:{patient_id}"},
        "encounter": {"reference": f"urn:uuid:{encounter_id}"},
        "authoredOn": iso(AS_OF_DATE - timedelta(days=30 * sequence)),
    }


def immunization_resource(idx: int, patient_id: str, encounter_id: str, code: str, display: str, sequence: int) -> dict[str, Any]:
    return {
        "resourceType": "Immunization",
        "id": stable_uuid("immunization", idx, code),
        "status": "completed",
        "vaccineCode": {"coding": [{"system": "http://hl7.org/fhir/sid/cvx", "code": code, "display": display}]},
        "patient": {"reference": f"urn:uuid:{patient_id}"},
        "encounter": {"reference": f"urn:uuid:{encounter_id}"},
        "occurrenceDateTime": iso(AS_OF_DATE - timedelta(days=60 * sequence)),
    }


def procedure_resource(idx: int, patient_id: str, encounter_id: str) -> dict[str, Any]:
    return {
        "resourceType": "Procedure",
        "id": stable_uuid("procedure", idx),
        "status": "completed",
        "code": {"coding": [{"system": "http://snomed.info/sct", "code": "43075005", "display": "Inhalation therapy"}]},
        "subject": {"reference": f"urn:uuid:{patient_id}"},
        "encounter": {"reference": f"urn:uuid:{encounter_id}"},
        "performedDateTime": iso(AS_OF_DATE - timedelta(days=14)),
    }


def payer_organization_resource(profile: dict[str, str]) -> dict[str, Any]:
    return {"resourceType": "Organization", "id": profile["id"], "active": True, "name": profile["name"], "type": [{"coding": [{"system": "http://terminology.hl7.org/CodeSystem/organization-type", "code": "pay", "display": "Payer"}]}]}


def coverage_resource(coverage_id: int | str, patient_id: str, profile: dict[str, str]) -> dict[str, Any]:
    resource_id = stable_uuid("coverage", coverage_id) if isinstance(coverage_id, int) else coverage_id
    return {
        "resourceType": "Coverage", "id": resource_id, "status": "active",
        "type": {"coding": [{"system": "http://terminology.hl7.org/CodeSystem/v3-ActCode", "code": profile["type_code"], "display": profile["type_display"]}], "text": profile["name"]},
        "beneficiary": {"reference": f"urn:uuid:{patient_id}"},
        "payor": [{"reference": f"Organization/{profile['id']}", "display": profile["name"]}],
        "period": {"start": "2024-01-01", "end": "2026-12-31"},
    }


def claim_resources(idx: int, sequence: int, patient_id: str, encounter_id: str, coverage_id: str, payer_id: str, payer_name: str) -> tuple[dict[str, Any], dict[str, Any]]:
    claim_id = stable_uuid("claim", idx, sequence)
    eob_id = stable_uuid("eob", idx, sequence)
    service_date = AS_OF_DATE - timedelta(days=90 * sequence)
    amount = float(500 + idx * 25 + sequence * 750)
    common = {
        "status": "active",
        "type": {"coding": [{"system": "http://terminology.hl7.org/CodeSystem/claim-type", "code": "institutional" if sequence % 2 else "professional", "display": "institutional" if sequence % 2 else "professional"}]},
        "patient": {"reference": f"urn:uuid:{patient_id}"},
        "provider": {"reference": f"Practitioner?identifier=http://hl7.org/fhir/sid/us-npi|99998{idx + 10000}"},
        "facility": {"reference": f"Location?identifier=https://brakekat.example/location|{ATLANTA_HOSPITALS[idx % len(ATLANTA_HOSPITALS)]}"},
        "billablePeriod": {"start": iso(service_date), "end": iso(service_date + timedelta(days=1))},
        "insurance": [{"sequence": 1, "focal": True, "coverage": {"reference": f"urn:uuid:{coverage_id}", "display": payer_name}}],
    }
    claim = {"resourceType": "Claim", "id": claim_id, "use": "claim", "created": iso(service_date), "priority": {"coding": [{"system": "http://terminology.hl7.org/CodeSystem/processpriority", "code": "normal"}]}, "total": {"value": amount, "currency": "USD"}, **common}
    eob = {"resourceType": "ExplanationOfBenefit", "id": eob_id, "use": "claim", "outcome": "complete", "created": iso(service_date), "insurer": {"reference": f"Organization/{payer_id}", "display": payer_name}, "claim": {"reference": f"urn:uuid:{claim_id}"}, "payment": {"amount": {"value": round(amount * 0.82, 2), "currency": "USD"}}, "total": [{"category": {"coding": [{"code": "submitted"}]}, "amount": {"value": amount, "currency": "USD"}}], **common}
    return claim, eob


def goal_resource(goal_id: str, patient_id: str, profile: dict[str, str]) -> dict[str, Any]:
    return {
        "resourceType": "Goal", "id": goal_id, "lifecycleStatus": "active",
        "description": {"text": profile["text"]}, "subject": {"reference": f"urn:uuid:{patient_id}"},
        "startDate": AS_OF_DATE.date().isoformat(),
        "target": [{"measure": {"text": profile["target"]}, "dueDate": (AS_OF_DATE + timedelta(days=90)).date().isoformat()}],
    }


def care_resources(idx: int, patient_id: str, encounter_id: str, condition_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    goal_id = stable_uuid("goal", idx)
    care_plan_id = stable_uuid("care-plan", idx)
    goal = goal_resource(goal_id, patient_id, {
        "text": "Maintain oxygen saturation at or above 94 percent",
        "target": "Maintain oxygen saturation at or above 94 percent",
    })
    care_plan = {
        "resourceType": "CarePlan", "id": care_plan_id, "status": "active", "intent": "plan",
        "category": [{"coding": [{"code": "assess-plan", "display": "Assessment and Plan of Treatment"}], "text": "Assessment and Plan of Treatment"}],
        "title": "Synthetic chronic care plan", "subject": {"reference": f"urn:uuid:{patient_id}"},
        "encounter": {"reference": f"urn:uuid:{encounter_id}"}, "period": {"start": "2026-01-01", "end": "2026-12-31"},
        "addresses": [{"reference": f"urn:uuid:{condition_id}"}], "goal": [{"reference": f"urn:uuid:{goal_id}"}],
    }
    return goal, care_plan


def generate_patient(idx: int) -> tuple[str, dict[str, Any]]:
    patient_id = stable_uuid("patient", idx)
    resources: list[dict[str, Any]] = [patient_resource(idx, patient_id)]

    encounter_specs = [
        ("AMB", 720, 1), ("EMER", 540, 0.25), ("IMP", 365, 3),
        ("IMP", 350, 2), ("AMB", 180, 1), ("EMER", 90, 0.2), ("IMP", 30, 4),
    ]
    encounters = []
    for sequence, (class_code, days_ago, duration_days) in enumerate(encounter_specs):
        start = AS_OF_DATE - timedelta(days=days_ago)
        end = start + timedelta(days=duration_days)
        enc = encounter_resource(idx, patient_id, sequence, class_code, start, end)
        encounters.append(enc)
        resources.append(enc)
    primary_encounter_id = encounters[-1]["id"]

    profile_conditions = [CONDITIONS[idx % len(CONDITIONS)], CONDITIONS[(idx + 1) % len(CONDITIONS)]]
    featured = {20: CONDITIONS[3], 32: CONDITIONS[4], 84: CONDITIONS[2]}
    if idx in featured and featured[idx] not in profile_conditions:
        profile_conditions[0] = featured[idx]
    conditions = []
    for sequence, (code, display) in enumerate(profile_conditions):
        cond = condition_resource(idx, sequence, patient_id, primary_encounter_id, code, display)
        conditions.append(cond)
        resources.append(cond)

    diabetic = any(condition[0] == "44054006" for condition in profile_conditions)
    hypertensive = any(condition[0] == "59621000" for condition in profile_conditions)
    resources.extend([
        observation_resource(idx, 1, patient_id, primary_encounter_id, "4548-4", "Hemoglobin A1c", 7.2 if idx % 2 else 10.1, "%"),
        observation_resource(idx, 2, patient_id, primary_encounter_id, "8480-6", "Systolic blood pressure", 128 if idx % 2 else 148, "mm[Hg]", "vital-signs"),
        observation_resource(idx, 3, patient_id, primary_encounter_id, "8462-4", "Diastolic blood pressure", 78 if idx % 2 else 94, "mm[Hg]", "vital-signs"),
        observation_resource(idx, 4, patient_id, primary_encounter_id, "39156-5", "Body mass index", 27.5 + idx % 8, "kg/m2", "vital-signs"),
        observation_resource(idx, 5, patient_id, primary_encounter_id, "14959-1", "Microalbumin/Creatinine", 20 + idx % 15, "mg/g"),
        observation_resource(idx, 6, patient_id, primary_encounter_id, "2708-6", "Oxygen saturation", 88 + idx % 11, "%", "vital-signs"),
    ])

    for med_index, (code, display, med_class) in enumerate(PDC_MEDICATIONS):
        if med_class == "PDC-DR" and not diabetic and idx % 3:
            continue
        if med_class == "PDC-RASA" and not hypertensive and idx % 3:
            continue
        fills = 12 if idx % 2 == 0 else 7
        for month in range(fills):
            resources.append(medication_resource(idx, month, patient_id, primary_encounter_id, code, display))
    resources.extend([
        immunization_resource(idx, patient_id, primary_encounter_id, "133", "Pneumococcal conjugate PCV 13", 2),
        immunization_resource(idx, patient_id, primary_encounter_id, "140", "Influenza seasonal injectable", 1),
        procedure_resource(idx, patient_id, primary_encounter_id),
    ])

    payer = PAYER_PROFILES[idx % len(PAYER_PROFILES)]
    payer_org = payer_organization_resource(payer)
    coverage = coverage_resource(idx, patient_id, payer)
    resources.extend([payer_org, coverage])
    for sequence, encounter in enumerate(encounters[:4]):
        resources.extend(claim_resources(idx, sequence, patient_id, encounter["id"], coverage["id"], payer["id"], payer["name"]))

    goal, care_plan = care_resources(idx, patient_id, primary_encounter_id, conditions[0]["id"])
    resources.extend([goal, care_plan])
    resources.append({
        "resourceType": "DocumentReference", "id": stable_uuid("document", idx), "status": "current",
        "type": {"coding": [{"system": "http://loinc.org", "code": "34133-9", "display": "Summary of episode note"}]},
        "subject": {"reference": f"urn:uuid:{patient_id}"}, "context": {"encounter": [{"reference": f"urn:uuid:{primary_encounter_id}"}]},
        "date": iso(AS_OF_DATE), "content": [{"attachment": {"contentType": "text/plain", "data": "U3ludGhldGljIGNsaW5pY2FsIHN1bW1hcnku"}}],
    })

    bundle = {"resourceType": "Bundle", "type": "transaction", "entry": [entry(resource) for resource in resources]}
    name = resources[0]["name"][0]["text"].replace(" ", "_")
    return f"{name}_{patient_id}.json", bundle


def generate_fixture(out_dir: Path, patient_count: int = PATIENT_COUNT) -> dict[str, Any]:
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)
    counts: Counter[str] = Counter()
    unique_ids: defaultdict[str, set[str]] = defaultdict(set)
    checksums: dict[str, str] = {}
    assignments = []
    profiles = []
    for idx in range(patient_count):
        filename, bundle = generate_patient(idx)
        payload = json.dumps(bundle, indent=2, sort_keys=True) + "\n"
        (out_dir / filename).write_text(payload)
        checksums[filename] = hashlib.sha256(payload.encode()).hexdigest()
        resources = [item["resource"] for item in bundle["entry"]]
        counts.update(resource["resourceType"] for resource in resources)
        for resource in resources:
            unique_ids[resource["resourceType"]].add(resource["id"])
        patient = next(resource for resource in resources if resource["resourceType"] == "Patient")
        conditions = [resource["code"]["coding"][0]["code"] for resource in resources if resource["resourceType"] == "Condition"]
        assignments.append({"deviceId": f"MASIMO-RADIUS7-{idx + 1:04d}", "patientId": patient["id"], "patientName": patient["name"][0]["text"]})
        profiles.append({"patientId": patient["id"], "conditionCodes": conditions})
    manifest = {
        "schemaVersion": 1,
        "fixtureVersion": FIXTURE_VERSION,
        "syntheticOnly": True,
        "asOfDate": AS_OF_DATE.date().isoformat(),
        "namespace": str(FIXTURE_NAMESPACE),
        "patientCount": patient_count,
        "resourceCounts": dict(sorted(counts.items())),
        "expectedUniqueResourceCounts": {resource_type: len(ids) for resource_type, ids in sorted(unique_ids.items())},
        "files": checksums,
        "deviceAssignments": assignments,
        "patientProfiles": profiles,
    }
    return manifest


def main() -> None:
    root = Path(__file__).resolve().parent
    manifest = generate_fixture(root / "prepackaged")
    manifest_path = root / "canonical-fixture-manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(f"Generated {manifest['patientCount']} patients and {sum(manifest['resourceCounts'].values())} resources")
    print(f"Manifest: {manifest_path}")


if __name__ == "__main__":
    main()
