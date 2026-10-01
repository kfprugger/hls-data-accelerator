import { describe, expect, it } from 'vitest';
import { parseSnapshotPayload, validateExpectedVersion, type SnapshotPayload } from './snapshot-payload';

function snapshot(): SnapshotPayload {
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

function parse(value: unknown): SnapshotPayload {
    return parseSnapshotPayload(JSON.stringify(value));
}

describe('complete atomic snapshot boundary', () => {
    it('preserves legitimate zero metrics and empty non-KPI result sets', () => {
        const input = snapshot();
        input.series = [];
        input.worklist = [];
        expect(parse(input)).toEqual(input);
    });

    it('does not accept a partial lens or duplicate metric as a whole publication', () => {
        const input = snapshot();
        input.kpis.pop();
        expect(() => parse(input)).toThrow();
        input.kpis.push({ ...input.kpis[0], rank: 99 });
        expect(() => parse(input)).toThrow();
    });

    it.each([null, '42', -1, Infinity, NaN, 9_007_199_254_740_992])('rejects missing, coerced, or invalid numeric values: %s', (value) => {
        const input = snapshot();
        (input.kpis[0] as unknown as Record<string, unknown>).value = value;
        expect(() => parse(input)).toThrow();
    });

    it('rejects missing metric values instead of manufacturing a zero', () => {
        const input = snapshot();
        delete (input.kpis[0] as Partial<typeof input.kpis[number]>).value;
        expect(() => parse(input)).toThrow();
    });

    it('rejects fractional counts and out-of-range percentages', () => {
        const input = snapshot();
        input.kpis[5].value = 1.5;
        expect(() => parse(input)).toThrow();
        input.kpis[5].value = 1;
        input.kpis[1].value = 1.01;
        expect(() => parse(input)).toThrow();
    });

    it('rejects source, unit, or lens substitution', () => {
        const input = snapshot();
        input.kpis[0].sourceModel = 'imagingGold';
        expect(() => parse(input)).toThrow();
        input.kpis[0].sourceModel = 'popHealthGold';
        input.series[0].lens = 'payer';
        expect(() => parse(input)).toThrow();
    });

    it('rejects colliding ranks in a panel but permits rank reuse across panels', () => {
        const input = snapshot();
        expect(parse(input).worklist.map((row) => row.rank)).toEqual([0, 0]);
        input.worklist.push({ ...input.worklist[0], subject: 'xyz…9999' });
        expect(() => parse(input)).toThrow();
    });

    it.each(['1234', '0123456789012345', 'Emanuel Schoen', 'abcde…1234'])('rejects unmasked or overexposed member identifiers: %s', (subject) => {
        const input = snapshot();
        input.worklist[0].subject = subject;
        expect(() => parse(input)).toThrow();
    });

    it.each(['…', '…1234', '—'])('accepts completely masked short or absent identifiers: %s', (subject) => {
        const input = snapshot();
        input.worklist[0].subject = subject;
        expect(parse(input).worklist[0].subject).toBe(subject);
    });

    it('rejects raw names and incomplete secondary measures', () => {
        const input = snapshot();
        input.worklist[1].subject = 'Alice Brown';
        expect(() => parse(input)).toThrow();
        input.worklist[1].subject = 'A. B.';
        delete input.worklist[0].secondaryUnit;
        expect(() => parse(input)).toThrow();
    });

    it('rejects undeclared payload fields, including caller-supplied identity', () => {
        expect(() => parse({ ...snapshot(), publisherId: 'other-user' })).toThrow();
        const input = snapshot();
        Object.assign(input.worklist[0], { rawMemberId: 'raw-identifier' });
        expect(() => parse(input)).toThrow();
    });

    it('does not echo rejected patient or member values into the failure message', () => {
        const input = snapshot();
        input.worklist[1].subject = 'Private Person';
        try { parse(input); throw new Error('Expected rejection'); }
        catch (error) {
            expect(String(error)).toContain('subject must be masked');
            expect(String(error)).not.toContain('Private Person');
        }
    });

    it.each([-1, 1.5, NaN, Infinity, 2_147_483_647])('rejects invalid compare-and-swap versions: %s', (version) => {
        expect(() => validateExpectedVersion(version)).toThrow();
    });
});
