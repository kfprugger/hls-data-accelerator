"""Gold analytical and operational products.

Fabric equivalent replaced here:
  healthcare1_msft_omop_analytics, the claims/quality materialization notebook,
  the reporting Gold lakehouse, and the payer worklist KQL functions.

Design rules:
  - Gold reads only governed Silver, never Bronze or a raw source path.
  - Every product is a materialized view so lineage and refresh stay declarative.
  - Sparse synthetic cohorts may yield zero rows in a product; that is checked by
    the gate notebooks, not hidden by a default row.
"""

from pyspark import pipelines as dp
from pyspark.sql import functions as F
from pyspark.sql import Window

CATALOG = spark.conf.get("hls.catalog")


@dp.materialized_view(
    name="omop_person",
    comment="OMOP person rows derived from governed FHIR Patient resources.",
    table_properties={"quality": "gold"},
)
def omop_person():
    return (
        spark.read.table(f"{CATALOG}.silver.patient")
        .select(
            F.col("resource_id").alias("person_source_value"),
            F.get_json_object("resource_json", "$.gender").alias("gender_source_value"),
            F.to_date(F.get_json_object("resource_json", "$.birthDate")).alias("birth_date"),
            F.get_json_object("resource_json", "$.address[0].state").alias("state_source_value"),
        )
        .withColumn("person_id", F.xxhash64("person_source_value"))
    )


@dp.materialized_view(
    name="omop_visit_occurrence",
    comment="OMOP visit rows derived from governed FHIR Encounter resources.",
    table_properties={"quality": "gold"},
)
def omop_visit_occurrence():
    return (
        spark.read.table(f"{CATALOG}.silver.encounter")
        .select(
            F.col("resource_id").alias("visit_source_value"),
            F.col("subject_reference").alias("person_source_reference"),
            F.get_json_object("resource_json", "$.class.code").alias("visit_concept_source_value"),
            F.to_timestamp(F.get_json_object("resource_json", "$.period.start")).alias("visit_start_datetime"),
            F.to_timestamp(F.get_json_object("resource_json", "$.period.end")).alias("visit_end_datetime"),
        )
        .withColumn("visit_occurrence_id", F.xxhash64("visit_source_value"))
    )


@dp.materialized_view(
    name="fact_claim",
    comment="Claim facts combining batch coverage context with streaming claim events.",
    table_properties={"quality": "gold"},
)
def fact_claim():
    coverage = (
        spark.read.table(f"{CATALOG}.silver.coverage")
        .select(
            F.col("subject_reference").alias("patient_reference"),
            F.get_json_object("resource_json", "$.payor[0].display").alias("payer_name"),
            F.get_json_object("resource_json", "$.type.coding[0].code").alias("payer_category"),
        )
        .dropDuplicates(["patient_reference"])
    )
    return (
        spark.read.table(f"{CATALOG}.silver.claim_events")
        .withColumn("patient_reference", F.concat(F.lit("Patient/"), F.col("patient_id")))
        .join(coverage, on="patient_reference", how="left")
        .select(
            "claim_id",
            "patient_reference",
            "payer_id",
            F.coalesce("payer_category", F.lit("Unknown")).alias("payer_category"),
            "claim_type",
            "submitted_at",
            "billed_amount",
            "allowed_amount",
        )
        .withColumn("denied_amount", F.col("billed_amount") - F.coalesce("allowed_amount", F.lit(0.0)))
    )


@dp.materialized_view(
    name="agg_utilization_by_payer",
    comment="Cost and utilization aggregates stratified by payer category.",
    table_properties={"quality": "gold"},
)
def agg_utilization_by_payer():
    return (
        spark.read.table(f"{CATALOG}.gold.fact_claim")
        .groupBy("payer_category")
        .agg(
            F.countDistinct("claim_id").alias("claim_count"),
            F.countDistinct("patient_reference").alias("patient_count"),
            F.sum("billed_amount").alias("billed_amount"),
            F.sum("allowed_amount").alias("allowed_amount"),
            F.sum("denied_amount").alias("denied_amount"),
        )
        .withColumn("denial_rate", F.col("denied_amount") / F.col("billed_amount"))
    )


@dp.materialized_view(
    name="payer_worklist",
    comment="Unified payer operations worklist over current claim behavior.",
    table_properties={"quality": "gold"},
)
def payer_worklist():
    claims = spark.read.table(f"{CATALOG}.gold.fact_claim")
    per_patient = claims.groupBy("patient_reference", "payer_category").agg(
        F.countDistinct("claim_id").alias("claim_count"),
        F.sum("billed_amount").alias("billed_amount"),
        F.sum("denied_amount").alias("denied_amount"),
        F.max("submitted_at").alias("last_claim_at"),
    )
    return (
        per_patient.withColumn(
            "worklist_reason",
            F.when(F.col("denied_amount") > 0, F.lit("DENIAL_REVIEW"))
            .when(F.col("billed_amount") > 25000, F.lit("HIGH_COST"))
            .when(F.col("claim_count") > 5, F.lit("UTILIZATION_REVIEW")),
        )
        .where(F.col("worklist_reason").isNotNull())
        .withColumn(
            "priority",
            F.when(F.col("worklist_reason") == "DENIAL_REVIEW", F.lit(1))
            .when(F.col("worklist_reason") == "HIGH_COST", F.lit(2))
            .otherwise(F.lit(3)),
        )
    )


