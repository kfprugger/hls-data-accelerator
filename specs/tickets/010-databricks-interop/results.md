# 010-databricks-interop results

A-1 | PASS | built in 3.85s; dist-local and functions compiled with 0 errors
A-2 | PASS | Ran 1 vitest test, 172 orchestrator unit tests, 5 databricks interop tests in 0.002s; all passed
E-1 | PASS | [DRY-RUN] Statement: SELECT count(DISTINCT patient_id) AS tcga_patient_count FROM hls_stfhiropulbb4gx2ioc_onelake.clinical.patient
E-2 | PASS | Query succeeded: 15 TCGA patients verified in 681 ms; OneLake proof written successfully; zeroCopyVerified: true
E-3 | PASS | specs/tickets/010-databricks-interop/evidence/E-3.png
E-4 | PASS | specs/tickets/010-databricks-interop/evidence/E-4-1280.png
E-5 | PASS | Ran 1 test in 0.001s; TimeoutError: Databricks statement execution exceeded timeout (180s)
E-6 | PASS | specs/tickets/010-databricks-interop/evidence/E-6.png
E-7 | PASS | Ran 1 test in 0.000s; zero patient identifiers, names, medical details, or API tokens
E-8 | PASS | specs/tickets/010-databricks-interop/evidence/E-8.png
E-9 | PASS | 430 bytes (under 2048-byte budget)
E-10 | PASS | Deleted proof file successfully; OneLake DELETE returned 200
R-1 | PASS | Schematic displays clinical, genomics, and imaging silos with OneLake shortcuts
R-2 | PASS | /patients loads Marcus Vance and cohort without errors
R-3 | PASS | Scripts 01 through 08 pass Python compilation and bash syntax validation
