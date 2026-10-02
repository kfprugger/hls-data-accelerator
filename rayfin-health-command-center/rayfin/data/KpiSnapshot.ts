import { entity, authenticated, uuid, text, decimal, int, date, set } from '@microsoft/rayfin-core';

/**
 * Legacy per-row KPI table from the pre-publication design. The dashboard reads
 * PublishedSnapshot; this entity stays registered read-only so schema apply never
 * drops the retained table, and no client can write to it.
 */
@entity('KpiSnapshot')
@authenticated('read')
export class KpiSnapshot {
    @uuid() id!: string;

    @set('payer', 'provider', 'medtech')
    lens!: 'payer' | 'provider' | 'medtech';

    @text({ max: 64 }) metricKey!: string;

    @text({ max: 64 }) label!: string;

    @decimal() value!: number;

    @text({ max: 16 }) unit!: string;

    @text({ max: 120, optional: true }) caption?: string;

    @int() rank!: number;

    @text({ max: 64 }) sourceModel!: string;

    @date() capturedAt!: Date;
}