@dp.materialized_view(
    name="imaging_report_facts",
    comment="Study-level facts and viewer paths for imaging reports and OHIF links.",
    table_properties={"quality": "gold"},
)
def imaging_report_facts():
    return (
        spark.read.table(f"{CATALOG}.silver.imaging_instance")
        .groupBy("study_uid", "imaging_study_resource_id", "patient_reference")
        .agg(
            F.countDistinct("series_uid").alias("series_count"),
            F.count("object_path").alias("instance_count"),
            F.sum("object_bytes").alias("study_bytes"),
            F.min("object_path").alias("sample_object_path"),
        )
    )


def _patient_identity():
    patients = spark.read.table(f"{CATALOG}.silver.patient")
    return patients.select(
        F.col("resource_id").alias("patient_id"),
        F.concat(F.lit("Patient/"), F.col("resource_id")).alias("patient_reference"),
        F.concat_ws(
            " ",
            F.get_json_object("resource_json", "$.name[0].prefix[0]"),
            F.get_json_object("resource_json", "$.name[0].given[0]"),
            F.get_json_object("resource_json", "$.name[0].given[1]"),
            F.get_json_object("resource_json", "$.name[0].family"),
        ).alias("patient_name"),
        F.get_json_object("resource_json", "$.gender").alias("gender"),
        F.to_date(F.get_json_object("resource_json", "$.birthDate")).alias("birth_date"),
        F.get_json_object("resource_json", "$.address[0].city").alias("city"),
        F.get_json_object("resource_json", "$.address[0].state").alias("state"),
        F.get_json_object("resource_json", "$.address[0].postalCode").alias("postal_code"),
    ).withColumn("age_years", F.floor(F.months_between(F.current_date(), "birth_date") / 12.0))


def _clinical_summary(table_name: str, patient_column: str, label_path: str, prefix: str):
    source = spark.read.table(f"{CATALOG}.silver.{table_name}")
    return source.groupBy(F.col(patient_column).alias("patient_reference")).agg(
        F.countDistinct("resource_id").alias(f"{prefix}_count"),
        F.concat_ws(
            ", ",
            F.sort_array(F.collect_set(F.get_json_object("resource_json", label_path))),
        ).alias(f"{prefix}_summary"),
    )


def _device_associations():
    return (
        spark.read.table(f"{CATALOG}.silver.device_association")
        .select(
            "subject_reference",
            F.regexp_replace(
                F.get_json_object("resource_json", "$.extension[0].valueReference.reference"),
                "^Device/",
                "",
            ).alias("device_id"),
        )
        .where(F.col("subject_reference").isNotNull() & F.col("device_id").isNotNull())
        .dropDuplicates(["subject_reference", "device_id"])
    )


@dp.materialized_view(
    name="agent_patient_device",
    comment="Governed patient-to-device links with the latest typed telemetry for Patient 360 and triage agents.",
    table_properties={"quality": "gold", "agent.domain": "clinical"},
)
def agent_patient_device():
    latest = (
        spark.read.table(f"{CATALOG}.silver.telemetry")
        .groupBy("device_id")
        .agg(
            F.max(
                F.struct(
                    "observed_at",
                    "spo2",
                    "pulse_rate",
                    "perfusion_index",
                    "signal_quality",
                )
            ).alias("latest")
        )
        .select(
            "device_id",
            F.col("latest.observed_at").alias("latest_reading_utc"),
            F.from_utc_timestamp(F.col("latest.observed_at"), "America/New_York").alias("latest_reading_eastern"),
            F.col("latest.spo2").alias("latest_spo2"),
            F.col("latest.pulse_rate").alias("latest_pulse_rate"),
            F.col("latest.perfusion_index").alias("latest_perfusion_index"),
            F.col("latest.signal_quality").alias("latest_signal_quality"),
        )
    )
    return (
        _device_associations()
        .withColumnRenamed("subject_reference", "patient_reference")
        .join(_patient_identity(), on="patient_reference", how="left")
        .join(latest, on="device_id", how="left")
        .select(
            "patient_id",
            "patient_reference",
            "patient_name",
            "gender",
            "birth_date",
            "age_years",
            "city",
            "state",
            "postal_code",
            "device_id",
            "latest_reading_utc",
            "latest_reading_eastern",
            "latest_spo2",
            "latest_pulse_rate",
            "latest_perfusion_index",
            "latest_signal_quality",
        )
    )


@dp.materialized_view(
    name="agent_patient_360",
    comment="One governed row per patient with clinical, device, medication, procedure, immunization, and imaging summaries.",
    table_properties={"quality": "gold", "agent.domain": "clinical"},
)
def agent_patient_360():
    conditions = _clinical_summary("condition", "subject_reference", "$.code.coding[0].display", "condition")
    medications = _clinical_summary(
        "medication_request",
        "subject_reference",
        "$.medicationCodeableConcept.coding[0].display",
        "medication",
    )
    procedures = _clinical_summary("procedure", "subject_reference", "$.code.coding[0].display", "procedure")
    immunizations = _clinical_summary(
        "immunization",
        "patient_reference",
        "$.vaccineCode.coding[0].display",
        "immunization",
    )
    imaging = _clinical_summary(
        "imaging_study",
        "subject_reference",
        "$.series[0].modality.code",
        "imaging_study",
    )
    devices = _device_associations().groupBy(F.col("subject_reference").alias("patient_reference")).agg(
        F.countDistinct("device_id").alias("device_count"),
        F.concat_ws(", ", F.sort_array(F.collect_set("device_id"))).alias("device_ids"),
    )
    latest = (
        spark.read.table(f"{CATALOG}.gold.agent_patient_device")
        .groupBy("patient_reference")
        .agg(
            F.max(
                F.struct(
                    "latest_reading_utc",
                    "device_id",
                    "latest_reading_eastern",
                    "latest_spo2",
                    "latest_pulse_rate",
                    "latest_perfusion_index",
                    "latest_signal_quality",
                )
            ).alias("latest")
        )
        .select(
            "patient_reference",
            F.col("latest.device_id").alias("latest_device_id"),
            F.col("latest.latest_reading_utc").alias("latest_reading_utc"),
            F.col("latest.latest_reading_eastern").alias("latest_reading_eastern"),
            F.col("latest.latest_spo2").alias("latest_spo2"),
            F.col("latest.latest_pulse_rate").alias("latest_pulse_rate"),
            F.col("latest.latest_perfusion_index").alias("latest_perfusion_index"),
            F.col("latest.latest_signal_quality").alias("latest_signal_quality"),
        )
    )
    summary = _patient_identity()
    for product in (conditions, medications, procedures, immunizations, imaging, devices, latest):
        summary = summary.join(product, on="patient_reference", how="left")
    return summary.fillna(
        0,
        subset=[
            "condition_count",
            "medication_count",
            "procedure_count",
            "immunization_count",
            "imaging_study_count",
            "device_count",
        ],
    )


