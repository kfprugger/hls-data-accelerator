import { entity, authenticated, uuid, text, decimal, boolean, int, date, set } from '@microsoft/rayfin-core';

/**
 * Legacy masked worklist table from the pre-publication design. Registered
 * read-only so schema apply never drops the retained table; the dashboard reads
 * PublishedSnapshot.
 */
@entity('WorklistRow')
@authenticated('read')
export class WorklistRow {
    @uuid() id!: string;

    @set('payer', 'provider', 'medtech')
    lens!: 'payer' | 'provider' | 'medtech';

    @text({ max: 32 }) kind!: string;

    @text({ max: 64 }) subject!: string;

    @text({ max: 64, optional: true }) segment?: string;

    @decimal() primaryValue!: number;

    @text({ max: 16 }) primaryUnit!: string;

    @decimal({ optional: true }) secondaryValue?: number;

    @text({ max: 16, optional: true }) secondaryUnit?: string;

    @boolean({ optional: true }) flagged?: boolean;

    @int() rank!: number;

    @date() capturedAt!: Date;
}
