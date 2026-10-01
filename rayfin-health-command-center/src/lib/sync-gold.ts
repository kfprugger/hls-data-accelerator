//-----------------------------------------------------------------------
// Gold → one validated publication. Only an authorized writer reads DAX;
// the native function authorizes again and publishes atomically in SQL.
//-----------------------------------------------------------------------

import { getFabricClient } from "@/lib/fabric-client";
import { getRayfinClient } from "@/lib/rayfin-client";
import {
    CARE_GAPS, HEAVIEST_STUDIES, HIGH_COST_MEMBERS, MEDTECH_KPIS, MODALITY_MIX,
    PAYER_KPIS, PAYER_SEGMENTS, PROVIDER_KPIS, READMISSION_TIERS, STAR_MEASURES,
    type Q,
} from "@/lib/queries";
import { count, maskId, maskName, money, pct, type Row, rowsOf } from "@/lib/format";
import {
    parseSnapshotPayload, type KpiSeed, type SeriesSeed, type WorklistSeed,
} from "../../rayfin/functions/src/snapshot-payload";

export class SyncDeniedError extends Error {
    constructor() { super("The server denied sync access. Your access is read-only; the published snapshot is unchanged."); }
}

export class SyncConflictError extends Error {
    constructor(version: number) {
        super(`Another writer published version ${version} during this sync. Your displayed snapshot is unchanged; reload the snapshot before trying again.`);
    }
}

export async function getSyncAccess() {
    return getRayfinClient().functions.getSyncAccess.invoke();
}

/** Missing, blank and non-finite values must never become a plausible zero. */
function numeric(value: unknown): number {
    if ((typeof value !== "number" && typeof value !== "string") ||
        (typeof value === "string" && value.trim() === "")) {
        throw new Error("Gold returned a missing or invalid numeric value.");
    }
    const number = Number(value);
    if (!Number.isFinite(number) || number < 0) throw new Error("Gold returned an invalid numeric value.");
    return number;
}

async function runQuery(spec: Q, columns: string[], numericColumns: string[], singleRow = false): Promise<Row[]> {
    const result = await getFabricClient().semanticModel(spec.connection).query(spec.query, { bypassCache: true });
    if (result.status !== "success") {
        throw new Error(`${spec.connection}: ${result.status === "error" ? result.error.message : "no result"}`);
    }
    const table = result.table;
    if (!table || !Array.isArray(table.columns) || !Array.isArray(table.rows)) {
        throw new Error(`${spec.connection}: malformed query result.`);
    }
    const names = table.columns.map((column) => column.name.match(/\[([^\]]+)\]\s*$/)?.[1] ?? column.name);
    if (new Set(names).size !== names.length || columns.some((name) => !names.includes(name)) ||
        table.rows.some((row) => !Array.isArray(row) || row.length !== names.length)) {
        throw new Error(`${spec.connection}: query result has missing or malformed columns.`);
    }
    const rows = rowsOf(result);
    if (singleRow && rows.length !== 1) throw new Error(`${spec.connection}: the required KPI query did not return exactly one row.`);
    for (const row of rows) {
        for (const name of numericColumns) row[name] = numeric(row[name]);
    }
    return rows;
}

