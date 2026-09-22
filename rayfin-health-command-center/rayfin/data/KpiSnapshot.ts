import { entity, authenticated, uuid, text, decimal, int, date, set } from '@microsoft/rayfin-core';

/**
 * A headline figure for one lens. Written by the Gold sync and read back by
 * the KPI tiles, so the dashboard renders from the app database rather than
 * re-querying the semantic model on every mount.
 */
@entity('KpiSnapshot')
@authenticated('*')
export class KpiSnapshot {
    @uuid() id!: string;

    @set('payer', 'provider', 'medtech')
    lens!: 'payer' | 'provider' | 'medtech';

    /** Stable key the UI looks up, e.g. "totalPaid". */
    @text({ max: 64 }) metricKey!: string;

    @text({ max: 64 }) label!: string;

    @decimal() value!: number;

    /** money | percent | count | ratio — drives client-side formatting. */
    @text({ max: 16 }) unit!: string;

    @text({ max: 120, optional: true }) caption?: string;

    /** Display order within the lens. */
    @int() rank!: number;

    @text({ max: 64 }) sourceModel!: string;

    @date() capturedAt!: Date;
}
