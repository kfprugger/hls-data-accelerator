# 004-realtime-alert-stopwatch results

A-1 | PASS | tsc -b and vite build localdata and functions tsc exit 0
A-2 | PASS | 24 vitest tests and 26 python unittest tests pass with 0 failures
E-1 | PASS | Patient: Marcus Vance (TCGA-G6-A8L6), Device: MASIMO-RADIUS7-0101, SpO2: 84.0% (CRITICAL), Pulse Rate: 115 bpm, Recipient: alerts@example.com, Mode: DRY RUN
E-2 | PASS | specs/tickets/004-realtime-alert-stopwatch/evidence/E-2.png
E-3 | PASS | Error: unauthorized_alert_recipient: Recipient must be alerts@example.com (exit 2)
E-4 | PASS | test_dedupe_sequences passed (dry run, status PLANNED, no observed dispatch): T=0 EXPECTED_DISPATCH, T=180s SUPPRESSED_DEDUPE, T=600s UNCERTAIN_BOUNDARY, T=720s EXPECTED_DISPATCH
E-5 | PASS | PASSED: All injection attempts blocked (exit 2 for all 5 attack vectors)
E-6 | PASS | grep zero matches for tokens, Bearer, and secrets in stdout/stderr
E-7 | PASS | test_stopwatch_latency_calculation passed: t_total 18.4s <= 60.0s latency budget
E-8 | PASS | specs/tickets/004-realtime-alert-stopwatch/evidence/E-8-360px.png
E-9 | PASS | Error: patient_device_not_found: No paired Masimo device found for patient TCGA-XX-0000 (exit 1)
E-10 | PASS | Error: no_alert_recipient_configured (exit 2 when HLS_ALERT_EMAIL unset)
E-11 | PENDING | Evidence predates Method 2 rewrite and SplitEvent wiring; re-run needs a live redeploy, getDefinition readback and decoded entity graph.
E-12 | PENDING | Evidence predates Method 2 rewrite and SplitEvent wiring; re-run needs a live redeploy, raw KQL output, and an inbox check.
E-13 | PENDING | Evidence predates Method 2 rewrite and SplitEvent wiring; re-run needs a live redeploy, raw KQL output, and an inbox check.
R-1 | PASS | Marcus Vance stage IV VHL verified, WardFlow cohort table and Stevenson profiles operational
R-2 | PASS | vitest run src/lib/api.test.ts 9 tests passed with 0 failures