@dp.materialized_view(
    name="agent_clinical_triage",
    comment="Fifteen-minute device triage with Fabric-equivalent SpO2 and pulse thresholds plus patient context.",
    table_properties={"quality": "gold", "agent.domain": "clinical"},
)
def agent_clinical_triage():
    telemetry = spark.read.table(f"{CATALOG}.silver.telemetry").where(
        F.col("observed_at") >= F.expr("current_timestamp() - INTERVAL 15 MINUTES")
    )
    current = telemetry.groupBy("device_id").agg(
        F.count("*").alias("reading_count"),
        F.min("spo2").alias("min_spo2"),
        F.avg("spo2").alias("avg_spo2"),
        F.min("pulse_rate").alias("min_pulse_rate"),
        F.max("pulse_rate").alias("max_pulse_rate"),
        F.avg("pulse_rate").alias("avg_pulse_rate"),
        F.max("observed_at").alias("last_reading_utc"),
    )
    classified = (
        current.withColumn("has_spo2_alert", F.col("min_spo2") < 94)
        .withColumn(
            "has_pulse_alert",
            (F.col("max_pulse_rate") > 110) | (F.col("min_pulse_rate") < 50),
        )
        .where(F.col("has_spo2_alert") | F.col("has_pulse_alert"))
        .withColumn(
            "alert_tier",
            F.when(
                (F.col("min_spo2") < 85)
                | (F.col("max_pulse_rate") > 150)
                | (F.col("min_pulse_rate") < 40),
                F.lit("CRITICAL"),
            )
            .when(
                (F.col("min_spo2") < 90)
                | (F.col("max_pulse_rate") > 130)
                | (F.col("min_pulse_rate") < 45),
                F.lit("URGENT"),
            )
            .otherwise(F.lit("WARNING")),
        )
        .withColumn(
            "alert_type",
            F.when(F.col("has_spo2_alert") & F.col("has_pulse_alert"), F.lit("MULTI_METRIC"))
            .when(F.col("has_spo2_alert"), F.lit("SPO2_LOW"))
            .otherwise(F.lit("PULSE_ABNORMAL")),
        )
        .withColumn(
            "priority_rank",
            F.when(F.col("alert_tier") == "CRITICAL", F.lit(1))
            .when(F.col("alert_tier") == "URGENT", F.lit(2))
            .otherwise(F.lit(3)),
        )
        .withColumn(
            "last_reading_eastern",
            F.from_utc_timestamp("last_reading_utc", "America/New_York"),
        )
    )
    context = spark.read.table(f"{CATALOG}.gold.agent_patient_360").select(
        "patient_reference",
        "condition_summary",
        "medication_summary",
        "procedure_summary",
        "imaging_study_summary",
    )
    device_context = spark.read.table(f"{CATALOG}.gold.agent_patient_device").select(
        "device_id",
        "patient_id",
        "patient_reference",
        "patient_name",
        "city",
        "state",
    )
    return (
        classified.join(device_context, on="device_id", how="left")
        .join(context, on="patient_reference", how="left")
        .select(
            "priority_rank",
            "alert_tier",
            "alert_type",
            "device_id",
            "patient_id",
            "patient_reference",
            "patient_name",
            "city",
            "state",
            "min_spo2",
            F.round("avg_spo2", 1).alias("avg_spo2"),
            "min_pulse_rate",
            "max_pulse_rate",
            F.round("avg_pulse_rate", 1).alias("avg_pulse_rate"),
            "reading_count",
            "last_reading_utc",
            "last_reading_eastern",
            "condition_summary",
            "medication_summary",
            "procedure_summary",
            "imaging_study_summary",
        )
    )


