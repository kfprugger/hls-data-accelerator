# 006-phi-persona-views results

A-1 | PASS | build commands exited 0 (TypeScript compile, Vite build dist-local, functions tsc)
A-2 | PASS | 14 vitest tests passed in rayfin-imaging and 177 unittest tests passed in orchestrator (test_phi_persona.py: 5/5)
E-1 | PASS | specs/tickets/006-phi-persona-views/evidence/E-1.png
E-2 | PASS | specs/tickets/006-phi-persona-views/evidence/E-2.png
E-3 | PASS | test_researcher_denied_on_identified_patient_table exited 0 (HTTP 403 / AccessDeniedOnPath: Tables/patient)
E-4 | PASS | specs/tickets/006-phi-persona-views/evidence/E-4.png
E-5 | PASS | dry-run exited 0; 0 password leaks found in repo files or logs
E-6 | PASS | manage_researcher_persona.py --dry-run and --delete --dry-run exited 0
E-7 | PASS | toggle latency 1.10ms (< 200ms) without window reload
E-8 | PASS | specs/tickets/006-phi-persona-views/evidence/E-8-1280px.png
E-9 | PASS | specs/tickets/006-phi-persona-views/evidence/E-4.png
E-10 | PASS | seed_deidentified_clinical.py --live idempotent (exit 0); SQL query: 15 rows, Marcus Vance display_name='TCGA-G6-A8L6', 0 rows with 'Vance'
E-11 | PASS | manage_researcher_persona.py --create --live idempotent (exit 0); researcher-demo@jbatl.dev exists; ClinicalResearcherRole grants Tables/patient_deidentified and denies Tables/patient; 0 passwords exposed
E-12 | FAIL | non-interactive sign-in blocked by tenant MFA policy: AADSTS50079: Due to a configuration change made by your administrator, or because you moved to a new location, you must enroll in multi-factor authentication to access 'e406a681-f3d4-42a8-90b6-c2b029497af1'.
R-1 | PASS | specs/tickets/006-phi-persona-views/evidence/R-1.png
R-2 | PASS | specs/tickets/006-phi-persona-views/evidence/R-2.png
