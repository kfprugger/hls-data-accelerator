import { entity, authenticated, uuid, text, decimal, int, date, set } from '@microsoft/rayfin-core';

/**
 * Legacy ranked-series table from the pre-publication design. Registered
 * read-only so schema apply never drops the retained table; the dashboard reads
 * PublishedSnapshot.
 */
@entity('SeriesPoint')
@authenticated('read')
export class SeriesPoint {
    @uuid() id!: string;

    @set('payer', 'provider', 'medtech')
    lens!: 'payer' | 'provider' | 'medtech';

    @text({ max: 32 }) series!: string;

    @text({ max: 160 }) label!: string;

    @decimal() value!: number;

    @text({ max: 16 }) unit!: string;

    @text({ max: 200, optional: true }) detail?: string;

    @int() rank!: number;

    @date() capturedAt!: Date;
}