@dp.materialized_view(
    name="agent_imaging_cohort",
    comment="Study and modality grain for imaging cohort discovery with patient and object-count context.",
    table_properties={"quality": "gold", "agent.domain": "imaging"},
)
def agent_imaging_cohort():
    series_schema = "array<struct<uid:string,number:int,modality:struct<system:string,code:string,display:string>>>"
    studies = (
        spark.read.table(f"{CATALOG}.silver.imaging_study")
        .select(
            F.col("resource_id").alias("imaging_study_resource_id"),
            "subject_reference",
            F.col("status").alias("imaging_status"),
            F.to_timestamp(F.get_json_object("resource_json", "$.started")).alias("started_at"),
            F.get_json_object("resource_json", "$.description").alias("study_description"),
            F.get_json_object("resource_json", "$.identifier[0].value").alias("study_uid"),
            F.from_json(F.get_json_object("resource_json", "$.series"), series_schema).alias("series"),
        )
        .withColumn("series_item", F.explode_outer("series"))
        .select(
            "imaging_study_resource_id",
            "subject_reference",
            "imaging_status",
            "started_at",
            "study_description",
            "study_uid",
            F.coalesce(F.col("series_item.modality.code"), F.lit("UNKNOWN")).alias("modality_code"),
        )
        .dropDuplicates(["imaging_study_resource_id", "modality_code"])
    )
    facts = spark.read.table(f"{CATALOG}.gold.imaging_report_facts").select(
        "imaging_study_resource_id",
        "series_count",
        "instance_count",
        "study_bytes",
        "sample_object_path",
    )
    return (
        studies.join(facts, on="imaging_study_resource_id", how="left")
        .join(
            _patient_identity().withColumnRenamed("patient_reference", "subject_reference"),
            on="subject_reference",
            how="left",
        )
        .select(
            "imaging_study_resource_id",
            "study_uid",
            "modality_code",
            "imaging_status",
            "started_at",
            "study_description",
            "patient_id",
            F.col("subject_reference").alias("patient_reference"),
            "patient_name",
            "gender",
            "birth_date",
            "age_years",
            "city",
            "state",
            "series_count",
            "instance_count",
            "study_bytes",
            "sample_object_path",
        )
    )


def _quality_gap(denominator, compliant, measure_id: str, measure_name: str, action: str):
    return (
        denominator.select("patient_id")
        .dropDuplicates()
        .join(compliant.select("patient_id").dropDuplicates().withColumn("quality_met", F.lit(True)), "patient_id", "left")
        .where(F.col("quality_met").isNull())
        .select(
            "patient_id",
            F.lit(measure_id).alias("measure_id"),
            F.lit(measure_name).alias("gap_type"),
            F.lit("open").alias("gap_status"),
            F.lit(90).alias("days_overdue"),
            F.lit(action).alias("recommended_action"),
        )
    )


@dp.materialized_view(
    name="agent_care_gaps",
    comment="Open CMS-oriented care gaps derived deterministically from governed FHIR conditions, observations, medications, and immunizations.",
    table_properties={"quality": "gold", "agent.domain": "payer"},
)
def agent_care_gaps():
    patients = _patient_identity().select("patient_id", "age_years")
    conditions = (
        spark.read.table(f"{CATALOG}.silver.condition")
        .select(
            F.regexp_replace("subject_reference", "^Patient/", "").alias("patient_id"),
            F.get_json_object("resource_json", "$.code.coding[0].code").alias("condition_code"),
            F.get_json_object("resource_json", "$.clinicalStatus.coding[0].code").alias("clinical_status"),
        )
        .where(F.col("patient_id").isNotNull())
    )
    observations = (
        spark.read.table(f"{CATALOG}.silver.observation")
        .select(
            F.regexp_replace("subject_reference", "^Patient/", "").alias("patient_id"),
            F.get_json_object("resource_json", "$.code.coding[0].code").alias("loinc_code"),
            F.get_json_object("resource_json", "$.valueQuantity.value").cast("double").alias("value"),
            F.to_date(F.get_json_object("resource_json", "$.effectiveDateTime")).alias("observed_date"),
        )
        .where(F.year("observed_date") == F.year(F.current_date()))
    )
    immunizations = (
        spark.read.table(f"{CATALOG}.silver.immunization")
        .select(
            F.regexp_replace("patient_reference", "^Patient/", "").alias("patient_id"),
            F.get_json_object("resource_json", "$.vaccineCode.coding[0].code").alias("vaccine_code"),
            F.to_date(F.get_json_object("resource_json", "$.occurrenceDateTime")).alias("immunization_date"),
        )
        .where(F.year("immunization_date") == F.year(F.current_date()))
    )
    medications = spark.read.table(f"{CATALOG}.silver.medication_request").select(
        F.regexp_replace("subject_reference", "^Patient/", "").alias("patient_id"),
        F.lower(F.get_json_object("resource_json", "$.medicationCodeableConcept.coding[0].display")).alias(
            "medication_name"
        ),
    )
    diabetes = conditions.where(
        F.col("condition_code").isin("44054006", "73211009")
        & F.col("clinical_status").isin("active", "recurrence")
    ).select("patient_id")
    hypertension = conditions.where(
        (F.col("condition_code") == "59621000") & F.col("clinical_status").isin("active", "recurrence")
    ).select("patient_id")
    heart_failure = conditions.where(
        F.col("condition_code").isin("42343007", "84114007")
        & F.col("clinical_status").isin("active", "recurrence")
    ).select("patient_id")
    latest_hba1c = (
        observations.where(F.col("loinc_code") == "4548-4")
        .withColumn("rn", F.row_number().over(Window.partitionBy("patient_id").orderBy(F.desc("observed_date"))))
        .where(F.col("rn") == 1)
        .where(F.col("value") <= 9.0)
        .select("patient_id")
    )
    latest_systolic = (
        observations.where(F.col("loinc_code") == "8480-6")
        .withColumn("rn", F.row_number().over(Window.partitionBy("patient_id").orderBy(F.desc("observed_date"))))
        .where(F.col("rn") == 1)
        .select("patient_id", F.col("value").alias("systolic"))
    )
    latest_diastolic = (
        observations.where(F.col("loinc_code") == "8462-4")
        .withColumn("rn", F.row_number().over(Window.partitionBy("patient_id").orderBy(F.desc("observed_date"))))
        .where(F.col("rn") == 1)
        .select("patient_id", F.col("value").alias("diastolic"))
    )
    controlled_bp = latest_systolic.join(latest_diastolic, "patient_id").where(
        (F.col("systolic") < 140) & (F.col("diastolic") < 90)
    )
    adult_diabetes = patients.join(diabetes, "patient_id").where(F.col("age_years").between(18, 75))
    adult_hypertension = patients.join(hypertension, "patient_id").where(F.col("age_years").between(18, 85))
    adults = patients.where(F.col("age_years") >= 18)
    older_adults = patients.where(F.col("age_years") >= 65)
    flu_eligible = patients.where(F.col("age_years") >= 1)
    nephropathy_screened = observations.where(
        F.col("loinc_code").isin("14959-1", "14957-5", "13705-9", "1754-1", "1755-8")
    ).select("patient_id").unionByName(
        medications.where(
            F.col("medication_name").rlike(
                "lisinopril|enalapril|ramipril|losartan|valsartan|irbesartan|olmesartan|candesartan|benazepril|captopril|fosinopril|quinapril|trandolapril|perindopril|eprosartan|telmisartan|azilsartan"
            )
        ).select("patient_id")
    )
    beta_blocker = medications.where(
        F.col("medication_name").rlike(
            "metoprolol|carvedilol|bisoprolol|atenolol|propranolol|nebivolol|nadolol|labetalol"
        )
    ).select("patient_id")
    gaps = [
        _quality_gap(
            adult_diabetes,
            latest_hba1c,
            "CMS122v12",
            "Diabetes: Hemoglobin A1c Poor Control",
            "Order HbA1c lab test; consider medication adjustment",
        ),
        _quality_gap(
            adult_hypertension,
            controlled_bp,
            "CMS165v12",
            "Controlling High Blood Pressure",
            "Recheck blood pressure; consider medication titration",
        ),
        _quality_gap(
            adults,
            observations.where(F.col("loinc_code") == "39156-5"),
            "CMS69v12",
            "Preventive Care: BMI Screening",
            "Record BMI and create follow-up plan",
        ),
        _quality_gap(
            older_adults,
            immunizations.where(F.col("vaccine_code").isin("33", "100", "109", "133", "152", "215")),
            "CMS127v12",
            "Pneumococcal Vaccination Status",
            "Administer pneumococcal vaccine (PCV20 or PPSV23)",
        ),
        _quality_gap(
            flu_eligible,
            immunizations.where(
                F.col("vaccine_code").isin("140", "141", "150", "155", "158", "161", "166", "171", "185", "186", "197", "205")
            ),
            "CMS147v13",
            "Preventive Care: Influenza Immunization",
            "Administer seasonal influenza vaccine",
        ),
        _quality_gap(
            adult_diabetes,
            nephropathy_screened,
            "CMS134v12",
            "Diabetes: Medical Attention for Nephropathy",
            "Order urine albumin test or start ACE/ARB therapy",
        ),
        _quality_gap(
            patients.join(heart_failure, "patient_id").where(F.col("age_years") >= 18),
            beta_blocker,
            "CMS144v12",
            "Heart Failure: Beta-Blocker Therapy",
            "Start beta-blocker therapy (carvedilol, metoprolol, bisoprolol)",
        ),
    ]
    result = gaps[0]
    for gap in gaps[1:]:
        result = result.unionByName(gap)
    return result.withColumn("scenario_source", F.lit("derived_from_fhir_quality_rules")).withColumn(
        "refreshed_at", F.current_timestamp()
    )


