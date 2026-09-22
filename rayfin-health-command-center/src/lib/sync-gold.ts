//-----------------------------------------------------------------------
// Gold → app-database sync.
//
// The dashboard renders from the Rayfin database, not from live DAX. This
// module is the only place that reads the Direct Lake semantic models: it
// executes every shipped query, masks identifiers, replaces the previous
// snapshot and records a SyncRun for provenance.
//-----------------------------------------------------------------------

import { getFabricClient } from "@/lib/fabric-client";
import { getRayfinClient, type AppRayfinClient } from "@/lib/rayfin-client";
import {
    CARE_GAPS, HEAVIEST_STUDIES, HIGH_COST_MEMBERS, MEDTECH_KPIS, MODALITY_MIX,
    PAYER_KPIS, PAYER_SEGMENTS, PROVIDER_KPIS, READMISSION_TIERS, STAR_MEASURES,
    type Q,
} from "@/lib/queries";
import { count, maskId, maskName, money, num, pct, type Row, rowsOf } from "@/lib/format";

type Lens = "payer" | "provider" | "medtech";

type KpiInsert = KpiSeed & { capturedAt: Date };
type SeriesInsert = SeriesSeed & { capturedAt: Date };
type WorklistInsert = WorklistSeed & { capturedAt: Date };

interface KpiSeed {
    lens: Lens; metricKey: string; label: string; value: number;
    unit: string; caption?: string; rank: number; sourceModel: string;
}
interface SeriesSeed {
    lens: Lens; series: string; label: string; value: number;
    unit: string; detail?: string; rank: number;
}
interface WorklistSeed {
    lens: Lens; kind: string; subject: string; segment?: string;
    primaryValue: number; primaryUnit: string;
    secondaryValue?: number; secondaryUnit?: string;
    flagged?: boolean; rank: number;
}

export interface SyncOutcome {
    kpiRows: number;
    seriesRows: number;
    worklistRows: number;
    completedAt: Date;
}

async function runQuery({ connection, query }: Q): Promise<Row[]> {
    const result = await getFabricClient().semanticModel(connection).query(query, { bypassCache: true });
    if (result.status !== "success") {
        throw new Error(`${connection}: ${result.status === "error" ? result.error.message : "no result"}`);
    }
    return rowsOf(result);
}

/**
 * Reads every Gold query, rewrites the snapshot tables and returns the row
 * counts written. Identifiers are masked here so the app database only ever
 * holds the masked form.
 */
