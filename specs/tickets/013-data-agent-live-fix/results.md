# 013-data-agent-live-fix results

A-1 | PASS | cd rayfin-imaging && ./node_modules/.bin/tsc -b && ./node_modules/.bin/vite build --mode localdata --outDir dist-local && cd rayfin/functions && ./node_modules/.bin/tsc --build exit 0
A-2 | PASS | vitest 39 passed; unittest 195 passed exit 0
A-3 | PASS | pwsh parser check on phase-2/deploy-data-agents.ps1 exits 0 with zero syntax errors
E-1 | PASS | specs/tickets/013-data-agent-live-fix/notes.md
E-2 | PASS | specs/tickets/013-data-agent-live-fix/evidence/E-2.json (answer 115, SQL generatedQuery, execution_time_ms 20518 <= 45000)
E-3 | PASS | specs/tickets/013-data-agent-live-fix/evidence/E-3.json (Clear cell renal cell carcinoma, SQL generatedQuery, execution_time_ms 27088 <= 45000)
E-4 | PASS | specs/tickets/013-data-agent-live-fix/evidence/E-4.txt (deploy-data-agents.ps1 exits 0, published agent answers E-2)
E-5 | PASS | specs/tickets/013-data-agent-live-fix/evidence/patient360-before.json; specs/tickets/013-data-agent-live-fix/evidence/E-5.txt (dry-run restore 15 parts exit 0)
E-6 | PASS | specs/tickets/013-data-agent-live-fix/evidence/E-6.json (prompt injection safely handled without instruction leak or scope bypass, exit 0)
E-7 | PASS | grep -rniE 'eyJ[a-zA-Z0-9_-]{20,}|bearer [a-z0-9]' specs/tickets/013-data-agent-live-fix/ scripts/ phase-2/deploy-data-agents.ps1 matched 0 secrets
R-1 | PASS | specs/tickets/013-data-agent-live-fix/evidence/R-1.txt (all 4 published agents verified with zero regressions)