@dp.materialized_view(
    name="agent_fraud_risk",
    comment="Fabric-equivalent 60-minute claim fraud scoring with provider velocity, amount outlier, denial-pattern, and upcoding evidence.",
    table_properties={"quality": "gold", "agent.domain": "payer"},
)
def agent_fraud_risk():
    recent = spark.read.table(f"{CATALOG}.silver.claim_events").where(
        (F.col("submitted_at") >= F.expr("current_timestamp() - INTERVAL 60 MINUTES"))
        & (F.col("event_type") == "CLAIM_SUBMITTED")
    )
    provider_stats = recent.groupBy("provider_id").agg(
        F.count("*").alias("provider_claims"),
        F.avg("billed_amount").alias("provider_avg_amount"),
        F.stddev("billed_amount").alias("provider_stdev_amount"),
    ).withColumn("claims_per_hour", F.col("provider_claims").cast("double"))
    scored = (
        recent.join(provider_stats, "provider_id", "left")
        .withColumn(
            "amount_zscore",
            F.when(
                F.col("provider_stdev_amount") > 0,
                (F.col("billed_amount") - F.col("provider_avg_amount")) / F.col("provider_stdev_amount"),
            ).otherwise(F.lit(0.0)),
        )
        .withColumn(
            "velocity_points",
            F.when(F.col("claims_per_hour") >= 20.0, F.lit(30.0))
            .when(F.col("claims_per_hour") >= 10.0, F.lit(15.0))
            .otherwise(F.lit(0.0)),
        )
        .withColumn(
            "amount_points",
            F.when(
                (F.col("amount_zscore") >= 3.0)
                | F.lower(F.coalesce("injected_fraud_flags", F.lit(""))).contains("amount_outlier"),
                F.lit(25.0),
            ).otherwise(F.lit(0.0)),
        )
        .withColumn(
            "denial_points",
            F.when(
                F.lower(F.coalesce("injected_fraud_flags", F.lit(""))).contains("denial_pattern"),
                F.lit(25.0),
            ).otherwise(F.lit(0.0)),
        )
        .withColumn(
            "upcoding_points",
            F.when(
                (F.col("procedure_code") == "99215")
                | F.lower(F.coalesce("injected_fraud_flags", F.lit(""))).contains("upcoding"),
                F.lit(20.0),
            ).otherwise(F.lit(0.0)),
        )
        .withColumn(
            "fraud_score",
            F.col("velocity_points") + F.col("amount_points") + F.col("denial_points") + F.col("upcoding_points"),
        )
        .withColumn(
            "risk_tier",
            F.when(F.col("fraud_score") >= 80.0, F.lit("CRITICAL"))
            .when(F.col("fraud_score") >= 50.0, F.lit("HIGH"))
            .when(F.col("fraud_score") >= 25.0, F.lit("MEDIUM"))
            .otherwise(F.lit("LOW")),
        )
        .withColumn(
            "fraud_flags",
            F.concat_ws(
                "|",
                F.when(F.col("velocity_points") > 0, F.lit("velocity_burst")),
                F.when(F.col("amount_points") > 0, F.lit("amount_outlier")),
                F.when(F.col("denial_points") > 0, F.lit("denial_pattern")),
                F.when(F.col("upcoding_points") > 0, F.lit("upcoding")),
                F.when(F.length(F.coalesce("injected_fraud_flags", F.lit(""))) > 0, F.col("injected_fraud_flags")),
            ),
        )
    )
    return scored.select(
        F.concat(F.lit("FRAUD-"), F.col("claim_id")).alias("score_id"),
        F.current_timestamp().alias("score_timestamp"),
        "claim_id",
        "patient_id",
        "provider_id",
        "facility_id",
        "payer_id",
        "diagnosis_code",
        "procedure_code",
        "claim_type",
        "submitted_at",
        "billed_amount",
        "fraud_score",
        "fraud_flags",
        "risk_tier",
        "claims_per_hour",
        "amount_zscore",
        "latitude",
        "longitude",
    )


