# 003-zero-copy-proof results

A-1 | PASS | tsc and vite build succeeded cleanly for localdata mode
A-2 | PASS | vitest and orchestrator unit tests passed
E-1 | PASS | specs/tickets/003-zero-copy-proof/evidence/E-1.png
E-2 | PASS | specs/tickets/003-zero-copy-proof/evidence/E-2-1280.png
E-3 | PASS | [DRY-RUN] Target: TCGA-G6-A8L6 (Marcus Vance) in clinical_lakehouse.patient
E-4 | PASS | Applied: Marcus Vance (Zero-Copy Proof) / Read back via patient360 / Reverted: Marcus Vance (0.13s)
E-5 | PASS | ValueError: Invalid patient ID format: INVALID_ID_123. Must match ^TCGA-[A-Z0-9]{2}-[A-Z0-9]{4}$
E-6 | PASS | test_sql_injection_defense passed rejecting injection strings before SQL dispatch
E-7 | PASS | specs/tickets/003-zero-copy-proof/evidence/E-7.png
E-8 | PASS | Zero new dependencies added; TypeScript type checking exited 0
E-9 | PASS | specs/tickets/003-zero-copy-proof/evidence/E-9.png
E-10 | PASS | Record is already at baseline value 'Marcus Vance'. No changes needed.
R-1 | PASS | /patients route loaded with zero console errors
R-2 | PASS | /wardflow route loaded displaying cardiology patient records
R-3 | PASS | getDataMap returned workspace, patient360, silos, provenance, and zeroCopy metadata
