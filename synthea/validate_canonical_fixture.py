#!/usr/bin/env python3
"""Fail-closed validator for the canonical synthetic healthcare fixture."""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from datetime import date, datetime
from pathlib import Path
from typing import Any

REQUIRED_TYPES = {
    "Patient", "Encounter", "Condition", "Observation", "MedicationRequest",
    "Immunization", "Procedure", "Coverage", "Claim", "ExplanationOfBenefit",
    "CarePlan", "Goal", "DocumentReference", "Organization",
}
REQUIRED_CONDITIONS = {"44054006", "59621000", "84114007", "13645005", "195967001"}
REQUIRED_OBSERVATIONS = {"4548-4", "8480-6", "8462-4", "39156-5", "14959-1"}
REQUIRED_MEDICATION_NAMES = {"metformin", "lisinopril", "atorvastatin"}
FORBIDDEN_IDENTIFIER_SYSTEMS = {
    "http://hl7.org/fhir/sid/us-ssn",
    "http://hl7.org/fhir/sid/passport-USA",
    "urn:oid:2.16.840.1.113883.4.3.25",
}
FEATURED_DEVICE_CONDITIONS = {
    "MASIMO-RADIUS7-0021": "13645005",
    "MASIMO-RADIUS7-0033": "195967001",
    "MASIMO-RADIUS7-0085": "84114007",
}
REFERENCE_FIELDS = {
    "Condition": ("subject", "encounter"),
    "Observation": ("subject", "encounter"),
    "Procedure": ("subject", "encounter"),
    "Encounter": ("subject",),
    "CarePlan": ("subject", "encounter"),
    "MedicationRequest": ("subject", "encounter"),
    "Immunization": ("patient", "encounter"),
    "Coverage": ("beneficiary",),
    "Claim": ("patient",),
    "ExplanationOfBenefit": ("patient",),
    "DocumentReference": ("subject",),
}


def coding_values(resource: dict[str, Any], field: str = "code") -> list[str]:
    value = resource.get(field, {})
    if not isinstance(value, dict):
        return []
    return [str(coding.get("code", "")) for coding in value.get("coding", [])]


def nested_references(value: Any) -> list[str]:
    refs: list[str] = []
    stack = [value]
    while stack:
        current = stack.pop()
        if isinstance(current, dict):
            reference = current.get("reference")
            if isinstance(reference, str):
                refs.append(reference)
            stack.extend(current.values())
        elif isinstance(current, list):
            stack.extend(current)
    return refs


