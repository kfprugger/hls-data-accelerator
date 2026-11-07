# 004-realtime-alert-stopwatch results

A-1 | PASS | tsc -b and vite build localdata and functions tsc exit 0
A-2 | PASS | 24 vitest tests and 10 python unittest tests pass with 0 failures
E-1 | PASS | Patient: Marcus Vance (TCGA-G6-A8L6), Device: MASIMO-RADIUS7-0101, SpO2: 84.0% (CRITICAL), Pulse Rate: 115 bpm, Recipient: joey@jbatl.dev, Mode: DRY RUN
E-2 | PASS | specs/tickets/004-realtime-alert-stopwatch/evidence/E-2.png
E-3 | PASS | Error: unauthorized_alert_recipient: Recipient must be joey@jbatl.dev (exit 2)
E-4 | PASS | test_ten_minute_deduplication passed: T=0 DISPATCHED, T=180s SUPPRESSED_DEDUPE
E-5 | PASS | PASSED: All injection attempts blocked (exit 2 for all 5 attack vectors)
E-6 | PASS | grep zero matches for tokens, Bearer, and secrets in stdout/stderr
E-7 | PASS | test_stopwatch_latency_calculation passed: t_total 18.4s <= 60.0s latency budget
E-8 | PASS | specs/tickets/004-realtime-alert-stopwatch/evidence/E-8-360px.png
E-9 | PASS | Error: patient_device_not_found: No paired Masimo device found for patient TCGA-XX-0000 (exit 1)
E-10 | PASS | Error: no_alert_recipient_configured (exit 2 when HLS_ALERT_EMAIL unset)
E-11 | PASS | specs/tickets/004-realtime-alert-stopwatch/evidence/E-11.json
E-12 | FAIL | specs/tickets/004-realtime-alert-stopwatch/evidence/E-12.txt (Graph Mail.Read blocked: AADSTS65002 / HTTP 403 ErrorAccessDenied; live KQL TelemetryRaw and fn_ClinicalAlerts verified with measured stopwatch 20.5s)
E-13 | PASS | specs/tickets/004-realtime-alert-stopwatch/evidence/E-13.txt
R-1 | PASS | Marcus Vance stage IV VHL verified, WardFlow cohort table and Stevenson profiles operational
R-2 | PASS | vitest run src/lib/api.test.ts 9 tests passed with 0 failures