@dp.materialized_view(
    name="agent_high_cost_members",
    comment="Fabric-equivalent 90-day member cost trajectory with 30-day spend, emergency utilization, trend, and risk tier.",
    table_properties={"quality": "gold", "agent.domain": "payer"},
)
def agent_high_cost_members():
    claims = spark.read.table(f"{CATALOG}.silver.claim_events").where(
        F.col("submitted_at") >= F.expr("current_timestamp() - INTERVAL 90 DAYS")
    )
    summarized = claims.groupBy("patient_id").agg(
        F.sum(
            F.when(
                F.col("submitted_at") >= F.expr("current_timestamp() - INTERVAL 30 DAYS"),
                F.col("billed_amount"),
            ).otherwise(F.lit(0.0))
        ).alias("rolling_spend_30d"),
        F.sum("billed_amount").alias("rolling_spend_90d"),
        F.sum(
            F.when(
                (F.col("submitted_at") >= F.expr("current_timestamp() - INTERVAL 30 DAYS"))
                & (
                    (F.lower(F.col("claim_type")) == "emergency")
                    | F.col("procedure_code").isin("99281", "99282", "99283", "99284", "99285")
                ),
                F.lit(1),
            ).otherwise(F.lit(0))
        ).alias("ed_visits_30d"),
        F.max("submitted_at").alias("last_claim_time"),
        F.first("latitude", ignorenulls=True).alias("latitude"),
        F.first("longitude", ignorenulls=True).alias("longitude"),
    )
    return (
        summarized.withColumn(
            "cost_trend",
            F.when(
                (F.col("rolling_spend_90d") > 0)
                & ((F.col("rolling_spend_30d") * 3.0) > (F.col("rolling_spend_90d") * 1.25)),
                F.lit("ACCELERATING"),
            )
            .when(
                (F.col("rolling_spend_90d") > 0)
                & (F.col("rolling_spend_30d") >= (F.col("rolling_spend_90d") * 0.40)),
                F.lit("RISING"),
            )
            .otherwise(F.lit("STABLE")),
        )
        .withColumn(
            "risk_tier",
            F.when(
                (F.col("rolling_spend_30d") > 100000.0) | (F.col("ed_visits_30d") >= 5),
                F.lit("CRITICAL"),
            )
            .when(
                (F.col("rolling_spend_30d") > 50000.0) | (F.col("ed_visits_30d") >= 3),
                F.lit("HIGH"),
            )
            .when(F.col("rolling_spend_30d") > 15000.0, F.lit("MEDIUM"))
            .otherwise(F.lit("LOW")),
        )
        .where(F.col("risk_tier") != "LOW")
        .select(
            F.concat(F.lit("HIGHCOST-"), F.col("patient_id")).alias("alert_id"),
            F.current_timestamp().alias("alert_timestamp"),
            "patient_id",
            "rolling_spend_30d",
            "rolling_spend_90d",
            "ed_visits_30d",
            F.lit(False).alias("readmission_flag"),
            "risk_tier",
            "cost_trend",
            "latitude",
            "longitude",
            "last_claim_time",
        )
    )


