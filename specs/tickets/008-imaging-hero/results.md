# 008-imaging-hero results

A-1 | PASS | tsc -b && vite build --mode localdata --outDir dist-local && tsc --build: built in 4.03s
A-2 | PASS | vitest run: 2 test files passed, 11 tests passed; python unittest discover: 172 tests passed
E-1 | PASS | specs/tickets/008-imaging-hero/evidence/E-1.png
E-2 | PASS | specs/tickets/008-imaging-hero/evidence/E-2.png
E-3 | PASS | specs/tickets/008-imaging-hero/evidence/E-3-1280.png
E-4 | PASS | specs/tickets/008-imaging-hero/evidence/E-4.png
E-5 | PASS | vitest run src/components/patient/tests/MultimodalHero.test.tsx -t "security": 4 passed
E-6 | PASS | specs/tickets/008-imaging-hero/evidence/E-6.png
E-7 | PASS | vitest run src/components/patient/tests/MultimodalHero.test.tsx -t "unmount": 1 passed
E-8 | PASS | specs/tickets/008-imaging-hero/evidence/E-8.png
E-9 | PASS | specs/tickets/008-imaging-hero/evidence/E-9.png
