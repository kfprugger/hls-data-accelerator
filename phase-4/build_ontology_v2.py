#!/usr/bin/env python3
"""Build Fabric IQ Ontology v2 (TMDL) item definitions for ClinicalDeviceOntology and DevicePayerOntology."""
from __future__ import annotations

import argparse
import base64
import json
import uuid


def _tag(seed: str) -> str:
    return str(uuid.uuid5(uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8"), seed))


def _table_tmdl(table_name: str, columns: list[tuple[str, str, str]]) -> str:
    lines = [
        f"table {table_name}",
        f"\tlineageTag: {_tag(f'table:{table_name}')}",
        "",
    ]
    for col_name, dtype, _prop_name in columns:
        lines.append(f"\tcolumn {col_name}")
        lines.append(f"\t\tdataType: {dtype}")
        if dtype == "int64":
            lines.append("\t\tformatString: 0")
        lines.append(f"\t\tlineageTag: {_tag(f'col:{table_name}:{col_name}')}")
        lines.append(f"\t\tsourceColumn: {col_name}")
        lines.append("")
    lines.extend([
        f"\tpartition {table_name} = entity",
        "\t\tmode: directLake",
        "\t\tsource",
        f"\t\t\tentityName: {table_name}",
        "\t\t\tschemaName: dbo",
        "\t\t\texpressionSource: DatabaseQuery",
        "",
    ])
    return "\n".join(lines)


def _entity_tmdl(
    entity_name: str,
    description: str,
    backing_table: str | None,
    key_property: str | None,
    columns: list[tuple[str, str, str]],
) -> str:
    lines = [
        f"/// {description}",
        f"entity {entity_name}",
        f"\tlineageTag: {_tag(f'entity:{entity_name}')}",
    ]
    if backing_table:
        lines.append(f"\tbackingTable: {backing_table}")
    if key_property:
        lines.append(f"\tkeyProperty: {key_property}")
    lines.append("")
    for col_name, dtype, prop_name in columns:
        lines.append(f"\tproperty {prop_name}")
        lines.append(f"\t\tdataType: {dtype}")
        lines.append(f"\t\tlineageTag: {_tag(f'prop:{entity_name}:{prop_name}')}")
        if backing_table:
            lines.append("")
            lines.append("\t\tbackingConfiguration")
            lines.append(f"\t\t\tvalueColumn: {backing_table}.{col_name}")
        lines.append("")
    return "\n".join(lines)


def build_ontology_v2_parts(
    ontology_name: str,
    sql_endpoint: str,
    sql_endpoint_id: str,
    include_fhir: bool = True,
    include_dicom: bool = True,
    include_telemetry: bool = True,
    include_gold: bool = False,
) -> dict:
    tables: list[tuple[str, list[tuple[str, str, str]]]] = []
    entities: list[tuple[str, str, str | None, str | None, list[tuple[str, str, str]]]] = []
    tom_rels: list[tuple[str, str, str]] = []
    ent_rels: list[dict] = []
    rules: list[tuple[str, str, list[tuple[str, list[str]]], list[str]]] = []

    if include_fhir or include_dicom:
        patient_cols = [
            ("idOrig", "string", "patientId"),
            ("name_string", "string", "patientName"),
            ("gender", "string", "gender"),
            ("birthDate", "string", "birthDate"),
        ]
        tables.append(("PatientOntology", patient_cols))
        entities.append((
            "Patient",
            "Clinical patient demographic record projected from FHIR Patient.",
            "PatientOntology",
            "patientId",
            patient_cols,
        ))

    if include_fhir:
        enc_cols = [
            ("idOrig", "string", "encounterId"),
            ("class_string", "string", "encounterClass"),
            ("status", "string", "encounterStatus"),
            ("period_start", "string", "periodStart"),
            ("patient_id", "string", "patientRef"),
        ]
        tables.append(("EncounterOntology", enc_cols))
        entities.append(("Encounter", "Clinical encounter record.", "EncounterOntology", "encounterId", enc_cols))
        tom_rels.append(("rel_encounter_patient", "EncounterOntology.patient_id", "PatientOntology.idOrig"))
        ent_rels.append({"name": "hasEncounter", "from": "Encounter", "to": "Patient", "rel": "rel_encounter_patient"})

        cond_cols = [
            ("idOrig", "string", "conditionId"),
            ("code_string", "string", "conditionName"),
            ("clinicalStatus_string", "string", "clinicalStatus"),
            ("patient_id", "string", "patientRef"),
        ]
        tables.append(("ConditionOntology", cond_cols))
        entities.append(("Condition", "Clinical diagnosis or condition.", "ConditionOntology", "conditionId", cond_cols))
        tom_rels.append(("rel_condition_patient", "ConditionOntology.patient_id", "PatientOntology.idOrig"))
        ent_rels.append({"name": "hasCondition", "from": "Condition", "to": "Patient", "rel": "rel_condition_patient"})

        med_cols = [
            ("idOrig", "string", "medicationRequestId"),
            ("medicationCodeableConcept_string", "string", "medication"),
            ("status", "string", "medStatus"),
            ("authoredOn", "string", "authoredOn"),
            ("patient_id", "string", "patientRef"),
        ]
        tables.append(("MedicationRequestOntology", med_cols))
        entities.append(("MedRequest", "Medication order from FHIR MedicationRequest.", "MedicationRequestOntology", "medicationRequestId", med_cols))
        tom_rels.append(("rel_medrequest_patient", "MedicationRequestOntology.patient_id", "PatientOntology.idOrig"))
        ent_rels.append({"name": "hasMedication", "from": "MedRequest", "to": "Patient", "rel": "rel_medrequest_patient"})

        obs_cols = [
            ("idOrig", "string", "observationId"),
            ("code_string", "string", "observationCode"),
            ("valueQuantity_value", "double", "observationValue"),
            ("valueQuantity_unit", "string", "observationUnit"),
            ("effectiveDateTime", "string", "effectiveDateTime"),
            ("patient_id", "string", "patientRef"),
        ]
        tables.append(("ObservationOntology", obs_cols))
        entities.append(("Observation", "Clinical observation or lab result.", "ObservationOntology", "observationId", obs_cols))
        tom_rels.append(("rel_observation_patient", "ObservationOntology.patient_id", "PatientOntology.idOrig"))
        ent_rels.append({"name": "hasObservation", "from": "Observation", "to": "Patient", "rel": "rel_observation_patient"})

    if include_dicom:
        img_cols = [
            ("idOrig", "string", "studyId"),
            ("description", "string", "description"),
            ("patient_id", "string", "patientRef"),
            ("numberOfSeries", "int64", "numberOfSeries"),
            ("numberOfInstances", "int64", "numberOfInstances"),
        ]
        tables.append(("ImagingStudyOntology", img_cols))
        entities.append(("ImagingStudy", "DICOM imaging study linked to a patient.", "ImagingStudyOntology", "studyId", img_cols))
        if include_fhir or include_dicom:
            tom_rels.append(("rel_imaging_patient", "ImagingStudyOntology.patient_id", "PatientOntology.idOrig"))
            ent_rels.append({"name": "hasImagingStudy", "from": "ImagingStudy", "to": "Patient", "rel": "rel_imaging_patient"})

    if include_telemetry:
        dev_cols = [
            ("idOrig", "string", "deviceId"),
            ("type_string", "string", "deviceType"),
            ("status", "string", "deviceStatus"),
        ]
        tables.append(("DeviceOntology", dev_cols))
        entities.append(("Device", "Bedside pulse-oximeter or clinical monitoring device.", "DeviceOntology", "deviceId", dev_cols))

        assoc_cols = [
            ("id", "string", "associationId"),
            ("device_ref", "string", "deviceRef"),
            ("patient_name", "string", "assocPatientName"),
            ("patient_id", "string", "assocPatientId"),
        ]
        tables.append(("DeviceAssociation", assoc_cols))
        entities.append(("DeviceAssoc", "Active patient-to-device assignment record.", "DeviceAssociation", "associationId", assoc_cols))

        # Ontology-first / KQL-enriched telemetry concept so ClinicalDeviceOntology retains all 9 clinical concepts in v2
        telem_cols = [
            ("device_id", "string", "telemetryDeviceId"),
            ("timestamp", "dateTime", "telemetryTimestamp"),
            ("spo2", "double", "spo2"),
            ("pulseRate", "double", "pulseRate"),
            ("perfusionIndex", "double", "perfusionIndex"),
            ("plethVariability", "double", "plethVariability"),
        ]
        entities.append((
            "DeviceTelemetry",
            "Real-time Masimo pulse-oximeter telemetry stream in MasimoEventhouse (TelemetryRaw).",
            None,
            None,
            telem_cols,
        ))

        if include_fhir or include_dicom:
            tom_rels.append(("rel_deviceassoc_patient", "DeviceAssociation.patient_id", "PatientOntology.idOrig"))
            tom_rels.append(("rel_deviceassoc_device", "DeviceAssociation.device_ref", "DeviceOntology.idOrig"))
            ent_rels.append({"name": "linkedToPatient", "from": "DeviceAssoc", "to": "Patient", "rel": "rel_deviceassoc_patient"})
            ent_rels.append({"name": "linkedToDevice", "from": "DeviceAssoc", "to": "Device", "rel": "rel_deviceassoc_device"})

        rules.append((
            "HypoxemiaTelemetryRule",
            "A monitored patient with SpO2 below 90 percent or pulse rate above 120 bpm requires immediate clinical triage review.",
            [("Device", ["deviceId", "deviceStatus"]), ("DeviceAssoc", ["assocPatientId", "deviceRef"])],
            ["linkedToDevice"],
        ))

    if include_gold:
        claim_cols = [
            ("claim_key", "int64", "claimKey"),
            ("claim_id", "string", "claimId"),
            ("claim_type", "string", "claimType"),
            ("claim_status", "string", "claimStatus"),
            ("billed_amount", "double", "billedAmount"),
            ("paid_amount", "double", "paidAmount"),
            ("allowed_amount", "double", "allowedAmount"),
            ("patient_responsibility", "double", "patientResponsibility"),
            ("denial_flag", "int64", "denialFlag"),
            ("patient_ref", "string", "claimPatientRef"),
            ("patient_id", "string", "claimPatientId"),
            ("coverage_id", "string", "coverageId"),
            ("payer_category", "string", "claimPayerCategory"),
            ("service_date", "string", "serviceDate"),
        ]
        tables.append(("fact_claim", claim_cols))
        entities.append(("Claim", "Healthcare claim adjudication record.", "fact_claim", "claimKey", claim_cols))

        payer_cols = [
            ("payer_id", "string", "payerId"),
            ("payer_key", "int64", "payerKey"),
            ("payer_name", "string", "payerName"),
            ("payer_type", "string", "payerType"),
            ("payer_category", "string", "payerCategory"),
        ]
        tables.append(("dim_payer", payer_cols))
        entities.append(("Payer", "Health plan or payer organization.", "dim_payer", "payerId", payer_cols))

        dx_cols = [
            ("diagnosis_key", "int64", "diagnosisKey"),
            ("icd_code", "string", "icdCode"),
            ("icd_description", "string", "icdDescription"),
            ("code_system", "string", "codeSystem"),
            ("is_chronic", "int64", "isChronic"),
        ]
        tables.append(("dim_diagnosis", dx_cols))
        entities.append(("Diagnosis", "ICD-10 clinical diagnosis dimension.", "dim_diagnosis", "icdCode", dx_cols))

        pdx_cols = [
            ("fact_diagnosis_key", "int64", "factDiagnosisKey"),
            ("diagnosis_id", "string", "diagnosisId"),
            ("icd_code", "string", "diagIcdCode"),
            ("diagnosis_description", "string", "diagDescription"),
            ("diagnosis_type", "string", "diagnosisType"),
            ("patient_id", "string", "diagPatientId"),
            ("diagnosis_date", "string", "diagnosisDate"),
        ]
        tables.append(("FactDiagnosisOntology", pdx_cols))
        entities.append(("PatientDiagnosis", "Patient-level diagnosis bridge fact.", "FactDiagnosisOntology", "factDiagnosisKey", pdx_cols))

        ma_cols = [
            ("patient_id", "string", "adherencePatientId"),
            ("medication_class", "string", "medicationClass"),
            ("pdc_score", "double", "pdcScore"),
            ("adherence_category", "string", "adherenceCategory"),
            ("gap_days", "int64", "gapDays"),
            ("total_fills", "int64", "totalFills"),
        ]
        tables.append(("agg_medication_adherence", ma_cols))
        entities.append(("MedAdherence", "Proportion of days covered (PDC) medication adherence summary.", "agg_medication_adherence", "adherencePatientId", ma_cols))

        cg_cols = [
            ("patient_id", "string", "careGapPatientId"),
            ("measure_id", "string", "measureId"),
            ("gap_type", "string", "gapType"),
            ("gap_status", "string", "gapStatus"),
            ("days_overdue", "int64", "daysOverdue"),
            ("recommended_action", "string", "recommendedAction"),
        ]
        tables.append(("care_gaps", cg_cols))
        entities.append(("CareGap", "HEDIS/CMS clinical quality care gap.", "care_gaps", "careGapPatientId", cg_cols))

        rs_cols = [
            ("patient_id", "string", "riskPatientId"),
            ("raf_score", "double", "rafScore"),
            ("risk_tier", "string", "riskTier"),
            ("hcc_count", "int64", "hccCount"),
            ("annual_revenue", "double", "annualRevenue"),
            ("payer_category", "string", "riskPayerCategory"),
        ]
        tables.append(("agg_risk_scores", rs_cols))
        entities.append(("PatientRisk", "CMS-HCC risk adjustment factor (RAF) profile.", "agg_risk_scores", "riskPatientId", rs_cols))

        hc_cols = [
            ("patient_id", "string", "highCostPatientId"),
            ("payer_category", "string", "highCostPayerCategory"),
            ("total_paid", "double", "totalPaid"),
            ("total_billed", "double", "totalBilled"),
            ("claim_count", "int64", "claimCount"),
            ("denied_claims", "int64", "deniedClaims"),
            ("is_stop_loss", "string", "isStopLoss"),
        ]
        tables.append(("agg_high_cost_claimants", hc_cols))
        entities.append(("HighCostClaimant", "High-cost member and stop-loss cohort summary.", "agg_high_cost_claimants", "highCostPatientId", hc_cols))

        if include_fhir or include_dicom:
            tom_rels.extend([
                ("rel_claim_patient", "fact_claim.patient_id", "PatientOntology.idOrig"),
                ("rel_claim_payer", "fact_claim.coverage_id", "dim_payer.payer_id"),
                ("rel_pdiag_patient", "FactDiagnosisOntology.patient_id", "PatientOntology.idOrig"),
                ("rel_pdiag_diagnosis", "FactDiagnosisOntology.icd_code", "dim_diagnosis.icd_code"),
                ("rel_adherence_patient", "agg_medication_adherence.patient_id", "PatientOntology.idOrig"),
                ("rel_caregap_patient", "care_gaps.patient_id", "PatientOntology.idOrig"),
                ("rel_risk_patient", "agg_risk_scores.patient_id", "PatientOntology.idOrig"),
                ("rel_highcost_patient", "agg_high_cost_claimants.patient_id", "PatientOntology.idOrig"),
            ])
            ent_rels.extend([
                {"name": "hasClaim", "from": "Claim", "to": "Patient", "rel": "rel_claim_patient"},
                {"name": "coveredBy", "from": "Claim", "to": "Payer", "rel": "rel_claim_payer"},
                {"name": "hasDiagnosis", "from": "PatientDiagnosis", "to": "Patient", "rel": "rel_pdiag_patient"},
                {"name": "diagnosisClassifiedAs", "from": "PatientDiagnosis", "to": "Diagnosis", "rel": "rel_pdiag_diagnosis"},
                {"name": "hasAdherence", "from": "MedAdherence", "to": "Patient", "rel": "rel_adherence_patient"},
                {"name": "hasCareGap", "from": "CareGap", "to": "Patient", "rel": "rel_caregap_patient"},
                {"name": "hasRiskScore", "from": "PatientRisk", "to": "Patient", "rel": "rel_risk_patient"},
                {"name": "hasHighCostProfile", "from": "HighCostClaimant", "to": "Patient", "rel": "rel_highcost_patient"},
            ])

    def _b64(text: str) -> str:
        return base64.b64encode(text.encode("utf-8")).decode("ascii")

    parts = []
    for tbl_name, cols in tables:
        parts.append({
            "path": f"tables/{tbl_name}.tmdl",
            "payload": _b64(_table_tmdl(tbl_name, cols)),
            "payloadType": "InlineBase64",
        })

    if tom_rels:
        rel_lines = []
        for rname, from_col, to_col in tom_rels:
            rel_lines.append(f"relationship {rname}")
            rel_lines.append(f"\tfromColumn: {from_col}")
            rel_lines.append(f"\ttoColumn: {to_col}")
            rel_lines.append("")
        parts.append({
            "path": "relationships.tmdl",
            "payload": _b64("\n".join(rel_lines)),
            "payloadType": "InlineBase64",
        })

    expr_tmdl = (
        "expression DatabaseQuery =\n"
        "\t\tlet\n"
        f'\t\t    database = Sql.Database("{sql_endpoint}", "{sql_endpoint_id}")\n'
        "\t\tin\n"
        "\t\t    database\n"
        f"\tlineageTag: {_tag(f'expr:{ontology_name}')}\n\n"
    )
    parts.append({
        "path": "expressions.tmdl",
        "payload": _b64(expr_tmdl),
        "payloadType": "InlineBase64",
    })

    for ent_name, desc, backing_tbl, key_prop, cols in entities:
        parts.append({
            "path": f"entities/{ent_name}.tmdl",
            "payload": _b64(_entity_tmdl(ent_name, desc, backing_tbl, key_prop, cols)),
            "payloadType": "InlineBase64",
        })

    if ent_rels:
        er_lines = []
        for er in ent_rels:
            er_name = er["name"]
            er_lines.append(f"entityRelationship {er_name}")
            er_lines.append(f"\tlineageTag: {_tag(f'er:{ontology_name}:{er_name}')}")
            er_lines.append(f"\tfromEntity: {er['from']}")
            er_lines.append(f"\ttoEntity: {er['to']}")
            er_lines.append("")
            er_lines.append("\tbackingConfiguration")
            er_lines.append(f"\t\trelationship: {er['rel']}")
            er_lines.append("")
        parts.append({
            "path": "entityRelationships.tmdl",
            "payload": _b64("\n".join(er_lines)),
            "payloadType": "InlineBase64",
        })

    parts.append({
        "path": "namespaces/default.tmdl",
        "payload": _b64("namespace default\n\tlineageTag: default\n\n"),
        "payloadType": "InlineBase64",
    })

    for rule_name, statement, ref_ents, ref_rels in rules:
        r_lines = [
            f"rule {rule_name}",
            f"\tstatement: {statement}",
            f"\tlineageTag: {_tag(f'rule:{ontology_name}:{rule_name}')}",
            "",
        ]
        for ent_name, props in ref_ents:
            r_lines.append(f"\truleReferencedEntity {ent_name}")
            if props:
                r_lines.append("\t\tpropertyScope: specific")
                r_lines.append("")
                for p in props:
                    r_lines.append(f"\t\truleReferencedProperty {p}")
                    r_lines.append("")
        for rname in ref_rels:
            r_lines.append(f"\truleReferencedRelationship {rname}")
            r_lines.append("")
        parts.append({
            "path": f"rules/{rule_name}.tmdl",
            "payload": _b64("\n".join(r_lines)),
            "payloadType": "InlineBase64",
        })

    model_lines = ["model Model", ""]
    for tbl_name, _ in tables:
        model_lines.append(f"ref table {tbl_name}")
    model_lines.append("")
    for ent_name, *_ in entities:
        model_lines.append(f"ref entity {ent_name}")
    model_lines.append("")
    model_lines.append("ref namespace default")
    if rules:
        model_lines.append("")
        for rule_name, *_ in rules:
            model_lines.append(f"ref rule {rule_name}")
    model_lines.append("")
    parts.append({
        "path": "model.tmdl",
        "payload": _b64("\n".join(model_lines)),
        "payloadType": "InlineBase64",
    })

    parts.append({
        "path": "database.tmdl",
        "payload": _b64("database\n\tcompatibilityLevel: 1000000\n\n"),
        "payloadType": "InlineBase64",
    })

    platform_json = json.dumps({
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/gitIntegration/platformProperties/2.0.0/schema.json",
        "metadata": {"type": "Ontology", "displayName": ontology_name},
        "config": {"version": "2.0", "logicalId": "00000000-0000-0000-0000-000000000000"},
    }, indent=2)
    parts.append({
        "path": ".platform",
        "payload": _b64(platform_json),
        "payloadType": "InlineBase64",
    })

    return {
        "parts": parts,
        "entityCount": len(entities),
        "tableCount": len(tables),
        "relationshipCount": len(ent_rels),
        "goldEntityCount": 8 if include_gold else 0,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ontology-name", required=True)
    parser.add_argument("--sql-endpoint", required=True)
    parser.add_argument("--sql-endpoint-id", required=True)
    parser.add_argument("--include-fhir", action="store_true")
    parser.add_argument("--include-dicom", action="store_true")
    parser.add_argument("--include-telemetry", action="store_true")
    parser.add_argument("--include-gold", action="store_true")
    args = parser.parse_args()

    res = build_ontology_v2_parts(
        ontology_name=args.ontology_name,
        sql_endpoint=args.sql_endpoint,
        sql_endpoint_id=args.sql_endpoint_id,
        include_fhir=args.include_fhir,
        include_dicom=args.include_dicom,
        include_telemetry=args.include_telemetry,
        include_gold=args.include_gold,
    )
    print(json.dumps(res))


if __name__ == "__main__":
    main()
