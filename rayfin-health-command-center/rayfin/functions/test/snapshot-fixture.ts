import type { SnapshotPayload } from '../src/snapshot-payload';

/** A complete, valid synthetic snapshot: all 14 KPIs, masked worklist subjects, no real data. */
export function snapshot(): SnapshotPayload {
    const definitions = [
        ['payer', 'totalPaid', 'money'], ['payer', 'collectionRate', 'percent'],
        ['payer', 'pmpm', 'money'], ['payer', 'revenueAtRisk', 'money'], ['payer', 'leakage', 'money'],
        ['provider', 'openGaps', 'count'], ['provider', 'qualityRate', 'percent'],
        ['provider', 'avgReadmit', 'percent'], ['provider', 'avgRaf', 'ratio'], ['provider', 'stars', 'ratio'],
        ['medtech', 'studies', 'count'], ['medtech', 'files', 'count'],
        ['medtech', 'perPatient', 'ratio'], ['medtech', 'avgAge', 'ratio'],
    ] as const;
    return {
        schemaVersion: 1,
        kpis: definitions.map(([lens, metricKey, unit], rank) => ({
            lens, metricKey, unit, label: metricKey, value: 0, rank,
            sourceModel: lens === 'medtech' ? 'imagingGold' : 'popHealthGold',
        })),
        series: [{ lens: 'medtech', series: 'modality', label: 'CT', value: 8, unit: 'count', rank: 0 }],
        worklist: [
            { lens: 'payer', kind: 'highCostMember', subject: 'abcd…5678', primaryValue: 250, primaryUnit: 'money', secondaryValue: 3, secondaryUnit: 'count', rank: 0 },
            { lens: 'medtech', kind: 'heavyAcquisition', subject: 'A. B.', primaryValue: 8, primaryUnit: 'count', rank: 0 },
        ],
    };
}
