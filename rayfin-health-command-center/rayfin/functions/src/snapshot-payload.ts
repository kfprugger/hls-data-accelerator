export type Lens = 'payer' | 'provider' | 'medtech';
export type Unit = 'money' | 'percent' | 'count' | 'ratio';

export interface KpiSeed {
    lens: Lens; metricKey: string; label: string; value: number;
    unit: Unit; caption?: string; rank: number; sourceModel: string;
}
export interface SeriesSeed {
    lens: Lens; series: string; label: string; value: number;
    unit: Unit; detail?: string; rank: number;
}
export interface WorklistSeed {
    lens: Lens; kind: string; subject: string; segment?: string;
    primaryValue: number; primaryUnit: Unit;
    secondaryValue?: number; secondaryUnit?: Unit;
    flagged?: boolean; rank: number;
}
export interface SnapshotPayload {
    schemaVersion: 1;
    kpis: KpiSeed[];
    series: SeriesSeed[];
    worklist: WorklistSeed[];
}

// Shared with the browser; this module deliberately has no server/runtime imports.
const metrics: Record<string, readonly [Lens, Unit]> = {
    totalPaid: ['payer', 'money'], collectionRate: ['payer', 'percent'],
    pmpm: ['payer', 'money'], revenueAtRisk: ['payer', 'money'], leakage: ['payer', 'money'],
    openGaps: ['provider', 'count'], qualityRate: ['provider', 'percent'],
    avgReadmit: ['provider', 'percent'], avgRaf: ['provider', 'ratio'], stars: ['provider', 'ratio'],
    studies: ['medtech', 'count'], files: ['medtech', 'count'],
    perPatient: ['medtech', 'ratio'], avgAge: ['medtech', 'ratio'],
};
const seriesKinds: Record<string, readonly [Lens, Unit]> = {
    payerSegment: ['payer', 'money'], careGap: ['provider', 'count'],
    riskTier: ['provider', 'count'], starMeasure: ['provider', 'ratio'], modality: ['medtech', 'count'],
};
const maxRows = 1000;
export const MAX_PAYLOAD_LENGTH = 1_000_000;

function invalid(path: string): never {
    // Never include unvalidated values (including raw identifiers) in errors.
    throw new Error(`Invalid snapshot: ${path}`);
}
function object(value: unknown, path: string, required: string[], optional: string[] = []): Record<string, unknown> {
    if (value === null || typeof value !== 'object' || Array.isArray(value)) invalid(path);
    const row = value as Record<string, unknown>;
    if (required.some((key) => !Object.hasOwn(row, key)) ||
        Object.keys(row).some((key) => !required.includes(key) && !optional.includes(key))) invalid(path);
    return row;
}
function text(value: unknown, max: number, path: string): asserts value is string {
    if (typeof value !== 'string' || !value.trim() || value.length > max || /[\u0000-\u001f\u007f]/.test(value)) invalid(path);
}
function numeric(value: unknown, path: string, unit?: unknown): asserts value is number {
    if (typeof value !== 'number' || !Number.isFinite(value) || value < 0 || value > Number.MAX_SAFE_INTEGER ||
        (unit === 'count' && !Number.isSafeInteger(value)) || (unit === 'percent' && value > 1)) invalid(path);
}
function rank(value: unknown, path: string): asserts value is number {
    if (typeof value !== 'number' || !Number.isInteger(value) || value < 0 || value >= maxRows) invalid(path);
}
function optionalText(row: Record<string, unknown>, key: string, max: number, path: string): void {
    if (Object.hasOwn(row, key)) text(row[key], max, `${path}.${key}`);
}
function unique(seen: Set<string>, key: string, path: string): void {
    if (seen.has(key)) invalid(`${path}: duplicate key or rank`);
    seen.add(key);
}

