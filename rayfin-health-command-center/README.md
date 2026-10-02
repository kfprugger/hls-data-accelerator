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

The dashboard reads the app's **own database**, not live DAX. Two read-only
authenticated entities in `rayfin/data/` serve it:

| Entity | Table | Holds |
|---|---|---|
| `PublishedSnapshot` | `PublishedSnapshots` | one complete versioned JSON snapshot containing all three lenses |
| `SyncRun` | `SyncRuns` | SQL-generated publication provenance, row counts, and terminal outcome |

The legacy `KpiSnapshot`, `SeriesPoint`, and `WorklistRow` tables from the previous
design stay registered read-only so schema apply never drops them; the dashboard
does not read them.

`src/lib/sync-gold.ts` collects the ten shipped DAX queries and masks identifiers
before calling the trusted `publishSnapshot` function. The function uses the
SDK's on-behalf-of SQL token; SQL requires membership in `health_snapshot_writer`
and permits only execution of the publication procedure, not direct table writes.
Snapshot replacement and its successful audit record commit in one transaction.
An expected-version check elects one winner among concurrent publishers; denied,
conflicting, or failed publication leaves the displayed snapshot intact. A lost
response requires reloading the published state before deciding whether to retry.

The Sync control is restricted to authorized writers. The SQL publication layer is
applied to the deployed database with one enrolled writer, and version 1 was
published on 2026-10-02 through `dbo.PublishHealthSnapshot` as that writer; all 14
KPIs matched the Gold semantic models. The in-app Sync control cannot publish yet:
the Rayfin backend rejects AppBackend function calls for this tenant with
`WorkloadException`/`FeatureNotSupported` (Rayfin Functions are experimental), which
the banner shows as HTTP 400 until Functions access is enabled. When the function
itself runs and fails, `getSyncAccess` returns a non-sensitive cause code such as
`sql-token-unavailable` that the banner displays.

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

`rayfin up db apply` compiles `rayfin/data/*.ts` itself. `rayfin/tsconfig.json`
keeps its incremental build info inside `.temp/compiled`, so a recompile after the
CLI clears that folder always emits the entities.

The hardened publication path also requires applying
`rayfin/functions/sql/publication.sql` to the discovered app SQL database,
enrolling an approved external SQL principal with `grant-writer.sql` (a workspace
admin who connects without a database user first needs
`CREATE USER [upn] FROM EXTERNAL PROVIDER`), and setting the trusted function's
`SQL_SERVER` and `SQL_DATABASE` secrets with `rayfin secret set <name> --stdin`
(names are declared in `rayfin.yml`) from that database's discovered connection
properties. Never put access tokens in app
configuration. Verify permissions and the published audit with
`inspect-publication.sql`; the opt-in live integration scenario requires distinct
writer, viewer, and observer tokens and an actual Gold snapshot.

Both the app database and the semantic models require a Fabric session, so a
standalone browser sees an empty dashboard and a banner that names the reason
rather than zeroes that read like real business results.

## Privacy

The cohort is synthetic Synthea data. Member identifiers are truncated and
patient names are reduced to initials before they reach the screen.
