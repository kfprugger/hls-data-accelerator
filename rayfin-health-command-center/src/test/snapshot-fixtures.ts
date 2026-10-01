import type { SnapshotPayload } from "../../rayfin/functions/src/snapshot-payload";
import {
    PAYER_KPIS, PAYER_SEGMENTS, HIGH_COST_MEMBERS, PROVIDER_KPIS, CARE_GAPS,
    READMISSION_TIERS, STAR_MEASURES, MEDTECH_KPIS, MODALITY_MIX, HEAVIEST_STUDIES,
} from "@/lib/queries";

export function publication(version = 1) {
    const payload: SnapshotPayload = {
        schemaVersion: 1,
        kpis: [
            { lens: "payer", metricKey: "totalPaid", unit: "money", rank: 0 },
            { lens: "payer", metricKey: "collectionRate", unit: "percent", rank: 1 },
            { lens: "payer", metricKey: "pmpm", unit: "money", rank: 2 },
            { lens: "payer", metricKey: "revenueAtRisk", unit: "money", rank: 3 },
            { lens: "payer", metricKey: "leakage", unit: "money", rank: 4 },
            { lens: "provider", metricKey: "openGaps", unit: "count", rank: 0 },
            { lens: "provider", metricKey: "qualityRate", unit: "percent", rank: 1 },
            { lens: "provider", metricKey: "avgReadmit", unit: "percent", rank: 2 },
            { lens: "provider", metricKey: "avgRaf", unit: "ratio", rank: 3 },
            { lens: "provider", metricKey: "stars", unit: "ratio", rank: 4 },
            { lens: "medtech", metricKey: "studies", unit: "count", rank: 0 },
            { lens: "medtech", metricKey: "files", unit: "count", rank: 1 },
            { lens: "medtech", metricKey: "perPatient", unit: "ratio", rank: 2 },
            { lens: "medtech", metricKey: "avgAge", unit: "ratio", rank: 3 },
        ].map((kpi) => ({
            ...kpi, label: kpi.metricKey, value: kpi.unit === "percent" ? 0.5 : version * 100,
            sourceModel: kpi.lens === "medtech" ? "imagingGold" : "popHealthGold",
        })) as SnapshotPayload["kpis"],
        series: [{ lens: "provider", series: "careGap", label: "Synthetic measure", value: version * 10, unit: "count", rank: 0 }],
        worklist: [{ lens: "payer", kind: "highCostMember", subject: "demo…0001", primaryValue: version * 1000, primaryUnit: "money", rank: 0 }],
    };
    return {
        id: "00000000-0000-0000-0000-000000000001", version,
        payloadJson: JSON.stringify(payload), capturedAt: "2026-09-29T12:00:00.000Z",
        publisherId: "synthetic-writer", syncRunId: "00000000-0000-0000-0000-000000000002",
        sources: "popHealthGold,imagingGold",
    };
}

function table(row: Record<string, unknown>) {
    return { status: "success", table: { columns: Object.keys(row).map((name) => ({ name: `[${name}]` })), rows: [Object.values(row)] } };
}

export function goldResults() {
    return new Map([
        [PAYER_KPIS.query, table({ totalPaid: 1000, totalBilled: 1200, leakage: 200, collectionRate: 0.8, denialRate: 0.1, totalClaims: 10, pmpm: 20, highCostMembers: 1, revenueAtRisk: 30 })],
        [PAYER_SEGMENTS.query, table({ segment: "Synthetic segment", paid: 1000, quality: 0.5, collection: 0.8, raf: 1.1, pmpm: 20 })],
        [HIGH_COST_MEMBERS.query, table({ member: "synthetic-member-12345678", payer: "Synthetic payer", paid: 1000, claims: 2, stopLoss: true })],
        [PROVIDER_KPIS.query, table({ openGaps: 10, qualityRate: 0.5, stars: 4, avgRaf: 1.1, avgReadmit: 0.1, alos: 2, starOpp: 1, patientsMeasured: 20 })],
        [CARE_GAPS.query, table({ gap_type: "Synthetic gap", gaps: 10 })],
        [READMISSION_TIERS.query, table({ risk_tier: "Low", encounters: 2, avgRisk: 0.1 })],
        [STAR_MEASURES.query, table({ measure_name: "Synthetic measure", rating: 4 })],
        [MEDTECH_KPIS.query, table({ studies: 3, patients: 2, files: 6, perPatient: 1.5, perStudy: 2, avgAge: 40 })],
        [MODALITY_MIX.query, table({ ModalityName: "Computed tomography", Modality: "CT", studies: 3, files: 6, patients: 2 })],
        [HEAVIEST_STUDIES.query, table({ FullName: "Synthetic Person", AgeRange: "40-49", studies: 3, files: 6 })],
    ]);
}
