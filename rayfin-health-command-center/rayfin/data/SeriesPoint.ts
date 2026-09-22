import { entity, authenticated, uuid, text, decimal, int, date, set } from '@microsoft/rayfin-core';

/**
 * One point in a ranked series — a payer segment, a care-gap measure, a
 * readmission tier, a Stars measure or an imaging modality. Keeping them in a
 * single table lets the sync write every bar chart in one pass while the
 * `series` discriminator keeps the panels separate.
 */
@entity('SeriesPoint')
@authenticated('*')
export class SeriesPoint {
    @uuid() id!: string;

    @set('payer', 'provider', 'medtech')
    lens!: 'payer' | 'provider' | 'medtech';

    /** payerSegment | careGap | riskTier | starMeasure | modality */
    @text({ max: 32 }) series!: string;

    @text({ max: 160 }) label!: string;

    @decimal() value!: number;

    @text({ max: 16 }) unit!: string;

    /** Secondary figure rendered beside the bar, already formatted. */
    @text({ max: 200, optional: true }) detail?: string;

    @int() rank!: number;

    @date() capturedAt!: Date;
}