def validate(root: Path) -> dict[str, Any]:
    manifest_path = root / "canonical-fixture-manifest.json"
    bundle_dir = root / "prepackaged"
    manifest = json.loads(manifest_path.read_text())
    errors: list[str] = []
    if manifest.get("syntheticOnly") is not True:
        errors.append("manifest syntheticOnly must be true")
    try:
        as_of = date.fromisoformat(manifest["asOfDate"])
    except Exception:
        errors.append("manifest asOfDate must be an ISO date")
        as_of = date.today()

    files = sorted(bundle_dir.glob("*.json"))
    expected_files = manifest.get("files", {})
    if {path.name for path in files} != set(expected_files):
        errors.append("manifest file list does not exactly match prepackaged directory")

    counts: Counter[str] = Counter()
    resources: list[dict[str, Any]] = []
    full_urls: set[str] = set()
    ids_by_type: defaultdict[str, set[str]] = defaultdict(set)
    patient_resources: dict[str, dict[str, Any]] = {}
    patient_conditions: defaultdict[str, set[str]] = defaultdict(set)
    encounter_classes: Counter[str] = Counter()
    observation_codes: Counter[str] = Counter()
    medication_names: Counter[str] = Counter()

    for path in files:
        payload = path.read_bytes()
        if hashlib.sha256(payload).hexdigest() != expected_files.get(path.name):
            errors.append(f"checksum mismatch: {path.name}")
        try:
            bundle = json.loads(payload)
        except Exception as exc:
            errors.append(f"invalid JSON {path.name}: {exc}")
            continue
        if bundle.get("resourceType") != "Bundle" or bundle.get("type") != "transaction":
            errors.append(f"{path.name} is not a transaction Bundle")
            continue
        local_urls = {item.get("fullUrl") for item in bundle.get("entry", []) if item.get("fullUrl")}
        full_urls.update(local_urls)
        for item in bundle.get("entry", []):
            resource = item.get("resource", {})
            resource_type = resource.get("resourceType")
            resource_id = resource.get("id")
            if not resource_type or not resource_id:
                errors.append(f"resource without type/id in {path.name}")
                continue
            if resource_id in ids_by_type[resource_type] and resource_type not in {"Organization"}:
                errors.append(f"duplicate {resource_type}/{resource_id}")
            ids_by_type[resource_type].add(resource_id)
            counts[resource_type] += 1
            resources.append(resource)
            for ref in nested_references(resource):
                if ref.startswith("urn:uuid:") and ref not in local_urls:
                    errors.append(f"dangling local reference {ref} in {path.name}")
            for field in REFERENCE_FIELDS.get(resource_type, ()):
                refs = nested_references(resource.get(field))
                if not refs:
                    errors.append(f"missing {resource_type}.{field} reference in {path.name}")
            if resource_type == "Claim":
                if not resource.get("priority") or not isinstance(resource.get("total"), dict):
                    errors.append(f"Claim/{resource_id} missing required priority or Money total")
            elif resource_type == "ExplanationOfBenefit":
                if not resource.get("insurer") or not isinstance(resource.get("total"), list):
                    errors.append(f"ExplanationOfBenefit/{resource_id} missing insurer or total array")
            if resource_type == "Patient":
                patient_resources[resource_id] = resource
            elif resource_type == "Condition":
                subject = resource.get("subject", {}).get("reference", "").removeprefix("urn:uuid:")
                patient_conditions[subject].update(coding_values(resource))
            elif resource_type == "Encounter":
                encounter_classes[str(resource.get("class", {}).get("code", ""))] += 1
            elif resource_type == "Observation":
                observation_codes.update(coding_values(resource))
            elif resource_type == "MedicationRequest":
                display = resource.get("medicationCodeableConcept", {}).get("coding", [{}])[0].get("display", "")
                medication_names[display.lower()] += 1

    if counts != Counter(manifest.get("resourceCounts", {})):
        errors.append("resource counts do not match manifest")
    if not REQUIRED_TYPES.issubset(counts):
        errors.append(f"missing resource types: {sorted(REQUIRED_TYPES - set(counts))}")
    if len(patient_resources) != manifest.get("patientCount"):
        errors.append("Patient count does not match manifest")

    for patient_id, patient in patient_resources.items():
        names = patient.get("name", [])
        if not names or not names[0].get("text"):
            errors.append(f"Patient/{patient_id} missing name.text")
        systems = {identifier.get("system") for identifier in patient.get("identifier", [])}
        forbidden = systems & FORBIDDEN_IDENTIFIER_SYSTEMS
        if forbidden:
            errors.append(f"Patient/{patient_id} has forbidden identifiers: {sorted(forbidden)}")
        extension_urls = {extension.get("url") for extension in patient.get("extension", [])}
        if not {"http://hl7.org/fhir/us/core/StructureDefinition/us-core-race", "http://hl7.org/fhir/us/core/StructureDefinition/us-core-ethnicity"}.issubset(extension_urls):
            errors.append(f"Patient/{patient_id} missing race/ethnicity extensions")
        birth = date.fromisoformat(patient["birthDate"])
        age = as_of.year - birth.year - ((as_of.month, as_of.day) < (birth.month, birth.day))
        if age < 0 or age > 120:
            errors.append(f"Patient/{patient_id} has invalid age {age}")

    condition_codes = {code for values in patient_conditions.values() for code in values}
    if not REQUIRED_CONDITIONS.issubset(condition_codes):
        errors.append(f"missing condition codes: {sorted(REQUIRED_CONDITIONS - condition_codes)}")
    if not REQUIRED_OBSERVATIONS.issubset(observation_codes):
        errors.append(f"missing observation codes: {sorted(REQUIRED_OBSERVATIONS - set(observation_codes))}")
    for medication in REQUIRED_MEDICATION_NAMES:
        if not any(medication in name for name in medication_names):
            errors.append(f"missing medication class exemplar: {medication}")
    for class_code in {"AMB", "EMER", "IMP"}:
        if encounter_classes[class_code] < 50:
            errors.append(f"insufficient {class_code} encounters: {encounter_classes[class_code]}")

    assignments = manifest.get("deviceAssignments", [])
    if len(assignments) != manifest.get("patientCount"):
        errors.append("device assignment count does not match Patient count")
    if len({item.get("deviceId") for item in assignments}) != len(assignments):
        errors.append("duplicate device assignments")
    if len({item.get("patientId") for item in assignments}) != len(assignments):
        errors.append("duplicate patient assignments")
    assignments_by_device = {item.get("deviceId"): item for item in assignments}
    for device_id, condition_code in FEATURED_DEVICE_CONDITIONS.items():
        assignment = assignments_by_device.get(device_id)
        if not assignment:
            errors.append(f"missing featured device assignment {device_id}")
        elif condition_code not in patient_conditions.get(assignment.get("patientId", ""), set()):
            errors.append(f"featured device {device_id} missing condition {condition_code}")

    summary = {
        "valid": not errors,
        "patientCount": len(patient_resources),
        "resourceCounts": dict(sorted(counts.items())),
        "encounterClasses": dict(sorted(encounter_classes.items())),
        "errors": errors,
    }
    if errors:
        raise ValueError(json.dumps(summary, indent=2))
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent)
    args = parser.parse_args()
    print(json.dumps(validate(args.root), indent=2))


if __name__ == "__main__":
    main()