export function parseSnapshotPayload(payloadJson: string): SnapshotPayload {
    if (typeof payloadJson !== 'string' || payloadJson.length > MAX_PAYLOAD_LENGTH) invalid('payload size');
    let value: unknown;
    try { value = JSON.parse(payloadJson); } catch { invalid('JSON'); }
    const root = object(value, 'document', ['schemaVersion', 'kpis', 'series', 'worklist']);
    if (root.schemaVersion !== 1) invalid('schemaVersion');
    for (const key of ['kpis', 'series', 'worklist']) {
        if (!Array.isArray(root[key]) || root[key].length > maxRows) invalid(key);
    }
    const kpis = root.kpis as unknown[];
    const series = root.series as unknown[];
    const worklist = root.worklist as unknown[];
    if (kpis.length !== Object.keys(metrics).length) invalid('kpis: incomplete lenses');
    const metricKeys = new Set<string>();
    const ranks = new Set<string>();
    kpis.forEach((item, index) => {
        const path = `kpis[${index}]`;
        const row = object(item, path, ['lens', 'metricKey', 'label', 'value', 'unit', 'rank', 'sourceModel'], ['caption']);
        text(row.metricKey, 64, `${path}.metricKey`);
        const expected = Object.hasOwn(metrics, row.metricKey) ? metrics[row.metricKey] : undefined;
        if (!expected || row.lens !== expected[0] || row.unit !== expected[1] ||
            row.sourceModel !== (row.lens === 'medtech' ? 'imagingGold' : 'popHealthGold')) invalid(path);
        text(row.label, 64, `${path}.label`);
        numeric(row.value, `${path}.value`, row.unit);
        optionalText(row, 'caption', 120, path);
        rank(row.rank, `${path}.rank`);
        unique(metricKeys, row.metricKey, path);
        unique(ranks, `kpi/${String(row.lens)}/${row.rank}`, path);
    });
    series.forEach((item, index) => {
        const path = `series[${index}]`;
        const row = object(item, path, ['lens', 'series', 'label', 'value', 'unit', 'rank'], ['detail']);
        text(row.series, 32, `${path}.series`);
        const expected = Object.hasOwn(seriesKinds, row.series) ? seriesKinds[row.series] : undefined;
        if (!expected || row.lens !== expected[0] || row.unit !== expected[1]) invalid(path);
        text(row.label, 160, `${path}.label`);
        numeric(row.value, `${path}.value`, row.unit);
        optionalText(row, 'detail', 200, path);
        rank(row.rank, `${path}.rank`);
        unique(ranks, `series/${row.series}/${row.rank}`, path);
    });
    worklist.forEach((item, index) => {
        const path = `worklist[${index}]`;
        const row = object(item, path, ['lens', 'kind', 'subject', 'primaryValue', 'primaryUnit', 'rank'],
            ['segment', 'secondaryValue', 'secondaryUnit', 'flagged']);
        const payer = row.kind === 'highCostMember';
        if ((!payer && row.kind !== 'heavyAcquisition') || row.lens !== (payer ? 'payer' : 'medtech') ||
            row.primaryUnit !== (payer ? 'money' : 'count')) invalid(path);
        text(row.subject, 64, `${path}.subject`);
        const masked = payer ? /^[A-Za-z0-9-]{0,4}…[A-Za-z0-9-]{0,4}$/ : /^[A-Z]\.(?: [A-Z]\.){0,7}$/;
        if (row.subject !== '—' && !masked.test(row.subject)) invalid(`${path}.subject must be masked`);
        optionalText(row, 'segment', 64, path);
        numeric(row.primaryValue, `${path}.primaryValue`, row.primaryUnit);
        if (Object.hasOwn(row, 'secondaryValue') !== Object.hasOwn(row, 'secondaryUnit')) invalid(`${path}.secondaryValue`);
        if (Object.hasOwn(row, 'secondaryValue')) {
            if (row.secondaryUnit !== 'count') invalid(`${path}.secondaryUnit`);
            numeric(row.secondaryValue, `${path}.secondaryValue`, row.secondaryUnit);
        }
        if (Object.hasOwn(row, 'flagged') && typeof row.flagged !== 'boolean') invalid(`${path}.flagged`);
        rank(row.rank, `${path}.rank`);
        unique(ranks, `worklist/${String(row.kind)}/${row.rank}`, path);
    });
    return value as SnapshotPayload;
}

export function validateExpectedVersion(version: number): void {
    if (!Number.isInteger(version) || version < 0 || version >= 2_147_483_647) {
        throw new Error('Invalid expected publication version');
    }
}
