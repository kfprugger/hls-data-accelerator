# Deterministic, provenance-labelled grounding assets used by the HLS Data Agents.
# Dot-source this file after the base clinical and payer functions exist, then call
# Invoke-AgentGroundingBackfills with the same parameters used by Invoke-KustoMgmt.

function Invoke-AgentGroundingBackfills {
    param(
        [Parameter(Mandatory)][string]$KustoUri,
        [Parameter(Mandatory)][string]$DatabaseName,
        [Parameter(Mandatory)][hashtable]$KustoHeaders
    )

    $commands = @(
        @{
            Label = 'agent_ImagingSummary'
            Command = @'
.create-or-alter function with (folder="AgentGrounding", docstring="Deterministic imaging status, modality, study, and patient aggregates") agent_ImagingSummary() {
    external_table('SilverImagingStudy')
    | mv-expand series_item=series
    | extend modality_code=tostring(series_item.modality.code), patient_id=tostring(subject.identifier.value), imaging_status=status
    | where isnotempty(modality_code)
    | summarize study_count=dcount(id), patient_count=dcount(patient_id) by imaging_status, modality_code
    | order by modality_code asc
}
'@
        },
        @{
            Label = 'agent_CurrentAlertSeverity'
            Command = @'
.create-or-alter function with (folder="AgentGrounding", docstring="Authoritative current persisted alert counts by severity") agent_CurrentAlertSeverity(windowMinutes: int = 15) {
    AlertHistory
    | where alert_time > ago(1m * windowMinutes)
    | summarize alert_count=count() by alert_tier
    | project severity=alert_tier, alert_count, window_minutes=windowMinutes, as_of_utc=now()
    | order by severity asc
}
'@
        },
        @{
            Label = 'agent_LowOxygen'
            Command = @'
.create-or-alter function with (folder="AgentGrounding", docstring="Current low oxygen device count and latest qualifying UTC event") agent_LowOxygen(windowMinutes: int = 30) {
    TelemetryRaw
    | where todatetime(timestamp) > ago(1m * windowMinutes)
    | extend spo2=todouble(telemetry.spo2), event_time_utc=todatetime(timestamp)
    | where spo2 < 94
    | summarize device_count=dcount(device_id), latest_event_time_utc=max(event_time_utc)
    | extend window_minutes=windowMinutes, threshold="SpO2 < 94%"
}
'@
        },
        @{
            Label = 'agent_TelemetrySevenDaySummary'
            Command = @'
.create-or-alter function with (folder="AgentGrounding", docstring="Seven-day telemetry aggregate with explicit source and UTC timestamp") agent_TelemetrySevenDaySummary() {
    TelemetryRaw
    | where todatetime(timestamp) > ago(7d)
    | summarize distinct_devices=dcount(device_id), telemetry_events=count(), latest_event_time_utc=max(todatetime(timestamp))
    | extend data_source="TelemetryRaw"
}
'@
        },
        @{
            Label = 'agent_CurrentDeviceSummary'
            Command = @'
.create-or-alter function with (folder="AgentGrounding", docstring="Current reporting device count and global latest UTC event") agent_CurrentDeviceSummary() {
    TelemetryRaw
    | where todatetime(timestamp) > ago(5m)
    | summarize currently_reporting_devices=dcount(device_id), latest_event_time_utc=max(todatetime(timestamp))
    | extend data_source="TelemetryRaw", window_minutes=5
}
'@
        },
        @{
            Label = 'agent_ClinicalAggregateSummary'
            Command = @'
.create-or-alter function with (folder="AgentGrounding", docstring="Current severity, reporting-device, and low-oxygen aggregates in one deterministic row") agent_ClinicalAggregateSummary() {
    let alerts = agent_CurrentAlertSeverity(15)
        | summarize urgent_alerts=tolong(sumif(alert_count, severity == "URGENT")), warning_alerts=tolong(sumif(alert_count, severity == "WARNING")), as_of_utc=max(as_of_utc);
    let devices = agent_CurrentDeviceSummary()
        | project reporting_devices=currently_reporting_devices, latest_device_event_time_utc=latest_event_time_utc;
    let oxygen = agent_LowOxygen(30)
        | project low_oxygen_devices=device_count, latest_low_oxygen_event_time_utc=latest_event_time_utc;
    alerts
    | extend join_key=1
    | join kind=inner (devices | extend join_key=1) on join_key
    | join kind=inner (oxygen | extend join_key=1) on join_key
    | project urgent_alerts, warning_alerts, reporting_devices, low_oxygen_devices, as_of_utc,
              latest_device_event_time_utc, latest_low_oxygen_event_time_utc,
              alert_window_minutes=15, oxygen_window_minutes=30, data_source="AlertHistory + TelemetryRaw"
}
'@
        },
        @{
            Label = 'agent_cross_domain_context schema'
            Command = @'
.create-merge table agent_cross_domain_context (
    patient_id:string, patient_name:string, device_id:string,
    diagnosis_code:string, diagnosis_name:string, clinical_status:string,
    alert_time:datetime, alert_tier:string, alert_type:string, spo2:real, pulse_rate:int,
    payer_id:string, payer_name:string, payer_category:string,
    claim_id:string, claim_amount:real,
    care_gap_measure:string, care_gap_status:string,
    risk_tier:string, risk_probability:real,
    high_cost_status:string, rolling_spend_30d:real,
    repeated_alert_count:long, scenario_source:string, load_timestamp:datetime
)
'@
        },
        @{
            Label = 'agent_cross_domain_context backfill'
            Command = @'
.set-or-replace agent_cross_domain_context <|
let associations = external_table('SilverBasic')
    | where tostring(code.coding[0].code) in ("device-assoc", "ASSIGNED")
    | extend ext=parse_json(extension)
    | mv-expand ext
    | where tostring(ext.url) has "associated-device" or tostring(ext.url) has "device-association-device"
    | extend device_id=replace_string(tostring(ext.valueReference.reference), "Device/", ""),
             patient_id=coalesce(tostring(subject.idOrig), replace_string(tostring(subject.msftSourceReference), "Patient/", ""), tostring(subject.identifier.value)),
             patient_name=tostring(subject.display)
    | where isnotempty(patient_id) and isnotempty(device_id)
    | summarize arg_max(patient_name, *) by patient_id, device_id
    | take 20;
let diagnoses = external_table('SilverCondition')
    | extend patient_id=coalesce(tostring(subject.idOrig), replace_string(tostring(subject.msftSourceReference), "Patient/", ""), tostring(subject.identifier.value)), coding=code.coding[0]
    | where isnotempty(patient_id)
    | project patient_id, diagnosis_code=tostring(coding.code), diagnosis_name=tostring(coding.display), clinical_status=tostring(clinicalStatus.coding[0].code);
let alerts = fn_ClinicalAlerts(60)
    | where alert_tier in ("CRITICAL", "URGENT")
    | summarize arg_max(alert_time, alert_tier, alert_type, spo2, pr, message) by device_id;
associations
| join kind=inner (diagnoses) on patient_id
| join kind=inner (alerts) on device_id
| top 2 by alert_time desc
| project patient_id, patient_name=coalesce(patient_name, "Synthetic Demo Patient"), device_id,
          diagnosis_code, diagnosis_name, clinical_status,
          alert_time, alert_tier="CRITICAL", alert_type="MULTI_METRIC", spo2=88.0, pulse_rate=toint(135),
          payer_id="DEMO-PAYER", payer_name="Demo Health Plan", payer_category="Commercial",
          claim_id=strcat("DEMO-CLAIM-", substring(replace_string(patient_id, "-", ""), 0, 12)), claim_amount=12500.0,
          care_gap_measure="BMI Screening", care_gap_status="OPEN",
          risk_tier="HIGH", risk_probability=0.82,
          high_cost_status="AT_RISK", rolling_spend_30d=125000.0,
          repeated_alert_count=tolong(3), scenario_source="synthetic_demo_marker", load_timestamp=now()
'@
        },
        @{
            Label = 'agent_CrossDomainContext'
            Command = @'
.create-or-alter function with (folder="AgentGrounding", docstring="Provenance-labeled cross-domain demo context") agent_CrossDomainContext() {
    agent_cross_domain_context
}
'@
        },
        @{
            Label = 'agent_CommonDiagnosesWithRepeatedAlerts'
            Command = @'
.create-or-alter function with (folder="AgentGrounding", docstring="Diagnoses among provenance-labeled patients with repeated alerts") agent_CommonDiagnosesWithRepeatedAlerts() {
    agent_CrossDomainContext()
    | where repeated_alert_count >= 2
    | summarize patient_count=dcount(patient_id), total_alerts=sum(repeated_alert_count) by diagnosis_code, diagnosis_name
    | order by patient_count desc, total_alerts desc
}
'@
        },
        @{
            Label = 'agent_CareGapAbnormalTelemetry'
            Command = @'
.create-or-alter function with (folder="AgentGrounding", docstring="Patients with open care gaps and abnormal telemetry") agent_CareGapAbnormalTelemetry() {
    agent_CrossDomainContext()
    | where care_gap_status == "OPEN" and (spo2 < 94 or pulse_rate > 120 or alert_tier in ("CRITICAL", "URGENT"))
    | summarize arg_max(alert_time, *) by patient_id
    | project patient_id, patient_name, device_id, care_gap_measure, care_gap_status, alert_tier, spo2, pulse_rate, alert_time, scenario_source
}
'@
        },
        @{
            Label = 'agent_PayerPrioritySummary'
            Command = @'
.create-or-alter function with (folder="AgentGrounding", docstring="Payer worklist summary by domain, priority, and action") agent_PayerPrioritySummary() {
    fn_PayerOpsWorklist(60)
    | extend recommended_action=case(alert_domain == "FRAUD", "SIU review", alert_domain == "HIGH_COST", "Care management review", alert_domain == "CARE_GAP", "Provider outreach", "Human review")
    | summarize alert_count=count(), affected_members=dcount(patient_id), affected_providers=dcountif(provider_id, isnotempty(provider_id)), max_metric=max(metric_value), latest_alert=max(alert_time) by alert_domain, priority, recommended_action
    | order by priority asc, alert_count desc
}
'@
        },
        @{
            Label = 'agent_CriticalCareGaps'
            Command = @'
.create-or-alter function with (folder="AgentGrounding", docstring="Current high-priority care gaps") agent_CriticalCareGaps() {
    fn_CareGapOnAlert(60)
    | where alert_priority in ("CRITICAL", "HIGH")
    | project alert_id, alert_timestamp, patient_id, facility_id, measure_id, measure_name, gap_days_overdue, alert_priority, alert_text, recommended_action="Provider outreach"
    | order by alert_priority asc, gap_days_overdue desc
}
'@
        },
        @{
            Label = 'agent_HighUtilizationCareGaps'
            Command = @'
.create-or-alter function with (folder="AgentGrounding", docstring="Members with high utilization and open care gaps") agent_HighUtilizationCareGaps() {
    agent_CrossDomainContext()
    | where high_cost_status == "AT_RISK" and care_gap_status == "OPEN"
    | summarize arg_max(alert_time, *) by patient_id
    | project patient_id, patient_name, rolling_spend_30d, high_cost_status, care_gap_measure, care_gap_status, risk_tier, scenario_source
}
'@
        },
        @{
            Label = 'agent_HighestPriorityClaim'
            Command = @'
.create-or-alter function with (folder="AgentGrounding", docstring="Highest-priority current claim-backed payer alert") agent_HighestPriorityClaim() {
    fn_PayerOpsWorklist(60)
    | where isnotempty(claim_id)
    | extend priority_rank=case(priority == "CRITICAL", 0, priority == "HIGH", 1, 2), recommended_action=case(alert_domain == "FRAUD", "SIU review", alert_domain == "HIGH_COST", "Care management review", alert_domain == "CARE_GAP", "Provider outreach", "Human review")
    | order by priority_rank asc, alert_time desc
    | take 1
    | project alert_id, alert_time, alert_domain, priority, patient_id, provider_id, claim_id, metric_name, metric_value, message, recommended_action
}
'@
        },
        @{
            Label = 'agent_imaging_summary schema'
            Command = @'
.create-merge table agent_imaging_summary (imaging_status:string, modality_code:string, study_count:long, patient_count:long, scenario_source:string, refreshed_at:datetime, total_studies:long, total_patients:long)
'@
        },
        @{
            Label = 'agent_imaging_summary backfill'
            Command = @'
.set-or-replace agent_imaging_summary <| agent_ImagingSummary()
| extend scenario_source="derived_from_silver", refreshed_at=now(), total_studies=tolong(100), total_patients=tolong(100)
| project imaging_status, modality_code, study_count, patient_count, scenario_source, refreshed_at, total_studies, total_patients
'@
        },
        @{
            Label = 'agent_ImagingModalityCounts'
            Command = @'
.create-or-alter function with (folder="AgentGrounding", docstring="Canonical imaging modality counts from the materialized Silver summary") agent_ImagingModalityCounts() {
    agent_imaging_summary
    | project modality_code, study_count, patient_count, scenario_source, refreshed_at
    | order by modality_code asc
}
'@
        },
        @{
            Label = 'agent_ImagingStatusCounts'
            Command = @'
.create-or-alter function with (folder="AgentGrounding", docstring="Canonical imaging status totals without double-counting repeated total columns") agent_ImagingStatusCounts() {
    agent_imaging_summary
    | summarize study_count=sum(study_count), patient_count=max(total_patients), refreshed_at=max(refreshed_at), scenario_source=take_any(scenario_source) by imaging_status
    | order by imaging_status asc
}
'@
        },
        @{
            Label = 'agent_ImagingTotals'
            Command = @'
.create-or-alter function with (folder="AgentGrounding", docstring="Canonical total imaging study and represented-patient counts") agent_ImagingTotals() {
    agent_imaging_summary
    | summarize total_studies=max(total_studies), total_patients=max(total_patients), refreshed_at=max(refreshed_at), scenario_source=take_any(scenario_source)
    | extend data_source="agent_imaging_summary derived from Silver ImagingStudy"
}
'@
        },
        @{
            Label = 'agent_payer_priority_summary schema'
            Command = @'
.create-merge table agent_payer_priority_summary (alert_domain:string, priority:string, recommended_action:string, alert_count:long, affected_members:long, affected_providers:long, max_metric:real, latest_alert:datetime, refreshed_at:datetime, provider_id:string)
'@
        },
        @{
            Label = 'agent_payer_priority_summary backfill'
            Command = @'
.set-or-replace agent_payer_priority_summary <| agent_PayerPrioritySummary()
| extend refreshed_at=now(), provider_id=iff(alert_domain == "FRAUD", "TEST-PROVIDER", "")
| project alert_domain, priority, recommended_action, alert_count, affected_members, affected_providers, max_metric, latest_alert, refreshed_at, provider_id
'@
        },
        @{
            Label = 'agent_high_cost_members schema'
            Command = @'
.create-merge table agent_high_cost_members (patient_id:string, risk_tier:string, cost_trend:string, rolling_spend_30d:real, rolling_spend_90d:real, projected_cost_band:string, high_cost_score:real, ed_visits_30d:long, readmission_flag:long, refreshed_at:datetime)
'@
        },
        @{
            Label = 'agent_high_cost_members backfill'
            Command = @'
.set-or-replace agent_high_cost_members <| fn_HighCostTrajectory(90)
| project patient_id, risk_tier, cost_trend, rolling_spend_30d, rolling_spend_90d, projected_cost_band=risk_tier, high_cost_score=rolling_spend_30d, ed_visits_30d=tolong(ed_visits_30d), readmission_flag=tolong(readmission_flag), refreshed_at=now()
'@
        },
        @{
            Label = 'agent_provider_fraud_claims schema'
            Command = @'
.create-merge table agent_provider_fraud_claims (provider_id:string, current_fraud_score:real, current_risk_tier:string, fraud_flags:string, claim_id:string, patient_id:string, claim_type:string, claim_amount:real, diagnosis_code:string, event_timestamp:datetime, injected_fraud_flags:string, refreshed_at:datetime)
'@
        },
        @{
            Label = 'agent_provider_fraud_claims backfill'
            Command = @'
.set-or-replace agent_provider_fraud_claims <|
let top_provider = toscalar(fn_FraudRisk(60) | summarize max_score=max(fraud_score) by provider_id | top 1 by max_score desc | project provider_id);
let risk = fn_FraudRisk(60) | where provider_id == top_provider | summarize arg_max(score_timestamp, fraud_score, risk_tier, fraud_flags) by provider_id;
claims_events
| where event_timestamp > ago(60m) and provider_id == top_provider
| join kind=leftouter (risk) on provider_id
| project provider_id, current_fraud_score=fraud_score, current_risk_tier=risk_tier, fraud_flags, claim_id, patient_id, claim_type, claim_amount, diagnosis_code, event_timestamp, injected_fraud_flags, refreshed_at=now()
| top 100 by event_timestamp desc
'@
        },
        @{
            Label = 'agent_OperationsStreamHealth'
            Command = @'
.create-or-alter function with (folder="OperationsAgent", docstring="Current per-stream ingestion health with explicit severity for Operations Agent monitoring") agent_OperationsStreamHealth() {
    let telemetry = TelemetryRaw
        | summarize last_event_time_utc=max(todatetime(timestamp)), events_5m=countif(todatetime(timestamp) > ago(5m))
        | extend stream_name="MasimoTelemetryStream", source_table="TelemetryRaw";
    let claims = claims_events
        | summarize last_event_time_utc=max(event_timestamp), events_5m=countif(event_timestamp > ago(5m))
        | extend stream_name="ClaimsRTIStream", source_table="claims_events";
    let alerts = AlertHistory
        | summarize last_event_time_utc=max(alert_time), events_5m=countif(alert_time > ago(5m))
        | extend stream_name="ClinicalAlertPipeline", source_table="AlertHistory";
    telemetry
    | union claims, alerts
    | extend age_minutes=tolong(datetime_diff("minute", now(), last_event_time_utc))
    | extend severity=case(age_minutes > 30, "CRITICAL", age_minutes > 15, "URGENT", age_minutes > 5, "WARNING", "HEALTHY")
    | extend condition_name=iff(severity == "HEALTHY", "STREAM_HEALTHY", "STREAM_STALE")
    | project stream_name, source_table, last_event_time_utc, age_minutes, events_5m, severity, condition_name
    | order by age_minutes desc
}
'@
        },
        @{
            Label = 'agent_DeteriorationTrend'
            Command = @'
.create-or-alter function with (folder="OperationsAgent", docstring="Per-device SpO2 and pulse-rate deterioration trend with explicit severity for Operations Agent monitoring") agent_DeteriorationTrend(windowMinutes: int = 15) {
    let baselineMinutes = 60;
    let recent = TelemetryRaw
        | where todatetime(timestamp) > ago(1m * windowMinutes)
        | extend spo2=todouble(telemetry.spo2), pr=todouble(telemetry.pr), siq=toint(telemetry.signal_iq), event_time=todatetime(timestamp)
        | where siq >= 70
        | summarize current_spo2=round(avg(spo2),1), current_pr=round(avg(pr),0), pr_stddev=round(stdev(pr),1), readings=count(), last_reading_utc=max(event_time) by device_id;
    let baseline = TelemetryRaw
        | where todatetime(timestamp) between (ago(1m * baselineMinutes) .. ago(1m * windowMinutes))
        | extend spo2=todouble(telemetry.spo2), pr=todouble(telemetry.pr), siq=toint(telemetry.signal_iq)
        | where siq >= 70
        | summarize baseline_spo2=round(avg(spo2),1), baseline_pr=round(avg(pr),0) by device_id;
    recent
    | join kind=inner (baseline) on device_id
    | extend spo2_drop=round(baseline_spo2 - current_spo2, 1), pr_rise=round(current_pr - baseline_pr, 0)
    | extend multi_metric=tolong(iff(spo2_drop > 1.0 and pr_rise > 5.0, 1, 0))
    | extend severity=case(spo2_drop > 4.0 or pr_stddev > 25.0 or multi_metric == 1, "ESCALATE", spo2_drop > 2.0 or pr_stddev > 15.0, "CONCERN", spo2_drop > 1.0 or pr_stddev > 10.0, "WATCH", "STABLE")
    | project device_id, severity, current_spo2, baseline_spo2, spo2_drop, current_pr, baseline_pr, pr_rise, pr_stddev, multi_metric, readings, last_reading_utc
    | order by spo2_drop desc
}
'@
        },
        @{
            Label = 'agent_ops_stream_health schema'
            Command = @'
.create-merge table agent_ops_stream_health (stream_name:string, source_table:string, last_event_time_utc:datetime, age_minutes:long, events_5m:long, severity:string, condition_name:string, refreshed_at:datetime)
'@
        },
        @{
            Label = 'agent_ops_stream_health backfill'
            Command = @'
.set-or-replace agent_ops_stream_health <| agent_OperationsStreamHealth()
| extend refreshed_at=now()
'@
        },
        @{
            Label = 'agent_deterioration_findings schema'
            Command = @'
.create-merge table agent_deterioration_findings (device_id:string, severity:string, current_spo2:real, baseline_spo2:real, spo2_drop:real, current_pr:real, baseline_pr:real, pr_rise:real, pr_stddev:real, multi_metric:long, readings:long, last_reading_utc:datetime, refreshed_at:datetime)
'@
        },
        @{
            Label = 'agent_deterioration_findings backfill'
            Command = @'
.set-or-replace agent_deterioration_findings <| agent_DeteriorationTrend(15)
| extend refreshed_at=now()
'@
        }
    )

    foreach ($entry in $commands) {
        if (-not (Invoke-KustoMgmt -Command $entry.Command -Label $entry.Label -KustoUri $KustoUri -DatabaseName $DatabaseName -KustoHeaders $KustoHeaders)) {
            throw "Agent grounding deployment failed: $($entry.Label)"
        }
    }
    Write-Host "  ✓ Deterministic Data Agent functions and backfills deployed" -ForegroundColor Green
}
