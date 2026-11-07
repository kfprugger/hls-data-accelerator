# 005-data-agent-qa results

A-1 | PASS | cd rayfin-imaging && ./node_modules/.bin/tsc -b && ./node_modules/.bin/vite build --mode localdata --outDir dist-local && cd rayfin/functions && ./node_modules/.bin/tsc --build exit 0
A-2 | PASS | vitest passed 18 tests across 3 files; python unittest passed 177 tests in 78.992s exit 0
E-1 | PASS | specs/tickets/005-data-agent-qa/evidence/E-1.png
E-2 | PASS | specs/tickets/005-data-agent-qa/evidence/E-2.png
E-3 | PASS | HTTP 400 {"error":"question_too_long"} and specs/tickets/005-data-agent-qa/evidence/E-3.png
E-4 | PASS | test_delegated_token_required exit 0; 401 unauthenticated, 403 unauthorized with 0 data rows, zero secrets in client storage
E-5 | PASS | specs/tickets/005-data-agent-qa/evidence/E-5.png
E-6 | PASS | test_logs_scrubbed_of_phi_and_tokens exit 0; 0 regex matches for PHI, patient IDs, or Bearer tokens in logs
E-7 | PASS | test_local_fixture_latency exit 0; 20 iterations in 21 ms (P95 < 100 ms)
E-8 | PASS | specs/tickets/005-data-agent-qa/evidence/E-8-1280px.png and specs/tickets/005-data-agent-qa/evidence/E-8-360px.png
E-9 | PASS | HTTP 400 {"error":"empty_question"} and submit button disabled with "Please enter a question" hint
E-10 | PASS | {"question": "How many distinct patients are in the Patient table?", "answer": "There are **115 distinct patients** in the `Patient` table.", "generatedQuery": "SELECT COUNT(DISTINCT id) AS distinct_patient_count\nFROM dbo.Patient;", "queryLanguage": "SQL", "execution_time_ms": 11188, "is_error": false}
R-1 | PASS | specs/tickets/005-data-agent-qa/evidence/R-1.png
R-2 | PASS | specs/tickets/005-data-agent-qa/evidence/R-2.png
