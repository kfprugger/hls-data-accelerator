# 001-local-demo-dataset results

A-1 | PASS | vite v7.3.7 build finished with 2521 modules transformed, dist-local generated with 0 errors
A-2 | PASS | vitest 1 passed, unittest 172 passed in 55.37s
E-1 | PASS | 26 parquet files generated across clinical, genomics, and imaging; patient.parquet has 15 rows
E-2 | PASS | getCohort, getPatient, and getDataMap returned HTTP 200 with full 15-patient dataset
E-3 | PASS | specs/tickets/001-local-demo-dataset/evidence/E-3.png
E-4 | PASS | specs/tickets/001-local-demo-dataset/evidence/E-4-1280.png, specs/tickets/001-local-demo-dataset/evidence/E-4-360.png
E-5 | PASS | env -i with isolated proxy returned 15 rows from build_tables with no fabric_config.load error
E-6 | PASS | consecutive CLI runs and --clean completed with status 0 and consistent row counts
E-7 | PASS | callable(getattr(seed_patient360_silos, 'get_config', None)) or hasattr(seed_patient360_silos, 'CONFIG') returned True
E-8 | PASS | execution completed in 0.352s (< 5.0s) with 208K storage footprint (< 10 MB)
E-9 | PASS | --out-dir /etc/cron.d exited with status 1 and printed Path traversal rejected
E-10 | PASS | missing cohort.json exited status 1 with 'Error: Missing pipeline fixture file: cohort.json'
