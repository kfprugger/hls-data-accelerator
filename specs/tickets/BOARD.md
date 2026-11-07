| # | Title | Status | Mode | Runs |
|---|---|---|---|---|
| 001 | Local demo dataset (offline 15-patient tables) | done | solo | alongside |
| 002 | TCGA patients through the synthetic HLS pipeline | ready | solo | alongside |
| 003 | Zero-copy proof on the data map | done | solo | waits for 001: local data map needs the 001 tables |
| 008 | Imaging hero (CT + slide + genomics side by side) | done | solo | waits for 001: patient view needs the 001 tables |
| 010 | Databricks reads the same OneLake tables | ready | solo | waits for 003: both change DataMap.tsx and the shared function files |
| 007 | Standards view (FHIR / DICOM to tables) | ready | solo | waits for 010: shared function_app.ts, local/api.ts, App.tsx, AppShell.tsx |
| 005 | Plain-English Data Agent questions | ready | solo | waits for 007: shared function_app.ts, App.tsx, AppShell.tsx |
| 006 | Nurse vs researcher PHI views | ready | solo | waits for 005: shared function_app.ts, AppShell.tsx; waits for 002: needs the TCGA records |
| 004 | Real-time alert with a stopwatch | ready | solo | waits for 006: shared function_app.ts and local/plugin.ts; waits for 002: needs Marcus Vance's device pairing |
| 009 | Plain-language copy pass + glossary | ready | solo | waits for 004: it rewrites copy on every page the UI tickets change (003, 004, 005, 006, 007, 008, 010) |
| 011 | Demo packaging (60 s film, walkthrough, deploy timer, synthetic badge) | ready | solo | waits for 009: the film is captured from the finished UI |
| 012 | Orchestrator wiring for fresh deployments | ready | solo | waits for 004: calls the CLI scripts from 002, 004, 006 and 010 |