/** Authorization precedes all ten source queries, even if the UI already checked it. */
export async function syncFromGold() {
    const client = getRayfinClient();
    const access = await getSyncAccess();
    if (!access.canSync) throw new SyncDeniedError();

    const payerNumbers = ["totalPaid", "totalBilled", "leakage", "collectionRate", "denialRate", "totalClaims", "pmpm", "highCostMembers", "revenueAtRisk"];
    const providerNumbers = ["openGaps", "qualityRate", "stars", "avgRaf", "avgReadmit", "alos", "starOpp", "patientsMeasured"];
    const medtechNumbers = ["studies", "patients", "files", "perPatient", "perStudy", "avgAge"];
    const [payer, segments, highCost, provider, gaps, tiers, stars, medtech, modality, heaviest] = await Promise.all([
        runQuery(PAYER_KPIS, payerNumbers, payerNumbers, true),
        runQuery(PAYER_SEGMENTS, ["segment", "paid", "quality", "collection", "raf", "pmpm"], ["paid", "quality", "collection", "raf", "pmpm"]),
        runQuery(HIGH_COST_MEMBERS, ["member", "payer", "paid", "claims", "stopLoss"], ["paid", "claims"]),
        runQuery(PROVIDER_KPIS, providerNumbers, providerNumbers, true),
        runQuery(CARE_GAPS, ["gap_type", "gaps"], ["gaps"]),
        runQuery(READMISSION_TIERS, ["risk_tier", "encounters", "avgRisk"], ["encounters", "avgRisk"]),
        runQuery(STAR_MEASURES, ["measure_name", "rating"], ["rating"]),
        runQuery(MEDTECH_KPIS, medtechNumbers, medtechNumbers, true),
        runQuery(MODALITY_MIX, ["ModalityName", "Modality", "studies", "files", "patients"], ["studies", "files", "patients"]),
        runQuery(HEAVIEST_STUDIES, ["FullName", "AgeRange", "studies", "files"], ["studies", "files"]),
    ]);

    const p = payer[0];
    const pr = provider[0];
    const mt = medtech[0];
    const kpis: KpiSeed[] = [
        { lens: "payer", metricKey: "totalPaid", label: "Total paid", value: numeric(p.totalPaid), unit: "money", caption: `of ${money(p.totalBilled)} billed`, rank: 0, sourceModel: "popHealthGold" },
        { lens: "payer", metricKey: "collectionRate", label: "Collection rate", value: numeric(p.collectionRate), unit: "percent", caption: `denial rate ${pct(p.denialRate)}`, rank: 1, sourceModel: "popHealthGold" },
        { lens: "payer", metricKey: "pmpm", label: "PMPM", value: numeric(p.pmpm), unit: "money", caption: "per member per month", rank: 2, sourceModel: "popHealthGold" },
        { lens: "payer", metricKey: "revenueAtRisk", label: "Revenue at risk", value: numeric(p.revenueAtRisk), unit: "money", caption: `${count(p.highCostMembers)} high-cost members`, rank: 3, sourceModel: "popHealthGold" },
        { lens: "payer", metricKey: "leakage", label: "Revenue leakage", value: numeric(p.leakage), unit: "money", caption: `${count(p.totalClaims)} claims adjudicated`, rank: 4, sourceModel: "popHealthGold" },
        { lens: "provider", metricKey: "openGaps", label: "Open care gaps", value: numeric(pr.openGaps), unit: "count", caption: "actionable outreach list", rank: 0, sourceModel: "popHealthGold" },
        { lens: "provider", metricKey: "qualityRate", label: "Quality rate", value: numeric(pr.qualityRate), unit: "percent", caption: `${count(pr.patientsMeasured)} patients measured`, rank: 1, sourceModel: "popHealthGold" },
        { lens: "provider", metricKey: "avgReadmit", label: "Avg readmission risk", value: numeric(pr.avgReadmit), unit: "percent", caption: `ALOS ${numeric(pr.alos).toFixed(1)} days`, rank: 2, sourceModel: "popHealthGold" },
        { lens: "provider", metricKey: "avgRaf", label: "Average RAF", value: numeric(pr.avgRaf), unit: "ratio", caption: "risk-adjusted acuity", rank: 3, sourceModel: "popHealthGold" },
        { lens: "provider", metricKey: "stars", label: "Overall stars", value: numeric(pr.stars), unit: "ratio", caption: `${count(pr.starOpp)} points of headroom`, rank: 4, sourceModel: "popHealthGold" },
        { lens: "medtech", metricKey: "studies", label: "Imaging studies", value: numeric(mt.studies), unit: "count", caption: `${count(mt.patients)} distinct patients`, rank: 0, sourceModel: "imagingGold" },
        { lens: "medtech", metricKey: "files", label: "DICOM instances", value: numeric(mt.files), unit: "count", caption: `${numeric(mt.perStudy).toFixed(0)} per study`, rank: 1, sourceModel: "imagingGold" },
        { lens: "medtech", metricKey: "perPatient", label: "Studies per patient", value: numeric(mt.perPatient), unit: "ratio", caption: "fleet utilization", rank: 2, sourceModel: "imagingGold" },
        { lens: "medtech", metricKey: "avgAge", label: "Average patient age", value: numeric(mt.avgAge), unit: "ratio", caption: "imaged cohort", rank: 3, sourceModel: "imagingGold" },
    ];
    const series: SeriesSeed[] = [
        ...segments.map((r, i): SeriesSeed => ({
            lens: "payer" as const, series: "payerSegment", label: String(r.segment ?? "—"),
            value: numeric(r.paid), unit: "money", rank: i,
            detail: `collection ${pct(r.collection)} · quality ${pct(r.quality)} · RAF ${numeric(r.raf).toFixed(2)}`,
        })),
        ...gaps.map((r, i): SeriesSeed => ({
            lens: "provider" as const, series: "careGap", label: String(r.gap_type ?? "Unknown"),
            value: numeric(r.gaps), unit: "count", rank: i,
        })),
        ...tiers.map((r, i): SeriesSeed => ({
            lens: "provider" as const, series: "riskTier", label: String(r.risk_tier ?? "—"),
            value: numeric(r.encounters), unit: "count", rank: i, detail: `avg risk ${pct(r.avgRisk)}`,
        })),
        ...stars.map((r, i): SeriesSeed => ({
            lens: "provider" as const, series: "starMeasure", label: String(r.measure_name ?? "—"),
            value: numeric(r.rating), unit: "ratio", rank: i,
        })),
        ...modality.map((r, i): SeriesSeed => ({
            lens: "medtech" as const, series: "modality", label: String(r.ModalityName ?? r.Modality ?? "—"),
            value: numeric(r.studies), unit: "count", rank: i,
            detail: `${count(r.files)} instances · ${count(r.patients)} patients`,
        })),
    ];
    const worklist: WorklistSeed[] = [
        ...highCost.map((r, i): WorklistSeed => {
            if (typeof r.stopLoss !== "boolean" && r.stopLoss !== 0 && r.stopLoss !== 1) {
                throw new Error("Gold returned a missing or invalid stop-loss flag.");
            }
            return {
                lens: "payer" as const, kind: "highCostMember", subject: maskId(r.member),
                segment: String(r.payer ?? "—"), primaryValue: numeric(r.paid), primaryUnit: "money",
                secondaryValue: numeric(r.claims), secondaryUnit: "count", flagged: Boolean(r.stopLoss), rank: i,
            };
        }),
        ...heaviest.map((r, i): WorklistSeed => ({
            lens: "medtech" as const, kind: "heavyAcquisition", subject: maskName(r.FullName),
            segment: String(r.AgeRange ?? "—"), primaryValue: numeric(r.files), primaryUnit: "count",
            secondaryValue: numeric(r.studies), secondaryUnit: "count", rank: i,
        })),
    ];
    const payloadJson = JSON.stringify({ schemaVersion: 1, kpis, series, worklist });
    parseSnapshotPayload(payloadJson);
    const output = await client.functions.publishSnapshot.invoke({ payloadJson, expectedVersion: access.version });
    if (output.status === "denied") throw new SyncDeniedError();
    if (output.status === "conflict") throw new SyncConflictError(output.version);
    if (output.status !== "published") throw new Error("The server did not confirm publication. The displayed snapshot is unchanged.");
    return output;
}