export async function syncFromGold(): Promise<SyncOutcome> {
    const client = getRayfinClient();
    const startedAt = new Date();

    const run = await client.data.SyncRun.create({
        startedAt,
        status: "running",
        kpiRows: 0,
        seriesRows: 0,
        worklistRows: 0,
        sources: "popHealthGold,imagingGold",
    });

    try {
        const [payer, segments, highCost, provider, gaps, tiers, stars, medtech, modality, heaviest] =
            await Promise.all([
                runQuery(PAYER_KPIS), runQuery(PAYER_SEGMENTS), runQuery(HIGH_COST_MEMBERS),
                runQuery(PROVIDER_KPIS), runQuery(CARE_GAPS), runQuery(READMISSION_TIERS),
                runQuery(STAR_MEASURES), runQuery(MEDTECH_KPIS), runQuery(MODALITY_MIX),
                runQuery(HEAVIEST_STUDIES),
            ]);

        const p = payer[0] ?? {};
        const pr = provider[0] ?? {};
        const mt = medtech[0] ?? {};
        const capturedAt = new Date();

        const kpis: KpiSeed[] = [
            { lens: "payer", metricKey: "totalPaid", label: "Total paid", value: num(p.totalPaid), unit: "money", caption: `of ${money(p.totalBilled)} billed`, rank: 0, sourceModel: "popHealthGold" },
            { lens: "payer", metricKey: "collectionRate", label: "Collection rate", value: num(p.collectionRate), unit: "percent", caption: `denial rate ${pct(p.denialRate)}`, rank: 1, sourceModel: "popHealthGold" },
            { lens: "payer", metricKey: "pmpm", label: "PMPM", value: num(p.pmpm), unit: "money", caption: "per member per month", rank: 2, sourceModel: "popHealthGold" },
            { lens: "payer", metricKey: "revenueAtRisk", label: "Revenue at risk", value: num(p.revenueAtRisk), unit: "money", caption: `${count(p.highCostMembers)} high-cost members`, rank: 3, sourceModel: "popHealthGold" },
            { lens: "payer", metricKey: "leakage", label: "Revenue leakage", value: num(p.leakage), unit: "money", caption: `${count(p.totalClaims)} claims adjudicated`, rank: 4, sourceModel: "popHealthGold" },

            { lens: "provider", metricKey: "openGaps", label: "Open care gaps", value: num(pr.openGaps), unit: "count", caption: "actionable outreach list", rank: 0, sourceModel: "popHealthGold" },
            { lens: "provider", metricKey: "qualityRate", label: "Quality rate", value: num(pr.qualityRate), unit: "percent", caption: `${count(pr.patientsMeasured)} patients measured`, rank: 1, sourceModel: "popHealthGold" },
            { lens: "provider", metricKey: "avgReadmit", label: "Avg readmission risk", value: num(pr.avgReadmit), unit: "percent", caption: `ALOS ${num(pr.alos).toFixed(1)} days`, rank: 2, sourceModel: "popHealthGold" },
            { lens: "provider", metricKey: "avgRaf", label: "Average RAF", value: num(pr.avgRaf), unit: "ratio", caption: "risk-adjusted acuity", rank: 3, sourceModel: "popHealthGold" },
            { lens: "provider", metricKey: "stars", label: "Overall stars", value: num(pr.stars), unit: "ratio", caption: `${count(pr.starOpp)} points of headroom`, rank: 4, sourceModel: "popHealthGold" },

            { lens: "medtech", metricKey: "studies", label: "Imaging studies", value: num(mt.studies), unit: "count", caption: `${count(mt.patients)} distinct patients`, rank: 0, sourceModel: "imagingGold" },
            { lens: "medtech", metricKey: "files", label: "DICOM instances", value: num(mt.files), unit: "count", caption: `${num(mt.perStudy).toFixed(0)} per study`, rank: 1, sourceModel: "imagingGold" },
            { lens: "medtech", metricKey: "perPatient", label: "Studies per patient", value: num(mt.perPatient), unit: "ratio", caption: "fleet utilization", rank: 2, sourceModel: "imagingGold" },
            { lens: "medtech", metricKey: "avgAge", label: "Average patient age", value: num(mt.avgAge), unit: "ratio", caption: "imaged cohort", rank: 3, sourceModel: "imagingGold" },
        ];

        const series: SeriesSeed[] = [
            ...segments.map((r, i) => ({
                lens: "payer" as const, series: "payerSegment", label: String(r.segment ?? "—"),
                value: num(r.paid), unit: "money", rank: i,
                detail: `collection ${pct(r.collection)} · quality ${pct(r.quality)} · RAF ${num(r.raf).toFixed(2)}`,
            })),
            ...gaps.map((r, i) => ({
                lens: "provider" as const, series: "careGap", label: String(r.gap_type ?? "Unknown"),
                value: num(r.gaps), unit: "count", rank: i,
            })),
            ...tiers.map((r, i) => ({
                lens: "provider" as const, series: "riskTier", label: String(r.risk_tier ?? "—"),
                value: num(r.encounters), unit: "count", rank: i,
                detail: `avg risk ${pct(r.avgRisk)}`,
            })),
            ...stars.map((r, i) => ({
                lens: "provider" as const, series: "starMeasure", label: String(r.measure_name ?? "—"),
                value: num(r.rating), unit: "ratio", rank: i,
            })),
            ...modality.map((r, i) => ({
                lens: "medtech" as const, series: "modality", label: String(r.ModalityName ?? r.Modality ?? "—"),
                value: num(r.studies), unit: "count", rank: i,
                detail: `${count(r.files)} instances · ${count(r.patients)} patients`,
            })),
        ];

        const worklist: WorklistSeed[] = [
            ...highCost.map((r, i) => ({
                lens: "payer" as const, kind: "highCostMember", subject: maskId(r.member),
                segment: String(r.payer ?? "—"), primaryValue: num(r.paid), primaryUnit: "money",
                secondaryValue: num(r.claims), secondaryUnit: "count", flagged: Boolean(r.stopLoss), rank: i,
            })),
            ...heaviest.map((r, i) => ({
                lens: "medtech" as const, kind: "heavyAcquisition", subject: maskName(r.FullName),
                segment: String(r.AgeRange ?? "—"), primaryValue: num(r.files), primaryUnit: "count",
                secondaryValue: num(r.studies), secondaryUnit: "count", rank: i,
            })),
        ];

        await replaceKpis(client, kpis.map((k) => ({ ...k, capturedAt })));
        await replaceSeries(client, series.map((s) => ({ ...s, capturedAt })));
        await replaceWorklist(client, worklist.map((w) => ({ ...w, capturedAt })));

        const completedAt = new Date();
        await client.data.SyncRun.update({ id: run.id }, {
            status: "succeeded",
            completedAt,
            kpiRows: kpis.length,
            seriesRows: series.length,
            worklistRows: worklist.length,
        });

        return { kpiRows: kpis.length, seriesRows: series.length, worklistRows: worklist.length, completedAt };
    } catch (err) {
        const message = err instanceof Error ? err.message : String(err);
        await client.data.SyncRun.update({ id: run.id }, {
            status: "failed",
            completedAt: new Date(),
            error: message.slice(0, 500),
        });
        throw err;
    }
}

/**
 * Replaces a snapshot table: clears the previous capture, then writes the new
 * rows. The three entities are handled explicitly rather than through an
 * entity-name union so each create keeps its own input type.
 */
async function replaceKpis(client: AppRayfinClient, rows: KpiInsert[]): Promise<void> {
    const existing = await client.data.KpiSnapshot.select(["id"]).execute();
    for (const row of existing) await client.data.KpiSnapshot.delete({ id: row.id });
    for (const row of rows) await client.data.KpiSnapshot.create(row);
}

async function replaceSeries(client: AppRayfinClient, rows: SeriesInsert[]): Promise<void> {
    const existing = await client.data.SeriesPoint.select(["id"]).execute();
    for (const row of existing) await client.data.SeriesPoint.delete({ id: row.id });
    for (const row of rows) await client.data.SeriesPoint.create(row);
}

async function replaceWorklist(client: AppRayfinClient, rows: WorklistInsert[]): Promise<void> {
    const existing = await client.data.WorklistRow.select(["id"]).execute();
    for (const row of existing) await client.data.WorklistRow.delete({ id: row.id });
    for (const row of rows) await client.data.WorklistRow.create(row);
}