@dp.materialized_view(
    name="agent_payer_worklist",
    comment="Unified human-review worklist across fraud, high-cost, and care-gap signals for the Payer Ops Genie Agent.",
    table_properties={"quality": "gold", "agent.domain": "payer"},
)
def agent_payer_worklist():
    fraud = (
        spark.read.table(f"{CATALOG}.gold.agent_fraud_risk")
        .where(F.col("risk_tier").isin("CRITICAL", "HIGH"))
        .select(
            F.col("score_id").alias("alert_id"),
            F.col("score_timestamp").alias("alert_time"),
            F.lit("FRAUD").alias("alert_domain"),
            F.col("risk_tier").alias("priority"),
            "patient_id",
            "provider_id",
            "claim_id",
            F.col("fraud_score").alias("metric_value"),
            F.lit("fraud_score").alias("metric_name"),
            F.concat(F.lit("Fraud risk evidence for claim "), "claim_id", F.lit(" from provider "), "provider_id").alias(
                "message"
            ),
            "latitude",
            "longitude",
            F.lit("SIU review").alias("recommended_action"),
            F.lit("derived_from_claim_stream").alias("scenario_source"),
        )
    )
    high_cost = (
        spark.read.table(f"{CATALOG}.gold.agent_high_cost_members")
        .where(F.col("risk_tier").isin("CRITICAL", "HIGH"))
        .select(
            "alert_id",
            F.col("alert_timestamp").alias("alert_time"),
            F.lit("HIGH_COST").alias("alert_domain"),
            F.col("risk_tier").alias("priority"),
            "patient_id",
            F.lit(None).cast("string").alias("provider_id"),
            F.lit(None).cast("string").alias("claim_id"),
            F.col("rolling_spend_30d").alias("metric_value"),
            F.lit("rolling_spend_30d").alias("metric_name"),
            F.concat(
                F.lit("30-day spend $"),
                F.round("rolling_spend_30d", 2).cast("string"),
                F.lit("; trend="),
                "cost_trend",
            ).alias("message"),
            "latitude",
            "longitude",
            F.lit("Care management review").alias("recommended_action"),
            F.lit("derived_from_claim_stream").alias("scenario_source"),
        )
    )
    care_gaps = spark.read.table(f"{CATALOG}.gold.agent_care_gaps").select(
        F.concat(F.lit("CAREGAP-"), "patient_id", F.lit("-"), "measure_id").alias("alert_id"),
        F.col("refreshed_at").alias("alert_time"),
        F.lit("CARE_GAP").alias("alert_domain"),
        F.when(F.col("days_overdue") >= 90, F.lit("HIGH")).otherwise(F.lit("MEDIUM")).alias("priority"),
        "patient_id",
        F.lit(None).cast("string").alias("provider_id"),
        F.lit(None).cast("string").alias("claim_id"),
        F.col("days_overdue").cast("double").alias("metric_value"),
        F.lit("gap_days_overdue").alias("metric_name"),
        F.concat("gap_type", F.lit(": "), "recommended_action").alias("message"),
        F.lit(None).cast("double").alias("latitude"),
        F.lit(None).cast("double").alias("longitude"),
        F.col("recommended_action"),
        "scenario_source",
    )
    return fraud.unionByName(high_cost).unionByName(care_gaps).withColumn(
        "priority_rank",
        F.when(F.col("priority") == "CRITICAL", F.lit(1))
        .when(F.col("priority") == "HIGH", F.lit(2))
        .otherwise(F.lit(3)),
    )


@dp.materialized_view(
    name="agent_cross_domain_context",
    comment="Relational replacement for the Fabric ontology agent across patients, devices, clinical alerts, claims, payer risk, imaging, and care gaps.",
    table_properties={"quality": "gold", "agent.domain": "cross-domain"},
)
def agent_cross_domain_context():
    patients = spark.read.table(f"{CATALOG}.gold.agent_patient_360")
    devices = spark.read.table(f"{CATALOG}.gold.agent_patient_device").select(
        "patient_id",
        "patient_reference",
        "device_id",
        "latest_reading_utc",
        "latest_spo2",
        "latest_pulse_rate",
    )
    triage = (
        spark.read.table(f"{CATALOG}.gold.agent_clinical_triage")
        .withColumn(
            "rn",
            F.row_number().over(
                Window.partitionBy("device_id").orderBy(F.asc("priority_rank"), F.desc("last_reading_utc"))
            ),
        )
        .where(F.col("rn") == 1)
        .select(
            "device_id",
            F.col("alert_tier"),
            F.col("alert_type"),
            F.col("last_reading_utc").alias("alert_time"),
            F.col("min_spo2").alias("alert_spo2"),
            F.col("max_pulse_rate").alias("alert_pulse_rate"),
        )
    )
    payer = (
        spark.read.table(f"{CATALOG}.gold.agent_payer_worklist")
        .withColumn(
            "rn",
            F.row_number().over(
                Window.partitionBy("patient_id").orderBy(F.asc("priority_rank"), F.desc("alert_time"))
            ),
        )
        .where(F.col("rn") == 1)
        .select(
            "patient_id",
            F.col("alert_domain").alias("payer_alert_domain"),
            F.col("priority").alias("payer_priority"),
            F.col("claim_id").alias("payer_claim_id"),
            F.col("provider_id").alias("payer_provider_id"),
            F.col("metric_name").alias("payer_metric_name"),
            F.col("metric_value").alias("payer_metric_value"),
            F.col("recommended_action").alias("payer_recommended_action"),
        )
    )
    high_cost = spark.read.table(f"{CATALOG}.gold.agent_high_cost_members").select(
        "patient_id",
        F.col("risk_tier").alias("high_cost_risk_tier"),
        "cost_trend",
        "rolling_spend_30d",
        "rolling_spend_90d",
        "ed_visits_30d",
    )
    care_gap = (
        spark.read.table(f"{CATALOG}.gold.agent_care_gaps")
        .withColumn(
            "rn",
            F.row_number().over(Window.partitionBy("patient_id").orderBy(F.desc("days_overdue"), F.asc("measure_id"))),
        )
        .where(F.col("rn") == 1)
        .select(
            "patient_id",
            F.col("measure_id").alias("care_gap_measure_id"),
            F.col("gap_type").alias("care_gap_measure"),
            F.col("gap_status").alias("care_gap_status"),
            F.col("recommended_action").alias("care_gap_recommended_action"),
        )
    )
    payer_category = spark.read.table(f"{CATALOG}.gold.fact_claim").groupBy("patient_reference").agg(
        F.first("payer_id", ignorenulls=True).alias("payer_id"),
        F.first("payer_category", ignorenulls=True).alias("payer_category"),
    )
    return (
        devices.join(
            patients.select(
                "patient_id",
                "patient_reference",
                "patient_name",
                "gender",
                "age_years",
                "city",
                "state",
                "condition_count",
                "condition_summary",
                "medication_summary",
                "procedure_summary",
                "imaging_study_count",
                "imaging_study_summary",
            ),
            on=["patient_id", "patient_reference"],
            how="left",
        )
        .join(triage, "device_id", "left")
        .join(payer, "patient_id", "left")
        .join(high_cost, "patient_id", "left")
        .join(care_gap, "patient_id", "left")
        .join(payer_category, "patient_reference", "left")
        .withColumn("scenario_source", F.lit("derived_from_governed_delta"))
    )


