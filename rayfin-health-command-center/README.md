# BrakeKat Health Command Center

A Fabric App (Rayfin) that puts payer, provider and medtech operations on one
surface, reading live from the Gold layer of the `med-0906` workspace.

Deployed item: `rayfin-health-command-center` (`AppBackend`
`db1f3f55-4e7e-4b35-9c28-16a79410b64a`)
Hosting URL: https://oaken-cove-7a1eb21ad7-westus2.webapp.fabricapps.net

## Why it exists

The Gold lakehouse already carries claims economics, quality measures and
imaging inventory for the same 100-patient cohort. Three audiences normally get
three disconnected reports. This app proves one Gold layer can serve all three:
a scheduled-on-demand sync pulls the Direct Lake models into the app's own
database, and all three lenses render from that single snapshot.

## How the numbers get there

The dashboard reads the app's **own database**, not live DAX. Four entities in
`rayfin/data/` back it:

| Entity | Table | Holds |
|---|---|---|
| `KpiSnapshot` | `KpiSnapshots` | headline figures per lens, with unit and caption |
| `SeriesPoint` | `SeriesPoints` | ranked bars: payer segments, care gaps, risk tiers, Stars measures, modality mix |
| `WorklistRow` | `WorklistRows` | high-cost members and heavy imaging acquisitions, already masked |
| `SyncRun` | `SyncRuns` | provenance: when the last sync ran, what it wrote, why it failed |

Every entity is `@authenticated('*')`, so the data plane rejects anonymous
callers — `POST /graphql` without a session returns
`Anonymous access to this app is not enabled`.

`src/lib/sync-gold.ts` is the only module that touches a semantic model. It
executes the ten shipped DAX queries, masks identifiers, replaces the snapshot
tables and records a `SyncRun`. The app runs it automatically the first time it
finds an empty database, and the **Sync from Gold** button re-runs it on demand.

## Data dependency

| Alias | Item | Backing store |
|---|---|---|
| `popHealthGold` | Population Health & Quality Semantic Model (`b7608be3…`) | Direct Lake over `healthcare1_reporting_gold` |
| `imagingGold` | ImagingReport (`cc801b43…`) | Direct Lake over the Gold imaging projections |
| `reportingGold` | `healthcare1_reporting_gold` lakehouse (`ddf46a8d…`) | declared for lineage |

Connections live in `fabric.yaml` and compile into `src/fabric.generated.ts`
via `fabric-app-data generate` (run automatically by `npm run build`). The
generated file is gitignored — `fabric.yaml` is the source of truth.

## The three lenses

**Payer** — total paid against billed, collection and denial rate, PMPM,
revenue at risk, paid split by line of business, and the highest-cost members
from `agg_high_cost_claimants`.

**Provider** — open care gaps, quality rate, average RAF, average readmission
risk, a CMS Stars gauge with remaining improvement headroom, care gaps ranked by
measure, readmission risk tiers, and the weakest Stars measures.

**MedTech** — imaging study and DICOM instance volume, studies per patient,
modality mix with per-modality instance counts, and the heaviest acquisitions.

Line-of-business figures come from the per-segment measures rather than a
`dim_payer` grouping: the claim-to-payer relationship in that model returns the
grand total for every category, so grouping would silently show identical
numbers per segment.

## Running it

```bash
npm install
npm run dev          # standalone shell; the data plane requires a Fabric session
npm run build        # rayfin env + fabric-app-data generate + typecheck + build
npm test             # unit tests
npx rayfin up --workspace-id <ws> --tenant <tenant> --yes   # deploy app
npx tsc -p rayfin/tsconfig.json && npx rayfin up db apply --yes   # apply schema
npx rayfin up status
```

`rayfin up db apply` compiles `rayfin/data/*.ts` first; run `tsc -p
rayfin/tsconfig.json` beforehand if the CLI reports no compiled entities.

Both the app database and the semantic models require a Fabric session, so a
standalone browser sees an empty dashboard and a banner that names the reason
rather than zeroes that read like real business results.

## Privacy

The cohort is synthetic Synthea data. Member identifiers are truncated and
patient names are reduced to initials before they reach the screen.