@dp.materialized_view(
    name="agent_healthcare_relationships",
    comment="Typed healthcare edge list for deterministic patient-device-clinical-imaging-payer traversal in the Healthcare Graph Genie Agent.",
    table_properties={"quality": "gold", "agent.domain": "cross-domain"},
)
def agent_healthcare_relationships():
    def edge(
        frame,
        source_type,
        source_id,
        relationship_type,
        target_type,
        target_id,
        target_label,
        event_time,
        metric_name,
        metric_value,
        scenario_source,
    ):
        return frame.select(
            source_type.alias("source_type"),
            source_id.cast("string").alias("source_id"),
            relationship_type.alias("relationship_type"),
            target_type.alias("target_type"),
            target_id.cast("string").alias("target_id"),
            target_label.cast("string").alias("target_label"),
            event_time.cast("timestamp").alias("event_time"),
            metric_name.cast("string").alias("metric_name"),
            metric_value.cast("double").alias("metric_value"),
            scenario_source.alias("scenario_source"),
        )

    patient_device = edge(
        spark.read.table(f"{CATALOG}.gold.agent_patient_device"),
        F.lit("Patient"),
        F.col("patient_id"),
        F.lit("HAS_DEVICE"),
        F.lit("Device"),
        F.col("device_id"),
        F.col("device_id"),
        F.col("latest_reading_utc"),
        F.lit("latest_spo2"),
        F.col("latest_spo2"),
        F.lit("derived_from_fhir_and_telemetry"),
    )
    patient_condition = edge(
        spark.read.table(f"{CATALOG}.silver.condition"),
        F.lit("Patient"),
        F.regexp_replace("subject_reference", "^Patient/", ""),
        F.lit("HAS_CONDITION"),
        F.lit("Condition"),
        F.col("resource_id"),
        F.get_json_object("resource_json", "$.code.coding[0].display"),
        F.to_timestamp(F.get_json_object("resource_json", "$.onsetDateTime")),
        F.lit(None),
        F.lit(None),
        F.lit("derived_from_fhir"),
    )
    patient_claim = edge(
        spark.read.table(f"{CATALOG}.silver.claim_events"),
        F.lit("Patient"),
        F.col("patient_id"),
        F.lit("HAS_CLAIM"),
        F.lit("Claim"),
        F.col("claim_id"),
        F.col("claim_type"),
        F.col("submitted_at"),
        F.lit("billed_amount"),
        F.col("billed_amount"),
        F.lit("derived_from_claim_stream"),
    )
    patient_imaging = edge(
        spark.read.table(f"{CATALOG}.gold.agent_imaging_cohort"),
        F.lit("Patient"),
        F.col("patient_id"),
        F.lit("HAS_IMAGING_STUDY"),
        F.lit("ImagingStudy"),
        F.col("imaging_study_resource_id"),
        F.col("modality_code"),
        F.col("started_at"),
        F.lit("instance_count"),
        F.col("instance_count"),
        F.lit("derived_from_fhir_and_dicom_inventory"),
    )
    device_alert = edge(
        spark.read.table(f"{CATALOG}.gold.agent_clinical_triage"),
        F.lit("Device"),
        F.col("device_id"),
        F.lit("HAS_CLINICAL_ALERT"),
        F.lit("ClinicalAlert"),
        F.concat("device_id", F.lit("@"), F.col("last_reading_utc").cast("string")),
        F.concat_ws("/", "alert_tier", "alert_type"),
        F.col("last_reading_utc"),
        F.lit("min_spo2"),
        F.col("min_spo2"),
        F.lit("derived_from_telemetry"),
    )
    patient_gap = edge(
        spark.read.table(f"{CATALOG}.gold.agent_care_gaps"),
        F.lit("Patient"),
        F.col("patient_id"),
        F.lit("HAS_CARE_GAP"),
        F.lit("CareGap"),
        F.concat("patient_id", F.lit("-"), F.col("measure_id")),
        F.col("gap_type"),
        F.col("refreshed_at"),
        F.lit("days_overdue"),
        F.col("days_overdue"),
        F.lit("derived_from_fhir_quality_rules"),
    )
    return (
        patient_device.unionByName(patient_condition)
        .unionByName(patient_claim)
        .unionByName(patient_imaging)
        .unionByName(device_alert)
        .unionByName(patient_gap)
        .where(F.col("source_id").isNotNull() & F.col("target_id").isNotNull())
    )
